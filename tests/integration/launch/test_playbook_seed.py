"""The seeded step set, read back from Postgres through the served playbook.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-playbook/spec.md`

Covers, against the real database after `alembic upgrade head` (schema +
seed migrations, `tasks.md` 2.1–2.3):

- MODIFIED requirement *The shipped playbook carries the authored step
  set* (renamed at apply time to "The seeded step set carries the
  authored v1 definitions") — every scenario except *The seed runs once*,
  which is recorded as uncovered in the manifest: forcing the seed
  revision to re-execute needs downgrade/upgrade cycling around a
  revision identifier that does not exist yet, and re-running
  `alembic upgrade head` at head is a no-op by construction, an
  assertion that cannot fail.
- MODIFIED requirement *Every gate is held by at least one blocking
  step* — *No gate opens for free*, as served from the seeded store.
- MODIFIED requirement *The authored set exercises the full step
  vocabulary* — all five scenarios, the undecided-rule-policies report
  now running "over the served playbook".
- MODIFIED requirement *Playbooks are versioned* — the serving half of
  *The loaded playbook reports its version* (the version now travels
  with the stored step set, not an authored YAML constant).

**Level.** Every scenario here states a property of what the seed
delivered to the database and what the adapter serves from it, so the
integration tier is the smallest level that can observe them. These are
the seeded-store successors of the YAML-era files
`test_shipped_playbook_steps.py`, `test_shipped_playbook_descriptions.py`
and `test_shipped_step_identifier_discipline.py` in
`tests/unit/launch/infrastructure/`, which the manifest records as
obsolete-test candidates (their subject, `playbook_v1.yaml` and its
loader, is removed by this change).

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 3.1 places "a repository adapter in
`launch/infrastructure/driven/` implementing the existing `Playbooks`
port" but fixes no module or class name. Assumed, following the
`launch_repository.LaunchRepository(session)` precedent in this
directory: `commerce_ops.launch.infrastructure.driven.playbook_repository`
exporting `PlaybookRepository(session)`, with the port's `get(version)
-> LaunchPlaybook` read (the shape every `_FakePlaybooks` in
`tests/unit/launch/application/` records). The served playbook is live:
`get` ignores the version it is passed rather than selecting by it, so
`_served()` below passes a throwaway value. Correcting module, class or
method is a fixture correction (`ai-toolkit:testing`, failure state 3);
the assertions over the served set are not.

## Seeded rows are read, never written

Every comparison below is stated by the delta "before any authored edit"
to the compared step. These tests therefore never write, and
`test_playbook_authoring_live.py` in this directory confines its writes
to steps it creates in the `mg.*` namespace — seeded `lp.*` rows stay
authored-edit-free in the test database. Seeded-set assertions filter to
the `lp.*` namespace so `mg.*` residue from authoring tests cannot leak
in.

**The reference document is parsed, not transcribed** — the same choice,
grammar and trimming rule `test_shipped_playbook_descriptions.py` and
`test_shipped_playbook_steps.py` record, re-declared here because those
files must not be edited by this pass.

**Expected first-run state.** Absent target: the adapter module does not
exist (`ModuleNotFoundError` at import), and before the migrations land
the tables do not either. Skips when `DATABASE_URL` is unset, like the
rest of this directory.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

import inspect
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.launch.application import report_undecided_rule_policies
from commerce_ops.launch.domain.launch_playbook import (
    ExecutionMode,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    StepDefinition,
    WindowAnchor,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

# SPECIFIED (main spec): the eight gates.
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

# SPECIFIED (delta): the seeded namespace.
SEEDED_PREFIX: Final = "lp."

# DERIVED: the reference document's row grammar, exactly as
# `test_shipped_playbook_steps.py` and
# `test_shipped_playbook_descriptions.py` record it.
_AREA_HEADING: Final = re.compile(r"^- (\d+)\. (.+?)\s*$")
_ROW_ID: Final = re.compile(r"\*\*ID:\*\*\s*(\S+?)\s*$")
_ROW_SOURCE: Final = re.compile(r"\*\*SOURCE:\*\*\s*(.*?)\s*(?:·\s*\*\*|$)")
_BULLET: Final = re.compile(r"^\s*-\s+(.*?)\s*$")

_BUILD_THE_LISTING: Final = "BUILD THE LISTING"

# SPECIFIED (delta): the closed trimming set.
_TERMINAL_MARKS: Final = ";:,."

# SPECIFIED (delta, tasks.md 3.1 of describe-playbook-steps / design):
# the six reference rows that restate gate-authored metric conditions,
# as `test_shipped_playbook_steps.py` records them.
METRIC_RESTATEMENT_ROW_IDS: Final = (
    "lp.inventory.040",
    "lp.inventory.041",
    "lp.strategy.033",
    "lp.strategy.025",
    "lp.ppc.048",
    "lp.finance.036",
)

MODES_REQUIRING_A_RULE_POLICY: Final = (
    ExecutionMode.AUTOMATED,
    ExecutionMode.AI_ASSISTED,
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's step tables and seed), and point DATABASE_URL at it."
        )
    return url


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_database_url())
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _served() -> LaunchPlaybook:
    """The live served playbook — the single correction point for the
    adapter's module, class and read method (see the docstring).

    The port's `get(version)` is sync on every existing fake; a real
    Postgres adapter may need it async. Both are tolerated here so the
    difference stays a fixture concern.
    """
    async with _session() as session:
        result: Any = PlaybookRepository(session).get("any-version-read-through")
        if inspect.isawaitable(result):
            result = await result
        assert isinstance(result, LaunchPlaybook)
        return result


def _seeded(playbook: LaunchPlaybook) -> tuple[StepDefinition, ...]:
    """The served seeded steps, guarded against a vacuous pass."""
    steps = tuple(
        step for step in playbook.steps if step.identifier.startswith(SEEDED_PREFIX)
    )
    assert steps, "the served playbook carries no seeded (lp.*) steps"
    return steps


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _trimmed(text: str) -> str:
    """The delta's trimming rule, applied exactly as stated."""
    reduced = text.rstrip()
    while reduced and reduced[-1] in _TERMINAL_MARKS:
        reduced = reduced[:-1].rstrip()
    return reduced


def _reference_rows() -> dict[str, tuple[str, str, str]]:
    """Every ID-bearing reference row as `id -> (area, citation, text)`."""
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
# Requirement (MODIFIED): The shipped playbook carries the authored step set
# ---------------------------------------------------------------------------


async def test_the_playbook_loads_with_steps_after_seeding() -> None:
    """Scenario: The shipped playbook loads with steps.

    WHEN the playbook is loaded after seeding
    THEN it loads coherently and its step list is non-empty
    AND every gate has at least one step attached.
    """
    playbook = await _served()

    assert len(tuple(playbook.steps)) > 0
    gates_with_steps = {step.gate for step in playbook.steps}
    assert set(SPECIFIED_GATE_ORDER) <= gates_with_steps


async def test_build_the_listing_is_fully_represented() -> None:
    """Scenario: BUILD THE LISTING is fully represented.

    WHEN the seeded step set is compared against the ID-bearing rows of
    the reference document's BUILD THE LISTING area
    THEN every such row's ID appears as a step identifier.
    """
    identifiers = {step.identifier for step in _seeded(await _served())}

    assert sorted(BUILD_THE_LISTING_ROW_IDS - identifiers) == []


async def test_every_seeded_step_traces_to_its_source_row() -> None:
    """Scenario: A step traces to its source row.

    WHEN any seeded step is read, before any authored edit to it
    THEN its identifier is a reference-document row ID and its provenance
    reference is that row's source citation
    AND the second segment of that identifier is the step's declared
    discipline.
    """
    untraceable: list[str] = []
    mis_cited: list[str] = []
    mis_segmented: list[str] = []
    for step in _seeded(await _served()):
        row = REFERENCE_ROWS.get(step.identifier)
        if row is None:
            untraceable.append(step.identifier)
            continue
        _, citation, _ = row
        if step.provenance != citation:
            mis_cited.append(step.identifier)
        if step.identifier.split(".")[1] != step.discipline.value:
            mis_segmented.append(step.identifier)

    assert untraceable == []
    assert mis_cited == []
    assert mis_segmented == []


async def test_every_seeded_step_states_its_work() -> None:
    """Scenario: A step states its work without the source document.

    WHEN any seeded step is read
    THEN its description is non-empty.
    """
    undescribed = [
        step.identifier for step in _seeded(await _served()) if not step.description
    ]

    assert undescribed == []


async def test_every_description_re_derives_from_its_reference_row() -> None:
    """Scenario: Every description re-derives from its reference row.

    WHEN every seeded step's description, before any authored edit to it,
    is compared against the text of the reference row its identifier
    names, reduced by the trimming rule
    THEN each description equals that row's trimmed text exactly.

    Equality, not containment — the delta's transcription is "unaltered".
    """
    mismatched: list[tuple[str, str, str]] = []
    for step in _seeded(await _served()):
        row = REFERENCE_ROWS.get(step.identifier)
        if row is None:
            continue  # reported by the traceability test, not twice
        _, _, text = row
        expected = _trimmed(text)
        if step.description != expected:
            mismatched.append((step.identifier, step.description, expected))

    assert mismatched == []


async def test_gate_authored_conditions_are_not_duplicated_as_steps() -> None:
    """Scenario: A gate-authored condition is not duplicated as a step.

    WHEN the seeded step identifiers are compared against the reference
    rows that restate a gate's authored metric conditions
    THEN none of those rows' IDs appears as a step identifier.
    """
    identifiers = {step.identifier for step in _seeded(await _served())}

    assert sorted(set(METRIC_RESTATEMENT_ROW_IDS) & identifiers) == []


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Every gate is held by at least one blocking step
# ---------------------------------------------------------------------------


async def test_no_gate_opens_for_free_in_the_served_set() -> None:
    """Scenario: No gate opens for free.

    WHEN the served step set is grouped by gate, at any point in the
    set's life — here, as the store currently serves it
    THEN every gate has at least one step with a true blocking flag.
    """
    playbook = await _served()

    unheld = [
        gate
        for gate in SPECIFIED_GATE_ORDER
        if not any(step.blocking and step.gate == gate for step in playbook.steps)
    ]
    assert unheld == []


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The authored set exercises the full step vocabulary
# ---------------------------------------------------------------------------


async def test_every_timing_anchor_kind_is_represented() -> None:
    """Scenario: Anchor kinds are all present.

    WHEN the seeded step set is grouped by timing-anchor kind
    THEN each of offset, window, open-ended, and recurring is represented
    by at least one step.
    """
    anchors = [step.timing_anchor for step in _seeded(await _served())]

    missing = [
        kind.__name__
        for kind in (OffsetAnchor, WindowAnchor, OpenEndedAnchor, RecurringAnchor)
        if not any(isinstance(anchor, kind) for anchor in anchors)
    ]
    assert missing == []


async def test_every_discipline_is_represented() -> None:
    """Scenario: Every discipline appears.

    WHEN the seeded step set is grouped by discipline
    THEN every discipline of the shared vocabulary is represented by at
    least one step.
    """
    disciplines = {step.discipline for step in _seeded(await _served())}

    assert (
        sorted(member.value for member in Discipline if member not in disciplines) == []
    )


async def test_execution_modes_and_the_compliance_hazard_are_represented() -> None:
    """Scenario: Execution modes and the compliance hazard are represented.

    WHEN the seeded step set is grouped by execution mode and filtered by
    hazard
    THEN each of automated, AI-assisted, and human-attested is represented
    AND every seeded step whose execution mode requires a rule policy
    carries one
    AND at least one `compliance-obligation` step exists.
    """
    steps = _seeded(await _served())

    modes = {step.execution for step in steps}
    missing = [
        mode.name
        for mode in (
            ExecutionMode.AUTOMATED,
            ExecutionMode.AI_ASSISTED,
            ExecutionMode.HUMAN_ATTESTED,
        )
        if mode not in modes
    ]
    assert missing == []

    without_policy = [
        step.identifier
        for step in steps
        if step.execution in MODES_REQUIRING_A_RULE_POLICY and step.rule_policy is None
    ]
    assert without_policy == []

    obligations = [
        step.identifier for step in steps if step.hazard is Hazard.COMPLIANCE_OBLIGATION
    ]
    assert obligations != []


async def test_prohibited_tactics_are_present_and_never_block() -> None:
    """Scenario: Prohibited tactics are present and never block.

    WHEN the seeded step set is filtered to hazard `prohibited-tactic`
    THEN at least one such step exists
    AND none of them has a true blocking flag.
    """
    tactics = [
        step
        for step in _seeded(await _served())
        if step.hazard is Hazard.PROHIBITED_TACTIC
    ]

    assert tactics != []
    assert [step.identifier for step in tactics if step.blocking] == []


async def test_outstanding_rule_policy_decisions_stay_visible() -> None:
    """Scenario: Outstanding rule-policy decisions stay visible.

    WHEN the undecided-rule-policies report runs over the served playbook
    while any human-attested step lacks a decided rule policy
    THEN it lists exactly those steps.
    """
    playbook = await _served()
    expected = {step.identifier for step in playbook.steps if step.rule_policy is None}

    reported = {row.identifier for row in report_undecided_rule_policies(playbook)}

    assert reported == expected


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Playbooks are versioned — the serving half
# ---------------------------------------------------------------------------


async def test_the_served_playbook_reports_a_version_identifier() -> None:
    """Scenario: The loaded playbook reports its version.

    WHEN a playbook is loaded
    THEN it reports a version identifier.
    """
    playbook = await _served()

    assert isinstance(playbook.version, str)
    assert playbook.version.strip() != ""
