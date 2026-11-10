"""LLM-based structured extraction from resume text.

The model is given pre-segmented text and a strict JSON schema, and is told to
copy rather than infer. Output is validated and coerced before use: anything
malformed is dropped and back-filled from the heuristic extractor rather than
trusted.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import llm
from app.services.resume.segment import segment

logger = logging.getLogger(__name__)

SYSTEM = (
    "You extract structured data from resumes. You transcribe only what the document "
    "states — you never invent, embellish or infer facts that are not present. "
    "If a field is absent, use null or an empty list. Respond with a single JSON object."
)

SCHEMA_PROMPT = """Extract this resume into JSON with exactly this shape:

{
  "contact": {
    "name": string|null, "email": string|null, "phone": string|null,
    "location": string|null, "links": [string]
  },
  "education": [{
    "degree": string, "level_label": "High School"|"Diploma"|"Bachelor"|"Master"|"Doctorate"|null,
    "field": string|null, "institution": string|null,
    "start": string|null, "end": string|null, "score": string|null
  }],
  "skills": { "technical": [string], "soft": [string] },
  "languages": [string],
  "frameworks": [string],
  "tools": [string],
  "projects": [{
    "name": string, "description": string, "tech": [string], "highlights": [string]
  }],
  "experience": [{
    "role": string, "company": string|null, "kind": "internship"|"job",
    "start": string|null, "end": string|null, "months": number|null,
    "description": string, "tech": [string]
  }],
  "certifications": [{ "name": string, "issuer": string|null, "year": string|null }],
  "achievements": [string]
}

Rules:
- "languages" means PROGRAMMING languages only, not spoken languages.
- "frameworks" means libraries and frameworks; "tools" means platforms, cloud
  services, databases and developer tooling.
- "kind" is "internship" for internships, trainee and apprentice roles.
- "months" is the duration in whole months if the dates allow it, else null.
- Preserve the resume's own wording in descriptions; do not rewrite or improve.
- Dates stay as written in the document.

Resume text follows, pre-segmented by section.

<resume>
{resume}
</resume>"""


async def structure_with_llm(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Return (payload, error). payload is None when the LLM is unavailable."""
    if not llm.llm_available():
        return None, "no_api_key"

    sections = segment(text)
    if sections:
        rendered = "\n\n".join(
            f"## {name.upper()}\n{body}" for name, body in sections.items() if body
        )
    else:
        rendered = text
    rendered = rendered[:24000]

    result = await llm.complete_json(
        SCHEMA_PROMPT.replace("{resume}", rendered),
        system=SYSTEM,
        max_tokens=8000,
    )
    if not result.ok:
        return None, result.error

    payload = _coerce(result.data)
    if payload is None:
        return None, "schema_mismatch"
    return payload, None


# ---------------------------------------------------------------------------
# Validation / coercion — never trust the model's shape
# ---------------------------------------------------------------------------


def _s(value: Any, limit: int = 400) -> str | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None
    return text[:limit]


def _slist(value: Any, limit: int = 60, item_limit: int = 120) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:limit]:
        text = _s(item, item_limit)
        if text and text not in out:
            out.append(text)
    return out


def _dlist(value: Any, limit: int = 30) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def _coerce(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    raw_contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
    contact = {
        "name": _s(raw_contact.get("name"), 120),
        "email": _s(raw_contact.get("email"), 320),
        "phone": _s(raw_contact.get("phone"), 60),
        "location": _s(raw_contact.get("location"), 160),
        "links": _slist(raw_contact.get("links"), 10, 300),
    }

    education: list[dict[str, Any]] = []
    for item in _dlist(data.get("education")):
        degree = _s(item.get("degree"), 160)
        institution = _s(item.get("institution"), 160)
        if not degree and not institution:
            continue
        education.append({
            "degree": degree or institution,
            "level_label": _s(item.get("level_label"), 40),
            "field": _s(item.get("field"), 120),
            "institution": institution,
            "start": _s(item.get("start"), 40),
            "end": _s(item.get("end"), 40),
            "score": _s(item.get("score"), 40),
        })

    raw_skills = data.get("skills") if isinstance(data.get("skills"), dict) else {}
    skills = {
        "technical": _slist(raw_skills.get("technical"), 150, 60),
        "soft": _slist(raw_skills.get("soft"), 40, 60),
    }

    projects: list[dict[str, Any]] = []
    for item in _dlist(data.get("projects")):
        name = _s(item.get("name"), 160)
        if not name:
            continue
        projects.append({
            "name": name,
            "description": _s(item.get("description"), 1200) or "",
            "tech": _slist(item.get("tech"), 40, 60),
            "highlights": _slist(item.get("highlights"), 10, 400),
        })

    experience: list[dict[str, Any]] = []
    for item in _dlist(data.get("experience")):
        role = _s(item.get("role"), 160)
        if not role:
            continue
        months = item.get("months")
        try:
            months_val = int(float(months)) if months is not None else 0
            if not (0 <= months_val <= 600):
                months_val = 0
        except (TypeError, ValueError):
            months_val = 0
        kind = _s(item.get("kind"), 20) or "job"
        if kind not in ("internship", "job"):
            kind = "internship" if "intern" in kind.lower() else "job"
        experience.append({
            "role": role,
            "company": _s(item.get("company"), 160),
            "kind": kind,
            "start": _s(item.get("start"), 40),
            "end": _s(item.get("end"), 40),
            "months": months_val,
            "description": _s(item.get("description"), 1200) or "",
            "tech": _slist(item.get("tech"), 40, 60),
        })

    certifications: list[dict[str, Any]] = []
    for item in _dlist(data.get("certifications")):
        name = _s(item.get("name"), 240)
        if not name:
            continue
        certifications.append({
            "name": name,
            "issuer": _s(item.get("issuer"), 160),
            "year": _s(item.get("year"), 20),
        })

    return {
        "contact": contact,
        "education": education,
        "skills": skills,
        "languages": _slist(data.get("languages"), 40, 60),
        "frameworks": _slist(data.get("frameworks"), 60, 60),
        "tools": _slist(data.get("tools"), 60, 60),
        "projects": projects,
        "experience": experience,
        "certifications": certifications,
        "achievements": _slist(data.get("achievements"), 30, 400),
    }
