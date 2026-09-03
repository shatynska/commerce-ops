"""Within-gate ordering writes of the `playbook-authoring` capability.

Derived strictly from the delta specs of `add-playbook-admin-ui`:
`openspec/changes/add-playbook-admin-ui/specs/playbook-authoring/spec.md`
(both ADDED requirements, all seven scenarios) and the unit-observable
half of `.../specs/launch-playbook/spec.md`'s MODIFIED requirement *Gate
sequence orders the launch* (scenario *Steps at a gate are served in
their authored order* — the live-Postgres half lives in
`tests/integration/launch/test_playbook_ordering_live.py`).

The seam is the one `test_playbook_authoring.py` in this directory
established and the implementation adopted: use cases taking the step
store as `steps=` plus `principal=`, over a store whose `load()` answers
`(records, version)` and whose `save(records, *, expected_version)`
persists conditionally.

## What is fixed, and what is INVENTED

Fixed by the artifacts, not invented:

- A `reorder_step` use case beside the existing writes, exported from
  `commerce_ops.launch.application` (`tasks.md` 1.3, `design.md`
  Decision 3).
- Reordering renumbers the gate's live steps atomically, preserves the
  relative order of unmoved steps, leaves every other field and every
  other gate untouched, records the principal/date on the moved step "as
  an update's are", and is subject to the same whole-set validation and
  write serialization (the delta's first requirement).
- Created and un-retired steps, and a gate-changed step, take the last
  slot of their (new) gate; retirement closes the gap (the delta's
  second requirement).
- `StaleStepSetError` as the write-serialization rejection —
  `design.md`'s Context names it as already exported on the launch
  public surface.

INVENTED, each recorded in the manifest as an unresolved project
question, with the single correction point named:

- `reorder_step(steps=, principal=, step_id=, target_index=)` —
  following the implemented siblings' call shape rather than
  `design.md` Decision 3's illustrative positional signature (which
  also lists `expected_version` and `today`; the implemented writes
  carry neither). Correction point: `_reorder` below.
- `target_index` is **0-based** over the gate's live steps. No artifact
  fixes the base; every assertion is about the resulting order, so a
  1-based implementation is a one-line fixture correction in
  `_reorder`'s callers.
- Stored records carry the authored order as a `display_order` integer
  attribute (`design.md` Decision 1 fixes the column; the record
  attribute spelling is the guess). Correction point: `_gate_order` and
  `_OrderedRecord` below.

## Expected first-run state

`commerce_ops.launch.application` does not export `reorder_step` yet, so
every test in this file fails at import — the absent-target state; the
assertions have not been exercised. The append/gap tests exercise
*existing* use cases (`create_step`, `update_step`, `retire_step`,
`unretire_step`) against behavior this change ADDS (slot assignment),
so once the import error clears they discriminate: the pre-change
implementation assigns no slots.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    StaleStepSetError,
    create_step,
    reorder_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fixtures import PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures (following test_playbook_authoring.py)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _holding_step(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


# ---------------------------------------------------------------------------
# The step store double, extended with `display_order` (INVENTED spelling)
# ---------------------------------------------------------------------------


class _OrderedRecord:
    """A stored step row: definition, authoring attribution, and the
    authored within-gate slot (`display_order`, `design.md` Decision 1)."""

    def __init__(self, definition: StepDefinition, display_order: int) -> None:
        self.definition = definition
        self.display_order = display_order
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None


class _FakeStepStore:
    """In-memory step-set store with the optimistic set-version, as
    `test_playbook_authoring.py` invented it and the implementation
    adopted it."""

    def __init__(self, records: tuple[Any, ...], version: int = 41) -> None:
        self.records = records
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


class _StaleStepStore(_FakeStepStore):
    """A store whose set-version has been superseded between this
    writer's load and its save — the deterministic stand-in for the
    delta's "a later accepted write" (`design.md`: the step-set version
    serializes writes; the conditional save is where staleness
    surfaces)."""

    async def save(self, records: Any, *, expected_version: int) -> None:
        raise StaleStepSetError(
            "the step set changed underneath this write: expected version "
            f"{expected_version} was superseded"
        )


def _is_retired(record: Any) -> bool:
    """Read off the *status*, not the attribution.

    `redesign-step-fields` (design.md Decision 2) made the status the one
    answer to "is this step in play"; the attribution columns stay,
    recording who moved the step and when."""
    return record.definition.status is StepStatus.RETIRED


def _is_active(record: Any) -> bool:
    """Whether the step is served — and so whether it holds a slot."""
    return record.definition.status is StepStatus.ACTIVE


def _gate_order(store: _FakeStepStore, gate: str) -> list[str]:
    """The gate's live steps in served order.

    Serving order is `display_order` with the identifier as
    deterministic backstop (`design.md` Decision 1 / `tasks.md` 1.2).
    Single correction point for the ordering-attribute spelling.
    """
    live = [
        record
        for record in store.records
        if record.definition.gate == gate and _is_active(record)
    ]
    live.sort(key=lambda record: (record.display_order, record.definition.identifier))
    return [record.definition.identifier for record in live]


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _store_with_listable(
    *identifiers: str, store_class: type[_FakeStepStore] = _FakeStepStore
) -> _FakeStepStore:
    """One record per gate's holding step, plus non-blocking `listable`
    steps in the given authored order (after the gate's holding step).

    Slot values are deliberately non-contiguous (10, 20, 30, ...) so an
    implementation that renumbers may, and one that sorts by identifier
    instead of by slot fails wherever authored order and identifier
    order diverge below.
    """
    records: list[_OrderedRecord] = []
    for gate in SPECIFIED_GATE_ORDER:
        records.append(_OrderedRecord(_holding_step(gate), display_order=10))
    for slot, identifier in enumerate(identifiers, start=2):
        records.append(
            _OrderedRecord(
                _step(
                    identifier=identifier,
                    name=f"Work of {identifier}",
                    gate="listable",
                ),
                display_order=slot * 10,
            )
        )
    return store_class(tuple(records))


async def _reorder(store: _FakeStepStore, step_id: str, target_index: int) -> Any:
    """The single correction point for `reorder_step`'s call shape."""
    return await reorder_step(
        steps=store, principal=PRINCIPAL, step_id=step_id, target_index=target_index
    )


_CREATE_DEFAULTS: Final[dict[str, Any]] = {
    "name": "Newly authored listable work",
    "gate": "listable",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
}


# ---------------------------------------------------------------------------
# Requirement: A gate's steps can be reordered
# ---------------------------------------------------------------------------


async def test_a_moved_step_is_served_in_its_new_slot() -> None:
    """Scenario: A moved step is served in its new slot.

    WHEN a gate's third step is moved to the gate's first position
    THEN the next read serves that gate's steps with the moved step first
    AND the remaining steps keep their previous relative order
    AND the move's principal and date are recorded against the moved step.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")
    assert _gate_order(store, "listable") == [
        "hold.listable",
        "listing.alpha",
        "listing.beta",
    ]

    await _reorder(store, "listing.beta", 0)

    # SPECIFIED: moved step first, the rest in their previous relative
    # order. The result differs from identifier order, so an
    # identifier-sorted serve cannot pass by accident.
    assert _gate_order(store, "listable") == [
        "listing.beta",
        "hold.listable",
        "listing.alpha",
    ]
    # SPECIFIED: after the write every live step of the gate holds a
    # distinct slot.
    slots = [
        record.display_order
        for record in store.records
        if record.definition.gate == "listable" and _is_active(record)
    ]
    assert len(set(slots)) == len(slots)
    # SPECIFIED: the reorder's principal and date are recorded against
    # the moved step, as an update's are.
    moved = _record_named(store, "listing.beta")
    assert moved.updated_by == PRINCIPAL
    assert moved.updated_on is not None


async def test_a_stale_reorder_is_rejected_whole() -> None:
    """Scenario: A stale reorder is rejected whole.

    WHEN a reorder is submitted against a version of the step set that a
    later accepted write has superseded
    THEN the reorder is rejected and the served order is unchanged.

    The superseding write is simulated at the conditional save — the
    exact point `design.md` fixes for write serialization — because a
    real interleaving is not deterministically observable through this
    seam.
    """
    store = _store_with_listable(
        "listing.alpha", "listing.beta", store_class=_StaleStepStore
    )
    order_before = _gate_order(store, "listable")

    with pytest.raises(StaleStepSetError):
        await _reorder(store, "listing.beta", 0)

    # SPECIFIED: rejected without persisting anything.
    assert store.saves == []
    assert _gate_order(store, "listable") == order_before


async def test_a_reorder_never_leaves_the_steps_own_gate() -> None:
    """Scenario: A reorder never leaves the step's own gate.

    WHEN a step is moved to any accepted position
    THEN the step's gate and every other field are unchanged
    AND the order of every other gate's steps is unchanged.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")
    definition_before = _record_named(store, "listing.beta").definition
    other_gates = [gate for gate in SPECIFIED_GATE_ORDER if gate != "listable"]
    orders_before = {gate: _gate_order(store, gate) for gate in other_gates}

    await _reorder(store, "listing.beta", 0)

    # SPECIFIED: gate and every other field unchanged — only the slot
    # moved.
    definition_after = _record_named(store, "listing.beta").definition
    assert definition_after.gate == "listable"
    assert definition_after == definition_before
    # SPECIFIED: every other gate's order is untouched.
    for gate in other_gates:
        assert _gate_order(store, gate) == orders_before[gate]


# ---------------------------------------------------------------------------
# Requirement: Every live step holds a slot in its gate's order
# ---------------------------------------------------------------------------


async def test_a_created_step_appends_to_its_gate() -> None:
    """Scenario: A created step appends to its gate.

    WHEN a step is created for a gate that already has live steps
    THEN the next read serves it as that gate's last step.
    """
    store = _store_with_listable("listing.alpha")
    before = {record.definition.identifier for record in store.records}

    await create_step(steps=store, principal=PRINCIPAL, **_CREATE_DEFAULTS)

    created = [
        record.definition.identifier
        for record in store.records
        if record.definition.identifier not in before
    ]
    assert len(created) == 1
    # SPECIFIED: the last slot of its gate.
    assert _gate_order(store, "listable")[-1] == created[0]


async def test_an_unretired_step_rejoins_at_the_end() -> None:
    """Scenario: An un-retired step rejoins at the end.

    WHEN a step is retired and later un-retired and activated
    THEN the next read serves it as the last step of its gate, whatever
    slot it held before retirement.

    `listing.alpha` sits in the middle before retirement, so rejoining
    last is distinguishable from reclaiming a remembered position.

    Two acts, not one, since `redesign-step-fields`: un-retiring returns
    a step to `in-development` — a step retired months ago may no longer
    satisfy what activation requires — and activating it is the separate
    deliberate act it is for any other step.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")
    assert _gate_order(store, "listable").index("listing.alpha") == 1

    await retire_step(steps=store, principal=PRINCIPAL, step_id="listing.alpha")
    await unretire_step(steps=store, principal=PRINCIPAL, step_id="listing.alpha")
    await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id="listing.alpha",
        status=StepStatus.ACTIVE,
    )

    # SPECIFIED: last, not its remembered middle slot.
    assert _gate_order(store, "listable") == [
        "hold.listable",
        "listing.beta",
        "listing.alpha",
    ]


async def test_a_gate_change_appends_to_the_new_gate() -> None:
    """Scenario: A gate change appends to the new gate.

    WHEN an update moves a step to a different gate
    THEN the next read serves it as the last step of its new gate
    AND the steps of its old gate keep their relative order.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")

    await update_step(
        steps=store, principal=PRINCIPAL, step_id="listing.alpha", gate="live"
    )

    # SPECIFIED: last slot of the new gate.
    assert _gate_order(store, "live") == ["hold.live", "listing.alpha"]
    # SPECIFIED: the old gate's remaining steps keep their relative
    # order.
    assert _gate_order(store, "listable") == ["hold.listable", "listing.beta"]


async def test_retirement_closes_the_gap() -> None:
    """Scenario: Retirement closes the gap.

    WHEN a step is retired from the middle of its gate's order
    THEN the next read serves the gate's remaining steps in their
    previous relative order with no gap in the listing.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")

    await retire_step(steps=store, principal=PRINCIPAL, step_id="listing.alpha")

    # SPECIFIED: the survivors, in their previous relative order, listed
    # gaplessly — exactly the two of them, nothing between.
    assert _gate_order(store, "listable") == ["hold.listable", "listing.beta"]


# ---------------------------------------------------------------------------
# launch-playbook (MODIFIED): Steps at a gate are served in their
# authored order
#
# NOT tested here, deliberately: with no write involved, the only unit
# observation available is this file's own `_gate_order` helper sorting
# this file's own fake records — a tautology that constrains nothing.
# The scenario's serve-side substance (the adapter reading in slot
# order, stable across reads) is covered at the integration tier in
# `tests/integration/launch/test_playbook_ordering_live.py`; the
# write-side substance (which slot each write leaves each step in) is
# every test above. Recorded in the manifest.
# ---------------------------------------------------------------------------
