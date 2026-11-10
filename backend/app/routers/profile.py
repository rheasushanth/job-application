from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, get_active_profile
from app.models import CandidateProfile
from app.schemas import ProfileOut, ProfileUpdate
from app.services.matching.skills import normalise_skills
from app.services.resume.pipeline import derive_profile_facts, embed_profile
from app.services.resume.seniority import SENIORITY_LABELS

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    return ProfileOut.model_validate(get_active_profile(db, user))


@router.patch("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate, user: CurrentUser, db: DbSession
) -> ProfileOut:
    """Edit the confirmed profile.

    Any edit bumps the revision and invalidates existing matches, because a
    changed profile means every stored score is stale.
    """
    profile = get_active_profile(db, user)
    data = payload.model_dump(exclude_unset=True)

    for field in ("full_name", "phone", "location"):
        if field in data:
            value = (data[field] or "").strip() if data[field] else None
            setattr(profile, field, value or None)
    if "links" in data:
        profile.links = [link for link in (data["links"] or []) if link]
    if "education" in data:
        profile.education = data["education"] or []
    if "certifications" in data:
        profile.certifications = data["certifications"] or []
    if "achievements" in data:
        profile.achievements = data["achievements"] or []

    # Skill lists go through the ontology so edits can't smuggle in
    # non-canonical strings the scorer wouldn't recognise.
    for field in ("skills", "programming_languages", "frameworks", "tools"):
        if field in data:
            canonical, _ = normalise_skills(data[field] or [])
            setattr(profile, field, canonical)

    for field in ("projects", "experience"):
        if field in data:
            items = []
            for item in data[field] or []:
                entry = dict(item)
                tech, _ = normalise_skills(entry.get("tech") or [])
                entry["tech"] = tech
                entry.pop("_embedding", None)
                items.append(entry)
            setattr(profile, field, items)

    payload_shape = {
        "contact": {
            "name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
            "links": profile.links,
        },
        "education": profile.education,
        "skills": {"technical": profile.skills, "soft": []},
        "languages": profile.programming_languages,
        "frameworks": profile.frameworks,
        "tools": profile.tools,
        "projects": profile.projects,
        "experience": profile.experience,
        "certifications": profile.certifications,
        "achievements": profile.achievements,
    }

    derived = derive_profile_facts(payload_shape)
    for key, value in derived.items():
        setattr(profile, key, value)

    embedded = embed_profile(payload_shape, derived)
    profile.profile_text = embedded["profile_text"]
    profile.embedding = embedded["embedding"]
    profile.embedding_model = embedded["embedding_model"]

    projects = [dict(p) for p in profile.projects]
    for project, vector in zip(projects, embedded["project_embeddings"]):
        project["_embedding"] = vector
    profile.projects = projects

    experience = [dict(e) for e in profile.experience]
    for entry, vector in zip(experience, embedded["experience_embeddings"]):
        entry["_embedding"] = vector
    profile.experience = experience

    profile.revision += 1
    db.commit()
    db.refresh(profile)

    from app.services.matching.service import invalidate_matches

    invalidate_matches(db, user.id)
    db.commit()

    return ProfileOut.model_validate(profile)


@router.get("/seniority")
def get_seniority(user: CurrentUser, db: DbSession) -> dict:
    profile = get_active_profile(db, user)
    return {
        "seniority": profile.seniority,
        "label": SENIORITY_LABELS.get(profile.seniority, profile.seniority),
        "signals": profile.seniority_signals or [],
        "total_experience_months": profile.total_experience_months,
        "internship_months": profile.internship_months,
        "graduation_year": profile.graduation_year,
        "highest_degree_level": profile.highest_degree_level,
        "field_of_study": profile.field_of_study,
        "all_labels": SENIORITY_LABELS,
    }


@router.get("/revisions", response_model=list[ProfileOut])
def list_revisions(user: CurrentUser, db: DbSession) -> list[ProfileOut]:
    rows = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id)
        .order_by(CandidateProfile.revision.desc())
    ).all()
    return [ProfileOut.model_validate(row) for row in rows]
