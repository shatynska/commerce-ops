"""The undecided-rule-policy report: which steps still lack a decided rule.

A pure query over a loaded `LaunchPlaybook` — this layer may not reach the
YAML loader (`.importlinter`'s module-layers contract: application never
imports infrastructure), so the caller loads the playbook (the existing
`launch.infrastructure.driven.playbook_loader` from a driving adapter or
test) and hands it in. Keeps the outstanding rule-policy decisions visible
while the playbook is authored, rather than surfacing one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass

from commerce_ops.launch.domain.launch_playbook import ExecutionMode, LaunchPlaybook
from commerce_ops.shared.domain.discipline import Discipline


@dataclass(frozen=True, slots=True)
class UndecidedRulePolicy:
    """One step whose rule policy is still undecided."""

    identifier: str
    gate: str
    discipline: Discipline
    execution: ExecutionMode


def report_undecided_rule_policies(
    playbook: LaunchPlaybook,
) -> tuple[UndecidedRulePolicy, ...]:
    """The steps of `playbook` that carry no rule policy."""
    return tuple(
        UndecidedRulePolicy(
            identifier=step.identifier,
            gate=step.gate,
            discipline=step.discipline,
            execution=step.execution,
        )
        for step in playbook.steps
        if step.rule_policy is None
    )
