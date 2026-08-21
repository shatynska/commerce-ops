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

# Migrations run to completion before uvicorn starts; a failed migration
# fails the container's startup rather than serving traffic against a
# stale/partial schema (add-products-store's deploy-pipeline delta).
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn commerce_ops.main:app --host 0.0.0.0 --port 8000"]
