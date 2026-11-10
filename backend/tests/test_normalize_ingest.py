"""Normalisation and ingestion tests.

The regression tests here exist because each of these was a real bug found
against live feed data, not a hypothetical.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import Job
from app.services.ingest import enrich, ingest_jobs
from app.services.normalize import (
    content_hash,
    html_to_text,
    infer_experience_level,
    infer_job_type,
    infer_work_mode,
    normalise_company,
    normalise_title,
    parse_datetime,
    parse_education_requirement,
    parse_experience_years,
    parse_location,
    parse_salary,
)
from app.services.sources.base import RawJob


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()


def _raw(**over) -> RawJob:
    base = dict(
        source="remotive",
        source_job_id="1",
        title="Backend Developer",
        company="Acme Inc.",
        apply_url="https://example.com/jobs/1",
        description="Requirements:\n- Python and Django\nNice to have:\n- Kubernetes\n",
    )
    base.update(over)
    return RawJob(**base)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def test_html_to_text_preserves_structure():
    html = "<p>Requirements:</p><ul><li>Python</li><li>Django</li></ul><p>Nice to have:</p><ul><li>Go</li></ul>"
    text = html_to_text(html)
    assert "Requirements:" in text
    assert "- Python" in text
    # Structure must survive, since requirement splitting depends on lines.
    assert text.index("Requirements:") < text.index("Nice to have:")


def test_html_to_text_handles_double_escaped_html():
    """Arbeitnow double-escapes its HTML."""
    assert "Location:" in html_to_text("&lt;p&gt;&lt;strong&gt;Location:&lt;/strong&gt; Berlin&lt;/p&gt;")


def test_html_to_text_strips_scripts():
    assert "alert" not in html_to_text("<p>Hi</p><script>alert('x')</script>")


# --------------------------------------------------------------------------
# Company / title normalisation
# --------------------------------------------------------------------------

def test_normalise_company_drops_legal_suffixes():
    assert normalise_company("Acme Inc.") == normalise_company("Acme Technologies Pvt Ltd")


def test_normalise_title_strips_seniority_and_gender_markers():
    assert normalise_title("Senior Backend Developer (m/w/d)") == normalise_title(
        "Backend Developer"
    )


def test_content_hash_is_stable_and_discriminating():
    a = content_hash("Backend Developer", "Acme Inc.", "Pune")
    b = content_hash("backend developer", "Acme Ltd", "Pune")
    c = content_hash("Frontend Developer", "Acme Inc.", "Pune")
    assert a == b
    assert a != c


# --------------------------------------------------------------------------
# Work mode / job type — word-boundary regressions
# --------------------------------------------------------------------------

def test_internship_not_inferred_from_the_word_international():
    """Regression: 'intern' substring-matched 'international', labelling a
    senior accountant role as an internship."""
    assert infer_job_type(
        title="Senior Accountant",
        raw_type=None,
        tags=[],
        description="Join our international finance team in Berlin.",
    ) != "internship"


def test_internship_not_inferred_from_body_mentions():
    assert infer_job_type(
        title="Engineering Manager",
        raw_type=None,
        tags=[],
        description="You will mentor our interns and graduate engineers.",
    ) != "internship"


def test_internship_detected_from_title():
    assert infer_job_type(
        title="Software Engineer Intern", raw_type=None, tags=[], description=""
    ) == "internship"


def test_contract_not_inferred_from_contractual():
    assert infer_job_type(
        title="Software Engineer",
        raw_type="full-time",
        tags=[],
        description="You must meet your contractual obligations.",
    ) == "full_time"


def test_hybrid_beats_generic_remote_mention():
    mode, remote = infer_work_mode(
        location_raw="Pune, Maharashtra",
        description="This is a hybrid role with some remote work allowed.",
        tags=[],
        is_remote=None,
    )
    assert mode == "hybrid"
    assert remote is False


def test_explicit_remote_flag_wins():
    mode, remote = infer_work_mode(
        location_raw="Worldwide", description="", tags=[], is_remote=True
    )
    assert mode == "remote" and remote is True


def test_experience_level_lead_not_matched_from_leading():
    level = infer_experience_level(
        title="Software Engineer",
        description="Join the leading provider of cloud software.",
        min_years=None,
        raw_level=None,
    )
    assert level != "lead"


def test_experience_level_from_min_years():
    assert infer_experience_level(
        title="Software Engineer", description="", min_years=5.0, raw_level=None
    ) == "senior"


# --------------------------------------------------------------------------
# Experience parsing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_min", [
    ("We need at least 3 years of experience in Python.", 3.0),
    ("Minimum of 5 years experience required.", 5.0),
    ("2+ years of relevant experience", 2.0),
    ("8 years experience with distributed systems", 8.0),
])
def test_parse_experience_minimum(text, expected_min):
    assert parse_experience_years(text)[0] == expected_min


def test_parse_experience_range():
    assert parse_experience_years("3 - 5 years of experience") == (3.0, 5.0)


def test_parse_experience_picks_lowest_bar_when_several_stated():
    low, _ = parse_experience_years(
        "5 years of Python experience and 1 year of SQL experience"
    )
    assert low == 1.0


def test_parse_experience_unstated_is_none():
    assert parse_experience_years("Join our wonderful team today!") == (None, None)


def test_fresher_phrasing_yields_zero_not_none():
    assert parse_experience_years("Freshers welcome to apply")[0] == 0.0


# --------------------------------------------------------------------------
# Education parsing
# --------------------------------------------------------------------------

def test_education_requirement_detects_bachelor():
    req = parse_education_requirement("Bachelor's degree in Computer Science required.")
    assert req["min_level"] == 3
    assert "Computer Science" in req["fields"]


def test_education_lowest_acceptable_degree_wins():
    """'Bachelor's or Master's' means a bachelor's suffices."""
    assert parse_education_requirement(
        "Bachelor's or Master's degree in Engineering"
    )["min_level"] == 3


def test_equivalent_experience_clause_removes_the_hard_gate():
    req = parse_education_requirement(
        "Bachelor's degree in Computer Science or equivalent practical experience."
    )
    assert req["equivalent_accepted"] is True
    assert req["min_level"] is None


def test_no_education_statement_returns_empty():
    assert parse_education_requirement("We are a fast growing startup.") == {}


# --------------------------------------------------------------------------
# Salary parsing
# --------------------------------------------------------------------------

def test_salary_range_with_k_suffix():
    result = parse_salary("$120k - $150k per year")
    assert result["salary_min"] == 120_000
    assert result["salary_max"] == 150_000
    assert result["salary_currency"] == "USD"


def test_salary_single_sided_k_suffix():
    """Regression: Remotive writes '$20k -$35k' with one suffix."""
    result = parse_salary("$20k -$35k")
    assert result["salary_min"] == 20_000
    assert result["salary_max"] == 35_000


def test_salary_monthly_is_annualised():
    result = parse_salary("INR 50,000 per month")
    assert result["salary_max"] == 600_000 or result["salary_min"] == 600_000
    assert result["salary_period"] == "month"


def test_salary_indian_lakh_notation():
    result = parse_salary("12 LPA")
    assert result["salary_currency"] == "INR"
    assert (result.get("salary_min") or 0) >= 100_000


def test_salary_hourly_is_annualised():
    result = parse_salary("$50 per hour")
    assert result["salary_min"] == 104_000


def test_implausible_salary_is_discarded():
    result = parse_salary("Salary: 5")
    assert result.get("salary_min") is None


def test_no_salary_returns_empty():
    assert parse_salary(None) == {}


# --------------------------------------------------------------------------
# Location parsing
# --------------------------------------------------------------------------

def test_location_city_state_country():
    result = parse_location("Pune, Maharashtra, India")
    assert result["city"] == "Pune"
    assert result["state"] == "Maharashtra"
    assert result["country"] == "India"


def test_location_infers_indian_state_and_country_from_city():
    result = parse_location("Bengaluru")
    assert result["state"] == "Karnataka"
    assert result["country"] == "India"


def test_location_city_country_pair():
    result = parse_location("Berlin, Germany")
    assert result["city"] == "Berlin"
    assert result["country"] == "Germany"


def test_remote_placeholder_yields_no_city():
    assert parse_location("Worldwide").get("city") is None
    assert parse_location("Remote").get("city") is None


def test_remote_with_qualifier_extracts_inner_location():
    assert parse_location("Remote (India)").get("country") == "India"


def test_location_strips_leading_mode_marker():
    assert parse_location("Hybrid - Pune, Maharashtra")["city"] == "Pune"


def test_multi_location_takes_the_first():
    assert parse_location("Europe, Berlin; Europe, Hamburg")["city"] == "Europe"


# --------------------------------------------------------------------------
# Date parsing
# --------------------------------------------------------------------------

def test_parse_datetime_iso_and_epoch():
    assert parse_datetime("2026-11-02T20:01:00").year == 2026
    assert parse_datetime(1793926523).year >= 2026
    assert parse_datetime("2026-11-02").month == 11


def test_parse_datetime_relative():
    result = parse_datetime("3 days ago")
    assert result is not None
    assert (datetime.now(timezone.utc) - result) >= timedelta(days=2)


def test_parse_datetime_garbage_is_none():
    assert parse_datetime("sometime soon") is None
    assert parse_datetime(None) is None


# --------------------------------------------------------------------------
# Enrichment
# --------------------------------------------------------------------------

def test_enrich_splits_mandatory_and_preferred():
    values = enrich(_raw())
    assert "Python" in values["required_skills"]
    assert "Django" in values["required_skills"]
    assert "Kubernetes" in values["preferred_skills"]
    assert "Kubernetes" not in values["required_skills"]


def test_enrich_clamps_internship_experience_floor():
    """An internship cannot carry a 5-year requirement, whatever the prose says."""
    values = enrich(_raw(
        title="Software Engineer Intern",
        description="We need at least 5 years of experience.",
    ))
    assert values["job_type"] == "internship"
    assert values["experience_min_years"] == 0.0
    assert values["experience_max_years"] == 1.0


def test_enrich_pulls_skills_from_tags_and_title():
    values = enrich(_raw(title="React Developer", tags=["TypeScript", "GraphQL"]))
    assert "React" in values["all_skills"]
    assert "TypeScript" in values["all_skills"]


# --------------------------------------------------------------------------
# Ingestion and deduplication
# --------------------------------------------------------------------------

def test_ingest_inserts_and_embeds(db):
    stats = ingest_jobs(db, [_raw()])
    db.commit()
    assert stats.inserted == 1
    job = db.query(Job).one()
    assert job.embedding
    assert job.embedding_model


def test_duplicate_source_id_within_one_batch_is_collapsed(db):
    """Regression: a run issues several keyword queries per source, so the same
    posting arrives twice in one batch before any flush — this previously hit
    the unique constraint and killed the whole run."""
    stats = ingest_jobs(db, [_raw(), _raw(), _raw()])
    db.commit()
    assert db.query(Job).count() == 1
    assert stats.inserted == 1
    assert stats.updated == 2


def test_refetching_a_known_posting_updates_in_place(db):
    ingest_jobs(db, [_raw()])
    db.commit()
    first_seen = db.query(Job).one().first_seen_at

    stats = ingest_jobs(db, [_raw(title="Backend Developer II")])
    db.commit()
    job = db.query(Job).one()
    assert stats.updated == 1
    assert job.title == "Backend Developer II"
    assert job.first_seen_at == first_seen


def test_cross_source_duplicate_is_linked_not_duplicated(db):
    ingest_jobs(db, [_raw(source="remotive", source_job_id="a")])
    db.commit()
    stats = ingest_jobs(db, [_raw(source="remoteok", source_job_id="b")])
    db.commit()

    assert stats.duplicates == 1
    canonical = db.query(Job).filter(Job.source == "remotive").one()
    duplicate = db.query(Job).filter(Job.source == "remoteok").one()
    assert duplicate.duplicate_of_id == canonical.id
    assert duplicate.is_active is False
    assert "remoteok" in canonical.also_seen_on


def test_different_roles_at_same_company_are_not_merged(db):
    ingest_jobs(db, [
        _raw(source_job_id="a", title="Backend Developer"),
        _raw(source_job_id="b", title="Marketing Manager"),
    ])
    db.commit()
    assert db.query(Job).filter(Job.duplicate_of_id.is_(None)).count() == 2


def test_malformed_job_does_not_abort_the_batch(db):
    """One bad posting must not cost the rest of the batch."""
    good = _raw(source_job_id="good")
    bad = _raw(source_job_id="bad", title=None)  # type: ignore[arg-type]
    stats = ingest_jobs(db, [bad, good])
    db.commit()
    assert stats.fetched == 2
    assert db.query(Job).count() == 1
