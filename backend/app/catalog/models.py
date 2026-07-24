from datetime import datetime
from decimal import Decimal

from sqlalchemy import Computed, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats_type", "ats_token"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    name_normalized: Mapped[str] = mapped_column(index=True)
    domain: Mapped[str | None] = mapped_column(index=True)
    ats_type: Mapped[str | None]  # greenhouse | lever | ashby
    ats_token: Mapped[str | None]


class Job(Base):
    """Canonical job posting. One row per deduplicated posting; salary kept
    in both as-stated and normalized-annual-USD forms (aggregates use the
    normalized form, display uses the raw form)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_posting_id: Mapped[int] = mapped_column(ForeignKey("raw_postings.id"), unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)

    title_raw: Mapped[str]
    canonical_title_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_titles.id"), index=True
    )
    description: Mapped[str | None] = mapped_column(Text)  # raw board HTML, unsanitized
    description_text: Mapped[str | None] = mapped_column(Text)  # extraction-time plain text
    # Sanitized display HTML (M8): safe formatting subset of `description`,
    # produced by extraction and the only description form served for rich
    # rendering. Never render `description` directly — it is untrusted.
    description_html: Mapped[str | None] = mapped_column(Text)
    apply_url: Mapped[str | None]

    employment_type: Mapped[str | None]  # full_time | part_time | contract | internship
    arrangement: Mapped[str | None]  # onsite | hybrid | remote
    experience_level: Mapped[str | None]  # entry | mid | senior | staff_plus
    years_of_experience: Mapped[int | None]

    extractor_version: Mapped[int | None] = mapped_column(index=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None]
    salary_period: Mapped[str | None]  # year | hour
    salary_annual_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_annual_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Database-generated (GIN-indexed): can never drift from the text it
    # indexes. Deferred — it's bulky and only the predicate reads it.
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', title_raw || ' ' || coalesce(description_text, ''))",
            persisted=True,
        ),
        deferred=True,
    )

    # Cross-source dedup (M5): id of this posting's group representative —
    # the single row per duplicate group that statistics count. NULL and
    # self-reference both mean "this row counts"; any other value means a
    # sibling row represents it. Assigned by `xcelsior dedupe`; rows are
    # never deleted, so provenance survives grouping.
    dedupe_group_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), index=True)

    status: Mapped[str] = mapped_column(default="active", index=True)  # active | expired
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped[Company] = relationship(lazy="joined")
    locations: Mapped[list["JobLocation"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class JobLocation(Base):
    """Separate table because postings are frequently multi-location and the
    counting rules depend on treating locations as first-class rows."""

    __tablename__ = "job_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    raw_text: Mapped[str]
    city: Mapped[str | None]
    region: Mapped[str | None]  # US state code once geocoding lands (M3)
    country: Mapped[str | None] = mapped_column(default="US")
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    is_remote: Mapped[bool] = mapped_column(default=False)

    job: Mapped[Job] = relationship(back_populates="locations")
