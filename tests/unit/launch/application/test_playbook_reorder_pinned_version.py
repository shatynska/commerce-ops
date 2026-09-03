"""A caller-supplied view of the step set on the authoring reorder write
(`playbook-authoring`, MODIFIED requirement *A gate's steps can be
reordered*).

Derived strictly from the delta spec
`openspec/changes/reorder-steps-under-filters/specs/playbook-authoring/spec.md`
— the three scenarios that requirement ADDS to the three it reproduces
verbatim:

- *A supplied view is not retried past*
- *A supplied view that does not match is refused whichever way it differs*
- *A reorder without a supplied view still resolves concurrency*

The three reproduced scenarios (*A moved step is served in its new
slot*, *A stale reorder is rejected whole*, *A reorder never leaves the
step's own gate*) already have passing tests in
`test_playbook_reorder.py` in this directory and are **not** duplicated
here; the manifest records them as already-covered.

The seam is the one `test_playbook_reorder.py` established and the
implementation adopted: use cases taking the step store as `steps=` plus
`principal=`, over a store whose `load()` answers `(records, version)`
and whose `save(records, *, expected_version)` persists conditionally.
The harness below duplicates that file's doubles rather than importing
them, because `tests/unit/launch/application/` carries no
`__init__.py` — it is not an importable package, and a cross-module test
import would depend on `pytest`'s sys.path insertion order.

## What is fixed, and what is INVENTED

Fixed by the artifacts, not invented:

- `reorder_step` gains an **optional** expected set version; when it is
  supplied, a version that is not the one the write reads is rejected
  rather than retried, in either direction; when it is absent, today's
  re-read-and-recompute behaviour is unchanged (the delta requirement's
  second paragraph, `design.md` — *The supplied version is honoured, not
  retried past*, `tasks.md` 4.1-4.2).
- `StaleStepSetError` is the rejection (`tasks.md` 4.2 names it).

INVENTED, recorded in `test-manifest.md` as unresolved project
questions, correction point named:

- The parameter's spelling, `expected_version=`, following the store
  protocol's own `save(..., expected_version=)` rather than any artifact
  — no artifact fixes a name. Correction point: `_reorder_pinned` below,
  the only place it is written.
- That an *absent* supplied view is expressed by not passing the
  parameter at all rather than by passing `None`. Correction point:
  `_reorder_unpinned` below.

## Expected first-run state

`reorder_step` does not accept the parameter yet, so the two pinned
tests fail with `TypeError` — the absent-target state; their assertions
have not been exercised. `test_a_reorder_without_a_supplied_view_...`
exercises behaviour that already exists, so it is expected to **pass**
on the first run: it is a regression pin on `tasks.md` 4.2's "no
existing caller changes meaning", not a new obligation, and is recorded
that way in the manifest.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here). The baseline is therefore scoped to the
two tiers this change's tests are written into.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    StaleStepSetError,
    reorder_step,
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
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "helen"
A_DISCIPLINE: Final = next(iter(Discipline))

#: The version the store below is loaded at. The two pinned tests supply
#: a *different* one, in each direction.
SET_VERSION: Final = 41


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures and the step-store double (test_playbook_reorder.py's)
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": A_DISCIPLINE,
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


class _OrderedRecord:
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
    """In-memory step-set store with the optimistic set-version."""

    def __init__(self, records: tuple[Any, ...], version: int = SET_VERSION) -> None:
        self.records = records
        self.version = version
        self.loads = 0
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        self.loads += 1
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


class _ConcurrentThenSettledStore(_FakeStepStore):
    """A store whose first conditional save loses a race and whose next
    one wins it.

    The deterministic stand-in for "meets a concurrent accepted write":
    the interposed write bumps the set version and the refused save
    raises, exactly as the real conditional persistence does. A caller
    that re-reads and recomputes gets through on its second attempt; one
    that does not, does not.
    """

    def __init__(self, records: tuple[Any, ...], version: int = SET_VERSION) -> None:
        super().__init__(records, version)
        self.refusals = 0

    async def save(self, records: Any, *, expected_version: int) -> None:
        if self.refusals == 0:
            self.refusals += 1
            self.version += 1  # the concurrent write landed
            raise StaleStepSetError(
                "the step set changed underneath this write: expected version "
                f"{expected_version} was superseded"
            )
        await super().save(records, expected_version=expected_version)


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
    live = [
        record
        for record in store.records
        if record.definition.gate == gate and _is_active(record)
    ]
    live.sort(key=lambda record: (record.display_order, record.definition.identifier))
    return [record.definition.identifier for record in live]


def _store_with_listable(
    *identifiers: str,
    store_class: type[_FakeStepStore] = _FakeStepStore,
) -> _FakeStepStore:
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


async def _reorder_pinned(
    store: _FakeStepStore,
    step_id: str,
    target_index: int,
    *,
    expected_version: int,
) -> Any:
    """The single correction point for the supplied-view parameter's
    spelling (INVENTED — see this file's docstring)."""
    return await reorder_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        target_index=target_index,
        expected_version=expected_version,
    )


async def _reorder_unpinned(
    store: _FakeStepStore, step_id: str, target_index: int
) -> Any:
    """A reorder supplying no view of the set: the parameter is simply
    not passed. Single correction point if absence is spelled some other
    way."""
    return await reorder_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        target_index=target_index,
    )


# ---------------------------------------------------------------------------
# Requirement: A gate's steps can be reordered (MODIFIED — the supplied
# view of the set)
# ---------------------------------------------------------------------------


async def test_a_supplied_view_is_not_retried_past() -> None:
    """Scenario: A supplied view is not retried past.

    WHEN a reorder supplying the set version its position was computed
    from meets a set that a later accepted write has moved past
    THEN the reorder is rejected without persisting anything
    AND the position is not recomputed and reapplied against the newer
    set.

    The store reads at `SET_VERSION`; the caller supplies the version
    one *behind* it — the view it computed its position against, which a
    later accepted write has moved past. The store's `save()` would
    accept a write made against its current version, so an
    implementation that re-read and recomputed would persist here and
    fail the assertions below: nothing about this store refuses on its
    own.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")
    order_before = _gate_order(store, "listable")

    with pytest.raises(StaleStepSetError):
        await _reorder_pinned(
            store, "listing.beta", 0, expected_version=SET_VERSION - 1
        )

    # SPECIFIED: rejected without persisting anything.
    assert store.saves == []
    # SPECIFIED: the position is not recomputed and reapplied against the
    # newer set — the served order is the set's own, untouched.
    assert _gate_order(store, "listable") == order_before


async def test_a_supplied_view_that_does_not_match_is_refused_either_way() -> None:
    """Scenario: A supplied view that does not match is refused whichever
    way it differs.

    WHEN a reorder supplies a set version that is not the version the
    write reads, and is not an earlier one
    THEN the reorder is rejected without persisting anything.

    The supplied version is one *ahead* of the store's — a value the
    caller cannot hold a view of. An implementation that compares with
    `<` rather than `!=` accepts this and fails here; that asymmetry is
    exactly what the requirement's "whichever way it differs" forecloses.
    """
    store = _store_with_listable("listing.alpha", "listing.beta")
    order_before = _gate_order(store, "listable")

    with pytest.raises(StaleStepSetError):
        await _reorder_pinned(
            store, "listing.beta", 0, expected_version=SET_VERSION + 1
        )

    # SPECIFIED: rejected without persisting anything.
    assert store.saves == []
    assert _gate_order(store, "listable") == order_before


async def test_a_reorder_without_a_supplied_view_still_resolves_concurrency() -> None:
    """Scenario: A reorder without a supplied view still resolves
    concurrency.

    WHEN a reorder supplying no view of the set meets a concurrent
    accepted write
    THEN the write may re-read the set and apply the chosen position
    against it.

    Classification note, recorded in the manifest: the scenario states
    this permissively (*may*), so the *asserted* outcome — that the
    write gets through, having re-read — traces to `tasks.md` 4.2 and
    `design.md`'s *"when absent, keep today's re-read-and-recompute
    behaviour so no existing caller changes meaning"* rather than to the
    scenario's own wording. It is a regression pin against the retry
    being removed wholesale while suppressing it for the supplied-view
    path, which is the change's live failure mode.
    """
    store = _store_with_listable(
        "listing.alpha", "listing.beta", store_class=_ConcurrentThenSettledStore
    )

    await _reorder_unpinned(store, "listing.beta", 0)

    # SPECIFIED (tasks.md 4.2): the write re-read the set rather than
    # giving up — more than one load, and exactly one accepted save.
    assert store.loads >= 2
    assert len(store.saves) == 1
    # SPECIFIED: the chosen position was applied against the set it
    # re-read.
    assert _gate_order(store, "listable") == [
        "listing.beta",
        "hold.listable",
        "listing.alpha",
    ]
