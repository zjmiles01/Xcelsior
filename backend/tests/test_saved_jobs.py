"""Saved jobs (M10): persistence, idempotency, search coexistence, and the
live-match dashboard.

The two behaviors the milestone insists on are pinned here: saving a job does
not remove it from search (it only records an edge), and the saved-jobs
dashboard's match info is computed live against the user's reviewed profile.
"""

import pytest

from tests.user_world import seed_world


@pytest.fixture
def world(db, user):
    return seed_world(db, user)


# ── Save / unsave / ids ──────────────────────────────────────────────────


def test_save_then_list_ids(client, world):
    job_id = world["backend_job"]
    resp = client.post("/api/v1/saved-jobs", json={"job_id": job_id})
    assert resp.status_code == 201
    assert job_id in resp.json()["job_ids"]
    assert client.get("/api/v1/saved-jobs/ids").json()["job_ids"] == [job_id]


def test_saving_is_idempotent(client, world):
    job_id = world["backend_job"]
    client.post("/api/v1/saved-jobs", json={"job_id": job_id})
    client.post("/api/v1/saved-jobs", json={"job_id": job_id})
    assert client.get("/api/v1/saved-jobs/ids").json()["job_ids"] == [job_id]


def test_saving_a_missing_job_is_404(client):
    assert client.post("/api/v1/saved-jobs", json={"job_id": 999999}).status_code == 404


def test_unsave_removes_the_edge(client, world):
    job_id = world["backend_job"]
    client.post("/api/v1/saved-jobs", json={"job_id": job_id})
    assert client.delete(f"/api/v1/saved-jobs/{job_id}").status_code == 204
    assert client.get("/api/v1/saved-jobs/ids").json()["job_ids"] == []


def test_unsave_is_idempotent(client, world):
    # Deleting a job that isn't saved is a harmless no-op.
    assert client.delete(f"/api/v1/saved-jobs/{world['backend_job']}").status_code == 204


def test_saving_does_not_remove_job_from_search(client, world):
    job_id = world["backend_job"]
    before = client.get("/api/v1/jobs", params={"limit": 100}).json()
    assert any(j["id"] == job_id for j in before["items"])

    client.post("/api/v1/saved-jobs", json={"job_id": job_id})

    after = client.get("/api/v1/jobs", params={"limit": 100}).json()
    # Still present in search, and the total is unchanged — save is additive.
    assert any(j["id"] == job_id for j in after["items"])
    assert after["total"] == before["total"]


# ── Dashboard: live match info ───────────────────────────────────────────


def test_dashboard_shows_live_match_against_reviewed_profile(client, world):
    client.post("/api/v1/saved-jobs", json={"job_id": world["backend_job"]})
    client.post("/api/v1/saved-jobs", json={"job_id": world["frontend_job"]})

    body = client.get("/api/v1/saved-jobs").json()
    assert body["profile_id"] == world["profile_id"]
    assert body["profile"]["experience_level"] == "senior"

    by_job = {item["job"]["id"]: item for item in body["items"]}

    # Backend job: python required + title + experience all align -> 100.
    backend = by_job[world["backend_job"]]
    assert backend["match"] is not None
    assert backend["match"]["score"] == 100
    assert [s["slug"] for s in backend["match"]["matched_skills"]] == ["python"]

    # Frontend job is still shown (the user saved it) but scores low: no
    # shared skill, wrong title family.
    frontend = by_job[world["frontend_job"]]
    assert frontend["match"] is not None
    assert frontend["match"]["score"] < backend["match"]["score"]
    assert [s["slug"] for s in frontend["match"]["missing_skills"]] == ["react"]


def test_dashboard_without_a_reviewed_profile_omits_match(db, client, user):
    # A saved job with no reviewed profile still lists — just without scores.
    world = seed_world(db, user, reviewed=False)
    client.post("/api/v1/saved-jobs", json={"job_id": world["backend_job"]})
    body = client.get("/api/v1/saved-jobs").json()
    assert body["profile"] is None
    assert body["profile_id"] is None
    assert len(body["items"]) == 1
    assert body["items"][0]["match"] is None
