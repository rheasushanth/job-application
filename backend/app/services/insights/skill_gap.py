"""Skill gap analysis.

Ranks the skills the candidate lacks by how often they are actually demanded
across the jobs discovered *for this user* — so the advice is grounded in live
market data from their own result set, not a generic "learn these" list.

Learning priority balances three things: demand frequency, how often the skill
appears as mandatory rather than preferred, and the estimated score lift from
acquiring it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.skills import SKILL_CATEGORY, related_skills
from app.models import CandidateProfile, Job, JobMatch

# Learning-order weights.
W_FREQUENCY = 0.45
W_MANDATORY = 0.35
W_LIFT = 0.20


def analyse(
    db: Session, profile: CandidateProfile, *, limit: int = 20
) -> dict[str, Any]:
    rows = db.execute(
        select(JobMatch, Job)
        .join(Job, Job.id == JobMatch.job_id)
        .where(JobMatch.user_id == profile.user_id, Job.is_active.is_(True))
    ).all()

    if not rows:
        return {
            "total_jobs_analysed": 0,
            "gaps": [],
            "learn_first": [],
            "strengths": [],
            "message": (
                "No scored jobs yet. Run job discovery first — this analysis is "
                "built from the roles actually open to you."
            ),
        }

    candidate_skills = set(profile.skills or [])
    for bucket in (profile.programming_languages, profile.frameworks, profile.tools):
        candidate_skills.update(bucket or [])

    demand: dict[str, int] = defaultdict(int)
    mandatory_demand: dict[str, int] = defaultdict(int)
    score_sum: dict[str, float] = defaultdict(float)
    example_jobs: dict[str, list[dict]] = defaultdict(list)

    # Strength tracking: skills the user has that the market wants.
    strength_demand: dict[str, int] = defaultdict(int)

    for match, job in rows:
        required = set(job.required_skills or [])
        preferred = set(job.preferred_skills or [])

        for skill in required | preferred:
            if skill in candidate_skills:
                strength_demand[skill] += 1
                continue
            demand[skill] += 1
            if skill in required:
                mandatory_demand[skill] += 1
            # Jobs where this skill is the blocker are the ones it would unlock.
            score_sum[skill] += float(match.score)
            if len(example_jobs[skill]) < 3:
                example_jobs[skill].append({
                    "job_id": str(job.id),
                    "title": job.title,
                    "company": job.company,
                    "score": float(match.score),
                })

    total_jobs = len(rows)
    if not demand:
        return {
            "total_jobs_analysed": total_jobs,
            "gaps": [],
            "learn_first": [],
            "strengths": _strengths(strength_demand, total_jobs),
            "message": "No skill gaps found across the jobs discovered for you.",
        }

    max_demand = max(demand.values())

    gaps: list[dict[str, Any]] = []
    for skill, count in demand.items():
        mandatory_count = mandatory_demand[skill]
        frequency = count / total_jobs
        mandatory_ratio = mandatory_count / count if count else 0.0

        # Estimated lift: the technical-skills category carries 0.30 weight, and
        # this skill is one of the job's requirements. Approximated from the
        # average current score of the jobs demanding it.
        avg_score = score_sum[skill] / count if count else 0.0
        headroom = max(0.0, 100.0 - avg_score)
        estimated_lift = round(headroom * frequency * (0.5 + 0.5 * mandatory_ratio), 1)

        priority = (
            W_FREQUENCY * (count / max_demand)
            + W_MANDATORY * mandatory_ratio
            + W_LIFT * min(1.0, estimated_lift / 15.0)
        )

        gaps.append({
            "skill": skill,
            "category": SKILL_CATEGORY.get(skill, "other"),
            "jobs_requiring": count,
            "jobs_requiring_as_mandatory": mandatory_count,
            "demand_percentage": round(frequency * 100, 1),
            "mandatory_ratio": round(mandatory_ratio * 100, 1),
            "estimated_score_lift": estimated_lift,
            "priority_score": round(priority, 4),
            "example_jobs": example_jobs[skill],
            "builds_on": [s for s in related_skills(skill) if s in candidate_skills][:3],
        })

    gaps.sort(key=lambda g: -g["priority_score"])
    gaps = gaps[:limit]

    learn_first = [
        {
            "rank": index + 1,
            "skill": gap["skill"],
            "reason": _learning_reason(gap, total_jobs),
            "estimated_score_lift": gap["estimated_score_lift"],
        }
        for index, gap in enumerate(gaps[:5])
    ]

    return {
        "total_jobs_analysed": total_jobs,
        "gaps": gaps,
        "learn_first": learn_first,
        "strengths": _strengths(strength_demand, total_jobs),
        "message": None,
    }


def _learning_reason(gap: dict[str, Any], total_jobs: int) -> str:
    bits = [
        f"Required by {gap['jobs_requiring']} of {total_jobs} jobs "
        f"({gap['demand_percentage']}%)"
    ]
    if gap["jobs_requiring_as_mandatory"]:
        bits.append(
            f"listed as mandatory in {gap['jobs_requiring_as_mandatory']} of them"
        )
    if gap["builds_on"]:
        bits.append(f"builds directly on your {', '.join(gap['builds_on'])}")
    if gap["estimated_score_lift"] >= 2:
        bits.append(f"worth roughly +{gap['estimated_score_lift']} points on average")
    return "; ".join(bits) + "."


def _strengths(
    strength_demand: dict[str, int], total_jobs: int, limit: int = 10
) -> list[dict[str, Any]]:
    """Skills the candidate has that the market is actually asking for."""
    items = [
        {
            "skill": skill,
            "jobs_requiring": count,
            "demand_percentage": round(count / total_jobs * 100, 1),
            "category": SKILL_CATEGORY.get(skill, "other"),
        }
        for skill, count in strength_demand.items()
    ]
    items.sort(key=lambda s: -s["jobs_requiring"])
    return items[:limit]
