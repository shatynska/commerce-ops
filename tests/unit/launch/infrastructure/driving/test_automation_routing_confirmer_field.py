"""Automated-result routing restated over `confirmer` rather than a flag.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-step-automation/spec.md`

This delta states no new routing policy for these three requirements —
only their vocabulary changes, from a boolean "confirmation flag" to a
named `confirmer` — but each is MODIFIED and each restates its scenario
in terms of the new field, so each gets a fresh test naming `confirmer`
rather than `needs_confirmation`, per this pass's own rule that a MODIFIED
requirement's scenarios-as-revised are covered exactly as an ADDED
requirement's would be:

- *A non-terminal outcome is recorded directly and never held for a
  decision* — scenario *A non-terminal outcome on a confirmable step is
  recorded, not held*, restated: "...whatever confirmer the step names."
- *A result needing no confirmation is recorded at once* — scenario *An
  unconfirmed result is recorded directly*, restated: "the resolved step
  names no confirmer."
- *A result needing confirmation is held until a person decides* —
  scenario *A confirmable terminal result is held rather than recorded*,
  restated: "the resolved step names a confirmer."
- *The retained record covers results held for a decision and nothing
  else* — both scenarios, restated over "a step naming [no] confirmer".

The existing `test_automation_pass.py` and
`test_retained_record_boundary.py` cover the same routing over the old
`needs_confirmation` fixture kwarg; they are not superseded (the field
rename is mechanical, tracked by `tasks.md` 7.1, not a behavioral
finding), and are not duplicated wholesale here — this file exists to
name `confirmer` where the delta's own scenario text now does, reusing
those two files' doubles and harness verbatim.

**Level.** The automation pass over doubles, plus the retained-results
read over the same result store the pass wrote to — the same placement
`test_retained_record_boundary.py` uses and explains for the same reason
(the read has to observe the set the pass actually produced).

## Expected first-run state

`StepDefinition` carries no `confirmer` field yet, so every test here
fails on a `TypeError` (unexpected keyword argument) — absence, and
nothing more.
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import automation_pass
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

CONFIRMED_STEP: Final = "listing.sub-category"
UNCONFIRMED_STEP: Final = "listing.needs-no-confirmer"
NON_TERMINAL_STEP: Final = "listing.still-running"

CONFIRMED_HANDLER: Final = "listing.subcategory_advisor"
UNCONFIRMED_HANDLER: Final = "listing.records_at_once"
NON_TERMINAL_HANDLER: Final = "listing.reports_progress"

ALICE: Final = "prs_01HQ8Z6M4A"
LAUNCH_DATE: Final = date(2027, 3, 2)
NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

HELD_TEXT: Final = "Home and Kitchen, Cutting Boards."
RECORDED_TEXT: Final = "Nothing here needed anyone's agreement."
PROGRESS_TEXT: Final = "The category tree read is still running."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": CONFIRMED_STEP,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "confirmer": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _automated(identifier: str, handler: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "kind": StepKind.AUTOMATED,
        "handler": handler,
        "assignees": (),
    }
    attributes.update(overrides)
    return _step(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work of hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (matching `test_automation_pass.py` /
# `test_retained_record_boundary.py`)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


class _FakeLaunches:
    def __init__(self, *launches: Launch) -> None:
        self._launches = list(launches)

    async def list_active(self) -> list[Launch]:
        return list(self._launches)

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        for launch in self._launches:
            if launch.product_id == product_id:
                return launch
        return None


class _ScriptedHandler:
    def __init__(self, resolution: StepResolution) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        return self.resolution


class _FakeHandlers:
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


@dataclass
class _PendingRow:
    id: int
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


_READ_NAMES: Final = (
    "for_product",
    "all_for_product",
    "retained_for",
    "retained_for_product",
    "results_for",
    "list_for_product",
    "by_product",
    "all_for",
)


class _FakeResults:
    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []
        self._next_id = 1

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

    async def store(
        self,
        *,
        product_id: ProductId,
        step_id: str,
        handler: str,
        proposed_outcome: Any,
        result_text: str,
        produced_at: datetime,
    ) -> _PendingRow:
        row = _PendingRow(
            id=self._next_id,
            product_id=product_id,
            step_id=step_id,
            handler=handler,
            proposed_outcome=proposed_outcome,
            result_text=result_text,
            produced_at=produced_at,
        )
        self._next_id += 1
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        self._row_of(row).delivered_at = when or NOW

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        return None

    async def _answer(self, *args: Any, **kwargs: Any) -> list[_PendingRow]:
        wanted = None
        for value in (*args, *kwargs.values()):
            if isinstance(value, ProductId):
                wanted = value
        rows = [row for row in self.rows if row.product_id == wanted]
        return sorted(rows, key=lambda row: (row.produced_at, row.id), reverse=True)

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        for candidate in self.rows:
            if candidate is row:
                return candidate
        raise AssertionError(f"unknown pending row {row!r}")


for _name in _READ_NAMES:
    setattr(_FakeResults, _name, _FakeResults._answer)


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    def for_step(self, step_id: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("step_id") == step_id]


class _FakeDelivery:
    def __init__(self) -> None:
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)


@dataclass
class _Collaborators:
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    handlers: _FakeHandlers
    results: _FakeResults = field(default_factory=_FakeResults)
    recorder: _RecordingOutcomes = field(default_factory=_RecordingOutcomes)
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    delivery: _FakeDelivery = field(default_factory=_FakeDelivery)


# ---------------------------------------------------------------------------
# The pass, reached through one correction point
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)


def _pass_entry() -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(automation_pass, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no pass entry point found on "
        f"{automation_pass.__name__} under any of {_ENTRY_NAMES} — correct "
        "this file's probe to the implemented name"
    )


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
    async def post_monitoring_message(self, message: str) -> None:
        return None


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    """Thread-establishment nothing in this file exercises."""
    return "FAKE_THREAD_TS", None


async def _run_pass(collaborators: _Collaborators) -> Any:
    entry = _pass_entry()
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "handlers": collaborators.handlers,
        "results": collaborators.results,
        "record_outcome": collaborators.recorder,
        "read_product": collaborators.catalog,
        "deliver": collaborators.delivery,
        "backoff": _InertBackoff(),
        "notifier": _InertNotifier(),
        "establish_thread": _inert_establish_thread,
        "now": NOW,
    }
    accepted = set(inspect.signature(entry).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct "
        "`_run_pass` to the implemented collaborator names"
    )
    return await entry(**supplied)


# ---------------------------------------------------------------------------
# The retained-results read, reached through one correction point
# ---------------------------------------------------------------------------

_USE_CASE_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)


def _use_case() -> Any:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no retained-results read is exported from `launch.application` "
        f"under any of {_USE_CASE_NAMES} — correct `_USE_CASE_NAMES` to "
        "the implemented name"
    )


async def _read(results: _FakeResults) -> tuple[Any, ...]:
    use_case = _use_case()
    names = list(inspect.signature(use_case).parameters)
    arguments: dict[str, Any] = {}
    for name in names[1:]:
        if "scope" in name:
            arguments[name] = AccessScope.unrestricted()
        elif "product" in name or name in ("identifier", "id"):
            arguments[name] = PRODUCT_ID
    return tuple(await use_case(results, **arguments))


def _step_ids(records: tuple[Any, ...]) -> list[str]:
    found: list[str] = []
    for record in records:
        for name in ("step_id", "step", "step_identifier", "identifier"):
            if hasattr(record, name):
                found.append(str(getattr(record, name)))
                break
        else:  # pragma: no cover - a fixture correction, not a result
            pytest.fail(f"{type(record).__name__} exposes no step identifier")
    return found


# ---------------------------------------------------------------------------
# One pass, three steps
# ---------------------------------------------------------------------------


def _three_steps() -> _Collaborators:
    """One pass over three automated steps — the same three-branch shape
    `test_retained_record_boundary.py` uses, restated with `confirmer`:

    - a step naming a confirmer whose handler proposes a **terminal**
      outcome — held for a decision;
    - a step naming **no confirmer** whose handler proposes a terminal
      outcome — recorded at once;
    - a step naming a confirmer whose handler proposes a **non-terminal**
      outcome — recorded against the launch regardless of the confirmer.
    """
    from commerce_ops.launch.domain.launch_playbook import InProgress

    steps = (
        _automated(CONFIRMED_STEP, CONFIRMED_HANDLER, confirmer=ALICE),
        _automated(UNCONFIRMED_STEP, UNCONFIRMED_HANDLER, confirmer=None),
        _automated(NON_TERMINAL_STEP, NON_TERMINAL_HANDLER, confirmer=ALICE),
    )
    playbook = _playbook(*steps)
    handlers = _FakeHandlers(
        **{
            CONFIRMED_HANDLER: _ScriptedHandler(
                StepResolution(outcome=Satisfied, result=HELD_TEXT)
            ),
            UNCONFIRMED_HANDLER: _ScriptedHandler(
                StepResolution(outcome=Satisfied, result=RECORDED_TEXT)
            ),
            NON_TERMINAL_HANDLER: _ScriptedHandler(
                StepResolution(outcome=InProgress, result=PROGRESS_TEXT)
            ),
        }
    )
    return _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A result needing no confirmation is recorded at
# once
# ---------------------------------------------------------------------------


async def test_a_step_naming_no_confirmer_is_recorded_directly() -> None:
    """Scenario: An unconfirmed result is recorded directly (restated).

    WHEN a handler resolves a step that names no confirmer
    THEN the outcome is recorded against the launch with `automated`
    provenance, and no decision is requested.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECORDED_TEXT))
    playbook = _playbook(
        _automated(UNCONFIRMED_STEP, UNCONFIRMED_HANDLER, confirmer=None)
    )
    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{UNCONFIRMED_HANDLER: handler}),
    )

    await _run_pass(collaborators)

    call = collaborators.recorder.for_step(UNCONFIRMED_STEP)
    assert len(call) == 1
    assert call[0]["outcome"] is Satisfied
    assert call[0]["provenance"].source == "automated"
    assert collaborators.results.rows == []


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A result needing confirmation is held until a
# person decides
# ---------------------------------------------------------------------------


async def test_a_step_naming_a_confirmer_holds_a_terminal_result() -> None:
    """Scenario: A confirmable terminal result is held rather than
    recorded (restated).

    WHEN a handler proposes a terminal outcome for a step naming a
    confirmer
    THEN no outcome is recorded against the launch, and a pending result
    is stored carrying the proposed outcome, the produced text, the
    handler and the moment it was produced.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=HELD_TEXT))
    playbook = _playbook(_automated(CONFIRMED_STEP, CONFIRMED_HANDLER, confirmer=ALICE))
    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{CONFIRMED_HANDLER: handler}),
    )

    await _run_pass(collaborators)

    assert collaborators.recorder.for_step(CONFIRMED_STEP) == []
    (row,) = collaborators.results.rows
    assert row.proposed_outcome is Satisfied
    assert row.result_text == HELD_TEXT
    assert row.handler == CONFIRMED_HANDLER
    assert row.produced_at == NOW


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A non-terminal outcome is recorded directly and
# never held for a decision
# ---------------------------------------------------------------------------


async def test_a_non_terminal_outcome_is_recorded_whatever_confirmer_is_named() -> None:
    """Scenario: A non-terminal outcome on a confirmable step is recorded,
    not held (restated).

    WHEN a handler proposes `Blocked` with a reason for a step naming a
    confirmer
    THEN the outcome is recorded against the launch with `automated`
    provenance, no pending result is stored, and no decision is
    requested.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(reason="Waiting on a category answer."),
            result="Waiting on a category answer.",
        )
    )
    playbook = _playbook(_automated(CONFIRMED_STEP, CONFIRMED_HANDLER, confirmer=ALICE))
    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{CONFIRMED_HANDLER: handler}),
    )

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(CONFIRMED_STEP)
    assert len(calls) == 1
    assert isinstance(calls[0]["outcome"], Blocked)
    assert calls[0]["provenance"].source == "automated"
    assert collaborators.results.rows == []


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The retained record covers results held for a
# decision and nothing else
# ---------------------------------------------------------------------------


async def test_an_outcome_needing_no_confirmer_is_not_retained() -> None:
    """Scenario: An outcome needing no confirmation is not retained
    (restated).

    WHEN a handler resolves a step that names no confirmer, and every
    result retained for that product is read
    THEN nothing is answered for that step.
    """
    collaborators = _three_steps()

    await _run_pass(collaborators)
    answered = await _read(collaborators.results)

    assert collaborators.recorder.for_step(UNCONFIRMED_STEP), (
        "the pass never recorded an outcome for the step naming no "
        "confirmer, so this test does not reach the scenario"
    )
    assert UNCONFIRMED_STEP not in _step_ids(answered)
    assert CONFIRMED_STEP in _step_ids(answered)


async def test_a_non_terminal_outcome_is_not_retained_naming_a_confirmer() -> None:
    """Scenario: A non-terminal outcome is not retained (restated).

    WHEN a handler proposes a non-terminal outcome for a step naming a
    confirmer, and every result retained for that product is read
    THEN nothing is answered for that step.
    """
    collaborators = _three_steps()

    await _run_pass(collaborators)
    answered = await _read(collaborators.results)

    assert collaborators.recorder.for_step(NON_TERMINAL_STEP), (
        "the pass never recorded the non-terminal outcome, so this test "
        "does not reach the scenario"
    )
    assert NON_TERMINAL_STEP not in _step_ids(answered)
    assert _step_ids(answered) == [CONFIRMED_STEP]
