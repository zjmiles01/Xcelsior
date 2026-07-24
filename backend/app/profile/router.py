"""Resume upload and candidate-profile review/edit endpoints (M7, M10).

These handle user-supplied personal data (name, email, phone, resume
bytes). In M10 they moved from a single shared bearer token to per-user
ownership: every route requires an authenticated session (`require_user`)
and is scoped to `user.id`. Ownership is always taken from the session,
never from the path — a profile id belonging to another user is a 404, not
another user's data. Manipulating the URL, the body, or the request cannot
reach a row you do not own.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.deps import require_user
from app.accounts.models import User
from app.catalog.deps import filters_from_query
from app.catalog.filters import JobFilters
from app.core.db import get_db
from app.profile.matching import compute_matches
from app.profile.models import CandidateProfile, Resume
from app.profile.pdf import EncryptedPdfError, NotAPdfError, NoTextError
from app.profile.schemas import (
    ProfileDetail,
    ProfileListItem,
    ProfileListResponse,
    ProfileMatchesResponse,
    ProfileUpdate,
)
from app.profile.service import (
    MAX_RESUME_BYTES,
    UnknownProfileItem,
    create_resume,
    delete_profile,
    extract_profile,
    update_profile,
)

router = APIRouter(tags=["profiles"])


@router.post("/resumes", response_model=ProfileDetail, status_code=201)
def upload_resume(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> CandidateProfile:
    """Upload a PDF resume: parse, extract, and return the structured
    profile in one synchronous call (the pipeline is deterministic rules,
    well under a second). The resume and profile are owned by the uploading
    user. Re-uploading identical bytes is idempotent and returns the user's
    existing profile untouched — edits survive."""
    data = file.file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume exceeds the 5 MB limit")

    try:
        resume, created = create_resume(
            db, user.id, file.filename or "resume.pdf",
            file.content_type or "application/pdf", data
        )
    except NotAPdfError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except (EncryptedPdfError, NoTextError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not created:
        existing = db.scalar(
            select(CandidateProfile).where(CandidateProfile.resume_id == resume.id)
        )
        if existing is not None:
            return existing
    return extract_profile(db, resume)


@router.get("/profiles", response_model=ProfileListResponse)
def list_profiles(
    db: Session = Depends(get_db), user: User = Depends(require_user)
) -> ProfileListResponse:
    """The current user's profiles only — the query is scoped to the
    session, so it can never surface another account's data."""
    profiles = db.scalars(
        select(CandidateProfile)
        .where(CandidateProfile.user_id == user.id)
        .order_by(CandidateProfile.id.desc())
    ).all()
    return ProfileListResponse(
        items=[
            ProfileListItem(
                id=p.id,
                full_name=p.full_name,
                email=p.email,
                filename=p.resume.filename,
                uploaded_at=p.resume.uploaded_at,
                reviewed_at=p.reviewed_at,
                skill_count=len(p.skills),
                experience_count=len(p.experiences),
            )
            for p in profiles
        ]
    )


@router.get("/profiles/{profile_id}", response_model=ProfileDetail)
def get_profile(
    profile_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> CandidateProfile:
    return _get_owned_or_404(db, user, profile_id)


@router.put("/profiles/{profile_id}", response_model=ProfileDetail)
def put_profile(
    profile_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> CandidateProfile:
    """Full-document reconcile: id = keep/update, no id = create as
    manual, absent = delete. One transaction — the review screen's Save."""
    profile = _get_owned_or_404(db, user, profile_id)
    try:
        return update_profile(db, profile, payload)
    except UnknownProfileItem as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/profiles/{profile_id}/matches", response_model=ProfileMatchesResponse)
def profile_matches(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    filters: JobFilters = Depends(filters_from_query),
    limit: int = Query(50, ge=1, le=100),
) -> ProfileMatchesResponse:
    """Rank active jobs against this profile (M9). The profile must belong to
    the signed-in user (404 otherwise) and be reviewed (409 otherwise —
    invariant #9: an unreviewed extraction is not usable). Accepts the same
    `JobFilters` the market surface does; the candidate job pool is the
    shared predicate, so the counts agree with search."""
    profile = _get_owned_or_404(db, user, profile_id)
    if profile.reviewed_at is None:
        raise HTTPException(
            status_code=409,
            detail="Profile must be reviewed before it can be matched to jobs",
        )
    return compute_matches(db, profile, filters, limit)


@router.post("/profiles/{profile_id}/reextract", response_model=ProfileDetail)
def reextract_profile(
    profile_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> CandidateProfile:
    """Rebuild the profile from the stored resume text, discarding all
    edits — an explicit user action (ADR-005), useful after taxonomy
    growth. The resume bytes and text are untouched."""
    profile = _get_owned_or_404(db, user, profile_id)
    resume = db.get(Resume, profile.resume_id)
    assert resume is not None
    return extract_profile(db, resume)


@router.delete("/profiles/{profile_id}", status_code=204)
def remove_profile(
    profile_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> None:
    """Delete the profile and its uploaded resume (user-owned data)."""
    delete_profile(db, _get_owned_or_404(db, user, profile_id))


def _get_owned_or_404(db: Session, user: User, profile_id: int) -> CandidateProfile:
    """Fetch a profile only if it belongs to the current user. A missing
    profile and one owned by someone else are the *same* 404 — the API never
    reveals that another user's profile exists."""
    profile = db.get(CandidateProfile, profile_id)
    if profile is None or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile
