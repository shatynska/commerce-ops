"""A step's lifecycle status, and what "served" means once it exists.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers the ADDED requirement *A step declares a lifecycle status, and
only active steps are served* — all three scenarios — plus the two
statements that requirement makes about the field itself: status is
declared explicitly with `draft` the value an author who declares
nothing gets, and "beyond `draft`" means `in-development` or `active`
and never `retired` (the latter exercised where it bites, in
`test_step_automation_brief_and_handler.py`).

**Level.** Every coherence rule of this playbook is a `LaunchPlaybook`
construction invariant (`tasks.md` 1.3–1.4, and the placement every
existing rule already has — see `test_launch_playbook.py`), and the
served/authored split is a property of the constructed playbook's own
queries, so construction is the smallest unit that can observe these
scenarios.

## The field set under test does not exist yet, and names are DERIVED

`tasks.md` 1.1–1.2 fix the two new enums (`StepKind`, `StepStatus`) and
the field names `name`, `assignees`, `kind`, `needs_confirmation`,
`status`, `automation_brief`, `handler`; the *member spellings*
(`StepStatus.IN_DEVELOPMENT` for the spec's `in-development`) are
DERIVED, as is the module they live in — the same module `Binding` and
`ExecutionMode` are deleted from.

INVENTED, recorded in `test-manifest.md` as an unresolved project
question: how the **authored** set is read back off a constructed
playbook. The spec fixes that the by-gate and by-scope queries answer
the *served* set and that non-active steps "remain readable to whoever
authors the step set", but names no accessor. `_authored()` below probes
a small set of spellings and fails loudly rather than defaulting, so no
assertion here can pass vacuously; it is the single correction point.

## Expected first-run state

`StepKind` and `StepStatus` do not exist, so every test here is expected
to fail on an absent target (`ImportError`). Per `ai-toolkit:testing`
that establishes absence only — nothing about whether these assertions
are any good.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed (the integration
tier skips: no database is configured here).
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


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
    """A coherent step, overridable one attribute at a time.

    The baseline is `human`, `active`, non-blocking and description-less
    — a step carrying nothing the new rules could object to, so a
    failure a test provokes is the one it intended. Assignees are empty
    even though the step is `active` and `human`: that rule is a
    write-time precondition and never a load-time one (see
    `test_step_assignees.py`).
    """
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
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """An `active` blocking filler holding `gate`.

    The gate-holding floor counts only `active` blocking steps, so every
    fixture needs one per gate before it can construct at all.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        status=StepStatus.ACTIVE,
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=_fill(steps))


def _served(playbook: LaunchPlaybook) -> set[str]:
    """Every step identifier the playbook's own by-gate query answers.

    SPECIFIED: "The playbook's own step queries — by gate, by scope —
    SHALL answer the **served** set".
    """
    return {
        step.identifier
        for gate in SPECIFIED_GATE_ORDER
        for step in playbook.steps_for_gate(gate)
    }


_AUTHORED_ACCESSORS: Final = ("authored_steps", "all_steps", "steps")


def _authored(playbook: LaunchPlaybook) -> set[str]:
    """Every step identifier the authored read answers (INVENTED — see
    the module docstring). The single correction point for that read's
    spelling."""
    for name in _AUTHORED_ACCESSORS:
        carried = getattr(playbook, name, None)
        if carried is None:
            continue
        steps = carried() if callable(carried) else carried
        return {step.identifier for step in steps}
    pytest.fail(
        f"the playbook exposes no authored read under any of "
        f"{_AUTHORED_ACCESSORS} — correct this file's accessor names to "
        "the implemented read"
    )


# ---------------------------------------------------------------------------
# Requirement: A step declares a lifecycle status, and only active steps
# are served
# ---------------------------------------------------------------------------


def test_a_draft_step_is_authored_but_not_served() -> None:
    """Scenario: A draft step is authored but not served.

    WHEN a step is created with status `draft`
    THEN it is readable in the authored set, and the served playbook does
    not carry it.
    """
    draft = _step(identifier="listing.draft-work", status=StepStatus.DRAFT)

    playbook = _playbook(steps=(draft,))

    # SPECIFIED: readable in the authored set...
    assert "listing.draft-work" in _authored(playbook)
    # ...and absent from every served view.
    assert "listing.draft-work" not in _served(playbook)
    assert "listing.draft-work" not in {
        step.identifier for step in playbook.steps_with_scope(Scope.PRODUCT)
    }


def test_only_active_steps_hold_a_gate() -> None:
    """Scenario: Only active steps hold a gate.

    WHEN a gate holds one active blocking step and one `in-development`
    blocking step
    THEN only the active one holds the gate, and the `in-development` one
    contributes no obligation.
    """
    active_blocker = _step(
        identifier="ignition.ppc-armed",
        gate="ignition",
        blocking=True,
        status=StepStatus.ACTIVE,
    )
    in_development_blocker = _step(
        identifier="ignition.price-watch",
        gate="ignition",
        blocking=True,
        status=StepStatus.IN_DEVELOPMENT,
    )

    playbook = _playbook(steps=(active_blocker, in_development_blocker))

    served_at_ignition = {
        step.identifier for step in playbook.steps_for_gate("ignition")
    }
    # SPECIFIED: only the active one is served, so only it can hold the
    # gate...
    assert "ignition.ppc-armed" in served_at_ignition
    # ...and the `in-development` one contributes no obligation, which at
    # this level is exactly its absence from the gate's served steps.
    assert "ignition.price-watch" not in served_at_ignition
    # SPECIFIED: it is nonetheless still authored, not discarded.
    assert "ignition.price-watch" in _authored(playbook)


def test_a_retired_step_leaves_the_served_set_without_leaving_the_record() -> None:
    """Scenario: A retired step leaves the served set without leaving the
    record.

    WHEN a step's status becomes `retired`
    THEN it is no longer served, and it remains readable to authors with
    its history intact.

    "History intact" at this level is the definition itself surviving
    whole under its own identifier; the attribution half — who retired it
    and when — is `playbook-authoring`'s and is covered in
    `tests/unit/launch/application/test_step_status_transitions.py`.
    """
    retired = _step(
        identifier="listing.superseded-copy",
        name="Copy the reference row asked for, since superseded",
        description="The longer statement of the work, kept for the record.",
        status=StepStatus.RETIRED,
        provenance="product-launch.md · BUILD THE LISTING · row 12",
    )

    playbook = _playbook(steps=(retired,))

    # SPECIFIED: no longer served.
    assert "listing.superseded-copy" not in _served(playbook)
    # SPECIFIED: still readable to authors, with what it carried intact.
    assert "listing.superseded-copy" in _authored(playbook)
    read_back = next(
        step
        for name in ("authored_steps", "all_steps", "steps")
        if getattr(playbook, name, None) is not None
        for step in (
            getattr(playbook, name)()
            if callable(getattr(playbook, name))
            else getattr(playbook, name)
        )
        if step.identifier == "listing.superseded-copy"
    )
    assert read_back.name == "Copy the reference row asked for, since superseded"
    assert read_back.description == (
        "The longer statement of the work, kept for the record."
    )
    assert read_back.provenance == "product-launch.md · BUILD THE LISTING · row 12"


# ---------------------------------------------------------------------------
# Requirement statements about the field itself
# ---------------------------------------------------------------------------


def test_status_has_exactly_the_four_specified_values() -> None:
    """Requirement statement: "Each step definition SHALL declare a
    status: `draft`, `in-development`, `active` or `retired`".

    SPECIFIED: the set is closed at four — a fifth value would put the
    model outside the specification, and every status-dependent rule
    below is written against exactly these.

    DERIVED: the member *names*. The spec gives the wire values; this
    asserts the set's size and that it holds the four membership the rest of
    this suite uses, rather than pinning `.value` spellings no artifact
    fixes for the domain layer.
    """
    assert len(set(StepStatus)) == 4
    assert {
        StepStatus.DRAFT,
        StepStatus.IN_DEVELOPMENT,
        StepStatus.ACTIVE,
        StepStatus.RETIRED,
    } == set(StepStatus)


def test_a_step_whose_author_declares_no_status_is_a_draft() -> None:
    """Requirement statement: "Status SHALL be declared explicitly, with
    `draft` the value a step carries when its author declares nothing".

    Constructed without a status, so the test exercises the default
    rather than restating it.
    """
    step = StepDefinition(
        identifier="strategy.written-down",
        name="Write the phase-one exit criteria down",
        gate="commit",
        discipline=_any_discipline(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-90),
        blocking=False,
        kind=StepKind.HUMAN,
    )

    # SPECIFIED: `draft` when the author declares nothing.
    assert step.status is StepStatus.DRAFT
    # ...and therefore not served.
    assert "strategy.written-down" not in _served(_playbook(steps=(step,)))


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - Which read the admin surface uses to reach the authored set. The spec
#   says it is "the read the admin surface already uses to reveal retired
#   steps"; that the page shows drafts is `playbook-admin`'s scenario and
#   is covered in
#   `tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py`.
# - That the four statuses are ordered, or that any status must be
#   climbed to reach another. The spec explicitly says "Any status MAY
#   move to any other" and "there is no transition table to consult", so
#   asserting an ordering would invent the rule this requirement denies.
