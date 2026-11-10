"""Skill normalisation, extraction from free text, and overlap scoring.

Everything here is deterministic. The LLM may *propose* skills, but every
proposal is funnelled through `normalise_skills` so the strings that reach the
scorer come from a closed vocabulary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.data.skills import (
    ALIAS_TO_CANONICAL,
    SCAN_TERMS,
    SKILL_CATEGORY,
    SKILL_ONTOLOGY,
    STOP_SKILL_WORDS,
    is_technical,
    related_skills,
)

_CANONICALS = list(SKILL_ONTOLOGY.keys())
_NORM_KEYS = list(ALIAS_TO_CANONICAL.keys())

# Credit given when the candidate lacks skill X but holds something the
# ontology marks as adjacent (e.g. Flask for a FastAPI requirement).
RELATED_CREDIT = 0.55
# Credit for a fuzzy string hit that is not an exact alias (typos, spacing).
FUZZY_CREDIT = 0.85
FUZZY_THRESHOLD = 88


def normalise_token(text: str) -> str:
    return " ".join(str(text).lower().replace("-", " ").replace("_", " ").split())


def canonicalise(raw: str) -> str | None:
    """Map one raw skill string to a canonical name, or None if unrecognised."""
    if not raw:
        return None
    raw = str(raw).strip().strip(".,;:()[]{}•·|/\\")
    if not raw or len(raw) > 60:
        return None

    low = raw.lower()
    if low in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[low]

    norm = normalise_token(raw)
    if not norm or norm in STOP_SKILL_WORDS:
        return None
    if norm in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[norm]

    # Strip common qualifiers: "advanced python", "python programming".
    stripped = re.sub(
        r"^(advanced|basic|intermediate|expert|proficient in|working knowledge of|hands on|hands-on)\s+",
        "", norm,
    )
    stripped = re.sub(r"\s+(programming|development|language|framework|library|skills?)$", "", stripped)
    if stripped and stripped in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[stripped]

    # Fuzzy, but only for strings long enough that a near-miss is meaningful.
    if len(norm) >= 4:
        hit = process.extractOne(norm, _NORM_KEYS, scorer=fuzz.ratio, score_cutoff=92)
        if hit:
            return ALIAS_TO_CANONICAL[hit[0]]
    return None


def normalise_skills(raw_skills: list[str]) -> tuple[list[str], list[str]]:
    """Return (canonical skills, unrecognised originals). Order-stable."""
    canonical: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for raw in raw_skills or []:
        if not isinstance(raw, str):
            continue
        hit = canonicalise(raw)
        if hit:
            if hit not in seen:
                seen.add(hit)
                canonical.append(hit)
        else:
            cleaned = raw.strip()
            if cleaned and len(cleaned) <= 60 and normalise_token(cleaned) not in STOP_SKILL_WORDS:
                unknown.append(cleaned)
    return canonical, unknown


_WORD_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _pattern_for(term: str) -> re.Pattern[str]:
    pat = _WORD_BOUNDARY_CACHE.get(term)
    if pat is None:
        # Escape, then allow flexible whitespace/hyphen between words.
        parts = [re.escape(p) for p in term.split()]
        body = r"[\s\-_]+".join(parts)
        # \b fails next to '+' or '#', so use lookarounds on word chars only.
        pat = re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[term] = pat
    return pat


def extract_skills_from_text(text: str, limit: int = 120) -> list[str]:
    """Scan free text for ontology terms. Used for job descriptions and as the
    resume fallback when no LLM is configured."""
    if not text:
        return []
    haystack = normalise_token(text)
    found: list[str] = []
    seen: set[str] = set()
    for term, canon in SCAN_TERMS:
        if canon in seen:
            continue
        if len(term) < 2:
            continue
        if term in haystack and _pattern_for(term).search(haystack):
            seen.add(canon)
            found.append(canon)
            if len(found) >= limit:
                break
    return found


# ---------------------------------------------------------------------------
# Requirement splitting: mandatory vs preferred
# ---------------------------------------------------------------------------

_MANDATORY_CUES = (
    "required", "requirements", "must have", "must-have", "minimum qualifications",
    "basic qualifications", "you will need", "what you need", "essential",
    "mandatory", "qualifications", "who you are", "skills required",
    "eligibility", "we require",
)
_PREFERRED_CUES = (
    "preferred", "nice to have", "nice-to-have", "bonus", "plus", "desirable",
    "good to have", "advantageous", "a plus", "additional skills",
    "preferred qualifications", "it would be great", "optional",
)


def split_requirements(description: str) -> tuple[list[str], list[str]]:
    """Partition a job description's skills into mandatory and preferred.

    Works on paragraph/bullet blocks: a block inherits the most recent cue
    heading it sits under. Blocks with no cue default to mandatory, which is the
    conservative choice — it means an unmatched skill can gate eligibility
    rather than being silently treated as optional.
    """
    if not description:
        return [], []

    blocks = re.split(r"\n+", description)
    current = "required"
    required_text: list[str] = []
    preferred_text: list[str] = []

    for block in blocks:
        low = block.lower().strip()
        if not low:
            continue
        # A short line containing a cue is a heading; switch mode.
        is_heading = len(low) < 120
        if is_heading and any(cue in low for cue in _PREFERRED_CUES):
            current = "preferred"
        elif is_heading and any(cue in low for cue in _MANDATORY_CUES):
            current = "required"
        (preferred_text if current == "preferred" else required_text).append(block)

    req = extract_skills_from_text("\n".join(required_text))
    pref = extract_skills_from_text("\n".join(preferred_text))
    # A skill named in both places is mandatory.
    pref = [s for s in pref if s not in set(req)]
    return req, pref


# ---------------------------------------------------------------------------
# Overlap scoring
# ---------------------------------------------------------------------------


@dataclass
class SkillMatchResult:
    score: float  # 0..1 weighted coverage
    matched: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    missing_mandatory: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def matched_names(self) -> list[str]:
        return [m["skill"] for m in self.matched]

    @property
    def missing_names(self) -> list[str]:
        return [m["skill"] for m in self.missing]


def score_skill_overlap(
    candidate_skills: list[str],
    required: list[str],
    preferred: list[str],
    mandatory_weight: float = 2.0,
    preferred_weight: float = 1.0,
) -> SkillMatchResult:
    """Weighted coverage of a job's skills by the candidate's skills.

    Mandatory skills count double by default, so covering optional extras can
    never fully substitute for a missing requirement. Credit tiers:
      exact/alias → 1.0, fuzzy → 0.85, ontology-adjacent → 0.55.
    """
    cand_set = set(candidate_skills)
    cand_norm = {normalise_token(s): s for s in candidate_skills}
    # Expand candidate skills with their adjacency sets for partial credit.
    adjacency: dict[str, str] = {}
    for skill in candidate_skills:
        for rel in related_skills(skill):
            adjacency.setdefault(rel, skill)

    matched: list[dict] = []
    missing: list[dict] = []
    missing_mandatory: list[str] = []
    total_weight = 0.0
    earned = 0.0

    def evaluate(skill: str, weight: float, kind: str) -> None:
        nonlocal total_weight, earned
        total_weight += weight

        if skill in cand_set:
            earned += weight
            matched.append({"skill": skill, "kind": kind, "via": "exact", "credit": 1.0})
            return

        norm = normalise_token(skill)
        if norm in cand_norm:
            earned += weight
            matched.append({"skill": skill, "kind": kind, "via": "exact", "credit": 1.0})
            return

        if cand_norm:
            hit = process.extractOne(
                norm, list(cand_norm.keys()), scorer=fuzz.ratio, score_cutoff=FUZZY_THRESHOLD
            )
            if hit:
                earned += weight * FUZZY_CREDIT
                matched.append({
                    "skill": skill, "kind": kind, "via": "fuzzy",
                    "credit": FUZZY_CREDIT, "candidate_skill": cand_norm[hit[0]],
                })
                return

        if skill in adjacency:
            earned += weight * RELATED_CREDIT
            matched.append({
                "skill": skill, "kind": kind, "via": "related",
                "credit": RELATED_CREDIT, "candidate_skill": adjacency[skill],
            })
            return

        missing.append({
            "skill": skill, "kind": kind,
            "category": SKILL_CATEGORY.get(skill, "other"),
        })
        if kind == "mandatory":
            missing_mandatory.append(skill)

    for skill in dict.fromkeys(required):
        evaluate(skill, mandatory_weight, "mandatory")
    for skill in dict.fromkeys(preferred):
        if skill in set(required):
            continue
        evaluate(skill, preferred_weight, "preferred")

    job_skills = set(required) | set(preferred)
    extra = [s for s in candidate_skills if s not in job_skills and is_technical(s)]

    score = (earned / total_weight) if total_weight > 0 else 0.0
    return SkillMatchResult(
        score=round(min(1.0, score), 4),
        matched=matched,
        missing=missing,
        missing_mandatory=missing_mandatory,
        extra=extra[:25],
    )
