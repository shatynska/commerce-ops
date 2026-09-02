"""The shape of the members collaborator an authoring write is given.

Derived strictly from the delta spec
`openspec/changes/restore-admin-step-writes/specs/playbook-authoring/spec.md`
(MODIFIED requirement *Every write is validated as the playbook it would
produce* — the **four appended scenarios**, which are the only part of
that requirement this change adds).

The six scenarios the delta carries forward verbatim are covered already
and are not restated here — `test_step_assignee_preconditions.py` owns
five of them and `test_step_retirement_and_slots.py` owns *Retiring a
gate's last blocking step is rejected*. `test-manifest.md` maps each one
to its existing test by name.

## The arrangement no existing test makes

`proposal.md` — *Why*: `main.py` injects a membership **store** (`load()` /
`save()` and nothing else) where the five write use cases expect a
reader, and `_read_members` accepts three shapes of which the store is
none. Every membership double under `tests/unit/launch/` exposes
`list_members()`, so the suite has never handed a store to a write. That
is exactly what `_StoreShapedCollaborator` below does, against all five
write use cases.

## Fixed by the delta, and what is INVENTED

Fixed: the three cases a members collaborator can arrive in, and that the
third is a **raised, named error** identifying what was supplied and what
was expected — never an entry in the write's fault list, and never
collapsible into case 2.

INVENTED, recorded in the manifest as unresolved project questions with
correction points named:

- The error's **type**. The delta fixes the outcome ("a named error"),
  not the class. These tests assert what the delta states — that it is
  raised, that it is not the fault-carrying `InvalidPlaybookError`, and
  that its message names both sides — rather than pinning a class the
  artifacts never chose. Correction point: `_refusal_of`.
- The spelling by which the message "identifies the shape expected".
  Read as naming the method the reader must answer, `list_members`, which
  `design.md` — *The members collaborator gets one shape* fixes as the
  protocol's single member. Correction point: `_EXPECTED_SHAPE_NAMES`.
- The `handlers=` collaborator and the membership row shape, both as
  `test_step_activation.py`'s docstring records them for the sibling
  files.

## Expected first-run state

`test_a_collaborator_of_the_wrong_shape_is_refused_by_name`,
`test_a_mis_wiring_is_not_reported_as_a_rejection_of_the_submission` and
`test_a_mis_shaped_collaborator_never_passes_for_an_absent_one` fail on
the behaviour that does not exist yet: today a store-shaped collaborator
raises `TypeError: '_StoreShapedCollaborator' object is not iterable`
from inside the write, which names what was supplied and nothing about
what was expected.

`test_no_members_is_still_a_permitted_case` is expected to **PASS** on its
first run. The no-members case already works; the delta states it so that
narrowing the collaborator's shape cannot remove it by accident
(`tasks.md` 2.6). It is recorded in the manifest as a regression guard,
not as coverage of new behaviour.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 985 passed, 0 failed, 0 skipped, the integration tier
included (2026-08-26, commit `a9414ba`, clean tree).
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    change_step_status,
    create_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

pytestmark = pytest.mark.anyio

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

PRINCIPAL: Final = "helen"
A_DISCIPLINE: Final = next(iter(Discipline))

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_NAME: Final = "Alice Admin"
#: An identifier no membership in this file carries.
NOBODY: Final = "prs_00000000NO"

EDITED: Final = "listing.zeta"
RETIRED_ALREADY: Final = "listing.omega"

#: How a message may spell "the shape expected" (INVENTED — see the
#: docstring). Correction point for the implemented wording.
_EXPECTED_SHAPE_NAMES: Final = ("list_members", "listpeople", "list members")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Step store, records and definitions (the shape the sibling files record)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": EDITED,
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _Record:
    def __init__(self, definition: StepDefinition, display_order: int = 10) -> None:
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
    def __init__(self, records: tuple[Any, ...], version: int = 41) -> None:
        self.records = tuple(records)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    """One `active` blocking step per gate — so no gate is left unheld by
    anything these tests do — plus the step they edit and one already
    retired, for the un-retire write."""
    holding = tuple(
        _Record(
            _step(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                blocking=True,
            )
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return _FakeStepStore(
        holding
        + (
            _Record(_step(identifier=EDITED, name="Work of listing.zeta"), 20),
            _Record(
                _step(
                    identifier=RETIRED_ALREADY,
                    name="Work of listing.omega",
                    status=StepStatus.RETIRED,
                    assignees=(),
                ),
                30,
            ),
        )
        + extra
    )


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


# ---------------------------------------------------------------------------
# Members collaborators: the reader, and the store production really injects
# ---------------------------------------------------------------------------


class _Member:
    def __init__(
        self, member_id: str, display_name: str, *, active: bool = True
    ) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeMembers:
    """A collaborator answering the stated shape — case 1."""

    def __init__(self, members: tuple[_Member, ...] | None = None) -> None:
        self.members_rows = (
            (_Member(ALICE, ALICE_NAME),) if members is None else members
        )

    async def list_members(self) -> tuple[_Member, ...]:
        return self.members_rows


class _StoreShapedCollaborator:
    """The shape `main.py` actually injects: `load()` / `save()` and
    nothing else.

    `PostgresMembers`'s shape, as `tests/unit/access/application/
    test_members_writes.py` records it for `access`'s own writes. It
    answers nothing about who the membership carries, so it is case 3 — and
    it is the arrangement no test in this repository made before this
    file (`proposal.md` — *What Changes*, last bullet).
    """

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.loads = 0

    async def load(self) -> tuple[tuple[Any, ...], int]:
        self.loads += 1
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        self.rows = tuple(rows)
        self.version += 1


class _FakeHandlerRegistry:
    def __init__(self, names: frozenset[str] = frozenset()) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self) -> Any:
        return iter(self._names)

    def names(self) -> frozenset[str]:
        return self._names


# ---------------------------------------------------------------------------
# The five writes, each addressable by name
# ---------------------------------------------------------------------------


_CREATE_DEFAULTS: Final = {
    "name": "Newly authored listable work",
    "description": None,
    "gate": "listable",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (ALICE,),
    "handler": None,
}


async def _create(store: _FakeStepStore, members: Any, **overrides: Any) -> Any:
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=members,
        handlers=_FakeHandlerRegistry(),
        **{**_CREATE_DEFAULTS, **overrides},
    )


async def _update(store: _FakeStepStore, members: Any, **fields: Any) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=EDITED,
        members=members,
        handlers=_FakeHandlerRegistry(),
        **({"name": "Work of listing.zeta, reworded"} | fields),
    )


async def _retire(store: _FakeStepStore, members: Any) -> Any:
    return await retire_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=EDITED,
        members=members,
        handlers=_FakeHandlerRegistry(),
    )


async def _unretire(store: _FakeStepStore, members: Any) -> Any:
    return await unretire_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=RETIRED_ALREADY,
        members=members,
        handlers=_FakeHandlerRegistry(),
    )


async def _change_status(store: _FakeStepStore, members: Any) -> Any:
    return await change_step_status(
        steps=store,
        principal=PRINCIPAL,
        step_id=EDITED,
        status=StepStatus.IN_DEVELOPMENT,
        members=members,
        handlers=_FakeHandlerRegistry(),
    )


#: Every write the delta's "the caller" can be. The proposal enumerates
#: exactly these five as the use cases taking a `members=` collaborator.
WRITES: Final = (
    ("create", _create),
    ("update", _update),
    ("retire", _retire),
    ("unretire", _unretire),
    ("change_status", _change_status),
)


def _refusal_of(caught: BaseException, supplied: object) -> str:
    """Assert the refusal is the delta's case 3 and answer its message.

    INVENTED where the delta is silent (the error's class); SPECIFIED in
    what it checks — raised, not a coherence fault, naming both what was
    supplied and what was expected.
    """
    assert not isinstance(caught, InvalidPlaybookError), (
        "the mis-wiring was refused as an `InvalidPlaybookError` — the type "
        "this capability uses to carry a rejected write's fault list. The "
        "delta reserves 'fault' for a judgement about the playbook the "
        "caller submitted and requires a mis-wired collaborator to be "
        "refused as something else entirely"
    )
    message = str(caught)
    assert type(supplied).__name__ in message, (
        "the refusal does not identify the collaborator that was supplied "
        f"({type(supplied).__name__!r}); it says: {message!r}"
    )
    lowered = message.lower()
    assert any(name in lowered for name in _EXPECTED_SHAPE_NAMES), (
        "the refusal does not identify the shape that was expected — it "
        f"names only what arrived: {message!r}. This is the message the "
        "production fault produced ('object is not iterable'), which is why "
        "a broken deployment read as an unexplained internal error"
    )
    return message


# ---------------------------------------------------------------------------
# MODIFIED requirement: Every write is validated as the playbook it would
# produce — the members collaborator's stated shape (case 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("write_name,write", WRITES, ids=[n for n, _ in WRITES])
async def test_a_collaborator_of_the_wrong_shape_is_refused_by_name(
    write_name: str, write: Any
) -> None:
    """Scenario: A collaborator of the wrong shape is refused by name.

    WHEN a write is given a members collaborator that cannot answer who
    the membership carries
    THEN the write is refused with a named error identifying the
    collaborator supplied and the shape expected
    AND the step set is unchanged.

    Parametrised over all five writes because the delta binds "a write",
    the proposal enumerates five, and the fault this change fixes is
    present in every one of them — a fix applied to `create` alone would
    pass a single-write test and leave four routes broken.

    The collaborator is the real injected shape (`load()` / `save()`),
    not an arbitrary wrong object: `proposal.md` — *Why* names it as what
    `main.py` supplies today.
    """
    store = _store()
    records_before = store.records
    supplied = _StoreShapedCollaborator()

    with pytest.raises(Exception) as caught:
        await write(store, supplied)

    # SPECIFIED: refused with a named error identifying both sides.
    _refusal_of(caught.value, supplied)
    # SPECIFIED: and the step set is unchanged.
    assert store.saves == [], (
        f"the {write_name} write persisted a step set while refusing the "
        "collaborator it was judged against"
    )
    assert store.records == records_before


async def test_a_mis_wiring_is_not_reported_as_a_rejection_of_the_submission() -> None:
    """Scenario: A mis-wiring is not reported as a rejection of the
    submission.

    WHEN a write is given a members collaborator that cannot answer who
    the membership carries
    THEN the refusal is raised rather than reported among the write's
    coherence faults, so a surface rendering those faults cannot present
    the mis-wiring as a fault of what was submitted.

    Read at this tier as: the refusal leaves the call by raising, and
    what it raises is not the type this capability's rejections carry.
    The surface half — that the admin page does not render it among its
    faults — is
    `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_members.py`
    (`tasks.md` 5.4).

    The contrast below is what makes the assertion mean anything: the
    *same* write, given a reader and a genuinely incoherent submission,
    is refused as an `InvalidPlaybookError` carrying faults. Two
    refusals, two different kinds, told apart by their type — which is
    all a surface has to go on.
    """
    store = _store()
    supplied = _StoreShapedCollaborator()

    with pytest.raises(Exception) as mis_wired:
        await _update(store, supplied)

    # SPECIFIED: raised, and not among the write's coherence faults.
    _refusal_of(mis_wired.value, supplied)

    # DERIVED contrast: a real rejection of the submission still arrives
    # as the fault-carrying type, so the distinction the surface draws is
    # a live one rather than an absence of rejections altogether.
    with pytest.raises(InvalidPlaybookError):
        await _update(_store(), _FakeMembers(), name="   ")


async def test_a_mis_shaped_collaborator_never_passes_for_an_absent_one() -> None:
    """Scenario: A mis-shaped collaborator never passes for an absent
    one.

    WHEN a write is given a members collaborator that cannot answer who
    the membership carries
    THEN the write is not treated as one made without a membership, and the
    two preconditions are not skipped.

    The discriminating pair: one write names a member no membership carries
    and is given the mis-shaped collaborator; the same write with no
    members at all is accepted. If case 3 could collapse into case 2 the
    first write would land too — which is the arrangement the delta says
    "shipped".
    """
    mis_wired_store = _store()
    supplied = _StoreShapedCollaborator()

    with pytest.raises(Exception) as caught:
        await _update(mis_wired_store, supplied, assignees=(NOBODY,))

    # SPECIFIED: not treated as a write made without a membership …
    _refusal_of(caught.value, supplied)
    assert mis_wired_store.saves == [], (
        "a write given an unreadable members collaborator persisted anyway, "
        "so the two membership preconditions were skipped exactly as though no "
        "members had been supplied"
    )

    # … and the comparison that gives that assertion its force: with no
    # members the identical write is a permitted case and lands.
    absent_store = _store()
    await _update(absent_store, None, assignees=(NOBODY,))
    assert len(absent_store.saves) == 1, (
        "the no-members write did not land, so the contrast above does not "
        "establish that the mis-shaped collaborator was refused rather than "
        "the write being refused for some unrelated reason"
    )


async def test_no_members_is_still_a_permitted_case() -> None:
    """Scenario: No members is still a permitted case.

    WHEN a write is made with no members collaborator at all
    THEN the write proceeds, evaluating every rule except the two the
    members decides.

    Three assertions, one per clause of the delta's case 2:

    1. the write proceeds;
    2. the two membership preconditions are not evaluated — a step naming
       somebody no members knows saves, which is only sound *because* the
       caller decided not to have them evaluated;
    3. the load-side rules are still evaluated in full — an incoherent
       submission is still rejected.

    Expected to **PASS** on its first run: the no-members case already
    works. `tasks.md` 2.6 asks for it because narrowing the collaborator
    to one shape is most likely to remove it by accident, so this is a
    regression guard rather than coverage of new behaviour.
    """
    store = _store()

    # SPECIFIED: the write proceeds.
    await _update(store, None, name="Work of listing.zeta, reworded")
    assert len(store.saves) == 1
    assert _record_named(store, EDITED).definition.name == (
        "Work of listing.zeta, reworded"
    )

    # SPECIFIED: except the two the membership decides — an `active` `human`
    # step naming somebody no members carries is not refused, because no
    # members was supplied to refuse it.
    await _update(store, None, assignees=(NOBODY,))
    assert tuple(_record_named(store, EDITED).definition.assignees) == (NOBODY,)

    # SPECIFIED: "The load-side rules are still evaluated in full."
    with pytest.raises(InvalidPlaybookError):
        await _update(_store(), None, name="   ")
