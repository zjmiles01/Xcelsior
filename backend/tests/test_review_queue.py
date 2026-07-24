"""Human review-queue curation: listing, dispositions, and the re-seen
status rules the extraction upsert enforces.

Status semantics under re-appearance (locked here, mirrored from expiry's
"re-seen means not gone" rule):
  - pending   + re-seen -> pending, occurrences + 1
  - resolved  + re-seen -> pending  (the fix didn't take; surface it)
  - dismissed + re-seen -> dismissed (ruled out of scope; stays quiet)
"""

import pytest

from app.catalog.models import Company, Job
from app.catalog.taxonomy_models import CanonicalTitle
from app.extraction.models import ReviewQueueItem
from app.extraction.review import (
    get_review_item,
    list_review_items,
    requeue_unresolved_titles,
    review_summary,
    set_review_status,
)
from app.extraction.service import _upsert_review_item
from app.ingestion.models import RawPosting, Source


def _make_job(
    db,
    external_id: str = "rq-1",
    *,
    status: str = "active",
    extractor_version: int | None = 2,
    canonical_title_id: int | None = None,
) -> Job:
    source = db.query(Source).filter_by(name="rq-test").first()
    if source is None:
        source = Source(name="rq-test", kind="ats_api", display_policy="full_text")
        company = Company(name="RQ Corp", name_normalized="rq corp")
        db.add_all([source, company])
        db.flush()
    else:
        company = db.query(Company).filter_by(name_normalized="rq corp").one()
    raw = RawPosting(
        source_id=source.id,
        external_id=external_id,
        payload={"synthetic": True},
        content_hash=external_id,
    )
    db.add(raw)
    db.flush()
    job = Job(
        source_id=source.id,
        company_id=company.id,
        raw_posting_id=raw.id,
        title_raw="Underwater Basket Weaver",
        status=status,
        extractor_version=extractor_version,
        canonical_title_id=canonical_title_id,
    )
    db.add(job)
    db.flush()
    return job


def _item(db, value: str, kind: str = "title", occurrences: int = 1,
          status: str = "pending") -> ReviewQueueItem:
    item = ReviewQueueItem(kind=kind, value=value, occurrences=occurrences, status=status)
    db.add(item)
    db.flush()
    return item


def test_summary_is_zero_filled_and_counts_by_kind_and_status(db):
    _item(db, "account executive", occurrences=40)
    _item(db, "recruiter", status="dismissed")
    _item(db, "ray", kind="technology")
    summary = review_summary(db)
    assert summary["title"] == {"pending": 1, "resolved": 0, "dismissed": 1}
    assert summary["technology"] == {"pending": 1, "resolved": 0, "dismissed": 0}


def test_list_orders_by_occurrences_then_id_and_respects_filters(db):
    a = _item(db, "account executive", occurrences=40)
    b = _item(db, "sales lead", occurrences=7)
    c = _item(db, "growth marketer", occurrences=40)  # ties a; higher id loses
    _item(db, "ray", kind="technology", occurrences=99)
    _item(db, "recruiter", occurrences=1000, status="dismissed")

    titles = list_review_items(db, kind="title")
    assert [i.id for i in titles] == [a.id, c.id, b.id]

    everything_pending = list_review_items(db)
    assert len(everything_pending) == 4  # dismissed excluded by default

    assert [i.value for i in list_review_items(db, status="dismissed")] == ["recruiter"]
    assert len(list_review_items(db, kind="title", limit=2)) == 2


def test_list_rejects_unknown_kind_and_status(db):
    with pytest.raises(ValueError, match="unknown kind"):
        list_review_items(db, kind="salary")
    with pytest.raises(ValueError, match="unknown status"):
        list_review_items(db, status="done")


def test_get_review_item_fails_loudly_on_unknown_id(db):
    with pytest.raises(ValueError, match="no review item with id 424242"):
        get_review_item(db, 424242)


def test_set_review_status_updates_all_named_items(db):
    a = _item(db, "account executive")
    b = _item(db, "sales lead")
    changed = set_review_status(db, [a.id, b.id], "dismissed")
    assert changed == 2
    assert get_review_item(db, a.id).status == "dismissed"
    assert get_review_item(db, b.id).status == "dismissed"


def test_set_review_status_rejects_unknown_ids_without_partial_updates(db):
    a = _item(db, "account executive")
    with pytest.raises(ValueError, match=r"no review items with ids \[424242\]"):
        set_review_status(db, [a.id, 424242], "resolved")
    assert get_review_item(db, a.id).status == "pending"


def test_set_review_status_rejects_unknown_status(db):
    a = _item(db, "account executive")
    with pytest.raises(ValueError, match="unknown status"):
        set_review_status(db, [a.id], "done")


def test_upsert_increments_pending_item(db):
    job = _make_job(db)
    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    db.flush()
    item = db.query(ReviewQueueItem).filter_by(value="underwater basket weaver").one()
    assert (item.status, item.occurrences) == ("pending", 2)


def test_resolved_item_reseen_reopens_to_pending(db):
    job = _make_job(db)
    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    db.flush()
    item = db.query(ReviewQueueItem).filter_by(value="underwater basket weaver").one()
    set_review_status(db, [item.id], "resolved")

    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    db.flush()
    db.refresh(item)
    assert (item.status, item.occurrences) == ("pending", 2)


def test_requeue_unresolved_titles_targets_exactly_the_right_jobs(db):
    """Cleared: active + unresolved title + extracted. Untouched: a job
    whose title resolved, an expired job, and a job never extracted."""
    title = CanonicalTitle(slug="basket-engineer", name="Basket Engineer")
    db.add(title)
    db.flush()
    unresolved = _make_job(db, "rq-unresolved")
    resolved = _make_job(db, "rq-resolved", canonical_title_id=title.id)
    expired = _make_job(db, "rq-expired", status="expired")
    never_extracted = _make_job(db, "rq-never", extractor_version=None)

    assert requeue_unresolved_titles(db) == 1

    for job in (unresolved, resolved, expired, never_extracted):
        db.refresh(job)
    assert unresolved.extractor_version is None  # re-queued for extract
    assert resolved.extractor_version == 2
    assert expired.extractor_version == 2
    assert never_extracted.extractor_version is None  # was already queued

    assert requeue_unresolved_titles(db) == 0  # idempotent once queued


def test_dismissed_item_reseen_stays_dismissed(db):
    job = _make_job(db)
    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    db.flush()
    item = db.query(ReviewQueueItem).filter_by(value="underwater basket weaver").one()
    set_review_status(db, [item.id], "dismissed")

    _upsert_review_item(db, "title", "underwater basket weaver", "ctx", job.id)
    db.flush()
    db.refresh(item)
    assert (item.status, item.occurrences) == ("dismissed", 2)
