from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Source(Base):
    """A data source we ingest from. display_policy governs whether the
    original description text may be shown or only our extracted structure."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str]  # ats_api | aggregator_api | gov_api
    display_policy: Mapped[str] = mapped_column(default="full_text")  # full_text | extracted_only
    attribution_text: Mapped[str | None]
    attribution_url: Mapped[str | None]
    enabled: Mapped[bool] = mapped_column(default=True)


class RawPosting(Base):
    """Immutable as-fetched payloads. The pipeline's system of record:
    every downstream table can be rebuilt from this one."""

    __tablename__ = "raw_postings"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IngestionRun(Base):
    """One row per connector per run; the source-breakage alarm reads this."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="running")  # running | succeeded | failed
    postings_fetched: Mapped[int] = mapped_column(default=0)
    postings_new: Mapped[int] = mapped_column(default=0)
    postings_updated: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)
