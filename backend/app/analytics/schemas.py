"""The /analysis response contract.

Statistical honesty is enforced here, in the shape itself: every payload
carries its denominators (`analyzed_jobs`, `salary_disclosed`), every
percentage is percent-of-all-analyzed-jobs, and the low-confidence flag is
decided server-side so every client renders small samples the same way.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.catalog.filters import JobFilters


class TechnologyStat(BaseModel):
    slug: str
    name: str
    count: int
    # Fraction of all analyzed jobs in scope (0..1). A job with no detected
    # framework still counts in the denominator — "no framework specified"
    # is market information, not missing data.
    share: float
    required_count: int


class CategoryStats(BaseModel):
    category: str
    label: str
    technologies: list[TechnologyStat]
    distinct_technologies: int


class DistributionBucket(BaseModel):
    value: str  # e.g. "remote" | "hybrid" | "onsite" | "unspecified"
    count: int
    share: float


class SalarySummary(BaseModel):
    disclosed_count: int
    p25: int | None
    median: int | None
    p75: int | None


class CompanyStat(BaseModel):
    name: str
    count: int


class AnalysisHeader(BaseModel):
    analyzed_jobs: int
    salary_disclosed: int
    low_confidence: bool
    min_sample_size: int


class AnalysisResponse(BaseModel):
    filters: JobFilters
    header: AnalysisHeader
    categories: list[CategoryStats]
    arrangements: list[DistributionBucket]
    experience_levels: list[DistributionBucket]
    salary: SalarySummary
    top_companies: list[CompanyStat]
    computed_at: datetime
    data_version: str


class SkillHeader(BaseModel):
    slug: str
    name: str
    category: str
    # Denominator: jobs matching the scope *without* this skill filter —
    # "share" is "of the market you're looking at, how much wants this".
    analyzed_jobs: int
    jobs_with_tech: int
    share: float
    low_confidence: bool  # decided on jobs_with_tech, the sample every stat uses
    min_sample_size: int


class CoOccurrenceStat(BaseModel):
    """A technology that appears alongside this skill more often than its
    base rate in the same scope predicts (lift >= the floor)."""

    slug: str
    name: str
    category: str
    count: int  # jobs with both, in scope
    share_given_tech: float  # count / jobs_with_tech
    baseline_share: float  # jobs with the other tech / analyzed_jobs
    lift: float  # share_given_tech / baseline_share


class SkillSalary(BaseModel):
    """Percentiles over disclosed-salary jobs with this skill, plus the
    all-jobs national baseline the delta is measured against."""

    disclosed_count: int
    p25: int | None
    median: int | None
    p75: int | None
    national_median: int | None
    national_disclosed_count: int
    delta_vs_national: int | None  # median - national_median


class TrendPoint(BaseModel):
    snapshot_date: date
    job_count: int


class SkillTrend(BaseModel):
    # collecting_history: too few snapshot days for an honest trend line;
    # the UI must say so rather than draw a two-point "trend".
    status: Literal["ok", "collecting_history"]
    days_observed: int
    min_days: int
    geo_slug: str  # bucket the series comes from ("national" fallback included)
    points: list[TrendPoint]


class SkillDetailResponse(BaseModel):
    filters: JobFilters  # the scope, with this skill's own slug removed
    header: SkillHeader
    requirement_levels: list[DistributionBucket]  # over jobs_with_tech
    arrangements: list[DistributionBucket]  # over jobs_with_tech
    experience_levels: list[DistributionBucket]  # over jobs_with_tech
    co_occurring: list[CoOccurrenceStat]
    salary: SkillSalary
    trend: SkillTrend
    computed_at: datetime
    data_version: str


class TitleOption(BaseModel):
    slug: str
    name: str


class TechnologyOption(BaseModel):
    slug: str
    name: str
    category: str


class LocationOption(BaseModel):
    slug: str
    label: str
    job_count: int


class MetaResponse(BaseModel):
    """Everything the filter UI needs to render its options."""

    titles: list[TitleOption]
    technologies: list[TechnologyOption]
    locations: list[LocationOption]
    data_version: str
