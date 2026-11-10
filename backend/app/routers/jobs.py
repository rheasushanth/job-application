"""Job search, match analysis and dashboard summary.

All filtering, sorting and pagination happen in SQL — the frontend never
receives a full result set to whittle down client-side.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentUser, DbSession, find_active_profile, paginate
from app.core.errors import NotFound
from app.models import (
    Application,
    DiscoveryRun,
    Job,
    JobMatch,
    Notification,
    SavedJob,
    User,
)
from app.schemas import (
    DashboardSummaryOut,
    DiscoveryRunOut,
    JobListOut,
    JobOut,
    JobWithMatchOut,
    MatchAnalysisOut,
    MatchSummaryOut,
)
from app.services.matching.eligibility import BAND_LABELS
from app.services.matching.weights import (
    CATEGORY_DESCRIPTIONS,
    get_user_weights,
)
from app.services.sources.registry import all_sources

router = APIRouter(tags=["jobs"])

SORTS = {
    "match_desc", "match_asc", "posted_desc", "posted_asc",
    "salary_desc", "salary_asc", "company_asc",
}


def match_summary(row: JobMatch | None) -> MatchSummaryOut | None:
    if row is None:
        return None
    return MatchSummaryOut(
        score=float(row.score),
        band=row.band,
        eligibility_status=row.eligibility_status,
        eligibility_multiplier=row.eligibility_multiplier,
        matched_skills=[m.get("skill") for m in (row.matched_skills or []) if m.get("skill")],
        missing_skills=[m.get("skill") for m in (row.missing_skills or []) if m.get("skill")],
        missing_mandatory_skills=list(row.missing_mandatory_skills or []),
        category_scores={
            k: v for k, v in (row.category_scores or {}).items() if not k.startswith("_")
        },
        computed_at=row.computed_at,
    )


@router.get("/jobs", response_model=JobListOut)
def search_jobs(
    user: CurrentUser,
    db: DbSession,
    q: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    work_mode: Annotated[list[str] | None, Query()] = None,
    job_type: Annotated[list[str] | None, Query()] = None,
    experience_level: Annotated[list[str] | None, Query()] = None,
    source: Annotated[list[str] | None, Query()] = None,
    company: Annotated[list[str] | None, Query()] = None,
    skills: Annotated[list[str] | None, Query()] = None,
    band: Annotated[list[str] | None, Query()] = None,
    eligibility: Annotated[list[str] | None, Query()] = None,
    min_match: float | None = Query(default=None, ge=0, le=100),
    max_match: float | None = Query(default=None, ge=0, le=100),
    salary_min: float | None = Query(default=None, ge=0),
    salary_max: float | None = Query(default=None, ge=0),
    posted_within_days: int | None = Query(default=None, ge=1, le=365),
    saved_only: bool = False,
    tracked_only: bool = False,
    sort: str = "match_desc",
    page: int = 1,
    page_size: int = 20,
) -> JobListOut:
    page, page_size = paginate(page, page_size)
    if sort not in SORTS:
        sort = "match_desc"

    # Matches are LEFT JOINed: a user with no profile still gets a browsable
    # job list, just without scores.
    base = (
        select(Job, JobMatch)
        .outerjoin(
            JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user.id)
        )
        .where(Job.is_active.is_(True), Job.duplicate_of_id.is_(None))
    )

    conditions = []

    if q:
        term = f"%{q.strip()}%"
        conditions.append(
            or_(Job.title.ilike(term), Job.company.ilike(term), Job.description.ilike(term))
        )
    if city:
        conditions.append(Job.city.ilike(f"%{city.strip()}%"))
    if state:
        conditions.append(Job.state.ilike(f"%{state.strip()}%"))
    if country:
        conditions.append(Job.country.ilike(f"%{country.strip()}%"))
    if work_mode:
        conditions.append(Job.work_mode.in_(work_mode))
    if job_type:
        conditions.append(Job.job_type.in_(job_type))
    if experience_level:
        conditions.append(Job.experience_level.in_(experience_level))
    if source:
        conditions.append(Job.source.in_(source))
    if company:
        conditions.append(or_(*[Job.company.ilike(f"%{c}%") for c in company]))
    if skills:
        # AND semantics: every requested skill must be present. JSON arrays are
        # matched with LIKE on the serialised text so one query works on both
        # SQLite and Postgres; the Postgres GIN index covers the common case.
        for skill in skills:
            conditions.append(
                func.lower(func.cast(Job.all_skills, type_=__import__("sqlalchemy").Text))
                .like(f'%"{skill.lower()}"%')
            )
    if salary_min is not None:
        # A job with no salary data must not be excluded by a lower bound —
        # absence of data is not evidence of a low salary.
        conditions.append(or_(Job.salary_max >= salary_min, Job.salary_max.is_(None)))
    if salary_max is not None:
        conditions.append(or_(Job.salary_min <= salary_max, Job.salary_min.is_(None)))
    if posted_within_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
        conditions.append(or_(Job.posted_at >= cutoff, Job.posted_at.is_(None)))

    if band:
        conditions.append(JobMatch.band.in_(band))
    if eligibility:
        conditions.append(JobMatch.eligibility_status.in_(eligibility))
    if min_match is not None:
        conditions.append(JobMatch.score >= min_match)
    if max_match is not None:
        conditions.append(JobMatch.score <= max_match)

    if saved_only:
        base = base.join(
            SavedJob, and_(SavedJob.job_id == Job.id, SavedJob.user_id == user.id)
        )
    if tracked_only:
        base = base.join(
            Application, and_(Application.job_id == Job.id, Application.user_id == user.id)
        )

    if conditions:
        base = base.where(and_(*conditions))

    total = db.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    ) or 0

    base = _apply_sort(base, sort)
    rows = db.execute(base.limit(page_size).offset((page - 1) * page_size)).all()

    job_ids = [job.id for job, _ in rows]
    saved_ids = _saved_ids(db, user.id, job_ids)
    app_statuses = _application_statuses(db, user.id, job_ids)

    items = [
        JobWithMatchOut(
            job=JobOut.model_validate(job),
            match=match_summary(match),
            is_saved=job.id in saved_ids,
            application_status=app_statuses.get(job.id),
        )
        for job, match in rows
    ]

    return JobListOut(
        items=items,
        total=int(total),
        page=page,
        page_size=page_size,
        facets=_facets(db, user.id),
    )


def _apply_sort(stmt: Select, sort: str) -> Select:
    if sort == "match_desc":
        # NULLs last so unscored jobs don't crowd out real matches.
        return stmt.order_by(JobMatch.score.is_(None), JobMatch.score.desc(), Job.posted_at.desc())
    if sort == "match_asc":
        return stmt.order_by(JobMatch.score.is_(None), JobMatch.score.asc())
    if sort == "posted_desc":
        return stmt.order_by(Job.posted_at.is_(None), Job.posted_at.desc())
    if sort == "posted_asc":
        return stmt.order_by(Job.posted_at.is_(None), Job.posted_at.asc())
    if sort == "salary_desc":
        return stmt.order_by(Job.salary_max.is_(None), Job.salary_max.desc())
    if sort == "salary_asc":
        return stmt.order_by(Job.salary_min.is_(None), Job.salary_min.asc())
    if sort == "company_asc":
        return stmt.order_by(Job.company.asc())
    return stmt.order_by(JobMatch.score.desc())


def _saved_ids(db: Session, user_id: uuid.UUID, job_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not job_ids:
        return set()
    return set(
        db.scalars(
            select(SavedJob.job_id).where(
                SavedJob.user_id == user_id, SavedJob.job_id.in_(job_ids)
            )
        ).all()
    )


def _application_statuses(
    db: Session, user_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not job_ids:
        return {}
    rows = db.execute(
        select(Application.job_id, Application.status).where(
            Application.user_id == user_id, Application.job_id.in_(job_ids)
        )
    ).all()
    return {job_id: status for job_id, status in rows}


def _facets(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    """Filter-panel options, derived from what is actually in the index."""
    active = and_(Job.is_active.is_(True), Job.duplicate_of_id.is_(None))

    def counts(column):
        rows = db.execute(
            select(column, func.count(Job.id))
            .where(active, column.isnot(None))
            .group_by(column)
            .order_by(func.count(Job.id).desc())
            .limit(40)
        ).all()
        return [{"value": value, "count": int(count)} for value, count in rows if value]

    companies = db.execute(
        select(Job.company, func.count(Job.id))
        .where(active)
        .group_by(Job.company)
        .order_by(func.count(Job.id).desc())
        .limit(60)
    ).all()

    skill_counts: dict[str, int] = {}
    for (skills,) in db.execute(select(Job.all_skills).where(active)).all():
        for skill in skills or []:
            skill_counts[skill] = skill_counts.get(skill, 0) + 1
    top_skills = sorted(skill_counts.items(), key=lambda kv: -kv[1])[:50]

    return {
        "sources": counts(Job.source),
        "work_modes": counts(Job.work_mode),
        "job_types": counts(Job.job_type),
        "experience_levels": counts(Job.experience_level),
        "cities": counts(Job.city),
        "countries": counts(Job.country),
        "companies": [{"value": c, "count": int(n)} for c, n in companies if c],
        "skills": [{"value": s, "count": n} for s, n in top_skills],
    }


@router.get("/jobs/{job_id}", response_model=JobWithMatchOut)
def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobWithMatchOut:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found")
    # Follow a duplicate link to the canonical posting.
    if job.duplicate_of_id:
        canonical = db.get(Job, job.duplicate_of_id)
        job = canonical or job

    match = db.scalars(
        select(JobMatch).where(JobMatch.user_id == user.id, JobMatch.job_id == job.id)
    ).first()
    saved = _saved_ids(db, user.id, [job.id])
    statuses = _application_statuses(db, user.id, [job.id])

    return JobWithMatchOut(
        job=JobOut.model_validate(job),
        match=match_summary(match),
        is_saved=job.id in saved,
        application_status=statuses.get(job.id),
    )


@router.get("/jobs/{job_id}/analysis", response_model=MatchAnalysisOut)
async def get_analysis(
    job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> MatchAnalysisOut:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found")

    match = db.scalars(
        select(JobMatch).where(JobMatch.user_id == user.id, JobMatch.job_id == job.id)
    ).first()
    if match is None:
        raise NotFound(
            "This job has not been scored against your profile yet. "
            "Confirm a resume and run discovery.",
            code="not_scored",
        )

    # Generate the prose explanation on demand and cache it on the row.
    if not match.explanation:
        profile = find_active_profile(db, user)
        if profile is not None:
            from app.services.matching.service import generate_explanation

            text, source = await generate_explanation(match, job, profile)
            match.explanation = text
            match.explanation_source = source
            db.commit()
            db.refresh(match)

    stored = match.category_scores or {}
    weights, _ = get_user_weights(db, user.id)

    return MatchAnalysisOut(
        job=JobOut.model_validate(job),
        score=float(match.score),
        band=match.band,
        band_label=BAND_LABELS.get(match.band, match.band),
        eligibility_status=match.eligibility_status,
        eligibility_multiplier=match.eligibility_multiplier,
        semantic_similarity=match.semantic_similarity,
        category_scores={k: v for k, v in stored.items() if not k.startswith("_")},
        calculation=stored.get("_calculation", {}),
        eligibility_checks=stored.get("_eligibility_checks", []),
        eligibility_warnings=stored.get("_eligibility_warnings", []),
        matched_skills=match.matched_skills or [],
        missing_skills=match.missing_skills or [],
        missing_mandatory_skills=match.missing_mandatory_skills or [],
        extra_skills=match.extra_skills or [],
        relevant_projects=match.relevant_projects or [],
        relevant_experience=match.relevant_experience or [],
        reasons=match.reasons or [],
        blockers=match.blockers or [],
        recommendations=match.recommendations or [],
        explanation=match.explanation,
        explanation_source=match.explanation_source,
        weights=weights,
        category_descriptions=CATEGORY_DESCRIPTIONS,
        computed_at=match.computed_at,
    )


@router.get("/matches/summary", response_model=DashboardSummaryOut)
def dashboard_summary(user: CurrentUser, db: DbSession) -> DashboardSummaryOut:
    active = and_(Job.is_active.is_(True), Job.duplicate_of_id.is_(None))

    total_jobs = int(db.scalar(select(func.count(Job.id)).where(active)) or 0)

    band_rows = db.execute(
        select(JobMatch.band, func.count(JobMatch.id))
        .where(JobMatch.user_id == user.id)
        .group_by(JobMatch.band)
    ).all()
    bands = {band: int(count) for band, count in band_rows}

    elig_rows = db.execute(
        select(JobMatch.eligibility_status, func.count(JobMatch.id))
        .where(JobMatch.user_id == user.id)
        .group_by(JobMatch.eligibility_status)
    ).all()
    elig = {status: int(count) for status, count in elig_rows}

    saved = int(
        db.scalar(select(func.count(SavedJob.id)).where(SavedJob.user_id == user.id)) or 0
    )
    tracked = int(
        db.scalar(select(func.count(Application.id)).where(Application.user_id == user.id)) or 0
    )
    unread = int(
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id, Notification.is_read.is_(False)
            )
        )
        or 0
    )

    last_run = db.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.user_id == user.id)
        .order_by(DiscoveryRun.started_at.desc())
    ).first()

    top_rows = db.execute(
        select(Job, JobMatch)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == user.id, active)
        .order_by(JobMatch.score.desc())
        .limit(6)
    ).all()
    job_ids = [job.id for job, _ in top_rows]
    saved_ids = _saved_ids(db, user.id, job_ids)
    statuses = _application_statuses(db, user.id, job_ids)

    live = [s.key for s in all_sources() if s.availability().available]
    unavailable = [s.key for s in all_sources() if not s.availability().available]

    return DashboardSummaryOut(
        total_jobs=total_jobs,
        excellent=bands.get("excellent", 0),
        good=bands.get("good", 0),
        moderate=bands.get("moderate", 0),
        low=bands.get("low", 0),
        saved=saved,
        tracked=tracked,
        eligible=elig.get("eligible", 0),
        partially_eligible=elig.get("partially_eligible", 0),
        not_eligible=elig.get("not_eligible", 0),
        sources_live=live,
        sources_unavailable=unavailable,
        last_discovery=(
            DiscoveryRunOut.model_validate(last_run) if last_run is not None else None
        ),
        unread_notifications=unread,
        has_profile=find_active_profile(db, user) is not None,
        top_matches=[
            JobWithMatchOut(
                job=JobOut.model_validate(job),
                match=match_summary(match),
                is_saved=job.id in saved_ids,
                application_status=statuses.get(job.id),
            )
            for job, match in top_rows
        ],
    )
