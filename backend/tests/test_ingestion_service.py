"""Ingestion service behavior against a scripted in-memory connector.

The registry (`CONNECTORS`) is the seam: tests register a fake spec and
drive `ingest_source` end-to-end through the real repository and schema —
raw-posting immutability rules, hash-based change detection, and company
-failure isolation are all exercised without any network.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.catalog.models import Company, Job
from app.ingestion import service
from app.ingestion.connectors.base import ConnectorSpec, NormalizedPosting
from app.ingestion.models import RawPosting, Source
from app.ingestion.repository import IngestionRepository

POSTED = datetime(2026, 7, 1, tzinfo=UTC)


def _posting(external_id: str, title: str = "Backend Engineer", content_hash: str | None = None,
             locations: list[str] | None = None) -> NormalizedPosting:
    return NormalizedPosting(
        external_id=external_id,
        title=title,
        description_html=f"<p>{title}</p>",
        apply_url=f"https://jobs.example.com/{external_id}",
        location_texts=locations if locations is not None else ["San Francisco, CA"],
        posted_at=POSTED,
        content_hash=content_hash or f"hash-{external_id}-{title}",
        payload={"id": external_id, "title": title},
    )


class FakeConnector:
    """Scripted board connector: token -> postings, or an exception."""

    source_name = "fakeboard"
    boards: dict[str, list[NormalizedPosting] | Exception] = {}

    def fetch_postings(self, board_token: str) -> list[NormalizedPosting]:
        result = self.boards.get(board_token, [])
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def fake_source(db, monkeypatch):
    """Register the fake connector and seed one company per board token."""
    monkeypatch.setattr(service, "REQUEST_DELAY_SECONDS", 0)
    spec = ConnectorSpec(
        factory=FakeConnector,
        kind="ats_api",
        display_policy="extracted_only",
        attribution_text="Postings via FakeBoard",
        attribution_url="https://fakeboard.example.com",
    )
    monkeypatch.setitem(service.CONNECTORS, "fakeboard", spec)
    FakeConnector.boards = {}
    repo = IngestionRepository(db)
    for token in ("acme", "globex"):
        repo.upsert_company(name=token.title(), ats_type="fakeboard", ats_token=token, domain=None)
    db.commit()
    return spec


def test_unknown_source_fails_loudly(db):
    with pytest.raises(ValueError, match="unknown source"):
        service.ingest_source(db, source_name="no-such-source")


def test_source_row_carries_declared_metadata(db, fake_source):
    service.ingest_source(db, source_name="fakeboard")

    source = db.scalar(select(Source).where(Source.name == "fakeboard"))
    assert source is not None
    assert source.kind == "ats_api"
    assert source.display_policy == "extracted_only"
    assert source.attribution_text == "Postings via FakeBoard"
    assert source.attribution_url == "https://fakeboard.example.com"


def test_new_postings_create_raw_and_job_rows(db, fake_source):
    FakeConnector.boards = {
        "acme": [_posting("a-1"), _posting("a-2", locations=["Remote", "New York, NY"])],
        "globex": [_posting("g-1")],
    }

    run = service.ingest_source(db, source_name="fakeboard")

    assert (run.postings_fetched, run.postings_new, run.errors) == (3, 3, 0)
    assert run.status == "succeeded"
    source = db.scalar(select(Source).where(Source.name == "fakeboard"))
    raws = db.scalars(select(RawPosting).where(RawPosting.source_id == source.id)).all()
    assert {r.external_id for r in raws} == {"a-1", "a-2", "g-1"}
    jobs = db.scalars(select(Job).where(Job.source_id == source.id)).all()
    assert len(jobs) == 3
    multi = next(j for j in jobs if j.raw_posting_id == next(
        r.id for r in raws if r.external_id == "a-2"))
    assert {loc.raw_text for loc in multi.locations} == {"Remote", "New York, NY"}
    acme = db.scalar(select(Company).where(Company.ats_token == "acme"))
    assert all(j.company_id == acme.id for j in jobs if j.raw_posting_id in
               {r.id for r in raws if r.external_id.startswith("a-")})


def test_unchanged_posting_only_touches_last_seen(db, fake_source):
    FakeConnector.boards = {"acme": [_posting("a-1", content_hash="stable")]}
    service.ingest_source(db, source_name="fakeboard")

    run = service.ingest_source(db, source_name="fakeboard")

    assert (run.postings_new, run.postings_updated) == (0, 0)
    assert run.postings_fetched == 1
    source = db.scalar(select(Source).where(Source.name == "fakeboard"))
    assert db.scalar(select(RawPosting).where(RawPosting.source_id == source.id)) is not None
    jobs = db.scalars(select(Job).where(Job.source_id == source.id)).all()
    assert len(jobs) == 1  # no duplicate job row on re-ingest


def test_changed_posting_rewrites_raw_and_job(db, fake_source):
    FakeConnector.boards = {"acme": [_posting("a-1", title="Engineer I", content_hash="v1")]}
    service.ingest_source(db, source_name="fakeboard")
    # Simulate the extractor having processed the first version.
    db.scalar(select(Job)).extractor_version = 2
    db.commit()
    FakeConnector.boards = {"acme": [_posting("a-1", title="Engineer II", content_hash="v2")]}

    run = service.ingest_source(db, source_name="fakeboard")

    assert (run.postings_new, run.postings_updated) == (0, 1)
    source = db.scalar(select(Source).where(Source.name == "fakeboard"))
    raw = db.scalar(select(RawPosting).where(RawPosting.source_id == source.id))
    assert raw.content_hash == "v2"
    job = db.scalar(select(Job).where(Job.source_id == source.id))
    assert job.title_raw == "Engineer II"
    # Changed text re-queues extraction; unchanged text (touch path) must not.
    assert job.extractor_version is None
    job.extractor_version = 2
    db.commit()
    run = service.ingest_source(db, source_name="fakeboard")
    assert run.postings_updated == 0
    assert db.scalar(select(Job).where(Job.source_id == source.id)).extractor_version == 2


def test_one_broken_board_never_sinks_the_run(db, fake_source):
    FakeConnector.boards = {
        "acme": RuntimeError("board 404"),
        "globex": [_posting("g-1")],
    }

    run = service.ingest_source(db, source_name="fakeboard")

    assert run.errors == 1
    assert run.postings_new == 1
    assert run.status == "succeeded"  # partial failure, not total
    assert run.finished_at is not None
    assert "Acme (acme): board 404" in (run.error_detail or "")


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com")
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=request, response=httpx.Response(status, request=request)
    )


class FlakyConnector:
    """Fails a scripted number of times per token before succeeding."""

    def __init__(self, failures: list[Exception]) -> None:
        self.failures = failures
        self.attempts = 0

    def fetch_postings(self, board_token: str) -> list[NormalizedPosting]:
        self.attempts += 1
        if self.failures:
            raise self.failures.pop(0)
        return [_posting("f-1")]


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(service, "RETRY_BACKOFF_SECONDS", 0)


def test_transient_failures_retry_until_success():
    connector = FlakyConnector([httpx.ConnectError("boom"), _status_error(503)])

    postings = service._fetch_with_retry(connector, "acme")

    assert connector.attempts == 3
    assert len(postings) == 1


def test_retry_budget_is_bounded():
    connector = FlakyConnector([_status_error(429)] * 5)

    with pytest.raises(httpx.HTTPStatusError):
        service._fetch_with_retry(connector, "acme")

    assert connector.attempts == service.RETRY_ATTEMPTS


def test_permanent_http_errors_do_not_retry():
    connector = FlakyConnector([_status_error(404)])

    with pytest.raises(httpx.HTTPStatusError):
        service._fetch_with_retry(connector, "acme")

    assert connector.attempts == 1


def _age_job(db, external_id: str, days: int) -> None:
    """Backdate a job's last_seen_at as if it vanished `days` ago."""
    stale = datetime.now(UTC) - timedelta(days=days)
    job = db.scalar(
        select(Job).join(RawPosting, RawPosting.id == Job.raw_posting_id).where(
            RawPosting.external_id == external_id
        )
    )
    job.last_seen_at = stale
    db.commit()


def test_expiry_marks_long_unseen_jobs(db, fake_source):
    FakeConnector.boards = {"acme": [_posting("a-1"), _posting("a-2")]}
    service.ingest_source(db, source_name="fakeboard")
    _age_job(db, "a-1", days=4)

    expired = service.expire_stale_jobs(db)

    assert expired["fakeboard"] == 1
    stale, fresh = (
        db.scalar(select(Job).join(RawPosting, RawPosting.id == Job.raw_posting_id).where(
            RawPosting.external_id == eid))
        for eid in ("a-1", "a-2")
    )
    assert stale.status == "expired"
    assert fresh.status == "active"


def test_expiry_skipped_when_source_has_no_recent_success(db, fake_source):
    """An outage must never mass-expire a source's corpus."""
    FakeConnector.boards = {"acme": [_posting("a-1")], "globex": RuntimeError("down")}
    service.ingest_source(db, source_name="fakeboard")
    _age_job(db, "a-1", days=10)
    # Rewrite the run history: only a failed run inside the grace window.
    from app.ingestion.models import IngestionRun

    for run in db.scalars(select(IngestionRun)):
        run.status = "failed"
    db.commit()

    expired = service.expire_stale_jobs(db)

    assert "fakeboard" not in expired
    job = db.scalar(select(Job))
    assert job.status == "active"


def test_reseen_posting_reactivates(db, fake_source):
    FakeConnector.boards = {"acme": [_posting("a-1", content_hash="stable")]}
    service.ingest_source(db, source_name="fakeboard")
    _age_job(db, "a-1", days=4)
    service.expire_stale_jobs(db)
    assert db.scalar(select(Job)).status == "expired"

    service.ingest_source(db, source_name="fakeboard")  # unchanged hash path

    assert db.scalar(select(Job)).status == "active"


def test_ingest_all_runs_every_enabled_source(db, fake_source, monkeypatch):
    """Two registered sources: the disabled one is skipped, the other runs."""
    monkeypatch.setattr(
        service, "CONNECTORS", {"fakeboard": fake_source, "otherboard": fake_source}
    )
    db.add(Source(name="otherboard", kind="ats_api", enabled=False))
    db.commit()
    FakeConnector.boards = {"acme": [_posting("a-1")]}

    runs = service.ingest_all(db)

    assert set(runs) == {"fakeboard"}
    assert runs["fakeboard"].postings_new == 1
