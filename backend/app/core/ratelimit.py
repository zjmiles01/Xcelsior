"""In-process per-client rate limiting for the API (M8, ADR-006).

A token bucket per client IP: each client gets `burst` tokens that refill
at `per_minute/60` per second. A request costs one token; a client with
none gets 429 + Retry-After. This is deliberately in-memory — the product
runs as a single instance on free infrastructure, so a shared store
(Redis) would be machinery without a second process to coordinate. With
multiple workers each holds its own buckets; the effective limit scales
with worker count, which is documented, not accidental (ADR-006).

The limiter is only correct single-threaded, and it is: check() never
awaits, so within uvicorn's event loop each call runs to completion before
the next — no lock needed. Memory is bounded by evicting full buckets
(a full bucket is indistinguishable from a never-seen one).
"""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core.errors import problem_response

# Sweep cadence: every N checks, drop buckets that have refilled to full.
_SWEEP_EVERY = 1024


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after: float  # seconds until the next token; 0 when allowed


class RateLimiter:
    def __init__(
        self, per_minute: int, burst: int, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.enabled = per_minute > 0
        self._per_second = per_minute / 60.0
        self._burst = float(max(burst, 1))
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._since_sweep = 0

    def check(self, key: str) -> RateDecision:
        """Charge one token to `key`; allow iff a token was available."""
        if not self.enabled:
            return RateDecision(True, 0.0)
        now = self._clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=self._burst, updated=now)
            self._buckets[key] = bucket
        else:
            elapsed = now - bucket.updated
            bucket.tokens = min(self._burst, bucket.tokens + elapsed * self._per_second)
            bucket.updated = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            decision = RateDecision(True, 0.0)
        else:
            decision = RateDecision(False, (1.0 - bucket.tokens) / self._per_second)
        # Sweep after charging: the just-touched bucket now holds < burst
        # tokens (or is being denied), so it is never the one evicted here.
        self._maybe_sweep(now)
        return decision

    def _maybe_sweep(self, now: float) -> None:
        self._since_sweep += 1
        if self._since_sweep < _SWEEP_EVERY:
            return
        self._since_sweep = 0
        # Evict any bucket that has (or by `now` would have) refilled to full:
        # such a bucket carries no state a fresh one wouldn't, so dropping it
        # is behaviour-preserving and bounds memory against one-hit clients.
        idle = [
            key
            for key, bucket in self._buckets.items()
            if bucket.tokens + (now - bucket.updated) * self._per_second >= self._burst
        ]
        for key in idle:
            del self._buckets[key]


def resolve_client_ip(
    peer: str | None, forwarded_for: str | None, trusted_proxies: int
) -> str:
    """The IP to rate-limit a request by, chosen so a client cannot forge it.

    With no trusted proxies (`trusted_proxies <= 0`) the only trustworthy
    signal is the socket peer: `X-Forwarded-For` is attacker-controlled and is
    ignored entirely, so a directly-connected client cannot pick its own
    bucket by sending a header.

    Behind `N` trusted proxies, each proxy appends the address it received the
    request *from* to `X-Forwarded-For`, left to right. The real client is
    therefore the entry `N` from the end — the one written by the outermost
    proxy we trust. A client may prepend any number of forged entries on the
    left; it can never change that Nth-from-last value, so it cannot rotate
    spoofed IPs to escape a rate limit. (If the header is shorter than the
    trusted hop count — a misconfiguration or a direct hit that skipped the
    proxy — we fall back to the leftmost present entry, never something the
    request could have chosen more freely.)"""
    fallback = peer or "unknown"
    if trusted_proxies <= 0 or not forwarded_for:
        return fallback
    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    if not parts:
        return fallback
    index = len(parts) - trusted_proxies
    return parts[index] if index >= 0 else parts[0]


def rate_limit_response(decision: RateDecision) -> JSONResponse:
    retry_after = max(1, math.ceil(decision.retry_after))
    return problem_response(
        429,
        "Too many requests",
        "Rate limit exceeded; slow down and retry.",
        headers={"Retry-After": str(retry_after)},
    )


def add_rate_limit_middleware(
    app: FastAPI, limiter: RateLimiter, *, trusted_proxies: int = 0
) -> None:
    """Install per-client rate limiting over the /api/v1 surface. Health
    checks and docs live outside that prefix and stay unlimited.

    `trusted_proxies` is the number of reverse proxies in front of the app;
    it decides how the client IP is derived from `X-Forwarded-For` (see
    `resolve_client_ip`). Left at 0, forwarded headers are ignored and the
    socket peer is used, which is correct for direct/local connections."""

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next) -> Response:
        if limiter.enabled and request.url.path.startswith("/api/v1"):
            peer = request.client.host if request.client else None
            key = resolve_client_ip(
                peer, request.headers.get("x-forwarded-for"), trusted_proxies
            )
            decision = limiter.check(key)
            if not decision.allowed:
                return rate_limit_response(decision)
        return await call_next(request)
