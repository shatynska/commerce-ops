"""A launch whose ClickUp list was deleted is given a new one.

Derived strictly from the delta spec of the OpenSpec change
`heal-a-launchs-deleted-list`:
`openspec/changes/heal-a-launchs-deleted-list/specs/launch-clickup-sync/spec.md`

Covers, from the MODIFIED requirement *Each launch is projected into its
own ClickUp list*, every scenario the delta adds or revises:

- *An existing list is not recreated* — **revised**: its WHEN now requires
  that "ClickUp reports that list as existing", which the existing test
  `test_clickup_sync_projection.py::test_an_existing_list_is_not_recreated`
  cannot express (its ClickUp double can answer nothing about a list).
  Re-established here against a double that can.
- *A launch whose list was deleted gets a new one* — new.
- *The replacement and the discard cannot come apart* — new (the caller's
  half; the single-commit half is
  `tests/integration/launch/test_clickup_mapping_list_replacement.py`).
- *Steps re-project into the replacement list* — new.
- *Finished work is not re-projected into the replacement list* — new.
- *Finished work of a step the launch is not held to survives the
  replacement* — new.
- *A mapping for an undefined step is discarded* — new.
- *Outcomes recorded before the deletion are kept* — new.
- *A failed write is not read as a deletion* — new.
- *A list whose state cannot be established is not healed* — new.
- *A graduated launch is left alone* — **broadened**: the delta adds "AND
  its recorded list is not checked for existence". Only that new clause is
  covered here; the first clause stays covered, untouched, by
  `test_clickup_sync_projection.py::test_a_graduated_launch_is_left_alone`.
- *Missing folder configuration fails the run* — **broadened**: the delta
  adds "AND this holds equally for a launch needing a list because ClickUp
  reports its recorded one deleted, which is not given its deleted list's
  identifier back". Only that new clause is covered here.

*A launch without a list gets one* is carried into the delta verbatim and
stays covered by `test_clickup_sync_projection.py`. This file is additive:
it touches, duplicates and supersedes no existing test. See
`openspec/changes/heal-a-launchs-deleted-list/test-manifest.md` for the
full accounting, including which existing tests bear on the revised
scenarios.

## The three things these tests exist to discriminate

1. **A deletion is what ClickUp says, never what a failure suggests.**
   `design.md` — Decision 4 turns the whole change on this. Two tests
   therefore drive failures that a weaker implementation would read as
   deletions — a `404` on a *write* (*A failed write is not read as a
   deletion*) and a failed *read of the list itself* (*A list whose state
   cannot be established is not healed*) — and assert that nothing is
   healed in either.
2. **The exemption is judged hazard-independently and over the authored
   set.** `design.md` — Decision 2b. `test_finished_work_of_a_step_the_
   launch_is_not_held_to_survives_the_replacement` runs both flips that a
   narrower reading gets wrong: a step retired after its work was
   finished (out of `served_steps`, still authored), and a step
   re-authored `prohibited-tactic` after its outcome was recorded (served,
   not projectable, and *not* terminal under the hazard-relative
   `_is_terminal`). Each then returns to active human work and must not be
   handed a fresh open task.
3. **The discard is one act with the replacement.** The store double's
   combined operation can be made to fail, and the assertions read the
   dichotomy the requirement states — old list with mappings intact, or
   new list with the discard applied, never a mixture.

## `NotApplicable`, and why `Refused` is absent

`design.md` — Decision 2 names `NotApplicable` the sharp case: "work
someone judged unnecessary, re-presented as outstanding, with nothing in
the list saying it was ever settled". The finished-work tests are
parametrised over `Satisfied` and `NotApplicable` for that reason.

`Refused` is deliberately not exercised on a projectable step. The same
decision records that `permissible_terminal_outcomes` permits `Refused`
**only** for a `prohibited-tactic` step, and `is_projectable` excludes
exactly that hazard — so a projectable step carrying `Refused` is a state
the domain refuses to produce, and constructing one would be asserting
against a fixture rather than against the system.

## INVENTED shapes

The harness follows `test_clickup_sync_tags.py` in this directory —
`converge_launch(launch=, playbook=, clickup=, mapping=, read_product=,
members=, folder_id=)` and `reconcile_launch(launch=, playbook=, clickup=,
mapping=, record_outcome=)` over in-memory fakes — extended with the two
operations this change adds, neither of which any artifact names:

- **The ClickUp port's read of a list's own state.** `_FakeClickUp`
  answers to several plausible spellings (`get_list`, `read_list`,
  `get_list_state`, ...), all one method, and records the call under
  `get_list`. Correction point: `_FakeClickUp`.
- **The mapping store's combined replace-and-discard.** `tasks.md` 2.1
  fixes that it is *one* operation and 2.2 that the *caller* hands it the
  mappings to spare; nothing fixes its name or its parameter names.
  `_FakeMapping` answers to several spellings and resolves its three
  arguments positionally or by keyword, accepting the spared set as step
  identifiers or as mapping objects. Correction point: `_FakeMapping`.

Both doubles record every attribute the pass probes but they do not have,
so a name this file failed to anticipate fails by name rather than
silently. `_converge` turns such a probe into a `pytest.fail` naming what
was reached for — a fixture correction (`ai-toolkit:testing` failure state
3), never a reason to weaken what a test asserts.

## The list *name* is asserted on the bare SKU only

`proposal.md` — Impact records that `_list_name` currently renders the SKU
value object rather than its value, that PR #81 fixes it ahead of this
change, and that task 5.3 confirms the fix on the healed launch's list.
The assertion below is `PRODUCT_SKU.value in name`, which holds both
before and after that fix — so nothing in this file turns red for a reason
that is not about healing, and nothing here asserts the defect either. The
repr-free form is left to PR #81's own test and to task 5.3.

## Expected first-run state

Nothing under test exists: the client has no read of a list's own state,
the store has no combined replace-and-discard, and `_ensure_list` has no
healing branch. Every test here is expected to fail on an absent target.
Per `ai-toolkit:testing` that establishes only absence, and nothing about
whether these assertions are well-formed.

Baseline recorded before these tests were written, at the worktree root:
`uv run pytest tests/unit tests/agents` — 1130 passed, 0 failed;
`uv run pytest tests/integration` — 3 passed, 94 skipped (no database is
configured here, so that tier's database-backed tests skip).
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    NotApplicable,
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
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    converge_launch,
    reconcile_launch,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import (
    ALICE,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"
#: The launch's recorded list -- the identifier `proposal.md` opens on.
LIST_ID: Final = "901220624358"

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

#: A projectable step whose work is unfinished: re-projects into the
#: replacement list.
OPEN_STEP_ID: Final = "listing.title-conforms"
OPEN_STEP_NAME: Final = "Conform the title to the style guide"

#: A second unfinished step, so "every projectable step whose work is
#: unfinished" is asserted over more than one.
OTHER_OPEN_STEP_ID: Final = "listing.images-approved"
OTHER_OPEN_STEP_NAME: Final = "Approve the image set"

#: A projectable step whose recorded outcome settles work: exempt.
DONE_STEP_ID: Final = "finance.unit-economics"
DONE_STEP_NAME: Final = "Check the unit economics still clear"

#: A step the playbook does not define at all: discarded with the rest.
UNDEFINED_STEP_ID: Final = "legacy.pre-postgres-step"

DEAD_TASK: Final = "task-in-the-dead-list"
OTHER_DEAD_TASK: Final = "task-in-the-dead-list-2"
DONE_DEAD_TASK: Final = "task-for-finished-work"
UNDEFINED_DEAD_TASK: Final = "task-for-an-undefined-step"

ALICE_CLICKUP: Final = "clickup-alice"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_clickup_sync_tags.py`
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": OPEN_STEP_ID,
        "name": OPEN_STEP_NAME,
        "description": None,
        "gate": "listable",
        "discipline": Discipline.LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """An `active` `automated` blocking filler for the gate-holding floor.

    Automated, so no filler is ever projected and every task assertion
    below is about the test's own steps.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _open_step() -> StepDefinition:
    return _step(identifier=OPEN_STEP_ID, name=OPEN_STEP_NAME)


def _other_open_step() -> StepDefinition:
    return _step(identifier=OTHER_OPEN_STEP_ID, name=OTHER_OPEN_STEP_NAME)


def _done_step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": DONE_STEP_ID,
        "name": DONE_STEP_NAME,
        "gate": "commit",
        "discipline": Discipline.FINANCE,
    }
    attributes.update(overrides)
    return _step(**attributes)


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "https://app.clickup.com/t/task-for-finished-work",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


def _graduated(playbook: LaunchPlaybook) -> Launch:
    """A launch walked along the ordinary advance path to `graduated`.

    Transcribed from `test_clickup_sync_projection.py`.
    """
    launch = _start(playbook)
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=RECORDED_AT,
                        evidence="filler obligations satisfied by the walk",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
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
    assert launch.current_gate == "graduated"
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return self._product


class _Member:
    def __init__(
        self, member_id: str, display_name: str, *, clickup_user_id: str | None
    ) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id = clickup_user_id
        self.active = True


class _FakeMembers:
    def __init__(self, members: tuple[_Member, ...]) -> None:
        self._members = members

    async def list_members(self) -> tuple[_Member, ...]:
        return self._members

    members = list_members

    async def member(self, member_id: str) -> _Member | None:
        for member in self._members:
            if member.id == member_id:
                return member
        return None

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


def _members() -> _FakeMembers:
    return _FakeMembers((_Member(ALICE, "Alice Admin", clickup_user_id=ALICE_CLICKUP),))


class _ClickUpRequestFailed(RuntimeError):
    """A non-success from ClickUp, as the client surfaces it.

    `clickup-task-client` obliges the client to propagate rather than
    suppress, and names no type; the pass is only ever required to *not*
    read one of these as a deletion.
    """


class _ClickUpUnreachable(RuntimeError):
    """ClickUp not answering at all -- no response received."""


class _StoreWriteFailed(RuntimeError):
    """The replace-and-discard transaction not completing."""


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    status: str = "to do"
    closed: bool = False
    due_date: Any = None
    body: Any = None
    assignees: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


@dataclass(frozen=True)
class _ListState:
    """What the client's read of a list's own state hands back.

    Carries `deleted` -- "at least whether ClickUp reports that list as
    deleted" -- and the name, which the pass has no stated use for.
    """

    id: str
    name: str
    deleted: bool


class _FakeClickUp:
    """In-memory ClickUp, offering exactly the operations the pass may use.

    Anything else the pass reaches for is recorded in `probed` and raises
    `AttributeError` in the ordinary way, so a call this file failed to
    anticipate leaves a named trace rather than passing silently.
    """

    def __init__(self) -> None:
        self._probed: list[str] = []
        self.lists: dict[str, str] = {}
        self.deleted_lists: set[str] = set()
        #: list_id -> the failure its state read raises. Decision 4's case:
        #: the state cannot be established at all.
        self.unreadable_lists: dict[str, Exception] = {}
        #: list_id -> the failure a *write* into it raises, while the list
        #: itself still reports alive.
        self.refuse_writes_into: dict[str, Exception] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    def __getattr__(self, name: str) -> Any:
        probed = self.__dict__.get("_probed")
        if probed is not None and not name.startswith("__"):
            probed.append(name)
        raise AttributeError(name)

    @property
    def probed(self) -> tuple[str, ...]:
        return tuple(self._probed)

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    # -- writes ------------------------------------------------------------

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        payload: dict[str, Any] = {"list_id": list_id, "name": name, **fields}
        if description is not None:
            payload["description"] = description
        self.calls.append(("create_task", payload))
        refusal = self.refuse_writes_into.get(list_id)
        if refusal is not None:
            raise refusal
        task_id = self._identifier("task")
        self.tasks[task_id] = _FakeTask(id=task_id, name=name, list_id=list_id)
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        if "name" in fields:
            task.name = fields["name"]
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag_name": tag_name}))
        task = self.tasks[task_id]
        if tag_name not in task.tags:
            task.tags = (*task.tags, tag_name)

    # -- reads -------------------------------------------------------------

    async def get_list(self, list_id: str) -> _ListState:
        """The list's own state.

        Faithful to `design.md` — Decision 4 in all three answers: a
        deleted list answers `200` with `deleted` true; a live one answers
        `200` with it false; and anything the client cannot establish --
        including a list this ClickUp has never heard of -- *raises*,
        because a failed request is not a report of a deletion.
        """
        self.calls.append(("get_list", {"list_id": list_id}))
        failure = self.unreadable_lists.get(list_id)
        if failure is not None:
            raise failure
        if list_id in self.deleted_lists:
            return _ListState(
                id=list_id, name=self.lists.get(list_id, "deleted list"), deleted=True
            )
        if list_id not in self.lists:
            raise _ClickUpRequestFailed(f"404 Not Found: /api/v2/list/{list_id}")
        return _ListState(id=list_id, name=self.lists[list_id], deleted=False)

    # The operation's name is INVENTED; these aliases are the correction
    # point. All record the call under "get_list".
    read_list = get_list
    get_list_state = get_list
    read_list_state = get_list
    list_state = get_list

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        """A deleted list answers this successfully, and empty.

        That is the measurement `design.md` — Context turns on: the task
        read cannot tell a deleted list from a live empty one, which is
        why the list-state read exists at all. Reproducing it here means a
        pass that tried to detect deletion from an empty task read is not
        rewarded by this double.
        """
        self.calls.append(("list_tasks", {"list_id": list_id}))
        if list_id in self.deleted_lists:
            return []
        return [task for task in self.tasks.values() if task.list_id == list_id]

    # -- test-side helpers -------------------------------------------------

    def seed_live_list(self, list_id: str, name: str = "seeded list") -> str:
        self.lists[list_id] = name
        return list_id

    def seed_deleted_list(self, list_id: str, name: str = "seeded list") -> str:
        """A list ClickUp still answers for, and reports as deleted."""
        self.lists[list_id] = name
        self.deleted_lists.add(list_id)
        return list_id

    def seed_task(self, list_id: str, task_id: str, **overrides: Any) -> _FakeTask:
        attributes = {"name": task_id, **overrides}
        task = _FakeTask(id=task_id, list_id=list_id, **attributes)
        self.tasks[task_id] = task
        return task

    def calls_named(self, name: str) -> list[Any]:
        return [payload for called, payload in self.calls if called == name]

    def created_task_list_ids(self) -> list[str]:
        return [payload["list_id"] for payload in self.calls_named("create_task")]

    def created_task_names(self) -> list[str]:
        return [payload["name"] for payload in self.calls_named("create_task")]


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False
    retained_name: str | None = None
    retained_body: str | None = None
    retained_assignees: tuple[str, ...] | None = None


#: Keyword fragments naming the set of mappings to *spare*. `tasks.md` 2.2
#: fixes that the caller hands the store that set; nothing fixes the name.
_SPARE_WORDS: Final = ("keep", "spare", "exempt", "retain", "preserve", "except")


def _step_id_of(item: Any) -> str:
    """A spared entry, whether it arrived as a step id or as a mapping."""
    return str(getattr(item, "step_id", item))


class _FakeMapping:
    """In-memory stand-in for the two mapping tables.

    Adds the combined replace-and-discard `tasks.md` 2.1 requires. Every
    other method is transcribed from `test_clickup_sync_tags.py`.
    """

    def __init__(self) -> None:
        self._probed: list[str] = []
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}
        self.replacements: list[tuple[str, str]] = []
        #: every call to the combined operation, as it arrived
        self.replace_calls: list[dict[str, Any]] = []
        #: (step_id, task_id) for every mapping the combined operation removed
        self.discarded: list[tuple[str, str]] = []
        #: how many times the list association was written on its own
        self.record_list_calls: list[tuple[ProductId, str]] = []
        #: set to make the combined operation fail, as a transaction that
        #: does not commit would
        self.fail_replacement: Exception | None = None

    def __getattr__(self, name: str) -> Any:
        probed = self.__dict__.get("_probed")
        if probed is not None and not name.startswith("__"):
            probed.append(name)
        raise AttributeError(name)

    @property
    def probed(self) -> tuple[str, ...]:
        return tuple(self._probed)

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
        self.record_list_calls.append((product_id, list_id))
        self.lists[product_id] = list_id

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> _TaskMapping | None:
        return self.tasks.get((product_id, step_id))

    async def tasks_for(self, product_id: ProductId) -> list[_TaskMapping]:
        return [
            mapping
            for (mapped_product, _), mapping in self.tasks.items()
            if mapped_product == product_id
        ]

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None:
        existing = self.tasks.get((product_id, step_id))
        if existing is not None:
            self.replacements.append((existing.task_id, task_id))
        self.tasks[(product_id, step_id)] = _TaskMapping(
            product_id=product_id, step_id=step_id, task_id=task_id
        )

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        self.tasks[(product_id, step_id)].last_observed_closed = closed

    async def record_composition(
        self,
        product_id: ProductId,
        step_id: str,
        *,
        name: str | None = None,
        body: str | None = None,
        assignees: Any = None,
    ) -> None:
        mapping = self.tasks[(product_id, step_id)]
        if name is not None:
            mapping.retained_name = name
        if body is not None:
            mapping.retained_body = body
        if assignees is not None:
            mapping.retained_assignees = tuple(str(item) for item in assignees)

    async def record_assignees(
        self, product_id: ProductId, step_id: str, assignees: Any
    ) -> None:
        self.tasks[(product_id, step_id)].retained_assignees = tuple(
            str(item) for item in assignees
        )

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    # -- the operation this change adds ------------------------------------

    async def replace_list(self, *args: Any, **kwargs: Any) -> None:
        """Record a new list for the launch and discard its task mappings,
        sparing the ones the caller names, as one act.

        Deliberately mutates **nothing** before the failure injection: a
        transaction that does not commit leaves no half of itself applied,
        and that dichotomy is what *The replacement and the discard cannot
        come apart* asserts.
        """
        self.replace_calls.append({"args": args, "kwargs": dict(kwargs)})

        product_id, list_id, spare = self._resolve_replacement(args, kwargs)

        if self.fail_replacement is not None:
            raise self.fail_replacement

        spared = {_step_id_of(item) for item in spare}
        for key in list(self.tasks):
            mapped_product, step_id = key
            if mapped_product != product_id or step_id in spared:
                continue
            self.discarded.append((step_id, self.tasks[key].task_id))
            del self.tasks[key]
        self.lists[product_id] = list_id

    # The operation's name is INVENTED; these aliases are the correction
    # point.
    replace_list_discarding_tasks = replace_list
    replace_list_and_discard_tasks = replace_list
    record_list_discarding_tasks = replace_list
    record_replacement_list = replace_list
    replace_launch_list = replace_list

    def _resolve_replacement(
        self, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[Any, str, Any]:
        """The three arguments, however the caller spelled them."""
        product_id: Any = kwargs.get("product_id") or kwargs.get("launch_id")
        list_id: Any = None
        spare: Any = None
        for key, value in kwargs.items():
            lowered = key.lower()
            if "list" in lowered and "id" in lowered:
                list_id = value
            elif any(word in lowered for word in _SPARE_WORDS):
                spare = value

        positional = list(args)
        if product_id is None and positional:
            product_id = positional.pop(0)
        if list_id is None and positional:
            list_id = positional.pop(0)
        if spare is None and positional:
            spare = positional.pop(0)

        if product_id is None or list_id is None:
            pytest.fail(
                "the mapping store's replace-and-discard was called in a "
                f"shape this double cannot read: args={args!r}, "
                f"kwargs={kwargs!r}. It must carry the launch's product "
                "identifier and the new list identifier. Teaching "
                "`_resolve_replacement` the real shape is a fixture "
                "correction."
            )
        if spare is None:
            # A caller with nothing to spare may legitimately omit it.
            spare = ()
        return product_id, str(list_id), spare

    # -- test-side helpers -------------------------------------------------

    def seed_task(
        self, step_id: str, task_id: str, *, closed: bool = False
    ) -> _TaskMapping:
        mapping = _TaskMapping(
            product_id=PRODUCT_ID,
            step_id=step_id,
            task_id=task_id,
            last_observed_closed=closed,
        )
        self.tasks[(PRODUCT_ID, step_id)] = mapping
        return mapping

    def step_ids(self) -> set[str]:
        return {step_id for (_, step_id) in self.tasks}

    def discarded_step_ids(self) -> set[str]:
        return {step_id for step_id, _ in self.discarded}


class _FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, *, product_id: ProductId, step_id: str, outcome: Any, provenance: Any
    ) -> None:
        self.calls.append(
            {
                "product_id": product_id,
                "step_id": step_id,
                "outcome": outcome,
                "provenance": provenance,
            }
        )


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(
        default_factory=lambda: _FakeCatalog(
            _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)
        )
    )
    members: _FakeMembers = field(default_factory=_members)
    recorder: _FakeRecorder = field(default_factory=_FakeRecorder)


# ---------------------------------------------------------------------------
# The single correction point: how the pass is invoked
# ---------------------------------------------------------------------------


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
    *,
    folder_id: str | None = FOLDER_ID,
) -> None:
    """INVENTED call shape -- see the module docstring.

    An `AttributeError` is turned into a `pytest.fail` naming what the pass
    reached for, because the two operations this change adds are named by
    no artifact: a miss here is a fixture correction
    (`ai-toolkit:testing` failure state 3), and it should say so rather
    than surfacing as an opaque traceback. `pytest.fail` raises a
    `BaseException`, so it is not swallowed by the `pytest.raises(Exception)`
    and `suppress(Exception)` blocks below.
    """
    try:
        await converge_launch(
            launch=launch,
            playbook=playbook,
            clickup=collaborators.clickup,
            mapping=collaborators.mapping,
            read_product=collaborators.catalog,
            members=collaborators.members,
            folder_id=folder_id,
        )
    except AttributeError as error:
        pytest.fail(
            f"the pass reached for something the fakes do not offer: {error!r}. "
            f"ClickUp double probed {collaborators.clickup.probed}; mapping "
            f"double probed {collaborators.mapping.probed}. If that names the "
            "real spelling of the list-state read or of the combined "
            "replace-and-discard, add it to the aliases in `_FakeClickUp` / "
            "`_FakeMapping` -- a fixture correction, not a change to what "
            "these tests assert."
        )


async def _reconcile(
    launch: Launch, playbook: LaunchPlaybook, collaborators: _Collaborators
) -> None:
    """INVENTED call shape -- the single correction point."""
    await reconcile_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        record_outcome=collaborators.recorder,
    )


async def _seed_broken_launch(
    collaborators: _Collaborators, *, deleted: bool = True
) -> None:
    """The state `proposal.md` opens on: a launch recorded against a list
    ClickUp reports as deleted, with the four mappings that list held."""
    if deleted:
        collaborators.clickup.seed_deleted_list(LIST_ID)
    else:
        collaborators.clickup.seed_live_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    collaborators.mapping.record_list_calls.clear()
    collaborators.mapping.seed_task(OPEN_STEP_ID, DEAD_TASK)
    collaborators.mapping.seed_task(OTHER_OPEN_STEP_ID, OTHER_DEAD_TASK)
    collaborators.mapping.seed_task(DONE_STEP_ID, DONE_DEAD_TASK, closed=True)
    collaborators.mapping.seed_task(UNDEFINED_STEP_ID, UNDEFINED_DEAD_TASK)


def _new_list_id(collaborators: _Collaborators) -> str:
    created = collaborators.clickup.calls_named("create_list")
    assert len(created) == 1, (
        f"expected exactly one replacement list to be created, got {created}. "
        f"ClickUp calls were {collaborators.clickup.calls}"
    )
    # The fake returns the identifier it minted; read it back off the
    # recorded association rather than reconstructing it.
    return min(collaborators.clickup.lists.keys() - {LIST_ID})


# ---------------------------------------------------------------------------
# Scenario: An existing list is not recreated (WHEN clause revised)
# ---------------------------------------------------------------------------


async def test_a_list_clickup_reports_as_existing_is_not_recreated() -> None:
    """Scenario: An existing list is not recreated.

    WHEN the reconciliation pass runs, the launch already has a recorded
    list, and ClickUp reports that list as existing
    THEN no new list is created.

    The delta revised this scenario's WHEN: what makes the no-second-list
    rule hold is now ClickUp's report, not the mere presence of a record.
    So the check being *taken* is as much a part of the scenario as the
    absence of a creation, and both are asserted.
    """
    playbook = _playbook((_open_step(),))
    collaborators = _Collaborators()
    collaborators.clickup.seed_live_list(LIST_ID)
    await collaborators.mapping.record_list(PRODUCT_ID, LIST_ID)
    launch = _start(playbook)

    await _converge(launch, playbook, collaborators)
    await _reconcile(launch, playbook, collaborators)

    # SPECIFIED: "Before a launch's projection uses a recorded list, once
    # per pass, the system SHALL establish from ClickUp that the list still
    # exists." Exactly once, over the whole pass -- a second probe in the
    # reconciliation half would make it twice.
    assert collaborators.clickup.calls_named("get_list") == [{"list_id": LIST_ID}], (
        "the recorded list's existence was not established from ClickUp "
        "exactly once over the pass; ClickUp calls were "
        f"{collaborators.clickup.calls}"
    )

    # SPECIFIED: no new list is created.
    assert collaborators.clickup.calls_named("create_list") == []
    # SPECIFIED corollary: the recorded association still names the same
    # list, and nothing was discarded.
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    assert collaborators.mapping.replace_calls == []
    assert collaborators.mapping.discarded == []


# ---------------------------------------------------------------------------
# Scenario: A launch whose list was deleted gets a new one
# ---------------------------------------------------------------------------


async def test_a_launch_whose_list_was_deleted_gets_a_new_one() -> None:
    """Scenario: A launch whose list was deleted gets a new one.

    WHEN the reconciliation pass runs and ClickUp reports the launch's
    recorded list as deleted
    THEN a new list is created in the configured folder, named with the
    product's catalog name and SKU as any launch list is
    AND the launch is recorded against the new list
    AND the launch's task mappings are discarded, except those for
    playbook-defined steps whose recorded outcome is terminal.

    All four mappings the dead list held are seeded, one of each kind the
    requirement distinguishes, so the exception is asserted against a real
    remainder rather than in isolation.
    """
    playbook = _playbook((_open_step(), _other_open_step(), _done_step()))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook, step_id=DONE_STEP_ID, outcome=Satisfied, provenance=_provenance()
    )
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: a new list is created, in the configured folder.
    created = collaborators.clickup.calls_named("create_list")
    assert len(created) == 1, f"expected exactly one list creation, got {created}"
    assert created[0]["folder_id"] == FOLDER_ID

    # SPECIFIED: named with the product's catalog name and SKU "as any
    # launch list is". DERIVED: containment rather than an exact format --
    # no artifact fixes the separator or the ordering. On the SKU, see the
    # module docstring: the bare value is what the recorded requirement
    # obliges, and it is present both before and after PR #81.
    name = created[0]["name"]
    assert PRODUCT_NAME in name, f"the list name carries no product name: {name!r}"
    assert PRODUCT_SKU.value in name, f"the list name carries no SKU: {name!r}"

    # SPECIFIED: the launch is recorded against the new list.
    new_list_id = _new_list_id(collaborators)
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == new_list_id
    assert new_list_id != LIST_ID

    # SPECIFIED: the mapping for a playbook-defined step whose recorded
    # outcome is terminal is NOT discarded -- and still names the task it
    # always named, since sparing it means leaving it alone.
    assert DONE_STEP_ID not in collaborators.mapping.discarded_step_ids(), (
        "the mapping for finished work was discarded; the requirement exempts it"
    )
    spared = await collaborators.mapping.task_for(PRODUCT_ID, DONE_STEP_ID)
    assert spared is not None
    assert spared.task_id == DONE_DEAD_TASK

    # SPECIFIED: the rest are discarded -- the two unfinished steps and the
    # one the playbook does not define.
    assert collaborators.mapping.discarded_step_ids() == {
        OPEN_STEP_ID,
        OTHER_OPEN_STEP_ID,
        UNDEFINED_STEP_ID,
    }


# ---------------------------------------------------------------------------
# Scenario: The replacement and the discard cannot come apart
# ---------------------------------------------------------------------------


async def test_the_replacement_and_the_discard_cannot_come_apart() -> None:
    """Scenario: The replacement and the discard cannot come apart.

    WHEN the reconciliation pass replaces a launch's deleted list and the
    write of that replacement does not complete
    THEN the launch is left recorded against its old list with its task
    mappings intact.

    The store double refuses the combined operation before mutating
    anything, standing in for a transaction that does not commit. What
    this observes at the unit level is the *caller's* half: that the pass
    performs one act rather than ordering two, so there is no window in
    which the launch is recorded against the new list with its mappings
    still intact. The single-commit half -- that the store's own two
    writes land or fail together against a real database -- is asserted in
    `tests/integration/launch/test_clickup_mapping_list_replacement.py`,
    which is the smallest level that can observe it.

    Whether the pass propagates the failure is not asserted: the
    requirement states what the record is left holding, and per-launch
    failure reporting belongs to `contain-a-failing-launch`, which
    `proposal.md` excludes from this change.
    """
    playbook = _playbook((_open_step(), _other_open_step(), _done_step()))
    launch = _start(playbook)
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)
    collaborators.mapping.fail_replacement = _StoreWriteFailed(
        "the replace-and-discard transaction did not commit"
    )
    before = {
        step_id: mapping.task_id
        for (_, step_id), mapping in collaborators.mapping.tasks.items()
    }

    with contextlib.suppress(Exception):
        await _converge(launch, playbook, collaborators)

    # Guard against a vacuous pass: the combined operation must actually
    # have been attempted. A pass that ordered `record_list` and a separate
    # discard would leave this empty -- and would also fail the
    # old-list assertion below, which is the requirement's own dichotomy.
    assert len(collaborators.mapping.replace_calls) == 1, (
        "the replacement was not attempted as one operation; the store "
        f"double saw {collaborators.mapping.replace_calls!r}, and the "
        f"list association was written separately "
        f"{len(collaborators.mapping.record_list_calls)} time(s). "
        f"Mapping double probed {collaborators.mapping.probed}."
    )

    # SPECIFIED: the launch is left recorded against its old list.
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    # SPECIFIED corollary: nothing wrote the association on its own -- the
    # indivisibility the requirement states is not satisfied by two writes
    # that happen to be adjacent.
    assert collaborators.mapping.record_list_calls == []

    # SPECIFIED: with its task mappings intact -- every one of them, still
    # naming the task it named before.
    after = {
        step_id: mapping.task_id
        for (_, step_id), mapping in collaborators.mapping.tasks.items()
    }
    assert after == before
    assert collaborators.mapping.discarded == []


# ---------------------------------------------------------------------------
# Scenario: Steps re-project into the replacement list
# ---------------------------------------------------------------------------


async def test_steps_re_project_into_the_replacement_list() -> None:
    """Scenario: Steps re-project into the replacement list.

    WHEN a launch's deleted list has been replaced and the reconciliation
    pass runs again
    THEN every projectable step whose work is unfinished has a task in the
    new list
    AND each such task begins unobserved, so its first completion is
    recorded as a transition.

    Two unfinished steps, so "every" is asserted over more than one. The
    "recorded as a transition" half is then driven for real: the newly
    created task is closed in ClickUp and the reconciliation half of the
    pass is run, which may only record an outcome because the task's
    retained observed state started as not closed.
    """
    playbook = _playbook((_open_step(), _other_open_step(), _done_step()))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook, step_id=DONE_STEP_ID, outcome=Satisfied, provenance=_provenance()
    )
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)

    await _converge(launch, playbook, collaborators)
    new_list_id = _new_list_id(collaborators)

    # SPECIFIED: every projectable step whose work is unfinished has a task
    # in the new list.
    for step_id in (OPEN_STEP_ID, OTHER_OPEN_STEP_ID):
        mapping = await collaborators.mapping.task_for(PRODUCT_ID, step_id)
        assert mapping is not None, f"{step_id} was not re-projected"
        assert mapping.task_id != DEAD_TASK
        assert mapping.task_id in collaborators.clickup.tasks, (
            f"{step_id}'s mapping names a task that does not exist"
        )
        assert collaborators.clickup.tasks[mapping.task_id].list_id == new_list_id, (
            f"{step_id}'s replacement task is not in the replacement list"
        )
        # SPECIFIED: each such task begins unobserved.
        assert mapping.last_observed_closed is False

    # SPECIFIED: "so its first completion is recorded as a transition" --
    # driven rather than inferred. A task whose retained observed state had
    # been carried over as closed would record nothing here.
    reprojected = await collaborators.mapping.task_for(PRODUCT_ID, OPEN_STEP_ID)
    assert reprojected is not None
    collaborators.clickup.tasks[reprojected.task_id].closed = True
    collaborators.clickup.tasks[reprojected.task_id].status = "complete"

    await _reconcile(launch, playbook, collaborators)

    recorded = [
        call for call in collaborators.recorder.calls if call["step_id"] == OPEN_STEP_ID
    ]
    assert len(recorded) == 1, (
        "closing the re-projected task recorded no transition; the "
        f"recorder saw {collaborators.recorder.calls!r}"
    )
    assert recorded[0]["outcome"] is Satisfied
    assert recorded[0]["provenance"].source == "clickup"


# ---------------------------------------------------------------------------
# Scenario: Finished work is not re-projected into the replacement list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        pytest.param(Satisfied, id="satisfied"),
        pytest.param(
            NotApplicable("single-marketplace product; the node is EU-only"),
            id="not-applicable",
        ),
    ],
)
async def test_finished_work_is_not_re_projected_into_the_replacement_list(
    outcome: Any,
) -> None:
    """Scenario: Finished work is not re-projected into the replacement list.

    WHEN a launch's deleted list is replaced and a projectable step's
    recorded outcome is already terminal
    THEN no task is created for that step in the new list.

    Both outcomes that a *projectable* step can carry terminally are
    exercised. `NotApplicable` is the sharp one `design.md` — Decision 2
    names: work someone judged unnecessary, which a fresh open task would
    re-present as outstanding with nothing saying it was ever settled.
    `Refused` is not exercised -- see the module docstring.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook, step_id=DONE_STEP_ID, outcome=outcome, provenance=_provenance()
    )
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: no task is created for that step in the new list.
    assert not any(
        DONE_STEP_ID in name for name in collaborators.clickup.created_task_names()
    ), (
        "a task was created for work already recorded terminal; created "
        f"names were {collaborators.clickup.created_task_names()!r}"
    )
    mapping = await collaborators.mapping.task_for(PRODUCT_ID, DONE_STEP_ID)
    assert mapping is not None, (
        "the exempt mapping was discarded, so nothing was left to tell the "
        "projection the step's work is finished"
    )
    assert mapping.task_id == DONE_DEAD_TASK

    # Guard against a vacuous pass: the heal really happened, and the
    # unfinished step really did re-project alongside.
    assert len(collaborators.clickup.calls_named("create_list")) == 1
    assert any(
        OPEN_STEP_ID in name for name in collaborators.clickup.created_task_names()
    )


# ---------------------------------------------------------------------------
# Scenario: Finished work of a step the launch is not held to survives the
# replacement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "departure",
    [
        pytest.param("retired", id="retired-out-of-the-served-set"),
        pytest.param("prohibited-tactic", id="hazard-re-authored"),
    ],
)
async def test_finished_work_of_a_step_the_launch_is_not_held_to_survives(
    departure: str,
) -> None:
    """Scenario: Finished work of a step the launch is not held to survives
    the replacement.

    WHEN a launch's deleted list is replaced, a step's recorded outcome is
    terminal, and the playbook defines that step but the launch is not
    currently held to it
    THEN its mapping is not discarded
    AND no task is created for that step should the launch later be held to
    it again.

    Two ways of not being held to a step, both of which a narrower reading
    of the exemption gets wrong (`design.md` — Decision 2b):

    - **retired**: still in `authored_steps`, absent from `served_steps`.
      An exemption ranged over the served or the projectable set discards
      this mapping.
    - **prohibited-tactic**: served, but not projectable -- and, because
      `permissible_terminal_outcomes` is hazard-relative, a step recorded
      `Satisfied` and re-authored this way is no longer *terminal* under
      `_is_terminal`. An exemption judged through that resolution discards
      the mapping. The requirement obliges the judgement to be made
      "without reference to the step's current hazard".

    In both cases the third act is the one that shows the cost: the step
    returns to active human work, and must not be handed a fresh open task
    for work already finished.
    """
    # Act one: the work was finished while the step was ordinary human work.
    active_playbook = _playbook((_open_step(), _done_step()))
    launch = _start(active_playbook)
    launch.record_step_outcome(
        active_playbook,
        step_id=DONE_STEP_ID,
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # Act two: the step is re-authored, so the launch is no longer held to
    # it -- and then its list is deleted and healed.
    if departure == "retired":
        departed = _done_step(status=StepStatus.RETIRED)
    else:
        departed = _done_step(hazard=Hazard.PROHIBITED_TACTIC)
    departed_playbook = _playbook((_open_step(), departed))

    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)

    await _converge(launch, departed_playbook, collaborators)

    # SPECIFIED: its mapping is not discarded.
    assert DONE_STEP_ID not in collaborators.mapping.discarded_step_ids(), (
        f"the mapping for finished work was discarded when the step was "
        f"{departure}; discarded {collaborators.mapping.discarded!r}"
    )
    surviving = await collaborators.mapping.task_for(PRODUCT_ID, DONE_STEP_ID)
    assert surviving is not None
    assert surviving.task_id == DONE_DEAD_TASK

    # Guard against a vacuous pass: the heal happened, and the mappings
    # that are not exempt really were discarded.
    assert len(collaborators.clickup.calls_named("create_list")) == 1
    assert OPEN_STEP_ID in collaborators.mapping.discarded_step_ids()

    # Act three: the step returns to active human work. SPECIFIED: no task
    # is created for it, because the mapping that survived is what tells
    # the projection the work is finished.
    created_before = len(collaborators.clickup.calls_named("create_task"))
    await _converge(launch, active_playbook, collaborators)
    created_after = collaborators.clickup.created_task_names()[created_before:]

    assert not any(DONE_STEP_ID in name for name in created_after), (
        "a returning step was handed a fresh open task for work already "
        f"finished; the second pass created {created_after!r}"
    )
    # And nothing was healed a second time -- the replacement list is alive.
    assert len(collaborators.clickup.calls_named("create_list")) == 1


# ---------------------------------------------------------------------------
# Scenario: A mapping for an undefined step is discarded
# ---------------------------------------------------------------------------


async def test_a_mapping_for_an_undefined_step_is_discarded() -> None:
    """Scenario: A mapping for an undefined step is discarded.

    WHEN a launch's deleted list is replaced and a mapping names a step the
    playbook no longer defines
    THEN that mapping is discarded with the rest.

    The undefined step is seeded with its ClickUp task recorded *closed*,
    so the discard cannot be passing for the trivial reason that nothing
    about the step looked finished: the requirement discards it because
    the playbook does not define it, not because of anything its outcome
    says. Nothing can re-project a step that is not defined, so there is
    no recorded outcome for it either.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook, step_id=DONE_STEP_ID, outcome=Satisfied, provenance=_provenance()
    )
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)
    collaborators.mapping.seed_task(UNDEFINED_STEP_ID, UNDEFINED_DEAD_TASK, closed=True)
    assert UNDEFINED_STEP_ID not in {
        step.identifier for step in playbook.authored_steps
    }

    await _converge(launch, playbook, collaborators)

    # SPECIFIED: that mapping is discarded with the rest.
    assert UNDEFINED_STEP_ID in collaborators.mapping.discarded_step_ids()
    assert await collaborators.mapping.task_for(PRODUCT_ID, UNDEFINED_STEP_ID) is None

    # SPECIFIED corollary: nothing re-projects it -- the loop only reaches
    # defined steps.
    assert not any(
        UNDEFINED_STEP_ID in name for name in collaborators.clickup.created_task_names()
    )
    # And the exemption still held for the step that qualifies for it, so
    # this is a discard of the undefined step and not of everything.
    assert DONE_STEP_ID not in collaborators.mapping.discarded_step_ids()


# ---------------------------------------------------------------------------
# Scenario: Outcomes recorded before the deletion are kept
# ---------------------------------------------------------------------------


async def test_outcomes_recorded_before_the_deletion_are_kept() -> None:
    """Scenario: Outcomes recorded before the deletion are kept.

    WHEN a launch's deleted list is replaced and steps had outcomes
    recorded from tasks in that list
    THEN those recorded outcomes are unchanged.

    Asserted on the provenance as well as the outcome: what the deletion
    ends is the ability to observe *further* transitions, not the record of
    the ones already observed, and a heal that re-derived the outcome from
    the replacement list would show up as a changed `when` or `evidence`
    even where the outcome itself matched.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    provenance = _provenance()
    launch.record_step_outcome(
        playbook, step_id=DONE_STEP_ID, outcome=Satisfied, provenance=provenance
    )
    recorded_before = set(launch.recorded_step_ids)
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)

    await _converge(launch, playbook, collaborators)

    # Guard against a vacuous pass: the list really was replaced.
    assert len(collaborators.clickup.calls_named("create_list")) == 1

    # SPECIFIED: those recorded outcomes are unchanged.
    progress = launch.progress_for(DONE_STEP_ID)
    assert progress is not None, "the recorded outcome was lost with the list"
    assert progress.outcome is Satisfied
    assert progress.provenance.source == provenance.source
    assert progress.provenance.who == provenance.who
    assert progress.provenance.when == provenance.when
    assert progress.provenance.evidence == provenance.evidence
    # SPECIFIED corollary: nothing else was recorded or unrecorded either.
    assert set(launch.recorded_step_ids) == recorded_before


# ---------------------------------------------------------------------------
# Scenario: A failed write is not read as a deletion
# ---------------------------------------------------------------------------


async def test_a_failed_write_is_not_read_as_a_deletion() -> None:
    """Scenario: A failed write is not read as a deletion.

    WHEN the reconciliation pass runs and a write against the launch's list
    fails with "not found" while ClickUp does not report the list as
    deleted
    THEN no new list is created and no task mapping is discarded.

    This is the production traceback `proposal.md` opens on, replayed
    against a list that is *alive*: `create_task` answers `404`, and the
    requirement forbids reading that as the deletion it happened to be on
    that day. A pass that inferred deletion from the write failure --
    the inference `design.md` — Decision 4 rejects -- heals here and fails
    this test.

    Whether the write failure propagates is not asserted; that is
    `contain-a-failing-launch`'s, and `proposal.md` excludes it.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators, deleted=False)
    collaborators.clickup.refuse_writes_into[LIST_ID] = _ClickUpRequestFailed(
        f"404 Not Found: /api/v2/list/{LIST_ID}/task"
    )
    # The mapped task is absent from the live list, so the pass takes the
    # re-projection branch and actually attempts the failing write.
    before = dict(collaborators.mapping.tasks)

    with contextlib.suppress(Exception):
        await _converge(launch, playbook, collaborators)

    # Guard against a vacuous pass: the failing write really was attempted.
    assert collaborators.clickup.calls_named("create_task"), (
        "no write was attempted, so this test observed nothing about how a "
        f"failed one is read; ClickUp calls were {collaborators.clickup.calls}"
    )

    # SPECIFIED: no new list is created.
    assert collaborators.clickup.calls_named("create_list") == []
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    # SPECIFIED: and no task mapping is discarded.
    assert collaborators.mapping.discarded == []
    assert collaborators.mapping.replace_calls == []
    assert collaborators.mapping.tasks == before


# ---------------------------------------------------------------------------
# Scenario: A list whose state cannot be established is not healed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            _ClickUpRequestFailed(f"404 Not Found: /api/v2/list/{LIST_ID}"),
            id="not-found",
        ),
        pytest.param(
            _ClickUpRequestFailed("401 Team not authorized"), id="unauthorized"
        ),
        pytest.param(
            _ClickUpUnreachable("connection failed; no response received"),
            id="unreachable",
        ),
    ],
)
async def test_a_list_whose_state_cannot_be_established_is_not_healed(
    failure: Exception,
) -> None:
    """Scenario: A list whose state cannot be established is not healed.

    WHEN the reconciliation pass cannot establish the state of a launch's
    recorded list, because the request for it fails
    THEN no new list is created and no task mapping is discarded
    AND that launch's pass fails, rather than the failure being read as a
    deletion.

    The `404` case is the one `design.md` — Decision 4 settles explicitly,
    and the one it records a cost for: a list purged from ClickUp's trash
    is not healed here. That cost is stated, not guarded against, so this
    test asserts the stated behaviour rather than the wish.

    SPECIFIED: the pass fails. DERIVED mechanism: it raises, which is how a
    per-launch failure reaches the walk that contains it. Not narrowed to a
    type, because no artifact names one.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)
    collaborators.clickup.unreadable_lists[LIST_ID] = failure
    before = dict(collaborators.mapping.tasks)

    # SPECIFIED: that launch's pass fails.
    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _converge(launch, playbook, collaborators)

    # SPECIFIED: rather than the failure being read as a deletion -- no new
    # list is created.
    assert collaborators.clickup.calls_named("create_list") == []
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    # SPECIFIED: and no task mapping is discarded.
    assert collaborators.mapping.discarded == []
    assert collaborators.mapping.replace_calls == []
    assert collaborators.mapping.tasks == before
    # SPECIFIED corollary: the dead identifier is not used for work either.
    assert collaborators.clickup.calls_named("create_task") == []


# ---------------------------------------------------------------------------
# Scenario: A graduated launch is left alone (the clause this delta adds)
# ---------------------------------------------------------------------------


async def test_a_graduated_launchs_recorded_list_is_not_checked_for_existence() -> None:
    """Scenario: A graduated launch is left alone.

    WHEN the reconciliation pass runs and a launch has reached `graduated`
    THEN no list or task is created or updated for it and no outcome is
    recorded from it
    AND its recorded list is not checked for existence.

    Only the AND is new; the first clause stays covered by
    `test_clickup_sync_projection.py::test_a_graduated_launch_is_left_alone`,
    which this file does not touch. The launch is given a recorded list
    that ClickUp reports as **deleted**, so the short-circuit is asserted
    against the one state that would otherwise cause a heal -- a graduated
    launch with a live list would satisfy the assertion for the wrong
    reason.
    """
    playbook = _playbook((_open_step(), _done_step()))
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)
    before = dict(collaborators.mapping.tasks)

    await _converge(_graduated(playbook), playbook, collaborators)

    # SPECIFIED: its recorded list is not checked for existence.
    assert collaborators.clickup.calls_named("get_list") == [], (
        "a graduated launch's recorded list was read from ClickUp; the "
        f"calls were {collaborators.clickup.calls}"
    )
    # SPECIFIED (carried forward): no list or task is created or updated.
    assert collaborators.clickup.calls == [], (
        f"a graduated launch caused ClickUp calls: {collaborators.clickup.calls}"
    )
    # SPECIFIED corollary: and nothing is healed behind its back.
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    assert collaborators.mapping.tasks == before
    assert collaborators.mapping.replace_calls == []


# ---------------------------------------------------------------------------
# Scenario: Missing folder configuration fails the run (the clause this
# delta adds)
# ---------------------------------------------------------------------------


async def test_missing_folder_configuration_fails_a_launch_needing_a_replacement() -> (
    None
):
    """Scenario: Missing folder configuration fails the run.

    WHEN the reconciliation pass runs, an active launch needs a list, and
    no parent folder is configured
    THEN the pass reports failure rather than skipping the launch silently
    AND this holds equally for a launch needing a list because ClickUp
    reports its recorded one deleted, which is not given its deleted list's
    identifier back.

    Only the AND is new; the base case stays covered by
    `test_clickup_sync_projection.py::test_missing_folder_configuration_fails_the_run`.
    `tasks.md` 3.2 names the trap this guards: "the probe must sit so that
    path is still reached" -- a healing branch placed after the folder
    check would hand the dead identifier back and let the pass project
    into a list that does not exist.

    SPECIFIED: failure is reported. DERIVED mechanism: the pass raises, the
    reading the existing test already records for this project. Not
    narrowed to a type.
    """
    playbook = _playbook((_open_step(), _done_step()))
    launch = _start(playbook)
    collaborators = _Collaborators()
    await _seed_broken_launch(collaborators)
    before = dict(collaborators.mapping.tasks)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _converge(launch, playbook, collaborators, folder_id=None)

    # SPECIFIED: the deleted list's identifier is not given back -- nothing
    # was projected into it, and nothing recorded against it changed.
    assert collaborators.clickup.calls_named("create_task") == []
    assert collaborators.clickup.calls_named("update_task") == []
    assert collaborators.clickup.calls_named("create_list") == []
    assert await collaborators.mapping.list_id_for(PRODUCT_ID) == LIST_ID
    # SPECIFIED corollary: rather than skipping silently -- nothing may be
    # left half-recorded either.
    assert collaborators.mapping.tasks == before
    assert collaborators.mapping.discarded == []


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - **The mid-pass terminality window.** `design.md` — Risks records that a
#   step attested terminal between the launch being read for the walk and
#   the discard has its mapping discarded and a fresh open task created,
#   that this does not self-correct, and that it is *accepted as a live
#   residual rather than guarded*. A test asserting against it would assert
#   a guard the change deliberately did not build.
# - **The orphan list left by a crash between `create_list` and the
#   transaction commit.** `design.md` — Risks accepts this explicitly:
#   "Decision 3 narrows this to the one window that cannot be closed from
#   inside the database -- ClickUp is not a transaction participant -- but
#   does not remove it." The requirement itself says the same ("a
#   replacement list created in ClickUp before the record is written may be
#   left with nothing naming it, and reclaiming such a list is not
#   undertaken here"), so there is no behaviour here to assert.
# - **A list purged from ClickUp's trash.** `design.md` — Decision 4
#   records that such a list presumably answers `404` and is therefore
#   never healed, and that closing the gap "belongs to a different change".
#   The `404` case above asserts the stated behaviour (no heal, the pass
#   fails); nothing asserts a purge is recognised, because nothing states
#   it should be.
# - **`Refused` as a terminal outcome exempting a mapping.** The
#   requirement's enumeration names it, but `permissible_terminal_outcomes`
#   permits it only for a `prohibited-tactic` step and `is_projectable`
#   excludes exactly that hazard, so no projectable step can carry it.
#   `test_finished_work_of_a_step_the_launch_is_not_held_to_survives`
#   covers the reachable half of the same concern -- a `Satisfied` step
#   re-authored `prohibited-tactic` -- which is where the requirement's
#   hazard-independence clause actually bites.
# - **The list name's freedom from the SKU value object's repr.** See the
#   module docstring: PR #81 ships that fix ahead of this change and task
#   5.3 confirms it on the healed launch's list, so asserting it here would
#   turn this file red for a reason that is not healing.
# - **Which ClickUp reads the pass takes in what order**, and whether the
#   state read precedes or follows the task read within `_ensure_list`. No
#   scenario states an ordering; what is stated is that the check happens
#   before a recorded list is *used*, which the folder-configuration and
#   graduated tests observe from the outside.
# ---------------------------------------------------------------------------
