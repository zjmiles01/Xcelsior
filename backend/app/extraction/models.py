"""Extraction process state. The canonical taxonomy and per-job
extraction results live in app.catalog.taxonomy_models — extraction is
the process that writes them, catalog is the layer that owns them."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReviewQueueItem(Base):
    """Unresolved extractions awaiting human curation: titles that didn't
    canonicalize and technology matches in the confidence doubt band.
    Upserted by (kind, value) with an occurrence counter so the queue stays
    proportional to distinct problems, not corpus size."""

    __tablename__ = "review_queue"
    __table_args__ = (UniqueConstraint("kind", "value"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]  # title | technology
    value: Mapped[str]
    example_context: Mapped[str | None] = mapped_column(Text)
    example_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    occurrences: Mapped[int] = mapped_column(default=1)
    # pending | resolved | dismissed
    status: Mapped[str] = mapped_column(default="pending", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
