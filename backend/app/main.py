import uuid

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.accounts.router import router as accounts_router
from app.analytics.router import router as analytics_router
from app.catalog.query import UnknownFilterValue
from app.catalog.router import router as catalog_router
from app.catalog.search import InvalidCursor
from app.core.config import get_settings
from app.core.errors import problem_response, register_error_handlers
from app.core.logging import configure_logging
from app.core.ratelimit import RateLimiter, add_rate_limit_middleware
from app.profile.router import router as profile_router
from app.profile.saved_router import router as saved_jobs_router


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="Xcelsior API", version="0.1.0")

    add_rate_limit_middleware(
        app,
        RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst),
        trusted_proxies=settings.trusted_proxy_count,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_error_handlers(app)

    @app.exception_handler(UnknownFilterValue)
    async def unknown_filter_handler(request: Request, exc: UnknownFilterValue) -> Response:
        return problem_response(
            422, "Unknown filter value", str(exc), field=exc.field, value=exc.value
        )

    @app.exception_handler(InvalidCursor)
    async def invalid_cursor_handler(request: Request, exc: InvalidCursor) -> Response:
        return problem_response(422, "Invalid cursor", str(exc))

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(catalog_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(accounts_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(saved_jobs_router, prefix="/api/v1")

    return app


app = create_app()
