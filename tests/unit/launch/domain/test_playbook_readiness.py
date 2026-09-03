"""Readiness as a property of the served set, not a coherence rule.

Derived strictly from the delta specs of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-playbook/spec.md`

Covers, from the MODIFIED requirement *Every gate is held by at least one
blocking step*:

- *A set that leaves a gate unheld still loads*
- *A set whose steps are all drafts loads*
- *No gate opens for free*, as revised — the grouping is now stated over a
  playbook **served to a launch**, not over the set "at any point in its
  life".

From the MODIFIED requirement *An incoherent playbook is rejected against
each step's status*:

- *A gate with no active blocking step is rejected* — the load half only.
  The body of that scenario now says the rejection "happens when that
  playbook is asked for in order to hold a launch ... and **not** when it
  is loaded", so what is observable at this level is the second clause.
  The first clause is the serving read's, covered in
  `tests/integration/launch/test_playbook_readiness_live.py`.
- The remaining coherence rules, as a guard that removing one rule removed
  only that one.

And from the ADDED requirement *A playbook that cannot hold a launch is not
served*, every scenario decidable without a repository:

- *A refusal carries the set it declined to serve*
- *The carried set may be classified but not acted on*
- *Not ready is distinguishable from incoherent*

The remaining scenarios of that requirement turn on a **read** — which read
refuses and which does not — so the repository is the smallest unit that can
observe them and they live in the integration module named above.

## Level

`LaunchPlaybook` construction and the aggregate's own derived reads
(`tasks.md` 1.1–1.3), the placement every existing coherence rule already
has (`tests/unit/launch/domain/test_playbook_coherence_by_status.py`).
Readiness is "derived from the step set on every read and SHALL NOT be
stored", so a constructed aggregate is the smallest thing that can answer
it.

## What is fixed, and what is INVENTED

Fixed by the artifacts: `PlaybookNotReadyError` as a name, that it is
**not** a subclass of `InvalidPlaybookError`, and that it carries both the
unheld gate identifiers and the playbook (`tasks.md` 1.3).

INVENTED, each with a single correction point below:

- The name of the unheld-gate read on `LaunchPlaybook` (`tasks.md` 1.2
  fixes the obligation, not the spelling). `_unheld(...)` probes
  `_UNHELD_READS` and fails loudly rather than defaulting.
- The name of the readiness predicate. `_is_ready(...)` probes
  `_READINESS_READS`; where none exists it falls back to the emptiness of
  the unheld read, which is what the requirement defines readiness *as*
  ("ready exactly when every gate has at least one active blocking step").
- The attribute names on `PlaybookNotReadyError` carrying the gates and
  the playbook. `_carried_gates(...)` / `_carried_playbook(...)` probe.

What must survive any correction is what each test asserts: which sets
construct, which gates the read names, and what the refusal carries.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so the tests importing it fail on
an absent target (`ImportError`) — absence, and nothing more
(`ai-toolkit:testing`, failure state 2). The three construction tests are
expected to fail differently: construction currently *raises* where they
assert it succeeds, which is a wrong-value failure over a rule this change
removes (state 1), not an absent target.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step

# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    """One `active` blocking step holding `gate` — the floor's minimum."""
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "blocking": True,
        "status": StepStatus.ACTIVE,
    }
    attributes.update(overrides)
    return _step(**attributes)


def _holding_steps(
    *, except_gates: frozenset[str] = frozenset()
) -> tuple[StepDefinition, ...]:
    return tuple(
        _hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in except_gates
    )


def _playbook(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


def _ready_playbook() -> LaunchPlaybook:
    return _playbook(_holding_steps())


# ---------------------------------------------------------------------------
# The INVENTED reads: the single correction points
# ---------------------------------------------------------------------------

_UNHELD_READS: Final = (
    "unheld_gates",
    "gates_without_active_blocking_step",
    "unheld_gate_identifiers",
    "gates_holding_no_active_blocking_step",
)

_READINESS_READS: Final = ("is_ready", "ready", "is_servable", "servable")


def _resolve(
    playbook: LaunchPlaybook, names: tuple[str, ...]
) -> tuple[str, Any] | None:
    for name in names:
        if hasattr(playbook, name):
            return name, getattr(playbook, name)
    return None


def _unheld(playbook: LaunchPlaybook) -> tuple[str, ...]:
    """The gates holding no `active` blocking step, as the aggregate reads
    them (INVENTED name — see the module docstring)."""
    found = _resolve(playbook, _UNHELD_READS)
    if found is None:
        pytest.fail(
            "LaunchPlaybook exposes no unheld-gate read under any of "
            f"{_UNHELD_READS} — `tasks.md` 1.2 requires one; correct this "
            "file's probe to the implemented name"
        )
    _, value = found
    if callable(value):
        value = value()
    return tuple(str(item) for item in value)


def _is_ready(playbook: LaunchPlaybook) -> bool:
    """The readiness predicate, or the definition it stands for.

    The requirement defines readiness *as* every gate holding an active
    blocking step, so where no dedicated predicate is exposed the emptiness
    of the unheld read is not a weakening — it is the same statement.
    """
    found = _resolve(playbook, _READINESS_READS)
    if found is None:
        return _unheld(playbook) == ()
    _, value = found
    if callable(value):
        value = value()
    return bool(value)


_CARRIED_GATE_ATTRIBUTES: Final = ("gates", "unheld_gates", "unheld", "identifiers")
_CARRIED_PLAYBOOK_ATTRIBUTES: Final = ("playbook", "set", "authored", "step_set")


def _not_ready_error() -> type[Exception]:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    return error  # type: ignore[no-any-return]


def _carried_gates(error: Exception) -> tuple[str, ...]:
    for name in _CARRIED_GATE_ATTRIBUTES:
        carried = getattr(error, name, None)
        if carried is None or isinstance(carried, LaunchPlaybook):
            continue
        if isinstance(carried, str):
            continue
        return tuple(str(item) for item in carried)
    pytest.fail(
        "PlaybookNotReadyError carries the unheld gate identifiers under "
        f"none of {_CARRIED_GATE_ATTRIBUTES} — `tasks.md` 1.3 requires it "
        "to carry them"
    )


def _carried_playbook(error: Exception) -> LaunchPlaybook:
    for name in _CARRIED_PLAYBOOK_ATTRIBUTES:
        carried = getattr(error, name, None)
        if isinstance(carried, LaunchPlaybook):
            return carried
    pytest.fail(
        "PlaybookNotReadyError carries no `LaunchPlaybook` under any of "
        f"{_CARRIED_PLAYBOOK_ATTRIBUTES} — `tasks.md` 1.3 requires it to "
        "carry the playbook it was constructed from"
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Every gate is held by at least one blocking step
# ---------------------------------------------------------------------------


def test_a_set_that_leaves_a_gate_unheld_still_loads() -> None:
    """Scenario: A set that leaves a gate unheld still loads.

    WHEN a step set satisfying every coherence rule leaves one or more
    gates with no active blocking step
    THEN it loads, and its authored steps are readable.

    This is the inversion at the heart of the change: today construction
    raises here.
    """
    steps = _holding_steps(except_gates=frozenset({"ignition"}))

    playbook = _playbook(steps)

    # SPECIFIED: it loads, and its authored steps are readable.
    assert set(playbook.authored_steps) == set(steps)


def test_a_set_leaving_several_gates_unheld_still_loads() -> None:
    """Scenario: A set that leaves a gate unheld still loads — the plural
    half of its WHEN ("one or more gates").

    Separate from the single-gate case because an implementation that
    reported the first unheld gate eagerly rather than removing the rule
    would pass one and fail the other.
    """
    steps = _holding_steps(except_gates=frozenset({"ignition", "live", "order"}))

    playbook = _playbook(steps)

    assert set(playbook.authored_steps) == set(steps)


def test_a_set_whose_steps_are_all_drafts_loads() -> None:
    """Scenario: A set whose steps are all drafts loads.

    WHEN every step in the set carries a status other than `active`
    THEN the set loads and no gate-holding fault is reported.

    The proposal's motivating case: 358 drafts, no active step anywhere,
    every gate unheld at once.
    """
    steps = tuple(_hold(gate, status=StepStatus.DRAFT) for gate in SPECIFIED_GATE_ORDER)

    playbook = _playbook(steps)

    # SPECIFIED: the set loads...
    assert set(playbook.authored_steps) == set(steps)
    # ...and no gate-holding fault is reported. Nothing raised, and the
    # served set is empty because no step is active.
    assert tuple(playbook.served_steps) == ()


def test_a_set_of_non_active_statuses_other_than_draft_also_loads() -> None:
    """Scenario: A set whose steps are all drafts loads — its WHEN says
    "a status other than `active`", not "draft".

    Covered separately because `in-development` is the status the seeded
    automated steps land in, so an implementation excluding only `draft`
    from the removal would pass the test above and fail this.
    """
    steps = tuple(
        _hold(gate, status=StepStatus.IN_DEVELOPMENT) for gate in SPECIFIED_GATE_ORDER
    )

    playbook = _playbook(steps)

    assert set(playbook.authored_steps) == set(steps)


def test_no_gate_opens_for_free_in_a_playbook_served_to_a_launch() -> None:
    """Scenario: No gate opens for free.

    WHEN a playbook is served to a launch and its served steps are grouped
    by gate
    THEN every gate has at least one active step with a true blocking flag.

    Asserted over a **ready** playbook, which after this change is what
    "served to a launch" means: the serving read refuses any other. Drafts
    and retired steps in the same set contribute nothing, which is what
    makes the grouping a statement about the served set.
    """
    playbook = _playbook(
        (
            *_holding_steps(),
            _step(identifier="listing.draft-work", status=StepStatus.DRAFT),
            _step(
                identifier="ignition.retired-work",
                gate="ignition",
                status=StepStatus.RETIRED,
                blocking=True,
            ),
        )
    )

    unheld = [
        gate
        for gate in SPECIFIED_GATE_ORDER
        if not any(
            step.blocking and step.status is StepStatus.ACTIVE
            for step in playbook.steps_for_gate(gate)
        )
    ]

    # SPECIFIED: every gate has at least one active blocking step.
    assert unheld == []
    # SPECIFIED by the ADDED requirement: that is exactly what readiness is,
    # so the aggregate's own read must agree with the grouping above.
    assert _unheld(playbook) == ()
    assert _is_ready(playbook) is True


# ---------------------------------------------------------------------------
# Requirement (ADDED): A playbook that cannot hold a launch is not served
# ---------------------------------------------------------------------------


def test_the_unheld_read_names_exactly_the_gates_with_no_active_blocker() -> None:
    """Requirement statement: "A playbook SHALL be **ready** exactly when
    every gate has at least one active blocking step attached", and
    "non-empty names exactly what is missing" (`proposal.md`).

    Two gates are left unheld by different means — one with no step at all,
    one whose only blocking step is a draft — so the read is established as
    counting `active` blocking steps rather than attachment.
    """
    steps = (
        *_holding_steps(except_gates=frozenset({"ignition", "live"})),
        _hold("live", status=StepStatus.DRAFT),
        _step(identifier="ignition.advice", gate="ignition", blocking=False),
    )

    playbook = _playbook(steps)

    # SPECIFIED: exactly the gates holding no active blocking step, and no
    # others.
    assert set(_unheld(playbook)) == {"ignition", "live"}
    assert _is_ready(playbook) is False


def test_the_unheld_read_is_empty_for_a_ready_set() -> None:
    """Requirement statement: "Empty means the playbook is ready to serve"
    (`proposal.md`, restating the ADDED requirement's definition).

    The negative case of the test above: without it, a read that always
    answered the whole gate sequence would satisfy that one.
    """
    playbook = _ready_playbook()

    assert _unheld(playbook) == ()
    assert _is_ready(playbook) is True


def test_the_unheld_read_follows_the_set_without_being_stored() -> None:
    """Requirement statement: "Readiness SHALL be derived from the step set
    on every read and SHALL NOT be stored, so it can never disagree with
    the steps it summarises."

    Two aggregates built from the same version identifier and different
    step sets answer differently — which a stored flag, or one memoised
    across construction, could not do.
    """
    unready = _playbook(_holding_steps(except_gates=frozenset({"graduated"})))
    ready = _playbook(_holding_steps())

    assert _unheld(unready) == ("graduated",)
    assert _unheld(ready) == ()
    # Read twice: a derived read gives the same answer, and an answer
    # cached on first read must not leak between aggregates.
    assert _unheld(unready) == ("graduated",)


def test_the_unheld_read_is_in_gate_sequence_order() -> None:
    """DERIVED, from `tasks.md` 1.2 ("the gates with no `active` blocking
    step, **in gate-sequence order**").

    No `#### Scenario:` fixes an order — the spec says only that the
    refusal "names the gates". Recorded as its own test so a deliberate
    change of ordering fails here alone, visibly, rather than inside an
    assertion about which gates are named.
    """
    steps = _holding_steps(except_gates=frozenset({"graduated", "commit", "listable"}))

    playbook = _playbook(steps)

    assert _unheld(playbook) == ("commit", "listable", "graduated")


def test_not_ready_is_distinguishable_from_incoherent() -> None:
    """Scenario: Not ready is distinguishable from incoherent.

    WHEN a consumer is refused a playbook because a gate is unheld
    THEN the condition reported is distinct from the one reported for a
    playbook that violates a coherence rule.

    Asserted on the types themselves rather than through a read, because
    what the scenario is about is the distinguishing — "the first is an
    expected stage of a set being written, the second is a defect"
    (`tasks.md` 1.3: "**not** a subclass of `InvalidPlaybookError`").
    A consumer catching `InvalidPlaybookError` must not catch this.
    """
    not_ready = _not_ready_error()

    assert not_ready is not InvalidPlaybookError
    # SPECIFIED: distinguishable *by a consumer* — which subclassing would
    # defeat, since `except InvalidPlaybookError` would swallow both.
    assert not issubclass(not_ready, InvalidPlaybookError)
    assert not issubclass(InvalidPlaybookError, not_ready)


def test_a_refusal_carries_the_gates_and_the_set_it_declined_to_serve() -> None:
    """Scenario: A refusal carries the set it declined to serve.

    WHEN a consumer is refused a playbook because a gate is unheld
    THEN the refusal carries both the unheld gate identifiers and the
    playbook itself, so the consumer can tell a served step from one that
    is not without taking a second read.

    Constructed directly rather than through a read: what this scenario
    fixes is what the refusal *carries*, which is the error's own contract.
    Which read raises it is the serving read's, covered at the integration
    tier.
    """
    playbook = _playbook(
        (
            *_holding_steps(except_gates=frozenset({"ignition"})),
            _step(identifier="listing.title-conforms", status=StepStatus.DRAFT),
        )
    )
    not_ready = _not_ready_error()

    error = not_ready(playbook=playbook, gates=_unheld(playbook))  # type: ignore[call-arg]

    # SPECIFIED: the unheld gate identifiers...
    assert tuple(_carried_gates(error)) == ("ignition",)
    # ...and the playbook itself.
    assert _carried_playbook(error) is playbook
    # SPECIFIED by the refusal's purpose: "the refusal SHALL name the gates
    # holding no active blocking step" — a message a human reads.
    assert "ignition" in str(error)


def test_the_carried_set_may_be_classified_but_not_acted_on() -> None:
    """Scenario: The carried set may be classified but not acted on.

    WHEN a consumer holds the playbook carried by a refusal
    THEN it may ask which of that set's steps are served, and may not use
    it to advance, project or report on a launch.

    The first clause is what is testable here, and it is the load-bearing
    one: `launch-clickup-sync`'s intake owes opposite treatments to a
    served and a non-served step, and this is the read that tells them
    apart.

    DELIBERATELY UNTESTED: the second clause. "May not be used to advance,
    project or report on a launch" is an obligation on each consumer, not a
    capability the aggregate withholds — the spec is explicit that the set
    is coherent and there is nothing unsafe about handing it back. It is
    established per consumer instead (`test_clickup_webhook_stand_down.py`
    asserts the webhook records nothing while holding it), and by review of
    the four call sites `design.md` enumerates.
    """
    served = _hold("listable", identifier="listing.title-conforms")
    drafted = _step(identifier="listing.copy-review", status=StepStatus.DRAFT)
    playbook = _playbook(
        (
            *_holding_steps(except_gates=frozenset({"listable", "ignition"})),
            served,
            drafted,
        )
    )
    not_ready = _not_ready_error()

    error = not_ready(playbook=playbook, gates=_unheld(playbook))  # type: ignore[call-arg]
    carried = _carried_playbook(error)

    # SPECIFIED: it may ask which of that set's steps are served.
    identifiers = {step.identifier for step in carried.served_steps}
    assert "listing.title-conforms" in identifiers
    assert "listing.copy-review" not in identifiers


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An incoherent playbook is rejected against each
# step's status — the rules that did NOT move
# ---------------------------------------------------------------------------


def test_a_gate_with_no_active_blocking_step_is_not_rejected_at_load() -> None:
    """Scenario: A gate with no active blocking step is rejected.

    WHEN a playbook's steps leave any gate with no active step whose
    blocking flag is true
    THEN the rejection happens when that playbook is asked for in order to
    hold a launch, naming the gate, **and not when it is loaded**.

    The "and not when it is loaded" clause is the half observable here.
    The "when asked for in order to hold a launch" half is the serving
    read's, and is covered in
    `tests/integration/launch/test_playbook_readiness_live.py`.
    """
    steps = _holding_steps(except_gates=frozenset({"stock-ready"}))

    # No `pytest.raises`: not raising is the assertion. Constructed
    # successfully, and the gate is named by the read instead.
    playbook = _playbook(steps)

    assert _unheld(playbook) == ("stock-ready",)


@pytest.mark.parametrize(
    ("label", "steps"),
    [
        pytest.param(
            "listing.title-conforms",
            (
                _step(identifier="listing.title-conforms", status=StepStatus.DRAFT),
                _step(
                    identifier="listing.title-conforms",
                    gate="live",
                    status=StepStatus.DRAFT,
                ),
            ),
            id="duplicate-identifier",
        ),
        pytest.param(
            "no-such-gate",
            (
                _step(
                    identifier="listing.title-conforms",
                    gate="no-such-gate",
                    status=StepStatus.DRAFT,
                ),
            ),
            id="unknown-gate",
        ),
        pytest.param(
            "listing.title-conforms",
            (
                _step(
                    identifier="listing.title-conforms",
                    name="   ",
                    status=StepStatus.DRAFT,
                ),
            ),
            id="empty-name",
        ),
        pytest.param(
            "listing.title-conforms",
            (
                _step(
                    identifier="listing.title-conforms",
                    name="Two\nlines",
                    status=StepStatus.DRAFT,
                ),
            ),
            id="multi-line-name",
        ),
        pytest.param(
            "price.buy-box-check",
            (
                _step(
                    identifier="price.buy-box-check",
                    kind=StepKind.HUMAN,
                    handler="price.buy_box_checker",
                    status=StepStatus.DRAFT,
                ),
            ),
            id="human-step-carrying-a-handler",
        ),
        pytest.param(
            "creative.competitor-copy",
            (
                _step(
                    identifier="creative.competitor-copy",
                    hazard=Hazard.PROHIBITED_TACTIC,
                    blocking=True,
                    status=StepStatus.DRAFT,
                ),
            ),
            id="prohibited-tactic-blocking",
        ),
    ],
)
def test_every_other_coherence_rule_still_rejects(
    label: str, steps: tuple[StepDefinition, ...]
) -> None:
    """Requirement statement: "`LaunchPlaybook` construction continues to
    enforce every other rule in the incoherence list ... and no longer
    rejects a set for leaving a gate unheld" (`proposal.md`, restating the
    requirement's own rule list).

    Each case is stated over a set that is **also not ready** — no gate
    holds an active blocking step in any of them. That is the point: an
    implementation that removed the fault list wholesale, rather than one
    rule from it, would construct every one of these silently.

    Covers, from this requirement's scenario list: *Duplicate step
    identifier*, *Step references an unknown gate*, *A step with no name is
    rejected by identifier*, *A name spanning several lines is rejected*,
    a `human` step carrying a handler, and *A prohibited tactic cannot
    block a gate*.
    """
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps)

    # SPECIFIED: the error names the offending step or gate.
    assert label in str(caught.value)


def test_two_faults_in_a_not_ready_set_are_still_reported_together() -> None:
    """Scenario: Multiple violations are reported together.

    WHEN a playbook contains two distinct coherence violations
    THEN loading fails once, and the failure names both.

    Re-established over a set that is **not ready**, which this change makes
    reachable: the aggregation must not have been the gate-holding fault's
    doing.
    """
    nameless = _step(
        identifier="creative.image-advice", name="   ", status=StepStatus.DRAFT
    )
    unknown_gate = _step(
        identifier="price.buy-box-check",
        gate="no-such-gate",
        status=StepStatus.DRAFT,
    )

    # A single raised error is what establishes "fails once".
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook((nameless, unknown_gate))

    message = str(caught.value)
    assert "creative.image-advice" in message
    assert "price.buy-box-check" in message


def test_a_coherent_but_unready_playbook_exposes_its_gates_and_steps() -> None:
    """Scenario: A coherent playbook loads — as this change revises what
    "coherent" means.

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    Stated over a set leaving every gate unheld, since after this change
    that set satisfies every coherence rule. The pre-change test of this
    scenario uses a fully held set, which no longer discriminates.
    """
    steps = tuple(_hold(gate, status=StepStatus.DRAFT) for gate in SPECIFIED_GATE_ORDER)

    playbook = _playbook(steps)

    assert tuple(gate.identifier for gate in playbook.gates) == SPECIFIED_GATE_ORDER
    assert set(playbook.authored_steps) == set(steps)
