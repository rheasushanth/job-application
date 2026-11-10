from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, find_active_profile, require_owned
from app.core.errors import BadRequest, NotFound
from app.models import DiscoveryRun, JobSourceRecord, SourceRunLog
from app.schemas import (
    DiscoveryRequest,
    DiscoveryRunOut,
    SourceOut,
    SourceUpdate,
)
from app.services.discovery import start_discovery
from app.services.sources.registry import all_sources, get_source

router = APIRouter(tags=["discovery"])


@router.get("/sources", response_model=list[SourceOut])
def list_sources(user: CurrentUser, db: DbSession) -> list[SourceOut]:
    """Every registered source with its live availability.

    This is what lets the UI state honestly which portals are active and what
    an unavailable one requires, rather than hiding them.
    """
    records = {r.key: r for r in db.scalars(select(JobSourceRecord)).all()}
    out: list[SourceOut] = []
    for source in all_sources():
        described = source.describe()
        record = records.get(source.key)
        out.append(SourceOut(
            **described,
            is_enabled=record.is_enabled if record else True,
            last_run_at=record.last_run_at if record else None,
            last_status=record.last_status if record else None,
            last_error=record.last_error if record else None,
            jobs_last_run=record.jobs_last_run if record else 0,
        ))
    return out


@router.patch("/sources/{key}", response_model=SourceOut)
def update_source(
    key: str, payload: SourceUpdate, user: CurrentUser, db: DbSession
) -> SourceOut:
    source = get_source(key)
    record = db.get(JobSourceRecord, key)
    if source is None or record is None:
        raise NotFound(f"Unknown source '{key}'")

    record.is_enabled = payload.is_enabled
    db.commit()
    db.refresh(record)

    return SourceOut(
        **source.describe(),
        is_enabled=record.is_enabled,
        last_run_at=record.last_run_at,
        last_status=record.last_status,
        last_error=record.last_error,
        jobs_last_run=record.jobs_last_run,
    )


@router.post(
    "/discovery/run", response_model=DiscoveryRunOut, status_code=status.HTTP_202_ACCEPTED
)
def run_discovery_endpoint(
    payload: DiscoveryRequest, user: CurrentUser, db: DbSession
) -> DiscoveryRunOut:
    if find_active_profile(db, user) is None and not payload.queries:
        raise BadRequest(
            "Confirm a resume first, or supply explicit search queries — "
            "discovery derives its searches from your profile.",
            code="no_profile",
        )

    # Avoid stacking concurrent runs for one user.
    running = db.scalars(
        select(DiscoveryRun).where(
            DiscoveryRun.user_id == user.id,
            DiscoveryRun.status.in_(("queued", "running")),
        )
    ).first()
    if running is not None:
        return DiscoveryRunOut.model_validate(running)

    run = start_discovery(
        db,
        user,
        sources=payload.sources,
        queries=payload.queries,
        location=payload.location,
    )
    return DiscoveryRunOut.model_validate(run)


@router.get("/discovery/runs", response_model=list[DiscoveryRunOut])
def list_runs(user: CurrentUser, db: DbSession, limit: int = 20) -> list[DiscoveryRunOut]:
    rows = db.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.user_id == user.id)
        .order_by(DiscoveryRun.started_at.desc())
        .limit(min(limit, 100))
    ).all()
    return [DiscoveryRunOut.model_validate(row) for row in rows]


@router.get("/discovery/runs/{run_id}")
def get_run(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict:
    run = require_owned(db, DiscoveryRun, run_id, user)
    logs = db.scalars(
        select(SourceRunLog)
        .where(SourceRunLog.discovery_run_id == run.id)
        .order_by(SourceRunLog.started_at.asc())
    ).all()
    return {
        "run": DiscoveryRunOut.model_validate(run).model_dump(),
        "source_logs": [
            {
                "source_key": log.source_key,
                "status": log.status,
                "fetched": log.fetched,
                "inserted": log.inserted,
                "duplicates": log.duplicates,
                "error": log.error,
                "query": log.query,
                "started_at": log.started_at,
                "finished_at": log.finished_at,
            }
            for log in logs
        ],
    }


@router.post("/discovery/rescore")
def rescore(user: CurrentUser, db: DbSession) -> dict:
    """Recompute matches against the current profile without re-fetching jobs."""
    profile = find_active_profile(db, user)
    if profile is None:
        raise BadRequest("Confirm a resume first.", code="no_profile")

    from app.services.matching.service import score_jobs_for_profile

    written = score_jobs_for_profile(db, profile, force=True)
    db.commit()
    return {"matches_computed": written}
