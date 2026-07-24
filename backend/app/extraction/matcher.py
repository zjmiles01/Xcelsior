"""Technology mention detection: one Aho-Corasick pass over the document,
then per-match gates (word boundaries, case, context) and confidence scoring.

Aho-Corasick searches for every alias simultaneously in a single O(text)
scan — with ~600 aliases, naive per-alias scanning would be 600 passes.
The automaton is built once per taxonomy load and reused across documents.
"""

import re
from dataclasses import dataclass

import ahocorasick

from app.extraction.taxonomy import AliasSpec, TaxonomyIndex

# Confidence routing thresholds: accepted matches become job_technologies;
# the band between REVIEW and ACCEPT goes to the review queue (the "doubt
# band" that LLM adjudication will consume in a later milestone); below
# REVIEW is discarded.
ACCEPT_THRESHOLD = 0.6
REVIEW_THRESHOLD = 0.3

_WORD_CHARS = re.compile(r"[A-Za-z0-9_]")
# Cues that a risky alias ("Go", "R", "Spring") is being used as a technology.
_CONTEXT_CUES = re.compile(
    r"experience|proficien|knowledge|programming|language|develop|engineer|"
    r"code|coding|stack|framework|librar|tool|technolog|written in|"
    r"expertise|familiar|skills|backend|frontend|infrastructure|services",
    re.IGNORECASE,
)
_CONTEXT_WINDOW = 90


@dataclass(frozen=True)
class TechMatch:
    spec: AliasSpec
    start: int
    end: int
    passed_context_gate: bool

    @property
    def tech_slug(self) -> str:
        return self.spec.tech_slug


@dataclass
class ScoredTech:
    tech_slug: str
    confidence: float
    occurrences: int
    evidence: str
    evidence_start: int
    occurrence_starts: list[int]


class TechnologyMatcher:
    def __init__(self, index: TaxonomyIndex) -> None:
        self._automaton = ahocorasick.Automaton()
        grouped: dict[str, list[AliasSpec]] = {}
        for spec in index.aliases:
            grouped.setdefault(spec.alias, []).append(spec)
        for alias, specs in grouped.items():
            self._automaton.add_word(alias, specs)
        self._automaton.make_automaton()

    def find(self, text: str) -> list[TechMatch]:
        lower = text.lower()
        raw: list[tuple[int, int, AliasSpec]] = []
        for end_idx, specs in self._automaton.iter(lower):
            for spec in specs:
                start = end_idx - len(spec.alias) + 1
                end = end_idx + 1
                if not _boundary_ok(lower, start, end):
                    continue
                if spec.case_sensitive and text[start:end] != spec.cased:
                    continue
                raw.append((start, end, spec))

        # Suppress matches strictly contained in a longer match's span:
        # "Ruby" inside "Ruby on Rails" is not a separate mention.
        raw.sort(key=lambda item: item[0] - item[1])  # longest first
        kept: list[tuple[int, int, AliasSpec]] = []
        for start, end, spec in raw:
            contained = any(
                ks <= start and end <= ke and (ke - ks) > (end - start)
                for ks, ke, _ in kept
            )
            if not contained:
                kept.append((start, end, spec))
        raw = sorted(kept, key=lambda item: item[0])

        # Context gates may use "another technology mentioned nearby" as a
        # cue, so gates are evaluated after all raw matches are collected.
        positions = [(s, spec.tech_slug) for s, _, spec in raw]
        matches: list[TechMatch] = []
        for start, end, spec in raw:
            gate_ok = True
            if spec.require_context:
                gate_ok = _context_gate(text, start, end, spec.tech_slug, positions)
            matches.append(TechMatch(spec=spec, start=start, end=end, passed_context_gate=gate_ok))
        return matches

    def score(
        self, text: str, matches: list[TechMatch]
    ) -> tuple[list[ScoredTech], list[ScoredTech]]:
        """Aggregate matches per technology, score, and route.

        Returns (accepted, review_band). Base confidence reflects alias
        risk and gate outcome; repeated mentions add a small boost. Section
        placement is handled by the caller, which knows section spans.
        """
        by_tech: dict[str, list[TechMatch]] = {}
        for m in matches:
            by_tech.setdefault(m.tech_slug, []).append(m)

        accepted: list[ScoredTech] = []
        review: list[ScoredTech] = []
        for slug, tech_matches in by_tech.items():
            gated = [m for m in tech_matches if m.passed_context_gate]
            usable = gated or tech_matches
            best = usable[0]
            risky = best.spec.require_context or len(best.spec.alias) <= 2

            if not gated:
                confidence = 0.35  # risky alias with no context support anywhere
            elif risky:
                confidence = 0.7  # risky alias that passed its gate
            else:
                confidence = 0.9  # unambiguous alias
            if len(usable) >= 2:
                confidence = min(1.0, confidence + 0.05)

            scored = ScoredTech(
                tech_slug=slug,
                confidence=round(confidence, 2),
                occurrences=len(usable),
                evidence=line_around(text, best.start)[:300],
                evidence_start=best.start,
                occurrence_starts=[m.start for m in usable],
            )
            if confidence >= ACCEPT_THRESHOLD:
                accepted.append(scored)
            elif confidence >= REVIEW_THRESHOLD:
                review.append(scored)
        return accepted, review


def _boundary_ok(lower: str, start: int, end: int) -> bool:
    # For 1-2 char aliases a hyphen joins them into a compound token
    # ("Objective-C", "R-squared", "go-getter" must not match C/R/Go), but
    # long aliases stay valid before a hyphen ("PostgreSQL-backed").
    short_alias = (end - start) <= 2
    if start > 0:
        prev = lower[start - 1]
        if _WORD_CHARS.match(prev) or (short_alias and prev in "-&"):
            return False
        # A single letter directly after a period is a dotted acronym
        # ("8 U.S.C. § 1324b" in export-control boilerplate), not a
        # language mention. Legit "C" always follows space/punct-space.
        if (end - start) == 1 and prev == ".":
            return False
    if end < len(lower):
        nxt = lower[end]
        # '+' and '#' extend tokens: "C" must not match inside C++ / C#.
        # For short aliases '-' and '&' join compounds too: "Objective-C",
        # "R&D", "go-getter" are not mentions of C, R, or Go.
        if _WORD_CHARS.match(nxt) or nxt in "+#" or (short_alias and nxt in "-&"):
            return False
    return True


def _context_gate(
    text: str, start: int, end: int, slug: str, positions: list[tuple[int, str]]
) -> bool:
    window_start = max(0, start - _CONTEXT_WINDOW)
    window_end = min(len(text), end + _CONTEXT_WINDOW)
    if _CONTEXT_CUES.search(text[window_start:window_end]):
        return True
    # A different technology nearby is strong evidence of a tech list
    # ("Go, Python, and Kubernetes").
    for other_start, other_slug in positions:
        if other_slug != slug and abs(other_start - start) <= _CONTEXT_WINDOW:
            return True
    line = line_around(text, start)
    return line.count(",") >= 2 or line.lstrip().startswith("•")


def line_around(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()
