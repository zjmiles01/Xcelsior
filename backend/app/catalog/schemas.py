from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.catalog.filters import JobFilters

SortOption = Literal["recency", "salary", "relevance"]


class JobLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_text: str
    is_remote: bool


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title_raw: str
    company_name: str
    apply_url: str | None
    posted_at: datetime | None
    locations: list[JobLocationOut]


class FacetBucket(BaseModel):
    value: str  # e.g. "remote" | "senior" | "unspecified"
    count: int
    share: float  # of all matching jobs, so buckets sum to the total


class SearchFacets(BaseModel):
    """Counts over the full matching set, not just the returned page."""

    arrangements: list[FacetBucket]
    experience_levels: list[FacetBucket]


class RelaxationOption(BaseModel):
    """One honest way out of a zero-result search: what would change,
    and how many jobs that buys. Never applied server-side."""

    kind: Literal["radius", "salary", "technology"]
    description: str
    filters: JobFilters  # the full relaxed filter set, ready to link to
    count: int


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    sort: SortOption
    facets: SearchFacets
    # Present iff another page exists; opaque, bound to this sort + filters.
    next_cursor: str | None
    # Populated only when total == 0: capped relaxation probes of
    # technology / salary / radius (never title or text query).
    relaxations: list[RelaxationOption] = []


class SalaryOut(BaseModel):
    """Both representations, deliberately: raw for honest display
    ('$60/hr'), normalized annual USD for anything comparative."""

    min_amount: Decimal | None
    max_amount: Decimal | None
    currency: str | None
    period: str | None
    annual_min: Decimal | None
    annual_max: Decimal | None


class JobTechnologyOut(BaseModel):
    slug: str
    name: str
    category: str
    requirement_level: str
    confidence: float
    evidence_snippet: str
    evidence_start: int


class JobSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    start_offset: int
    end_offset: int


class SourceOut(BaseModel):
    name: str
    display_policy: str
    attribution_text: str | None
    attribution_url: str | None


class JobDetail(BaseModel):
    id: int
    title_raw: str
    canonical_title: str | None
    canonical_title_slug: str | None
    company_name: str
    locations: list[JobLocationOut]
    arrangement: str | None
    experience_level: str | None
    years_of_experience: int | None
    employment_type: str | None
    salary: SalaryOut
    status: str
    posted_at: datetime | None
    last_seen_at: datetime
    apply_url: str | None
    description_text: str | None
    # Sanitized HTML safe to render directly; same display-policy gate as
    # description_text. Prefer this over description_text for rich display.
    description_html: str | None
    sections: list[JobSectionOut]
    technologies: list[JobTechnologyOut]
    source: SourceOut
