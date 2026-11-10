"""Rule-based eligibility validation.

Separate from scoring on purpose. Scoring answers "how good a fit is this?";
eligibility answers "is this candidate actually allowed to apply?". The brief
requires that strong optional-skill matches cannot compensate for an unmet
mandatory requirement, so eligibility produces a *multiplier* applied after the
weighted sum, plus a status that the UI shows independently of the percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Degree levels, ordered. Used for both candidate and requirement.
DEGREE_LEVELS: dict[str, int] = {
    "none": 0,
    "high_school": 1,
    "diploma": 2,
    "bachelor": 3,
    "master": 4,
    "doctorate": 5,
}
DEGREE_LABELS = {v: k for k, v in DEGREE_LEVELS.items()}

# First unmet mandatory skill is heavily penalised; further ones compound more
# gently, because one strict parse miss shouldn't zero out an otherwise good
# match. Floor keeps a clearly-ineligible job from reading as a 0 and vanishing.
FIRST_MANDATORY_MISS = 0.55
SUBSEQUENT_MANDATORY_MISS = 0.75
MANDATORY_FLOOR = 0.25

DEGREE_SHORTFALL_PENALTY = 0.60
EXPERIENCE_SHORTFALL_FLOOR = 0.50

# A role is only treated as having real mandatory skills if the parser found a
# plausible number; a 40-skill "required" list is usually a mis-segmented page.
MAX_TRUSTED_MANDATORY = 18


@dataclass
class EligibilityResult:
    status: str  # eligible | partially_eligible | not_eligible
    multiplier: float
    blockers: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)

    @property
    def is_hard_fail(self) -> bool:
        return self.status == "not_eligible"


def evaluate_eligibility(
    *,
    missing_mandatory_skills: list[str],
    mandatory_skill_count: int,
    candidate_degree_level: int,
    required_degree_level: int | None,
    candidate_field: str | None,
    required_fields: list[str] | None,
    candidate_months: int,
    required_min_years: float | None,
    job_type: str,
    seniority: str,
) -> EligibilityResult:
    multiplier = 1.0
    blockers: list[dict] = []
    warnings: list[dict] = []
    checks: list[dict] = []

    # ---- mandatory skills ------------------------------------------------
    trusted = mandatory_skill_count <= MAX_TRUSTED_MANDATORY
    misses = list(dict.fromkeys(missing_mandatory_skills))
    if misses and trusted:
        penalty = FIRST_MANDATORY_MISS
        for _ in misses[1:]:
            penalty *= SUBSEQUENT_MANDATORY_MISS
        penalty = max(penalty, MANDATORY_FLOOR)
        multiplier *= penalty
        blockers.append({
            "type": "mandatory_skills",
            "severity": "high" if len(misses) > 1 else "medium",
            "message": (
                f"{len(misses)} mandatory skill{'s' if len(misses) > 1 else ''} not evidenced "
                f"in your profile: {', '.join(misses[:6])}"
                + ("…" if len(misses) > 6 else "")
            ),
            "skills": misses,
            "multiplier_applied": round(penalty, 4),
        })
    elif misses and not trusted:
        warnings.append({
            "type": "mandatory_skills_unreliable",
            "message": (
                f"This posting lists {mandatory_skill_count} skills as required, which is too "
                "many to treat as hard requirements — they were scored but not used to gate "
                "eligibility."
            ),
            "skills": misses[:10],
        })
    checks.append({
        "check": "mandatory_skills",
        "passed": not (misses and trusted),
        "detail": (
            f"{mandatory_skill_count - len(misses)}/{mandatory_skill_count} mandatory skills covered"
            if mandatory_skill_count else "No mandatory skills detected in the posting"
        ),
    })

    # ---- education -------------------------------------------------------
    if required_degree_level:
        if candidate_degree_level < required_degree_level:
            multiplier *= DEGREE_SHORTFALL_PENALTY
            blockers.append({
                "type": "education",
                "severity": "high",
                "message": (
                    f"Requires a {DEGREE_LABELS.get(required_degree_level, 'higher')} degree; "
                    f"your highest recorded level is "
                    f"{DEGREE_LABELS.get(candidate_degree_level, 'unspecified')}."
                ),
                "multiplier_applied": DEGREE_SHORTFALL_PENALTY,
            })
        checks.append({
            "check": "education_level",
            "passed": candidate_degree_level >= required_degree_level,
            "detail": (
                f"Needs {DEGREE_LABELS.get(required_degree_level)}, "
                f"you have {DEGREE_LABELS.get(candidate_degree_level)}"
            ),
        })

        if required_fields and candidate_field:
            cand = candidate_field.lower()
            if not any(f.lower() in cand or cand in f.lower() for f in required_fields):
                warnings.append({
                    "type": "field_of_study",
                    "message": (
                        f"Prefers {', '.join(required_fields[:3])}; your field is "
                        f"{candidate_field}. Often flexible, so this is a note, not a blocker."
                    ),
                })

    # ---- experience floor ------------------------------------------------
    candidate_years = candidate_months / 12.0
    if required_min_years and required_min_years > 0:
        if candidate_years + 1e-9 < required_min_years:
            ratio = candidate_years / required_min_years if required_min_years else 1.0
            penalty = max(EXPERIENCE_SHORTFALL_FLOOR, min(1.0, ratio))
            multiplier *= penalty
            severity = "high" if ratio < 0.5 else "medium"
            blockers.append({
                "type": "experience",
                "severity": severity,
                "message": (
                    f"Asks for {_fmt_years(required_min_years)} of experience; your profile "
                    f"shows {_fmt_years(candidate_years)}."
                ),
                "multiplier_applied": round(penalty, 4),
            })
        checks.append({
            "check": "minimum_experience",
            "passed": candidate_years + 1e-9 >= required_min_years,
            "detail": (
                f"Needs {_fmt_years(required_min_years)}, "
                f"you have {_fmt_years(candidate_years)}"
            ),
        })

    # ---- experience-level / job-type sanity -----------------------------
    if job_type == "internship" and seniority == "experienced" and candidate_months >= 36:
        warnings.append({
            "type": "overqualified",
            "message": (
                "This is an internship and your profile shows "
                f"{_fmt_years(candidate_years)} of experience — you may be overqualified."
            ),
        })
    if job_type != "internship" and seniority in ("student",) and (required_min_years or 0) >= 2:
        warnings.append({
            "type": "student_fulltime",
            "message": "Full-time role with an experience floor while you are still studying.",
        })

    multiplier = round(max(0.0, min(1.0, multiplier)), 4)

    high_blockers = [b for b in blockers if b.get("severity") == "high"]
    if high_blockers:
        status = "not_eligible"
    elif blockers:
        status = "partially_eligible"
    else:
        status = "eligible"

    return EligibilityResult(
        status=status,
        multiplier=multiplier,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )


def _fmt_years(years: float) -> str:
    if years <= 0:
        return "no professional experience"
    if years < 1:
        months = int(round(years * 12))
        return f"{months} month{'s' if months != 1 else ''}"
    if abs(years - round(years)) < 0.1:
        n = int(round(years))
        return f"{n} year{'s' if n != 1 else ''}"
    return f"{years:.1f} years"


def band_for_score(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "moderate"
    return "low"


BAND_LABELS = {
    "excellent": "Excellent Match",
    "good": "Good Match",
    "moderate": "Moderate Match",
    "low": "Low Match",
}
