# ADR-003: Analytics engine — one predicate, live aggregation, honest numbers

**Status:** accepted · **Date:** 2026-07-19

## Context

M3 turns extracted facts into market statistics. The dominant risk is not
performance but *silent wrongness*: a dashboard number that disagrees with
its click-through search count, a percentage over an undeclared
denominator, a metro stat polluted by foreign postings.

## Decisions

**One query builder for every number.** `catalog/query.py` turns the
canonical `JobFilters` into the matching-jobs predicate; search selects
rows through it, analytics aggregates over it (one CTE, all aggregates
join it), snapshots capture through it. Enforced culturally by the module
docstring and structurally by the invariant suite (dashboard count ==
search count across predicate shapes, on a 25-job micro-market with
hand-computed truth).

**Live aggregation + exact cache, not precomputation.** The query space
(any title × point × radius) is unbounded; the live computation is cheap
(cold national ≈ 100–310 ms over 12k jobs, budget 500 ms); the
`analysis_cache` absorbs repetition (warm ≈ 13 ms). Because data changes
only nightly, cached payloads are exactly right until
`bump-data-version` truncates the cache and rotates the ETag version as
the pipeline's final step. Precomputation exists only where the space is
bounded: `market_snapshots` (date × tech × title family × national/top-30
metros) — the trends table that must be written daily because history
cannot be recomputed.

**Statistical honesty is server-side.** Payloads carry their denominators
(analyzed jobs, salary-disclosed count); shares are
percent-of-all-analyzed; salary p25/median/p75 use range midpoints over
the disclosed subset only; scopes under 30 jobs get a low-confidence flag
the UI must render. Multi-location postings count once (EXISTS, not
JOIN). Distributions include "unspecified" as a bucket.

**Geocoding is conservative and US-only.** GeoNames-derived city index
(pop ≥ 5k + hand supplement); explicit state codes beat state-name
inference; non-US country markers reject a string outright; famous
world-city names ("London", "Dublin") refuse to fall back to small
same-named US towns. This last rule came from a live bug: ~2,300 foreign
postings had resolved to London OH, Dublin CA, Paris TX and were feeding
metro stats.

**Contract as artifact.** One `JobFilters` model; URL params, API query
params, and cache keys all speak it. The OpenAPI schema is committed and
TypeScript types are generated from it; CI regenerates both and fails on
drift.

## Notable incident during the milestone

Corpus-scale evidence sampling caught "C" at a false 20% share: `8
U.S.C. § 1324b` legal citations in export-control boilerplate matched the
language C on ~1,900 SpaceX postings. The gold set (now including an ITAR
document) couldn't have seen it — labeled sets undercount boilerplate.
Fix: single-letter aliases reject dotted-acronym adjacency; corpus
reprocessed via `EXTRACTOR_VERSION` bump — the retroactive-improvement
mechanism working as designed. Lesson recorded: **sample evidence
snippets at corpus scale after every extractor change**; per-document
eval alone misses systematic boilerplate errors.

## Known limits / graduation criteria

- Radius EXISTS does per-row `earth_distance` (no GiST earth_box index).
  Fine at ~23k location rows; add the functional index when active jobs
  approach ~200k or p95 cold analysis exceeds ~1s.
- Metro snapshot buckets are recomputed nightly (top-30 by job count);
  rank-edge metros may have gappy series. Revisit with a pinned list if
  trend continuity at the margin starts to matter.
- `analysis_cache` grows unbounded within a day only (truncated
  nightly); no eviction needed at MVP query diversity.
