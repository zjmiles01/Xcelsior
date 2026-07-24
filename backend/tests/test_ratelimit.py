"""In-process rate limiting (M8, ADR-006).

The token-bucket math is exercised with an injected clock so every
assertion is exact, and the middleware wiring is exercised on a tiny app
so the 429 + Retry-After + /api/v1 scoping are pinned end-to-end.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.ratelimit import (
    _SWEEP_EVERY,
    RateLimiter,
    add_rate_limit_middleware,
    resolve_client_ip,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_burst_then_denied():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=3, clock=clock)
    assert [limiter.check("ip").allowed for _ in range(3)] == [True, True, True]
    denied = limiter.check("ip")
    assert denied.allowed is False
    # 60/min = 1 token/sec, so the next token is ~1s away.
    assert denied.retry_after == 1.0


def test_refill_over_time():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=2, clock=clock)
    limiter.check("ip")
    limiter.check("ip")
    assert limiter.check("ip").allowed is False
    clock.t = 1.0  # one second -> one token back
    assert limiter.check("ip").allowed is True
    assert limiter.check("ip").allowed is False


def test_refill_caps_at_burst():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=2, clock=clock)
    limiter.check("ip")  # 2 -> 1
    clock.t = 1000.0  # a long idle can't bank more than `burst`
    assert [limiter.check("ip").allowed for _ in range(2)] == [True, True]
    assert limiter.check("ip").allowed is False


def test_keys_are_independent():
    limiter = RateLimiter(per_minute=60, burst=1, clock=FakeClock())
    assert limiter.check("a").allowed is True
    assert limiter.check("b").allowed is True  # b's bucket is untouched by a
    assert limiter.check("a").allowed is False


def test_disabled_limiter_always_allows():
    limiter = RateLimiter(per_minute=0, burst=5)
    assert limiter.enabled is False
    assert all(limiter.check("ip").allowed for _ in range(100))


def test_idle_buckets_are_evicted():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=2, clock=clock)
    limiter.check("idle")  # drops to 1 token at t=0, then goes untouched
    clock.t = 100.0  # long enough that "idle" has fully refilled
    limiter._since_sweep = _SWEEP_EVERY - 1  # arm the next check to sweep
    limiter.check("active")
    assert "idle" not in limiter._buckets  # refilled-to-full bucket dropped
    assert "active" in limiter._buckets  # just-charged bucket kept


def _app(limiter: RateLimiter, *, trusted_proxies: int = 0) -> TestClient:
    app = FastAPI()
    add_rate_limit_middleware(app, limiter, trusted_proxies=trusted_proxies)

    @app.get("/api/v1/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_middleware_returns_429_with_retry_after():
    client = _app(RateLimiter(per_minute=60, burst=2))
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/api/v1/ping").status_code == 200
    limited = client.get("/api/v1/ping")
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert limited.headers["content-type"].startswith("application/problem+json")


def test_middleware_does_not_limit_outside_api_prefix():
    client = _app(RateLimiter(per_minute=60, burst=1))
    client.get("/api/v1/ping")  # exhausts the api bucket
    # /health is outside /api/v1 and must never be limited (health checks).
    assert all(client.get("/health").status_code == 200 for _ in range(5))


# ── Client-IP resolution: the X-Forwarded-For trust boundary (M10) ───────
#
# The rate-limit key must not be forgeable. resolve_client_ip decides which
# IP a request is charged to, given how many proxy hops we trust.


def test_resolve_ignores_forwarded_for_when_no_trusted_proxies():
    # trusted_proxies=0: a directly-connected client cannot pick its bucket
    # by sending X-Forwarded-For — only the socket peer counts.
    assert resolve_client_ip("10.0.0.9", "1.1.1.1", 0) == "10.0.0.9"
    assert resolve_client_ip("10.0.0.9", "1.1.1.1, 2.2.2.2", 0) == "10.0.0.9"
    assert resolve_client_ip("10.0.0.9", None, 0) == "10.0.0.9"


def test_resolve_takes_the_proxy_attested_client_behind_one_hop():
    # One trusted proxy appends the real client's IP last. Forged entries the
    # client prepends on the left never change that last value.
    assert resolve_client_ip("proxy", "real", 1) == "real"
    assert resolve_client_ip("proxy", "spoof, real", 1) == "real"
    assert resolve_client_ip("proxy", "s1, s2, s3, real", 1) == "real"


def test_resolve_counts_hops_from_the_end():
    # Two trusted proxies: the client is two from the end.
    assert resolve_client_ip("proxy", "client, edge", 2) == "client"
    # Header shorter than the trusted hop count: fall back to the leftmost
    # present entry (never a value the request chose more freely).
    assert resolve_client_ip("proxy", "only", 2) == "only"


def test_resolve_falls_back_to_peer_and_unknown():
    assert resolve_client_ip("10.0.0.9", "", 1) == "10.0.0.9"
    assert resolve_client_ip("10.0.0.9", "   ", 1) == "10.0.0.9"
    assert resolve_client_ip(None, None, 0) == "unknown"


def test_spoofed_forwarded_for_cannot_evade_the_limit_behind_a_proxy():
    # burst=1: one request per client. Behind one trusted proxy, an attacker
    # rotates the LEFTMOST (forged) X-Forwarded-For entry every request but
    # the proxy always appends their true IP last — so every request keys to
    # the same bucket and the second is throttled.
    client = _app(RateLimiter(per_minute=60, burst=1), trusted_proxies=1)
    first = client.get("/api/v1/ping", headers={"X-Forwarded-For": "9.9.9.9, 203.0.113.7"})
    second = client.get("/api/v1/ping", headers={"X-Forwarded-For": "8.8.8.8, 203.0.113.7"})
    third = client.get("/api/v1/ping", headers={"X-Forwarded-For": "7.7.7.7, 203.0.113.7"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert third.status_code == 429


def test_distinct_real_clients_still_get_independent_buckets():
    # The flip side: two genuinely different clients (different last entry)
    # are limited independently, so the fix does not collapse everyone into
    # one bucket.
    client = _app(RateLimiter(per_minute=60, burst=1), trusted_proxies=1)
    a = client.get("/api/v1/ping", headers={"X-Forwarded-For": "203.0.113.7"})
    b = client.get("/api/v1/ping", headers={"X-Forwarded-For": "198.51.100.4"})
    assert a.status_code == 200
    assert b.status_code == 200


def test_direct_client_cannot_forge_bucket_when_untrusted():
    # trusted_proxies=0 (local/direct): the TestClient's socket peer is fixed,
    # so sending different X-Forwarded-For values cannot win a fresh bucket.
    client = _app(RateLimiter(per_minute=60, burst=1), trusted_proxies=0)
    first = client.get("/api/v1/ping", headers={"X-Forwarded-For": "1.1.1.1"})
    second = client.get("/api/v1/ping", headers={"X-Forwarded-For": "2.2.2.2"})
    assert first.status_code == 200
    assert second.status_code == 429
