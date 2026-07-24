"""Cross-source deduplication: deterministic grouping, no deletion.

The same real-world posting reachable from two sources must collapse to
one countable row before it reaches `job_predicate`, or every downstream
statistic double-counts. Two exact rules decide "same posting" (ADR-004):

1. **URL identity** — canonicalized apply URLs are equal.
2. **Exact key** — same company (exact normalized-name or exact domain
   match), same normalized title, and compatible locations.

Both rules apply only to jobs from *different* sources: two same-titled
postings on one company's own board are two real openings, not
duplicates (external_id uniqueness already guarantees one row each).
There is no fuzzy matching anywhere — a missed duplicate is recoverable
by improving the rules and re-running; a false merge silently corrupts
statistics. Rows are never deleted: every source's copy keeps its raw
posting, its evidence, and its attribution.

Assignment is a full, idempotent recompute: `dedupe_group_id` is set to
the group representative's id for every member, and cleared where a job
no longer belongs to any group. The whole corpus is loaded into memory —
fine well past 100k rows; revisit with blocking-in-SQL if that changes.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.catalog.models import Company, Job, JobLocation
from app.ingestion.models import Source

log = structlog.get_logger()

# Representative preference: the company's own board carries the fullest
# description and the best extraction; government API beats commercial
# aggregator on the same grounds.
KIND_RANK = {"ats_api": 0, "gov_api": 1, "aggregator_api": 2}


def canonical_apply_url(url: str) -> str | None:
    """Deterministic URL identity: case-normalized host/scheme, fragment
    dropped, utm_* stripped, remaining query params sorted, trailing
    slash trimmed. Query params are otherwise KEPT — some ATS boards put
    the job id in the query (`?gh_jid=...`), and dropping it would merge
    every posting on that board."""
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return None
    query = urlencode(
        sorted((k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_"))
    )
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _company_classes(db: Session) -> dict[int, int]:
    """Company identity across sources: exact normalized-name match or
    exact domain match. Returns company_id -> identity-class root."""
    uf = _UnionFind()
    by_name: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    for company_id, name_normalized, domain in db.execute(
        select(Company.id, Company.name_normalized, Company.domain)
    ):
        uf.find(company_id)
        if name_normalized:
            if name_normalized in by_name:
                uf.union(company_id, by_name[name_normalized])
            by_name.setdefault(name_normalized, company_id)
        if domain:
            key = domain.lower()
            if key in by_domain:
                uf.union(company_id, by_domain[key])
            by_domain.setdefault(key, company_id)
    return {cid: uf.find(cid) for cid in list(uf.parent)}


def assign_dedupe_groups(db: Session) -> dict[str, int]:
    """Recompute every job's dedupe_group_id from scratch. Idempotent."""
    source_kind = dict(db.execute(select(Source.id, Source.kind)).all())
    company_class = _company_classes(db)

    rows = db.execute(
        select(
            Job.id, Job.source_id, Job.company_id, Job.title_raw,
            Job.apply_url, Job.first_seen_at, Job.status, Job.dedupe_group_id,
        )
    ).all()

    geocoded: dict[int, set[tuple[str, str]]] = {}
    for job_id, city, region in db.execute(
        select(JobLocation.job_id, JobLocation.city, JobLocation.region).where(
            JobLocation.city.is_not(None), JobLocation.region.is_not(None)
        )
    ):
        geocoded.setdefault(job_id, set()).add((city.lower(), region))

    uf = _UnionFind()

    # Rule 1: URL identity across different sources.
    by_url: dict[str, list[tuple[int, int]]] = {}  # url -> [(job_id, source_id)]
    for row in rows:
        if not row.apply_url:
            continue
        url = canonical_apply_url(row.apply_url)
        if url is None:
            continue
        for other_id, other_source in by_url.setdefault(url, []):
            if other_source != row.source_id:
                uf.union(row.id, other_id)
        by_url[url].append((row.id, row.source_id))

    # Rule 2: exact key (company class, normalized title) with compatible
    # locations, across different sources. "Compatible" is an identical
    # geocoded (city, region) in common — or neither side geocoded at all
    # (e.g. both remote); a resolvable location conflict blocks the merge.
    by_key: dict[tuple[int, str], list] = {}
    for row in rows:
        key = (company_class.get(row.company_id, row.company_id), _normalize_title(row.title_raw))
        locations = geocoded.get(row.id, set())
        for other in by_key.setdefault(key, []):
            if other.source_id == row.source_id:
                continue
            other_locations = geocoded.get(other.id, set())
            if (locations and other_locations and locations & other_locations) or (
                not locations and not other_locations
            ):
                uf.union(row.id, other.id)
        by_key[key].append(row)

    groups: dict[int, list] = {}
    by_id = {row.id: row for row in rows}
    for job_id in uf.parent:
        groups.setdefault(uf.find(job_id), []).append(by_id[job_id])
    groups = {root: members for root, members in groups.items() if len(members) > 1}

    # Representative: active members first (an expired representative
    # would hide a posting that is still live on a sibling source), then
    # source-kind preference, then earliest first_seen_at, then lowest id.
    desired: dict[int, int] = {}
    for members in groups.values():
        representative = min(
            members,
            key=lambda m: (
                m.status != "active",
                KIND_RANK.get(source_kind.get(m.source_id), 99),
                m.first_seen_at,
                m.id,
            ),
        )
        for member in members:
            desired[member.id] = representative.id

    changed = 0
    for row in rows:
        target = desired.get(row.id)
        if row.dedupe_group_id != target:
            db.execute(update(Job).where(Job.id == row.id).values(dedupe_group_id=target))
            changed += 1
    db.commit()

    stats = {
        "groups": len(groups),
        "grouped_jobs": sum(len(m) for m in groups.values()),
        "changed": changed,
    }
    log.info("dedupe_done", **stats)
    return stats
