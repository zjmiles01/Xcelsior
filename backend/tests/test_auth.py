"""Account auth: signup, login, logout, sessions, and the protected surface (M10).

Xcelsior moved from a single shared bearer token (M8) to per-user accounts
with server-side sessions carried in an HTTP-only cookie. These tests pin the
full auth contract: successful signup/login, duplicate-email and
invalid-credential handling, session persistence and revocation, the
protected-route gate, and the case-insensitive email identity. Cross-user
isolation lives in test_authorization.py; the pure primitives (Argon2 hashing,
token hashing) in test_accounts.py.
"""

from app.core.config import get_settings

COOKIE = get_settings().session_cookie_name

GOOD = {"email": "sam@example.com", "password": "correct horse battery"}


# ── Signup ───────────────────────────────────────────────────────────────


def test_signup_creates_account_and_logs_in(unauth_client):
    resp = unauth_client.post("/api/v1/auth/signup", json=GOOD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "sam@example.com"
    assert "id" in body
    # The response never leaks the password or a raw token.
    assert "password" not in body and "token" not in body
    # Signup logs the user in: a session cookie is set, and /me now works.
    assert COOKIE in resp.cookies
    assert unauth_client.get("/api/v1/auth/me").status_code == 200


def test_signup_normalizes_email_case(unauth_client):
    unauth_client.post(
        "/api/v1/auth/signup", json={"email": "Mixed@Case.COM", "password": "a-long-password"}
    )
    me = unauth_client.get("/api/v1/auth/me").json()
    assert me["email"] == "mixed@case.com"


def test_duplicate_email_is_rejected(unauth_client):
    assert unauth_client.post("/api/v1/auth/signup", json=GOOD).status_code == 201
    # Same email, different case, still a conflict — identity is normalized.
    dup = unauth_client.post(
        "/api/v1/auth/signup", json={"email": "SAM@example.com", "password": "another-password"}
    )
    assert dup.status_code == 409


def test_signup_rejects_short_password(unauth_client):
    resp = unauth_client.post(
        "/api/v1/auth/signup", json={"email": "x@y.com", "password": "short"}
    )
    assert resp.status_code == 422


def test_signup_rejects_malformed_email(unauth_client):
    resp = unauth_client.post(
        "/api/v1/auth/signup", json={"email": "not-an-email", "password": "a-long-password"}
    )
    assert resp.status_code == 422


# ── Login ────────────────────────────────────────────────────────────────


def test_login_with_valid_credentials(unauth_client):
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    unauth_client.post("/api/v1/auth/logout")
    resp = unauth_client.post("/api/v1/auth/login", json=GOOD)
    assert resp.status_code == 200
    assert resp.json()["email"] == "sam@example.com"
    assert unauth_client.get("/api/v1/auth/me").status_code == 200


def test_login_is_case_insensitive_on_email(unauth_client):
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    unauth_client.post("/api/v1/auth/logout")
    resp = unauth_client.post(
        "/api/v1/auth/login", json={"email": "SAM@EXAMPLE.COM", "password": GOOD["password"]}
    )
    assert resp.status_code == 200


def test_login_wrong_password_is_401(unauth_client):
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    unauth_client.post("/api/v1/auth/logout")
    resp = unauth_client.post(
        "/api/v1/auth/login", json={"email": GOOD["email"], "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_email_is_401(unauth_client):
    resp = unauth_client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-longpw"}
    )
    # Same 401 as a wrong password — no account-enumeration signal.
    assert resp.status_code == 401


# ── Sessions: persistence and logout ─────────────────────────────────────


def test_session_persists_across_requests(unauth_client):
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    # The cookie the client now holds keeps working on subsequent requests.
    assert unauth_client.get("/api/v1/auth/me").status_code == 200
    assert unauth_client.get("/api/v1/auth/me").status_code == 200


def test_logout_revokes_the_session(unauth_client):
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    assert unauth_client.get("/api/v1/auth/me").status_code == 200
    resp = unauth_client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    # The cookie is cleared and the session is gone server-side.
    assert unauth_client.get("/api/v1/auth/me").status_code == 401


def test_logout_is_idempotent_without_a_session(unauth_client):
    assert unauth_client.post("/api/v1/auth/logout").status_code == 204


def test_stale_token_after_logout_is_rejected(db, unauth_client):
    """A token captured before logout must not keep working afterwards — the
    session is deleted server-side, not merely dropped from the browser."""
    unauth_client.post("/api/v1/auth/signup", json=GOOD)
    token = unauth_client.cookies.get(COOKIE)
    unauth_client.post("/api/v1/auth/logout")
    # Re-present the old token explicitly.
    unauth_client.cookies.set(COOKIE, token)
    assert unauth_client.get("/api/v1/auth/me").status_code == 401


# ── The protected surface ────────────────────────────────────────────────


def test_me_requires_authentication(unauth_client):
    assert unauth_client.get("/api/v1/auth/me").status_code == 401


def test_protected_routes_require_a_session(unauth_client):
    for method, path in [
        ("get", "/api/v1/profiles"),
        ("post", "/api/v1/resumes"),
        ("get", "/api/v1/saved-jobs"),
        ("get", "/api/v1/saved-jobs/ids"),
        ("post", "/api/v1/saved-jobs"),
    ]:
        resp = getattr(unauth_client, method)(path)
        assert resp.status_code == 401, f"{method} {path} -> {resp.status_code}"


def test_public_market_routes_need_no_session(unauth_client):
    assert unauth_client.get("/health").status_code == 200
    assert unauth_client.get("/api/v1/meta").status_code == 200


def test_authenticated_client_reaches_protected_routes(client):
    resp = client.get("/api/v1/profiles")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── Session cookie hardening ─────────────────────────────────────────────
#
# The session cookie is the only thing standing between a browser and an
# account, so its flags are a security contract, not an implementation
# detail. These drive the real endpoints and read the actual Set-Cookie
# header — they would catch a regression that flipping a constant would not.


def _session_set_cookie(resp) -> str:
    """The raw Set-Cookie header for the session cookie on a response."""
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(f"{COOKIE}="):
            return header
    raise AssertionError(f"no Set-Cookie for {COOKIE}: {resp.headers.get_list('set-cookie')}")


def test_signup_sets_hardened_cookie_in_development(make_client):
    client = make_client("development")
    resp = client.post("/api/v1/auth/signup", json=GOOD)
    assert resp.status_code == 201, resp.text
    cookie = _session_set_cookie(resp).lower()
    assert "httponly" in cookie  # unreadable by JavaScript
    assert "samesite=lax" in cookie  # blocks cross-site POST CSRF, allows nav
    assert "path=/" in cookie  # scoped to the whole app
    # Development serves plain HTTP; a Secure cookie would never be sent back.
    assert "secure" not in cookie


def test_login_sets_hardened_cookie(make_client):
    client = make_client("development")
    client.post("/api/v1/auth/signup", json=GOOD)
    client.post("/api/v1/auth/logout")
    resp = client.post("/api/v1/auth/login", json=GOOD)
    assert resp.status_code == 200
    cookie = _session_set_cookie(resp).lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_production_config_adds_secure_flag(make_client):
    client = make_client("production")
    resp = client.post("/api/v1/auth/signup", json=GOOD)
    assert resp.status_code == 201, resp.text
    cookie = _session_set_cookie(resp).lower()
    # In production the cookie is TLS-only, on top of the same hardening.
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


def test_logout_clears_cookie_with_matching_attributes(make_client):
    client = make_client("development")
    client.post("/api/v1/auth/signup", json=GOOD)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    cookie = _session_set_cookie(resp).lower()
    # Expired immediately (Max-Age=0), but with the same Path/SameSite/HttpOnly
    # so the browser matches and removes the exact cookie that was set.
    assert "max-age=0" in cookie or "expires=" in cookie
    assert "path=/" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
