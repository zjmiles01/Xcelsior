"""Skill detail tests over the micro-market. Every asserted number is
hand-computed from tests/micro_market.py's docstring, per the project's
known-truth rule.

Hand computations used below (national scope, 23 active jobs):

  python: 13 jobs (share 13/23); required 11, preferred 2.
    co-occurrence: postgresql 6 of 13 (baseline 6/23, lift 23/13 ~ 1.769),
    pytorch 3 of 13 (baseline 3/23, lift 23/13). go/react/typescript
    co-occur 0 times. Salary over 9 disclosed python jobs
    (150,150,200,200,200,200,300,300,300): median 200k -> delta 0 vs the
    200k national median.
  react: 5 jobs, all with typescript (5 of 5, baseline 5/23, lift 23/5 =
    4.6) — but python co-occurs 0 times. Salary: 5 x 120k -> median 120k,
    delta -80k vs national.
  SF 10mi scope: 10 analyzed; python on 6 SF + 2 Oakland = 8 (the 2
    multi-location jobs are go-only).
"""

import datetime

import pytest
from sqlalchemy import select

from app.analytics.models import MarketSnapshot
from app.catalog.taxonomy_models import Technology
from tests.micro_market import seed_micro_market


@pytest.fixture
def market(db):
    seed_micro_market(db)
    return db


def _get(client, slug, **params):
    response = client.get(f"/api/v1/skills/{slug}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


class TestHeader:
    def test_national_python(self, market, client):
        body = _get(client, "python")
        header = body["header"]
        assert header["analyzed_jobs"] == 23
        assert header["jobs_with_tech"] == 13
        assert header["share"] == pytest.approx(13 / 23)
        assert header["low_confidence"] is True  # 13 < 30

    def test_scoped_to_sf(self, market, client):
        header = _get(client, "python", location="san-francisco-ca", radius_miles=10)["header"]
        assert header["analyzed_jobs"] == 10
        assert header["jobs_with_tech"] == 8

    def test_own_slug_in_tech_filter_is_not_a_tautology(self, market, client):
        # /skills/python?tech=python must not make share 13/13.
        body = _get(client, "python", tech="python")
        assert body["header"]["analyzed_jobs"] == 23
        assert body["filters"]["technologies"] == []

    def test_requirement_levels(self, market, client):
        levels = {b["value"]: b["count"] for b in _get(client, "python")["requirement_levels"]}
        assert levels == {"required": 11, "preferred": 2}


class TestCoOccurrence:
    def test_python_pairs_with_hand_computed_lift(self, market, client):
        pairs = {s["slug"]: s for s in _get(client, "python")["co_occurring"]}
        assert set(pairs) == {"postgresql", "pytorch"}
        pg = pairs["postgresql"]
        assert pg["count"] == 6
        assert pg["share_given_tech"] == pytest.approx(6 / 13)
        assert pg["baseline_share"] == pytest.approx(6 / 23)
        assert pg["lift"] == pytest.approx(23 / 13)
        assert pairs["pytorch"]["count"] == 3

    def test_react_typescript_pairing(self, market, client):
        pairs = {s["slug"]: s for s in _get(client, "react")["co_occurring"]}
        assert set(pairs) == {"typescript"}
        ts = pairs["typescript"]
        assert ts["share_given_tech"] == pytest.approx(1.0)
        assert ts["lift"] == pytest.approx(23 / 5)


class TestSalaryDelta:
    def test_python_matches_national_median(self, market, client):
        salary = _get(client, "python")["salary"]
        assert salary["disclosed_count"] == 9
        assert salary["median"] == 200_000
        assert salary["national_median"] == 200_000
        assert salary["delta_vs_national"] == 0

    def test_react_pays_below_national(self, market, client):
        salary = _get(client, "react")["salary"]
        assert salary["median"] == 120_000
        assert salary["delta_vs_national"] == -80_000

    def test_no_disclosures_means_no_delta(self, market, client):
        # go jobs disclose (250k x2), but scoped to Denver nothing matches.
        salary = _get(client, "go", location="denver-co", radius_miles=10)["salary"]
        assert salary["disclosed_count"] == 0
        assert salary["median"] is None
        assert salary["delta_vs_national"] is None


class TestTrend:
    def _seed_snapshots(self, db, slug: str, days: int) -> None:
        tech_id = db.scalar(select(Technology.id).where(Technology.slug == slug))
        start = datetime.date(2026, 6, 1)
        for offset in range(days):
            db.add(
                MarketSnapshot(
                    snapshot_date=start + datetime.timedelta(days=offset),
                    technology_id=tech_id,
                    canonical_title_id=None,
                    geo_slug="national",
                    job_count=10 + offset,
                )
            )
        db.flush()

    def test_collecting_history_below_min_days(self, market, client):
        self._seed_snapshots(market, "python", days=2)
        trend = _get(client, "python")["trend"]
        assert trend["status"] == "collecting_history"
        assert trend["days_observed"] == 2
        assert len(trend["points"]) == 2

    def test_ok_at_min_days(self, market, client):
        self._seed_snapshots(market, "python", days=7)
        trend = _get(client, "python")["trend"]
        assert trend["status"] == "ok"
        assert [p["job_count"] for p in trend["points"]] == [10, 11, 12, 13, 14, 15, 16]

    def test_non_metro_scope_falls_back_to_national(self, market, client):
        self._seed_snapshots(market, "python", days=3)
        trend = _get(client, "python", location="san-francisco-ca")["trend"]
        assert trend["geo_slug"] == "national"  # no SF bucket rows exist
        assert trend["days_observed"] == 3


class TestAliasRedirect:
    def test_alias_slug_301s_to_canonical(self, market, client):
        response = client.get("/api/v1/skills/golang", follow_redirects=False)
        assert response.status_code == 301
        assert response.headers["location"].endswith("/api/v1/skills/go")

    def test_redirect_preserves_scope(self, market, client):
        response = client.get(
            "/api/v1/skills/react-js",
            params={"location": "new-york-city-ny"},
            follow_redirects=False,
        )
        assert response.status_code == 301
        assert "/api/v1/skills/react?location=new-york-city-ny" in response.headers["location"]

    def test_unknown_skill_404s(self, market, client):
        assert client.get("/api/v1/skills/blockchain-sommelier").status_code == 404
