"""Shared fixtures for `tests/integration/products/`.

These exercise `ProductRepository` against a real Postgres connection, per
`add-products-store`'s `tasks.md` 6.1 ("Add `tests/integration/products/`
covering the `launch-instance` spec's scenarios against a real Postgres
connection") and `design.md`'s Migration Plan step 8.

## What these fixtures assume, and why nothing here builds schema

At the time this pass was written, no DB driver, ORM model, repository, or
Alembic setup exists anywhere in this project (`add-products-store`'s
Impact section) -- this is the project's first persistence layer. These
fixtures therefore import a `ProductRepository` that does not exist yet, and
every test in this directory is expected to fail on that absence
(`ModuleNotFoundError`) until the implementation lands. That failure
establishes only absence, per `ai-toolkit:testing`'s failure-state
taxonomy -- it is not evidence the scenarios below are wrong.

These fixtures do **not** create the `products` table. `tasks.md` section 2
assigns that to the first Alembic migration; creating it here (e.g. via
`Base.metadata.create_all` or raw DDL) would be writing implementation
inside a test-authoring pass, which this pass does not do. Every test in
this directory assumes `alembic upgrade head` has already been applied to
the database `DATABASE_URL` points at -- exactly the assumption `tasks.md`
4.1 makes when it says running the compose `postgres` service locally and
pointing `DATABASE_URL` at it is what makes this directory runnable.

## Recorded assumptions (see test-manifest.md's "Unresolved project
## questions" for the full list; summarized here where they affect fixtures)

- **`DATABASE_URL`'s scheme.** `tasks.md` 1.2 and 4.1 both say `DATABASE_URL`
  is read from the environment, but no artifact fixes whether it already
  carries an async-driver scheme (e.g. `postgresql+asyncpg://...`) or a
  plain `postgresql://` one `create_async_engine` would reject. These
  fixtures pass the value through unchanged and let `create_async_engine`
  raise if it's the wrong shape -- correcting that shape (e.g. by rewriting
  the scheme here) is a fixture correction if the real convention turns out
  to differ, not a change to what any test asserts.
- **`ProductRepository(session)` and per-call commits.** No artifact
  specifies the repository's constructor or transaction ownership.
  INVENTED here: the repository takes a single `AsyncSession` and each
  method (`create`, `get_by_id`, `get_by_sku`, `update_current_gate`)
  commits its own work, since design.md says this change "does not yet add
  a use case that calls it, since none is needed to exercise the store
  directly via integration tests" -- i.e. the repository is meant to be
  usable standalone, without an external caller managing a transaction.
  If the real implementation instead requires an explicit
  `await session.commit()` from the caller, adjusting these fixtures (not
  the tests' assertions) is what needs correcting.
- **No pytest-asyncio.** This project's `pyproject.toml` declares neither
  `pytest-asyncio` nor an `asyncio_mode`. `anyio` is already an installed
  transitive dependency (FastAPI/Starlette) and auto-registers a pytest
  plugin (`anyio.pytest_plugin`, confirmed present via
  `importlib.metadata.entry_points(group="pytest11")`), so async tests here
  use `@pytest.mark.anyio` instead. No convention file records which async
  test plugin this project intends to standardize on -- recorded as an
  unresolved project question in test-manifest.md.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.products.infrastructure.driven.product_repository import (
    ProductRepository,
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    # Pinned to asyncio: no `trio` dependency is installed in this project
    # (confirmed: `import trio` fails), and nothing in this change's
    # artifacts calls for trio support. Pinning avoids these tests silently
    # gaining a second, trio-backed parametrization if trio is ever added
    # as a transitive dependency later.
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally and point DATABASE_URL at it, per "
            "add-products-store's tasks.md 4.1, to run "
            "tests/integration/products/."
        )
    return url


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    """A fresh async engine per test, disposed on teardown."""
    eng = create_async_engine(_database_url())
    try:
        yield eng
    finally:
        await eng.dispose()


@asynccontextmanager
async def _open_repository(engine: AsyncEngine) -> AsyncIterator[ProductRepository]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield ProductRepository(session)


@pytest.fixture()
async def repository(engine: AsyncEngine) -> AsyncIterator[ProductRepository]:
    """A `ProductRepository` bound to its own session.

    Most scenarios only need one repository instance. Scenarios that must
    prove data actually reached Postgres -- not merely a session's identity
    map -- use `new_repository` below to open a second, independent one.
    """
    async with _open_repository(engine) as repo:
        yield repo


@pytest.fixture()
def new_repository(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[ProductRepository]]:
    """A factory for opening additional, independent repository instances.

    Usage: `async with new_repository() as repo: ...`. Each call opens its
    own session against the same engine/database, so a read through one
    instance after a write through another can only succeed if the write
    was actually committed to Postgres.
    """

    def _factory() -> AbstractAsyncContextManager[ProductRepository]:
        return _open_repository(engine)

    return _factory


def unique_sku() -> str:
    """A SKU unique to this test run.

    Tests in this directory run against a real, persistent Postgres
    database (no truncate/rollback fixture is provided here -- see
    test-manifest.md's unresolved project questions). Generating a fresh
    SKU per test keeps each test correct regardless of rows left over from
    earlier runs, rather than assuming the database starts empty.
    """
    return f"sku-{uuid.uuid4()}"
