"""The automation brief and the handler: what is required when, and by whom.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers, from the ADDED requirement *A step carries the brief and the
handler its automation needs*:

- *A draft automated step needs neither* — its one scenario, at load.
- *A human step carries no automation fields* — its one scenario, at
  load; the write half is
  `tests/unit/launch/application/test_step_status_transitions.py`.
- The requirement's load/activation split, which no scenario states in
  the affirmative and which is the distinction this requirement was
  revised to make: **that a handler is present is a load rule; that the
  running code registers it is checked only at activation and SHALL NOT
  be re-checked at load.**
- The definition of "beyond `draft`" — `in-development` or `active`, and
  never `retired`.

The two scenarios stated as writes — *Leaving draft requires the brief*
and *A handler the code does not register cannot be activated* — are
covered where the spec puts them, in
`tests/unit/launch/application/test_step_status_transitions.py`.

**Level.** `LaunchPlaybook` construction: the load-time rules are
construction invariants (`tasks.md` 1.3), so construction is the
smallest unit that can observe "loading fails" and "loading succeeds".

**Why the registration test matters.** An implementation that took a
handler registry into the load path would pass every other test in this
suite and would still be wrong in the way `design.md` Decision 6 names:
"a rename in the registry should fail a deployment, not take down
launches". The test below is the one that discriminates, and it works by
constructing a playbook with no registry in reach at all — a load that
consulted one could not succeed.

## Names are DERIVED

`tasks.md` 1.2 fixes the field names `automation_brief` and `handler`;
the enum member spellings and the module are DERIVED, as in
`test_step_lifecycle_status.py`.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

A_BRIEF: Final = "Buy Box share is at or above 90% over a rolling week."


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "automation_brief": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        status=StepStatus.ACTIVE,
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _authored(playbook: LaunchPlaybook) -> tuple[StepDefinition, ...]:
    """The authored read (INVENTED — see
    `test_step_lifecycle_status.py`, which owns this correction point)."""
    for name in ("authored_steps", "all_steps", "steps"):
        carried = getattr(playbook, name, None)
        if carried is None:
            continue
        return tuple(carried() if callable(carried) else carried)
    pytest.fail("the playbook exposes no authored read")


def _read_back(playbook: LaunchPlaybook, identifier: str) -> StepDefinition:
    for step in _authored(playbook):
        if step.identifier == identifier:
            return step
    raise AssertionError(f"{identifier!r} is not in the authored set")


# ---------------------------------------------------------------------------
# Requirement: A step carries the brief and the handler its automation needs
# ---------------------------------------------------------------------------


def test_a_draft_automated_step_needs_neither() -> None:
    """Scenario: A draft automated step needs neither.

    WHEN an automated step is created as a draft with no brief and no
    handler
    THEN the write is accepted.

    At this level "accepted" is the playbook constructing — the same
    predicate a write is validated against ("what a write cannot persist,
    a load cannot see"). This is the case the lifecycle status exists
    for: an author writing down work whose automation does not exist yet.
    """
    draft = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.DRAFT,
        automation_brief=None,
        handler=None,
    )

    playbook = _playbook(steps=(draft,))

    read_back = _read_back(playbook, "price.buy-box-check")
    assert read_back.automation_brief is None
    assert read_back.handler is None


def test_an_automated_step_beyond_draft_without_a_brief_is_rejected() -> None:
    """Requirement statement: "The brief SHALL be required to leave
    `draft`".

    Covered here at `in-development`, the status the seeded automated
    steps land in, so the rule is established against the value that is
    not `active` — an implementation checking the brief only at `active`
    would pass a test using `active` alone.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.IN_DEVELOPMENT,
        automation_brief=None,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "price.buy-box-check" in str(caught.value)


def test_a_retired_automated_step_owes_no_brief() -> None:
    """Requirement statement: ""Beyond `draft`" means `in-development` or
    `active`, and does not include `retired`: a step abandoned before its
    automation was ever specified is retired without ever owing a brief".

    This is the one place the definition bites, and an implementation
    reading "beyond draft" as "any status other than draft" would make
    every such step unretirable — its playbook would stop loading.
    """
    abandoned = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.RETIRED,
        automation_brief=None,
        handler=None,
    )

    playbook = _playbook(steps=(abandoned,))

    # SPECIFIED: it loads, carrying neither.
    assert _read_back(playbook, "price.buy-box-check").automation_brief is None


def test_an_active_automated_step_without_a_handler_is_rejected() -> None:
    """Requirement statement: "That a handler is *present* is a property
    of the step set, and is checked whenever the playbook is loaded."

    The presence half of the load/activation split. Its counterpart —
    that *registration* is not checked here — is the test below.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        automation_brief=A_BRIEF,
        handler=None,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    assert "price.buy-box-check" in str(caught.value)


def test_a_load_never_checks_whether_the_handler_is_registered() -> None:
    """Requirement statement: "That the running code actually
    **registers** it is not [a property of the step set] ... so it SHALL
    be checked when a step is activated and SHALL NOT be re-checked at
    load, for the same reason assignees are not: a rename in the registry
    would otherwise make every stored playbook unloadable, taking down
    launches to report a deployment fault."

    The discriminating test of `design.md` Decision 6 as applied to the
    registry. The handler named below is deliberately one no code could
    plausibly answer for, and construction is handed no registry at all:
    a load that consulted one could not succeed here.

    SPECIFIED: the playbook loads and the step is served. What a
    deployment whose registry no longer answers for it must do instead —
    report at startup — is `playbook-authoring`'s, and is covered in
    `tests/unit/launch/application/test_step_status_transitions.py`.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        automation_brief=A_BRIEF,
        handler="handler.no.deployment.has.ever.registered",
    )

    playbook = _playbook(steps=(step,))

    # SPECIFIED: loading succeeds...
    read_back = _read_back(playbook, "price.buy-box-check")
    assert read_back.handler == "handler.no.deployment.has.ever.registered"
    # ...and the step is served, not quietly withheld.
    assert "price.buy-box-check" in {
        step.identifier for step in playbook.steps_for_gate("listable")
    }


def test_a_human_step_carrying_an_automation_brief_is_rejected() -> None:
    """Scenario: A human step carries no automation fields (brief).

    WHEN a `human` step is written with an automation brief
    THEN the write is rejected with a fault naming the step.
    """
    step = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        automation_brief=A_BRIEF,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    assert "listing.title-conforms" in str(caught.value)


def test_a_human_step_carrying_a_handler_is_rejected() -> None:
    """Scenario: A human step carries no automation fields (handler).

    Covered separately from the brief because the spec names both, and
    an implementation checking only one would pass a test covering only
    the other. This is also the rule the seed migration must respect:
    copying `rule_policy` onto the 95 rows becoming `human` steps would
    produce an unloadable playbook (`tasks.md` 3.2).
    """
    step = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        handler="listing.title_conforms",
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    assert "listing.title-conforms" in str(caught.value)


def test_an_automated_step_with_both_is_accepted() -> None:
    """The permitted side, without which an implementation that rejected
    every automated step would pass the four rejection tests above.

    Same permitted-side pattern the existing suite applies to the
    prohibited-tactic rule (`test_launch_playbook.py`).
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        automation_brief=A_BRIEF,
        handler="price.buy_box_check",
    )

    read_back = _read_back(_playbook(steps=(step,)), "price.buy-box-check")

    assert read_back.automation_brief == A_BRIEF
    assert read_back.handler == "price.buy_box_check"
