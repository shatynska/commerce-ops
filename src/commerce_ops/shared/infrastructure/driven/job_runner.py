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
from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

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

    Parsed into components and reassembled, NOT rewritten as a string. An
    earlier version merely swapped the `postgresql+asyncpg://` prefix for
    `postgresql://` and handed the rest to psycopg. That is wrong whenever the
    password contains a character with meaning in a URI: libpq's own URI
    parser reads `postgresql://user:pa/ss@host:5432/db` as host `user`, port
    `pa`, and fails with "Servname not supported for ai_socktype" -- observed
    in production, where the worker could not reach the queue at all.
    SQLAlchemy tolerates the same string because it parses the URL itself,
    which is why `app` was unaffected and only the queue broke.

    `make_url` does the parsing (the same parser that accepts this URL for the
    application's own engine) and `make_conninfo` does the quoting, so no
    escaping rule is reimplemented here.

    One case this cannot repair: a literal `@` in the password. The URL is
    then ambiguous and `make_url` splits at the first one, so the application's
    own engine reads the same wrong host and fails too -- it is a constraint on
    how `docker-compose.yml` builds the URL (percent-encode it), not something
    this function can decide. It is named here so the next reader does not
    mistake it for the defect above, which was this function's alone.
    """
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError(
            "DATABASE_URL is not set (or is set but empty); the job runner "
            "cannot reach the queue without it"
        )
    url = make_url(value)
    return make_conninfo(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )


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
