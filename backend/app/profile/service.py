"""Resume → candidate profile pipeline (M7, ADR-005).

Two stages, versioned independently: `create_resume` stores bytes and
deterministic text (RESUME_PARSER_VERSION), `extract_profile` turns that
text into evidence-backed facts (RESUME_EXTRACTOR_VERSION) using the
*same* machinery the job pipeline uses — TechnologyMatcher over the
shared taxonomy for skills, canonicalize_title for titles — so a
candidate's facts and a job's facts speak the same vocabulary.

Re-extraction replaces the whole profile (facts and edits): it is only
ever an explicit user action, per ADR-005.
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.taxonomy_models import CanonicalTitle, Technology
from app.extraction.matcher import TechnologyMatcher
from app.extraction.service import load_index_from_db
from app.extraction.title import canonicalize_title
from app.profile.contact import extract_email, extract_name, extract_phone
from app.profile.education import match_degree_level, parse_education
from app.profile.experience import parse_experience
from app.profile.models import (
    CandidateProfile,
    ProfileEducation,
    ProfileExperience,
    ProfileSkill,
    Resume,
)
from app.profile.pdf import PARSER_NAME, RESUME_PARSER_VERSION, parse_pdf
from app.profile.schemas import ProfileUpdate
from app.profile.sections import detect_layout

RESUME_EXTRACTOR_VERSION = 1
MAX_RESUME_BYTES = 5 * 1024 * 1024


class UnknownProfileItem(Exception):
    """An update referenced an id or slug that isn't on this profile."""

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"unknown {field}: {value!r}")


def create_resume(
    db: Session, user_id: int, filename: str, content_type: str, data: bytes
) -> tuple[Resume, bool]:
    """Parse and store an uploaded resume for a user. Identical bytes from
    the same user are idempotent: the existing row comes back with
    created=False. The dedup key is scoped to the user, so one user's upload
    never collides with — or reveals the existence of — another's. Raises the
    typed pdf.ResumeParseError family on anything that can't become text."""
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(Resume).where(Resume.user_id == user_id, Resume.content_hash == digest)
    )
    if existing is not None:
        return existing, False

    parsed = parse_pdf(data)
    resume = Resume(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        file_size=len(data),
        file_bytes=data,
        content_hash=digest,
        extracted_text=parsed.text,
        page_count=parsed.page_count,
        parser_name=PARSER_NAME,
        parser_version=RESUME_PARSER_VERSION,
    )
    db.add(resume)
    db.commit()
    return resume, True


def extract_profile(db: Session, resume: Resume) -> CandidateProfile:
    """Build (or rebuild) the structured profile for a resume. Replaces
    any existing profile wholesale — including user edits — so callers
    must treat this as an explicit, user-confirmed action after the
    first extraction."""
    existing = db.scalar(
        select(CandidateProfile).where(CandidateProfile.resume_id == resume.id)
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    text = resume.extracted_text or ""
    layout = detect_layout(text)
    header_text = text[: layout.header_end]

    index = load_index_from_db(db)
    tech_ids = dict(db.execute(select(Technology.slug, Technology.id)).all())
    tech_names = dict(db.execute(select(Technology.slug, Technology.name)).all())
    title_ids = dict(db.execute(select(CanonicalTitle.slug, CanonicalTitle.id)).all())

    profile = CandidateProfile(
        user_id=resume.user_id,
        resume_id=resume.id,
        full_name=extract_name(header_text),
        email=extract_email(header_text),
        phone=extract_phone(header_text),
        extractor_version=RESUME_EXTRACTOR_VERSION,
        extracted_at=datetime.now(UTC),
    )

    # Skills: one matcher pass over the whole document (skills live in
    # bullets as much as in the skills section). Accepted and doubt-band
    # matches are both stored — on a resume the user reviewing their own
    # profile is the review queue, and confidence is shown, not hidden.
    matcher = TechnologyMatcher(index)
    accepted, review = matcher.score(text, matcher.find(text))
    for scored in sorted(accepted + review, key=lambda s: (-s.confidence, s.tech_slug)):
        profile.skills.append(
            ProfileSkill(
                technology_id=tech_ids[scored.tech_slug],
                label=tech_names[scored.tech_slug],
                confidence=scored.confidence,
                occurrences=scored.occurrences,
                evidence_snippet=scored.evidence,
                evidence_start=scored.evidence_start,
                origin="extracted",
            )
        )

    experience_section = layout.section("experience")
    if experience_section is not None:
        entries = parse_experience(text, experience_section.start, experience_section.end)
        for position, entry in enumerate(entries):
            title_result = canonicalize_title(entry.title_raw, index)
            profile.experiences.append(
                ProfileExperience(
                    company=entry.company,
                    title_raw=entry.title_raw,
                    canonical_title_id=(
                        title_ids.get(title_result.canonical_slug)
                        if title_result.canonical_slug
                        else None
                    ),
                    level=title_result.level,
                    start_date=entry.dates.start if entry.dates else None,
                    end_date=entry.dates.end if entry.dates else None,
                    is_current=entry.dates.is_current if entry.dates else False,
                    summary=entry.summary or None,
                    evidence_start=entry.start,
                    evidence_end=entry.end,
                    position=position,
                    origin="extracted",
                )
            )

    education_section = layout.section("education")
    if education_section is not None:
        entries = parse_education(text, education_section.start, education_section.end)
        for position, entry in enumerate(entries):
            profile.education.append(
                ProfileEducation(
                    institution=entry.institution,
                    degree_raw=entry.degree_raw,
                    degree_level=entry.degree_level,
                    field_of_study=entry.field_of_study,
                    start_year=entry.start_year,
                    end_year=entry.end_year,
                    evidence_start=entry.start,
                    evidence_end=entry.end,
                    position=position,
                    origin="extracted",
                )
            )

    db.add(profile)
    db.commit()
    return profile


def update_profile(
    db: Session, profile: CandidateProfile, payload: ProfileUpdate
) -> CandidateProfile:
    """Reconcile a full-document edit (schemas.ProfileUpdate) onto the
    profile: id = keep/update, no id = create as manual, absent = delete.

    Field edits on an extracted row flip its origin to manual (the fact is
    now the user's statement, not the extractor's) but keep its evidence
    span — the span still points at the text the fact came from. A changed
    experience title is re-canonicalized so `canonical_title_id` never
    drifts from `title_raw`."""
    profile.full_name = payload.full_name
    profile.email = payload.email
    profile.phone = payload.phone

    # Skills: existing rows are kept or dropped, never field-edited (fix a
    # wrong skill by removing it and adding the right one).
    existing_skills = {s.id: s for s in profile.skills}
    kept: list[ProfileSkill] = []
    for item in payload.skills:
        if item.id is not None:
            if item.id not in existing_skills:
                raise UnknownProfileItem("skill id", item.id)
            kept.append(existing_skills[item.id])
            continue
        tech_id = None
        label = item.label
        if item.technology_slug:
            tech = db.scalar(select(Technology).where(Technology.slug == item.technology_slug))
            if tech is None:
                raise UnknownProfileItem("technology_slug", item.technology_slug)
            tech_id = tech.id
            label = label or tech.name
        kept.append(ProfileSkill(technology_id=tech_id, label=label, origin="manual"))
    profile.skills = kept

    index = load_index_from_db(db)
    title_ids = dict(db.execute(select(CanonicalTitle.slug, CanonicalTitle.id)).all())

    existing_exp = {e.id: e for e in profile.experiences}
    new_experiences: list[ProfileExperience] = []
    for position, item in enumerate(payload.experiences):
        if item.id is not None:
            if item.id not in existing_exp:
                raise UnknownProfileItem("experience id", item.id)
            row = existing_exp[item.id]
            fields = {
                "company": item.company,
                "title_raw": item.title_raw,
                "start_date": item.start_date,
                "end_date": item.end_date,
                "is_current": item.is_current,
                "summary": item.summary,
            }
            changed = any(getattr(row, name) != value for name, value in fields.items())
            if changed:
                title_changed = row.title_raw != item.title_raw
                for name, value in fields.items():
                    setattr(row, name, value)
                row.origin = "manual"
                if title_changed:
                    result = canonicalize_title(row.title_raw, index)
                    row.canonical_title_id = (
                        title_ids.get(result.canonical_slug) if result.canonical_slug else None
                    )
                    row.level = result.level
        else:
            result = canonicalize_title(item.title_raw, index)
            row = ProfileExperience(
                company=item.company,
                title_raw=item.title_raw,
                canonical_title_id=(
                    title_ids.get(result.canonical_slug) if result.canonical_slug else None
                ),
                level=result.level,
                start_date=item.start_date,
                end_date=item.end_date,
                is_current=item.is_current,
                summary=item.summary,
                origin="manual",
            )
        row.position = position
        new_experiences.append(row)
    profile.experiences = new_experiences

    existing_edu = {e.id: e for e in profile.education}
    new_education: list[ProfileEducation] = []
    for position, item in enumerate(payload.education):
        if item.id is not None:
            if item.id not in existing_edu:
                raise UnknownProfileItem("education id", item.id)
            row = existing_edu[item.id]
            fields = {
                "institution": item.institution,
                "degree_raw": item.degree_raw,
                "field_of_study": item.field_of_study,
                "start_year": item.start_year,
                "end_year": item.end_year,
            }
            changed = any(getattr(row, name) != value for name, value in fields.items())
            if changed:
                for name, value in fields.items():
                    setattr(row, name, value)
                row.origin = "manual"
                row.degree_level = match_degree_level(row.degree_raw) if row.degree_raw else None
        else:
            row = ProfileEducation(
                institution=item.institution,
                degree_raw=item.degree_raw,
                degree_level=match_degree_level(item.degree_raw) if item.degree_raw else None,
                field_of_study=item.field_of_study,
                start_year=item.start_year,
                end_year=item.end_year,
                origin="manual",
            )
        row.position = position
        new_education.append(row)
    profile.education = new_education

    if payload.reviewed:
        if profile.reviewed_at is None:
            profile.reviewed_at = datetime.now(UTC)
    else:
        profile.reviewed_at = None

    db.commit()
    return profile


def delete_profile(db: Session, profile: CandidateProfile) -> None:
    """Remove the profile and its resume — the user deleting their own
    uploaded document (ADR-005's deliberate raw-layer exception)."""
    resume = db.get(Resume, profile.resume_id)
    db.delete(profile)
    if resume is not None:
        db.delete(resume)
    db.commit()
