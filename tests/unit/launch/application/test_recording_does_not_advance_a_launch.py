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

from datetime import UTC, date, datetime
from typing import Any, Final, cast

import pytest

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeLaunches
from tests.support.fakes import FakePlaybooks as _FakePlaybooks
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
LAUNCH_DATE: Final = date(2027, 9, 1)
RECORDED_AT: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=0),
    )


def _playbook() -> LaunchPlaybook:
    """No metric condition anywhere, deliberately: the scenario is stated
    over the *last outstanding* condition being satisfied, so the gate's
    only condition must be the step this test records."""
    return _build_playbook(
        version="recording-v1",
        filler=_hold,
    )


class _FakeLaunches(FakeLaunches):
    """The shared launch store, adapted: this file reads it through its
    own helper. The helpers are rewritten against the shared list, since
    every local kept its launches in a dict keyed by identifier."""

    def __init__(self, launch: Launch) -> None:
        super().__init__(launch)

    @property
    def only(self) -> Launch:
        return cast(Launch, self.launches[0])


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
# - The three `record_step_outcome` call sites still fully bound by this
#   requirement's SHALL NOT (`clickup_sync_job`, `automation_pass`,
#   `automation_confirmation`). They are covered by their own files, and
#   none of them can advance a gate that the use case they all share does
#   not advance.
# - `clickup_webhook`, which `advance-gates-from-clickup-webhook` carves a
#   named exception for: it MAY also trigger the same advance-and-ask
#   cascade the pass runs, off its own response path, immediately after
#   recording. That the recording itself still advances nothing is
#   asserted above, same as for every call site; the cascade the webhook
#   goes on to trigger is covered in
#   `tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py`
#   and `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py`,
#   and its exclusivity to this one call site in
#   `tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py`.
# - That the launch *is* advanced by a later pass. That is the cascade's
#   own requirement and is covered in
#   `tests/unit/launch/application/test_progress_launch.py`; repeating it
#   here would make this guard fail for a reason it does not state.
# ---------------------------------------------------------------------------
