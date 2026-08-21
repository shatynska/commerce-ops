"""Tests for the `LaunchPlaybook` domain model.

Derived from the delta spec:
openspec/changes/add-launch-playbook/specs/launch-playbook/spec.md

Covers the requirements *Gate sequence orders the launch*, *A step
definition declares how it is to be resolved*, *Hazard classification
distinguishes what is refused from what is complied with*, *Provenance
references are never identifiers*, *Playbooks are versioned*, *An
incoherent playbook is rejected at load time*, and *An undecided rule does
not prevent loading*.

Every requirement in that spec is `ADDED`; no prior `launch-playbook` spec
exists. These tests were written from the scenarios alone, before any
implementation, and were never run against implementation code.

**Level.** The coherence rules are exercised through `LaunchPlaybook`
construction rather than through the YAML loader, because `tasks.md` 3.5
places them there ("Implement the five coherence rules as playbook
construction invariants") and construction is the smallest unit that can
observe the outcome. The two scenarios that genuinely need the file
boundary — a malformed step reported alongside a coherence violation, and
the gate opening modes, which no coherence rule validates — live in
`tests/unit/products/infrastructure/test_playbook_loader.py`.

At the time of writing `src/commerce_ops/products/domain/` is empty
scaffolding, so every test here is expected to fail on an absent target
(`ModuleNotFoundError`). That failure establishes only that the target is
absent; it establishes nothing about the assertions, which never executed.

Names imported from the domain are DERIVED — no artifact fixes module
paths, class names or field names. See
`openspec/changes/add-launch-playbook/test-manifest.md`.

**Follow-up pass (this file's tail, second delivery).** Two tests were
added after the rest of this file was written and the suite's collection
state confirmed unchanged: `test_each_specified_track_value_is_accepted` /
`test_track_outside_the_fixed_set_is_rejected` (new *Track names one of a
fixed set of disciplines* requirement) and
`test_gate_opening_mode_disagreeing_with_the_specification_is_rejected`
(sixth coherence rule, added to *An incoherent playbook is rejected at
load time*). Nothing above this note was edited.
"""

from __future__ import annotations

from typing import Any, Final

import pytest
from commerce_ops.products.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    Track,
    WindowAnchor,
)

# SPECIFIED: the eight gates, in this order (Requirement: Gate sequence
# orders the launch).
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

# SPECIFIED: "commit, order, phase-one-complete and graduated require
# confirmation, and listable, stock-ready, live and ignition open
# automatically" (Requirement: A gate declares how it opens).
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


def _any_track() -> Track:
    """Return some `Track` member, asserting nothing about which.

    DERIVED / unresolved project question: no artifact enumerates the
    tracks. `tasks.md` 2.1 says only that `Track` is an enumeration.
    Constructing a `StepDefinition` needs a track value, so these tests
    take the first member rather than naming one — nothing here depends on
    the track set, and hard-coding a member would invent a constraint.
    """
    return next(iter(Track))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def specified_gates() -> tuple[Gate, ...]:
    """The eight gates in the specified order, with distinct positions.

    DERIVED: positions are numbered from 1, matching the numbered list in
    the spec. The spec does not actually fix the base, so no assertion
    below depends on it — see `test_gates_expose_a_stable_order`.
    """
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    """Build a valid `StepDefinition`, overriding named attributes.

    The baseline values are a coherent step, chosen so that a test can
    change one attribute and know the failure it provokes is the one it
    intended.
    """
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "gate": "listable",
        "track": _any_track(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "binding": Binding.FRAMEWORK,
        "blocking": False,
        "execution": ExecutionMode.HUMAN_ATTESTED,
        "hazard": Hazard.NONE,
        "rule_policy": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook(
    *,
    version: str = "test-v1",
    gates: tuple[Gate, ...] | None = None,
    steps: tuple[StepDefinition, ...] = (),
) -> LaunchPlaybook:
    return LaunchPlaybook(
        version=version,
        gates=specified_gates() if gates is None else gates,
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Requirement: Gate sequence orders the launch
# ---------------------------------------------------------------------------


def test_gates_expose_a_stable_order() -> None:
    """Scenario: Gates expose a stable order.

    WHEN the playbook's gates are read
    THEN they are returned in the defined order, each carrying its position
    in the sequence
    AND two gates never share a position.
    """
    gates = _playbook().gates

    # SPECIFIED: exactly the eight gates, in the defined order.
    assert [gate.identifier for gate in gates] == list(SPECIFIED_GATE_ORDER)

    positions = [gate.position for gate in gates]
    # SPECIFIED: two gates never share a position.
    assert len(set(positions)) == len(positions)
    # SPECIFIED: each gate carries its position *in the sequence* — so
    # position must agree with the order the gates are returned in.
    # DELIBERATELY UNTESTED: whether positions are numbered from 0 or from
    # 1. The spec fixes the order, not the base, so this asserts only that
    # the numbering ascends with the sequence.
    assert positions == sorted(positions)


# DERIVED: attribute names that would express an ordering between two
# steps. The spec forbids the concept ("Step definitions attached to the
# same gate SHALL carry no ordering relative to one another"; "Gates SHALL
# be the only ordering primitive"), not any particular spelling of it, so
# this list is a best-effort probe rather than an exhaustive one.
ORDERING_ATTRIBUTE_NAMES: Final = (
    "position",
    "order",
    "sequence",
    "index",
    "rank",
    "priority",
    "depends_on",
    "dependencies",
    "after",
    "before",
    "predecessor",
    "successor",
)


def test_steps_at_the_same_gate_carry_no_ordering() -> None:
    """Scenario: Steps at the same gate are unordered.

    WHEN two step definitions declare the same gate
    THEN the playbook expresses no ordering between them.
    """
    first = _step(identifier="listing.first", gate="listable")
    second = _step(identifier="listing.second", gate="listable")

    forward = _playbook(steps=(first, second))
    reversed_ = _playbook(steps=(second, first))

    # SPECIFIED: authoring order carries no meaning, so the same two steps
    # are attached to the gate either way round.
    assert {step.identifier for step in forward.steps_for_gate("listable")} == {
        "listing.first",
        "listing.second",
    }
    assert {step.identifier for step in reversed_.steps_for_gate("listable")} == {
        "listing.first",
        "listing.second",
    }

    # SPECIFIED: a step definition carries no ordering relative to another.
    # If a step grew an ordering attribute, the model would express an
    # ordering the spec says does not exist.
    for name in ORDERING_ATTRIBUTE_NAMES:
        assert not hasattr(first, name), (
            f"StepDefinition exposes {name!r}: gates are meant to be the "
            f"only ordering primitive in the playbook"
        )


# ---------------------------------------------------------------------------
# Requirement: Track names one of a fixed set of disciplines
#
# Added on a follow-up pass, after the rest of this file was written and
# committed (see the module docstring). Not present in the delta spec at
# the time of the first pass.
# ---------------------------------------------------------------------------

# SPECIFIED: the twelve disciplines a step definition's track may declare
# (Requirement: Track names one of a fixed set of disciplines).
SPECIFIED_TRACKS: Final = (
    "strategy",
    "finance",
    "setup",
    "inventory",
    "creative",
    "listing",
    "rank",
    "price",
    "ppc",
    "customer",
    "external",
    "traffic",
)


@pytest.mark.parametrize("track_name", SPECIFIED_TRACKS)
def test_each_specified_track_value_is_accepted(track_name: str) -> None:
    """Scenario: Track is restricted to the known disciplines (permitted side).

    Not itself a `#### Scenario:` block — the spec's rejection scenario
    only forbids a track *outside* the fixed set of twelve, so this checks
    the permitted complement: an implementation that rejected every track,
    known or not, would still pass
    `test_track_outside_the_fixed_set_is_rejected` alone. Same relationship
    as `test_automated_step_with_a_rule_policy_is_accepted` bears to its
    rejection scenario, above.

    DERIVED: the mapping from the spec's wire spelling (e.g. `"strategy"`)
    to a `Track` member name (`Track.STRATEGY`) follows the same
    hyphen-to-underscore, upper-case convention already assumed for
    `Hazard` elsewhere in this file (see `test_hazard_classification_...`
    and the manifest's Q2) — no artifact fixes `Track`'s Python member
    names, only its twelve wire values, which the spec now states in full.
    """
    track = getattr(Track, track_name.upper())
    step = _step(identifier=f"track.{track_name}-example", track=track)

    (read_back,) = _playbook(steps=(step,)).steps_for_gate(step.gate)

    # SPECIFIED: a step definition declaring one of the twelve disciplines
    # is accepted and read back with that track.
    assert read_back.track is track


def test_track_outside_the_fixed_set_is_rejected() -> None:
    """Scenario: Track is restricted to the known disciplines.

    WHEN a step definition declares a track outside this set
    THEN loading fails with an error naming the step and the unrecognised
    track.

    Checked at `StepDefinition` construction directly, per `tasks.md` 3.2
    ("reject a track outside the fixed set of twelve at construction") —
    unlike an unknown *gate* (which needs a playbook's gate sequence to
    judge against, see `test_step_referencing_an_unknown_gate_is_rejected`
    below), an unrecognised track needs no playbook context: the set of
    twelve disciplines is fixed independent of any one playbook.

    DERIVED: `InvalidPlaybookError` as the raised type, and a raw string
    (`"not-a-recognised-track"`) as how an unrecognised track is
    "declared" at this level. The spec requires only "an error naming the
    step and the unrecognised track"; this file's other rejection tests
    that use this same "loading fails with an error naming X" phrasing all
    raise `InvalidPlaybookError`, so the same type is assumed here — see
    the manifest's Q2, extended to cover this scenario.
    """
    with pytest.raises(InvalidPlaybookError) as caught:
        _step(identifier="listing.mystery-track", track="not-a-recognised-track")

    # SPECIFIED: the error names the step and the unrecognised track.
    message = str(caught.value)
    assert "listing.mystery-track" in message
    assert "not-a-recognised-track" in message


# ---------------------------------------------------------------------------
# Requirement: A step definition declares how it is to be resolved
# ---------------------------------------------------------------------------


def test_step_definition_is_read_back_with_every_declared_attribute() -> None:
    """Scenario: A step definition is read back with every declared attribute.

    WHEN a step definition is read from a loaded playbook
    THEN its identifier, gate, track, scope, timing anchor, binding,
    blocking flag, execution mode, and hazard classification are all
    present.
    """
    track = _any_track()
    anchor = WindowAnchor(start=28, end=55)
    step = _step(
        identifier="inventory.fulfillable-units",
        gate="stock-ready",
        track=track,
        scope=Scope.MARKET,
        timing_anchor=anchor,
        binding=Binding.LESSON,
        blocking=True,
        execution=ExecutionMode.HUMAN_ATTESTED,
        hazard=Hazard.COMPLIANCE_OBLIGATION,
        rule_policy="At least 60 fulfillable units checked in.",
        provenance="lp.inventory.040",
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("stock-ready")

    # SPECIFIED: each of the nine mandatory attributes is present and is
    # what was declared.
    assert read_back.identifier == "inventory.fulfillable-units"
    assert read_back.gate == "stock-ready"
    assert read_back.track is track
    assert read_back.scope is Scope.MARKET
    assert read_back.timing_anchor == anchor
    assert read_back.binding is Binding.LESSON
    assert read_back.blocking is True
    assert read_back.execution is ExecutionMode.HUMAN_ATTESTED
    assert read_back.hazard is Hazard.COMPLIANCE_OBLIGATION
    # SPECIFIED: rule policy and provenance are present when authored.
    assert read_back.rule_policy == "At least 60 fulfillable units checked in."
    assert read_back.provenance == "lp.inventory.040"


def test_unauthored_optional_attributes_are_absent() -> None:
    """Scenario: A step definition is read back with every declared attribute.

    ...AND its rule policy and provenance reference are present only if
    authored.

    Also covers Scenario: *Classification is always present* — the same
    construction omits the hazard classification, which the spec says
    defaults to `none`.
    """
    # Constructed without hazard, rule policy or provenance, so the test
    # exercises the defaults rather than restating them.
    step = StepDefinition(
        identifier="strategy.undecided",
        gate="commit",
        track=_any_track(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-90),
        binding=Binding.FRAMEWORK,
        blocking=False,
        execution=ExecutionMode.HUMAN_ATTESTED,
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("commit")

    # SPECIFIED: present only if authored.
    assert read_back.rule_policy is None
    assert read_back.provenance is None
    # SPECIFIED: hazard classification defaults to `none` when the author
    # declared nothing, and is one of the three classifications.
    assert read_back.hazard is Hazard.NONE
    assert read_back.hazard in set(Hazard)


def test_steps_can_be_selected_by_gate_and_by_scope() -> None:
    """Scenario: Steps can be selected by gate and by scope.

    WHEN the playbook is queried for the steps attached to a given gate
    THEN exactly the step definitions declaring that gate are returned
    AND the same holds when querying by scope.
    """
    product_listable = _step(
        identifier="sourcing.unit-economics", gate="listable", scope=Scope.PRODUCT
    )
    market_listable = _step(
        identifier="listing.a-plus-content", gate="listable", scope=Scope.MARKET
    )
    market_live = _step(
        identifier="rank.indexation-confirmed", gate="live", scope=Scope.MARKET
    )

    playbook = _playbook(steps=(product_listable, market_listable, market_live))

    # SPECIFIED: exactly the steps declaring that gate — no more, no fewer.
    assert {step.identifier for step in playbook.steps_for_gate("listable")} == {
        "sourcing.unit-economics",
        "listing.a-plus-content",
    }
    assert {step.identifier for step in playbook.steps_for_gate("live")} == {
        "rank.indexation-confirmed"
    }
    assert list(playbook.steps_for_gate("graduated")) == []

    # SPECIFIED: the same holds when querying by scope.
    assert {step.identifier for step in playbook.steps_with_scope(Scope.MARKET)} == {
        "listing.a-plus-content",
        "rank.indexation-confirmed",
    }
    assert {step.identifier for step in playbook.steps_with_scope(Scope.PRODUCT)} == {
        "sourcing.unit-economics"
    }


# ---------------------------------------------------------------------------
# Requirement: Hazard classification distinguishes what is refused from what
# is complied with
# ---------------------------------------------------------------------------


def test_compliance_obligation_may_block_a_gate() -> None:
    """Scenario: A compliance obligation may block a gate.

    WHEN a step definition is classified `compliance-obligation` and marked
    as blocking its gate
    THEN the playbook loads successfully.
    """
    step = _step(
        identifier="listing.gs1-record-matches",
        gate="listable",
        hazard=Hazard.COMPLIANCE_OBLIGATION,
        blocking=True,
    )

    playbook = _playbook(steps=(step,))

    # SPECIFIED: no restriction applies to a compliance obligation.
    (read_back,) = playbook.steps_for_gate("listable")
    assert read_back.blocking is True
    assert read_back.hazard is Hazard.COMPLIANCE_OBLIGATION


def test_hazard_classification_has_exactly_the_three_specified_values() -> None:
    """Scenario: Classification is always present.

    THEN it reports one of the three hazard classifications.

    SPECIFIED: the spec names exactly three — `none`, `prohibited-tactic`,
    `compliance-obligation` — and says a step declares exactly one of them,
    so a fourth value would put the model outside the specification.

    DERIVED: the member *names* below. The spec gives the wire values, not
    Python identifiers; `tasks.md` 2.1 repeats the wire values. This
    asserts the classification set has size three and contains the three
    members the rest of this file uses, rather than asserting on `.value`
    spellings the artifacts do not fix for the domain layer.
    """
    assert len(set(Hazard)) == 3
    assert {Hazard.NONE, Hazard.PROHIBITED_TACTIC, Hazard.COMPLIANCE_OBLIGATION} == set(
        Hazard
    )


# ---------------------------------------------------------------------------
# Requirement: Provenance references are never identifiers
# ---------------------------------------------------------------------------


def test_two_steps_may_cite_the_same_provenance_reference() -> None:
    """Scenario: Two steps cite the same source row.

    WHEN two step definitions declare the same provenance reference
    THEN the playbook loads successfully
    AND each step remains addressable only by its own identifier.
    """
    first = _step(identifier="inventory.cover-floor", provenance="lp.inventory.040")
    second = _step(identifier="inventory.cover-ceiling", provenance="lp.inventory.040")

    playbook = _playbook(steps=(first, second))

    # SPECIFIED: a shared provenance reference is not a uniqueness fault.
    by_identifier = {step.identifier: step for step in playbook.steps}
    assert set(by_identifier) == {"inventory.cover-floor", "inventory.cover-ceiling"}
    assert by_identifier["inventory.cover-floor"].provenance == "lp.inventory.040"
    assert by_identifier["inventory.cover-ceiling"].provenance == "lp.inventory.040"

    # SPECIFIED: a provenance reference is not usable to address a step.
    assert "lp.inventory.040" not in by_identifier


# ---------------------------------------------------------------------------
# Requirement: Playbooks are versioned
# ---------------------------------------------------------------------------


def test_playbook_reports_the_version_it_was_authored_with() -> None:
    """Scenario: The loaded playbook reports its version.

    WHEN a playbook is loaded
    THEN it reports the version identifier it was authored with.

    The same scenario is covered against the shipped data file, through the
    real loader, in
    `tests/unit/products/infrastructure/test_playbook_loader.py`.
    """
    assert _playbook(version="v3").version == "v3"


# ---------------------------------------------------------------------------
# Requirement: An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


def test_gate_sequence_that_omits_a_gate_is_rejected() -> None:
    """Scenario: Gate sequence deviates from the specification (omission).

    WHEN a playbook's gate sequence omits a gate
    THEN loading fails with an error naming the deviation.
    """
    without_ignition = tuple(
        gate for gate in specified_gates() if gate.identifier != "ignition"
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=without_ignition)

    # SPECIFIED: the error names the deviation.
    assert "ignition" in str(caught.value)


def test_gate_sequence_with_an_extra_gate_is_rejected() -> None:
    """Scenario: Gate sequence deviates from the specification (addition).

    WHEN a playbook's gate sequence adds a gate
    THEN loading fails with an error naming the deviation.
    """
    with_extra = (
        *specified_gates(),
        Gate(identifier="warehoused", position=9, opening=GateOpening.AUTOMATIC),
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=with_extra)

    # SPECIFIED: the error names the deviation.
    assert "warehoused" in str(caught.value)


def test_gate_sequence_in_the_wrong_order_is_rejected() -> None:
    """Scenario: Gate sequence deviates from the specification (reordering).

    WHEN a playbook's gate sequence orders the gates differently from the
    defined sequence
    THEN loading fails with an error naming the deviation.

    `live` and `ignition` are swapped because `design.md` records their
    separation as one of the two deliberate corrections this change makes
    to the reference material — a sequence that reverses them is exactly
    the mistake this rule exists to catch.
    """
    gates = list(specified_gates())
    live_index = SPECIFIED_GATE_ORDER.index("live")
    ignition_index = SPECIFIED_GATE_ORDER.index("ignition")
    gates[live_index], gates[ignition_index] = (
        Gate(
            identifier="ignition",
            position=live_index + 1,
            opening=GateOpening.AUTOMATIC,
        ),
        Gate(
            identifier="live",
            position=ignition_index + 1,
            opening=GateOpening.AUTOMATIC,
        ),
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=tuple(gates))

    # SPECIFIED: the error names the deviation. Either misplaced gate is an
    # acceptable naming of it.
    message = str(caught.value)
    assert "live" in message or "ignition" in message


def test_gate_sequence_repeating_a_position_is_rejected() -> None:
    """Scenario: Gate sequence deviates from the specification (repeat).

    WHEN a playbook's gate sequence repeats a position
    THEN loading fails with an error naming the deviation.
    """
    gates = list(specified_gates())
    # `stock-ready` is given `listable`'s position, so two gates claim the
    # same point in the sequence.
    listable_index = SPECIFIED_GATE_ORDER.index("listable")
    stock_ready_index = SPECIFIED_GATE_ORDER.index("stock-ready")
    gates[stock_ready_index] = Gate(
        identifier="stock-ready",
        position=gates[listable_index].position,
        opening=GateOpening.AUTOMATIC,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=tuple(gates))

    # SPECIFIED: the error names the deviation.
    message = str(caught.value)
    assert "stock-ready" in message or "listable" in message


def test_gate_opening_mode_disagreeing_with_the_specification_is_rejected() -> None:
    """Scenario: A gate's opening mode disagrees with the specification.

    WHEN a playbook declares an opening mode for a gate that differs from
    the mode this specification assigns to it
    THEN loading fails with an error naming that gate.

    Added on a follow-up pass — see the module docstring. `commit` is used
    because the spec's own worked example puts it on the wrong side
    deliberately: *A gate declares how it opens* fixes `commit` as
    requiring confirmation, and it is authored here as opening
    automatically instead.
    """
    gates = list(specified_gates())
    commit_index = SPECIFIED_GATE_ORDER.index("commit")
    gates[commit_index] = Gate(
        identifier="commit",
        position=gates[commit_index].position,
        opening=GateOpening.AUTOMATIC,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=tuple(gates))

    # SPECIFIED: the error names that gate.
    assert "commit" in str(caught.value)


def test_duplicate_step_identifier_is_rejected() -> None:
    """Scenario: Duplicate step identifier.

    WHEN a playbook defines two steps with the same identifier
    THEN loading fails with an error naming that identifier.
    """
    first = _step(identifier="listing.title-conforms", gate="listable")
    second = _step(identifier="listing.title-conforms", gate="live")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(first, second))

    # SPECIFIED: the error names that identifier.
    assert "listing.title-conforms" in str(caught.value)


def test_step_referencing_an_unknown_gate_is_rejected() -> None:
    """Scenario: Step references an unknown gate.

    WHEN a step definition declares a gate that is not part of the gate
    sequence
    THEN loading fails with an error naming the step and the unknown gate.
    """
    step = _step(identifier="ppc.campaigns-armed", gate="pre-launch")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names both the step and the unknown gate.
    message = str(caught.value)
    assert "ppc.campaigns-armed" in message
    assert "pre-launch" in message


def test_automated_step_without_a_rule_policy_is_rejected() -> None:
    """Scenario: Automation without a decided rule (automated).

    WHEN a step definition declares an automated execution mode and has no
    rule policy
    THEN loading fails with an error naming that step.
    """
    step = _step(
        identifier="price.buy-box-check",
        execution=ExecutionMode.AUTOMATED,
        rule_policy=None,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "price.buy-box-check" in str(caught.value)


def test_ai_assisted_step_without_a_rule_policy_is_rejected() -> None:
    """Scenario: Automation without a decided rule (AI-assisted).

    WHEN a step definition declares an AI-assisted execution mode and has
    no rule policy
    THEN loading fails with an error naming that step.

    Covered separately from the automated case because the spec names both
    modes, and an implementation that checked only one would pass a test
    covering only the other.
    """
    step = _step(
        identifier="creative.image-brief",
        execution=ExecutionMode.AI_ASSISTED,
        rule_policy=None,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "creative.image-brief" in str(caught.value)


def test_automated_step_with_a_rule_policy_is_accepted() -> None:
    """Scenario: Automation without a decided rule (the permitted side).

    The rule rejects an automated step *whose rule policy is absent*. This
    checks the rule is conditioned on the absent policy rather than on the
    execution mode alone — without it, an implementation that rejected
    every automated step would pass the two tests above.
    """
    step = _step(
        identifier="price.buy-box-check",
        execution=ExecutionMode.AUTOMATED,
        rule_policy="Buy Box share is at or above 90% over a rolling week.",
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("listable")

    assert read_back.execution is ExecutionMode.AUTOMATED
    assert read_back.rule_policy is not None


def test_prohibited_tactic_marked_blocking_is_rejected() -> None:
    """Scenario: A prohibited tactic cannot block a gate.

    WHEN a step definition is classified `prohibited-tactic` and marked as
    blocking its gate
    THEN loading fails with an error naming that step.
    """
    step = _step(
        identifier="reviews.purchase-ring",
        hazard=Hazard.PROHIBITED_TACTIC,
        blocking=True,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "reviews.purchase-ring" in str(caught.value)


def test_prohibited_tactic_that_does_not_block_is_accepted() -> None:
    """Scenario: A prohibited tactic cannot block a gate (permitted side).

    The restriction is on *blocking*, not on the classification: the spec
    records prohibited tactics precisely so they are recognised and
    refused, so a non-blocking one must load.
    """
    step = _step(
        identifier="reviews.purchase-ring",
        hazard=Hazard.PROHIBITED_TACTIC,
        blocking=False,
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("listable")

    assert read_back.hazard is Hazard.PROHIBITED_TACTIC
    assert read_back.blocking is False


def test_two_distinct_violations_are_reported_together() -> None:
    """Scenario: Multiple violations are reported together.

    WHEN a playbook contains two distinct coherence violations
    THEN loading fails once, and the failure names both.
    """
    unknown_gate_step = _step(identifier="ppc.campaigns-armed", gate="pre-launch")
    prohibited_blocking_step = _step(
        identifier="reviews.purchase-ring",
        hazard=Hazard.PROHIBITED_TACTIC,
        blocking=True,
    )

    # SPECIFIED: it fails *once* — a single raised error, not one per
    # fault. `pytest.raises` catching a single exception is what
    # establishes that; the assertions below establish that the one error
    # carries both faults.
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(unknown_gate_step, prohibited_blocking_step))

    message = str(caught.value)
    # SPECIFIED: the failure names both.
    assert "ppc.campaigns-armed" in message
    assert "reviews.purchase-ring" in message


def test_a_coherent_playbook_loads() -> None:
    """Scenario: A coherent playbook loads.

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.
    """
    steps = (
        _step(identifier="sourcing.unit-economics", gate="commit", scope=Scope.PRODUCT),
        _step(identifier="listing.a-plus-content", gate="listable", scope=Scope.MARKET),
    )

    playbook = _playbook(version="v1", steps=steps)

    # SPECIFIED: it exposes its gates and its step definitions.
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)
    assert {step.identifier for step in playbook.steps} == {
        "sourcing.unit-economics",
        "listing.a-plus-content",
    }


# ---------------------------------------------------------------------------
# Requirement: An undecided rule does not prevent loading
# ---------------------------------------------------------------------------


def test_human_attested_step_with_no_rule_policy_loads() -> None:
    """Scenario: Human-attested step with no rule policy.

    WHEN a step definition declares human attestation as its execution mode
    and has no rule policy
    THEN the playbook loads successfully and the step reports its rule
    policy as absent.

    This is the case the whole reference import depends on: all 358 rows
    arrive with an empty rule column.
    """
    step = _step(
        identifier="strategy.phase-one-criteria",
        execution=ExecutionMode.HUMAN_ATTESTED,
        rule_policy=None,
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("listable")

    # SPECIFIED: loads successfully, and reports its rule policy as absent.
    assert read_back.execution is ExecutionMode.HUMAN_ATTESTED
    assert read_back.rule_policy is None


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - That the domain objects are immutable (`tasks.md` 3.1-3.3). Immutability
#   is a task-level implementation decision, not a scenario in the delta
#   spec, and the mechanism (frozen dataclass, `__slots__`, a read-only
#   property) is the implementer's to choose.
# - That no domain module imports `yaml`, FastAPI or any I/O (`tasks.md`
#   3.7). It is an architectural check over the whole layer, not a
#   behaviour of the playbook, and it belongs to a lint/import-linter rule
#   rather than to a unit test derived from these scenarios.
# - A dedicated single-step lookup on the playbook. "Addressable by its own
#   identifier" is asserted above through the `steps` collection so that no
#   lookup API is invented here; if the implementation adds one, that is a
#   free choice, not a constraint from this spec.
# - The member sets of `Scope`, `Binding`, `ExecutionMode` and `Cadence`
#   beyond the members these tests use. Only `Hazard`'s set (three) and, as
#   of the follow-up pass, `Track`'s set (twelve) are closed by the spec,
#   and only those are asserted.
