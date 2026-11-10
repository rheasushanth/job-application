"""Source registry.

Adapters self-register with `@register_source`. The registry is the single
place the rest of the app learns which portals exist, so adding a module is the
whole integration story.
"""

from __future__ import annotations

import importlib
import logging
from typing import Iterable, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, "JobSource"] = {}

# Modules scanned at import time. A new file listed here is picked up
# everywhere — API, discovery runner and UI — with no other changes.
_ADAPTER_MODULES = (
    "app.services.sources.public_feeds",
    "app.services.sources.keyed_feeds",
)

_loaded = False


def register_source(cls: Type) -> Type:
    """Class decorator that adds a JobSource implementation to the registry."""
    if not getattr(cls, "key", ""):
        raise ValueError(f"{cls.__name__} must define a non-empty `key`")
    instance = cls()
    if instance.key in _REGISTRY:
        raise ValueError(f"Duplicate source key '{instance.key}'")
    _REGISTRY[instance.key] = instance
    return cls


def load_sources() -> None:
    global _loaded
    if _loaded:
        return
    for module in _ADAPTER_MODULES:
        try:
            importlib.import_module(module)
        except Exception:
            logger.exception("Failed to import source module %s", module)
    _loaded = True


def all_sources() -> list["JobSource"]:
    load_sources()
    return sorted(_REGISTRY.values(), key=lambda s: (not s.availability().available, s.key))


def get_source(key: str) -> "JobSource | None":
    load_sources()
    return _REGISTRY.get(key)


def available_sources() -> list["JobSource"]:
    return [s for s in all_sources() if s.availability().available]


def describe_sources() -> list[dict]:
    return [s.describe() for s in all_sources()]


def sync_source_registry(db: Session) -> None:
    """Mirror the in-code registry into the DB so status is queryable/joinable."""
    from app.models import JobSourceRecord

    load_sources()
    existing = {
        row.key: row for row in db.scalars(select(JobSourceRecord)).all()
    }

    for source in all_sources():
        description = source.describe()
        record = existing.get(source.key)
        if record is None:
            db.add(JobSourceRecord(
                key=source.key,
                display_name=description["display_name"],
                kind=description["kind"],
                requires_credentials=description["requires_credentials"],
                credential_env_vars=description["credential_env_vars"],
                is_enabled=True,
                notes=description["notes"],
            ))
        else:
            # Code is the source of truth for metadata; `is_enabled` is the
            # operator's choice and is deliberately not overwritten.
            record.display_name = description["display_name"]
            record.kind = description["kind"]
            record.requires_credentials = description["requires_credentials"]
            record.credential_env_vars = description["credential_env_vars"]
            record.notes = description["notes"]
    db.flush()


def enabled_source_keys(db: Session, requested: Iterable[str] | None = None) -> list[str]:
    """Keys that are both operator-enabled and currently available."""
    from app.models import JobSourceRecord

    rows = {r.key: r for r in db.scalars(select(JobSourceRecord)).all()}
    keys: list[str] = []
    for source in all_sources():
        if requested and source.key not in set(requested):
            continue
        record = rows.get(source.key)
        if record is not None and not record.is_enabled:
            continue
        if not source.availability().available:
            continue
        keys.append(source.key)
    return keys


# Imported late to avoid a circular import at module load.
from app.services.sources.base import JobSource  # noqa: E402
