"""The pending-result store against a real Postgres.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirement *A result needing confirmation is held
until a member decides*, the one scenario that no in-memory fake can
observe:

    #### Scenario: Two overlapping passes cannot both produce a pending
    result
    - **WHEN** two passes overlap and both would store a pending result
      for the same launch and step
    - **THEN** exactly one pending result stands, and the step is left for
      a later pass

together with the requirement's own statement of the same rule ("At most
one pending result SHALL stand for a launch and step at any moment").

`design.md` is explicit that this is a *database* guarantee and not a
code one: "**A partial unique index on `(product_id, step_id) WHERE state
= 'pending'`** is what makes 'one pending result per step' true under
concurrency rather than only in the read-then-write path. Two overlapping
passes cannot both insert." A unit test over an in-memory fake would
assert the read-then-write path and establish nothing about the case the
scenario names, so the integration tier is the smallest level that can
observe it (`ai-toolkit:testing`'s level rule).

`tasks.md` 1.3 asks for exactly this check: "Verify the revision upgrades
and downgrades cleanly against a live database, and that the partial
index actually refuses a second pending row."

The requirement's other two scenarios are behavioural and are covered in
`tests/unit/launch/infrastructure/driving/test_automation_pass.py`.

See `test-manifest.md` at the change root for the full accounting.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 1.1–1.4 and `design.md`: the table
`automated_step_results` with `product_id`, `step_id`, `handler`,
`proposed_outcome`, `result_text`, `produced_at`, `delivered_at`,
`state` (`pending`/`accepted`/`rejected`/`voided`), `decided_by` and
`decided_at`; the partial unique index; that settled rows are kept, never
deleted.

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The repository's module path and class name. `_repository_class()`
  probes the plausible spellings under
  `launch/infrastructure/driven/` and fails loudly rather than
  defaulting.
- Its method names (`_store`, `_pending_for`, `_settle`), which
  `tasks.md` 1.4 fixes as operations but not as spellings.

What must survive any correction is what each test asserts: that a second
*pending* row for the same launch and step is refused by the database,
that exactly one stands afterwards, and that settling one frees the pair
again.

## Test-database lifecycle

The convention of this directory: a fresh product and launch per test,
no truncate fixture, `alembic upgrade head` (including this change's
revision) assumed applied, and a skip when no database is configured.

## Expected first-run state

Absent target: neither the table nor the repository exists. Where no
database is configured — as here — the tier's gate skips instead, so
these assertions have never been executed at all. Both facts are recorded
in `test-manifest.md`.

Baseline recorded before these tests were written:
`uv run pytest tests/integration` — 3 passed, 81 skipped (no database is
configured here); `uv run pytest tests/unit tests/agents` — 901 passed,
0 failed.
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import (
    ALICE,
    HANDLER_NAME,
    LAUNCH_DATE,
    MARKETPLACE,
    STEP_ID,
)
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

FIRST_TEXT: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards."
SECOND_TEXT: Final = "Sports & Outdoors > Camping & Hiking > Cookware."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# The repository, reached through one correction point
# ---------------------------------------------------------------------------

_REPOSITORY_MODULES: Final = (
    "commerce_ops.launch.infrastructure.driven.automated_results",
    "commerce_ops.launch.infrastructure.driven.automated_result_repository",
    "commerce_ops.launch.infrastructure.driven.automation_results",
)

_REPOSITORY_NAMES: Final = (
    "AutomatedResultRepository",
    "AutomatedStepResultRepository",
)


def _repository_class() -> Any:
    for module_name in _REPOSITORY_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for name in _REPOSITORY_NAMES:
            found = getattr(module, name, None)
            if found is not None:
                return found
    pytest.fail(
        "no pending-result repository found under any of "
        f"{_REPOSITORY_MODULES} as any of {_REPOSITORY_NAMES} — correct "
        "this file's probe to the implemented module and class"
    )


async def _store(
    repository: Any,
    *,
    product_id: ProductId,
    result_text: str,
) -> Any:
    """INVENTED call shape — the single correction point for the write."""
    for name in ("store", "insert", "hold", "add"):
        writer = getattr(repository, name, None)
        if callable(writer):
            return await writer(
                product_id=product_id,
                step_id=STEP_ID,
                handler=HANDLER_NAME,
                proposed_outcome="Satisfied",
                result_text=result_text,
                produced_at=PRODUCED_AT,
            )
    pytest.fail("the pending-result repository exposes no write")


async def _pending_for(repository: Any, product_id: ProductId) -> Any:
    for name in ("pending_for", "pending", "get_pending"):
        reader = getattr(repository, name, None)
        if callable(reader):
            return await reader(product_id, STEP_ID)
    pytest.fail("the pending-result repository exposes no pending read")


async def _settle_as_rejected(repository: Any, row: Any) -> None:
    for name in ("settle", "decide", "resolve"):
        settler = getattr(repository, name, None)
        if callable(settler):
            await settler(
                row, state="rejected", decided_by=ALICE, decided_at=DECIDED_AT
            )
            return
    pytest.fail("the pending-result repository exposes no settle")


# ---------------------------------------------------------------------------
# Domain and database fixtures
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"AR-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": "Choose the sub-category node",
            "kind": StepKind.AUTOMATED,
            "confirmer": ALICE,
            "handler": HANDLER_NAME,
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        confirmer=ALICE,
        handler=f"hold.{gate.replace('-', '_')}",
        kind=StepKind.AUTOMATED,
        name="Choose the sub-category node",
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        _step(),
        filler=_hold,
    )


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
def new_results(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[Any]]:
    """An independent session/store factory per call — two of them are
    what stands in for two overlapping passes."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    repository = _repository_class()

    @asynccontextmanager
    async def _open() -> AsyncIterator[Any]:
        async with maker() as session:
            yield repository(session)

    return _open


@pytest.fixture()
def launched_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product that also has a launch record — the state
    a pending result can reference."""

    async def _launch() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        playbook = _playbook()
        launch, _ = Launch.start(
            product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
        )
        async with maker() as session:
            await LaunchRepository(session).save(launch)
        return product.id

    return _launch


# ---------------------------------------------------------------------------
# Requirement: A result needing confirmation is held until a member decides
# ---------------------------------------------------------------------------


async def test_two_overlapping_passes_cannot_both_produce_a_pending_result(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Two overlapping passes cannot both produce a pending
    result.

    WHEN two passes overlap and both would store a pending result for the
    same launch and step
    THEN exactly one pending result stands, and the step is left for a
    later pass.

    Two independent sessions, so the second insert is refused by the
    database rather than by a read-then-write check in one of them —
    which is the case `design.md` names: "Two overlapping passes cannot
    both insert."
    """
    product_id = await launched_product_id()

    async with new_results() as first:
        await _store(first, product_id=product_id, result_text=FIRST_TEXT)

    # SPECIFIED: the second store for the same launch and step is
    # refused. The losing pass catches it and leaves the step for a later
    # pass, which is what makes this a guarantee rather than a crash.
    with pytest.raises(IntegrityError):
        async with new_results() as second:
            await _store(second, product_id=product_id, result_text=SECOND_TEXT)

    # SPECIFIED: exactly one pending result stands, and it is the first.
    async with new_results() as reader:
        standing = await _pending_for(reader, product_id)
    assert standing is not None
    assert getattr(standing, "result_text", None) == FIRST_TEXT


async def test_settling_a_result_frees_the_launch_and_step_pair(
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """`design.md`: the index is **partial** — `WHERE state = 'pending'`
    — and "Settled rows are kept, never deleted".

    SPECIFIED by the requirement's "at most one pending result ... **at
    any moment**", which a total unique index would over-enforce: once a
    result is decided the step is available again (*A rejected step is
    offered to the handler again once the cool-off elapses*), and a
    second row must be insertable without the first being deleted.

    This is the assertion that distinguishes the specified index from a
    total one, which would pass the test above and then park the step
    forever after its first decision.
    """
    product_id = await launched_product_id()

    async with new_results() as first:
        row = await _store(first, product_id=product_id, result_text=FIRST_TEXT)
        await _settle_as_rejected(first, row)

    async with new_results() as second:
        await _store(second, product_id=product_id, result_text=SECOND_TEXT)

    async with new_results() as reader:
        standing = await _pending_for(reader, product_id)
    # SPECIFIED: a new pending result stands.
    assert standing is not None
    assert getattr(standing, "result_text", None) == SECOND_TEXT


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The Alembic revision's own upgrade/downgrade (`tasks.md` 1.3's first
#   half). Every test in this tier runs against a database already at
#   head, so the upgrade is exercised as a precondition of the file
#   running at all; asserting downgrade would need a migration harness
#   this suite does not have, and `tests/unit/shared/infrastructure/
#   driven/test_alembic_runner_schema_guard.py` is where this project
#   keeps its migration-level guard.
# - The full column set of `automated_step_results`. The columns are
#   `tasks.md` 1.1's list rather than a specification of behaviour, and
#   each one that carries behaviour is observed through the repository
#   above or through the pass's unit tests.
# ---------------------------------------------------------------------------
