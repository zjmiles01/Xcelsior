# ADR-002: Hybrid extraction pipeline design

**Status:** accepted · **Date:** 2026-07-19

## Context

Every statistic Xcelsior shows derives from structured facts extracted from
messy job-description text. Extraction quality is therefore product
correctness. An LLM-only approach would be expensive at corpus scale,
nondeterministic, and hard to audit; a rules-only approach misses genuinely
ambiguous cases.

## Decision

A layered pipeline where the cheapest sufficient method wins:

1. **Curated taxonomy** (`data/taxonomy/`, ~290 technologies in 10
   categories, ~24 canonical title families) — versioned, reviewed data.
2. **Aho-Corasick alias matching** — one pass per document over all ~600
   aliases, with per-alias gates: word boundaries (hyphen/`&` compound
   blocking for 1–2 char aliases; `+`/`#` token extension), case
   sensitivity ("Go", "R", "Rails"), and context gates for ambiguous
   aliases (nearby tech-context cues, other technologies, or list shape).
3. **Structural rules** — section-header detection (requirements /
   nice-to-have / responsibilities / benefits) drives requirement levels;
   regex extractors for salary (raw + normalized annual USD at 2,080
   hrs/yr), years of experience, and work arrangement.
4. **Confidence scoring and routing** — accepted matches (≥0.6) become
   `job_technologies` rows with evidence snippets; the 0.3–0.6 doubt band
   goes to a review queue (the future LLM-adjudication input); below 0.3 is
   discarded. Titles that fail exact-alias and pg_trgm fallback also queue
   for review.

The LLM is deliberately absent from this milestone: it will consume the
doubt band and propose novel taxonomy terms (human-approved), never
free-write facts.

## Consequences

- **Traceability:** every extracted technology stores the sentence it came
  from; the UI shows it on hover.
- **Reprocessability:** `extractor_version` on jobs + immutable
  `raw_postings` mean extractor improvements re-run over history
  (`xcelsior extract` reprocesses anything below the current version).
- **Measurability:** a hand-labeled gold set (30 docs, growing) gates CI at
  ≥90% skills precision / ≥80% recall. Labels are ground truth; the
  extractor is never "tuned to the test" by editing labels to match output.
- Known limitations: section detection is regex-based and English-only;
  title taxonomy covers software roles only (78.5% resolution among
  engineer-titled postings at v1); confidence thresholds are hand-tuned.

## First full-corpus run (2026-07-19, extractor v1)

12,217 jobs processed: 8,524 with ≥1 technology, 8,595 with salary
extracted, 3,948 titles canonicalized (78.5% of engineer-pattern titles;
unresolved remainder is dominated by non-software roles, visible in the
review queue). Gold-set: precision 1.00 / recall 1.00 (n=30; authored
alongside the extractor, so real-world precision is expected lower —
threshold gates stay at 0.90/0.80).
