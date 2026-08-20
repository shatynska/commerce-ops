FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./

RUN uv sync --frozen --no-dev

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD uv run python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "commerce_ops.main:app", "--host", "0.0.0.0", "--port", "8000"]
