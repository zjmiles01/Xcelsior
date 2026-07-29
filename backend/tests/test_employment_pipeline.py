"""Employment typing through the real pipeline: extraction fills the column
for jobs whose source declared nothing, leaves declared values alone, and
backfills rows that predate the feature (the EXTRACTOR_VERSION bump is what
puts them back in the queue)."""

from sqlalchemy import select

from app.catalog.models import Company, Job
from app.extraction.core import EXTRACTOR_VERSION, extract_document
from app.extraction.matcher import TechnologyMatcher
from app.extraction.service import extract_pending
from app.extraction.taxonomy import AliasSpec, TaxonomyIndex, TechSpec
from app.ingestion.models import RawPosting, Source
from tests.resume_taxonomy import seed_micro_taxonomy


def _index() -> TaxonomyIndex:
    index = TaxonomyIndex()
    index.technologies["python"] = TechSpec(slug="python", name="Python", category="languages")
    index.aliases.append(
        AliasSpec(alias="python", cased="Python", tech_slug="python",
                  case_sensitive=False, require_context=False)
    )
    return index


# --- the pure core --------------------------------------------------------


def test_extract_document_classifies_from_the_title():
    index = _index()
    result = extract_document(
        description_html="<p>Write Python for our platform team.</p>",
        raw_title="Software Engineering Intern",
        index=index,
        matcher=TechnologyMatcher(index),
    )
    assert result.employment_type == "internship"


def test_extract_document_defaults_an_ordinary_role_to_full_time():
    index = _index()
    result = extract_document(
        description_html="<p>Write Python for our platform team.</p>",
        raw_title="Backend Software Engineer",
        index=index,
        matcher=TechnologyMatcher(index),
    )
    assert result.employment_type == "full_time"


def test_extract_document_honors_the_declared_type():
    index = _index()
    result = extract_document(
        description_html="<p>Write Python for our platform team.</p>",
        raw_title="Backend Software Engineer",
        index=index,
        matcher=TechnologyMatcher(index),
        declared_employment_type="internship",
    )
    assert result.employment_type == "internship"


# --- pipeline persistence -------------------------------------------------


def _seed_job(db, title: str, description_html: str = "<p>Build things with Python.</p>",
              employment_type: str | None = None, suffix: str = "") -> int:
    source = db.scalar(select(Source).where(Source.name == "emp-src"))
    if source is None:
        source = Source(name="emp-src", kind="ats_api", display_policy="full_text")
        db.add(source)
        db.flush()
    company = Company(
        name=f"Acme{suffix}", name_normalized=f"acme{suffix}",
        ats_type="greenhouse", ats_token=f"acme{suffix}",
    )
    db.add(company)
    db.flush()
    raw = RawPosting(
        source_id=source.id, external_id=f"e-{suffix}", payload={}, content_hash=f"h-{suffix}"
    )
    db.add(raw)
    db.flush()
    job = Job(
        raw_posting_id=raw.id,
        source_id=source.id,
        company_id=company.id,
        title_raw=title,
        description=description_html,
        employment_type=employment_type,
    )
    db.add(job)
    db.commit()
    return job.id


def test_extraction_fills_employment_type_from_text(db):
    seed_micro_taxonomy(db)
    intern_id = _seed_job(db, "Software Engineering Intern", suffix="1")
    swe_id = _seed_job(db, "Backend Software Engineer", suffix="2")

    extract_pending(db)

    intern, swe = db.get(Job, intern_id), db.get(Job, swe_id)
    assert intern.employment_type == "internship"
    assert swe.employment_type == "full_time"
    assert intern.extractor_version == EXTRACTOR_VERSION


def test_extraction_does_not_overwrite_a_declared_type(db):
    seed_micro_taxonomy(db)
    # The board said "contract" even though the title reads like a
    # permanent role; ingestion's fact outranks extraction's inference.
    job_id = _seed_job(db, "Backend Software Engineer", employment_type="contract", suffix="3")

    extract_pending(db)

    assert db.get(Job, job_id).employment_type == "contract"


def test_stale_extractor_version_backfills_the_column(db):
    seed_micro_taxonomy(db)
    job_id = _seed_job(db, "Data Science Intern", suffix="4")
    # A row as it looks today: extracted by an older extractor, so the
    # column was never populated.
    job = db.get(Job, job_id)
    job.employment_type = None
    job.extractor_version = EXTRACTOR_VERSION - 1
    db.commit()

    extract_pending(db)

    assert db.get(Job, job_id).employment_type == "internship"
