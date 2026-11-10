"""Adapters that need an API key, plus the portals with no lawful public API.

Important honesty note, since the brief asks for LinkedIn, Indeed, Naukri,
Glassdoor, Wellfound, Internshala and Google Jobs:

  * None of those seven expose a free, public, general-purpose job-search API
    for this use case. LinkedIn's Jobs API is restricted to approved partners;
    Indeed retired its public Publisher job-search API; Naukri, Glassdoor,
    Wellfound and Internshala have no public search API. Scraping them would
    violate their terms, so this application does not scrape them.

  * Google Jobs, LinkedIn and Indeed listings *are* reachable through licensed
    aggregators. `JSearchSource` implements that path against JSearch
    (RapidAPI), which indexes exactly those boards. One key enables all three,
    and each is registered as its own source so the UI can attribute listings
    to the right portal.

  * Adzuna has a genuine free API and is implemented directly.

  * Naukri, Glassdoor, Wellfound and Internshala are registered as `gated`
    sources. They appear in the UI with the precise reason they are inactive
    and what an operator would need to supply. They never return fabricated
    listings — `fetch` raises instead.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.normalize import html_to_text, parse_datetime
from app.services.sources.base import (
    KIND_GATED,
    KIND_LICENSED_API,
    JobSource,
    RawJob,
    SourceAvailability,
    SourceQuery,
    UnavailableSource,
)
from app.services.sources.registry import register_source

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adzuna — real free API
# ---------------------------------------------------------------------------


@register_source
class AdzunaSource(JobSource):
    key = "adzuna"
    display_name = "Adzuna"
    kind = KIND_LICENSED_API
    requires_credentials = True
    credential_env_vars = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
    notes = (
        "Official Adzuna API — free developer tier at developer.adzuna.com. "
        "Aggregates listings from many boards and company career pages."
    )

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        country = (settings.adzuna_country or "in").lower()
        params: dict[str, Any] = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "results_per_page": min(query.limit, 50),
            "content-type": "application/json",
        }
        if query.keywords:
            params["what"] = query.keywords
        if query.location:
            params["where"] = query.location
        if query.job_type == "internship":
            params["what_or"] = "internship intern trainee"

        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{max(1, query.page)}"
        async with httpx.AsyncClient(timeout=settings.source_timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        jobs: list[RawJob] = []
        for item in data.get("results", []) or []:
            job_id = item.get("id")
            url_ = item.get("redirect_url")
            title = item.get("title")
            company = (item.get("company") or {}).get("display_name")
            if not (job_id and url_ and title and company):
                continue

            location = item.get("location") or {}
            areas = location.get("area") or []
            description = item.get("description") or ""

            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            salary_raw = None
            if salary_min or salary_max:
                salary_raw = f"{salary_min or ''}-{salary_max or ''} per year".strip("-")

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(job_id),
                title=str(title).strip(),
                company=str(company).strip(),
                apply_url=url_,
                description=html_to_text(description),
                description_html=description,
                location_raw=location.get("display_name"),
                # Adzuna's `area` is ordered broadest-first: [country, …, city].
                city=areas[-1] if len(areas) >= 2 else None,
                state=areas[-2] if len(areas) >= 3 else None,
                country=areas[0] if areas else None,
                job_type="full_time" if item.get("contract_time") == "full_time" else item.get("contract_time"),
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                salary_currency=_adzuna_currency(country),
                salary_period="year",
                salary_raw=salary_raw,
                posted_at=parse_datetime(item.get("created")),
                tags=[(item.get("category") or {}).get("label") or ""],
            ))
        return jobs


def _adzuna_currency(country: str) -> str:
    return {
        "in": "INR", "gb": "GBP", "us": "USD", "au": "AUD", "ca": "CAD",
        "de": "EUR", "fr": "EUR", "nl": "EUR", "sg": "SGD",
    }.get(country, "USD")


# ---------------------------------------------------------------------------
# JSearch — licensed aggregator covering Google Jobs, LinkedIn and Indeed
# ---------------------------------------------------------------------------


class _JSearchBase(JobSource):
    """Shared JSearch client.

    One RapidAPI key enables every subclass. `jsearch_publisher` filters results
    to the originating board so listings are attributed to the right portal
    rather than all being labelled "JSearch".
    """

    kind = KIND_LICENSED_API
    requires_credentials = True
    credential_env_vars = ("JSEARCH_API_KEY",)
    jsearch_publisher: tuple[str, ...] = ()

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        keywords = query.keywords or "software developer"
        search = f"{keywords} in {query.location}" if query.location else keywords

        params: dict[str, Any] = {
            "query": search,
            "page": str(max(1, query.page)),
            "num_pages": "1",
            "date_posted": "month",
        }
        if query.remote_only:
            params["remote_jobs_only"] = "true"
        if query.job_type == "internship":
            params["employment_types"] = "INTERN"
        elif query.job_type == "part_time":
            params["employment_types"] = "PARTTIME"
        elif query.job_type == "full_time":
            params["employment_types"] = "FULLTIME"

        headers = {
            "X-RapidAPI-Key": settings.jsearch_api_key,
            "X-RapidAPI-Host": settings.jsearch_host,
        }
        async with httpx.AsyncClient(timeout=settings.source_timeout_seconds) as client:
            response = await client.get(
                f"https://{settings.jsearch_host}/search", params=params, headers=headers
            )
            response.raise_for_status()
            data = response.json()

        jobs: list[RawJob] = []
        for item in data.get("data", []) or []:
            job_id = item.get("job_id")
            title = item.get("job_title")
            company = item.get("employer_name")
            apply_url = item.get("job_apply_link") or item.get("job_google_link")
            if not (job_id and title and company and apply_url):
                continue

            # Attribute to the right portal.
            publisher = str(item.get("job_publisher") or "").lower()
            if self.jsearch_publisher:
                if not any(p in publisher for p in self.jsearch_publisher):
                    continue

            html = item.get("job_description") or ""
            employment = str(item.get("job_employment_type") or "").lower()
            required = item.get("job_required_experience") or {}
            months_required = required.get("required_experience_in_months")

            jobs.append(RawJob(
                source=self.key,
                source_job_id=str(job_id),
                title=str(title).strip(),
                company=str(company).strip(),
                apply_url=apply_url,
                description=html_to_text(html),
                description_html=html,
                location_raw=item.get("job_location"),
                city=item.get("job_city"),
                state=item.get("job_state"),
                country=item.get("job_country"),
                is_remote=bool(item.get("job_is_remote")),
                job_type=employment or None,
                experience_min_years=(
                    round(float(months_required) / 12.0, 1) if months_required else None
                ),
                salary_min=item.get("job_min_salary"),
                salary_max=item.get("job_max_salary"),
                salary_currency=item.get("job_salary_currency"),
                salary_period=item.get("job_salary_period"),
                posted_at=parse_datetime(
                    item.get("job_posted_at_datetime_utc")
                    or item.get("job_posted_at_timestamp")
                ),
                deadline_at=parse_datetime(item.get("job_offer_expiration_datetime_utc")),
                extra={"publisher": item.get("job_publisher")},
            ))
        return jobs


@register_source
class GoogleJobsSource(_JSearchBase):
    key = "google_jobs"
    display_name = "Google Jobs"
    notes = (
        "Reached through the JSearch aggregator (RapidAPI), which indexes the "
        "Google Jobs aggregation. Google has no direct public job-search API. "
        "Set JSEARCH_API_KEY to enable."
    )
    # Unfiltered: Google Jobs is itself the aggregation layer.


@register_source
class LinkedInSource(_JSearchBase):
    key = "linkedin"
    display_name = "LinkedIn"
    jsearch_publisher = ("linkedin",)
    notes = (
        "LinkedIn's official Jobs API is restricted to approved partners, so "
        "listings are sourced via the licensed JSearch aggregator and filtered "
        "to LinkedIn-published postings. Set JSEARCH_API_KEY to enable. "
        "LinkedIn is never scraped."
    )


@register_source
class IndeedSource(_JSearchBase):
    key = "indeed"
    display_name = "Indeed"
    jsearch_publisher = ("indeed",)
    notes = (
        "Indeed retired its public Publisher job-search API, so listings are "
        "sourced via the licensed JSearch aggregator and filtered to "
        "Indeed-published postings. Set JSEARCH_API_KEY to enable."
    )


# ---------------------------------------------------------------------------
# Portals with no lawful public API
# ---------------------------------------------------------------------------


class _GatedPortal(UnavailableSource):
    kind = KIND_GATED
    credential_env_vars = ("JSEARCH_API_KEY",)

    def availability(self) -> SourceAvailability:
        return SourceAvailability(
            available=False,
            reason=self.notes,
            missing_env=list(self.credential_env_vars),
            note=self.notes,
        )


@register_source
class NaukriSource(_GatedPortal):
    key = "naukri"
    display_name = "Naukri"
    notes = (
        "Naukri has no public job-search API and its terms prohibit scraping. "
        "Integration requires a commercial Naukri/Infoedge partner agreement. "
        "Listed here for transparency; it returns no jobs and is never "
        "populated with placeholder data."
    )


@register_source
class GlassdoorSource(_GatedPortal):
    key = "glassdoor"
    display_name = "Glassdoor"
    notes = (
        "Glassdoor closed its public API to new applicants and its terms "
        "prohibit scraping. Integration requires a Glassdoor partner "
        "agreement. Listed here for transparency; it returns no jobs."
    )


@register_source
class WellfoundSource(_GatedPortal):
    key = "wellfound"
    display_name = "Wellfound"
    notes = (
        "Wellfound (formerly AngelList Talent) offers no public job-search API. "
        "Integration requires their recruiter/partner API. Listed here for "
        "transparency; it returns no jobs."
    )


@register_source
class InternshalaSource(_GatedPortal):
    key = "internshala"
    display_name = "Internshala"
    notes = (
        "Internshala has no public API and its terms prohibit scraping. "
        "Internship coverage in this build comes from the keyless public feeds "
        "and Adzuna instead. Listed here for transparency; it returns no jobs."
    )
