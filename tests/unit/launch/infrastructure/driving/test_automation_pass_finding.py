"""The pass's handling of a handler's typed `finding` (`launch-step-automation`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/launch-step-automation/spec.md`

Covers every scenario stated over *a pass running* in this delta:

- MODIFIED requirement *A handler receives the step, the launch and the
  product, and attributes nothing* — all four scenarios, including the
  three whose wording is unchanged from the served spec (*The product is
  supplied, not fetched*, *A produced outcome is attributed to the
  handler*, *A handler cannot claim another source*) — written fresh here
  per this pass's own instructions for a MODIFIED requirement ("write new
  tests for the requirement's scenarios as revised, exactly as you would
  for ADDED"), even though `test_automation_pass.py` already covers the
  same three and is untouched by this change. That duplication is
  recorded, not hidden, in `test-manifest.md`.
- ADDED requirement *A handler MAY report a typed finding alongside its
  outcome* — both scenarios.
- ADDED requirement *A handler's supported finding is recorded
  independently of the step's own confirmation* — all five scenarios.

A separate file from `test_automation_pass.py`, per this pass's
additive-only rule: that file is not edited. Its fixtures are duplicated
here rather than imported, following the precedent
`test_subcategory_advisor_verdict.py` set for the same reason ("this pass
is additive only").

See `test-manifest.md` at the change root for the full accounting.

## Level

Every scenario above is stated over *a pass* — what it invokes, what it
records, what it stores. The pass function over in-memory doubles is the
smallest unit that can observe those, matching the level
`test_automation_pass.py` already established for this module.

## What is fixed, and what is INVENTED

Fixed by `design.md` and `tasks.md`:

- The pass invokes the recording capability "after the existing
  hazard-permission check on the proposed outcome passes ... where the
  handler's resolution carries a `Success` finding and a recording
  capability has been supplied for that step" (`tasks.md` 2.3).
- A recording-capability failure "report[s] the launch, step and handler
  (mirroring the existing handler-failure report) without recording any
  step outcome and without stopping the pass" (`tasks.md` 2.4) — read as
  the *stronger* of the two readings the scenario text alone would allow
  (see the module-level note on
  `test_a_recording_failure_does_not_stop_the_pass` below), since
  `tasks.md` states it explicitly and unambiguously.
- The recorder is wired "for `lp.listing.007` specifically — not for
  every step" (`tasks.md` 4.2), so the collaborator the pass accepts must
  be able to answer "is one supplied for *this* step".

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The pass's entry point name and call shape, and every collaborator
  `test_automation_pass.py` already invents (`_FakeCatalog`,
  `_FakeLaunches`, `_ScriptedHandler`, `_FakeHandlers`, `_FakeResults`,
  `_RecordingOutcomes`, `_FakeDelivery`, `_InertBackoff`,
  `_InertNotifier`, `now=`) — duplicated here unchanged from that file's
  own documented assumptions.
- The **new** collaborator carrying the per-step recording capability.
  `_RECORDER_KWARG_CANDIDATES` and `_recorder_kwarg()` are this file's own
  correction point for its keyword name; `_recorders_for(...)`'s shape — a
  mapping from step identifier to an async `(product_id, value) -> object`
  callable — is the single guess for *how* "supplied for that step
  specifically" is expressed. If the real pass instead takes one recorder
  plus a set of step identifiers it applies to, or resolves the mapping
  some other way, correcting `_run_pass`'s handling of `recorders=` is the
  fixture correction; what must survive is what each test asserts: when
  the recorder is called, with what, and when it is not.

What must survive any correction is what each test asserts: which
handlers are invoked, what is recorded, what is stored, what the recorder
is called with, and — for the several requirements stated in the
negative — what is *not*.

## Expected first-run state

Nothing under test exists in this shape: `StepResolution.finding` does
not exist (`tasks.md` 2.1) and the pass accepts no recording-capability
collaborator (`tasks.md` 2.2-2.4). Every test here is expected to fail —
most on `TypeError` from constructing a `StepResolution` with a `finding`
keyword the type does not yet declare, and the rest (once that much
exists) on the pass entry point rejecting an unrecognised collaborator
keyword. Per `ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Refused,
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
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

AUTOMATED_STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"
#: Naming a confirmer is what makes a step's automated result require
#: confirmation; there is no separate flag (`launch_playbook.StepDefinition`).
CONFIRMER: Final = "prs_01HQ8Z6M4A"

LAUNCH_DATE: Final = date(2027, 3, 2)
NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home & Kitchen > "
    "Home Decor."
)
SUB_CATEGORY_NODE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — duplicated from test_automation_pass.py
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


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
        assignees=("prs_01HQ8Z6M4A",),
        handler=None,
        provenance=None,
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _launch(playbook: LaunchPlaybook, product_id: ProductId = PRODUCT_ID) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — duplicated from test_automation_pass.py, plus _FakeRecorder
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
    def __init__(self, resolution: StepResolution) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        return self.resolution

    @property
    def invoked(self) -> bool:
        return bool(self.contexts)


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
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


class _FakeResults:
    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []

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
        finding: Any = None,
    ) -> _PendingRow:
        row = _PendingRow(
            product_id=product_id,
            step_id=step_id,
            handler=handler,
            proposed_outcome=proposed_outcome,
            result_text=result_text,
            produced_at=produced_at,
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
        target = self._row_of(row)
        target.delivered_at = when or NOW

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        return None

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        for candidate in self.rows:
            if candidate is row or getattr(row, "id", None) is candidate:
                return candidate
        raise AssertionError(f"unknown pending row {row!r}")

    @property
    def pending_rows(self) -> list[_PendingRow]:
        return [row for row in self.rows if row.state == "pending"]


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
    """Stands in for `SubCategoryRecorder` (`launch/application/ports.py`):
    `async def __call__(self, product_id: ProductId, sub_category: str) ->
    object`, recorded here as positional-or-keyword since the port's own
    calling convention is not fixed by any artifact.
    """

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[tuple[Any, str]] = []

    async def __call__(self, product_id: Any, sub_category: str) -> object:
        self.calls.append((product_id, sub_category))
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


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    """Thread-establishment nothing in this file exercises.

    Added by `thread-launch-slack-notifications`, which made it a required
    collaborator like `backoff` and `notifier` above -- inert here for the
    same reason `test_automation_pass.py`'s own double is: nothing below
    asserts on threading or tagging, that has its own file.
    """
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
# The pass, reached through its known correction points plus this file's own
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)

_RECORDER_KWARG_CANDIDATES: Final = (
    "recorders",
    "finding_recorders",
    "recording_capabilities",
    "sub_category_recorders",
    "record_finding",
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


def _recorder_kwarg(accepted: set[str]) -> str:
    """This file's own correction point: the keyword the pass entry point
    accepts for the per-step recording-capability collaborator.

    Fails loudly rather than silently supplying no recorder at all, which
    would make every scenario below observe "no recording capability
    supplied" regardless of what the test intended.
    """
    for name in _RECORDER_KWARG_CANDIDATES:
        if name in accepted:
            return name
    pytest.fail(
        "no recording-capability collaborator keyword found on the pass "
        f"entry point among {list(_RECORDER_KWARG_CANDIDATES)}; accepted "
        f"parameters are {sorted(accepted)} — correct this file's probe to "
        "the implemented keyword"
    )


async def _run_pass(
    collaborators: _Collaborators,
    *,
    now: datetime = NOW,
    recorders: dict[str, _FakeRecorder] | None = None,
) -> Any:
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
        "now": now,
    }
    accepted = set(inspect.signature(entry).parameters)
    if recorders is not None:
        supplied[_recorder_kwarg(accepted)] = recorders
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct "
        "`_run_pass` to the implemented collaborator names"
    )
    return await entry(**supplied)


def _setup(*steps: StepDefinition, handler: Any) -> _Collaborators:
    playbook = _playbook(*steps)
    return _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# Requirement: A handler receives the step, the launch and the product, and
# attributes nothing
# ---------------------------------------------------------------------------


async def test_the_product_is_supplied_not_fetched() -> None:
    """Scenario: The product is supplied, not fetched.

    Unchanged wording from the served spec; written fresh per this MODIFIED
    requirement, alongside `test_automation_pass.py`'s own unedited
    coverage of the same scenario.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    assert handler.contexts, "the handler was never invoked"
    context = handler.contexts[0]
    assert context.product.name == PRODUCT_NAME
    assert collaborators.catalog.reads == [PRODUCT_ID]


async def test_a_produced_outcome_is_attributed_to_the_handler() -> None:
    """Scenario: A produced outcome is attributed to the handler.

    Unchanged wording; written fresh for the same reason as above.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1
    provenance = calls[0]["provenance"]
    assert provenance.source == "automated"
    assert HANDLER_NAME in str(provenance.who)
    assert provenance.when == NOW
    assert RECOMMENDATION in str(provenance.evidence)


async def test_a_handler_cannot_claim_another_source_even_with_a_finding() -> None:
    """Scenario: A handler cannot claim another source.

    Written fresh for the same reason as the two tests above, and folding
    in a `Success` finding on the smuggling resolution — a finding does
    not open a second route for a handler to attribute its own work.
    """

    class _SmugglingResolution:
        outcome = Satisfied
        result = RECOMMENDATION
        finding = Success(value=SUB_CATEGORY_NODE, comment="demands and alternative")
        provenance = "a claimed source, if the contract had a place for one"

    class _SmugglingHandler:
        async def __call__(self, context: Any) -> Any:
            return _SmugglingResolution()

    collaborators = _setup(_automated(), handler=_SmugglingHandler())

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    if calls:
        provenance = calls[0]["provenance"]
        assert provenance.source == "automated"
        assert HANDLER_NAME in str(provenance.who)
    else:
        assert collaborators.results.rows == []


async def test_a_finding_changes_nothing_about_the_outcome_or_the_result() -> None:
    """Scenario: A finding changes nothing about the outcome or the result.

    WHEN a handler reports a typed finding alongside its outcome and result
    THEN the outcome is recorded, and the result is stored as evidence,
    exactly as they would be for a handler reporting no finding.
    """
    with_finding = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    without_finding = _ScriptedHandler(
        StepResolution(outcome=Satisfied, result=RECOMMENDATION)
    )

    with_collaborators = _setup(_automated(), handler=with_finding)
    without_collaborators = _setup(_automated(), handler=without_finding)

    await _run_pass(with_collaborators)
    await _run_pass(without_collaborators)

    with_calls = with_collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    without_calls = without_collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(with_calls) == len(without_calls) == 1
    assert with_calls[0]["outcome"] is without_calls[0]["outcome"]
    assert (
        with_calls[0]["provenance"].evidence == without_calls[0]["provenance"].evidence
    )


# ---------------------------------------------------------------------------
# Requirement: A handler MAY report a typed finding alongside its outcome
# ---------------------------------------------------------------------------


async def test_a_handler_reporting_no_finding_triggers_no_recording() -> None:
    """Scenario: A handler reports no finding by default.

    WHEN a handler that does not report a finding resolves a step
    THEN no finding is recorded anywhere on its behalf, and nothing about
    the step's resolution is affected by its absence.

    A recorder *is* supplied for the step here — the point is that its
    absence from the resolution, not the absence of a wired capability, is
    what keeps it silent.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: recorder})

    # SPECIFIED: no finding recorded on the handler's behalf.
    assert recorder.calls == []
    # SPECIFIED: the step's own resolution is unaffected by the absence.
    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1
    assert calls[0]["outcome"] is Satisfied


async def test_a_findings_presence_does_not_change_confirmation() -> None:
    """Scenario: A finding's presence does not change confirmation.

    WHEN a handler reports a finding alongside a terminal outcome for a
    step whose confirmation flag is true
    THEN the outcome is still held as a pending result exactly as it would
    be without a finding.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: _FakeRecorder()})

    # SPECIFIED: no outcome recorded against the launch — held, not recorded.
    assert collaborators.recorder.calls == []
    pending = collaborators.results.pending_rows
    assert len(pending) == 1
    row = pending[0]
    assert row.proposed_outcome is Satisfied
    assert row.result_text == RECOMMENDATION
    assert row.handler == HANDLER_NAME


# ---------------------------------------------------------------------------
# Requirement: A handler's supported finding is recorded independently of
# the step's own confirmation
# ---------------------------------------------------------------------------


async def test_a_supported_finding_is_recorded_immediately() -> None:
    """Scenario: A supported finding is recorded immediately.

    WHEN a handler reports a success finding for a step whose confirmation
    flag is true, and a recording capability is supplied for that step
    THEN the finding's value is recorded before any Slack decision is
    sought, and independent of what that decision later is.

    "Before any Slack decision is sought" is read here as "the recorder is
    invoked on this same pass, regardless of the outcome being merely held
    pending rather than recorded" — the delivery/decision loop is not
    driven to completion within a single pass in this test harness, so
    what is observable is that the recorder is called at all while the
    step's own outcome is only held.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: recorder})

    # SPECIFIED: the finding's value is recorded.
    assert recorder.calls == [(PRODUCT_ID, SUB_CATEGORY_NODE)]
    # SPECIFIED (this requirement's own text): "whether or not it is held
    # for a member's confirmation" — here it is held, not recorded.
    assert collaborators.recorder.calls == []
    assert len(collaborators.results.pending_rows) == 1


async def test_no_recording_capability_means_no_recording_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: No recording capability means no recording, silently.

    WHEN a handler reports a success finding for a step no recording
    capability has been supplied for
    THEN nothing is recorded on the finding's behalf, and this is not
    reported as a fault.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    collaborators = _setup(_automated(), handler=handler)

    with caplog.at_level(logging.WARNING):
        await _run_pass(collaborators, recorders={})

    # SPECIFIED: the step's own outcome is still recorded normally.
    assert len(collaborators.recorder.for_step(AUTOMATED_STEP_ID)) == 1
    # SPECIFIED: not reported as a fault.
    reported = _warnings(caplog)
    assert "record" not in reported.lower()


async def test_a_failure_finding_is_never_recorded_this_way() -> None:
    """Scenario: A failure finding is never recorded this way.

    WHEN a handler reports a finding that is a failure
    THEN no recording capability is invoked — a failure finding carries
    nothing to record.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked("no verdict could be read"),
            result="Could not choose a node: no verdict could be read.",
            finding=Failure(error="no verdict could be read"),
        )
    )
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: recorder})

    assert recorder.calls == []


async def test_an_impermissible_proposals_finding_is_never_recorded() -> None:
    """Scenario: An impermissible proposal's finding is never recorded.

    WHEN a handler proposes a terminal outcome the step's hazard does not
    permit, alongside a success finding
    THEN the recording capability is not invoked, exactly as no step
    outcome is recorded for that proposal.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Refused,
            result="declining this listing tactic",
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    collaborators = _setup(
        _automated(hazard=Hazard.COMPLIANCE_OBLIGATION, confirmer=CONFIRMER),
        handler=handler,
    )
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={AUTOMATED_STEP_ID: recorder})

    # SPECIFIED: the recording capability is not invoked.
    assert recorder.calls == []
    # SPECIFIED: exactly as no step outcome is recorded for that proposal.
    assert collaborators.recorder.calls == []
    assert collaborators.results.rows == []


async def test_a_recording_failure_does_not_stop_the_pass(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A recording failure does not stop the pass.

    WHEN invoking a step's recording capability fails
    THEN no step outcome is recorded as a result of that failure, the
    failure is reported naming the launch, the step and the handler, and
    the pass continues.

    Read here as the stronger of two possible readings of "no step outcome
    is recorded **as a result of that failure**" — `tasks.md` 2.4 states
    unambiguously that the whole proposal records nothing, "mirroring the
    existing handler-failure report", so this test asserts that the
    step's own outcome is *not* recorded this pass either, not only that
    the failure itself is not entered as an outcome. Recorded as a
    DERIVED reading of an ambiguous scenario sentence, resolved by the
    task's own more explicit wording.

    "The pass continues" is asserted through a second step on the same
    launch whose recorder does not fail, mirroring
    `test_automation_pass.py`'s own `test_a_failing_handler_leaves_the_step_untouched`
    pattern for the handler-failure case.
    """
    failing_recorder = _FakeRecorder(failing=True)
    healthy_recorder = _FakeRecorder()

    failing_step = _automated()
    healthy_step = _automated(
        identifier="listing.other-automated", handler="listing.other_handler"
    )
    playbook = _playbook(failing_step, healthy_step)
    launch = _launch(playbook, PRODUCT_ID)

    failing_handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result=RECOMMENDATION,
            finding=Success(value=SUB_CATEGORY_NODE, comment="demands"),
        )
    )
    healthy_handler = _ScriptedHandler(
        StepResolution(
            outcome=Satisfied,
            result="the second step's own result",
            finding=Success(value="a different node", comment="other demands"),
        )
    )
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(
            **{HANDLER_NAME: failing_handler, "listing.other_handler": healthy_handler}
        ),
    )

    with caplog.at_level(logging.WARNING):
        await _run_pass(
            collaborators,
            recorders={
                AUTOMATED_STEP_ID: failing_recorder,
                "listing.other-automated": healthy_recorder,
            },
        )

    # SPECIFIED: no step outcome is recorded as a result of the failure.
    assert collaborators.recorder.for_step(AUTOMATED_STEP_ID) == []
    assert [
        row for row in collaborators.results.rows if row.step_id == AUTOMATED_STEP_ID
    ] == []
    # SPECIFIED: the failure is reported naming the launch, step, handler.
    reported = _warnings(caplog)
    assert str(PRODUCT_ID) in reported
    assert AUTOMATED_STEP_ID in reported
    assert HANDLER_NAME in reported
    # SPECIFIED: the pass continues — the healthy step's recorder was
    # still reached.
    assert healthy_recorder.calls == [(PRODUCT_ID, "a different node")]
