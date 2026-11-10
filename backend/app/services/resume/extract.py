"""Resume text extraction for PDF and DOCX.

PDFs are tried with pdfplumber first (better at preserving reading order in
multi-column layouts) and PyMuPDF second, which is faster and rescues files
pdfplumber chokes on. DOCX goes through python-docx, including tables and
headers, because resumes frequently hide the contact block in a table.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"

ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass
class ExtractionResult:
    text: str
    engine: str
    pages: int = 0
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


class UnsupportedResume(Exception):
    pass


def detect_kind(filename: str, head: bytes) -> str:
    """Determine the real file type from magic bytes, not just the extension."""
    suffix = Path(filename).suffix.lower()
    if head.startswith(PDF_MAGIC):
        return "pdf"
    if head.startswith(DOCX_MAGIC):
        # .docx is a zip; legacy .doc is OLE2 and not supported.
        if suffix == ".docx":
            return "docx"
        raise UnsupportedResume(
            "That looks like a zip-based Office file but not a .docx. Please upload a PDF or DOCX."
        )
    if suffix == ".pdf":
        raise UnsupportedResume("The file has a .pdf extension but is not a valid PDF.")
    if suffix == ".doc":
        raise UnsupportedResume(
            "Legacy .doc files are not supported. Save as .docx or export to PDF."
        )
    raise UnsupportedResume("Unsupported file type. Please upload a PDF or DOCX resume.")


def extract_text(path: Path, kind: str) -> ExtractionResult:
    if kind == "pdf":
        return _extract_pdf(path)
    if kind == "docx":
        return _extract_docx(path)
    raise UnsupportedResume(f"Cannot extract text from '{kind}'")


def _extract_pdf(path: Path) -> ExtractionResult:
    warnings: list[str] = []

    try:
        import pdfplumber

        chunks: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            pages = len(pdf.pages)
            for page in pdf.pages:
                chunks.append(page.extract_text(x_tolerance=1.5, y_tolerance=2.5) or "")
        text = _clean("\n".join(chunks))
        if len(text) >= 200:
            return ExtractionResult(text=text, engine="pdfplumber", pages=pages, warnings=warnings)
        warnings.append("pdfplumber returned little text; retried with PyMuPDF.")
    except Exception as exc:
        logger.info("pdfplumber failed on %s: %s", path.name, exc)
        warnings.append("pdfplumber could not read the PDF; retried with PyMuPDF.")

    try:
        import fitz  # PyMuPDF

        with fitz.open(str(path)) as doc:
            pages = doc.page_count
            text = _clean("\n".join(page.get_text("text") for page in doc))
        if len(text) < 100:
            warnings.append(
                "Very little text was recovered — this may be a scanned or image-only resume. "
                "OCR is not enabled, so please upload a text-based PDF or fill the form manually."
            )
        return ExtractionResult(text=text, engine="pymupdf", pages=pages, warnings=warnings)
    except Exception as exc:
        logger.warning("PyMuPDF failed on %s: %s", path.name, exc)
        raise UnsupportedResume(
            "The PDF could not be read. It may be corrupted or password-protected."
        ) from exc


def _extract_docx(path: Path) -> ExtractionResult:
    try:
        import docx
    except Exception as exc:  # pragma: no cover
        raise UnsupportedResume("DOCX support is unavailable on the server.") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise UnsupportedResume(
            "The DOCX file could not be opened. It may be corrupted."
        ) from exc

    parts: list[str] = []

    for section in document.sections:
        for container in (section.header, section.footer):
            for para in container.paragraphs:
                if para.text.strip():
                    parts.append(para.text)

    for para in document.paragraphs:
        if para.text.strip():
            parts.append(para.text)

    # Resumes often put contact details or skill grids in tables.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            # Repeated merged cells come back duplicated; collapse them.
            deduped: list[str] = []
            for cell in cells:
                if cell and (not deduped or deduped[-1] != cell):
                    deduped.append(cell)
            if deduped:
                parts.append(" | ".join(deduped))

    text = _clean("\n".join(parts))
    warnings: list[str] = []
    if len(text) < 100:
        warnings.append("Very little text was found in the document.")
    return ExtractionResult(text=text, engine="python-docx", pages=1, warnings=warnings)


_BULLET_CHARS = "•◦▪●‣·∙–—*"


def _clean(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("​", "")
    # Repair words split by a line-wrapping hyphen.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Normalise bullets to "- " so segmentation can rely on them.
    text = re.sub(rf"^[\s]*[{re.escape(_BULLET_CHARS)}]+[\s]*", "- ", text, flags=re.MULTILINE)
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
