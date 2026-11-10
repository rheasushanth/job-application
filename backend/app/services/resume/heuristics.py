"""Rule-based structured extraction.

Two jobs:
  1. Sole extractor when no LLM key is configured.
  2. Cross-check and gap-filler when the LLM runs — anything the model omits is
     back-filled from here, and agreement between the two raises the confidence
     score shown in the review UI.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.data.skills import STOP_SKILL_WORDS
from app.services.matching.skills import extract_skills_from_text, normalise_skills
from app.services.resume.segment import section_text, segment, split_entries

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Grab any run of digits with optional separators, then filter by digit count.
# Counting digits is far more reliable than trying to anticipate every grouping
# convention (+91 98765 43210, (555) 123-4567, 555.123.4567, …).
PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{7,18}\d")
LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?((?:linkedin\.com|github\.com|gitlab\.com|"
                     r"behance\.net|dribbble\.com|medium\.com|kaggle\.com|leetcode\.com|"
                     r"stackoverflow\.com)/[\w\-./%?=&#]+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[\w\-.]+\.[a-z]{2,}(?:/[\w\-./%?=&#]*)?", re.IGNORECASE)

MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
MONTH_INDEX = {m: i + 1 for i, m in enumerate(MONTHS)}

DATE_RANGE_RE = re.compile(
    r"(?P<start>(?:" + "|".join(MONTHS) + r")[a-z]*\.?\s*,?\s*\d{4}|\d{1,2}/\d{4}|\d{4})"
    r"\s*(?:-|–|—|to|till|until)\s*"
    r"(?P<end>(?:" + "|".join(MONTHS) + r")[a-z]*\.?\s*,?\s*\d{4}|\d{1,2}/\d{4}|\d{4}|present|current|ongoing|now)",
    re.IGNORECASE,
)

DEGREE_PATTERNS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (5, "Doctorate", ("ph.d", "phd", "doctorate", "doctoral", "d.phil")),
    (4, "Master", ("m.tech", "mtech", "m.e.", "m.sc", "msc", "m.s.", "masters", "master",
                   "mba", "m.c.a", "mca", "m.com", "m.a.", "post graduate", "postgraduate", "pg diploma")),
    (3, "Bachelor", ("b.tech", "btech", "b.e.", "be ", "bachelor", "bachelors", "b.sc", "bsc",
                     "b.s.", "b.c.a", "bca", "b.com", "bcom", "b.a.", "bba", "undergraduate",
                     "engineering", "mbbs")),
    (2, "Diploma", ("diploma", "polytechnic", "associate degree")),
    (1, "High School", ("high school", "higher secondary", "senior secondary", "intermediate",
                        "12th", "xii", "hsc", "10th", "ssc", "secondary school", "cbse", "icse")),
)

FIELD_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Computer Science", ("computer science", "cse", "computer engineering", "comp sci")),
    ("Information Technology", ("information technology", " it ", "i.t.")),
    ("Electronics", ("electronics", "ece", "electrical", "eee", "instrumentation")),
    ("Mechanical Engineering", ("mechanical", "automobile")),
    ("Civil Engineering", ("civil", "structural")),
    ("Data Science", ("data science", "data analytics")),
    ("Artificial Intelligence", ("artificial intelligence", "machine learning", "ai & ml", "ai and ml", "aiml")),
    ("Business Administration", ("business administration", "management", "mba", "bba", "commerce")),
    ("Mathematics", ("mathematics", "maths", "statistics")),
    ("Physics", ("physics",)),
    ("Chemistry", ("chemistry", "chemical")),
    ("Biotechnology", ("biotechnology", "biotech", "bioinformatics")),
    ("Design", ("design", "fine arts")),
    ("Economics", ("economics",)),
)

INTERNSHIP_CUES = ("intern", "internship", "trainee", "apprentice", "co-op", "summer training")

# Lines that are never a candidate's name.
_NAME_BLOCKLIST = re.compile(
    r"resume|curriculum vitae|\bcv\b|@|\d{4}|http|www\.|phone|mobile|email|address|"
    r"linkedin|github|objective|summary|profile",
    re.IGNORECASE,
)


def extract_structured(text: str) -> tuple[dict[str, Any], list[str]]:
    """Return (payload, warnings) in the ParsedResume payload shape."""
    sections = segment(text)
    warnings: list[str] = []

    contact = _extract_contact(text, sections)
    education = _extract_education(sections, warnings)
    skills_payload, langs, frameworks, tools = _extract_skills(text, sections)
    projects = _extract_projects(sections)
    experience = _extract_experience(sections)
    certifications = _extract_certifications(sections)
    achievements = _extract_achievements(sections)

    if not contact.get("name"):
        warnings.append("Could not identify your name — please add it.")
    if not contact.get("email"):
        warnings.append("No email address found in the resume.")
    if not education:
        warnings.append("No education section could be parsed.")
    if not skills_payload["technical"]:
        warnings.append("No technical skills were recognised — add a skills section.")
    if not projects and not experience:
        warnings.append("Neither projects nor work experience were found.")

    payload = {
        "contact": contact,
        "education": education,
        "skills": skills_payload,
        "languages": langs,
        "frameworks": frameworks,
        "tools": tools,
        "projects": projects,
        "experience": experience,
        "certifications": certifications,
        "achievements": achievements,
    }
    return payload, warnings


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------


def _extract_contact(text: str, sections: dict[str, str]) -> dict[str, Any]:
    head = "\n".join(text.split("\n")[:18])
    search_space = section_text(sections, "header", "contact") or head

    email_match = EMAIL_RE.search(text)
    email = email_match.group(0).rstrip(".") if email_match else None

    phone = _extract_phone(search_space) or _extract_phone(text[:2000])

    links: list[str] = []
    for match in LINK_RE.finditer(text):
        url = "https://" + match.group(1).rstrip("/.,);")
        if url not in links:
            links.append(url)
    for match in URL_RE.finditer(search_space):
        url = match.group(0).rstrip("/.,);")
        if not any(url in existing or existing in url for existing in links):
            links.append(url)

    return {
        "name": _extract_name(text, email),
        "email": email,
        "phone": phone,
        "location": _extract_location(search_space),
        "links": links[:8],
    }


def _extract_phone(text: str) -> str | None:
    """Find a phone number by digit count rather than by grouping pattern."""
    for line in text.split("\n"):
        # Dates and CGPA/percentage figures live on their own lines or next to
        # tell-tale words; skip those outright to cut false positives.
        if re.search(r"cgpa|gpa|percentage|\bscore\b|\bmarks\b", line, re.IGNORECASE):
            continue
        for match in PHONE_RE.finditer(line):
            raw = match.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            # 10 digits domestic, up to 13 with a country code.
            if not (10 <= len(digits) <= 13):
                continue
            # A bare 4-digit year pair like "2022 - 2026" also yields 8 digits,
            # so require that the run not look like a date range.
            if re.fullmatch(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}", raw):
                continue
            return raw
    return None


def _extract_name(text: str, email: str | None) -> str | None:
    for raw_line in text.split("\n")[:12]:
        line = raw_line.strip().strip("|-–—•*").strip()
        if not line or len(line) > 60:
            continue
        if _NAME_BLOCKLIST.search(line):
            continue
        words = [w for w in re.split(r"\s+", line) if w]
        if not (1 < len(words) <= 5):
            continue
        # Accept Title Case or ALL CAPS, which covers most resume headers.
        alpha_words = [w for w in words if re.fullmatch(r"[A-Za-z.'-]+", w)]
        if len(alpha_words) != len(words):
            continue
        if all(w[0].isupper() for w in words) or line.isupper():
            return " ".join(w.title() if w.isupper() else w for w in words)

    # Fall back to the email local part: "rhea.sushanth@..." → "Rhea Sushanth".
    if email:
        local = email.split("@")[0]
        parts = [p for p in re.split(r"[._\-0-9]+", local) if len(p) > 1]
        if len(parts) >= 2:
            return " ".join(p.capitalize() for p in parts[:3])
    return None


_LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\s*,\s*([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\b"
)


def _extract_location(text: str) -> str | None:
    """Find a "City, Region" pair in the header.

    The contact line usually packs several fields together
    ("Bengaluru, Karnataka | me@example.com | +91 ..."), so each line is split
    on its separators and the fragments are examined individually rather than
    discarding the whole line because it also contains an email.
    """
    for line in text.split("\n")[:12]:
        for fragment in re.split(r"\s*[|•·]\s*|\s{3,}", line):
            fragment = fragment.strip()
            if not fragment or len(fragment) > 60:
                continue
            if EMAIL_RE.search(fragment) or "http" in fragment.lower():
                continue
            if re.search(r"\d", fragment):
                continue
            match = _LOCATION_RE.search(fragment)
            if match:
                return f"{match.group(1)}, {match.group(2)}"
    return None


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------


def _degree_level(text: str) -> tuple[int, str | None]:
    low = f" {text.lower()} "
    for level, label, cues in DEGREE_PATTERNS:
        if any(cue in low for cue in cues):
            return level, label
    return 0, None


def _field_of_study(text: str) -> str | None:
    low = f" {text.lower()} "
    for field, cues in FIELD_KEYWORDS:
        if any(cue in low for cue in cues):
            return field
    return None


_SCORE_RE = re.compile(
    r"(?:cgpa|gpa|sgpa|percentage|score|marks)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?)\s*(?:/\s*(\d{1,2}))?"
    r"|(\d{1,2}\.\d{1,2})\s*/\s*(10|10\.0|4|4\.0)\b"
    r"|\b(\d{2}(?:\.\d{1,2})?)\s*%",
    re.IGNORECASE,
)


def _extract_education(sections: dict[str, str], warnings: list[str]) -> list[dict[str, Any]]:
    block = sections.get("education", "")
    if not block:
        return []

    entries: list[dict[str, Any]] = []
    for entry in split_entries(block):
        level, label = _degree_level(entry)
        if level == 0 and not re.search(r"\b(university|college|institute|school|academy)\b",
                                        entry, re.IGNORECASE):
            continue

        institution = None
        for line in entry.split("\n"):
            if re.search(r"\b(university|college|institute|school|academy|polytechnic)\b",
                         line, re.IGNORECASE):
                institution = line.strip(" -|,").strip()
                if len(institution) > 120:
                    institution = institution[:120]
                break

        start = end = None
        ongoing = bool(
            re.search(r"present|current|ongoing|expected|pursuing", entry, re.IGNORECASE)
        )
        full = re.findall(r"\b((?:19|20)\d{2})\b", entry)
        if full:
            start = full[0]
            # Keep the end *year* even when the course is in progress — it is
            # the expected graduation year, which seniority rules depend on.
            end = full[-1] if len(full) > 1 else None

        score = None
        score_match = _SCORE_RE.search(entry)
        if score_match:
            score = next((g for g in score_match.groups() if g), None)

        degree_line = next(
            (ln.strip() for ln in entry.split("\n")
             if _degree_level(ln)[0] > 0),
            entry.split("\n")[0].strip(),
        )

        entries.append({
            "degree": (degree_line[:140] if degree_line else label),
            "level": level,
            "level_label": label,
            "field": _field_of_study(entry),
            "institution": institution,
            "start": start,
            "end": end,
            "ongoing": ongoing,
            "score": score,
        })

    if not entries and block:
        warnings.append("An education section was found but no entries could be parsed from it.")
    entries.sort(key=lambda e: e.get("level") or 0, reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

_SKILL_SPLIT_RE = re.compile(r"[,;|/•·]|\s{3,}|\sand\s")


def _extract_skills(
    text: str, sections: dict[str, str]
) -> tuple[dict[str, list[str]], list[str], list[str], list[str]]:
    from app.data.skills import SKILL_CATEGORY

    skills_block = sections.get("skills", "")

    # Explicit list from the skills section, plus a full-text ontology scan so
    # skills mentioned only inside project bullets are not lost.
    listed: list[str] = []
    for line in skills_block.split("\n"):
        body = line
        if ":" in line:
            body = line.split(":", 1)[1]
        body = body.lstrip("- ").strip()
        for token in _SKILL_SPLIT_RE.split(body):
            token = token.strip(" .()[]")
            if token and 1 < len(token) <= 40 and token.lower() not in STOP_SKILL_WORDS:
                listed.append(token)

    canonical_listed, unknown = normalise_skills(listed)
    scanned = extract_skills_from_text(text)

    all_canonical: list[str] = []
    for skill in canonical_listed + scanned:
        if skill not in all_canonical:
            all_canonical.append(skill)

    languages = [s for s in all_canonical if SKILL_CATEGORY.get(s) == "language"]
    frameworks = [s for s in all_canonical if SKILL_CATEGORY.get(s) == "framework"]
    tools = [s for s in all_canonical if SKILL_CATEGORY.get(s) in ("tool", "devops", "cloud", "database")]
    soft = [s for s in all_canonical if SKILL_CATEGORY.get(s) == "soft"]
    technical = [s for s in all_canonical if SKILL_CATEGORY.get(s) != "soft"]

    payload = {
        "technical": technical,
        "soft": soft,
        "tools": tools,
        "unrecognised": unknown[:20],
    }
    return payload, languages, frameworks, tools


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _extract_projects(sections: dict[str, str]) -> list[dict[str, Any]]:
    block = sections.get("projects", "")
    if not block:
        return []

    projects: list[dict[str, Any]] = []
    for entry in split_entries(block):
        lines = [ln for ln in entry.split("\n") if ln.strip()]
        if not lines:
            continue

        head = lines[0].strip(" -|")
        # A project title is usually before a separator or dash.
        name = re.split(r"\s[-–—|:]\s", head)[0].strip()
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        if len(name) > 110:
            name = name[:110]

        body = "\n".join(lines[1:]).strip() or head
        highlights = [ln.strip("- ").strip() for ln in lines[1:] if ln.strip().startswith("- ")]
        tech = extract_skills_from_text(entry)

        projects.append({
            "name": name or "Untitled project",
            "description": _trim(body, 900),
            "tech": tech,
            "highlights": highlights[:6],
            "links": [m.group(0) for m in URL_RE.finditer(entry)][:3],
        })
    return projects[:20]


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


def _parse_date_token(token: str) -> tuple[int, int] | None:
    token = token.strip().lower().replace(",", " ")
    if re.fullmatch(r"present|current|ongoing|now", token):
        today = date.today()
        return today.year, today.month
    slash = re.fullmatch(r"(\d{1,2})/(\d{4})", token)
    if slash:
        return int(slash.group(2)), int(slash.group(1))
    month_year = re.match(r"([a-z]{3})[a-z]*\.?\s+(\d{4})", token)
    if month_year:
        month = MONTH_INDEX.get(month_year.group(1))
        if month:
            return int(month_year.group(2)), month
    year_only = re.fullmatch(r"(19|20)\d{2}", token)
    if year_only:
        return int(token), 1
    return None


def _months_between(entry: str) -> tuple[int, str | None, str | None]:
    match = DATE_RANGE_RE.search(entry)
    if not match:
        return 0, None, None
    start = _parse_date_token(match.group("start"))
    end = _parse_date_token(match.group("end"))
    if not start or not end:
        return 0, match.group("start"), match.group("end")
    months = (end[0] - start[0]) * 12 + (end[1] - start[1])
    # Inclusive of the starting month; clamp out nonsense ranges.
    months = max(0, months) + 1 if months >= 0 else 0
    if months > 600:
        months = 0
    return months, match.group("start"), match.group("end")


def _extract_experience(sections: dict[str, str]) -> list[dict[str, Any]]:
    block = section_text(sections, "experience", "internships")
    if not block:
        return []

    out: list[dict[str, Any]] = []
    for entry in split_entries(block):
        lines = [ln for ln in entry.split("\n") if ln.strip()]
        if not lines:
            continue

        head = lines[0].strip(" -|")
        parts = [p.strip() for p in re.split(r"\s[-–—|,]\s|\sat\s", head) if p.strip()]
        role = parts[0][:140] if parts else head[:140]
        company = None
        for part in parts[1:]:
            if not DATE_RANGE_RE.search(part) and not re.fullmatch(r"[\d\s/–-]+", part):
                company = part[:140]
                break
        # The company sometimes sits on the second line instead.
        if company is None and len(lines) > 1 and not lines[1].strip().startswith("- "):
            second = lines[1].strip(" -|")
            if len(second) <= 90 and not DATE_RANGE_RE.search(second):
                company = second

        months, start, end = _months_between(entry)
        kind = "internship" if any(cue in entry.lower() for cue in INTERNSHIP_CUES) else "job"

        out.append({
            "role": role,
            "company": company,
            "kind": kind,
            "start": start,
            "end": end,
            "months": months,
            "description": _trim("\n".join(lines[1:]) or head, 900),
            "tech": extract_skills_from_text(entry),
        })
    return out[:20]


# ---------------------------------------------------------------------------
# Certifications & achievements
# ---------------------------------------------------------------------------


def _extract_certifications(sections: dict[str, str]) -> list[dict[str, Any]]:
    block = sections.get("certifications", "")
    if not block:
        return []
    out: list[dict[str, Any]] = []
    for line in block.split("\n"):
        item = line.strip("- ").strip()
        if not item or len(item) < 4:
            continue
        year_match = re.search(r"\b((?:19|20)\d{2})\b", item)
        issuer = None
        issuer_match = re.search(
            r"\b(?:by|from|-|–|\|)\s*([A-Z][\w&.,'\- ]{2,60})$", item
        )
        if issuer_match:
            issuer = issuer_match.group(1).strip(" .,-")
        out.append({
            "name": re.sub(r"\s*[\(\[]?\b(?:19|20)\d{2}\b[\)\]]?\s*$", "", item).strip(" -–|")[:200],
            "issuer": issuer,
            "year": year_match.group(1) if year_match else None,
        })
    return out[:25]


def _extract_achievements(sections: dict[str, str]) -> list[str]:
    block = section_text(sections, "achievements", "publications")
    if not block:
        return []
    out: list[str] = []
    for line in block.split("\n"):
        item = line.strip("- ").strip()
        if item and len(item) > 8:
            out.append(_trim(item, 300))
    return out[:25]


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
