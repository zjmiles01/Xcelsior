"""Nightly market snapshots at fixed coarse dimensions.

Trends cannot be recomputed from current data — if we don't write today's
counts down today, they are gone. Rows are date × technology ×
title-family (NULL = all) × geo bucket (national + top metros), the
cardinality-budgeted grid from §7: only nonzero combinations are stored.

Each geo bucket resolves through the same shared query builder as the
dashboard and search, so a snapshot row is exactly "what the dashboard
would have said that day".
"""

from datetime import UTC, datetime
from datetime import date as date_type

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.analytics.models import NATIONAL, MarketSnapshot, SnapshotRun
from app.catalog.filters import JobFilters
from app.catalog.models import Job, JobLocation
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.taxonomy_models import JobTechnology
from app.geo.resolver import load_geo_index
from app.ingestion.models import Source

log = structlog.get_logger()

TOP_METROS = 30
METRO_RADIUS_MILES = 25


def _metro_slugs(db: Session) -> list[str]:
    """Busiest metros by active-job count, slugged via the geo index.

    Recomputed each run: a metro that falls out of the top set simply
    stops accruing rows (sparse series), while big metros stay stable.
    """
    geo = load_geo_index()
    rows = db.execute(
        select(JobLocation.city, JobLocation.region, func.count(JobLocation.job_id.distinct()))
        .join(Job, Job.id == JobLocation.job_id)
        .where(Job.status == "active", JobLocation.city.is_not(None))
        .group_by(JobLocation.city, JobLocation.region)
        .order_by(func.count(JobLocation.job_id.distinct()).desc())
        .limit(TOP_METROS)
    ).all()
    slugs = []
    for city_name, region, _count in rows:
        city = geo.lookup(city_name, region)
        if city is not None:
            slugs.append(city.slug)
    return slugs


def capture_snapshot(db: Session, snapshot_date: date_type | None = None) -> dict[str, int]:
    """Write today's counts. Idempotent: re-running a day replaces it."""
    snapshot_date = snapshot_date or datetime.now(UTC).date()
    db.execute(delete(MarketSnapshot).where(MarketSnapshot.snapshot_date == snapshot_date))

    buckets = [NATIONAL, *_metro_slugs(db)]
    rows_written = 0
    for geo_slug in buckets:
        filters = (
            JobFilters()
            if geo_slug == NATIONAL
            else JobFilters(location=geo_slug, radius_miles=METRO_RADIUS_MILES)
        )
        matching = job_predicate(resolve_filters(db, filters)).cte(f"snap_{geo_slug[:40]}")

        # Two grouped queries per bucket: the all-families rollup, then
        # per-family detail. (Deliberately not GROUPING SETS — at ~31
        # buckets the extra query is free and the code stays obvious.)
        rollup = db.execute(
            select(
                JobTechnology.technology_id,
                func.count(JobTechnology.job_id.distinct()),
            )
            .select_from(matching)
            .join(JobTechnology, JobTechnology.job_id == matching.c.id)
            .group_by(JobTechnology.technology_id)
        ).all()
        for tech_id, count in rollup:
            db.add(
                MarketSnapshot(
                    snapshot_date=snapshot_date,
                    technology_id=tech_id,
                    canonical_title_id=None,
                    geo_slug=geo_slug,
                    job_count=count,
                )
            )
            rows_written += 1

        detail = db.execute(
            select(
                JobTechnology.technology_id,
                Job.canonical_title_id,
                func.count(JobTechnology.job_id.distinct()),
            )
            .select_from(matching)
            .join(JobTechnology, JobTechnology.job_id == matching.c.id)
            .join(Job, Job.id == matching.c.id)
            # Unresolved-title jobs are represented in the rollup row; a
            # NULL-family detail row would just duplicate it.
            .where(Job.canonical_title_id.is_not(None))
            .group_by(JobTechnology.technology_id, Job.canonical_title_id)
        ).all()
        for tech_id, title_id, count in detail:
            db.add(
                MarketSnapshot(
                    snapshot_date=snapshot_date,
                    technology_id=tech_id,
                    canonical_title_id=title_id,
                    geo_slug=geo_slug,
                    job_count=count,
                )
            )
            rows_written += 1

    national_predicate = job_predicate(resolve_filters(db, JobFilters()))
    active_jobs = db.scalar(select(func.count()).select_from(national_predicate.subquery())) or 0
    source_names = list(
        db.scalars(
            select(Source.name)
            .join(Job, Job.source_id == Source.id)
            .where(Job.status == "active")
            .distinct()
            .order_by(Source.name)
        )
    )
    db.merge(
        SnapshotRun(
            snapshot_date=snapshot_date,
            active_jobs=active_jobs,
            sources={"names": source_names},
        )
    )
    db.commit()
    log.info(
        "snapshot_captured",
        snapshot_date=str(snapshot_date),
        buckets=len(buckets),
        rows=rows_written,
    )
    return {"buckets": len(buckets), "rows": rows_written, "active_jobs": active_jobs}
