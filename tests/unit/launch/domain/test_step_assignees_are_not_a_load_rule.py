"""Assignees on the step, and the rule the load path must *not* have.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers, from the ADDED requirement *A step names the membership responsible
for it*, the half that lives at load:

> Both rules above are **write-time preconditions, not load-time
> coherence rules** ... A load SHALL NOT re-check assignees: a step
> whose assignee has since been deactivated SHALL continue to load and
> be served.

and the field's own shape — zero or more members, referenced by the
membership's generated identifier rather than by name or Slack identity.

The requirement's four scenarios are all stated as writes and are
covered in
`tests/unit/launch/application/test_step_assignee_preconditions.py`.
This file exists for the rule *no scenario states*, because it is the
one an implementation is most likely to get wrong: assignee validation
reads naturally as a coherence rule, and putting it there would mean a
members deactivation retroactively makes a stored playbook unloadable —
"a write in another module breaking a capability that accepted no
write", which is what `design.md` Decision 6 refuses.

The discriminating construction below is a playbook handed **no members
at all**, carrying an `active` `human` step that names nobody and
another naming an identifier no membership could match. A load that
evaluated either rule could not succeed.

**Level.** `LaunchPlaybook` construction — where every load-time rule
lives (`tasks.md` 1.3), and therefore the only level at which "the load
path does not have this rule" is observable.

## Names are DERIVED

`tasks.md` 1.2 fixes the field name `assignees`; that it holds the
membership's generated identifiers is SPECIFIED ("each referencing a member
by the membership's own generated identifier"), while their *form* is not
fixed by any artifact here — so nothing below asserts a format, only
that what goes in comes back and that no name or Slack identity is
carried alongside.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

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

# DERIVED sample identifiers. `members` generates them; no artifact fixes
# their form, so nothing below depends on it.
MEMBER_A: Final = "prs_01HQ8Z6M4A"
MEMBER_B: Final = "prs_01HQ8Z6M4B"
NOBODY_IS_A_MEMBER: Final = "prs_00000000NO"


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
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
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


def _served(playbook: LaunchPlaybook, gate: str) -> dict[str, StepDefinition]:
    return {step.identifier: step for step in playbook.steps_for_gate(gate)}


# ---------------------------------------------------------------------------
# The rule the load path must not have
# ---------------------------------------------------------------------------


def test_an_active_human_step_naming_nobody_still_loads_and_is_served() -> None:
    """Requirement statement: assignee rules are "write-time
    preconditions, not load-time coherence rules".

    This is the state the migration deliberately leaves behind: 95
    migrated `human` steps, `active` and unowned (`design.md` Migration
    Plan step 2). Were the assignee rule a coherence rule, the migrated
    set would not load at all — the whole capability would be down on the
    deploy that shipped it.
    """
    unowned = _step(identifier="listing.title-conforms", assignees=())

    playbook = _playbook(steps=(unowned,))

    # SPECIFIED: it continues to load and be served.
    assert "listing.title-conforms" in _served(playbook, "listable")


def test_a_step_whose_assignee_the_members_no_longer_carries_still_loads() -> None:
    """Requirement statement: "a step whose assignee has since been
    deactivated SHALL continue to load and be served, and SHALL appear in
    the report of what a step still needs".

    Constructed with no members in reach, so a load that consulted one
    could not succeed. Note what is *not* asserted: that the identifier
    below is unknown to some members — there is no members here. What is
    asserted is that the load neither knows nor asks.

    The report half is covered in
    `tests/unit/launch/application/test_report_activation_blockers.py`.
    """
    step = _step(
        identifier="listing.title-conforms",
        assignees=(NOBODY_IS_A_MEMBER,),
    )

    playbook = _playbook(steps=(step,))

    served = _served(playbook, "listable")
    assert "listing.title-conforms" in served
    # SPECIFIED: the reference is carried through unaltered — a load that
    # dropped an unresolvable assignee would be re-checking it by another
    # route.
    assert served["listing.title-conforms"].assignees == (NOBODY_IS_A_MEMBER,)


def test_a_playbook_construction_takes_no_members() -> None:
    """`design.md` Decision 6's rejected alternative, pinned: "give the
    load path a members reader ... Rejected — it makes every playbook read
    depend on another module's store being reachable".

    DERIVED probe, not exhaustive: the constructor exposes no parameter
    that would be a membership in disguise. Recorded as derived in
    `test-manifest.md` — the spec fixes that the load does not evaluate
    the rules, and this pins the seam that would let it.
    """
    import inspect

    parameters = set(inspect.signature(LaunchPlaybook).parameters)

    assert not parameters & {
        "members",
        "known_members",
        "active_members",
        "members_reader",
        "read_members",
        "handlers",
        "registry",
        "handler_registry",
    }, (
        f"LaunchPlaybook takes a membership or registry collaborator: {sorted(parameters)}"
    )


# ---------------------------------------------------------------------------
# The field itself
# ---------------------------------------------------------------------------


def test_a_step_may_name_zero_one_or_several_members() -> None:
    """Requirement statement: "Each step definition SHALL be able to name
    zero or more assignees"; and, for an `automated` step, "MAY name
    assignees ... and MAY name none".
    """
    none_named = _step(identifier="listing.unowned", assignees=())
    one_named = _step(identifier="listing.owned", assignees=(MEMBER_A,))
    two_named = _step(identifier="listing.shared", assignees=(MEMBER_A, MEMBER_B))
    automated_with_members = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        handler="price.buy_box_check",
        assignees=(MEMBER_B,),
    )

    served = _served(
        _playbook(steps=(none_named, one_named, two_named, automated_with_members)),
        "listable",
    )

    assert served["listing.unowned"].assignees == ()
    assert served["listing.owned"].assignees == (MEMBER_A,)
    assert tuple(served["listing.shared"].assignees) == (MEMBER_A, MEMBER_B)
    # SPECIFIED: an automated step may name assignees or none; naming
    # them no longer says who is asked to confirm a result.
    assert served["price.buy-box-check"].assignees == (MEMBER_B,)


_NOT_ON_A_STEP: Final = (
    "assignee_names",
    "assignee_display_names",
    "assignee_slack_ids",
    "assignee_identities",
    "owners_by_name",
)


def test_assignees_are_references_and_never_copied_details() -> None:
    """Requirement statement: "Assignees SHALL be referenced by identifier
    rather than by name or Slack identity, so that correcting a member's
    details never rewrites the steps that point at them" — and
    `design.md` Decision 7's rejected alternative, "copy the member's name
    and ClickUp id onto the step at authoring time. Rejected".

    DERIVED probe of the spellings such a copy would take; recorded as
    derived. The behavioural half — a display-name correction leaves
    every step naming that member unchanged — is
    `test_step_assignee_preconditions.py`'s scenario.
    """
    step = _step(assignees=(MEMBER_A,))

    for name in _NOT_ON_A_STEP:
        assert not hasattr(step, name), (
            f"StepDefinition exposes {name!r}: a step references a member "
            "by the membership's identifier and copies nothing about them"
        )


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The *form* of a member identifier. `members` generates it and no
#   artifact of this change fixes it, so pinning a format here would
#   invent a constraint on another capability.
# - Whether `assignees` preserves the order it was given. Nothing in the
#   spec makes assignees ordered; `test_a_step_may_name_zero_one_or_
#   several_members` asserts order only where it was written that way, and
#   a set-like implementation failing that assertion is a finding for
#   review, not a fixture to loosen without one.
