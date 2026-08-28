"""The roster collaborator a decision is actually wired to, and what a
mis-wiring says to the decider.

Derived strictly from the delta spec
`openspec/changes/restore-automated-decisions/specs/launch-step-automation/spec.md`
(MODIFIED requirement *Only a known, active person may decide a pending
result*).

This file carries the halves of that requirement's added scenarios that
cannot be observed at the use-case level:

- *A person the roster carries can decide through the wiring production
  supplies* — whole. `design.md` — Decision 6 makes the object under
  test the one `commerce_ops.main` injects, so no other tier can carry
  it.
- *An absent collaborator is refused the same way, not silently* — its
  adapter half: the error's type, that the decider is answered, and that
  the decision does not fail without an answer.
- *A mis-wiring is never reported as an unknown identity* — its adapter
  half: the reply carries no clause about the decider, and the fault is
  reported where operators see faults.

The use-case halves of those two, and the requirement's other four
scenarios, are
`tests/unit/launch/application/test_automated_decision_roster_shape.py`.
See `test-manifest.md` at the change root for the full accounting.

## Level

Each test here is at the smallest level that can observe its scenario,
and no higher.

The wiring scenario needs the *identity* of an object, not its shape, so
the smallest unit that can observe it is the composition root's own
attribute — `automation_confirmation.read_people` as `commerce_ops.main`
left it. A test that rebuilt a reader "the way `main.py` builds it" would
be a second object of the same shape and would go on passing at the
moment `main.py` regressed, which is precisely how this fault shipped
past a suite covering every rule it breaks (`design.md` — Decision 6,
citing `tests/integration/launch/test_playbook_authoring_roster_live.py`:
"A double can be shaped wrongly and pass; the real adapter cannot").

`tests/unit/launch/infrastructure/driving/test_main_monitoring_wiring.py`
already imports `commerce_ops.main` at module scope in this tier with no
database and no production secrets, so this needs no new tier and no new
fixture. What is under test is the object at the assignment, not
Postgres.

The substitution goes at the **store** — `commerce_ops.main.roster` —
and nowhere lower, per `design.md` — Decision 6 and `tasks.md` 4.5.
Substituting `commerce_ops.main.list_people` would replace the reader's
entire body, so a reader closed over the wrong store, or over nothing,
would still pass: the same escape this file exists to close, one level
down. Leaving the reader's call into `access`'s real `list_people`
intact is what makes the assertion about the wiring rather than about a
stub — and `_FakeRosterStore.loads` below is what proves the
substitution was reached at all.

The roster rows are built by driving `access`'s own `create_person`
rather than by inventing a row class, so the reader adapts the real rows
production would hand it. That is the arrangement
`test_playbook_admin_writes_reach_the_roster.py` records for the sibling
seam.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- That `main.py` injects a **reader** at the site currently assigning the
  store, and that the reader resolves the module-level `roster` global
  inside `list_people()` rather than capturing it at construction
  (`tasks.md` 2.3, 2.4).
- That the absent-collaborator fault raises `UnreadableRosterError`
  rather than `RuntimeError`, so one catch covers both wiring faults
  (`tasks.md` 2.2; `design.md` — Decision 4).
- That `_handle_decision` catches that error by its own type, logs it at
  `exception` level, and answers the decider with a sentence carrying no
  clause about their identity, roster entry or authority (`tasks.md`
  3.1, 3.2).

INVENTED, recorded in `test-manifest.md` as unresolved project questions
with their correction points:

- The names of the adapter's roster resolver and its decision entry
  point. Both are named in this change's own artifacts
  (`_roster_or_fail`, `_handle_decision`), but neither is a spec term, so
  each is probed over alternatives and fails loudly rather than
  defaulting. Correction points: `_RESOLVER_NAMES`, `_ENTRY_NAMES`.
- The decision entry point's **call shape**. `_drive_decision` supplies a
  pool of plausible Bolt and parsed-decision arguments and filters it by
  the implemented signature, the way `test_automation_confirmation_
  delivery.py`'s `_deliver` does. It is the single correction point.
- The seams that keep this tier off a database: the module-level
  `session` provider every driving module here holds (the convention
  `test_clickup_webhook.py` records), and every module-level class named
  for persistence by this repository's own suffixes. Correction points:
  `_SESSION_SEAM_NAMES`, `_PERSISTENCE_SUFFIXES`. Both were confirmed to
  drive the entry point as far as the roster resolution before these
  tests were reported: the fault they observe is the real
  `read_people`-is-absent fault escaping the listener, not an unmet
  collaborator of this file's own. Should a later change break that,
  correct the arrangement — never the assertions.
- The wording by which a reply blames the decider. Correction point:
  `_BLAMES_THE_IDENTITY`, kept identical to the application file's, where
  it is checked against a genuine unknown-identity refusal so it cannot
  match nothing.

Deliberately **not** driven here: the *mis-shaped* collaborator's reply.
The shape check sits after the settled lookup by `tasks.md` 1.3, so
reaching it needs the pending-result store to answer with a real pending
row — which the permissive substitution above cannot do, and a real
double for it would need the repository's own shape, which no artifact
fixes. The absent collaborator, by contrast, is refused by the adapter
before any of that. What makes the two answer alike is that they raise
one type (asserted in the application file) and that one catch handles it
(asserted below by the type the catch is keyed on). Recorded in
`test-manifest.md` rather than omitted.

## Expected first-run state

Every test in this file is expected to **FAIL**, and each on a different
part of the missing mechanism:

- the wiring test, because `read_people` is the `PostgresRoster` store
  today, so `_person_for` finds none of its spellings and the decision is
  refused as though the roster did not carry Alice — with the substituted
  store never read at all;
- the resolver test, because the pre-injection window raises a bare
  `RuntimeError` (`tasks.md` 2.2);
- the two reply tests, because nothing catches either wiring fault, so
  the error escapes the Bolt listener after `ack()` and the decider is
  answered with silence — the outcome `design.md` — Decision 4 forbids
  as loudly as a false refusal.

A test here that passes before the implementation lands is a defect in
that test, not good news.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1155 passed, 0 failed, 96 skipped (the integration tier,
which finds no `DATABASE_URL` here), 2026-08-27, commit `ea9f31b`, clean
tree.
"""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
import commerce_ops.main as composition_root
from commerce_ops.access.application import create_person
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import automation_confirmation
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"

ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Admin"
BOOTSTRAP_PRINCIPAL: Final = "bootstrap"

LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration."
)

#: Kept identical to the application file's list — see that file, where a
#: genuine unknown-identity refusal is asserted to match one of them, so
#: the negative assertions here cannot pass vacuously.
_BLAMES_THE_IDENTITY: Final = (
    "does not know",
    "doesn't know",
    "not on the roster",
    "unknown identity",
    "unrecognised",
    "unrecognized",
    "no such person",
    "not known",
)

#: Words a reply must carry for the decider to learn their press did
#: nothing (INVENTED; `tasks.md` 3.1 fixes the substance, not the
#: phrasing). Correction point for the implemented wording.
_SAYS_NOT_PROCESSED: Final = (
    "not processed",
    "could not be processed",
    "couldn't be processed",
    "not be processed",
    "went wrong",
    "failed",
    "reported",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    """Stands in for the process-wide session provider's `session()`.

    Yields `None`: nothing below reaches a repository that would issue a
    query, because each of these tests is refused before the decision is
    judged. The convention -- a module-level `session` seam substituted
    with `monkeypatch.setattr` -- is the one every other file in this
    directory uses (`test_clickup_webhook.py`, `test_clickup_sync_job_
    stand_down.py`), and is what keeps this file unit-tier with no
    `DATABASE_URL` and no Postgres.
    """
    yield None


#: The seams a driving module in this directory holds its session
#: provider under. Probed rather than assumed; substituting a name the
#: module does not have would leave the real provider in place.
_SESSION_SEAM_NAMES: Final = ("session", "transaction")

#: Suffixes this repository names its persistence collaborators with.
#: Every module-level class matching one is substituted below, so a
#: decision refused at the wiring never reaches a query. Named by
#: convention rather than by a list of specific classes, so a repository
#: this adapter gains later is covered without editing this file.
_PERSISTENCE_SUFFIXES: Final = ("Repository", "Repositories", "Store", "Roster")


class _AnswersNothing:
    """A persistence collaborator that accepts any construction and
    answers `None` to anything asked of it.

    Sound only because every test in this file is refused *before* the
    decision is judged: nothing below asserts on what a repository
    returned. A test that needed a real answer from one would need a real
    double, not this.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def __getattr__(self, name: str) -> Any:
        async def _answer(*args: Any, **kwargs: Any) -> None:
            return None

        return _answer


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    """INVENTED, and a correction point: which seam the confirmation
    adapter obtains its session through is fixed by no artifact."""
    substituted = [
        name for name in _SESSION_SEAM_NAMES if hasattr(automation_confirmation, name)
    ]
    for name in substituted:
        monkeypatch.setattr(automation_confirmation, name, _fake_session)
    assert substituted, (
        "the confirmation adapter exposes no session seam under any of "
        f"{_SESSION_SEAM_NAMES}; correct `_SESSION_SEAM_NAMES` to the "
        "implemented one, or these tests will reach a real database"
    )

    for name, value in list(vars(automation_confirmation).items()):
        if isinstance(value, type) and name.endswith(_PERSISTENCE_SUFFIXES):
            monkeypatch.setattr(automation_confirmation, name, _AnswersNothing)


# ---------------------------------------------------------------------------
# Domain fixtures (the shape `test_automated_result_decisions.py` records)
# ---------------------------------------------------------------------------


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
        "identifier": STEP_ID,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "needs_confirmation": True,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "automation_brief": "Propose the Amazon sub-category node.",
        "handler": HANDLER_NAME,
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
        kind=StepKind.HUMAN,
        needs_confirmation=False,
        assignees=(),
        automation_brief=None,
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(_step(), *fillers))


@dataclass
class _PendingRow:
    product_id: ProductId = PRODUCT_ID
    step_id: str = STEP_ID
    handler: str = HANDLER_NAME
    proposed_outcome: Any = Satisfied
    result_text: str = RECOMMENDATION
    produced_at: datetime = PRODUCED_AT
    state: str = "pending"
    delivered_at: datetime | None = PRODUCED_AT + timedelta(seconds=2)
    decided_by: str | None = None
    decided_at: datetime | None = None


class _FakeResults:
    def __init__(self, *rows: _PendingRow) -> None:
        self.rows: list[_PendingRow] = list(rows)

    async def pending_for(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        for row in self.rows:
            if (
                row.product_id == product_id
                and row.step_id == step_id
                and row.state == "pending"
            ):
                return row
        return None

    async def settle(
        self, row: object, *, state: str, decided_by: str, decided_at: datetime
    ) -> None:
        target = self._row_of(row)
        target.state = state
        target.decided_by = decided_by
        target.decided_at = decided_at

    async def void(self, row: object) -> None:
        self._row_of(row).state = "voided"

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        rejected = [row for row in self.rows if row.state == "rejected"]
        return rejected[-1] if rejected else None

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        raise AssertionError(f"unknown pending row {row!r}")

    @property
    def only(self) -> _PendingRow:
        assert len(self.rows) == 1
        return self.rows[0]


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self._launch = launch

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launch if product_id == self._launch.product_id else None

    async def list_active(self) -> list[Launch]:
        return [self._launch]


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()


# ---------------------------------------------------------------------------
# The roster store `commerce_ops.main` holds, and the rows it carries
# ---------------------------------------------------------------------------


class _FakeRosterStore:
    """In-memory whole-set roster store, shaped as
    `tests/unit/access/application/test_roster_writes.py` records
    `RosterStore` — which is `PostgresRoster`'s shape, and so the shape
    `main.py`'s reader must be able to read through."""

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 7) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.loads = 0
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        self.loads += 1
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


async def _roster_carrying_alice() -> _FakeRosterStore:
    """A roster the administration surface holds as active, built by
    driving `access`'s own `create_person` so the rows are the real ones
    the reader adapts."""
    store = _FakeRosterStore()
    await create_person(
        roster=store,
        principal=BOOTSTRAP_PRINCIPAL,
        display_name=ALICE_NAME,
        slack_identity=ALICE_SLACK,
        clickup_user_id=None,
        admin=True,
    )
    store.loads = 0  # only reads made by the decision under test count
    return store


# ---------------------------------------------------------------------------
# The decision use case, reached through one correction point
# ---------------------------------------------------------------------------

_ACCEPT_NAMES: Final = (
    "accept_automated_result",
    "accept_pending_result",
    "accept_result",
)
_DECIDE_NAMES: Final = ("decide_automated_result", "decide_pending_result")


@dataclass
class _Collaborators:
    results: _FakeResults
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    recorder: _RecordingOutcomes


def _collaborators() -> _Collaborators:
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return _Collaborators(
        results=_FakeResults(_PendingRow()),
        launches=_FakeLaunches(launch),
        playbook=playbook,
        recorder=_RecordingOutcomes(),
    )


async def _accept(collaborators: _Collaborators, roster: Any) -> Any:
    """INVENTED call shape — kept identical to the application file's, so
    the two correct together."""
    supplied: dict[str, Any] = {
        "results": collaborators.results,
        "roster": roster,
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "record_outcome": collaborators.recorder,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }

    use_case = None
    for name in _ACCEPT_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            use_case = found
            break
    if use_case is None:
        for name in _DECIDE_NAMES:
            found = getattr(launch_application, name, None)
            if callable(found):
                use_case = found
                supplied["accept"] = True
                break
    if use_case is None:
        pytest.fail(
            "no decision use case is exported from "
            "`commerce_ops.launch.application` under any of "
            f"{_ACCEPT_NAMES + _DECIDE_NAMES} — correct this file's probe"
        )

    accepted = set(inspect.signature(use_case).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the decision use case does not accept {unknown}; correct `_accept` "
        "to the implemented collaborator names"
    )
    return await use_case(**supplied)


def _reason(returned: Any) -> str:
    for attribute in ("reason", "message", "detail"):
        carried = getattr(returned, attribute, None)
        if isinstance(carried, str) and carried:
            return carried
    return str(returned)


def _blames_the_identity(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _BLAMES_THE_IDENTITY)


def _wiring_error_type() -> type[BaseException]:
    found = getattr(launch_application, "UnreadableRosterError", None)
    if isinstance(found, type) and issubclass(found, BaseException):
        return found
    pytest.fail(
        "`commerce_ops.launch.application` exports no `UnreadableRosterError` "
        "— `tasks.md` 1.6 requires it on the module's public surface, "
        "because `automation_confirmation` may reach it no other way"
    )


# ---------------------------------------------------------------------------
# Scenario: A person the roster carries can decide through the wiring
# production supplies
# ---------------------------------------------------------------------------


async def test_a_roster_person_can_decide_through_the_injected_collaborator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A person the roster carries can decide through the
    wiring production supplies.

    WHEN a decision arrives from a Slack identity that the
    roster-administration surface holds as active, judged against the
    roster collaborator the running system supplies
    THEN that person is resolved and the decision is judged on its merits
    rather than refused as unknown.

    The collaborator under test is `automation_confirmation.read_people`
    **as `commerce_ops.main` left it** — read, never rebuilt. Rebuilding
    it would test a second object of the same shape and would keep
    passing at the moment `main.py` regressed (`design.md` — Decision 6).

    The substitution is at `commerce_ops.main.roster`, the store, and
    nowhere lower (`tasks.md` 4.5). `store.loads` is asserted for that
    reason: a reader that captured a different store at construction, or
    closed over nothing, would answer an empty roster and refuse Alice
    while never touching the store this test substituted — so the read
    count is what distinguishes "the wiring works" from "something
    answered".

    Expected to FAIL on its first run: `read_people` is the
    `PostgresRoster` store today, `_person_for` finds none of its
    spellings on it, and Alice is refused as unknown with the
    substituted store never read (`proposal.md` — *Why*).
    """
    store = await _roster_carrying_alice()
    monkeypatch.setattr(composition_root, "roster", store)

    injected = automation_confirmation.read_people
    assert injected is not None, (
        "`commerce_ops.main` injected no roster collaborator into "
        "`automation_confirmation.read_people` at all, so no decision this "
        "deployment receives can be judged"
    )

    collaborators = _collaborators()
    returned = await _accept(collaborators, injected)

    # SPECIFIED: the roster production supplies was actually read …
    assert store.loads >= 1, (
        "the decision resolved without ever reading the roster store "
        "`commerce_ops.main` holds. The injected collaborator is not reading "
        "through that store — it either captured a different one at "
        "construction (`tasks.md` 2.4) or is not a reader at all"
    )
    # SPECIFIED: … the person was resolved, and not refused as unknown …
    assert not _blames_the_identity(_reason(returned)), (
        "an identity the roster carries as active was refused as one the "
        f"roster does not know: {_reason(returned)!r}"
    )
    assert getattr(returned, "refused", False) is not True, (
        f"the decision was refused: {_reason(returned)!r}"
    )
    # SPECIFIED: … and the decision was judged on its merits, which at
    # this point means the outcome the handler proposed was recorded.
    assert len(collaborators.recorder.calls) == 1, (
        "the decision was neither refused nor recorded, so it was not judged "
        "on its merits"
    )
    assert collaborators.results.only.state != "pending"


# ---------------------------------------------------------------------------
# Scenario: An absent collaborator is refused the same way, not silently
# ---------------------------------------------------------------------------

_RESOLVER_NAMES: Final = (
    "_roster_or_fail",
    "roster_or_fail",
    "_require_roster",
    "_read_people_or_fail",
)


def _roster_resolver() -> Any:
    """The adapter's narrowing of the injected collaborator (`tasks.md`
    2.2). Probed rather than assumed — the name is fixed by this change's
    artifacts, not by the spec."""
    for name in _RESOLVER_NAMES:
        found = getattr(automation_confirmation, name, None)
        if callable(found):
            return found
    pytest.fail(
        "the confirmation adapter exposes no roster resolver under any of "
        f"{_RESOLVER_NAMES} — correct this file's probe to the implemented "
        "name rather than letting the pre-injection window go unasserted"
    )


async def test_an_absent_collaborator_raises_the_named_wiring_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An absent collaborator is refused the same way, not
    silently — the "same named wiring error" half.

    WHEN a decision arrives at a deployment where no roster collaborator
    was supplied at all
    THEN it is refused with the same named wiring error […].

    "The same" is the point: `design.md` — Decision 4 makes both wiring
    faults raise one type so that one catch, one reply and one scenario
    cover them, "because they are one mistake made in two places and a
    decider cannot act differently on them". A `RuntimeError` here is
    caught by nothing and escapes the Bolt listener after `ack()`.

    Expected to FAIL on its first run: the pre-injection window raises a
    bare `RuntimeError` today (`tasks.md` 2.2).
    """
    monkeypatch.setattr(automation_confirmation, "read_people", None)

    resolver = _roster_resolver()
    parameters = inspect.signature(resolver).parameters
    required = [
        name
        for name, parameter in parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in (
            parameter.POSITIONAL_ONLY,
            parameter.POSITIONAL_OR_KEYWORD,
            parameter.KEYWORD_ONLY,
        )
    ]
    assert not required, (
        f"the roster resolver takes required arguments {required}; correct "
        "`_roster_resolver`'s call below to the implemented signature"
    )

    # The catch cannot be narrowed: the raised type is exactly what this
    # test is here to pin, and narrowing it would assert the answer.
    with pytest.raises(Exception) as caught:
        outcome = resolver()
        if inspect.isawaitable(outcome):
            await outcome

    # SPECIFIED: the named wiring error, not the bare `RuntimeError`
    # nothing catches today. Asserted before the type is looked up by
    # name, so today's failure reads as what was actually raised rather
    # than as a missing export.
    assert type(caught.value) is not RuntimeError, (
        "a deployment with no roster collaborator raised a bare "
        f"RuntimeError({str(caught.value)!r}). `tasks.md` 2.2 preserves that "
        "message and changes the type, because a `RuntimeError` here is "
        "caught by nothing and escapes the Bolt listener after `ack()`"
    )
    assert type(caught.value) is _wiring_error_type(), (
        "a deployment with no roster collaborator refused the decision as "
        f"{type(caught.value).__name__}. `tasks.md` 2.2 requires the same "
        "`UnreadableRosterError` the mis-shaped collaborator raises, so that "
        "one catch in `_handle_decision` covers both"
    )
    # SPECIFIED (`tasks.md` 2.2): its message is preserved — only its
    # type changes — so it still says what was missing.
    assert str(caught.value).strip(), (
        "the wiring error carries no message at all; `tasks.md` 2.2 changes "
        "only the type of the pre-injection failure, preserving what it said"
    )


# ---------------------------------------------------------------------------
# Scenario: A mis-wiring is never reported as an unknown identity — the
# adapter's half, and the reply half of the absent-collaborator scenario
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "_handle_decision",
    "handle_decision",
    "_decide",
    "handle_decision_action",
)


class _CapturingRespond:
    def __init__(self) -> None:
        self.replies: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.replies.append({"args": args, "kwargs": kwargs})

    @property
    def rendered(self) -> str:
        return json.dumps(self.replies, default=str)


class _CountingAck:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


def _button_body(*, accept: bool) -> dict[str, Any]:
    """A Slack `block_actions` payload for one of the two decision
    buttons.

    The value carries `product_id` and `step_id`, which `proposal.md` —
    *Impact* fixes as what the posted messages hold; the encoding is
    INVENTED and is part of `_drive_decision`'s correction point.
    """
    value = json.dumps({"product_id": str(PRODUCT_ID), "step_id": STEP_ID})
    action = {
        "action_id": "accept_automated_result" if accept else "reject_automated_result",
        "type": "button",
        "value": value,
    }
    return {
        "type": "block_actions",
        "user": {"id": ALICE_SLACK},
        "channel": {"id": "C0MONITORING"},
        "actions": [action],
        "response_url": "https://slack.example/respond",
    }


@dataclass
class _Answer:
    """What the decider got back: whatever the entry point returned, plus
    whatever it sent through `respond`."""

    returned: Any
    respond: _CapturingRespond
    escaped: BaseException | None

    @property
    def text(self) -> str:
        parts = [self.respond.rendered]
        if self.returned is not None:
            parts.append(str(self.returned))
            parts.append(_reason(self.returned))
        return "\n".join(parts)

    @property
    def answered(self) -> bool:
        if self.respond.replies:
            return True
        return isinstance(self.returned, str) and bool(self.returned.strip())


async def _drive_decision(*, accept: bool = True) -> _Answer:
    """INVENTED call shape — the single correction point for this file's
    two reply tests.

    Supplies a pool of plausible Bolt and parsed-decision arguments and
    filters it by the implemented signature, as
    `test_automation_confirmation_delivery.py`'s `_deliver` does. If the
    entry point cannot be driven without a database session, correct this
    helper to substitute that seam — do not weaken what the tests below
    assert.
    """
    entry = None
    for name in _ENTRY_NAMES:
        found = getattr(automation_confirmation, name, None)
        if callable(found):
            entry = found
            break
    if entry is None:
        pytest.fail(
            "the confirmation adapter exposes no decision entry point under "
            f"any of {_ENTRY_NAMES} — correct `_ENTRY_NAMES` to the "
            "implemented name"
        )

    respond = _CapturingRespond()
    body = _button_body(accept=accept)
    pool: dict[str, Any] = {
        "ack": _CountingAck(),
        "body": body,
        "payload": body["actions"][0],
        "action": body["actions"][0],
        "respond": respond,
        "say": respond,
        "client": None,
        "context": {},
        "logger": logging.getLogger("commerce_ops.launch.automation_confirmation"),
        "accept": accept,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }

    accepted = set(inspect.signature(entry).parameters)
    supplied = {key: value for key, value in pool.items() if key in accepted}
    assert supplied, (
        "none of this file's supplied arguments matched the decision entry "
        f"point's signature ({sorted(accepted)}); correct `_drive_decision`"
    )

    try:
        returned = entry(**supplied)
        if inspect.isawaitable(returned):
            returned = await returned
    except Exception as error:  # noqa: BLE001 -- an escaping fault is exactly
        # the outcome the scenario forbids, so it is observed, not raised
        return _Answer(returned=None, respond=respond, escaped=error)
    return _Answer(returned=returned, respond=respond, escaped=None)


async def test_a_wiring_fault_answers_the_decider_rather_than_falling_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An absent collaborator is refused the same way, not
    silently — its "the decider is told" half.

    WHEN a decision arrives at a deployment where no roster collaborator
    was supplied at all
    THEN […] the decider is told their decision was not processed, and
    the decision does not fail without an answer.

    The failure this forbids is specific: Bolt swallows an exception
    raised after `ack()`, so the decider sees nothing at all — "the one
    outcome the requirement forbids as loudly as a false refusal"
    (`design.md` — Decision 4). `tasks.md` 3.4 states it as: no wiring
    fault may leave the listener without calling `respond`.

    Expected to FAIL on its first run: nothing catches the fault today,
    so it escapes and the decider is answered with silence.
    """
    monkeypatch.setattr(automation_confirmation, "read_people", None)

    answer = await _drive_decision()

    # SPECIFIED: the decision does not fail without an answer.
    assert answer.escaped is None, (
        "the wiring fault escaped the decision listener rather than being "
        f"answered: {answer.escaped!r}. If this is not the wiring fault but "
        "an unmet collaborator of this test's own (a database session, say), "
        "that is a defect in `_drive_decision`, which is the correction point"
    )
    assert answer.answered, (
        "the decider got nothing back at all — no reply and no message — "
        "which after `ack()` is a button that silently does nothing"
    )
    # SPECIFIED: and what they got says their decision was not processed.
    lowered = answer.text.lower()
    assert any(marker in lowered for marker in _SAYS_NOT_PROCESSED), (
        "the reply does not tell the decider their decision was not "
        f"processed: {answer.text!r}"
    )


async def test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: A mis-wiring is never reported as an unknown identity —
    its adapter half.

    WHEN a decision is judged against a roster collaborator that cannot
    answer who the roster carries
    THEN the decider is not told that the roster does not know their
    Slack identity, and the mis-wiring is reported where operators see
    faults.

    Two assertions, one per clause. The reply carries "no clause about
    the decider's identity, their roster entry, or their authority"
    (`tasks.md` 3.2), and the fault is logged at `exception` level, which
    `design.md` — Decision 4 names as the "reported where operators see
    faults" half of the requirement.

    Driven through the absent-collaborator fault rather than the
    mis-shaped one: both raise one type and are caught once (`design.md`
    — Decision 4), and the absent case is refused by the adapter before
    the decision reaches the pending-result store this tier does not
    have. The mis-shaped collaborator's own refusal is asserted in
    `tests/unit/launch/application/test_automated_decision_roster_shape.py`.

    Expected to FAIL on its first run: nothing catches the fault, so
    there is no reply to inspect and nothing is logged.
    """
    monkeypatch.setattr(automation_confirmation, "read_people", None)

    with caplog.at_level(logging.DEBUG):
        answer = await _drive_decision()

    # The non-vacuity guard: an empty reply satisfies every "does not
    # say" assertion below, and an empty reply is what a mis-wired
    # deployment produces today. The sibling test above owns this clause;
    # it is repeated here so these assertions cannot pass by silence.
    assert answer.answered, (
        "there is no reply to inspect — the decider got nothing back, so "
        "the assertions below would pass for the wrong reason"
    )

    # SPECIFIED: the decider is not told the roster does not know them.
    assert not _blames_the_identity(answer.text), (
        "a mis-wired deployment told the decider something about their own "
        f"identity: {answer.text!r}"
    )
    assert ALICE_SLACK not in answer.text, (
        f"the reply names the decider's Slack identity: {answer.text!r}"
    )

    # SPECIFIED: the mis-wiring is reported where operators see faults.
    faults = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert faults, (
        "the mis-wiring was answered to the decider but never reported at "
        "`error` level or above, so the only trace of a broken deployment is "
        "a sentence in one Slack thread"
    )
    assert any(record.exc_info is not None for record in faults), (
        "the fault was logged without its exception, so an operator sees "
        "that something failed but not what was wired where. `design.md` — "
        "Decision 4 asks for `exception` level"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the two Bolt listeners keep their `ack()`-first ordering
#   (`tasks.md` 3.3). Unchanged by this delta, and already covered for
#   this app's listeners by
#   `test_slack_entry_ack_and_failure_visibility.py`; asserting it here
#   would pin the entry point's shape further than any scenario states.
# - That `read_people`'s declared type turns a store-shaped injection
#   into a `mypy` error at the assigning line (`design.md` — Decision 3,
#   `tasks.md` 2.5). A static guarantee; no runtime assertion observes
#   it, and a test pretending to would pass for the wrong reason.
# - The *mis-shaped* collaborator's reply, driven at this tier. See the
#   module docstring — reaching it requires the decision to enter the use
#   case, and what makes the two faults answer alike is the single type
#   and single catch asserted above and in the application file.
# ---------------------------------------------------------------------------
