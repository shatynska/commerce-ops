"""The pass carrying the compliance screen's finding to its sink, with an
**empty sequence** as the value (`launch-step-automation`,
`launch-instance`, exercised for this change's second sink).

Derived from the delta specs of the change `screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/compliance-screen/spec.md`

## What this file covers, and what it does not

**`launch-step-automation` and `launch-instance` take no delta in this
change.** `design.md`'s Goals is explicit that they do not, and calls that
"the check that this change is the consumer the last one was built for
rather than an extension of it". So no scenario here is SPECIFIED by a
scenario in *those* capabilities' deltas.

What it does cover:

- **`tasks.md` 1.15 and 1.16**, DERIVED: the generic finding path already
  has coverage; these rows pin the **empty sequence** case for the second
  sink, which `lp.listing.007` — the only sink today, whose value is a
  string — never exercised. A read path treating a falsy value as "no
  finding" collapses it on the launch record while the catalog side stays
  correct, which is why this cannot be inferred from the catalog tests.
- From `compliance-screen`'s ADDED requirement *The screen reports what it
  established as a typed finding*, the pass-side half of one scenario:
  **A prior flag survives a later screening that establishes nothing** —
  asserted here as "the recorder is not invoked at all" (`tasks.md`
  1.10), which is what makes the product's value unchanged rather than
  re-written with the same content. The handler-side half is in
  `tests/agents/step_handlers/strategy/test_compliance_screen_hazard_finding.py`.

A **separate file** from `test_automation_pass_kept_finding.py` and
`test_automation_pass_finding.py`, per this pass's additive-only rule:
neither is edited, and their fixtures are duplicated here rather than
imported, following the precedent both set for the same reason.

## Level

The pass function over in-memory doubles — the level
`test_automation_pass.py` established for this module, and the smallest
that can observe what the pass writes, what it stores, and what it does
*not* invoke.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 5.3: a second `FindingSink` registered for
`lp.strategy.006` with `field="hazard_categories"` and
`reads_as="Hazard categories"`.

Fixed by `launch-instance`, unchanged and re-exercised: a finding whose
value is empty is a present finding, distinguishable from a recording
carrying none.

INVENTED, inherited from the two sibling files' own documented
assumptions and recorded in `test-manifest.md`: the sink type's location
and construction (`_sink`), the keyword a kept finding travels under
(`_KEPT_KWARGS`), the pass entry point's collaborator names, and the
doubles.

## Expected first-run state

The pass, the sink type and the kept-finding path all exist
(`separate-the-result-from-the-comment`), and this change adds no
mechanism to them — so these tests are expected to **pass on first run**,
in the target-exists situation `ai-toolkit:testing` describes. They are
regression guards on the generic mechanism's behaviour for a value type
it has never carried, and the row that fails if a later author
"simplifies" the write with a truthiness test.

Recorded here rather than hidden: a first-run pass in this situation is
the expected result, not evidence the rows are worthless.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
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
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.result import Success
from tests.support.fakes import FakeHandlers as _FakeHandlers
from tests.support.fakes import InertBackoff as _InertBackoff
from tests.support.fixtures import LAUNCH_DATE, PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.values import CatalogProduct as _CatalogProduct

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
SCREEN_STEP_ID: Final = "lp.strategy.006"
HANDLER_NAME: Final = "strategy.compliance_screen"
CONFIRMER: Final = "prs_01HQ8Z6M4A"

NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

SCREEN_TEXT: Final = (
    "Verdict: clear. Screened against the FBA-prohibited hazmat list and "
    "high-compliance categories. None of them applies to this product."
)
FINDING_COMMENT: Final = "None of the named categories applies to this product."

#: `tasks.md` 5.3 fixes both.
SINK_FIELD: Final = "hazard_categories"
SINK_WORDING: Final = "Hazard categories"

FLAGGED_MEMBERS: Final = ["supplements", "medical devices"]

_ABSENT: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — duplicated from test_automation_pass_kept_finding.py
# ---------------------------------------------------------------------------


def _automated(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": SCREEN_STEP_ID,
        "name": "Screen for prohibited and high-compliance categories",
        "description": None,
        "gate": "listable",
        "discipline": Discipline("strategy"),
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
    return _build_hold(
        gate,
        assignees=(CONFIRMER,),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    return _build_playbook(
        *steps,
        version="hazard-v1",
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — duplicated
# ---------------------------------------------------------------------------


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
    """Stands in for the sink's recording callable — the catalog use case
    partially applied over its store."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    async def __call__(self, product_id: Any, value: Any) -> object:
        self.calls.append((product_id, value))
        return object()


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
# The sink, and the keyword a kept finding travels under — inherited
# ---------------------------------------------------------------------------

_SINK_MODULES: Final = (
    "commerce_ops.launch.application",
    "commerce_ops.launch.application.ports",
)
_SINK_NAMES: Final = ("FindingSink", "Sink", "FindingRegistration")
_KEPT_KWARGS: Final = ("finding", "carried_finding", "kept_finding")


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
        f"as any of {list(_SINK_NAMES)} — correct `_SINK_NAMES`"
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


async def _run_pass(
    collaborators: _Collaborators,
    *,
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
        now=NOW,
        recorders=dict(recorders or {}),
    )


def _setup(*steps: StepDefinition, handler: Any) -> _Collaborators:
    playbook = _playbook(*steps)
    return _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )


def _resolution(value: Any) -> Any:
    return StepResolution(
        outcome=Satisfied,
        result=SCREEN_TEXT,
        finding=Success(value=value, comment=FINDING_COMMENT),
    )


def _one_recording(collaborators: _Collaborators) -> Mapping[str, Any]:
    calls = collaborators.recorder.for_step(SCREEN_STEP_ID)
    assert len(calls) == 1, f"the pass made {len(calls)} recordings, expected one"
    return calls[0]


def _one_stored(collaborators: _Collaborators) -> Mapping[str, Any]:
    calls = [
        call
        for call in collaborators.results.store_calls
        if call.get("step_id") == SCREEN_STEP_ID
    ]
    assert len(calls) == 1, f"the pass stored {len(calls)} rows, expected one"
    return calls[0]


# ---------------------------------------------------------------------------
# `tasks.md` 1.15 — the empty sequence reaches the sink as an empty
# sequence
# ---------------------------------------------------------------------------


async def test_an_empty_sequence_finding_reaches_the_recorder_as_an_empty_sequence() -> (
    None
):
    """DERIVED from `tasks.md` 1.15, not from a `#### Scenario:`.

    The generic write path has coverage for a string value; this row pins
    the empty-sequence case for the second sink. An implementation that
    guarded the write with `if value:` — an entirely natural-looking
    edit — skips it silently, and the product then reports the question as
    open after a screening answered it.

    Asserted as the *identity* of what the recorder was called with: not
    merely that a call happened, and not by truthiness.
    """
    handler = _ScriptedHandler(_resolution([]))
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={SCREEN_STEP_ID: _sink(recorder)})

    assert len(recorder.calls) == 1, (
        "the pass did not write the empty set to its sink; a screening that "
        "found the product clear recorded nothing, so the product still "
        f"reports the question as open. Calls: {recorder.calls!r}"
    )
    product_id, value = recorder.calls[0]
    assert product_id == PRODUCT_ID
    assert value is not None, "the pass wrote `None` for an empty sequence"
    assert not isinstance(value, str), (
        f"the pass wrote the string {value!r} rather than a sequence"
    )
    assert list(value) == []


async def test_a_flagged_finding_reaches_the_recorder_with_every_member() -> None:
    """The other half of the same row: a non-empty sequence arrives whole.

    Paired with the empty case so that an implementation writing only
    truthy values passes one and fails the other, rather than looking
    correct on the case that happens to be exercised.
    """
    handler = _ScriptedHandler(_resolution(list(FLAGGED_MEMBERS)))
    collaborators = _setup(_automated(confirmer=None), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={SCREEN_STEP_ID: _sink(recorder)})

    assert len(recorder.calls) == 1
    _product_id, value = recorder.calls[0]
    assert list(value) == FLAGGED_MEMBERS


# ---------------------------------------------------------------------------
# `tasks.md` 1.16 — a stored/kept finding whose value is an empty sequence
# reads back as present-and-empty
# ---------------------------------------------------------------------------


async def test_an_empty_sequence_finding_is_kept_as_present_and_empty() -> None:
    """DERIVED from `tasks.md` 1.16 and `launch-instance`'s standing
    guarantee that an absent finding is distinguishable from an empty
    value — re-exercised here for the first **non-scalar** consumer of it.

    Asserted on the recording the pass makes: the finding is present, and
    its value is an empty sequence rather than absent. A read path
    treating a falsy value as "no finding" collapses it on the launch
    record while the catalog side stays correct, so this cannot be
    inferred from the catalog tests.
    """
    handler = _ScriptedHandler(_resolution([]))
    collaborators = _setup(_automated(confirmer=None), handler=handler)

    await _run_pass(collaborators, recorders={SCREEN_STEP_ID: _sink(_FakeRecorder())})

    kept = _kept(_one_recording(collaborators))
    assert not _carries_nothing(kept), (
        "the recording carries no finding for a value that was written; an "
        "empty value is a present finding, distinct from a recording "
        "carrying none"
    )
    field_name, value, comment = _parts(kept)
    assert field_name == SINK_FIELD
    assert value is not None and not isinstance(value, str)
    assert list(value) == []
    assert comment == FINDING_COMMENT


async def test_a_kept_empty_finding_is_distinguishable_from_no_finding_at_all() -> None:
    """The distinctness clause, asserted differentially over two runs of
    the same pass.

    One handler reports a finding whose value is empty; the other reports
    none at all. Comparing the two recordings is what discriminates
    against an implementation that reports both as "nothing kept" —
    asserting each against a literal does not.
    """
    empty = _setup(
        _automated(confirmer=None), handler=_ScriptedHandler(_resolution([]))
    )
    none_at_all = _setup(
        _automated(confirmer=None),
        handler=_ScriptedHandler(StepResolution(outcome=Satisfied, result=SCREEN_TEXT)),
    )

    await _run_pass(empty, recorders={SCREEN_STEP_ID: _sink(_FakeRecorder())})
    await _run_pass(none_at_all, recorders={SCREEN_STEP_ID: _sink(_FakeRecorder())})

    assert not _carries_nothing(_kept(_one_recording(empty)))
    assert _carries_nothing(_kept(_one_recording(none_at_all)))


async def test_a_confirmable_screening_stores_its_empty_finding_with_the_result() -> (
    None
):
    """`lp.strategy.006` names a confirmer, so its terminal proposal is
    *held* rather than recorded — and the finding travels with the pending
    result.

    DERIVED from `tasks.md` 1.15's "keeps the finding on what it stores",
    and the shape this change's step actually runs in: the sibling file
    exercises the same path for a step with no confirmer, which is
    `lp.listing.007`'s shape and not this one's.
    """
    handler = _ScriptedHandler(_resolution([]))
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={SCREEN_STEP_ID: _sink(recorder)})

    # Held, not recorded: existing behaviour, restated so the row is
    # unambiguous.
    assert collaborators.recorder.for_step(SCREEN_STEP_ID) == []
    # The write happens anyway — "independently of the step's own
    # confirmation".
    assert len(recorder.calls) == 1
    assert list(recorder.calls[0][1]) == []

    stored = _kept(_one_stored(collaborators))
    assert not _carries_nothing(stored), (
        "the pending result stores no finding, so an acceptance has nothing "
        "to carry onto the recording it makes"
    )
    _field, value, _comment = _parts(stored)
    assert list(value) == []


# ---------------------------------------------------------------------------
# `compliance-screen` — Scenario: A prior flag survives a later screening
# that establishes nothing (the pass-side half; `tasks.md` 1.10)
# ---------------------------------------------------------------------------


async def test_a_screening_that_establishes_nothing_invokes_no_recorder() -> None:
    """Scenario: A prior flag survives a later screening that establishes
    nothing — asserted against the recorder, which must not be invoked at
    all.

    The screen reports no finding, so the pass has nothing to write; the
    product's recorded categories are unchanged because *nothing reached
    them*, which is a stronger and more directly observable fact than
    re-reading a value.

    A non-terminal outcome is used, since that is what every route
    establishing nothing proposes.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(reason="the screen could not settle the question"),
            result=SCREEN_TEXT,
        )
    )
    collaborators = _setup(_automated(confirmer=CONFIRMER), handler=handler)
    recorder = _FakeRecorder()

    await _run_pass(collaborators, recorders={SCREEN_STEP_ID: _sink(recorder)})

    assert recorder.calls == [], (
        "a screening that established nothing wrote to the product's hazard "
        f"categories anyway: {recorder.calls!r} — a flag an earlier "
        "screening recorded would be replaced"
    )
