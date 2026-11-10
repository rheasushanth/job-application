from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from app.core.config import settings
from app.core.db import utcnow
from app.core.deps import CurrentUser, DbSession, RateLimiter
from app.core.errors import Conflict, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UpdateMeRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_limit = RateLimiter(settings.auth_rate_limit_per_minute, "authentication")


def _issue_tokens(db, user: User) -> TokenPair:
    raw, token_hash, expires = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires))
    db.commit()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, db: DbSession, _: None = Depends(_limit)
) -> TokenPair:
    email = payload.email.lower().strip()
    if db.scalars(select(User).where(User.email == email)).first():
        raise Conflict("An account with that email already exists")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_tokens(db, user)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: DbSession, _: None = Depends(_limit)) -> TokenPair:
    user = db.scalars(select(User).where(User.email == payload.email.lower().strip())).first()
    # Same message either way so the endpoint cannot be used to enumerate
    # registered email addresses.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Incorrect email or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("This account has been deactivated")
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession, _: None = Depends(_limit)) -> TokenPair:
    token_hash = hash_refresh_token(payload.refresh_token)
    row = db.scalars(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).first()

    if row is None:
        raise Unauthorized("Invalid refresh token", code="refresh_invalid")

    if row.revoked_at is not None:
        # Reuse of a rotated token means it leaked; drop the whole family.
        _revoke_all(db, row.user_id)
        db.commit()
        raise Unauthorized(
            "This refresh token was already used. Please sign in again.",
            code="refresh_reused",
        )

    if row.expires_at < datetime.now(timezone.utc):
        raise Unauthorized("Refresh token expired", code="refresh_expired")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account unavailable")

    raw, new_hash, expires = new_refresh_token()
    replacement = RefreshToken(user_id=user.id, token_hash=new_hash, expires_at=expires)
    db.add(replacement)
    db.flush()

    row.revoked_at = utcnow()
    row.replaced_by_id = replacement.id
    db.commit()

    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=raw,
        expires_in=settings.access_token_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshRequest, db: DbSession) -> Response:
    row = db.scalars(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(payload.refresh_token)
        )
    ).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: UpdateMeRequest, user: CurrentUser, db: DbSession) -> UserOut:
    data = payload.model_dump(exclude_unset=True)
    if "full_name" in data:
        user.full_name = (data["full_name"] or "").strip() or None
    if "alert_enabled" in data:
        user.alert_enabled = bool(data["alert_enabled"])
    if "alert_min_match" in data:
        user.alert_min_match = int(data["alert_min_match"])
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


def _revoke_all(db, user_id) -> None:
    rows = db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    for row in rows:
        row.revoked_at = utcnow()
