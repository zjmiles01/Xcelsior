"""Milestone 4 acceptance: the full product loop, dashboard -> skill ->
filtered search -> job detail -> back, with the URL carrying the state at
every step and every surface agreeing on the numbers.

Each hop reuses the previous hop's query parameters plus at most one new
constraint — exactly what the frontend does — so this test fails if any
surface stops speaking the shared filter dialect or drifts from the
shared predicate.
"""

import pytest

from tests.micro_market import seed_micro_market

# 12 backend jobs in the micro-market: 6 SF + 2 Oakland + 2 San Jose +
# 2 SF+NYC multi-location. Python on all but the go-only multi pair = 10.
SCOPE = {"title": "backend-engineer"}


@pytest.fixture
def market(db):
    seed_micro_market(db)
    return db


def test_full_loop_with_count_parity(market, client):
    # 1. Dashboard: the analysis for a role scope.
    analysis = client.get("/api/v1/analysis", params=SCOPE).json()
    assert analysis["header"]["analyzed_jobs"] == 12
    python = next(
        t
        for c in analysis["categories"]
        for t in c["technologies"]
        if t["slug"] == "python"
    )
    assert python["count"] == 10  # all but the go-only multi-location pair

    # 2. Click the stat: skill page, same scope carried in the query.
    skill = client.get("/api/v1/skills/python", params=SCOPE).json()
    assert skill["header"]["analyzed_jobs"] == analysis["header"]["analyzed_jobs"]
    assert skill["header"]["jobs_with_tech"] == python["count"]

    # 3. "View all": search scoped to (same scope + this skill).
    search_params = {**SCOPE, "tech": "python"}
    search = client.get("/api/v1/jobs", params=search_params).json()
    assert search["total"] == skill["header"]["jobs_with_tech"]
    assert len(search["items"]) == search["total"]

    # 4. Open a job from the results; it really belongs to the scope.
    job_id = search["items"][0]["id"]
    detail = client.get(f"/api/v1/jobs/{job_id}").json()
    assert detail["canonical_title_slug"] == "backend-engineer"
    assert "python" in {t["slug"] for t in detail["technologies"]}

    # 5. Back: the same URL answers with the same numbers.
    again = client.get("/api/v1/jobs", params=search_params).json()
    assert again["total"] == search["total"]
    assert [item["id"] for item in again["items"]] == [item["id"] for item in search["items"]]


def test_loop_survives_an_alias_entry_point(market, client):
    # A shared /skills/golang link must land on the same numbers as /skills/go.
    response = client.get("/api/v1/skills/golang", params=SCOPE)  # follows the 301
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["slug"] == "go"
    assert body["header"]["jobs_with_tech"] == 2  # the two SF+NYC multi-location jobs

    search = client.get("/api/v1/jobs", params={**SCOPE, "tech": "go"}).json()
    assert search["total"] == body["header"]["jobs_with_tech"]


def test_loop_holds_under_geo_scope(market, client):
    # The same walk with a location + radius in the URL end to end.
    scope = {"location": "san-francisco-ca", "radius_miles": 10}
    analysis = client.get("/api/v1/analysis", params=scope).json()
    skill = client.get("/api/v1/skills/python", params=scope).json()
    search = client.get("/api/v1/jobs", params={**scope, "tech": "python"}).json()
    assert analysis["header"]["analyzed_jobs"] == 10
    assert skill["header"]["analyzed_jobs"] == 10
    assert skill["header"]["jobs_with_tech"] == 8  # 6 SF + 2 Oakland; multi jobs are go-only
    assert search["total"] == 8
