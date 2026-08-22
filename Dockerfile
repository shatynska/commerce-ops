FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./
COPY alembic.ini ./
COPY alembic/ ./alembic/

RUN uv sync --frozen --no-dev

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Two gates run to completion before uvicorn starts, in this order:
#
# 1. The runtime configuration is checked, and every faulting variable is
#    named on stderr. Only a startup-critical fault (DATABASE_URL) exits
#    non-zero and stops the chain here -- a fault scoped to one capability
#    is reported and startup continues, so a missing channel id degrades
#    that capability rather than the whole deployment
#    (revise-foundation-for-launch-mvp's deploy-pipeline delta).
# 2. Migrations run; a failed migration fails the container's startup
#    rather than serving traffic against a stale/partial schema
#    (add-products-store's deploy-pipeline delta).
#
# The configuration check goes first: there is no point migrating a
# database whose connection string is the thing that is missing.
CMD ["sh", "-c", "uv run python -m commerce_ops.preflight && uv run alembic upgrade head && uv run uvicorn commerce_ops.main:app --host 0.0.0.0 --port 8000"]
