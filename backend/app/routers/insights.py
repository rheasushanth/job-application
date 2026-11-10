"""Skill gap, alternative roles, resume feedback, notifications and settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, get_active_profile, require_owned
from app.core.errors import BadRequest
from app.models import Notification
from app.schemas import (
    AlertConfig,
    AlternativeRolesOut,
    NotificationOut,
    ResumeFeedbackOut,
    SkillGapOut,
    WeightsOut,
    WeightsUpdate,
)
from app.services.insights import alt_roles, resume_feedback, skill_gap
from app.services.matching.weights import (
    CATEGORY_DESCRIPTIONS,
    CATEGORY_LABELS,
    DEFAULT_WEIGHTS,
    get_user_weights,
    reset_user_weights,
    set_user_weights,
)

router = APIRouter(tags=["insights"])


@router.get("/insights/skill-gap", response_model=SkillGapOut)
def get_skill_gap(user: CurrentUser, db: DbSession, limit: int = 20) -> SkillGapOut:
    profile = get_active_profile(db, user)
    return SkillGapOut(**skill_gap.analyse(db, profile, limit=min(limit, 50)))


@router.get("/insights/alternative-roles", response_model=AlternativeRolesOut)
def get_alternative_roles(
    user: CurrentUser,
    db: DbSession,
    limit: int = 12,
    include_all: bool = False,
) -> AlternativeRolesOut:
    profile = get_active_profile(db, user)
    return AlternativeRolesOut(
        seniority=profile.seniority,
        roles=alt_roles.recommend_roles(
            db, profile, limit=min(limit, 30), include_all=include_all
        ),
    )


@router.get("/insights/resume-feedback", response_model=ResumeFeedbackOut)
async def get_resume_feedback(
    user: CurrentUser,
    db: DbSession,
    include_rewrites: bool = False,
    target_role: str | None = Query(default=None, max_length=120),
) -> ResumeFeedbackOut:
    profile = get_active_profile(db, user)
    result = resume_feedback.analyse(db, profile)

    rewrites = None
    if include_rewrites:
        rewrites = await resume_feedback.suggest_rewrites(profile, target_role)

    return ResumeFeedbackOut(**result, rewrites=rewrites)


# ---------------------------------------------------------------------------
# Notifications / alerts
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    user: CurrentUser, db: DbSession, unread_only: bool = False, limit: int = 50
) -> list[NotificationOut]:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(min(limit, 200))
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    return [NotificationOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> NotificationOut:
    row = require_owned(db, Notification, notification_id, user)
    row.is_read = True
    db.commit()
    db.refresh(row)
    return NotificationOut.model_validate(row)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(user: CurrentUser, db: DbSession) -> Response:
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ).all()
    for row in rows:
        row.is_read = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/alerts/config", response_model=AlertConfig)
def get_alert_config(user: CurrentUser) -> AlertConfig:
    return AlertConfig(
        alert_enabled=user.alert_enabled, alert_min_match=user.alert_min_match
    )


@router.put("/alerts/config", response_model=AlertConfig)
def set_alert_config(
    payload: AlertConfig, user: CurrentUser, db: DbSession
) -> AlertConfig:
    user.alert_enabled = payload.alert_enabled
    user.alert_min_match = payload.alert_min_match
    db.commit()
    db.refresh(user)
    return AlertConfig(
        alert_enabled=user.alert_enabled, alert_min_match=user.alert_min_match
    )


# ---------------------------------------------------------------------------
# Match weights
# ---------------------------------------------------------------------------


def _weights_out(weights: dict[str, float], digest: str) -> WeightsOut:
    return WeightsOut(
        weights=weights,
        defaults=DEFAULT_WEIGHTS,
        labels=CATEGORY_LABELS,
        descriptions=CATEGORY_DESCRIPTIONS,
        hash=digest,
    )


@router.get("/settings/weights", response_model=WeightsOut)
def get_weights(user: CurrentUser, db: DbSession) -> WeightsOut:
    weights, digest = get_user_weights(db, user.id)
    return _weights_out(weights, digest)


@router.put("/settings/weights", response_model=WeightsOut)
def update_weights(
    payload: WeightsUpdate, user: CurrentUser, db: DbSession
) -> WeightsOut:
    try:
        weights, digest = set_user_weights(db, user.id, payload.weights)
    except ValueError as exc:
        raise BadRequest(str(exc), code="invalid_weights") from exc
    db.commit()

    # Changing the weights makes every stored score stale; rescore now so the
    # dashboard is never showing numbers from the old configuration.
    from app.core.deps import find_active_profile
    from app.services.matching.service import score_jobs_for_profile

    profile = find_active_profile(db, user)
    if profile is not None:
        score_jobs_for_profile(db, profile, force=True)
        db.commit()

    return _weights_out(weights, digest)


@router.post("/settings/weights/reset", response_model=WeightsOut)
def reset_weights(user: CurrentUser, db: DbSession) -> WeightsOut:
    weights, digest = reset_user_weights(db, user.id)
    db.commit()

    from app.core.deps import find_active_profile
    from app.services.matching.service import score_jobs_for_profile

    profile = find_active_profile(db, user)
    if profile is not None:
        score_jobs_for_profile(db, profile, force=True)
        db.commit()

    return _weights_out(weights, digest)
