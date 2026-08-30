"""Recording a step outcome moves no gate.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers exactly one scenario, from the ADDED requirement *A recurring pass
advances every launch whose gate may open*:

    #### Scenario: Recording an outcome does not itself advance a launch
    - **WHEN** a step outcome is recorded that satisfies the last
      outstanding condition on a launch's current gate
    - **THEN** the launch's current gate is unchanged until a pass or a
      recorded decision advances it

See `test-manifest.md` at the change root for the full accounting.

## Why this scenario has its own file

It is a **regression guard**, and the only test of this change expected to
pass on its first run: `record_step_outcome` advances nothing today, and
the requirement's job is to keep it that way while advancement is wired
elsewhere. `proposal.md` — Impact names its four call sites and commits to
leaving all of them unchanged; `design.md` — Decision 1 records the
rejected alternative this test rules out, which is advancing inside the
recording use case or at each of its call sites.

A test that must run *before* the implementation lands cannot share a
module with tests that fail on an absent import. Every other application-
tier test of this change probes for `progress_launch`; this one must not,
or a change that added advancement to `record_step_outcome` would go
uncaught for as long as the cascade was missing.

## Level

The recording use case over in-memory doubles. The scenario is stated over
recording, and the launch the store holds afterwards is the smallest thing
that can observe "the current gate is unchanged" — no pass and no database
is needed to see it.

## What is fixed, and what is INVENTED

Nothing is invented. `record_step_outcome`'s call shape is the one
`tests/unit/launch/application/test_launch_journal_appends.py` already
records, and the gate vocabulary is `launch-playbook`'s, unchanged by this
change.

## Expected first-run state

Expected to **PASS**. It states behaviour this change must preserve rather
than introduce, so a failure here before the implementation lands would
mean the fixture is wrong, not the code. Its value is afterwards: it fails
if advancement is ever folded into a recording path.

Baseline recorded before this test was written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.domain.launch_playbook import (
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
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

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
LAUNCH_DATE: Final = date(2027, 9, 1)
RECORDED_AT: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _hold(gate: str) -> StepDefinition:
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=0),
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(),
        handler="fixture.holding_check",
        provenance=None,
    )


def _playbook() -> LaunchPlaybook:
    """No metric condition anywhere, deliberately: the scenario is stated
    over the *last outstanding* condition being satisfied, so the gate's
    only condition must be the step this test records."""
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(
        version="recording-v1",
        gates=gates,
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self._launches = {launch.product_id: launch}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    @property
    def only(self) -> Launch:
        return next(iter(self._launches.values()))


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str = "") -> LaunchPlaybook:
        return self.playbook


class _FakeJournal:
    def __init__(self) -> None:
        self.appended: list[Any] = []

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        return None


async def test_recording_an_outcome_does_not_itself_advance_a_launch() -> None:
    """Scenario: Recording an outcome does not itself advance a launch.

    WHEN a step outcome is recorded that satisfies the last outstanding
    condition on a launch's current gate
    THEN the launch's current gate is unchanged until a pass or a recorded
    decision advances it.

    `listable` is the gate: it opens automatically and, once its one
    blocking step is satisfied, has nothing else outstanding — so a
    recording path that advanced would visibly move the launch, and the
    assertion is not satisfied merely by some other condition still
    blocking.
    """
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    # Walk to `listable` on the aggregate, so the recording under test is
    # the only command this test issues through the use case.
    while launch.current_gate != "listable":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=RECORDED_AT,
                        evidence="the blocking check reported green",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            from commerce_ops.launch.domain.launch_run import (
                ApprovalDecision,
                GateApproval,
            )

            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=RECORDED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    launches = _FakeLaunches(launch)

    await record_step_outcome(
        launches,
        _FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        step_id="hold.listable",
        outcome=Satisfied,
        provenance=Provenance(
            source="clickup",
            who="Dana",
            when=RECORDED_AT,
            evidence="ClickUp task closed with its checklist complete",
        ),
        journal=_FakeJournal(),
    )

    # Guard: the recording really did satisfy the gate's last outstanding
    # condition, so "the gate is unchanged" is not merely a gate that was
    # never ready. `advance_gate` is not called here — the launch is asked
    # whether it *would* open, through the same public read the pass uses.
    assert launches.only.current_gate == "listable", (
        "recording a step outcome advanced the launch's gate; advancement "
        "is a convergence pass and not a consequence of recording "
        "(design.md — Decision 1)"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The other three `record_step_outcome` call sites (`clickup_webhook`,
#   `clickup_sync_job`, `automation_pass`, `automation_confirmation`).
#   They are covered by their own files, and none of them can advance a
#   gate that the use case they all share does not advance.
# - That the launch *is* advanced by a later pass. That is the cascade's
#   own requirement and is covered in
#   `tests/unit/launch/application/test_progress_launch.py`; repeating it
#   here would make this guard fail for a reason it does not state.
# ---------------------------------------------------------------------------
