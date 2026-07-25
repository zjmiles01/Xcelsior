# Single image for all runtime roles (API, ingestion, extraction).
# The role is chosen by the command: uvicorn for the API, `xcelsior ...`
# CLI entrypoints for pipeline work.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Dependency layer first so code changes don't bust the dependency cache.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY data ./data

RUN uv sync --frozen --no-dev

ENV PATH="/srv/.venv/bin:$PATH" \
    XCELSIOR_ENVIRONMENT=production

EXPOSE 8000
# No uvicorn --proxy-headers / --forwarded-allow-ips: those would rewrite
# request.client.host from the LEFTMOST X-Forwarded-For entry, which a client
# can forge — letting an attacker rotate spoofed IPs to evade the per-IP rate
# limiter (ADR-006). Instead the app derives the rate-limit client IP itself
# from X-Forwarded-For using XCELSIOR_TRUSTED_PROXY_COUNT (M10 hardening),
# reading the Nth-from-last entry the trusted proxy attests. request.client.host
# then stays the real socket peer (the platform proxy), a safe fallback.
# Deployment must set XCELSIOR_TRUSTED_PROXY_COUNT to its proxy-hop count
# (Render = 1); see infra/render.yaml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
