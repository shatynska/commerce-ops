"""A handler that repeats a non-terminal outcome is cooled off, and the
stuck step is reported once.

Derived strictly from the delta spec of the OpenSpec change
`cool-off-a-repeatedly-blocked-step`:
`openspec/changes/cool-off-a-repeatedly-blocked-step/specs/launch-step-automation/spec.md`

Covers:

- the **revised** scenario of the MODIFIED requirement *A non-terminal
  outcome is recorded directly and never held for a decision* -- *A step
  reporting no progress is reconsidered on the next pass*, whose WHEN the
  delta narrows to the changed-outcome case. Its other scenario is
  unchanged and stays covered by `test_automation_pass.py`.
- every scenario of the ADDED requirement *A handler that repeats itself
  is not asked again immediately* -- all ten -- plus three clauses of its
  statement that carry no scenario of their own (the cool-off being its
  own constant, a failed *write* leaving the step eligible, and a failed
  restore ending the walk).
- every scenario of the ADDED requirement *A step whose handler has
  stopped making progress is reported once* -- all seven.

The four scenarios of the MODIFIED requirement *An automated step's
handler is invoked by recurring work* are unchanged by this delta and
stay covered by `test_automation_pass.py`; what the delta adds to that
requirement is a fourth openness condition, which is what the ADDED
requirement's scenarios above exercise.

See `test-manifest.md` at the change root for the full accounting.

## Level

Every scenario here is stated over *a pass* -- which handlers it invokes,
what it records, what it reports, and what it leaves alone across two
passes. The pass function over in-memory doubles is the smallest unit
that can observe those, and it is the level `test_automation_pass.py`
already establishes for this same function.

## THE SEAM CONTRACT

`tasks.md` 3.1 and 4.2 fix that both new collaborators -- the backoff
record and the monitoring notifier -- **reach `run_automation_pass` as
arguments**, "the way `results` and `deliver` already do". What is
INVENTED is only their *names*, so `_run_pass` probes the entry point's
signature for each and supplies it under the first name the pass accepts.
`test_the_pass_accepts_a_backoff_record_and_a_report_seam` states that
contract once, with a directive, rather than every test failing on it.

INVENTED, each with its correction point:

- **The argument names** (`_BACKOFF_ARGUMENT_NAMES`,
  `_REPORT_ARGUMENT_NAMES`).
- **The store's accessors** -- `read`, `note`, `mark_reported` --
  installed under every plausible spelling as aliases on `_BackoffStore`,
  and each absorbing `*args, **kwargs` so nothing here pins a call shape.
  `_identify` recovers the launch, the step, the outcome kind and the
  moment from whatever it is handed.
- **The row's attribute names.** `_BackoffRow` answers to
  `outcome`/`outcome_kind`/`kind`/`noted_outcome`, `noted_at`/`when`, and
  `reported_at`/`reported`/`has_been_reported`, and its kind compares
  equal to a class, an instance or a name string alike (`_Kind`), so a
  round-trip through this fake pins no representation.
- **How the shared store is restored.** Modelled two ways at once: the
  store offers `rollback()`, and `automation_pass.session` is replaced by
  a provider yielding the same `_FakeSession`. Either route restores it.
- **That "reported" means a WARNING-or-above log record or a monitoring
  message.** `_reported_text` reads both, so no test here pins the
  channel a *fault* is reported through. What the *stuck-step report*
  goes through is not invented, but it is now pinned rather than
  tolerant of either shape: `_FakeNotifier.post_monitoring_message`
  originally transcribed `test_clickup_field_configuration_check.py`'s
  `MonitoringNotifier` double and accepted both the message-only positional
  call and the channel/text/thread_ts keyword call, "satisfied
  structurally" and pinning no call shape. `fix-stuck-step-report-notifier`
  narrowed it to `ThreadReplyNotifier` (`channel`/`text`/`thread_ts`
  keywords only) once `worker.py` started injecting `launch`'s own notifier
  here instead of `briefing`'s: the dual tolerance is exactly what let that
  mismatch reach production unnoticed, since a double accepting every shape
  a caller might use can never notice which one it was actually given.

Correcting any of the above is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: which handlers are invoked, what is recorded, what is delivered,
how many times, and -- for the several clauses stated in the negative --
what is *not*.

## The store fake is deliberately naive, and that is what makes two
## tests discriminate

`tasks.md` 3.1 puts one obligation inside the driven accessor: noting a
repeat against a **different outcome kind must clear the reported
stamp**. A fake implementing that obligation would do the implementation's
work, and *A step that gets stuck again after moving is reported again*
would then pass whether or not anything in the pass had been written.

So `_BackoffStore.note` models the naive `SET outcome=..., noted_at=...`:
it leaves `reported_at` exactly as it found it. The scenario therefore
turns on the pass's own **lazy lift** -- the delta's "a cool-off SHALL
cease to govern the step as soon as the step's recorded outcome is no
longer an outcome of the kind the cool-off was noted against", which
`design.md` Decision 4 extends to the report suppression in the same
breath. An implementation that lazily lifts passes here whether or not
its store also clears the stamp; one that relies on the store alone does
not.

## The poisoned session

`tasks.md` 1.2 names the trap, inherited from `contain-a-failing-launch`
(archived 2026-08-27) and again from `add-launch-journal`: **a store fake
that merely raises reproduces the exception but not the failed
transaction state the restore exists for**, so a test built on one passes
whether or not the restoration was ever written.

`_FakeSession` here is transcribed from
`tests/unit/launch/application/test_launch_journal_containment.py`: a
failed access poisons it, and every later use raises
`PendingRollbackError` until it is rolled back. The launches read, the
outcome recorder and the backoff store all share one, exactly as the
composing adapters share one real session -- so *A failed backoff access
does not cost the pass its other work* is red unless the restore is
there. `design.md` Decision 5 records why the exposure is worse here than
at the `clickup-sync` precedent: this record is touched per step *inside*
the walk, where a poisoned session makes every later `record_outcome`
fail while the run still reports success.

## The split degrade is tested in halves, never together

`design.md` Decision 5: one row carries two decisions that fail in
**opposite** directions -- a failed access leaves the step **eligible for
invocation** and delivers **no report** for it on that pass. A single
test asserting one half passes against an implementation that applied one
default to both, which is the mistake the change's third review round
caught. So the two halves are two tests:
`test_a_step_whose_backoff_record_cannot_be_read_is_still_invoked` and
`test_a_pass_that_cannot_read_the_backoff_record_delivers_no_report`,
each asserting its own half and neither standing in for the other.

## Vacuous-pass guards

Several assertions below are satisfied by the behaviour that already
ships -- "the handler is invoked" is what the pass does unconditionally
today. Those tests call `_require_backoff_reached`, which fails with a
directive where the pass never consulted the record at all, so a pass
that is green because the feature is absent is not mistaken for coverage
(`ai-toolkit:testing`, the fourth failure state). Every test asserting an
absence carries a positive control in the same test -- the same state
under which the thing does happen.

## Expected state

Every test here passes, and the whole file runs in the commit-time tier.

That was not true between `cool-off-a-repeatedly-blocked-step` and
`restore-the-skipped-unit-tests`. This file was skipped wholesale by an
autouse fixture matching its *filename*, under the reason "Unit test
requires database", which was false: `thread-launch-slack-notifications`
had given `run_automation_pass` a required `establish_thread` argument
that `_run_pass` was never told about, and 17 tests failed on that
`TypeError` alone. The 7 stuck-step report tests failed on two further
harness gaps -- `launches_channel()` reading an unset environment
variable, and `_FakeNotifier` modelling the pre-thread call shape -- both
swallowed by `_report_stuck_step`'s own `except`, so they surfaced only
as an empty message list. Nothing here ever needed a database. The
fixtures below carry the corrections; no assertion was changed.

The section this replaces recorded the file's *first-run* state, when it
was written before its subject existed and every test was expected to
fail. That state is three changes old.

Baseline recorded before these tests were written, at the worktree root:
`uv run pytest tests/unit tests/agents` -- 1427 passed, 2 xfailed, 0
failed.
`uv run pytest tests/integration` -- 108 passed, 2 skipped (a database is
reachable here; both skips are pre-existing seed-data skips).
"""

from __future__ import annotations

import inspect
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from sqlalchemy.exc import PendingRollbackError

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    InProgress,
    LaunchPlaybook,
    NotStarted,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import (
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driving import automation_pass
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fakes import FakeHandlers as _FakeHandlers
from tests.support.fixtures import (
    ALICE,
    HANDLER_NAME,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import PendingRow as _PendingRow

pytestmark = pytest.mark.anyio

# ---------------------------------------------------------------------------
# Transcribed from `test_automation_pass.py` -- the same playbook, the same
# launch, the same two step kinds. Re-declared rather than imported, the
# way every other file in this directory re-declares its fixtures.
# ---------------------------------------------------------------------------

PRODUCT_ID: Final = product_id()
OTHER_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

OTHER_PRODUCT_NAME: Final = "Walnut Serving Tray"
OTHER_PRODUCT_SKU: Final = Sku("WST-2027-02")

AUTOMATED_STEP_ID: Final = "listing.sub-category"
SECOND_STEP_ID: Final = "listing.bullet-points"
SECOND_HANDLER_NAME: Final = "listing.bullet_advisor"
THREAD_TS: Final = "1700000000.000100"
LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"  # not a real channel

NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 5, 9, 30, tzinfo=UTC)

PASS_INTERVAL: Final = timedelta(minutes=15)

# DERIVED from `design.md` Decision 6 ("its own constant at the same 24
# hours"). What is SPECIFIED is that *some* fixed cool-off both suppresses
# and then expires, and that it is not the rejection one. If the figure is
# revised, this constant is what to correct; the two-sided behaviour it
# guards is not.
REPEAT_COOL_OFF: Final = timedelta(hours=24)

# The two wordings `proposal.md` quotes from the advisor's own journal
# entries -- the same block, reworded. Decision 2 turns on these.
FIRST_WORDING: Final = "I cannot confidently determine the appropriate sub-category"
SECOND_WORDING: Final = "I am unable to determine a specific sub-category node"


def _produced(reason: str) -> str:
    """What the handler produced as its *result*.

    A superstring of the reason, deliberately: `tasks.md` 4.1 says the
    report names "what the handler produced as its result", explicitly
    "not 'the outcome's reason'", so an implementation quoting the reason
    alone must not satisfy the assertion.
    """
    return f"No node chosen. {reason}."


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": AUTOMATED_STEP_ID,
            "name": "Choose the sub-category node",
            "assignees": (ALICE,),
            **overrides,
        }
    )


def _automated(**overrides: Any) -> StepDefinition:
    """The step under test: `active`, `automated`, naming a handler."""
    attributes: dict[str, Any] = {
        "kind": StepKind.AUTOMATED,
        "handler": HANDLER_NAME,
        "assignees": (),
    }
    attributes.update(overrides)
    return _step(**attributes)


def _second_automated() -> StepDefinition:
    """A second automated step on the same launch.

    *A failed backoff access does not cost the pass its other work* is
    stated over "the remaining steps **and** launches", so both halves
    need something remaining.
    """
    return _automated(
        identifier=SECOND_STEP_ID,
        name="Draft the bullet points",
        handler=SECOND_HANDLER_NAME,
    )


def _hold(gate: str) -> StepDefinition:
    """One blocking `human` step per gate, satisfying the gate-holding
    floor without adding a step the pass would invoke."""
    return _build_hold(
        gate,
        assignees=(ALICE,),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    return _build_playbook(
        *steps,
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook, product_id: ProductId = PRODUCT_ID) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _provenance(
    *, who: str = HANDLER_NAME, evidence: str, when: datetime
) -> Provenance:
    return Provenance(source="automated", who=who, when=when, evidence=evidence)


def _carrying(
    launch: Launch,
    playbook: LaunchPlaybook,
    outcome: Any,
    *,
    step_id: str = AUTOMATED_STEP_ID,
    evidence: str | None = None,
    who: str = HANDLER_NAME,
    when: datetime = APPROVED_AT,
) -> Launch:
    """The launch, with an outcome already recorded against one step.

    The delta says the outcome being repeated is "the one the step
    carries, **whatever recorded it**", so `who` is a parameter: a
    member's rejection recorded the `Blocked` in one of the tests below.
    """
    launch.record_step_outcome(
        playbook,
        step_id=step_id,
        outcome=outcome,
        provenance=_provenance(
            who=who,
            evidence=evidence if evidence is not None else _produced(FIRST_WORDING),
            when=when,
        ),
    )
    return launch


# ---------------------------------------------------------------------------
# The outcome *kind*, which is the whole of Decision 2
# ---------------------------------------------------------------------------


def _kind_name(value: Any) -> str:
    """`Blocked("a")`, `Blocked` and `"Blocked"` all name one kind."""
    if isinstance(value, _Kind):
        return value.name
    if isinstance(value, str):
        return value
    if isinstance(value, type):
        return value.__name__
    return type(value).__name__


class _Kind:
    """The kind a backoff row was noted against.

    Compares equal to a class, to an instance of it, or to its name, so a
    round-trip through this fake pins no representation on the
    implementation -- while still refusing to equal a *different* kind,
    which is what every assertion below depends on.
    """

    __slots__ = ("name",)

    def __init__(self, value: Any) -> None:
        self.name = _kind_name(value)

    def __eq__(self, other: object) -> bool:
        return _kind_name(other) == self.name

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"_Kind({self.name!r})"


# ---------------------------------------------------------------------------
# The shared session, and what a failed access leaves it in
# ---------------------------------------------------------------------------

_ACCESS_FAILURE: Final = "the backoff record could not be reached"


class _FakeSession:
    """The one session the launches read, the recorder and the backoff
    record share.

    Transcribed from `test_launch_journal_containment.py`: a failed
    statement poisons it, and every later use raises until `rollback()`
    is called. An implementation that catches the backoff access's
    exception but never restores the session leaves every later
    `record_outcome` in the pass failing -- which is the fault
    `c8bca97` fixed at the `clickup-sync` precedent and `design.md`
    Decision 5 says lands worse here.
    """

    def __init__(self) -> None:
        self.poisoned = False
        self.rollbacks = 0
        self.rollback_error: BaseException | None = None

    def use(self, what: str) -> None:
        if self.poisoned:
            raise PendingRollbackError(
                f"{what} attempted on a session poisoned by a failed backoff "
                "access; the transaction must be rolled back first"
            )

    def fail(self, what: str) -> None:
        self.use(what)
        self.poisoned = True
        raise RuntimeError(f"{_ACCESS_FAILURE}: {what}")

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error
        self.poisoned = False

    async def commit(self) -> None:
        self.use("a commit")

    async def flush(self) -> None:
        self.use("a flush")

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# The backoff record
# ---------------------------------------------------------------------------


@dataclass
class _BackoffRow:
    """One row per (launch, step), per `design.md` Decisions 3 and 4."""

    product_id: ProductId
    step_id: str
    noted_kind: _Kind
    noted_at: datetime
    reported_at: datetime | None = None

    # Attribute spellings an implementation might read it under. Nothing
    # in the artifacts fixes these, so the row answers to all of them.
    @property
    def outcome_kind(self) -> _Kind:
        return self.noted_kind

    @property
    def outcome(self) -> _Kind:
        return self.noted_kind

    @property
    def kind(self) -> _Kind:
        return self.noted_kind

    @property
    def noted_outcome(self) -> _Kind:
        return self.noted_kind

    @property
    def when(self) -> datetime:
        return self.noted_at

    @property
    def reported(self) -> datetime | None:
        return self.reported_at

    @property
    def has_been_reported(self) -> bool:
        return self.reported_at is not None


def _as_product(value: Any) -> ProductId | None:
    if isinstance(value, ProductId):
        return value
    if isinstance(value, Launch):
        return value.product_id
    product_id = getattr(value, "product_id", None)
    if isinstance(product_id, ProductId):
        return product_id
    return None


def _as_step(value: Any) -> str | None:
    if isinstance(value, StepDefinition):
        return value.identifier
    if isinstance(value, str):
        return value
    identifier = getattr(value, "identifier", None)
    if isinstance(identifier, str):
        return identifier
    return None


@dataclass
class _Identified:
    product_id: ProductId | None = None
    step_id: str | None = None
    kind: _Kind | None = None
    when: datetime | None = None
    reported: datetime | bool | None = None


def _identify(args: tuple[Any, ...], kwargs: dict[str, Any]) -> _Identified:
    """Recover what an accessor was called about, whatever its call shape.

    Keyword names are read first where they say what they carry, then
    everything left over is classified by type. Nothing here pins the
    accessor's signature -- correcting this function is a fixture
    correction.
    """
    found = _Identified()
    leftovers: list[Any] = list(args)
    for key, value in kwargs.items():
        lowered = key.lower()
        if "product" in lowered or "launch" in lowered:
            found.product_id = _as_product(value) or found.product_id
        elif "step" in lowered:
            found.step_id = _as_step(value) or found.step_id
        elif "report" in lowered:
            found.reported = value
        elif "outcome" in lowered or "kind" in lowered:
            found.kind = _Kind(value)
        elif isinstance(value, datetime):
            found.when = value
        else:
            leftovers.append(value)
    for value in leftovers:
        if found.product_id is None and _as_product(value) is not None:
            found.product_id = _as_product(value)
        elif isinstance(value, datetime) and found.when is None:
            found.when = value
        elif found.step_id is None and _as_step(value) is not None:
            found.step_id = _as_step(value)
        elif found.kind is None and value is not None:
            found.kind = _Kind(value)
    return found


class _BackoffStore:
    """The record the repeat and the report suppression are kept in.

    Deliberately naive: `note` writes the kind and the moment and leaves
    `reported_at` exactly as it found it -- see this file's docstring for
    why the fake must not do the pass's lazy lift for it.
    """

    def __init__(self, session: _FakeSession, *, now: datetime = NOW) -> None:
        self.session = session
        self.now = now
        self.rows: dict[tuple[str, str], _BackoffRow] = {}
        self.reads: list[tuple[Any, Any]] = []
        self.notes: list[_Identified] = []
        self.reports: list[_Identified] = []
        self.fail_read: BaseException | None = None
        self.fail_note: BaseException | None = None
        self.fail_report: BaseException | None = None
        self.fail_first_access = False
        self.inferred_noted_at = False

    # -- seeding, used by the tests themselves ----------------------------

    def seed(
        self,
        *,
        outcome: Any,
        noted_at: datetime,
        reported_at: datetime | None = None,
        product_id: ProductId = PRODUCT_ID,
        step_id: str = AUTOMATED_STEP_ID,
    ) -> _BackoffRow:
        row = _BackoffRow(
            product_id=product_id,
            step_id=step_id,
            noted_kind=_Kind(outcome),
            noted_at=noted_at,
            reported_at=reported_at,
        )
        self.rows[(product_id.value, step_id)] = row
        return row

    def row_for(
        self, product_id: ProductId = PRODUCT_ID, step_id: str = AUTOMATED_STEP_ID
    ) -> _BackoffRow | None:
        return self.rows.get((product_id.value, step_id))

    # -- the accessors -----------------------------------------------------

    def _keys(self, what: str, found: _Identified) -> tuple[str, str]:
        assert found.product_id is not None and found.step_id is not None, (
            f"{what} was called without anything this fake could read as a "
            f"launch and a step: {found!r}. Correct `_identify` to the "
            "implemented call shape -- a fixture correction, not a change "
            "to what is asserted."
        )
        return (found.product_id.value, found.step_id)

    def _guard(self, what: str, configured: BaseException | None) -> None:
        self.session.use(what)
        if self.fail_first_access:
            self.fail_first_access = False
            self.session.fail(what)
        if configured is not None:
            self.session.poisoned = True
            raise configured

    async def read(self, *args: Any, **kwargs: Any) -> _BackoffRow | None:
        found = _identify(args, kwargs)
        self.reads.append((found.product_id, found.step_id))
        self._guard("a backoff read", self.fail_read)
        return self.rows.get(self._keys("a backoff read", found))

    async def note(self, *args: Any, **kwargs: Any) -> None:
        found = _identify(args, kwargs)
        self.notes.append(found)
        self._guard("a backoff write", self.fail_note)
        key = self._keys("a backoff write", found)
        when = found.when
        if when is None:
            when = self.now
            self.inferred_noted_at = True
        existing = self.rows.get(key)
        kind = found.kind if found.kind is not None else _Kind(NotStarted)
        if existing is None:
            self.rows[key] = _BackoffRow(
                product_id=ProductId(key[0]),
                step_id=key[1],
                noted_kind=kind,
                noted_at=when,
            )
        else:
            # Naive on purpose: the stamp is left exactly as it was.
            existing.noted_kind = kind
            existing.noted_at = when
        if found.reported is not None:
            self.rows[key].reported_at = (
                found.reported if isinstance(found.reported, datetime) else when
            )

    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        found = _identify(args, kwargs)
        self.reports.append(found)
        self._guard("a backoff report stamp", self.fail_report)
        key = self._keys("a backoff report stamp", found)
        row = self.rows.get(key)
        when = found.when or self.now
        if row is None:
            self.rows[key] = _BackoffRow(
                product_id=ProductId(key[0]),
                step_id=key[1],
                noted_kind=found.kind or _Kind(NotStarted),
                noted_at=when,
                reported_at=when,
            )
        else:
            row.reported_at = when

    async def rollback(self) -> None:
        await self.session.rollback()

    # Spellings the pass might reach each accessor under.
    get = read
    read_for = read
    for_step = read
    current = read
    note_repeat = note
    record_repeat = note
    upsert = note
    save = note
    record = note
    record_reported = mark_reported
    mark_report_delivered = mark_reported
    note_reported = mark_reported
    restore = rollback
    restore_after_store_fault = rollback

    @property
    def used(self) -> bool:
        return bool(self.reads or self.notes or self.reports)


# ---------------------------------------------------------------------------
# The monitoring notifier
# ---------------------------------------------------------------------------


class _DeliveryRefused(RuntimeError):
    """What the monitoring notifier raises when Slack cannot be reached."""


class _FakeNotifier:
    """A `ThreadReplyNotifier` (`launch.application.ports`), satisfied
    structurally. Originally transcribed from
    `test_clickup_field_configuration_check.py` as a `MonitoringNotifier`
    double tolerant of either call shape; narrowed to the one shape the pass
    actually calls this collaborator under once `worker.py` started
    injecting `launch`'s own notifier here instead of `briefing`'s
    (`fix-stuck-step-report-notifier`) -- the dual tolerance was exactly
    what let that mismatch ship unnoticed."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self.attempts: list[str] = []
        self.refuse = False

    async def post_monitoring_message(
        self, *, channel: str, text: str, thread_ts: str | None = None
    ) -> None:
        self.attempts.append(text)
        if self.refuse:
            raise _DeliveryRefused("Slack refused the message")
        self.messages.append(text)


# ---------------------------------------------------------------------------
# The remaining collaborators
# ---------------------------------------------------------------------------


class _FakeCatalog:
    """**Kept local**: answers a second product for `OTHER_PRODUCT_ID`, so its
    behaviour is conditional on the identifier and a single-product reader
    cannot reproduce it. The equality proof reported 2 value mismatches over
    34 calls (`share-the-aggregate-fakes`, task 3.4b).
    """

    def __init__(self) -> None:
        self.reads: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.reads.append(product_id)
        if product_id == OTHER_PRODUCT_ID:
            return _CatalogProduct(name=OTHER_PRODUCT_NAME, sku=OTHER_PRODUCT_SKU)
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


class _SessionBoundLaunches:
    """`list_active` over the shared session, so a poisoned session breaks
    a read exactly as a real one would."""

    def __init__(self, session: _FakeSession, *launches: Launch) -> None:
        self.session = session
        self._launches = list(launches)

    async def list_active(self) -> list[Launch]:
        self.session.use("a launch enumeration")
        return list(self._launches)

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        self.session.use("a launch read")
        for launch in self._launches:
            if launch.product_id == product_id:
                return launch
        return None


class _ScriptedHandler:
    """A registered handler returning scripted resolutions in order.

    The last one stands for every further invocation, so a two-pass test
    scripts two wordings and a many-pass test scripts one.
    """

    def __init__(self, *resolutions: StepResolution) -> None:
        assert resolutions, "a scripted handler needs at least one resolution"
        self._resolutions = list(resolutions)
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        if len(self._resolutions) > 1:
            return self._resolutions.pop(0)
        return self._resolutions[0]

    @property
    def invoked(self) -> bool:
        return bool(self.contexts)

    @property
    def invocations(self) -> int:
        return len(self.contexts)


class _FakeResults:
    """In-memory stand-in for `AutomatedResultRepository`, transcribed from
    `test_automation_pass.py` and trimmed to what this file drives."""

    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []

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

    async def store(self, **kwargs: Any) -> _PendingRow:
        row = _PendingRow(**kwargs)
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: Any, when: datetime | None = None) -> None:
        row.delivered_at = when or NOW

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        rejected = [
            row
            for row in self.rows
            if row.product_id == product_id
            and row.step_id == step_id
            and row.state == "rejected"
        ]
        if not rejected:
            return None
        return max(rejected, key=lambda row: row.decided_at or row.produced_at)

    def seed_rejection(
        self, *, decided_at: datetime, product_id: ProductId = PRODUCT_ID
    ) -> _PendingRow:
        row = _PendingRow(
            product_id=product_id,
            step_id=AUTOMATED_STEP_ID,
            handler=HANDLER_NAME,
            proposed_outcome=Satisfied,
            result_text=_produced(FIRST_WORDING),
            produced_at=decided_at - timedelta(minutes=5),
            state="rejected",
            delivered_at=decided_at - timedelta(minutes=4),
            decided_by=ALICE,
            decided_at=decided_at,
        )
        self.rows.append(row)
        return row


class _RecordingOutcomes:
    """Stands in for `record_step_outcome`, and **actually records**.

    The existing `test_automation_pass.py` collects the keywords and
    leaves the launch untouched, which is enough for a one-pass test. It
    is not enough here: every scenario below turns on what the step
    *carries* on the pass after, and a recorder that never writes would
    make the repeat undetectable by construction -- and several tests
    green for the wrong reason.

    Session-bound, so a poisoned session breaks a recording exactly as a
    real one would.
    """

    def __init__(
        self,
        session: _FakeSession,
        playbook: LaunchPlaybook,
        launches: tuple[Launch, ...],
    ) -> None:
        self.session = session
        self._playbook = playbook
        self._launches = {launch.product_id: launch for launch in launches}
        self.calls: list[dict[str, Any]] = []
        self.failures: list[BaseException] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        try:
            self.session.use("recording a step outcome")
        except BaseException as error:
            self.failures.append(error)
            raise
        product_id = kwargs.get("product_id")
        if product_id is None:
            product_id = next(
                (found for found in map(_as_product, args) if found is not None),
                None,
            )
        assert product_id in self._launches, (
            f"the recorder was called for {product_id!r}, which is not one of "
            f"{list(self._launches)}; correct this fixture to the implemented "
            "call shape"
        )
        self._launches[product_id].record_step_outcome(
            self._playbook,
            step_id=kwargs["step_id"],
            outcome=kwargs["outcome"],
            provenance=kwargs["provenance"],
        )
        self.calls.append(kwargs)
        return ()

    def for_step(
        self, step_id: str, product_id: ProductId | None = None
    ) -> list[dict[str, Any]]:
        return [
            call
            for call in self.calls
            if call.get("step_id") == step_id
            and (product_id is None or call.get("product_id") == product_id)
        ]


class _FakeDelivery:
    """The pending-result delivery seam -- untouched by this change, and
    present only so the pass has one."""

    def __init__(self) -> None:
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)


# ---------------------------------------------------------------------------
# The world, and the pass reached through one correction point
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)

_BACKOFF_ARGUMENT_NAMES: Final = (
    "backoff",
    "backoffs",
    "backoff_record",
    "backoff_records",
    "backoff_store",
    "repeats",
    "repeat_backoff",
    "step_backoff",
    "suppression",
)


class _EstablishesThread:
    """`launch_thread_delivery.establish_thread_and_resolve_mention`, as a port.

    The pass takes this as an injected collaborator (`automation_pass.py`'s
    own docstring: "threaded as an argument like every other collaborator
    here, not a module global, which is what lets this pass be exercised
    without a database"), so the stand-in is supplied through `_run_pass`
    like the rest rather than monkeypatched.

    **Returns no mention, deliberately.** `_report_stuck_step` builds
    `mention_tag = f" <@{mention}>" if mention else ""`, so a `None` mention
    leaves every reported message's text exactly as it was before this
    collaborator existed -- which is what lets this file's report assertions
    stand unchanged. A double returning an identity would prepend a tag and
    force them to be edited, which this change forbids.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[str, str | None]:
        self.calls.append({"args": args, "kwargs": kwargs})
        return (THREAD_TS, None)


_THREAD_ARGUMENT_NAMES: Final = (
    "establish_thread",
    "establish_thread_and_resolve_mention",
    "thread",
    "ensure_thread",
)

_REPORT_ARGUMENT_NAMES: Final = (
    "notifier",
    "monitoring_notifier",
    "notify",
    "report",
    "report_stuck_step",
    "deliver_report",
    "monitoring",
)


def _pass_entry() -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(automation_pass, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {automation_pass.__name__} under any "
        f"of {_ENTRY_NAMES} -- correct this file's probe to the implemented "
        "name"
    )


def _accepted_parameters() -> set[str]:
    return set(inspect.signature(_pass_entry()).parameters)


def _argument_for(candidates: tuple[str, ...]) -> str | None:
    accepted = _accepted_parameters()
    return next((name for name in candidates if name in accepted), None)


_LIVE_SESSIONS: Final[list[_FakeSession]] = []
"""The session the current test's world shares, for the module's session
provider to hand back. See `_restorable_session`."""


@dataclass
class _World:
    session: _FakeSession
    playbook: LaunchPlaybook
    launches: _SessionBoundLaunches
    handlers: _FakeHandlers
    handler: _ScriptedHandler
    results: _FakeResults
    recorder: _RecordingOutcomes
    catalog: _FakeCatalog
    delivery: _FakeDelivery
    store: _BackoffStore
    notifier: _FakeNotifier
    launch: Launch
    thread: _EstablishesThread = field(default_factory=lambda: _EstablishesThread())
    other_launch: Launch | None = None
    extra_handlers: dict[str, _ScriptedHandler] = field(default_factory=dict)

    @property
    def messages(self) -> list[str]:
        return self.notifier.messages


def _world(
    *steps: StepDefinition,
    handler: _ScriptedHandler | None = None,
    extra: dict[str, _ScriptedHandler] | None = None,
    carrying: Any | None = None,
    carrying_who: str = HANDLER_NAME,
    second_launch: bool = False,
) -> _World:
    session = _FakeSession()
    _LIVE_SESSIONS.clear()
    _LIVE_SESSIONS.append(session)
    playbook = _playbook(*(steps or (_automated(),)))
    launch = _launch(playbook)
    if carrying is not None:
        _carrying(launch, playbook, carrying, who=carrying_who)
    others: tuple[Launch, ...] = ()
    other_launch: Launch | None = None
    if second_launch:
        other_launch = _launch(playbook, product_id=OTHER_PRODUCT_ID)
        others = (other_launch,)
    the_handler = handler or _ScriptedHandler(
        StepResolution(outcome=Blocked(FIRST_WORDING), result=_produced(FIRST_WORDING))
    )
    registry: dict[str, Any] = {HANDLER_NAME: the_handler}
    registry.update(extra or {})
    return _World(
        session=session,
        playbook=playbook,
        launches=_SessionBoundLaunches(session, launch, *others),
        handlers=_FakeHandlers(**registry),
        handler=the_handler,
        results=_FakeResults(),
        recorder=_RecordingOutcomes(session, playbook, (launch, *others)),
        catalog=_FakeCatalog(),
        delivery=_FakeDelivery(),
        store=_BackoffStore(session),
        notifier=_FakeNotifier(),
        launch=launch,
        other_launch=other_launch,
        extra_handlers=extra or {},
    )


async def _run_pass(world: _World, *, now: datetime = NOW) -> Any:
    """INVENTED call shape -- the single correction point.

    The two collaborators this change adds are supplied only where the
    entry point accepts them, so that a pass that does not yet take them
    still *runs* and each test fails on its own behavioural assertion
    rather than on a `TypeError` in the harness (`tasks.md` 1.3).
    """
    entry = _pass_entry()
    world.store.now = now
    supplied: dict[str, Any] = {
        "launches": world.launches,
        "playbook": world.playbook,
        "handlers": world.handlers,
        "results": world.results,
        "record_outcome": world.recorder,
        "read_product": world.catalog,
        "deliver": world.delivery,
        "now": now,
    }
    accepted = _accepted_parameters()
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct `_run_pass` "
        "to the implemented collaborator names"
    )
    backoff_argument = _argument_for(_BACKOFF_ARGUMENT_NAMES)
    if backoff_argument is not None:
        supplied[backoff_argument] = world.store
    report_argument = _argument_for(_REPORT_ARGUMENT_NAMES)
    if report_argument is not None:
        supplied[report_argument] = world.notifier
    thread_argument = _argument_for(_THREAD_ARGUMENT_NAMES)
    if thread_argument is not None:
        supplied[thread_argument] = world.thread
    return await entry(**supplied)


@pytest.fixture(autouse=True)
def _launches_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """The channel the stuck-step report is posted to.

    `_report_stuck_step` calls `launches_channel()`, which reads this
    variable from the environment directly rather than taking it as a port.
    Unset, it raises `KeyError` inside that function's own `try`, the report
    is swallowed into a warning, and the report tests fail on an empty
    `world.messages` with nothing naming the cause. Set here the way three
    sibling files in this directory already set it.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)


@pytest.fixture(autouse=True)
def _restorable_session(monkeypatch: pytest.MonkeyPatch) -> Any:
    """`automation_pass.session` yields **the world's own** fake session.

    Two routes reach the same restore, because nothing fixes which one an
    implementation takes: the backoff store's `rollback()`, and the
    module's session provider. `_LIVE_SESSIONS` is what lets the provider
    hand back the session `_world()` built, which everything else in the
    test shares.
    """

    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> Any:
        if not _LIVE_SESSIONS:
            _LIVE_SESSIONS.append(_FakeSession())
        yield _LIVE_SESSIONS[-1]

    if hasattr(automation_pass, "session"):
        monkeypatch.setattr(automation_pass, "session", _provider)
    yield
    _LIVE_SESSIONS.clear()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _require_backoff_reached(world: _World) -> None:
    """Guards the assertions the pass already satisfies without this change.

    Where the pass never consulted the backoff record, "the handler was
    invoked" says nothing about the rule under test -- it is what the
    pass does unconditionally today. Failing here rather than passing
    green is `ai-toolkit:testing`'s fourth failure state, refused.
    """
    assert world.store.used, (
        "the pass never touched the backoff record. This file supplies it as "
        f"whichever of {list(_BACKOFF_ARGUMENT_NAMES)} the entry point "
        "accepts, per `tasks.md` 3.1 ('reach `run_automation_pass` as an "
        "argument'). Until it does, this assertion would pass for the "
        "pre-change reason rather than the specified one."
    )


def _reported_text(caplog: pytest.LogCaptureFixture, world: _World) -> str:
    """Everything the pass 'reported', through either channel.

    INVENTED that a *fault* is reported through logging rather than to
    Slack -- the artifacts fix only that it is reported -- so both are
    read and no test here pins the channel.
    """
    logged = " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )
    return " ".join([logged, *world.notifier.attempts])


def _names_the_launch(message: str) -> bool:
    return any(
        token in message
        for token in (PRODUCT_NAME, PRODUCT_SKU.value, PRODUCT_ID.value)
    )


def _names_the_step(message: str, step: StepDefinition) -> bool:
    return step.identifier in message or step.name in message


# ---------------------------------------------------------------------------
# The seam this change adds, stated once
# ---------------------------------------------------------------------------


def test_the_pass_accepts_a_backoff_record_and_a_report_seam() -> None:
    """`tasks.md` 3.1 and 4.2: both new collaborators reach
    `run_automation_pass` **as arguments**, "the way `results` and
    `deliver` already do", so that the pass stays exercisable without a
    database.

    Stated once, here, so that the twenty tests below fail on what they
    assert rather than each repeating this directive.
    """
    accepted = sorted(_accepted_parameters())
    assert _argument_for(_BACKOFF_ARGUMENT_NAMES) is not None, (
        f"the pass accepts {accepted}, none of which is the backoff record "
        f"this change adds. Either name it one of {list(_BACKOFF_ARGUMENT_NAMES)} "
        "or correct that tuple to the implemented name -- a fixture "
        "correction, not a change to what is asserted."
    )
    assert _argument_for(_REPORT_ARGUMENT_NAMES) is not None, (
        f"the pass accepts {accepted}, none of which is the monitoring "
        "notifier the stuck-step report is delivered through (`tasks.md` "
        f"4.2). Either name it one of {list(_REPORT_ARGUMENT_NAMES)} or "
        "correct that tuple to the implemented name."
    )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A non-terminal outcome is recorded directly and
# never held for a decision
# ---------------------------------------------------------------------------


async def test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass_when_the_outcome_differs() -> (
    None
):
    """Scenario (as revised): A step reporting no progress is reconsidered
    on the next pass.

    WHEN a handler proposes a non-terminal outcome that **differs from the
    one the step already carries**, and a later pass runs
    THEN the handler is invoked again for that step.

    The delta narrows this scenario's WHEN; the THEN is unchanged. So this
    test is **expected to pass on its first run**, and that is not
    `ai-toolkit:testing`'s fourth failure state: it states behaviour the
    change must preserve, and its value is as the guard that the cool-off
    did not swallow the progressing case. The complementary negative --
    that a *repeat* is not reconsidered -- is the next test down.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the category tree read is running")
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))

    await _run_pass(world)

    # The premise: the proposal really did differ from what the step carried.
    assert handler.invocations == 1
    recorded = world.launch.progress_for(AUTOMATED_STEP_ID)
    assert recorded is not None and recorded.outcome is InProgress

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the handler is invoked again for that step.
    assert handler.invocations == 2, (
        "a changed non-terminal outcome must leave the step on the "
        "fifteen-minute cadence"
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A handler that repeats itself is not asked again
# immediately
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("carried", "proposed", "produced"),
    [
        pytest.param(
            Blocked(FIRST_WORDING),
            Blocked(FIRST_WORDING),
            _produced(FIRST_WORDING),
            id="blocked",
        ),
        pytest.param(
            InProgress,
            InProgress,
            "the category tree read is still running",
            id="in-progress",
        ),
        pytest.param(
            NotStarted,
            NotStarted,
            "nothing has begun on this node choice yet",
            id="not-started",
        ),
    ],
)
async def test_a_repeated_non_terminal_outcome_is_recorded_and_cools_the_step_off(
    carried: Any, proposed: Any, produced: str
) -> None:
    """Scenario: A repeated non-terminal outcome is recorded and cools the
    step off.

    WHEN a handler proposes the non-terminal outcome the step already
    carries
    THEN the outcome is recorded against the launch, and the step's
    handler is not invoked on the next pass.

    Parametrised over all three non-terminal outcomes because the
    requirement is stated over "a non-terminal outcome ... of the same
    kind", not over `Blocked`; two of the three carry no reason at all,
    and an implementation reaching for `.reason` treats them differently.
    """
    handler = _ScriptedHandler(StepResolution(outcome=proposed, result=produced))
    world = _world(_automated(), handler=handler, carrying=carried)

    await _run_pass(world)

    # SPECIFIED: the outcome is recorded against the launch. Recording is
    # not suspended by the backoff -- only re-invocation is.
    calls = world.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1, f"the repeated outcome was not recorded: {calls}"
    assert calls[0]["provenance"].source == "automated"

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the handler is not invoked on the next pass.
    assert handler.invocations == 1, (
        "the handler was asked again on the next pass after repeating "
        f"{proposed!r}; the repeat must cool the step off"
    )


async def test_a_differently_worded_repeat_still_counts_as_a_repeat() -> None:
    """Scenario: A differently worded repeat still counts as a repeat.

    WHEN a handler proposes `Blocked` with a reason worded differently
    from the reason recorded on the step, which is also `Blocked`
    THEN it is treated as a repeat, and the step's handler is not invoked
    on the next pass.

    **The load-bearing test of this change** (`design.md` Decision 2;
    `tasks.md` 1.2). The two wordings are the two `proposal.md` quotes
    from the deployment's own journal. `Blocked` is a frozen dataclass
    whose equality includes `reason`, so an implementation comparing
    outcomes with `==` finds these two unequal, cools nothing off, and
    looks implemented while changing nothing -- which is exactly what
    this test refuses.
    """
    assert Blocked(FIRST_WORDING) != Blocked(SECOND_WORDING), (
        "the premise of this test: the two proposals are unequal as values "
        "and identical in kind"
    )

    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))

    await _run_pass(world)

    # The premise: the differently worded block really was recorded.
    recorded = world.launch.progress_for(AUTOMATED_STEP_ID)
    assert recorded is not None
    assert isinstance(recorded.outcome, Blocked)
    assert recorded.outcome.reason == SECOND_WORDING

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: it is treated as a repeat.
    assert handler.invocations == 1, (
        "the handler was asked again after re-blocking in different words. "
        "Sameness is the outcome *kind*, never the reason text "
        "(`design.md` Decision 2)."
    )


async def test_a_first_non_terminal_outcome_does_not_cool_the_step_off() -> None:
    """Scenario: A first non-terminal outcome does not cool the step off.

    WHEN a handler proposes a non-terminal outcome for a step carrying no
    recorded outcome
    THEN the outcome is recorded and the handler is invoked again on the
    next pass.

    `tasks.md` 1.2's second trap: a test that only checks "it eventually
    stops calling" passes against an implementation that backs off on the
    *first* non-terminal outcome -- the behaviour this change explicitly
    refused, because it would slow every legitimately-polling handler from
    four checks an hour to one. The third pass below is the positive
    control in the same test: it establishes that this harness *can*
    observe a cool-off, so the second assertion is not green merely
    because nothing ever backs off.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked(FIRST_WORDING), result=_produced(FIRST_WORDING))
    )
    world = _world(_automated(), handler=handler)
    assert world.launch.progress_for(AUTOMATED_STEP_ID) is None

    await _run_pass(world)

    # SPECIFIED: the outcome is recorded.
    assert len(world.recorder.for_step(AUTOMATED_STEP_ID)) == 1

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the handler is invoked again on the next pass. One
    # further invocation is what distinguishes a stuck step from a
    # progressing one, and this change deliberately pays for it.
    assert handler.invocations == 2, (
        "the handler was not asked a second time. A repeat is established "
        "from two recordings, never predicted from one (`design.md` "
        "Decision 1)."
    )

    # The control: the second recording *is* a repeat, so the third pass
    # must find the step cooled off.
    await _run_pass(world, now=NOW + 2 * PASS_INTERVAL)
    assert handler.invocations == 2, (
        "the second, repeating recording did not cool the step off, so the "
        "assertion above proves nothing about when the backoff engages"
    )


async def test_a_changed_outcome_lifts_the_cool_off() -> None:
    """Scenario: A changed outcome lifts the cool-off.

    WHEN a handler that had repeated itself is invoked after the cool-off
    elapses and proposes a different non-terminal outcome
    THEN the outcome is recorded and the handler is invoked again on the
    next pass.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the category tree read resumed")
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    world.store.seed(
        outcome=Blocked(FIRST_WORDING),
        noted_at=NOW - REPEAT_COOL_OFF - timedelta(minutes=1),
        reported_at=NOW - REPEAT_COOL_OFF - timedelta(minutes=1),
    )

    await _run_pass(world)
    _require_backoff_reached(world)

    # The premise: the cool-off had elapsed, so the handler ran and said
    # something different.
    assert handler.invocations == 1
    recorded = world.launch.progress_for(AUTOMATED_STEP_ID)
    assert recorded is not None and recorded.outcome is InProgress

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the handler is invoked again on the next pass -- the row
    # noted against `Blocked` governs nothing once the step carries
    # something else.
    assert handler.invocations == 2


async def test_a_repeated_step_is_asked_again_once_the_cool_off_elapses() -> None:
    """Scenario: A repeated step is asked again once the cool-off elapses.

    WHEN a pass runs after the cool-off has elapsed since a step's handler
    repeated itself
    THEN that step's handler is invoked again.

    Both sides of the window in one test: a pass a minute *inside* it must
    not invoke, and a pass a minute outside must. A test that only ran the
    second half would pass against a pass that never backs off at all.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked(FIRST_WORDING), result=_produced(FIRST_WORDING))
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    noted_at = NOW - REPEAT_COOL_OFF + timedelta(minutes=1)
    world.store.seed(outcome=Blocked(FIRST_WORDING), noted_at=noted_at)

    await _run_pass(world)
    _require_backoff_reached(world)

    # SPECIFIED (the suppressing half): still inside the cool-off.
    assert handler.invocations == 0

    await _run_pass(world, now=noted_at + REPEAT_COOL_OFF + timedelta(minutes=1))

    # SPECIFIED: once the cool-off has elapsed, the handler is invoked again.
    assert handler.invocations == 1


async def test_a_cool_off_is_anchored_to_the_repeat_that_caused_it() -> None:
    """Scenario: A cool-off is anchored to the repeat that caused it.

    WHEN a step's handler repeats itself again after an earlier cool-off
    has elapsed
    THEN the step is cooled off again, measured from the later repeat.

    The anchor is what `design.md` settles as a stored `noted_at` rather
    than the recorded provenance's `when`: a clock read from the
    provenance would restart on every recording, including the one that
    notes the repeat, and would never elapse. Here the reverse failure is
    what is caught -- an anchor left at the *earlier* repeat leaves the
    step immediately eligible again.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    earlier = NOW - REPEAT_COOL_OFF - timedelta(minutes=1)
    world.store.seed(
        outcome=Blocked(FIRST_WORDING), noted_at=earlier, reported_at=earlier
    )

    await _run_pass(world)
    _require_backoff_reached(world)

    # The premise: the elapsed cool-off let the handler run, and it
    # repeated itself.
    assert handler.invocations == 1

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: cooled off again, measured from the later repeat -- a
    # pass fifteen minutes after it must not invoke.
    assert handler.invocations == 1, (
        "the step was asked again fifteen minutes after repeating itself; "
        "the cool-off must be measured from the later repeat, not from the "
        "earlier one"
    )


async def test_a_cool_off_stops_governing_once_the_outcome_differs_from_it() -> None:
    """Scenario: A cool-off stops governing once the outcome differs from
    it.

    WHEN a step cooled off against one non-terminal outcome has a
    different outcome recorded against it **by something other than a
    pass**
    THEN the step is eligible for invocation on the next pass.

    The lazy lift (`design.md` Decision 4): nothing actively lifts the
    row, so `automation_confirmation` -- which records for these same
    steps and which this change leaves untouched -- owes nothing. Here the
    launch carries an `InProgress` a member recorded while the row still
    says `Blocked`, well inside the cool-off; an implementation reading
    only `noted_at` skips the step.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="a member restarted the read")
    )
    world = _world(
        _automated(),
        handler=handler,
        carrying=InProgress,
        carrying_who=ALICE,
    )
    world.store.seed(
        outcome=Blocked(FIRST_WORDING),
        noted_at=NOW - timedelta(hours=1),
        reported_at=NOW - timedelta(hours=1),
    )

    await _run_pass(world)
    _require_backoff_reached(world)

    # SPECIFIED: the step is eligible for invocation.
    assert handler.invoked, (
        "a row noted against `Blocked` still suppressed a step now carrying "
        "`InProgress`; a cool-off ceases to govern as soon as the recorded "
        "outcome is no longer of the kind it was noted against"
    )


async def test_the_rejection_cool_off_does_not_govern_a_repeat() -> None:
    """Scenario: The rejection cool-off does not govern a repeat.

    WHEN a step's handler has repeated a non-terminal outcome and no
    rejection stands against that step
    THEN the step is cooled off by the repeat alone.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))

    # The premise: nothing was ever rejected for this step, so the
    # rejection cool-off cannot be what suppresses anything below.
    assert await world.results.latest_rejection(PRODUCT_ID, AUTOMATED_STEP_ID) is None

    await _run_pass(world)
    assert handler.invocations == 1

    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the step is cooled off by the repeat alone.
    assert handler.invocations == 1, (
        "the handler was asked again although it had just repeated itself. "
        "No rejection stands against this step, so nothing but the repeat "
        "could have cooled it off -- and something must have."
    )


@pytest.mark.parametrize(
    ("rejection_cool_off", "noted_ago", "expected_invocations", "why"),
    [
        pytest.param(
            timedelta(0),
            timedelta(hours=1),
            0,
            "a rejection cool-off of zero must not release a repeat that is "
            "an hour old",
            id="shortened-rejection-cool-off-does-not-release-a-repeat",
        ),
        pytest.param(
            timedelta(days=90),
            REPEAT_COOL_OFF + timedelta(minutes=1),
            1,
            "a rejection cool-off of ninety days must not hold a repeat "
            "whose own cool-off has elapsed",
            id="lengthened-rejection-cool-off-does-not-hold-a-repeat",
        ),
    ],
)
async def test_the_repeat_cool_off_is_independent_of_the_rejection_cool_off(
    monkeypatch: pytest.MonkeyPatch,
    rejection_cool_off: timedelta,
    noted_ago: timedelta,
    expected_invocations: int,
    why: str,
) -> None:
    """Requirement statement: the cool-off "SHALL be independent of the
    cool-off placed after a rejection ... a step that has repeated itself
    SHALL NOT be affected by a change to the rejection cool-off".

    Carried by no scenario, and `design.md` Decision 6 is explicit that
    the two must not share a constant: "a future change to one silently
    moves the other". Moving `COOL_OFF` and finding the repeat unmoved is
    the only way to observe that from outside.

    Both directions, because an implementation that reused `COOL_OFF`
    fails only one of them depending on which way it was moved.
    """
    monkeypatch.setattr(automation_pass, "COOL_OFF", rejection_cool_off)

    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked(FIRST_WORDING), result=_produced(FIRST_WORDING))
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    world.store.seed(outcome=Blocked(FIRST_WORDING), noted_at=NOW - noted_ago)

    await _run_pass(world)
    _require_backoff_reached(world)

    assert handler.invocations == expected_invocations, why


def test_the_repeat_cool_off_is_a_fixed_constant_of_its_own() -> None:
    """Requirement statement: "The cool-off SHALL be a fixed property of
    the system rather than a configured one, and SHALL be independent of
    the cool-off placed after a rejection"; `tasks.md` 3.2 makes that a
    module constant distinct from `COOL_OFF`, "exported the way `COOL_OFF`
    is".

    The behavioural half is the test above. This is the structural half:
    that the two figures are two names, so that moving one cannot move the
    other by construction. DERIVED that 24 hours is the value.
    """
    constants = {
        name: value
        for name, value in vars(automation_pass).items()
        if isinstance(value, timedelta) and name.isupper() and name != "COOL_OFF"
    }
    repeat = [name for name, value in constants.items() if value == REPEAT_COOL_OFF]
    assert repeat, (
        f"{automation_pass.__name__} exposes no 24-hour constant other than "
        f"`COOL_OFF` (it has {sorted(constants)}). The repeat's cool-off is "
        "its own constant, not a reuse of the rejection one (`design.md` "
        "Decision 6)."
    )


async def test_a_step_whose_backoff_record_cannot_be_read_is_still_invoked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A step whose backoff record cannot be read is still
    invoked.

    WHEN a pass cannot read whether a step is cooled off
    THEN the step's handler is invoked, the failure is reported, and the
    pass continues.

    **One half of the split degrade** (`design.md` Decision 5):
    *invocation* degrades toward running, because a fault in a cost
    optimisation must never be the reason a step goes unresolved. The
    other half -- that no report is delivered on such a pass -- is a
    separate test, deliberately, since a single test asserting one half
    passes against an implementation that applied one default to both.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    # Seeded so that a *readable* row would have cooled the step off: the
    # degrade has to be observed against a state that otherwise suppresses.
    world.store.seed(outcome=Blocked(FIRST_WORDING), noted_at=NOW - timedelta(hours=1))
    world.store.fail_read = RuntimeError(_ACCESS_FAILURE)

    with caplog.at_level(logging.DEBUG):
        await _run_pass(world)

    _require_backoff_reached(world)

    # SPECIFIED: the step's handler is invoked -- as it would have been
    # before this requirement existed.
    assert handler.invoked, (
        "a failed backoff read left the step uninvoked; invocation degrades "
        "toward running, never toward silence"
    )
    # SPECIFIED: the failure is reported.
    reported = _reported_text(caplog, world)
    assert reported.strip(), "the backoff access failure was not reported anywhere"
    assert AUTOMATED_STEP_ID in reported or _ACCESS_FAILURE in reported, (
        f"the report names neither the step nor the failure: {reported!r}"
    )
    # SPECIFIED: the pass continues -- and the step's own outcome is
    # still recorded, which a poisoned session would have prevented.
    assert len(world.recorder.for_step(AUTOMATED_STEP_ID)) == 1


async def test_a_failed_backoff_access_does_not_cost_the_pass_its_other_work(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed backoff access does not cost the pass its other
    work.

    WHEN reading or writing the backoff record fails for one step
    THEN the remaining steps and launches are still walked and their
    recorded outcomes are still persisted.

    `tasks.md` 1.2's fourth trap. The store here does not merely raise: it
    **poisons the shared session**, which is the state a failed statement
    really leaves an `AsyncSession` in, so an implementation that catches
    the exception without restoring the store leaves every later
    `record_outcome` in the pass raising -- writing nothing while the run
    reports success. That is `c8bca97`'s fault, in the worse place
    `design.md` Decision 5 describes.

    The fault is armed on the *first* access rather than for a named step,
    so the test does not depend on the order the walk happens to take: two
    steps and one further launch remain whichever step goes first.
    """
    first = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the sub-category read is running")
    )
    second = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the bullet draft is running")
    )
    world = _world(
        _automated(),
        _second_automated(),
        handler=first,
        extra={SECOND_HANDLER_NAME: second},
        second_launch=True,
    )
    world.store.fail_first_access = True

    with caplog.at_level(logging.DEBUG):
        await _run_pass(world)

    _require_backoff_reached(world)

    # The premise: the session really was poisoned, and really was left
    # usable again -- either through the store's own restore or through
    # the module's session provider.
    assert world.session.poisoned is False, (
        "the shared session is still poisoned when the pass returned. A "
        "failed backoff access must restore the store before the walk "
        "continues (`design.md` Decision 5); every recording behind it "
        "fails otherwise."
    )

    # SPECIFIED: the remaining steps and launches are still walked, and
    # their recorded outcomes are still persisted. Three (launch, step)
    # pairs exist; at most the one that faulted may be missing.
    persisted = {(call["product_id"], call["step_id"]) for call in world.recorder.calls}
    assert len(persisted) >= 2, (
        "only "
        f"{sorted((str(p), s) for p, s in persisted)} was persisted out of "
        "three (launch, step) pairs; the remaining work must survive one "
        f"step's backoff fault. Recorder rejections: {world.recorder.failures}"
    )
    assert (OTHER_PRODUCT_ID, AUTOMATED_STEP_ID) in persisted, (
        "the second launch's outcome was never persisted; one step's fault "
        "must not starve the launches behind it"
    )
    assert not world.recorder.failures, (
        f"a recording was refused by a poisoned session: {world.recorder.failures}"
    )
    # SPECIFIED: the failure does not fail the pass -- reaching here
    # without an exception is the whole of that.


async def test_a_failed_backoff_write_leaves_the_step_eligible(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Requirement statement: "Where the system cannot read **or write**
    whatever it keeps this judgement in, the step SHALL be left eligible
    for invocation and the failure SHALL be reported".

    Carried by no scenario of its own -- the two scenarios name a read --
    and `design.md` Decision 5 states the write half separately: "a failed
    write leaves the step eligible too, logged; the next pass notices the
    repeat again and re-notes it. One further invocation, not a lost
    guarantee."
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    world.store.fail_note = RuntimeError(_ACCESS_FAILURE)

    with caplog.at_level(logging.DEBUG):
        await _run_pass(world)

    _require_backoff_reached(world)
    assert world.store.notes, "the repeat was never written, so nothing failed here"

    # SPECIFIED: the failure is reported, and does not fail the pass.
    assert _reported_text(caplog, world).strip(), (
        "the failed backoff write was not reported anywhere"
    )

    world.store.fail_note = None
    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the step was left eligible -- the next pass notices the
    # repeat again and re-notes it.
    assert handler.invocations == 2, (
        "a failed write cooled the step off anyway; the degrade is toward "
        "invoking, at the cost of one further call"
    )


async def test_a_restore_that_itself_fails_ends_the_walk_and_fails_the_run() -> None:
    """Requirement statement: "Where the shared store cannot be restored
    to a usable state after such a failure, the pass SHALL end and the run
    SHALL be recorded as failed. A pass that walked on against a store
    that cannot record would persist nothing while reporting success,
    which is worse than stopping."

    Carried by no scenario. "Recorded as failed" is read as *the pass body
    raises* -- the reading `test_clickup_sync_job_containment.py` and
    `test_clickup_field_configuration_check.py` already record for the
    same words, and the only outcome signal a pass body has.
    """
    first = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the sub-category read is running")
    )
    second = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the bullet draft is running")
    )
    world = _world(
        _automated(),
        _second_automated(),
        handler=first,
        extra={SECOND_HANDLER_NAME: second},
        second_launch=True,
    )
    world.store.fail_first_access = True
    world.session.rollback_error = RuntimeError("the restore itself failed")

    ended: BaseException | None = None
    try:
        await _run_pass(world)
    except BaseException as error:  # noqa: BLE001 - the type is unspecified
        ended = error

    # SPECIFIED: the run is recorded as failed. The exception *type* is
    # not specified anywhere, so what is asserted is that the pass did not
    # return normally, and that the restore was what stopped it.
    assert ended is not None, (
        "the pass returned normally after the restore itself failed. A pass "
        "that walks on against a store it cannot restore persists nothing "
        "while reporting success, which is the one outcome worse than "
        "stopping."
    )
    assert world.session.rollbacks >= 1, (
        "no restore was attempted after the contained failure, so this test "
        "is not observing what it claims to"
    )
    assert not isinstance(ended, AssertionError), (
        f"the pass ended on a fixture assertion rather than on the failed "
        f"restore: {ended}"
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A step whose handler has stopped making progress is
# reported once
# ---------------------------------------------------------------------------


async def test_a_newly_cooled_off_step_is_reported() -> None:
    """Scenario: A newly cooled-off step is reported.

    WHEN a handler repeats a non-terminal outcome and the step is cooled
    off for the first time
    THEN a report naming the launch, the step and what the handler
    produced as its result is delivered.

    "What the handler produced as its **result**" is `tasks.md` 4.1's
    wording, explicitly "not 'the outcome's reason'" -- a repeated
    `InProgress` carries no reason at all. `_produced` therefore makes the
    result a superstring of the reason, so an implementation quoting only
    the reason does not satisfy this.
    """
    step = _automated()
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(step, handler=handler, carrying=Blocked(FIRST_WORDING))

    await _run_pass(world)

    assert len(world.messages) == 1, (
        f"expected exactly one report for the newly cooled-off step, got "
        f"{world.messages}"
    )
    message = world.messages[0]
    # SPECIFIED: it names the launch.
    assert _names_the_launch(message), (
        f"the report names neither the product, its SKU nor its identifier: {message!r}"
    )
    # SPECIFIED: it names the step.
    assert _names_the_step(message, step), (
        f"the report names neither the step's identifier nor its name: {message!r}"
    )
    # SPECIFIED: it names what the handler produced as its result.
    assert _produced(SECOND_WORDING) in message, (
        "the report does not carry what the handler produced as its result; "
        f"got {message!r}"
    )


async def test_a_step_that_stays_stuck_is_not_reported_again() -> None:
    """Scenario: A step that stays stuck is not reported again.

    WHEN a later pass runs while the same step is still cooled off with an
    unchanged outcome
    THEN no further report is delivered for it.

    The first pass is the positive control in the same test: without it,
    "no further report" would be green against a pass that never reports
    at all.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))

    await _run_pass(world)
    assert len(world.messages) == 1, (
        "the control failed: the step was never reported in the first place"
    )

    await _run_pass(world, now=NOW + PASS_INTERVAL)
    await _run_pass(world, now=NOW + 2 * PASS_INTERVAL)

    # SPECIFIED: no further report is delivered for it.
    assert len(world.messages) == 1, (
        "a still-stuck step was reported again: "
        f"{world.messages[1:]}. A wall of identical messages trains a team "
        "to ignore the channel."
    )


async def test_a_step_still_stuck_after_the_cool_off_expires_is_not_reported_again() -> (
    None
):
    """Scenario: A step still stuck after the cool-off expires is not
    reported again.

    WHEN the cool-off elapses, the handler is invoked again, and it
    repeats the same non-terminal outcome
    THEN the step is cooled off again and no further report is delivered
    for it.

    The report is lifted by the step **moving**, never by the cool-off
    expiring: a step stuck for a week is one message, not seven. This is
    the assertion `tasks.md` 7.4 says a second report would falsify on the
    deployment itself.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))

    await _run_pass(world)
    assert len(world.messages) == 1, (
        "the control failed: the step was never reported in the first place"
    )

    later = NOW + REPEAT_COOL_OFF + timedelta(minutes=1)
    await _run_pass(world, now=later)

    # The premise: the cool-off really had elapsed and the handler really
    # was asked again.
    assert handler.invocations == 2, (
        "the handler was not re-asked after the cool-off elapsed, so this "
        "test is not observing the situation the scenario names"
    )
    # SPECIFIED: the step is cooled off again ...
    await _run_pass(world, now=later + PASS_INTERVAL)
    assert handler.invocations == 2
    # ... and no further report is delivered for it.
    assert len(world.messages) == 1, (
        f"a second report arrived once the cool-off expired: {world.messages[1:]}"
    )


async def test_a_step_that_gets_stuck_again_after_moving_is_reported_again() -> None:
    """Scenario: A step that gets stuck again after moving is reported
    again.

    WHEN a step that was reported later records a different outcome, and
    later still repeats a non-terminal outcome again
    THEN a report is delivered for it again.

    This test's discrimination sits in the pass, not in the fake: see this
    file's docstring. `_BackoffStore.note` models the naive
    `SET outcome=..., noted_at=...` and leaves the reported stamp exactly
    where it was, so the second report can only arrive if the pass applies
    the lazy lift -- "a row whose noted outcome is not the step's
    currently recorded one governs nothing, neither the cool-off nor the
    report suppression" (`design.md` Decision 4).
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=InProgress, result="the category tree read resumed"),
        StepResolution(outcome=InProgress, result="the category tree read is running"),
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    # The state the scenario starts from: reported, against `Blocked`.
    #
    # FIXTURE CORRECTION (made during implementation, assertions
    # untouched): this was seeded two hours back, which is *inside* the
    # cool-off, so the row still governed and the first pass could not
    # invoke the handler at all -- the step never moved and the test's own
    # premise failed. A governing row suppressing invocation is exactly
    # what `test_a_step_that_stays_stuck_is_not_reported_again` depends
    # on, so the requirement is not in doubt; the seed was. Placing it
    # just outside the cool-off lets the step move on the first pass,
    # which is what the scenario says happens before it gets stuck again.
    reported_at = NOW - REPEAT_COOL_OFF - timedelta(minutes=1)
    world.store.seed(
        outcome=Blocked(FIRST_WORDING),
        noted_at=reported_at,
        reported_at=reported_at,
    )

    # The step moves: a different outcome is recorded.
    await _run_pass(world)
    _require_backoff_reached(world)
    moved = world.launch.progress_for(AUTOMATED_STEP_ID)
    assert moved is not None and moved.outcome is InProgress, (
        "the premise failed: the step did not move to a different outcome"
    )
    assert world.messages == [], (
        "a step that has just moved is not stuck, and must not be reported"
    )

    # And gets stuck again, on the new outcome.
    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: a report is delivered for it again.
    assert len(world.messages) == 1, (
        "no report was delivered after the step got stuck again. A step "
        "whose outcome changed becomes eligible to be reported afresh; a "
        "reported stamp left over from the earlier `Blocked` must not "
        "suppress it."
    )


async def test_a_pass_that_cannot_read_the_backoff_record_delivers_no_report(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A pass that cannot read the backoff record delivers no
    report.

    WHEN a pass cannot read whether a step has already been reported
    THEN the step's handler is invoked, no report is delivered for it, and
    the access failure is reported.

    **The other half of the split degrade** (`design.md` Decision 5):
    *reporting* degrades toward silence, opposite to invocation, because a
    report that cannot be recorded as delivered cannot be delivered
    *once*, and inverting it would turn a store outage into one message
    per stuck step every fifteen minutes.

    The second pass is the positive control in the same test, and is also
    the statement's own clause: "the step is reported normally on the
    first pass that can read the record again".
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    world.store.fail_read = RuntimeError(_ACCESS_FAILURE)

    with caplog.at_level(logging.DEBUG):
        await _run_pass(world)

    _require_backoff_reached(world)

    # SPECIFIED: the step's handler is invoked (the invocation half).
    assert handler.invoked
    # SPECIFIED: no report is delivered for it.
    assert world.notifier.attempts == [], (
        "a report was attempted on a pass that could not read whether the "
        f"step had already been reported: {world.notifier.attempts}"
    )
    # SPECIFIED: the access failure is reported.
    assert _reported_text(caplog, world).strip(), (
        "the backoff access failure was not reported anywhere"
    )

    # The control, and the statement's own clause: the first pass that can
    # read the record again reports normally.
    world.store.fail_read = None
    await _run_pass(world, now=NOW + PASS_INTERVAL)
    assert len(world.messages) == 1, (
        "no report arrived on the pass that could read the record again, so "
        "the assertion above cannot distinguish the specified silence from "
        "a pass that never reports at all"
    )


async def test_a_report_that_could_not_be_delivered_is_not_suppressed() -> None:
    """Scenario: A report that could not be delivered is not suppressed.

    WHEN delivery of the report fails
    THEN nothing is recorded as reported, and the next pass attempts the
    report again.

    `tasks.md` 1.2's third trap: a notifier that silently succeeds cannot
    distinguish "wrote the row after delivering" from "wrote the row
    regardless", so the delivery here **fails**. `design.md` Decision 7 is
    what this pins -- recording first and then failing to deliver would
    silence the step for exactly as long as it stays stuck, since the row
    is lifted by the step moving rather than by Slack recovering.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    world = _world(_automated(), handler=handler, carrying=Blocked(FIRST_WORDING))
    world.notifier.refuse = True

    await _run_pass(world)

    # The premise: a delivery really was attempted, and really failed.
    assert len(world.notifier.attempts) == 1, (
        "no report was attempted at all, so nothing here observes what a "
        "failed delivery leaves behind"
    )
    assert world.messages == []

    # SPECIFIED: nothing is recorded as reported.
    row = world.store.row_for()
    assert row is None or row.reported_at is None, (
        "the step was stamped as reported although the delivery failed; the "
        "record is written only after a delivery succeeds"
    )

    world.notifier.refuse = False
    await _run_pass(world, now=NOW + PASS_INTERVAL)

    # SPECIFIED: the next pass attempts the report again.
    assert len(world.notifier.attempts) == 2, (
        "the next pass did not attempt the report again, so the undelivered "
        "report silenced the step for as long as it stays stuck"
    )
    assert len(world.messages) == 1


async def test_a_failed_report_leaves_the_pass_walking() -> None:
    """Scenario: A failed report leaves the pass walking.

    WHEN delivery of the report fails for one launch's step
    THEN the pass continues with the remaining steps and launches, and the
    pass is still recorded as a successful run.

    The statement adds a third clause tested here -- a failed delivery
    "SHALL NOT record any outcome" -- read as: it causes no recording of
    its own beyond what the handlers themselves produced.
    `contain-a-failing-launch` already established that one launch's fault
    must not starve the ones behind it.
    """
    handler = _ScriptedHandler(
        StepResolution(
            outcome=Blocked(SECOND_WORDING), result=_produced(SECOND_WORDING)
        )
    )
    # A second launch whose step carries nothing, so only the first
    # launch's step is stuck and only its report can fail.
    world = _world(
        _automated(),
        handler=handler,
        carrying=Blocked(FIRST_WORDING),
        second_launch=True,
    )
    world.notifier.refuse = True

    # SPECIFIED: the pass is still recorded as a successful run -- the
    # body returning normally is the only signal it has.
    await _run_pass(world)

    assert len(world.notifier.attempts) == 1, (
        "no report was attempted, so nothing here observes a failed delivery"
    )
    # SPECIFIED: the pass continues with the remaining steps and launches.
    persisted = {(call["product_id"], call["step_id"]) for call in world.recorder.calls}
    assert (OTHER_PRODUCT_ID, AUTOMATED_STEP_ID) in persisted, (
        "the second launch was never walked after the report failed on the "
        f"first; persisted: {sorted((str(p), s) for p, s in persisted)}"
    )
    # SPECIFIED: it records no outcome of its own.
    assert len(world.recorder.calls) == 2, (
        "a failed report recorded something beyond the two handlers' own "
        f"outcomes: {world.recorder.calls}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - **"The judgement SHALL NOT be made from the launch journal."** No test
#   drives it directly. It is observed only negatively, and everywhere:
#   this file supplies the pass no journal at all, and every cool-off
#   above engages without one. An implementation reading
#   `launch_journal_entries` would have nothing to read here. A positive
#   test -- a journal fake asserted never to be read -- would pin a
#   collaborator the pass is specified *not* to have.
#
# - **"Two passes running over the same step at once MAY each deliver the
#   report."** A permission, not an obligation, and a concurrency
#   property of the store's composite key. Nothing at this level can
#   observe it, and nothing is owed for a MAY.
#
# - **The store's own obligation** from `tasks.md` 3.1 -- that noting a
#   repeat against a different outcome kind clears the reported stamp.
#   Deliberately *not* modelled by the fake here, so that the pass's lazy
#   lift is what carries *A step that gets stuck again after moving is
#   reported again*. The accessor's own behaviour is an integration-tier
#   question against the real table (`tasks.md` 2.4, 5.3), and its shape
#   does not exist yet to be tested against.
#
# - **The Alembic revision, up and down** (`tasks.md` 2.3, 2.4). A
#   migration, not a stated scenario; its verification is a task, and
#   `tests/integration/launch/` has no precedent for asserting one.
# ---------------------------------------------------------------------------
