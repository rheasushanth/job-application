"""Behaviour pins for the match algorithm.

These tests are the reason the scorer is a pure function: the match percentage
is a product claim, so it needs to be reproducible and its invariants explicit.
"""

from __future__ import annotations

from app.services.matching.embeddings import embed_text
from app.services.matching.scorer import CandidateInput, JobInput, score_job
from app.services.matching.skills import (
    canonicalise,
    extract_skills_from_text,
    normalise_skills,
    score_skill_overlap,
    split_requirements,
)


def _candidate(**over) -> CandidateInput:
    base = dict(
        skills=["Python", "Django", "PostgreSQL", "Docker", "Git", "REST API"],
        programming_languages=["Python", "SQL"],
        frameworks=["Django"],
        tools=["Git", "Docker"],
        projects=[
            {
                "name": "Inventory API",
                "description": "A REST backend for stock tracking",
                "tech": ["Python", "Django", "PostgreSQL"],
            }
        ],
        experience=[
            {
                "role": "Backend Intern",
                "company": "Acme",
                "kind": "internship",
                "months": 6,
                "description": "Built Django REST endpoints",
                "tech": ["Python", "Django"],
            }
        ],
        total_experience_months=6,
        internship_months=6,
        highest_degree_level=3,
        field_of_study="Computer Science",
        seniority="fresher",
    )
    base.update(over)
    return CandidateInput(**base)


def _job(**over) -> JobInput:
    base = dict(
        title="Backend Developer",
        company="Example Co",
        description="Build Django services backed by PostgreSQL. Docker experience required.",
        required_skills=["Python", "Django", "PostgreSQL"],
        preferred_skills=["Docker", "Kubernetes"],
        education_requirement={"min_level": 3, "fields": ["Computer Science"]},
        experience_min_years=0.0,
        experience_level="entry",
        job_type="full_time",
    )
    base.update(over)
    return JobInput(**base)


# --------------------------------------------------------------------------
# Core invariants
# --------------------------------------------------------------------------

def test_score_is_bounded_and_banded():
    result = score_job(_candidate(), _job())
    assert 0.0 <= result.score <= 100.0
    assert result.band in {"excellent", "good", "moderate", "low"}


def test_strong_candidate_scores_well_and_is_eligible():
    result = score_job(_candidate(), _job())
    assert result.score >= 70, result.calculation
    assert result.eligibility.status == "eligible"
    assert result.missing_mandatory_skills == []


def test_contributions_sum_to_pre_gate_percentage():
    """The displayed arithmetic has to actually add up."""
    result = score_job(_candidate(), _job())
    total = sum(c["contribution"] for c in result.category_scores.values())
    assert abs(total - result.calculation["pre_gate_percentage"]) < 0.05


def test_final_equals_pre_gate_times_multiplier():
    result = score_job(_candidate(), _job(required_skills=["Python", "Rust", "Scala"]))
    expected = result.calculation["pre_gate_percentage"] * result.eligibility.multiplier
    assert abs(result.score - round(expected, 2)) < 0.05


def test_deterministic_across_runs():
    a = score_job(_candidate(), _job())
    b = score_job(_candidate(), _job())
    assert a.score == b.score
    assert a.category_scores == b.category_scores


# --------------------------------------------------------------------------
# The headline requirement: optional strength cannot mask a mandatory miss
# --------------------------------------------------------------------------

def test_missing_mandatory_skill_gates_the_score():
    job = _job(required_skills=["Python", "Rust"], preferred_skills=["Docker", "Git"])
    result = score_job(_candidate(), job)
    assert "Rust" in result.missing_mandatory_skills
    assert result.eligibility.multiplier < 1.0
    assert result.eligibility.status != "eligible"


def test_optional_matches_cannot_outweigh_unmet_mandatory_requirement():
    """A candidate acing every optional skill must still rank below one who
    meets the mandatory requirement."""
    gated_job = _job(
        required_skills=["Python", "Rust"],
        preferred_skills=["Docker", "Git", "REST API", "PostgreSQL"],
    )
    clean_job = _job(
        required_skills=["Python", "Django"],
        preferred_skills=["Docker"],
    )
    gated = score_job(_candidate(), gated_job)
    clean = score_job(_candidate(), clean_job)
    assert gated.score < clean.score
    assert gated.eligibility.status in {"partially_eligible", "not_eligible"}


def test_many_mandatory_misses_compound_but_hit_a_floor():
    job = _job(required_skills=["Rust", "Scala", "Go", "Haskell", "Erlang"])
    result = score_job(_candidate(), job)
    assert result.eligibility.multiplier >= 0.25
    assert result.eligibility.status == "not_eligible"


def test_implausibly_long_required_list_does_not_gate():
    """A mis-segmented posting listing 25 'required' skills should warn, not
    hard-fail the candidate."""
    many = [
        "Rust", "Scala", "Go", "Haskell", "Erlang", "Elixir", "Clojure", "Perl",
        "COBOL", "Fortran", "Lua", "Julia", "Dart", "Swift", "Kotlin", "Ruby",
        "PHP", "MATLAB", "R", "Assembly",
    ]
    result = score_job(_candidate(), _job(required_skills=many))
    assert result.eligibility.status == "eligible"
    assert any(w["type"] == "mandatory_skills_unreliable" for w in result.eligibility.warnings)


# --------------------------------------------------------------------------
# Education and experience gating
# --------------------------------------------------------------------------

def test_degree_shortfall_penalises():
    job = _job(education_requirement={"min_level": 4, "fields": ["Computer Science"]})
    low = score_job(_candidate(highest_degree_level=1), job)
    assert low.eligibility.multiplier < 1.0
    assert any(b["type"] == "education" for b in low.eligibility.blockers)


def test_degree_met_is_not_penalised():
    job = _job(education_requirement={"min_level": 3, "fields": ["Computer Science"]})
    result = score_job(_candidate(highest_degree_level=3), job)
    assert not any(b["type"] == "education" for b in result.eligibility.blockers)


def test_experience_floor_scales_with_shortfall():
    senior = _job(experience_min_years=5.0, experience_level="senior")
    fresher = score_job(_candidate(total_experience_months=6), senior)
    midway = score_job(_candidate(total_experience_months=48), senior)
    assert fresher.score < midway.score
    assert fresher.eligibility.multiplier <= midway.eligibility.multiplier


def test_experience_level_fit_rewards_being_in_band():
    job = _job(experience_min_years=None, experience_max_years=None, experience_level="mid")
    in_band = score_job(_candidate(total_experience_months=36), job)
    out_of_band = score_job(_candidate(total_experience_months=1), job)
    assert (
        in_band.category_scores["experience_level_fit"]["raw"]
        > out_of_band.category_scores["experience_level_fit"]["raw"]
    )


def test_overqualified_internship_warns_without_blocking():
    job = _job(job_type="internship", experience_level="internship", experience_min_years=0.0)
    result = score_job(
        _candidate(total_experience_months=60, seniority="experienced"), job
    )
    assert any(w["type"] == "overqualified" for w in result.eligibility.warnings)
    assert result.eligibility.status == "eligible"


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------

def test_weights_change_the_outcome():
    cand = _candidate()
    job = _job()
    skills_heavy = score_job(cand, job, {"technical_skills": 1.0, "semantic_similarity": 0.0,
                                         "project_relevance": 0.0, "experience_relevance": 0.0,
                                         "education_match": 0.0, "experience_level_fit": 0.0})
    semantic_heavy = score_job(cand, job, {"technical_skills": 0.0, "semantic_similarity": 1.0,
                                           "project_relevance": 0.0, "experience_relevance": 0.0,
                                           "education_match": 0.0, "experience_level_fit": 0.0})
    assert skills_heavy.score != semantic_heavy.score
    assert skills_heavy.category_scores["technical_skills"]["weight"] == 1.0


def test_zero_weight_category_contributes_nothing():
    weights = {**{k: 0.0 for k in (
        "technical_skills", "semantic_similarity", "project_relevance",
        "experience_relevance", "education_match", "experience_level_fit")},
        "technical_skills": 1.0}
    result = score_job(_candidate(), _job(), weights)
    assert result.category_scores["education_match"]["contribution"] == 0.0


# --------------------------------------------------------------------------
# Graceful degradation
# --------------------------------------------------------------------------

def test_empty_candidate_does_not_crash():
    result = score_job(CandidateInput(), _job())
    assert 0.0 <= result.score <= 100.0
    assert result.recommendations


def test_job_with_no_parsed_skills_does_not_crash():
    result = score_job(_candidate(), _job(required_skills=[], preferred_skills=[]))
    assert 0.0 <= result.score <= 100.0
    assert result.category_scores["technical_skills"]["raw"] == 0.0


def test_semantic_component_uses_real_embeddings():
    """Related texts must score above unrelated ones through the real provider."""
    cand_vec, _ = embed_text(
        "Backend engineer building Django REST APIs with PostgreSQL and Docker"
    )
    close, _ = embed_text("Hiring a Django backend developer to build REST APIs on PostgreSQL")
    far, _ = embed_text("Seeking a dental hygienist for a paediatric clinic reception desk")

    near_score = score_job(
        _candidate(embedding=cand_vec), _job(embedding=close)
    ).category_scores["semantic_similarity"]["raw"]
    far_score = score_job(
        _candidate(embedding=cand_vec), _job(embedding=far)
    ).category_scores["semantic_similarity"]["raw"]
    assert near_score > far_score


def test_reasons_and_recommendations_are_populated():
    result = score_job(_candidate(), _job(required_skills=["Python", "Rust"]))
    assert result.reasons
    assert result.recommendations
    assert any("Rust" in r for r in result.recommendations)


# --------------------------------------------------------------------------
# Skill layer
# --------------------------------------------------------------------------

def test_canonicalise_handles_aliases_and_punctuation():
    assert canonicalise("py") == "Python"
    assert canonicalise("ReactJS") == "React"
    assert canonicalise("node js") == "Node.js"
    assert canonicalise("c++") == "C++"
    assert canonicalise("k8s") == "Kubernetes"
    assert canonicalise("advanced python") == "Python"
    assert canonicalise("machine-learning") == "Machine Learning"
    assert canonicalise("") is None
    assert canonicalise("experience") is None


def test_normalise_skills_dedupes_and_reports_unknown():
    canonical, unknown = normalise_skills(["Python", "py", "PYTHON", "Blorptech"])
    assert canonical == ["Python"]
    assert "Blorptech" in unknown


def test_extract_skills_from_text_avoids_substring_false_positives():
    found = extract_skills_from_text("We use Java and Spring Boot for our services.")
    assert "Java" in found
    assert "Spring" in found
    # "JavaScript" must not be inferred from "Java"
    assert "JavaScript" not in found


def test_split_requirements_separates_mandatory_from_preferred():
    description = (
        "Requirements:\n"
        "- Strong Python and Django experience\n"
        "- SQL databases\n"
        "Nice to have:\n"
        "- Kubernetes\n"
        "- Terraform\n"
    )
    required, preferred = split_requirements(description)
    assert "Python" in required and "Django" in required
    assert "Kubernetes" in preferred
    assert "Kubernetes" not in required


def test_related_skill_earns_partial_not_full_credit():
    exact = score_skill_overlap(["FastAPI"], ["FastAPI"], [])
    related = score_skill_overlap(["Flask"], ["FastAPI"], [])
    assert exact.score == 1.0
    assert 0.0 < related.score < 1.0
    assert related.matched[0]["via"] == "related"


def test_mandatory_skills_weigh_double_the_preferred():
    only_mandatory = score_skill_overlap(["Python"], ["Python"], ["Docker"])
    only_preferred = score_skill_overlap(["Docker"], ["Python"], ["Docker"])
    assert only_mandatory.score > only_preferred.score


# --------------------------------------------------------------------------
# Thin-requirement postings must not win on trivial coverage
# --------------------------------------------------------------------------

def test_single_skill_posting_does_not_earn_full_technical_weight():
    """Regression: a posting where the parser found one skill the candidate
    happens to have scored 1.000 on technical match at full weight, floating
    thinly-described senior roles above genuinely relevant ones."""
    thin = _job(
        title="Head of Engineering",
        required_skills=["Python"],
        preferred_skills=[],
        experience_min_years=None,
        experience_level="lead",
    )
    result = score_job(_candidate(), thin)
    technical = result.category_scores["technical_skills"]
    assert technical["raw"] == 1.0
    # Full coverage, but the weight was damped because the evidence is thin.
    assert technical["weight"] < technical["configured_weight"]
    assert result.calculation["skill_confidence"] < 1.0
    assert result.calculation["weight_adjustments"]


def test_rich_posting_keeps_its_full_configured_weight():
    rich = _job(
        required_skills=["Python", "Django", "PostgreSQL"],
        preferred_skills=["Docker", "Git"],
    )
    result = score_job(_candidate(), rich)
    technical = result.category_scores["technical_skills"]
    assert technical["weight"] == technical["configured_weight"]
    assert result.calculation["skill_confidence"] == 1.0
    assert result.calculation["weight_adjustments"] == []


def test_relevant_junior_role_outranks_thin_senior_posting():
    """The end-to-end symptom this guards against."""
    relevant = _job(
        title="Backend Developer Intern",
        required_skills=["Python", "Django", "PostgreSQL"],
        preferred_skills=["Docker", "Git"],
        experience_min_years=0.0,
        experience_level="internship",
        job_type="internship",
    )
    thin_senior = _job(
        title="Head of Engineering",
        required_skills=["Python"],
        preferred_skills=[],
        experience_min_years=8.0,
        experience_level="lead",
    )
    assert score_job(_candidate(), relevant).score > score_job(_candidate(), thin_senior).score


def test_contributions_still_reconcile_after_weight_damping():
    result = score_job(_candidate(), _job(required_skills=["Python"], preferred_skills=[]))
    total = sum(c["contribution"] for c in result.category_scores.values())
    assert abs(total - result.calculation["pre_gate_percentage"]) < 0.05


def test_posting_with_no_parsed_skills_falls_back_to_other_signals():
    result = score_job(_candidate(), _job(required_skills=[], preferred_skills=[]))
    assert 0.0 <= result.score <= 100.0
    assert result.reasons
    # Education and level still contributed.
    assert result.calculation["pre_gate_percentage"] > 0


# --------------------------------------------------------------------------
# Prose-scanning precision
# --------------------------------------------------------------------------

def test_ambiguous_words_are_not_extracted_as_skills_from_prose():
    """Regression: bare common words were matching as skills, so a backend
    posting listed Operations, Human Resources and Go as requirements, and the
    skill-gap advice told a CS student to learn Sales."""
    prose = (
        "You will go through our onboarding, work closely with day-to-day "
        "operations and our HR team, and excel at communication and teamwork. "
        "Our sales and finance partners rely on this service. Security is "
        "everyone's responsibility, and testing your changes is expected."
    )
    found = extract_skills_from_text(prose)
    for bogus in (
        "Go", "Operations", "Human Resources", "Excel", "Communication",
        "Teamwork", "Sales", "Finance", "Cybersecurity", "Manual Testing",
    ):
        assert bogus not in found, f"{bogus} should not be scanned from prose: {found}"


def test_unambiguous_aliases_still_scan():
    """Excluding the bare form must not break the real alias."""
    assert "Go" in extract_skills_from_text("Experience with Golang required.")
    assert "R" in extract_skills_from_text("Statistical work in R language.")
    assert "Excel" in extract_skills_from_text("Advanced Microsoft Excel skills.")


def test_ambiguous_terms_still_accepted_when_listed_explicitly():
    """A candidate who lists these in a skills section must still match."""
    canonical, _ = normalise_skills(["Go", "Operations", "Communication", "Excel"])
    assert "Go" in canonical
    assert "Operations" in canonical
    assert "Communication" in canonical
    assert "Excel" in canonical


def test_language_names_are_not_over_blocked():
    """Rust, Swift, Scala and Spring mean the technology in a software posting,
    so they must keep scanning from prose."""
    found = extract_skills_from_text(
        "We write Rust and Swift, run Scala jobs, and use Spring on the JVM."
    )
    for expected in ("Rust", "Swift", "Scala", "Spring"):
        assert expected in found, f"{expected} missing from {found}"


def test_real_technical_skills_still_scan_normally():
    found = extract_skills_from_text(
        "Build Django REST APIs on PostgreSQL, deploy with Docker and Kubernetes, "
        "write tests in pytest, and use React with TypeScript on the frontend."
    )
    for expected in (
        "Django", "REST API", "PostgreSQL", "Docker", "Kubernetes",
        "Unit Testing", "React", "TypeScript",
    ):
        assert expected in found, f"{expected} missing from {found}"
