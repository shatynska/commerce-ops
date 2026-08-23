"""Loader-boundary tests for the completed playbook definition.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

The metric-condition scenarios of *A gate carries authored metric
conditions* are covered at the domain level in
`tests/unit/launch/domain/test_gate_conditions.py`; this file establishes
the same through the file boundary and the shipped `v1` file, because
parsing authored metric conditions out of YAML (`tasks.md` 4.5) is
observable only here — a loader that never parsed them would leave the
domain tests passing while every shipped gate silently read back empty.

No YAML document shape for a metric condition is invented in this file:
the shipped `playbook_v1.yaml` is the fixture, exactly as the earlier
pass used it for gate opening modes. The cost of that choice is recorded
in the manifest: the empty-threshold rejection has no file-boundary test,
because provoking it would require inventing the metric-condition YAML
shape `tasks.md` 4.5 leaves to the implementer.

At the time of writing `commerce_ops.launch` does not exist, so every
test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

DERIVED: which gates carry conditions is authored *data*, not spec
(`design.md` Decision 7) — the three gates below and their metric
identifiers trace to `proposal.md` and `tasks.md` 6.1, not to a SHALL.
An intentional data change that moves a condition supersedes the
assertion naming its gate; the shape assertions (a condition reports a
metric identifier and a non-empty threshold description) trace to the
spec and survive any such change.
"""

from __future__ import annotations

from typing import Final

import pytest

from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)

# DERIVED from `proposal.md` ("the v1 playbook authors the map's three
# metric-checked gates as data") and `tasks.md` 6.1.
METRIC_CHECKED_GATES: Final = ("stock-ready", "phase-one-complete", "graduated")


@pytest.mark.parametrize("identifier", METRIC_CHECKED_GATES)
def test_a_shipped_metric_checked_gate_reports_its_conditions(
    identifier: str,
) -> None:
    """Scenario: A gate's metric conditions are read back (file boundary).

    WHEN a gate authored with a metric condition is read from a loaded
    playbook
    THEN the condition reports its metric identifier and its threshold
    description.

    DERIVED: that *these three* gates carry conditions is authored data
    (see module docstring). SPECIFIED: each condition read back reports a
    metric identifier and a non-empty threshold description.
    """
    gates = {gate.identifier: gate for gate in load_shipped_playbook().gates}

    conditions = list(gates[identifier].metric_conditions)
    assert conditions, f"gate {identifier!r} ships with no metric condition"
    for condition in conditions:
        # SPECIFIED: the condition names the metric it turns on and
        # carries a human-readable threshold description that is not
        # empty.
        assert condition.metric_id.value
        assert condition.threshold


def test_shipped_gates_without_authored_conditions_report_none() -> None:
    """Scenario: A gate with no metric conditions is valid (file boundary).

    WHEN a gate authored with no metric conditions is read
    THEN it reports an empty set of metric conditions.

    DERIVED: that exactly the three metric-checked gates carry conditions
    — so the other five read back empty — is authored data, per
    `proposal.md`.
    """
    playbook = load_shipped_playbook()

    for gate in playbook.gates:
        if gate.identifier in METRIC_CHECKED_GATES:
            continue
        assert list(gate.metric_conditions) == []


def test_the_shipped_playbook_still_loads_coherently() -> None:
    """Scenario: A coherent playbook loads (shipped file, as revised).

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    Loading the shipped file at all establishes that the authored metric
    conditions and the `discipline` key survive every coherence rule this
    change adds. The gate order and version assertions are the same ones
    the earlier pass fixed against the shipped file.
    """
    playbook = load_shipped_playbook()

    assert playbook.version == "v1"
    assert [gate.identifier for gate in playbook.gates] == [
        "commit",
        "order",
        "listable",
        "stock-ready",
        "live",
        "ignition",
        "phase-one-complete",
        "graduated",
    ]
