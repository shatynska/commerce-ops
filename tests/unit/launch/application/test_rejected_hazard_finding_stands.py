"""A rejected proposal leaves the value the screening already wrote
(`product-catalog`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/product-catalog/spec.md`

Covers, from the ADDED requirement *A recorded hazard-category set is what
a screening established, not what a member ratified*, the two scenarios
stated over a member's decision:

- A rejected proposal's recorded value stands
- A rejected clear reading is still a screening, not an open question

The requirement's third scenario, *A later screening replaces a disputed
value*, is covered where the replacement actually happens — at the
recording level, in
`tests/unit/catalog/domain/test_product_hazard_categories.py`. Recorded
rather than silently omitted.

`tasks.md` 1.17.

## Why this file exists at all

**This requirement is satisfied by the system doing nothing**, which is
exactly why it needs a guard. `tasks.md` 1.17 says so: "it has no
implementation task to hang a guard on; without this row a later author
adding reconciliation breaks nothing the suite notices."

So the assertions are made in two directions, and the second is what
gives the first teeth:

1. **The value is unchanged after the rejection.** Read back off the
   product the screening wrote to.
2. **The rejection path is given no route to the product at all.** The
   decision use case is asked what collaborators it accepts, and a
   catalog store or a finding recorder among them is a failure. A future
   erase-on-rejection would have to add one, and adding one is what this
   assertion catches — before the behaviour it enables is ever written.

Both are asserted for a **non-empty** recorded set and, separately, for a
**recorded empty** one. The empty case is the one where an
erase-on-rejection implementation looks superficially correct: erasing
`{}` produces `None`, which reads as "nothing here" either way unless the
two are compared.

## Level

The application tier: the reject use case over in-memory doubles, beside
a real `Product` carrying the recorded set. That is where a rejection
actually happens, and the smallest unit that can observe both directions
above. Fixtures are duplicated from
`test_accepted_result_carried_finding.py` rather than imported, per this
project's convention and this pass's additive-only rule.

## What is fixed, and what is INVENTED

Fixed by the delta: that a value recorded from a proposal a member later
rejected **stands**; that a rejected clear reading still reports as
recorded-and-empty rather than as never recorded; and that "this
capability builds no mechanism that reaches back into a value on a
decision's behalf".

INVENTED, recorded in `test-manifest.md`: the decision use case's
exported name (probed over `_REJECT_NAMES`), its call shape, the doubles
and the fixture identities — all inherited from
`test_accepted_result_carried_finding.py`'s own documented assumptions.
`_PRODUCT_REACHING_COLLABORATORS` is this file's own: the names a route to
the catalog would plausibly arrive under, and the correction point if a
legitimate one is added for an unrelated reason.

## Expected first-run state

`Product.record_hazard_categories` does not exist (`tasks.md` 3.1), so
every test here is expected to fail on an absent target —
`AttributeError` while building the fixture product. Per
`ai-toolkit:testing` that establishes absence only.

Once the domain method lands, these are expected to **pass without any
further implementation**, because the requirement is satisfied by the
system doing nothing. That is the intended outcome, not a sign the rows
are worthless: they are the guard on an absence.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import inspect
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import pytest

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch import application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
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
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
STEP_ID: Final = "lp.strategy.006"
HANDLER_NAME: Final = "strategy.compliance_screen"

ALICE: Final = "prs_01HQ8Z6M4A"
ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Admin"

LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

SCREEN_TEXT: Final = (
    "Verdict: clear. Screened against the FBA-prohibited hazmat list and "
    "high-compliance categories."
)
FIELD: Final = "hazard_categories"
FLAGGED: Final = ("supplements", "medical devices")
EMPTY: Final[tuple[str, ...]] = ()

_KEPT_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_ABSENT: Final = object()

#: INVENTED. The names a route from the decision use case to the catalog
#: would plausibly arrive under. The delta forbids the mechanism, not any
#: particular spelling, so this is a probe and its correction point is
#: here — but a *legitimate* addition to this list should be argued for,
#: not made silently, since that is the change the requirement forbids.
_PRODUCT_REACHING_COLLABORATORS: Final = (
    "recorders",
    "finding_recorders",
    "record_finding",
    "catalog",
    "catalog_store",
    "products",
    "product_store",
    "record_hazard_categories",
    "record_sub_category",
    "erase_finding",
    "reconcile",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — duplicated from test_accepted_result_carried_finding.py
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
        "name": "Screen for prohibited and high-compliance categories",
        "description": None,
        "gate": "listable",
        "discipline": Discipline("strategy"),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "confirmer": ALICE,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
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
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(_step(), *fillers))


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — duplicated
# ---------------------------------------------------------------------------


@dataclass
class _Member:
    id: str
    display_name: str
    slack_identity: str
    active: bool = True
    clickup_user_id: str | None = None
    admin: bool = False


class _FakeMembers:
    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


def _members() -> _FakeMembers:
    return _FakeMembers(
        _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
    )


class _PendingRow:
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    delivered_at: datetime | None

    def __init__(self, *, finding: Any = None, **attributes: Any) -> None:
        for key, value in attributes.items():
            setattr(self, key, value)
        for name in _KEPT_KWARGS:
            setattr(self, name, finding)
        self.state = "pending"
        self.decided_by: str | None = None
        self.decided_at: datetime | None = None


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
        return None

    def _row_of(self, row: object) -> _PendingRow:
        for candidate in self.rows:
            if candidate is row:
                return candidate
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

    @property
    def only(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected one recording, got {self.calls}"
        return self.calls[0]


def _stored_finding(value: Any) -> dict[str, Any]:
    """A finding as the pending-result store holds it."""
    return {
        "field": FIELD,
        "value": list(value),
        "comment": "None of the named categories applies to this product.",
    }


def _pending(finding: Any = None) -> _PendingRow:
    return _PendingRow(
        finding=finding,
        product_id=PRODUCT_ID,
        step_id=STEP_ID,
        handler=HANDLER_NAME,
        proposed_outcome=Satisfied,
        result_text=SCREEN_TEXT,
        produced_at=PRODUCED_AT,
        delivered_at=PRODUCED_AT + timedelta(seconds=2),
    )


@dataclass
class _Collaborators:
    results: _FakeResults
    members: _FakeMembers
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    recorder: _RecordingOutcomes


def _setup(finding: Any = None) -> _Collaborators:
    playbook = _playbook()
    return _Collaborators(
        results=_FakeResults(_pending(finding)),
        members=_members(),
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        recorder=_RecordingOutcomes(),
    )


# ---------------------------------------------------------------------------
# The product the screening already wrote to
# ---------------------------------------------------------------------------


def _screened(categories: tuple[str, ...], sku: str) -> Product:
    """A product a screening has already recorded a set against — the
    provisional write `launch-step-automation` makes when the handler
    runs, before any confirmation is sought."""
    product = Product.register(
        sku=Sku(sku),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Bamboo Cutting Board",
        registered_at=T_REGISTERED,
    )
    product.record_hazard_categories(categories)
    return product


def _reading(product: Product) -> Any:
    return product.hazard_categories


def _members_of(product: Product) -> list[str]:
    reading = _reading(product)
    assert reading is not None, (
        "the product reports its hazard categories as never recorded"
    )
    return list(reading)


# ---------------------------------------------------------------------------
# The decision, reached through one correction point
# ---------------------------------------------------------------------------

_REJECT_NAMES: Final = (
    "reject_automated_result",
    "reject_pending_result",
    "reject_result",
)


def _reject_use_case() -> Any:
    for name in _REJECT_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no rejection use case is exported from "
        f"`commerce_ops.launch.application` under any of {list(_REJECT_NAMES)}"
    )


async def _reject(collaborators: _Collaborators) -> Any:
    use_case = _reject_use_case()
    supplied: dict[str, Any] = {
        "results": collaborators.results,
        "members": collaborators.members,
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "record_outcome": collaborators.recorder,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }
    accepted = set(inspect.signature(use_case).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the rejection use case does not accept {unknown}; correct `_reject`"
    )
    return await use_case(**supplied)


def _assert_rejected(collaborators: _Collaborators, decision: Any) -> None:
    """Every fact a rejection is obliged to produce.

    Asserted alongside each scenario below so the "value unchanged" claim
    is made about a rejection that actually happened, rather than about a
    call that refused and did nothing.
    """
    assert getattr(decision, "refused", True) is False, (
        f"the rejection was refused: {getattr(decision, 'reason', decision)!r}"
    )
    assert isinstance(collaborators.recorder.only["outcome"], Blocked)
    assert collaborators.results.only.state == "rejected"
    assert collaborators.results.only.decided_at == DECIDED_AT


# ---------------------------------------------------------------------------
# Scenario: A rejected proposal's recorded value stands
# ---------------------------------------------------------------------------


async def test_a_rejected_proposals_recorded_value_stands() -> None:
    """Scenario: A rejected proposal's recorded value stands.

    WHEN a screening records a set of hazard categories for a product and
    a member subsequently rejects the pending result that screening
    proposed
    THEN reading the product back still reports the recorded set,
    unchanged by the rejection.

    "The rejection is a decision about the *step* … and this capability
    does not hold a record of steps."
    """
    product = _screened(FLAGGED, "HAZ-REJECT-01")
    collaborators = _setup(_stored_finding(FLAGGED))

    decision = await _reject(collaborators)

    _assert_rejected(collaborators, decision)
    assert _members_of(product) == list(FLAGGED), (
        "the rejection changed the set the screening recorded on the product"
    )


async def test_a_rejected_clear_reading_is_still_a_screening() -> None:
    """Scenario: A rejected clear reading is still a screening, not an open
    question.

    WHEN a screening records an empty set for a product and a member
    subsequently rejects the pending result it proposed
    THEN reading the product back reports the hazard categories as
    recorded and empty, not as never recorded.

    **The row an erase-on-rejection implementation looks correct on.**
    Erasing `{}` produces "never recorded", which reads as nothing much
    unless it is compared against a product that really was never
    screened — which is what the second assertion does. Without it, the
    delta's whole reason for this requirement ("it would leave the product
    reporting the question as *open* after it had demonstrably been
    screened") is untested.
    """
    product = _screened(EMPTY, "HAZ-REJECT-02")
    never_screened = Product.register(
        sku=Sku("HAZ-NEVER-02"),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Bamboo Cutting Board",
        registered_at=T_REGISTERED,
    )
    collaborators = _setup(_stored_finding(EMPTY))

    decision = await _reject(collaborators)

    _assert_rejected(collaborators, decision)
    assert _members_of(product) == []
    assert _reading(product) != _reading(never_screened), (
        "after the rejection the product reports the question as open, "
        "though it had demonstrably been screened — the one confusion the "
        "three-state rule exists to prevent"
    )


# ---------------------------------------------------------------------------
# "A rejection SHALL be answerable by a later screening, not by a
# reconciliation" — the guard on the absence
# ---------------------------------------------------------------------------


def test_the_rejection_path_is_given_no_route_to_the_product() -> None:
    """The requirement's closing clause: "this capability builds no
    mechanism that reaches back into a value on a decision's behalf".

    SPECIFIED as a prohibition, asserted structurally because there is no
    behaviour to observe: a rejection that leaves a value alone and a
    rejection that could not reach it are indistinguishable from the
    outside, and only the second is what the delta requires.

    A future erase-on-rejection would have to give this use case a way to
    the catalog. That is what this catches — before the behaviour it
    enables exists.
    """
    accepted = set(inspect.signature(_reject_use_case()).parameters)

    reaching = sorted(accepted & set(_PRODUCT_REACHING_COLLABORATORS))
    assert not reaching, (
        "the rejection use case accepts "
        f"{reaching}, which is a route from a member's decision back into "
        "the product's recorded value. `product-catalog` states that the "
        "correction path is a subsequent screening or a direct recording, "
        "and that no mechanism reaches back on a decision's behalf"
    )


async def test_a_later_screening_is_what_replaces_a_disputed_value() -> None:
    """*A later screening replaces a disputed value*, asserted here in the
    half this file owns: the replacement is performed by the screening,
    and the earlier decision performed none of it.

    The recording half — that a later recording replaces wholesale — is in
    `tests/unit/catalog/domain/test_product_hazard_categories.py`. What is
    added here is the sequencing: reject first, observe no change, then
    record and observe the change.
    """
    product = _screened(FLAGGED, "HAZ-REJECT-03")
    collaborators = _setup(_stored_finding(FLAGGED))

    decision = await _reject(collaborators)

    _assert_rejected(collaborators, decision)
    assert _members_of(product) == list(FLAGGED)

    product.record_hazard_categories(EMPTY)

    assert _members_of(product) == [], (
        "the later screening did not replace the disputed value"
    )
