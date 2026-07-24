"""Saved jobs: a persistent, per-user bookmark with a live match (M10).

Two ideas the milestone insists on:

1. **Saving does not remove a job from search.** `save_job` only records an
   ownership edge; the search/detail UIs reflect saved state by asking for
   the set of saved ids (`saved_job_ids`) and toggling a button, never by
   hiding the row.
2. **The dashboard match is always live.** `build_dashboard` recomputes each
   saved job's match against the user's *most recently reviewed* profile
   (`current_reviewed_profile`), reusing the exact M9 scoring
   (`score_job`) — so the score, matched skills, and gaps a user sees today
   reflect the profile they have today, not a snapshot frozen at save time.

Everything here is scoped to the authenticated user; a `job_id` is validated
to exist, but ownership is never taken from the request.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import User
from app.catalog.models import Job
from app.profile.matching import _load_job_summaries as load_job_summaries  # reused shaper
from app.profile.matching import _profile_summary as profile_summary  # reused shaper
from app.profile.matching import (
    build_candidate_facts,
    load_job_facts_by_ids,
    score_job,
)
from app.profile.models import CandidateProfile, SavedJob
from app.profile.schemas import (
    ExperienceAlignmentOut,
    MatchSkillOut,
    SavedJobIdsResponse,
    SavedJobMatch,
    SavedJobOut,
    SavedJobsResponse,
    ScoreComponentOut,
    TitleAlignmentOut,
)


class JobNotFound(Exception):
    """Save request for a job id that does not exist."""


def save_job(db: Session, user: User, job_id: int) -> SavedJob:
    """Save a job for the user. Idempotent: saving an already-saved job
    returns the existing edge. A non-existent job id is a JobNotFound."""
    if db.get(Job, job_id) is None:
        raise JobNotFound(job_id)
    existing = db.scalar(
        select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
    )
    if existing is not None:
        return existing
    saved = SavedJob(user_id=user.id, job_id=job_id)
    db.add(saved)
    db.commit()
    return saved


def unsave_job(db: Session, user: User, job_id: int) -> None:
    """Remove a saved job. Idempotent — unsaving a job that is not saved is
    a no-op, so the button is safe to double-click."""
    saved = db.scalar(
        select(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
    )
    if saved is not None:
        db.delete(saved)
        db.commit()


def saved_job_ids(db: Session, user: User) -> SavedJobIdsResponse:
    ids = list(
        db.scalars(select(SavedJob.job_id).where(SavedJob.user_id == user.id)).all()
    )
    return SavedJobIdsResponse(job_ids=ids)


def current_reviewed_profile(db: Session, user: User) -> CandidateProfile | None:
    """The user's most recently reviewed profile, or None. Matching only ever
    reads a reviewed profile (invariant #9), and 'most recent' keeps the
    dashboard reflecting the latest profile the user confirmed."""
    return db.scalar(
        select(CandidateProfile)
        .where(
            CandidateProfile.user_id == user.id,
            CandidateProfile.reviewed_at.is_not(None),
        )
        .order_by(CandidateProfile.reviewed_at.desc())
        .limit(1)
    )


def build_dashboard(db: Session, user: User) -> SavedJobsResponse:
    """The saved-jobs dashboard: every saved job with its live match info."""
    saved = db.scalars(
        select(SavedJob)
        .where(SavedJob.user_id == user.id)
        .order_by(SavedJob.created_at.desc(), SavedJob.id.desc())
    ).all()
    job_ids = [s.job_id for s in saved]

    facts = load_job_facts_by_ids(db, job_ids)
    summaries = load_job_summaries(db, job_ids, facts)

    profile = current_reviewed_profile(db, user)
    cand = None
    profile_out = None
    if profile is not None:
        cand = build_candidate_facts(profile, datetime.now(UTC).date())
        profile_out = profile_summary(db, profile, cand)

    items: list[SavedJobOut] = []
    for edge in saved:
        summary = summaries.get(edge.job_id)
        if summary is None:  # job vanished mid-request; skip defensively
            continue
        match = None
        if cand is not None and edge.job_id in facts:
            result = score_job(cand, facts[edge.job_id], require_signal=False)
            if result is not None:
                match = _to_saved_match(result, summary)
        items.append(SavedJobOut(job=summary, saved_at=edge.created_at, match=match))

    return SavedJobsResponse(
        profile=profile_out,
        profile_id=profile.id if profile is not None else None,
        items=items,
    )


def _to_saved_match(result, summary) -> SavedJobMatch:
    return SavedJobMatch(
        score=result.score,
        components=[
            ScoreComponentOut(
                key=c.key,
                label=c.label,
                weight=c.weight,
                score=c.score,
                applicable=c.applicable,
                contribution=c.contribution,
                detail=c.detail,
            )
            for c in result.components
        ],
        matched_skills=[
            MatchSkillOut(slug=t.slug, name=t.name, requirement_level=t.requirement_level)
            for t in result.matched_skills
        ],
        missing_skills=[
            MatchSkillOut(slug=t.slug, name=t.name, requirement_level=t.requirement_level)
            for t in result.missing_skills
        ],
        title=TitleAlignmentOut(
            matched=result.title_matched,
            job_title=summary.canonical_title,
            job_title_slug=summary.canonical_title_slug,
        ),
        experience=ExperienceAlignmentOut(
            verdict=result.experience.verdict,
            candidate_level=result.experience.candidate_level,
            candidate_years=result.experience.candidate_years,
            job_level=result.experience.job_level,
            job_years=result.experience.job_years,
        ),
        reasons=list(result.reasons),
    )
