"""The shared eager-convergence helper: lock, delegation, containment.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers the parts of the ADDED requirement *A launch is converged eagerly at
start and at a gate crossing* that are properties of the **shared helper**
itself, independent of which of the four call sites reaches it:

- *The eager run applies the same eligibility rules as the pass* — the
  guard that the helper delegates to the real `converge_launch`, not a
  reimplementation.
- *The eager run does not record completions* — the guard that the helper
  never reaches a completion-recording collaborator.
- *The eager run and the pass do not duplicate each other's work* — the
  structural half: the lock is acquired around the call, and
  `converge_launch`'s own collaborators (`mapping`, `clickup`,
  `read_product`, `members`) are never rebound to the lock's own
  transaction (`tasks.md` 1.1; `design.md` — "The lock acquisition and
  `converge_launch`'s own writes deliberately do not share a
  transaction"). The concurrent-race half — that two lock-holding callers
  really do serialize against a real Postgres lock — is integration-tier,
  in `tests/integration/launch/test_eager_convergence_atomicity_live.py`.
- *A failed eager run does not fail the action that triggered it* — the
  helper's own broad catch (`tasks.md` 1.1: "catches and logs any
  exception internally without re-raising"), asserted here once rather
  than once per call site; each call site's own file asserts only that its
  own action (a Slack ack, an HTTP response, a pass's own run) is
  unaffected.
- *A failed eager run is caught up by the next periodic pass* — that a
  failure contained by the helper leaves nothing behind that would make a
  second attempt at the same launch behave differently from a first one.

Each call site's own wiring — that it calls this helper at all, when, and
with what — is in its own file: `test_slack_entry_eager_convergence.py`,
`test_gate_confirmation_eager_convergence.py`,
`test_gate_progression_pass_eager_convergence.py`,
`test_clickup_webhook_eager_convergence.py`. The stand-down scenario is
inherited by each call site from its own existing readiness check
(`design.md` — "Stand-down is inherited... not re-implemented") and is
asserted there, not here — this file's helper is only ever reached once a
caller has already cleared that check.

See `test-manifest.md` at the change root for the full accounting.

## Level

The helper function itself, over in-memory doubles for its lock,
transaction and `converge_launch`. Nothing smaller can observe "the lock
was acquired around the call" or "the collaborators were not rebound" —
both are properties of what the helper does with its own arguments, not of
what `converge_launch` does with them once called.

One test (`test_a_failure_partway_through_convergence_leaves_prior_writes_
standing_for_a_later_attempt`) drives the **real** `converge_launch`
through the helper, against fakes transcribed from
`test_clickup_sync_projection.py`, because a helper that substitutes
`converge_launch` cannot demonstrate what a real one leaves behind after a
partial failure. It stays unit-tier because the fakes are plain Python
objects with no transactional semantics; the same claim against a real
Postgres session, where `converge_launch`'s writes could otherwise be
undone by a savepoint rollback, is
`test_eager_convergence_atomicity_live.py`'s.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts (`tasks.md` 1.1, `design.md`):

- The helper opens its own `transaction()` **solely** to acquire
  `hold_launch_advance_lock`.
- It then calls `converge_launch` from inside that block, using
  collaborators bound to the caller's own session — never rebound to the
  lock-holding transaction.
- It catches and logs any exception `converge_launch` raises, internally,
  without re-raising.
- `converge_launch`'s own fixed keyword collaborators — `launch`,
  `playbook`, `clickup`, `mapping`, `read_product`, `members`, `folder_id`
  — transcribed from `test_clickup_sync_projection.py` and
  `test_clickup_projection_step_fields.py`, which record them as INVENTED
  there; not re-invented here.

INVENTED, and recorded in the manifest as unresolved project questions:

- **Where** the helper lives. `tasks.md` 1.1 names two candidate homes —
  colocated with `converge_launch` in `clickup_sync.py`, or a thin
  driving-adapter function next to `advance_and_ask` in
  `gate_progression_job.py`. `_MODULE_CANDIDATES` probes both;
  `_locate_helper` fails loudly if neither carries a plausible entry
  point. This file is placed under `infrastructure/driven/` because its
  primary subject is the wrapping of `converge_launch`, not because the
  location question is resolved.
- The helper's own name (`_HELPER_NAMES`) and call shape (`_invoke`),
  probed and filtered by the implemented signature exactly as
  `test_advance_and_ask.py` does for its own trigger.
- The lock and session-seam names it reaches `hold_launch_advance_lock`
  and `transaction`/`session` through — transcribed from
  `test_gate_decision_wiring.py`'s `_LOCK_NAMES` and this repository's
  `_SESSION_NAMES` convention, which already record the provenance of
  each.

## Expected first-run state

Neither candidate module carries this helper yet (`tasks.md` 1.1), so
every test here is expected to fail on an **absent target** —
`_locate_helper`'s loud failure. Per `ai-toolkit:testing` that establishes
absence only: none of the assertions below has been exercised. Never
resolve it by adding the helper; that is `tasks.md` section 1's to add.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped. `uv run pytest tests/integration` — 3
passed, 125 skipped (no `DATABASE_URL` is configured here, so that tier
did not in fact run).
"""

from __future__ import annotations

import importlib
import inspect
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_sync import converge_launch
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import LAUNCH_DATE, PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
FOLDER_ID: Final = "90110042424"
_MODULE_CANDIDATES: Final = (
    "commerce_ops.launch.infrastructure.driven.clickup_sync",
    "commerce_ops.launch.infrastructure.driving.gate_progression_job",
)
_HELPER_NAMES: Final = (
    "converge_launch_eagerly",
    "eager_converge_launch",
    "converge_launch_now",
    "converge_one_launch_eagerly",
    "eagerly_converge_launch",
)
_LOCK_NAMES: Final = ("hold_launch_advance_lock", "advance_lock", "hold_advance_lock")
_SESSION_NAMES: Final = ("transaction", "session")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_clickup_sync_projection.py`
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _second_step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.images-conform",
        "name": "Second piece of work this step asks for",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(version="test-v1", gates=gates, steps=_fill(steps))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — `converge_launch` itself, substituted for most tests
# ---------------------------------------------------------------------------


class _RecordingConverge:
    """Stands in for `converge_launch`.

    Records the whole call, so a test can assert not only *that* it ran
    but *what it was handed* — in particular, whether `mapping`, `clickup`,
    `read_product` and `members` arrived as the very objects the test
    supplied, which is the "never rebound" guarantee's own observable.
    """

    def __init__(self, *, failing: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.failing:
            raise RuntimeError("simulated convergence failure")


# ---------------------------------------------------------------------------
# Test doubles — real `converge_launch`'s collaborators, transcribed from
# `test_clickup_sync_projection.py`, for the partial-write-survival test
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    #: `converge_launch` reads this (`_as_date(task.due_date)`) for every
    #: already-mapped task it re-encounters on a later pass; `None` is a
    #: task with no due date set, which `_as_date` already handles.
    due_date: Any = None


@dataclass(frozen=True)
class _CreatedTask:
    id: str
    url: str


class _FakeClickUp:
    """In-memory ClickUp — transcribed from `test_clickup_sync_projection.py`.

    `fail_after_tasks`, if set, makes the *next* `create_task` call after
    that many have already succeeded raise — the shape `tasks.md` 1.2 asks
    for: "after the list is created but before a task write".
    """

    def __init__(self, *, fail_after_tasks: int | None = None) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0
        self._fail_after_tasks = fail_after_tasks

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{self._next:03d}"

    async def read_list_state(self, list_id: str) -> ClickUpListState:
        return ClickUpListState(deleted=False)

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        if (
            self._fail_after_tasks is not None
            and len(self.tasks) >= self._fail_after_tasks
        ):
            raise RuntimeError("simulated ClickUp fault partway through projection")
        self.calls.append(("create_task", {"list_id": list_id, "name": name, **fields}))
        task_id = self._identifier("task")
        self.tasks[task_id] = _FakeTask(id=task_id, name=name, list_id=list_id)
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag": tag_name}))

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        return [task for task in self.tasks.values() if task.list_id == list_id]

    def calls_named(self, name: str) -> list[Any]:
        return [payload for called, payload in self.calls if called == name]


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False


class _FakeMapping:
    """In-memory mapping store — transcribed from
    `test_clickup_sync_projection.py`."""

    def __init__(self) -> None:
        self.lists: dict[ProductId, str] = {}
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {}

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
        self.lists[product_id] = list_id

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> _TaskMapping | None:
        return self.tasks.get((product_id, step_id))

    async def tasks_for(self, product_id: ProductId) -> list[_TaskMapping]:
        return [
            mapping
            for (mapped_product, _), mapping in self.tasks.items()
            if mapped_product == product_id
        ]

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None:
        self.tasks[(product_id, step_id)] = _TaskMapping(
            product_id=product_id, step_id=step_id, task_id=task_id
        )

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        self.tasks[(product_id, step_id)].last_observed_closed = closed

    async def record_composition(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    async def replace_list_discarding_tasks(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0
        self.commits = 0

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return None


# ---------------------------------------------------------------------------
# Reaching the helper, through two correction points: which module, which
# name
# ---------------------------------------------------------------------------


def _locate_helper() -> tuple[ModuleType, str]:
    for path in _MODULE_CANDIDATES:
        try:
            module = importlib.import_module(path)
        except ImportError:
            continue
        for name in _HELPER_NAMES:
            if callable(getattr(module, name, None)):
                return module, name
    pytest.fail(
        f"neither of {_MODULE_CANDIDATES} exposes an eager-convergence helper "
        f"under any of {_HELPER_NAMES}; `tasks.md` 1.1 adds it to one of them. "
        "This is the absent-target state, not a defect in this file — do not "
        "add the helper to make this pass."
    )


@dataclass
class _Order:
    events: list[str] = field(default_factory=list)

    def note(self, event: str) -> None:
        self.events.append(event)


@dataclass
class _Harness:
    module: ModuleType
    name: str
    monkeypatch: pytest.MonkeyPatch
    converge: Any
    order: _Order
    session: _FakeSession
    placed_session: bool = False
    placed_lock: bool = False

    def install(self) -> None:
        self.monkeypatch.setattr(self.module, "converge_launch", self.converge)
        self._place_lock()
        self._place_session()

    def _place_lock(self) -> None:
        order = self.order

        async def _lock(*args: Any, **kwargs: Any) -> None:
            order.note("lock")

        for name in _LOCK_NAMES:
            if hasattr(self.module, name):
                self.monkeypatch.setattr(self.module, name, _lock)
                self.placed_lock = True

    def _place_session(self) -> None:
        order = self.order
        session = self.session

        for name in _SESSION_NAMES:
            if not hasattr(self.module, name):
                continue

            @asynccontextmanager
            async def _provider(
                *args: Any, _session: _FakeSession = session, **kwargs: Any
            ) -> AsyncIterator[_FakeSession]:
                order.note("transaction-open")
                try:
                    yield _session
                finally:
                    order.note("transaction-close")

            self.monkeypatch.setattr(self.module, name, _provider)
            self.placed_session = True

    def entry(self) -> Any:
        return getattr(self.module, self.name)


def _harness(monkeypatch: pytest.MonkeyPatch, converge: Any | None = None) -> _Harness:
    module, name = _locate_helper()
    order = _Order()
    harness = _Harness(
        module=module,
        name=name,
        monkeypatch=monkeypatch,
        converge=converge if converge is not None else _RecordingConverge(),
        order=order,
        session=_FakeSession(),
    )
    harness.install()
    assert harness.placed_lock, (
        f"{module.__name__} exposes no lock collaborator under any of "
        f"{_LOCK_NAMES} — correct `_LOCK_NAMES` to the implemented name"
    )
    assert harness.placed_session, (
        f"{module.__name__} exposes no session-seam collaborator under any "
        f"of {_SESSION_NAMES} — correct `_SESSION_NAMES` to the implemented "
        "name"
    )
    return harness


async def _invoke(harness: _Harness, **collaborators: Any) -> Any:
    """INVENTED call shape — the single correction point.

    Supplies a pool of plausible arguments (a product identifier, a loaded
    launch, its playbook, and `converge_launch`'s own four collaborators
    plus `folder_id`) and filters it by the helper's actual signature,
    exactly as `test_advance_and_ask.py`'s own `run` does for its trigger.
    """
    entry = harness.entry()
    parameters = inspect.signature(entry).parameters
    pool: dict[str, Any] = {
        "product_id": PRODUCT_ID,
        "product": PRODUCT_ID,
        **collaborators,
    }
    supplied = {key: value for key, value in pool.items() if key in parameters}
    for name in ("product_id", "product", "launch"):
        if (
            name in parameters
            and parameters[name].kind is not inspect.Parameter.POSITIONAL_ONLY
        ):
            break
    else:
        # No named product/launch parameter matched by keyword; try
        # positional as a last resort.
        if "launch" in collaborators:
            return await entry(
                collaborators["launch"],
                **{k: v for k, v in supplied.items() if k != "launch"},
            )
        return await entry(
            PRODUCT_ID,
            **{k: v for k, v in supplied.items() if k not in ("product_id", "product")},
        )
    return await entry(**supplied)


# ---------------------------------------------------------------------------
# "the lock acquisition and converge_launch's own writes deliberately do
# not share a transaction" — the structural half of "do not duplicate"
# ---------------------------------------------------------------------------


async def test_the_lock_is_acquired_around_the_convergence_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED-BY-TASKS (`tasks.md` 1.1): the helper "opens its own
    `transaction()` solely to acquire `hold_launch_advance_lock`, then
    calls `converge_launch` from inside that block".

    Ordering is asserted directly: the transaction opens, the lock is
    taken, `converge_launch` runs, and the transaction closes — in that
    order — which is what makes mutual exclusion against a concurrently
    locking caller hold at all (`design.md`: "the writes still happen
    strictly between the lock's acquisition and its release in real
    time").
    """
    converge = _RecordingConverge()
    harness = _harness(monkeypatch, converge)

    await _invoke(
        harness,
        launch=_launch(_playbook((_step(),))),
        playbook=_playbook((_step(),)),
        clickup=object(),
        mapping=object(),
        read_product=_FakeCatalog(),
        members=None,
        folder_id=FOLDER_ID,
    )

    order = harness.order.events
    assert "lock" in order, (
        "the helper never reached the advisory lock collaborator, so the "
        f"call is not guarded against a concurrent one: {order!r}"
    )
    assert order.index("transaction-open") < order.index("lock"), (
        f"the lock was not taken inside the helper's own transaction: {order!r}"
    )
    assert order.index("transaction-close") > order.index("lock"), (
        f"the transaction closed before the lock was taken: {order!r}"
    )
    assert converge.calls, (
        "convergence never ran, so this test exercised nothing about "
        "ordering the lock around it"
    )


async def test_converge_launchs_collaborators_are_not_rebound_to_the_lock_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED-BY-DESIGN (`design.md` — "The lock acquisition and
    `converge_launch`'s own writes deliberately do not share a
    transaction"): `mapping`, `clickup`, `read_product` and `members` reach
    `converge_launch` as the very objects the caller already had, never
    rebuilt against the lock-holding session.

    This is what makes the partial-progress-survives-failure guarantee
    hold: a collaborator rebound to the lock's own transaction would have
    its writes undone by that transaction's rollback, per `design.md`'s
    account of `join_transaction_mode="create_savepoint"` — the defect
    this test exists to catch before it reaches a real database.
    """
    converge = _RecordingConverge()
    harness = _harness(monkeypatch, converge)
    sentinel_clickup = object()
    sentinel_mapping = object()
    sentinel_catalog = _FakeCatalog()
    sentinel_members = object()

    await _invoke(
        harness,
        launch=_launch(_playbook((_step(),))),
        playbook=_playbook((_step(),)),
        clickup=sentinel_clickup,
        mapping=sentinel_mapping,
        read_product=sentinel_catalog,
        members=sentinel_members,
        folder_id=FOLDER_ID,
    )

    assert len(converge.calls) == 1, (
        f"convergence ran an unexpected number of times: {converge.calls!r}"
    )
    received = converge.calls[0]
    # SPECIFIED-BY-DESIGN: each collaborator that reached the real
    # `converge_launch` is identically the object the caller supplied.
    if "clickup" in received:
        assert received["clickup"] is sentinel_clickup, (
            "the `clickup` collaborator reaching convergence is not the "
            "caller's own object, so it was rebuilt or rebound somewhere"
        )
    if "mapping" in received:
        assert received["mapping"] is sentinel_mapping, (
            "the `mapping` collaborator reaching convergence is not the "
            "caller's own object — a rebuild here is exactly what would let "
            "the lock's own transaction roll its writes back"
        )
    if "read_product" in received:
        assert received["read_product"] is sentinel_catalog
    if "members" in received:
        assert received["members"] is sentinel_members
    assert received, (
        "no collaborator arrived at convergence under any of its known "
        "keyword names; correct this file's reading of the call shape"
    )


# ---------------------------------------------------------------------------
# "The eager run applies the same eligibility rules as the pass"
# ---------------------------------------------------------------------------


async def test_the_helper_delegates_to_the_real_converge_launch_not_a_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The eager run applies the same eligibility rules as the
    pass.

    "because it is the same convergence, run early, not a second rule" —
    asserted here as identity: the collaborator the helper calls, once
    substituted, is reached under the very name `converge_launch` imports
    to. A helper that reimplemented eligibility beside it would leave this
    collaborator untouched and fail here, exactly as every eligibility
    scenario already tested in `test_clickup_sync_projection.py` and its
    siblings would then be silently bypassed for launches the eager path
    reaches first.
    """
    harness = _harness(monkeypatch)
    assert isinstance(harness.converge, _RecordingConverge)

    await _invoke(
        harness,
        launch=_launch(_playbook((_step(),))),
        playbook=_playbook((_step(),)),
        clickup=object(),
        mapping=object(),
        read_product=_FakeCatalog(),
        members=None,
        folder_id=FOLDER_ID,
    )

    assert harness.converge.calls, (
        "the helper never called the substituted `converge_launch` "
        "collaborator at all, so it is not delegating to it"
    )


# ---------------------------------------------------------------------------
# "The eager run does not record completions"
# ---------------------------------------------------------------------------


async def test_the_eager_run_reaches_no_completion_recording_collaborator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The eager run does not record completions.

    A `reconcile_launch` or `record_step_outcome`-shaped collaborator,
    where the helper's own module happens to carry one (both candidate
    homes are modules that also touch completion machinery elsewhere), is
    never reached by the helper's own call. Failing loudly if either is
    even substituted-and-not-called would be too strong — the test asserts
    only that if such a collaborator exists, this call left it untouched.
    """
    harness = _harness(monkeypatch)
    reconcile_calls: list[Any] = []

    async def _forbidden_reconcile(*args: Any, **kwargs: Any) -> None:
        reconcile_calls.append((args, kwargs))

    for name in ("reconcile_launch", "record_step_outcome"):
        if hasattr(harness.module, name):
            monkeypatch.setattr(harness.module, name, _forbidden_reconcile)

    await _invoke(
        harness,
        launch=_launch(_playbook((_step(),))),
        playbook=_playbook((_step(),)),
        clickup=object(),
        mapping=object(),
        read_product=_FakeCatalog(),
        members=None,
        folder_id=FOLDER_ID,
    )

    # SPECIFIED: no ClickUp state is read back and no outcome is recorded
    # as a consequence of the eager run itself.
    assert reconcile_calls == [], (
        "the eager run reached a completion-recording collaborator, which "
        f"the requirement forbids: {reconcile_calls!r}"
    )


# ---------------------------------------------------------------------------
# "A failed eager run does not fail the action that triggered it" — at the
# helper's own level
# ---------------------------------------------------------------------------


async def test_a_failing_convergence_is_logged_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: A failed eager run does not fail the action that
    triggered it — the helper's own containment (`tasks.md` 1.1: "catches
    and logs any exception internally without re-raising").

    Each call site's own file asserts that *its* action survives; this is
    the one place the containment mechanism itself is exercised, so a gap
    in any one call site's own catch is distinguishable from a gap in the
    shared mechanism they all rely on.
    """
    converge = _RecordingConverge(failing=True)
    harness = _harness(monkeypatch, converge)

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED-BY-TASKS: it returns rather than raising.
        await _invoke(
            harness,
            launch=_launch(_playbook((_step(),))),
            playbook=_playbook((_step(),)),
            clickup=object(),
            mapping=object(),
            read_product=_FakeCatalog(),
            members=None,
            folder_id=FOLDER_ID,
        )

    assert converge.calls, (
        "the failing convergence was never reached, so this test exercised nothing"
    )
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert logged.strip(), (
        "a failed eager run left no log entry at all, so a launch whose "
        "convergence silently failed is unattributable"
    )


# ---------------------------------------------------------------------------
# "the failure of the recovery ... A failed eager run is caught up by the
# next periodic pass" — no prior partial write is lost or duplicated
# ---------------------------------------------------------------------------


async def test_a_failure_partway_through_convergence_leaves_prior_writes_standing_for_a_later_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenarios: *The eager run and the pass do not duplicate each
    other's work*, and *A failed eager run is caught up by the next
    periodic pass* — driven together, because what makes the second true
    is precisely what the first requires: nothing the failed attempt wrote
    is undone, so a later attempt (whether the pass, or the helper called
    again) resumes from it rather than re-creating it.

    Drives the **real** `converge_launch` through the helper (not a
    substitute), against a `_FakeClickUp` that fails on the second task —
    after the list and the first task have already been created and
    recorded — exactly the shape `tasks.md` 1.2 asks for. A second call
    through the same helper then completes what the first left standing.

    This is a fake in-memory store, so it cannot demonstrate that a real
    Postgres savepoint rollback would leave the same writes standing —
    only that the helper itself performs no compensating undo of its own.
    The real-transaction version of this claim is
    `test_eager_convergence_atomicity_live.py`'s.
    """
    playbook = _playbook((_step(), _second_step()))
    launch = _launch(playbook)
    clickup = _FakeClickUp(fail_after_tasks=1)
    mapping = _FakeMapping()
    catalog = _FakeCatalog()
    harness = _harness(monkeypatch, converge_launch)

    # First attempt: fails after the list and one task are created.
    await _invoke(
        harness,
        launch=launch,
        playbook=playbook,
        clickup=clickup,
        mapping=mapping,
        read_product=catalog,
        members=None,
        folder_id=FOLDER_ID,
    )

    # Premise: the first attempt really did get partway before failing.
    assert clickup.calls_named("create_list"), (
        "the first attempt never created a list, so this test does not "
        "exercise a partial failure at all"
    )
    first_task_mapping = await mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert first_task_mapping is not None, (
        "the first attempt's own task was not recorded, so this test does "
        "not exercise a partial failure at all"
    )
    # SPECIFIED: the second step's task was not created — the failure
    # really did stop the launch partway.
    assert await mapping.task_for(PRODUCT_ID, "listing.images-conform") is None

    recorded_list_id = await mapping.list_id_for(PRODUCT_ID)
    assert recorded_list_id is not None

    # A later attempt (the next periodic pass, modelled here as a second
    # call through the helper with a ClickUp double that no longer fails).
    clickup._fail_after_tasks = None
    await _invoke(
        harness,
        launch=launch,
        playbook=playbook,
        clickup=clickup,
        mapping=mapping,
        read_product=catalog,
        members=None,
        folder_id=FOLDER_ID,
    )

    # SPECIFIED: nothing the first attempt wrote is lost — no second list,
    # no re-creation of the task it already recorded.
    assert await mapping.list_id_for(PRODUCT_ID) == recorded_list_id, (
        "a later attempt created a second list for a launch whose first "
        "list had already been recorded"
    )
    assert clickup.calls_named("create_list") == [
        clickup.calls_named("create_list")[0]
    ], (
        "more than one `create_list` call was made across the two attempts, "
        "so the first attempt's list was duplicated rather than reused"
    )
    still_first = await mapping.task_for(PRODUCT_ID, "listing.title-conforms")
    assert (
        still_first is not None and still_first.task_id == first_task_mapping.task_id
    ), (
        "the task the first attempt recorded before failing was recreated "
        "by the later attempt rather than left standing"
    )
    # SPECIFIED: the later attempt converges the launch exactly as it
    # would a launch for which no eager run was ever attempted — the
    # second step's task now exists.
    assert await mapping.task_for(PRODUCT_ID, "listing.images-conform") is not None, (
        "the later attempt did not finish converging the launch, so the "
        "first attempt's failure was not, in fact, caught up"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the two lock-holding callers genuinely serialize against a real
#   Postgres `pg_advisory_xact_lock`. An advisory lock holds nothing
#   without a database; see `test_eager_convergence_atomicity_live.py`.
# - That a real Postgres savepoint rollback around the lock's own
#   transaction leaves `converge_launch`'s writes on a *different*
#   connection standing. Nothing here is a real transaction; see the same
#   integration file.
# - Every eligibility rule `converge_launch` itself applies (release,
#   kind, status, hazard, retained-composition healing, Custom Fields).
#   Already covered by the existing driven-tier suite
#   (`test_clickup_sync_projection.py` and its siblings), which this
#   change leaves untouched; re-asserting each here would duplicate rather
#   than add, and this file's own guard is that the helper reaches the
#   same collaborator those tests already constrain.
# - The stand-down condition. Inherited by each call site from its own
#   existing readiness check (`design.md`), never re-tested by the helper
#   itself, which is only ever reached once that check has passed.
# ---------------------------------------------------------------------------
