"""Driven adapter: the Postgres-backed job runner this process shares.

Implements the `scheduled-jobs` capability
(`openspec/changes/replace-cron-with-job-runner/specs/scheduled-jobs/spec.md`).

Owns the runner's application object -- the queue itself, infrastructure the
whole process shares. Job *definitions* do not live here: a scheduled job is a
driving adapter and belongs to the module whose work it runs, so the daily
digest's definition is in `products/infrastructure/driving/`. See design.md,
"The daily job definition lives in `products`, not in `shared`".
"""

from __future__ import annotations

import os
from typing import Any

import procrastinate
import psycopg_pool

_ASYNC_DRIVER_PREFIX = "postgresql+asyncpg://"
_PSYCOPG_PREFIX = "postgresql://"

# The runner's schedules are evaluated in UTC and cannot be evaluated in
# anything else -- `PeriodicTask` builds its croniter with no timezone
# parameter and the deferrer works from absolute instants. This is the
# schedule's timezone; a container's `TZ` is for log timestamps only.
# See design.md, "The schedule is interpreted in UTC".
#
# `max_delay` is infinite deliberately. Its default is 600 seconds, and a due
# moment older than that is *dropped* -- which is the silent skip this whole
# change exists to remove. A large finite value would only move the threshold
# rather than remove it. See design.md, "A missed window runs once".
PERIODIC_DEFAULTS: dict[str, Any] = {"max_delay": float("inf")}


def queue_conninfo() -> str:
    """The queue's psycopg-style connection string, from `DATABASE_URL`.

    Derived rather than delivered as a second secret: the deploy renders one
    URL and `docker-compose.yml` builds it from `POSTGRES_PASSWORD`, so a
    second variable would be a second thing to keep in step (tasks.md 1.2).

    The application connects with `asyncpg` and declares its URL accordingly;
    psycopg does not understand the `+asyncpg` driver marker, so it is
    stripped here. Nothing else about the URL changes -- same host, same
    database, same credentials.
    """
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError(
            "DATABASE_URL is not set (or is set but empty); the job runner "
            "cannot reach the queue without it"
        )
    if value.startswith(_ASYNC_DRIVER_PREFIX):
        return _PSYCOPG_PREFIX + value[len(_ASYNC_DRIVER_PREFIX) :]
    return value


def _queue_pool(**kwargs: Any) -> psycopg_pool.AsyncConnectionPool:
    # Called when the connector opens, never at import. This is what keeps
    # `DATABASE_URL` out of the import path: `import commerce_ops.worker` (or
    # any module holding a job definition) must not require configuration,
    # consistent with `runtime-configuration`'s import/start requirement.
    return psycopg_pool.AsyncConnectionPool(conninfo=queue_conninfo(), **kwargs)


app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(pool_factory=_queue_pool),
    periodic_defaults=PERIODIC_DEFAULTS,
)
