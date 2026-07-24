import logging

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Structured JSON logs in production, readable console logs in development."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: structlog.typing.Processor
    if settings.environment == "development":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=level, format="%(message)s")
