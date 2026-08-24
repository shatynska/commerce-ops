"""Tests for the undecided-rule-policy report use case.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the ADDED requirement *Undecided rule policies are reported*.

At the time of writing `commerce_ops.launch` does not exist, so every
test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

DERIVED / unresolved project questions (see the manifest at the change
root):

- `report_undecided_rule_policies` imported from
  `commerce_ops.launch.application` — its public-surface placement is
  fixed by `tasks.md` 5.2; the *call shape* is not. **Q7 resolved during
  implementation**: the use case takes a loaded `LaunchPlaybook`, not a
  path — `.importlinter`'s module-layers contract forbids the application
  layer from importing the infrastructure loader, so the caller loads
  (as these tests now do via `load_playbook`). Correcting the calls was
  the fixture correction the original note anticipated; no assertion
  changed.
- Report rows expose `identifier`, `gate`, `discipline`, and `execution`
  — the four fields `tasks.md` 5.1 names, with `execution` spelled as
  `StepDefinition` already spells it.
- **The YAML document shape below is INVENTED**, extending the shape the
  earlier pass invented for the loader tests with the renamed
  `discipline:` key (`tasks.md` 3.2) and a `rule_policy:` key no
  artifact fixes. A mismatch with the implemented shape is a fixture
  correction in the *input*, never in what the tests assert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from commerce_ops.launch.application import report_undecided_rule_policies
from commerce_ops.launch.domain.launch_playbook import ExecutionMode
from commerce_ops.launch.infrastructure.driven.playbook_loader import load_playbook
from commerce_ops.shared.domain.discipline import Discipline

# DERIVED / INVENTED: the gates document, unchanged from the earlier
# pass's invented shape.
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

# DERIVED / INVENTED: one step with a rule policy, one without. The
# undecided step is human-attested because any other execution mode
# without a rule policy is a coherence fault (main spec: *Automation
# without a decided rule*), which would make the playbook unloadable.
_ONE_DECIDED_ONE_UNDECIDED_YAML: Final = """\
steps:
  - identifier: price.buy-box-check
    description: Work this step asks for
    gate: live
    discipline: price
    scope: market
    timing_anchor:
      kind: offset
      days: 0
    binding: framework
    blocking: false
    execution: automated
    rule_policy: Buy Box share is at or above 90% over a rolling week.
  - identifier: strategy.phase-one-criteria
    description: Work this step asks for
    gate: commit
    discipline: strategy
    scope: product
    timing_anchor:
      kind: offset
      days: -90
    binding: framework
    blocking: false
    execution: human-attested
"""

# DERIVED / INVENTED: every step carries a rule policy.
_FULLY_DECIDED_YAML: Final = """\
steps:
  - identifier: price.buy-box-check
    description: Work this step asks for
    gate: live
    discipline: price
    scope: market
    timing_anchor:
      kind: offset
      days: 0
    binding: framework
    blocking: false
    execution: automated
    rule_policy: Buy Box share is at or above 90% over a rolling week.
  - identifier: strategy.phase-one-criteria
    description: Work this step asks for
    gate: commit
    discipline: strategy
    scope: product
    timing_anchor:
      kind: offset
      days: -90
    binding: framework
    blocking: false
    execution: human-attested
    rule_policy: Phase-one exit criteria are written down and agreed.
"""


def _write_playbook(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "playbook.yaml"
    path.write_text(_GATES_YAML + body, encoding="utf-8")
    return path


def test_steps_without_a_rule_policy_are_listed(tmp_path: Path) -> None:
    """Scenario: Steps without a rule policy are listed.

    WHEN the report is requested against a playbook containing one step
    with a rule policy and one without
    THEN exactly the step without a rule policy is reported, with its
    identifier, gate, discipline, and execution mode.
    """
    source = _write_playbook(tmp_path, _ONE_DECIDED_ONE_UNDECIDED_YAML)

    rows = list(report_undecided_rule_policies(load_playbook(source)))

    # SPECIFIED: exactly the step without a rule policy is reported.
    (row,) = rows
    # SPECIFIED: identified by its identifier, its gate, its owning
    # discipline, and its execution mode.
    assert row.identifier == "strategy.phase-one-criteria"
    assert row.gate == "commit"
    assert row.discipline is Discipline("strategy")
    assert row.execution is ExecutionMode.HUMAN_ATTESTED


def test_a_fully_decided_playbook_reports_nothing(tmp_path: Path) -> None:
    """Scenario: A fully decided playbook reports nothing.

    WHEN the report is requested against a playbook in which every step
    carries a rule policy
    THEN the report is empty.
    """
    source = _write_playbook(tmp_path, _FULLY_DECIDED_YAML)

    assert list(report_undecided_rule_policies(load_playbook(source))) == []
