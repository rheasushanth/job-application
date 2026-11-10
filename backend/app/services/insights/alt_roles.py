"""Alternative role recommendations.

The brief's requirement is that recommendations are *not* limited to the titles
written on the resume. So instead of reading titles, this scores the candidate's
skill set against every role in the catalogue: core skills are weighted heavily
(they define the role), supporting skills fill in the rest, and adjacency from
the skill ontology earns partial credit.

Every suggestion comes with its fit percentage, the skills that justify it, and
the skills still missing — so the user can see why it was offered.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data.roles import ROLE_CATALOGUE, RoleDefinition, roles_for_level
from app.data.skills import related_skills
from app.models import CandidateProfile, Job, JobMatch

CORE_WEIGHT = 3.0
SUPPORTING_WEIGHT = 1.0
RELATED_CREDIT = 0.5

# Below this, a role is not worth suggesting.
MIN_FIT = 0.28


def _candidate_skills(profile: CandidateProfile) -> set[str]:
    merged: set[str] = set()
    for bucket in (
        profile.skills, profile.programming_languages, profile.frameworks, profile.tools
    ):
        merged.update(bucket or [])
    for project in profile.projects or []:
        merged.update(project.get("tech") or [])
    for entry in profile.experience or []:
        merged.update(entry.get("tech") or [])
    return merged


def score_role(profile: CandidateProfile, role: RoleDefinition) -> dict[str, Any]:
    """Skill-coverage fit for one role."""
    skills = _candidate_skills(profile)
    adjacency: dict[str, str] = {}
    for skill in skills:
        for rel in related_skills(skill):
            adjacency.setdefault(rel, skill)

    earned = 0.0
    total = 0.0
    matched: list[str] = []
    missing_core: list[str] = []
    missing_supporting: list[str] = []
    transferable: list[dict[str, str]] = []

    def evaluate(skill: str, weight: float, is_core: bool) -> None:
        nonlocal earned, total
        total += weight
        if skill in skills:
            earned += weight
            matched.append(skill)
        elif skill in adjacency:
            earned += weight * RELATED_CREDIT
            transferable.append({"required": skill, "via": adjacency[skill]})
        else:
            (missing_core if is_core else missing_supporting).append(skill)

    for skill in role.core_skills:
        evaluate(skill, CORE_WEIGHT, True)
    for skill in role.supporting_skills:
        evaluate(skill, SUPPORTING_WEIGHT, False)

    fit = (earned / total) if total else 0.0

    # Missing a core skill caps the fit: you cannot be a 90% match for a role
    # whose defining skill you lack.
    if missing_core:
        cap = max(0.3, 1.0 - 0.35 * len(missing_core))
        fit = min(fit, cap)

    # Degree gate, applied gently — most of these roles list a degree but
    # accept equivalent evidence.
    if role.typical_degree_level and (profile.highest_degree_level or 0) < role.typical_degree_level:
        fit *= 0.85

    return {
        "role_key": role.key,
        "title": role.title,
        "family": role.family,
        "fit": round(min(1.0, fit) * 100, 1),
        "blurb": role.blurb,
        "matched_skills": matched,
        "transferable_skills": transferable,
        "missing_core_skills": missing_core,
        "missing_supporting_skills": missing_supporting[:8],
        "search_terms": list(role.search_terms),
        "levels": list(role.levels),
    }


def recommend_roles(
    db: Session | None,
    profile: CandidateProfile,
    *,
    limit: int = 12,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    """Ranked alternative roles the candidate could apply for."""
    pool = ROLE_CATALOGUE if include_all else roles_for_level(profile.seniority or "fresher")
    if not pool:
        pool = ROLE_CATALOGUE

    scored = [score_role(profile, role) for role in pool]
    scored = [s for s in scored if s["fit"] >= MIN_FIT * 100]
    scored.sort(key=lambda s: -s["fit"])
    scored = scored[:limit]

    for entry in scored:
        entry["why"] = _build_why(entry)
        entry["skills_to_add"] = (
            entry["missing_core_skills"] + entry["missing_supporting_skills"]
        )[:6]
        if db is not None:
            entry["sample_jobs"] = _sample_jobs(db, profile, entry)
            entry["open_job_count"] = _job_count(db, profile, entry)
        else:
            entry["sample_jobs"] = []
            entry["open_job_count"] = 0

    return scored


def _build_why(entry: dict[str, Any]) -> str:
    matched = entry["matched_skills"]
    parts: list[str] = []
    if matched:
        parts.append(
            f"You already have {len(matched)} of this role's defining skills "
            f"({', '.join(matched[:5])}{'…' if len(matched) > 5 else ''})."
        )
    if entry["transferable_skills"]:
        pairs = ", ".join(
            f"{t['via']} → {t['required']}" for t in entry["transferable_skills"][:3]
        )
        parts.append(f"Transferable from {pairs}.")
    if entry["missing_core_skills"]:
        parts.append(
            f"You would need to pick up {', '.join(entry['missing_core_skills'])} "
            "to be a serious candidate."
        )
    elif entry["missing_supporting_skills"]:
        parts.append(
            f"Adding {', '.join(entry['missing_supporting_skills'][:3])} would "
            "strengthen your application."
        )
    if not parts:
        parts.append("Suggested from your overall skill profile.")
    return " ".join(parts)


def _role_title_filter(entry: dict[str, Any]):
    """SQL filter matching jobs whose title looks like this role."""
    tokens: list[str] = []
    for term in entry["search_terms"] or [entry["title"]]:
        # Use the distinctive head of each search term.
        words = [w for w in term.split() if w.lower() not in ("intern", "internship", "engineer")]
        if words:
            tokens.append(" ".join(words[:2]))
    tokens = tokens or [entry["title"]]
    clauses = [Job.title.ilike(f"%{token}%") for token in tokens]
    from sqlalchemy import or_

    return or_(*clauses)


def _sample_jobs(
    db: Session, profile: CandidateProfile, entry: dict[str, Any], limit: int = 3
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Job, JobMatch)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .where(
            JobMatch.user_id == profile.user_id,
            Job.is_active.is_(True),
            Job.duplicate_of_id.is_(None),
            _role_title_filter(entry),
        )
        .order_by(JobMatch.score.desc())
        .limit(limit)
    ).all()

    return [
        {
            "job_id": str(job.id),
            "title": job.title,
            "company": job.company,
            "source": job.source,
            "score": float(match.score),
            "band": match.band,
        }
        for job, match in rows
    ]


def _job_count(db: Session, profile: CandidateProfile, entry: dict[str, Any]) -> int:
    return int(
        db.scalar(
            select(func.count(Job.id)).where(
                Job.is_active.is_(True),
                Job.duplicate_of_id.is_(None),
                _role_title_filter(entry),
            )
        )
        or 0
    )


def derive_role_queries(profile: CandidateProfile, limit: int = 6) -> list[str]:
    """Search keywords for discovery, taken from the best-fitting roles.

    This is what makes discovery broader than the resume's own job titles.
    """
    scored = recommend_roles(None, profile, limit=limit)
    queries: list[str] = []
    for entry in scored:
        for term in entry["search_terms"]:
            if term not in queries:
                queries.append(term)
                break
        if len(queries) >= limit:
            break

    if not queries:
        queries = ["software developer"]
    return queries
