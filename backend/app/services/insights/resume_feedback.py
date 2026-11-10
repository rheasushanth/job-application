"""Resume improvement suggestions.

Deterministic checks run first (they are specific, verifiable and cost
nothing), then the LLM is asked for prose suggestions on top. Missing keywords
are taken from the user's own matched jobs, so they reflect the roles actually
being targeted rather than generic resume advice.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidateProfile, Job, JobMatch

# Verbs that signal an accomplishment rather than a duty.
STRONG_VERBS = {
    "built", "designed", "implemented", "shipped", "led", "launched", "reduced",
    "improved", "optimised", "optimized", "automated", "architected", "scaled",
    "migrated", "developed", "created", "delivered", "increased", "decreased",
    "achieved", "deployed", "integrated", "refactored", "mentored",
}
WEAK_OPENERS = {
    "responsible", "worked", "helped", "assisted", "involved", "participated",
    "various", "etc", "tasked",
}


def analyse(db: Session, profile: CandidateProfile) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []

    suggestions += _check_completeness(profile)
    suggestions += _check_projects(profile)
    suggestions += _check_experience(profile)
    suggestions += _check_contact(profile)

    missing_keywords = _missing_keywords(db, profile)
    if missing_keywords:
        top = [k["keyword"] for k in missing_keywords[:8]]
        suggestions.append({
            "section": "skills",
            "severity": "high",
            "title": "Add the keywords your target jobs actually use",
            "detail": (
                "These terms appear across the jobs matched to you but not in your "
                f"resume: {', '.join(top)}. Only add the ones you can genuinely "
                "evidence — list them in your skills section and show them in a "
                "project or role bullet."
            ),
        })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: severity_order.get(s["severity"], 3))

    return {
        "suggestions": suggestions,
        "missing_keywords": missing_keywords,
        "score": _resume_health(profile, suggestions),
        "section_coverage": _section_coverage(profile),
    }


def _check_completeness(profile: CandidateProfile) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not profile.projects:
        out.append({
            "section": "projects",
            "severity": "high",
            "title": "No projects listed",
            "detail": (
                "Projects are 15% of the match score and are the main evidence "
                "available to a student or fresher. Add two or three with the "
                "technologies named explicitly."
            ),
        })
    if not profile.experience:
        out.append({
            "section": "experience",
            "severity": "high",
            "title": "No internships or work experience listed",
            "detail": (
                "Experience relevance is another 15% of the score. Include "
                "internships, freelance work, open-source contributions or "
                "teaching assistantships — all of it counts."
            ),
        })
    if not profile.certifications:
        out.append({
            "section": "certifications",
            "severity": "low",
            "title": "No certifications listed",
            "detail": (
                "Certifications are not weighted directly, but a relevant one "
                "(cloud, data, security) corroborates a skill claim."
            ),
        })
    if len(profile.skills or []) < 8:
        out.append({
            "section": "skills",
            "severity": "medium",
            "title": "Thin skills section",
            "detail": (
                f"Only {len(profile.skills or [])} recognised skills were found. "
                "Group them under headings (Languages, Frameworks, Tools, "
                "Concepts) so both parsers and recruiters can read them."
            ),
        })
    return out


def _check_projects(profile: CandidateProfile) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for project in profile.projects or []:
        name = project.get("name") or "a project"
        description = str(project.get("description") or "")

        if not project.get("tech"):
            out.append({
                "section": "projects",
                "severity": "medium",
                "title": f"“{name}” does not name its technologies",
                "detail": (
                    "Add an explicit stack line, e.g. “Tech: Python, FastAPI, "
                    "PostgreSQL, Docker”. Skill matching reads these directly."
                ),
            })
        if len(description) < 80:
            out.append({
                "section": "projects",
                "severity": "medium",
                "title": f"“{name}” is described too briefly",
                "detail": (
                    "Use two or three bullets: what it does, how you built it, "
                    "and a measurable outcome. Suggested shape — “Built <what> "
                    "using <stack> to <purpose>; achieved <metric>.”"
                ),
            })
        elif not _has_metric(description):
            out.append({
                "section": "projects",
                "severity": "low",
                "title": f"“{name}” has no measurable outcome",
                "detail": (
                    "Add a number: users served, latency reduced, accuracy "
                    "reached, records processed. Quantified bullets read as "
                    "evidence rather than intent."
                ),
            })
    return out[:6]


def _check_experience(profile: CandidateProfile) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in profile.experience or []:
        role = entry.get("role") or "a role"
        description = str(entry.get("description") or "")
        low = description.lower()

        if not entry.get("months"):
            out.append({
                "section": "experience",
                "severity": "medium",
                "title": f"“{role}” has no clear date range",
                "detail": (
                    "Write dates as “Jun 2025 – Dec 2025”. Durations feed the "
                    "experience-level check, and an unparseable range is treated "
                    "as zero months."
                ),
            })
        weak = [word for word in WEAK_OPENERS if word in low]
        if weak and not any(verb in low for verb in STRONG_VERBS):
            out.append({
                "section": "experience",
                "severity": "medium",
                "title": f"“{role}” is written as duties, not achievements",
                "detail": (
                    f"Phrases like “{weak[0]}” describe responsibility. Lead with "
                    "an action verb and an outcome: “Reduced p95 latency 40% by "
                    "adding Redis caching” instead of “Responsible for caching”."
                ),
            })
    return out[:6]


def _check_contact(profile: CandidateProfile) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not profile.email:
        out.append({
            "section": "contact",
            "severity": "high",
            "title": "No email address",
            "detail": "Add a professional email near the top of the resume.",
        })
    links = " ".join(profile.links or []).lower()
    if "github" not in links and "gitlab" not in links:
        out.append({
            "section": "contact",
            "severity": "medium",
            "title": "No code profile linked",
            "detail": (
                "Link your GitHub or GitLab. For engineering roles it is the "
                "fastest corroboration of every skill you claim."
            ),
        })
    if "linkedin" not in links:
        out.append({
            "section": "contact",
            "severity": "low",
            "title": "No LinkedIn linked",
            "detail": "Add your LinkedIn URL; most recruiters look for it.",
        })
    if not profile.location:
        out.append({
            "section": "contact",
            "severity": "low",
            "title": "No location given",
            "detail": (
                "State your city. Location filters are common, and an absent "
                "location gets filtered out rather than treated as flexible."
            ),
        })
    return out


def _has_metric(text: str) -> bool:
    import re

    return bool(re.search(r"\d+\s*(%|percent|x|k\b|users|requests|ms\b|seconds|hours|"
                          r"records|rows|teams|people|accuracy|f1)", text, re.IGNORECASE))


def _missing_keywords(
    db: Session, profile: CandidateProfile, limit: int = 20
) -> list[dict[str, Any]]:
    """Skills demanded by the user's matched jobs but absent from the resume."""
    rows = db.execute(
        select(Job)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == profile.user_id, Job.is_active.is_(True))
        .order_by(JobMatch.score.desc())
        .limit(150)
    ).all()

    have = set(profile.skills or [])
    for bucket in (profile.programming_languages, profile.frameworks, profile.tools):
        have.update(bucket or [])

    counter: Counter[str] = Counter()
    mandatory: Counter[str] = Counter()
    for (job,) in rows:
        for skill in job.required_skills or []:
            if skill not in have:
                counter[skill] += 1
                mandatory[skill] += 1
        for skill in job.preferred_skills or []:
            if skill not in have:
                counter[skill] += 1

    total = len(rows) or 1
    return [
        {
            "keyword": skill,
            "job_count": count,
            "frequency_percentage": round(count / total * 100, 1),
            "mandatory_count": mandatory[skill],
        }
        for skill, count in counter.most_common(limit)
    ]


def _section_coverage(profile: CandidateProfile) -> dict[str, bool]:
    return {
        "contact": bool(profile.email),
        "education": bool(profile.education),
        "skills": bool(profile.skills),
        "projects": bool(profile.projects),
        "experience": bool(profile.experience),
        "certifications": bool(profile.certifications),
        "achievements": bool(profile.achievements),
    }


def _resume_health(profile: CandidateProfile, suggestions: list[dict]) -> int:
    """A 0–100 completeness indicator. Explicitly not a match score."""
    coverage = _section_coverage(profile)
    base = sum(coverage.values()) / len(coverage) * 70

    penalty = sum(
        {"high": 8, "medium": 4, "low": 1}.get(s["severity"], 0) for s in suggestions
    )
    bonus = 0
    if len(profile.skills or []) >= 12:
        bonus += 10
    if any(_has_metric(str(p.get("description") or "")) for p in profile.projects or []):
        bonus += 10
    if profile.links:
        bonus += 10

    return max(0, min(100, int(round(base + bonus - penalty))))


# ---------------------------------------------------------------------------
# Optional LLM layer
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = (
    "You are a technical resume editor. You rewrite bullets to be specific and "
    "achievement-led using only the facts given — you never invent metrics, "
    "employers, technologies or outcomes. If a bullet lacks a measurable result, "
    "say what the candidate should measure rather than making a number up."
)


async def suggest_rewrites(profile: CandidateProfile, target_role: str | None = None) -> dict[str, Any]:
    """Ask the LLM to rewrite the weakest bullets. Falls back to guidance."""
    from app.services import llm

    items: list[dict[str, str]] = []
    for project in (profile.projects or [])[:4]:
        if project.get("description"):
            items.append({
                "kind": "project",
                "name": str(project.get("name") or ""),
                "text": str(project["description"])[:600],
                "tech": ", ".join(project.get("tech") or []),
            })
    for entry in (profile.experience or [])[:4]:
        if entry.get("description"):
            items.append({
                "kind": "experience",
                "name": str(entry.get("role") or ""),
                "text": str(entry["description"])[:600],
                "tech": ", ".join(entry.get("tech") or []),
            })

    if not items:
        return {
            "available": False,
            "reason": "Add at least one project or role description first.",
            "rewrites": [],
        }

    if not llm.llm_available():
        return {
            "available": False,
            "reason": (
                "AI rewriting needs an LLM API key (ANTHROPIC_API_KEY). The "
                "rule-based suggestions above are still active."
            ),
            "rewrites": [],
        }

    rendered = "\n\n".join(
        f"[{i}] ({item['kind']}) {item['name']}\nTech: {item['tech']}\n{item['text']}"
        for i, item in enumerate(items)
    )
    target = target_role or "software engineering roles"

    result = await llm.complete_json(
        f"""Rewrite each entry below as 2-3 achievement-led resume bullets aimed at {target}.

Return JSON: {{"rewrites": [{{"index": number, "name": string,
"bullets": [string], "note": string}}]}}

"note" states what metric the candidate should measure if the original has none.
Use only the facts provided. Never invent numbers.

{rendered}""",
        system=REWRITE_SYSTEM,
        max_tokens=2500,
    )

    if not result.ok or not isinstance(result.data, dict):
        return {
            "available": False,
            "reason": "The AI rewrite service did not return a usable response.",
            "rewrites": [],
        }

    rewrites = []
    for entry in result.data.get("rewrites", [])[:8]:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        original = items[index]["text"] if isinstance(index, int) and 0 <= index < len(items) else ""
        bullets = [str(b)[:300] for b in (entry.get("bullets") or [])][:4]
        if not bullets:
            continue
        rewrites.append({
            "name": str(entry.get("name") or "")[:160],
            "original": original,
            "bullets": bullets,
            "note": str(entry.get("note") or "")[:300],
        })

    return {"available": True, "reason": None, "rewrites": rewrites}
