from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XCELSIOR_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://xcelsior:xcelsior@localhost:5432/xcelsior"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Session-based authentication (M10). Users sign up with email/password;
    # the server issues an opaque session token stored (hashed) server-side
    # and set as an HTTP-only cookie. No token is ever exposed to JavaScript
    # or persisted in localStorage. Cookies are Secure in production and
    # SameSite=Lax (the SPA is same-origin with the API, so Lax lets normal
    # navigation carry the session while blocking cross-site POSTs).
    session_cookie_name: str = "xcelsior_session"
    session_ttl_days: int = 14

    # In-process rate limit: requests per minute per client IP across the
    # API. 0 disables the limiter (tests, trusted local dev).
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 40

    # Number of reverse proxies we trust in front of the app, used only to
    # derive the rate-limit client IP (M10 hardening). 0 (default) trusts
    # none: the limiter keys off the socket peer and ignores X-Forwarded-For,
    # so a directly-connected client cannot spoof its identity. Behind a
    # proxy, set this to the number of hops we control; the limiter then reads
    # the IP the outermost trusted proxy attests (the Nth-from-last XFF
    # entry), which a client cannot forge by prepending entries. Render routes
    # through a single proxy hop, so production sets this to 1.
    trusted_proxy_count: int = 0

    @property
    def cookie_secure(self) -> bool:
        """Session cookie carries the Secure flag outside development, so it
        is never sent over plain HTTP once deployed behind TLS."""
        return self.environment != "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
