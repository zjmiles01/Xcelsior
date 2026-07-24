"""Market analysis endpoints.

ETags are keyed to (data version, canonical filter key): a browser that
re-requests an unchanged dashboard gets a 304 with no body, and every ETag
in the wild dies the moment the nightly pipeline bumps the data version.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.schemas import (
    AnalysisResponse,
    LocationOption,
    MetaResponse,
    SkillDetailResponse,
    TechnologyOption,
    TitleOption,
)
from app.analytics.service import get_analysis, get_data_version
from app.analytics.skills import (
    canonical_slug_for_alias,
    get_skill_detail,
    scope_without,
    skill_cache_key,
)
from app.catalog.deps import filters_from_query
from app.catalog.filters import JobFilters
from app.catalog.models import Job, JobLocation
from app.catalog.taxonomy_models import CanonicalTitle, Technology
from app.core.db import get_db
from app.geo.resolver import load_geo_index

router = APIRouter(tags=["analytics"])

TOP_LOCATIONS = 40


def _etag(data_version: str, cache_key: str) -> str:
    return f'W/"{data_version}-{cache_key[:16]}"'


@router.get("/analysis", response_model=AnalysisResponse)
def analysis(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    filters: JobFilters = Depends(filters_from_query),
) -> AnalysisResponse | Response:
    etag = _etag(get_data_version(db), filters.cache_key())
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    result = get_analysis(db, filters)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"
    return result


@router.get("/skills/{slug}", response_model=SkillDetailResponse)
def skill_detail(
    slug: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    filters: JobFilters = Depends(filters_from_query),
) -> SkillDetailResponse | Response:
    slug = slug.lower()
    tech = db.scalar(select(Technology).where(Technology.slug == slug))
    if tech is None:
        # Alias-shaped slugs ("golang", "react-js") 301 to the canonical
        # page so shared links never fork a skill's identity.
        canonical = canonical_slug_for_alias(db, slug)
        if canonical is not None:
            url = request.url.replace(
                path=request.url.path.rsplit("/", 1)[0] + "/" + canonical
            )
            return RedirectResponse(str(url), status_code=301)
        raise HTTPException(status_code=404, detail=f"Unknown skill: {slug}")

    scope = scope_without(tech, filters)
    etag = _etag(get_data_version(db), skill_cache_key(tech.slug, scope))
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    result = get_skill_detail(db, tech, scope)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"
    return result


@router.get("/meta", response_model=MetaResponse)
def meta(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> MetaResponse | Response:
    data_version = get_data_version(db)
    etag = _etag(data_version, "meta")
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    titles = db.execute(
        select(CanonicalTitle.slug, CanonicalTitle.name).order_by(CanonicalTitle.name)
    ).all()
    technologies = db.execute(
        select(Technology.slug, Technology.name, Technology.category).order_by(Technology.name)
    ).all()

    # Locations offered in the picker: cities that actually have jobs,
    # busiest first, slugged via the geo index so links are stable.
    geo = load_geo_index()
    location_rows = db.execute(
        select(JobLocation.city, JobLocation.region, func.count(JobLocation.job_id.distinct()))
        .join(Job, Job.id == JobLocation.job_id)
        .where(Job.status == "active", JobLocation.city.is_not(None))
        .group_by(JobLocation.city, JobLocation.region)
        .order_by(func.count(JobLocation.job_id.distinct()).desc())
        .limit(TOP_LOCATIONS)
    ).all()
    locations = []
    for city_name, region, count in location_rows:
        city = geo.lookup(city_name, region)
        if city is not None:
            locations.append(LocationOption(slug=city.slug, label=city.label, job_count=count))

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=300"
    return MetaResponse(
        titles=[TitleOption(slug=s, name=n) for s, n in titles],
        technologies=[TechnologyOption(slug=s, name=n, category=c) for s, n, c in technologies],
        locations=locations,
        data_version=data_version,
    )
