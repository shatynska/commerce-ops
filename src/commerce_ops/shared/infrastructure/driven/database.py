"""Driven adapter: the single database session provider for the process.

Implements the `database-session` capability
(`openspec/changes/centralize-database-session/specs/database-session/spec.md`).

Owns the one engine and session factory every caller in this process draws
from -- both callers serving an HTTP request (`get_session`, a FastAPI
dependency) and callers that are not (`session`, a plain async context
manager). See design.md's Decisions for why there are two accessors over
one engine rather than two engines, why the engine stays lazily
constructed, and why disposal tolerates an engine that was never created.
"""

from __future__ import annotations

import functools
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.shared.application.settings import must_be_an_async_postgres_url


def _read_database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError(
            "DATABASE_URL is not set (or is set but empty); the application "
            "cannot obtain a database session without it"
        )
    try:
        return must_be_an_async_postgres_url(value)
    except ValueError as exc:
        raise RuntimeError(f"DATABASE_URL {exc}") from exc


@functools.lru_cache
def _get_engine_and_session_factory() -> tuple[
    AsyncEngine, async_sessionmaker[AsyncSession]
]:
    # Lazy and cached -- constructed on first use, not at import time, so
    # importing this module (and therefore `commerce_ops.main`) never
    # requires `DATABASE_URL` to be set. The session factory is built here
    # too, once, rather than per session request.
    engine = create_async_engine(_read_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """Yields a session to any caller, HTTP request or not.

    Released on both normal completion and exception; an exception from
    the caller's own work propagates unchanged.
    """
    _, session_factory = _get_engine_and_session_factory()
    async with session_factory() as db_session:
        yield db_session


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """Yields a session whose callees' commits cannot end the transaction.

    `session()` is not enough when two writes must land together. Every
    repository in this project commits its own write -- `CatalogProductRepository.add`
    and `LaunchRepository.save` both call `commit()` -- so two writes through
    two repositories are two transactions however carefully the caller shares
    one session between them.

    Binding the session to an explicit connection with
    `join_transaction_mode="create_savepoint"` makes each inner `commit()`
    release a SAVEPOINT instead, leaving the outer transaction -- begun and
    ended here -- the only thing that decides whether anything persists. An
    inner `rollback()` (the one `add` performs before raising
    `DuplicateSkuError`) likewise unwinds only to its savepoint.

    A stopgap, deliberately: the correct fix is to make those repositories
    commit-neutral and let their caller own the boundary. Recorded in
    `docs/deferred-work.md` under "Repositories commit their own writes".
    """
    engine, _ = _get_engine_and_session_factory()
    async with engine.connect() as connection, connection.begin():
        db_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield db_session
        finally:
            # Closing before the outer transaction resolves: the session's
            # own savepoint machinery must be released while its connection
            # is still the one it joined.
            await db_session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """The FastAPI dependency -- a thin `AsyncIterator` over `session()`."""
    async with session() as db_session:
        yield db_session


async def dispose_engine() -> None:
    """Disposes the engine if one was created, clearing the factory cache
    in the same operation so a later session request builds a fresh engine.

    Returns without error if no engine was ever created.
    """
    if _get_engine_and_session_factory.cache_info().currsize > 0:
        engine, _ = _get_engine_and_session_factory()
        await engine.dispose()
    _get_engine_and_session_factory.cache_clear()
