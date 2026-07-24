"""Profile API endpoints (M7): upload, review, full-document edit,
re-extract, delete. Runs through the savepoint-isolated TestClient
against the committed alex_chen.pdf fixture and the micro taxonomy."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.profile.models import Resume
from tests.resume_taxonomy import EXPECTED_ALEX_CHEN_SLUGS, seed_micro_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"


@pytest.fixture
def micro_taxonomy(db):
    return seed_micro_taxonomy(db)


def _upload(client, name="alex_chen.pdf"):
    return client.post(
        "/api/v1/resumes",
        files={"file": (name, (FIXTURES / name).read_bytes(), "application/pdf")},
    )


@pytest.fixture
def profile(client, micro_taxonomy):
    response = _upload(client)
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_returns_full_profile(profile):
    assert profile["full_name"] == "Alex Chen"
    assert profile["email"] == "alex.chen@example.com"
    assert profile["reviewed_at"] is None
    assert len(profile["skills"]) == len(EXPECTED_ALEX_CHEN_SLUGS)
    assert len(profile["experiences"]) == 3
    assert len(profile["education"]) == 1
    assert profile["resume"]["filename"] == "alex_chen.pdf"
    # The review UI renders evidence spans out of this text.
    assert profile["resume"]["extracted_text"].startswith("Alex Chen")


def test_reupload_same_bytes_returns_existing_profile(client, profile):
    again = _upload(client, name="alex_chen.pdf")
    assert again.status_code == 201
    assert again.json()["id"] == profile["id"]


def test_upload_rejections(client, micro_taxonomy):
    not_pdf = client.post(
        "/api/v1/resumes", files={"file": ("x.pdf", b"plain text", "application/pdf")}
    )
    assert not_pdf.status_code == 415

    encrypted = _upload(client, name="encrypted.pdf")
    assert encrypted.status_code == 422

    blank = _upload(client, name="blank.pdf")
    assert blank.status_code == 422

    huge = client.post(
        "/api/v1/resumes",
        files={"file": ("big.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024), "application/pdf")},
    )
    assert huge.status_code == 413


def test_list_and_detail(client, profile):
    listing = client.get("/api/v1/profiles").json()
    assert len(listing["items"]) == 1
    item = listing["items"][0]
    assert item["id"] == profile["id"]
    assert item["skill_count"] == len(EXPECTED_ALEX_CHEN_SLUGS)
    assert item["experience_count"] == 3

    detail = client.get(f"/api/v1/profiles/{profile['id']}")
    assert detail.status_code == 200
    assert detail.json()["full_name"] == "Alex Chen"

    assert client.get("/api/v1/profiles/999999").status_code == 404


def _as_update(profile, **overrides):
    """Identity update payload: keeps everything as-is."""
    payload = {
        "full_name": profile["full_name"],
        "email": profile["email"],
        "phone": profile["phone"],
        "reviewed": False,
        "skills": [{"id": s["id"]} for s in profile["skills"]],
        "experiences": [
            {
                "id": e["id"],
                "company": e["company"],
                "title_raw": e["title_raw"],
                "start_date": e["start_date"],
                "end_date": e["end_date"],
                "is_current": e["is_current"],
                "summary": e["summary"],
            }
            for e in profile["experiences"]
        ],
        "education": [
            {
                "id": e["id"],
                "institution": e["institution"],
                "degree_raw": e["degree_raw"],
                "field_of_study": e["field_of_study"],
                "start_year": e["start_year"],
                "end_year": e["end_year"],
            }
            for e in profile["education"]
        ],
    }
    payload.update(overrides)
    return payload


def test_identity_update_changes_nothing_but_stays_extracted(client, profile):
    response = client.put(f"/api/v1/profiles/{profile['id']}", json=_as_update(profile))
    assert response.status_code == 200
    body = response.json()
    assert len(body["skills"]) == len(profile["skills"])
    # No field changed, so extracted rows keep their extracted origin.
    assert all(e["origin"] == "extracted" for e in body["experiences"])


def test_full_document_reconcile(client, profile):
    update = _as_update(profile)
    # Drop the first skill, add a taxonomy-mapped one and a free-text one.
    dropped_skill = profile["skills"][0]
    update["skills"] = [{"id": s["id"]} for s in profile["skills"][1:]] + [
        {"technology_slug": "kubernetes"},  # duplicate slug is the user's call
        {"label": "Distributed Systems"},
    ]
    # Edit the second experience's title; drop the third.
    update["experiences"][1]["title_raw"] = "Backend Engineer"
    update["experiences"] = update["experiences"][:2]
    # Replace education with a new manual entry.
    update["education"] = [
        {"institution": "MIT", "degree_raw": "M.S. in Computer Science", "end_year": 2024}
    ]
    update["full_name"] = "Alexandra Chen"
    update["reviewed"] = True

    body = client.put(f"/api/v1/profiles/{profile['id']}", json=update).json()

    labels = [s["label"] for s in body["skills"]]
    assert dropped_skill["label"] not in labels
    assert "Distributed Systems" in labels
    manual = next(s for s in body["skills"] if s["label"] == "Distributed Systems")
    assert manual["origin"] == "manual"
    assert manual["evidence_snippet"] is None

    assert len(body["experiences"]) == 2
    edited = body["experiences"][1]
    assert edited["title_raw"] == "Backend Engineer"
    assert edited["origin"] == "manual"  # field edit flips provenance
    assert edited["canonical_title_id"] is not None  # re-canonicalized
    assert edited["evidence_start"] is not None  # evidence span survives

    (education,) = body["education"]
    assert education["institution"] == "MIT"
    assert education["degree_level"] == "master"  # derived, not client-sent
    assert education["origin"] == "manual"

    assert body["full_name"] == "Alexandra Chen"
    assert body["reviewed_at"] is not None


def test_unreview_by_sending_reviewed_false(client, profile):
    client.put(f"/api/v1/profiles/{profile['id']}", json=_as_update(profile, reviewed=True))
    body = client.put(f"/api/v1/profiles/{profile['id']}", json=_as_update(profile)).json()
    assert body["reviewed_at"] is None


def test_update_validation_errors(client, profile):
    unknown_skill = _as_update(profile)
    unknown_skill["skills"] = [{"id": 987654}]
    assert client.put(f"/api/v1/profiles/{profile['id']}", json=unknown_skill).status_code == 422

    unknown_slug = _as_update(profile)
    unknown_slug["skills"] = [{"technology_slug": "not-a-tech"}]
    assert client.put(f"/api/v1/profiles/{profile['id']}", json=unknown_slug).status_code == 422

    current_with_end = _as_update(profile)
    current_with_end["experiences"][0]["is_current"] = True
    current_with_end["experiences"][0]["end_date"] = "2023-01-01"
    assert (
        client.put(f"/api/v1/profiles/{profile['id']}", json=current_with_end).status_code == 422
    )


def test_reextract_discards_edits(client, profile):
    update = _as_update(profile)
    update["skills"] = update["skills"][:3]
    client.put(f"/api/v1/profiles/{profile['id']}", json=update)

    body = client.post(f"/api/v1/profiles/{profile['id']}/reextract").json()
    assert len(body["skills"]) == len(EXPECTED_ALEX_CHEN_SLUGS)
    assert body["reviewed_at"] is None


def test_delete_removes_profile_and_resume(client, db, profile):
    assert client.delete(f"/api/v1/profiles/{profile['id']}").status_code == 204
    assert client.get(f"/api/v1/profiles/{profile['id']}").status_code == 404
    assert db.scalars(select(Resume)).all() == []
