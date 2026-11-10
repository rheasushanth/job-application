from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MatchWeightProfile

# Six scoring categories. Weights are configurable per user; these are the
# shipped defaults and sum to 1.0 for readability (the scorer normalises by the
# weight total anyway, so any positive values work).
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical_skills": 0.30,
    "semantic_similarity": 0.20,
    "project_relevance": 0.15,
    "experience_relevance": 0.15,
    "education_match": 0.10,
    "experience_level_fit": 0.10,
}

CATEGORY_LABELS: dict[str, str] = {
    "technical_skills": "Technical skills match",
    "semantic_similarity": "Semantic profile similarity",
    "project_relevance": "Project relevance",
    "experience_relevance": "Internship / work experience relevance",
    "education_match": "Educational qualification match",
    "experience_level_fit": "Experience-level compatibility",
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "technical_skills": (
        "Coverage of the role's required and preferred skills by your skills. "
        "Mandatory skills count double; related technologies earn partial credit."
    ),
    "semantic_similarity": (
        "Cosine similarity between an embedding of your whole profile and an "
        "embedding of the job description."
    ),
    "project_relevance": (
        "How closely your strongest project matches this job description, by "
        "both meaning and shared technologies."
    ),
    "experience_relevance": (
        "Relevance of your internships and roles to this job, weighted by how "
        "long each lasted."
    ),
    "education_match": (
        "Your highest degree level and field of study against the role's stated "
        "educational requirement."
    ),
    "experience_level_fit": (
        "Your total months of experience against the role's expected band."
    ),
}

MIN_WEIGHT = 0.0
MAX_WEIGHT = 1.0


def weights_hash(weights: dict[str, float]) -> str:
    payload = json.dumps({k: round(float(v), 6) for k, v in sorted(weights.items())})
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:40]


def validate_weights(raw: dict[str, Any]) -> dict[str, float]:
    """Accept a partial dict; unknown keys rejected, missing keys defaulted."""
    unknown = set(raw) - set(DEFAULT_WEIGHTS)
    if unknown:
        raise ValueError(f"Unknown weight categories: {', '.join(sorted(unknown))}")

    merged = dict(DEFAULT_WEIGHTS)
    for key, value in raw.items():
        try:
            val = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Weight for '{key}' must be a number")
        if not (MIN_WEIGHT <= val <= MAX_WEIGHT):
            raise ValueError(f"Weight for '{key}' must be between {MIN_WEIGHT} and {MAX_WEIGHT}")
        merged[key] = val

    if sum(merged.values()) <= 0:
        raise ValueError("At least one weight must be greater than zero")
    return merged


def ensure_default_weight_profile(db: Session) -> MatchWeightProfile:
    profile = db.scalars(
        select(MatchWeightProfile).where(MatchWeightProfile.user_id.is_(None))
    ).first()
    if profile is None:
        profile = MatchWeightProfile(
            user_id=None,
            name="System default",
            weights=dict(DEFAULT_WEIGHTS),
            hash=weights_hash(DEFAULT_WEIGHTS),
            is_active=True,
        )
        db.add(profile)
        db.flush()
    return profile


def get_user_weights(db: Session, user_id: uuid.UUID) -> tuple[dict[str, float], str]:
    profile = db.scalars(
        select(MatchWeightProfile).where(
            MatchWeightProfile.user_id == user_id, MatchWeightProfile.is_active.is_(True)
        )
    ).first()
    if profile is not None:
        weights = {**DEFAULT_WEIGHTS, **(profile.weights or {})}
        return weights, profile.hash
    return dict(DEFAULT_WEIGHTS), weights_hash(DEFAULT_WEIGHTS)


def set_user_weights(
    db: Session, user_id: uuid.UUID, raw: dict[str, Any]
) -> tuple[dict[str, float], str]:
    weights = validate_weights(raw)
    digest = weights_hash(weights)
    profile = db.scalars(
        select(MatchWeightProfile).where(
            MatchWeightProfile.user_id == user_id, MatchWeightProfile.is_active.is_(True)
        )
    ).first()
    if profile is None:
        profile = MatchWeightProfile(
            user_id=user_id, name="Custom", weights=weights, hash=digest, is_active=True
        )
        db.add(profile)
    else:
        profile.weights = weights
        profile.hash = digest
    db.flush()
    return weights, digest


def reset_user_weights(db: Session, user_id: uuid.UUID) -> tuple[dict[str, float], str]:
    profile = db.scalars(
        select(MatchWeightProfile).where(MatchWeightProfile.user_id == user_id)
    ).first()
    if profile is not None:
        db.delete(profile)
        db.flush()
    return dict(DEFAULT_WEIGHTS), weights_hash(DEFAULT_WEIGHTS)
