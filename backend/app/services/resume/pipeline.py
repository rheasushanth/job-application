"""Resume processing orchestration: extract → structure → merge → profile.

The merge step is the interesting one. When both extractors run, a field is
taken from the LLM (better at messy layouts) but *corroborated* by the
heuristic: agreement raises confidence, disagreement lowers it and the review
UI flags the field for the user to check. Nothing is silently assumed correct.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.matching.embeddings import embed_text, embed_texts
from app.services.matching.skills import normalise_skills
from app.services.resume import heuristics, llm_structure, seniority
from app.services.resume.extract import extract_text
from app.services.resume.segment import detected_sections, missing_sections, segment

logger = logging.getLogger(__name__)


async def process_resume_text(text: str) -> dict[str, Any]:
    """Structure raw resume text. Returns a dict ready for ParsedResume."""
    heuristic_payload, warnings = heuristics.extract_structured(text)

    llm_payload, llm_error = await llm_structure.structure_with_llm(text)

    if llm_payload is None:
        payload = heuristic_payload
        mode = "heuristic"
        confidence = _confidence_for_heuristic(payload)
        if llm_error and llm_error != "no_api_key":
            warnings.append(
                "AI extraction was unavailable, so rule-based parsing was used. "
                "Please review the fields below carefully."
            )
    else:
        payload, confidence, merge_notes = _merge(llm_payload, heuristic_payload)
        mode = "merged"
        warnings.extend(merge_notes)

    payload = _normalise_payload(payload)

    sections = segment(text)
    for missing in missing_sections(sections):
        warnings.append(f"No '{missing}' section was detected in the resume.")

    derived = derive_profile_facts(payload)

    return {
        "payload": payload,
        "field_confidence": confidence,
        "warnings": list(dict.fromkeys(warnings)),
        "structuring_mode": mode,
        "detected_sections": detected_sections(sections),
        "derived": derived,
    }


async def process_resume_file(path: Path, kind: str) -> dict[str, Any]:
    extraction = extract_text(path, kind)
    if not extraction.text.strip():
        return {
            "payload": _empty_payload(),
            "field_confidence": {},
            "warnings": [
                "No text could be extracted from this file. If it is a scanned image, "
                "please upload a text-based PDF or DOCX instead."
            ],
            "structuring_mode": "heuristic",
            "detected_sections": [],
            "derived": derive_profile_facts(_empty_payload()),
            "raw_text": "",
            "engine": extraction.engine,
        }

    result = await process_resume_text(extraction.text)
    result["raw_text"] = extraction.text
    result["engine"] = extraction.engine
    result["warnings"] = list(dict.fromkeys(extraction.warnings + result["warnings"]))
    return result


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

_CONTACT_FIELDS = ("name", "email", "phone", "location")


def _merge(
    llm_payload: dict[str, Any], heuristic_payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    merged: dict[str, Any] = {}
    confidence: dict[str, Any] = {}
    notes: list[str] = []

    # ---- contact: prefer LLM, corroborate with regex -------------------
    llm_contact = llm_payload.get("contact") or {}
    heur_contact = heuristic_payload.get("contact") or {}
    contact: dict[str, Any] = {}
    for field in _CONTACT_FIELDS:
        llm_value = llm_contact.get(field)
        heur_value = heur_contact.get(field)
        if llm_value and heur_value:
            if _loosely_equal(llm_value, heur_value):
                contact[field] = llm_value
                confidence[f"contact.{field}"] = 0.98
            else:
                # Email and phone are regex-verifiable, so trust the regex there.
                if field in ("email", "phone"):
                    contact[field] = heur_value
                    confidence[f"contact.{field}"] = 0.8
                else:
                    contact[field] = llm_value
                    confidence[f"contact.{field}"] = 0.6
                notes.append(
                    f"Two different values were found for your {field} — please confirm it."
                )
        elif llm_value:
            contact[field] = llm_value
            confidence[f"contact.{field}"] = 0.82
        elif heur_value:
            contact[field] = heur_value
            confidence[f"contact.{field}"] = 0.7
        else:
            contact[field] = None
            confidence[f"contact.{field}"] = 0.0

    links = list(dict.fromkeys((llm_contact.get("links") or []) + (heur_contact.get("links") or [])))
    contact["links"] = links[:10]
    confidence["contact.links"] = 0.9 if links else 0.0
    merged["contact"] = contact

    # ---- education: LLM structure, heuristic levels --------------------
    llm_edu = llm_payload.get("education") or []
    heur_edu = heuristic_payload.get("education") or []
    education = llm_edu or heur_edu
    for entry in education:
        if not entry.get("level"):
            blob = " ".join(
                str(entry.get(k) or "") for k in ("level_label", "degree", "field")
            )
            level, label = heuristics._degree_level(blob)
            entry["level"] = level
            entry.setdefault("level_label", label)
        if not entry.get("field"):
            entry["field"] = heuristics._field_of_study(
                " ".join(str(entry.get(k) or "") for k in ("degree", "institution"))
            )
    merged["education"] = education
    confidence["education"] = _agreement_confidence(len(llm_edu), len(heur_edu), bool(education))

    # ---- skills: union of both, then normalised -------------------------
    llm_skills = llm_payload.get("skills") or {}
    heur_skills = heuristic_payload.get("skills") or {}
    technical = _union(llm_skills.get("technical"), heur_skills.get("technical"))
    soft = _union(llm_skills.get("soft"), heur_skills.get("soft"))
    merged["skills"] = {"technical": technical, "soft": soft}
    merged["languages"] = _union(llm_payload.get("languages"), heuristic_payload.get("languages"))
    merged["frameworks"] = _union(llm_payload.get("frameworks"), heuristic_payload.get("frameworks"))
    merged["tools"] = _union(llm_payload.get("tools"), heuristic_payload.get("tools"))
    confidence["skills"] = 0.95 if technical else 0.0

    # ---- projects / experience: prefer the richer extraction ------------
    merged["projects"] = _prefer_richer(
        llm_payload.get("projects"), heuristic_payload.get("projects"), "name"
    )
    confidence["projects"] = _agreement_confidence(
        len(llm_payload.get("projects") or []),
        len(heuristic_payload.get("projects") or []),
        bool(merged["projects"]),
    )

    experience = _prefer_richer(
        llm_payload.get("experience"), heuristic_payload.get("experience"), "role"
    )
    # Durations are arithmetic — take the heuristic's parsed months when the
    # LLM left them blank.
    heur_by_role = {
        str(e.get("role", "")).lower(): e for e in (heuristic_payload.get("experience") or [])
    }
    for entry in experience:
        if not entry.get("months"):
            match = heur_by_role.get(str(entry.get("role", "")).lower())
            if match and match.get("months"):
                entry["months"] = match["months"]
        if not entry.get("tech"):
            entry["tech"] = heuristics.extract_skills_from_text(
                f"{entry.get('role','')} {entry.get('description','')}"
            )
    merged["experience"] = experience
    confidence["experience"] = _agreement_confidence(
        len(llm_payload.get("experience") or []),
        len(heuristic_payload.get("experience") or []),
        bool(experience),
    )

    merged["certifications"] = _prefer_richer(
        llm_payload.get("certifications"), heuristic_payload.get("certifications"), "name"
    )
    confidence["certifications"] = 0.9 if merged["certifications"] else 0.0

    merged["achievements"] = _union(
        llm_payload.get("achievements"), heuristic_payload.get("achievements")
    )
    confidence["achievements"] = 0.9 if merged["achievements"] else 0.0

    return merged, confidence, notes


def _loosely_equal(a: Any, b: Any) -> bool:
    sa = "".join(ch for ch in str(a).lower() if ch.isalnum())
    sb = "".join(ch for ch in str(b).lower() if ch.isalnum())
    if not sa or not sb:
        return False
    return sa == sb or sa in sb or sb in sa


def _union(*lists: Any) -> list[str]:
    out: list[str] = []
    for lst in lists:
        if not isinstance(lst, list):
            continue
        for item in lst:
            if isinstance(item, str):
                value = item.strip()
                if value and value not in out:
                    out.append(value)
    return out


def _prefer_richer(primary: Any, secondary: Any, key: str) -> list[dict]:
    """Use the list with more entries; if equal, prefer the primary (LLM)."""
    primary = [p for p in (primary or []) if isinstance(p, dict) and p.get(key)]
    secondary = [s for s in (secondary or []) if isinstance(s, dict) and s.get(key)]
    if len(secondary) > len(primary):
        chosen, other = secondary, primary
    else:
        chosen, other = primary, secondary

    # Fold in entries the chosen list missed entirely.
    seen = {str(c.get(key, "")).lower()[:40] for c in chosen}
    for entry in other:
        token = str(entry.get(key, "")).lower()[:40]
        if token and token not in seen:
            chosen.append(entry)
            seen.add(token)
    return chosen


def _agreement_confidence(llm_count: int, heur_count: int, has_data: bool) -> float:
    if not has_data:
        return 0.0
    if llm_count and heur_count:
        ratio = min(llm_count, heur_count) / max(llm_count, heur_count)
        return round(0.72 + 0.26 * ratio, 2)
    return 0.72 if llm_count else 0.6


def _confidence_for_heuristic(payload: dict[str, Any]) -> dict[str, Any]:
    """Rule-based parsing alone warrants modest confidence — be honest about it."""
    contact = payload.get("contact") or {}
    conf: dict[str, Any] = {}
    # Regex-verifiable fields are reliable; inferred ones are not.
    conf["contact.email"] = 0.95 if contact.get("email") else 0.0
    conf["contact.phone"] = 0.85 if contact.get("phone") else 0.0
    conf["contact.name"] = 0.6 if contact.get("name") else 0.0
    conf["contact.location"] = 0.5 if contact.get("location") else 0.0
    conf["contact.links"] = 0.9 if contact.get("links") else 0.0
    conf["education"] = 0.6 if payload.get("education") else 0.0
    conf["skills"] = 0.8 if (payload.get("skills") or {}).get("technical") else 0.0
    conf["projects"] = 0.55 if payload.get("projects") else 0.0
    conf["experience"] = 0.55 if payload.get("experience") else 0.0
    conf["certifications"] = 0.6 if payload.get("certifications") else 0.0
    conf["achievements"] = 0.6 if payload.get("achievements") else 0.0
    return conf


# ---------------------------------------------------------------------------
# Normalisation & derived facts
# ---------------------------------------------------------------------------


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonicalise every skill list against the ontology, keeping originals."""
    skills = payload.get("skills") or {}
    technical_raw = skills.get("technical") or []
    canonical, unknown = normalise_skills(technical_raw)

    languages, _ = normalise_skills(payload.get("languages") or [])
    frameworks, _ = normalise_skills(payload.get("frameworks") or [])
    tools, _ = normalise_skills(payload.get("tools") or [])

    # Anything the model filed under languages/frameworks/tools is also a skill.
    for bucket in (languages, frameworks, tools):
        for item in bucket:
            if item not in canonical:
                canonical.append(item)

    payload["skills"] = {
        "technical": canonical,
        "soft": skills.get("soft") or [],
        "raw": technical_raw,
        "unrecognised": unknown[:25],
    }
    payload["languages"] = languages
    payload["frameworks"] = frameworks
    payload["tools"] = tools

    for project in payload.get("projects") or []:
        tech, _ = normalise_skills(project.get("tech") or [])
        project["tech"] = tech
    for entry in payload.get("experience") or []:
        tech, _ = normalise_skills(entry.get("tech") or [])
        entry["tech"] = tech

    return payload


def derive_profile_facts(payload: dict[str, Any]) -> dict[str, Any]:
    education = payload.get("education") or []
    experience = payload.get("experience") or []

    total_months, internship_months = seniority.derive_totals(experience)
    degree_level, field_of_study, graduation_year = seniority.derive_education_facts(education)
    label, signals = seniority.classify(
        education=education, experience=experience, graduation_year=graduation_year
    )

    return {
        "total_experience_months": total_months,
        "internship_months": internship_months,
        "highest_degree_level": degree_level,
        "field_of_study": field_of_study,
        "graduation_year": graduation_year,
        "seniority": label,
        "seniority_signals": signals,
    }


def build_profile_text(payload: dict[str, Any], derived: dict[str, Any]) -> str:
    """Flatten a profile into the text that gets embedded.

    Ordering is deliberate: role-ish and skill content first, since the
    embedding of a job description is dominated by the same.
    """
    parts: list[str] = []
    skills = (payload.get("skills") or {}).get("technical") or []
    if skills:
        parts.append("Skills: " + ", ".join(skills[:60]))
    if payload.get("languages"):
        parts.append("Programming languages: " + ", ".join(payload["languages"]))
    if payload.get("frameworks"):
        parts.append("Frameworks: " + ", ".join(payload["frameworks"]))
    if payload.get("tools"):
        parts.append("Tools and platforms: " + ", ".join(payload["tools"]))

    for entry in (payload.get("experience") or [])[:6]:
        bits = [entry.get("role") or ""]
        if entry.get("company"):
            bits.append(f"at {entry['company']}")
        if entry.get("description"):
            bits.append(str(entry["description"])[:400])
        parts.append(" ".join(b for b in bits if b))

    for project in (payload.get("projects") or [])[:8]:
        bits = [f"Project {project.get('name') or ''}"]
        if project.get("description"):
            bits.append(str(project["description"])[:400])
        if project.get("tech"):
            bits.append("using " + ", ".join(project["tech"][:12]))
        parts.append(" ".join(b for b in bits if b))

    for entry in (payload.get("education") or [])[:3]:
        bits = [entry.get("degree") or ""]
        if entry.get("field"):
            bits.append(f"in {entry['field']}")
        if entry.get("institution"):
            bits.append(f"from {entry['institution']}")
        parts.append(" ".join(b for b in bits if b))

    if payload.get("certifications"):
        parts.append(
            "Certifications: "
            + ", ".join(str(c.get("name") or "") for c in payload["certifications"][:10])
        )
    parts.append(f"Candidate level: {derived.get('seniority', 'fresher').replace('_', ' ')}")

    return "\n".join(p for p in parts if p.strip())


def embed_profile(payload: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    """Compute the profile embedding plus per-project/experience embeddings."""
    profile_text = build_profile_text(payload, derived)
    vector, model = embed_text(profile_text)

    project_texts = [
        f"{p.get('name') or ''} {p.get('description') or ''} {' '.join(p.get('tech') or [])}"
        for p in (payload.get("projects") or [])
    ]
    experience_texts = [
        f"{e.get('role') or ''} {e.get('company') or ''} {e.get('description') or ''} "
        f"{' '.join(e.get('tech') or [])}"
        for e in (payload.get("experience") or [])
    ]

    project_vectors = embed_texts(project_texts)[0] if project_texts else []
    experience_vectors = embed_texts(experience_texts)[0] if experience_texts else []

    return {
        "profile_text": profile_text,
        "embedding": vector,
        "embedding_model": model,
        "project_embeddings": project_vectors,
        "experience_embeddings": experience_vectors,
    }


def _empty_payload() -> dict[str, Any]:
    return {
        "contact": {"name": None, "email": None, "phone": None, "location": None, "links": []},
        "education": [],
        "skills": {"technical": [], "soft": [], "raw": [], "unrecognised": []},
        "languages": [],
        "frameworks": [],
        "tools": [],
        "projects": [],
        "experience": [],
        "certifications": [],
        "achievements": [],
    }
