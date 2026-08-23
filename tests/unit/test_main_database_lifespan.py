"""Application-level tests for `database-session`'s process-exit and
unconfigured-startup requirements.

Derived strictly from the `database-session` delta spec's ADDED
requirements' scenarios:

- "A Process That Obtained A Session Closes Its Pool Before Exiting" /
  Scenario: The HTTP process releases connections when it stops
- "The Connection Setting Is Read No Earlier Than The First Session
  Request" / Scenario: Starting and stopping with the database unconfigured

Both need `commerce_ops.main.app` and its lifespan, not just the provider
module in isolation -- see
`tests/unit/shared/infrastructure/driven/test_database.py`'s module
docstring for the other nine scenarios of this same delta spec, covered
there instead.

## Why these two need `main.app`, and the other eleven don't

design.md's own Decisions section says it directly: "The wiring itself
needs its own test. Adding `dispose_engine()` and forgetting to pass
`lifespan=` to `FastAPI(...)` would leave the change's headline defect --
the engine is never disposed -- in place while every unit test, both
regression guards, `mypy`, `ruff` and `lint-imports` still pass, because
the guards all take the no-engine path. A test that starts and stops
`main.app` with an engine in existence, asserting disposal happened, is
the only thing that can catch it." `test_database.py`'s own
`test_dispose_engine_after_use_disposes_the_engine` exercises
`dispose_engine()` directly and would keep passing even if `main.py` never
called it -- only a test going through `main.app`'s own lifespan can catch
that specific miswiring, which is why this file exists as a separate unit
of coverage rather than folding into that one.

## The seam used to observe disposal

Same technique as `test_database.py`: `AsyncEngine.dispose` is
monkeypatched to record which engine instances it was called on, then
delegates to the original -- public SQLAlchemy API, not this project's own
source. See that file's module docstring, "The seams used to observe
'released' and 'disposed'", for the full reasoning; duplicated here in
miniature rather than imported, since this repository's test-path glob and
this pass's additive-only rule both stop at test files, not at a shared
conftest this pass would have to introduce.

## No real Postgres is used

Forcing "an engine in existence" is done by entering and exiting
`database.session()` directly against a syntactically-valid-but-
unreachable `DATABASE_URL`, before the `TestClient` is ever opened --
verified directly that `create_async_engine`/`async_sessionmaker`/
entering-and-exiting an `AsyncSession` issue no query and therefore open no
real connection. Disposing that engine from a different event loop than
the one that constructed it (this test's own vs. `TestClient`'s internal
portal thread) was also verified directly to raise nothing, precisely
because no real connection was ever opened for it to have to close.

## At the time this pass was written, the code under test is unchanged

`commerce_ops.main` declares no lifespan yet (design.md's Context: "FastAPI
supplies a no-op default"), so `test_http_process_disposes_the_engine_it_
obtained_when_it_stops` is expected to fail -- observably, on the assertion
that `AsyncEngine.dispose` was ever called -- until tasks.md 3.1 lands. The
other test in this file,
`test_stopping_http_application_with_database_unconfigured_succeeds`,
exercises behaviour this repository states is unaffected by this change
(no session is ever requested on that path, so the lifespan's "no engine"
branch is what runs) and may therefore pass before the implementation
exists; per `ai-toolkit:testing`'s failure-state taxonomy that is the
expected, correct result for a scenario stating a *non*-regression, not the
"passed before any implementation existed" alarm that applies to the other
test in this file.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from commerce_ops.main import app
from commerce_ops.shared.infrastructure.driven import database

pytestmark = pytest.mark.anyio

TEST_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:1/dummy"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _DisposeSpy:
    disposed_ids: set[int] = field(default_factory=set)

    def was_disposed(self, engine: AsyncEngine) -> bool:
        return id(engine) in self.disposed_ids


@pytest.fixture()
def track_engine_dispose(monkeypatch: pytest.MonkeyPatch) -> _DisposeSpy:
    spy = _DisposeSpy()
    original_dispose = AsyncEngine.dispose

    async def _spy_dispose(self: AsyncEngine, close: bool = True) -> None:
        spy.disposed_ids.add(id(self))
        await original_dispose(self, close)

    monkeypatch.setattr(AsyncEngine, "dispose", _spy_dispose)
    return spy


@pytest.fixture(autouse=True)
def _reset_provider_state() -> Iterator[None]:
    """Sync fixture running its own `asyncio.run(...)` -- see
    `test_database.py`'s own `_reset_provider_state` for why an async
    autouse fixture is unsafe in a module that (there) mixes sync and
    async tests. This file's own tests are all async, but the same sync
    form is used here too so both files stay consistent and so a future
    sync test added here does not silently reintroduce the bug.
    """
    asyncio.run(database.dispose_engine())
    yield
    asyncio.run(database.dispose_engine())


# ---------------------------------------------------------------------------
# Requirement: A Process That Obtained A Session Closes Its Pool Before
# Exiting
# ---------------------------------------------------------------------------


async def test_http_process_disposes_the_engine_it_obtained_when_it_stops(
    monkeypatch: pytest.MonkeyPatch,
    track_engine_dispose: _DisposeSpy,
) -> None:
    """Scenario: The HTTP process releases connections when it stops.

    WHEN the process serving HTTP has obtained a session, and that process
    is then stopped
    THEN its connection pool SHALL be closed as part of stopping

    "Has obtained a session" is forced directly through the provider (see
    module docstring, "No real Postgres is used") rather than through an
    actual route, so this test's subject stays the lifespan wiring, not
    any particular endpoint's behaviour.
    """
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    async with database.session() as session:
        engine = session.bind

    assert isinstance(engine, AsyncEngine)

    # Context-managed so the lifespan's shutdown half actually runs.
    with TestClient(app):
        pass

    # SPECIFIED.
    assert track_engine_dispose.was_disposed(engine), (
        "the engine obtained before the process stopped was not disposed "
        "when the process stopped -- main.py must pass its dispose_engine() "
        "lifespan to FastAPI(lifespan=...) (design.md, 'The wiring itself "
        "needs its own test')"
    )


# ---------------------------------------------------------------------------
# Requirement: The Connection Setting Is Read No Earlier Than The First
# Session Request
# ---------------------------------------------------------------------------


def test_stopping_http_application_with_database_unconfigured_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Starting and stopping with the database unconfigured.

    WHEN the application's HTTP application object is started and then
    stopped with the database connection setting absent, without any
    session being requested
    THEN both SHALL succeed without raising, AND endpoints requiring no
    database SHALL serve normally

    The *starting* half, with every declared variable absent, is already
    covered by `tests/unit/test_startup_without_configuration.py`
    (tasks.md 4.9a: "cite it rather than duplicating it"). This test's own
    contribution is the *stopping* half specifically -- `DATABASE_URL`
    absent, no session ever requested, and the `with` block's exit (which
    runs the lifespan's shutdown half) completing without raising.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with TestClient(app) as client:
        response = client.get("/health")
        # SPECIFIED: endpoints requiring no database serve normally.
        assert response.status_code == 200
    # SPECIFIED: reaching this line means the `with` block's __exit__ (the
    # lifespan's shutdown half) completed without raising -- i.e. stopping
    # succeeded.
