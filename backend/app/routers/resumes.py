from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RateLimiter, require_owned
from app.core.errors import BadRequest, NotFound, UnprocessableUpload
from app.models import CandidateProfile, ParsedResume, Resume
from app.schemas import (
    ParsedResumeOut,
    ParsedResumeUpdate,
    ProfileOut,
    ResumeOut,
)
from app.services.resume.extract import ALLOWED, UnsupportedResume, detect_kind
from app.services.resume.pipeline import (
    derive_profile_facts,
    embed_profile,
    process_resume_file,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["resumes"])

_limit = RateLimiter(settings.upload_rate_limit_per_minute, "upload")
CHUNK = 64 * 1024


@router.post("", response_model=ParsedResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    _: None = Depends(_limit),
) -> ParsedResumeOut:
    if not file.filename:
        raise UnprocessableUpload("No filename supplied")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED:
        raise UnprocessableUpload(
            f"Unsupported file type '{suffix or 'unknown'}'. Upload a PDF or DOCX."
        )

    # Stream to disk under a generated name, enforcing the size cap as we go so
    # a large upload can't be used to exhaust disk.
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = settings.upload_dir / stored_name
    digest = hashlib.sha256()
    size = 0
    head = b""

    try:
        with stored_path.open("wb") as handle:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UnprocessableUpload(
                        f"File is larger than "
                        f"{settings.max_upload_bytes // (1024 * 1024)} MB."
                    )
                if not head:
                    head = chunk[:8]
                digest.update(chunk)
                handle.write(chunk)

        if size == 0:
            raise UnprocessableUpload("The uploaded file is empty.")

        # Trust magic bytes over the extension and the client's content type.
        kind = detect_kind(file.filename, head)

        resume = Resume(
            user_id=user.id,
            original_filename=file.filename[:500],
            stored_path=str(stored_path),
            content_type=ALLOWED[suffix],
            size_bytes=size,
            file_sha256=digest.hexdigest(),
            status="extracting",
        )
        db.add(resume)
        db.commit()
        db.refresh(resume)

    except UnsupportedResume as exc:
        stored_path.unlink(missing_ok=True)
        raise UnprocessableUpload(str(exc)) from exc
    except UnprocessableUpload:
        stored_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        logger.exception("Upload failed")
        raise UnprocessableUpload("The file could not be stored.") from exc

    # Parse inline: a resume is small and the user is waiting on the review
    # screen. Discovery, which is slow, is the part that gets queued.
    try:
        result = await process_resume_file(stored_path, kind)
    except UnsupportedResume as exc:
        resume.status = "failed"
        resume.error_message = str(exc)
        db.commit()
        raise UnprocessableUpload(str(exc)) from exc
    except Exception as exc:
        resume.status = "failed"
        resume.error_message = "Parsing failed unexpectedly."
        db.commit()
        logger.exception("Resume parsing failed for %s", resume.id)
        raise UnprocessableUpload(
            "The resume could not be parsed. Try a different file or export it as a PDF."
        ) from exc

    resume.raw_text = result.get("raw_text") or ""
    resume.extraction_engine = result.get("engine")
    resume.status = "awaiting_review"

    parsed = ParsedResume(
        resume_id=resume.id,
        structuring_mode=result["structuring_mode"],
        payload=result["payload"],
        field_confidence=result["field_confidence"],
        warnings=result["warnings"],
    )
    db.add(parsed)
    db.commit()
    db.refresh(parsed)

    return ParsedResumeOut(
        resume_id=resume.id,
        status=resume.status,
        structuring_mode=parsed.structuring_mode,
        payload=parsed.payload,
        field_confidence=parsed.field_confidence,
        warnings=parsed.warnings,
        derived=result["derived"],
        edited_by_user=False,
    )


@router.get("", response_model=list[ResumeOut])
def list_resumes(user: CurrentUser, db: DbSession) -> list[ResumeOut]:
    rows = db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.uploaded_at.desc())
    ).all()
    return [ResumeOut.model_validate(row) for row in rows]


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeOut:
    return ResumeOut.model_validate(require_owned(db, Resume, resume_id, user))


@router.get("/{resume_id}/parsed", response_model=ParsedResumeOut)
def get_parsed(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ParsedResumeOut:
    resume = require_owned(db, Resume, resume_id, user)
    parsed = db.scalars(
        select(ParsedResume).where(ParsedResume.resume_id == resume.id)
    ).first()
    if parsed is None:
        raise NotFound("This resume has not been parsed yet")

    return ParsedResumeOut(
        resume_id=resume.id,
        status=resume.status,
        structuring_mode=parsed.structuring_mode,
        payload=parsed.payload,
        field_confidence=parsed.field_confidence,
        warnings=parsed.warnings,
        derived=derive_profile_facts(parsed.payload),
        edited_by_user=parsed.edited_by_user,
    )


@router.put("/{resume_id}/parsed", response_model=ParsedResumeOut)
def update_parsed(
    resume_id: uuid.UUID,
    payload: ParsedResumeUpdate,
    user: CurrentUser,
    db: DbSession,
) -> ParsedResumeOut:
    """Persist the user's edits to the extracted data before confirmation."""
    resume = require_owned(db, Resume, resume_id, user)
    parsed = db.scalars(
        select(ParsedResume).where(ParsedResume.resume_id == resume.id)
    ).first()
    if parsed is None:
        raise NotFound("This resume has not been parsed yet")

    from app.services.resume.pipeline import _normalise_payload

    merged = {**parsed.payload, **payload.payload}
    parsed.payload = _normalise_payload(merged)
    parsed.edited_by_user = True
    db.commit()
    db.refresh(parsed)

    return ParsedResumeOut(
        resume_id=resume.id,
        status=resume.status,
        structuring_mode=parsed.structuring_mode,
        payload=parsed.payload,
        field_confidence=parsed.field_confidence,
        warnings=parsed.warnings,
        derived=derive_profile_facts(parsed.payload),
        edited_by_user=True,
    )


@router.post("/{resume_id}/confirm", response_model=ProfileOut)
def confirm_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProfileOut:
    """Promote the reviewed extraction into the active candidate profile."""
    resume = require_owned(db, Resume, resume_id, user)
    parsed = db.scalars(
        select(ParsedResume).where(ParsedResume.resume_id == resume.id)
    ).first()
    if parsed is None:
        raise NotFound("This resume has not been parsed yet")

    payload = parsed.payload
    contact = payload.get("contact") or {}
    if not (payload.get("skills") or {}).get("technical"):
        raise BadRequest(
            "Add at least one skill before confirming — matching needs something to work with.",
            code="no_skills",
        )

    derived = derive_profile_facts(payload)
    embedded = embed_profile(payload, derived)

    # Store per-item embeddings alongside their items so project/experience
    # relevance can be scored without recomputing them for every job.
    projects = [dict(p) for p in (payload.get("projects") or [])]
    for project, vector in zip(projects, embedded["project_embeddings"]):
        project["_embedding"] = vector
    experience = [dict(e) for e in (payload.get("experience") or [])]
    for entry, vector in zip(experience, embedded["experience_embeddings"]):
        entry["_embedding"] = vector

    previous = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id, CandidateProfile.is_active.is_(True))
        .order_by(CandidateProfile.revision.desc())
    ).all()
    revision = (previous[0].revision + 1) if previous else 1
    for row in previous:
        row.is_active = False

    profile = CandidateProfile(
        user_id=user.id,
        resume_id=resume.id,
        revision=revision,
        is_active=True,
        full_name=contact.get("name"),
        email=contact.get("email"),
        phone=contact.get("phone"),
        location=contact.get("location"),
        links=contact.get("links") or [],
        education=payload.get("education") or [],
        skills=(payload.get("skills") or {}).get("technical") or [],
        raw_skills=(payload.get("skills") or {}).get("raw") or [],
        programming_languages=payload.get("languages") or [],
        frameworks=payload.get("frameworks") or [],
        tools=payload.get("tools") or [],
        projects=projects,
        experience=experience,
        certifications=payload.get("certifications") or [],
        achievements=payload.get("achievements") or [],
        profile_text=embedded["profile_text"],
        embedding=embedded["embedding"],
        embedding_model=embedded["embedding_model"],
        **derived,
    )
    db.add(profile)
    resume.status = "confirmed"
    db.commit()
    db.refresh(profile)

    # A new profile revision invalidates every previous score.
    from app.services.matching.service import invalidate_matches

    invalidate_matches(db, user.id)
    db.commit()

    return ProfileOut.model_validate(profile)


@router.get("/{resume_id}/file")
def download_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FileResponse:
    resume = require_owned(db, Resume, resume_id, user)
    path = Path(resume.stored_path)
    if not path.is_file():
        raise NotFound("The stored file is no longer available")
    return FileResponse(
        path,
        media_type=resume.content_type,
        filename=resume.original_filename,
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    resume = require_owned(db, Resume, resume_id, user)
    Path(resume.stored_path).unlink(missing_ok=True)
    db.delete(resume)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
