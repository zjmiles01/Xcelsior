"""API schemas for resume upload and profile review/edit (M7).

The update payload is a full-document PUT: the client sends the entire
edited profile and the server reconciles — an item with `id` keeps (and
may update) the existing row, an item without `id` is created as
`origin: manual`, and any existing row missing from the list is deleted.
One request, one transaction: exactly what a review screen's Save needs.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.catalog.filters import JobFilters
from app.catalog.schemas import JobLocationOut, SalaryOut


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size: int
    page_count: int | None
    parser_name: str | None
    parser_version: int | None
    uploaded_at: datetime
    # The normalized text every evidence offset indexes into; the review
    # UI renders spans out of it.
    extracted_text: str | None


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    technology_id: int | None
    label: str
    confidence: float | None
    occurrences: int
    evidence_snippet: str | None
    evidence_start: int | None
    origin: str


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str | None
    title_raw: str
    canonical_title_id: int | None
    level: str | None
    start_date: date | None
    end_date: date | None
    is_current: bool
    summary: str | None
    evidence_start: int | None
    evidence_end: int | None
    position: int
    origin: str


class EducationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution: str | None
    degree_raw: str | None
    degree_level: str | None
    field_of_study: str | None
    start_year: int | None
    end_year: int | None
    evidence_start: int | None
    evidence_end: int | None
    position: int
    origin: str


class ProfileDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume: ResumeOut
    full_name: str | None
    email: str | None
    phone: str | None
    extractor_version: int
    extracted_at: datetime
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    skills: list[SkillOut]
    experiences: list[ExperienceOut]
    education: list[EducationOut]


class ProfileListItem(BaseModel):
    id: int
    full_name: str | None
    email: str | None
    filename: str
    uploaded_at: datetime
    reviewed_at: datetime | None
    skill_count: int
    experience_count: int


class ProfileListResponse(BaseModel):
    items: list[ProfileListItem]


class SkillIn(BaseModel):
    """Keep an existing skill (id) or add a manual one (label, optionally
    mapped to a taxonomy slug so it stays matchable)."""

    id: int | None = None
    label: str | None = None
    technology_slug: str | None = None

    @model_validator(mode="after")
    def _id_or_label(self) -> "SkillIn":
        if self.id is None and not (self.label or self.technology_slug):
            raise ValueError("a new skill needs a label or a technology_slug")
        return self


class ExperienceIn(BaseModel):
    id: int | None = None
    company: str | None = None
    title_raw: str
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    summary: str | None = None

    @model_validator(mode="after")
    def _current_has_no_end(self) -> "ExperienceIn":
        if self.is_current and self.end_date is not None:
            raise ValueError("a current position cannot have an end_date")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date is after end_date")
        return self


class EducationIn(BaseModel):
    id: int | None = None
    institution: str | None = None
    degree_raw: str | None = None
    field_of_study: str | None = None
    start_year: int | None = None
    end_year: int | None = None

    @model_validator(mode="after")
    def _something_present(self) -> "EducationIn":
        if self.id is None and not (self.institution or self.degree_raw):
            raise ValueError("a new education entry needs an institution or a degree")
        return self


class ProfileUpdate(BaseModel):
    """Full-document replacement. `reviewed` is the document state, not an
    event: true sets reviewed_at (now, if not already set), false clears
    it — editing after review naturally un-reviews by sending false."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    reviewed: bool = False
    skills: list[SkillIn]
    experiences: list[ExperienceIn]
    education: list[EducationIn]


# ── Job matching (M9) ────────────────────────────────────────────────────
#
# The response is deliberately verbose: the whole point of matching is that
# a user can see *why* a job ranks where it does. Every score carries the
# component breakdown that produced it, the matched/missing skills, and the
# title/experience alignment behind it.


class MatchWeights(BaseModel):
    """The nominal component weights, surfaced so the ranking is legible."""

    skills: float
    title: float
    experience: float


class ScoreComponentOut(BaseModel):
    key: str  # skills | title | experience
    label: str
    weight: float  # nominal weight
    score: float | None  # 0..1, null when the component does not apply
    applicable: bool
    contribution: float  # this component's share of the final 0..100 score
    detail: str


class MatchSkillOut(BaseModel):
    slug: str
    name: str
    requirement_level: str  # required | preferred | mentioned


class TitleAlignmentOut(BaseModel):
    matched: bool | None  # null when there is no canonical family to compare
    job_title: str | None
    job_title_slug: str | None


class ExperienceAlignmentOut(BaseModel):
    verdict: str  # meets | exceeds | below | unknown | unspecified
    candidate_level: str | None
    candidate_years: float | None
    job_level: str | None
    job_years: int | None


class MatchJobSummary(BaseModel):
    """Enough of a job to render and link a match card. Deliberately no
    description: matches never serve posting text — the job-detail endpoint
    does, under the display-policy gate."""

    id: int
    title_raw: str
    canonical_title: str | None
    canonical_title_slug: str | None
    company_name: str
    locations: list[JobLocationOut]
    arrangement: str | None
    experience_level: str | None
    salary: SalaryOut
    posted_at: datetime | None
    apply_url: str | None


class JobMatchOut(BaseModel):
    job: MatchJobSummary
    score: int  # 0..100
    components: list[ScoreComponentOut]
    matched_skills: list[MatchSkillOut]
    missing_skills: list[MatchSkillOut]
    title: TitleAlignmentOut
    experience: ExperienceAlignmentOut
    reasons: list[str]


class MatchProfileSummary(BaseModel):
    """The candidate side of the match, for context and honesty: how many
    skills actually join the taxonomy, which title families were matched
    on, and the derived seniority the experience component used."""

    id: int
    full_name: str | None
    reviewed_at: datetime
    matched_skill_count: int  # skills mapped to a taxonomy technology
    unmapped_skill_count: int  # manual/unknown skills that cannot match jobs
    title_families: list[str]
    experience_level: str | None
    years_experience: float | None
    highest_degree: str | None


class ProfileMatchesResponse(BaseModel):
    profile: MatchProfileSummary
    filters: JobFilters  # the scope the matches were drawn from
    weights: MatchWeights
    total_active_jobs: int  # size of the predicate pool (the honest denominator)
    matched_jobs: int  # jobs sharing a skill or title signal (before the limit)
    returned: int
    matches: list[JobMatchOut]
    computed_at: datetime


# ── Saved jobs (M10) ─────────────────────────────────────────────────────
#
# A saved job is a persistent, user-owned bookmark whose match information is
# recomputed live against the user's most recently reviewed profile — never a
# frozen score. The dashboard reuses the M9 explanation shapes so a saved-job
# card carries the same auditable breakdown the matcher does.


class SavedJobRequest(BaseModel):
    job_id: int


class SavedJobMatch(BaseModel):
    """The M9 match for a saved job, minus the job (which the card already
    holds). Present only when the user has a reviewed profile to match
    against; `score` may be 0 for a saved job with no overlap — a saved job
    is always explained, never dropped."""

    score: int  # 0..100
    components: list[ScoreComponentOut]
    matched_skills: list[MatchSkillOut]
    missing_skills: list[MatchSkillOut]
    title: TitleAlignmentOut
    experience: ExperienceAlignmentOut
    reasons: list[str]


class SavedJobOut(BaseModel):
    job: MatchJobSummary
    saved_at: datetime
    match: SavedJobMatch | None  # null when the user has no reviewed profile


class SavedJobsResponse(BaseModel):
    # The reviewed profile the match info reflects, plus its id so the card
    # can deep-link to the full M9 explanation. Both null when the user has
    # not reviewed a profile yet (saved jobs still list, without scores).
    profile: MatchProfileSummary | None
    profile_id: int | None
    items: list[SavedJobOut]


class SavedJobIdsResponse(BaseModel):
    """The ids the current user has saved — the search/detail UIs use this to
    render the Save button's saved state without leaking anything else."""

    job_ids: list[int]
