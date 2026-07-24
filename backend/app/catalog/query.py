"""The shared query builder: canonical filters -> matching-jobs predicate.

Every number the product shows and every job list it returns must resolve
through `job_predicate`. Duplicated predicate logic drifts — one surface
includes expired jobs, another double-counts multi-location postings —
and drift between a dashboard stat and its click-through search result is
the product's trust-killer. One builder makes drift structurally
impossible.

Counting rule (architecture §2): a job posted in five cities is one job.
Geographic filters use EXISTS over job_locations, so a job matches when
*any* location qualifies but is never counted twice.
"""

from dataclasses import dataclass

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from app.catalog.filters import JobFilters
from app.catalog.models import Job, JobLocation
from app.catalog.taxonomy_models import CanonicalTitle, JobTechnology, Technology
from app.geo.resolver import City, load_geo_index

MILES_TO_METERS = 1609.344


class UnknownFilterValue(ValueError):
    """A filter references a slug that doesn't exist (bad URL, stale link)."""

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"Unknown {field}: {value!r}")


@dataclass(frozen=True)
class ResolvedFilters:
    """Filters with slugs resolved against the taxonomy and geo index."""

    filters: JobFilters
    title_id: int | None
    technology_ids: tuple[int, ...]
    city: City | None


def resolve_filters(db: Session, filters: JobFilters) -> ResolvedFilters:
    """Resolve slugs to ids/coordinates, failing loudly on unknown values.

    A typo'd or stale slug must 422 rather than silently match nothing —
    an empty result labeled "0 jobs use Python" would be a lie.
    """
    title_id: int | None = None
    if filters.title:
        title_id = db.scalar(select(CanonicalTitle.id).where(CanonicalTitle.slug == filters.title))
        if title_id is None:
            raise UnknownFilterValue("title", filters.title)

    technology_ids: list[int] = []
    for slug in filters.technologies:
        tech_id = db.scalar(select(Technology.id).where(Technology.slug == slug))
        if tech_id is None:
            raise UnknownFilterValue("technology", slug)
        technology_ids.append(tech_id)

    city: City | None = None
    if filters.location:
        city = load_geo_index().by_slug(filters.location)
        if city is None:
            raise UnknownFilterValue("location", filters.location)

    return ResolvedFilters(
        filters=filters,
        title_id=title_id,
        technology_ids=tuple(technology_ids),
        city=city,
    )


def job_predicate(resolved: ResolvedFilters) -> Select:
    """Return a Select of matching active job ids — the one shared truth."""
    f = resolved.filters
    stmt = select(Job.id).where(Job.status == "active")

    # Cross-source dedup (ADR-004): only a group's representative row
    # counts. NULL (ungrouped) and self-reference both mean "counts";
    # any other value means a sibling row represents this posting.
    stmt = stmt.where((Job.dedupe_group_id.is_(None)) | (Job.dedupe_group_id == Job.id))

    if f.q:
        stmt = stmt.where(Job.search_tsv.op("@@")(func.websearch_to_tsquery("english", f.q)))

    if resolved.title_id is not None:
        stmt = stmt.where(Job.canonical_title_id == resolved.title_id)

    for tech_id in resolved.technology_ids:
        stmt = stmt.where(
            exists(
                select(1).where(
                    JobTechnology.job_id == Job.id,
                    JobTechnology.technology_id == tech_id,
                )
            )
        )

    if f.arrangement is not None:
        stmt = stmt.where(Job.arrangement == f.arrangement)

    if f.experience_level is not None:
        stmt = stmt.where(Job.experience_level == f.experience_level)

    if f.salary_min is not None:
        # A job qualifies if any part of its disclosed range clears the
        # floor. Jobs without disclosed salary are excluded — the UI owes
        # users a note about that (search surface, M4).
        stmt = stmt.where(Job.salary_annual_max >= f.salary_min)

    if resolved.city is not None:
        stmt = stmt.where(
            exists(
                select(1).where(
                    JobLocation.job_id == Job.id,
                    JobLocation.latitude.is_not(None),
                    func.earth_distance(
                        func.ll_to_earth(JobLocation.latitude, JobLocation.longitude),
                        func.ll_to_earth(resolved.city.latitude, resolved.city.longitude),
                    )
                    <= f.radius_miles * MILES_TO_METERS,
                )
            )
        )

    return stmt
