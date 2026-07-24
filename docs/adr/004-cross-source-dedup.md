# ADR-004: Cross-source deduplication

**Status:** accepted · **Date:** 2026-07-19

## Context

M5 makes multiple sources live. The same real-world posting reachable
from two sources (a company cross-posted to its own ATS board and an
aggregator, or two boards after an ATS migration) must collapse to one
countable row before it reaches `job_predicate`, or every downstream
number silently double-counts. The existing technical-debt note
sequences this before any public statistics launch.

Design forces:

- A **false merge silently corrupts statistics** and is invisible in any
  eval; a **missed duplicate** is visible (inflated counts) and fully
  recoverable by improving the rules and re-running. Asymmetry demands
  conservatism.
- Provenance is a product promise (every stat traceable to real
  postings), so grouping must never destroy a source's copy.
- The raw layer is immutable; anything derived must be recomputable.

## Decision

**Two deterministic rules, no fuzzy matching, applied only across
different sources** (two same-titled postings on one board are two real
openings — per-source `external_id` uniqueness already gives them one
row each):

1. **URL identity.** Canonicalized apply URLs are equal. Canonical form:
   lowercased scheme/host, fragment dropped, `utm_*` params stripped,
   remaining query params sorted (params are otherwise kept — some ATS
   boards carry the job id in the query), trailing slash trimmed.
2. **Exact key.** Same company identity (exact `name_normalized` match
   or exact domain match), same whitespace/case-normalized `title_raw`,
   and compatible locations: an identical geocoded `(city, region)` in
   common, or neither side geocoded at all (e.g. both remote). A
   resolvable location conflict blocks the merge.

Grouping is the transitive closure of pairwise matches (union-find).

**Representative (the row statistics count):** active members first —
an expired representative would hide a posting still live on a sibling
source — then source kind `ats_api` > `gov_api` > `aggregator_api` (the
company's own board has the fullest text and best extraction), then
earliest `first_seen_at`, then lowest id.

**Storage:** `jobs.dedupe_group_id` holds the representative's id for
every group member (self-referencing for the representative). `NULL`
and self-reference both mean "this row counts" — `job_predicate` adds
one row-local condition and every surface inherits it. `xcelsior
dedupe` recomputes all assignments from scratch after geocoding
(rule 2 depends on resolved locations) and is idempotent.

**Nothing is deleted.** Every member keeps its raw posting, extraction
evidence, and source attribution; ungrouping (a URL changes, a rule
improves) is a plain recompute.

## Consequences

- Aggregator copies of an ATS-boarded job collapse automatically once an
  aggregator source exists; its truncated description never becomes the
  counted row while the ATS copy is active.
- Transitive closure can chain A–B–C even where A and C would not match
  directly; with exact rules this requires a shared exact bridge and is
  accepted.
- The recompute loads the corpus into memory (fine well past 100k jobs;
  revisit with SQL-side blocking if that changes).
- Duplicates the rules cannot see (different title strings across
  sources, no shared URL) remain double-counted until a rule improves —
  the conservative direction, and visible rather than silent.
