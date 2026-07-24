"""GET /profiles/{id}/matches (M9): the matching endpoint end to end, over
a tiny hand-built world of jobs and one reviewed profile.

Every expected score is computed by hand from the scoring rules (weights
0.55 skills / 0.25 title / 0.20 experience; required skills count double;
N/A components renormalise), exactly as test_matching.py does for the pure
core — this test proves the DB orchestration feeds those rules the right
facts and the endpoint enforces the review gate.

World (all one company, source is full_text ATS):
  techs: python, postgresql, docker, kafka, react
  titles: backend-engineer, frontend-engineer

  Job A  backend-engineer, senior, remote
         required python, postgresql, kafka; preferred docker
  Job B  frontend-engineer, entry, hybrid
         required react; mentioned python
  Job C  backend-engineer, mid, onsite
         required python
  Job D  frontend-engineer, entry, onsite
         required react                       (no shared signal → not a match)

Candidate (reviewed): skills python, postgresql, docker; one senior
backend-engineer role (2019-01 → current); bachelor's degree.

Hand-computed scores:
  Job C  skills 2/2=1.0, title 1.0, exp mid<senior→exceeds 1.0 → 100
  Job A  skills (2*2+1)/(2*3+1)=5/7, title 1.0, exp meets 1.0
         = 100*(0.55*5/7 + 0.25 + 0.20) = 84.2857 → 84
  Job B  skills required react missing → 0.0 (python only mentioned, but
         a required bar exists), title frontend≠backend → 0.0,
         exp entry<senior→exceeds 1.0 → 100*(0.20) = 20
  Job D  no matched skill, title differs → excluded
Ranking: C (100), A (84), B (20).
"""

from datetime import UTC, date, datetime

import pytest

from app.catalog.models import Company, Job
from app.catalog.taxonomy_models import CanonicalTitle, JobTechnology, Technology
from app.ingestion.models import RawPosting, Source
from app.profile.models import (
    CandidateProfile,
    ProfileEducation,
    ProfileExperience,
    ProfileSkill,
    Resume,
)

NOW = datetime(2026, 7, 1, tzinfo=UTC)


@pytest.fixture
def world(db, user):
    """Seed the hand-computed world; return the ids the assertions need.
    The resume/profile are owned by `user`, the account `client` is
    authenticated as, so the matches endpoint's ownership check passes."""
    techs = {}
    for slug, name, category in [
        ("python", "Python", "languages"),
        ("postgresql", "PostgreSQL", "databases"),
        ("docker", "Docker", "infrastructure"),
        ("kafka", "Kafka", "messaging"),
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

    counter = 0

    def make_job(title_slug, level, arrangement, tech_levels) -> int:
        nonlocal counter
        counter += 1
        raw = RawPosting(
            source_id=source.id,
            external_id=f"job-{counter}",
            payload={"x": True},
            content_hash=f"job-{counter}",
        )
        db.add(raw)
        db.flush()
        job = Job(
            source_id=source.id,
            company_id=company.id,
            raw_posting_id=raw.id,
            title_raw=f"{title_slug} #{counter}",
            canonical_title_id=titles[title_slug],
            experience_level=level,
            arrangement=arrangement,
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

    job_a = make_job("backend-engineer", "senior", "remote",
                     [("python", "required"), ("postgresql", "required"),
                      ("kafka", "required"), ("docker", "preferred")])
    job_b = make_job("frontend-engineer", "entry", "hybrid",
                     [("react", "required"), ("python", "mentioned")])
    job_c = make_job("backend-engineer", "mid", "onsite", [("python", "required")])
    job_d = make_job("frontend-engineer", "entry", "onsite", [("react", "required")])

    resume = Resume(
        user_id=user.id,
        filename="cand.pdf",
        content_type="application/pdf",
        file_size=10,
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
        reviewed_at=NOW,  # reviewed: matching is allowed
    )
    profile.skills = [
        ProfileSkill(technology_id=techs["python"], label="Python", origin="extracted"),
        ProfileSkill(technology_id=techs["postgresql"], label="PostgreSQL", origin="extracted"),
        ProfileSkill(technology_id=techs["docker"], label="Docker", origin="extracted"),
        ProfileSkill(technology_id=None, label="Distributed Systems", origin="manual"),
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
    profile.education = [
        ProfileEducation(degree_raw="B.S.", degree_level="bachelor", position=0, origin="extracted")
    ]
    db.add(profile)
    db.commit()

    return {
        "profile_id": profile.id,
        "job_a": job_a,
        "job_b": job_b,
        "job_c": job_c,
        "job_d": job_d,
    }


def test_matches_rank_and_explain(client, world):
    resp = client.get(f"/api/v1/profiles/{world['profile_id']}/matches")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_active_jobs"] == 4  # A, B, C, D all active in the pool
    assert body["matched_jobs"] == 3  # D has no signal
    assert body["returned"] == 3
    assert body["weights"] == {"skills": 0.55, "title": 0.25, "experience": 0.2}

    profile = body["profile"]
    assert profile["matched_skill_count"] == 3  # python, postgresql, docker
    assert profile["unmapped_skill_count"] == 1  # Distributed Systems (manual, no tech id)
    assert profile["title_families"] == ["Backend Engineer"]
    assert profile["experience_level"] == "senior"
    assert profile["highest_degree"] == "bachelor"

    ids = [m["job"]["id"] for m in body["matches"]]
    scores = [m["score"] for m in body["matches"]]
    assert ids == [world["job_c"], world["job_a"], world["job_b"]]
    assert scores == [100, 84, 20]

    match_a = body["matches"][1]
    assert [s["slug"] for s in match_a["matched_skills"]] == ["postgresql", "python", "docker"]
    assert [s["slug"] for s in match_a["missing_skills"]] == ["kafka"]
    assert match_a["title"]["matched"] is True
    assert match_a["title"]["job_title"] == "Backend Engineer"
    assert match_a["title"]["job_title_slug"] == "backend-engineer"
    assert match_a["experience"]["verdict"] == "meets"
    comp = {c["key"]: c for c in match_a["components"]}
    assert comp["skills"]["score"] == round(5 / 7, 3)
    assert comp["title"]["score"] == 1.0
    assert comp["experience"]["score"] == 1.0
    assert all(c["applicable"] for c in match_a["components"])
    reasons = " | ".join(match_a["reasons"])
    assert "Matches 2 of 3 required skills" in reasons
    assert "Missing 1 required skill(s): Kafka" in reasons

    # Job C is the perfect match (exceeds the mid requirement with senior).
    match_c = body["matches"][0]
    assert match_c["experience"]["verdict"] == "exceeds"
    assert match_c["missing_skills"] == []


def test_matches_respect_filter_scope(client, world):
    """The same JobFilters the market surface uses narrow the candidate
    pool through the shared predicate. arrangement=remote → only Job A."""
    resp = client.get(f"/api/v1/profiles/{world['profile_id']}/matches?arrangement=remote")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_active_jobs"] == 1  # only Job A is remote
    assert body["matched_jobs"] == 1
    assert [m["job"]["id"] for m in body["matches"]] == [world["job_a"]]


def test_matches_limit(client, world):
    body = client.get(f"/api/v1/profiles/{world['profile_id']}/matches?limit=1").json()
    assert body["matched_jobs"] == 3  # counted before the limit
    assert body["returned"] == 1
    assert [m["job"]["id"] for m in body["matches"]] == [world["job_c"]]  # top-ranked survives


def test_unreviewed_profile_is_409(client, world, db):
    profile = db.get(CandidateProfile, world["profile_id"])
    profile.reviewed_at = None
    db.commit()
    resp = client.get(f"/api/v1/profiles/{world['profile_id']}/matches")
    assert resp.status_code == 409
    # HTTPException.detail becomes the RFC 9457 problem "title" (core/errors.py).
    assert "reviewed" in resp.json()["title"].lower()


def test_matches_missing_profile_is_404(client, world):
    assert client.get("/api/v1/profiles/999999/matches").status_code == 404


def test_matches_unknown_filter_slug_is_422(client, world):
    """A bad filter slug fails loudly through the shared resolver, the same
    422 the market surface returns — matching reuses `resolve_filters`."""
    resp = client.get(f"/api/v1/profiles/{world['profile_id']}/matches?tech=nope")
    assert resp.status_code == 422
    assert resp.json()["value"] == "nope"


def test_matches_requires_auth(unauth_client, world):
    assert unauth_client.get(f"/api/v1/profiles/{world['profile_id']}/matches").status_code == 401
