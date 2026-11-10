from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_rounds)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt silently truncates at 72 bytes; pre-hash so long passphrases
    # keep their full entropy instead of collapsing to a shared prefix.
    return _pwd.hash(_prepare(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(_prepare(password), password_hash)
    except ValueError:
        return False


def _prepare(password: str) -> str:
    if len(password.encode("utf-8")) <= 72:
        return password
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_access_token(user_id: uuid.UUID, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def new_refresh_token() -> tuple[str, str, datetime]:
    """Return (plaintext, sha256 hash, expiry). Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)
    return raw, hash_refresh_token(raw), expires


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
