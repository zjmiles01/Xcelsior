from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.deps import filters_from_query
from app.catalog.filters import JobFilters
from app.catalog.models import Job
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.relaxation import probe_relaxations
from app.catalog.schemas import (
    JobDetail,
    JobListItem,
    JobListResponse,
    JobSectionOut,
    JobTechnologyOut,
    SalaryOut,
    SortOption,
    SourceOut,
)
from app.catalog.search import DEFAULT_SORT, apply_keyset, encode_cursor, facet_counts, sort_key
from app.catalog.taxonomy_models import CanonicalTitle, JobSection, JobTechnology, Technology
from app.core.db import get_db
from app.ingestion.models import Source

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    filters: JobFilters = Depends(filters_from_query),
    limit: int = Query(50, ge=1, le=100),
    sort: SortOption = Query(DEFAULT_SORT),
    cursor: str | None = Query(None, description="Opaque keyset cursor from a previous page"),
) -> JobListResponse:
    """List matching active jobs with facet counts and keyset pagination.

    Both the count and the rows come from the shared predicate — this is
    the endpoint dashboard stats click through to, and its total must
    always equal the number the user clicked."""
    if sort == "relevance" and not filters.q:
        raise HTTPException(status_code=422, detail="sort=relevance requires a text query (q)")

    resolved = resolve_filters(db, filters)
    matching = job_predicate(resolved).cte("matching_jobs")
    total = db.scalar(select(func.count()).select_from(matching)) or 0
    facets = facet_counts(db, matching, total)

    # Fetch one extra row: its existence is the "another page" signal, and
    # the cursor is built from the DB-computed key of the last *returned*
    # row, so the next page's tuple comparison uses identical values.
    key = sort_key(sort, filters)
    stmt = (
        select(Job, key.label("sort_key"))
        .join(matching, matching.c.id == Job.id)
        .limit(limit + 1)
    )
    rows = db.execute(apply_keyset(stmt, key, sort, filters, cursor)).all()

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last_job, last_key = rows[-1]
        next_cursor = encode_cursor(sort, filters, last_key, last_job.id)

    items = [
        JobListItem(
            id=job.id,
            title_raw=job.title_raw,
            company_name=job.company.name,
            apply_url=job.apply_url,
            posted_at=job.posted_at,
            locations=job.locations,
        )
        for job, _ in rows
    ]
    return JobListResponse(
        items=items,
        total=total,
        sort=sort,
        facets=facets,
        next_cursor=next_cursor,
        relaxations=probe_relaxations(db, filters) if total == 0 else [],
    )


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobDetail:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    source = db.get(Source, job.source_id)
    assert source is not None
    canonical = db.get(CanonicalTitle, job.canonical_title_id) if job.canonical_title_id else None

    technologies = db.execute(
        select(JobTechnology, Technology)
        .join(Technology, Technology.id == JobTechnology.technology_id)
        .where(JobTechnology.job_id == job.id)
        .order_by(JobTechnology.confidence.desc(), Technology.name)
    ).all()
    sections = db.scalars(
        select(JobSection).where(JobSection.job_id == job.id).order_by(JobSection.start_offset)
    ).all()

    return JobDetail(
        id=job.id,
        title_raw=job.title_raw,
        canonical_title=canonical.name if canonical else None,
        canonical_title_slug=canonical.slug if canonical else None,
        company_name=job.company.name,
        locations=job.locations,
        arrangement=job.arrangement,
        experience_level=job.experience_level,
        years_of_experience=job.years_of_experience,
        employment_type=job.employment_type,
        salary=SalaryOut(
            min_amount=job.salary_min,
            max_amount=job.salary_max,
            currency=job.salary_currency,
            period=job.salary_period,
            annual_min=job.salary_annual_min,
            annual_max=job.salary_annual_max,
        ),
        status=job.status,
        posted_at=job.posted_at,
        last_seen_at=job.last_seen_at,
        apply_url=job.apply_url,
        # Display policy enforcement: extracted-only sources never leak the
        # original text through this API, regardless of what the UI does.
        description_text=job.description_text if source.display_policy == "full_text" else None,
        description_html=job.description_html if source.display_policy == "full_text" else None,
        sections=[JobSectionOut.model_validate(s) for s in sections],
        technologies=[
            JobTechnologyOut(
                slug=tech.slug,
                name=tech.name,
                category=tech.category,
                requirement_level=jt.requirement_level,
                confidence=jt.confidence,
                evidence_snippet=jt.evidence_snippet,
                evidence_start=jt.evidence_start,
            )
            for jt, tech in technologies
        ],
        source=SourceOut(
            name=source.name,
            display_policy=source.display_policy,
            attribution_text=source.attribution_text,
            attribution_url=source.attribution_url,
        ),
    )
