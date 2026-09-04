"""A confirmable step's finding survives the wait for a member
(`launch-step-automation`), end to end.

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-step-automation/spec.md`

Covers two scenarios of its ADDED requirement *A written finding is kept
on the recording it produced*, across the seam neither half can observe
alone (`tasks.md` 1.11 and 1.18b):

    #### Scenario: A confirmable step's finding survives until the result
    is accepted
    - **WHEN** a handler reports a supported finding with a terminal
      outcome for a step naming a confirmer, and the value is written
    - **THEN** the finding is stored with the pending result, and the
      recording made when a member accepts carries the field name, the
      value and the comment

    #### Scenario: The value kept is the value as written
    - **WHEN** a pending result's finding is kept on the recording an
      acceptance makes
    - **THEN** the value kept is the one written when the handler ran, and
      the sink is not re-read at acceptance

This is the row `design.md` records the change's first draft got wrong:
"A design that kept the finding only on the recording the pass makes
would ... deliver nothing for the compliance step — the step this whole
line of work exists for." Both automated steps that exist today sit on
opposite sides of the confirmation line, and `lp.strategy.006` — the one
this feature is for — is on this one. A suite passing without this file
would report a working mechanism that renders nothing for it.

The pass's storing half alone is also asserted in
`tests/unit/launch/infrastructure/driving/test_automation_pass_kept_finding.py`;
the decision's accepting half alone in
`tests/unit/launch/application/test_accepted_result_carried_finding.py`.
Neither can observe the hop, which is why this file exists in addition to
both rather than instead of either. See `test-manifest.md` at the change
root for the full accounting of all 28 scenarios.

## Level

Two units joined by one store: the real `run_automation_pass` and the
real `accept_automated_result`, over one in-memory pending-result double
they both hold. That is the smallest unit that can observe a finding
*surviving* the wait — the point of the scenario — and it is still a unit
test: no database, no network, no LLM.

## What is fixed, and what is INVENTED

Fixed by the artifacts: everything the two single-sided files record as
fixed, plus that the value written when the handler ran is what the
acceptance records, and that the sink is not re-read (`tasks.md` 2.7;
delta).

INVENTED, each recorded in `test-manifest.md`:

- `FindingSink`'s export location and construction (`_sink`), and the
  keyword a kept finding travels under (`_KEPT_KWARGS`) — the same two
  correction points as the pass file.
- That "a direct write elsewhere" is modelled by mutating the catalog
  double between the hold and the acceptance. The delta names the case
  ("a direct write elsewhere can [overwrite it]") without saying what
  performs it; nothing in this deployment does today, so the mutation
  stands in for one.
- The doubles and the call shapes, carried from the two single-sided
  files.

## Expected first-run state

**Absent target.** `FindingSink` does not exist (`tasks.md` 2.2), so
every test here is expected to fail through `_sink()`'s loud probe. Per
`ai-toolkit:testing` that establishes absence and nothing about whether
these assertions are any good.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution, accept_automated_result
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import automation_pass
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.result import Success
from tests.support._paired import paired as _paired
from tests.support.fakes import InertBackoff as _Shared
from tests.support.fixtures import (
    ALICE,
    ALICE_NAME,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import MemberValue as _Member

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
STEP_ID: Final = "strategy.compliance-screen"
HANDLER_NAME: Final = "strategy.compliance_screen"

ALICE_SLACK: Final = "U01ALICE"
PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Screened against the hazardous-category list; none applies. "
    "Checked: aerosols, lithium cells, pressurised containers."
)
#: The value the handler establishes and the sink writes.
WRITTEN_VALUE: Final = "no hazardous categories"
FINDING_COMMENT: Final = "Checked aerosols, lithium cells, pressurised containers."

#: The value something *else* writes to the product between the hold and
#: the acceptance. If it appears on the recording, the sink was re-read.
LATER_VALUE: Final = "A LATER VALUE NOBODY DECIDED ON"

SINK_FIELD: Final = "hazard_screen"
SINK_WORDING: Final = "Hazard screen"

_KEPT_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_ABSENT: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": "Screen for hazardous categories",
            "kind": StepKind.AUTOMATED,
            "confirmer": ALICE,
            "handler": HANDLER_NAME,
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(
        version="confirmable-finding-v1", gates=_gates(), steps=(_step(), *fillers)
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Doubles the two halves share
# ---------------------------------------------------------------------------


class _Catalog:
    """The product the handler is given, and the place the sink writes.

    `written` is what a later reader of the product would see, which is
    what the "not re-read at acceptance" clause is about.
    """

    def __init__(self) -> None:
        self.written: dict[ProductId, Any] = {}
        self.reads: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.reads.append(product_id)
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


class _SinkWriter:
    """The sink's recording callable, writing into the catalog double."""

    def __init__(self, catalog: _Catalog) -> None:
        self.catalog = catalog
        self.calls: list[tuple[ProductId, Any]] = []

    async def __call__(self, product_id: ProductId, value: Any) -> object:
        self.calls.append((product_id, value))
        self.catalog.written[product_id] = value
        return object()


class _Launches:
    def __init__(self, launch: Launch) -> None:
        self._launch = launch

    async def list_active(self) -> list[Launch]:
        return [self._launch]

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launch if product_id == self._launch.product_id else None


class _Handlers:
    def __init__(self, **handlers: Any) -> None:
        self._handlers = dict(handlers)

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def resolve(self, name: str) -> Any:
        return self._handlers[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self._handlers.get(name, default)


class _Handler:
    def __init__(self, resolution: Any) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> Any:
        self.contexts.append(context)
        return self.resolution


class _PendingRow:
    """One pending result, exposing whatever was stored beside it under
    every candidate name (see the pass file's note on `_KEPT_KWARGS`)."""

    #: Declared so the row reads as a row rather than as a bag of
    #: attributes; the values are supplied by the constructor below.
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime

    def __init__(self, **attributes: Any) -> None:
        extra = {key: value for key, value in attributes.items() if key in _KEPT_KWARGS}
        stored = next(iter(extra.values()), None)
        for key, value in attributes.items():
            setattr(self, key, value)
        for name in _KEPT_KWARGS:
            setattr(self, name, stored)
        self.state = "pending"
        self.delivered_at: datetime | None = None
        self.decided_by: str | None = None
        self.decided_at: datetime | None = None
        self.stored_extra = dict(extra)


class _Results:
    """The one store both halves hold — the seam this file exists for."""

    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []
        self.store_calls: list[dict[str, Any]] = []

    async def store(self, **kwargs: Any) -> _PendingRow:
        self.store_calls.append(dict(kwargs))
        row = _PendingRow(**kwargs)
        self.rows.append(row)
        return row

    async def pending_for(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        for row in self.rows:
            if (
                row.product_id == product_id
                and row.step_id == step_id
                and row.state == "pending"
            ):
                return row
        return None

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        for candidate in self.rows:
            if candidate is row:
                candidate.delivered_at = when or PRODUCED_AT

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        return None

    async def settle(
        self, row: object, *, state: str, decided_by: str, decided_at: datetime
    ) -> None:
        for candidate in self.rows:
            if candidate is row:
                candidate.state = state
                candidate.decided_by = decided_by
                candidate.decided_at = decided_at
                return
        raise AssertionError(f"unknown pending row {row!r}")

    async def void(self, row: object) -> None:
        for candidate in self.rows:
            if candidate is row:
                candidate.state = "voided"

    @property
    def only(self) -> _PendingRow:
        assert len(self.rows) == 1, f"expected one pending row, got {len(self.rows)}"
        return self.rows[0]


class _Recordings:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    def for_step(self, step_id: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("step_id") == step_id]


class _Members:
    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


@_paired(_Shared)
class _InertBackoff:
    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def note(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _InertNotifier:
    """A `ThreadReplyNotifier` (`launch.application.ports`) never reached
    in this file: nothing here exercises a repeat, so `_report_stuck_step`
    is never called. Shaped to match it anyway rather than the message-only
    `MonitoringNotifier` — `fix-stuck-step-report-notifier` narrowed
    `run_automation_pass`'s `notifier` parameter to `ThreadReplyNotifier`,
    the shape this collaborator actually stands in for."""

    async def post_monitoring_message(
        self, *, channel: str, text: str, thread_ts: str | None = None
    ) -> None:
        return None


class _Delivery:
    def __init__(self) -> None:
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    return "FAKE_THREAD_TS", None


# ---------------------------------------------------------------------------
# `FindingSink`, and reading a kept finding
# ---------------------------------------------------------------------------

_SINK_MODULES: Final = (
    "commerce_ops.launch.application",
    "commerce_ops.launch.application.ports",
)
_SINK_NAMES: Final = ("FindingSink", "Sink", "FindingRegistration")


def _sink_class() -> Any:
    for module_name in _SINK_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover
            continue
        for name in _SINK_NAMES:
            found = getattr(module, name, None)
            if isinstance(found, type):
                return found
    pytest.fail(
        f"no sink registration type found under any of {list(_SINK_MODULES)} "
        f"as any of {list(_SINK_NAMES)}; `tasks.md` 2.2 adds one to "
        "`launch/application/ports.py` — correct `_SINK_NAMES`"
    )


def _sink(record: Any) -> Any:
    sink_type = _sink_class()
    try:
        return sink_type(record, SINK_FIELD, SINK_WORDING)
    except TypeError:
        return sink_type(record=record, field=SINK_FIELD, reads_as=SINK_WORDING)


def _kept(call: Mapping[str, Any]) -> Any:
    for name in _KEPT_KWARGS:
        if name in call:
            return call[name]
    return _ABSENT


def _carries_nothing(kept: Any) -> bool:
    return kept is _ABSENT or kept is None


def _parts(kept: Any) -> tuple[Any, Any, Any]:
    def _part(key: str) -> Any:
        if isinstance(kept, Mapping):
            return kept.get(key, _ABSENT)
        return getattr(kept, key, _ABSENT)

    comment = _part("comment")
    return _part("field"), _part("value"), _ABSENT if comment is None else comment


# ---------------------------------------------------------------------------
# The two halves, run in order over one store
# ---------------------------------------------------------------------------


@dataclass
class _World:
    playbook: LaunchPlaybook
    launches: _Launches
    results: _Results = field(default_factory=_Results)
    recordings: _Recordings = field(default_factory=_Recordings)
    catalog: _Catalog = field(default_factory=_Catalog)
    delivery: _Delivery = field(default_factory=_Delivery)


def _world(
    value: Any = WRITTEN_VALUE, comment: Any = FINDING_COMMENT
) -> tuple[_World, _Handlers, _SinkWriter]:
    playbook = _playbook()
    world = _World(playbook=playbook, launches=_Launches(_launch(playbook)))
    handler = _Handler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=value, comment=comment),
        )
    )
    return world, _Handlers(**{HANDLER_NAME: handler}), _SinkWriter(world.catalog)


async def _run_pass(world: _World, handlers: _Handlers, writer: _SinkWriter) -> None:
    """Run the pass. The step names a confirmer and the proposal is
    terminal, so the outcome is held rather than recorded."""
    await automation_pass.run_automation_pass(
        launches=world.launches,
        playbook=world.playbook,
        handlers=handlers,
        results=world.results,
        record_outcome=world.recordings,
        read_product=world.catalog,
        deliver=world.delivery,
        backoff=_InertBackoff(),
        notifier=_InertNotifier(),
        establish_thread=_inert_establish_thread,
        now=PRODUCED_AT,
        recorders={STEP_ID: _sink(writer)},
    )


async def _accept(world: _World) -> Any:
    return await accept_automated_result(
        results=world.results,
        members=_Members(
            _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
        ),
        launches=world.launches,
        playbook=world.playbook,
        record_outcome=world.recordings,
        product_id=PRODUCT_ID,
        step_id=STEP_ID,
        slack_identity=ALICE_SLACK,
        when=DECIDED_AT,
    )


# ---------------------------------------------------------------------------
# Scenario: A confirmable step's finding survives until the result is
# accepted (tasks.md 1.11)
# ---------------------------------------------------------------------------


async def test_a_confirmable_steps_finding_survives_until_it_is_accepted() -> None:
    """The whole scenario in one run: written at the handler, stored with
    the pending result, and carried onto the recording acceptance makes.

    Every link is asserted, so a break in any one of them is readable from
    the failure rather than needing to be traced.
    """
    world, handlers, writer = _world()

    await _run_pass(world, handlers, writer)

    # The value was written to the sink when the handler ran.
    assert writer.calls == [(PRODUCT_ID, WRITTEN_VALUE)]
    # The terminal proposal was held, not recorded.
    assert world.recordings.for_step(STEP_ID) == []
    # ... and the finding was stored with it.
    stored = _kept(world.results.store_calls[0])
    assert not _carries_nothing(stored), (
        "the pending result was stored carrying no finding, so nothing can "
        "survive the wait for the confirmer"
    )

    decision = await _accept(world)

    assert getattr(decision, "refused", True) is False, (
        f"the acceptance was refused: {getattr(decision, 'reason', decision)!r}"
    )
    calls = world.recordings.for_step(STEP_ID)
    assert len(calls) == 1, f"the acceptance made {len(calls)} recordings"
    kept = _kept(calls[0])
    assert not _carries_nothing(kept), (
        "the acceptance recorded no finding; the mechanism produces nothing "
        "on the page for a confirmable step, which is every step this "
        "feature is for"
    )
    field_name, value, comment = _parts(kept)
    assert field_name == SINK_FIELD
    assert value == WRITTEN_VALUE
    assert comment == FINDING_COMMENT
    assert world.results.only.state == "accepted"


async def test_an_empty_value_survives_the_wait_as_a_finding() -> None:
    """The `lp.strategy.006` shape specifically: the screen establishes
    that *no* hazardous category applies, and that emptiness must survive
    the hold as a finding rather than as nothing.

    `design.md` names this as the state a reader most needs distinguished
    from a step that established nothing, and the hold is where it is
    most easily lost.
    """
    world, handlers, writer = _world(value=[])

    await _run_pass(world, handlers, writer)
    decision = await _accept(world)

    assert getattr(decision, "refused", True) is False
    kept = _kept(world.recordings.for_step(STEP_ID)[0])
    assert not _carries_nothing(kept), (
        "an empty value was lost across the wait for a confirmer"
    )
    _field, value, _comment = _parts(kept)
    assert value == []


# ---------------------------------------------------------------------------
# Scenario: The value kept is the value as written (tasks.md 1.18b)
# ---------------------------------------------------------------------------


async def test_the_value_kept_is_the_one_written_when_the_handler_ran() -> None:
    """WHEN a pending result's finding is kept on the recording an
    acceptance makes THEN the value kept is the one written when the
    handler ran, and the sink is not re-read at acceptance.

    The product's value is changed between the hold and the acceptance,
    standing in for the "direct write elsewhere" the delta names. An
    implementation that re-read the sink at acceptance would record the
    later value — substituting something for the value the member was
    shown and decided on — and would pass a test that only asserted the
    recording carried *a* value.
    """
    world, handlers, writer = _world()

    await _run_pass(world, handlers, writer)
    assert world.catalog.written[PRODUCT_ID] == WRITTEN_VALUE

    # A direct write elsewhere, after the member was shown the proposal.
    world.catalog.written[PRODUCT_ID] = LATER_VALUE

    decision = await _accept(world)

    assert getattr(decision, "refused", True) is False
    kept = _kept(world.recordings.for_step(STEP_ID)[0])
    assert not _carries_nothing(kept)
    _field, value, _comment = _parts(kept)
    assert value == WRITTEN_VALUE, (
        "the acceptance recorded a value written after the member decided"
    )
    assert value != LATER_VALUE
    # And the sink itself was invoked exactly once, by the pass — the
    # acceptance neither read it nor wrote through it again.
    assert writer.calls == [(PRODUCT_ID, WRITTEN_VALUE)]
    assert world.catalog.written[PRODUCT_ID] == LATER_VALUE
