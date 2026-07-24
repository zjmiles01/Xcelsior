# ADR-005: Resume intelligence — deterministic pipeline, user-owned profile

**Status:** accepted · **Date:** 2026-07-19

## Context

M7 adds the first user-supplied data to a system that until now only
ingested public postings: an uploaded PDF resume becomes a structured
candidate profile (skills, work experience, education, job titles) that
future job matching will consume. Design forces:

- The market side already has a hard-won extraction discipline: evidence
  for every fact, deterministic rules first, versioned reprocessing,
  confidence routing. The resume side should inherit it, not reinvent it.
- Matching must eventually join candidate facts against job facts. If the
  two sides don't share vocabulary tables from day one, matching becomes
  a migration project instead of a query.
- A resume is the user's data, and extraction from real-world resumes
  will be imperfect. The user — not an eval set — is the reviewer of
  record; nothing downstream may consume an unreviewed profile.
- There is no auth yet (scheduled M8). Profiles are therefore
  reachable by anyone who can reach the API, which is acceptable only in
  the current single-user development posture and is recorded as debt.

## Decision

**Deterministic core pipeline, no LLM.** PDF → text via `pypdf`
(pure-Python, deterministic) → resume-specific section segmentation →
rule-based entry parsing. Skills reuse the existing Aho-Corasick
`TechnologyMatcher` and technology taxonomy verbatim; titles reuse
`canonicalize_title` and the title taxonomy. The same input always
produces the same profile. An LLM may later *propose* profile edits, but
they land through the same review/edit path as human edits — the exact
rule ADR-002/M6a established for taxonomy curation.

**The market three-layer discipline, mirrored:**

- Raw: `resumes` — original bytes (BYTEA, ≤5 MB), sha256 `content_hash`
  (unique: re-uploading identical bytes is idempotent), extracted text,
  `parser_name`/`parser_version`. A parser fix is a version bump and a
  re-parse of stored bytes, never a re-upload — the resume-side analog of
  `extractor_version` over `raw_postings`.
- Canonical: `candidate_profiles` (1:1 with resume, `extractor_version`,
  `extracted_at`) plus fact tables `profile_skills`,
  `profile_experiences`, `profile_education`. Every extracted fact
  carries evidence — snippet + character offsets into
  `resumes.extracted_text` — the same traceability contract as
  `job_technologies`.

One deliberate divergence from the market layers: profile facts are
**user-editable in place**. Job facts are derived data, rebuildable from
raw; profile facts become *user-owned* data the moment the user reviews
them. Edits set `origin: manual` (or clear evidence fields), and
re-extraction is only ever an explicit user action that discards edits —
never something the pipeline does behind the user's back.

**Matching-readiness is structural.** `profile_skills.technology_id`
references the same `technologies` table `job_technologies` does;
`profile_experiences.canonical_title_id` references the same
`canonical_titles` table `jobs` do; experience date ranges give years of
experience. Future matching is a join plus scoring policy — no schema
change anticipated.

**Review is a gate, not a suggestion.** `candidate_profiles.reviewed_at`
is NULL until the user confirms the extraction. Any future consumer
(matching, recommendations, exports) must treat NULL as "not usable
yet". Extraction confidence is shown, not hidden: doubt-band skill
matches (0.3–0.6) are included on the extracted profile flagged by their
confidence value, because here the user reviewing their own resume *is*
the review queue.

**Storage and deletion.** PDF bytes live in Postgres — one durable
store, transactional with the profile, trivially adequate at portfolio
scale; revisit object storage only if resumes ever become numerous.
`DELETE /profiles/{id}` removes the profile *and* its resume row: the
raw layer's append-only rule protects market data provenance, and does
not override a user deleting their own uploaded document.

**Layering.** New `app.profile` package sits beside `app.analytics`
(above `extraction`, whose pure matcher/title modules it reuses; above
`catalog`, whose taxonomy tables it references). Enforced by the same
import-linter contract as everything else.

## Consequences

- Two-column or heavily designed PDFs may extract in awkward reading
  order; scanned (image-only) PDFs are rejected loudly rather than
  OCR'd. Both are visible failures the review UI surfaces, consistent
  with "conservative and visible beats clever and silent".
- Skills the taxonomy doesn't know are not extracted (the resume side
  inherits taxonomy gaps). They can be added manually, and taxonomy
  growth + re-extraction picks them up later — same loop as jobs.
- Until auth lands (M8), profile endpoints are unauthenticated. Recorded
  in HANDOFF known debt; matching/launch is gated on closing it.
- `RESUME_PARSER_VERSION` and `RESUME_EXTRACTOR_VERSION` version the two
  stages independently (text extraction vs. fact extraction), so a
  parser swap and an extractor fix each invalidate exactly the work they
  changed.
