"""Invariant tests over the micro-market: every asserted number is
hand-computed in tests/micro_market.py's docstring, never derived by
running the system and copying its output."""

import pytest
from sqlalchemy import func, select

from app.analytics.service import compute_analysis
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


def _analysis(db, **kwargs):
    return compute_analysis(db, JobFilters(**kwargs))


def _tech(analysis, slug):
    for category in analysis.categories:
        for tech in category.technologies:
            if tech.slug == slug:
                return tech
    return None


class TestParity:
    """Dashboard number == search count, for every predicate shape."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"technologies": ("python",)},
            {"location": "san-francisco-ca", "radius_miles": 10},
            {"location": "san-francisco-ca", "radius_miles": 50, "technologies": ("python",)},
            {"arrangement": "remote"},
            {"title": "backend-engineer", "salary_min": 140_000},
        ],
    )
    def test_analysis_equals_search(self, market, kwargs):
        filters = JobFilters(**kwargs)
        analysis = compute_analysis(market, filters)
        assert analysis.header.analyzed_jobs == _count(market, filters)


class TestCounting:
    def test_national_counts_each_job_once(self, market):
        # 23 active jobs; the two SF+NYC multi-location jobs count once.
        assert _analysis(market).header.analyzed_jobs == 23

    def test_multi_location_jobs_appear_in_both_metros(self, market):
        sf = _analysis(market, location="san-francisco-ca", radius_miles=10)
        nyc = _analysis(market, location="new-york-city-ny", radius_miles=10)
        assert sf.header.analyzed_jobs == 10  # 6 SF + 2 Oakland + 2 multi
        assert nyc.header.analyzed_jobs == 7  # 5 frontend + 2 multi

    def test_radius_buckets_widen_the_market(self, market):
        sf10 = _analysis(market, location="san-francisco-ca", radius_miles=10)
        sf50 = _analysis(market, location="san-francisco-ca", radius_miles=50)
        assert sf10.header.analyzed_jobs == 10
        assert sf50.header.analyzed_jobs == 12  # + 2 San Jose

    def test_expired_jobs_are_invisible(self, market):
        # The expired SF backend job (python, 999k) must not leak into
        # counts or salary stats anywhere.
        national = _analysis(market)
        assert national.header.analyzed_jobs == 23
        assert _tech(national, "python").count == 13
        assert national.salary.median == 200_000


class TestDenominators:
    def test_shares_use_all_analyzed_jobs(self, market):
        national = _analysis(market)
        python = _tech(national, "python")
        # 13 of 23 — including the three Denver jobs with no extracted
        # technologies in the denominator.
        assert python.count == 13
        assert python.share == pytest.approx(13 / 23)

    def test_required_count_excludes_preferred(self, market):
        python = _tech(_analysis(market), "python")
        assert python.required_count == 11  # San Jose pair is preferred-only

    def test_distributions_include_unspecified(self, market):
        national = _analysis(market)
        arrangements = {b.value: b.count for b in national.arrangements}
        assert arrangements == {"hybrid": 11, "onsite": 4, "remote": 5, "unspecified": 3}
        levels = {b.value: b.count for b in national.experience_levels}
        assert levels == {"senior": 8, "mid": 4, "entry": 5, "staff_plus": 3, "unspecified": 3}
        assert sum(arrangements.values()) == 23  # distributions partition the market


class TestSalaryHonesty:
    def test_stats_over_disclosed_subset_only(self, market):
        national = _analysis(market)
        assert national.header.salary_disclosed == 16
        assert national.salary.disclosed_count == 16
        assert national.salary.median == 200_000
        assert national.salary.p25 == 120_000
        assert national.salary.p75 == 250_000

    def test_salary_floor_excludes_undisclosed(self, market):
        # 4 SF@200k + 2 Oakland@150k + 2 multi@250k + 3 ML@300k = 11; the
        # undisclosed backend jobs must not match a salary filter.
        assert _count(market, JobFilters(salary_min=140_000)) == 11


class TestSmallSamples:
    def test_micro_market_is_flagged_low_confidence(self, market):
        national = _analysis(market)
        assert national.header.analyzed_jobs < national.header.min_sample_size
        assert national.header.low_confidence is True

    def test_empty_scope_is_zero_not_error(self, market):
        empty = _analysis(market, location="denver-co", radius_miles=10,
                          technologies=("pytorch",))
        assert empty.header.analyzed_jobs == 0
        assert empty.salary.median is None
        assert empty.arrangements == []


class TestDedup:
    """Cross-source duplicates (#26, #27) must be invisible everywhere.

    Their absurd salaries (400k/500k) are tripwires: if either leaked
    into stats, TestSalaryHonesty's hand-computed percentiles would
    already be failing — these tests pin the mechanism itself.
    """

    def test_duplicates_point_at_their_originals(self, market):
        from app.catalog.models import Job

        original_1 = market.scalar(
            select(Job).where(Job.title_raw == "Job 1", Job.dedupe_group_id == Job.id)
        )
        exact_dup = market.scalar(
            select(Job).where(Job.title_raw == "Job 1", Job.id != Job.dedupe_group_id)
        )
        url_dup = market.scalar(select(Job).where(Job.title_raw == "Sr Job 13 (via agg)"))
        original_13 = market.scalar(select(Job).where(Job.title_raw == "Job 13"))

        assert original_1 is not None and exact_dup is not None
        assert exact_dup.dedupe_group_id == original_1.id
        assert url_dup.dedupe_group_id == original_13.id  # URL rule, titles differ
        assert original_13.dedupe_group_id == original_13.id

    def test_job_rows_exceed_counted_jobs(self, market):
        from app.catalog.models import Job

        assert market.scalar(select(func.count(Job.id))) == 27  # 25 + 2 duplicates
        assert _analysis(market).header.analyzed_jobs == 23  # unchanged by M5

    def test_duplicate_never_surfaces_in_search_rows(self, market):
        from app.catalog.models import Job

        predicate = job_predicate(resolve_filters(market, JobFilters()))
        ids = set(market.scalars(predicate))
        duplicate_ids = set(
            market.scalars(select(Job.id).where(Job.dedupe_group_id != Job.id))
        )
        assert ids.isdisjoint(duplicate_ids)
        assert len(ids) == 23
