"""Batch geocoding of job locations against the canonical city index."""

from collections import Counter

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import JobLocation
from app.geo.resolver import load_geo_index

log = structlog.get_logger()

BATCH_SIZE = 2000


def geocode_locations(db: Session, redo: bool = False) -> dict[str, int]:
    """Resolve raw location strings to canonical cities and store coordinates.

    Idempotent: by default only rows without coordinates are attempted, so
    re-running after a dataset upgrade with `redo=True` reprocesses
    everything, while the nightly run touches only new rows.
    """
    index = load_geo_index()
    stmt = select(JobLocation)
    if not redo:
        stmt = stmt.where(JobLocation.latitude.is_(None))

    stats: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    rows = db.scalars(stmt.execution_options(yield_per=BATCH_SIZE))
    for loc in rows:
        stats["attempted"] += 1
        city = index.resolve(loc.raw_text)
        if city is None:
            unresolved[loc.raw_text] += 1
            stats["unresolved"] += 1
            continue
        loc.city = city.name
        loc.region = city.state
        loc.country = "US"
        loc.latitude = city.latitude  # type: ignore[assignment]
        loc.longitude = city.longitude  # type: ignore[assignment]
        stats["resolved"] += 1
    db.commit()

    for text, count in unresolved.most_common(15):
        log.info("geocode_unresolved", raw_text=text, occurrences=count)
    return dict(stats)
