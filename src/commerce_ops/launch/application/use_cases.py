"""Launch use cases: the module's public behavior over its ports.

Implements `launch-instance`'s driving surface for slice 3 (see
`openspec/changes/introduce-launch-aggregate/`): application use cases
only — no HTTP or Slack adapter exists yet (those arrive with the ClickUp
loop and briefing slices). Each command loads the aggregate, loads the
playbook version the launch pinned, invokes the domain command, persists,
and returns the events the domain produced.

Graduation is the one cross-module write: when `advance_gate` opens
`graduated`, the advanced launch is persisted first, then the catalog
product is stamped steady-state through the stamping port — carrying the
posture the graduation approver chose and the approver as the human
confirmer. A stamp the catalog rejects leaves the advance standing and
surfaces as `GraduationStampError` naming the manual catalog correction.

Unknown-product and duplicate-launch rejections on `start_launch` are the
store's own (`launch-instance`'s persistence requirements): the catalog
reference is enforced where the record is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from commerce_ops.catalog.application import StageTransitionError
from commerce_ops.launch.application.errors import (
    GraduationStampError,
    LaunchNotFoundError,
)
from commerce_ops.launch.application.ports import (
    LaunchStore,
    Playbooks,
    SteadyStateStamper,
)
from commerce_ops.launch.domain.launch_playbook import AnchorPeriod, LaunchPlaybook
from commerce_ops.launch.domain.launch_run import (
    GateApproval,
    Launch,
    LaunchDateAtRisk,
    LaunchEvent,
    LaunchGraduated,
    MetricAttestation,
    Provenance,
    StepOutcomeValue,
    StepProgress,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import SteadyState


async def start_launch(
    launches: LaunchStore,
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = None,
) -> tuple[LaunchEvent, ...]:
    """Start a launch for a catalog product, pinning the given playbook's
    version. The store rejects an unknown product or a second launch."""
    launch, started = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    await launches.save(launch)
    return (started,)


async def record_step_outcome(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    step_id: str,
    outcome: StepOutcomeValue,
    provenance: Provenance,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    events = launch.record_step_outcome(
        playbook, step_id=step_id, outcome=outcome, provenance=provenance
    )
    await launches.save(launch)
    return events


async def record_metric_attestation(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    attestation: MetricAttestation,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    events = launch.record_metric_attestation(playbook, attestation)
    await launches.save(launch)
    return events


async def approve_gate(
    launches: LaunchStore,
    *,
    product_id: ProductId,
    gate_id: str,
    approval: GateApproval,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    events = launch.approve_gate(gate_id, approval)
    await launches.save(launch)
    return events


async def advance_gate(
    *,
    launches: LaunchStore,
    playbooks: Playbooks,
    stamp_steady_state: SteadyStateStamper,
    product_id: ProductId,
) -> tuple[LaunchEvent, ...]:
    """Advance the launch past its current gate. Opening `graduated`
    additionally stamps the catalog product steady-state — after the
    advanced launch is persisted, so a rejected stamp leaves the advance
    standing."""
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    events = launch.advance_gate(playbook)
    await launches.save(launch)

    graduated = next(
        (event for event in events if isinstance(event, LaunchGraduated)), None
    )
    if graduated is not None:
        try:
            await stamp_steady_state(
                launch.product_id,
                SteadyState(posture=graduated.posture),
                confirmed_by=graduated.approver,
            )
        except StageTransitionError as exc:
            raise GraduationStampError(
                f"product '{product_id.value}' ({product_id}) graduated, "
                f"but the catalog rejected the steady-state stamp ({exc}); "
                f"the launch stands at 'graduated' — correct the product's "
                f"stage in the catalog by hand"
            ) from exc
    return events


async def move_launch_date(
    launches: LaunchStore,
    *,
    product_id: ProductId,
    new_date: date,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    events = launch.move_launch_date(new_date)
    await launches.save(launch)
    return events


@dataclass(frozen=True, slots=True)
class StepStatus:
    """One step's runtime status: what was recorded, when it is due, and
    the two judgements only the launch context can make.

    `discipline` and `blocking` come from the playbook; `overdue` folds
    "the due period has fully passed" together with "the step has not
    reached a terminal outcome its hazard permits". A reader outside this
    module has neither the playbook nor the hazard rules, so each of these
    travels on the report rather than being re-derived (`launch-instance`,
    "The launch report carries each step's discipline").
    """

    step_id: str
    discipline: Discipline
    due_period: AnchorPeriod | None
    progress: StepProgress | None
    blocking: bool
    overdue: bool


@dataclass(frozen=True, slots=True)
class LaunchReport:
    """The launch's full state plus its derived schedule, as of a date."""

    product_id: ProductId
    playbook_version: str
    current_gate: str
    launch_date: date | None
    steps: tuple[StepStatus, ...]
    at_risk: LaunchDateAtRisk | None
    awaiting_confirmation: bool


def _report_for(launch: Launch, playbook: LaunchPlaybook, as_of: date) -> LaunchReport:
    """One launch's report — the single construction both reads share, so
    an enumerated report can never drift from a singly-read one."""
    overdue = set(launch.overdue_step_ids(playbook, as_of))
    return LaunchReport(
        product_id=launch.product_id,
        playbook_version=launch.playbook_version,
        current_gate=launch.current_gate,
        launch_date=launch.launch_date,
        steps=tuple(
            StepStatus(
                step_id=step.identifier,
                discipline=step.discipline,
                due_period=launch.due_period_for(playbook, step.identifier),
                progress=launch.progress_for(step.identifier),
                blocking=step.blocking,
                overdue=step.identifier in overdue,
            )
            for step in playbook.steps
        ),
        at_risk=launch.date_at_risk(playbook, as_of),
        awaiting_confirmation=launch.awaiting_confirmation(playbook),
    )


async def read_launch(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    as_of: date,
) -> LaunchReport | None:
    """The launch with every step's due period and the at-risk evaluation
    as of `as_of`; absence is reported as None, not an error."""
    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        return None
    return _report_for(launch, playbooks.get(launch.playbook_version), as_of)


async def read_launches(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    as_of: date,
) -> tuple[LaunchReport, ...]:
    """Every persisted launch position, reported as of `as_of`.

    Filtered by nothing: this context does not own a product's stage, and
    its persisted shape does not distinguish a graduated launch from one
    standing at the final gate. A caller wanting only live launches asks
    the catalog for the stage stamp (`launch-instance`, "Launch positions
    are enumerable with their reports"). An empty store is an empty
    result, not an error.
    """
    return tuple(
        _report_for(launch, playbooks.get(launch.playbook_version), as_of)
        for launch in await launches.list_all()
    )


async def _existing(launches: LaunchStore, product_id: ProductId) -> Launch:
    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        raise LaunchNotFoundError(f"product '{product_id.value}' has no launch record")
    return launch
