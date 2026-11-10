"""Split resume text into labelled sections.

Both the heuristic extractor and the LLM prompt consume this: giving the model
pre-segmented text markedly improves field accuracy versus handing it a wall of
raw text, and it gives the fallback path something structured to work with.
"""

from __future__ import annotations

import re

# Canonical section -> heading cues. Order matters only for ambiguity.
SECTION_CUES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "objective", "profile", "about me", "career objective", "professional summary"),
    "education": ("education", "academic", "academics", "qualification", "qualifications", "educational background", "academic details"),
    "skills": ("skills", "technical skills", "technical expertise", "core competencies", "competencies",
               "technologies", "tech stack", "areas of expertise", "skill set", "proficiencies"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "professional background"),
    "internships": ("internship", "internships", "internship experience", "training", "industrial training"),
    "projects": ("projects", "project work", "academic projects", "personal projects", "key projects",
                 "project experience", "selected projects"),
    "certifications": ("certification", "certifications", "certificates", "licenses",
                       "courses", "online courses", "professional development"),
    "achievements": ("achievements", "achievement", "accomplishments", "awards", "honors", "honours",
                     "awards and honors", "extracurricular", "activities", "positions of responsibility"),
    "publications": ("publications", "papers", "research"),
    "languages": ("languages", "languages known", "language proficiency"),
    "interests": ("interests", "hobbies", "hobbies and interests"),
    "references": ("references", "referees"),
    "contact": ("contact", "contact information", "personal details", "personal information"),
}

_CUE_TO_SECTION: dict[str, str] = {}
for _section, _cues in SECTION_CUES.items():
    for _cue in _cues:
        _CUE_TO_SECTION[_cue] = _section

_MAX_HEADING_WORDS = 6
_MAX_HEADING_CHARS = 60


def _normalise_heading(line: str) -> str:
    cleaned = line.strip().strip(":•-–—_=|#*").strip()
    cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
    cleaned = re.sub(r"[^a-zA-Z& ]+", " ", cleaned)
    return " ".join(cleaned.lower().split())


def is_heading(line: str) -> str | None:
    """Return the canonical section name if this line looks like a heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    if stripped.startswith("- "):
        return None

    normalised = _normalise_heading(stripped)
    if not normalised or len(normalised.split()) > _MAX_HEADING_WORDS:
        return None

    if normalised in _CUE_TO_SECTION:
        return _CUE_TO_SECTION[normalised]

    # Headings are often decorated: "TECHNICAL SKILLS —", "## Projects".
    # Accept a cue match only when the line is short and mostly the cue itself.
    for cue, section in _CUE_TO_SECTION.items():
        if normalised.startswith(cue) and len(normalised) <= len(cue) + 14:
            return section
        if normalised.endswith(cue) and len(normalised) <= len(cue) + 14:
            return section
    return None


def segment(text: str) -> dict[str, str]:
    """Split into {section: text}. Pre-heading content lands in 'header'."""
    if not text:
        return {}

    sections: dict[str, list[str]] = {"header": []}
    current = "header"

    for line in text.split("\n"):
        section = is_heading(line)
        if section:
            current = section
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)

    return {
        name: "\n".join(lines).strip()
        for name, lines in sections.items()
        if "\n".join(lines).strip()
    }


def section_text(sections: dict[str, str], *names: str) -> str:
    """Concatenate several sections, skipping missing ones."""
    return "\n".join(sections[n] for n in names if sections.get(n)).strip()


def detected_sections(sections: dict[str, str]) -> list[str]:
    return [s for s in sections if s != "header"]


def missing_sections(sections: dict[str, str]) -> list[str]:
    """Sections whose absence is worth warning the user about."""
    important = ("education", "skills", "projects", "experience")
    found = set(sections)
    missing = []
    for name in important:
        if name in found:
            continue
        if name == "experience" and "internships" in found:
            continue
        missing.append(name)
    return missing


def split_entries(block: str) -> list[str]:
    """Split a section body into individual entries.

    Resumes separate entries by blank lines, by bullet groups, or not at all.
    This prefers blank-line grouping, then falls back to treating a non-bullet
    line followed by bullets as an entry head.
    """
    if not block:
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", block) if b.strip()]
    if len(blocks) > 1:
        return blocks

    entries: list[str] = []
    buffer: list[str] = []
    for line in block.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        is_bullet = stripped.startswith("- ")
        if not is_bullet and buffer and any(b.strip().startswith("- ") for b in buffer):
            entries.append("\n".join(buffer).strip())
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        entries.append("\n".join(buffer).strip())
    return [e for e in entries if e]
