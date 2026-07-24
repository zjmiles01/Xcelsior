# ADR-001: Data coverage go/no-go metrics

**Status:** accepted · **Date:** 2026-07-18

## Context

Xcelsior's value depends entirely on having enough job postings to make
market statistics credible. Data is collected only from free, legally clean
sources (public ATS endpoints, Adzuna, USAJobs), so coverage is the
project's highest-uncertainty risk and must be measured before further
investment, not assumed.

## Decision

Coverage is measured at the end of Milestone 1 (first connector live) and
re-measured at the end of Milestone 5 (all sources live) against:

- **≥ 25,000** active US job postings in the index overall
- **≥ 500** active postings matching the flagship market query
  ("Backend Engineer", San Francisco, 50 mi)

If Milestone 5 misses these numbers, the response is scope adjustment
(fewer flagship markets, honest sample framing), not silent launch.

## Consequences

- The Milestone 1 measurement steers which sources Milestone 5 prioritizes.
- Dashboards must always display the analyzed-jobs denominator, so thin
  coverage is visible rather than hidden.

## First measurement (M1, full 101-company seed list, Greenhouse only)

- 12,217 active postings from 72 reachable boards (29 seed tokens invalid —
  to be corrected or pruned as the list grows toward 500+ companies)
- 4,391 postings with "engineer" in the title; 868 of those list a San
  Francisco location (crude pre-canonicalization proxy for the flagship
  market query)
- 4,100 postings flagged remote by the naive location-text heuristic

**Verdict: on track.** Half the 25k bar from one source and ~14% of the
target company count; the flagship-market proxy already exceeds 500. The
precise measurement reruns at M5 with all sources and real title/geo
canonicalization.

## Second measurement (M5, Greenhouse + Lever live, real canonicalization)

Measured 2026-07-19 through the shared `job_predicate` (deduplicated,
canonical titles, real geocoding) — the first measurement that means
what the bars mean:

- **13,139 active postings** (12,224 Greenhouse across 72 reachable
  boards, 915 Lever across 12 live-verified boards) — **misses the 25k
  bar**
- **47 active postings** for the flagship query (canonical
  Backend Engineer title, San Francisco, 50 mi) — **misses the 500 bar**
  by an order of magnitude. The M1 proxy (868) counted every posting
  with "engineer" in the title and an SF location string; the exact
  query is what a user actually sees
- Cross-source dedup found 0 groups in this corpus (no seed company
  currently runs two boards); the machinery is exercised by tests and
  active for future aggregator sources

**Verdict: bars missed — per this ADR, the response is scope adjustment
and honest sample framing, not silent launch.** M5 deliberately
prioritized production ingestion architecture (generalized connectors,
dedup, expiry, reliability) over source count; one demo source was
added, not all of them. Growth levers, in expected-yield order: the two
keyed aggregator sources this architecture is now ready for (Adzuna,
USAJobs — API credentials are the only gate), growing the seed list
toward 500+ companies, and widening title canonicalization beyond the
current 24 software families. Until the bars are met, every surface
already frames statistics against its server-side `analyzed_jobs`
denominator, so thin coverage stays visible by construction.
