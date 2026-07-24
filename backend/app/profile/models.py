"""Resume intelligence data model (M7, ADR-005).

Mirrors the market-data layering: `resumes` is the raw layer (uploaded
bytes + extracted text, append-only apart from user deletion of their own
data), `candidate_profiles` and its fact tables are the canonical layer —
extracted deterministically, then owned by the user through review/edit.

Every extracted fact carries evidence offsets into `resumes.extracted_text`
(same traceability contract as `job_technologies`). Matching-readiness is
structural, not aspirational: `profile_skills.technology_id` joins
`job_technologies.technology_id`, and `profile_experiences.
canonical_title_id` joins `jobs.canonical_title_id`, so future job
matching is a query, not a migration.
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Resume(Base):
    """Uploaded resume: original bytes plus the deterministic text
    extraction they produced. `parser_version` plays the role
    `extractor_version` plays for jobs — bumping it and re-parsing is how
    a parser fix reaches stored resumes, without re-upload.

    Owned by exactly one user (M10). `content_hash` is unique *per user*,
    not globally: identical bytes re-uploaded by the same user are
    idempotent, but two different users uploading the same resume are two
    independent private documents."""

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_resumes_user_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str]
    content_type: Mapped[str]
    file_size: Mapped[int]
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    content_hash: Mapped[str]  # sha256 hex of file_bytes; unique per user

    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    parser_name: Mapped[str | None]
    parser_version: Mapped[int | None]

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CandidateProfile(Base):
    """One structured profile per resume. `reviewed_at` is the gate every
    future consumer (matching, recommendations) must respect: NULL means
    the user has not confirmed the extraction yet."""

    __tablename__ = "candidate_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), unique=True)

    full_name: Mapped[str | None]
    email: Mapped[str | None]
    phone: Mapped[str | None]

    extractor_version: Mapped[int]
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    resume: Mapped[Resume] = relationship(lazy="joined")
    skills: Mapped[list["ProfileSkill"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    experiences: Mapped[list["ProfileExperience"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProfileExperience.position",
    )
    education: Mapped[list["ProfileEducation"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProfileEducation.position",
    )


class ProfileSkill(Base):
    """A skill on the profile. `technology_id` is set when the skill maps
    into the shared taxonomy (the join key job matching will use); a
    user-added skill outside the taxonomy keeps only its label. Evidence
    fields are NULL exactly when origin is manual."""

    __tablename__ = "profile_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)
    technology_id: Mapped[int | None] = mapped_column(ForeignKey("technologies.id"), index=True)

    label: Mapped[str]
    confidence: Mapped[float | None] = mapped_column(Float)
    occurrences: Mapped[int] = mapped_column(default=1)
    evidence_snippet: Mapped[str | None] = mapped_column(Text)
    evidence_start: Mapped[int | None]
    origin: Mapped[str] = mapped_column(default="extracted")  # extracted | manual

    profile: Mapped[CandidateProfile] = relationship(back_populates="skills")


class ProfileExperience(Base):
    """One work-history entry. `title_raw` is what the resume said;
    `canonical_title_id` + `level` come from the same title
    canonicalization jobs use. Dates are month-precision at best on real
    resumes, stored as the first of the month."""

    __tablename__ = "profile_experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)

    company: Mapped[str | None]
    title_raw: Mapped[str]
    canonical_title_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_titles.id"), index=True
    )
    level: Mapped[str | None]  # entry | mid | senior | staff_plus

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(default=False)

    summary: Mapped[str | None] = mapped_column(Text)  # the entry's own bullet text
    evidence_start: Mapped[int | None]
    evidence_end: Mapped[int | None]
    position: Mapped[int] = mapped_column(default=0)  # resume order, top first
    origin: Mapped[str] = mapped_column(default="extracted")  # extracted | manual

    profile: Mapped[CandidateProfile] = relationship(back_populates="experiences")


class ProfileEducation(Base):
    """One education entry. Degree kept in both as-printed and normalized
    forms (same raw-plus-normalized pattern as salary on jobs)."""

    __tablename__ = "profile_education"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), index=True)

    institution: Mapped[str | None]
    degree_raw: Mapped[str | None]
    degree_level: Mapped[str | None]  # associate | bachelor | master | doctorate | other
    field_of_study: Mapped[str | None]

    start_year: Mapped[int | None]
    end_year: Mapped[int | None]

    evidence_start: Mapped[int | None]
    evidence_end: Mapped[int | None]
    position: Mapped[int] = mapped_column(default=0)
    origin: Mapped[str] = mapped_column(default="extracted")  # extracted | manual

    profile: Mapped[CandidateProfile] = relationship(back_populates="education")


class SavedJob(Base):
    """A job a user has saved (M10). Deliberately thin: it records only the
    ownership edge (user + job + when), never a copy of the job or a frozen
    match score. The saved-jobs dashboard recomputes the match live against
    the user's most recently reviewed profile, so the numbers a user sees
    always reflect their current profile — a bookmark that stays honest as
    the profile evolves, not a stale snapshot.

    Unique on (user_id, job_id): saving an already-saved job is idempotent.
    Saving does not remove the job from search — it only records the edge;
    search reflects the saved state by asking which ids are saved."""

    __tablename__ = "saved_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_saved_jobs_user_job"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
