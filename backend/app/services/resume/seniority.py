"""Candidate seniority classification.

Rule-based and fully traceable: every decision records the signals that drove
it, which the profile page displays. The five labels come from the brief:
student, fresher, intern, entry-level professional, experienced professional.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

STUDENT_CUES = ("pursuing", "ongoing", "expected", "present", "current", "continuing", "till date")

# Months of full-time (non-internship) experience separating the bands.
ENTRY_LEVEL_CEILING = 24
EXPERIENCED_FLOOR = 24


def classify(
    *,
    education: list[dict[str, Any]],
    experience: list[dict[str, Any]],
    graduation_year: int | None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return (seniority, signals)."""
    signals: list[dict[str, Any]] = []
    today = date.today()

    internship_months = sum(
        int(e.get("months") or 0) for e in experience if e.get("kind") == "internship"
    )
    job_months = sum(
        int(e.get("months") or 0) for e in experience if e.get("kind") != "internship"
    )
    total_months = internship_months + job_months

    has_internships = any(e.get("kind") == "internship" for e in experience)
    has_jobs = any(e.get("kind") != "internship" for e in experience)

    # --- is the candidate still studying? --------------------------------
    studying = False
    for entry in education:
        # The heuristic parser sets `ongoing` explicitly; the LLM path leaves it
        # unset, so fall back to scanning the text fields for cue words.
        blob = " ".join(
            str(entry.get(k) or "") for k in ("end", "degree", "start", "score")
        ).lower()
        if entry.get("ongoing") or any(cue in blob for cue in STUDENT_CUES):
            studying = True
            signals.append({
                "signal": "education_in_progress",
                "detail": f"Education entry '{_short(entry.get('degree'))}' is marked as ongoing.",
            })
            break

    if not studying and graduation_year and graduation_year > today.year:
        studying = True
        signals.append({
            "signal": "future_graduation",
            "detail": f"Graduation year {graduation_year} is in the future.",
        })

    # --- currently in an internship? -------------------------------------
    in_internship_now = any(
        e.get("kind") == "internship"
        and re.search(r"present|current|ongoing|now", str(e.get("end") or ""), re.IGNORECASE)
        for e in experience
    )

    signals.append({
        "signal": "experience_totals",
        "detail": (
            f"{job_months} month(s) of full-time experience and "
            f"{internship_months} month(s) of internship experience recorded."
        ),
    })

    # --- decision ---------------------------------------------------------
    if studying and in_internship_now:
        label = "intern"
        signals.append({
            "signal": "classification",
            "detail": "Still studying and currently in an internship → intern.",
        })
    elif studying:
        label = "student"
        signals.append({
            "signal": "classification",
            "detail": "Education is still in progress → student.",
        })
    elif job_months >= EXPERIENCED_FLOOR:
        label = "experienced"
        signals.append({
            "signal": "classification",
            "detail": (
                f"{job_months} months of full-time experience meets the "
                f"{EXPERIENCED_FLOOR}-month threshold → experienced professional."
            ),
        })
    elif has_jobs and job_months > 0:
        label = "entry_level"
        signals.append({
            "signal": "classification",
            "detail": (
                f"{job_months} months of full-time experience, below the "
                f"{EXPERIENCED_FLOOR}-month threshold → entry-level professional."
            ),
        })
    elif in_internship_now:
        label = "intern"
        signals.append({
            "signal": "classification",
            "detail": "An internship is listed as current → intern.",
        })
    elif has_internships or total_months > 0:
        label = "fresher"
        signals.append({
            "signal": "classification",
            "detail": (
                "Graduated with internship experience but no full-time role → fresher."
            ),
        })
    else:
        label = "fresher"
        signals.append({
            "signal": "classification",
            "detail": "No professional experience recorded → fresher.",
        })

    if graduation_year and graduation_year <= today.year:
        signals.append({
            "signal": "graduation_year",
            "detail": f"Graduated (or graduating) in {graduation_year}.",
        })

    return label, signals


def derive_totals(experience: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (total_experience_months, internship_months)."""
    internship = sum(
        int(e.get("months") or 0) for e in experience if e.get("kind") == "internship"
    )
    total = sum(int(e.get("months") or 0) for e in experience)
    return total, internship


def derive_education_facts(
    education: list[dict[str, Any]]
) -> tuple[int, str | None, int | None]:
    """Return (highest_degree_level, field_of_study, graduation_year)."""
    from app.services.resume.heuristics import _degree_level, _field_of_study

    best_level = 0
    best_field: str | None = None
    grad_year: int | None = None

    for entry in education:
        blob = " ".join(
            str(entry.get(k) or "") for k in ("degree", "level_label", "field", "institution")
        )
        level = int(entry.get("level") or 0)
        if not level:
            label = str(entry.get("level_label") or "")
            level = _degree_level(label or blob)[0]

        if level > best_level:
            best_level = level
            best_field = entry.get("field") or _field_of_study(blob)

        for value in (entry.get("end"), entry.get("start")):
            years = re.findall(r"\b((?:19|20)\d{2})\b", str(value or ""))
            for year in years:
                year_int = int(year)
                if grad_year is None or year_int > grad_year:
                    grad_year = year_int

    if best_field is None:
        for entry in education:
            if entry.get("field"):
                best_field = entry["field"]
                break

    return best_level, best_field, grad_year


SENIORITY_LABELS = {
    "student": "Student",
    "fresher": "Fresher",
    "intern": "Intern",
    "entry_level": "Entry-level professional",
    "experienced": "Experienced professional",
}


def _short(value: Any, limit: int = 60) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
