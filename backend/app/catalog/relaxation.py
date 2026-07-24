"""Capped zero-result relaxation probing.

A zero-result search is a dead end the product created (the filters are
all our own vocabulary), so it owes the user a way out — but an honest
one. Only technology, salary, and radius are ever relaxed: dropping the
title or the text query would answer a different question than the one
asked, and no relaxation is applied silently — every option is returned
to the client labeled with what it changes and how many jobs it yields,
for the user to choose.

Work is capped by construction: at most 3 radius probes (stop at the
first bucket that helps), 1 salary probe, and 4 single-technology drops —
each a single COUNT over the shared predicate.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.filters import RADIUS_BUCKETS, JobFilters
from app.catalog.query import job_predicate, resolve_filters
from app.catalog.schemas import RelaxationOption

MAX_TECHNOLOGY_PROBES = 4


def probe_relaxations(db: Session, filters: JobFilters) -> list[RelaxationOption]:
    def count(relaxed: JobFilters) -> int:
        predicate = job_predicate(resolve_filters(db, relaxed))
        return db.scalar(select(func.count()).select_from(predicate.subquery())) or 0

    options: list[RelaxationOption] = []

    if filters.location is not None:
        for bucket in RADIUS_BUCKETS:
            if bucket <= filters.radius_miles:
                continue
            relaxed = filters.model_copy(update={"radius_miles": bucket})
            if matches := count(relaxed):
                options.append(
                    RelaxationOption(
                        kind="radius",
                        description=f"Widen the search radius to {bucket} miles",
                        filters=relaxed,
                        count=matches,
                    )
                )
                break

    if filters.salary_min is not None:
        relaxed = filters.model_copy(update={"salary_min": None})
        if matches := count(relaxed):
            options.append(
                RelaxationOption(
                    kind="salary",
                    description="Remove the salary floor (jobs without disclosed salary are"
                    " excluded by it)",
                    filters=relaxed,
                    count=matches,
                )
            )

    for slug in filters.technologies[:MAX_TECHNOLOGY_PROBES]:
        remaining = tuple(t for t in filters.technologies if t != slug)
        relaxed = filters.model_copy(update={"technologies": remaining})
        if matches := count(relaxed):
            options.append(
                RelaxationOption(
                    kind="technology",
                    description=f"Search without {slug}",
                    filters=relaxed,
                    count=matches,
                )
            )

    return options
