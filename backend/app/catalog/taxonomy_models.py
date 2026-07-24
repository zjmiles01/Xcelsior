"""Canonical taxonomy and per-job extraction results (canonical layer,
architecture §7). Populated by the extraction pipeline, owned here so the
query builder and API never depend on the pipeline package."""

from sqlalchemy import Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Technology(Base):
    """Canonical technology. The taxonomy YAML is the reviewable source of
    truth; load-taxonomy syncs it here."""

    __tablename__ = "technologies"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    category: Mapped[str] = mapped_column(index=True)


class TechnologyAlias(Base):
    __tablename__ = "technology_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    technology_id: Mapped[int] = mapped_column(ForeignKey("technologies.id"))
    alias: Mapped[str] = mapped_column(unique=True)
    cased: Mapped[str]
    case_sensitive: Mapped[bool] = mapped_column(default=False)
    require_context: Mapped[bool] = mapped_column(default=False)


class CanonicalTitle(Base):
    __tablename__ = "canonical_titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]


class TitleAlias(Base):
    __tablename__ = "title_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title_id: Mapped[int] = mapped_column(ForeignKey("canonical_titles.id"))
    alias: Mapped[str] = mapped_column(unique=True)


class JobTechnology(Base):
    """One extracted technology per job, with the evidence that makes every
    downstream statistic traceable to a sentence in a real posting."""

    __tablename__ = "job_technologies"
    __table_args__ = (UniqueConstraint("job_id", "technology_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    technology_id: Mapped[int] = mapped_column(ForeignKey("technologies.id"), index=True)
    requirement_level: Mapped[str]  # required | preferred | mentioned
    confidence: Mapped[float] = mapped_column(Float)
    occurrences: Mapped[int] = mapped_column(default=1)
    extraction_method: Mapped[str] = mapped_column(default="rules")  # rules | llm
    extractor_version: Mapped[int]
    evidence_snippet: Mapped[str] = mapped_column(Text)
    evidence_start: Mapped[int]


class JobSection(Base):
    """Detected description sections; offsets index into jobs.description_text."""

    __tablename__ = "job_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    kind: Mapped[str]  # required | preferred | responsibilities | benefits
    start_offset: Mapped[int]
    end_offset: Mapped[int]
