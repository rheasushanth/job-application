from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Annotated, Any, Type, TypeVar

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import NotFound, TooManyRequests, Unauthorized
from app.core.security import decode_access_token
from app.models import CandidateProfile, User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if creds is None or not creds.credentials:
        raise Unauthorized()
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise Unauthorized("Session expired", code="token_expired")
    except jwt.PyJWTError:
        raise Unauthorized("Invalid token", code="token_invalid")

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthorized("Account unavailable")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

T = TypeVar("T")


def require_owned(db: Session, model: Type[T], obj_id: uuid.UUID, user: User) -> T:
    """Fetch a row and verify ownership.

    Returns 404 rather than 403 on a mismatch so IDs cannot be probed for
    existence by an unauthorised caller.
    """
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise NotFound(f"{model.__name__} not found")
    return obj


def get_active_profile(db: Session, user: User) -> CandidateProfile:
    profile = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id, CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.revision.desc())
    ).first()
    if profile is None:
        raise NotFound(
            "No confirmed candidate profile yet. Upload and confirm a resume first.",
            code="no_profile",
        )
    return profile


def find_active_profile(db: Session, user: User) -> CandidateProfile | None:
    return db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id, CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.revision.desc())
    ).first()


_RATE_LIMIT_BUCKETS: list[dict[str, deque[float]]] = []


def reset_rate_limits() -> None:
    """Clear all rate-limit windows. For tests, which share one client IP."""
    for bucket in _RATE_LIMIT_BUCKETS:
        bucket.clear()


def RateLimiter(per_minute: int, name: str):
    """Build an in-process sliding-window rate-limit dependency.

    Deliberately a closure rather than a callable class: FastAPI resolves a
    dependency's type hints through the callable's ``__globals__``, which a
    class *instance* does not have. With ``from __future__ import annotations``
    making hints strings, an instance-based dependency leaves ``request`` as an
    unresolvable annotation and FastAPI then demands it as a query parameter.

    Adequate for a single API instance; behind multiple replicas this should be
    swapped for a Redis-backed implementation with the same signature.
    """
    hits: dict[str, deque[float]] = defaultdict(deque)
    _RATE_LIMIT_BUCKETS.append(hits)

    def check_rate_limit(request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= per_minute:
            raise TooManyRequests(
                f"Too many {name} requests. Try again in a minute.",
                fields={"retry_after_seconds": int(61 - (now - window[0]))},
            )
        window.append(now)

    return check_rate_limit


def paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return page, page_size


def serialise(value: Any) -> Any:
    """JSON-safe conversion for UUIDs / Decimals inside nested structures."""
    import decimal
    from datetime import date, datetime

    if isinstance(value, dict):
        return {k: serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialise(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
