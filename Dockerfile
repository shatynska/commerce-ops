FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ ./src/
COPY README.md ./
COPY alembic.ini ./
COPY alembic/ ./alembic/

RUN uv sync --frozen --no-dev

# Declared AFTER the build's own `uv sync`, so a variable meant for the
# runtime is never in scope for the step that produces the environment.
#
# Without it, every `uv run` below re-syncs before running anything, and uv's
# default group set includes `dev` -- so the runtime undoes the `--no-dev`
# above and downloads pytest, mypy, ruff and their trees into a running
# production container. That is not merely slow: it makes a container start
# depend on a reachable package index, and a container with no route to one
# cannot start at all. One variable rather than flags on each `uv run`,
# because the call sites include commands an operator types into
# `docker compose exec`, which no edit to this repository can reach.
ENV UV_NO_SYNC=1

# Calls the venv's interpreter directly rather than `uv run`, unlike the CMD
# chain below. The reasoning inverts for this one call site: it is a fixed
# string with no operator-typed variant to miss, and it runs every 10 seconds
# for the life of every `app` container, so launching uv to discover a venv it
# will not modify is pure overhead on the most frequent command in the
# deployment. It also keeps uv out of the liveness signal -- each layer between
# the probe and the HTTP request is another way to report the wrong thing.
# (`worker` overrides this to `disable: true`, having no HTTP surface.)
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

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
#
# `exec` before the final command is required, not stylistic: without it
# `sh` stays PID 1 (verified directly -- an `&&` chain is not exec-
# optimized), SIGTERM never reaches uvicorn, and `main.py`'s lifespan --
# which disposes the database engine on shutdown -- never runs
# (centralize-database-session's design.md, "The container's start command
# must `exec` the server"). `docker-compose.yml`'s `cron` service uses the
# same `exec crond -f -l 2` pattern.
CMD ["sh", "-c", "uv run python -m commerce_ops.preflight && uv run alembic upgrade head && uv run python -m commerce_ops.seed_admin && uv run python -m commerce_ops.check_step_handlers && exec uv run uvicorn commerce_ops.main:app --host 0.0.0.0 --port 8000"]
