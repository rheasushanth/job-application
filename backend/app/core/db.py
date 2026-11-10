from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy import DateTime, String, TypeDecorator, create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import JSON

from app.core.config import settings


def _engine_kwargs() -> dict[str, Any]:
    if settings.is_sqlite:
        return {
            "connect_args": {"check_same_thread": False},
            "pool_pre_ping": True,
        }
    return {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


engine = create_engine(settings.resolved_database_url, future=True, **_engine_kwargs())

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver glue
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class GUID(TypeDecorator):
    """UUID that is native on Postgres and a 36-char string on SQLite."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class JSONB(TypeDecorator):
    """JSONB on Postgres, plain JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())


class TZDateTime(TypeDecorator):
    """Always hand back timezone-aware UTC datetimes, including on SQLite."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list: JSONB, datetime: TZDateTime}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables and seed the source registry. Idempotent."""
    from app import models  # noqa: F401  - ensure models are imported

    Base.metadata.create_all(bind=engine)
    _create_indexes()
    with SessionLocal() as db:
        from app.services.sources.registry import sync_source_registry

        sync_source_registry(db)
        from app.services.matching.weights import ensure_default_weight_profile

        ensure_default_weight_profile(db)
        db.commit()


def _create_indexes() -> None:
    """GIN indexes for skill arrays — Postgres only, best effort."""
    if settings.is_sqlite:
        return
    from sqlalchemy import text

    statements = [
        "CREATE INDEX IF NOT EXISTS ix_jobs_all_skills_gin ON jobs USING gin (all_skills)",
        "CREATE INDEX IF NOT EXISTS ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops)",
    ]
    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception:
            statements = statements[:1]
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
