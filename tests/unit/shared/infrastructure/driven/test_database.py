"""Tests for the `database-session` capability's provider.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/centralize-database-session/specs/database-session/spec.md`:

- "One Connection Pool Per Process Serves Every Application Session" /
  Scenario: Repeated session requests share one pool
- "One Connection Pool Per Process Serves Every Application Session" /
  Scenario: Request-scoped and standalone callers share one pool
- "A Session Is Available Outside An HTTP Request" / Scenario: Work that is
  not an HTTP request obtains a session
- "A Session Is Available Outside An HTTP Request" / Scenario: A session is
  released after the caller's work completes
- "A Session Is Available Outside An HTTP Request" / Scenario: A session is
  released when the caller's work raises
- "A Process That Obtained A Session Closes Its Pool Before Exiting" /
  Scenario: Shutdown with no database use is not an error
- "The Connection Setting Is Read No Earlier Than The First Session
  Request" / Scenario: The connection setting is read only when a session
  is first requested
- "An Absent Or Malformed Connection Setting Is Reported At The Point Of
  Use" / Scenario: A session is requested with the setting absent
- "An Absent Or Malformed Connection Setting Is Reported At The Point Of
  Use" / Scenario: A session is requested with a setting the application
  cannot connect with

The remaining four scenarios in that delta spec are accounted for
elsewhere, not here:

- "Infrastructure holding its own connection or pool is not a second route
  to domain data" and "An exempt component reaching domain data is a
  violation" -- recorded UNCOVERED in test-manifest.md. No infrastructure
  component holding its own bookkeeping connection/pool exists in this
  codebase yet (design.md: the task-queue example this axis was drawn from
  arrives via the sibling `replace-cron-with-job-runner` change); there is
  no subject in the current tree to exercise either branch against, and
  fabricating one would be inventing a component this change does not add.
- "The HTTP process releases connections when it stops" and "Starting and
  stopping with the database unconfigured" -- covered in
  `tests/unit/test_main_database_lifespan.py`, since both need
  `commerce_ops.main.app`, not just this provider module in isolation.

See `test-manifest.md` at this change's root for the full
specified/derived/deliberately-untested accounting.

## Names and shapes used here are SPECIFIED, not invented

Unlike most first-pass test files in this repo, every name this file
depends on is fixed by an artifact, not guessed:

- Module `shared/infrastructure/driven/database.py` (proposal.md's Impact
  section).
- `session()` -- "an `@asynccontextmanager` yielding an `AsyncSession`,
  releasing it on both normal completion and exception, letting the
  exception propagate unchanged" (tasks.md 1.5).
- `get_session()` -- "the FastAPI dependency, a thin `AsyncIterator` over
  `session()`" (tasks.md 1.6), taking no arguments, mirroring the existing
  `get_session()` signature design.md's Context section transcribes from
  today's `monitoring.py`.
- `dispose_engine()` -- "awaits `engine.dispose()` if an engine was
  created, returns without error otherwise, and clears the factory cache in
  the same operation" (tasks.md 1.7).
- The required scheme, `postgresql+asyncpg`, named literally in design.md's
  "`DATABASE_URL` is read directly..." decision.

## The seams used to observe "released" and "disposed"

Neither "released" nor "disposed" has a public boolean flag on
`AsyncSession`/`AsyncEngine` to assert against directly. Tasks.md fixes the
mechanism instead: `dispose_engine()` "awaits `engine.dispose()`"
(tasks.md 1.7), and `session()` "releas[es]" the session on both paths
(tasks.md 1.5) -- the only established release idiom for a SQLAlchemy
`AsyncSession` is `.close()`, which is exactly what design.md's own
`async with session_factory() as session: yield session` excerpt already
relies on (`AsyncSession.__aexit__` calls `.close()`). This file therefore
monkeypatches `AsyncSession.close`/`AsyncEngine.dispose` themselves --
public SQLAlchemy API, not this project's own source -- to record which
instances were closed/disposed, then delegates to the original
implementation so behaviour is unchanged. This holds regardless of which
internal path the real implementation takes to call them.

## What "same pool" means here

`session.bind` is the `AsyncEngine` a session was built against (verified
directly against installed sqlalchemy: `async_sessionmaker(engine)()`
sessions have `.bind is engine`) -- comparing `.bind` identity across two
sessions is what "drawn from the same connection pool" is asserted as,
since the engine owns exactly one pool per `create_async_engine` call.

## What "an exception is raised" means for the two failure scenarios

Neither failure scenario's spec text names a specific exception type, so
every `pytest.raises` below is scoped to `Exception` broadly, narrowly
around the call under test, per `ai-toolkit:testing`'s `pytest.raises`-
scoping rule -- what the spec commits to is "a report naming the setting
[and scheme]", not any particular exception class.

## No real Postgres is used

`create_async_engine`/`async_sessionmaker`/entering-and-exiting an
`AsyncSession` do not open a real connection until a query is actually
issued (verified directly) -- confirmed by hand against this project's
pinned sqlalchemy/asyncpg. Every test that needs a "configured" URL uses an
syntactically-valid-but-unreachable one (`TEST_DATABASE_URL` below) and
never issues a query, keeping this file in the unit tier with no real I/O.

## At the time this pass was written, nothing under test exists

`shared/infrastructure/driven/` currently declares only `clickup_client.py`
(plus an empty `__init__.py`) -- no `database` module. Every test in this
file is expected to fail on that absence (`ModuleNotFoundError`) until
tasks.md section 1 lands. Per `ai-toolkit:testing`'s failure-state
taxonomy, that failure establishes only that the target is absent, nothing
about whether the assertions below are well-formed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from commerce_ops.shared.infrastructure.driven import database

pytestmark = pytest.mark.anyio

# Syntactically valid so the scheme validator and SQLAlchemy accept it, but
# never actually reachable -- no test in this file issues a query, so this
# is never dialled.
TEST_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:1/dummy"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio -- see tests/integration/products/conftest.py's own
    # anyio_backend fixture for the reasoning (no trio dependency installed,
    # nothing in this project's artifacts calls for trio support).
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixtures / test doubles
# ---------------------------------------------------------------------------


@pytest.fixture()
def configured_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)


@dataclass
class _CloseSpy:
    closed_ids: set[int] = field(default_factory=set)

    def was_closed(self, session: AsyncSession) -> bool:
        return id(session) in self.closed_ids


@pytest.fixture()
def track_session_close(monkeypatch: pytest.MonkeyPatch) -> _CloseSpy:
    """Records every `AsyncSession.close()` call, then delegates to the
    original -- see module docstring, "The seams used to observe 'released'
    and 'disposed'"."""
    spy = _CloseSpy()
    original_close = AsyncSession.close

    async def _spy_close(self: AsyncSession) -> None:
        spy.closed_ids.add(id(self))
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", _spy_close)
    return spy


@dataclass
class _DisposeSpy:
    disposed_ids: set[int] = field(default_factory=set)

    def was_disposed(self, engine: AsyncEngine) -> bool:
        return id(engine) in self.disposed_ids


@pytest.fixture()
def track_engine_dispose(monkeypatch: pytest.MonkeyPatch) -> _DisposeSpy:
    """Records every `AsyncEngine.dispose()` call, then delegates to the
    original -- see module docstring, "The seams used to observe 'released'
    and 'disposed'"."""
    spy = _DisposeSpy()
    original_dispose = AsyncEngine.dispose

    async def _spy_dispose(self: AsyncEngine, close: bool = True) -> None:
        spy.disposed_ids.add(id(self))
        await original_dispose(self, close)

    monkeypatch.setattr(AsyncEngine, "dispose", _spy_dispose)
    return spy


@pytest.fixture(autouse=True)
def _reset_provider_state() -> Iterator[None]:
    """Disposes whatever engine a test created, both before and after it
    runs, so state never leaks between tests. Relies only on the module's
    own public `dispose_engine()` -- tasks.md 1.7 says disposal "clears the
    factory cache in the same operation", so this is enough to guarantee
    the next test starts from "no engine created" without this file needing
    to know the provider's private cache's name.

    Deliberately a *sync* fixture running its own `asyncio.run(...)`, rather
    than an async fixture the anyio plugin would manage: this module mixes
    async scenario tests with plain sync subprocess-based ones (e.g.
    `test_importing_the_provider_does_not_require_database_url`), and an
    async autouse fixture breaks pytest's fixture machinery for the sync
    ones (verified directly: "assert not self._finalizers" in
    `_pytest/fixtures.py`, cascading into spurious errors on every test
    after the first sync one). Calling `dispose_engine()` from a fresh
    event loop here, separate from whichever loop a given test's own body
    runs under, is safe because no test in this file ever opens a real
    connection (see module docstring, "No real Postgres is used") --
    verified directly that disposing an engine from a different event loop
    than the one that created it raises nothing when no connection was
    ever opened.
    """
    asyncio.run(database.dispose_engine())
    yield
    asyncio.run(database.dispose_engine())


# ---------------------------------------------------------------------------
# Requirement: One Connection Pool Per Process Serves Every Application
# Session
# ---------------------------------------------------------------------------


async def test_repeated_session_requests_share_one_pool(
    configured_database_url: None,
) -> None:
    """Scenario: Repeated session requests share one pool.

    WHEN sessions are requested more than once in a process
    THEN every session SHALL be drawn from the same connection pool
    """
    async with database.session() as first:
        first_engine = first.bind

    async with database.session() as second:
        second_engine = second.bind

    # SPECIFIED.
    assert first_engine is second_engine


async def test_request_scoped_and_standalone_callers_share_one_pool(
    configured_database_url: None,
) -> None:
    """Scenario: Request-scoped and standalone callers share one pool.

    WHEN a session is requested while serving an HTTP request, and another
    is requested by a caller that is not serving an HTTP request
    THEN both SHALL be drawn from the same connection pool

    `get_session()` is driven directly as the async generator it is
    (tasks.md 1.6), standing in for "serving an HTTP request" without
    needing FastAPI's own dependency-injection machinery -- this module's
    subject is the provider, not the HTTP layer around it.
    """
    async with database.session() as standalone_session:
        standalone_engine = standalone_session.bind

    request_scoped_generator = database.get_session()
    request_scoped_session = await anext(request_scoped_generator)
    request_scoped_engine = request_scoped_session.bind
    with contextlib.suppress(StopAsyncIteration):
        await anext(request_scoped_generator)

    # SPECIFIED.
    assert standalone_engine is request_scoped_engine


# ---------------------------------------------------------------------------
# Requirement: A Session Is Available Outside An HTTP Request
# ---------------------------------------------------------------------------


async def test_standalone_caller_obtains_a_usable_session(
    configured_database_url: None,
) -> None:
    """Scenario: Work that is not an HTTP request obtains a session.

    WHEN a caller that is not serving an HTTP request requests a session
    THEN a usable session SHALL be provided

    This test function is not serving any HTTP request -- calling
    `database.session()` directly from a plain async test *is* "a caller
    that is not serving an HTTP request". "Usable" is read as: a real
    `AsyncSession`, bound to an engine.
    """
    async with database.session() as session:
        # SPECIFIED.
        assert isinstance(session, AsyncSession)
        assert session.bind is not None


async def test_session_released_after_the_callers_work_completes(
    configured_database_url: None,
    track_session_close: _CloseSpy,
) -> None:
    """Scenario: A session is released after the caller's work completes.

    WHEN a caller that obtained a session outside an HTTP request finishes
    its work
    THEN the session SHALL be released back to the pool
    """
    async with database.session() as session:
        obtained = session

    # SPECIFIED: released -- observed as AsyncSession.close() having been
    # called on the exact instance yielded (see module docstring).
    assert track_session_close.was_closed(obtained)


async def test_session_released_when_the_callers_work_raises(
    configured_database_url: None,
    track_session_close: _CloseSpy,
) -> None:
    """Scenario: A session is released when the caller's work raises.

    WHEN a caller that obtained a session outside an HTTP request raises an
    exception before finishing
    THEN the session SHALL be released back to the pool, AND the exception
    SHALL propagate to the caller unchanged
    """

    class _CallerRaised(Exception):
        pass

    obtained: AsyncSession | None = None

    with pytest.raises(_CallerRaised) as caught:
        async with database.session() as session:
            obtained = session
            raise _CallerRaised("caller's own work failed")

    # SPECIFIED: the exception propagates unchanged -- same type, same
    # message, not swallowed or wrapped.
    assert caught.value.args == ("caller's own work failed",)

    # SPECIFIED: released.
    assert obtained is not None
    assert track_session_close.was_closed(obtained)


# ---------------------------------------------------------------------------
# Requirement: A Process That Obtained A Session Closes Its Pool Before
# Exiting
# ---------------------------------------------------------------------------


async def test_dispose_with_no_session_ever_requested_does_not_raise() -> None:
    """Scenario: Shutdown with no database use is not an error.

    WHEN a process exits without any session having been requested
    THEN exiting SHALL succeed without raising

    `dispose_engine()` is this provider's own half of "exiting" (tasks.md
    1.7); the `_reset_provider_state` autouse fixture guarantees no session
    was requested by this test before this call runs.
    """
    # SPECIFIED: exiting succeeds without raising.
    await database.dispose_engine()


# ---------------------------------------------------------------------------
# DERIVED, not itself a `#### Scenario:` block (tasks.md 4.6, 4.8)
# ---------------------------------------------------------------------------


async def test_dispose_engine_after_use_disposes_the_engine(
    configured_database_url: None,
    track_engine_dispose: _DisposeSpy,
) -> None:
    """DERIVED from tasks.md 4.6: "`dispose_engine()` after use disposes
    the engine -- this covers the provider's half only, not the
    application-shutdown scenario" (that half is
    `tests/unit/test_main_database_lifespan.py`).
    """
    async with database.session() as session:
        engine = session.bind

    await database.dispose_engine()

    assert isinstance(engine, AsyncEngine)
    # DERIVED.
    assert track_engine_dispose.was_disposed(engine)


async def test_session_after_dispose_gets_a_fresh_usable_engine(
    configured_database_url: None,
) -> None:
    """DERIVED from tasks.md 4.8 and design.md's Risks ("`lru_cache` on an
    engine factory holds it for the process's life, so disposal must be
    paired with cache invalidation... a test requests a session after
    disposal to confirm a usable engine is produced rather than a disposed
    one").
    """
    async with database.session() as first:
        first_engine = first.bind

    await database.dispose_engine()

    async with database.session() as second:
        second_engine = second.bind
        # DERIVED: a fresh engine, not the disposed one.
        assert second_engine is not first_engine
        # DERIVED: usable -- entering/exiting raises nothing.
        assert isinstance(second, AsyncSession)


# ---------------------------------------------------------------------------
# Requirement: The Connection Setting Is Read No Earlier Than The First
# Session Request
# ---------------------------------------------------------------------------


def test_importing_the_provider_does_not_require_database_url() -> None:
    """Scenario: The connection setting is read only when a session is
    first requested (import half).

    WHEN the application has started but no session has yet been requested
    THEN the database connection setting SHALL NOT have been read

    Proxied here as: importing the provider module succeeds even with
    `DATABASE_URL` entirely absent -- if the setting were read (and
    validated, per the malformed/absent-reporting requirement) at import
    time, this would fail instead. Run in a fresh interpreter on purpose,
    mirroring `test_clickup_client.py`'s
    `test_importing_the_module_does_not_require_a_configured_credential`:
    within this pytest process the module is already imported (see the
    module-level import above), so an in-process import would be a no-op
    cache hit and would assert nothing about import-time behaviour.
    """
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import commerce_ops.shared.infrastructure.driven.database",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.shared.infrastructure.driven.database with "
        "DATABASE_URL absent failed; the connection setting must be read no "
        "earlier than the first session request.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Requirement: An Absent Or Malformed Connection Setting Is Reported At The
# Point Of Use
# ---------------------------------------------------------------------------


async def test_session_requested_with_the_setting_absent_reports_the_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A session is requested with the setting absent.

    WHEN a session is requested and the database connection setting is
    absent from the environment
    THEN the request SHALL fail with a report naming that setting
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(Exception) as caught:
        async with database.session():
            pass

    # SPECIFIED: a report naming the setting.
    assert "DATABASE_URL" in str(caught.value)


async def test_session_requested_with_an_unconnectable_scheme_reports_setting_and_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A session is requested with a setting the application
    cannot connect with.

    WHEN a session is requested and the database connection setting
    carries a scheme the application cannot connect with
    THEN the request SHALL fail with a report naming that setting and the
    scheme required

    `postgresql://` (no `+asyncpg`) is design.md's own example of "the
    exact failure `_must_be_an_async_postgres_url` was written to
    prevent"; `postgresql+asyncpg` is the required scheme design.md names
    literally.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/dummy")

    with pytest.raises(Exception) as caught:
        async with database.session():
            pass

    message = str(caught.value)
    # SPECIFIED: a report naming the setting and the scheme required.
    assert "DATABASE_URL" in message
    assert "postgresql+asyncpg" in message


async def test_session_requested_with_the_setting_empty_reports_the_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from tasks.md 1.3 ("reporting absence or emptiness in a
    message naming DATABASE_URL") and the requirement's own text ("absent,
    empty, or not a connection string...") -- not itself a `#### Scenario:`
    block, which covers only the absent and malformed-scheme cases by name.
    Included as extra coverage for the requirement's third named case,
    mirroring how `test_clickup_client.py` adds symmetric derived coverage
    for an update path a scenario names only generically.
    """
    monkeypatch.setenv("DATABASE_URL", "")

    with pytest.raises(Exception) as caught:
        async with database.session():
            pass

    # DERIVED.
    assert "DATABASE_URL" in str(caught.value)
