"""Database fixtures for integration tests.

Tests run against a dedicated `xcelsior_test` database (created on demand,
migrated by Alembic — the same migrations production runs). Each test gets
a session inside an outer transaction that is rolled back afterwards;
`join_transaction_mode="create_savepoint"` turns service-layer commit()
calls into savepoint releases, so code under test commits normally while
the test leaves no trace.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Set before any app import so the lru_cached Settings picks them up: a
# disabled rate limiter so the suite's many requests never trip it (rate
# limiting is tested on its own with an explicit low limit). Auth is now
# per-user session cookies (M10), minted by the `client` fixture below —
# there is no shared token to configure.
os.environ["XCELSIOR_RATE_LIMIT_PER_MINUTE"] = "0"

from app.core.config import get_settings  # noqa: E402

TEST_DB_NAME = "xcelsior_test"


def _test_db_url() -> str:
    override = os.environ.get("XCELSIOR_TEST_DATABASE_URL")
    if override:
        return override
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + "/" + TEST_DB_NAME


@pytest.fixture(scope="session")
def test_engine():
    from alembic.config import Config

    import app.models  # noqa: F401  (complete metadata before migrations)
    from alembic import command

    url = _test_db_url()
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB_NAME}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def _bind_client(db):
    """A TestClient whose get_db is overridden to the savepoint-isolated
    session, so endpoint tests see fixture data and leave no trace."""
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


@pytest.fixture
def user(db):
    """A default account the authenticated `client` acts as. Personal-data
    fixtures (profiles, resumes, saved jobs) attach ownership to this id."""
    from app.accounts.service import create_user

    return create_user(db, "primary@example.com", "primary-password")


@pytest.fixture
def other_user(db):
    """A second, independent account — for cross-user authorization tests
    (one user must never reach another's data)."""
    from app.accounts.service import create_user

    return create_user(db, "other@example.com", "other-password")


def _login_cookie(db, user):
    from app.accounts.service import create_session

    return create_session(db, user, get_settings().session_ttl_days)


@pytest.fixture
def client(db, user):
    """API test client authenticated as `user` via a real session cookie —
    the same mechanism a browser uses. Public routes work regardless; the
    personal-data routes see `user` as the owner. Auth negatives and
    public-access checks use `unauth_client`."""
    tc = _bind_client(db)
    tc.cookies.set(get_settings().session_cookie_name, _login_cookie(db, user))
    try:
        yield tc
    finally:
        from app.main import app

        app.dependency_overrides.clear()


@pytest.fixture
def other_client(db, other_user):
    """A client authenticated as `other_user`, for cross-user tests."""
    tc = _bind_client(db)
    tc.cookies.set(get_settings().session_cookie_name, _login_cookie(db, other_user))
    try:
        yield tc
    finally:
        from app.main import app

        app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(db):
    """A client with no session — for exercising the auth gate (401 on
    protected routes) and confirming public routes stay open."""
    tc = _bind_client(db)
    try:
        yield tc
    finally:
        from app.main import app

        app.dependency_overrides.clear()


@pytest.fixture
def make_client(db):
    """Factory for an unauthenticated client whose runtime environment is
    chosen per call, by overriding `get_settings`. Used to assert the real
    Set-Cookie hardening the auth endpoints emit under development vs
    production config (the Secure flag is environment-driven)."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings, get_settings
    from app.core.db import get_db
    from app.main import app

    def _make(environment: str = "development") -> TestClient:
        def _db_override():
            yield db

        app.dependency_overrides[get_db] = _db_override
        app.dependency_overrides[get_settings] = lambda: Settings(environment=environment)
        return TestClient(app)

    try:
        yield _make
    finally:
        from app.main import app as _app

        _app.dependency_overrides.clear()
