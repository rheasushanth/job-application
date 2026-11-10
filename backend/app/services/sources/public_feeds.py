"""Adapters for free, keyless public job APIs.

These four are the sources that work out of the box, so the application has
real listings without any credentials. Each one's payload shape was verified
against the live endpoint; field names are not guessed.

  Remotive   https://remotive.com/api/remote-jobs
  Arbeitnow  https://www.arbeitnow.com/api/job-board-api
  Jobicy     https://jobicy.com/api/v2/remote-jobs
  RemoteOK   https://remoteok.com/api
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalize import html_to_text, parse_datetime
from app.services.sources.base import (
    KIND_PUBLIC_API,
    JobSource,
    RawJob,
    SourceQuery,
)
from app.services.sources.registry import register_source

logger = logging.getLogger(__name__)

USER_AGENT = "JobMatch/1.0 (resume matching platform; contact: admin@jobmatch.local)"


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(
        timeout=settings.source_timeout_seconds,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


@register_source
class RemotiveSource(JobSource):
    key = "remotive"
    display_name = "Remotive"
    kind = KIND_PUBLIC_API
    remote_only_source = True
    notes = "Free public API for remote jobs. No credentials required."

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        # `search` and `limit` are sent because they are documented, but this
        # endpoint currently ignores both and returns a fixed recent window —
        # verified against the live API. So relevance filtering is applied
        # client-side, as with the other keyless feeds.
        params: dict[str, Any] = {"limit": min(query.limit, 100)}
        if query.keywords:
            params["search"] = query.keywords
        data = await _get_json("https://remotive.com/api/remote-jobs", params)

        terms = [t for t in (query.keywords or "").lower().split() if len(t) > 2]
        jobs: list[RawJob] = []

        for item in data.get("jobs", []) or []:
            job_id = item.get("id")
            url = item.get("url")
            title = item.get("title")
            company = item.get("company_name")
            if not (job_id and url and title and company):
                continue

            html = item.get("description") or ""
            text = html_to_text(html)

            if terms:
                haystack = (
                    f"{title} {item.get('category') or ''} "
                    f"{' '.join(item.get('tags') or [])} {text[:3000]}"
                ).lower()
                if not any(term in haystack for term in terms):
                    continue

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(job_id),
                title=title.strip(),
                company=company.strip(),
                apply_url=url,
                description=text,
                description_html=html,
                location_raw=item.get("candidate_required_location"),
                is_remote=True,
                work_mode="remote",
                job_type=item.get("job_type"),
                salary_raw=item.get("salary") or None,
                posted_at=parse_datetime(item.get("publication_date")),
                tags=[t for t in (item.get("tags") or []) if isinstance(t, str)],
                extra={"category": item.get("category")},
            ))
        return jobs


@register_source
class ArbeitnowSource(JobSource):
    key = "arbeitnow"
    display_name = "Arbeitnow"
    kind = KIND_PUBLIC_API
    notes = "Free public job board API, Europe-weighted. No credentials required."

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        # This feed has no server-side search, so it is filtered client-side.
        data = await _get_json(
            "https://www.arbeitnow.com/api/job-board-api", {"page": max(1, query.page)}
        )

        terms = [t for t in (query.keywords or "").lower().split() if len(t) > 2]
        jobs: list[RawJob] = []

        for item in data.get("data", []) or []:
            slug = item.get("slug")
            url = item.get("url")
            title = item.get("title")
            company = item.get("company_name")
            if not (slug and url and title and company):
                continue

            html = item.get("description") or ""
            text = html_to_text(html)

            if terms:
                haystack = f"{title} {' '.join(item.get('tags') or [])} {text[:3000]}".lower()
                if not any(term in haystack for term in terms):
                    continue

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(slug),
                title=title.strip(),
                company=company.strip(),
                apply_url=url,
                description=text,
                description_html=html,
                location_raw=item.get("location"),
                is_remote=bool(item.get("remote")),
                job_type=", ".join(item.get("job_types") or []) or None,
                posted_at=parse_datetime(item.get("created_at")),
                tags=[t for t in (item.get("tags") or []) if isinstance(t, str)],
            ))
            if len(jobs) >= query.limit:
                break
        return jobs


@register_source
class JobicySource(JobSource):
    key = "jobicy"
    display_name = "Jobicy"
    kind = KIND_PUBLIC_API
    remote_only_source = True
    notes = "Free public API for remote jobs. No credentials required."

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        params: dict[str, Any] = {"count": min(query.limit, 50)}
        if query.keywords:
            params["tag"] = query.keywords

        try:
            data = await _get_json("https://jobicy.com/api/v2/remote-jobs", params)
        except httpx.HTTPStatusError as exc:
            # The `tag` filter 404s on terms it doesn't recognise (it expects a
            # known tag, not free text). Retry unfiltered and filter locally
            # rather than losing the source for this query.
            if exc.response.status_code != 404 or not query.keywords:
                raise
            data = await _get_json(
                "https://jobicy.com/api/v2/remote-jobs", {"count": min(query.limit, 50)}
            )

        terms = [t for t in (query.keywords or "").lower().split() if len(t) > 2]
        jobs: list[RawJob] = []
        for item in data.get("jobs", []) or []:
            job_id = item.get("id")
            url = item.get("url")
            title = item.get("jobTitle")
            company = item.get("companyName")
            if not (job_id and url and title and company):
                continue

            html = item.get("jobDescription") or item.get("jobExcerpt") or ""
            job_types = item.get("jobType") or []
            if isinstance(job_types, str):
                job_types = [job_types]

            if terms:
                industries = " ".join(
                    str(t) for t in (item.get("jobIndustry") or []) if t
                )
                haystack = f"{title} {industries} {html_to_text(html)[:2000]}".lower()
                if not any(term in haystack for term in terms):
                    continue

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(job_id),
                title=title.strip(),
                company=company.strip(),
                apply_url=url,
                description=html_to_text(html),
                description_html=html,
                location_raw=item.get("jobGeo"),
                is_remote=True,
                work_mode="remote",
                job_type=", ".join(str(t) for t in job_types) or None,
                experience_level=item.get("jobLevel"),
                salary_raw=_jobicy_salary(item),
                posted_at=parse_datetime(item.get("pubDate")),
                tags=[t for t in (item.get("jobIndustry") or []) if isinstance(t, str)],
            ))
        return jobs


def _jobicy_salary(item: dict[str, Any]) -> str | None:
    low = item.get("annualSalaryMin")
    high = item.get("annualSalaryMax")
    currency = item.get("salaryCurrency") or "USD"
    if low and high:
        return f"{currency} {low} - {high} per year"
    if low:
        return f"{currency} {low} per year"
    return None


@register_source
class RemoteOKSource(JobSource):
    key = "remoteok"
    display_name = "RemoteOK"
    kind = KIND_PUBLIC_API
    remote_only_source = True
    notes = "Free public API for remote jobs. No credentials required."

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        data = await _get_json("https://remoteok.com/api")
        if not isinstance(data, list):
            return []

        terms = [t for t in (query.keywords or "").lower().split() if len(t) > 2]
        jobs: list[RawJob] = []

        # The first element is a legal/attribution notice, not a posting.
        for item in data:
            if not isinstance(item, dict) or not item.get("id"):
                continue

            title = item.get("position") or item.get("title")
            company = item.get("company")
            url = item.get("url") or item.get("apply_url")
            if not (title and company and url):
                continue

            html = item.get("description") or ""
            text = html_to_text(html)
            tags = [t for t in (item.get("tags") or []) if isinstance(t, str)]

            if terms:
                haystack = f"{title} {' '.join(tags)} {text[:3000]}".lower()
                if not any(term in haystack for term in terms):
                    continue

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(item["id"]),
                title=str(title).strip(),
                company=str(company).strip(),
                apply_url=url,
                description=text,
                description_html=html,
                location_raw=item.get("location") or "Remote",
                is_remote=True,
                work_mode="remote",
                salary_raw=_remoteok_salary(item),
                posted_at=parse_datetime(item.get("date") or item.get("epoch")),
                tags=tags,
            ))
            if len(jobs) >= query.limit:
                break
        return jobs


def _remoteok_salary(item: dict[str, Any]) -> str | None:
    low = item.get("salary_min")
    high = item.get("salary_max")
    if low and high:
        return f"USD {low} - {high} per year"
    if low:
        return f"USD {low} per year"
    return None
