"""Normalisation helpers shared by every source adapter.

Each function is conservative: when a value cannot be determined with
reasonable confidence it returns None / "unspecified" rather than guessing, so
the match engine can tell "no requirement stated" from "requirement is zero".
"""

from __future__ import annotations

import hashlib
import html as html_lib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_END_RE = re.compile(r"</(p|div|li|ul|ol|tr|h[1-6]|br)\s*/?>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LI_RE = re.compile(r"<li\b[^>]*>", re.IGNORECASE)


def html_to_text(raw: str | None) -> str:
    """Strip HTML to readable text, preserving block and bullet structure.

    Structure matters here: `split_requirements` relies on line breaks to tell
    a "Requirements:" heading from a "Nice to have:" one.
    """
    if not raw:
        return ""
    text = raw
    # Feeds sometimes double-escape their HTML (Arbeitnow does).
    for _ in range(2):
        if "&lt;" in text or "&amp;" in text or "&gt;" in text:
            text = html_lib.unescape(text)
        else:
            break
    text = _SCRIPT_RE.sub(" ", text)
    text = _LI_RE.sub("\n- ", text)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    text = text.replace("\xa0", " ").replace("​", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(line)
    return "\n".join(out).strip()


def normalise_company(name: str) -> str:
    """Canonical company token for deduplication across portals."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    # Drop legal suffixes so "Acme Inc." and "Acme Technologies Pvt Ltd" align.
    text = re.sub(
        r"\b(inc|llc|ltd|limited|pvt|private|plc|gmbh|corp|corporation|co|company|"
        r"technologies|technology|tech|labs|solutions|services|systems|group|"
        r"holdings|global|india|software|consulting)\b",
        " ", text,
    )
    return " ".join(text.split())


def normalise_title(title: str) -> str:
    if not title:
        return ""
    text = title.lower()
    text = re.sub(r"\(.*?\)", " ", text)
    # Strip gender/diversity markers common in EU postings: (m/w/d), (f/m/x).
    text = re.sub(r"\b[mfwdx](\s*/\s*[mfwdx]){1,3}\b", " ", text)
    text = re.sub(r"[^a-z0-9+#. ]+", " ", text)
    text = re.sub(
        r"\b(senior|sr|junior|jr|lead|staff|principal|intern|internship|trainee|"
        r"remote|hybrid|onsite|full|part|time|contract|freelance|urgent|hiring|"
        r"immediate|joiner|fresher|experienced)\b",
        " ", text,
    )
    return " ".join(text.split())


def content_hash(title: str, company: str, location: str | None) -> str:
    payload = "|".join([
        normalise_title(title),
        normalise_company(company),
        " ".join((location or "").lower().split())[:60],
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:40]


# ---------------------------------------------------------------------------
# Work mode / job type
# ---------------------------------------------------------------------------

_REMOTE_CUES = ("remote", "work from home", "wfh", "anywhere", "distributed", "telecommute")
_HYBRID_CUES = ("hybrid", "partially remote", "flexible location", "remote friendly")
_ONSITE_CUES = ("on-site", "onsite", "in office", "in-office", "on site")

_CUE_PATTERNS: dict[str, re.Pattern[str]] = {}


def _has_cue(haystack: str, cue: str) -> bool:
    """Whole-word cue test.

    Plain substring matching is wrong here: "intern" matches "international",
    "contract" matches "contractual obligations", and "lead" matches "leading".
    Those false positives land directly in job_type / experience_level, which
    the scorer and the filters both depend on.
    """
    pattern = _CUE_PATTERNS.get(cue)
    if pattern is None:
        body = r"[\s\-_/]+".join(re.escape(part) for part in cue.split())
        pattern = re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])", re.IGNORECASE)
        _CUE_PATTERNS[cue] = pattern
    return bool(pattern.search(haystack))


def _any_cue(haystack: str, cues: tuple[str, ...]) -> bool:
    return any(_has_cue(haystack, cue) for cue in cues)


def infer_work_mode(
    *, location_raw: str | None, description: str, tags: list[str], is_remote: bool | None
) -> tuple[str, bool]:
    """Return (work_mode, is_remote)."""
    blob = " ".join(
        part.lower() for part in ([location_raw or ""] + (tags or []) + [description[:2500]])
    )

    # An explicit hybrid signal beats a generic "remote" mention, since hybrid
    # postings almost always also say "remote".
    if _any_cue(blob, _HYBRID_CUES):
        return "hybrid", False
    if is_remote is True:
        return "remote", True
    if _any_cue(blob, _REMOTE_CUES):
        return "remote", True
    if _any_cue(blob, _ONSITE_CUES):
        return "onsite", False
    if is_remote is False and location_raw:
        return "onsite", False
    return "unspecified", bool(is_remote)


_JOB_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("internship", ("intern", "internship", "trainee", "apprentice", "co-op", "summer analyst")),
    ("part_time", ("part time", "part-time", "parttime")),
    ("contract", ("contract", "contractor", "fixed term", "fixed-term", "temporary", "c2h")),
    ("freelance", ("freelance", "freelancer", "gig")),
    ("full_time", ("full time", "full-time", "fulltime", "permanent", "regular")),
)


def infer_job_type(*, title: str, raw_type: str | None, tags: list[str], description: str) -> str:
    # Title and the source's own type field are the most reliable signals.
    primary = f"{title} {raw_type or ''} {' '.join(tags or [])}".lower()
    for job_type, cues in _JOB_TYPE_PATTERNS:
        if _any_cue(primary, cues):
            return job_type
    low_desc = description[:1500].lower()
    for job_type, cues in _JOB_TYPE_PATTERNS:
        # "internship" is never inferred from body text alone. Descriptions
        # mention interns incidentally ("you'll mentor our interns"), and a
        # false internship label both mis-sorts the job and rewrites its
        # experience band during enrichment.
        if job_type == "internship":
            continue
        if _any_cue(low_desc, cues):
            return job_type
    return "unspecified"


_LEVEL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("internship", ("intern", "internship", "trainee", "apprentice")),
    ("lead", ("principal", "staff engineer", "head of", "director", "vp ", "architect",
              "engineering manager", "tech lead", "team lead")),
    ("senior", ("senior", "sr.", "sr ", "experienced", "specialist", "expert", "iii", "iv")),
    ("entry", ("junior", "jr.", "jr ", "graduate", "entry level", "entry-level", "fresher",
               "associate", "trainee engineer", "campus")),
)


def infer_experience_level(
    *, title: str, description: str, min_years: float | None, raw_level: str | None
) -> str:
    blob = f"{title} {raw_level or ''}".lower()
    for level, cues in _LEVEL_PATTERNS:
        if _any_cue(blob, cues):
            return level

    # Fall back to the stated minimum, which is more trustworthy than prose.
    if min_years is not None:
        if min_years <= 0.5:
            return "entry"
        if min_years < 3:
            return "mid"
        if min_years < 7:
            return "senior"
        return "lead"

    low = description[:2000].lower()
    for level, cues in _LEVEL_PATTERNS:
        if _any_cue(low, cues):
            return level
    return "unspecified"


# ---------------------------------------------------------------------------
# Experience requirement
# ---------------------------------------------------------------------------

_YEARS_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:year|yr)s?",
    re.IGNORECASE,
)
_YEARS_MIN_RE = re.compile(
    r"(?:(?:at\s*least|minimum(?:\s*of)?|min\.?|over|more\s*than)\s*)?"
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:year|yr)s?"
    # "5 years of Python experience" — allow a short noun phrase between the
    # duration and the word "experience", which real postings almost always have.
    r"(?:\s*(?:of|in|with|as))?\s*(?:[\w+#./&-]+\s+){0,3}"
    r"(?:experience|exp\b)",
    re.IGNORECASE,
)
_FRESHER_RE = re.compile(
    r"\b(freshers?|no (?:prior )?experience (?:is )?(?:required|necessary)|"
    r"0\s*[-–]\s*1\s*years?|entry[- ]level)\b",
    re.IGNORECASE,
)


def parse_experience_years(description: str, title: str = "") -> tuple[float | None, float | None]:
    """Extract (min_years, max_years) from a description. None when unstated."""
    if not description:
        return None, None
    window = description[:6000]

    match = _YEARS_RANGE_RE.search(window)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        if low <= high and high <= 40:
            return low, high

    best_min: float | None = None
    for match in _YEARS_MIN_RE.finditer(window):
        value = float(match.group(1))
        if value > 40:
            continue
        # Several figures can appear ("3 years of Python, 1 year of SQL"); the
        # smallest is the safest reading of the overall bar.
        if best_min is None or value < best_min:
            best_min = value
    if best_min is not None:
        return best_min, None

    if _FRESHER_RE.search(window) or "intern" in title.lower():
        return 0.0, None
    return None, None


# ---------------------------------------------------------------------------
# Education requirement
# ---------------------------------------------------------------------------

_DEGREE_REQ_PATTERNS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("ph.d", "phd", "doctorate", "doctoral")),
    (4, ("master", "m.tech", "mtech", "m.sc", "msc", "mba", "m.s.", "mca", "postgraduate",
         "post-graduate")),
    (3, ("bachelor", "b.tech", "btech", "b.e.", "b.sc", "bsc", "b.s.", "bca", "undergraduate",
         "degree in", "bs/ms", "b.a.", "bba", "university degree")),
    (2, ("diploma", "associate degree")),
    (1, ("high school", "secondary school", "12th", "hsc")),
)

_FIELD_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Computer Science", ("computer science", "cs degree", "computer engineering")),
    ("Information Technology", ("information technology",)),
    ("Engineering", ("engineering",)),
    ("Mathematics", ("mathematics", "statistics")),
    ("Data Science", ("data science",)),
    ("Business", ("business", "commerce", "management", "finance", "economics")),
    ("Design", ("design", "fine arts", "hci")),
    ("Marketing", ("marketing", "communications")),
)


def parse_education_requirement(description: str) -> dict[str, Any]:
    """Return {min_level, fields, raw} — empty dict when nothing is stated."""
    if not description:
        return {}
    window = description[:6000]
    low = window.lower()

    min_level: int | None = None
    matched_phrase: str | None = None
    # Scan from the lowest acceptable degree up: "Bachelor's or Master's" means
    # a bachelor's is sufficient.
    for level, cues in sorted(_DEGREE_REQ_PATTERNS, key=lambda p: p[0]):
        for cue in cues:
            if _has_cue(low, cue):
                min_level = level
                matched_phrase = cue
                break
        if min_level is not None:
            break

    if min_level is None:
        return {}

    # "or equivalent experience" means the degree is not a hard gate.
    equivalent = bool(
        re.search(r"or equivalent(?:\s+(?:practical\s+)?experience)?|"
                  r"equivalent work experience|or relevant experience",
                  low)
    )

    fields: list[str] = []
    for name, cues in _FIELD_CUES:
        if _any_cue(low, cues) and name not in fields:
            fields.append(name)

    return {
        "min_level": min_level,
        "fields": fields[:4],
        "raw": matched_phrase,
        "equivalent_accepted": equivalent,
        # A degree that accepts equivalents should not hard-gate eligibility.
        **({"min_level": None} if equivalent else {}),
    }


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {
    "$": "USD", "₹": "INR", "€": "EUR", "£": "GBP", "¥": "JPY",
    "a$": "AUD", "c$": "CAD", "s$": "SGD",
}
_CURRENCY_CODES = ("USD", "INR", "EUR", "GBP", "CAD", "AUD", "SGD", "AED", "JPY", "CHF", "SEK")

_PERIOD_MULTIPLIER = {
    "year": 1.0, "annum": 1.0, "annual": 1.0, "yr": 1.0, "pa": 1.0,
    "month": 12.0, "mo": 12.0, "monthly": 12.0, "pm": 12.0,
    "week": 52.0, "wk": 52.0, "weekly": 52.0,
    "day": 260.0, "daily": 260.0,
    "hour": 2080.0, "hr": 2080.0, "hourly": 2080.0,
}

# The separated form requires at least one actual separator group, otherwise
# `\d{1,3}` alone would match just the first three digits of a plain number
# ("40000" -> "400") and silently scale the salary down by 100x.
# `\d{2,3}` groups accommodate Indian lakh grouping ("1,50,000") as well as
# western thousands ("150,000").
_NUM_RE = r"(\d{1,3}(?:[,\s]\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_SALARY_RANGE_RE = re.compile(
    rf"{_NUM_RE}\s*([kKlL])?\s*(?:-|–|—|to)\s*{_NUM_RE}\s*([kKlL])?", re.IGNORECASE
)
_SALARY_SINGLE_RE = re.compile(rf"{_NUM_RE}\s*([kKlL])?", re.IGNORECASE)


def _to_number(raw: str, suffix: str | None) -> float | None:
    try:
        value = float(raw.replace(",", "").replace(" ", ""))
    except ValueError:
        return None
    if suffix:
        low = suffix.lower()
        if low == "k":
            value *= 1_000
        elif low == "l":  # Indian lakh
            value *= 100_000
    return value


def parse_salary(raw: str | None, *, default_currency: str | None = None) -> dict[str, Any]:
    """Parse a salary string into annualised min/max plus the original period."""
    if not raw:
        return {}
    text = " ".join(str(raw).split())
    if not text or len(text) > 220:
        return {}
    low = text.lower()

    currency = None
    for code in _CURRENCY_CODES:
        if code.lower() in low:
            currency = code
            break
    if currency is None:
        for symbol, code in _CURRENCY_SYMBOLS.items():
            if symbol in low:
                currency = code
                break
    # Indian notation: "12 LPA", "8 lakh per annum".
    is_lakh_notation = bool(re.search(r"\blpa\b|\blakhs?\b|\bl\.?p\.?a\.?\b", low))
    if currency is None and (is_lakh_notation or "inr" in low or "rs." in low):
        currency = "INR"
    currency = currency or default_currency

    period = None
    multiplier = 1.0
    for cue, mult in _PERIOD_MULTIPLIER.items():
        if re.search(rf"(?:per\s+|/|\bp)?\b{re.escape(cue)}\b", low):
            period = cue
            multiplier = mult
            break
    if period is None and (is_lakh_notation or "per annum" in low):
        period, multiplier = "year", 1.0

    # Build a digits-and-suffix-only view. Currency symbols must go too:
    # leaving the "$" in "$120k - $150k" stops the range regex from matching
    # its second operand, so the range silently degraded to a single value.
    numeric_space = low
    for symbol in ("₹", "€", "£", "¥", "$"):
        numeric_space = numeric_space.replace(symbol, " ")
    # Drop alphabetic words but keep the bare k/l magnitude suffixes.
    numeric_space = re.sub(r"\b(?![kl]\b)[a-z]{1,}\b", " ", numeric_space)

    smin = smax = None
    match = _SALARY_RANGE_RE.search(numeric_space)
    if match:
        smin = _to_number(match.group(1), match.group(2))
        smax = _to_number(match.group(3), match.group(4))
        # "20k - 35k" is often written with one suffix: "$20 -$35k".
        if smin and smax and match.group(4) and not match.group(2) and smin < smax / 100:
            smin = _to_number(match.group(1), match.group(4))
    else:
        match = _SALARY_SINGLE_RE.search(numeric_space)
        if match:
            smin = _to_number(match.group(1), match.group(2))

    if smin is None and smax is None:
        return {"salary_raw": text, "salary_currency": currency, "salary_period": period}

    # "12 LPA" means 12 lakh per annum; the magnitude lives in the notation,
    # not in a digit suffix.
    if is_lakh_notation:
        if smin is not None and smin < 1000:
            smin *= 100_000
        if smax is not None and smax < 1000:
            smax *= 100_000

    # Guess the period when unstated, from the magnitude and currency.
    if period is None:
        reference = smax or smin or 0
        # With neither a currency nor a period stated, a small bare number
        # carries no interpretable meaning — inventing an hourly rate from
        # "Salary: 5" is worse than reporting nothing.
        if currency is None and reference < 1000:
            return {"salary_raw": text, "salary_currency": None, "salary_period": None}
        if currency == "INR":
            period, multiplier = ("year", 1.0) if reference >= 100_000 else ("month", 12.0)
        elif reference < 200:
            period, multiplier = "hour", 2080.0
        elif reference < 15_000:
            period, multiplier = "month", 12.0
        else:
            period, multiplier = "year", 1.0

    annual_min = round(smin * multiplier, 2) if smin is not None else None
    annual_max = round(smax * multiplier, 2) if smax is not None else None
    if annual_min and annual_max and annual_min > annual_max:
        annual_min, annual_max = annual_max, annual_min

    # Discard implausible figures rather than polluting salary filters.
    for value in (annual_min, annual_max):
        if value is not None and (value < 100 or value > 100_000_000):
            return {"salary_raw": text, "salary_currency": currency, "salary_period": period}

    return {
        "salary_min": annual_min,
        "salary_max": annual_max,
        "salary_currency": currency,
        "salary_period": period,
        "salary_raw": text,
    }


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

_COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States",
    "united states of america": "United States", "uk": "United Kingdom",
    "u.k.": "United Kingdom", "uae": "United Arab Emirates",
    "in": "India", "ind": "India",
}

_INDIAN_CITIES = {
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka",
    "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra",
    "delhi": "Delhi", "new delhi": "Delhi", "noida": "Uttar Pradesh",
    "gurugram": "Haryana", "gurgaon": "Haryana", "chennai": "Tamil Nadu",
    "coimbatore": "Tamil Nadu", "hyderabad": "Telangana", "kolkata": "West Bengal",
    "ahmedabad": "Gujarat", "surat": "Gujarat", "jaipur": "Rajasthan",
    "kochi": "Kerala", "thiruvananthapuram": "Kerala", "indore": "Madhya Pradesh",
    "chandigarh": "Chandigarh", "bhubaneswar": "Odisha", "lucknow": "Uttar Pradesh",
}

_REMOTE_PLACEHOLDERS = {
    "remote", "worldwide", "anywhere", "global", "work from home", "wfh",
    "fully remote", "remote - worldwide", "distributed", "", "n/a", "multiple locations",
}


def parse_location(raw: str | None) -> dict[str, Any]:
    """Split a free-text location into city/state/country."""
    if not raw:
        return {}
    text = " ".join(str(raw).split())
    if not text:
        return {}

    low = text.lower().strip(" ,-")
    if low in _REMOTE_PLACEHOLDERS or low.startswith("remote"):
        # Keep anything qualifying the remoteness: "Remote (India)".
        inner = re.search(r"[\(\-,]\s*([A-Za-z ,]+)\s*\)?$", text)
        if inner:
            return parse_location(inner.group(1)) | {"location_raw": text}
        return {"location_raw": text}

    # Strip leading mode markers: "Hybrid - Pune, Maharashtra".
    text = re.sub(r"^(remote|hybrid|on[- ]?site)\s*[-–—:,]\s*", "", text, flags=re.IGNORECASE)
    # Multi-location postings: take the first.
    first = re.split(r"\s*(?:;|\bor\b|\band\b|\|)\s*", text)[0].strip()

    parts = [p.strip() for p in first.split(",") if p.strip()]
    city = state = country = None

    if len(parts) >= 3:
        city, state, country = parts[0], parts[1], parts[-1]
    elif len(parts) == 2:
        first_part, second = parts
        canonical = _COUNTRY_ALIASES.get(second.lower(), second)
        if _looks_like_country(canonical):
            city, country = first_part, canonical
        else:
            city, state = first_part, second
    elif len(parts) == 1:
        single = parts[0]
        canonical = _COUNTRY_ALIASES.get(single.lower(), single)
        if _looks_like_country(canonical):
            country = canonical
        else:
            city = single

    if city:
        derived_state = _INDIAN_CITIES.get(city.lower())
        if derived_state:
            state = state or derived_state
            country = country or "India"

    if country:
        country = _COUNTRY_ALIASES.get(country.lower(), country)

    return {
        "location_raw": " ".join(str(raw).split()),
        "city": _clean_place(city),
        "state": _clean_place(state),
        "country": _clean_place(country),
    }


_KNOWN_COUNTRIES = {
    "india", "united states", "united kingdom", "canada", "australia", "germany",
    "france", "netherlands", "singapore", "united arab emirates", "ireland",
    "spain", "italy", "poland", "portugal", "sweden", "switzerland", "japan",
    "china", "brazil", "mexico", "israel", "new zealand", "south africa",
    "philippines", "indonesia", "vietnam", "malaysia", "europe", "worldwide",
    "belgium", "austria", "denmark", "norway", "finland", "czech republic",
    "romania", "hungary", "greece", "turkey", "argentina", "chile", "colombia",
}


def _looks_like_country(value: str) -> bool:
    return value.lower().strip() in _KNOWN_COUNTRIES


def _clean_place(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(value.split()).strip(" ,-")
    if not text or len(text) > 120:
        return None
    if text.lower() in _REMOTE_PLACEHOLDERS:
        return None
    return text


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


def parse_datetime(value: Any) -> datetime | None:
    """Parse the date formats these feeds actually emit."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (int, float)):
        try:
            # Heuristic: values beyond year ~2286 in seconds are milliseconds.
            seconds = float(value)
            if seconds > 1e11:
                seconds /= 1000.0
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        return parse_datetime(int(text))

    # Relative phrasings used by scraped aggregator feeds.
    relative = re.match(
        r"(\d+)\s*(minute|hour|day|week|month)s?\s*ago", text, re.IGNORECASE
    )
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        delta = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "month": timedelta(days=30 * amount),
        }[unit]
        return datetime.now(timezone.utc) - delta
    if re.fullmatch(r"(just\s*now|today|new)", text, re.IGNORECASE):
        return datetime.now(timezone.utc)
    if re.fullmatch(r"yesterday", text, re.IGNORECASE):
        return datetime.now(timezone.utc) - timedelta(days=1)

    cleaned = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
        "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%b %d, %Y", "%d %b %Y",
        "%B %d, %Y", "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
