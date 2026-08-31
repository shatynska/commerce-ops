"""A dependency never reaches the commitment machinery
(`launch-playbook`, MODIFIED *Gate sequence orders the launch*).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-playbook/spec.md`,
which amends the requirement so that `after_steps` — a second ordering
primitive — cannot be read as contradicting "Gates SHALL remain the only
primitive ordering the launch's commitments":

    `after_steps` cannot move a step to another gate, cannot add or
    remove a gate's obligations, and cannot make a gate open earlier or
    later given the same recorded outcomes.

Covers the requirement's **two new scenarios only**:

- *A dependency does not change when a gate opens*
- *A dependency does not move a step's obligations*

The requirement's three retained scenarios are covered elsewhere and are
not re-derived here: *Gates expose a stable order* and *Steps at a gate
are served in their authored order* by
`tests/unit/launch/domain/test_launch_playbook.py` and the serving-layer
tests, and *Steps at the same gate are unordered* by
`tests/unit/launch/domain/test_within_gate_order_commitment_neutrality.py`,
whose shape this file deliberately follows — the two files answer the
same question about two different orderings.

## Level

The domain. Both scenarios are about what the commitment machinery does
with a declaration: when `Launch.advance_gate` opens a gate, and what
`LaunchPlaybook.conditions_for_gate` names. A `LaunchPlaybook` and a
`Launch` over it are the smallest unit that can observe either, and no
I/O is involved. Fixtures follow `test_step_start_release.py` and
`test_within_gate_order_commitment_neutrality.py` in this directory.

## How "exactly as it would with no such declaration" is asserted

Both scenarios are stated as a comparison against an absent
declaration, so both build **two** playbooks differing in one field and
nothing else — a control whose steps declare no `after_steps`, and a
subject whose steps declare one — and compare the observations. The
comparison is of the two runs against each other; it fixes no wording,
no gate name and no condition ordering of its own, so it cannot be
satisfied by a machinery that is uniformly wrong, only by one that is
uniformly *indifferent* — which is what the requirement claims.

Each test additionally asserts that the declaration was doing something
in the subject run (the declaring steps are unreleased where the control
run's are released). Without that, both tests would pass against an
implementation that ignored `after_steps` altogether.

## INVENTED, with correction points

- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition` (the field names are SPECIFIED by the delta; the
  keyword form is not). Correction point: `_step`.
- `Launch.has_released(playbook, step)` as the release predicate — the
  delta names the concept, not the method. Correction point:
  `_released`.

## Expected first-run state

The target **already exists**: the change is implemented, and the
implementation deliberately leaves gate opening untouched by release.
Per `ai-toolkit:testing`, a first-run pass in the target-exists
situation is the expected result and establishes that the code behaves
as asserted — these two tests are regression guards against a later
edit letting a dependency leak into the commitment machinery, not
target-absent tests. A first-run *failure* here is a defect in the
implementation, not in the assertion: every assertion below is
SPECIFIED except the two spellings named above.

Baseline recorded before these tests were written, at the worktree root
on 2026-08-29: `uv run pytest tests/unit tests/agents` — 1650 passed, 0
failed; `uv run pytest tests/integration` — 1 failed, 125 passed, 1
skipped, the one failure being the pre-existing
`test_registered_handlers_activate_nothing.py::test_every_seeded_human_step_is_still_active_after_registration`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

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
    StepObligation,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    LaunchError,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

# SPECIFIED: the eight gates, in this order.
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

# SPECIFIED: the four gates that require confirmation to open.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

#: The gate under evaluation, and the one after it in the sequence.
GATE: Final = "listable"
NEXT_GATE: Final = "stock-ready"

#: The step every declaring step waits on. It is never resolved in any
#: run here — the whole point being that the gate opens regardless.
DEPENDENCY: Final = "listing.photos-approved"
#: A blocking step at `GATE` that declares the dependency.
BLOCKING_DECLARER: Final = "listing.title-conforms"
#: A non-blocking step at `GATE` that declares the same dependency.
NON_BLOCKING_DECLARER: Final = "listing.copy-drafted"

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 4, 15)

A_DISCIPLINE: Final = next(iter(Discipline))

#: One fixed product identifier, shared by the control run and the
#: subject run. It is fixed rather than generated because a refusal
#: names the product it refused for, and two runs that differed only in
#: a random identifier could not be compared for equality at all.
PRODUCT_ID: Final = ProductId("3f6c1b52-7d2a-4a1e-9c47-5b0f8e2d1a90")


# ---------------------------------------------------------------------------
# Builders
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
    """A valid step definition, overriding named attributes.

    INVENTED: `starts_at_gate` and `after_steps` as constructor
    keywords. Both are omitted from the baseline deliberately, so that
    a control step exercises the "author said nothing" defaults rather
    than restating them.
    """
    attributes: dict[str, Any] = {
        "identifier": BLOCKING_DECLARER,
        "name": "Work this step asks for",
        "description": None,
        "gate": GATE,
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, satisfying the gate-holding floor.

    It declares neither start field, so a filler can never be the reason
    anything in these tests is held back.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
    )


def _playbook(*, declaring: bool) -> LaunchPlaybook:
    """Two playbooks that differ in `after_steps` and in nothing else.

    `declaring=False` is the control the scenarios compare against: the
    same steps, at the same gates, with the same blocking flags, saying
    nothing about what they wait on.
    """
    waits: tuple[str, ...] = (DEPENDENCY,) if declaring else ()
    steps = (
        _step(
            identifier=DEPENDENCY,
            name="The work the declarers build on",
            gate=GATE,
            blocking=False,
        ),
        _step(
            identifier=BLOCKING_DECLARER, gate=GATE, blocking=True, after_steps=waits
        ),
        _step(
            identifier=NON_BLOCKING_DECLARER,
            name="Work that follows the photos",
            gate=GATE,
            blocking=False,
            after_steps=waits,
        ),
    )
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate != GATE)
    return LaunchPlaybook(
        version="dependency-neutrality-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _provenance() -> Provenance:
    return Provenance(
        source="attestation",
        who="Helen",
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=APPROVED_AT,
        posture=None,
    )


def _satisfy(launch: Launch, playbook: LaunchPlaybook, step_id: str) -> None:
    launch.record_step_outcome(
        playbook, step_id=step_id, outcome=Satisfied, provenance=_provenance()
    )


def _released(launch: Launch, playbook: LaunchPlaybook, step: StepDefinition) -> bool:
    """Whether `launch` has released `step`.

    INVENTED spelling, and this is the single correction point for it:
    the delta names the concept ("released") and fixes no method name.
    """
    return bool(launch.has_released(playbook, step))


def _advance_to_the_gate(playbook: LaunchPlaybook) -> Launch:
    """Walk a fresh launch to `GATE`, satisfying only the fillers.

    Nothing at `GATE` itself is resolved here — each test does that
    explicitly, so that what opened the gate is visible in the test.
    """
    launch, _ = Launch.start(
        product_id=PRODUCT_ID,
        playbook=playbook,
        launch_date=LAUNCH_DATE,
    )
    while launch.current_gate != GATE:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and launch.progress_for(step.identifier) is None:
                _satisfy(launch, playbook, step.identifier)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# Scenario: A dependency does not change when a gate opens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Opening:
    """Everything one run of the gate-opening sequence made observable."""

    unreleased_at_the_gate: tuple[str, ...]
    refusal_before_the_blocking_step_was_resolved: str
    gate_after_the_refusal: str
    gate_after_the_blocking_step_was_resolved: str
    dependency_outcome_recorded: bool


def _open_the_gate(playbook: LaunchPlaybook) -> _Opening:
    """Drive one playbook through `GATE` opening, recording what happened.

    The same sequence runs against the control and against the subject:
    walk to the gate, try to advance with the gate's blocking step still
    unresolved, resolve it, advance again.
    """
    launch = _advance_to_the_gate(playbook)

    unreleased = tuple(
        step.identifier
        for step in playbook.steps_for_gate(GATE)
        if not _released(launch, playbook, step)
    )

    with pytest.raises(LaunchError) as caught:
        launch.advance_gate(playbook)
    refusal = str(caught.value)
    gate_after_the_refusal = launch.current_gate

    _satisfy(launch, playbook, BLOCKING_DECLARER)
    launch.advance_gate(playbook)

    return _Opening(
        unreleased_at_the_gate=unreleased,
        refusal_before_the_blocking_step_was_resolved=refusal,
        gate_after_the_refusal=gate_after_the_refusal,
        gate_after_the_blocking_step_was_resolved=launch.current_gate,
        dependency_outcome_recorded=launch.progress_for(DEPENDENCY) is not None,
    )


def test_a_dependency_does_not_change_when_a_gate_opens() -> None:
    """Scenario: A dependency does not change when a gate opens.

    WHEN a gate's blocking steps are all resolved, and some step at that
    gate declares steps it waits on
    THEN the gate opens exactly as it would with no such declaration,
    the declaration having governed only when the work was asked for.

    Two launches run the identical sequence over two playbooks differing
    only in `after_steps`. In the declaring run the dependency is never
    resolved, so both declarers sit at the gate unreleased while it
    opens — which is the requirement's "whatever any step waited on
    before starting", made observable.
    """
    control = _open_the_gate(_playbook(declaring=False))
    declaring = _open_the_gate(_playbook(declaring=True))

    # SPECIFIED: the declaration governs "when work is asked for" — so in
    # the subject run it must actually be holding both declarers back,
    # and in the control run nothing at the gate is held. Without this
    # the comparison below would pass against an implementation that
    # ignored `after_steps` entirely.
    assert control.unreleased_at_the_gate == ()
    assert set(declaring.unreleased_at_the_gate) == {
        BLOCKING_DECLARER,
        NON_BLOCKING_DECLARER,
    }

    # SPECIFIED: "a gate opens exactly when its own blocking steps are
    # resolved and its conditions are met" — with the gate's one blocking
    # step unresolved it refuses, in both runs alike, and the declaration
    # changes neither that it refuses nor what it reports unmet. The
    # wording is not asserted; only that the two runs agree on it.
    assert (
        declaring.refusal_before_the_blocking_step_was_resolved
        == control.refusal_before_the_blocking_step_was_resolved
    )
    assert BLOCKING_DECLARER in control.refusal_before_the_blocking_step_was_resolved
    assert declaring.gate_after_the_refusal == control.gate_after_the_refusal == GATE

    # SPECIFIED: `after_steps` "cannot make a gate open earlier or later
    # given the same recorded outcomes" — the same outcomes were recorded
    # in both runs, and the gate opens in both.
    assert (
        declaring.gate_after_the_blocking_step_was_resolved
        == control.gate_after_the_blocking_step_was_resolved
        == NEXT_GATE
    )

    # SPECIFIED: the gate opened over an unresolved dependency in both
    # runs — nothing was resolved to make the declaring run catch up.
    assert declaring.dependency_outcome_recorded is False
    assert control.dependency_outcome_recorded is False


# ---------------------------------------------------------------------------
# Scenario: A dependency does not move a step's obligations
# ---------------------------------------------------------------------------


def _gate_of_each_step(playbook: LaunchPlaybook) -> dict[str, str]:
    """Which gate each step is served under, read gate by gate.

    Read through `steps_for_gate` rather than off the definitions, so
    that a served set placing a step under a gate other than the one it
    declares would be caught rather than assumed away.
    """
    return {
        step.identifier: gate
        for gate in SPECIFIED_GATE_ORDER
        for step in playbook.steps_for_gate(gate)
    }


def _obligations_of_each_gate(playbook: LaunchPlaybook) -> dict[str, tuple[str, ...]]:
    """The step identifiers each gate's conditions name, gate by gate."""
    return {
        gate: tuple(
            sorted(
                condition.step_id
                for condition in playbook.conditions_for_gate(gate)
                if isinstance(condition, StepObligation)
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    }


def _condition_counts(playbook: LaunchPlaybook) -> dict[str, int]:
    """How many conditions of any kind each gate carries."""
    return {
        gate: len(list(playbook.conditions_for_gate(gate)))
        for gate in SPECIFIED_GATE_ORDER
    }


def test_a_dependency_does_not_move_a_steps_obligations() -> None:
    """Scenario: A dependency does not move a step's obligations.

    WHEN a step declaring steps it waits on is read from the served
    playbook
    THEN it belongs to the gate it declares, and that gate's conditions
    name it exactly as they would without the declaration.

    Read across every gate rather than at `listable` alone: "cannot move
    a step to another gate" and "cannot add or remove a gate's
    obligations" are both claims about the whole set, and a declaration
    that relocated a step would show up as an obligation appearing
    somewhere else, which a single-gate read would miss.
    """
    control = _playbook(declaring=False)
    declaring = _playbook(declaring=True)

    # The subject really does declare what the scenario is about, read
    # back off the served definition.
    (declared,) = [
        step
        for step in declaring.steps_for_gate(GATE)
        if step.identifier == BLOCKING_DECLARER
    ]
    assert tuple(declared.after_steps) == (DEPENDENCY,)

    # SPECIFIED: "it belongs to the gate it declares" — the declaring
    # step is served under its own gate, and under no other.
    assert declared.gate == GATE
    assert _gate_of_each_step(declaring)[BLOCKING_DECLARER] == GATE
    assert _gate_of_each_step(declaring)[NON_BLOCKING_DECLARER] == GATE

    # SPECIFIED: `after_steps` "cannot move a step to another gate" —
    # every step is served under exactly the gate it is under in the
    # control set.
    assert _gate_of_each_step(declaring) == _gate_of_each_step(control)

    # SPECIFIED: "that gate's conditions name it exactly as they would
    # without the declaration", and `after_steps` "cannot add or remove
    # a gate's obligations" — the obligations are identical gate for
    # gate, and the gate under test names its blocking step and nothing
    # else it did not name before.
    assert _obligations_of_each_gate(declaring) == _obligations_of_each_gate(control)
    assert _obligations_of_each_gate(declaring)[GATE] == (BLOCKING_DECLARER,)

    # SPECIFIED: nor does a declaration add a condition of some other
    # kind — the count of conditions of every kind matches gate for gate,
    # so an obligation cannot have been swapped for something else.
    assert _condition_counts(declaring) == _condition_counts(control)

    # SPECIFIED: the dependency is a non-blocking step, so it is named by
    # no gate's conditions — a declaration naming it does not make it one
    # of the depending step's gate's obligations.
    assert all(
        DEPENDENCY not in obligations
        for obligations in _obligations_of_each_gate(declaring).values()
    )
