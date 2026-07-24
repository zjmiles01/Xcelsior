"""Snapshot rows over the micro-market, checked against hand-computed
truth (see tests/micro_market.py docstring)."""

from datetime import date

import pytest
from sqlalchemy import select

from app.analytics.models import NATIONAL, MarketSnapshot, SnapshotRun
from app.analytics.snapshots import capture_snapshot
from app.catalog.taxonomy_models import CanonicalTitle, Technology
from tests.micro_market import seed_micro_market

DAY = date(2026, 7, 19)


@pytest.fixture
def market(db):
    seed_micro_market(db)
    return db


def _rows(db, tech_slug: str, geo: str):
    return db.execute(
        select(MarketSnapshot.canonical_title_id, MarketSnapshot.job_count)
        .join(Technology, Technology.id == MarketSnapshot.technology_id)
        .where(
            Technology.slug == tech_slug,
            MarketSnapshot.geo_slug == geo,
            MarketSnapshot.snapshot_date == DAY,
        )
    ).all()


def test_national_rollup_and_family_detail(market):
    capture_snapshot(market, DAY)

    backend_id = market.scalar(
        select(CanonicalTitle.id).where(CanonicalTitle.slug == "backend-engineer")
    )
    python = dict(_rows(market, "python", NATIONAL))
    # All-families rollup (None) = 13; backend detail = 10 (6 SF + 2
    # Oakland + 2 San Jose); ML detail = 3.
    assert python[None] == 13
    assert python[backend_id] == 10

    go = dict(_rows(market, "go", NATIONAL))
    assert go == {None: 2, backend_id: 2}


def test_metro_bucket_counts(market):
    capture_snapshot(market, DAY)
    # SF @25mi: 6 SF + 2 Oakland + 2 multi-location have python? Multi
    # jobs carry go, not python: python in SF bucket = 6 + 2 Oakland = 8.
    python_sf = dict(_rows(market, "python", "san-francisco-ca"))
    assert python_sf[None] == 8
    react_nyc = dict(_rows(market, "react", "new-york-city-ny"))
    assert react_nyc[None] == 5


def test_rerun_is_idempotent(market):
    capture_snapshot(market, DAY)
    first = market.scalar(
        select(MarketSnapshot.id).where(MarketSnapshot.snapshot_date == DAY).limit(1)
    )
    result = capture_snapshot(market, DAY)
    total = market.scalar(
        select(MarketSnapshot.id)
        .where(MarketSnapshot.snapshot_date == DAY)
        .limit(1)
        .offset(result["rows"])
    )
    assert first is not None
    assert total is None  # exactly `rows` rows exist, not 2x


def test_run_metadata_records_source_mix(market):
    capture_snapshot(market, DAY)
    run = market.get(SnapshotRun, DAY)
    assert run is not None
    assert run.active_jobs == 23
    # M5: the aggregator source joins the honesty record, even though its
    # two duplicate rows are dedup-hidden from every count.
    assert run.sources == {"names": ["micro", "micro-agg"]}
