"""Human curation workflow over the review queue.

The queue aggregates unresolved extractions by (kind, value) — one row
per distinct problem, not per job — so curation operates on taxonomy-level
decisions: "this title string belongs to an existing family" (add an alias
to data/taxonomy/titles.yaml), "this is a non-engineering role" (dismiss),
"this technology match is a false positive" (tighten a gate in
technologies.yaml).

Nothing here edits taxonomy files, job rows, or extracted facts. A status
change records that a human acted; the data itself only changes through
the existing sanctioned path — edit the YAML, `xcelsior load-taxonomy`,
then re-extraction through the extractor-version gate.

ADR-002 reserves a future LLM-assisted advisor for this queue (consuming
the doubt band, proposing dispositions a human confirms). Its proposals
would land here as ordinary resolve/dismiss calls; like the aggregator
connector protocol (ingestion/connectors/base.py), the advisor interface
is defined when its first real implementation lands, not guessed at now.
"""

from sqlalchemy import Case, case, func, select, update
from sqlalchemy.orm import Session

from app.catalog.models import Job
from app.extraction.models import ReviewQueueItem

VALID_KINDS = ("title", "technology")
VALID_STATUSES = ("pending", "resolved", "dismissed")


def review_summary(db: Session) -> dict[str, dict[str, int]]:
    """Item counts by kind and status, zero-filled so the CLI table is
    always the same shape regardless of what the queue contains."""
    summary: dict[str, dict[str, int]] = {
        kind: dict.fromkeys(VALID_STATUSES, 0) for kind in VALID_KINDS
    }
    rows = db.execute(
        select(ReviewQueueItem.kind, ReviewQueueItem.status, func.count()).group_by(
            ReviewQueueItem.kind, ReviewQueueItem.status
        )
    ).all()
    for kind, status, count in rows:
        summary.setdefault(kind, dict.fromkeys(VALID_STATUSES, 0))[status] = count
    return summary


def list_review_items(
    db: Session,
    kind: str | None = None,
    status: str = "pending",
    limit: int = 50,
) -> list[ReviewQueueItem]:
    """Queue slice ordered by impact: most-occurring first, id as the
    stable tie-break so repeated listings paginate consistently."""
    if kind is not None and kind not in VALID_KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {VALID_KINDS}")
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {VALID_STATUSES}")
    stmt = (
        select(ReviewQueueItem)
        .where(ReviewQueueItem.status == status)
        .order_by(ReviewQueueItem.occurrences.desc(), ReviewQueueItem.id)
        .limit(limit)
    )
    if kind is not None:
        stmt = stmt.where(ReviewQueueItem.kind == kind)
    return list(db.scalars(stmt))


def get_review_item(db: Session, item_id: int) -> ReviewQueueItem:
    item = db.get(ReviewQueueItem, item_id)
    if item is None:
        raise ValueError(f"no review item with id {item_id}")
    return item


def set_review_status(db: Session, item_ids: list[int], status: str) -> int:
    """Record a human disposition for one or more items.

    Fails loudly on unknown ids — a typo'd id silently ignored would
    leave the curator believing an item was handled when it wasn't.
    """
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {VALID_STATUSES}")
    items = list(db.scalars(select(ReviewQueueItem).where(ReviewQueueItem.id.in_(item_ids))))
    missing = set(item_ids) - {item.id for item in items}
    if missing:
        raise ValueError(f"no review items with ids {sorted(missing)}")
    for item in items:
        item.status = status
    db.commit()
    return len(items)


def requeue_unresolved_titles(db: Session) -> int:
    """Re-queue active jobs whose title never canonicalized, so the next
    `xcelsior extract` revisits them against the grown title taxonomy.

    Same mechanism as the changed-content re-queue (clear
    `extractor_version`; the extract gate does the rest) — nothing is
    modified here except pipeline bookkeeping, and re-extraction is
    idempotent. Scoped to titles because title aliases are data the
    curation loop grows routinely; technology gate changes remain
    extraction-logic changes and take the EXTRACTOR_VERSION bump path
    (architectural invariant #3).
    """
    result = db.execute(
        update(Job)
        .where(
            Job.status == "active",
            Job.canonical_title_id.is_(None),
            Job.extractor_version.is_not(None),
        )
        .values(extractor_version=None)
    )
    db.commit()
    return result.rowcount


def reopened_status_on_reseen() -> Case:
    """ON CONFLICT status expression for the extraction upsert: a *resolved*
    item seen again means its fix didn't take, so it flips back to pending
    (the honesty rule expiry already follows — re-seen means not gone).
    A *dismissed* item stays dismissed: it was ruled out of scope, and
    reappearing is expected, not actionable.
    """
    return case(
        (ReviewQueueItem.status == "resolved", "pending"),
        else_=ReviewQueueItem.status,
    )
