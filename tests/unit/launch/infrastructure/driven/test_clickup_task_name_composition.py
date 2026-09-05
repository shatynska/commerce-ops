"""The composed shape of a projected task's name, and its shortened shape.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-clickup-sync/spec.md`

Second test-writing pass. The first pass covered *that* a projected task's
name leads with the description and ends with the identifier, and *that* an
over-long name is shortened and its full description carried in the task's
body — see
`tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py`. It
could go no further, because the delta then fixed neither the joining text
nor the cut point, and that file records both as unresolved.

The delta has since fixed all of it. This file covers what became
assertable:

- **The separator is normative.** "then ` · ` (a space, a middle dot, a
  space), then the step's identifier" is now in the delta itself, not only
  in `design.md` Decision 4. The first pass's separator assertion was
  labelled DERIVED; the same value is now SPECIFIED.
- **The composed name is compositional.** "Before any shortening under the
  rule below, the name SHALL consist of exactly those three parts and no
  further element: the step's discipline SHALL NOT be appended as a further
  element of the name."
- **That constrains composition, not vocabulary.** "This constrains what
  the system composes, not what a description happens to say — a
  description whose own wording mentions its discipline is unaffected."
- **The shortened shape is fixed.** "the step's description cut at its end,
  then `…` marking that it was cut, then ` · ` and the step's identifier in
  full", and "cut to the longest leading portion that leaves the whole
  composed name within the limit, so that shortening surrenders no more of
  the wording than the limit requires".
- **A task whose name fits is created without a body.** "the body carries
  the description only where the name could not."

**Why an equality, and never an absence.** The compositional clause is
asserted here as `name == description + " · " + identifier`. It is
deliberately *not* asserted as "the discipline word does not appear in the
name": the delta's own carve-out says a description may legitimately
contain its discipline's word, so an absence assertion would fail on a
conformant name. The equality forbids an appended element without
constraining what the description may say, which is exactly the clause's
own distinction. `test_the_discipline_does_not_appear_in_the_task_name` in
the first pass's file takes the absence form and is listed in
`test-manifest.md` as an obsolete-test candidate for that reason; this pass
did not edit it.

**The limit is read from the implementation's own named constant** rather
than hard-coded. `design.md` Decision 4 now records the measured number
(2048 characters, ClickUp rejecting rather than truncating, applied as
Python `len()` characters) and `tasks.md` 1.1 requires it expressed "as a
named constant, not a bare literal" — but no artifact fixes the constant's
*name*, so `_task_name_limit()` locates it by shape, as the first pass did.
That remains an unresolved project question in `test-manifest.md`.

**The doubles and the call shape are inherited from
`test_clickup_sync_projection.py`** via the first pass's naming file, which
records them as INVENTED (`converge_launch(launch=, playbook=, clickup=,
mapping=, read_product=, folder_id=)`, and the ClickUp port's operations).
They are re-declared here rather than imported, matching this project's
existing per-file test-fixture convention, and so that this file does not
depend on a file whose own tests are candidates for revision. Correcting
any name or call shape is a fixture correction (failure state 3 in
`ai-toolkit:testing`); changing what these tests assert about the resulting
name or body is not.

**Level.** Every outcome is observable from one convergence pass against a
fake ClickUp and a fake mapping store — no HTTP, no Postgres — so the fast
mocked unit tier is the smallest level that can observe it.

At the time of writing `StepDefinition` has no `description` field and
`_task_name` composes something else, so these tests are expected to fail
on an absent target rather than on a wrong value.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 585 passed, 23 failed. All 23
failures are the first pass's own tests, failing on the same absent field.
`tests/integration` was not run: it needs a live Postgres, unavailable
here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven import clickup_sync
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import LAUNCH_DATE, PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import CreatedTask as _CreatedTask
from tests.support.values import FakeTask as _FakeTask
from tests.support.values import TaskMapping as _TaskMapping

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"

STEP_ID: Final = "lp.creative.008"
STEP_DESCRIPTION: Final = (
    "Main image designed to be scroll-stopping and explicitly different "
    "from competitors, not blending in"
)

# SPECIFIED (delta): "then ` · ` (a space, a middle dot, a space), then the
# step's identifier". Normative in the delta as of its third review pass;
# the first pass could only derive this from `design.md`.
SEPARATOR: Final = " · "

# SPECIFIED (delta): "then `…` marking that it was cut". One character.
ELLIPSIS: Final = "…"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": STEP_DESCRIPTION,
            "discipline": Discipline("creative"),
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated, so the sync never projects a filler and
    every projection assertion is untouched by them."""
    return _build_hold(
        gate,
        discipline=Discipline("creative"),
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        name=STEP_DESCRIPTION,
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return _build_playbook(
        *_fill(steps),
        filler=_hold,
    )


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (inherited — see the module docstring)
# ---------------------------------------------------------------------------


class _FakeCatalog:
    def __init__(self, product: _CatalogProduct) -> None:
        self._product = product

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return self._product


def _due_date_in(fields: dict[str, Any]) -> tuple[bool, Any]:
    for key, value in fields.items():
        if "due" in key.lower():
            return True, value
    return False, None


class _FakeClickUp:
    """In-memory ClickUp, recording every call — including task bodies."""

    def __init__(self) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    async def read_list_state(self, list_id: str) -> ClickUpListState:
        """Every list this file uses is one that still exists.

        `heal-a-launchs-deleted-list` makes the projection verify a
        recorded list before it uses it, so a double that cannot answer
        this stops the pass before any scenario here is reached. Nothing
        below asserts on the answer -- the deleted case belongs to
        `test_clickup_sync_list_healing.py`.
        """
        return ClickUpListState(deleted=False)

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        self.calls.append(
            (
                "create_task",
                {
                    "list_id": list_id,
                    "name": name,
                    "description": description,
                    **fields,
                },
            )
        )
        task_id = self._identifier("task")
        present, due = _due_date_in(fields)
        self.tasks[task_id] = _FakeTask(
            id=task_id,
            name=name,
            list_id=list_id,
            description=description,
            due_date=due if present else None,
        )
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        task = self.tasks[task_id]
        present, due = _due_date_in(fields)
        if present:
            task.due_date = due
        if "name" in fields:
            task.name = fields["name"]
        if "status" in fields:
            task.status = fields["status"]
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        self.calls.append(("list_tasks", {"list_id": list_id}))
        return [task for task in self.tasks.values() if task.list_id == list_id]

    def calls_named(self, name: str) -> list[Any]:
        return [payload for called, payload in self.calls if called == name]


class _FakeMapping:
    def __init__(self) -> None:
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}
        self.replacements: list[tuple[str, str]] = []

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def replace_list_discarding_tasks(
        self,
        product_id: ProductId,
        list_id: str,
        *,
        spare: Sequence[str] = (),
    ) -> None:
        """Present so this double still stands in for the whole
        `MappingStore` port, which `heal-a-launchs-deleted-list` widened.
        No scenario in this file replaces a list; the behaviour is
        exercised in `test_clickup_sync_list_healing.py`."""
        spared = {str(step_id) for step_id in spare}
        self.tasks = {
            key: mapped
            for key, mapped in self.tasks.items()
            if key[0] != product_id or key[1] in spared
        }
        self.lists[product_id] = list_id

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
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
        """`move-playbook-steps-to-postgres`: a system write of a field
        updates that field's retained value; `None` leaves it untouched."""
        mapping = self.tasks[(product_id, step_id)]
        if name is not None:
            mapping.retained_name = name
        if body is not None:
            mapping.retained_body = body
        if assignees is not None:
            mapping.retained_assignees = tuple(str(item) for item in assignees)

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None


@dataclass
class _Collaborators:
    clickup: _FakeClickUp = field(default_factory=_FakeClickUp)
    mapping: _FakeMapping = field(default_factory=_FakeMapping)
    catalog: _FakeCatalog = field(
        default_factory=lambda: _FakeCatalog(
            _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)
        )
    )


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def _converge(
    launch: Launch,
    playbook: LaunchPlaybook,
    collaborators: _Collaborators,
) -> None:
    """INVENTED call shape — the single correction point (see docstring)."""
    await converge_launch(
        launch=launch,
        playbook=playbook,
        clickup=collaborators.clickup,
        mapping=collaborators.mapping,
        read_product=collaborators.catalog,
        folder_id=FOLDER_ID,
    )


async def _created_task(step: StepDefinition) -> dict[str, Any]:
    """Project one step and return the single `create_task` call made."""
    playbook = _playbook(steps=(step,))
    collaborators = _Collaborators()

    await _converge(_start(playbook), playbook, collaborators)

    created = collaborators.clickup.calls_named("create_task")
    assert len(created) == 1, f"expected exactly one task creation, got {created}"
    return dict(created[0])


def _task_name_limit() -> int:
    """The implementation's own task-name limit constant.

    `tasks.md` 1.1 requires the measured ClickUp limit (2048 characters,
    `design.md` Decision 4) to be expressed as a named constant in
    `clickup_sync.py`. Its *name* is not fixed by any artifact, so it is
    located by shape: a public, module-level, non-boolean integer whose
    name mentions the task name. Reading it rather than hard-coding 2048
    keeps this file's assertions about the *rule* rather than about the
    number.
    """
    candidates = {
        name: value
        for name, value in vars(clickup_sync).items()
        if not name.startswith("_")
        and isinstance(value, int)
        and not isinstance(value, bool)
        and "NAME" in name.upper()
    }
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    pytest.fail(
        "expected exactly one public integer task-name-limit constant in "
        f"clickup_sync (tasks.md 1.1), found: {sorted(candidates)}"
    )


def _overhead() -> int:
    """What a shortened name spends on everything but the description."""
    return len(ELLIPSIS) + len(SEPARATOR) + len(STEP_ID)


def _long_description(limit: int) -> str:
    """A one-line description long enough to force shortening.

    Built so the cut point falls **mid-word**: both the last kept character
    and the first dropped one are non-whitespace. That matters for two
    reasons. It keeps the assertions away from a case no artifact settles —
    whether a cut landing on a space keeps or trims that space — and it
    makes the exactness assertion discriminating, since an implementation
    that backed the cut off to the previous word boundary would surrender
    more of the wording than the limit requires and would be caught.

    The leading `x` padding is fixture mechanics: it slides the wording
    relative to the cut point until the boundary is clean.
    """
    unit = "Long reference-row wording that keeps going and going. "
    boundary = limit - _overhead()
    for pad in range(len(unit)):
        candidate = ("x" * pad) + unit * ((limit // len(unit)) + 3)
        if not candidate[boundary - 1].isspace() and not candidate[boundary].isspace():
            return candidate
    pytest.fail("could not build a description whose cut point falls mid-word")


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Human-attested steps are projected as tasks
# ---------------------------------------------------------------------------


async def test_the_composed_name_is_exactly_description_separator_identifier() -> None:
    """Scenario: A human-attested step gets a task (composed form).

    WHEN the reconciliation pass runs and a `human-attested` step of an
    active launch has no recorded task
    THEN a task named with the step's description, then ` · `, then its
    identifier is created in the launch's list.

    Asserted as a whole-string equality because the delta now fixes all
    three parts *and* forbids a fourth: "Before any shortening under the
    rule below, the name SHALL consist of exactly those three parts and no
    further element". A test asserting only that the name starts with the
    description and ends with the identifier — which is what the first pass
    could assert — permits an extra element in the middle.
    """
    created = await _created_task(_step())

    # SPECIFIED: exactly those three parts, in that order, and no further
    # element. The separator itself is SPECIFIED as of this revision of the
    # delta ("then ` · ` (a space, a middle dot, a space)"), where the first
    # pass could only derive it from design.md Decision 4.
    assert created["name"] == f"{STEP_DESCRIPTION}{SEPARATOR}{STEP_ID}"


async def test_the_discipline_is_not_appended_as_a_further_element() -> None:
    """Scenario: A human-attested step gets a task (second THEN).

    WHEN the reconciliation pass runs and a `human-attested` step of an
    active launch has no recorded task
    THEN the step's discipline is not appended as a further element of that
    name.

    The step is given a discipline (`ppc`) that neither its description nor
    its identifier's second segment (`creative`) names, so a name still
    carrying the discipline is detectable — which it would not be for a
    step whose discipline and identifier segment agree.

    The assertion is the same compositional equality as above, applied to
    this step, and **not** an assertion that the string `ppc` is absent
    from the name. The delta is explicit that the clause "constrains what
    the system composes, not what a description happens to say", so an
    absence assertion would fail on a conformant name — see the next test,
    and the module docstring.
    """
    created = await _created_task(_step(discipline=Discipline("ppc")))

    # SPECIFIED: exactly the three parts — so nothing was appended, whatever
    # the step's discipline is.
    assert created["name"] == f"{STEP_DESCRIPTION}{SEPARATOR}{STEP_ID}"


async def test_a_description_naming_its_own_discipline_is_composed_unaltered() -> None:
    """Requirement clause: the constraint is on composition, not wording.

    "This constrains what the system composes, not what a description
    happens to say — a description whose own wording mentions its
    discipline is unaffected."

    The step's discipline is `ppc` and its description says "PPC" in its
    own wording. The composed name therefore contains the discipline word,
    legitimately. This test fails for an implementation that strips the
    discipline out of the description to satisfy the drop-the-discipline
    rule, and it is the reason the tests above assert an equality rather
    than an absence.
    """
    description = "PPC campaigns structured before launch, not after reviews land"
    created = await _created_task(_step(discipline=Discipline("ppc"), name=description))

    # SPECIFIED: the description is composed into the name unaltered — the
    # discipline word it contains is the description's, not an appended
    # element, and nothing removes it.
    assert created["name"] == f"{description}{SEPARATOR}{STEP_ID}"


async def test_a_task_whose_name_fits_is_created_without_a_body() -> None:
    """Requirement clause: the body carries the description only where the
    name could not.

    "A task whose composed name is within the limit SHALL be created
    without a body: the body carries the description only where the name
    could not."

    Newly stated in the delta; the first pass recorded "whether a task body
    is written when the name already fits" as deliberately untested,
    because at that point a body written in every case violated nothing.

    Asserted as falsy rather than as `is None`, because "without a body"
    does not distinguish an omitted argument from an empty one, and no
    artifact does either.
    """
    limit = _task_name_limit()
    assert len(STEP_DESCRIPTION) + len(SEPARATOR) + len(STEP_ID) <= limit, (
        "the fixture description is not within the limit, so this test would "
        "be exercising the shortening rule instead"
    )

    created = await _created_task(_step())

    # DERIVED (unresolved project question 5 in test-manifest.md): the task's
    # body is `create_task`'s `description` argument, the shape
    # `tests/unit/shared/infrastructure/driven/test_clickup_client.py`
    # records.
    # SPECIFIED: no body is set when the name fits.
    assert not created["description"], (
        f"a body was written for a task whose name fits: {created['description']!r}"
    )


async def test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier() -> None:
    """Scenario: An over-long name is shortened rather than failing.

    WHEN a task is projected for a step whose composed name exceeds the
    length the task system accepts
    THEN the task is created with a shortened name that fits, ending in
    `… · ` followed by the step's identifier in full.

    The delta now fixes the shortened *shape*, which the first pass
    recorded as unassertable: the description cut at its end, then `…`
    marking the cut, then ` · ` and the identifier in full. Asserted here as
    the shape, and in the next test as the exact cut point, so that the
    weaker fact survives if the exactness assertion is ever superseded.
    """
    limit = _task_name_limit()
    description = _long_description(limit)
    assert len(description) + len(SEPARATOR) + len(STEP_ID) > limit, (
        "the fixture description is not long enough to exceed the limit"
    )

    created = await _created_task(_step(name=description))
    name = created["name"]

    # SPECIFIED: "no step fails to project merely because its description is
    # long" — a task exists at all.
    # SPECIFIED: the name fits. `design.md` Decision 4 states the constant is
    # applied as Python `len()` characters.
    assert len(name) <= limit, (
        f"the composed name was not shortened to the {limit}-character limit: "
        f"{len(name)} characters"
    )
    # SPECIFIED: ending in `… · ` followed by the step's identifier in full.
    assert name.endswith(f"{ELLIPSIS}{SEPARATOR}{STEP_ID}"), (
        f"the shortened name does not end in the specified shape: ...{name[-40:]!r}"
    )
    # SPECIFIED: what precedes the ellipsis is the description *cut at its
    # end* — a leading portion of it, not a summary, not the middle, and not
    # empty.
    cut = name[: -len(f"{ELLIPSIS}{SEPARATOR}{STEP_ID}")]
    assert cut, "the shortened name surrendered the whole description"
    assert description.startswith(cut), (
        "the retained portion is not a leading portion of the description: "
        f"{cut[-40:]!r}"
    )


async def test_the_shortened_name_surrenders_no_more_than_the_limit_requires() -> None:
    """Scenario: An over-long name is shortened rather than failing (2nd AND).

    AND no more of the description is surrendered than the limit requires.

    "The description SHALL be cut to the longest leading portion that
    leaves the whole composed name within the limit." Under `len()`
    characters (`design.md` Decision 4) that fixes the cut exactly: one more
    character of the description would push the composed name past the
    limit, so the retained portion is the description's first
    `limit - len('… · ' + identifier)` characters.

    The fixture's cut point falls mid-word (see `_long_description`), so an
    implementation retreating to the previous word boundary — a plausible
    reading of "cut at its end" that the delta forecloses — fails here while
    still passing the shape test above.
    """
    limit = _task_name_limit()
    description = _long_description(limit)
    tail = f"{ELLIPSIS}{SEPARATOR}{STEP_ID}"
    expected_cut = description[: limit - len(tail)]

    created = await _created_task(_step(name=description))

    # SPECIFIED: the longest leading portion that still fits.
    assert created["name"] == expected_cut + tail
    # SPECIFIED, restated as the property the equality encodes: one more
    # character of the description would not have fitted.
    assert len(created["name"]) == limit


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - A cut point landing on whitespace — whether the retained portion keeps
#   its trailing space before the `…` or has it trimmed. No artifact says,
#   and the fixture is built to avoid the case rather than to assert an
#   answer to it.
# - Whether the limit is counted in characters, bytes, or UTF-16 units.
#   `design.md` Decision 4 states honestly that its measurement ladder was
#   ASCII-only and that the constant "is therefore applied as Python
#   `len()` characters"; these tests read that same unit, so they cannot
#   independently establish it, and at a real worst case of 271 characters
#   the distinction cannot bite.
# - That ClickUp rejects rather than truncates an over-long name (`HTTP
#   400`, `INPUT_005`). That is a fact about the live platform, established
#   by measurement in `tasks.md` 1.1; a fake cannot re-establish it, and
#   the rule under test exists precisely so it is never reached.
# - The five unchanged scenarios of this requirement, covered in
#   `test_clickup_sync_projection.py`, and the two never-rewrite scenarios,
#   covered in `test_clickup_task_naming.py`. Re-asserting them here would
#   duplicate coverage rather than add it.
# - Whether a *shortened* name's body is the full description. Covered by
#   `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`
#   from the first pass.
