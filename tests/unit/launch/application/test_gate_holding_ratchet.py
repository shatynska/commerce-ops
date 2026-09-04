"""The gate-holding rule on the write path, as a one-directional ratchet.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/playbook-authoring/spec.md`

Covers, from the MODIFIED requirement *Every write is validated as the
playbook it would produce*:

- *Retiring a gate's last blocking step is rejected*, as revised — its WHEN
  now carries the qualifier "in a set where every gate is currently held".
- *A write against a set that is not ready may leave it unready* (new).

And from the MODIFIED requirement *Activation is a validated transition*:

- *Un-activating a gate's last blocking step is refused*, as revised — same
  qualifier.
- *Un-activating within a set that is not ready is permitted* (new).

The pair in each case is the requirement: "it is always permitted to move a
set toward being served, and never permitted to move a served set away from
it in a single write." A test of either half alone is satisfiable by an
implementation that kept the rule, or by one that dropped it.

## Scenarios of these requirements this file does not re-cover

The unchanged scenarios — *A rejected write reports all faults and persists
nothing*, *An untouched unowned step does not block an unrelated write*,
*Editing an unowned step requires giving it an owner*, *A membership change does
not break an accepted set*, *What a write cannot persist, a load cannot
see*, *An activation that satisfies its kind's rules lands*, *A refused
activation explains itself and persists nothing*, *Registering a handler
does not activate anything* — keep their existing tests in
`test_playbook_authoring.py`, `test_step_assignee_preconditions.py` and
`test_step_activation.py`, and are accounted for against those in
`test-manifest.md`.

## Level

The use cases over a step-store double, the level this capability already
uses (`tests/unit/launch/application/test_step_activation.py`): what an
accepted write hands the store, and what a rejected write does not. The
ratchet compares the loaded set with the candidate set (`design.md`, "Cost:
`playbook_authoring._accept` must judge the loaded set as well as the
candidate"), and both are in hand at that level.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the use-case names on
`commerce_ops.launch.application`; that the ratchet is evaluated in
`_accept` and gathered alongside the existing faults so a rejection still
reports everything at once (`tasks.md` 2.1); and the fault's wording, which
`tasks.md` 2.1 requires be kept because `playbook_admin._CROSSINGS` matches
the substring `has no active blocking step attached`.

INVENTED — the collaborator and call shapes, transcribed from
`test_step_activation.py` rather than re-derived, so a correction there is
the correction here. `_set_status`, `_create`, `_update` and `_retire`
below are the single correction points.

## Expected first-run state

The ratchet does not exist: the two "permitted in a not-ready set" tests are
expected to fail because the write is currently *refused* where they assert
it lands — a wrong-value failure over a rule this change introduces
(`ai-toolkit:testing` failure state 1), not an absent target. The two
"refused in a ready set" tests are expected to pass already; they are here
to pin the half of the rule that survives, not to discriminate, and are
recorded as such in `test-manifest.md`.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import (
    reorder_step,
    retire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    InvalidPlaybookError,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fakes import FakeHandlerRegistry as _FakeHandlerRegistry
from tests.support.fakes import FakeStepStore
from tests.support.fixtures import PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))
MEMBER_ACTIVE: Final = "prs_01HQ8Z6M4A"

# SPECIFIED by `tasks.md` 2.1: the fault's wording is kept, because
# `playbook_admin._CROSSINGS` (`playbook_admin.py:593`) matches this
# substring to attribute the fault to a page-level crossing rather than to
# a field.
FLOOR_FAULT_SUBSTRING: Final = "has no active blocking step attached"

# INVENTED refusal surface, transcribed from `test_step_activation.py`.
REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"assignees": (MEMBER_ACTIVE,), **overrides})


def _holding_step(gate: str, **overrides: Any) -> StepDefinition:
    """One `active`, owned, blocking step per gate: the minimal set both
    the gate-holding floor and the assignee precondition accept."""
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "blocking": True,
        "status": StepStatus.ACTIVE,
        "assignees": (MEMBER_ACTIVE,),
    }
    attributes.update(overrides)
    return _step(**attributes)


# ---------------------------------------------------------------------------
# Doubles — transcribed from `test_step_activation.py`
# ---------------------------------------------------------------------------


_FakeStepStore = FakeStepStore[Any]


class _FakeMembers:
    def __init__(self, members: tuple[_Member, ...]) -> None:
        self._members = members

    async def list_members(self) -> tuple[_Member, ...]:
        return self._members

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


def _members() -> _FakeMembers:
    return _FakeMembers((_Member(MEMBER_ACTIVE, "Alice Admin", active=True),))


def _registry() -> _FakeHandlerRegistry:
    return _FakeHandlerRegistry(frozenset({"price.buy_box_check"}))


# ---------------------------------------------------------------------------
# Store shapes: a ready set, and one that is not
# ---------------------------------------------------------------------------


def _ready_store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    """Every gate held by exactly one `active` blocking step."""
    records = tuple(_Record(_holding_step(gate)) for gate in SPECIFIED_GATE_ORDER)
    return _FakeStepStore(records + extra)


def _all_draft_store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    """The proposal's motivating state: a set whose every step is a draft,
    so all eight gates are unheld and none is reachable one at a time under
    the pre-change rule."""
    records = tuple(
        _Record(_holding_step(gate, status=StepStatus.DRAFT))
        for gate in SPECIFIED_GATE_ORDER
    )
    return _FakeStepStore(records + extra)


def _partly_held_store(unheld: str = "graduated") -> _FakeStepStore:
    """Ready but for one gate — the state a not-ready set is in for most of
    its climb, and the one *Un-activating within a set that is not ready is
    permitted* is stated over ("some other gate is already unheld")."""
    records = tuple(
        _Record(
            _holding_step(
                gate, status=StepStatus.DRAFT if gate == unheld else StepStatus.ACTIVE
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return _FakeStepStore(records)


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _status(store: _FakeStepStore, identifier: str) -> StepStatus:
    status: StepStatus = _record_named(store, identifier).definition.status
    return status


# ---------------------------------------------------------------------------
# Use-case call shapes: the single correction points
# ---------------------------------------------------------------------------

_STATUS_USE_CASES: Final = ("change_step_status", "set_step_status")


async def _set_status(store: _FakeStepStore, step_id: str, status: StepStatus) -> Any:
    """Move a step to `status` through whichever surface the implementation
    offers (INVENTED — transcribed from `test_step_activation.py`)."""
    for name in _STATUS_USE_CASES:
        use_case = getattr(launch_application, name, None)
        if use_case is not None:
            return await use_case(
                steps=store,
                principal=PRINCIPAL,
                step_id=step_id,
                status=status,
                members=_members(),
                handlers=_registry(),
            )
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        status=status,
        members=_members(),
        handlers=_registry(),
    )


async def _retire(store: _FakeStepStore, step_id: str) -> Any:
    return await retire_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=_members(),
        handlers=_registry(),
    )


async def _reorder(store: _FakeStepStore, step_id: str, target_index: int) -> Any:
    """`reorder_step`'s call shape, transcribed from
    `tests/unit/launch/application/test_playbook_reorder.py`."""
    return await reorder_step(
        steps=store, principal=PRINCIPAL, step_id=step_id, target_index=target_index
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Every write is validated as the playbook it would
# produce — the ratchet's refusing half
# ---------------------------------------------------------------------------


async def test_retiring_a_gates_last_blocking_step_is_rejected_in_a_ready_set() -> None:
    """Scenario: Retiring a gate's last blocking step is rejected.

    WHEN a retire targets the only active blocking step attached to a gate,
    **in a set where every gate is currently held**
    THEN the write is rejected, naming the gate that would be left unheld.

    The qualifier is what this change adds to the scenario, so the store is
    a ready set and nothing else. This is the protection the requirement
    says the ratchet exists to preserve: "the playbook a running launch is
    being held to cannot stop serving because of a single authoring
    action."
    """
    store = _ready_store()

    with pytest.raises(REJECTED) as caught:
        await _retire(store, "hold.live")

    message = str(caught.value)
    # SPECIFIED: naming the gate that would be left unheld.
    assert "live" in message
    # SPECIFIED by `tasks.md` 2.1: the fault keeps its existing wording, so
    # `playbook_admin`'s crossing match keeps recognising it at page level.
    assert FLOOR_FAULT_SUBSTRING in message
    # SPECIFIED: nothing of a rejected write is persisted.
    assert store.saves == []
    assert _status(store, "hold.live") is StepStatus.ACTIVE


async def test_un_activating_a_gates_last_blocking_step_is_refused_in_a_ready_set() -> (
    None
):
    """Scenario: Un-activating a gate's last blocking step is refused.

    WHEN a step is moved out of `active` while it is its gate's only active
    blocking step, **in a set where every gate is currently held**
    THEN the write is refused, exactly as retiring it would be.

    "Exactly as retiring it would be" is a comparison, so this uses the
    same store and the same gate as the retirement test above.
    """
    store = _ready_store()

    with pytest.raises(REJECTED) as caught:
        await _set_status(store, "hold.live", StepStatus.IN_DEVELOPMENT)

    assert "live" in str(caught.value)
    assert store.saves == []
    assert _status(store, "hold.live") is StepStatus.ACTIVE


# ---------------------------------------------------------------------------
# The ratchet's permitting half
# ---------------------------------------------------------------------------


async def test_the_first_activation_against_an_all_draft_set_lands() -> None:
    """Scenario: A write against a set that is not ready may leave it
    unready.

    WHEN a step is activated in a set where no step is yet active, leaving
    seven gates still unheld
    THEN the write lands, and the gates still unheld are not reported as
    faults.

    The state the change exists for. Under the pre-change rule this write
    is refused with seven faults, and the set can never be climbed out of.
    """
    store = _all_draft_store()

    await _set_status(store, "hold.commit", StepStatus.ACTIVE)

    # SPECIFIED: the write lands.
    assert store.saves, "the first activation against an all-draft set was not saved"
    assert _status(store, "hold.commit") is StepStatus.ACTIVE
    # SPECIFIED: the seven gates still unheld are unchanged, so nothing was
    # activated to satisfy the floor as a side effect.
    for gate in SPECIFIED_GATE_ORDER:
        if gate != "commit":
            assert _status(store, f"hold.{gate}") is StepStatus.DRAFT


async def test_no_fault_names_the_gates_an_accepted_unready_write_leaves_unheld() -> (
    None
):
    """Scenario: A write against a set that is not ready may leave it
    unready — its second THEN clause, "the gates still unheld are not
    reported as faults".

    Asserted as the absence of a raised fault at all: a write that landed
    reported nothing. Separated from the test above so that "it landed" and
    "it reported no gate-holding fault" fail distinguishably — an
    implementation that gathered the fault and then ignored it would still
    surface it through `playbook_admin`'s fault display.
    """
    store = _all_draft_store()

    # No `pytest.raises`: not raising is the assertion.
    await _set_status(store, "hold.order", StepStatus.ACTIVE)

    assert len(store.saves) == 1


async def test_climbing_from_all_draft_to_ready_one_activation_at_a_time() -> None:
    """Requirement statement: "A set being built toward readiness must be
    able to reach it, and rejecting every activation until all eight gates
    are held at once would make the first activation impossible and the set
    unreachable from its own starting state."

    DERIVED as a walk rather than as a scenario: no `#### Scenario:` states
    the whole climb, but the requirement's reason clause is a claim about
    reachability that only a walk establishes. `design.md` states the same
    three-line table.
    """
    store = _all_draft_store()

    for gate in SPECIFIED_GATE_ORDER:
        await _set_status(store, f"hold.{gate}", StepStatus.ACTIVE)

    assert len(store.saves) == len(SPECIFIED_GATE_ORDER)
    assert all(
        _status(store, f"hold.{gate}") is StepStatus.ACTIVE
        for gate in SPECIFIED_GATE_ORDER
    )

    # And the ratchet closes behind the climb: the set is now ready, so the
    # last write's inverse is refused.
    with pytest.raises(REJECTED):
        await _set_status(store, "hold.graduated", StepStatus.DRAFT)


async def test_un_activating_within_a_set_that_is_not_ready_is_permitted() -> None:
    """Scenario: Un-activating within a set that is not ready is permitted.

    WHEN a step is moved out of `active` while it is its gate's only active
    blocking step, in a set where **some other gate is already unheld**
    THEN the write lands, since the set was not being served in the first
    place.

    The store holds every gate but `graduated`, and the step moved out of
    `active` holds `live` — so the write both starts from a not-ready set
    and would leave a second gate unheld. An implementation keying the
    ratchet on the *candidate* set rather than the *prior* one refuses this.
    """
    store = _partly_held_store(unheld="graduated")

    await _set_status(store, "hold.live", StepStatus.IN_DEVELOPMENT)

    assert store.saves, "the un-activation was not saved"
    assert _status(store, "hold.live") is StepStatus.IN_DEVELOPMENT


async def test_retiring_a_gates_last_blocking_step_is_permitted_in_an_unready_set() -> (
    None
):
    """Requirement statement: "A write against a set that is **not** ready
    SHALL NOT be rejected for leaving gates unheld", applied to a retire —
    which the requirement's bullet covers by naming no write kind, and
    which `proposal.md` states in as many words ("Retiring or un-activating
    a gate's last blocking step stays refused in a ready set, and is
    permitted in one that is not").

    Covered alongside the un-activation because a retire reaches the write
    path by a different use case, and `tasks.md` 2.3 asks that every write
    path reach `_accept`.
    """
    store = _partly_held_store(unheld="graduated")

    await _retire(store, "hold.live")

    assert store.saves, "the retirement was not saved"
    assert _status(store, "hold.live") is StepStatus.RETIRED


# ---------------------------------------------------------------------------
# The exemption `tasks.md` 2.2 records
# ---------------------------------------------------------------------------


async def test_a_reorder_of_an_unowned_active_human_step_still_lands() -> None:
    """DERIVED regression guard, from `tasks.md` 2.2 and 5.5.

    No `#### Scenario:` covers this. `tasks.md` 2.2 records that
    `reorder_step` must stay on its direct `_validate` call, because
    routing it through `_accept` would newly subject the moved step to
    `_precondition_faults` and so refuse reorders of the migrated unowned
    `active` `human` steps — which `playbook-authoring`'s reorder
    requirement does not contemplate.

    Recorded as its own test so that a reorder newly refused for an
    assignee reason fails here, visibly, rather than inside an assertion
    about ordering.
    """
    unowned = _Record(
        _step(
            identifier="listing.migrated-unowned",
            gate="listable",
            status=StepStatus.ACTIVE,
            kind=StepKind.HUMAN,
            assignees=(),
        ),
        display_order=20,
    )
    store = _ready_store(extra=(unowned,))

    await _reorder(store, "listing.migrated-unowned", 1)

    assert store.saves, "a reorder of an unowned active human step was refused"
