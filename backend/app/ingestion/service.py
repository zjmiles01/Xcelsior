import csv
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.catalog.models import Company, Job
from app.ingestion.connectors.base import (
    CompanyBoardConnector,
    ConnectorSpec,
    NormalizedPosting,
)
from app.ingestion.connectors.greenhouse import GreenhouseConnector
from app.ingestion.connectors.lever import LeverConnector
from app.ingestion.models import IngestionRun, Source
from app.ingestion.repository import IngestionRepository

log = structlog.get_logger()

# Polite pacing between company-board requests; one public board fetch per
# company per night is far inside anyone's tolerance, but bursts are rude.
REQUEST_DELAY_SECONDS = 0.5

# Transient-failure retry budget per board fetch. Only network faults and
# 429/5xx responses retry; a 4xx (bad token, gone board) is a fact about
# the seed list, not the weather, and retrying it just delays the run.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0  # doubled after each failed attempt

# `error_detail` is an alarm payload, not an archive; cap it so one run
# with a broken source can't write megabytes into the runs table.
ERROR_DETAIL_MAX_CHARS = 4000

# A posting absent from its board for this many days is expired. Board
# fetches are full listings, so one absence already means "gone"; the
# grace absorbs weekend outages and transient company-level fetch
# failures (which never bump last_seen) before we call it.
EXPIRY_GRACE_DAYS = 3

CONNECTORS: dict[str, ConnectorSpec] = {
    "greenhouse": ConnectorSpec(factory=GreenhouseConnector, kind="ats_api"),
    "lever": ConnectorSpec(factory=LeverConnector, kind="ats_api"),
}


def seed_companies(db: Session, seed_file: Path) -> int:
    """Idempotently sync the versioned seed list into the companies table."""
    repo = IngestionRepository(db)
    count = 0
    with seed_file.open() as f:
        for row in csv.DictReader(f):
            repo.upsert_company(
                name=row["name"],
                ats_type=row["ats_type"],
                ats_token=row["ats_token"],
                domain=row.get("domain") or None,
            )
            count += 1
    db.commit()
    return count


def ingest_all(db: Session, limit_companies: int | None = None) -> dict[str, IngestionRun]:
    """Run every registered source, honoring the `enabled` operational
    switch on its `sources` row. This is what the nightly cron invokes."""
    runs: dict[str, IngestionRun] = {}
    for source_name in CONNECTORS:
        source = db.scalar(select(Source).where(Source.name == source_name))
        if source is not None and not source.enabled:
            log.info("source_disabled_skipped", source=source_name)
            continue
        runs[source_name] = ingest_source(db, source_name, limit_companies)
    return runs


def _fetch_with_retry(
    connector: CompanyBoardConnector, board_token: str
) -> list[NormalizedPosting]:
    delay = RETRY_BACKOFF_SECONDS
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return connector.fetch_postings(board_token)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status != 429 and status < 500:
                raise
            error: Exception = exc
        except httpx.TransportError as exc:
            error = exc
        if attempt == RETRY_ATTEMPTS:
            raise error
        log.info("fetch_retrying", token=board_token, attempt=attempt, error=str(error))
        time.sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def ingest_source(
    db: Session, source_name: str, limit_companies: int | None = None
) -> IngestionRun:
    """Fetch every company board for a source, upserting raw postings and
    canonical jobs. Company-level failures are isolated: one broken board
    must never sink the run."""
    repo = IngestionRepository(db)
    spec = CONNECTORS.get(source_name)
    if spec is None:
        raise ValueError(f"unknown source: {source_name}")

    connector: CompanyBoardConnector = spec.factory()
    source = repo.get_or_create_source(source_name, spec)
    run = repo.start_run(source.id)
    companies = repo.companies_for_ats(source_name, limit=limit_companies)
    log.info("ingest_started", source=source_name, companies=len(companies))

    failures: list[str] = []
    for company in companies:
        try:
            postings = _fetch_with_retry(connector, company.ats_token or "")
        except Exception as exc:
            run.errors += 1
            failures.append(f"{company.name} ({company.ats_token}): {exc}")
            log.warning(
                "company_fetch_failed",
                company=company.name,
                token=company.ats_token,
                error=str(exc),
            )
            continue

        for posting in postings:
            outcome = _upsert_posting(repo, source.id, company.id, posting)
            run.postings_fetched += 1
            if outcome == "new":
                run.postings_new += 1
            elif outcome == "updated":
                run.postings_updated += 1

        db.commit()
        time.sleep(REQUEST_DELAY_SECONDS)

    run.status = "succeeded" if run.errors < max(len(companies), 1) else "failed"
    run.error_detail = "\n".join(failures)[:ERROR_DETAIL_MAX_CHARS] or None
    run.finished_at = datetime.now(UTC)
    db.commit()
    log.info(
        "ingest_finished",
        source=source_name,
        fetched=run.postings_fetched,
        new=run.postings_new,
        updated=run.postings_updated,
        errors=run.errors,
    )
    return run


def expire_stale_jobs(db: Session, grace_days: int = EXPIRY_GRACE_DAYS) -> dict[str, int]:
    """Expire jobs whose posting has stopped appearing on its board.

    Keyed on `last_seen_at`, which every sighting bumps. Guard: a source
    only expires jobs while it has a *successful* run inside the grace
    window — a source outage or a disabled source must never mass-expire
    its corpus, because "we could not look" is not "the posting is gone".
    (A single company whose board keeps failing inside an otherwise
    healthy source will still expire after the grace; runs are recorded
    per source, not per company, and a board that 404s through three
    nights of retries is most likely genuinely dead.)
    """
    cutoff = datetime.now(UTC) - timedelta(days=grace_days)
    expired: dict[str, int] = {}
    for source in db.scalars(select(Source)):
        latest_success = db.scalar(
            select(func.max(IngestionRun.finished_at)).where(
                IngestionRun.source_id == source.id,
                IngestionRun.status == "succeeded",
            )
        )
        if latest_success is None or latest_success < cutoff:
            log.info("expiry_skipped_no_recent_success", source=source.name)
            continue
        count = db.execute(
            update(Job)
            .where(Job.source_id == source.id, Job.status == "active", Job.last_seen_at < cutoff)
            .values(status="expired")
        ).rowcount
        expired[source.name] = count
        log.info("expiry_done", source=source.name, expired=count)
    db.commit()
    return expired


def _upsert_posting(
    repo: IngestionRepository, source_id: int, company_id: int, posting: NormalizedPosting
) -> str:
    """Hash-based change detection: unchanged postings only get their
    last_seen bumped (which is what expiry will key on in M5); changed ones
    are rewritten and will be flagged for re-extraction in M2."""
    raw = repo.find_raw(source_id, posting.external_id)

    if raw is None:
        raw = repo.insert_raw(source_id, posting)
        company = repo.db.get(Company, company_id)
        assert company is not None
        repo.create_job(raw, company, posting)
        return "new"

    if raw.content_hash == posting.content_hash:
        repo.touch_raw(raw)
        job = repo.job_for_raw(raw.id)
        if job is not None:
            repo.touch_job(job)
        return "unchanged"

    repo.replace_raw_payload(raw, posting)
    job = repo.job_for_raw(raw.id)
    if job is not None:
        repo.update_job(job, posting)
    return "updated"
