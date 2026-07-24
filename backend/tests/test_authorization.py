"""Cross-user authorization (M10): one account can never reach another's data.

`client` is authenticated as `user`; `other_client` as `other_user`. The
world (profile + jobs) is owned by `user`. Every attempt by `other_client` to
read, edit, delete, or match against `user`'s profile must be a 404 — the API
does not even confirm the resource exists. Ownership is derived from the
session, so manipulating the id in the URL changes nothing.
"""

import pytest

from tests.user_world import seed_world


@pytest.fixture
def world(db, user):
    return seed_world(db, user)


# ── Profile ownership ────────────────────────────────────────────────────


def test_other_user_cannot_read_the_profile(other_client, world):
    assert other_client.get(f"/api/v1/profiles/{world['profile_id']}").status_code == 404


def test_other_user_cannot_edit_the_profile(other_client, world):
    payload = {"skills": [], "experiences": [], "education": [], "reviewed": False}
    resp = other_client.put(f"/api/v1/profiles/{world['profile_id']}", json=payload)
    assert resp.status_code == 404


def test_other_user_cannot_delete_the_profile(other_client, world):
    assert other_client.delete(f"/api/v1/profiles/{world['profile_id']}").status_code == 404


def test_other_user_cannot_reextract_the_profile(other_client, world):
    resp = other_client.post(f"/api/v1/profiles/{world['profile_id']}/reextract")
    assert resp.status_code == 404


def test_other_user_cannot_match_against_the_profile(other_client, world):
    # Not a 409 (would confirm the profile exists but is unreviewed) and not a
    # 200 — a flat 404, the same as any nonexistent id.
    resp = other_client.get(f"/api/v1/profiles/{world['profile_id']}/matches")
    assert resp.status_code == 404


def test_owner_still_reaches_everything(client, world):
    pid = world["profile_id"]
    assert client.get(f"/api/v1/profiles/{pid}").status_code == 200
    assert client.get(f"/api/v1/profiles/{pid}/matches").status_code == 200


def test_profile_list_is_scoped_to_the_caller(client, other_client, world):
    assert len(client.get("/api/v1/profiles").json()["items"]) == 1
    assert other_client.get("/api/v1/profiles").json()["items"] == []


def test_deleting_a_missing_profile_id_is_404_not_a_leak(other_client, world):
    # Even for an id that does exist (just not theirs), the response is the
    # same 404 as a truly nonexistent id — no existence oracle.
    real_but_foreign = other_client.delete(f"/api/v1/profiles/{world['profile_id']}")
    nonexistent = other_client.delete("/api/v1/profiles/98765")
    assert real_but_foreign.status_code == nonexistent.status_code == 404


# ── Saved-job ownership ──────────────────────────────────────────────────


def test_saved_jobs_are_per_user(client, other_client, world):
    job_id = world["backend_job"]
    client.post("/api/v1/saved-jobs", json={"job_id": job_id})

    # The other user sees none of it.
    assert other_client.get("/api/v1/saved-jobs/ids").json()["job_ids"] == []
    assert other_client.get("/api/v1/saved-jobs").json()["items"] == []


def test_other_user_cannot_unsave_someone_elses_job(client, other_client, world):
    job_id = world["backend_job"]
    client.post("/api/v1/saved-jobs", json={"job_id": job_id})

    # A delete by the other user is a no-op on their (empty) set and leaves
    # the owner's save intact — it never reaches the owner's edge.
    assert other_client.delete(f"/api/v1/saved-jobs/{job_id}").status_code == 204
    assert client.get("/api/v1/saved-jobs/ids").json()["job_ids"] == [job_id]
