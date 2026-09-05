"""What the retained record does *not* cover
(`launch-step-automation`).

Derived strictly from the delta spec
`openspec/changes/add-product-dossier-page/specs/launch-step-automation/spec.md`
— the ADDED requirement *The retained record covers results held for a
decision and nothing else*, both scenarios:

- *An outcome needing no confirmation is not retained*
- *A non-terminal outcome is not retained*

The requirement's sibling — *A retained result is kept and stays
readable as the product's record* — is covered in
`tests/unit/launch/application/test_retained_results_read.py` and
`tests/integration/launch/test_retained_results_read_live.py`.
`test-manifest.md` at the change root records every scenario, every
assertion's classification, and the project questions this file answered
by assumption.

## Why these two scenarios need the pass, and so live here

Each scenario's WHEN is *a handler resolving a step*, and its THEN is
what the read then answers. Nothing smaller can observe them: a test
that simply seeded no row and read nothing back would assert nothing at
all. So the pass runs over doubles and the read is taken over the same
result store the pass wrote to — which is why this file sits in the
driving tier beside `test_automation_pass.py`, whose harness it reuses,
rather than in `tests/unit/launch/application/` where `tasks.md` 1.2
places the read's own scenarios. That placement is this file's one
departure from 1.2, and it is recorded in the manifest as an unresolved
project question with the reasoning above as the assumption taken.

The requirement adds no routing policy: which outcomes are held and
which are recorded directly is settled by three requirements already
served, and this is their consequence. What it adds is the boundary as a
fact *about the retained set*, which is exactly what the read below
observes — so a change to that routing changes this test with it, which
is the requirement's own stated intent.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the branch on **terminality**, not on the
confirmation flag alone; that a non-terminal outcome is recorded against
the launch whatever the flag says; that a terminal outcome on a step
needing no confirmation is recorded at once. All three are served
requirements of `launch-step-automation`, restated by this delta as a
property of the retained set.

INVENTED, each recorded in the manifest with its correction point:

- The pass's entry point and call shape (`_pass_entry`, `_run_pass`) and
  every double below — taken verbatim from `test_automation_pass.py`,
  which the implementation already satisfies, so a correction there is a
  correction here.
- The new read's method name on the result store (`_READ_NAMES`) and the
  use case's name and call shape (`_USE_CASE_NAMES`, `_read`) — the same
  probes `test_retained_results_read.py` records.

What must survive any correction: that the read answers nothing for a
step needing no confirmation and nothing for a non-terminal outcome,
while still answering the confirmable terminal proposal produced in the
same pass.

## Expected first-run state

The read and its use case do not exist, so both tests are expected to
fail on an **absent target** — `_use_case()` fails by name. The pass
itself ships today and runs; nothing here asserts anything new about it.

Baseline recorded before these tests were written: `uv run pytest` at the
worktree root — 1232 passed, 96 skipped, 0 failed (2026-08-27).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    InProgress,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import automation_pass
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeHandlers as _FakeHandlers
from tests.support.fakes import FakeLaunches as _FakeLaunches
from tests.support.fakes import FakeProductReader
from tests.support.fakes import InertBackoff as _InertBackoff
from tests.support.fixtures import (
    ALICE,
    LAUNCH_DATE,
    PRODUCT_NAME,
    PRODUCT_SKU,
    product_id,
)
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
CONFIRMABLE_STEP: Final = "listing.sub-category"
UNCONFIRMED_STEP: Final = "listing.needs-no-confirmation"
NON_TERMINAL_STEP: Final = "listing.still-running"

CONFIRMABLE_HANDLER: Final = "listing.subcategory_advisor"
UNCONFIRMED_HANDLER: Final = "listing.records_at_once"
NON_TERMINAL_HANDLER: Final = "listing.reports_progress"

NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

HELD_TEXT: Final = "Home and Kitchen, Cutting Boards."
RECORDED_TEXT: Final = "Nothing here needed anyone's agreement."
PROGRESS_TEXT: Final = "The category tree read is still running."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures (the shapes `test_automation_pass.py` records)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": CONFIRMABLE_STEP,
            "name": "Choose the sub-category node",
            "assignees": (ALICE,),
            **overrides,
        }
    )


def _automated(identifier: str, handler: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "kind": StepKind.AUTOMATED,
        "handler": handler,
        "assignees": (),
    }
    attributes.update(overrides)
    return _step(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking `human` filler per gate, satisfying the gate-holding
    floor without becoming a candidate the pass would invoke."""
    return _build_hold(
        gate,
        assignees=(ALICE,),
        name=f"Blocking work of hold.{gate}",
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    return _build_playbook(
        *steps,
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (`test_automation_pass.py`)
# ---------------------------------------------------------------------------


class _FakeCatalog(FakeProductReader):
    """The shared reader, adapted: this file's call sites build no product.

    Constructor-only difference, so the equality proof runs over this adapter --
    it answered field-wise-equal values on every call the file executes.
    """

    def __init__(self) -> None:
        super().__init__(_CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU))


class _ScriptedHandler:
    def __init__(self, resolution: StepResolution) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        return self.resolution


@dataclass
class _PendingRow:
    id: int
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


#: The read `tasks.md` 2.1 adds — its spelling is not fixed by any
#: artifact, so the store answers the plausible ones and fails loudly,
#: naming them, for anything else.
_READ_NAMES: Final = (
    "for_product",
    "all_for_product",
    "retained_for",
    "retained_for_product",
    "results_for",
    "list_for_product",
    "by_product",
    "all_for",
)


class _FakeResults:
    """The pass's result store *and* the store the new read reads.

    One object on purpose: the whole point of these two scenarios is
    that the set the pass writes is the set the read answers, so a
    separate double for the read would assert nothing about the
    boundary.
    """

    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []
        self._next_id = 1

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

    async def store(
        self,
        *,
        product_id: ProductId,
        step_id: str,
        handler: str,
        proposed_outcome: Any,
        result_text: str,
        produced_at: datetime,
        finding: Any = None,
    ) -> _PendingRow:
        row = _PendingRow(
            id=self._next_id,
            product_id=product_id,
            step_id=step_id,
            handler=handler,
            proposed_outcome=proposed_outcome,
            result_text=result_text,
            produced_at=produced_at,
        )
        self._next_id += 1
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        self._row_of(row).delivered_at = when or NOW

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        return None

    async def _answer(self, *args: Any, **kwargs: Any) -> list[_PendingRow]:
        wanted = None
        for value in (*args, *kwargs.values()):
            if isinstance(value, ProductId):
                wanted = value
        rows = [row for row in self.rows if row.product_id == wanted]
        return sorted(rows, key=lambda row: (row.produced_at, row.id), reverse=True)

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        for candidate in self.rows:
            if candidate is row:
                return candidate
        raise AssertionError(f"unknown pending row {row!r}")


for _name in _READ_NAMES:
    setattr(_FakeResults, _name, _FakeResults._answer)


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    def for_step(self, step_id: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("step_id") == step_id]


class _FakeDelivery:
    def __init__(self) -> None:
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)


@dataclass
class _Collaborators:
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    handlers: _FakeHandlers
    results: _FakeResults = field(default_factory=_FakeResults)
    recorder: _RecordingOutcomes = field(default_factory=_RecordingOutcomes)
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    delivery: _FakeDelivery = field(default_factory=_FakeDelivery)


# ---------------------------------------------------------------------------
# The pass, reached through one correction point
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)


def _pass_entry() -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(automation_pass, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no pass entry point found on "
        f"{automation_pass.__name__} under any of {_ENTRY_NAMES} — correct "
        "this file's probe to the implemented name"
    )


class _InertNotifier:
    async def post_monitoring_message(self, message: str) -> None:
        return None


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    """Thread-establishment nothing in this file exercises."""
    return "FAKE_THREAD_TS", None


async def _run_pass(collaborators: _Collaborators) -> Any:
    entry = _pass_entry()
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "handlers": collaborators.handlers,
        "results": collaborators.results,
        "record_outcome": collaborators.recorder,
        "read_product": collaborators.catalog,
        "deliver": collaborators.delivery,
        "backoff": _InertBackoff(),
        "notifier": _InertNotifier(),
        "establish_thread": _inert_establish_thread,
        "now": NOW,
    }
    accepted = set(inspect.signature(entry).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct "
        "`_run_pass` to the implemented collaborator names"
    )
    return await entry(**supplied)


# ---------------------------------------------------------------------------
# The read, reached through one correction point
# ---------------------------------------------------------------------------

_USE_CASE_NAMES: Final = (
    "read_retained_results",
    "retained_results",
    "read_retained_results_for_product",
    "list_retained_results",
    "read_produced_record",
    "retained_results_for",
)


def _use_case() -> Any:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no retained-results read is exported from `launch.application` "
        f"under any of {_USE_CASE_NAMES} — correct `_USE_CASE_NAMES` to "
        "the implemented name"
    )


async def _read(results: _FakeResults) -> tuple[Any, ...]:
    use_case = _use_case()
    names = list(inspect.signature(use_case).parameters)
    arguments: dict[str, Any] = {}
    for name in names[1:]:
        if "scope" in name:
            arguments[name] = AccessScope.unrestricted()
        elif "product" in name or name in ("identifier", "id"):
            arguments[name] = PRODUCT_ID
    return tuple(await use_case(results, **arguments))


def _step_ids(records: tuple[Any, ...]) -> list[str]:
    found: list[str] = []
    for record in records:
        for name in ("step_id", "step", "step_identifier", "identifier"):
            if hasattr(record, name):
                found.append(str(getattr(record, name)))
                break
        else:  # pragma: no cover - a fixture correction, not a result
            pytest.fail(
                f"{type(record).__name__} exposes no step identifier (`tasks.md` 2.4)"
            )
    return found


# ---------------------------------------------------------------------------
# One pass, three steps, one read
# ---------------------------------------------------------------------------


def _three_steps() -> _Collaborators:
    """One pass over three automated steps, one per branch the routing
    already settles:

    - a confirmable step whose handler proposes a **terminal** outcome —
      held for a decision, and so retained;
    - a step needing **no confirmation** whose handler proposes a
      terminal outcome — recorded at once, and so not retained;
    - a confirmable step whose handler proposes a **non-terminal**
      outcome — recorded against the launch, and so not retained.

    All three in one pass, so "nothing is answered for that step" is
    read off the same answer that does carry the held one.
    """
    steps = (
        _automated(CONFIRMABLE_STEP, CONFIRMABLE_HANDLER, confirmer=ALICE),
        _automated(UNCONFIRMED_STEP, UNCONFIRMED_HANDLER),
        _automated(NON_TERMINAL_STEP, NON_TERMINAL_HANDLER, confirmer=ALICE),
    )
    playbook = _playbook(*steps)
    handlers = _FakeHandlers(
        **{
            CONFIRMABLE_HANDLER: _ScriptedHandler(
                StepResolution(outcome=Satisfied, result=HELD_TEXT)
            ),
            UNCONFIRMED_HANDLER: _ScriptedHandler(
                StepResolution(outcome=Satisfied, result=RECORDED_TEXT)
            ),
            NON_TERMINAL_HANDLER: _ScriptedHandler(
                StepResolution(outcome=InProgress, result=PROGRESS_TEXT)
            ),
        }
    )
    return _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Requirement: The retained record covers results held for a decision
# and nothing else
# ---------------------------------------------------------------------------


async def test_an_outcome_needing_no_confirmation_is_not_retained() -> None:
    """Scenario: An outcome needing no confirmation is not retained.

    WHEN a handler resolves a step whose confirmation flag is false, and
    every result retained for that product is read
    THEN nothing is answered for that step.
    """
    collaborators = _three_steps()

    await _run_pass(collaborators)
    answered = await _read(collaborators.results)

    # DERIVED precondition: the step really was resolved, so "nothing is
    # answered for it" is the retained set's boundary rather than a pass
    # that never reached the step.
    assert collaborators.recorder.for_step(UNCONFIRMED_STEP), (
        "the pass never recorded an outcome for the step needing no "
        "confirmation, so this test does not reach the scenario"
    )
    # SPECIFIED: nothing is answered for that step.
    assert UNCONFIRMED_STEP not in _step_ids(answered)
    # DERIVED guard: the read is not answering nothing to everything —
    # the confirmable proposal from the same pass is answered.
    assert CONFIRMABLE_STEP in _step_ids(answered)


async def test_a_non_terminal_outcome_is_not_retained() -> None:
    """Scenario: A non-terminal outcome is not retained.

    WHEN a handler proposes a non-terminal outcome for a step whose
    confirmation flag is true, and every result retained for that
    product is read
    THEN nothing is answered for that step.

    This is the trap the served requirements record the confirmation
    branch being moved to close: an implementation branching on the
    confirmation flag alone would hold "please accept: still running",
    and the retained record would then carry something nobody was asked
    to accept.
    """
    collaborators = _three_steps()

    await _run_pass(collaborators)
    answered = await _read(collaborators.results)

    # DERIVED precondition: the non-terminal outcome really was
    # produced and recorded against the launch.
    assert collaborators.recorder.for_step(NON_TERMINAL_STEP), (
        "the pass never recorded the non-terminal outcome, so this test "
        "does not reach the scenario"
    )
    # SPECIFIED: nothing is answered for that step.
    assert NON_TERMINAL_STEP not in _step_ids(answered)
    # SPECIFIED by the requirement's own statement: everything the
    # record *does* carry is a proposal someone was asked to accept.
    assert _step_ids(answered) == [CONFIRMABLE_STEP]


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The converse. The requirement is stated as a necessary condition and
#   not as a biconditional, and says why: a terminal outcome the step's
#   hazard forbids stores nothing at all, and a second proposal racing an
#   existing pending one stores nothing either. A test asserting that
#   every proposal ever made is in the record would assert the converse
#   the requirement explicitly disclaims.
# - The routing itself — which outcomes are held and which are recorded
#   directly. Three served requirements settle it and
#   `tests/unit/launch/infrastructure/driving/test_automation_pass.py`
#   already covers them; this file leans on that rather than restating
#   it, and asserts only what the *retained set* then looks like.
# ---------------------------------------------------------------------------
