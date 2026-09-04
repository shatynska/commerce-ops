"""The gate-holding floor as a readiness property of `LaunchPlaybook`.

`serve-only-a-ready-playbook` moved this rule out of the constructor: its
subject is not whether the step set is internally consistent but whether
it is complete enough to hold a launch, and as a construction rule it made
an all-`draft` set unrepresentable. So each test below now asserts that
the set **constructs** and that the readiness read names the gate it
leaves unheld. What each one establishes — which gate, and that attachment
or a non-`active` status does not satisfy the floor — is unchanged; only
where the answer is read has moved. That the *serving read* refuses such a
set is covered by the repository tests (`tasks.md` 5.6), which is the
layer that can observe it.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-playbook/spec.md`

Covers, from the MODIFIED requirement *An incoherent playbook is rejected
at load time*:

- *A gate with no blocking step is rejected* (new rule) — "a gate has no
  blocking step attached to it — the gate-holding floor its own
  requirement states, promoted to a coherence rule now that the step set
  is editable".
- The aggregation contract applied to the new rule: "The failure SHALL
  report **every** fault found" — a floor fault travels in the same
  single error as any other fault.
- *A coherent playbook loads* — as revised: "coherent" now includes every
  gate holding at least one blocking step.

And from the MODIFIED requirement *Every gate is held by at least one
blocking step*, the construction-rule half of *No gate opens for free*:
"at seed, and after every authored change ... enforced by the same
validation at load and at every write alike". The write half of that
scenario is covered in
`tests/unit/launch/application/test_playbook_authoring.py`
(*Retiring a gate's last blocking step is rejected*).

**Level.** `tasks.md` 1.1 places the rule in `LaunchPlaybook` construction
in `launch/domain/launch_playbook.py`, the same placement every existing
coherence rule has (`tests/unit/launch/domain/test_launch_playbook.py`),
so construction is the smallest unit that can observe it.

**Expected first-run state.** The rule does not exist yet: the rejection
tests are expected to fail because construction *succeeds* where they
assert it raises (a wrong-value failure over an absent rule, not an
absent target — the class under test exists). The coherent-construction
test is expected to pass already, since a fully held playbook is coherent
under the current rules too; it is here to pin the revised meaning of
"coherent", not to discriminate.

**Ripple, deliberately not repaired here.** Once this rule lands, every
existing test fixture that constructs a playbook with unheld gates
becomes invalid input. `tasks.md` 1.2 assigns that fixture repair to the
implementation step; per `ai-toolkit:testing` it is failure state 3
(broken fixture), never grounds to weaken what those tests assert.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

from typing import Any

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import step as _build_step


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _holding_step(gate: str) -> StepDefinition:
    """One blocking, framework-bound step holding `gate`.

    Automated with a rule policy so the fixture violates no other
    coherence rule (automation without a decided rule is a fault).
    """
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=0),
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        handler="fixture.holding_check",
        provenance=None,
    )


def _holding_steps(
    *, except_gates: frozenset[str] = frozenset()
) -> tuple[StepDefinition, ...]:
    return tuple(
        _holding_step(gate) for gate in SPECIFIED_GATE_ORDER if gate not in except_gates
    )


def _playbook(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    return _build_playbook(
        *steps,
        fill_unheld=False,
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


def test_a_gate_with_no_step_at_all_is_rejected_naming_the_gate() -> None:
    """Scenario: A gate with no blocking step is rejected (no step case).

    WHEN a playbook's steps leave any gate with no step whose blocking
    flag is true
    THEN loading fails with an error naming that gate.

    Every other gate is held, so the one named gate is the only fault.
    """
    steps = _holding_steps(except_gates=frozenset({"ignition"}))

    playbook = _playbook(steps)

    # SPECIFIED: the set constructs, and the readiness read names the gate
    # left unheld.
    assert playbook.unheld_gates == ("ignition",)
    assert not playbook.is_ready


def test_a_gate_with_only_non_blocking_steps_is_rejected() -> None:
    """Scenario: A gate with no blocking step is rejected (attached case).

    WHEN a gate has steps attached but none with a true blocking flag
    THEN loading fails with an error naming that gate.

    Sharper than the empty-gate case: a step being *attached* must not
    satisfy the floor — the rule reads the blocking flag, not attachment.
    """
    non_blocking_at_live = _step(
        identifier="live.launch-checklist-reviewed", gate="live", blocking=False
    )
    steps = (
        *_holding_steps(except_gates=frozenset({"live"})),
        non_blocking_at_live,
    )

    playbook = _playbook(steps)

    # SPECIFIED: the read names the gate, not the attached step — a step
    # being attached does not satisfy the floor.
    assert playbook.unheld_gates == ("live",)
    assert not playbook.is_ready


def test_the_floor_fault_is_reported_alongside_another_fault() -> None:
    """Scenario: Multiple violations are reported together — applied to
    the new rule.

    WHEN a playbook leaves a gate unheld and also carries a step whose
    name is empty
    THEN loading fails once, and the failure names both the gate and the
    step.

    The delta states the floor is "reported in the same aggregated
    `InvalidPlaybookError` as every other" fault (`tasks.md` 1.1); a rule
    raised eagerly on its own would fail this.

    The second fault was a `lesson`-bound blocking step until
    `redesign-step-fields` removed `binding` and its one rule; it is
    re-derived here from a surviving rule rather than dropped, because
    what this test is about is the aggregation, not either fault.
    """
    nameless = _step(
        identifier="creative.image-advice",
        gate="listable",
        name="   ",
    )
    steps = (
        *_holding_steps(except_gates=frozenset({"order"})),
        nameless,
    )

    # A single raised error is what establishes "fails once".
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps)

    message = str(caught.value)
    # SPECIFIED: the coherence fault is still reported, naming its step.
    assert "creative.image-advice" in message
    # SPECIFIED, and the half this change inverts: the unheld gate is no
    # longer a fault, so it is absent from the aggregated report — it is a
    # readiness fact now, and readable as one only once the set is
    # otherwise coherent enough to construct.
    assert "order" not in message
    assert _playbook(
        _holding_steps(except_gates=frozenset({"order"}))
    ).unheld_gates == ("order",)


def test_a_playbook_with_every_gate_held_constructs() -> None:
    """Scenario: A coherent playbook loads — as revised by this delta.

    WHEN a playbook satisfies every coherence rule, the gate-holding
    floor now among them
    THEN it loads successfully and exposes its gates and step definitions.

    Also the construction-rule half of *No gate opens for free* (MODIFIED
    requirement *Every gate is held by at least one blocking step*): the
    constructed playbook's steps, grouped by gate, leave no gate without
    a step whose blocking flag is true.
    """
    steps = _holding_steps()

    playbook = _playbook(steps)

    assert tuple(gate.identifier for gate in playbook.gates) == SPECIFIED_GATE_ORDER
    assert set(playbook.steps) == set(steps)

    # SPECIFIED (*No gate opens for free*): every gate has at least one
    # step with a true blocking flag.
    unheld = [
        gate.identifier
        for gate in playbook.gates
        if not any(
            step.blocking and step.gate == gate.identifier for step in playbook.steps
        )
    ]
    assert unheld == []
