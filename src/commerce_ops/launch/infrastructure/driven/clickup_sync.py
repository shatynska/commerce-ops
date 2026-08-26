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

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Protocol

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InProgress,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
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

_logger = logging.getLogger(__name__)

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

    async def record_composition(
        self,
        product_id: ProductId,
        step_id: str,
        *,
        name: str | None = None,
        body: str | None = None,
        assignees: Sequence[str] | None = None,
    ) -> None: ...


ProductReader = Callable[[ProductId], Awaitable[Any]]
"""Reads the catalog product a launch is for. Supplied by the composition
root, because the launch module may not import the catalog's own store."""

OutcomeRecorder = Callable[..., Awaitable[Any]]
"""`launch.application.record_step_outcome`, with its stores already
bound. Recording always goes through the public use case — this module
never writes an outcome row itself."""


RosterReader = Any
"""Reads the roster's people, so a step's assignees can be resolved to
ClickUp users. Supplied by the composition root across the module
boundary, because `launch` may only reach `access` through its public
application surface — the same shape `read_product` has for the catalog."""


async def _roster_people(roster: RosterReader) -> tuple[Any, ...]:
    if roster is None:
        return ()
    lister = getattr(roster, "list_people", None)
    if lister is not None:
        return tuple(await lister())
    if callable(roster):
        return tuple(await roster())
    return tuple(roster)


def _person_identifier(person: Any) -> str:
    for name in ("identifier", "id", "person_id"):
        value = getattr(person, name, None)
        if value is not None:
            return str(value)
    raise ValueError(f"a roster person exposes no identifier: {person!r}")


def _clickup_users(
    step: StepDefinition, people: Mapping[str, Any], *, task_id: str | None
) -> tuple[str, ...]:
    """The step's assignees as ClickUp user ids, in the order the step
    names them.

    An assignee the roster carries without a ClickUp user id is skipped
    and **reported**, never silently dropped: the task is still created
    and still carries the step's remaining assignees, because a failed
    run would hide a data gap behind a retry, and the run record only
    says whether the pass succeeded.
    """
    resolved: list[str] = []
    for identifier in step.assignees:
        person = people.get(identifier)
        if person is None:
            _logger.warning(
                "step %s names assignee %s, whom the roster does not carry; "
                "the ClickUp task %s is left without them",
                step.identifier,
                identifier,
                task_id or "(being created)",
            )
            continue
        user_id = getattr(person, "clickup_user_id", None)
        if not user_id:
            _logger.warning(
                "step %s names assignee %s (%s), who has no ClickUp account; "
                "the task %s is created and assigned to the step's remaining "
                "assignees",
                step.identifier,
                identifier,
                getattr(person, "display_name", "?"),
                task_id or "(being created)",
            )
            continue
        resolved.append(str(user_id))
    return tuple(resolved)


def _assignee_change(
    retained: Sequence[str] | None,
    current_in_clickup: Sequence[str],
    desired: Sequence[str],
) -> Mapping[str, object] | None:
    """The assignee edit a pass may send, or `None` for none.

    A mapping holding no retained assignees — every mapping made before
    assignees existed — is read as having last been set to nobody, so a
    task the system left unassigned heals to its step's assignees while
    one somebody has already assigned is treated as person-edited and
    left alone. Assignees are the one field where that reading is right:
    an unassigned task is the failure this projection exists to fix, so
    silence there is the system's own doing rather than an edit worth
    preserving.
    """
    last_set = tuple(retained or ())
    current = tuple(current_in_clickup)
    if set(current) != set(last_set):
        return None
    if set(current) == set(desired):
        return None
    add = [user for user in desired if user not in current]
    remove = [user for user in current if user not in desired]
    return {"assignees": {"add": add, "rem": remove}}


def is_projectable(step: StepDefinition) -> bool:
    """Whether a step becomes a ClickUp task.

    Only `active` human work does. An `automated` step resolves through
    its own path whether or not its result needs a person's
    confirmation — the confirmation flag is not a way back into this
    projection. A step that is not `active` is not part of the launch's
    obligations at all, and a `prohibited-tactic` step can only ever be
    `Refused` — offering a person a task to tick would invite them to
    complete the thing the model says is uncompletable.
    """
    return (
        step.kind is StepKind.HUMAN
        and step.status is StepStatus.ACTIVE
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


CLICKUP_TASK_NAME_LIMIT = 2048
"""The longest task name ClickUp accepts, measured against the live API on
2026-08-24: 2048 characters are stored intact, 2049 is refused with
`HTTP 400` / `INPUT_005 "Task name invalid"` — it refuses rather than
truncating. Counted the way `len()` counts characters; the ladder used
ASCII only, so it does not distinguish characters from bytes, which cannot
matter while the longest name this playbook can compose is 271 (see the
change's design.md, Decision 4)."""

_NAME_SEPARATOR = " · "
_NAME_CUT_MARK = "…"


def _task_name(step: StepDefinition) -> str:
    """The step's name, then its identifier — never its discipline.

    The discipline is not appended because the identifier's own second
    segment already carries it (`lp.creative.008` is a `creative` step), and
    the width would be spent restating what is already there instead of on
    the wording that makes the task readable. A name that happens to
    mention its own discipline is composed unaltered; the rule is about what
    is appended, not about what the wording says.
    """
    composed = f"{step.name}{_NAME_SEPARATOR}{step.identifier}"
    if len(composed) <= CLICKUP_TASK_NAME_LIMIT:
        return composed

    # Keep the identifier whole — it is what makes the task traceable — and
    # surrender no more of the name than the limit requires. The surrendered
    # text is *not* moved into the body: the body belongs to the step's
    # description, and overwriting it with a fragment of the name would
    # displace what an author wrote.
    tail = f"{_NAME_CUT_MARK}{_NAME_SEPARATOR}{step.identifier}"
    kept = max(CLICKUP_TASK_NAME_LIMIT - len(tail), 0)
    return f"{step.name[:kept]}{tail}"


def _task_body(step: StepDefinition) -> str | None:
    """The step's description, or nothing at all where it carries none.

    `None` means *compose no body*, never *compose an empty one*. A task
    projected before the step gained two fields carries the step's full
    former text in its body, written by the system and therefore matching
    its retained value — so a rule composing an empty body here would be
    licenced to rewrite it away, leaving that task stating its work
    nowhere.
    """
    return step.description


def _wants_rewrite(
    retained: str | None, current_in_clickup: str | None, desired: str | None
) -> bool:
    """Whether a field may be rewritten to `desired`: only while the field
    in ClickUp still carries exactly what the system last wrote for it —
    a field that differs has been edited by a person and is never touched.
    """
    if retained is None or desired is None:
        return False
    return current_in_clickup == retained and retained != desired


async def _heal_wording(
    *,
    step: StepDefinition,
    task: Any,
    mapped: Any,
    product_id: ProductId,
    clickup: Any,
    mapping: MappingStore,
    desired_assignees: Sequence[str],
) -> None:
    """Drive the task's name and body toward the step's current composition
    — each field independently, and only while it still carries the
    system's own words.

    A mapping predating retained compositions holds none: a field whose
    ClickUp content is exactly what the system would currently compose is
    adopted as retained (an unedited legacy task starts healing); anything
    else is left unadopted and forever unrewritten — where the system
    cannot tell an authored change from a person's edit, the person wins.
    """
    desired_name = _task_name(step)
    desired_body = _task_body(step)
    retained_name = getattr(mapped, "retained_name", None)
    retained_body = getattr(mapped, "retained_body", None)
    task_name = getattr(task, "name", None)
    task_body = getattr(task, "description", None)

    adopt_name = retained_name is None and task_name == desired_name
    adopt_body = (
        retained_body is None and desired_body is not None and task_body == desired_body
    )
    if adopt_name or adopt_body:
        await mapping.record_composition(
            product_id,
            step.identifier,
            name=desired_name if adopt_name else None,
            body=desired_body if adopt_body else None,
        )
        retained_name = desired_name if adopt_name else retained_name
        retained_body = desired_body if adopt_body else retained_body

    write_name = _wants_rewrite(retained_name, task_name, desired_name)
    write_body = _wants_rewrite(retained_body, task_body, desired_body)
    assignee_change = _assignee_change(
        getattr(mapped, "retained_assignees", None),
        getattr(task, "assignees", ()),
        desired_assignees,
    )
    if not write_name and not write_body and assignee_change is None:
        return
    fields: dict[str, object] = {}
    if write_name:
        fields["name"] = desired_name
    if write_body:
        fields["description"] = desired_body
    if assignee_change is not None:
        fields.update(assignee_change)
    await clickup.update_task(mapped.task_id, fields)
    await mapping.record_composition(
        product_id,
        step.identifier,
        name=desired_name if write_name else None,
        body=desired_body if write_body else None,
        assignees=tuple(desired_assignees) if assignee_change is not None else None,
    )


async def converge_launch(
    *,
    launch: Launch,
    playbook: LaunchPlaybook,
    clickup: Any,
    mapping: MappingStore,
    read_product: ProductReader,
    folder_id: str | None,
    roster: RosterReader = None,
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

    steps = [step for step in playbook.served_steps if is_projectable(step)]
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
    people = {
        _person_identifier(person): person for person in await _roster_people(roster)
    }

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
            await _heal_wording(
                step=step,
                task=task,
                mapped=mapped,
                product_id=launch.product_id,
                clickup=clickup,
                mapping=mapping,
                desired_assignees=_clickup_users(step, people, task_id=task_id),
            )
        else:
            composed_name = _task_name(step)
            composed_body = _task_body(step)
            assignees = _clickup_users(step, people, task_id=None)
            created = await clickup.create_task(
                list_id=list_id,
                name=composed_name,
                description=composed_body,
                assignees=list(assignees),
            )
            await mapping.record_task(launch.product_id, step.identifier, created.id)
            # Whenever the system writes a name, a body or an assignee
            # set, the retained value follows the write — creation
            # included.
            await mapping.record_composition(
                launch.product_id,
                step.identifier,
                name=composed_name,
                body=composed_body,
                assignees=assignees,
            )
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
    # The set the loop still projects, not merely the served set. A step
    # that becomes `automated` stays `active`, so nothing about its status
    # signals its departure — and its orphaned task, closed by a person
    # tidying up, would otherwise record a `clickup`-sourced completion for
    # work a handler is about to do. One predicate, shared with the outward
    # half above, so the two directions cannot drift apart.
    defined = {
        step.identifier for step in playbook.served_steps if is_projectable(step)
    }

    for mapped in await mapping.tasks_for(launch.product_id):
        task = present.get(mapped.task_id)
        if task is None:
            continue
        outcome = transition_outcome(mapped.last_observed_closed, task.closed)
        if outcome is None:
            continue
        # The observation always updates the retained state — steps
        # outside the served set included, so what happened while a step
        # was out of it is never replayed as a transition later.
        await mapping.observe(launch.product_id, mapped.step_id, task.closed)
        if mapped.step_id not in defined:
            # A step that is not `active` records nothing — retired, or
            # moved back to `draft` or `in-development` alike: the step
            # the recording would name is no longer part of the launch's
            # obligations. The observation above still ran, so what
            # happened while it was out is never replayed later.
            continue
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
