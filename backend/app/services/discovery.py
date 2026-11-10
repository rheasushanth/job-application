"""Discovery runner: fetch from every enabled source, ingest, score, alert.

Failure isolation is the design priority. One portal timing out, rate-limiting
or changing its payload shape must not lose the other portals' results, so each
source × query runs independently and its outcome is recorded in
`source_run_log`. A run finishes as `completed`, `partial` or `failed` and the
UI reports exactly which sources contributed.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, utcnow
from app.models import (
    CandidateProfile,
    DiscoveryRun,
    Job,
    JobMatch,
    JobSourceRecord,
    Notification,
    SourceRunLog,
    User,
)
from app.services.ingest import IngestStats, ingest_jobs
from app.services.insights.alt_roles import derive_role_queries
from app.services.matching.service import score_jobs_for_profile
from app.services.sources.base import RawJob, SourceQuery, SourceUnavailable
from app.services.sources.registry import enabled_source_keys, get_source

logger = logging.getLogger(__name__)

MAX_QUERIES = 6


def run_discovery(
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    source_keys: list[str],
    queries: list[dict],
) -> None:
    """Entry point for the task queue. Owns its own DB session."""
    with SessionLocal() as db:
        try:
            _execute(db, run_id, user_id, source_keys, queries)
        except Exception as exc:
            logger.exception("Discovery run %s failed", run_id)
            run = db.get(DiscoveryRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(exc)[:1000]
                run.finished_at = utcnow()
                db.commit()


def _execute(
    db: Session,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    source_keys: list[str],
    queries: list[dict],
) -> None:
    run = db.get(DiscoveryRun, run_id)
    if run is None:
        return

    run.status = "running"
    run.progress = 5
    db.commit()

    search_queries = [SourceQuery(**q) for q in queries]

    # Fetching is network-bound and every (source, query) pair is independent,
    # so they run concurrently under a semaphore rather than one at a time.
    # Sequentially, a run costs sources x queries x timeout in the worst case
    # (24 fetches x 30s = 12 minutes); concurrently it is bounded by the
    # slowest few. Ingestion stays single-threaded afterwards because it shares
    # one DB session.
    plan: list[tuple[str, SourceQuery]] = []
    missing: list[str] = []
    for key in source_keys:
        source = get_source(key)
        if source is None:
            missing.append(key)
            continue
        for query in search_queries:
            # Location-specific queries are pointless against remote-only feeds.
            effective = query
            if source.remote_only_source and query.location:
                effective = SourceQuery(
                    keywords=query.keywords,
                    location=None,
                    remote_only=True,
                    job_type=query.job_type,
                    limit=query.limit,
                    page=query.page,
                )
            plan.append((key, effective))

    run.progress = 8
    db.commit()

    results = asyncio.run(_fetch_all(plan))

    run.progress = 55
    db.commit()

    succeeded: list[str] = []
    failed: list[dict] = []
    stats = IngestStats()
    for key in missing:
        failed.append({"source": key, "error": "Source not registered"})

    # Group outcomes by source so each source gets one status and one summary.
    by_source: dict[str, list[tuple[SourceQuery, list[RawJob] | None, str | None, str]]] = {}
    for key, query, raws, error, status in results:
        by_source.setdefault(key, []).append((query, raws, error, status))

    total_units = max(1, len(by_source))
    for index, (key, outcomes) in enumerate(by_source.items(), start=1):
        source_stats = IngestStats()
        source_error: str | None = None

        for query, raws, error, status in outcomes:
            log = SourceRunLog(
                discovery_run_id=run_id,
                source_key=key,
                status=status,
                query=query.as_dict(),
                started_at=utcnow(),
            )
            db.add(log)

            if raws is not None:
                try:
                    batch = ingest_jobs(db, raws)
                    source_stats.merge(batch)
                    log.status = "ok"
                    log.fetched = batch.fetched
                    log.inserted = batch.inserted
                    log.duplicates = batch.duplicates
                except Exception as exc:
                    db.rollback()
                    log = SourceRunLog(
                        discovery_run_id=run_id,
                        source_key=key,
                        status="error",
                        query=query.as_dict(),
                        started_at=utcnow(),
                        error=f"Ingestion failed: {type(exc).__name__}"[:500],
                    )
                    db.add(log)
                    source_error = source_error or log.error
                    logger.exception("Ingestion failed for %s", key)
            else:
                log.error = (error or "")[:500]
                source_error = source_error or error

            log.finished_at = utcnow()

        stats.merge(source_stats)
        _update_source_record(db, key, source_stats, source_error)

        if source_error and source_stats.fetched == 0:
            failed.append({"source": key, "error": source_error})
        else:
            succeeded.append(key)

        # Ingestion spans 55% to 80%; scoring owns the rest.
        run.progress = 55 + int(25 * index / total_units)
        db.commit()

    run.jobs_fetched = stats.fetched
    run.jobs_new = stats.inserted
    run.jobs_duplicate = stats.duplicates
    run.sources_succeeded = succeeded
    run.sources_failed = failed
    run.progress = 82
    db.commit()

    # ---- score ---------------------------------------------------------
    profile = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user_id, CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.revision.desc())
    ).first()

    if profile is not None:
        before = _high_match_job_ids(db, user_id)
        run.matches_computed = score_jobs_for_profile(db, profile)
        db.commit()
        run.progress = 95
        db.commit()
        _emit_alerts(db, user_id, before)
    else:
        run.error = "Jobs were discovered but no confirmed profile exists to score against."

    run.status = "partial" if failed and succeeded else ("failed" if failed and not succeeded else "completed")
    run.progress = 100
    run.finished_at = utcnow()
    db.commit()


async def _fetch_all(
    plan: list[tuple[str, SourceQuery]],
) -> list[tuple[str, SourceQuery, list[RawJob] | None, str | None, str]]:
    """Fetch every (source, query) pair concurrently.

    Returns one tuple per pair: (source_key, query, raws, error, status).
    A failure is captured per pair and never propagates, so one portal timing
    out or changing its payload shape cannot lose the other portals' results.
    """
    semaphore = asyncio.Semaphore(max(1, settings.source_concurrency))

    async def run_one(
        key: str, query: SourceQuery
    ) -> tuple[str, SourceQuery, list[RawJob] | None, str | None, str]:
        source = get_source(key)
        if source is None:
            return key, query, None, "Source not registered", "error"
        async with semaphore:
            try:
                raws = await asyncio.wait_for(
                    source.fetch(query), timeout=settings.source_timeout_seconds
                )
                return key, query, raws, None, "ok"
            except SourceUnavailable as exc:
                return key, query, None, str(exc), "skipped"
            except asyncio.TimeoutError:
                return (
                    key, query, None,
                    f"Timed out after {settings.source_timeout_seconds}s", "error",
                )
            except Exception as exc:
                logger.warning("Source %s failed: %s", key, exc)
                return key, query, None, f"{type(exc).__name__}: {exc}", "error"

    return await asyncio.gather(*(run_one(key, query) for key, query in plan))


def _update_source_record(
    db: Session, key: str, stats: IngestStats, error: str | None
) -> None:
    record = db.get(JobSourceRecord, key)
    if record is None:
        return
    record.last_run_at = utcnow()
    record.jobs_last_run = stats.fetched
    if error and stats.fetched == 0:
        record.last_status = "error"
        record.last_error = error[:1000]
    else:
        record.last_status = "ok"
        record.last_error = None


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def _high_match_job_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    user = db.get(User, user_id)
    threshold = user.alert_min_match if user else 70
    rows = db.scalars(
        select(JobMatch.job_id).where(
            JobMatch.user_id == user_id, JobMatch.score >= threshold
        )
    ).all()
    return set(rows)


def _emit_alerts(db: Session, user_id: uuid.UUID, before: set[uuid.UUID]) -> None:
    user = db.get(User, user_id)
    if user is None or not user.alert_enabled:
        return

    threshold = user.alert_min_match or 70
    rows = db.scalars(
        select(JobMatch)
        .where(JobMatch.user_id == user_id, JobMatch.score >= threshold)
        .order_by(JobMatch.score.desc())
    ).all()

    fresh = [row for row in rows if row.job_id not in before]
    if not fresh:
        return

    top = fresh[:5]
    titles = []
    for row in top:
        job = db.get(Job, row.job_id)
        if job is not None:
            titles.append(f"{job.title} at {job.company} ({row.score:.0f}%)")

    db.add(Notification(
        user_id=user_id,
        kind="new_matches",
        title=(
            f"{len(fresh)} new job{'s' if len(fresh) != 1 else ''} matching "
            f"{threshold}% or above"
        ),
        body="; ".join(titles) if titles else None,
        payload={
            "count": len(fresh),
            "threshold": threshold,
            "job_ids": [str(r.job_id) for r in top],
        },
    ))
    db.flush()


# ---------------------------------------------------------------------------
# Query planning
# ---------------------------------------------------------------------------


def plan_queries(
    profile: CandidateProfile | None,
    *,
    explicit: list[str] | None = None,
    location: str | None = None,
) -> list[dict]:
    """Decide what to search for.

    Searches are driven by the candidate's *eligible roles*, not just titles
    found in the resume — that is what surfaces the alternative roles the brief
    asks for (a CS student gets backend, data and QA queries, not only the one
    title they wrote down).
    """
    keywords: list[str]
    if explicit:
        keywords = [k.strip() for k in explicit if k and k.strip()][:MAX_QUERIES]
    elif profile is not None:
        keywords = derive_role_queries(profile)[:MAX_QUERIES]
    else:
        keywords = ["software developer"]

    if not keywords:
        keywords = ["software developer"]

    job_type = None
    if profile is not None and profile.seniority in ("student", "intern"):
        job_type = "internship"

    effective_location = location or (profile.location if profile else None)
    limit = settings.max_jobs_per_source_per_query

    return [
        SourceQuery(
            keywords=keyword,
            location=effective_location,
            job_type=job_type,
            limit=limit,
        ).as_dict()
        for keyword in keywords
    ]


def start_discovery(
    db: Session,
    user: User,
    *,
    sources: list[str] | None = None,
    queries: list[str] | None = None,
    location: str | None = None,
) -> DiscoveryRun:
    """Create the run row and enqueue the work."""
    from app.services import tasks

    profile = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id, CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.revision.desc())
    ).first()

    source_keys = enabled_source_keys(db, sources)
    planned = plan_queries(profile, explicit=queries, location=location)

    run = DiscoveryRun(
        user_id=user.id,
        status="queued",
        sources_attempted=source_keys,
        queries=[q["keywords"] for q in planned],
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if not source_keys:
        run.status = "failed"
        run.error = (
            "No job sources are currently available. The keyless public feeds "
            "should always be available — check network access, or enable a "
            "credentialed source in Settings."
        )
        run.finished_at = utcnow()
        db.commit()
        return run

    tasks.enqueue(run_discovery, run.id, user.id, source_keys, planned)
    return run


def prune_stale_jobs(days: int = 60) -> int:
    """Deactivate postings not seen in a while. Intended for a cron/beat job."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with SessionLocal() as db:
        rows = db.scalars(
            select(Job).where(Job.is_active.is_(True), Job.last_seen_at < cutoff)
        ).all()
        for job in rows:
            job.is_active = False
        db.commit()
        return len(rows)
