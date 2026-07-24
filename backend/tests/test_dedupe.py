"""Dedup grouping rules (ADR-004) against hand-built cross-source rows.

Every scenario states its expected grouping in the test name and body;
nothing is asserted against "whatever the code outputs".
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.catalog.models import Company, Job, JobLocation
from app.ingestion.dedupe import assign_dedupe_groups, canonical_apply_url
from app.ingestion.models import RawPosting, Source

NOW = datetime(2026, 7, 1, tzinfo=UTC)

SF = {"raw_text": "San Francisco, CA", "city": "San Francisco", "region": "CA",
      "latitude": 37.77, "longitude": -122.42}
NYC = {"raw_text": "New York, NY", "city": "New York City", "region": "NY",
       "latitude": 40.71, "longitude": -74.01}
REMOTE = {"raw_text": "Remote - US", "is_remote": True}


class Corpus:
    """Tiny builder: sources, companies, and jobs with locations."""

    def __init__(self, db) -> None:
        self.db = db
        self.counter = 0
        self.ats = Source(name="ats", kind="ats_api")
        self.agg = Source(name="agg", kind="aggregator_api")
        self.gov = Source(name="gov", kind="gov_api")
        db.add_all([self.ats, self.agg, self.gov])
        db.flush()

    def company(self, name: str, domain: str | None = None) -> Company:
        company = Company(name=name, name_normalized=name.strip().lower(), domain=domain)
        self.db.add(company)
        self.db.flush()
        return company

    def job(self, source: Source, company: Company, title: str, *,
            apply_url: str | None = None, locations: list[dict] | None = None,
            status: str = "active", first_seen: datetime = NOW) -> Job:
        self.counter += 1
        raw = RawPosting(source_id=source.id, external_id=f"x-{self.counter}",
                         payload={}, content_hash=f"h-{self.counter}")
        self.db.add(raw)
        self.db.flush()
        job = Job(raw_posting_id=raw.id, source_id=source.id, company_id=company.id,
                  title_raw=title, apply_url=apply_url, status=status,
                  posted_at=NOW, first_seen_at=first_seen, last_seen_at=NOW)
        self.db.add(job)
        self.db.flush()
        for loc in locations or []:
            self.db.add(JobLocation(job_id=job.id, **loc))
        self.db.flush()
        return job


@pytest.fixture
def corpus(db) -> Corpus:
    return Corpus(db)


def _group_of(db, job: Job) -> int | None:
    return db.scalar(select(Job.dedupe_group_id).where(Job.id == job.id))


def test_url_identity_groups_across_sources(db, corpus):
    company_a = corpus.company("Acme", "acme.com")
    company_b = corpus.company("Acme Corp")  # aggregator spells it differently
    ats = corpus.job(corpus.ats, company_a, "Backend Engineer",
                     apply_url="https://Boards.example.com/acme/jobs/123/")
    agg = corpus.job(corpus.agg, company_b, "Sr Backend Eng (Acme)",
                     apply_url="https://boards.example.com/acme/jobs/123?utm_source=agg")

    assign_dedupe_groups(db)

    assert _group_of(db, ats) == ats.id  # representative: ats_api beats aggregator
    assert _group_of(db, agg) == ats.id


def test_query_param_job_ids_are_not_merged(db, corpus):
    """Boards that key jobs by query param must keep distinct postings."""
    company = corpus.company("Acme", "acme.com")
    one = corpus.job(corpus.ats, company, "Backend Engineer",
                     apply_url="https://acme.com/careers?gh_jid=1")
    two = corpus.job(corpus.agg, company, "Platform Engineer",
                     apply_url="https://acme.com/careers?gh_jid=2")

    assign_dedupe_groups(db)

    assert _group_of(db, one) is None
    assert _group_of(db, two) is None


def test_exact_key_groups_matching_company_title_location(db, corpus):
    company_a = corpus.company("Globex", "globex.com")
    company_b = corpus.company("globex")  # same normalized name, no domain
    ats = corpus.job(corpus.ats, company_a, "Data Engineer", locations=[dict(SF)])
    agg = corpus.job(corpus.agg, company_b, "  data   ENGINEER ", locations=[dict(SF)])

    assign_dedupe_groups(db)

    assert _group_of(db, ats) == ats.id
    assert _group_of(db, agg) == ats.id


def test_same_source_never_groups(db, corpus):
    """Two same-titled reqs on one board are two real openings."""
    company = corpus.company("Acme", "acme.com")
    one = corpus.job(corpus.ats, company, "Backend Engineer", locations=[dict(SF)])
    two = corpus.job(corpus.ats, company, "Backend Engineer", locations=[dict(SF)])

    assign_dedupe_groups(db)

    assert _group_of(db, one) is None
    assert _group_of(db, two) is None


def test_location_conflict_blocks_merge(db, corpus):
    company = corpus.company("Acme", "acme.com")
    sf = corpus.job(corpus.ats, company, "Backend Engineer", locations=[dict(SF)])
    nyc = corpus.job(corpus.agg, company, "Backend Engineer", locations=[dict(NYC)])

    assign_dedupe_groups(db)

    assert _group_of(db, sf) is None
    assert _group_of(db, nyc) is None


def test_both_ungeocoded_are_compatible(db, corpus):
    """Two remote copies of the same posting have no geocoded rows."""
    company = corpus.company("Acme", "acme.com")
    a = corpus.job(corpus.ats, company, "Backend Engineer", locations=[dict(REMOTE)])
    b = corpus.job(corpus.agg, company, "Backend Engineer", locations=[dict(REMOTE)])

    assign_dedupe_groups(db)

    assert _group_of(db, a) == a.id
    assert _group_of(db, b) == a.id


def test_different_companies_never_group(db, corpus):
    one = corpus.job(corpus.ats, corpus.company("Acme", "acme.com"),
                     "Backend Engineer", locations=[dict(SF)])
    two = corpus.job(corpus.agg, corpus.company("Globex", "globex.com"),
                     "Backend Engineer", locations=[dict(SF)])

    assign_dedupe_groups(db)

    assert _group_of(db, one) is None
    assert _group_of(db, two) is None


def test_domain_match_is_company_identity(db, corpus):
    """Different display names, same domain: one company."""
    a = corpus.company("Acme Inc.", "acme.com")
    b = corpus.company("Acme Incorporated", "acme.com")
    ats = corpus.job(corpus.ats, a, "Backend Engineer", locations=[dict(SF)])
    agg = corpus.job(corpus.agg, b, "Backend Engineer", locations=[dict(SF)])

    assign_dedupe_groups(db)

    assert _group_of(db, agg) == ats.id


def test_representative_prefers_gov_over_aggregator_and_earliest_first_seen(db, corpus):
    company = corpus.company("Acme", "acme.com")
    later_gov = corpus.job(corpus.gov, company, "Backend Engineer",
                           locations=[dict(SF)], first_seen=NOW + timedelta(days=1))
    early_agg = corpus.job(corpus.agg, company, "Backend Engineer",
                           locations=[dict(SF)], first_seen=NOW)

    assign_dedupe_groups(db)

    # kind rank beats recency: gov_api wins though it was seen later
    assert _group_of(db, later_gov) == later_gov.id
    assert _group_of(db, early_agg) == later_gov.id


def test_expired_representative_yields_to_active_member(db, corpus):
    """The counted row must be one that is actually still live."""
    company = corpus.company("Acme", "acme.com")
    ats = corpus.job(corpus.ats, company, "Backend Engineer",
                     locations=[dict(SF)], status="expired")
    agg = corpus.job(corpus.agg, company, "Backend Engineer", locations=[dict(SF)])

    assign_dedupe_groups(db)

    assert _group_of(db, ats) == agg.id
    assert _group_of(db, agg) == agg.id


def test_recompute_is_idempotent_and_clears_stale_groups(db, corpus):
    company = corpus.company("Acme", "acme.com")
    ats = corpus.job(corpus.ats, company, "Backend Engineer", locations=[dict(SF)])
    agg = corpus.job(corpus.agg, company, "Backend Engineer", locations=[dict(SF)])

    first = assign_dedupe_groups(db)
    second = assign_dedupe_groups(db)
    assert first["groups"] == 1
    assert second == {"groups": 1, "grouped_jobs": 2, "changed": 0}

    # The aggregator copy changes title: no longer the same posting.
    agg_row = db.get(Job, agg.id)
    agg_row.title_raw = "Completely Different Role"
    db.commit()
    assign_dedupe_groups(db)

    assert _group_of(db, ats) is None
    assert _group_of(db, agg) is None


def test_canonical_apply_url_rules():
    assert canonical_apply_url("https://X.com/a/") == canonical_apply_url("https://x.com/a")
    assert canonical_apply_url("https://x.com/a?utm_source=z&b=2&a=1") == \
        canonical_apply_url("https://x.com/a?a=1&b=2")
    assert canonical_apply_url("https://x.com/c?gh_jid=1") != \
        canonical_apply_url("https://x.com/c?gh_jid=2")
    assert canonical_apply_url("https://x.com/a#top") == canonical_apply_url("https://x.com/a")
    assert canonical_apply_url("not a url") is None
