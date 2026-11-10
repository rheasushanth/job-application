"""Saved jobs and the application tracker."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select

from app.core.db import utcnow
from app.core.deps import CurrentUser, DbSession, require_owned
from app.core.errors import Conflict, NotFound
from app.models import APPLICATION_STATUSES, Application, ApplicationEvent, Job, JobMatch, SavedJob
from app.routers.jobs import match_summary
from app.schemas import (
    ApplicationBoardOut,
    ApplicationCreate,
    ApplicationEventOut,
    ApplicationOut,
    ApplicationUpdate,
    JobOut,
    SavedJobCreate,
    SavedJobOut,
    SavedJobUpdate,
)

router = APIRouter(tags=["tracking"])


def _match_for(db, user_id: uuid.UUID, job_id: uuid.UUID):
    return db.scalars(
        select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job_id)
    ).first()


# ---------------------------------------------------------------------------
# Saved jobs
# ---------------------------------------------------------------------------


@router.get("/saved", response_model=list[SavedJobOut])
def list_saved(
    user: CurrentUser, db: DbSession, collection: str | None = None
) -> list[SavedJobOut]:
    stmt = (
        select(SavedJob)
        .where(SavedJob.user_id == user.id)
        .order_by(SavedJob.created_at.desc())
    )
    if collection:
        stmt = stmt.where(SavedJob.collection == collection)

    out: list[SavedJobOut] = []
    for row in db.scalars(stmt).all():
        out.append(SavedJobOut(
            id=row.id,
            collection=row.collection,
            notes=row.notes,
            created_at=row.created_at,
            job=JobOut.model_validate(row.job),
            match=match_summary(_match_for(db, user.id, row.job_id)),
        ))
    return out


@router.get("/saved/collections")
def list_collections(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = db.execute(
        select(SavedJob.collection, func.count(SavedJob.id))
        .where(SavedJob.user_id == user.id)
        .group_by(SavedJob.collection)
        .order_by(func.count(SavedJob.id).desc())
    ).all()
    return [{"name": name, "count": int(count)} for name, count in rows]


@router.post("/saved", response_model=SavedJobOut, status_code=status.HTTP_201_CREATED)
def save_job(payload: SavedJobCreate, user: CurrentUser, db: DbSession) -> SavedJobOut:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise NotFound("Job not found")

    existing = db.scalars(
        select(SavedJob).where(
            SavedJob.user_id == user.id, SavedJob.job_id == payload.job_id
        )
    ).first()
    if existing is not None:
        raise Conflict("This job is already saved")

    row = SavedJob(
        user_id=user.id,
        job_id=payload.job_id,
        collection=payload.collection.strip() or "Default",
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return SavedJobOut(
        id=row.id,
        collection=row.collection,
        notes=row.notes,
        created_at=row.created_at,
        job=JobOut.model_validate(job),
        match=match_summary(_match_for(db, user.id, job.id)),
    )


@router.patch("/saved/{saved_id}", response_model=SavedJobOut)
def update_saved(
    saved_id: uuid.UUID, payload: SavedJobUpdate, user: CurrentUser, db: DbSession
) -> SavedJobOut:
    row = require_owned(db, SavedJob, saved_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "collection" in data and data["collection"]:
        row.collection = data["collection"].strip()
    if "notes" in data:
        row.notes = data["notes"]
    db.commit()
    db.refresh(row)

    return SavedJobOut(
        id=row.id,
        collection=row.collection,
        notes=row.notes,
        created_at=row.created_at,
        job=JobOut.model_validate(row.job),
        match=match_summary(_match_for(db, user.id, row.job_id)),
    )


@router.delete("/saved/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    """Keyed by job_id so the UI can unsave from a job card without extra state."""
    row = db.scalars(
        select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
    ).first()
    if row is None:
        raise NotFound("This job is not saved")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


def _application_out(db, user_id: uuid.UUID, row: Application, include_events: bool = False):
    return ApplicationOut(
        id=row.id,
        status=row.status,
        notes=row.notes,
        applied_at=row.applied_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        job=JobOut.model_validate(row.job),
        match=match_summary(_match_for(db, user_id, row.job_id)),
        events=(
            [ApplicationEventOut.model_validate(e)
             for e in sorted(row.events, key=lambda e: e.created_at)]
            if include_events else []
        ),
    )


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    user: CurrentUser,
    db: DbSession,
    status_filter: list[str] | None = Query(default=None, alias="status"),
) -> list[ApplicationOut]:
    stmt = (
        select(Application)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Application.status.in_(status_filter))
    return [_application_out(db, user.id, row) for row in db.scalars(stmt).all()]


@router.get("/applications/board", response_model=ApplicationBoardOut)
def application_board(user: CurrentUser, db: DbSession) -> ApplicationBoardOut:
    """Grouped by status for the kanban view."""
    rows = db.scalars(
        select(Application)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
    ).all()

    columns: dict[str, list[ApplicationOut]] = {s: [] for s in APPLICATION_STATUSES}
    for row in rows:
        columns.setdefault(row.status, []).append(_application_out(db, user.id, row))

    return ApplicationBoardOut(
        columns=columns,
        counts={key: len(value) for key, value in columns.items()},
    )


@router.post(
    "/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED
)
def create_application(
    payload: ApplicationCreate, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise NotFound("Job not found")

    existing = db.scalars(
        select(Application).where(
            Application.user_id == user.id, Application.job_id == payload.job_id
        )
    ).first()
    if existing is not None:
        raise Conflict("This job is already in your tracker")

    row = Application(
        user_id=user.id,
        job_id=payload.job_id,
        status=payload.status,
        notes=payload.notes,
        applied_at=utcnow() if payload.status != "interested" else None,
    )
    db.add(row)
    db.flush()
    db.add(ApplicationEvent(application_id=row.id, from_status=None, to_status=row.status))
    db.commit()
    db.refresh(row)
    return _application_out(db, user.id, row, include_events=True)


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ApplicationOut:
    row = require_owned(db, Application, application_id, user)
    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] and data["status"] != row.status:
        previous = row.status
        row.status = data["status"]
        # Stamp the application date on the first move out of "interested".
        if row.applied_at is None and row.status != "interested":
            row.applied_at = utcnow()
        db.add(ApplicationEvent(
            application_id=row.id,
            from_status=previous,
            to_status=row.status,
            note=data.get("notes"),
        ))

    if "notes" in data:
        row.notes = data["notes"]

    db.commit()
    db.refresh(row)
    return _application_out(db, user.id, row, include_events=True)


@router.get("/applications/{application_id}/events", response_model=list[ApplicationEventOut])
def list_events(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[ApplicationEventOut]:
    row = require_owned(db, Application, application_id, user)
    return [
        ApplicationEventOut.model_validate(event)
        for event in sorted(row.events, key=lambda e: e.created_at)
    ]


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    row = require_owned(db, Application, application_id, user)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
