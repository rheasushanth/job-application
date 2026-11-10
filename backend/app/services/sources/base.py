"""Job source contract.

Adding a portal means writing one module that subclasses `JobSource` and
decorating it with `@register_source`. Nothing in the matching engine, the API
layer or the frontend changes — the frontend renders whatever `/api/v1/sources`
reports, including availability and the reason a source is unavailable.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# How a source gets its data. Surfaced in the UI so users know what they are
# looking at rather than assuming every portal is equally covered.
KIND_PUBLIC_API = "public_api"       # free, keyless, documented JSON feed
KIND_LICENSED_API = "licensed_api"   # official/commercial API, needs a key
KIND_GATED = "gated"                 # no lawful public API available


@dataclass
class SourceQuery:
    """A single search request, derived from the candidate profile."""

    keywords: str = ""
    location: str | None = None
    remote_only: bool = False
    job_type: str | None = None  # internship | full_time | ...
    limit: int = 50
    page: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "keywords": self.keywords,
            "location": self.location,
            "remote_only": self.remote_only,
            "job_type": self.job_type,
            "limit": self.limit,
            "page": self.page,
        }


@dataclass
class SourceAvailability:
    available: bool
    reason: str = ""
    # Env vars an operator must set to enable this source.
    missing_env: list[str] = field(default_factory=list)
    # Short note shown in the UI next to the source.
    note: str = ""


@dataclass
class RawJob:
    """A posting as returned by a source, before enrichment.

    Only `source`, `source_job_id`, `title`, `company` and `apply_url` are
    mandatory. Everything else is optional because coverage varies wildly
    between portals; the enrichment step infers what it can and leaves the rest
    explicitly unknown rather than guessing.
    """

    source: str
    source_job_id: str
    title: str
    company: str
    apply_url: str

    description: str = ""
    description_html: str | None = None
    location_raw: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    is_remote: bool | None = None
    work_mode: str | None = None
    job_type: str | None = None
    experience_level: str | None = None
    experience_min_years: float | None = None
    experience_max_years: float | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    salary_raw: str | None = None
    posted_at: datetime | None = None
    deadline_at: datetime | None = None
    tags: list[str] = field(default_factory=list)
    education_requirement: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class JobSource(abc.ABC):
    """Base class for every job source adapter."""

    key: str = ""
    display_name: str = ""
    kind: str = KIND_PUBLIC_API
    requires_credentials: bool = False
    credential_env_vars: tuple[str, ...] = ()
    notes: str = ""
    # Sources that only ever return remote work; used to skip pointless
    # location-specific queries.
    remote_only_source: bool = False

    def availability(self) -> SourceAvailability:
        """Default: available unless credentials are declared and missing."""
        if not self.requires_credentials:
            return SourceAvailability(available=True, note=self.notes)
        missing = [name for name in self.credential_env_vars if not self._env(name)]
        if missing:
            return SourceAvailability(
                available=False,
                reason=(
                    f"{self.display_name} needs an API integration. Set "
                    f"{' and '.join(missing)} to enable it."
                ),
                missing_env=missing,
                note=self.notes,
            )
        return SourceAvailability(available=True, note=self.notes)

    @staticmethod
    def _env(name: str) -> str:
        from app.core.config import settings

        return str(getattr(settings, name.lower(), "") or "")

    @abc.abstractmethod
    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        """Fetch postings for one query. Raise on transport failure; the runner
        isolates and records it per source."""
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        avail = self.availability()
        return {
            "key": self.key,
            "display_name": self.display_name,
            "kind": self.kind,
            "requires_credentials": self.requires_credentials,
            "credential_env_vars": list(self.credential_env_vars),
            "available": avail.available,
            "reason": avail.reason,
            "missing_env": avail.missing_env,
            "notes": self.notes,
            "remote_only_source": self.remote_only_source,
        }


class UnavailableSource(JobSource):
    """A portal with no lawful public API.

    These exist so the UI can list the portal and state precisely what is
    needed, instead of silently omitting it or — worse — showing invented
    listings. `fetch` always raises.
    """

    kind = KIND_GATED
    requires_credentials = True

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        avail = self.availability()
        raise SourceUnavailable(avail.reason or f"{self.display_name} is not integrated.")


class SourceUnavailable(RuntimeError):
    """Raised when a source cannot run; recorded as 'skipped', not an error."""
