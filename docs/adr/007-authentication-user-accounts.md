# ADR-007: Authentication & user accounts — sessions, ownership, saved jobs

**Status:** accepted · **Date:** 2026-07-21

## Context

M8 (ADR-006) closed the security gap with a single shared bearer token
gating the profile/resume router. That was correct for a single-owner
development posture and explicitly recorded as debt: "a real multi-tenant
product needs user accounts (a `user_id` on profiles, login, per-user
isolation) and a new ADR." M10 is that milestone. It turns Xcelsior into a
multi-user SaaS where every user's personal data belongs to their account
and only their account.

The forces:

- **The public market surface must stay open.** Jobs, analysis, skills,
  dashboards, and job detail are the product; a visitor browses them
  without an account. Only the *personal* actions — uploading a resume,
  editing a profile, running the matcher, viewing My Matches, saving
  jobs — require authentication.
- **The shared token has to go, from the user's perspective.** The M8
  experience exposed a secret the user typed into an unlock box and that
  the frontend stored in `localStorage`. That is not an account system and
  it leaks a long-lived credential to JavaScript.
- **Same-origin deployment** (Vite proxies `/api` in dev; one host in
  prod). Cookies and CORS behave identically in both, so a cookie-based
  session is natural and needs no cross-origin machinery.
- **Single-instance, free infrastructure** (unchanged from M8): no Redis,
  no external session store.

## Decision

**Email/password accounts with server-side sessions in an HTTP-only
cookie.** Four decisions follow from "secure, revocable, nothing
long-lived in the browser":

1. **Argon2id password hashing** (`argon2-cffi`, `app/accounts/
   security.py`). The reference binding of the PHC winner: memory-hard,
   salted internally, self-describing parameters. No plaintext is ever
   stored; `verify_password` collapses every failure (mismatch, corrupt
   hash) to `False` so callers cannot distinguish them.

2. **Server-side sessions, not signed tokens.** A session is a row in
   `sessions` (`user_id`, `token_hash`, `expires_at`). The cookie holds an
   opaque 256-bit random token; only its **SHA-256 hash** is stored, so a
   database leak does not hand out live sessions. Server-side was chosen
   over a self-contained JWT precisely because it is **revocable**: logout
   deletes the row, and a "sign out everywhere" is a `DELETE` away. Session
   lookup is an indexed equality on the hash — no per-request crypto.

3. **HTTP-only, SameSite=Lax, Secure-in-prod cookie.** The token is never
   readable by JavaScript (no `localStorage`, the deliberate break from
   M8), `SameSite=Lax` lets normal navigation carry the session while
   blocking cross-site POSTs, and `Secure` is set outside development so it
   never travels over plain HTTP once deployed.

4. **Ownership is always derived from the session, never from the
   request.** `resumes`, `candidate_profiles`, and `saved_jobs` each carry
   a `user_id`. Every personal-data query is scoped to `require_user`'s
   `user.id`; a path or body id belonging to another user resolves to a
   **404**, identical to a nonexistent id — the API is not an existence
   oracle. `resumes.content_hash` uniqueness moved from global to
   **per-user** so two users may upload the same file as independent
   private documents.

**Saved jobs are an ownership edge with a live match, not a snapshot.** A
`saved_jobs` row is just `(user_id, job_id)`. Saving never removes a job
from search — the search/detail UIs reflect saved state by asking which ids
are saved and toggling a button. The saved-jobs dashboard recomputes each
job's match **live** against the user's most recently reviewed profile,
reusing the exact M9 scoring (`score_job`), so the score, matched skills,
and gaps always reflect the profile the user has *now*. A saved job with no
signal is still shown and explained (the M9 matcher's "drop zero-overlap"
rule is opt-out here via `require_signal=False`) because the user
explicitly chose to track it.

**A new leaf-adjacent package, `app.accounts`**, holds the User/Session
models, Argon2 + token primitives, the session service, the FastAPI cookie
dependencies (`require_user` / `get_optional_user`), and the `/auth`
router. It imports only `app.core` and sits just below `app.catalog` in the
import-linter layering, so `app.profile` (profiles + saved jobs) can depend
on it without breaking the architecture contract.

## Alternatives considered

- **Keep the shared token / add JWTs.** The shared token is not an account
  system. A stateless JWT-in-cookie avoids a session table but cannot be
  revoked without one anyway (a denylist), so the table wins on
  revocability at no real cost at this scale.
- **`user_id` nullable + backfill.** Pre-M10 profiles were gated by one
  shared token and belong to no account; there is no correct owner to
  assign. The migration deletes those orphan personal rows (the immutable
  job corpus is untouched) and makes `user_id` NOT NULL, so the invariant
  "personal data always has an owner" holds structurally.
- **403 vs 404 for another user's resource.** 404 is chosen so the API
  never confirms that a resource it won't serve exists.

## Deliberately out of scope (recorded, not forgotten)

Email verification, password reset, OAuth providers, billing, multiple
resumes per user, application-status tracking, recruiter/admin accounts,
and social features. M10 is scoped to secure authentication, per-user
ownership, persistent profiles, and intelligent saved jobs. Each omission
is a known follow-on, not an oversight.

## Consequences

- The M8 single-user-auth debt is closed. The public market surface stays
  open by design; the personal surface is per-user and isolated.
- New contract: `/auth/{signup,login,logout,me}` and `/saved-jobs*`; the
  profile routes drop the `BearerToken` scheme for the session cookie.
- New migration (#8) and three new tables; `resumes`/`candidate_profiles`
  gain `user_id`. Reversible.
- **Rate limiting (ADR-006) is unchanged and still keyed by IP** — it
  throttles abuse, orthogonal to identity.
- A future "sign out everywhere", session listing, or sliding-expiry
  refresh is a query away because sessions are server-side. Password reset
  / email verification, when they land, compose onto this without a schema
  redesign.
