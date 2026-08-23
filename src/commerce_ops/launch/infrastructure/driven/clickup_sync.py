"""Driven adapter: the two halves of the launch↔ClickUp completion loop.

Implements `launch-clickup-sync`'s projection and reconciliation
requirements. Both halves are written as *convergence* over one launch:
`converge_launch` drives ClickUp toward what the launch schedule implies,
`reconcile_launch` drives recorded outcomes toward what ClickUp says. A
crashed pass, a missed webhook, or a moved launch date all heal on the next
run with no special case — which is why nothing here reacts to an event.

**Recording is transition-based.** An outcome is recorded only when a
task's freshly read closed state differs from the state the mapping row
last retained; every observation writes that state back. It is never
compared against the *step's recorded outcome*: a read exposes state, not
history, so "open" cannot be told from "reopened", and comparing against
the recorded outcome would overwrite an attested `Satisfied` with
`InProgress` on the very next pass — a state the one-way-status non-goal
guarantees will occur. See design.md, "Recording is transition-based,
keyed on the last observed state".

Collaborators arrive as arguments rather than by import: this module must
not reach the catalog (`.importlinter`'s `products-infrastructure-boundary`
forbids it), and the passes are the same code whether a job or a test
drives them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Protocol

from commerce_ops.launch.domain.launch_playbook import (
    ExecutionMode,
    Hazard,
    InProgress,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    permissible_terminal_outcomes,
)
from commerce_ops.launch.domain.launch_run import (
    Launch,
    Provenance,
    StepOutcomeValue,
)
from commerce_ops.shared.domain.identity import ProductId

# design.md fixes this identity: a reconciliation read exposes no acting
# user, so the pass records itself as the recorder rather than inventing a
# human one.
RECONCILIATION_RECORDER = "clickup-reconciliation"

_GRADUATED_GATE = "graduated"
_CLICKUP_SOURCE = "clickup"


class ClickUpSyncError(RuntimeError):
    """A pass could not run: the ClickUp folder to project into is not
    configured, so a launch that needs a list cannot get one."""


class MappingStore(Protocol):
    """The step↔task mapping this module reads and writes. Satisfied by
    `clickup_mapping.ClickUpMappingRepository`."""

    async def list_id_for(self, product_id: ProductId) -> str | None: ...

    async def record_list(self, product_id: ProductId, list_id: str) -> None: ...

    async def task_for(self, product_id: ProductId, step_id: str) -> Any: ...

    async def tasks_for(self, product_id: ProductId) -> Sequence[Any]: ...

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None: ...

    async def observe(
        self, product_id: ProductId, step_id: str, closed: bool
    ) -> None: ...


ProductReader = Callable[[ProductId], Awaitable[Any]]
"""Reads the catalog product a launch is for. Supplied by the composition
root, because the launch module may not import the catalog's own store."""

OutcomeRecorder = Callable[..., Awaitable[Any]]
"""`launch.application.record_step_outcome`, with its stores already
bound. Recording always goes through the public use case — this module
never writes an outcome row itself."""


def is_projectable(step: StepDefinition) -> bool:
    """Whether a step becomes a ClickUp task.

    Only human-attested work does. An `automated` or `ai-assisted` step
    resolves through its own path, and a `prohibited-tactic` step can only
    ever be `Refused` — offering a person a task to tick would invite them
    to complete the thing the model says is uncompletable.
    """
    return (
        step.execution is ExecutionMode.HUMAN_ATTESTED
        and step.hazard is not Hazard.PROHIBITED_TACTIC
    )


def _is_terminal(launch: Launch, step: StepDefinition) -> bool:
    progress = launch.progress_for(step.identifier)
    if progress is None:
        return False
    recorded = progress.outcome
    kind = recorded if isinstance(recorded, type) else type(recorded)
    return kind in permissible_terminal_outcomes(step.hazard)


def _due_date(launch: Launch, playbook: LaunchPlaybook, step_id: str) -> date | None:
    """The day the step's work is due: the end of its resolved period.

    Absent for a launch with no date, for an open-ended anchor (an
    obligation that does not expire) and for a recurring one (a cadence,
    not a due date) — the three cases the requirement names.
    """
    period = launch.due_period_for(playbook, step_id)
    return period.end if period is not None else None


def _as_date(value: object) -> date | None:
    """The calendar day a due date names, however it is carried.

    A read from `clickup_client` already yields a `date`; ClickUp's own
    wire form is epoch milliseconds, and a stored value may still arrive
    that way.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    return None


def _due_date_field(due: date | None) -> Mapping[str, object]:
    """ClickUp's own due-date encoding: epoch milliseconds, or null to
    clear one that has become unresolvable."""
    if due is None:
        return {"due_date": None}
    moment = datetime(due.year, due.month, due.day, tzinfo=UTC)
    return {"due_date": int(moment.timestamp() * 1000)}


def transition_outcome(
    observed_closed: bool, now_closed: bool
) -> StepOutcomeValue | None:
    """The outcome a change of closed state records, or None for no change.

    The only two transitions that mean anything: a task becoming closed is
    the work being finished, and a closed task reopening is the work being
    taken up again. Everything else — including every repeat delivery — is
    silence.
    """
    if now_closed and not observed_closed:
        return Satisfied
    if observed_closed and not now_closed:
        return InProgress
    return None


def _list_name(product: Any) -> str:
    """The launch list's name, from the catalog product.

    The product identifier is opaque and never parsed for meaning, so the
    name the ops team reads is the product's own name and SKU.
    """
    return f"{product.name} ({product.sku})"


def _task_name(step: StepDefinition) -> str:
    return f"{step.identifier} · {step.discipline.value}"


async def converge_launch(
    *,
    launch: Launch,
    playbook: LaunchPlaybook,
    clickup: Any,
    mapping: MappingStore,
    read_product: ProductReader,
    folder_id: str | None,
) -> None:
    """Drive ClickUp toward what this launch's schedule implies.

    Creates the launch's list if it has none, creates a task for every
    projectable step that lacks one, re-creates a task that was deleted in
    ClickUp while its step is unfinished, and corrects any due date that no
    longer matches — which is how a moved launch date reaches the tasks
    that were already created.
    """
    if launch.current_gate == _GRADUATED_GATE:
        return

    steps = [step for step in playbook.steps if is_projectable(step)]
    list_id = await _ensure_list(
        launch=launch,
        mapping=mapping,
        clickup=clickup,
        read_product=read_product,
        folder_id=folder_id,
        steps=steps,
    )
    if list_id is None:
        return

    present = {task.id: task for task in await clickup.list_tasks(list_id)}

    for step in steps:
        mapped = await mapping.task_for(launch.product_id, step.identifier)
        task = present.get(mapped.task_id) if mapped is not None else None

        # Mapped but gone from ClickUp: deleting a task is not a sanctioned
        # way to finish work, so unfinished work is re-projected below.
        # Finished work is left alone — a task for something already
        # recorded as done is only noise.
        if mapped is not None and task is None and _is_terminal(launch, step):
            continue

        if task is not None and mapped is not None:
            task_id = mapped.task_id
            current_due = _as_date(task.due_date)
        else:
            created = await clickup.create_task(list_id=list_id, name=_task_name(step))
            await mapping.record_task(launch.product_id, step.identifier, created.id)
            task_id = str(created.id)
            current_due = None

        desired = _due_date(launch, playbook, step.identifier)
        if desired != current_due:
            await clickup.update_task(task_id, _due_date_field(desired))


async def _ensure_list(
    *,
    launch: Launch,
    mapping: MappingStore,
    clickup: Any,
    read_product: ProductReader,
    folder_id: str | None,
    steps: Sequence[StepDefinition],
) -> str | None:
    list_id = await mapping.list_id_for(launch.product_id)
    if list_id is not None:
        return list_id
    if not folder_id:
        raise ClickUpSyncError(
            f"launch for product '{launch.product_id.value}' needs a ClickUp "
            f"list, but no parent folder is configured "
            f"(CLICKUP_LAUNCH_FOLDER_ID); the pass fails rather than "
            f"skipping the launch silently"
        )
    product = await read_product(launch.product_id)
    created = str(
        await clickup.create_list(folder_id=folder_id, name=_list_name(product))
    )
    await mapping.record_list(launch.product_id, created)
    return created


async def reconcile_launch(
    *,
    launch: Launch,
    playbook: LaunchPlaybook,
    clickup: Any,
    mapping: MappingStore,
    record_outcome: OutcomeRecorder,
) -> None:
    """Record the completions and reopenings no webhook delivered.

    Reads every mapped task's state and compares it against the state the
    mapping retained, never against the step's own recorded outcome — see
    the module docstring for why that distinction is load-bearing.
    """
    if launch.current_gate == _GRADUATED_GATE:
        return

    list_id = await mapping.list_id_for(launch.product_id)
    if list_id is None:
        return

    present = {task.id: task for task in await clickup.list_tasks(list_id)}

    for mapped in await mapping.tasks_for(launch.product_id):
        task = present.get(mapped.task_id)
        if task is None:
            continue
        outcome = transition_outcome(mapped.last_observed_closed, task.closed)
        if outcome is None:
            continue
        await mapping.observe(launch.product_id, mapped.step_id, task.closed)
        await record_outcome(
            product_id=launch.product_id,
            step_id=mapped.step_id,
            outcome=outcome,
            provenance=Provenance(
                source=_CLICKUP_SOURCE,
                who=RECONCILIATION_RECORDER,
                when=datetime.now(UTC),
                evidence=f"ClickUp task {mapped.task_id}",
            ),
        )
