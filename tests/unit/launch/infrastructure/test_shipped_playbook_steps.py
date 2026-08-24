"""Tests for the authored step set carried by the shipped `v1` playbook.

Derived from the delta spec:
openspec/changes/author-playbook-steps/specs/launch-playbook/spec.md

Covers the three ADDED requirements *The shipped playbook carries the
authored step set*, *Every gate is held by at least one blocking step*, and
*The authored set exercises the full step vocabulary* — every scenario of
each except *Outstanding rule-policy decisions stay visible*, which
observes the application-layer report and lives in
`tests/unit/launch/application/test_shipped_playbook_undecided_policies.py`.

The subject under test is *data*: the shipped
`playbook_v1.yaml`. Nothing here asserts anything about the loader, the
step schema, or the coherence rules — those are specified by the existing
`launch-playbook` spec and covered by `test_playbook_loader.py` and
`tests/unit/launch/domain/`. The loader is used only as the means of
observing the file.

At the time of writing the shipped file carries `steps: []`, so every test
below is expected to fail on a wrong value rather than on an absent
target — the loader, the domain types and the file all exist. Per
`ai-toolkit:testing` that is failure state 1: the assertions execute and
discriminate.

Baseline recorded before these tests were written:
`uv run pytest tests/unit/launch tests/unit/shared/domain/test_discipline.py`
— 178 passed, 0 failed.

SPECIFIED / DERIVED provenance, per `ai-toolkit:testing`:

- The reference document (`docs/reference/product-launch.md`) is parsed
  here rather than transcribed, because the delta states the coverage
  obligation *against that document* ("every ID-bearing row of that area
  appears as a step"). Transcribing 72 identifiers into this file would
  make the test assert a copy rather than the source. The parser's row
  grammar (`**SOURCE:** … · **ID:** …` on one metadata line) is DERIVED
  from the document's own shape; a document reformatting would be a
  fixture defect in this parser (failure state 3), never grounds to
  weaken an assertion.
- The enumerated identifier lists below (the metric-restatement rows, the
  TOS-risk cautions) are the ones `design.md` Decisions 5 and 8 fix and
  `tasks.md` 3.1 names. The delta states the *rule*; the design states
  *which rows* it selects. Both are change artifacts, so these are
  treated as specified, with the artifact named at each site.

Unresolved project question, recorded rather than assumed (see the
manifest at the change root): the delta says a step's "provenance SHALL
carry that row's source citation", and `design.md` Decision 2 maps
`SOURCE → provenance` "verbatim". `test_every_step_provenance_carries_its
_row_source_citation` therefore asserts equality with the verbatim
citation string. If the authoring instead wraps the citation (a document
path, a prefix), that is a disagreement between the design and the
authored data to be reported — not an assertion to loosen here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Hazard,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    StepDefinition,
    WindowAnchor,
)
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)
from commerce_ops.shared.domain.discipline import Discipline

# ---------------------------------------------------------------------------
# The reference document, parsed
# ---------------------------------------------------------------------------

# DERIVED: the reference document's row grammar. An ID-bearing row is a
# metadata line ending in `**ID:** lp.<discipline>.<nnn>`, and an area
# heading is a top-level `- <n>. <NAME>` list item.
_AREA_HEADING: Final = re.compile(r"^- (\d+)\. (.+?)\s*$")
_ROW_ID: Final = re.compile(r"\*\*ID:\*\*\s*(\S+?)\s*$")
_ROW_SOURCE: Final = re.compile(r"\*\*SOURCE:\*\*\s*(.*?)\s*(?:·\s*\*\*|$)")

# SPECIFIED: "the BUILD THE LISTING area is represented completely"
# (Requirement: The shipped playbook carries the authored step set).
_BUILD_THE_LISTING: Final = "BUILD THE LISTING"


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _reference_rows() -> dict[str, tuple[str, str]]:
    """Every ID-bearing reference row as `id -> (area, source citation)`.

    Parsed, not transcribed — see the module docstring.
    """
    source_file = _repository_root() / "docs" / "reference" / "product-launch.md"
    rows: dict[str, tuple[str, str]] = {}
    area = ""
    for raw in source_file.read_text(encoding="utf-8").splitlines():
        heading = _AREA_HEADING.match(raw)
        if heading is not None:
            area = heading.group(2)
            continue
        identifier = _ROW_ID.search(raw)
        if identifier is None:
            continue
        citation = _ROW_SOURCE.search(raw)
        if citation is None:
            pytest.fail(f"reference row {identifier.group(1)} carries no SOURCE")
        rows[identifier.group(1)] = (area, citation.group(1))
    if not rows:
        pytest.fail("no ID-bearing rows parsed from the reference document")
    return rows


REFERENCE_ROWS: Final = _reference_rows()

BUILD_THE_LISTING_ROW_IDS: Final = frozenset(
    identifier
    for identifier, (area, _) in REFERENCE_ROWS.items()
    if area == _BUILD_THE_LISTING
)

# SPECIFIED (delta): "Rows ... that restate a condition a gate already
# authors as a metric condition SHALL NOT additionally appear as steps".
# The six rows the rule selects are enumerated by `design.md` Decision 8
# and named by `tasks.md` 3.1.
METRIC_RESTATEMENT_ROW_IDS: Final = (
    "lp.inventory.040",
    "lp.inventory.041",
    "lp.strategy.033",
    "lp.strategy.025",
    "lp.ppc.048",
    "lp.finance.036",
)

# SPECIFIED (delta): "a row that is a caution about a mistake SHALL remain
# an ordinary step". The two TOS-RISK rows the rule selects as cautions
# rather than tactics are enumerated by `design.md` Decision 5.
TOS_RISK_CAUTION_ROW_IDS: Final = ("lp.setup.020", "lp.inventory.018")

# SPECIFIED (main spec, Requirement: Gate sequence orders the launch).
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

# SPECIFIED (main spec, Requirement: An incoherent playbook is rejected at
# load time): these two modes may not ship without a rule policy.
MODES_REQUIRING_A_RULE_POLICY: Final = (
    ExecutionMode.AUTOMATED,
    ExecutionMode.AI_ASSISTED,
)


def _shipped_steps() -> tuple[StepDefinition, ...]:
    """The shipped playbook's steps, guarded against a vacuous pass.

    Several assertions below quantify over the step set. With `steps: []`
    — the state this change starts from — every such assertion would hold
    vacuously, which `ai-toolkit:testing` classes as an alarm rather than
    a result. The guard makes the emptiness fail those tests loudly
    instead; the emptiness *requirement* itself is asserted separately by
    `test_the_shipped_playbook_loads_with_a_non_empty_step_list`.
    """
    steps = tuple(load_shipped_playbook().steps)
    assert steps, "the shipped playbook carries no steps"
    return steps


# ---------------------------------------------------------------------------
# Requirement: The shipped playbook carries the authored step set
# ---------------------------------------------------------------------------


def test_the_shipped_playbook_loads_with_a_non_empty_step_list() -> None:
    """Scenario: The shipped playbook loads with steps.

    WHEN the shipped playbook is loaded
    THEN it loads coherently and its step list is non-empty.

    Loading at all is what establishes coherence: the loader rejects an
    incoherent playbook rather than returning a partially valid one (main
    spec, *An incoherent playbook is rejected at load time*).
    """
    playbook = load_shipped_playbook()

    # SPECIFIED: its step list is non-empty.
    assert len(tuple(playbook.steps)) > 0


def test_every_gate_has_at_least_one_step_attached() -> None:
    """Scenario: The shipped playbook loads with steps (second THEN).

    WHEN the shipped playbook is loaded
    THEN every gate has at least one step attached.
    """
    steps = _shipped_steps()

    gates_with_steps = {step.gate for step in steps}

    # SPECIFIED: every gate — asserted as a set difference so the failure
    # names the gates left empty rather than only the first.
    assert sorted(set(SPECIFIED_GATE_ORDER) - gates_with_steps) == []


def test_build_the_listing_is_fully_represented() -> None:
    """Scenario: BUILD THE LISTING is fully represented.

    WHEN the shipped playbook's steps are compared against the ID-bearing
    rows of the reference document's BUILD THE LISTING area
    THEN every such row's ID appears as a step identifier in the playbook.
    """
    identifiers = {step.identifier for step in _shipped_steps()}

    # SPECIFIED: every ID-bearing row of that area appears as a step.
    assert sorted(BUILD_THE_LISTING_ROW_IDS - identifiers) == []


def test_every_step_identifier_is_a_reference_row_id() -> None:
    """Scenario: A step traces to its source row (first THEN).

    WHEN any authored step is read from the loaded playbook
    THEN its identifier is a reference-document row ID.

    Stated over *any* step, so this quantifies over the whole set rather
    than sampling one.
    """
    identifiers = {step.identifier for step in _shipped_steps()}

    # SPECIFIED: every step traces to exactly one reference row, and the
    # identifier is how it traces.
    assert sorted(identifiers - REFERENCE_ROWS.keys()) == []


def test_every_step_provenance_carries_its_row_source_citation() -> None:
    """Scenario: A step traces to its source row (second THEN).

    WHEN any authored step is read from the loaded playbook
    THEN its provenance reference is that row's source citation.

    Equality with the verbatim SOURCE string is the reading `design.md`
    Decision 2 fixes ("SOURCE → provenance, verbatim"). See the module
    docstring's unresolved-project-question note.
    """
    mismatched: list[tuple[str, str | None, str]] = []
    for step in _shipped_steps():
        row = REFERENCE_ROWS.get(step.identifier)
        if row is None:
            # Reported by the identifier test above; not restated here.
            continue
        if step.provenance != row[1]:
            mismatched.append((step.identifier, step.provenance, row[1]))

    # SPECIFIED: provenance carries that row's source citation, so every
    # authored step traces to exactly one reference row.
    assert mismatched == []


def test_metric_condition_restatements_do_not_appear_as_steps() -> None:
    """Scenario: A gate-authored condition is not duplicated as a step.

    WHEN the shipped playbook's step identifiers are compared against the
    reference rows that restate a gate's authored metric conditions
    THEN none of those rows' IDs appears as a step identifier.

    The six rows are those `design.md` Decision 8 enumerates — the delta
    states the rule, the design states which rows it selects.
    """
    identifiers = {step.identifier for step in _shipped_steps()}

    # Guard: an enumerated ID that is not a real reference row would make
    # the assertion below hold for the wrong reason.
    assert sorted(set(METRIC_RESTATEMENT_ROW_IDS) - REFERENCE_ROWS.keys()) == []

    # SPECIFIED: one obligation is expressed once.
    assert sorted(identifiers & set(METRIC_RESTATEMENT_ROW_IDS)) == []


# ---------------------------------------------------------------------------
# Requirement: Every gate is held by at least one blocking step
# ---------------------------------------------------------------------------


def test_no_gate_opens_for_free() -> None:
    """Scenario: No gate opens for free.

    WHEN the shipped playbook's steps are grouped by gate
    THEN every gate has at least one step with a true blocking flag.
    """
    steps = _shipped_steps()

    gates_held = {step.gate for step in steps if step.blocking}

    # SPECIFIED: each of the eight gates, so that no gate's step
    # obligations are trivially satisfied by an empty set.
    assert sorted(set(SPECIFIED_GATE_ORDER) - gates_held) == []


def test_every_blocking_step_is_framework_bound() -> None:
    """Requirement statement: "Blocking steps SHALL be `framework`-bound".

    No scenario states this on its own; the requirement's prose does, and
    it is the property that distinguishes a blocking spine from an
    arbitrary set of flags. The coherence rules independently forbid a
    `lesson` step from blocking, so this asserts the shipped data agrees
    with the rule rather than establishing the rule.
    """
    non_framework = [
        step.identifier
        for step in _shipped_steps()
        if step.blocking and step.binding is not Binding.FRAMEWORK
    ]

    # SPECIFIED: advice, cautions and optional-at-launch work do not block.
    assert non_framework == []


# ---------------------------------------------------------------------------
# Requirement: The authored set exercises the full step vocabulary
# ---------------------------------------------------------------------------


def test_every_timing_anchor_kind_is_represented() -> None:
    """Scenario: Anchor kinds are all present.

    WHEN the shipped playbook's steps are grouped by timing-anchor kind
    THEN each of offset, window, open-ended, and recurring is represented
    by at least one step.
    """
    anchors = [step.timing_anchor for step in _shipped_steps()]

    # SPECIFIED: all four kinds the main spec defines. Grouped by anchor
    # type, which is how the four kinds are distinguished in the model.
    missing = [
        kind.__name__
        for kind in (OffsetAnchor, WindowAnchor, OpenEndedAnchor, RecurringAnchor)
        if not any(isinstance(anchor, kind) for anchor in anchors)
    ]
    assert missing == []


def test_every_discipline_is_represented() -> None:
    """Scenario: Every discipline appears.

    WHEN the shipped playbook's steps are grouped by discipline
    THEN every discipline of the shared vocabulary is represented by at
    least one step.
    """
    disciplines = {step.discipline for step in _shipped_steps()}

    # SPECIFIED: *every* discipline the shared vocabulary defines — read
    # from the vocabulary itself, so that adding a thirteenth discipline
    # there makes this fail rather than silently passing.
    assert (
        sorted(member.value for member in Discipline if member not in disciplines) == []
    )


def test_every_execution_mode_is_represented() -> None:
    """Scenario: Execution modes and the compliance hazard are represented.

    WHEN the shipped playbook's steps are grouped by execution mode
    THEN each of automated, AI-assisted, and human-attested is
    represented by at least one step.
    """
    modes = {step.execution for step in _shipped_steps()}

    # SPECIFIED: at least one step of each execution mode.
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


def test_steps_requiring_a_rule_policy_carry_one() -> None:
    """Scenario: Execution modes ... (second THEN).

    WHEN the shipped playbook's steps are grouped by execution mode
    THEN every step whose execution mode requires a rule policy carries
    one.

    The loader rejects a playbook violating this, so a shipped file that
    loads already satisfies it; asserted directly anyway, because this
    scenario states it as a property of the authored set rather than
    leaving it to be inferred from loadability.
    """
    without_policy = [
        step.identifier
        for step in _shipped_steps()
        if step.execution in MODES_REQUIRING_A_RULE_POLICY and step.rule_policy is None
    ]

    assert without_policy == []


def test_at_least_one_compliance_obligation_step_exists() -> None:
    """Scenario: Execution modes ... (third THEN).

    WHEN the shipped playbook's steps are filtered by hazard
    THEN at least one `compliance-obligation` step exists.
    """
    obligations = [
        step.identifier
        for step in _shipped_steps()
        if step.hazard is Hazard.COMPLIANCE_OBLIGATION
    ]

    # SPECIFIED: the compliance hazard is exercised by the authored set.
    assert obligations != []


def test_prohibited_tactic_steps_exist_and_never_block() -> None:
    """Scenario: Prohibited tactics are present and never block.

    WHEN the shipped playbook's steps are filtered to hazard
    `prohibited-tactic`
    THEN at least one such step exists
    AND none of them has a true blocking flag.
    """
    tactics = [
        step for step in _shipped_steps() if step.hazard is Hazard.PROHIBITED_TACTIC
    ]

    # SPECIFIED: at least one such step exists.
    assert [step.identifier for step in tactics] != []
    # SPECIFIED: none of them blocks — a gate can never wait on something
    # whose only terminal outcome is refusal.
    assert [step.identifier for step in tactics if step.blocking] == []


def test_tos_risk_cautions_remain_ordinary_steps() -> None:
    """Requirement statement: cautions are not prohibited tactics.

    "Tactics the reference document marks as suspension risks SHALL be
    represented as `prohibited-tactic` steps only where the row names a
    tactic to refuse; a row that is a caution about a mistake SHALL
    remain an ordinary step".

    No scenario states this; the requirement's prose does, and it is the
    distinction `design.md` Decision 5 turns on — a caution recorded as a
    tactic could only ever terminate in `Refused`, misstating work that
    is done by complying. The two caution rows are the ones Decision 5
    enumerates.
    """
    steps = {step.identifier: step for step in _shipped_steps()}

    misclassified = [
        identifier
        for identifier in TOS_RISK_CAUTION_ROW_IDS
        if identifier in steps and steps[identifier].hazard is Hazard.PROHIBITED_TACTIC
    ]

    # SPECIFIED: a caution stays an ordinary step.
    assert misclassified == []
    # Guard: the assertion above is vacuous if neither row was authored at
    # all. Both are authored per `design.md`'s step table (`listable` and
    # `stock-ready` respectively).
    assert sorted(set(TOS_RISK_CAUTION_ROW_IDS) - steps.keys()) == []


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The *total* number of authored steps (97), the per-gate counts, and
#   the specific gate each reassigned area-3 row is attached to. The
#   delta states coverage properties, not a census; `design.md`'s table
#   is the reviewable record of those choices, and asserting them here
#   would freeze curation decisions the change explicitly leaves as
#   one-line YAML edits (design.md, Risks / Trade-offs).
# - Which particular rows are `prohibited-tactic` (design.md Decision 5
#   names three). The delta requires at least one and requires cautions
#   *not* to be tactics — the latter is tested above; pinning the exact
#   membership of the tactic set would assert a curation decision the
#   delta does not state.
# - That every *other* reference area carries a representative subset of
#   a particular size. The delta says "every other gate carries a
#   representative subset" and settles what "representative" means via
#   the vocabulary-coverage requirement, which the tests above assert
#   directly.
# - The binding (`framework`/`lesson`), scope, and timing anchor of any
#   individual step. Specified per-step only by `design.md`'s table, not
#   by the delta.
