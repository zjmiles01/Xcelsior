"""FastAPI dependencies for the filter contract.

Explicit query parameters (rather than a model with extra="forbid") so
every filter is individually documented in OpenAPI and coexists with
endpoint-specific params like `limit`.
"""

from typing import Annotated

from fastapi import Query

from app.catalog.filters import DEFAULT_RADIUS, Arrangement, ExperienceLevel, JobFilters


def filters_from_query(
    q: Annotated[str | None, Query(description="Free-text query (websearch syntax)")] = None,
    title: Annotated[str | None, Query(description="Canonical title family slug")] = None,
    location: Annotated[str | None, Query(description="City slug, e.g. san-francisco-ca")] = None,
    radius_miles: Annotated[int, Query(ge=1, le=500)] = DEFAULT_RADIUS,
    tech: Annotated[list[str], Query(description="Technology slugs (AND)")] = [],  # noqa: B006
    arrangement: Annotated[Arrangement | None, Query()] = None,
    experience_level: Annotated[ExperienceLevel | None, Query()] = None,
    salary_min: Annotated[int | None, Query(ge=0, description="Annual USD floor")] = None,
) -> JobFilters:
    return JobFilters(
        q=q,
        title=title,
        location=location,
        radius_miles=radius_miles,
        technologies=tuple(tech),
        arrangement=arrangement,
        experience_level=experience_level,
        salary_min=salary_min,
    )
