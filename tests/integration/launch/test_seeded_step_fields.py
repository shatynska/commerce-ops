"""The seeded step set after the backfill, read back from Postgres.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers, against the real database after `alembic upgrade head` (schema,
seed and this change's backfill migration):

- MODIFIED requirement *The seeded step set carries the authored v1
  definitions*, restated around `name`: every scenario except *The seed
  runs once*, which is recorded as uncovered in `test-manifest.md` for
  the reason the existing seed file already records (re-running
  `alembic upgrade head` at head is a no-op by construction, an
  assertion that cannot fail).
- MODIFIED requirement *The authored set exercises the full step
  vocabulary*, restated around kind and confirmation and around the
  statuses the migration lands on.
- MODIFIED requirement *Every gate is held by at least one blocking
  step*, as served — now counting only `active` steps.
- `tasks.md` 6.4: integration-tier coverage for the migration's backfill
  against live Postgres. The Migration Plan's step 2 decides three
  things that no obvious column-for-column mapping would produce, and
  each has a test below:
  * `status` is `active` for live `human` rows and `in-development` for
    the two automated ones,
  * `automation_brief` ← `rule_policy` **only for rows becoming
    `automated`** — "Copying `rule_policy` unconditionally produces 95
    human steps carrying a brief, which is an unloadable playbook",
  * `assignees` ← empty, deliberately: "Backfilling an owner ... would
    make the report claim the work is owned when nobody has accepted
    it".

**Level.** Every scenario states a property of what the seed and the
backfill left in the database and of what the adapter serves from it, so
the integration tier is the smallest level that can observe them.

## Read, never written

Every comparison is stated by the delta "before any authored edit", so
this file never writes; assertions filter to the `lp.*` namespace so
`mg.*` residue from the authoring tests cannot leak in. The reference
document is parsed rather than transcribed, with the same grammar and
trimming rule `test_playbook_seed.py` records — re-declared here because
that file must not be edited by this pass.

## INVENTED

- `PlaybookRepository(session).get(version)` for the served playbook, as
  `test_playbook_seed.py` records it.
- The **authored** read, which is new with this change: the served
  queries answer active steps only, and this file's subject is the
  seeded set whole, including the two automated steps the migration
  lands at `in-development`. `_authored_steps()` probes a small set of
  spellings on the playbook and on the repository and fails loudly
  rather than defaulting.

**Expected first-run state.** Absent target: the new fields and the
backfill migration do not exist. Skips where no database is configured,
through the tier's `database_url` gate.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed (this tier skipped
throughout: no database is configured here, so these tests have never
been executed against one).
"""

from __future__ import annotations

import functools
import inspect
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

import pytest
import yaml
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    StepDefinition,
    StepKind,
    StepStatus,
    WindowAnchor,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

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

SEEDED_PREFIX: Final = "lp."

# `seed-the-reference-step-set` added a second, larger seeded set alongside
# this one. It only ever *adds* rows — a step the stored set already carries
# is never touched — so every assertion below stays true of the rows
# `d2f8b3c64e17` seeded, and false of the 255 rows the preparation step adds
# (whose names are authored rather than transcribed, and which are drafts).
#
# So "seeded" is scoped to the migration's own vendored file rather than to
# the `lp.` prefix, which now matches both sets. Nothing here needs to know
# whether the preparation step has run.
_AREA_HEADING: Final = re.compile(r"^- (\d+)\. (.+?)\s*$")
_ROW_ID: Final = re.compile(r"\*\*ID:\*\*\s*(\S+?)\s*$")
_ROW_SOURCE: Final = re.compile(r"\*\*SOURCE:\*\*\s*(.*?)\s*(?:·\s*\*\*|$)")
_BULLET: Final = re.compile(r"^\s*-\s+(.*?)\s*$")

_BUILD_THE_LISTING: Final = "BUILD THE LISTING"

_TERMINAL_MARKS: Final = ";:,."

METRIC_RESTATEMENT_ROW_IDS: Final = (
    "lp.inventory.040",
    "lp.inventory.041",
    "lp.strategy.033",
    "lp.strategy.025",
    "lp.ppc.048",
    "lp.finance.036",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate."""


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _served() -> LaunchPlaybook:
    """The live served playbook — active steps only."""
    async with _session() as session:
        result = await _resolve(
            PlaybookRepository(session).get("any-version-read-through")
        )
        assert isinstance(result, LaunchPlaybook)
        return result


_AUTHORED_ON_PLAYBOOK: Final = ("authored_steps", "all_steps")
_AUTHORED_ON_REPOSITORY: Final = (
    "authored_steps",
    "all_steps",
    "list_authored",
    "load",
)


async def _authored_steps() -> tuple[StepDefinition, ...]:
    """Every authored step definition, whatever its status.

    INVENTED read — see the module docstring. The single correction point
    for how the authored set is reached.
    """
    playbook = await _served()
    for name in _AUTHORED_ON_PLAYBOOK:
        carried = getattr(playbook, name, None)
        if carried is not None:
            steps = await _resolve(carried() if callable(carried) else carried)
            return tuple(steps)
    async with _session() as session:
        repository = PlaybookRepository(session)
        for name in _AUTHORED_ON_REPOSITORY:
            reader = getattr(repository, name, None)
            if reader is None:
                continue
            answered = await _resolve(reader())
            rows = answered[0] if isinstance(answered, tuple) else answered
            steps = [
                row if isinstance(row, StepDefinition) else row.definition
                for row in rows
            ]
            if steps:
                return tuple(steps)
    pytest.fail(
        "no authored read was found on the playbook or the repository — "
        "the admin surface reads every status through one, so correct "
        "this file's probe to the implemented read"
    )


def _seeded(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    found = tuple(
        step for step in steps if step.identifier in _migration_era_identifiers()
    )
    assert found, "no seeded (lp.*) steps were read back"
    return found


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _trimmed(text: str) -> str:
    reduced = text.rstrip()
    while reduced and reduced[-1] in _TERMINAL_MARKS:
        reduced = reduced[:-1].rstrip()
    return reduced


def _reference_rows() -> dict[str, tuple[str, str, str]]:
    source_file = _repository_root() / "docs" / "reference" / "product-launch.md"
    lines = source_file.read_text(encoding="utf-8").splitlines()
    rows: dict[str, tuple[str, str, str]] = {}
    area = ""
    for index, line in enumerate(lines):
        heading = _AREA_HEADING.match(line)
        if heading is not None:
            area = heading.group(2)
            continue
        identifier = _ROW_ID.search(line)
        if identifier is None:
            continue
        citation = _ROW_SOURCE.search(line)
        if citation is None:
            pytest.fail(f"reference row {identifier.group(1)} carries no SOURCE")
        bullet = _BULLET.match(lines[index - 1]) if index else None
        if bullet is None:
            pytest.fail(
                f"reference row {identifier.group(1)} is not preceded by a row "
                "text line"
            )
        rows[identifier.group(1)] = (area, citation.group(1), bullet.group(1))
    if not rows:
        pytest.fail("no ID-bearing rows parsed from the reference document")
    return rows


REFERENCE_ROWS: Final = _reference_rows()

BUILD_THE_LISTING_ROW_IDS: Final = frozenset(
    identifier
    for identifier, (area, _, _) in REFERENCE_ROWS.items()
    if area == _BUILD_THE_LISTING
)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The seeded step set carries the authored v1
# definitions
# ---------------------------------------------------------------------------


async def test_the_playbook_loads_with_steps_after_the_backfill() -> None:
    """Scenario: The shipped playbook loads with steps.

    WHEN the playbook is loaded after seeding
    THEN it loads coherently and its step list is non-empty
    AND every gate has at least one step attached.

    Restated against the backfilled set: the migration rewrites `name`,
    `description`, kind, confirmation, `status` and `automation_brief` in
    place, and every coherence rule is evaluated over the result — so
    this test failing is the first thing a mis-specified backfill breaks.
    """
    playbook = await _served()

    # SPECIFIED: the step list is non-empty, and the seeded rows are what
    # populate it.
    served = tuple(
        step for gate in SPECIFIED_GATE_ORDER for step in playbook.steps_for_gate(gate)
    )
    assert _seeded(served)
    # SPECIFIED: every gate has at least one step attached.
    for gate in SPECIFIED_GATE_ORDER:
        assert playbook.steps_for_gate(gate), f"gate {gate} carries no served step"


async def test_no_gate_opens_for_free_in_the_served_set() -> None:
    """Scenario (MODIFIED requirement *Every gate is held by at least one
    blocking step*): No gate opens for free.

    Restated by this change as counting only **active** steps, which is
    what the backfill has to respect: "Neither automated row blocks a
    gate, so the gate-holding floor is unaffected" — a backfill that
    dropped a *blocking* row to `in-development` would leave its gate
    unheld and make the playbook unloadable.
    """
    playbook = await _served()

    for gate in SPECIFIED_GATE_ORDER:
        holding = [
            step
            for step in playbook.steps_for_gate(gate)
            if step.blocking and step.status is StepStatus.ACTIVE
        ]
        assert holding, f"gate {gate} has no active blocking step"


async def test_build_the_listing_is_fully_represented() -> None:
    """Scenario: BUILD THE LISTING is fully represented.

    WHEN the seeded step set is compared against the ID-bearing rows of
    the reference document's BUILD THE LISTING area
    THEN every such row's ID appears as a step identifier.

    Read over the **authored** set, because a row that the backfill left
    at `in-development` is still a seeded step and the guarantee is about
    the seed, not about what is served.
    """
    identifiers = {step.identifier for step in _seeded(await _authored_steps())}

    missing = sorted(BUILD_THE_LISTING_ROW_IDS - identifiers)
    assert missing == [], f"BUILD THE LISTING rows missing from the seed: {missing}"


async def test_a_step_traces_to_its_source_row() -> None:
    """Scenario: A step traces to its source row.

    WHEN any seeded step is read, before any authored edit to it
    THEN its identifier is a reference-document row ID and its provenance
    reference is that row's source citation
    AND the second segment of that identifier is the step's declared
    discipline.
    """
    for step in _seeded(await _authored_steps()):
        assert step.identifier in REFERENCE_ROWS, (
            f"{step.identifier} is not a reference-document row ID"
        )
        _, citation, _ = REFERENCE_ROWS[step.identifier]
        assert step.provenance == citation
        assert step.identifier.split(".")[1] == step.discipline.value


async def test_a_step_states_its_work_without_the_source_document() -> None:
    """Scenario: A step states its work without the source document.

    WHEN any seeded step is read
    THEN its **name** is non-empty.

    The requirement moves from description to name; the description is
    now optional and the migration sets it to null, so an implementation
    that carried this assertion across unchanged would be asserting
    something the migration deliberately makes false.
    """
    for step in _seeded(await _authored_steps()):
        assert step.name and step.name.strip(), f"{step.identifier} carries no name"


async def test_every_name_re_derives_from_its_reference_row() -> None:
    """Scenario: Every description re-derives from its reference row
    (retained scenario title; the field is now the name).

    WHEN every seeded step's name, before any authored edit to it, is
    compared against the text of the reference row its identifier names,
    reduced by the trimming rule
    THEN each name equals that row's trimmed text exactly.

    This is the check that makes the backfill's `name` ← `description`
    move verifiable rather than trusted: `design.md`'s risk register
    leans on it — "a mistake is detectable by the existing re-derivation
    scenario rather than silent".
    """
    for step in _seeded(await _authored_steps()):
        _, _, text = REFERENCE_ROWS[step.identifier]
        assert step.name == _trimmed(text), (
            f"{step.identifier}: name {step.name!r} does not re-derive from "
            f"its reference row {_trimmed(text)!r}"
        )


async def test_a_gate_authored_condition_is_not_duplicated_as_a_step() -> None:
    """Scenario: A gate-authored condition is not duplicated as a step.

    WHEN the seeded step identifiers are compared against the reference
    rows that restate a gate's authored metric conditions
    THEN none of those rows' IDs appears as a step identifier.
    """
    identifiers = {step.identifier for step in _seeded(await _authored_steps())}

    duplicated = sorted(set(METRIC_RESTATEMENT_ROW_IDS) & identifiers)
    assert duplicated == [], f"metric restatements seeded as steps: {duplicated}"


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The authored set exercises the full step vocabulary
# ---------------------------------------------------------------------------


async def test_every_timing_anchor_kind_is_represented() -> None:
    """Scenario: Anchor kinds are all present."""
    kinds = {type(step.timing_anchor) for step in _seeded(await _authored_steps())}

    for anchor in (OffsetAnchor, WindowAnchor, OpenEndedAnchor, RecurringAnchor):
        assert anchor in kinds, f"no seeded step carries a {anchor.__name__}"


async def test_every_discipline_is_represented() -> None:
    """Scenario: Every discipline appears."""
    disciplines = {step.discipline for step in _seeded(await _authored_steps())}

    missing = sorted(
        discipline.value for discipline in Discipline if discipline not in disciplines
    )
    assert missing == [], f"disciplines with no seeded step: {missing}"


async def test_kinds_confirmation_and_the_compliance_hazard_are_represented() -> None:
    """Scenario: Execution modes and the compliance hazard are
    represented (retained scenario title; the vocabulary is now kind and
    confirmation).

    WHEN the seeded step set is grouped by kind and confirmation and
    filtered by hazard
    THEN `human` and `automated` are each represented, an automated step
    needing confirmation and one not needing it are both present, and at
    least one `compliance-obligation` step exists.

    This is the migration's vocabulary mapping made checkable: the one
    `ai-assisted` row becomes `automated` needing confirmation and the
    one `automated` row becomes `automated` without it, so a mapping that
    collapsed both to the same confirmation value fails here.
    """
    steps = _seeded(await _authored_steps())

    kinds = {step.kind for step in steps}
    assert StepKind.HUMAN in kinds
    assert StepKind.AUTOMATED in kinds

    automated = [step for step in steps if step.kind is StepKind.AUTOMATED]
    assert any(step.needs_confirmation for step in automated), (
        "no seeded automated step needs confirmation"
    )
    assert any(not step.needs_confirmation for step in automated), (
        "every seeded automated step needs confirmation"
    )

    assert any(step.hazard is Hazard.COMPLIANCE_OBLIGATION for step in steps)


async def test_prohibited_tactics_are_present_and_never_block() -> None:
    """Scenario: Prohibited tactics are present and never block."""
    steps = _seeded(await _authored_steps())

    tactics = [step for step in steps if step.hazard is Hazard.PROHIBITED_TACTIC]
    assert tactics, "no seeded step carries the prohibited-tactic hazard"
    assert [step.identifier for step in tactics if step.blocking] == []


async def test_every_seeded_human_step_is_active_and_the_automated_ones_are_not() -> (
    None
):
    """Requirement statement: "Every seeded `human` step SHALL be
    `active`. The seeded `automated` steps SHALL be `in-development`: no
    automation runtime exists yet, so no handler can be registered for
    them, and `active` would be a claim that something resolves them."

    Migration Plan step 2's `status` decision, made checkable. A backfill
    setting every row `active` would claim two steps are resolved by code
    that does not exist; one setting every row `in-development` would
    unhold every gate.
    """
    steps = _seeded(await _authored_steps())

    wrongly_inactive = [
        step.identifier
        for step in steps
        if step.kind is StepKind.HUMAN
        and step.status not in (StepStatus.ACTIVE, StepStatus.RETIRED)
    ]
    assert wrongly_inactive == [], (
        f"seeded human steps left out of the served set: {wrongly_inactive}"
    )

    automated = [step for step in steps if step.kind is StepKind.AUTOMATED]
    assert automated, "the seed carries no automated step"
    assert [
        step.identifier for step in automated if step.status is StepStatus.ACTIVE
    ] == [], "a seeded automated step was activated with no handler registered"
    # SPECIFIED: "Neither is a blocking step, so the gate-holding floor is
    # unaffected — which is what makes this the honest migration rather
    # than a compromise."
    assert [step.identifier for step in automated if step.blocking] == []


# ---------------------------------------------------------------------------
# The backfill's three non-obvious decisions (`tasks.md` 3.2 / 6.4)
# ---------------------------------------------------------------------------


async def test_no_seeded_human_step_carries_an_automation_brief() -> None:
    """Migration Plan step 2: "`automation_brief` ← `rule_policy` **only
    for rows becoming `automated`**; null on `human` rows, which the
    rules forbid from carrying one."

    `tasks.md` 3.2 states the consequence of getting this wrong outright:
    "Copying `rule_policy` unconditionally produces 95 human steps
    carrying a brief, which is an unloadable playbook." The load would
    fail before this assertion could — so this test's value is that it
    names *which* rows are at fault rather than reporting an aggregate
    failure.
    """
    offenders = [
        step.identifier
        for step in _seeded(await _authored_steps())
        if step.kind is StepKind.HUMAN
        and (step.automation_brief is not None or step.handler is not None)
    ]
    assert offenders == [], (
        f"seeded human steps carrying automation fields: {offenders}"
    )


async def test_every_seeded_automated_step_carries_its_brief() -> None:
    """Migration Plan step 2, the other half: the brief is carried across
    from `rule_policy` for rows becoming `automated`.

    Both automated rows land at `in-development`, which is beyond
    `draft`, so each owes a brief — a backfill that dropped `rule_policy`
    entirely would produce a set that does not load.
    """
    automated = [
        step
        for step in _seeded(await _authored_steps())
        if step.kind is StepKind.AUTOMATED and step.status is not StepStatus.RETIRED
    ]
    assert automated, "the seed carries no automated step"
    for step in automated:
        assert step.automation_brief, (
            f"{step.identifier} is automated and beyond draft with no brief"
        )


async def test_migrated_steps_are_unowned_and_carry_no_description() -> None:
    """Migration Plan step 2: "`description` ← null" and "`assignees` ←
    empty. The 95 migrated human steps are active and unowned, and the
    readiness report says so. Backfilling an owner — the roster's only
    person — would make the report claim the work is owned when nobody
    has accepted it, which is the honest signal this change exists to
    produce."

    A backfill that copied the row text into both `name` and
    `description` would double every ClickUp task's body, and one that
    assigned the roster's only person would silence the report this
    change exists to produce. Neither is a load-time fault, so nothing
    else in this suite would notice.
    """
    for step in _seeded(await _authored_steps()):
        assert tuple(step.assignees) == (), (
            f"{step.identifier} was backfilled with an owner nobody chose"
        )
        assert step.description is None, (
            f"{step.identifier} was backfilled with a description: {step.description!r}"
        )


# ---------------------------------------------------------------------------
# The readiness report over the seeded set
# ---------------------------------------------------------------------------

_REPORT_NAMES: Final = (
    "report_activation_blockers",
    "report_what_blocks_activation",
    "report_blocked_activations",
    "report_steps_not_ready_to_activate",
)


class _Person:
    """A roster row for the report's collaborator.

    The report is a function of the step set, the roster and the handler
    registry; the *seeded set* is what this file has under test, so the
    other two are doubles here rather than live reads — a live roster
    would make the assertion depend on who happens to be on it.
    """

    def __init__(self, person_id: str, display_name: str) -> None:
        self.id = person_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeRoster:
    async def list_people(self) -> tuple[_Person, ...]:
        return ()

    people = list_people

    async def __call__(self) -> tuple[_Person, ...]:
        return await self.list_people()


class _EmptyRegistry:
    """No handler is registered: `tasks.md` states outright that "no
    automation runtime exists yet"."""

    def __contains__(self, name: object) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter(())

    def names(self) -> frozenset[str]:
        return frozenset()


async def test_outstanding_readiness_decisions_stay_visible() -> None:
    """Scenario: Outstanding rule-policy decisions stay visible (retained
    scenario title; the report's subject is now what blocks activation).

    WHEN the report of what blocks activation runs over the authored set
    while any step cannot yet be made `active`
    THEN it lists exactly those steps.

    Over the seeded set that is two populations, and both are the
    migration's deliberate residue: the automated steps, which name no
    handler any deployment registers, and the 95 `active` `human` steps
    the backfill left unowned — "the readiness report says so ...
    which is the honest signal this change exists to produce".
    """
    report = None
    for name in _REPORT_NAMES:
        report = getattr(launch_application, name, None)
        if report is not None:
            break
    if report is None:
        pytest.fail(
            "the launch application surface exports no report of what "
            f"blocks activation under any of {_REPORT_NAMES}"
        )

    steps = _seeded(await _authored_steps())
    rows = list(
        await _resolve(
            report(steps=steps, roster=_FakeRoster(), handlers=_EmptyRegistry())
        )
    )
    reported = {getattr(row, "identifier", None) for row in rows}

    automated = [step for step in steps if step.kind is StepKind.AUTOMATED]
    assert automated, "the seed carries no automated step"
    for step in automated:
        assert step.identifier in reported, (
            f"{step.identifier} names a handler nothing registers and is "
            "not reported as blocked"
        )

    unowned_active = [
        step
        for step in steps
        if step.kind is StepKind.HUMAN
        and step.status is StepStatus.ACTIVE
        and not tuple(step.assignees)
    ]
    assert unowned_active, (
        "the backfill left no unowned active human step, so this "
        "assertion would pass vacuously — see the Migration Plan"
    )
    for step in unowned_active:
        assert step.identifier in reported, (
            f"{step.identifier} is active and unowned and is not reported"
        )


# Cached because the call sites below sit inside comprehension conditions,
# where an uncached read re-parses a 43 KB file once per step — 97 parses per
# test, and ~6 s added to each.
@functools.cache
def _migration_era_identifiers() -> frozenset[str]:
    document = yaml.safe_load(
        (_repository_root() / "alembic" / "data" / "playbook_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    return frozenset(step["identifier"] for step in document["steps"])
