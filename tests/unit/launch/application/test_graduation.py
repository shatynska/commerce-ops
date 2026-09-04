"""Tests for graduation: opening the `graduated` gate stamps the catalog
product steady-state.

Derived from the delta spec:
openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md

Covers the ADDED requirement *Graduation stamps the catalog product
steady-state* — scenarios *Graduation stamps the product with the
approver's chosen posture* and *A rejected stage stamp leaves the advance
standing*. The third scenario (*A graduation approval without a posture
is rejected*) is a property of recording an approval on the aggregate and
lives in `tests/unit/launch/domain/test_launch_gate_advance.py`.

Only the application layer can observe these two scenarios: the stamp is
a cross-module call into `catalog` made by the `advance_gate` use case
after the advanced launch is persisted (`tasks.md` 3.3). This is the fast
mocked unit tier, so the collaborators are fakes and the catalog is
represented by a stage-stamping collaborator, not a database.

At the time of writing `commerce_ops.launch.application` exports no
launch use cases, so every test here is expected to fail on an absent
target (`ImportError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

## The interface under test does not exist yet, and its shape is INVENTED

Beyond the aggregate shape recorded in
`tests/unit/launch/domain/test_launch_run.py`, this file assumes, and
the manifest records as unresolved project questions:

- `advance_gate` exported from `commerce_ops.launch.application`
  (`tasks.md` 3.5 fixes the placement, not the call shape), taking its
  collaborators as arguments per this module's ports-and-adapters shape:
  `await advance_gate(launches=..., playbooks=..., stamp_steady_state=...,
  product_id=...)` returning the produced events. The launch store is
  async (`save` / `get_by_product_id`); the playbook port is
  `get(version)`.
- The stage-stamping collaborator is called as
  `await stamp(product_id, stage, confirmed_by=...)` — `change_stage`'s
  own shape minus the store, as
  `tests/integration/catalog/test_catalog_products.py` records it. If the
  implemented use case instead takes the catalog store and calls the real
  `catalog.application.change_stage` itself, replacing this collaborator
  with that wiring is a fixture correction.
- A catalog-rejected stamp is signalled by `StageTransitionError` (the
  real, existing catalog rejection type) and surfaces from the use case
  as `GraduationStampError`, importable from
  `commerce_ops.launch.application`, whose message names the manual
  catalog correction required.

Correcting any of those names or shapes is a fixture correction; what
must survive unweakened is what each test asserts: what stage is
stamped, with whose posture and confirmation, that the launch is
persisted before the stamp is attempted, and that a rejected stamp
leaves the advance standing with no stage changed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.catalog.domain.product import StageTransitionError
from commerce_ops.launch.application import (
    GraduationStampError,
    JournalOccurrence,
    advance_gate,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    LaunchGraduated,
    Provenance,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture, SteadyState
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import hold as _build_hold

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
APPROVED_AT: Final = datetime(2027, 7, 1, 10, 0, tzinfo=UTC)
APPROVER: Final = "Helen"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids a coherent playbook with
    unheld gates, so a steps-free fixture is no longer constructible.
    The walk satisfies these, restoring the premise that only the
    approval requirements remain."""
    return _build_hold(
        gate,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=0),
    )


def _playbook() -> LaunchPlaybook:
    """A coherent playbook with no metric conditions and only the holding
    fillers the gate-holding floor requires; once they are satisfied,
    only the approval requirements remain."""
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=steps)


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _launch_at_graduated(playbook: LaunchPlaybook) -> Launch:
    """A launch walked to `graduated` along the ordinary advance path,
    with the graduation approval (posture `Scale`) already recorded."""
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=Provenance(
                    source="automated",
                    who="hold-filler",
                    when=APPROVED_AT,
                    evidence="filler obligations satisfied by the walk",
                ),
            )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    for step in playbook.steps_for_gate("graduated"):
        launch.record_step_outcome(
            playbook,
            step_id=step.identifier,
            outcome=Satisfied,
            provenance=Provenance(
                source="automated",
                who="hold-filler",
                when=APPROVED_AT,
                evidence="filler obligations satisfied by the walk",
            ),
        )
    launch.approve_gate("graduated", _approval(posture=Posture.SCALE))
    return launch


class FakeLaunchStore:
    """In-memory launch store; appends ("save", ...) to the shared log."""

    def __init__(self, launch: Launch, log: list[tuple[str, ...]]) -> None:
        self._launches = {launch.product_id: launch}
        self._log = log

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._log.append(("save", launch.current_gate))
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        # Part of `LaunchStore` since `introduce-launch-briefing`; nothing
        # in this file enumerates, but the fake must satisfy the whole
        # port to stand in for it.
        return tuple(self._launches.values())


class FakePlaybooks:
    """Playbook port returning the one version the launch pinned."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


class FakeStamper:
    """Stage-stamping collaborator; records calls, optionally rejecting
    like `catalog`'s transition rules would."""

    def __init__(
        self,
        log: list[tuple[str, ...]],
        failure: Exception | None = None,
    ) -> None:
        self._log = log
        self._failure = failure
        self.calls: list[tuple[ProductId, object, str]] = []

    async def __call__(
        self, product_id: ProductId, stage: object, *, confirmed_by: str
    ) -> None:
        if self._failure is not None:
            raise self._failure
        self._log.append(("stamp",))
        self.calls.append((product_id, stage, confirmed_by))


class CollectingJournal:
    """The launch journal `add-launch-journal` made a required argument.

    Deliberately absent from the shared log: what this file's ordering
    assertion is about is that the stamp follows the save, and the
    journal append sits between them without being either. What the
    journal records is `test_launch_journal_appends.py`'s subject, not
    this file's.
    """

    def __init__(self) -> None:
        self.appended: list[JournalOccurrence] = []

    async def append(self, occurrence: JournalOccurrence) -> None:
        self.appended.append(occurrence)

    async def read(self, product_id: ProductId) -> tuple[JournalOccurrence, ...]:
        return tuple(self.appended)

    async def rollback(self) -> None:
        return None


async def test_graduation_stamps_the_product_with_the_approvers_chosen_posture() -> (
    None
):
    """Scenario: Graduation stamps the product with the approver's chosen
    posture.

    WHEN every blocking condition on `graduated` is satisfied for a
    product in a launching stage and an approval naming an approver and a
    posture is recorded, and the launch is advanced
    THEN a `LaunchGraduated` occurrence is reported and the catalog
    product's stage becomes steady state with the chosen posture,
    confirmed by that approver.
    """
    playbook = _playbook()
    log: list[tuple[str, ...]] = []
    launches = FakeLaunchStore(_launch_at_graduated(playbook), log)
    stamp = FakeStamper(log)

    events = await advance_gate(
        launches=launches,
        playbooks=FakePlaybooks(playbook),
        stamp_steady_state=stamp,
        product_id=PRODUCT_ID,
        journal=CollectingJournal(),
    )

    # SPECIFIED: a `LaunchGraduated` occurrence is reported.
    assert any(isinstance(event, LaunchGraduated) for event in events)
    # SPECIFIED: steady state with the chosen posture — the system never
    # chooses a posture itself — confirmed by that approver.
    ((stamped_id, stamped_stage, confirmed_by),) = stamp.calls
    assert stamped_id == PRODUCT_ID
    assert stamped_stage == SteadyState(posture=Posture.SCALE)
    assert confirmed_by == APPROVER
    # SPECIFIED by the requirement statement: the stamp is attempted only
    # after the advanced launch is persisted.
    kinds = [entry[0] for entry in log]
    assert "save" in kinds and "stamp" in kinds
    assert kinds.index("save") < kinds.index("stamp")


async def test_a_rejected_stage_stamp_leaves_the_advance_standing() -> None:
    """Scenario: A rejected stage stamp leaves the advance standing.

    WHEN the `graduated` gate opens for a product whose current stage
    does not permit a transition to steady state
    THEN the launch's current gate remains `graduated`, the product's
    stage is unchanged, and an error is reported naming the manual
    catalog correction required.
    """
    playbook = _playbook()
    log: list[tuple[str, ...]] = []
    launches = FakeLaunchStore(_launch_at_graduated(playbook), log)
    stamp = FakeStamper(
        log,
        failure=StageTransitionError(
            "no transition from the current stage to steady state"
        ),
    )

    # SPECIFIED: the failure is reported as an error. DERIVED mechanism:
    # `GraduationStampError` raised by the use case (see docstring).
    with pytest.raises(GraduationStampError) as caught:
        await advance_gate(
            launches=launches,
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=stamp,
            product_id=PRODUCT_ID,
            journal=CollectingJournal(),
        )

    # SPECIFIED: the error names the manual catalog correction required —
    # at minimum, which product's catalog record must be corrected by
    # hand. DERIVED: the exact wording beyond the product identifier.
    assert str(PRODUCT_ID) in str(caught.value)
    # SPECIFIED: the advance stands — the persisted launch remains at
    # `graduated`.
    stored = await launches.get_by_product_id(PRODUCT_ID)
    assert stored is not None
    assert stored.current_gate == "graduated"
    # SPECIFIED: no stage changes — the collaborator recorded no
    # successful stamp.
    assert stamp.calls == []
