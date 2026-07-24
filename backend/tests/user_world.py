"""A compact, hand-verifiable world for the M10 saved-jobs and authorization
tests: a couple of active jobs, a taxonomy they share with a candidate, and a
reviewed profile owned by a given user.

Kept deliberately tiny and explicit (same discipline as micro_market): every
match number a test asserts is derivable from what is seeded here.
"""

from datetime import UTC, date, datetime

from app.catalog.models import Company, Job
from app.catalog.taxonomy_models import CanonicalTitle, JobTechnology, Technology
from app.ingestion.models import RawPosting, Source
from app.profile.models import (
    CandidateProfile,
    ProfileExperience,
    ProfileSkill,
    Resume,
)

NOW = datetime(2026, 7, 1, tzinfo=UTC)


def seed_world(db, user, *, reviewed: bool = True) -> dict:
    """Seed two active jobs and a profile owned by `user`.

    Techs: python, react. Title: backend-engineer.
      backend_job  backend-engineer, senior, required python  -> matches
      frontend_job frontend-engineer, entry,  required react  -> no signal

    Profile (owned by user): skill python; one senior backend-engineer role.
    So the backend job scores skills 1.0 + title 1.0 + exp meets -> 100, and
    the frontend job shares no signal (score-only path drops it, saved-jobs
    keeps it with a 0-ish explanation).
    """
    techs = {}
    for slug, name, category in [
        ("python", "Python", "languages"),
        ("react", "React", "frameworks"),
    ]:
        t = Technology(slug=slug, name=name, category=category)
        db.add(t)
        db.flush()
        techs[slug] = t.id

    titles = {}
    for slug, name in [
        ("backend-engineer", "Backend Engineer"),
        ("frontend-engineer", "Frontend Engineer"),
    ]:
        ct = CanonicalTitle(slug=slug, name=name)
        db.add(ct)
        db.flush()
        titles[slug] = ct.id

    source = Source(name="src", kind="ats_api", display_policy="full_text")
    company = Company(name="Acme", name_normalized="acme")
    db.add_all([source, company])
    db.flush()

    counter = {"n": 0}

    def make_job(title_slug, level, tech_levels) -> int:
        counter["n"] += 1
        raw = RawPosting(
            source_id=source.id,
            external_id=f"job-{counter['n']}",
            payload={"x": True},
            content_hash=f"job-{counter['n']}",
        )
        db.add(raw)
        db.flush()
        job = Job(
            source_id=source.id,
            company_id=company.id,
            raw_posting_id=raw.id,
            title_raw=f"{title_slug} #{counter['n']}",
            canonical_title_id=titles[title_slug],
            experience_level=level,
            arrangement="remote",
            status="active",
            posted_at=NOW,
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        db.add(job)
        db.flush()
        for slug, req in tech_levels:
            db.add(
                JobTechnology(
                    job_id=job.id,
                    technology_id=techs[slug],
                    requirement_level=req,
                    confidence=1.0,
                    extractor_version=1,
                    evidence_snippet="x",
                    evidence_start=0,
                )
            )
        return job.id

    backend_job = make_job("backend-engineer", "senior", [("python", "required")])
    frontend_job = make_job("frontend-engineer", "entry", [("react", "required")])

    resume = Resume(
        user_id=user.id,
        filename="cand.pdf",
        content_type="application/pdf",
        file_size=8,
        file_bytes=b"%PDF-1.4",
        content_hash="cand-hash",
        extracted_text="Candidate",
        parser_name="test",
        parser_version=1,
    )
    db.add(resume)
    db.flush()
    profile = CandidateProfile(
        user_id=user.id,
        resume_id=resume.id,
        full_name="Casey Dev",
        extractor_version=1,
        extracted_at=NOW,
        reviewed_at=NOW if reviewed else None,
    )
    profile.skills = [
        ProfileSkill(technology_id=techs["python"], label="Python", origin="extracted")
    ]
    profile.experiences = [
        ProfileExperience(
            title_raw="Senior Backend Engineer",
            canonical_title_id=titles["backend-engineer"],
            level="senior",
            start_date=date(2019, 1, 1),
            is_current=True,
            position=0,
            origin="extracted",
        )
    ]
    db.add(profile)
    db.commit()

    return {
        "backend_job": backend_job,
        "frontend_job": frontend_job,
        "profile_id": profile.id,
    }
