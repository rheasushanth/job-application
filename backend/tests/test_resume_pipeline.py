"""Resume parsing tests.

These run the offline (heuristic) path, which is what executes without an API
key — so they pin the floor of extraction quality, not the best case.
"""

from __future__ import annotations

import asyncio

from tests.conftest import SAMPLE_RESUME_TEXT

from app.services.resume import heuristics
from app.services.resume.extract import UnsupportedResume, detect_kind, extract_text
from app.services.resume.pipeline import (
    build_profile_text,
    derive_profile_facts,
    embed_profile,
    process_resume_text,
)
from app.services.resume.segment import missing_sections, segment


def _parsed():
    return asyncio.run(process_resume_text(SAMPLE_RESUME_TEXT))


# --------------------------------------------------------------------------
# Segmentation
# --------------------------------------------------------------------------

def test_segmentation_finds_expected_sections():
    sections = segment(SAMPLE_RESUME_TEXT)
    for expected in ("education", "skills", "projects", "certifications", "achievements"):
        assert expected in sections, f"missing {expected}: got {list(sections)}"
    assert "internships" in sections or "experience" in sections


def test_missing_sections_reports_gaps():
    sparse = "JOHN DOE\njohn@example.com\n\nSKILLS\nPython, SQL\n"
    gaps = missing_sections(segment(sparse))
    assert "education" in gaps
    assert "skills" not in gaps


# --------------------------------------------------------------------------
# Contact extraction
# --------------------------------------------------------------------------

def test_contact_details_extracted():
    contact = _parsed()["payload"]["contact"]
    assert contact["email"] == "ananya.sharma@example.com"
    assert contact["name"] == "Ananya Sharma"
    assert contact["phone"] is not None
    assert "9876543210" in contact["phone"].replace(" ", "").replace("+91", "")
    assert any("github.com" in link for link in contact["links"])
    assert any("linkedin.com" in link for link in contact["links"])


def test_location_extracted():
    assert _parsed()["payload"]["contact"]["location"] == "Bengaluru, Karnataka"


# --------------------------------------------------------------------------
# Education
# --------------------------------------------------------------------------

def test_education_entries_and_levels():
    education = _parsed()["payload"]["education"]
    assert len(education) >= 1
    top = education[0]
    assert top["level"] == 3  # bachelor
    assert top["field"] == "Computer Science"
    assert top["institution"] is not None and "PES" in top["institution"]


def test_cgpa_captured():
    education = _parsed()["payload"]["education"]
    assert any(e.get("score") for e in education)


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------

def test_skills_canonicalised_into_buckets():
    payload = _parsed()["payload"]
    technical = payload["skills"]["technical"]
    for expected in ("Python", "Java", "Django", "FastAPI", "React", "Docker",
                     "PostgreSQL", "PyTorch", "scikit-learn", "AWS"):
        assert expected in technical, f"{expected} missing from {technical}"
    assert "Python" in payload["languages"]
    assert "Django" in payload["frameworks"]


def test_skills_deduplicated():
    technical = _parsed()["payload"]["skills"]["technical"]
    assert len(technical) == len(set(technical))


# --------------------------------------------------------------------------
# Projects and experience
# --------------------------------------------------------------------------

def test_projects_extracted_with_tech():
    projects = _parsed()["payload"]["projects"]
    assert len(projects) >= 3
    names = " ".join(p["name"] for p in projects)
    assert "Resume Ranking Engine" in names
    ranker = next(p for p in projects if "Resume Ranking" in p["name"])
    assert "FastAPI" in ranker["tech"]
    assert ranker["highlights"]


def test_internships_extracted_and_classified():
    experience = _parsed()["payload"]["experience"]
    assert len(experience) >= 2
    assert all(e["kind"] == "internship" for e in experience)
    zeta = next(e for e in experience if "Zeta" in (e.get("company") or ""))
    assert zeta["months"] == 7  # Jun 2025 - Dec 2025, inclusive


def test_durations_sum_into_derived_totals():
    derived = _parsed()["derived"]
    assert derived["internship_months"] >= 9
    assert derived["total_experience_months"] == derived["internship_months"]


# --------------------------------------------------------------------------
# Certifications / achievements
# --------------------------------------------------------------------------

def test_certifications_and_achievements():
    payload = _parsed()["payload"]
    certs = payload["certifications"]
    assert len(certs) >= 2
    assert any("AWS" in c["name"] for c in certs)
    assert any(c.get("year") == "2025" for c in certs)
    assert len(payload["achievements"]) >= 3


# --------------------------------------------------------------------------
# Seniority classification
# --------------------------------------------------------------------------

def test_pursuing_degree_classifies_as_student_or_intern():
    derived = _parsed()["derived"]
    assert derived["seniority"] in ("student", "intern")
    assert derived["seniority_signals"]
    assert derived["graduation_year"] == 2026
    assert derived["highest_degree_level"] == 3


def test_experienced_professional_classification():
    payload = {
        "education": [{"degree": "B.Tech", "level": 3, "end": "2019"}],
        "experience": [
            {"role": "Software Engineer", "kind": "job", "months": 40, "end": "present"},
        ],
    }
    assert derive_profile_facts(payload)["seniority"] == "experienced"


def test_entry_level_classification():
    payload = {
        "education": [{"degree": "B.Tech", "level": 3, "end": "2024"}],
        "experience": [{"role": "Junior Developer", "kind": "job", "months": 10}],
    }
    assert derive_profile_facts(payload)["seniority"] == "entry_level"


def test_fresher_classification_with_only_internships():
    payload = {
        "education": [{"degree": "B.Tech", "level": 3, "end": "2025"}],
        "experience": [{"role": "Intern", "kind": "internship", "months": 3, "end": "Aug 2025"}],
    }
    assert derive_profile_facts(payload)["seniority"] == "fresher"


# --------------------------------------------------------------------------
# Embedding / profile text
# --------------------------------------------------------------------------

def test_profile_text_and_embedding_built():
    parsed = _parsed()
    text = build_profile_text(parsed["payload"], parsed["derived"])
    assert "Python" in text
    assert "Resume Ranking Engine" in text

    embedded = embed_profile(parsed["payload"], parsed["derived"])
    assert len(embedded["embedding"]) > 0
    assert len(embedded["project_embeddings"]) == len(parsed["payload"]["projects"])
    assert embedded["embedding_model"]


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------

def test_empty_resume_degrades_gracefully():
    result = asyncio.run(process_resume_text(""))
    assert result["warnings"]
    assert result["payload"]["skills"]["technical"] == []
    assert result["derived"]["seniority"] == "fresher"


def test_minimal_resume_does_not_crash():
    result = asyncio.run(process_resume_text("Bob\nbob@example.com\nPython developer"))
    assert result["payload"]["contact"]["email"] == "bob@example.com"
    assert result["warnings"]


def test_detect_kind_uses_magic_bytes():
    assert detect_kind("cv.pdf", b"%PDF-1.7 rest") == "pdf"
    assert detect_kind("cv.docx", b"PK\x03\x04rest") == "docx"
    try:
        detect_kind("cv.pdf", b"not a pdf at all")
        assert False, "should have raised"
    except UnsupportedResume:
        pass
    try:
        detect_kind("cv.doc", b"\xd0\xcf\x11\xe0")
        assert False, "should have raised"
    except UnsupportedResume:
        pass


# --------------------------------------------------------------------------
# Real file round-trip
# --------------------------------------------------------------------------

def test_docx_round_trip(tmp_path):
    import docx

    document = docx.Document()
    for line in SAMPLE_RESUME_TEXT.split("\n"):
        document.add_paragraph(line)
    path = tmp_path / "resume.docx"
    document.save(str(path))

    extraction = extract_text(path, "docx")
    assert extraction.engine == "python-docx"
    assert "ANANYA SHARMA" in extraction.text

    parsed = asyncio.run(process_resume_text(extraction.text))
    assert parsed["payload"]["contact"]["email"] == "ananya.sharma@example.com"
    assert "Python" in parsed["payload"]["skills"]["technical"]
    assert len(parsed["payload"]["projects"]) >= 3


def test_pdf_round_trip(tmp_path):
    import fitz

    doc = fitz.open()
    lines = SAMPLE_RESUME_TEXT.split("\n")
    per_page = 48
    for start in range(0, len(lines), per_page):
        page = doc.new_page()
        page.insert_text(
            (56, 60), "\n".join(lines[start : start + per_page]), fontsize=9, fontname="helv"
        )
    path = tmp_path / "resume.pdf"
    doc.save(str(path))
    doc.close()

    extraction = extract_text(path, "pdf")
    assert extraction.text
    assert "ANANYA SHARMA" in extraction.text

    parsed = asyncio.run(process_resume_text(extraction.text))
    assert parsed["payload"]["contact"]["email"] == "ananya.sharma@example.com"
    assert "Python" in parsed["payload"]["skills"]["technical"]


def test_heuristic_date_parsing():
    months, start, end = heuristics._months_between("Jun 2025 - Dec 2025")
    assert months == 7
    months, _, _ = heuristics._months_between("May 2024 - Jul 2024")
    assert months == 3
    months, _, _ = heuristics._months_between("no dates here")
    assert months == 0
