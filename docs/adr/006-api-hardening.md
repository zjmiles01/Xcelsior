# ADR-006: API hardening — auth, rate limiting, description sanitization

**Status:** accepted · **Date:** 2026-07-20

## Context

Through M7 the API had no security posture: every endpoint was
unauthenticated, unbounded in request rate, and served descriptions
derived from employer-authored HTML that was stored but never sanitized.
This was recorded as deliberate debt and scoped to the current single-user
development posture — but M7 raised the stakes by putting user-supplied
personal data (name, email, phone, uploaded resume bytes) behind the
unauthenticated profile endpoints. M8 is the "never-cut" milestone that
closes all three gaps before any public deploy.

Three forces shape the choices:

- **The product is single-user in its current posture** (ADR-005). The
  market-analysis surface (jobs, analysis, skills, meta) is public by
  design — it *is* the product. The private surface is the profile/resume
  data of one owner.
- **The deployment target is free, single-instance infrastructure**
  (`infra/render.yaml`: one web service, one cron). No Redis, no second
  process to coordinate shared state.
- **Descriptions are untrusted HTML from third parties.** They are stored
  (`jobs.description`) and, until M8, only ever flattened to plain text
  before display. Rendering them richly — better UX — requires that they
  be safe first.

## Decision

**Auth: one single-user bearer token, not a user-account system.** A
multi-user system would need a `user_id` on every profile row, per-user
data isolation, and login/registration flows — scope the data model does
not need for one owner. Instead, one configured secret
(`XCELSIOR_AUTH_TOKEN`) gates the profile/resume router; the public
market surface stays open. `require_auth` compares the presented bearer
token in constant time (`secrets.compare_digest`). The scheme is
registered with FastAPI so the requirement is documented in OpenAPI (the
`/docs` Authorize button and the generated contract), not just in prose.

Fail-closed, everywhere:
- token **unset** → protected routes return 503 (locked, never silently
  open);
- token unset **in production** → the app refuses to start (a loud
  startup guard beats serving 503s or, worse, going open);
- token **missing/wrong** → 401 with a `WWW-Authenticate: Bearer`
  challenge.

When an LLM or a future multi-tenant need arrives, this is the seam it
replaces — the gate is one dependency and one config value, and the public
surface is unaffected.

**Rate limiting: in-process token bucket per client IP.** Each client gets
`burst` tokens refilling at `per_minute/60` per second; a request costs one
token, and an empty bucket earns 429 + `Retry-After`. It is in-memory on
purpose: with a single instance there is no second process to coordinate,
so a shared store (Redis) would be machinery without a job. With multiple
workers each holds its own buckets and the effective limit scales with
worker count — documented, not accidental. Correctness relies on the
event loop: `check()` never awaits, so each call runs to completion before
the next and no lock is needed. Memory is bounded by evicting buckets that
have (or by sweep time would have) refilled to full — such a bucket is
indistinguishable from a never-seen one, so dropping it changes nothing
and reclaims idle one-hit clients. The limiter scopes to `/api/v1`;
`/health` and `/docs` stay unlimited so health checks are never throttled.
Behind a proxy the client IP must reach the app or all traffic shares one
bucket. **Superseded by the M10 audit fix** (see the addendum below): the
original deploy used uvicorn `--proxy-headers --forwarded-allow-ips *`, but
`*` makes uvicorn take the *leftmost*, client-forgeable `X-Forwarded-For`
entry, so an attacker could rotate spoofed IPs to evade their own limit.
That trust is now removed. Nothing authenticates or authorizes off the
client IP — only the rate limiter reads it — so even the old forgeable value
could not escalate beyond rate-limit evasion.

**Description sanitization: allowlist in the extraction stage, stored, and
served.** The safe form is produced by `nh3` (Rust `ammonia` bindings — a
vetted sanitizer, not a hand-rolled one, which for a security boundary is
the whole point) against an explicit allowlist tuned for job descriptions:
formatting/structure tags only, `href`-only anchors over http(s)/mailto
with a hardening `rel`, everything else (scripts, styles, event handlers,
iframes, unknown schemes) dropped. It lives in **extraction**, versioned by
`EXTRACTOR_VERSION` (bumped 2 → 3), not in ingestion: a tightened allowlist
is then a version bump and a re-extract of the immutable raw layer —
exactly the reprocessing contract every other extractor change follows —
never a re-fetch. The result is stored in `jobs.description_html` and
served on `JobDetail` under the **same display-policy gate** as
`description_text` (extracted-only sources leak neither). The plain-text
`description_text`, whose offsets anchor extraction evidence, is untouched
and independent. The frontend renders `description_html` directly; that is
the one place `dangerouslySetInnerHTML` is used, and it is safe precisely
because the string was sanitized server-side.

## Consequences

- A fresh checkout must set `XCELSIOR_AUTH_TOKEN` to use the profile
  endpoints; unset means 503, by design. The frontend stores the token in
  `localStorage` and offers a one-time unlock form — a single-user "login",
  not an account system.
- The rate limit is per-worker and per-instance. Fine for the current
  single-instance deploy; a horizontal scale-out or a strict global limit
  would need a shared store and a new ADR.
- Sanitization inherits extraction's reprocessing model: existing rows get
  `description_html` on the next full `xcelsior extract` after the version
  bump (the same re-queue that any `EXTRACTOR_VERSION` change triggers).
- `nh3` is a compiled (abi3) dependency. Prebuilt wheels cover the target
  platforms; it is the maintained successor to `bleach` and the correct
  tool for an XSS boundary.
- The auth token is a shared secret, not per-user credentials, and offers
  no repudiation or per-actor audit. Acceptable for a single owner;
  revisit with real accounts if the product ever becomes multi-tenant.

## Addendum (M10 audit fix): un-forgeable rate-limit client IP

The original rate-limit keying trusted uvicorn's `--proxy-headers
--forwarded-allow-ips *`, which resolves `request.client.host` from the
*leftmost* `X-Forwarded-For` entry — a value any client can send. An
attacker could therefore rotate spoofed `X-Forwarded-For` values to land in
a fresh bucket on every request and defeat the limiter (most damagingly on
the auth endpoints, where the limit is brute-force protection).

The fix moves client-IP resolution out of uvicorn and into the app, gated
on an explicit trust count:

- The Dockerfile no longer passes `--proxy-headers`/`--forwarded-allow-ips`,
  so `request.client.host` stays the real socket peer (the platform proxy).
- `resolve_client_ip(peer, x_forwarded_for, trusted_proxies)` derives the
  key. With `XCELSIOR_TRUSTED_PROXY_COUNT = 0` (local/direct connections)
  `X-Forwarded-For` is ignored entirely and the socket peer is used, so a
  direct client cannot choose its bucket. With `N` trusted proxies the key
  is the `N`-th entry from the *end* of `X-Forwarded-For` — the address the
  outermost proxy *we trust* appended. A client may prepend any number of
  forged entries on the left; the trusted-attested tail entry never moves,
  so spoofing cannot evade the limit.
- Render routes through a single load-balancer hop, so its deploy sets
  `XCELSIOR_TRUSTED_PROXY_COUNT = 1` (infra/render.yaml). Taking the last
  entry is correct whether Render appends to or replaces an inbound header.

Tests in `test_ratelimit.py` pin `resolve_client_ip` across hop counts and
prove end-to-end that rotating a spoofed leftmost `X-Forwarded-For` keeps a
client in one bucket (throttled), that genuinely distinct clients still get
independent buckets, and that a direct (untrusted) client cannot use the
header to win a fresh bucket. Nothing else in the app reads the client IP,
so this is purely a limiter-integrity fix.
