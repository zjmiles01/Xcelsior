"""Search-surface mechanics: sort orders, keyset cursors, facet counts.

Pagination is keyset, not offset: offset pages drift when the nightly
pipeline inserts rows (the same job appears on two pages, or vanishes),
and OFFSET N scans N rows to throw them away. A cursor pins the scan to
"strictly after the last row you saw" under a total order (sort key, id).

NULL sort keys are coalesced to sentinels (epoch / -1) so the key is
always comparable and NULL rows land at the end of the descending scan —
which is what makes the tuple comparison in `apply_keyset` sound.

Cursors are opaque but not trusted: each one carries the sort option and
a fingerprint of the canonical filters it belongs to, and a cursor
presented against a different query fails loudly (422) instead of
silently returning rows from the wrong ordering.
"""

import base64
import binascii
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Double, Select, case, cast, func, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.catalog.filters import JobFilters
from app.catalog.models import Job
from app.catalog.schemas import FacetBucket, SearchFacets, SortOption

DEFAULT_SORT: SortOption = "recency"

# Descending-sort sentinels for NULL keys: older than any posted_at,
# lower than any salary.
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
NO_SALARY = Decimal(-1)


class InvalidCursor(ValueError):
    """Cursor is malformed or belongs to a different query."""


def sort_key(sort: SortOption, filters: JobFilters) -> ColumnElement:
    """The non-null column expression the scan is ordered by (descending)."""
    if sort == "salary":
        return func.coalesce(Job.salary_annual_max, NO_SALARY)
    if sort == "relevance":
        # Router guarantees filters.q is set for relevance sort. The cast
        # matters: ts_rank_cd returns real (float4), whose shortest text
        # form does not round-trip through a float8 cursor value — the
        # keyset comparison would quietly skip every remaining row.
        return cast(
            func.ts_rank_cd(Job.search_tsv, func.websearch_to_tsquery("english", filters.q)),
            Double,
        )
    return func.coalesce(Job.posted_at, EPOCH)


def apply_keyset(
    stmt: Select, key: ColumnElement, sort: SortOption, filters: JobFilters, cursor: str | None
) -> Select:
    stmt = stmt.order_by(key.desc(), Job.id.desc())
    if cursor is not None:
        key_value, job_id = _decode_cursor(cursor, sort, filters)
        stmt = stmt.where(tuple_(key, Job.id) < tuple_(key_value, job_id))
    return stmt


def encode_cursor(sort: SortOption, filters: JobFilters, key_value: Any, job_id: int) -> str:
    if isinstance(key_value, datetime):
        serialized: str | float = key_value.isoformat()
    elif isinstance(key_value, Decimal):
        serialized = str(key_value)
    else:
        serialized = float(key_value)
    payload = {"s": sort, "f": _fingerprint(filters), "k": serialized, "id": job_id}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str, sort: SortOption, filters: JobFilters) -> tuple[Any, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
        serialized = payload["k"]
        job_id = int(payload["id"])
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError,
            ValueError) as exc:
        raise InvalidCursor("Malformed cursor") from exc
    if payload.get("s") != sort or payload.get("f") != _fingerprint(filters):
        raise InvalidCursor("Cursor does not belong to this query; restart from the first page")
    try:
        if sort == "salary":
            return Decimal(str(serialized)), job_id
        if sort == "relevance":
            return float(serialized), job_id
        return datetime.fromisoformat(str(serialized)), job_id
    except (InvalidOperation, ValueError) as exc:
        raise InvalidCursor("Malformed cursor") from exc


def _fingerprint(filters: JobFilters) -> str:
    return filters.cache_key()[:12]


def facet_counts(db: Session, matching, total: int) -> SearchFacets:
    """Arrangement / experience counts over the full matching set.

    Same shape rules as the dashboard distributions: NULL is an explicit
    "unspecified" bucket and shares are out of all matching jobs, so the
    buckets always sum to the total the user is looking at.
    """

    def dist(column) -> list[FacetBucket]:
        value = case((column.is_(None), "unspecified"), else_=column).label("value")
        rows = db.execute(
            select(value, func.count().label("count"))
            .select_from(matching)
            .join(Job, Job.id == matching.c.id)
            .group_by(value)
            .order_by(func.count().desc(), value)
        ).all()
        return [FacetBucket(value=v, count=c, share=c / total if total else 0.0) for v, c in rows]

    return SearchFacets(
        arrangements=dist(Job.arrangement),
        experience_levels=dist(Job.experience_level),
    )
