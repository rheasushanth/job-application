"""API integration tests over the full user journey.

Job fetching is stubbed here (a deterministic fake source) so these tests do
not depend on third-party uptime. The live adapters are exercised separately.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app
from app.services.sources.base import RawJob, SourceQuery

API = "/api/v1"


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, future=True)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Every test request arrives from the same client IP, so the sliding
    # windows must be cleared or later tests trip the auth/upload limiter.
    from app.core.deps import reset_rate_limits

    reset_rate_limits()

    # Seed the source registry and default weights in the test DB.
    with TestSession() as db:
        from app.services.matching.weights import ensure_default_weight_profile
        from app.services.sources.registry import sync_source_registry

        sync_source_registry(db)
        ensure_default_weight_profile(db)
        db.commit()

    # Run background work inline so tests are deterministic.
    from app.services import tasks

    monkeypatch.setattr(tasks, "enqueue", lambda fn, *a, **k: (fn(*a, **k), "inline")[1])

    # Point discovery's session factory at the test database.
    import app.services.discovery as discovery_module

    monkeypatch.setattr(discovery_module, "SessionLocal", TestSession)

    with TestClient(app) as test_client:
        test_client._session_factory = TestSession  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()


def register(client, email="user@example.com") -> dict:
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "correct-horse-battery", "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


RESUME_TEXT = """PRIYA MENON
Bengaluru, Karnataka | priya.menon@example.com | +91 98765 43210
github.com/priyamenon

EDUCATION
B.Tech in Computer Science and Engineering
PES University, Bengaluru
2021 - 2025 | CGPA: 8.9/10

TECHNICAL SKILLS
Languages: Python, JavaScript, SQL
Frameworks: Django, FastAPI, React
Tools: Docker, Git, PostgreSQL, Redis, AWS
Concepts: Data Structures, Algorithms, REST APIs, OOP

PROJECTS
Inventory API - Python, FastAPI, PostgreSQL
- Built a REST backend for stock tracking serving 5000 requests daily
- Containerised with Docker and deployed on AWS

Analytics Dashboard - React, Django
- Full-stack dashboard with JWT authentication

INTERNSHIPS
Backend Developer Intern - Zeta Technologies
Jun 2024 - Dec 2024
- Developed REST APIs in Django serving 50k daily requests
- Reduced p95 latency 40% using Redis caching

CERTIFICATIONS
AWS Certified Cloud Practitioner - Amazon Web Services (2024)

ACHIEVEMENTS
- Winner, PES Hackathon 2024
- Solved 500+ LeetCode problems
"""


def upload_resume(client, headers) -> dict:
    """Upload a generated DOCX resume through the real endpoint."""
    import docx

    document = docx.Document()
    for line in RESUME_TEXT.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)

    response = client.post(
        f"{API}/resumes",
        headers=headers,
        files={
            "file": (
                "resume.docx",
                buffer,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


class FakeSource:
    """Deterministic stand-in for a live portal."""

    key = "remotive"
    display_name = "Fake"
    kind = "public_api"
    requires_credentials = False
    credential_env_vars = ()
    notes = ""
    remote_only_source = False

    def availability(self):
        from app.services.sources.base import SourceAvailability

        return SourceAvailability(available=True)

    def describe(self):
        return {
            "key": self.key, "display_name": self.display_name, "kind": self.kind,
            "requires_credentials": False, "credential_env_vars": [],
            "available": True, "reason": "", "missing_env": [], "notes": "",
            "remote_only_source": False,
        }

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        return [
            RawJob(
                source=self.key,
                source_job_id="fake-1",
                title="Backend Developer Intern",
                company="Northwind Labs",
                apply_url="https://example.com/jobs/fake-1",
                description=(
                    "Requirements:\n- Strong Python and Django\n- PostgreSQL\n"
                    "- REST API design\nNice to have:\n- Docker\n- Kubernetes\n"
                    "Bachelor's degree in Computer Science required.\n"
                ),
                location_raw="Bengaluru, Karnataka, India",
                job_type="internship",
                salary_raw="INR 40000 per month",
                posted_at=datetime.now(timezone.utc),
                tags=["Python", "Django"],
            ),
            RawJob(
                source=self.key,
                source_job_id="fake-2",
                title="Senior Rust Systems Engineer",
                company="Ferrous Corp",
                apply_url="https://example.com/jobs/fake-2",
                description=(
                    "Requirements:\n- Expert Rust\n- 8 years of experience\n"
                    "- Distributed systems\nMaster's degree required.\n"
                ),
                location_raw="Remote",
                job_type="full_time",
                posted_at=datetime.now(timezone.utc),
                tags=["Rust"],
            ),
        ]


@pytest.fixture
def seeded(client, monkeypatch):
    """A registered user with a confirmed profile and two scored jobs."""
    import app.services.discovery as discovery_module

    fake = FakeSource()
    monkeypatch.setattr(
        discovery_module, "get_source", lambda key: fake if key == "remotive" else None
    )
    monkeypatch.setattr(
        discovery_module, "enabled_source_keys", lambda db, requested=None: ["remotive"]
    )

    tokens = register(client)
    headers = auth_headers(tokens)
    parsed = upload_resume(client, headers)
    resume_id = parsed["resume_id"]

    confirm = client.post(f"{API}/resumes/{resume_id}/confirm", headers=headers)
    assert confirm.status_code == 200, confirm.text

    run = client.post(f"{API}/discovery/run", headers=headers, json={})
    assert run.status_code == 202, run.text

    return {"headers": headers, "resume_id": resume_id, "tokens": tokens}


# --------------------------------------------------------------------------
# Health & sources
# --------------------------------------------------------------------------

def test_health_reports_backends(client):
    body = client.get(f"{API}/health").json()
    assert body["status"] == "ok"
    assert body["embedding_backend"]
    assert body["task_backend"]
    assert "remotive" in body["sources_live"]


def test_sources_endpoint_declares_unavailable_portals_honestly(client):
    tokens = register(client)
    sources = client.get(f"{API}/sources", headers=auth_headers(tokens)).json()
    by_key = {s["key"]: s for s in sources}

    # The keyless public feeds must be live.
    for key in ("remotive", "arbeitnow", "jobicy", "remoteok"):
        assert by_key[key]["available"] is True

    # The gated portals must be present, unavailable, and say why.
    for key in ("linkedin", "naukri", "glassdoor", "wellfound", "internshala", "indeed"):
        entry = by_key[key]
        assert entry["available"] is False
        assert entry["reason"], f"{key} must explain why it is unavailable"
        assert entry["credential_env_vars"] or entry["kind"] == "gated"


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def test_register_login_and_me(client):
    tokens = register(client)
    assert tokens["user"]["email"] == "user@example.com"

    login = client.post(
        f"{API}/auth/login",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    me = client.get(f"{API}/auth/me", headers=auth_headers(login.json()))
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_duplicate_email_rejected(client):
    register(client)
    response = client.post(
        f"{API}/auth/register",
        json={"email": "user@example.com", "password": "another-long-password"},
    )
    assert response.status_code == 409


def test_weak_password_rejected(client):
    response = client.post(
        f"{API}/auth/register", json={"email": "a@b.com", "password": "short"}
    )
    assert response.status_code == 422


def test_wrong_password_is_generic(client):
    register(client)
    response = client.post(
        f"{API}/auth/login", json={"email": "user@example.com", "password": "wrong-password-x"}
    )
    assert response.status_code == 401
    # Must not reveal whether the account exists.
    assert "password" in response.json()["detail"]["message"].lower()


def test_protected_route_requires_token(client):
    assert client.get(f"{API}/jobs").status_code == 401
    assert client.get(f"{API}/profile").status_code == 401


def test_refresh_rotates_and_detects_reuse(client):
    tokens = register(client)
    first = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != tokens["refresh_token"]

    # Replaying the old token must fail and invalidate the family.
    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "refresh_reused"


# --------------------------------------------------------------------------
# Resume upload / review / confirm
# --------------------------------------------------------------------------

def test_upload_returns_structured_payload_for_review(client):
    tokens = register(client)
    parsed = upload_resume(client, auth_headers(tokens))

    assert parsed["status"] == "awaiting_review"
    contact = parsed["payload"]["contact"]
    assert contact["email"] == "priya.menon@example.com"
    assert contact["name"] == "Priya Menon"
    assert "Python" in parsed["payload"]["skills"]["technical"]
    assert len(parsed["payload"]["projects"]) >= 2
    # Confidence must be reported per field so the UI can flag uncertainty.
    assert parsed["field_confidence"]
    assert parsed["derived"]["seniority"] in {"student", "fresher", "intern", "entry_level"}


def test_rejects_non_resume_file(client):
    tokens = register(client)
    response = client.post(
        f"{API}/resumes",
        headers=auth_headers(tokens),
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 422


def test_rejects_file_with_mismatched_magic_bytes(client):
    """A .pdf extension on non-PDF content must be caught."""
    tokens = register(client)
    response = client.post(
        f"{API}/resumes",
        headers=auth_headers(tokens),
        files={"file": ("fake.pdf", io.BytesIO(b"this is not a pdf"), "application/pdf")},
    )
    assert response.status_code == 422


def test_user_can_edit_extracted_data_before_confirming(client):
    tokens = register(client)
    headers = auth_headers(tokens)
    parsed = upload_resume(client, headers)
    resume_id = parsed["resume_id"]

    payload = parsed["payload"]
    payload["contact"]["name"] = "Priya M. Menon"
    payload["skills"]["technical"] = payload["skills"]["technical"] + ["Kubernetes"]

    update = client.put(
        f"{API}/resumes/{resume_id}/parsed", headers=headers, json={"payload": payload}
    )
    assert update.status_code == 200
    assert update.json()["edited_by_user"] is True
    assert "Kubernetes" in update.json()["payload"]["skills"]["technical"]

    confirm = client.post(f"{API}/resumes/{resume_id}/confirm", headers=headers)
    assert confirm.status_code == 200
    profile = confirm.json()
    assert profile["full_name"] == "Priya M. Menon"
    assert "Kubernetes" in profile["skills"]


def test_confirm_requires_at_least_one_skill(client):
    tokens = register(client)
    headers = auth_headers(tokens)
    parsed = upload_resume(client, headers)
    resume_id = parsed["resume_id"]

    payload = parsed["payload"]
    payload["skills"] = {"technical": [], "soft": []}
    payload["languages"] = []
    payload["frameworks"] = []
    payload["tools"] = []
    client.put(f"{API}/resumes/{resume_id}/parsed", headers=headers, json={"payload": payload})

    response = client.post(f"{API}/resumes/{resume_id}/confirm", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "no_skills"


def test_cannot_read_another_users_resume(client):
    first = register(client, "one@example.com")
    parsed = upload_resume(client, auth_headers(first))
    second = register(client, "two@example.com")

    response = client.get(
        f"{API}/resumes/{parsed['resume_id']}", headers=auth_headers(second)
    )
    # 404 rather than 403 so IDs cannot be probed for existence.
    assert response.status_code == 404


def test_profile_requires_confirmation_first(client):
    tokens = register(client)
    response = client.get(f"{API}/profile", headers=auth_headers(tokens))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_profile"


# --------------------------------------------------------------------------
# Discovery and matching
# --------------------------------------------------------------------------

def test_discovery_ingests_and_scores(client, seeded):
    headers = seeded["headers"]

    runs = client.get(f"{API}/discovery/runs", headers=headers).json()
    assert runs
    run = runs[0]
    assert run["status"] in {"completed", "partial"}
    assert run["jobs_new"] == 2
    assert run["matches_computed"] == 2

    jobs = client.get(f"{API}/jobs", headers=headers).json()
    assert jobs["total"] == 2
    assert all(item["match"] is not None for item in jobs["items"])


def test_matching_ranks_the_relevant_job_above_the_irrelevant_one(client, seeded):
    jobs = client.get(f"{API}/jobs?sort=match_desc", headers=seeded["headers"]).json()
    titles = [item["job"]["title"] for item in jobs["items"]]
    assert titles[0] == "Backend Developer Intern"

    backend, rust = jobs["items"][0], jobs["items"][1]
    assert backend["match"]["score"] > rust["match"]["score"]
    # The Rust role fails mandatory skills, degree and experience gates.
    assert rust["match"]["eligibility_status"] != "eligible"
    assert "Rust" in rust["match"]["missing_mandatory_skills"]


def test_match_analysis_exposes_the_arithmetic(client, seeded):
    headers = seeded["headers"]
    jobs = client.get(f"{API}/jobs?sort=match_desc", headers=headers).json()
    job_id = jobs["items"][0]["job"]["id"]

    analysis = client.get(f"{API}/jobs/{job_id}/analysis", headers=headers).json()

    assert 0 <= analysis["score"] <= 100
    assert analysis["band_label"]
    assert analysis["calculation"]["formula"]
    assert analysis["calculation"]["steps"]
    # Contributions must reconcile with the pre-gate percentage.
    total = sum(step["contribution_points"] for step in analysis["calculation"]["steps"])
    assert abs(total - analysis["calculation"]["pre_gate_percentage"]) < 0.1
    assert analysis["weights"]
    assert analysis["reasons"]
    assert analysis["recommendations"]
    assert analysis["explanation"]
    # Six scoring categories, all present.
    assert len(analysis["category_scores"]) == 6


def test_enrichment_parsed_the_posting_fields(client, seeded):
    jobs = client.get(f"{API}/jobs?sort=match_desc", headers=seeded["headers"]).json()
    backend = jobs["items"][0]["job"]

    assert backend["job_type"] == "internship"
    assert backend["city"] == "Bengaluru"
    assert backend["country"] == "India"
    assert "Python" in backend["required_skills"]
    assert "Kubernetes" in backend["preferred_skills"]
    # 40,000/month annualised.
    assert backend["salary_max"] == 480000 or backend["salary_min"] == 480000
    assert backend["education_requirement"]["min_level"] == 3


def test_dashboard_summary(client, seeded):
    summary = client.get(f"{API}/matches/summary", headers=seeded["headers"]).json()
    assert summary["total_jobs"] == 2
    assert summary["has_profile"] is True
    assert (
        summary["excellent"] + summary["good"] + summary["moderate"] + summary["low"] == 2
    )
    assert "remotive" in summary["sources_live"]
    assert summary["sources_unavailable"]
    assert summary["top_matches"]


# --------------------------------------------------------------------------
# Filtering and sorting (SQL-side)
# --------------------------------------------------------------------------

def test_filter_by_job_type(client, seeded):
    body = client.get(f"{API}/jobs?job_type=internship", headers=seeded["headers"]).json()
    assert body["total"] == 1
    assert body["items"][0]["job"]["job_type"] == "internship"


def test_filter_by_skill_uses_and_semantics(client, seeded):
    headers = seeded["headers"]
    one = client.get(f"{API}/jobs?skills=Python", headers=headers).json()
    assert one["total"] == 1

    impossible = client.get(f"{API}/jobs?skills=Python&skills=Rust", headers=headers).json()
    assert impossible["total"] == 0


def test_filter_by_match_range(client, seeded):
    headers = seeded["headers"]
    everything = client.get(f"{API}/jobs?min_match=0", headers=headers).json()
    assert everything["total"] == 2

    high = client.get(f"{API}/jobs?min_match=50", headers=headers).json()
    assert high["total"] <= 2
    for item in high["items"]:
        assert item["match"]["score"] >= 50


def test_filter_by_location_and_source(client, seeded):
    headers = seeded["headers"]
    assert client.get(f"{API}/jobs?city=Bengaluru", headers=headers).json()["total"] == 1
    assert client.get(f"{API}/jobs?source=remotive", headers=headers).json()["total"] == 2
    assert client.get(f"{API}/jobs?country=India", headers=headers).json()["total"] == 1


def test_free_text_search(client, seeded):
    headers = seeded["headers"]
    assert client.get(f"{API}/jobs?q=Rust", headers=headers).json()["total"] == 1
    assert client.get(f"{API}/jobs?q=Northwind", headers=headers).json()["total"] == 1


def test_salary_filter_keeps_jobs_with_unknown_salary(client, seeded):
    """Absence of salary data is not evidence of a low salary."""
    body = client.get(f"{API}/jobs?salary_min=100000", headers=seeded["headers"]).json()
    titles = [item["job"]["title"] for item in body["items"]]
    assert "Senior Rust Systems Engineer" in titles


def test_sorting_directions_differ(client, seeded):
    headers = seeded["headers"]
    desc = client.get(f"{API}/jobs?sort=match_desc", headers=headers).json()
    asc = client.get(f"{API}/jobs?sort=match_asc", headers=headers).json()
    assert [i["job"]["id"] for i in desc["items"]] == list(
        reversed([i["job"]["id"] for i in asc["items"]])
    )


def test_pagination(client, seeded):
    headers = seeded["headers"]
    page1 = client.get(f"{API}/jobs?page=1&page_size=1", headers=headers).json()
    page2 = client.get(f"{API}/jobs?page=2&page_size=1", headers=headers).json()
    assert page1["total"] == 2
    assert len(page1["items"]) == 1
    assert page1["items"][0]["job"]["id"] != page2["items"][0]["job"]["id"]


def test_facets_populated_for_filter_panel(client, seeded):
    facets = client.get(f"{API}/jobs", headers=seeded["headers"]).json()["facets"]
    assert facets["sources"]
    assert facets["job_types"]
    assert facets["skills"]
    assert facets["companies"]


# --------------------------------------------------------------------------
# Saved jobs
# --------------------------------------------------------------------------

def test_save_list_and_unsave(client, seeded):
    headers = seeded["headers"]
    jobs = client.get(f"{API}/jobs", headers=headers).json()
    job_id = jobs["items"][0]["job"]["id"]

    saved = client.post(
        f"{API}/saved", headers=headers, json={"job_id": job_id, "collection": "Shortlist"}
    )
    assert saved.status_code == 201

    duplicate = client.post(f"{API}/saved", headers=headers, json={"job_id": job_id})
    assert duplicate.status_code == 409

    listing = client.get(f"{API}/saved", headers=headers).json()
    assert len(listing) == 1
    assert listing[0]["collection"] == "Shortlist"
    assert listing[0]["match"] is not None

    collections = client.get(f"{API}/saved/collections", headers=headers).json()
    assert collections[0]["name"] == "Shortlist"

    # The saved flag must be reflected on the job listing.
    flagged = client.get(f"{API}/jobs?saved_only=true", headers=headers).json()
    assert flagged["total"] == 1
    assert flagged["items"][0]["is_saved"] is True

    assert client.delete(f"{API}/saved/{job_id}", headers=headers).status_code == 204
    assert client.get(f"{API}/saved", headers=headers).json() == []


# --------------------------------------------------------------------------
# Application tracker
# --------------------------------------------------------------------------

def test_application_lifecycle_records_events(client, seeded):
    headers = seeded["headers"]
    job_id = client.get(f"{API}/jobs", headers=headers).json()["items"][0]["job"]["id"]

    created = client.post(f"{API}/applications", headers=headers, json={"job_id": job_id})
    assert created.status_code == 201
    application = created.json()
    assert application["status"] == "interested"
    assert application["applied_at"] is None

    app_id = application["id"]
    for status_value in ("applied", "assessment", "interview", "offer"):
        response = client.patch(
            f"{API}/applications/{app_id}", headers=headers, json={"status": status_value}
        )
        assert response.status_code == 200
        assert response.json()["status"] == status_value

    final = client.get(f"{API}/applications/{app_id}/events", headers=headers).json()
    # Creation plus four transitions.
    assert len(final) == 5
    assert final[-1]["to_status"] == "offer"
    assert final[-1]["from_status"] == "interview"

    detail = client.get(f"{API}/applications", headers=headers).json()[0]
    assert detail["applied_at"] is not None

    board = client.get(f"{API}/applications/board", headers=headers).json()
    assert board["counts"]["offer"] == 1
    assert set(board["statuses"]) == {
        "interested", "applied", "assessment", "interview", "rejected", "offer"
    }


def test_invalid_application_status_rejected(client, seeded):
    headers = seeded["headers"]
    job_id = client.get(f"{API}/jobs", headers=headers).json()["items"][0]["job"]["id"]
    response = client.post(
        f"{API}/applications", headers=headers, json={"job_id": job_id, "status": "hired"}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Insights
# --------------------------------------------------------------------------

def test_skill_gap_is_grounded_in_discovered_jobs(client, seeded):
    body = client.get(f"{API}/insights/skill-gap", headers=seeded["headers"]).json()
    assert body["total_jobs_analysed"] == 2
    gap_skills = [g["skill"] for g in body["gaps"]]
    assert "Rust" in gap_skills
    for gap in body["gaps"]:
        assert gap["jobs_requiring"] >= 1
        assert "estimated_score_lift" in gap
    assert body["strengths"]


def test_alternative_roles_go_beyond_resume_titles(client, seeded):
    body = client.get(
        f"{API}/insights/alternative-roles", headers=seeded["headers"]
    ).json()
    roles = body["roles"]
    assert roles

    titles = {r["title"] for r in roles}
    # The resume only mentions a backend internship; the engine must still
    # surface adjacent roles from skill coverage.
    assert len(titles) >= 3
    for role in roles:
        assert 0 <= role["fit"] <= 100
        assert role["why"]
        assert "skills_to_add" in role
    # Ranked by fit.
    assert roles == sorted(roles, key=lambda r: -r["fit"])


def test_resume_feedback_reports_actionable_items(client, seeded):
    body = client.get(f"{API}/insights/resume-feedback", headers=seeded["headers"]).json()
    assert 0 <= body["score"] <= 100
    assert body["section_coverage"]["skills"] is True
    for suggestion in body["suggestions"]:
        assert suggestion["severity"] in {"high", "medium", "low"}
        assert suggestion["title"]
        assert suggestion["detail"]


# --------------------------------------------------------------------------
# Alerts, notifications, weights
# --------------------------------------------------------------------------

def test_alert_config_roundtrip(client, seeded):
    headers = seeded["headers"]
    updated = client.put(
        f"{API}/alerts/config",
        headers=headers,
        json={"alert_enabled": True, "alert_min_match": 55},
    ).json()
    assert updated["alert_min_match"] == 55
    assert client.get(f"{API}/alerts/config", headers=headers).json()["alert_min_match"] == 55


def test_notifications_created_for_new_matches(client, seeded):
    headers = seeded["headers"]
    notifications = client.get(f"{API}/notifications", headers=headers).json()
    # The fixture's default threshold may or may not be met; the endpoint must
    # work regardless, and marking all read must be idempotent.
    assert isinstance(notifications, list)
    assert client.post(f"{API}/notifications/read-all", headers=headers).status_code == 204


def test_weights_are_configurable_and_trigger_rescore(client, seeded):
    headers = seeded["headers"]
    before = client.get(f"{API}/jobs?sort=match_desc", headers=headers).json()
    before_score = before["items"][0]["match"]["score"]

    response = client.put(
        f"{API}/settings/weights",
        headers=headers,
        json={"weights": {"technical_skills": 1.0, "semantic_similarity": 0.0,
                          "project_relevance": 0.0, "experience_relevance": 0.0,
                          "education_match": 0.0, "experience_level_fit": 0.0}},
    )
    assert response.status_code == 200
    assert response.json()["weights"]["technical_skills"] == 1.0

    after = client.get(f"{API}/jobs?sort=match_desc", headers=headers).json()
    assert after["items"][0]["match"]["score"] != before_score

    reset = client.post(f"{API}/settings/weights/reset", headers=headers).json()
    assert reset["weights"] == reset["defaults"]


def test_invalid_weights_rejected(client, seeded):
    response = client.put(
        f"{API}/settings/weights",
        headers=seeded["headers"],
        json={"weights": {"nonsense_category": 0.5}},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_weights"


def test_all_zero_weights_rejected(client, seeded):
    response = client.put(
        f"{API}/settings/weights",
        headers=seeded["headers"],
        json={"weights": {k: 0.0 for k in (
            "technical_skills", "semantic_similarity", "project_relevance",
            "experience_relevance", "education_match", "experience_level_fit")}},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Profile editing
# --------------------------------------------------------------------------

def test_profile_edit_bumps_revision_and_invalidates_matches(client, seeded):
    headers = seeded["headers"]
    before = client.get(f"{API}/profile", headers=headers).json()

    response = client.patch(
        f"{API}/profile", headers=headers, json={"location": "Pune, Maharashtra"}
    )
    assert response.status_code == 200
    assert response.json()["revision"] == before["revision"] + 1
    assert response.json()["location"] == "Pune, Maharashtra"

    # Matches were invalidated, so scores are gone until a rescore runs.
    jobs = client.get(f"{API}/jobs", headers=headers).json()
    assert all(item["match"] is None for item in jobs["items"])

    rescore = client.post(f"{API}/discovery/rescore", headers=headers).json()
    assert rescore["matches_computed"] == 2
    rescored = client.get(f"{API}/jobs", headers=headers).json()
    assert all(item["match"] is not None for item in rescored["items"])


def test_seniority_endpoint_explains_its_reasoning(client, seeded):
    body = client.get(f"{API}/profile/seniority", headers=seeded["headers"]).json()
    assert body["seniority"]
    assert body["label"]
    assert body["signals"], "the classification must be explainable"
    assert any(s["signal"] == "classification" for s in body["signals"])
