"""Pydantic request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import APPLICATION_STATUSES


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        # Length is the dominant factor; a character-class maze mostly pushes
        # users toward predictable substitutions.
        if value.strip() != value:
            raise ValueError("Password must not start or end with whitespace")
        if value.lower() in {"password123", "letmein123", "qwerty12345"}:
            raise ValueError("That password is too common")
        if len(set(value)) < 5:
            raise ValueError("Password must contain at least 5 distinct characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    alert_enabled: bool
    alert_min_match: int
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UpdateMeRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    alert_enabled: bool | None = None
    alert_min_match: int | None = Field(default=None, ge=0, le=100)


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------


class ResumeOut(ORMModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    extraction_engine: str | None
    error_message: str | None
    uploaded_at: datetime
    updated_at: datetime


class ParsedResumeOut(BaseModel):
    resume_id: uuid.UUID
    status: str
    structuring_mode: str
    payload: dict[str, Any]
    field_confidence: dict[str, Any]
    warnings: list[str]
    derived: dict[str, Any]
    edited_by_user: bool


class ParsedResumeUpdate(BaseModel):
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class ProfileOut(ORMModel):
    id: uuid.UUID
    resume_id: uuid.UUID | None
    revision: int
    full_name: str | None
    email: str | None
    phone: str | None
    location: str | None
    links: list
    education: list
    skills: list
    programming_languages: list
    frameworks: list
    tools: list
    projects: list
    experience: list
    certifications: list
    achievements: list
    total_experience_months: int
    internship_months: int
    highest_degree_level: int
    field_of_study: str | None
    graduation_year: int | None
    seniority: str
    seniority_signals: list
    embedding_model: str | None
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=60)
    location: str | None = Field(default=None, max_length=200)
    links: list[str] | None = None
    education: list[dict[str, Any]] | None = None
    skills: list[str] | None = None
    programming_languages: list[str] | None = None
    frameworks: list[str] | None = None
    tools: list[str] | None = None
    projects: list[dict[str, Any]] | None = None
    experience: list[dict[str, Any]] | None = None
    certifications: list[dict[str, Any]] | None = None
    achievements: list[str] | None = None


# ---------------------------------------------------------------------------
# Sources & discovery
# ---------------------------------------------------------------------------


class SourceOut(BaseModel):
    key: str
    display_name: str
    kind: str
    requires_credentials: bool
    credential_env_vars: list[str]
    available: bool
    reason: str
    missing_env: list[str]
    notes: str
    is_enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    jobs_last_run: int


class SourceUpdate(BaseModel):
    is_enabled: bool


class DiscoveryRequest(BaseModel):
    sources: list[str] | None = None
    queries: list[str] | None = Field(default=None, max_length=10)
    location: str | None = Field(default=None, max_length=200)


class DiscoveryRunOut(ORMModel):
    id: uuid.UUID
    status: str
    progress: int
    sources_attempted: list
    sources_succeeded: list
    sources_failed: list
    queries: list
    jobs_fetched: int
    jobs_new: int
    jobs_duplicate: int
    matches_computed: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


# ---------------------------------------------------------------------------
# Jobs & matches
# ---------------------------------------------------------------------------


class JobOut(ORMModel):
    id: uuid.UUID
    source: str
    title: str
    company: str
    description: str
    required_skills: list
    preferred_skills: list
    all_skills: list
    education_requirement: dict[str, Any]
    experience_min_years: float | None
    experience_max_years: float | None
    experience_level: str
    location_raw: str | None
    city: str | None
    state: str | None
    country: str | None
    is_remote: bool
    work_mode: str
    job_type: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    salary_raw: str | None
    posted_at: datetime | None
    deadline_at: datetime | None
    apply_url: str
    also_seen_on: list
    first_seen_at: datetime


class MatchSummaryOut(BaseModel):
    score: float
    band: str
    eligibility_status: str
    eligibility_multiplier: float
    matched_skills: list[str]
    missing_skills: list[str]
    missing_mandatory_skills: list[str]
    category_scores: dict[str, Any]
    computed_at: datetime


class JobWithMatchOut(BaseModel):
    job: JobOut
    match: MatchSummaryOut | None
    is_saved: bool = False
    application_status: str | None = None


class MatchAnalysisOut(BaseModel):
    job: JobOut
    score: float
    band: str
    band_label: str
    eligibility_status: str
    eligibility_multiplier: float
    semantic_similarity: float
    category_scores: dict[str, Any]
    calculation: dict[str, Any]
    eligibility_checks: list[dict[str, Any]]
    eligibility_warnings: list[dict[str, Any]]
    matched_skills: list[dict[str, Any]]
    missing_skills: list[dict[str, Any]]
    missing_mandatory_skills: list[str]
    extra_skills: list[str]
    relevant_projects: list[dict[str, Any]]
    relevant_experience: list[dict[str, Any]]
    reasons: list[str]
    blockers: list[dict[str, Any]]
    recommendations: list[str]
    explanation: str | None
    explanation_source: str
    weights: dict[str, float]
    category_descriptions: dict[str, str]
    computed_at: datetime


class JobListOut(BaseModel):
    items: list[JobWithMatchOut]
    total: int
    page: int
    page_size: int
    facets: dict[str, Any]


class DashboardSummaryOut(BaseModel):
    total_jobs: int
    excellent: int
    good: int
    moderate: int
    low: int
    saved: int
    tracked: int
    eligible: int
    partially_eligible: int
    not_eligible: int
    sources_live: list[str]
    sources_unavailable: list[str]
    last_discovery: DiscoveryRunOut | None
    unread_notifications: int
    has_profile: bool
    top_matches: list[JobWithMatchOut]


# ---------------------------------------------------------------------------
# Saved jobs
# ---------------------------------------------------------------------------


class SavedJobCreate(BaseModel):
    job_id: uuid.UUID
    collection: str = Field(default="Default", max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class SavedJobUpdate(BaseModel):
    collection: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class SavedJobOut(BaseModel):
    id: uuid.UUID
    collection: str
    notes: str | None
    created_at: datetime
    job: JobOut
    match: MatchSummaryOut | None


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

ApplicationStatus = Literal[
    "interested", "applied", "assessment", "interview", "rejected", "offer"
]


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    status: ApplicationStatus = "interested"
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationEventOut(ORMModel):
    id: uuid.UUID
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class ApplicationOut(BaseModel):
    id: uuid.UUID
    status: str
    notes: str | None
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job: JobOut
    match: MatchSummaryOut | None
    events: list[ApplicationEventOut] = []


class ApplicationBoardOut(BaseModel):
    columns: dict[str, list[ApplicationOut]]
    counts: dict[str, int]
    statuses: list[str] = list(APPLICATION_STATUSES)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


class SkillGapOut(BaseModel):
    total_jobs_analysed: int
    gaps: list[dict[str, Any]]
    learn_first: list[dict[str, Any]]
    strengths: list[dict[str, Any]]
    message: str | None


class AlternativeRolesOut(BaseModel):
    seniority: str
    roles: list[dict[str, Any]]


class ResumeFeedbackOut(BaseModel):
    score: int
    suggestions: list[dict[str, Any]]
    missing_keywords: list[dict[str, Any]]
    section_coverage: dict[str, bool]
    rewrites: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Notifications & settings
# ---------------------------------------------------------------------------


class NotificationOut(ORMModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    payload: dict[str, Any]
    is_read: bool
    created_at: datetime


class AlertConfig(BaseModel):
    alert_enabled: bool
    alert_min_match: int = Field(ge=0, le=100)


class WeightsOut(BaseModel):
    weights: dict[str, float]
    defaults: dict[str, float]
    labels: dict[str, str]
    descriptions: dict[str, str]
    hash: str


class WeightsUpdate(BaseModel):
    weights: dict[str, float]


class HealthOut(BaseModel):
    status: str
    database: str
    embedding_backend: str
    llm_provider: str
    task_backend: str
    sources_live: list[str]
    sources_unavailable: list[str]
    jobs_indexed: int
