import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    **extra: object,
) -> JSONResponse:
    """RFC 9457 problem-details response body."""
    body: dict[str, object] = {"status": status, "title": title}
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(
        status_code=status, content=body, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Forward any headers the raiser set (e.g. WWW-Authenticate on a 401).
        return problem_response(exc.status_code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic model_validator failures carry the raw exception in
        # ctx; stringify so the problem body is always serializable.
        errors = [
            {**e, "ctx": {k: str(v) for k, v in e["ctx"].items()}} if "ctx" in e else e
            for e in exc.errors()
        ]
        return problem_response(422, "Validation error", errors=errors)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return problem_response(500, "Internal server error")
