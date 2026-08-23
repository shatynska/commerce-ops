"""Tests for the playbook loader (driven adapter) and the shipped v1 file.

Derived from the delta spec:
openspec/changes/add-launch-playbook/specs/launch-playbook/spec.md

This file holds the three scenarios that cannot be observed below the file
boundary:

- *A discretionary gate is marked as requiring confirmation* and *An
  objective gate opens automatically*. No coherence rule validates opening
  modes — the five rules in the spec cover the gate *sequence* only — so
  the shipped data file is the only place the specified assignment of
  opening modes is actually settled.
- *A malformed step is reported alongside a coherence violation*. A
  malformed step definition cannot exist as a domain object (a reversed
  window is rejected at anchor construction), so only the loader can hold
  one, per `tasks.md` 4.3.

Every other scenario is covered at the domain level, in
`tests/unit/products/domain/`.

At the time of writing neither the loader nor the data file exists, so
every test here is expected to fail on an absent target
(`ModuleNotFoundError`). That failure establishes only absence.

**The YAML document shape used by `test_malformed_step_is_reported_...` is
INVENTED.** `tasks.md` 4.1 leaves the document shape to the implementer and
no artifact records one. If the implemented shape differs, the document
builder below is wrong in its *input*, not in its assertions — correcting
the keys to match the real shape is a fixture correction (failure state 3
in `ai-toolkit:testing`), whereas changing what the test asserts about the
resulting error would be weakening it. See
`openspec/changes/add-launch-playbook/test-manifest.md`.

**Follow-up pass, since removed.** A follow-up pass added a
loader-boundary test for the *Track names one of a fixed set of
disciplines* requirement; `complete-playbook-definition`'s delta REMOVES
that requirement and renames the attribute to `discipline`, so that test
was removed with it — replacement coverage lives in
`tests/unit/launch/domain/test_step_definition_discipline.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    GateOpening,
    InvalidPlaybookError,
)
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_playbook,
    load_shipped_playbook,
)

# SPECIFIED: the eight gates, in this order.
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

# SPECIFIED: "By that criterion `commit`, `order`, `phase-one-complete` and
# `graduated` require confirmation, and `listable`, `stock-ready`, `live`
# and `ignition` open automatically."
CONFIRMATION_GATES: Final = ("commit", "order", "phase-one-complete", "graduated")
AUTOMATIC_GATES: Final = ("listable", "stock-ready", "live", "ignition")

# DERIVED / INVENTED: the YAML document shape. See the module docstring.
_GATES_YAML: Final = """\
version: v1
gates:
  - identifier: commit
    position: 1
    opening: requires-confirmation
  - identifier: order
    position: 2
    opening: requires-confirmation
  - identifier: listable
    position: 3
    opening: automatic
  - identifier: stock-ready
    position: 4
    opening: automatic
  - identifier: live
    position: 5
    opening: automatic
  - identifier: ignition
    position: 6
    opening: automatic
  - identifier: phase-one-complete
    position: 7
    opening: requires-confirmation
  - identifier: graduated
    position: 8
    opening: requires-confirmation
"""

# DERIVED / INVENTED: two steps, the first carrying a reversed window (a
# malformed timing anchor), the second declaring a gate that is not in the
# sequence (a coherence violation). Two separate faults on two separate
# steps, so the assertion can tell them apart by identifier.
_TWO_FAULTY_STEPS_YAML: Final = """\
steps:
  - identifier: inventory.reversed-window
    gate: stock-ready
    discipline: inventory
    scope: product
    timing_anchor:
      kind: window
      start: 55
      end: 28
    binding: framework
    blocking: false
    execution: human-attested
  - identifier: ppc.unknown-gate
    gate: pre-launch
    discipline: ppc
    scope: market
    timing_anchor:
      kind: offset
      days: -7
    binding: framework
    blocking: false
    execution: human-attested
"""


def _write_playbook(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "playbook.yaml"
    path.write_text(_GATES_YAML + body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Requirement: A gate declares how it opens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("identifier", CONFIRMATION_GATES)
def test_discretionary_gate_requires_confirmation(identifier: str) -> None:
    """Scenario: A discretionary gate is marked as requiring confirmation.

    WHEN the `commit`, `order`, `phase-one-complete`, or `graduated` gate is
    read
    THEN it reports that it requires human confirmation to open.
    """
    gates = {gate.identifier: gate for gate in load_shipped_playbook().gates}

    # SPECIFIED: these four turn on a judgement no objective condition
    # settles, so each requires confirmation.
    assert gates[identifier].opening is GateOpening.REQUIRES_CONFIRMATION


@pytest.mark.parametrize("identifier", AUTOMATIC_GATES)
def test_objective_gate_opens_automatically(identifier: str) -> None:
    """Scenario: An objective gate opens automatically.

    WHEN the `listable`, `stock-ready`, `live`, or `ignition` gate is read
    THEN it reports that it opens automatically.

    `ignition` is included deliberately: `design.md` records it as the case
    most likely to be modelled wrongly, since it is the launch's most
    consequential moment yet its preconditions are all observable.
    """
    gates = {gate.identifier: gate for gate in load_shipped_playbook().gates}

    # SPECIFIED: these four have preconditions that are an observable state
    # of the world.
    assert gates[identifier].opening is GateOpening.AUTOMATIC


def test_the_two_opening_modes_are_distinct() -> None:
    """Scenario: A discretionary gate ... / An objective gate ... (guard).

    The two scenarios above would both pass if `GateOpening` collapsed to a
    single value. This asserts the distinction the requirement rests on.
    """
    # Statically decidable given the enum as defined today -- that tautology
    # is exactly what this guard exists to detect if it ever stops holding.
    assert GateOpening.REQUIRES_CONFIRMATION is not GateOpening.AUTOMATIC  # type: ignore[comparison-overlap]


# ---------------------------------------------------------------------------
# Requirement: Playbooks are versioned / Gate sequence orders the launch
# (asserted against the shipped file, through the real loader)
# ---------------------------------------------------------------------------


def test_shipped_playbook_reports_its_version() -> None:
    """Scenario: The loaded playbook reports its version.

    WHEN a playbook is loaded
    THEN it reports the version identifier it was authored with.

    DERIVED from `tasks.md` 4.2, which fixes the shipped version as `v1`.
    The spec requires a version identifier, not this particular value.
    """
    assert load_shipped_playbook().version == "v1"


def test_shipped_playbook_exposes_the_eight_gates_in_order() -> None:
    """Scenario: Gates expose a stable order (shipped file).

    WHEN the playbook's gates are read
    THEN they are returned in the defined order, each carrying its position
    in the sequence
    AND two gates never share a position.

    Also covers `tasks.md` 5.12: the shipped `v1` file loads successfully
    through the real loader. Loading it at all is what establishes that the
    file satisfies every coherence rule.
    """
    playbook = load_shipped_playbook()

    # SPECIFIED: exactly the eight gates, in the defined order.
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)

    positions = [gate.position for gate in playbook.gates]
    # SPECIFIED: two gates never share a position.
    assert len(set(positions)) == len(positions)
    # DELIBERATELY UNTESTED: whether positions are numbered from 0 or 1.
    assert positions == sorted(positions)


def test_shipped_playbook_ships_with_no_step_definitions() -> None:
    """Not a spec scenario — `tasks.md` 4.2 and `proposal.md`.

    DERIVED: "Ship the playbook containing the eight gates and no step
    definitions. Authoring the step definitions is deliberately a follow-up
    change." Asserted so that the follow-up cannot land inside this change
    unnoticed. The delta spec itself says nothing about
    how many steps the shipped playbook holds; if the import change lands,
    this assertion is superseded and should be removed with that change,
    not weakened to fit.
    """
    assert list(load_shipped_playbook().steps) == []


# ---------------------------------------------------------------------------
# Requirement: An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


def test_malformed_step_is_reported_alongside_a_coherence_violation(
    tmp_path: Path,
) -> None:
    """Scenario: A malformed step is reported alongside a coherence violation.

    WHEN a playbook contains one step whose timing anchor is invalid and a
    second, separate coherence violation
    THEN loading fails once, and the failure names both faults.

    This is the scenario the requirement exists for: when steps are
    authored in bulk, a malformed step is the likelier error, and
    discovering faults one load at a time is the experience the rule
    prevents.
    """
    source = _write_playbook(tmp_path, _TWO_FAULTY_STEPS_YAML)

    # SPECIFIED: loading fails *once* — one raised error carrying both
    # faults, not one error per fault.
    with pytest.raises(InvalidPlaybookError) as caught:
        load_playbook(source)

    message = str(caught.value)
    # SPECIFIED: the failure names both faults, each naming its offending
    # step.
    assert "inventory.reversed-window" in message
    assert "ppc.unknown-gate" in message


def test_a_coherent_playbook_file_loads(tmp_path: Path) -> None:
    """Scenario: A coherent playbook loads.

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    The domain-level counterpart is
    `test_launch_playbook.py::test_a_coherent_playbook_loads`; this one
    establishes the same through the file boundary, so that a loader which
    rejected every file would not pass unnoticed.
    """
    source = _write_playbook(tmp_path, "steps: []\n")

    playbook = load_playbook(source)

    assert playbook.version == "v1"
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)
    assert list(playbook.steps) == []


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - Loader behaviour for a missing file, unreadable file, or YAML that is
#   not a mapping at all. The delta spec's rejection rules are about the
#   playbook's coherence, not about I/O or parse failure, and inventing a
#   contract for them here would impose an unagreed constraint.
# - That the data file is present as package data in an installed build
#   (`tasks.md` 4.4). That is a packaging property, observable only from a
#   built wheel, not from this source-tree unit tier.
# - The exact wording of any error message. Only that it names the
#   offending step or gate, which is what the spec requires.
