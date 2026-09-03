"""A stored pending result is delivered in the form it was stored, and its
controls resolve it.

Derived strictly from the MODIFIED requirement *A pending result is
delivered for a decision, and delivery failure does not lose it* in
`openspec/changes/fix-launch-thread-mentions/specs/launch-step-automation/spec.md`,
and specifically from the two scenarios that requirement adds:

    #### Scenario: A stored pending result is delivered in the form it was
    stored
    - **WHEN** a pending result that was stored is read back by a later
      pass and delivered
    - **THEN** the message is posted, and no delivery is refused because of
      the form the stored result carries its identifiers in

    #### Scenario: A delivered result's controls resolve the result they
    were composed for
    - **WHEN** a decision is made on the accept or reject control of a
      delivered pending result
    - **THEN** the launch and step the control names are the ones the
      pending result was stored against, and the decision resolves that
      pending result

## Why this cannot be a unit test

The requirement says so itself, in the sentence it adds above these
scenarios:

    A delivery path that requires an identifier in a form the store does
    not produce delivers nothing at all, **while satisfying any test that
    supplies the form it wants**.

That is the whole defect. Every unit stub for this path declares
`product_id: ProductId`, which is the one form the delivery accepted and
the one form `AutomatedStepResult.product_id` (`Mapped[uuid.UUID]`) never
produces. A hand-built result cannot establish either scenario, because
building it *is* the mistake. So the row here is stored through the real
repository and read back through the real `undelivered()` — the same query
the pass reads it with — and nothing about its shape is this file's
invention.

Slack is still substituted. The scenarios are about the form the store
hands back and about what the controls carry, neither of which needs a
real Slack; raising the level further would buy no evidence
(`ai-toolkit:testing`'s level rule).

## Level, precisely

The store and the delivery together, over a real Postgres, with the
thread-and-mention preamble and the Slack poster substituted at
`automation_confirmation.py`'s module-level seams — the same two seams the
unit tests in
`tests/unit/launch/infrastructure/driving/` substitute, so a correction to
either applies here identically.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: `AutomatedResultRepository.undelivered()`
as the query that hands back the rows the pass delivers (`proposal.md`
defect 4; `tasks.md` 5.4 names it as the query to count off); the
`product_id: ProductId` parameter and the button payload composed from
`product_id.value` (`tasks.md` 2.1–2.2); that `_deliver_waiting` passes the
`ProductId` it already builds (2.3).

INVENTED, recorded in `test-manifest.md`:

- The repository's module path, class and write method — probed, exactly
  as `test_automated_result_store_live.py` in this directory probes them,
  and reusing its correction points rather than inventing new ones.
- The control payload's internal format. Nothing fixes how a product
  identifier and a step identifier are joined into one action value, so
  this file asserts on *containment* of each part plus the absence of an
  object rendering, and does the resolution half through the store's own
  pending lookup rather than by re-parsing the payload with a separator it
  would have to guess.

## Expected first-run state

Where no database is configured — as in the environment this file was
written in — this tier skips, and these assertions have never executed at
all. Recorded in `test-manifest.md`, per `ai-toolkit:testing`'s rule that
an unexecuted assertion establishes nothing.

Against a database, both tests are expected to FAIL: today
`deliver_pending_result` takes no `product_id` parameter, so `_deliver`'s
probe fails first; with the parameter removed from the call it would
instead raise `TypeError: product_id must be ProductId, got <class
'uuid.UUID'>`, which is the defect itself.
"""

from __future__ import annotations

import importlib
import inspect
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import HANDLER_NAME, LAUNCH_DATE, MARKETPLACE, STEP_ID
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

CONFIRMATION_MODULE: Final = (
    "commerce_ops.launch.infrastructure.driving.automation_confirmation"
)

STEP_NAME: Final = "Choose the sub-category node"
CONFIRMER_MEMBER_ID: Final = "3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30"
CONFIRMER_SLACK: Final = "U01ALICE"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
SLACK_THREAD_TS: Final = "1700000000.000100"

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration."
)

_PRODUCT_ID_PARAMETER_NAMES: Final = ("product_id",)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# The repository, reached through the same correction points
# `test_automated_result_store_live.py` established
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
        f"{_REPOSITORY_MODULES} as any of {_REPOSITORY_NAMES}"
    )


async def _store(repository: Any, *, product_id: ProductId) -> Any:
    for name in ("store", "insert", "hold", "add"):
        writer = getattr(repository, name, None)
        if callable(writer):
            return await writer(
                product_id=product_id,
                step_id=STEP_ID,
                handler=HANDLER_NAME,
                proposed_outcome="Satisfied",
                result_text=RECOMMENDATION,
                produced_at=PRODUCED_AT,
            )
    pytest.fail("the pending-result repository exposes no write")


async def _undelivered(repository: Any) -> Any:
    """`undelivered()` by name — the query `_deliver_waiting` iterates, and
    the one `tasks.md` 5.4 insists the pre-deploy count be read off rather
    than off a hand-written predicate."""
    reader = getattr(repository, "undelivered", None)
    if not callable(reader):
        pytest.fail(
            "the pending-result repository exposes no `undelivered()`; "
            "`proposal.md`'s defect 4 and `tasks.md` 5.4 both name it"
        )
    return await reader()


async def _pending_for(repository: Any, product_id: ProductId, step_id: str) -> Any:
    for name in ("pending_for", "pending", "get_pending"):
        reader = getattr(repository, name, None)
        if callable(reader):
            return await reader(product_id, step_id)
    pytest.fail("the pending-result repository exposes no pending read")


# ---------------------------------------------------------------------------
# Slack substitution, at the same two seams the unit tier substitutes
# ---------------------------------------------------------------------------


class _CapturingPoster:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    @property
    def rendered(self) -> str:
        return json.dumps(self.calls, default=str)

    @property
    def control_values(self) -> list[str]:
        """Every action `value` the posted blocks carry — the payload a
        decision is parsed out of.

        Read structurally rather than by matching the rendered JSON, so
        that "the controls carry X" cannot be satisfied by X appearing in
        the message text instead.
        """
        values: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                carried = node.get("value")
                if isinstance(carried, str) and node.get("type") == "button":
                    values.append(carried)
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        for call in self.calls:
            walk(call.get("blocks"))
        return values


async def _fake_thread_seam(*args: Any, **kwargs: Any) -> tuple[str, str | None]:
    return SLACK_THREAD_TS, CONFIRMER_SLACK


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


def _install_slack(monkeypatch: pytest.MonkeyPatch) -> _CapturingPoster:
    module = importlib.import_module(CONFIRMATION_MODULE)
    poster = _CapturingPoster()
    for name, double in (
        ("establish_thread_and_resolve_mention", _fake_thread_seam),
        ("post_monitoring_message", poster),
    ):
        if not hasattr(module, name):
            pytest.fail(f"{CONFIRMATION_MODULE} exposes no substitutable `{name}`")
        monkeypatch.setattr(module, name, double)
    return poster


async def _deliver(*, result: Any, product: Any, product_id: ProductId) -> None:
    """INVENTED call shape — the single correction point, kept identical to
    `tests/unit/launch/infrastructure/driving/test_pending_result_ask_untagged_policy.py`'s."""
    module = importlib.import_module(CONFIRMATION_MODULE)
    entry = getattr(module, "deliver_pending_result", None)
    if not callable(entry):
        pytest.fail(f"{CONFIRMATION_MODULE} has no `deliver_pending_result`")

    parameters = inspect.signature(entry).parameters
    for name in _PRODUCT_ID_PARAMETER_NAMES:
        if name in parameters:
            break
    else:
        pytest.fail(
            "`deliver_pending_result` accepts no product identifier under any "
            f"of {_PRODUCT_ID_PARAMETER_NAMES}; its parameters are "
            f"{tuple(parameters)}"
        )

    await entry(
        result=result,
        product=product,
        step_name=STEP_NAME,
        step=None,
        **{name: product_id},
    )


# ---------------------------------------------------------------------------
# Domain and database fixtures (this directory's convention)
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"SEAM-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": STEP_NAME,
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "confirmer": CONFIRMER_MEMBER_ID,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": HANDLER_NAME,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(_step(), *fillers))


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
    maker = async_sessionmaker(engine, expire_on_commit=False)
    repository = _repository_class()

    @asynccontextmanager
    async def _open() -> AsyncIterator[Any]:
        async with maker() as session:
            yield repository(session)

    return _open


@pytest.fixture()
def launched_product(
    engine: AsyncEngine,
) -> Callable[[], Awaitable[tuple[ProductId, _CatalogProduct]]]:
    async def _launch() -> tuple[ProductId, _CatalogProduct]:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        sku = _unique_sku()
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=sku,
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        playbook = _playbook()
        launch, _ = Launch.start(
            product_id=product.id, playbook=playbook, launch_date=LAUNCH_DATE
        )
        async with maker() as session:
            await LaunchRepository(session).save(launch)
        return product.id, _CatalogProduct(name="Bamboo Cutting Board", sku=sku)

    return _launch


# ---------------------------------------------------------------------------
# Scenario: A stored pending result is delivered in the form it was stored
# ---------------------------------------------------------------------------


async def test_a_stored_pending_result_is_delivered_in_the_form_it_was_stored(
    monkeypatch: pytest.MonkeyPatch,
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product: Callable[[], Awaitable[tuple[ProductId, _CatalogProduct]]],
) -> None:
    """Scenario: A stored pending result is delivered in the form it was
    stored.

    WHEN a pending result that was stored is read back by a later pass and
    delivered
    THEN the message is posted, and no delivery is refused because of the
    form the stored result carries its identifiers in.

    SPECIFIED. The row is read back through `undelivered()` — the query the
    pass itself iterates — rather than constructed, which is the only way
    this scenario can be observed at all.

    The precondition below is not decoration: it is what makes the test
    establish the scenario rather than merely exercise the code. If the
    row's identifier arrived as a `ProductId`, the delivery would succeed
    for the wrong reason and this test would pass while the production path
    still raised.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")
    poster = _install_slack(monkeypatch)
    product_id, product = await launched_product()

    async with new_results() as writer:
        await _store(writer, product_id=product_id)

    async with new_results() as reader:
        waiting = [row for row in await _undelivered(reader) if row.step_id == STEP_ID]

    assert waiting, (
        "the stored pending result was not returned by `undelivered()`; "
        "nothing downstream of this point can be established"
    )
    row = next(
        candidate
        for candidate in waiting
        if str(candidate.product_id) == product_id.value
    )
    # Precondition: the store really does hand the identifier back in the
    # form the delivery used to reject.
    assert not isinstance(row.product_id, ProductId), (
        f"the stored row carries its product identifier as {type(row.product_id)!r}, "
        "which is the form the delivery already accepted — this test then "
        "establishes nothing about the scenario"
    )

    # SPECIFIED: the message is posted, and no delivery is refused because
    # of the form the stored result carries its identifiers in. A raised
    # TypeError here is defect 4 itself.
    await _deliver(
        result=row,
        product=product,
        product_id=ProductId(str(row.product_id)),
    )

    assert poster.calls, (
        "a pending result read back from the store was not delivered at all"
    )
    assert RECOMMENDATION in poster.rendered, (
        f"the delivered message did not carry the stored result text: "
        f"{poster.rendered!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A delivered result's controls resolve the result they were
# composed for
# ---------------------------------------------------------------------------


async def test_a_delivered_results_controls_resolve_the_result_they_were_composed_for(
    monkeypatch: pytest.MonkeyPatch,
    new_results: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product: Callable[[], Awaitable[tuple[ProductId, _CatalogProduct]]],
) -> None:
    """Scenario: A delivered result's controls resolve the result they were
    composed for.

    WHEN a decision is made on the accept or reject control of a delivered
    pending result
    THEN the launch and step the control names are the ones the pending
    result was stored against, and the decision resolves that pending
    result.

    SPECIFIED. Asserted in three steps, which together are the round trip:

    1. the controls carry the stored identifier's own value and the stored
       step — never a rendering of the object, which a parsed payload could
       not resolve at all;
    2. reconstructing a `ProductId` from what the control carries, the way
       `_handle_decision` does, yields the identifier the result was stored
       against;
    3. looking that pair up in the store — which is what a decision does to
       resolve the result — returns the row that was stored.

    Step 3 is the "resolves that pending result" clause, done through the
    store's own pending lookup rather than by driving `accept_automated_
    result` end to end: the latter would need a membership and a served
    playbook whose absence would fail this test for reasons that have
    nothing to do with the control payload. Recorded in `test-manifest.md`
    as a narrower reading of the scenario's second half.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")
    poster = _install_slack(monkeypatch)
    product_id, product = await launched_product()

    async with new_results() as writer:
        await _store(writer, product_id=product_id)

    async with new_results() as reader:
        row = next(
            candidate
            for candidate in await _undelivered(reader)
            if str(candidate.product_id) == product_id.value
            and candidate.step_id == STEP_ID
        )

    await _deliver(
        result=row, product=product, product_id=ProductId(str(row.product_id))
    )

    values = poster.control_values
    # SPECIFIED: an accept and a reject decision are offered.
    assert len(values) >= 2, (
        f"the delivered ask carried fewer than two decision controls: {values!r}"
    )
    for carried in values:
        # SPECIFIED: naming the launch and the step it was stored against …
        assert str(row.product_id) in carried, (
            f"a control does not name the launch the result was stored "
            f"against: {carried!r}"
        )
        assert row.step_id in carried, (
            f"a control does not name the step the result was stored against: "
            f"{carried!r}"
        )
        # SPECIFIED (`shared-vocabulary`): … as the identifier's own value.
        # A payload is parsed rather than read, so an object rendering here
        # is unresolvable, not merely ugly.
        assert "ProductId" not in carried, (
            f"a control payload carries a rendering of the identifier's "
            f"object: {carried!r}"
        )

    # SPECIFIED: and the decision resolves that pending result — the pair
    # the control names, reconstructed the way a decision reconstructs it,
    # finds the row that was stored.
    named = ProductId(str(row.product_id))
    assert named == product_id, (
        f"the control names {named!r}, which is not the launch the result was "
        f"stored against ({product_id!r})"
    )
    async with new_results() as reader:
        resolved = await _pending_for(reader, named, row.step_id)
    assert resolved is not None, (
        "the launch and step the controls name resolve to no pending result; "
        "a decision on them would find nothing to settle"
    )
    assert getattr(resolved, "result_text", None) == RECOMMENDATION, (
        "the controls resolve to a different pending result than the one they "
        "were composed for"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Driving `accept_automated_result` end to end from the control payload.
#   It needs a members collaborator and a served playbook, whose absence
#   would fail this file for reasons unrelated to the seam under test; the
#   decision rules themselves are covered in
#   `tests/unit/launch/application/test_automated_result_decisions.py`. What
#   this file establishes instead is the half those tests assume: that the
#   pair reaching them is the pair the result was stored against.
# - The one-time backlog release (`design.md`; `tasks.md` 5.4). It is a
#   deployment observation about rows that already exist in production, not
#   a property of the code, and no test over a fresh test database can
#   observe it.
# ---------------------------------------------------------------------------
