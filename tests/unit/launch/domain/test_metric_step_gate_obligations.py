"""A launch's obligations once attestation is gone.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-instance/spec.md`

Covers, at the domain level:

- MODIFIED requirement *A gate opens only when every blocking condition
  attached to it is satisfied* — its new scenario *An unresolved metric
  step holds its gate closed*, and the requirement's rewritten sentence
  ("every step obligation ... has reached a permitted terminal outcome",
  the metric-condition clause struck).
- MODIFIED requirement *A step outcome is recorded with provenance* —
  its rewritten scenario *A satisfied step is recorded with its
  provenance*, whose source is now `clickup` where it was `attestation`,
  and the requirement's narrowed source set (`clickup` or `automated`)
  together with its new sentence: "there is no source naming the
  significance of the step rather than the channel the outcome arrived
  through".
- REMOVED requirement *A metric condition is satisfied by human
  attestation until live evaluation exists* — asserted as the absence of
  the command, the value object and the store the requirement needed.
- MODIFIED requirement *A launch position can be read back by product
  identifier*, whose scenario *A launch position is retrieved* drops "and
  a metric attestation" / "each attestation it was persisted with".
  **Only the dropped half is covered here**, at the level that observes
  it: a launch that carries no attestations cannot persist or rehydrate
  any, so the aggregate is where the removal is visible without a
  database. The scenario's surviving half — that the version, gate, date,
  step progress with provenance and approvals all round-trip through
  Postgres — is unchanged by this delta and stays covered by
  `tests/integration/launch/test_launch_repository.py`, whose fixtures
  this change supersedes (recorded in `test-manifest.md`).

The requirement's four unchanged scenarios (re-recording, the two
prohibited-tactic rejections, the unknown identifier) are unchanged by
this delta and stay covered by
`tests/unit/launch/domain/test_launch_run.py`.

## Level

The `Launch` aggregate over a fixture playbook. Gate readiness is
computed from the launch's own recorded outcomes with no I/O
(`launch_run.py`), so the domain is the smallest unit that observes
both the holding and the recording; it is the level
`test_launch_gate_advance.py` already holds for the same requirement.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- `PROVENANCE_SOURCES` as the name of the declared source set, narrowed
  to `("clickup", "automated")` (`tasks.md` 5.4).
- `MetricAttestation`, `Launch.record_metric_attestation`, the
  `attestations` accessor and the constructor argument, all deleted
  (`tasks.md` 5.1).
- That a rejected advance raises `LaunchError` naming each unsatisfied
  condition — the reading `test_launch_gate_advance.py` records.

INVENTED: nothing beyond the fixture shapes this directory's sibling
files already use.

## Expected first-run state

`record_metric_attestation`, `MetricAttestation` and the `attestation`
source all still exist, so the three removal tests are expected to
**fail on a wrong value**. *An unresolved metric step holds its gate
closed* and *A satisfied step is recorded with its provenance* are
expected to fail on an absent target (`StepDefinition` takes no
`metric_id`) and to pass respectively — the latter's subject is
unchanged by this delta except in which source string the fixture uses,
and a source is a free string today. Per `ai-toolkit:testing` a pass
where the implementation exists is the expected result, not the alarm.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
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
    LaunchError,
    Provenance,
    StepSatisfied,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

PRODUCT_ID: Final = product_id()
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")

METRIC_STEP: Final = "lp.inventory.040"

#: SPECIFIED (`launch-instance` delta): the whole of the source set
#: after this change. Stated as a literal because a test derived from a
#: constant the implementation also defines would assert nothing.
SPECIFIED_SOURCES: Final = ("clickup", "automated")


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
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


def _metric_step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": METRIC_STEP,
        "name": "INVENTORY GATE: 60-80+ units fulfillable before going live",
        "description": (
            "INVENTORY GATE: do not make the listing live until 60-80, and "
            "hopefully 100+, units are FULFILLABLE - not in transfer, not "
            "reserved, not inbound"
        ),
        "gate": "listable",
        "blocking": True,
        "metric_id": STOCK_METRIC,
    }
    attributes.update(overrides)
    return _step(**attributes)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A gate opens only when every blocking condition
# attached to it is satisfied
# ---------------------------------------------------------------------------


def test_an_unresolved_metric_step_holds_its_gate_closed() -> None:
    """Scenario: An unresolved metric step holds its gate closed.

    WHEN the launch is advanced while a blocking step declaring a metric
    identifier, attached to the current gate, has no permitted terminal
    outcome
    THEN the advance is rejected and a `GateBlocked` occurrence names
    that step, exactly as for any other blocking step.

    The gate's other blocking obligation is satisfied first, so the metric
    step is the only thing holding it — an advance refused for some other
    reason would name a different condition and this assertion would not
    hold.
    """
    playbook = _playbook(steps=(_metric_step(), _hold("listable")))
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)
    _advance_to(launch, playbook, "listable")
    launch.record_step_outcome(
        playbook,
        step_id="hold.listable",
        outcome=Satisfied,
        provenance=_provenance(source="automated"),
    )

    with pytest.raises(LaunchError) as caught:
        launch.advance_gate(playbook)

    # SPECIFIED: the advance is rejected and the gate is unchanged.
    assert launch.current_gate == "listable"
    # SPECIFIED: the occurrence names that step — read through the
    # error's rendering, as `test_launch_gate_advance.py` records.
    assert METRIC_STEP in str(caught.value)


def test_a_satisfied_metric_step_opens_its_gate() -> None:
    """Requirement statement: "a threshold a gate turns on holds it as the
    obligation of the step that establishes it, satisfied by that step's
    recorded outcome".

    DERIVED from the requirement's own sentence rather than a named
    scenario, and paired with the test above: without it, an
    implementation that never satisfied a metric step's obligation at all
    would pass the holding scenario and stall every launch — which is the
    failure this whole change exists to end.
    """
    playbook = _playbook(steps=(_metric_step(), _hold("listable")))
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)
    _advance_to(launch, playbook, "listable")
    for step_id in ("hold.listable", METRIC_STEP):
        launch.record_step_outcome(
            playbook,
            step_id=step_id,
            outcome=Satisfied,
            provenance=_provenance(),
        )

    launch.advance_gate(playbook)

    assert launch.current_gate == "stock-ready"


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step outcome is recorded with provenance
# ---------------------------------------------------------------------------


def test_a_satisfied_step_is_recorded_with_its_provenance() -> None:
    """Scenario: A satisfied step is recorded with its provenance.

    WHEN a `Satisfied` outcome is recorded for a defined step with source
    `clickup`, a named recorder, a timestamp, and evidence
    THEN reading the launch back reports that step's outcome as
    `Satisfied` with exactly that provenance, and a `StepSatisfied`
    occurrence is reported.

    The source is `clickup` where this scenario previously said
    `attestation`. Driven over a step **declaring a metric identifier**,
    which is the requirement's new sentence: "A step establishing a metric
    is recorded through this same path, with the source that recorded it
    — there is no source naming the significance of the step rather than
    the channel the outcome arrived through."
    """
    playbook = _playbook(steps=(_metric_step(),))
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)
    provenance = _provenance(source="clickup")

    events = launch.record_step_outcome(
        playbook,
        step_id=METRIC_STEP,
        outcome=Satisfied,
        provenance=provenance,
    )

    # SPECIFIED: a `StepSatisfied` occurrence is reported.
    assert any(isinstance(event, StepSatisfied) for event in events)
    progress = launch.progress_for(METRIC_STEP)
    assert progress is not None
    # SPECIFIED: exactly that provenance.
    assert progress.outcome is Satisfied
    assert progress.provenance.source == "clickup"
    assert progress.provenance.who == "Helen"
    assert progress.provenance.when == RECORDED_AT
    assert progress.provenance.evidence == (
        "72 fulfillable units confirmed in Seller Central"
    )


def test_the_declared_source_set_is_clickup_and_automated_alone() -> None:
    """Requirement statement: "a source (`clickup` or `automated`)", and
    `tasks.md` 5.4 ("Remove `attestation` from `PROVENANCE_SOURCES`").

    The requirement enumerates the sources in its own words, so this is
    SPECIFIED rather than derived. It is asserted over the declared set
    rather than by attempting a rejected recording, because `Provenance`
    validates no source today and this delta does not ask it to start —
    what changes is which sources the system declares and writes.
    """
    import commerce_ops.launch.domain.launch_run as module

    declared = getattr(module, "PROVENANCE_SOURCES", None)
    assert declared is not None, (
        "`launch_run.py` declares no `PROVENANCE_SOURCES`; `tasks.md` 5.4 "
        "fixes that name — correct this probe if the set is declared "
        "elsewhere, but the set itself is what must narrow"
    )
    assert tuple(declared) == SPECIFIED_SOURCES, (
        f"the declared source set is {tuple(declared)!r}; the requirement "
        f"names {SPECIFIED_SOURCES!r} and nothing besides"
    )


# ---------------------------------------------------------------------------
# Requirement (REMOVED): A metric condition is satisfied by human
# attestation until live evaluation exists
# ---------------------------------------------------------------------------


def test_attestation_is_gone_from_the_launch_aggregate() -> None:
    """REMOVED requirement, and `tasks.md` 5.1-5.2.

    "The obligation each condition expressed is now a blocking step,
    satisfied by a recorded step outcome through the path every other
    obligation already uses." A `record_metric_attestation` left in place
    would leave a second way to satisfy an obligation — the exact
    duplication this change removes — and it is exported from the launch
    module's public surface, so a caller outside the module could still
    reach it.
    """
    import commerce_ops.launch.domain.launch_run as module
    from commerce_ops.launch import application

    assert not hasattr(module, "MetricAttestation"), (
        "`MetricAttestation` still exists; the REMOVED requirement takes "
        "attestation out entirely (`tasks.md` 5.1)"
    )
    assert not hasattr(Launch, "record_metric_attestation"), (
        "`Launch.record_metric_attestation` still exists (`tasks.md` 5.1)"
    )
    assert not hasattr(application, "record_metric_attestation"), (
        "`record_metric_attestation` is still exported from the launch "
        "module's public surface (`tasks.md` 5.2)"
    )


def test_a_launch_carries_no_attestations_to_persist_or_read_back() -> None:
    """Scenario: A launch position is retrieved — the clause this delta
    strikes.

    The scenario previously read "...each approval, **and each
    attestation** it was persisted with". With the store dropped there is
    nothing to persist and nothing to rehydrate, so a launch exposes no
    attestations at all — which is the half of the scenario this level
    can observe. The surviving half round-trips through Postgres and is
    covered at the integration tier (see the module docstring).
    """
    playbook = _playbook(steps=(_metric_step(),))
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook)

    assert not hasattr(launch, "attestations"), (
        "the launch still exposes `attestations`; `tasks.md` 5.1 removes "
        "the accessor and the constructor argument, and 5.3 stops the "
        "repository persisting and rehydrating them"
    )
