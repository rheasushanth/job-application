"""Ingestion: RawJob → enriched → deduplicated → persisted Job rows.

Enrichment is where a posting becomes matchable: skills are split into
mandatory vs preferred, experience and education requirements are parsed out of
the prose, and salary/location/work-mode are normalised. None of it is
invented — every field is either present in the feed or derived from the
posting's own text, and unknowns stay unknown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Job
from app.services.matching.embeddings import embed_texts
from app.services.matching.skills import extract_skills_from_text, split_requirements
from app.services.normalize import (
    content_hash,
    infer_experience_level,
    infer_job_type,
    infer_work_mode,
    normalise_company,
    normalise_title,
    parse_education_requirement,
    parse_experience_years,
    parse_location,
    parse_salary,
)
from app.services.sources.base import RawJob

logger = logging.getLogger(__name__)

# Near-duplicate thresholds for cross-portal matching (tier 3).
TITLE_SIMILARITY = 92
COMPANY_SIMILARITY = 90


@dataclass
class IngestStats:
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0

    def merge(self, other: "IngestStats") -> None:
        self.fetched += other.fetched
        self.inserted += other.inserted
        self.updated += other.updated
        self.duplicates += other.duplicates


def enrich(raw: RawJob) -> dict:
    """Turn a RawJob into the column values for a Job row."""
    description = raw.description or ""
    title = raw.title.strip()

    # --- location -------------------------------------------------------
    location = parse_location(raw.location_raw)
    city = raw.city or location.get("city")
    state = raw.state or location.get("state")
    country = raw.country or location.get("country")

    # --- work mode / job type -------------------------------------------
    work_mode, is_remote = infer_work_mode(
        location_raw=raw.location_raw,
        description=description,
        tags=raw.tags,
        is_remote=raw.is_remote,
    )
    if raw.work_mode:
        work_mode = raw.work_mode
        is_remote = work_mode == "remote"

    job_type = infer_job_type(
        title=title, raw_type=raw.job_type, tags=raw.tags, description=description
    )

    # --- requirements ----------------------------------------------------
    min_years, max_years = raw.experience_min_years, raw.experience_max_years
    if min_years is None:
        min_years, max_years = parse_experience_years(description, title)

    experience_level = infer_experience_level(
        title=title,
        description=description,
        min_years=min_years,
        raw_level=raw.experience_level,
    )
    # An internship never carries a multi-year floor, whatever the prose says.
    if job_type == "internship" and (min_years or 0) > 1:
        min_years, max_years = 0.0, 1.0

    education = raw.education_requirement
    if education is None:
        education = parse_education_requirement(description)

    required_skills, preferred_skills = split_requirements(description)
    # Tags and the title often name the stack more reliably than the prose.
    tag_skills = extract_skills_from_text(" ".join(raw.tags or []) + " " + title)
    for skill in tag_skills:
        if skill not in required_skills and skill not in preferred_skills:
            required_skills.append(skill)

    all_skills: list[str] = []
    for skill in required_skills + preferred_skills:
        if skill not in all_skills:
            all_skills.append(skill)

    # --- salary ----------------------------------------------------------
    salary: dict = {}
    if raw.salary_min is not None or raw.salary_max is not None:
        period = (raw.salary_period or "year").lower()
        multiplier = {
            "year": 1.0, "yearly": 1.0, "annual": 1.0,
            "month": 12.0, "monthly": 12.0,
            "week": 52.0, "weekly": 52.0,
            "day": 260.0, "daily": 260.0,
            "hour": 2080.0, "hourly": 2080.0,
        }.get(period, 1.0)
        salary = {
            "salary_min": round(float(raw.salary_min) * multiplier, 2) if raw.salary_min else None,
            "salary_max": round(float(raw.salary_max) * multiplier, 2) if raw.salary_max else None,
            "salary_currency": raw.salary_currency,
            "salary_period": raw.salary_period,
            "salary_raw": raw.salary_raw,
        }
    elif raw.salary_raw:
        salary = parse_salary(raw.salary_raw)

    location_for_hash = city or country or (raw.location_raw or "")

    return {
        "source": raw.source,
        "source_job_id": raw.source_job_id[:200],
        "title": title[:400],
        "company": raw.company.strip()[:300],
        "company_normalised": normalise_company(raw.company)[:300],
        "description": description,
        "description_html": raw.description_html,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "all_skills": all_skills,
        "education_requirement": education or {},
        "experience_min_years": min_years,
        "experience_max_years": max_years,
        "experience_level": experience_level,
        "location_raw": (raw.location_raw or None),
        "city": city,
        "state": state,
        "country": country,
        "is_remote": is_remote,
        "work_mode": work_mode,
        "job_type": job_type,
        "salary_min": salary.get("salary_min"),
        "salary_max": salary.get("salary_max"),
        "salary_currency": salary.get("salary_currency"),
        "salary_period": salary.get("salary_period"),
        "salary_raw": salary.get("salary_raw") or raw.salary_raw,
        "posted_at": raw.posted_at,
        "deadline_at": raw.deadline_at,
        "apply_url": raw.apply_url,
        "content_hash": content_hash(title, raw.company, location_for_hash),
    }


def ingest_jobs(db: Session, raws: Iterable[RawJob]) -> IngestStats:
    """Enrich, deduplicate and persist. Returns counts."""
    stats = IngestStats()
    pending: list[dict] = []

    for raw in raws:
        stats.fetched += 1
        try:
            pending.append(enrich(raw))
        except Exception:
            logger.exception("Failed to enrich job %s/%s", raw.source, raw.source_job_id)

    if not pending:
        return stats

    # Tier 1: same posting re-fetched from the same source.
    new_rows: list[Job] = []
    # One discovery run issues several keyword queries per source, so the same
    # posting routinely arrives more than once inside a single batch. Those
    # repeats are not yet flushed, so the DB lookup below cannot see them —
    # track the keys claimed in this batch separately.
    claimed: dict[tuple[str, str], Job] = {}

    for values in pending:
        key = (values["source"], values["source_job_id"])

        in_batch = claimed.get(key)
        if in_batch is not None:
            stats.updated += 1
            continue

        existing = db.scalars(
            select(Job).where(Job.source == key[0], Job.source_job_id == key[1])
        ).first()
        if existing is not None:
            _refresh(existing, values)
            stats.updated += 1
            continue

        job = Job(**values, first_seen_at=utcnow(), last_seen_at=utcnow(), is_active=True)
        db.add(job)
        new_rows.append(job)
        claimed[key] = job

    db.flush()

    # Tiers 2 and 3 run over the newly inserted rows.
    stats.duplicates = _deduplicate(db, new_rows)
    stats.inserted = len(new_rows) - stats.duplicates

    _embed_missing(db, new_rows)
    db.flush()
    return stats


def _refresh(job: Job, values: dict) -> None:
    """Update a known posting in place; keep first_seen_at."""
    job.last_seen_at = utcnow()
    job.is_active = True
    for field in (
        "title", "company", "company_normalised", "description", "description_html",
        "required_skills", "preferred_skills", "all_skills", "education_requirement",
        "experience_min_years", "experience_max_years", "experience_level",
        "location_raw", "city", "state", "country", "is_remote", "work_mode",
        "job_type", "salary_min", "salary_max", "salary_currency", "salary_period",
        "salary_raw", "deadline_at", "apply_url", "content_hash",
    ):
        setattr(job, field, values[field])
    if values.get("posted_at"):
        job.posted_at = values["posted_at"]


def _deduplicate(db: Session, new_rows: list[Job]) -> int:
    """Link duplicates to a canonical row. Returns the number marked."""
    marked = 0

    for job in new_rows:
        if job.duplicate_of_id is not None:
            continue

        # Tier 2: exact content hash on another source.
        canonical = db.scalars(
            select(Job)
            .where(
                Job.content_hash == job.content_hash,
                Job.id != job.id,
                Job.duplicate_of_id.is_(None),
            )
            .order_by(Job.first_seen_at.asc())
        ).first()

        # Tier 3: fuzzy match within the same normalised company.
        if canonical is None and job.company_normalised:
            siblings = db.scalars(
                select(Job)
                .where(
                    Job.company_normalised == job.company_normalised,
                    Job.id != job.id,
                    Job.duplicate_of_id.is_(None),
                )
                .limit(80)
            ).all()
            own_title = normalise_title(job.title)
            for sibling in siblings:
                if not own_title:
                    break
                title_score = fuzz.token_set_ratio(own_title, normalise_title(sibling.title))
                if title_score < TITLE_SIMILARITY:
                    continue
                company_score = fuzz.token_set_ratio(
                    job.company_normalised, sibling.company_normalised
                )
                if company_score < COMPANY_SIMILARITY:
                    continue
                canonical = sibling
                break

        if canonical is None:
            continue

        # Keep the earliest-seen row canonical so links stay stable.
        job.duplicate_of_id = canonical.id
        job.is_active = False
        seen = list(canonical.also_seen_on or [])
        if job.source not in seen and job.source != canonical.source:
            seen.append(job.source)
            canonical.also_seen_on = seen
        marked += 1

    return marked


def _embed_missing(db: Session, jobs: list[Job]) -> None:
    """Embed the canonical new jobs in one batch."""
    targets = [j for j in jobs if j.duplicate_of_id is None and not j.embedding]
    if not targets:
        return
    texts = [job_embedding_text(j) for j in targets]
    vectors, model = embed_texts(texts)
    for job, vector in zip(targets, vectors):
        job.embedding = vector
        job.embedding_model = model


def job_embedding_text(job: Job) -> str:
    """The text that represents a job in embedding space.

    Title and skills are repeated ahead of the description because they carry
    the most matching signal and descriptions are often padded with boilerplate
    about company culture and benefits.
    """
    parts = [job.title, job.title]
    if job.all_skills:
        parts.append("Skills: " + ", ".join(job.all_skills[:40]))
    if job.experience_level and job.experience_level != "unspecified":
        parts.append(f"Level: {job.experience_level}")
    if job.job_type and job.job_type != "unspecified":
        parts.append(f"Type: {job.job_type.replace('_', ' ')}")
    parts.append((job.description or "")[:4000])
    return "\n".join(p for p in parts if p)
