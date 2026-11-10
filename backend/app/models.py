"""SQLAlchemy models. See docs/SCHEMA.md for the design rationale."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import GUID, JSONB, Base, TZDateTime, new_uuid, utcnow

# --------------------------------------------------------------------------
# Enumerated values are kept as plain strings + CheckConstraints rather than
# native DB enums: adding a new job source or status then needs no migration.
# --------------------------------------------------------------------------

RESUME_STATUSES = ("uploaded", "extracting", "parsed", "awaiting_review", "confirmed", "failed")
SENIORITIES = ("student", "fresher", "intern", "entry_level", "experienced")
WORK_MODES = ("remote", "hybrid", "onsite", "unspecified")
JOB_TYPES = ("internship", "full_time", "part_time", "contract", "freelance", "unspecified")
EXPERIENCE_LEVELS = ("internship", "entry", "mid", "senior", "lead", "unspecified")
BANDS = ("excellent", "good", "moderate", "low")
ELIGIBILITY = ("eligible", "partially_eligible", "not_eligible")
APPLICATION_STATUSES = ("interested", "applied", "assessment", "interview", "rejected", "offer")
DISCOVERY_STATUSES = ("queued", "running", "completed", "failed", "partial")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    alert_min_match: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    profiles: Mapped[list["CandidateProfile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)
    replaced_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    extraction_engine: Mapped[Optional[str]] = mapped_column(String(32))
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="resumes")
    parsed: Mapped[Optional["ParsedResume"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','extracting','parsed','awaiting_review','confirmed','failed')",
            name="ck_resume_status",
        ),
    )


class ParsedResume(Base):
    __tablename__ = "parsed_resumes"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    resume_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    structuring_mode: Mapped[str] = mapped_column(String(16), default="heuristic", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    field_confidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    resume: Mapped[Resume] = relationship(back_populates="parsed")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    resume_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    links: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    education: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    raw_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    programming_languages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    frameworks: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    tools: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    projects: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    experience: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    certifications: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    achievements: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    total_experience_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    internship_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    highest_degree_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    field_of_study: Mapped[Optional[str]] = mapped_column(String(200))
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer)
    seniority: Mapped[str] = mapped_column(String(24), default="fresher", nullable=False)
    seniority_signals: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    profile_text: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(JSONB)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120))

    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="profiles")

    __table_args__ = (
        Index("ix_profile_user_active", "user_id", "is_active"),
        CheckConstraint(
            "seniority IN ('student','fresher','intern','entry_level','experienced')",
            name="ck_profile_seniority",
        ),
    )


class JobSourceRecord(Base):
    """Mirror of the in-code source registry so status is queryable."""

    __tablename__ = "job_sources"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), default="public_api", nullable=False)
    requires_credentials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credential_env_vars: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)
    last_status: Mapped[Optional[str]] = mapped_column(String(24))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    jobs_last_run: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SourceRunLog(Base):
    __tablename__ = "source_run_log"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    discovery_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID, index=True)
    source_key: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(200), nullable=False)

    title: Mapped[str] = mapped_column(String(400), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    company_normalised: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    description_html: Mapped[Optional[str]] = mapped_column(Text)

    required_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferred_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    all_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    education_requirement: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    experience_min_years: Mapped[Optional[float]] = mapped_column(Float)
    experience_max_years: Mapped[Optional[float]] = mapped_column(Float)
    experience_level: Mapped[str] = mapped_column(
        String(24), default="unspecified", index=True, nullable=False
    )

    location_raw: Mapped[Optional[str]] = mapped_column(String(400))
    city: Mapped[Optional[str]] = mapped_column(String(160), index=True)
    state: Mapped[Optional[str]] = mapped_column(String(160), index=True)
    country: Mapped[Optional[str]] = mapped_column(String(160), index=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    work_mode: Mapped[str] = mapped_column(
        String(16), default="unspecified", index=True, nullable=False
    )
    job_type: Mapped[str] = mapped_column(
        String(16), default="unspecified", index=True, nullable=False
    )

    salary_min: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[Optional[str]] = mapped_column(String(8))
    salary_period: Mapped[Optional[str]] = mapped_column(String(16))
    salary_raw: Mapped[Optional[str]] = mapped_column(String(200))

    posted_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime, index=True)
    deadline_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)
    apply_url: Mapped[str] = mapped_column(Text, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    duplicate_of_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    also_seen_on: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    embedding: Mapped[Optional[list]] = mapped_column(JSONB)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_job_source_id"),
        Index("ix_jobs_salary_max", "salary_max"),
        Index("ix_jobs_active_posted", "is_active", "posted_at"),
    )


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    profile_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    job_content_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    weight_profile_hash: Mapped[str] = mapped_column(String(40), nullable=False)

    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    band: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    eligibility_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    semantic_similarity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    category_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    matched_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    missing_mandatory_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    extra_skills: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    relevant_projects: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    relevant_experience: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    blockers: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    explanation_source: Mapped[str] = mapped_column(String(16), default="template", nullable=False)

    computed_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    job: Mapped[Job] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_match_user_job"),
        Index("ix_match_user_score", "user_id", "score"),
    )


class MatchWeightProfile(Base):
    __tablename__ = "match_weight_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="Default", nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    hash: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    collection: Mapped[str] = mapped_column(String(120), default="Default", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    job: Mapped[Job] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_saved_user_job"),)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default="interested", index=True, nullable=False
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    applied_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    job: Mapped[Job] = relationship(lazy="joined")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_app_user_job"),
        CheckConstraint(
            "status IN ('interested','applied','assessment','interview','rejected','offer')",
            name="ck_application_status",
        ),
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)

    application: Mapped[Application] = relationship(back_populates="events")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sources_attempted: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sources_succeeded: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    sources_failed: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    queries: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    jobs_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_computed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TZDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TZDateTime)


class SkillOntologyOverride(Base):
    __tablename__ = "skill_ontology_overrides"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=new_uuid)
    canonical: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    category: Mapped[str] = mapped_column(String(48), default="technical", nullable=False)
    related: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
