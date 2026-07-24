"""Persistence layer around the pure extraction core: loads the taxonomy
from the database, runs extraction in resumable batches, applies the
pg_trgm title fallback, and maintains the review queue.

Idempotency: extracting a job first deletes its previous rows, so
re-running any batch — or re-extracting the whole corpus after an extractor
upgrade — converges to the same state.
"""

from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.catalog.models import Job, JobLocation
from app.catalog.taxonomy_models import (
    CanonicalTitle,
    JobSection,
    JobTechnology,
    Technology,
    TechnologyAlias,
    TitleAlias,
)
from app.extraction.core import EXTRACTOR_VERSION, extract_document
from app.extraction.matcher import TechnologyMatcher
from app.extraction.models import ReviewQueueItem
from app.extraction.review import reopened_status_on_reseen
from app.extraction.taxonomy import AliasSpec, TaxonomyIndex, TechSpec, TitleSpec, load_index

log = structlog.get_logger()

TRGM_SIMILARITY_THRESHOLD = 0.55
BATCH_SIZE = 200


def sync_taxonomy(db: Session, taxonomy_dir: Path | None = None) -> tuple[int, int]:
    """Sync YAML taxonomy into the database (idempotent upserts)."""
    index = load_index(taxonomy_dir) if taxonomy_dir else load_index()

    tech_ids: dict[str, int] = {}
    for spec in index.technologies.values():
        row = db.scalar(select(Technology).where(Technology.slug == spec.slug))
        if row is None:
            row = Technology(slug=spec.slug, name=spec.name, category=spec.category)
            db.add(row)
            db.flush()
        else:
            row.name, row.category = spec.name, spec.category
        tech_ids[spec.slug] = row.id

    for alias_spec in index.aliases:
        row = db.scalar(select(TechnologyAlias).where(TechnologyAlias.alias == alias_spec.alias))
        if row is None:
            db.add(
                TechnologyAlias(
                    technology_id=tech_ids[alias_spec.tech_slug],
                    alias=alias_spec.alias,
                    cased=alias_spec.cased,
                    case_sensitive=alias_spec.case_sensitive,
                    require_context=alias_spec.require_context,
                )
            )
        else:
            row.technology_id = tech_ids[alias_spec.tech_slug]
            row.cased = alias_spec.cased
            row.case_sensitive = alias_spec.case_sensitive
            row.require_context = alias_spec.require_context

    title_ids: dict[str, int] = {}
    for title in index.titles.values():
        row = db.scalar(select(CanonicalTitle).where(CanonicalTitle.slug == title.slug))
        if row is None:
            row = CanonicalTitle(slug=title.slug, name=title.name)
            db.add(row)
            db.flush()
        title_ids[title.slug] = row.id

    for alias, slug in index.title_aliases.items():
        row = db.scalar(select(TitleAlias).where(TitleAlias.alias == alias))
        if row is None:
            db.add(TitleAlias(canonical_title_id=title_ids[slug], alias=alias))
        else:
            row.canonical_title_id = title_ids[slug]

    db.commit()
    return len(index.technologies), len(index.titles)


def load_index_from_db(db: Session) -> TaxonomyIndex:
    index = TaxonomyIndex()
    tech_by_id: dict[int, str] = {}
    for tech in db.scalars(select(Technology)):
        index.technologies[tech.slug] = TechSpec(
            slug=tech.slug, name=tech.name, category=tech.category
        )
        tech_by_id[tech.id] = tech.slug
    for alias in db.scalars(select(TechnologyAlias)):
        index.aliases.append(
            AliasSpec(
                alias=alias.alias,
                cased=alias.cased,
                tech_slug=tech_by_id[alias.technology_id],
                case_sensitive=alias.case_sensitive,
                require_context=alias.require_context,
            )
        )
    title_by_id: dict[int, str] = {}
    for title in db.scalars(select(CanonicalTitle)):
        index.titles[title.slug] = TitleSpec(slug=title.slug, name=title.name)
        title_by_id[title.id] = title.slug
    for talias in db.scalars(select(TitleAlias)):
        index.title_aliases[talias.alias] = title_by_id[talias.canonical_title_id]
    return index


def extract_pending(db: Session, limit: int | None = None) -> dict[str, int]:
    """Process jobs whose extraction is missing or from an older extractor.

    Selection uses FOR UPDATE SKIP LOCKED so multiple workers can run the
    same command safely; per-batch commits make the run crash-resumable
    (finished batches never reprocess).
    """
    index = load_index_from_db(db)
    matcher = TechnologyMatcher(index)
    tech_ids = {
        slug: id_
        for slug, id_ in db.execute(select(Technology.slug, Technology.id)).all()
    }
    title_ids = {
        slug: id_
        for slug, id_ in db.execute(select(CanonicalTitle.slug, CanonicalTitle.id)).all()
    }

    stats = {"processed": 0, "with_technologies": 0, "titles_resolved": 0, "salaries_new": 0}
    while True:
        batch_limit = BATCH_SIZE if limit is None else min(BATCH_SIZE, limit - stats["processed"])
        if batch_limit <= 0:
            break
        jobs = list(
            db.scalars(
                select(Job)
                .where(
                    (Job.extractor_version.is_(None))
                    | (Job.extractor_version < EXTRACTOR_VERSION)
                )
                .order_by(Job.id)
                .limit(batch_limit)
                # of=Job: lock only job rows — the joined-eager company
                # (outer join) can't take FOR UPDATE, and doesn't need it.
                .with_for_update(skip_locked=True, of=Job)
            )
        )
        if not jobs:
            break
        for job in jobs:
            _extract_one(db, job, index, matcher, tech_ids, title_ids, stats)
        db.commit()
        log.info("extraction_batch_done", processed=stats["processed"])
    return stats


def _extract_one(
    db: Session,
    job: Job,
    index: TaxonomyIndex,
    matcher: TechnologyMatcher,
    tech_ids: dict[str, int],
    title_ids: dict[str, int],
    stats: dict[str, int],
) -> None:
    location_is_remote = any(loc.is_remote for loc in job.locations)
    result = extract_document(
        description_html=job.description or "",
        raw_title=job.title_raw,
        index=index,
        matcher=matcher,
        location_is_remote=location_is_remote,
    )

    db.execute(delete(JobTechnology).where(JobTechnology.job_id == job.id))
    db.execute(delete(JobSection).where(JobSection.job_id == job.id))

    for tech in result.technologies:
        db.add(
            JobTechnology(
                job_id=job.id,
                technology_id=tech_ids[tech.tech_slug],
                requirement_level=tech.requirement_level,
                confidence=tech.confidence,
                occurrences=tech.occurrences,
                extractor_version=EXTRACTOR_VERSION,
                evidence_snippet=tech.evidence,
                evidence_start=tech.evidence_start,
            )
        )
    for section in result.sections:
        db.add(
            JobSection(
                job_id=job.id, kind=section.kind,
                start_offset=section.start, end_offset=section.end,
            )
        )
    for doubtful in result.review_band:
        _upsert_review_item(db, "technology", doubtful.tech_slug, doubtful.evidence, job.id)

    job.description_text = result.text
    job.description_html = result.safe_html
    job.arrangement = result.arrangement or job.arrangement
    job.years_of_experience = result.years_of_experience
    job.experience_level = result.experience_level or job.experience_level
    if result.salary and job.salary_annual_min is None:
        job.salary_min = result.salary.min_amount
        job.salary_max = result.salary.max_amount
        job.salary_period = result.salary.period
        job.salary_currency = result.salary.currency
        job.salary_annual_min = result.salary.annual_min
        job.salary_annual_max = result.salary.annual_max
        stats["salaries_new"] += 1

    title = result.title
    if title and title.canonical_slug:
        job.canonical_title_id = title_ids[title.canonical_slug]
        stats["titles_resolved"] += 1
    elif title and title.normalized:
        fallback_id = _trgm_title_fallback(db, title.normalized)
        if fallback_id is not None:
            job.canonical_title_id = fallback_id
            stats["titles_resolved"] += 1
        else:
            _upsert_review_item(db, "title", title.normalized, job.title_raw, job.id)

    job.extractor_version = EXTRACTOR_VERSION
    job.extracted_at = datetime.now(UTC)
    stats["processed"] += 1
    if result.technologies:
        stats["with_technologies"] += 1


def _trgm_title_fallback(db: Session, normalized_title: str) -> int | None:
    """pg_trgm similarity against the title alias table: catches near-miss
    spellings the exact lookup can't ('backend engineeer', 'back--end dev')."""
    row = db.execute(
        select(TitleAlias.canonical_title_id, func.similarity(TitleAlias.alias, normalized_title))
        .where(func.similarity(TitleAlias.alias, normalized_title) > TRGM_SIMILARITY_THRESHOLD)
        .order_by(func.similarity(TitleAlias.alias, normalized_title).desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def _upsert_review_item(db: Session, kind: str, value: str, context: str, job_id: int) -> None:
    # Native ON CONFLICT upsert: atomic under concurrency, and immune to the
    # session-visibility trap where a SELECT-then-INSERT can't see rows added
    # earlier in the same uncommitted batch.
    stmt = pg_insert(ReviewQueueItem).values(
        kind=kind,
        value=value[:300],
        example_context=context[:500],
        example_job_id=job_id,
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["kind", "value"],
            set_={
                "occurrences": ReviewQueueItem.occurrences + 1,
                "last_seen_at": func.now(),
                # A resolved item seen again means its fix didn't take —
                # flip it back to pending; dismissed stays dismissed.
                "status": reopened_status_on_reseen(),
            },
        )
    )


def unresolved_title_stats(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(Job).where(Job.status == "active")) or 0
    resolved = (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "active", Job.canonical_title_id.is_not(None))
        )
        or 0
    )
    top_unresolved = db.execute(
        select(ReviewQueueItem.value, ReviewQueueItem.occurrences)
        .where(ReviewQueueItem.kind == "title", ReviewQueueItem.status == "pending")
        .order_by(ReviewQueueItem.occurrences.desc())
        .limit(25)
    ).all()
    return {
        "active_jobs": total,
        "titles_resolved": resolved,
        "resolution_rate": round(resolved / total, 3) if total else 0.0,
        "top_unresolved": [(value, count) for value, count in top_unresolved],
    }


def location_string_report(db: Session, limit: int = 40) -> list[tuple[str, int]]:
    rows = db.execute(
        select(JobLocation.raw_text, func.count())
        .group_by(JobLocation.raw_text)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [(text, count) for text, count in rows]
