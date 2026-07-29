"""Search-surface tests over the micro-market: full-text filtering,
pagination, sort, and facets all resolve through the same shared
predicate as every other number."""

import pytest
from sqlalchemy import func, select

from app.catalog.filters import JobFilters
from app.catalog.query import job_predicate, resolve_filters
from tests.micro_market import seed_micro_market


@pytest.fixture
def market(db):
    seed_micro_market(db)
    return db


def _count(db, filters: JobFilters) -> int:
    predicate = job_predicate(resolve_filters(db, filters))
    return db.scalar(select(func.count()).select_from(predicate.subquery())) or 0


class TestFullText:
    def test_q_matches_titles(self, market):
        # Every micro-market job is titled "Job N"; websearch AND semantics
        # narrow "job 5" to exactly that one posting.
        assert _count(market, JobFilters(q="job")) == 23
        assert _count(market, JobFilters(q="job 5")) == 1

    def test_q_excludes_expired(self, market):
        # Jobs 24-25 are expired; "job 24" must find nothing.
        assert _count(market, JobFilters(q="job 24")) == 0

    def test_q_composes_with_other_filters(self, market):
        assert _count(market, JobFilters(q="job", technologies=("python",))) == 13

    def test_no_match_is_zero_not_error(self, market):
        assert _count(market, JobFilters(q="blockchain sommelier")) == 0


def _collect_pages(client, params: dict, limit: int) -> list[dict]:
    """Walk the cursor chain to exhaustion, returning every item seen."""
    items: list[dict] = []
    cursor = None
    for _ in range(30):  # hard stop: a cursor bug must not loop forever
        query = {**params, "limit": limit}
        if cursor:
            query["cursor"] = cursor
        body = client.get("/api/v1/jobs", params=query).json()
        items.extend(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return items
    raise AssertionError("cursor chain did not terminate")


class TestKeysetPagination:
    def test_pages_partition_the_result_set(self, market, client):
        items = _collect_pages(client, {}, limit=10)
        ids = [item["id"] for item in items]
        assert len(ids) == 23  # every active job exactly once
        assert len(set(ids)) == 23

    def test_last_page_has_no_cursor(self, market, client):
        body = client.get("/api/v1/jobs", params={"limit": 100}).json()
        assert body["total"] == 23
        assert len(body["items"]) == 23
        assert body["next_cursor"] is None

    def test_salary_sort_orders_disclosed_first(self, market, client):
        items = _collect_pages(client, {"sort": "salary"}, limit=10)
        # Micro-market salaries, descending: 300k x3, 250k x2, 200k x4,
        # 150k x2, 120k x5, then the 7 undisclosed jobs.
        titles = [item["title_raw"] for item in items]
        assert len(titles) == 23
        first = client.get("/api/v1/jobs", params={"sort": "salary", "limit": 3}).json()
        assert {i["title_raw"] for i in first["items"]} == {"Job 18", "Job 19", "Job 20"}

    def test_relevance_sort_requires_q(self, market, client):
        response = client.get("/api/v1/jobs", params={"sort": "relevance"})
        assert response.status_code == 422

    def test_relevance_sort_paginates(self, market, client):
        items = _collect_pages(client, {"sort": "relevance", "q": "job"}, limit=7)
        assert len({item["id"] for item in items}) == 23

    def test_malformed_cursor_fails_loudly(self, market, client):
        response = client.get("/api/v1/jobs", params={"cursor": "not-a-cursor"})
        assert response.status_code == 422

    def test_cursor_bound_to_its_query(self, market, client):
        page = client.get("/api/v1/jobs", params={"limit": 5}).json()
        cursor = page["next_cursor"]
        assert cursor is not None
        # Same cursor, different sort or different filters: refuse.
        assert (
            client.get("/api/v1/jobs", params={"cursor": cursor, "sort": "salary"}).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/jobs", params={"cursor": cursor, "arrangement": "remote"}
            ).status_code
            == 422
        )


class TestFacets:
    def test_facets_match_hand_computed_distributions(self, market, client):
        body = client.get("/api/v1/jobs", params={"limit": 1}).json()
        arrangements = {b["value"]: b["count"] for b in body["facets"]["arrangements"]}
        levels = {b["value"]: b["count"] for b in body["facets"]["experience_levels"]}
        assert arrangements == {"hybrid": 11, "onsite": 4, "remote": 5, "unspecified": 3}
        assert levels == {"senior": 8, "mid": 4, "entry": 5, "staff_plus": 3, "unspecified": 3}
        # Facets cover the full matching set even though one item was returned.
        assert sum(arrangements.values()) == body["total"] == 23

    def test_facets_reflect_active_filters(self, market, client):
        body = client.get("/api/v1/jobs", params={"arrangement": "remote"}).json()
        arrangements = {b["value"]: b["count"] for b in body["facets"]["arrangements"]}
        levels = {b["value"]: b["count"] for b in body["facets"]["experience_levels"]}
        assert arrangements == {"remote": 5}
        assert levels == {"senior": 2, "staff_plus": 3}


class TestEmploymentTypeFilter:
    """Ground truth (micro_market): internship 2, contract 1, full_time 17,
    NULL 3 — over the 23 active, deduplicated jobs."""

    def test_internships_are_filterable_on_their_own(self, market, client):
        body = client.get("/api/v1/jobs", params={"employment_type": "internship"}).json()
        assert body["total"] == 2
        assert _count(market, JobFilters(employment_type="internship")) == 2

    def test_full_time_excludes_internships(self, market, client):
        body = client.get("/api/v1/jobs", params={"employment_type": "full_time"}).json()
        assert body["total"] == 17

    def test_unknown_also_matches_never_classified_jobs(self, market, client):
        # NULL (ingested before employment typing) and 'unknown' (classified,
        # no signal) answer the same user question, so one filter returns both.
        body = client.get("/api/v1/jobs", params={"employment_type": "unknown"}).json()
        assert body["total"] == 3

    def test_types_partition_the_market(self, market, client):
        total = 0
        for value in ("full_time", "part_time", "internship", "contract", "temporary", "unknown"):
            total += client.get("/api/v1/jobs", params={"employment_type": value}).json()["total"]
        assert total == 23

    def test_composes_with_other_filters(self, market, client):
        # Both internships are NYC frontend jobs.
        body = client.get(
            "/api/v1/jobs",
            params={"employment_type": "internship", "title": "frontend-engineer"},
        ).json()
        assert body["total"] == 2
        body = client.get(
            "/api/v1/jobs",
            params={"employment_type": "internship", "title": "backend-engineer"},
        ).json()
        assert body["total"] == 0

    def test_unknown_value_is_rejected(self, market, client):
        assert (
            client.get("/api/v1/jobs", params={"employment_type": "freelance"}).status_code == 422
        )

    def test_facets_report_the_distribution(self, market, client):
        body = client.get("/api/v1/jobs", params={"limit": 1}).json()
        types = {b["value"]: b["count"] for b in body["facets"]["employment_types"]}
        assert types == {"full_time": 17, "internship": 2, "contract": 1, "unspecified": 3}
        assert sum(types.values()) == body["total"] == 23

    def test_filter_is_absent_by_default(self, market, client):
        # Backward compatibility: a search that never mentions employment
        # type still sees the whole market, NULL-typed jobs included.
        assert client.get("/api/v1/jobs").json()["total"] == 23


class TestZeroResultRelaxation:
    def test_drops_a_technology_but_never_the_title(self, market, client):
        # Denver has 3 jobs, none with pytorch (the pytorch jobs are
        # remote with no geocoded location, so no radius helps either).
        body = client.get(
            "/api/v1/jobs",
            params={"location": "denver-co", "radius_miles": 10, "tech": "pytorch"},
        ).json()
        assert body["total"] == 0
        assert [(o["kind"], o["count"]) for o in body["relaxations"]] == [("technology", 3)]
        relaxed = body["relaxations"][0]["filters"]
        assert relaxed["technologies"] == []
        assert relaxed["location"] == "denver-co"

    def test_offers_salary_floor_removal(self, market, client):
        # All 5 frontend jobs pay 120k; a 200k floor zeroes the search.
        body = client.get(
            "/api/v1/jobs", params={"title": "frontend-engineer", "salary_min": 200_000}
        ).json()
        assert body["total"] == 0
        assert [(o["kind"], o["count"]) for o in body["relaxations"]] == [("salary", 5)]
        # The title must survive relaxation — relaxing it would answer a
        # different question than the one asked.
        assert body["relaxations"][0]["filters"]["title"] == "frontend-engineer"

    def test_widens_radius_to_first_bucket_that_helps(self, market, client):
        # go only exists on the SF+NYC multi-location jobs; from San Jose
        # they enter the picture at the 50-mile bucket (SF is ~48 miles).
        body = client.get(
            "/api/v1/jobs", params={"location": "san-jose-ca", "radius_miles": 10, "tech": "go"}
        ).json()
        assert body["total"] == 0
        by_kind = {o["kind"]: o for o in body["relaxations"]}
        assert by_kind["radius"]["count"] == 2
        assert by_kind["radius"]["filters"]["radius_miles"] == 50
        # Dropping go instead finds the 2 San Jose jobs.
        assert by_kind["technology"]["count"] == 2

    def test_no_options_when_nothing_relaxable_helps(self, market, client):
        body = client.get("/api/v1/jobs", params={"q": "blockchain sommelier"}).json()
        assert body["total"] == 0
        assert body["relaxations"] == []

    def test_absent_when_results_exist(self, market, client):
        body = client.get("/api/v1/jobs", params={"tech": "python"}).json()
        assert body["total"] == 13
        assert body["relaxations"] == []
