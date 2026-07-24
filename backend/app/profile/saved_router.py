"""Saved-jobs endpoints (M10): save, unsave, list ids, and the dashboard.

All are session-gated and scoped to the current user. Saving is idempotent
and never mutates search results; the dashboard (`GET /saved-jobs`) returns
each saved job with a live match computed against the user's most recently
reviewed profile.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.accounts.deps import require_user
from app.accounts.models import User
from app.core.db import get_db
from app.profile.saved import (
    JobNotFound,
    build_dashboard,
    save_job,
    saved_job_ids,
    unsave_job,
)
from app.profile.schemas import (
    SavedJobIdsResponse,
    SavedJobRequest,
    SavedJobsResponse,
)

router = APIRouter(prefix="/saved-jobs", tags=["saved-jobs"])


@router.get("", response_model=SavedJobsResponse)
def get_saved_jobs(
    db: Session = Depends(get_db), user: User = Depends(require_user)
) -> SavedJobsResponse:
    """The saved-jobs dashboard: each saved job with a live match score,
    matched/missing skills, and reasons drawn from the user's most recently
    reviewed profile."""
    return build_dashboard(db, user)


@router.get("/ids", response_model=SavedJobIdsResponse)
def get_saved_job_ids(
    db: Session = Depends(get_db), user: User = Depends(require_user)
) -> SavedJobIdsResponse:
    """The ids the user has saved — for rendering the Save button's state in
    search and job detail. Saved jobs stay in search; this only toggles UI."""
    return saved_job_ids(db, user)


@router.post("", response_model=SavedJobIdsResponse, status_code=201)
def create_saved_job(
    payload: SavedJobRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> SavedJobIdsResponse:
    """Save a job. Idempotent; returns the updated saved-id set."""
    try:
        save_job(db, user, payload.job_id)
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return saved_job_ids(db, user)


@router.delete("/{job_id}", status_code=204)
def delete_saved_job(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)
) -> None:
    """Unsave a job. Idempotent."""
    unsave_job(db, user, job_id)
