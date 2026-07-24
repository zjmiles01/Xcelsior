"""HTML sanitization of stored job descriptions (M8).

Three layers, each with hand-derived truth:
- the pure `sanitize_html` allowlist against real XSS vectors;
- `extract_document` emitting `safe_html` alongside the plain text;
- the full pipeline persisting `jobs.description_html` and the job-detail
  endpoint serving it under the same display-policy gate as description_text.
"""

from app.catalog.models import Company, Job
from app.extraction.core import EXTRACTOR_VERSION, extract_document
from app.extraction.matcher import TechnologyMatcher
from app.extraction.sanitize import sanitize_html
from app.extraction.service import extract_pending
from app.extraction.taxonomy import AliasSpec, TaxonomyIndex, TechSpec
from app.ingestion.models import RawPosting, Source
from tests.resume_taxonomy import seed_micro_taxonomy


def _index() -> TaxonomyIndex:
    """A one-alias index — enough for the Aho-Corasick automaton to build."""
    index = TaxonomyIndex()
    index.technologies["python"] = TechSpec(slug="python", name="Python", category="languages")
    index.aliases.append(
        AliasSpec(alias="python", cased="Python", tech_slug="python",
                  case_sensitive=False, require_context=False)
    )
    return index

# --- the sanitizer in isolation -------------------------------------------


def test_script_tag_and_content_removed():
    assert sanitize_html("<p>Hi</p><script>steal()</script>") == "<p>Hi</p>"


def test_event_handlers_stripped_body_kept():
    assert sanitize_html('<p onclick="steal()">click</p>') == "<p>click</p>"


def test_javascript_and_data_hrefs_dropped_leaving_inert_anchor():
    for scheme in ("javascript:alert(1)", "data:text/html,<script>x</script>"):
        out = sanitize_html(f'<a href="{scheme}">x</a>')
        assert "href" not in out and ">x</a>" in out


def test_safe_link_survives_with_hardening_rel():
    out = sanitize_html('<a href="https://jobs.example.com/apply">Apply</a>')
    assert 'href="https://jobs.example.com/apply"' in out
    assert 'rel="noopener noreferrer nofollow"' in out


def test_style_and_media_and_iframe_removed():
    assert sanitize_html("<style>*{}</style><p>ok</p>") == "<p>ok</p>"
    assert sanitize_html("<img src=x onerror=alert(1)>") is None
    assert sanitize_html('<iframe src="https://evil"></iframe><p>t</p>') == "<p>t</p>"


def test_formatting_and_lists_preserved():
    html = "<p><strong>Requirements</strong></p><ul><li>Python</li><li>Go</li></ul>"
    assert sanitize_html(html) == html


def test_empty_and_none_and_blank_yield_none():
    assert sanitize_html(None) is None
    assert sanitize_html("") is None
    assert sanitize_html("<script>only()</script>") is None


def test_idempotent():
    once = sanitize_html("<p>Hi <b>there</b></p><script>x()</script>")
    assert sanitize_html(once) == once


# --- extract_document emits safe_html -------------------------------------


def test_extract_document_produces_safe_html_and_text():
    index = _index()
    result = extract_document(
        description_html="<p>Build <b>backend</b> systems.</p><script>x()</script>",
        raw_title="Backend Engineer",
        index=index,
        matcher=TechnologyMatcher(index),
    )
    assert result.safe_html == "<p>Build <b>backend</b> systems.</p>"
    assert "script" not in (result.safe_html or "")
    # The plain-text form is unchanged: still flattened, no tags.
    assert "Build backend systems." in result.text
    assert "<" not in result.text


def test_extract_document_plain_text_input_has_no_safe_html():
    index = _index()
    result = extract_document(
        description_html="   ", raw_title="X", index=index, matcher=TechnologyMatcher(index)
    )
    assert result.safe_html is None


# --- pipeline persistence + display-policy gate ---------------------------


def _seed_job(db, description_html: str, display_policy: str) -> int:
    source = Source(name=f"src-{display_policy}", kind="ats_api", display_policy=display_policy)
    db.add(source)
    db.flush()
    company = Company(name="Acme", name_normalized="acme", ats_type="greenhouse", ats_token="acme")
    db.add(company)
    db.flush()
    raw = RawPosting(
        source_id=source.id, external_id="e1", payload={}, content_hash=f"h-{display_policy}"
    )
    db.add(raw)
    db.flush()
    job = Job(
        raw_posting_id=raw.id,
        source_id=source.id,
        company_id=company.id,
        title_raw="Backend Engineer",
        description=description_html,
    )
    db.add(job)
    db.commit()
    return job.id


DIRTY = (
    '<p>Join us.</p><script>evil()</script>'
    '<a href="javascript:x">bad</a><ul><li>Python</li></ul>'
)


def test_extract_persists_sanitized_description_html(db):
    seed_micro_taxonomy(db)
    job_id = _seed_job(db, DIRTY, display_policy="full_text")
    extract_pending(db)
    job = db.get(Job, job_id)
    assert job.extractor_version == EXTRACTOR_VERSION
    assert "script" not in job.description_html
    assert "javascript:" not in job.description_html
    assert "<li>Python</li>" in job.description_html
    # The untrusted raw markup is retained as-is; only the served form is safe.
    assert "<script>" in job.description


def test_job_detail_serves_sanitized_html_for_full_text_source(db, client):
    seed_micro_taxonomy(db)
    job_id = _seed_job(db, DIRTY, display_policy="full_text")
    extract_pending(db)
    body = client.get(f"/api/v1/jobs/{job_id}").json()
    assert "<script>" not in body["description_html"]
    assert "<li>Python</li>" in body["description_html"]


def test_job_detail_withholds_html_for_extracted_only_source(db, client):
    seed_micro_taxonomy(db)
    job_id = _seed_job(db, DIRTY, display_policy="extracted_only")
    extract_pending(db)
    body = client.get(f"/api/v1/jobs/{job_id}").json()
    assert body["description_html"] is None
    assert body["description_text"] is None
