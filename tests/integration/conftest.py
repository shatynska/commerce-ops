"""How the integration tier reaches its database — the one place that
decides it.

Twelve files used to carry the same `_database_url()` helper, each
skipping when `DATABASE_URL` was unset. The rule lived in twelve copies
and was owned by none, and it produced a false green: `pre-push` runs
this tier, set no variable, and reported `3 passed, 64 skipped` as a
pass. See `openspec/changes/verify-the-integration-tier/`.

Two fixtures, because there are two jobs and one test must not be gated:

- `_publish_database_url` (autouse) puts a resolved URL into the process
  environment. Four files drive the real application, whose session
  provider reads `os.environ["DATABASE_URL"]` directly rather than
  taking it from a fixture, so without this the file rungs below would
  make them fail instead of run.
- `database_url` gates. Requesting it is how a test says it needs a
  configured database — so `test_scheduled_runs_freshness_unreachable.py`,
  which supplies its own unreachable address and documents that it never
  skips, requests neither and is untouched.

Reporting goes through `pytest_report_header`, not `print`: a session
fixture's stdout is captured and surfaces only beside a failing test,
which is exactly the wrong place on the run that matters most — a bare
machine, where everything skips and nothing fails.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.shared.infrastructure.driven.database import dispose_engine

#: Set by CI. Where it is set, no database is a failure rather than a
#: skip, so a validation job cannot report success for a tier it never
#: ran. Deliberately not set by the `pre-push` hook — see the change's
#: `design.md`, "A required-tier flag turns a skip into a failure — in
#: CI only".
REQUIRE_DATABASE: Final = "COMMERCE_OPS_REQUIRE_DATABASE"

_KEY: Final = "DATABASE_URL"
_REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: Searched in order. An explicit environment variable wins; `.env.test`
#: is a standing choice to keep the tier out of the database the
#: developer works in; `.env` is what every working machine already has.
_ENV_FILES: Final = (".env.test", ".env")

_START_HINT: Final = (
    "Start it with `docker compose up -d postgres` and apply "
    "`alembic upgrade head` (schema and seed) before running this tier."
)


def _from_env_file(path: Path) -> str | None:
    """The `DATABASE_URL` line of an env file, and nothing else.

    Only this key is read. The same files carry the OpenAI key, both
    Slack tokens and the ClickUp token, and the suite is hermetic with
    respect to credentials — every test that needs one sets its own. A
    whole-file load would let a test that forgot to set one inherit an
    ambient value and pass, which is the same defect this module exists
    to remove, one layer down.
    """
    if not path.is_file():
        return None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() != _KEY:
            continue
        value = value.strip()
        if value[:1] in {"'", '"'} and value[-1:] == value[:1] and len(value) > 1:
            return value[1:-1] or None
        # An unquoted value ends at an inline comment; a quoted one does
        # not, which is why this runs only on the unquoted branch.
        return value.split(" #")[0].strip() or None
    return None


def _resolve() -> tuple[str, str] | None:
    """`(url, where it came from)`, or `None` when nothing is configured.

    Empty is absent throughout, matching `database.py`'s own reading and
    all twelve helpers this replaces.
    """
    from_environment = os.environ.get(_KEY)
    if from_environment:
        return from_environment, f"the {_KEY} environment variable"
    for name in _ENV_FILES:
        found = _from_env_file(_REPO_ROOT / name)
        if found:
            return found, name
    return None


def _redacted(url: str) -> str:
    """The URL with its password removed. Everything else is kept — the
    username included, since it tells two databases apart and the point
    of a stated rule is that nothing is left to decide at the keyboard."""
    scheme, separator, rest = url.partition("://")
    if not separator or "@" not in rest:
        return url
    credentials, _, location = rest.rpartition("@")
    user, has_password, _ = credentials.partition(":")
    if not has_password:
        return url
    return f"{scheme}://{user}:***@{location}"


def pytest_report_header() -> str:
    """Printed above the run, uncaptured and unconditionally.

    Both states are reported. The resolved one names the rung, so a
    stale `.env.test` pointing at a reachable but unmigrated database is
    diagnosable — the case with no connection error to hang a diagnosis
    on. The unresolved one says the tier will skip, because that is
    where a test needing a database that did not request `database_url`
    hard-errors from the application's own reader, and nothing else
    would explain it.
    """
    resolved = _resolve()
    if resolved is None:
        return (
            f"integration tier: no database configured — no {_KEY}, "
            f"no {' or '.join(_ENV_FILES)}. Tests needing one will skip. "
            f"{_START_HINT}"
        )
    url, source = resolved
    return f"integration tier: database from {source} — {_redacted(url)}"


def pytest_runtest_teardown() -> None:
    """Disposes the application's own global engine singleton after every
    test — a plain `pytest` hook, not a fixture.

    `database.py`'s `_get_engine_and_session_factory()` is process-wide and
    `functools.lru_cache`d: once a test calls the real, unpatched
    `session()`/`transaction()` (several "live" files in this tier
    deliberately do, to exercise the real thing), it lazily builds one
    `AsyncEngine` and keeps it — and its connection pool — for the rest of
    the `pytest` process, across every test function that follows.

    That collides with `anyio`'s default per-function event loop: a pooled
    `asyncpg` connection is bound to the loop it was created on, and
    handing it back out to a *later* test running on a *different* (new)
    loop fails opaquely — `InterfaceError: cannot perform operation:
    another operation is in progress` or `RuntimeError: Event loop is
    closed`, depending on where in the connection's lifecycle the mismatch
    is hit. See `docs/deferred-work.md`, "The application's global engine
    singleton outlives pytest's per-test event loop".

    **A hook, not an `autouse` fixture, and that distinction is
    load-bearing.** An async `autouse` fixture calling `dispose_engine()`
    was tried first and reverted: it produced `pytest`-internal
    `AssertionError: assert not self._finalizers` across a large slice of
    the suite, an async-fixture/`anyio`-plugin interaction this project's
    exact `pytest`+`anyio` combination does not accept the way
    `pytest-asyncio` would. `pytest_runtest_teardown` sidesteps that
    entirely: it is a plain, synchronous hook `pytest` calls once per test
    *after* that test's own async fixtures and their teardowns — and
    `anyio`'s per-test event loop with them — have already finished. No
    event loop is running here, so a fresh, private one via `asyncio.run`
    is exactly what disposal needs, and nothing about `pytest`'s fixture
    dependency graph is involved.

    A test that never touches the real engine (nearly all of them patch
    `session`/`transaction` away) pays nothing extra: `dispose_engine()`
    is a no-op when nothing was built.
    """
    asyncio.run(dispose_engine())


@pytest.fixture(scope="session", autouse=True)
def _publish_database_url() -> object:
    """Publish a resolved URL into the environment for the whole session.

    Session-scoped `MonkeyPatch` rather than a bare assignment, so it
    unwinds afterwards and a per-test `setenv` still overrides it —
    which `test_scheduled_runs_freshness_unreachable.py` relies on.

    Publishes nothing when nothing resolves, and never raises: gating is
    the other fixture's job, and this one runs for every test including
    the ones that must not be gated.
    """
    patch = pytest.MonkeyPatch()
    resolved = _resolve()
    if resolved is not None:
        patch.setenv(_KEY, resolved[0])
    yield patch
    patch.undo()


@pytest.fixture(scope="session")
def database_url() -> str:
    """The tier's database, for a test that needs one configured.

    Requesting this fixture is how a test opts into being gated. Where
    nothing resolves it skips — or fails, if `COMMERCE_OPS_REQUIRE_DATABASE`
    says the tier is required here, so that a gate cannot report success
    for work it never exercised.
    """
    resolved = _resolve()
    if resolved is not None:
        return resolved[0]
    unconfigured = (
        f"No database is configured for the integration tier: {_KEY} is "
        f"unset (or empty) and neither {' nor '.join(_ENV_FILES)} carries "
        f"it. {_START_HINT}"
    )
    if os.environ.get(REQUIRE_DATABASE):
        pytest.fail(
            f"{unconfigured} {REQUIRE_DATABASE} is set, so this "
            "tier is required here and may not be skipped."
        )
    pytest.skip(unconfigured)


@pytest.fixture(scope="session", autouse=True)
def _no_worker_against_production_schedules() -> object:
    """Fail any test that starts a worker against production schedules.

    Test infrastructure, not a subject of any requirement.

    Four modules in this tier call `registrations.register_all()` at import,
    and pytest imports every selected module at collection -- so the shared
    `job_runner.app` carries this application's real recurring work before
    the first test runs. A worker started against it defers and *executes*
    that work: the developer's database has held `briefing.daily`,
    `launch.clickup.completion_pass` and `shared.scheduled_runs.overdue_check`
    rows written by pytest rather than by a worker. Its shutdown also hangs
    forever at a measurable rate, because procrastinate cancels each side
    task once and then gathers with no deadline while psycopg_pool treats
    `CancelledError` as a retryable client exception.

    The two runner files own private `App`s so this cannot happen to them.
    This guard is what makes the rule hold for tests nobody has written yet,
    since it asks nothing of a future author.

    **The condition is the registry of the App the worker is starting on**,
    not the shared one. Reading the fixed `job_runner.app` would fire on the
    private Apps too -- the shared registry is armed at collection whenever
    an arming sibling is in the run -- and so would fail the very tests the
    private Apps exist to fix.

    Patched from this fixture's body, never at import: this module is loaded
    and executed by `tests/unit/test_integration_tier_database_resolution.py`
    inside the commit-time tier, where patching `procrastinate` would be
    reaching into `tests/unit`.

    What it does not cover, deliberately: a directly constructed
    `procrastinate.worker.Worker`, a `PeriodicDeferrer` driven over a
    standalone registry, and a bare `defer_async()` on a production task.
    Each is a deliberate act rather than something a test falls into.
    """
    import procrastinate

    original = procrastinate.App.run_worker_async

    async def guarded(self: procrastinate.App, *args: Any, **kwargs: Any) -> Any:
        scheduled = sorted(self.periodic_registry.periodic_tasks)
        if scheduled:
            pytest.fail(
                "this test started a worker against an application carrying "
                f"periodic work: {scheduled}. The worker would defer and run "
                "it -- production jobs, if this is the shared application -- "
                "and its shutdown can hang forever. Give the test its own "
                "`procrastinate.App`, as tests/integration/shared/"
                "test_scheduled_run_history.py does."
            )
        return await original(self, *args, **kwargs)

    patch = pytest.MonkeyPatch()
    patch.setattr(procrastinate.App, "run_worker_async", guarded)
    yield patch
    patch.undo()
