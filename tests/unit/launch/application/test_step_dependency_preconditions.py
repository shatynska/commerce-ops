"""Authoring the two start declarations (`playbook-authoring`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/playbook-authoring/spec.md`:

- ADDED *A dependency may only be authored on an active step* — all six
  scenarios.
- ADDED *A `prohibited-tactic` step may not be depended upon* — both
  scenarios.
- MODIFIED *A step can be created* — only its two new scenarios, *A step
  is created declaring when it starts* and *A step is created declaring
  neither*. The other two are reproduced unchanged and are covered by
  `test_playbook_authoring.py` and `test_playbook_authoring_new_field_set.py`.
- MODIFIED *Every write is validated as the playbook it would produce* —
  only its one new scenario, *A dependency precondition is evaluated with
  no members supplied*. The other eleven are reproduced unchanged.
- `launch-playbook`'s ADDED *The stored step set declares when its steps
  start* — only its scenario *An author may set a step back to starting
  immediately*, which is a statement about the authoring surface.

The manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
accounts for every scenario in the change.

## Level

The real `create_step` / `update_step` / status-change use cases over a
step-store double and a membership double — the same level and the same
doubles `test_step_assignee_preconditions.py` uses, which is the
smallest unit that can observe a write being refused and nothing being
persisted.

## INVENTED, with correction points

Inherited from `test_step_assignee_preconditions.py`, whose docstring
records them in full: the `members=` and `handlers=` collaborators, the
members row shape, `REJECTED` as the tuple of acceptable refusal types
(the delta fixes the outcome, not the exception type), and `_load` as
the composition the serving adapter performs.

Added by this file:

- `starts_at_gate=` and `after_steps=` as keyword fields of both use
  cases, per `tasks.md` 1.4 ("carry both fields through ...
  `playbook_authoring`'s `StepRecord`, `_as_record`, `_copy_record` and
  `_write_fields`"). Correction points: `_CREATE_DEFAULTS`, `_create`,
  `_update`.
- The release predicate probe, for the one scenario stated about
  release. Correction point: `_released`; the predicate's own call shape
  is owned by `tests/unit/launch/domain/test_step_start_release.py`.

## Expected first-run state

Neither field exists on `StepDefinition` and neither use case accepts
it, so every test here is expected to fail on an **absent target** — a
`TypeError` from the constructor or the use case. Per
`ai-toolkit:testing` that establishes absence and nothing about these
assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import create_step, update_step
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeHandlerRegistry as _FakeHandlerRegistry
from tests.support.fakes import FakeMembers, FakeStepStore
from tests.support.fixtures import ALICE, ALICE_NAME, PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import step as _build_step
from tests.support.values import Member as _Member
from tests.support.values import Record as _Record

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))

LAUNCH_DATE: Final = date(2027, 4, 15)

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Doubles, as `test_step_assignee_preconditions.py` records them
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"assignees": (ALICE,), **overrides})


def _holding_step(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
    )


_FakeStepStore = FakeStepStore[Any]


class _FakeMembers(FakeMembers):
    def __init__(self) -> None:
        super().__init__((_Member(ALICE, ALICE_NAME),))


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(_Record(_holding_step(gate)) for gate in SPECIFIED_GATE_ORDER)
    return _FakeStepStore(records + extra)


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


_CREATE_DEFAULTS: Final[dict[str, Any]] = {
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

#: A sentinel meaning "do not pass this keyword at all", distinguishing
#: an omitted membership from one supplied as `None`. The delta makes those
#: two different cases and forbids collapsing them.
_UNSUPPLIED: Final = object()


async def _create(
    store: _FakeStepStore, *, members: Any = _UNSUPPLIED, **overrides: Any
) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    if members is _UNSUPPLIED:
        members = _FakeMembers()
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=members,
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _create_without_a_members(store: _FakeStepStore, **overrides: Any) -> Any:
    """A create made with no members collaborator at all — the permitted
    case the delta names, in which the two assignee preconditions are not
    evaluated and every other rule still is."""
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _update(
    store: _FakeStepStore, step_id: str, *, members: Any = _UNSUPPLIED, **fields: Any
) -> Any:
    if members is _UNSUPPLIED:
        members = _FakeMembers()
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=members,
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _set_status(store: _FakeStepStore, step_id: str, status: StepStatus) -> Any:
    for name in ("change_step_status", "set_step_status"):
        use_case = getattr(launch_application, name, None)
        if use_case is not None:
            return await use_case(
                steps=store,
                principal=PRINCIPAL,
                step_id=step_id,
                status=status,
                members=_FakeMembers(),
                handlers=_FakeHandlerRegistry(),
            )
    return await _update(store, step_id, status=status)


def _load(store: _FakeStepStore) -> LaunchPlaybook:
    """What the serving adapter does on read: the stored definitions plus
    the code-owned gates, with no members in reach."""
    return LaunchPlaybook(
        version=f"set-v{store.version}",
        gates=tuple(
            Gate(
                identifier=identifier,
                position=position,
                opening=_opening_for(identifier),
            )
            for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
        ),
        steps=tuple(record.definition for record in store.records),
    )


def _released(launch: Launch, playbook: LaunchPlaybook, step: StepDefinition) -> bool:
    """The release predicate, probed rather than assumed.

    Its call shape is owned by
    `tests/unit/launch/domain/test_step_start_release.py`; this is the
    minimal probe the one release-shaped scenario here needs.
    """
    for name in (
        "has_released",
        "released",
        "is_released",
        "releases",
        "has_started",
        "step_released",
    ):
        candidate = getattr(launch, name, None)
        if callable(candidate):
            return bool(candidate(playbook, step))
    pytest.fail(
        "`Launch` exposes no release predicate — correct this probe to the "
        "implemented name"
    )


def _new_launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=ProductId(str(uuid.uuid4())),
        playbook=playbook,
        launch_date=LAUNCH_DATE,
    )
    return launch


# ---------------------------------------------------------------------------
# ADDED Requirement: A dependency may only be authored on an active step
# ---------------------------------------------------------------------------


async def test_naming_a_draft_step_is_refused() -> None:
    """Scenario: Naming a draft step is refused.

    WHEN a write names a `draft` step in another step's `after_steps`
    THEN the write is refused, with a fault naming the depending step and
    that identifier.
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="listing.photos-approved",
                    name="Photos are approved",
                    status=StepStatus.DRAFT,
                )
            ),
        )
    )

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Copy is written from the approved photos",
            after_steps=("listing.photos-approved",),
        )

    reported = str(caught.value)
    # SPECIFIED: the fault names the offending identifier.
    assert "listing.photos-approved" in reported
    # SPECIFIED: nothing of a rejected write is persisted.
    assert store.saves == []


async def test_naming_a_retired_step_is_refused() -> None:
    """Scenario: Naming a retired step is refused.

    WHEN a write names a `retired` step in another step's `after_steps`
    THEN the write is refused.
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="listing.photos-approved",
                    name="Photos are approved",
                    status=StepStatus.RETIRED,
                )
            ),
        )
    )

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Copy is written from the approved photos",
            after_steps=("listing.photos-approved",),
        )

    assert "listing.photos-approved" in str(caught.value)
    assert store.saves == []


async def test_naming_an_undefined_step_is_refused() -> None:
    """Scenario: Naming an undefined step is refused.

    WHEN a write names an identifier no step in the set carries
    THEN the write is refused, with a fault naming the depending step and
    that identifier.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Copy is written from something that is not there",
            after_steps=("listing.no-such-step",),
        )

    assert "listing.no-such-step" in str(caught.value)
    assert store.saves == []


async def test_every_offending_dependency_is_reported_at_once() -> None:
    """Scenario: Every offending dependency is reported at once.

    WHEN a write names three dependencies of which two are not `active`
    THEN the refusal names both offending identifiers, not only the
    first.

    SPECIFIED reason: "so that a write naming three dependencies of which
    two are wrong is corrected once rather than three times". The two
    offending steps are deliberately *not* adjacent in the tuple, so an
    implementation that stopped at the first still fails here.
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="listing.drafted",
                    name="Drafted work",
                    status=StepStatus.DRAFT,
                )
            ),
            _Record(_step(identifier="listing.served", name="Served work")),
            _Record(
                _step(
                    identifier="listing.retired",
                    name="Retired work",
                    status=StepStatus.RETIRED,
                )
            ),
        )
    )

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Work founded on all three",
            after_steps=("listing.drafted", "listing.served", "listing.retired"),
        )

    reported = str(caught.value)
    # SPECIFIED: both offending identifiers, not only the first.
    assert "listing.drafted" in reported
    assert "listing.retired" in reported
    assert store.saves == []


async def test_naming_only_active_steps_is_accepted() -> None:
    """The permitted side, without which an implementation refusing every
    `after_steps` value would pass every rejection above.

    DERIVED: stated by the requirement as the rule's complement rather
    than as a scenario of its own.
    """
    store = _store((_Record(_step(identifier="listing.served", name="Served work")),))

    await _create(
        store,
        name="Work founded on served work",
        after_steps=("listing.served",),
    )

    created = [
        record
        for record in store.records
        if record.definition.name == "Work founded on served work"
    ]
    assert len(created) == 1
    assert tuple(created[0].definition.after_steps) == ("listing.served",)


async def test_retiring_a_depended_on_step_is_not_refused() -> None:
    """Scenario: Retiring a depended-on step is not refused.

    WHEN a step is retired while other steps name it in their
    `after_steps`
    THEN the write is accepted, the dependents being released rather than
    stranded.

    `tasks.md` 5.3 makes this the test of the precondition's *scope*: it
    is evaluated over the steps a write touches, and retiring C touches
    C, not its dependents. An implementation that widened it into a
    set-wide check passes every rejection above and fails here.
    """
    store = _store(
        (
            _Record(
                _step(identifier="listing.photos-approved", name="Photos approved")
            ),
            _Record(
                _step(
                    identifier="listing.copy-written",
                    name="Copy written",
                    after_steps=("listing.photos-approved",),
                )
            ),
        )
    )

    await _set_status(store, "listing.photos-approved", StepStatus.RETIRED)

    # SPECIFIED: the write is accepted.
    assert (
        _record_named(store, "listing.photos-approved").definition.status
        is StepStatus.RETIRED
    )
    # SPECIFIED: the dependent is left naming it, not rewritten.
    assert tuple(
        _record_named(store, "listing.copy-written").definition.after_steps
    ) == ("listing.photos-approved",)


async def test_a_stored_dependency_on_a_since_retired_step_still_loads() -> None:
    """Scenario: A stored dependency on a since-retired step still loads.

    WHEN a playbook is loaded whose step names a dependency that has
    since been retired
    THEN the playbook loads and is served.

    SPECIFIED reason: a load rule "would mean that retiring a step
    renders every stored playbook carrying a reference to it unloadable —
    taking down every launch as the consequence of one authoring action,
    which is the mistake `serve-only-a-ready-playbook` was written to
    undo".
    """
    store = _store(
        (
            _Record(
                _step(identifier="listing.photos-approved", name="Photos approved")
            ),
            _Record(
                _step(
                    identifier="listing.copy-written",
                    name="Copy written",
                    after_steps=("listing.photos-approved",),
                )
            ),
        )
    )

    await _set_status(store, "listing.photos-approved", StepStatus.RETIRED)

    playbook = _load(store)

    # SPECIFIED: it loads, and is served.
    assert "listing.copy-written" in {step.identifier for step in playbook.served_steps}


# ---------------------------------------------------------------------------
# ADDED Requirement: A `prohibited-tactic` step may not be depended upon
# ---------------------------------------------------------------------------


async def test_depending_on_a_prohibited_tactic_step_is_refused() -> None:
    """Scenario: Depending on a prohibited-tactic step is refused.

    WHEN a write names a step whose hazard is `prohibited-tactic` in
    another step's `after_steps`
    THEN the write is refused, naming the depending step and that
    identifier.

    SPECIFIED reason: "sequencing other work behind a refusal is not a
    dependency anyone should be able to author". The rule is policy, not
    a claim about what can be recorded — so the step below is `active`,
    which is the case that would otherwise pass the other rule.
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="reviews.purchase-ring",
                    name="Solicit reviews through a purchase ring",
                    hazard=Hazard.PROHIBITED_TACTIC,
                )
            ),
        )
    )

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="Work sequenced behind a refusal",
            after_steps=("reviews.purchase-ring",),
        )

    assert "reviews.purchase-ring" in str(caught.value)
    assert store.saves == []


async def test_a_step_re_authored_prohibited_tactic_releases_its_dependents() -> None:
    """Scenario: A step re-authored prohibited-tactic releases its
    dependents.

    WHEN a step named by another's `after_steps` is re-authored to the
    `prohibited-tactic` hazard
    THEN stored playbooks naming it still load, and the depending step is
    released, on the same footing as a dependency that is no longer
    `active`.
    """
    store = _store(
        (
            _Record(
                _step(identifier="reviews.purchase-ring", name="A tactic under review")
            ),
            _Record(
                _step(
                    identifier="listing.copy-written",
                    name="Copy written",
                    after_steps=("reviews.purchase-ring",),
                )
            ),
        )
    )

    await _update(store, "reviews.purchase-ring", hazard=Hazard.PROHIBITED_TACTIC)

    playbook = _load(store)
    # SPECIFIED: stored playbooks naming it still load.
    depending = next(
        step
        for step in playbook.authored_steps
        if step.identifier == "listing.copy-written"
    )

    # SPECIFIED: and the depending step is released.
    assert _released(_new_launch(playbook), playbook, depending)


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A step can be created (the two new scenarios)
# ---------------------------------------------------------------------------


async def test_a_step_is_created_declaring_when_it_starts() -> None:
    """Scenario: A step is created declaring when it starts.

    WHEN a step is created declaring a start gate and one or more steps
    it waits on
    THEN both are persisted and read back on the created step.
    """
    store = _store((_Record(_step(identifier="listing.served", name="Served work")),))

    await _create(
        store,
        name="Work that starts at listable and waits on one step",
        gate="live",
        starts_at_gate="listable",
        after_steps=("listing.served",),
    )

    created = [
        record
        for record in store.records
        if record.definition.name
        == "Work that starts at listable and waits on one step"
    ]
    assert len(created) == 1
    definition = created[0].definition
    # SPECIFIED: both persisted and read back.
    assert definition.starts_at_gate == "listable"
    assert tuple(definition.after_steps) == ("listing.served",)


async def test_a_step_is_created_declaring_neither() -> None:
    """Scenario: A step is created declaring neither.

    WHEN a step is created declaring no start gate and no steps it waits
    on
    THEN it is created, and is eligible from a launch's first gate.

    The eligibility half is asserted through the predicate against a
    launch standing at the first gate — "eligible from a launch's first
    gate" is a statement about release, and nothing weaker would
    distinguish it from a step merely stored with a null field.
    """
    store = _store()

    await _create(store, name="Work whose author said nothing about starting")

    created = [
        record
        for record in store.records
        if record.definition.name == "Work whose author said nothing about starting"
    ]
    assert len(created) == 1
    definition = created[0].definition
    assert definition.starts_at_gate is None
    assert tuple(definition.after_steps) == ()

    playbook = _load(store)
    launch = _new_launch(playbook)
    assert launch.current_gate == SPECIFIED_GATE_ORDER[0]
    # SPECIFIED: eligible from a launch's first gate.
    assert _released(launch, playbook, definition)


# ---------------------------------------------------------------------------
# MODIFIED Requirement: Every write is validated as the playbook it would
# produce (the one new scenario)
# ---------------------------------------------------------------------------


async def test_a_dependency_precondition_is_evaluated_with_no_members_supplied() -> (
    None
):
    """Scenario: A dependency precondition is evaluated with no members
    supplied.

    WHEN a write naming a `retired` step in another step's `after_steps`
    is validated with no members supplied
    THEN the write is refused, the dependency precondition having been
    evaluated.

    SPECIFIED reason: "A dependency rule skipped because no members was
    supplied would be a step-set rule going unevaluated for a reason
    having nothing to do with it." `tasks.md` 5.2 asks for exactly this.

    The step is created as `draft` with no assignee, so the two
    members-decided preconditions have nothing to say about it either way
    and cannot be what refuses the write.
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="listing.photos-approved",
                    name="Photos approved",
                    status=StepStatus.RETIRED,
                )
            ),
        )
    )

    with pytest.raises(REJECTED) as caught:
        await _create_without_a_members(
            store,
            name="Copy written from retired photos",
            status=StepStatus.DRAFT,
            assignees=(),
            after_steps=("listing.photos-approved",),
        )

    assert "listing.photos-approved" in str(caught.value)
    assert store.saves == []


# ---------------------------------------------------------------------------
# `launch-playbook`, ADDED Requirement: The stored step set declares when
# its steps start (the scenario stated about authoring)
# ---------------------------------------------------------------------------


async def test_an_author_may_set_a_step_back_to_starting_immediately() -> None:
    """Scenario: An author may set a backfilled step's start gate to
    "starts immediately".

    WHEN an author sets a backfilled step's start gate to "starts
    immediately"
    THEN the write is accepted, this obligation binding the backfill and
    the delivery path rather than every later write.

    SPECIFIED: the obligation "is not a standing invariant over the
    stored set" — a step carrying "starts immediately" afterwards "is a
    step whose author has said when it starts".
    """
    store = _store(
        (
            _Record(
                _step(
                    identifier="listing.backfilled",
                    name="A step the backfill gave its own gate",
                    starts_at_gate="listable",
                )
            ),
        )
    )

    await _update(store, "listing.backfilled", starts_at_gate=None)

    # SPECIFIED: the write is accepted, and the value stands.
    assert _record_named(store, "listing.backfilled").definition.starts_at_gate is None
