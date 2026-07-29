"""The pure extraction pipeline: HTML in, structured extraction out.

No I/O and no database — everything here runs identically in the live
pipeline, the gold-set evaluation, and unit tests. The service layer wraps
this with persistence.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.extraction.employment import classify_employment_type
from app.extraction.experience import (
    extract_years_of_experience,
    infer_arrangement,
    level_from_years,
)
from app.extraction.matcher import ScoredTech, TechnologyMatcher, line_around
from app.extraction.salary import SalaryExtraction, extract_salary
from app.extraction.sanitize import sanitize_html
from app.extraction.sections import Section, detect_sections, requirement_level_at
from app.extraction.taxonomy import TaxonomyIndex
from app.extraction.text import html_to_text
from app.extraction.title import TitleResult, canonicalize_title

# v3 (M8): extraction now also emits sanitized display HTML (safe_html).
# v4: extraction infers employment_type from title + description text for
# jobs whose source declared none. The bump re-runs the whole corpus, which
# is what backfills the column for postings ingested before this landed.
EXTRACTOR_VERSION = 4


@dataclass(frozen=True)
class ExtractedTechnology:
    tech_slug: str
    requirement_level: str  # required | preferred | mentioned
    confidence: float
    occurrences: int
    evidence: str
    evidence_start: int


@dataclass
class DocumentExtraction:
    text: str
    # Sanitized display HTML — the same source markup as `text`, but kept as
    # a safe formatting subset instead of flattened. None when empty.
    safe_html: str | None = None
    sections: list[Section] = field(default_factory=list)
    technologies: list[ExtractedTechnology] = field(default_factory=list)
    review_band: list[ScoredTech] = field(default_factory=list)
    salary: SalaryExtraction | None = None
    years_of_experience: int | None = None
    arrangement: str | None = None
    title: TitleResult | None = None
    experience_level: str | None = None
    employment_type: str | None = None


def extract_document(
    description_html: str,
    raw_title: str,
    index: TaxonomyIndex,
    matcher: TechnologyMatcher,
    location_is_remote: bool = False,
    declared_employment_type: str | None = None,
) -> DocumentExtraction:
    text = html_to_text(description_html)
    result = DocumentExtraction(text=text, safe_html=sanitize_html(description_html))

    result.sections = detect_sections(text)

    matches = matcher.find(text)
    accepted, result.review_band = matcher.score(text, matches)
    result.technologies = [
        _with_requirement_level(t, result.sections, text) for t in accepted
    ]

    result.salary = extract_salary(text)
    result.years_of_experience = extract_years_of_experience(text)
    result.arrangement = infer_arrangement(text, location_is_remote)
    result.title = canonicalize_title(raw_title, index)
    result.employment_type = classify_employment_type(
        raw_title, text, declared=declared_employment_type
    )

    # Title tokens are the strongest level signal; YOE is the fallback.
    if result.title.level:
        result.experience_level = result.title.level
    elif result.years_of_experience is not None:
        result.experience_level = level_from_years(result.years_of_experience)

    return result


_LEVEL_RANK = {"required": 0, "preferred": 1, "mentioned": 2}


def _with_requirement_level(
    scored: ScoredTech, sections: list[Section], text: str
) -> ExtractedTechnology:
    """A technology mentioned in both the intro and the requirements list is
    a requirement — classify by the strongest section any occurrence falls
    in, and point the evidence at that occurrence."""
    best_level, best_start = "mentioned", scored.evidence_start
    for start in scored.occurrence_starts:
        level = requirement_level_at(sections, start)
        if _LEVEL_RANK[level] < _LEVEL_RANK[best_level]:
            best_level, best_start = level, start
    confidence = scored.confidence
    if best_level in ("required", "preferred"):
        confidence = min(1.0, confidence + 0.05)
    return ExtractedTechnology(
        tech_slug=scored.tech_slug,
        requirement_level=best_level,
        confidence=round(confidence, 2),
        occurrences=scored.occurrences,
        evidence=line_around(text, best_start)[:300],
        evidence_start=best_start,
    )


def format_salary(salary: SalaryExtraction) -> tuple[Decimal, Decimal, str, Decimal, Decimal]:
    return (
        salary.min_amount,
        salary.max_amount,
        salary.period,
        salary.annual_min,
        salary.annual_max,
    )
