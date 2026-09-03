"""Activation as a validated transition, and the handler registry.

Derived strictly from the delta specs:
`openspec/changes/redesign-step-fields/specs/playbook-authoring/spec.md`
(ADDED requirement *Activation is a validated transition* — all four
scenarios) and `.../specs/launch-playbook/spec.md` (the two scenarios of
*A step carries the brief and the handler its automation needs* that are
stated as writes: *Leaving draft requires the brief* and *A handler the
code does not register cannot be activated*), together with that
requirement's startup obligation:

> A deployment whose registry no longer answers for an `active` step's
> handler SHALL instead be reported at startup, where a deployment fault
> belongs.

**Level.** The use cases over a step-store double, the level
`test_playbook_authoring.py` already establishes for this capability:
what an accepted write hands the store, and what a rejected write does
not. The serving halves are integration-tier.

## The interface under test does not exist yet, and its shape is INVENTED

Fixed by the artifacts: the use-case names `create_step`, `update_step`,
`retire_step`, `unretire_step` on `commerce_ops.launch.application`
(unchanged by this change); that a status change "routes through the
same validation as any other write" (`tasks.md` 2.1); that a handler
registry is added and checked at activation only (`tasks.md` 2.3–2.4);
that a members reader is a use-case collaborator supplied by the
composition root (`tasks.md` 2.6).

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The two new collaborators are passed as `members=` and `handlers=`
  keyword arguments, mirroring `steps=`/`principal=`. Correction point:
  `_update`/`_create` below.
- `handlers=` is satisfied by a plain container of registered names.
  `tasks.md` 2.3 says to mirror `registrations.py` rather than invent a
  second idiom, so the real collaborator may be a registry object; the
  fake below is both — a set-like object answering `__contains__` and
  `names()`. Correction point: `_FakeHandlerRegistry`.
- The members reader answers members as rows carrying an identifier, a
  display name, a ClickUp user id and an active flag — the shape
  `move-principals-to-roster` records
  (`tests/unit/access/application/test_members_writes.py`). Correction
  point: `_FakeMembers`.
- The startup report's exported name. `_startup_report()` probes the
  public surface for it and fails loudly rather than defaulting.
- A status change is expressed as `update_step(status=...)`, since the
  spec says an update that changes status "SHALL be validated as the
  transition it is"; where the implementation instead exports a
  dedicated status use case, `_set_status()` finds it. Correction point:
  `_set_status`.

What must survive any correction is what each test asserts: which write
lands, which is refused, what the refusal names, and that a refused
write persists nothing.

## Expected first-run state

None of the new fields or collaborators exist, so every test here is
expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing` that establishes absence only — the assertions have
not been exercised.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed (the integration
tier skips: no database is configured here).
"""

from __future__ import annotations

from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import create_step, update_step
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
from tests.support.fixtures import PRINCIPAL
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))

REGISTERED_HANDLER: Final = "price.buy_box_check"
UNREGISTERED_HANDLER: Final = "price.a_handler_no_deploy_answers_for"

MEMBER_ACTIVE: Final = "prs_01HQ8Z6M4A"
MEMBER_DEACTIVATED: Final = "prs_01HQ8Z6M4B"

# INVENTED refusal surface: the delta fixes the outcome ("the write is
# refused naming the step and what it lacks"), not the exception type.
# `InvalidPlaybookError` is first because the spec says a write is
# validated "exactly as loading an incoherent playbook does".
REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"assignees": (MEMBER_ACTIVE,), **overrides})


def _holding_step(gate: str) -> StepDefinition:
    """One `active`, owned, blocking step per gate: the minimal set both
    the gate-holding floor and the assignee precondition accept."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        status=StepStatus.ACTIVE,
        assignees=(MEMBER_ACTIVE,),
    )


# ---------------------------------------------------------------------------
# Doubles (INVENTED shapes — see the module docstring)
# ---------------------------------------------------------------------------


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
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


class _Member:
    def __init__(self, member_id: str, display_name: str, *, active: bool) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeMembers:
    """Stands in for the members reader `launch` takes from `access`'s
    public application surface (`tasks.md` 2.6).

    Offers several plausible call shapes so a correction to the seam is a
    one-line change here rather than a rewrite: it is callable, and it
    answers `list_members()` and `members()` alike.
    """

    def __init__(self, members: tuple[_Member, ...]) -> None:
        self._members = members
        self.calls = 0

    async def list_members(self) -> tuple[_Member, ...]:
        self.calls += 1
        return self._members

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeHandlerRegistry:
    """The names the deployed code answers to (`tasks.md` 2.3)."""

    def __init__(self, names: frozenset[str]) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self) -> Any:
        return iter(self._names)

    def names(self) -> frozenset[str]:
        return self._names


def _members(*, deactivated: bool = False) -> _FakeMembers:
    return _FakeMembers(
        (
            _Member(MEMBER_ACTIVE, "Alice Admin", active=True),
            _Member(MEMBER_DEACTIVATED, "Bohdan Former", active=not deactivated),
        )
    )


def _registry(*names: str) -> _FakeHandlerRegistry:
    return _FakeHandlerRegistry(frozenset(names or (REGISTERED_HANDLER,)))


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(_Record(_holding_step(gate)) for gate in SPECIFIED_GATE_ORDER)
    return _FakeStepStore(records + extra)


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _status(store: _FakeStepStore, identifier: str) -> StepStatus:
    status: StepStatus = _record_named(store, identifier).definition.status
    return status


# ---------------------------------------------------------------------------
# Use-case call shapes: the single correction point
# ---------------------------------------------------------------------------

_CREATE_DEFAULTS: Final = {
    "name": "Refresh the hero image ahead of ignition",
    "description": None,
    "gate": "ignition",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.DRAFT,
    "hazard": Hazard.NONE,
    "assignees": (),
    "handler": None,
}


async def _create(
    store: _FakeStepStore,
    *,
    members: _FakeMembers | None = None,
    handlers: _FakeHandlerRegistry | None = None,
    **overrides: Any,
) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=members or _members(),
        handlers=handlers or _registry(),
        **fields,
    )


async def _update(
    store: _FakeStepStore,
    step_id: str,
    *,
    members: _FakeMembers | None = None,
    handlers: _FakeHandlerRegistry | None = None,
    **fields: Any,
) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=members or _members(),
        handlers=handlers or _registry(),
        **fields,
    )


_STATUS_USE_CASES: Final = ("change_step_status", "set_step_status", "activate_step")


async def _set_status(
    store: _FakeStepStore,
    step_id: str,
    status: StepStatus,
    *,
    members: _FakeMembers | None = None,
    handlers: _FakeHandlerRegistry | None = None,
) -> Any:
    """Move a step to `status`, through whichever surface the
    implementation offers (INVENTED — see the module docstring).

    `update_step(status=...)` is tried first because the spec states the
    rule that way: "An update that changes a step's status SHALL be
    validated as the transition it is".
    """
    for name in _STATUS_USE_CASES:
        use_case = getattr(launch_application, name, None)
        if use_case is not None and name != "activate_step":
            return await use_case(
                steps=store,
                principal=PRINCIPAL,
                step_id=step_id,
                status=status,
                members=members or _members(),
                handlers=handlers or _registry(),
            )
    return await _update(
        store, step_id, status=status, members=members, handlers=handlers
    )


_STARTUP_REPORTS: Final = (
    "report_unregistered_handlers",
    "report_missing_handlers",
    "report_handler_registration_faults",
    "check_handler_registrations",
)


def _startup_report() -> Any:
    """The startup report of `active` steps whose handler the deployed
    registry no longer answers for (INVENTED name — `tasks.md` 2.4 fixes
    the obligation, not the spelling)."""
    for name in _STARTUP_REPORTS:
        found = getattr(launch_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        "the launch application surface exports no startup report of "
        f"unregistered handlers under any of {_STARTUP_REPORTS} — correct "
        "this file's probe to the implemented name"
    )


# ---------------------------------------------------------------------------
# Requirement: Activation is a validated transition
# ---------------------------------------------------------------------------


async def test_an_activation_that_satisfies_its_kinds_rules_lands() -> None:
    """Scenario: An activation that satisfies its kind's rules lands.

    WHEN an `automated` step carrying a registered handler is activated
    THEN the write lands and the next read serves the step.

    The serving half is the adapter's and is integration-tier; here "the
    write lands" is the persisted status.
    """
    ready = _Record(
        _step(
            identifier="price.buy-box-check",
            gate="live",
            kind=StepKind.AUTOMATED,
            status=StepStatus.IN_DEVELOPMENT,
            handler=REGISTERED_HANDLER,
            assignees=(),
        )
    )
    store = _store(extra=(ready,))

    await _set_status(store, "price.buy-box-check", StepStatus.ACTIVE)

    # SPECIFIED: the write lands.
    assert _status(store, "price.buy-box-check") is StepStatus.ACTIVE
    assert len(store.saves) == 1


async def test_a_refused_activation_explains_itself_and_persists_nothing() -> None:
    """Scenario: A refused activation explains itself and persists
    nothing.

    WHEN a `human` step naming no active assignee is activated
    THEN the write is refused naming the step and what it lacks, and a
    subsequent read observes the set exactly as it was.
    """
    unowned = _Record(
        _step(
            identifier="listing.unowned",
            status=StepStatus.IN_DEVELOPMENT,
            assignees=(),
        )
    )
    store = _store(extra=(unowned,))
    records_before = store.records

    with pytest.raises(REJECTED) as caught:
        await _set_status(store, "listing.unowned", StepStatus.ACTIVE)

    # SPECIFIED: the refusal names the step...
    message = str(caught.value)
    assert "listing.unowned" in message
    # ...and what it lacks. DERIVED wording: the fault is recognisably
    # about an assignee. Correcting the substring to the implemented
    # wording is a fixture correction; dropping the assertion is not.
    assert "assign" in message.lower()

    # SPECIFIED: a subsequent read observes the set exactly as it was.
    assert store.saves == []
    assert store.records == records_before
    assert _status(store, "listing.unowned") is StepStatus.IN_DEVELOPMENT


async def test_registering_a_handler_does_not_activate_anything() -> None:
    """Scenario: Registering a handler does not activate anything.

    WHEN the code begins registering a handler an `in-development` step
    names
    THEN that step's status is unchanged until someone activates it.

    SPECIFIED reason: "whoever registers the handler is not necessarily
    whoever decides the step is ready, and a step that begins holding a
    gate because a deploy happened is a gate whose obligations moved
    without anyone choosing it".

    Read as: with the registry now answering for the handler, the startup
    pass — the one thing that *does* run on a deploy and *does* look at
    the registry — neither activates the step nor writes anything.
    """
    waiting = _Record(
        _step(
            identifier="price.buy-box-check",
            gate="live",
            kind=StepKind.AUTOMATED,
            status=StepStatus.IN_DEVELOPMENT,
            handler=REGISTERED_HANDLER,
            assignees=(),
        )
    )
    store = _store(extra=(waiting,))

    report = _startup_report()
    result = report(
        steps=tuple(record.definition for record in store.records),
        handlers=_registry(REGISTERED_HANDLER),
    )
    if hasattr(result, "__await__"):
        result = await result

    # SPECIFIED: the status is unchanged until someone activates it.
    assert _status(store, "price.buy-box-check") is StepStatus.IN_DEVELOPMENT
    assert store.saves == []


async def test_un_activating_a_gates_last_blocking_step_is_refused() -> None:
    """Scenario: Un-activating a gate's last blocking step is refused.

    WHEN a step is moved out of `active` while it is its gate's only
    active blocking step
    THEN the write is refused, exactly as retiring it would be.

    The store holds exactly one blocking step per gate, so `hold.live` is
    `live`'s only one — the same fixture the existing retirement test
    uses, which is what makes "exactly as retiring it would be" a
    comparison rather than a phrase.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _set_status(store, "hold.live", StepStatus.IN_DEVELOPMENT)

    # SPECIFIED: refused, and the gate-holding floor is what refuses it.
    assert "live" in str(caught.value)
    assert store.saves == []
    assert _status(store, "hold.live") is StepStatus.ACTIVE


# ---------------------------------------------------------------------------
# launch-playbook's write-shaped scenarios
# ---------------------------------------------------------------------------


async def test_a_handler_the_code_does_not_register_cannot_be_activated() -> None:
    """Scenario (launch-playbook): A handler the code does not register
    cannot be activated.

    WHEN an `automated` step naming a handler no registered use case
    answers to is made `active`
    THEN the write is rejected with a fault naming the step and the
    unknown handler.

    This is the *only* place registration is checked; a load does not
    re-check it.
    """
    unregistered = _Record(
        _step(
            identifier="price.buy-box-check",
            gate="live",
            kind=StepKind.AUTOMATED,
            status=StepStatus.IN_DEVELOPMENT,
            handler=UNREGISTERED_HANDLER,
            assignees=(),
        )
    )
    store = _store(extra=(unregistered,))

    with pytest.raises(REJECTED) as caught:
        await _set_status(
            store,
            "price.buy-box-check",
            StepStatus.ACTIVE,
            handlers=_registry(REGISTERED_HANDLER),
        )

    message = str(caught.value)
    # SPECIFIED: the fault names the step and the unknown handler.
    assert "price.buy-box-check" in message
    assert UNREGISTERED_HANDLER in message
    assert store.saves == []


async def test_a_human_step_written_with_a_handler_is_refused() -> None:
    """Scenario (launch-playbook): A human step carries no handler —
    the write half.

    WHEN a `human` step is written with a handler
    THEN the write is rejected with a fault naming the step.
    """
    store = _store()

    with pytest.raises(REJECTED) as caught:
        await _create(
            store,
            name="A human step someone tried to give a handler",
            kind=StepKind.HUMAN,
            handler=REGISTERED_HANDLER,
        )

    assert "handler" in str(caught.value).lower()
    assert store.saves == []


# ---------------------------------------------------------------------------
# The startup report: a deployment fault reported where it belongs
# ---------------------------------------------------------------------------


async def test_a_deploy_dropping_an_active_steps_handler_is_reported_at_startup() -> (
    None
):
    """Requirement statement: "A deployment whose registry no longer
    answers for an `active` step's handler SHALL instead be reported at
    startup, where a deployment fault belongs" (`tasks.md` 2.4).

    The counterpart to the load rule: the fault is real and must surface,
    but it surfaces at the deployment boundary rather than by making
    every playbook load fail. An implementation with no startup report at
    all would let a rename silently unbind an active step, which is the
    outcome Decision 6 accepts the load-path relaxation *in exchange
    for*.
    """
    active_unregistered = _step(
        identifier="price.buy-box-check",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler=UNREGISTERED_HANDLER,
        assignees=(),
    )
    in_development_unregistered = _step(
        identifier="creative.image-brief",
        gate="ignition",
        kind=StepKind.AUTOMATED,
        status=StepStatus.IN_DEVELOPMENT,
        handler=UNREGISTERED_HANDLER,
        assignees=(),
    )
    registered_active = _step(
        identifier="rank.indexation-confirmed",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler=REGISTERED_HANDLER,
        assignees=(),
    )

    report = _startup_report()
    result = report(
        steps=(active_unregistered, in_development_unregistered, registered_active),
        handlers=_registry(REGISTERED_HANDLER),
    )
    if hasattr(result, "__await__"):
        result = await result

    reported = str(result) if not isinstance(result, str) else result
    if isinstance(result, (list, tuple, set, frozenset)):
        reported = " ".join(str(row) for row in result)

    # SPECIFIED: the `active` step whose handler is unregistered is
    # reported...
    assert "price.buy-box-check" in reported
    # ...and the unknown handler named with it.
    assert UNREGISTERED_HANDLER in reported
    # SPECIFIED: only `active` steps are the subject — a step still in
    # development is expected to name a handler nothing registers yet,
    # and reporting it would make the signal noise.
    assert "creative.image-brief" not in reported
    assert "rank.indexation-confirmed" not in reported
