"""Resume → profile pipeline against the database (M7).

Runs end-to-end from the committed alex_chen.pdf fixture through
create_resume + extract_profile, against a hand-inserted micro taxonomy
(so every expected skill, confidence, and title below is hand-computed
from the fixture text and the matcher's documented scoring rules, not
copied from a first run).

Hand-computed skill expectations (matcher rules: unambiguous alias 0.9,
risky-but-gated 0.7, +0.05 when seen twice or more):
- python: 3 mentions (summary, skills line, PostgreSQL bullet) -> 0.95
- go: case-sensitive + context-gated, 3 gated mentions -> 0.75
- kafka, kubernetes, aws, terraform, postgresql: 2 mentions -> 0.95
- typescript, sql, redis, docker, flask, fastapi: 1 mention -> 0.9
  (sql matches only standalone "SQL" — the one inside "PostgreSQL" is
  boundary-rejected)
"""

from datetime import date
from pathlib import Path

import pytest

from app.profile.models import CandidateProfile, ProfileSkill
from app.profile.service import create_resume, extract_profile
from tests.resume_taxonomy import EXPECTED_ALEX_CHEN_SLUGS, seed_micro_taxonomy

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "resumes" / "alex_chen.pdf"

EXPECTED_SLUGS = EXPECTED_ALEX_CHEN_SLUGS


@pytest.fixture
def micro_taxonomy(db):
    return seed_micro_taxonomy(db)


@pytest.fixture
def resume(db, user, micro_taxonomy):
    r, created = create_resume(
        db, user.id, "alex_chen.pdf", "application/pdf", FIXTURE_PDF.read_bytes()
    )
    assert created is True
    return r


def test_create_resume_stores_bytes_and_text(db, resume):
    assert resume.parser_name == "pypdf"
    assert resume.parser_version == 1
    assert resume.page_count == 1
    assert resume.file_size == FIXTURE_PDF.stat().st_size
    assert resume.extracted_text.startswith("Alex Chen")


def test_create_resume_is_idempotent_on_identical_bytes(db, user, resume):
    again, created = create_resume(
        db, user.id, "renamed.pdf", "application/pdf", FIXTURE_PDF.read_bytes()
    )
    assert created is False
    assert again.id == resume.id


def test_extracted_contact(db, resume):
    profile = extract_profile(db, resume)
    assert profile.full_name == "Alex Chen"
    assert profile.email == "alex.chen@example.com"
    assert profile.phone == "(415) 555-0100"
    assert profile.extractor_version == 1
    assert profile.reviewed_at is None


def test_extracted_skills_match_hand_computed_truth(db, resume):
    profile = extract_profile(db, resume)
    by_label = {s.label: s for s in profile.skills}
    slugs = {s.label.lower().replace(" ", "-") for s in profile.skills}
    assert {s.lower() for s in slugs} == EXPECTED_SLUGS

    assert by_label["Python"].confidence == 0.95
    assert by_label["Python"].occurrences == 3
    assert by_label["Go"].confidence == 0.75
    assert by_label["Docker"].confidence == 0.9
    assert by_label["Kafka"].confidence == 0.95

    text = resume.extracted_text
    for skill in profile.skills:
        assert skill.technology_id is not None
        assert skill.origin == "extracted"
        assert skill.evidence_snippet in text  # evidence round-trips


def test_extracted_experiences_match_hand_computed_truth(db, resume, micro_taxonomy):
    profile = extract_profile(db, resume)
    first, second, third = profile.experiences

    assert first.title_raw == "Senior Software Engineer"
    assert first.company == "Wavelength Analytics"
    assert first.level == "senior"
    assert first.canonical_title_id == micro_taxonomy
    assert first.start_date == date(2022, 3, 1)
    assert first.end_date is None
    assert first.is_current is True
    assert "Kafka-based event pipeline" in first.summary

    assert second.title_raw == "Software Engineer"
    assert second.company == "Harborview Systems"
    assert second.level is None
    assert second.start_date == date(2019, 7, 1)
    assert second.end_date == date(2022, 2, 1)

    assert third.title_raw == "Backend Engineer Intern"
    assert third.company == "Northstar Labs"
    assert third.level == "entry"
    assert third.canonical_title_id == micro_taxonomy

    # Evidence spans reproduce each entry's own text.
    text = resume.extracted_text
    span = text[first.evidence_start : first.evidence_end]
    assert span.startswith("Senior Software Engineer, Wavelength Analytics")
    assert "Led migration of the core API" in span
    assert "Harborview" not in span


def test_extracted_education_matches_hand_computed_truth(db, resume):
    profile = extract_profile(db, resume)
    (entry,) = profile.education
    assert entry.institution == "University of California, Berkeley"
    assert entry.degree_raw == "B.S. in Computer Science"
    assert entry.degree_level == "bachelor"
    assert entry.field_of_study == "Computer Science"
    assert entry.start_year == 2015
    assert entry.end_year == 2019


def test_reextract_replaces_profile_and_discards_edits(db, resume):
    profile = extract_profile(db, resume)
    profile.skills.append(ProfileSkill(label="Juggling", origin="manual"))
    db.commit()
    assert len(profile.skills) == len(EXPECTED_SLUGS) + 1

    rebuilt = extract_profile(db, resume)
    labels = {s.label for s in rebuilt.skills}
    assert "Juggling" not in labels
    assert len(rebuilt.skills) == len(EXPECTED_SLUGS)
    assert db.query(CandidateProfile).filter_by(resume_id=resume.id).count() == 1
