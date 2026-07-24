from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import Company, Job, JobLocation
from app.ingestion.connectors.base import ConnectorSpec, NormalizedPosting
from app.ingestion.models import IngestionRun, RawPosting, Source


class IngestionRepository:
    """All database access for the ingestion pipeline. Services above this
    layer make decisions; this layer only reads and writes."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_source(self, name: str, spec: ConnectorSpec) -> Source:
        source = self.db.scalar(select(Source).where(Source.name == name))
        if source is None:
            source = Source(
                name=name,
                kind=spec.kind,
                display_policy=spec.display_policy,
                attribution_text=spec.attribution_text,
                attribution_url=spec.attribution_url,
            )
            self.db.add(source)
            self.db.flush()
        return source

    def upsert_company(
        self, name: str, ats_type: str, ats_token: str, domain: str | None
    ) -> Company:
        company = self.db.scalar(
            select(Company).where(Company.ats_type == ats_type, Company.ats_token == ats_token)
        )
        if company is None:
            company = Company(
                name=name,
                name_normalized=name.strip().lower(),
                ats_type=ats_type,
                ats_token=ats_token,
                domain=domain,
            )
            self.db.add(company)
            self.db.flush()
        return company

    def companies_for_ats(self, ats_type: str, limit: int | None = None) -> list[Company]:
        stmt = select(Company).where(Company.ats_type == ats_type).order_by(Company.id)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def find_raw(self, source_id: int, external_id: str) -> RawPosting | None:
        return self.db.scalar(
            select(RawPosting).where(
                RawPosting.source_id == source_id, RawPosting.external_id == external_id
            )
        )

    def insert_raw(self, source_id: int, posting: NormalizedPosting) -> RawPosting:
        raw = RawPosting(
            source_id=source_id,
            external_id=posting.external_id,
            payload=posting.payload,
            content_hash=posting.content_hash,
        )
        self.db.add(raw)
        self.db.flush()
        return raw

    def touch_raw(self, raw: RawPosting) -> None:
        raw.last_seen_at = datetime.now(UTC)

    def replace_raw_payload(self, raw: RawPosting, posting: NormalizedPosting) -> None:
        raw.payload = posting.payload
        raw.content_hash = posting.content_hash
        raw.fetched_at = datetime.now(UTC)
        raw.last_seen_at = datetime.now(UTC)

    def job_for_raw(self, raw_posting_id: int) -> Job | None:
        return self.db.scalar(select(Job).where(Job.raw_posting_id == raw_posting_id))

    def create_job(
        self, raw: RawPosting, company: Company, posting: NormalizedPosting
    ) -> Job:
        job = Job(
            raw_posting_id=raw.id,
            source_id=raw.source_id,
            company_id=company.id,
            title_raw=posting.title,
            description=posting.description_html,
            apply_url=posting.apply_url,
            posted_at=posting.posted_at,
        )
        self.db.add(job)
        self.db.flush()
        self._set_locations(job, posting)
        return job

    def update_job(self, job: Job, posting: NormalizedPosting) -> None:
        job.title_raw = posting.title
        job.description = posting.description_html
        job.apply_url = posting.apply_url
        job.posted_at = posting.posted_at
        job.last_seen_at = datetime.now(UTC)
        job.status = "active"  # a re-seen posting is alive again
        # Changed text invalidates everything extracted from the old text;
        # clearing the version puts the job back in extract_pending's queue.
        job.extractor_version = None
        job.locations.clear()
        self._set_locations(job, posting)

    def touch_job(self, job: Job) -> None:
        job.last_seen_at = datetime.now(UTC)
        job.status = "active"  # a re-seen posting is alive again

    def _set_locations(self, job: Job, posting: NormalizedPosting) -> None:
        for text in posting.location_texts:
            job.locations.append(
                JobLocation(
                    raw_text=text,
                    is_remote="remote" in text.lower(),
                )
            )

    def start_run(self, source_id: int) -> IngestionRun:
        run = IngestionRun(source_id=source_id)
        self.db.add(run)
        self.db.flush()
        return run
