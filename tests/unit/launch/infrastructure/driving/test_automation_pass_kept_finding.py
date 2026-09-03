"""What the pass keeps beside a recording when a handler's finding is
written (`launch-step-automation`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-step-automation/spec.md`

Covers, from its one ADDED requirement *A written finding is kept on the
recording it produced*, seven of its eleven scenarios — every one stated
over *a pass running*:

- A written finding is kept with the field it was written to (`tasks.md` 1.10)
- The field's name is not the handler's to supply (1.10)
- A non-terminal outcome keeps the finding it wrote (1.13)
- A finding for a step naming no sink is kept no more than it is written (1.14)
- A failure finding keeps nothing (1.14)
- A finding whose write did not succeed is not kept (1.14)
- The outcome and the evidence are unaffected by what is kept beside them (1.2)

together with the *storing* half of *A confirmable step's finding
survives until the result is accepted* (1.11) — the pass hands the
finding to the pending-result store. The accepting half, and the whole
scenario end to end, live in
`tests/unit/launch/test_confirmable_finding_end_to_end.py`.

The requirement's remaining three scenarios (*An unreadable stored
finding does not fail an acceptance*, *The value kept is the value as
written*, *A rejected result keeps no finding*) are stated over a
member's decision and live in
`tests/unit/launch/application/test_accepted_result_carried_finding.py`
(`tasks.md` 1.12, 1.18a, 1.18b).

A separate file from `test_automation_pass.py` and
`test_automation_pass_finding.py`, per this pass's additive-only rule:
neither is edited. Their fixtures are duplicated here rather than
imported, following the precedent those two files set for the same
reason. See `test-manifest.md` at the change root for the full accounting
of all 28 scenarios.

## Level

Every scenario above is stated over *a pass* — what it records, what it
stores, what it keeps beside either. The pass function over in-memory
doubles is the smallest unit that can observe those, matching the level
`test_automation_pass.py` established for this module.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- A sink registration is a frozen value carrying the recording callable,
  the storage field name and the wording an admin reads, spelled
  `FindingSink(record=..., field="sub_category", reads_as="Sub-category")`
  (`design.md`, *A sink registration carries its field's name and
  wording*; `tasks.md` 2.2, 2.3).
- The registration lives in the `recorders` mapping keyed by step
  identifier, which the pass already accepts (`design.md`, Context).
- The kept payload is `{"field": ..., "value": ..., "comment": ...}`,
  where `field` is the **sink's** and `value`/`comment` are the
  handler's (`tasks.md` 2.4, 2.5).
- Keeping follows the write: nothing is kept for a `Failure`, for a step
  with no sink, or where the write did not succeed (`tasks.md` 2.4).
- Where the pass holds a pending result, the finding is stored on it
  (`tasks.md` 2.6).

INVENTED, each with its correction point named below and recorded in
`test-manifest.md`:

- **Where `FindingSink` is exported from and how it is constructed.**
  `_sink()` probes `launch.application` and `launch.application.ports`
  for `_SINK_NAMES` and constructs positionally, then by keyword. It
  fails loudly rather than substituting a local stand-in, which would
  let these tests pass against a type that does not exist.
- **The keyword a finding travels under** onto a recording and onto the
  pending-result store: `_KEPT_KWARGS`, read off whatever the doubles
  were called with.
- Every collaborator `test_automation_pass.py` already invents
  (`_FakeCatalog`, `_FakeLaunches`, `_ScriptedHandler`, `_FakeHandlers`,
  `_FakeResults`, `_RecordingOutcomes`, `_FakeDelivery`, `_InertBackoff`,
  `_InertNotifier`, `now=`), duplicated unchanged from that file's own
  documented assumptions.

What must survive any correction is what each test asserts: what the
recording carries, what the pending-result store is handed, and — for the
several clauses stated in the negative — what is kept nowhere.

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
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    InProgress,
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
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.result import Failure, Success

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

AUTOMATED_STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"
CONFIRMER: Final = "prs_01HQ8Z6M4A"

LAUNCH_DATE: Final = date(2027, 3, 2)
NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home & Kitchen > "
    "Home Decor."
)
SUB_CATEGORY_NODE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
FINDING_COMMENT: Final = "Rejected alternative: Home & Kitchen > Home Decor."

#: SPECIFIED indirectly, and chosen so the assertion cannot pass by
#: accident: the sink's field name appears nowhere in the handler, its
#: name, its outcome, its result text or its finding. If it is kept, it
#: came from the registration.
SINK_FIELD: Final = "a_field_no_handler_here_names"
SINK_WORDING: Final = "A field no handler here names"

_ABSENT: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — duplicated from test_automation_pass_finding.py
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _automated(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": AUTOMATED_STEP_ID,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": HANDLER_NAME,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        discipline=_any_discipline(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-7),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(CONFIRMER,),
        handler=None,
        provenance=None,
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="kept-v1", gates=_gates(), steps=(*steps, *fillers))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — duplicated from test_automation_pass_finding.py
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    def __init__(self) -> None:
        self.reads: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.reads.append(product_id)
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
    def __init__(self, resolution: Any) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> Any:
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
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    extra: dict[str, Any] = field(default_factory=dict)
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


class _FakeResults:
    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []
        self.store_calls: list[dict[str, Any]] = []

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
        **extra: Any,
    ) -> _PendingRow:
        self.store_calls.append(
            {
                "product_id": product_id,
                "step_id": step_id,
                "handler": handler,
                "proposed_outcome": proposed_outcome,
                "result_text": result_text,
                "produced_at": produced_at,
                **extra,
            }
        )
        row = _PendingRow(
            product_id=product_id,
            step_id=step_id,
            handler=handler,
            proposed_outcome=proposed_outcome,
            result_text=result_text,
            produced_at=produced_at,
            extra=dict(extra),
        )
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        for candidate in self.rows:
            if candidate is row:
                candidate.delivered_at = when or NOW
                return

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        return None


class _RecordingOutcomes:
    """Stands in for `record_step_outcome`; only the keywords are read."""

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


class _FakeRecorder:
    """Stands in for the sink's recording callable."""

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[tuple[Any, Any]] = []

    async def __call__(self, product_id: Any, value: Any) -> object:
        self.calls.append((product_id, value))
        if self.failing:
            raise RuntimeError("simulated recording failure")
        return object()


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
    return "FAKE_THREAD_TS", None


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
# `FindingSink`, and the keyword a kept finding travels under
# ---------------------------------------------------------------------------

_SINK_MODULES: Final = (
    "commerce_ops.launch.application",
    "commerce_ops.launch.application.ports",
)
_SINK_NAMES: Final = ("FindingSink", "Sink", "FindingRegistration")

#: The keyword a kept finding is assumed to travel under, onto a recording
#: and onto the pending-result store alike.
_KEPT_KWARGS: Final = ("finding", "carried_finding", "kept_finding")


def _sink_class() -> Any:
    for module_name in _SINK_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:  # pragma: no cover - a module that must exist
            continue
        for name in _SINK_NAMES:
            found = getattr(module, name, None)
            if isinstance(found, type):
                return found
    pytest.fail(
        f"no sink registration type found under any of {list(_SINK_MODULES)} "
        f"as any of {list(_SINK_NAMES)}; `tasks.md` 2.2 adds one to "
        "`launch/application/ports.py` — correct `_SINK_NAMES` to the "
        "implemented name"
    )


def _sink(
    record: Any, field_name: str = SINK_FIELD, reads_as: Any = SINK_WORDING
) -> Any:
    """A sink registration carrying its recording callable, its storage
    field name and the wording an admin reads.

    INVENTED construction, and the correction point for it: positional in
    the order `design.md` writes, then by the keywords it names.
    """
    sink_type = _sink_class()
    try:
        if reads_as is _ABSENT:
            return sink_type(record, field_name)
        return sink_type(record, field_name, reads_as)
    except TypeError:
        parts: dict[str, Any] = {"record": record, "field": field_name}
        if reads_as is not _ABSENT:
            parts["reads_as"] = reads_as
        return sink_type(**parts)


def _kept(call: Mapping[str, Any]) -> Any:
    """What a call carried as a kept finding, or `_ABSENT` where it
    carried none.

    `_ABSENT` and `None` are kept apart on purpose: not passing a finding
    and passing an explicit `None` are two acts, and several clauses below
    are satisfied by either.
    """
    for name in _KEPT_KWARGS:
        if name in call:
            return call[name]
    return _ABSENT


def _parts(kept: Any) -> tuple[Any, Any, Any]:
    def _part(key: str) -> Any:
        if isinstance(kept, Mapping):
            return kept.get(key, _ABSENT)
        return getattr(kept, key, _ABSENT)

    comment = _part("comment")
    return _part("field"), _part("value"), _ABSENT if comment is None else comment


def _carries_nothing(kept: Any) -> bool:
    return kept is _ABSENT or kept is None


async def _run_pass(
    collaborators: _Collaborators,
    *,
    now: datetime = NOW,
    recorders: Mapping[str, Any] | None = None,
) -> None:
    await automation_pass.run_automation_pass(
        launches=collaborators.launches,
        playbook=collaborators.playbook,
        handlers=collaborators.handlers,
        results=collaborators.results,
        record_outcome=collaborators.recorder,
        read_product=collaborators.catalog,
        deliver=collaborators.delivery,
        backoff=_InertBackoff(),
        notifier=_InertNotifier(),
        establish_thread=_inert_establish_thread,
        now=now,
        recorders=dict(recorders or {}),
    )


def _setup(*steps: StepDefinition, handler: Any) -> _Collaborators:
    playbook = _playbook(*steps)
    return _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )


def _supported(value: Any = SUB_CATEGORY_NODE, comment: Any = FINDING_COMMENT) -> Any:
    return StepResolution(
        outcome=Satisfied,
        result=RECOMMENDATION,
        finding=Success(value=value, comment=comment),
    )


def _one_recording(collaborators: _Collaborators) -> Mapping[str, Any]:
    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1, f"the pass made {len(calls)} recordings, expected one"
    return calls[0]


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# Scenario: A written finding is kept with the field it was written to
# (tasks.md 1.10)
# ---------------------------------------------------------------------------


async def test_a_written_finding_is_kept_with_the_field_it_was_written_to() -> None:
    """WHEN a handler reports a supported finding for a step naming a sink
    and no confirmer, and the value is written THEN the recording the pass
    makes carries that sink's field name, the value written, and the
    finding's comment.
    """
    handler = _ScriptedHandler(_supported())
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    assert recorder.calls == [(PRODUCT_ID, SUB_CATEGORY_NODE)], (
        "the value was not written to its sink, so nothing could be kept"
    )
    call = _one_recording(collaborators)
    kept = _kept(call)
    assert not _carries_nothing(kept), "the recording carries no finding"
    field_name, value, comment = _parts(kept)
    assert field_name == SINK_FIELD
    assert value == SUB_CATEGORY_NODE
    assert comment == FINDING_COMMENT


async def test_the_field_name_is_the_sinks_and_never_the_handlers() -> None:
    """Scenario: The field's name is not the handler's to supply.

    The registration's field name appears nowhere in the handler, its
    registered name, its outcome, its result text or its finding — so a
    kept field equal to it can only have come from the registration. The
    handler additionally *offers* a field name of its own, which must be
    ignored: a handler reports a value and a comment, and where the value
    goes is not its business.
    """

    class _NamingResolution:
        outcome = Satisfied
        result = RECOMMENDATION
        finding = Success(value=SUB_CATEGORY_NODE, comment=FINDING_COMMENT)
        field = "a_field_the_handler_chose"
        finding_field = "a_field_the_handler_chose"

    class _NamingHandler:
        async def __call__(self, context: Any) -> Any:
            return _NamingResolution()

    collaborators = _setup(_automated(confirmer=None), handler=_NamingHandler())

    await _run_pass(
        collaborators, recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder())}
    )

    kept = _kept(_one_recording(collaborators))
    assert not _carries_nothing(kept)
    field_name, _value, _comment = _parts(kept)
    assert field_name == SINK_FIELD
    assert field_name != "a_field_the_handler_chose"
    assert "a_field_the_handler_chose" not in repr(kept)


async def test_two_sinks_keep_their_own_field_names() -> None:
    """The same rule, differentially: the same handler output kept under
    two different registrations keeps two different field names.

    An implementation that hard-coded `sub_category`, or took the name
    from the step identifier, passes the test above and fails this one.
    """
    first = _setup(_automated(confirmer=None), handler=_ScriptedHandler(_supported()))
    second = _setup(_automated(confirmer=None), handler=_ScriptedHandler(_supported()))

    await _run_pass(
        first,
        recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder(), "first_field", "First")},
    )
    await _run_pass(
        second,
        recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder(), "second_field", "Second")},
    )

    assert _parts(_kept(_one_recording(first)))[0] == "first_field"
    assert _parts(_kept(_one_recording(second)))[0] == "second_field"


# ---------------------------------------------------------------------------
# Scenario: A confirmable step's finding survives until the result is
# accepted — the storing half (tasks.md 1.11; `tasks.md` 2.6)
# ---------------------------------------------------------------------------


async def test_a_confirmable_terminal_proposal_stores_the_finding_with_it() -> None:
    """The pass's half of the scenario: held, with the finding stored
    alongside the proposed outcome and produced text.

    Without this hop the mechanism produces nothing for `lp.strategy.006`
    — the step the whole feature exists for (`design.md`, *The finding
    travels with the pending result*).
    """
    handler = _ScriptedHandler(_supported())
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    # SPECIFIED (existing behaviour, restated so the row is unambiguous):
    # a terminal outcome on a step naming a confirmer is held, not
    # recorded.
    assert collaborators.recorder.for_step(AUTOMATED_STEP_ID) == []
    assert len(collaborators.results.store_calls) == 1
    stored = collaborators.results.store_calls[0]
    assert stored["result_text"] == RECOMMENDATION

    kept = _kept(stored)
    assert not _carries_nothing(kept), (
        "the pending result was stored carrying no finding; the finding "
        "cannot survive the wait for a confirmer"
    )
    field_name, value, comment = _parts(kept)
    assert field_name == SINK_FIELD
    assert value == SUB_CATEGORY_NODE
    assert comment == FINDING_COMMENT


async def test_a_held_result_with_no_finding_stores_none() -> None:
    """The absent counterpart at the store, so the assertion above is
    falsifiable: a handler reporting no finding leaves the pending row
    carrying nothing."""
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)

    await _run_pass(
        collaborators, recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder())}
    )

    assert len(collaborators.results.store_calls) == 1
    assert _carries_nothing(_kept(collaborators.results.store_calls[0]))


# ---------------------------------------------------------------------------
# Scenario: A non-terminal outcome keeps the finding it wrote (tasks.md 1.13)
# ---------------------------------------------------------------------------


async def test_a_non_terminal_outcome_keeps_the_finding_it_wrote() -> None:
    """WHEN a handler writes a finding and proposes a non-terminal outcome
    THEN that outcome is recorded directly and carries the field name, the
    value and the comment.

    The step names a confirmer here on purpose: terminality, not the
    confirmer, decides what is held, and a non-terminal proposal is
    recorded directly even on a confirmable step. "Nothing about keeping a
    finding is conditional on the outcome being a satisfying one."
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=InProgress,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment=FINDING_COMMENT),
        )
    )
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    assert collaborators.results.store_calls == []
    call = _one_recording(collaborators)
    assert call["outcome"] is InProgress
    field_name, value, comment = _parts(_kept(call))
    assert field_name == SINK_FIELD
    assert value == SUB_CATEGORY_NODE
    assert comment == FINDING_COMMENT


# ---------------------------------------------------------------------------
# Keeping follows the write (tasks.md 1.14)
# ---------------------------------------------------------------------------


async def test_a_finding_for_a_step_naming_no_sink_is_kept_no_more_than_written() -> (
    None
):
    """Scenario: A finding for a step naming no sink is kept no more than
    it is written.

    THEN nothing is written and nothing is kept, and the outcome and
    evidence are recorded as they are for any handler reporting no
    finding.
    """
    handler = _ScriptedHandler(_supported())
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    unrelated = _FakeRecorder()

    await _run_pass(collaborators, recorders={"some.other.step": _sink(unrelated)})

    assert unrelated.calls == []
    call = _one_recording(collaborators)
    assert _carries_nothing(_kept(call)), (
        "a finding was kept for a step no sink was registered for"
    )
    assert call["outcome"] is Satisfied
    assert call["provenance"].evidence == RECOMMENDATION


async def test_a_failure_finding_keeps_nothing() -> None:
    """Scenario: A failure finding keeps nothing.

    THEN nothing is kept, exactly as nothing is written.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Failure(error="no confident node", comment="ambiguous listing"),
        )
    )
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    assert recorder.calls == []
    call = _one_recording(collaborators)
    assert _carries_nothing(_kept(call))
    assert call["outcome"] is Satisfied
    assert call["provenance"].evidence == RECOMMENDATION


async def test_a_handler_reporting_no_finding_keeps_nothing() -> None:
    """The commonest case, and the one every existing handler is in."""
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    assert recorder.calls == []
    assert _carries_nothing(_kept(_one_recording(collaborators)))


async def test_a_finding_whose_write_did_not_succeed_is_not_kept(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A finding whose write did not succeed is not kept.

    The existing pass already suppresses the step's own recording when the
    sink fails, so the strongest reading is asserted: nothing is recorded
    and nothing is stored — and, should a later implementation record
    anyway, no recording carries a finding.
    """
    caplog.set_level(logging.WARNING)
    handler = _ScriptedHandler(_supported())
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder(failing=True)

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _sink(recorder)})

    assert recorder.calls == [(PRODUCT_ID, SUB_CATEGORY_NODE)]
    for call in collaborators.recorder.for_step(AUTOMATED_STEP_ID):
        assert _carries_nothing(_kept(call)), (
            "a finding whose write failed was kept on a recording anyway"
        )
    for stored in collaborators.results.store_calls:
        assert _carries_nothing(_kept(stored))
    assert AUTOMATED_STEP_ID in _warnings(caplog)


# ---------------------------------------------------------------------------
# Scenario: The outcome and the evidence are unaffected by what is kept
# beside them (tasks.md 1.2)
# ---------------------------------------------------------------------------


async def test_the_outcome_and_evidence_are_unaffected_by_what_is_kept() -> None:
    """WHEN a handler reports a supported finding that is written and kept
    THEN the outcome recorded and the evidence stored are exactly what
    they would have been had the handler reported no finding at all.

    Stated differentially, because "exactly what they would have been" is
    a comparison.
    """
    keeping = _setup(_automated(confirmer=None), handler=_ScriptedHandler(_supported()))
    bare = _setup(
        _automated(confirmer=None),
        handler=_ScriptedHandler(
            StepResolution(outcome=Satisfied, result=RECOMMENDATION)
        ),
    )

    await _run_pass(keeping, recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder())})
    await _run_pass(bare, recorders={AUTOMATED_STEP_ID: _sink(_FakeRecorder())})

    kept_call = _one_recording(keeping)
    bare_call = _one_recording(bare)
    assert kept_call["outcome"] is bare_call["outcome"]
    assert kept_call["provenance"] == bare_call["provenance"]
    assert kept_call["provenance"].evidence == RECOMMENDATION
    # And the finding really was kept, so the equality above is not being
    # satisfied by the pass having kept nothing.
    assert not _carries_nothing(_kept(kept_call))
