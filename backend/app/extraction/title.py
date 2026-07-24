"""Title canonicalization: raw posting titles → canonical title families.

Strategy (cheapest sufficient method wins, same philosophy as tech
extraction): normalize → split into segments → strip seniority/level tokens
→ exact alias lookup → token-suffix lookup ("Streaming Platform Engineer"
ends in "Platform Engineer"). When several families match, the most
specific wins — the generic software-engineer family only applies when
nothing sharper does. The pg_trgm similarity fallback and review-queue
insertion live in the service layer because they need the database; this
module stays pure. Seniority tokens are extracted as a by-product because
titles are the best experience-level signal available.
"""

import re
from dataclasses import dataclass

from app.extraction.taxonomy import TaxonomyIndex

GENERIC_TITLE_SLUG = "software-engineer"

_PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_SPLIT_RE = re.compile(r"\s*[|,–—/]\s*|\s+-\s+")
_WS_RE = re.compile(r"\s+")

_LEVEL_TOKENS: dict[str, str] = {
    "intern": "entry", "internship": "entry", "co-op": "entry", "coop": "entry",
    "junior": "entry", "jr": "entry", "associate": "entry",
    "entry": "entry", "entry-level": "entry", "graduate": "entry", "grad": "entry",
    "university": "entry", "early": "entry",
    "mid": "mid", "mid-level": "mid", "intermediate": "mid",
    "senior": "senior", "sr": "senior", "lead": "senior",
    "staff": "staff_plus", "principal": "staff_plus", "distinguished": "staff_plus",
}
_STRIP_TOKENS = {"new", "career"}
_ORDINAL_LEVELS = {
    "1": "entry", "i": "entry",
    "2": "mid", "ii": "mid", "3": "mid",
    "iii": "senior", "4": "senior", "iv": "senior",
    "5": "staff_plus", "v": "staff_plus",
}
# Company ladder notations: L3/E3/IC3-style levels.
_LADDER_RE = re.compile(r"^(?:l|e|ic)([3-8])$")
_LADDER_LEVELS = {
    "3": "entry", "4": "mid", "5": "senior",
    "6": "staff_plus", "7": "staff_plus", "8": "staff_plus",
}
_ORDINAL_RE = re.compile(r"^(i{1,3}|iv|v|[1-9]|l[3-8]|e[3-8]|ic[3-8])$")


@dataclass(frozen=True)
class TitleResult:
    canonical_slug: str | None
    level: str | None  # entry | mid | senior | staff_plus
    normalized: str  # stripped form used for lookup (and as the review-queue key)


def canonicalize_title(raw_title: str, index: TaxonomyIndex) -> TitleResult:
    cleaned = _WS_RE.sub(" ", _PAREN_RE.sub(" ", raw_title.lower())).strip()
    segments = [s for s in _SPLIT_RE.split(cleaned) if s]

    candidates = [cleaned, *segments]
    if len(segments) == 2:
        # "Software Engineer, Infrastructure" → "infrastructure software engineer"
        candidates.append(f"{segments[1]} {segments[0]}")
        # "Software Engineer, Data Platform" → "data platform engineer"
        if "engineer" in segments[0] or "developer" in segments[0]:
            candidates.append(f"{segments[1]} engineer")

    level: str | None = None
    forms: list[str] = []
    for candidate in candidates:
        stripped_tokens: list[str] = []
        for token in candidate.split():
            bare = token.strip(".,:;")
            if bare in _LEVEL_TOKENS:
                level = level or _LEVEL_TOKENS[bare]
            elif _ORDINAL_RE.match(bare):
                ladder = _LADDER_RE.match(bare)
                if ladder:
                    level = level or _LADDER_LEVELS.get(ladder.group(1))
                else:
                    level = level or _ORDINAL_LEVELS.get(bare)
            elif bare not in _STRIP_TOKENS and bare:
                stripped_tokens.append(bare)
        stripped = " ".join(stripped_tokens)
        for form in (candidate, stripped):
            form = _WS_RE.sub(" ", form).strip()
            if form and form not in forms:
                forms.append(form)

    hits: list[str] = []
    for form in forms:
        slug = index.title_aliases.get(form)
        if slug:
            hits.append(slug)
    for form in forms:  # suffix pass, min 2-token suffixes
        tokens = form.split()
        for i in range(1, len(tokens) - 1):
            slug = index.title_aliases.get(" ".join(tokens[i:]))
            if slug:
                hits.append(slug)

    normalized = _strip_only(forms, cleaned)
    chosen = next((slug for slug in hits if slug != GENERIC_TITLE_SLUG), hits[0] if hits else None)
    return TitleResult(canonical_slug=chosen, level=level, normalized=normalized)


def _strip_only(forms: list[str], cleaned: str) -> str:
    # forms[1] is the stripped variant of the full cleaned title when it
    # differs; fall back to the cleaned title itself.
    return forms[1] if len(forms) > 1 and forms[0] == cleaned else cleaned
