"""Scoring orchestration: load profile + jobs, score, persist JobMatch rows.

Scoring is incremental. A match is recomputed only when something that affects
it changed — the job's content hash, the profile revision, or the user's weight
profile — which is tracked by storing all three on the row.
"""

from __future__ import annotations

import logging
import uuid
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import CandidateProfile, Job, JobMatch
from app.services.matching.scorer import CandidateInput, JobInput, ScoreResult, score_job
from app.services.matching.weights import get_user_weights

logger = logging.getLogger(__name__)

SCORE_BATCH = 400


def candidate_input_from_profile(profile: CandidateProfile) -> CandidateInput:
    skills = list(profile.skills or [])
    return CandidateInput(
        skills=skills,
        programming_languages=list(profile.programming_languages or []),
        frameworks=list(profile.frameworks or []),
        tools=list(profile.tools or []),
        projects=list(profile.projects or []),
        experience=list(profile.experience or []),
        total_experience_months=profile.total_experience_months or 0,
        internship_months=profile.internship_months or 0,
        highest_degree_level=profile.highest_degree_level or 0,
        field_of_study=profile.field_of_study,
        seniority=profile.seniority or "fresher",
        embedding=profile.embedding,
        project_embeddings=_stored_embeddings(profile, "project_embeddings"),
        experience_embeddings=_stored_embeddings(profile, "experience_embeddings"),
    )


def _stored_embeddings(profile: CandidateProfile, key: str) -> list[list[float]] | None:
    """Per-item embeddings live alongside the items in the JSON column."""
    source = profile.projects if key == "project_embeddings" else profile.experience
    if not source:
        return None
    vectors: list[list[float]] = []
    for item in source:
        vector = item.get("_embedding") if isinstance(item, dict) else None
        vectors.append(vector or [])
    return vectors if any(vectors) else None


def job_input_from_job(job: Job) -> JobInput:
    return JobInput(
        title=job.title or "",
        company=job.company or "",
        description=job.description or "",
        required_skills=list(job.required_skills or []),
        preferred_skills=list(job.preferred_skills or []),
        education_requirement=dict(job.education_requirement or {}),
        experience_min_years=job.experience_min_years,
        experience_max_years=job.experience_max_years,
        experience_level=job.experience_level or "unspecified",
        job_type=job.job_type or "unspecified",
        embedding=job.embedding,
    )


def score_jobs_for_profile(
    db: Session,
    profile: CandidateProfile,
    *,
    job_ids: Sequence[uuid.UUID] | None = None,
    force: bool = False,
) -> int:
    """Compute/refresh matches for a profile. Returns the number written."""
    weights, weight_hash = get_user_weights(db, profile.user_id)
    candidate = candidate_input_from_profile(profile)

    existing_rows = {
        row.job_id: row
        for row in db.scalars(
            select(JobMatch).where(JobMatch.user_id == profile.user_id)
        ).all()
    }

    query = select(Job).where(Job.is_active.is_(True), Job.duplicate_of_id.is_(None))
    if job_ids:
        query = query.where(Job.id.in_(list(job_ids)))

    written = 0
    offset = 0
    while True:
        jobs = db.scalars(query.limit(SCORE_BATCH).offset(offset)).all()
        if not jobs:
            break
        offset += SCORE_BATCH

        for job in jobs:
            row = existing_rows.get(job.id)
            if row is not None and not force and _is_fresh(row, job, profile, weight_hash):
                continue
            try:
                result = score_job(candidate, job_input_from_job(job), weights)
            except Exception:
                logger.exception("Scoring failed for job %s", job.id)
                continue
            _persist(db, row, result, profile, job, weight_hash)
            written += 1

        db.flush()

    return written


def _is_fresh(
    row: JobMatch, job: Job, profile: CandidateProfile, weight_hash: str
) -> bool:
    return (
        row.job_content_hash == job.content_hash
        and row.profile_revision == profile.revision
        and row.weight_profile_hash == weight_hash
        and row.profile_id == profile.id
    )


def _persist(
    db: Session,
    row: JobMatch | None,
    result: ScoreResult,
    profile: CandidateProfile,
    job: Job,
    weight_hash: str,
) -> JobMatch:
    values = {
        "score": result.score,
        "raw_score": result.raw_score,
        "band": result.band,
        "eligibility_status": result.eligibility.status,
        "eligibility_multiplier": result.eligibility.multiplier,
        "semantic_similarity": result.semantic_similarity,
        "category_scores": {
            **result.category_scores,
            "_calculation": result.calculation,
            "_eligibility_checks": result.eligibility.checks,
            "_eligibility_warnings": result.eligibility.warnings,
        },
        "matched_skills": result.matched_skills,
        "missing_skills": result.missing_skills,
        "missing_mandatory_skills": result.missing_mandatory_skills,
        "extra_skills": result.extra_skills,
        "relevant_projects": result.relevant_projects,
        "relevant_experience": result.relevant_experience,
        "reasons": result.reasons,
        "blockers": result.eligibility.blockers,
        "recommendations": result.recommendations,
        "job_content_hash": job.content_hash,
        "profile_id": profile.id,
        "profile_revision": profile.revision,
        "weight_profile_hash": weight_hash,
        "computed_at": utcnow(),
    }

    if row is None:
        row = JobMatch(user_id=profile.user_id, job_id=job.id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
        # A changed score invalidates any cached prose explanation.
        row.explanation = None
        row.explanation_source = "template"
    return row


def invalidate_matches(db: Session, user_id: uuid.UUID) -> None:
    """Drop a user's matches so the next run recomputes from scratch."""
    rows = db.scalars(select(JobMatch).where(JobMatch.user_id == user_id)).all()
    for row in rows:
        db.delete(row)
    db.flush()


# ---------------------------------------------------------------------------
# LLM explanation (prose only — never the number)
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM = (
    "You explain job-match results to a candidate. You are given a match score that "
    "was already computed by a deterministic algorithm, along with its component "
    "scores. Never dispute, recompute or restate a different score. Explain in plain "
    "language why the candidate does or does not fit, grounded only in the supplied "
    "data. Be direct and specific. 120 words maximum, no preamble, no bullet lists."
)


async def generate_explanation(match: JobMatch, job: Job, profile: CandidateProfile) -> tuple[str, str]:
    """Return (explanation, source). Falls back to the template narrative."""
    from app.services import llm

    template = _template_explanation(match, job)
    if not llm.llm_available():
        return template, "template"

    matched = [m.get("skill") for m in (match.matched_skills or [])][:12]
    missing = [m.get("skill") for m in (match.missing_skills or [])][:12]
    categories = {
        key: value.get("raw")
        for key, value in (match.category_scores or {}).items()
        if not key.startswith("_") and isinstance(value, dict)
    }

    prompt = f"""Candidate:
- Level: {profile.seniority}
- Total experience: {profile.total_experience_months} months
- Field of study: {profile.field_of_study or "unknown"}
- Key skills: {", ".join((profile.skills or [])[:25])}

Job: {job.title} at {job.company}
- Type: {job.job_type}, level: {job.experience_level}, mode: {job.work_mode}
- Minimum experience: {job.experience_min_years if job.experience_min_years is not None else "not stated"} years

Algorithm output (authoritative — do not change these numbers):
- Final match score: {match.score}% ({match.band})
- Eligibility: {match.eligibility_status}
- Component scores (0-1): {categories}
- Skills matched: {matched}
- Skills missing: {missing}
- Blockers: {[b.get("message") for b in (match.blockers or [])]}

Explain this result to the candidate."""

    result = await llm.complete(prompt, system=EXPLAIN_SYSTEM, max_tokens=400, temperature=0.2)
    if result.ok and result.text.strip():
        return result.text.strip(), "llm"
    return template, "template"


def _template_explanation(match: JobMatch, job: Job) -> str:
    from app.services.matching.eligibility import BAND_LABELS

    lines = [
        f"{job.title} at {job.company} scores {match.score}% "
        f"({BAND_LABELS.get(match.band, match.band)}), eligibility: "
        f"{match.eligibility_status.replace('_', ' ')}."
    ]
    lines.extend(match.reasons or [])
    if match.blockers:
        lines.append("Blockers: " + " ".join(b.get("message", "") for b in match.blockers))
    return " ".join(lines)
