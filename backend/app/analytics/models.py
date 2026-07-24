"""Derived-layer tables: rebuildable aggregates, never a source of truth.

`market_snapshots` is the day-one trends table — history that cannot be
recomputed later, captured at fixed coarse dimensions (cardinality
budgeting: dates × technologies × title families × ~31 geo buckets stays
small forever; snapshotting arbitrary query combinations would not).

`analysis_cache` holds dashboard payloads keyed by canonicalized filters.
Data changes only when the nightly pipeline runs, so entries are exactly
correct until the pipeline truncates the table as its final step.
"""

from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Geo bucket slug for rows that aggregate the whole country.
NATIONAL = "national"


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "technology_id",
            "canonical_title_id",
            "geo_slug",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_market_snapshots_tech_geo", "technology_id", "geo_slug", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date)
    technology_id: Mapped[int] = mapped_column(ForeignKey("technologies.id"))
    # NULL = all title families; a value scopes the count to one family.
    canonical_title_id: Mapped[int | None] = mapped_column(ForeignKey("canonical_titles.id"))
    geo_slug: Mapped[str] = mapped_column(default=NATIONAL)
    job_count: Mapped[int]


class SnapshotRun(Base):
    """One row per snapshot day: the denominator and the source mix.

    The source list is what makes trend lines honest — a demand jump the
    week a big source was added is the sampling changing, not the market,
    and this table is how the UI can annotate that.
    """

    __tablename__ = "snapshot_runs"

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    active_jobs: Mapped[int]
    sources: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AnalysisCache(Base):
    __tablename__ = "analysis_cache"

    cache_key: Mapped[str] = mapped_column(primary_key=True)
    # The canonicalized filters, stored for inspectability: "what query
    # produced this entry" must never require reversing a hash.
    filters: Mapped[dict] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class PipelineMeta(Base):
    """Key-value bookkeeping: the data_version row is bumped when pipeline
    output changes and versions every ETag the API hands out."""

    __tablename__ = "pipeline_meta"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
