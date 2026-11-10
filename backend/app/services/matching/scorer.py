"""The weighted scoring algorithm.

This module is pure: it takes plain dataclasses in and returns a result out. No
database, no network, no LLM. That is what makes the match percentage testable
and reproducible — `tests/test_scorer.py` pins its behaviour.

The LLM contributes *inputs* (structured resume fields, extracted job skills)
and *prose* (explanations), never the number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.matching.eligibility import (
    DEGREE_LEVELS,
    EligibilityResult,
    band_for_score,
    evaluate_eligibility,
)
from app.services.matching.embeddings import cosine_similarity, rescale_similarity
from app.services.matching.skills import score_skill_overlap
from app.services.matching.weights import CATEGORY_LABELS, DEFAULT_WEIGHTS

# A posting's skill coverage is only as trustworthy as the number of skills the
# parser actually found in it. Covering "1 of 1" skills is a 100% coverage
# figure carrying almost no evidence, and left unchecked it floats
# thinly-described senior postings to the top of a junior candidate's results.
#
# Below this many extracted skills, the technical-skills category has its
# *weight* scaled down proportionally. Because the final score normalises by
# the total weight, the remaining categories absorb the slack automatically —
# the score stays a true weighted mean and the adjustment is reported in the
# breakdown rather than being a hidden fudge.
MIN_TRUSTED_JOB_SKILLS = 4

# Experience-level expected bands in years, used when a posting gives a level
# but no explicit minimum.
LEVEL_BANDS: dict[str, tuple[float, float]] = {
    "internship": (0.0, 1.0),
    "entry": (0.0, 2.0),
    "mid": (2.0, 5.0),
    "senior": (5.0, 10.0),
    "lead": (8.0, 20.0),
}


@dataclass
class CandidateInput:
    skills: list[str] = field(default_factory=list)
    programming_languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    total_experience_months: int = 0
    internship_months: int = 0
    highest_degree_level: int = 0
    field_of_study: str | None = None
    seniority: str = "fresher"
    embedding: list[float] | None = None
    project_embeddings: list[list[float]] | None = None
    experience_embeddings: list[list[float]] | None = None

    @property
    def all_skills(self) -> list[str]:
        merged: list[str] = []
        for bucket in (self.skills, self.programming_languages, self.frameworks, self.tools):
            for s in bucket:
                if s not in merged:
                    merged.append(s)
        return merged


@dataclass
class JobInput:
    title: str = ""
    company: str = ""
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education_requirement: dict[str, Any] = field(default_factory=dict)
    experience_min_years: float | None = None
    experience_max_years: float | None = None
    experience_level: str = "unspecified"
    job_type: str = "unspecified"
    embedding: list[float] | None = None


@dataclass
class ScoreResult:
    score: float
    raw_score: float
    band: str
    eligibility: EligibilityResult
    category_scores: dict[str, dict[str, float]]
    semantic_similarity: float
    matched_skills: list[dict]
    missing_skills: list[dict]
    missing_mandatory_skills: list[str]
    extra_skills: list[str]
    relevant_projects: list[dict]
    relevant_experience: list[dict]
    reasons: list[str]
    recommendations: list[str]
    calculation: dict[str, Any]


def score_job(
    candidate: CandidateInput,
    job: JobInput,
    weights: dict[str, float] | None = None,
) -> ScoreResult:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    cand_skills = candidate.all_skills

    # ---------------- 1. technical skills -------------------------------
    skill_result = score_skill_overlap(
        cand_skills, job.required_skills, job.preferred_skills
    )

    # ---------------- 2. semantic similarity ----------------------------
    raw_cosine = cosine_similarity(candidate.embedding, job.embedding)
    semantic = rescale_similarity(raw_cosine)

    # ---------------- 3. project relevance ------------------------------
    project_score, relevant_projects = _score_items(
        items=candidate.projects,
        item_embeddings=candidate.project_embeddings,
        job=job,
        name_keys=("name", "title"),
        tech_key="tech",
        duration_weighted=False,
    )

    # ---------------- 4. experience relevance ---------------------------
    experience_score, relevant_experience = _score_items(
        items=candidate.experience,
        item_embeddings=candidate.experience_embeddings,
        job=job,
        name_keys=("role", "title"),
        tech_key="tech",
        duration_weighted=True,
    )

    # ---------------- 5. education --------------------------------------
    education_score, required_degree_level, required_fields = _score_education(candidate, job)

    # ---------------- 6. experience-level fit ---------------------------
    level_score, level_detail = _score_level_fit(candidate, job)

    subscores = {
        "technical_skills": skill_result.score,
        "semantic_similarity": semantic,
        "project_relevance": project_score,
        "experience_relevance": experience_score,
        "education_match": education_score,
        "experience_level_fit": level_score,
    }

    # Down-weight skill coverage when the posting yielded too few skills for
    # the coverage figure to mean anything.
    job_skill_count = len(set(job.required_skills) | set(job.preferred_skills))
    skill_confidence = (
        min(1.0, job_skill_count / MIN_TRUSTED_JOB_SKILLS)
        if MIN_TRUSTED_JOB_SKILLS
        else 1.0
    )
    effective_weights = dict(weights)
    effective_weights["technical_skills"] = (
        weights.get("technical_skills", 0.0) * skill_confidence
    )

    total_weight = sum(effective_weights.get(k, 0.0) for k in subscores)
    if total_weight <= 0:
        # Every category was zero-weighted (either by configuration or because
        # the only weighted category was skills on a skill-less posting).
        # Fall back to the semantic signal rather than returning a flat zero.
        effective_weights = {**{k: 0.0 for k in subscores}, "semantic_similarity": 1.0}
        total_weight = 1.0
    raw = sum(
        subscores[k] * effective_weights.get(k, 0.0) for k in subscores
    ) / total_weight

    # ---------------- eligibility gate ----------------------------------
    eligibility = evaluate_eligibility(
        missing_mandatory_skills=skill_result.missing_mandatory,
        mandatory_skill_count=len(set(job.required_skills)),
        candidate_degree_level=candidate.highest_degree_level,
        required_degree_level=required_degree_level,
        candidate_field=candidate.field_of_study,
        required_fields=required_fields,
        candidate_months=candidate.total_experience_months,
        required_min_years=job.experience_min_years,
        job_type=job.job_type,
        seniority=candidate.seniority,
    )

    final = round(raw * eligibility.multiplier * 100, 2)
    final = max(0.0, min(100.0, final))

    category_scores = {
        key: {
            "raw": round(subscores[key], 4),
            "weight": round(effective_weights.get(key, 0.0), 4),
            "configured_weight": round(weights.get(key, 0.0), 4),
            "contribution": round(
                subscores[key] * effective_weights.get(key, 0.0) / total_weight * 100, 2
            ),
            "label": CATEGORY_LABELS.get(key, key),
        }
        for key in subscores
    }

    reasons = _build_reasons(skill_result, subscores, raw_cosine, relevant_projects,
                            relevant_experience, level_detail, job)
    recommendations = _build_recommendations(skill_result, subscores, eligibility, job)

    calculation = {
        "formula": "score = (Σ weightᵢ × subscoreᵢ ÷ Σ weightᵢ) × eligibility_multiplier × 100",
        "weighted_sum": round(raw, 6),
        "weight_total": round(total_weight, 4),
        "eligibility_multiplier": eligibility.multiplier,
        "pre_gate_percentage": round(raw * 100, 2),
        "final_percentage": final,
        "steps": [
            {
                "category": key,
                "label": CATEGORY_LABELS.get(key, key),
                "subscore": round(subscores[key], 4),
                "weight": round(effective_weights.get(key, 0.0), 4),
                "configured_weight": round(weights.get(key, 0.0), 4),
                "contribution_points": round(
                    subscores[key] * effective_weights.get(key, 0.0) / total_weight * 100, 2
                ),
            }
            for key in sorted(subscores, key=lambda k: -effective_weights.get(k, 0.0))
        ],
        "job_skills_parsed": job_skill_count,
        "skill_confidence": round(skill_confidence, 3),
        "weight_adjustments": (
            [] if skill_confidence >= 1.0 else [{
                "category": "technical_skills",
                "configured_weight": round(weights.get("technical_skills", 0.0), 4),
                "effective_weight": round(effective_weights["technical_skills"], 4),
                "reason": (
                    f"Only {job_skill_count} skill"
                    f"{'s' if job_skill_count != 1 else ''} could be parsed from this "
                    f"posting, which is too few for skill coverage to be reliable "
                    f"evidence, so its weight was reduced to "
                    f"{skill_confidence:.0%} and the other categories carry more."
                ),
            }]
        ),
        "gate_adjustments": [
            {"reason": b["message"], "multiplier": b.get("multiplier_applied")}
            for b in eligibility.blockers
        ],
        "semantic_cosine_raw": round(raw_cosine, 4),
        "level_fit_detail": level_detail,
    }

    return ScoreResult(
        score=final,
        raw_score=round(raw, 6),
        band=band_for_score(final),
        eligibility=eligibility,
        category_scores=category_scores,
        semantic_similarity=round(raw_cosine, 4),
        matched_skills=skill_result.matched,
        missing_skills=skill_result.missing,
        missing_mandatory_skills=skill_result.missing_mandatory,
        extra_skills=skill_result.extra,
        relevant_projects=relevant_projects,
        relevant_experience=relevant_experience,
        reasons=reasons,
        recommendations=recommendations,
        calculation=calculation,
    )


# ---------------------------------------------------------------------------
# Sub-score helpers
# ---------------------------------------------------------------------------


def _score_items(
    *,
    items: list[dict],
    item_embeddings: list[list[float]] | None,
    job: JobInput,
    name_keys: tuple[str, ...],
    tech_key: str,
    duration_weighted: bool,
) -> tuple[float, list[dict]]:
    """Score projects or experience entries against the job.

    Each item gets a blend of semantic similarity (if embeddings available) and
    shared-technology overlap. The category score is the best item, nudged up by
    the runner-up so a candidate with several relevant items beats one with a
    single lucky hit.
    """
    if not items:
        return 0.0, []

    job_skills = {s.lower() for s in (job.required_skills + job.preferred_skills)}
    title_tokens = {t for t in job.title.lower().split() if len(t) > 3}

    scored: list[dict] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        name = ""
        for key in name_keys:
            if item.get(key):
                name = str(item[key])
                break

        emb = None
        if item_embeddings and idx < len(item_embeddings):
            emb = item_embeddings[idx]
        semantic = rescale_similarity(cosine_similarity(emb, job.embedding)) if emb else 0.0

        tech = item.get(tech_key) or []
        if isinstance(tech, str):
            tech = [tech]
        tech_lower = {str(t).lower() for t in tech if t}
        shared = sorted(tech_lower & job_skills)
        overlap = len(shared) / len(job_skills) if job_skills else 0.0
        # Overlap saturates quickly: matching 5 of a job's 20 skills in one
        # project is already strong evidence of relevance.
        overlap_score = min(1.0, overlap * 3.0)

        blob = f"{name} {item.get('description') or ''}".lower()
        title_hit = bool(title_tokens & set(blob.split()))

        if emb is not None:
            combined = 0.55 * semantic + 0.45 * overlap_score
        else:
            combined = overlap_score
        if title_hit:
            combined = min(1.0, combined + 0.08)

        weight = 1.0
        if duration_weighted:
            months = item.get("months") or 0
            try:
                months = float(months)
            except (TypeError, ValueError):
                months = 0.0
            # 6 months is treated as a full-credit stint; shorter counts less.
            weight = min(1.0, 0.45 + months / 12.0) if months else 0.6

        scored.append({
            "name": name or "(untitled)",
            "relevance": round(min(1.0, combined), 4),
            "weighted_relevance": round(min(1.0, combined) * weight, 4),
            "semantic": round(semantic, 4),
            "shared_technologies": shared,
            "duration_months": item.get("months") if duration_weighted else None,
            "kind": item.get("kind"),
            "company": item.get("company"),
        })

    if not scored:
        return 0.0, []

    scored.sort(key=lambda s: -s["weighted_relevance"])
    best = scored[0]["weighted_relevance"]
    second = scored[1]["weighted_relevance"] if len(scored) > 1 else 0.0
    category = min(1.0, best + 0.25 * second)

    relevant = [s for s in scored if s["relevance"] >= 0.15][:5] or scored[:2]
    return round(category, 4), relevant


def _score_education(
    candidate: CandidateInput, job: JobInput
) -> tuple[float, int | None, list[str] | None]:
    req = job.education_requirement or {}
    required_level = req.get("min_level")
    required_fields = req.get("fields") or None

    if not required_level:
        # No stated requirement: neutral-positive rather than zero, since
        # having a degree is never a negative.
        return (0.8 if candidate.highest_degree_level >= 2 else 0.6), None, required_fields

    try:
        required_level = int(required_level)
    except (TypeError, ValueError):
        return 0.7, None, required_fields

    cand_level = candidate.highest_degree_level
    if cand_level >= required_level:
        score = 1.0
        # Field adjacency nudges, it doesn't dominate.
        if required_fields and candidate.field_of_study:
            cand_field = candidate.field_of_study.lower()
            if not any(f.lower() in cand_field or cand_field in f.lower() for f in required_fields):
                score = 0.78
    elif cand_level == required_level - 1:
        # e.g. pursuing a bachelor's for a bachelor's-required role.
        score = 0.5
    else:
        score = max(0.0, 0.25 * (cand_level / max(1, required_level)))

    return round(score, 4), required_level, required_fields


def _score_level_fit(candidate: CandidateInput, job: JobInput) -> tuple[float, dict[str, Any]]:
    years = candidate.total_experience_months / 12.0

    low = job.experience_min_years
    high = job.experience_max_years
    if low is None and high is None:
        low, high = LEVEL_BANDS.get(job.experience_level, (None, None))  # type: ignore[assignment]

    detail: dict[str, Any] = {
        "candidate_years": round(years, 2),
        "band_low": low,
        "band_high": high,
        "source": "posting" if job.experience_min_years is not None else "experience_level",
    }

    if low is None and high is None:
        detail["note"] = "No experience expectation stated; scored neutral."
        return 0.7, detail

    low = low or 0.0
    if high is None:
        high = low + 3.0

    if low <= years <= high:
        detail["note"] = "Within the expected band."
        return 1.0, detail

    if years < low:
        gap = low - years
        # Under-shooting matters: half the band's width costs roughly half the
        # score, and a 3+ year shortfall bottoms out.
        score = max(0.0, 1.0 - gap / max(1.5, low if low > 0 else 1.5))
        detail["note"] = f"{gap:.1f} year(s) below the expected minimum."
        return round(min(1.0, score), 4), detail

    over = years - high
    # Over-shooting is penalised far more gently — being experienced is rarely
    # disqualifying, though it can signal a mismatch for junior roles.
    score = max(0.45, 1.0 - over / 12.0)
    detail["note"] = f"{over:.1f} year(s) above the expected maximum."
    return round(score, 4), detail


# ---------------------------------------------------------------------------
# Narrative built from the numbers (template path; the LLM may replace it)
# ---------------------------------------------------------------------------


def _build_reasons(
    skill_result,
    subscores: dict[str, float],
    raw_cosine: float,
    projects: list[dict],
    experience: list[dict],
    level_detail: dict[str, Any],
    job: JobInput,
) -> list[str]:
    reasons: list[str] = []

    total_job_skills = len(set(job.required_skills) | set(job.preferred_skills))
    matched_count = len(skill_result.matched)
    if total_job_skills >= MIN_TRUSTED_JOB_SKILLS:
        reasons.append(
            f"Covers {matched_count} of {total_job_skills} skills listed on the posting "
            f"({skill_result.score * 100:.0f}% weighted coverage, mandatory skills counted double)."
        )
    elif total_job_skills:
        reasons.append(
            f"Only {total_job_skills} skill{'s' if total_job_skills != 1 else ''} could be "
            f"parsed from this posting, so skill coverage carried less weight than usual "
            f"and the other categories decided most of this score."
        )
    else:
        reasons.append(
            "No skills could be parsed from this posting, so the score rests on semantic "
            "similarity, your experience and your education."
        )
    exact = [m for m in skill_result.matched if m["via"] == "exact"]
    if exact:
        names = ", ".join(m["skill"] for m in exact[:6])
        reasons.append(f"Direct skill matches: {names}{'…' if len(exact) > 6 else ''}.")
    related = [m for m in skill_result.matched if m["via"] == "related"]
    if related:
        pairs = ", ".join(
            f"{m.get('candidate_skill')} → {m['skill']}" for m in related[:4]
        )
        reasons.append(f"Transferable-skill credit (partial): {pairs}.")

    if subscores["semantic_similarity"] > 0.6:
        reasons.append(
            f"Your profile reads as semantically close to this description "
            f"(cosine {raw_cosine:.2f})."
        )
    elif subscores["semantic_similarity"] < 0.25:
        reasons.append(
            f"Overall profile wording diverges from this description "
            f"(cosine {raw_cosine:.2f}), which held the semantic component down."
        )

    if projects and projects[0]["relevance"] >= 0.3:
        top = projects[0]
        shared = ", ".join(top["shared_technologies"][:4])
        reasons.append(
            f"Project “{top['name']}” is the strongest evidence"
            + (f", sharing {shared}." if shared else ".")
        )
    if experience and experience[0]["relevance"] >= 0.3:
        top = experience[0]
        where = f" at {top['company']}" if top.get("company") else ""
        reasons.append(f"Relevant experience: {top['name']}{where}.")

    if subscores["education_match"] >= 0.95:
        reasons.append("Meets the stated educational requirement.")
    if level_detail.get("note"):
        reasons.append(f"Experience level: {level_detail['note']}")

    return reasons


def _build_recommendations(
    skill_result,
    subscores: dict[str, float],
    eligibility: EligibilityResult,
    job: JobInput,
) -> list[str]:
    recs: list[str] = []

    if skill_result.missing_mandatory:
        top = ", ".join(skill_result.missing_mandatory[:3])
        recs.append(
            f"Close the mandatory gap first: {top}. These carry the most weight and currently "
            "cap your eligibility for this role."
        )
    optional_missing = [m["skill"] for m in skill_result.missing if m["kind"] == "preferred"]
    if optional_missing:
        recs.append(
            f"Preferred extras that would lift the score: {', '.join(optional_missing[:4])}."
        )
    if subscores["project_relevance"] < 0.4:
        recs.append(
            "Add or reframe a project that uses this role's core stack — project relevance is "
            "15% of the score and is currently your weakest evidence."
        )
    if subscores["semantic_similarity"] < 0.35:
        recs.append(
            "Mirror the posting's own vocabulary in your summary and bullet points; the "
            "semantic component compares whole-profile wording."
        )
    if any(b["type"] == "experience" for b in eligibility.blockers):
        recs.append(
            "You are below the stated experience floor — lead with internships, freelance work "
            "and shipped projects to argue equivalent experience."
        )
    if any(b["type"] == "education" for b in eligibility.blockers):
        recs.append(
            "The degree requirement is unmet on paper; look for an equivalent-experience clause "
            "or a referral before applying."
        )
    if not recs:
        recs.append("Strong alignment — apply with a cover note citing your closest project.")
    return recs
