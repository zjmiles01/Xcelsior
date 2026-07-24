"""On-demand market aggregation over the shared predicate, with a
read-through cache.

The matching-job set is resolved once (a CTE) and every aggregate joins
against it — the same predicate the search endpoint uses, which is what
makes every dashboard number equal its click-through search count.

Caching: data changes only when the nightly pipeline runs, so cached
payloads are exactly correct — not approximately — until the pipeline
truncates the cache and bumps the data version as its final step.
"""

from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.analytics.models import AnalysisCache, PipelineMeta
from app.analytics.schemas import (
    AnalysisHeader,
    AnalysisResponse,
    CategoryStats,
    CompanyStat,
    DistributionBucket,
    SalarySummary,
    TechnologyStat,
)
from app.catalog.filters import JobFilters
from app.catalog.models import Company, Job
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.taxonomy_models import JobTechnology, Technology

MIN_SAMPLE_SIZE = 30
TECHNOLOGIES_PER_CATEGORY = 12
TOP_COMPANIES = 10

# Fixed presentation order; also the order the taxonomy YAML documents.
CATEGORY_LABELS = {
    "languages": "Languages",
    "frameworks": "Frameworks",
    "cloud": "Cloud",
    "infrastructure": "Infrastructure & DevOps",
    "databases": "Databases",
    "testing": "Testing",
    "messaging": "Messaging & Streaming",
    "data_engineering": "Data Engineering",
    "ai_ml": "AI / ML",
    "security": "Security",
}

DATA_VERSION_KEY = "data_version"


def get_data_version(db: Session) -> str:
    row = db.get(PipelineMeta, DATA_VERSION_KEY)
    return row.value if row else "initial"


def bump_data_version(db: Session) -> str:
    """Pipeline's final step: invalidate every cached payload at once."""
    version = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    db.execute(AnalysisCache.__table__.delete())
    stmt = pg_insert(PipelineMeta).values(
        key=DATA_VERSION_KEY, value=version, updated_at=datetime.now(UTC)
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": version, "updated_at": datetime.now(UTC)},
        )
    )
    db.commit()
    return version


def get_analysis(db: Session, filters: JobFilters) -> AnalysisResponse:
    """Read-through: serve the cached payload or compute and store it."""
    key = filters.cache_key()
    cached = db.get(AnalysisCache, key)
    if cached is not None:
        return AnalysisResponse.model_validate(cached.payload)

    response = compute_analysis(db, filters)
    stmt = pg_insert(AnalysisCache).values(
        cache_key=key,
        filters=filters.canonical_dict(),
        payload=response.model_dump(mode="json"),
        computed_at=response.computed_at,
    )
    # Two concurrent cold requests may both compute; either result is
    # correct (same data version), so the first write wins quietly.
    db.execute(stmt.on_conflict_do_nothing(index_elements=["cache_key"]))
    db.commit()
    return response


def compute_analysis(db: Session, filters: JobFilters) -> AnalysisResponse:
    resolved = resolve_filters(db, filters)
    matching = job_predicate(resolved).cte("matching_jobs")
    m_id = matching.c.id

    total = db.scalar(select(func.count()).select_from(matching)) or 0

    # ── Salary, over the disclosed subset only ──────────────────────────
    midpoint = (Job.salary_annual_min + Job.salary_annual_max) / 2
    salary_row = db.execute(
        select(
            func.count(),
            func.percentile_cont(0.25).within_group(midpoint),
            func.percentile_cont(0.5).within_group(midpoint),
            func.percentile_cont(0.75).within_group(midpoint),
        )
        .select_from(matching)
        .join(Job, Job.id == m_id)
        .where(Job.salary_annual_min.is_not(None))
    ).one()
    disclosed = salary_row[0] or 0
    salary = SalarySummary(
        disclosed_count=disclosed,
        p25=round(salary_row[1]) if salary_row[1] is not None else None,
        median=round(salary_row[2]) if salary_row[2] is not None else None,
        p75=round(salary_row[3]) if salary_row[3] is not None else None,
    )

    # ── Per-category technology demand ──────────────────────────────────
    tech_rows = db.execute(
        select(
            Technology.category,
            Technology.slug,
            Technology.name,
            func.count(JobTechnology.job_id.distinct()).label("count"),
            func.count(JobTechnology.job_id.distinct())
            .filter(JobTechnology.requirement_level == "required")
            .label("required_count"),
        )
        .select_from(matching)
        .join(JobTechnology, JobTechnology.job_id == m_id)
        .join(Technology, Technology.id == JobTechnology.technology_id)
        .group_by(Technology.category, Technology.slug, Technology.name)
        .order_by(func.count(JobTechnology.job_id.distinct()).desc(), Technology.name)
    ).all()

    by_category: dict[str, list[TechnologyStat]] = {c: [] for c in CATEGORY_LABELS}
    distinct_counts: dict[str, int] = dict.fromkeys(CATEGORY_LABELS, 0)
    for category, slug, name, count, required_count in tech_rows:
        distinct_counts[category] += 1
        if len(by_category[category]) < TECHNOLOGIES_PER_CATEGORY:
            by_category[category].append(
                TechnologyStat(
                    slug=slug,
                    name=name,
                    count=count,
                    share=count / total if total else 0.0,
                    required_count=required_count,
                )
            )
    categories = [
        CategoryStats(
            category=category,
            label=label,
            technologies=by_category[category],
            distinct_technologies=distinct_counts[category],
        )
        for category, label in CATEGORY_LABELS.items()
    ]

    # ── Distributions (unspecified is a bucket, not an omission) ────────
    arrangements = distribution(db, matching, Job.arrangement, total)
    experience_levels = distribution(db, matching, Job.experience_level, total)

    # ── Top companies ───────────────────────────────────────────────────
    company_rows = db.execute(
        select(Company.name, func.count().label("count"))
        .select_from(matching)
        .join(Job, Job.id == m_id)
        .join(Company, Company.id == Job.company_id)
        .group_by(Company.name)
        .order_by(func.count().desc(), Company.name)
        .limit(TOP_COMPANIES)
    ).all()

    return AnalysisResponse(
        filters=filters,
        header=AnalysisHeader(
            analyzed_jobs=total,
            salary_disclosed=disclosed,
            low_confidence=total < MIN_SAMPLE_SIZE,
            min_sample_size=MIN_SAMPLE_SIZE,
        ),
        categories=categories,
        arrangements=arrangements,
        experience_levels=experience_levels,
        salary=salary,
        top_companies=[CompanyStat(name=n, count=c) for n, c in company_rows],
        computed_at=datetime.now(UTC),
        data_version=get_data_version(db),
    )


def distribution(db: Session, matching, column, total: int) -> list[DistributionBucket]:
    value = case((column.is_(None), "unspecified"), else_=column).label("value")
    rows = db.execute(
        select(value, func.count().label("count"))
        .select_from(matching)
        .join(Job, Job.id == matching.c.id)
        .group_by(value)
        .order_by(func.count().desc())
    ).all()
    return [
        DistributionBucket(value=v, count=c, share=c / total if total else 0.0) for v, c in rows
    ]
