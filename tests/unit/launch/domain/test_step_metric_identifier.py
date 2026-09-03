"""A step definition's optional metric identifier.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-playbook/spec.md`

Covers the MODIFIED requirement *A step definition declares how it is to
be resolved* — the scenarios this change writes or rewrites:

- *A step definition is read back with every declared attribute*, whose
  optional list this delta extends with "a metric identifier, drawn from
  the shared vocabulary, naming the metric the step establishes", and
  whose second clause now reads "...provenance reference **and metric
  identifier** are present only if authored",
- *A metric identifier names no defined metric* (new),
- *A metric identifier does not change how a step resolves* (new).

Its remaining scenario, *Steps can be selected by gate and by scope*, is
unchanged by this delta and stays covered by
`tests/unit/launch/domain/test_step_definition_field_set.py`, which this
pass does not touch.

## Level

`LaunchPlaybook` construction and its reads, plus one `Launch` recording
for the resolution scenario. The identifier is a field on the definition
and is required to change no rule, so the domain is the smallest unit
that observes both halves — no persistence, no adapter and no I/O is
needed to see either.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- `metric_id` as the field's name on `StepDefinition`, typed as the
  shared `MetricId` and defaulting to absent (`tasks.md` 2.1).
- `MetricId` in `commerce_ops.shared.domain.identity`
  (`tests/unit/shared/domain/test_metric_id.py`).
- That the identifier is inert: nothing validates that the metric it
  names is defined, and a step naming one is resolved by its recorded
  outcome exactly as any other (`design.md` — Decision 2).

INVENTED: that "absent" is spelled `None` rather than some other empty
value — the spelling every other optional field of `StepDefinition`
uses (`description`, `handler`, `confirmer`, `provenance`). Correction
point: the `is None` assertions below. What must survive any correction
is that an unauthored identifier reads back as absent rather than as a
value, and that an authored one reads back as given.

## Expected first-run state

`StepDefinition` carries no `metric_id` (`tasks.md` 2.1), so every test
here is expected to fail on an absent target — `TypeError` from the
unexpected keyword, or `AttributeError` from the read-back. Per
`ai-toolkit:testing` that establishes absence only: none of the
assertions below has been exercised.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

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
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.playbook import SPECIFIED_GATE_ORDER

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

#: SPECIFIED: the metric identifier `launch_playbook.py` authors on
#: `stock-ready` today and which `lp.inventory.040` inherits
#: (`proposal.md` — Impact).
STOCK_METRIC: Final = MetricId("units-fulfillable")

#: SPECIFIED (`design.md` — Decision 1): the threshold is the step's own
#: description, not a field of its own.
STOCK_THRESHOLD: Final = (
    "INVENTORY GATE: do not make the listing live until 60-80, and hopefully "
    "100+, units are FULFILLABLE - not in transfer, not reserved, not inbound"
)


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


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "lp.inventory.040",
        "name": "Work this step asks for",
        "description": None,
        "gate": "stock-ready",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(version="metric-step-v1", gates=_gates(), steps=_fill(steps))


def _read_back(playbook: LaunchPlaybook, gate: str, identifier: str) -> StepDefinition:
    (found,) = [
        candidate
        for candidate in playbook.steps_for_gate(gate)
        if candidate.identifier == identifier
    ]
    return found


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "72 fulfillable units confirmed in Seller Central",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


def _approval(*, gate: str) -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=RECORDED_AT,
        posture=Posture.SCALE if gate == "graduated" else None,
    )


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> None:
    """Walk the launch to `gate`, satisfying each earlier gate's blocking
    steps and approving the confirmation gates on the way."""
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(source="automated", who="hold-filler"),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate, _approval(gate=launch.current_gate)
            )
        launch.advance_gate(playbook)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step definition declares how it is to be
# resolved
# ---------------------------------------------------------------------------


def test_an_authored_metric_identifier_is_read_back() -> None:
    """Scenario: A step definition is read back with every declared
    attribute — the metric-identifier leg this delta adds.

    ...AND its description, assignees, handler, confirmer, provenance
    reference and metric identifier are present only if authored.

    The threshold half of the same decision is asserted alongside: the
    delta states that "the threshold a metric step establishes SHALL live
    in the step's own description", so the fixture puts it there and the
    read-back reports it there. A step carrying its threshold anywhere
    else would satisfy the identifier assertion alone.
    """
    step = _step(
        identifier="lp.inventory.040",
        name="INVENTORY GATE: 60-80+ units fulfillable before going live",
        description=STOCK_THRESHOLD,
        gate="stock-ready",
        blocking=True,
        metric_id=STOCK_METRIC,
    )

    read_back = _read_back(_playbook(steps=(step,)), "stock-ready", "lp.inventory.040")

    # SPECIFIED: an authored metric identifier is read back as given.
    assert read_back.metric_id == STOCK_METRIC
    # SPECIFIED: the threshold is the description, admin-editable and
    # displayed, rather than a field of its own.
    assert read_back.description == STOCK_THRESHOLD
    assert not hasattr(read_back, "threshold"), (
        "the step carries a `threshold` field of its own; `design.md` "
        "Decision 1 puts the threshold in the description precisely so "
        "there is not a second place to state the work"
    )


def test_an_unauthored_metric_identifier_reads_back_as_absent() -> None:
    """Scenario: A step definition is read back with every declared
    attribute — "present only if authored".

    Constructed omitting `metric_id` entirely, so the test exercises the
    default rather than restating it. "Almost every step declares none",
    so the absent case is the ordinary one and an implementation that
    made the field required would break every other step in the set.
    """
    step = _step(identifier="listing.a-plus-content", gate="listable", blocking=True)

    read_back = _read_back(
        _playbook(steps=(step,)), "listable", "listing.a-plus-content"
    )

    # SPECIFIED: present only if authored — INVENTED spelling of absence
    # as `None`, per the module docstring.
    assert read_back.metric_id is None


def test_a_metric_identifier_naming_no_defined_metric_still_loads() -> None:
    """Scenario: A metric identifier names no defined metric.

    WHEN a step declares a metric identifier naming a metric no registry
    defines
    THEN the playbook loads, because resolution against a metric registry
    is not this definition's concern.

    Every metric identifier is in this state today — no registry exists
    at all — so the fixture names one no artifact of this project
    mentions, to keep the assertion from passing merely because the value
    happened to be a familiar one.
    """
    invented = MetricId("returns-rate-trailing-thirty-days")
    step = _step(
        identifier="lp.finance.036",
        name="Hold graduation until the trailing return rate settles",
        gate="graduated",
        blocking=True,
        metric_id=invented,
    )

    playbook = _playbook(steps=(step,))

    # SPECIFIED: the playbook loads. Construction is the load, and a
    # rejection would raise rather than return.
    assert _read_back(playbook, "graduated", "lp.finance.036").metric_id == invented


def test_a_metric_identifier_does_not_change_how_a_step_resolves() -> None:
    """Scenario: A metric identifier does not change how a step resolves.

    WHEN a step declaring a metric identifier records a satisfying
    outcome
    THEN its gate obligation counts as satisfied on that outcome alone,
    exactly as for a step declaring none.

    Driven at `listable`, the first automatic gate, so that the advance
    itself is the observation: a metric step needing anything beyond its
    recorded outcome would leave the advance refused. The launch is
    walked there by satisfying each earlier gate's holding filler and
    approving the two confirmation gates on the way — the same walk
    `test_launch_gate_advance.py` uses.
    """
    metric_step = _step(
        identifier="lp.inventory.040",
        name="INVENTORY GATE: 60-80+ units fulfillable before going live",
        description=STOCK_THRESHOLD,
        gate="listable",
        blocking=True,
        metric_id=STOCK_METRIC,
    )
    ordinary_step = _step(
        identifier="lp.strategy.001",
        name="Write the phase-one exit criteria down",
        gate="listable",
        blocking=True,
    )
    playbook = _playbook(steps=(metric_step, ordinary_step))
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)
    _advance_to(launch, playbook, "listable")

    for step_id in ("lp.inventory.040", "lp.strategy.001"):
        launch.record_step_outcome(
            playbook,
            step_id=step_id,
            outcome=Satisfied,
            provenance=_provenance(),
        )
    launch.advance_gate(playbook)

    # SPECIFIED: the gate obligation counts as satisfied on that outcome
    # alone — the gate opened, with nothing recorded for the metric step
    # beyond its outcome.
    assert launch.current_gate == "stock-ready"
