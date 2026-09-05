"""Scope-aware launch reads (`launch-instance`).

Derived strictly from the two MODIFIED requirements in
`openspec/changes/introduce-access-scope/specs/launch-instance/spec.md`:

- *A launch position can be read back by product identifier* (all 3
  scenarios, as revised)
- *Launch positions are enumerable with their reports* (all 4 scenarios, as
  revised)

Every scenario is covered here as revised, not merely the two the change
adds. See `test-manifest.md` at the change root for the accounting,
including the existing tests in
`tests/unit/launch/application/test_launch_reports.py` whose call
convention this change supersedes -- this pass neither edits nor deletes
them.

## Why the application level

The filtering is stated about the read use cases and `design.md` places it
there (Decision 7; `tasks.md` 3.2). Fake stores over real `Launch`
aggregates are the smallest unit that can observe "the store held it and
the read still reported absence", which is what an out-of-scope read must
do. Same collaborators, same fakes, same builders as
`test_launch_reports.py` -- duplicated rather than imported, since this
project shares no test-helper module between test files.

## The store doubles ignore any scope handed to them, deliberately

`_FakeLaunchStore` filters nothing. If an implementation pushed the filter
down into the store port, the double would hand back everything and the
filtering assertions here would fail -- the honest outcome, since
`design.md` puts the filter in the use case. Its methods accept and discard
extra arguments so that a signature mismatch does not fail these tests for
a reason unrelated to what they assert.

## What exists and what does not

`read_launches` exists today; `read_launch`, the `AccessScope` parameter,
and the filtering are what this change adds (`tasks.md` 1.1, 3.2). These
tests are therefore expected to fail on an absent target -- `AccessScope`
does not exist, `read_launch` may not be exported, and the use cases do not
yet take a scope (`_scope_argument` fails by name when they do not). None
of those failures establishes anything about the assertions themselves.

INVENTED, and recorded as unresolved project questions in the manifest:

- `read_launch(launches, playbooks, product_id, ...)`, exported from
  `commerce_ops.launch.application`. `proposal.md` fixes the name and that
  it gains a scope; nothing fixes its argument order or whether it takes
  `as_of`. `_read_launch` below passes `as_of` only when the signature
  declares it, and is the single correction point.
- The record's own attribute spellings (`_ATTRIBUTE_ALIASES`), following
  the same accommodation `test_launch_reports.py` records for the report.
- `AccessScope`'s construction spellings, per
  `tests/unit/shared/domain/test_access_scope.py`.

What must survive unweakened: which launches each read returns, and that an
out-of-scope launch is indistinguishable from a product that has none.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, date, datetime
from typing import Any, Final, cast

import pytest

from commerce_ops.launch.application import read_launch, read_launches
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId, ProductId
from tests.support.fakes import FakeLaunches
from tests.support.fakes import FakePlaybooks as _FakePlaybooks
from tests.support.playbook import CONFIRMATION_GATES
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"
EVIDENCE: Final = "screenshot in the launch Slack thread"
ATTESTER: Final = "Nadia"
ATTESTATION_EVIDENCE: Final = "inventory dashboard export, 2027-01-05"

STOCK_METRIC: Final = MetricId("units-fulfillable")

# DERIVED dates, the construction `test_launch_reports.py` records: a
# -30-day offset is already past on the evaluation date for the at-risk
# launch and still ahead for the healthy one.
AT_RISK_LAUNCH_DATE: Final = date(2027, 4, 15)  # -30 days => 2027-03-16
HEALTHY_LAUNCH_DATE: Final = date(2027, 8, 1)
AS_OF: Final = date(2027, 4, 1)
AT_RISK_STEP_DUE: Final = date(2027, 3, 16)

# INVENTED: see `tests/unit/shared/domain/test_access_scope.py`.
_UNRESTRICTED_NAMES: Final = (
    "unrestricted",
    "UNRESTRICTED",
    "all_products",
    "ALL_PRODUCTS",
    "unrestricted_scope",
)
_EXPLICIT_FACTORY_NAMES: Final = (
    "of",
    "permitting",
    "for_products",
    "restricted_to",
    "explicit",
)

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "product_id": ("product_id",),
    "version": ("version", "playbook_version", "pinned_version"),
    "current_gate": ("current_gate", "gate"),
    "launch_date": ("launch_date", "date"),
    "steps": ("steps", "step_statuses"),
    "at_risk": ("at_risk", "date_at_risk", "launch_date_at_risk"),
    "identifier": ("identifier", "step_id"),
    "due_period": ("due_period", "due"),
    "outcome": ("outcome", "recorded_outcome", "progress"),
    "provenance": ("provenance", "recorded_by", "recording"),
    # No `approvals`/`attestations` entries: a launch report does not carry
    # them, and the persisted round trip that does is tested against the
    # repository -- see the retrieval test's docstring.
}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# Scope construction and passing
# ---------------------------------------------------------------------------


def _unrestricted() -> AccessScope:
    return AccessScope.unrestricted()


def _permitting(*product_ids: ProductId) -> AccessScope:
    return AccessScope.permitting(product_ids)


def _scope_argument(use_case: Any, scope: AccessScope) -> dict[str, Any]:
    """The scope, keyed by whatever the use case calls its scope parameter.

    SPECIFIED, not an accommodation: both requirements state the read takes
    "the caller's access scope", so a use case with no such parameter fails
    here by name rather than being called without one.
    """
    for name, parameter in inspect.signature(use_case).parameters.items():
        if "scope" in name:
            assert parameter.kind is not inspect.Parameter.POSITIONAL_ONLY, (
                f"`{use_case.__name__}`'s scope parameter is positional-only; "
                "pass it positionally instead (a fixture correction)"
            )
            return {name: scope}
    pytest.fail(
        f"`{use_case.__name__}` takes no access-scope parameter, so the "
        "caller's scope cannot reach the read at all"
    )


def _as_of_argument(use_case: Any, as_of: date) -> dict[str, Any]:
    """`as_of`, passed only where the use case declares it.

    `read_launches` takes one; whether the single read does is not fixed by
    any artifact, and inspecting is cheaper than guessing.
    """
    if "as_of" in inspect.signature(use_case).parameters:
        return {"as_of": as_of}
    return {}


# ---------------------------------------------------------------------------
# Builders -- the shapes `test_launch_reports.py` and
# `test_launch_gate_advance.py` already record for this aggregate.
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "gate": "live",
            "discipline": Discipline("listing"),
            "timing_anchor": OffsetAnchor(days=-30),
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires, and anchored a year after launch so a filler
    is never the overdue step an at-risk evaluation is about."""
    return _build_hold(
        gate,
        discipline=Discipline("listing"),
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        name="Work this step asks for",
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return _build_playbook(*steps, filler=_hold)


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who=APPROVER,
        when=RECORDED_AT,
        evidence=EVIDENCE,
    )


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _start(
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = None,
) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    return launch


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    """Walks a launch to `gate`, approving each confirmation gate on the
    way (the walk `test_graduation.py` and `test_launch_reports.py`
    record)."""
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


class _FakeLaunchStore(FakeLaunches):
    """The shared launch store, adapted: this file reads it through its
    own helper. The helpers are rewritten against the shared list, since
    every local kept its launches in a dict keyed by identifier."""

    async def get(
        self, product_id: ProductId, *args: Any, **kwargs: Any
    ) -> Launch | None:
        return cast(
            "Launch | None", await self.get_by_product_id(product_id, *args, **kwargs)
        )


# ---------------------------------------------------------------------------
# Reading a record -- the single correction point for attribute spellings.
# ---------------------------------------------------------------------------


def _read(subject: object, field: str) -> Any:
    for name in _ATTRIBUTE_ALIASES[field]:
        if hasattr(subject, name):
            return getattr(subject, name)
    pytest.fail(
        f"{type(subject).__name__} exposes none of "
        f"{_ATTRIBUTE_ALIASES[field]} for '{field}'; the launch record must "
        "carry it (see the module docstring's INVENTED shapes)"
    )


def _entry_for(record: Any, step_id: str) -> Any:
    entries = [
        entry
        for entry in _read(record, "steps")
        if str(_read(entry, "identifier")) == step_id
    ]
    assert len(entries) == 1, (
        f"expected exactly one entry for step {step_id!r}, got {len(entries)}"
    )
    return entries[0]


async def _read_launch(
    store: _FakeLaunchStore,
    playbooks: _FakePlaybooks,
    product_id: ProductId,
    scope: AccessScope,
) -> Any:
    """The one place to correct if `read_launch`'s call shape differs.

    The call is assembled from the signature rather than guessed: the store
    goes first (this project's port-passing precedent), and every other
    parameter is matched by name -- playbooks, the product identifier, the
    scope, and `as_of` where one is declared. `read_launch` exists today
    and takes neither a scope nor, apparently, a playbook port; building
    the call this way means the scope parameter it gains is the only thing
    that has to be right, whatever its position.
    """
    parameters = inspect.signature(read_launch).parameters
    arguments: dict[str, Any] = {}
    for name in list(parameters)[1:]:
        if "playbook" in name:
            arguments[name] = playbooks
        elif "product" in name or name in ("identifier", "launch_id"):
            arguments[name] = product_id
        elif "scope" in name:
            arguments[name] = scope
        elif name == "as_of":
            arguments[name] = AS_OF
    assert any("product" in name for name in parameters), (
        "`read_launch` takes no product-identifier parameter, so a launch "
        "cannot be read back by the identifier it references"
    )
    # SPECIFIED: the read takes the caller's access scope.
    assert any("scope" in name for name in parameters), (
        "`read_launch` takes no access-scope parameter, so the caller's "
        "scope cannot reach the read at all"
    )
    return await read_launch(store, **arguments)


async def _read_launches(
    store: _FakeLaunchStore, playbooks: _FakePlaybooks, scope: AccessScope
) -> tuple[Any, ...]:
    return tuple(
        await read_launches(
            store,
            playbooks,
            as_of=AS_OF,
            **_scope_argument(read_launches, scope),
        )
    )


def _by_product(records: tuple[Any, ...]) -> dict[ProductId, Any]:
    return {_read(record, "product_id"): record for record in records}


# ---------------------------------------------------------------------------
# Requirement: A launch position can be read back by product identifier
# ---------------------------------------------------------------------------


async def test_a_launch_position_is_retrieved_under_a_permitting_scope() -> None:
    """Requirement: A launch position can be read back by product identifier
    -- the scope half of it.

    WHEN a launch is read on a caller's behalf under a scope that permits
    its product identifier
    THEN the record is returned, carrying the pinned version, current gate,
    launch date, and each step's outcome with its provenance.

    A second launch, whose product the scope does not permit, sits in the
    store so that "returned" is the scope's decision about this launch
    rather than a read ignoring the scope.

    ## Why this does not assert approvals and attestations

    An earlier draft of this test did, reading the requirement's *A launch
    position is retrieved* scenario -- "each approval, and each attestation
    it was persisted with" -- at this level. That scenario is about the
    persisted record's round trip, which the repository satisfies and
    `tests/integration/launch/test_launch_repository.py::
    test_a_launch_is_retrieved_with_its_full_recorded_state` already covers;
    `read_launch` answers with a `LaunchReport`, which has never carried
    approvals. The requirement now says so explicitly ("the
    scope ... SHALL NOT require any particular read to carry the whole
    persisted record"), so this test asserts what this read contracts and
    leaves the round trip where it is tested.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),),
    )
    product_id, other_id = _new_product_id(), _new_product_id()
    launch = _start(playbook, product_id=product_id, launch_date=AT_RISK_LAUNCH_DATE)
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    _advance_to(launch, playbook, "listable")
    hidden = _start(playbook, product_id=other_id, launch_date=HEALTHY_LAUNCH_DATE)
    store = _FakeLaunchStore(launch, hidden)

    record = await _read_launch(
        store, _FakePlaybooks(playbook), product_id, _permitting(product_id)
    )

    assert record is not None
    # SPECIFIED: the pinned version, current gate and launch date.
    assert str(_read(record, "version")) == "test-v1"
    assert str(_read(record, "current_gate")) == "listable"
    assert _read(record, "launch_date") == AT_RISK_LAUNCH_DATE

    # SPECIFIED: each step's outcome and its provenance.
    entry = _entry_for(record, "listing.title-conforms")
    outcome = _read(entry, "outcome")
    assert outcome is not None
    provenance = getattr(entry, "provenance", None) or getattr(
        outcome, "provenance", None
    )
    assert provenance is not None, (
        "the record carries no provenance for the recorded step outcome"
    )
    rendered_provenance = str(provenance)
    assert APPROVER in rendered_provenance
    assert EVIDENCE in rendered_provenance

    # SPECIFIED: the scope's decision is what produced this record, not a
    # read that ignored the scope -- the launch the scope does not permit
    # is not what came back.
    assert _read(record, "product_id") == product_id


@pytest.mark.parametrize("permissive", [True, False], ids=["unrestricted", "empty"])
async def test_a_product_without_a_launch_position_reports_absence(
    permissive: bool,
) -> None:
    """Scenario: A product without a launch position reports absence.

    WHEN a launch record is read for a product identifier that has none,
    under any scope
    THEN the system reports that none exists, rather than an error.

    "Under any scope" is exercised at both ends of the range. Reaching the
    assertion is the "rather than an error" half.
    """
    playbook = _playbook()
    persisted_id, absent_id = _new_product_id(), _new_product_id()
    store = _FakeLaunchStore(
        _start(playbook, product_id=persisted_id, launch_date=AT_RISK_LAUNCH_DATE)
    )
    scope = _unrestricted() if permissive else _permitting()

    record = await _read_launch(store, _FakePlaybooks(playbook), absent_id, scope)

    # SPECIFIED: none exists.
    assert record is None


async def test_an_out_of_scope_launch_reports_the_same_absence() -> None:
    """Scenario: An out-of-scope launch reports the same absence.

    WHEN a launch record is read for a product identifier the caller's
    scope does not permit
    THEN the system reports that none exists, exactly as it does for a
    product with no launch record.

    "Exactly as" is asserted by comparing the two answers to each other, so
    a distinct sentinel, a raised refusal, or a redacted placeholder each
    fail -- a bare falsiness check would let two of the three through.
    """
    playbook = _playbook()
    hidden_id, permitted_id = _new_product_id(), _new_product_id()
    store = _FakeLaunchStore(
        _start(playbook, product_id=hidden_id, launch_date=AT_RISK_LAUNCH_DATE),
        _start(playbook, product_id=permitted_id, launch_date=HEALTHY_LAUNCH_DATE),
    )
    playbooks = _FakePlaybooks(playbook)
    scope = _permitting(permitted_id)

    out_of_scope = await _read_launch(store, playbooks, hidden_id, scope)
    no_such_launch = await _read_launch(store, playbooks, _new_product_id(), scope)

    # SPECIFIED: the same absence.
    assert out_of_scope == no_such_launch
    assert out_of_scope is None
    # DERIVED, so the assertions above cannot pass by everything being
    # absent: the permitted launch is still readable under this scope.
    assert await _read_launch(store, playbooks, permitted_id, scope) is not None


# ---------------------------------------------------------------------------
# Requirement: Launch positions are enumerable with their reports
# ---------------------------------------------------------------------------


async def test_all_launch_positions_are_reported_under_the_unrestricted_scope() -> None:
    """Scenario: All launch positions are reported.

    WHEN several launch positions exist and the launches are enumerated as
    of a date under the unrestricted scope
    THEN every persisted launch position SHALL be reported, each with its
    steps' due periods, recorded progress, and at-risk evaluation as of
    that date.

    The same three launches `test_launch_reports.py` uses for this
    scenario, re-asserted under the unrestricted scope: the delta's clause
    is "under the unrestricted scope every persisted position SHALL be
    reported", so the content assertions still have to hold once a scope is
    in the call.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready", discipline=Discipline("inventory")
            ),
        )
    )
    at_risk_id, healthy_id, resolved_id = (
        _new_product_id(),
        _new_product_id(),
        _new_product_id(),
    )
    at_risk = _start(playbook, product_id=at_risk_id, launch_date=AT_RISK_LAUNCH_DATE)
    healthy = _start(playbook, product_id=healthy_id, launch_date=HEALTHY_LAUNCH_DATE)
    resolved = _start(playbook, product_id=resolved_id, launch_date=AT_RISK_LAUNCH_DATE)
    resolved.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(),
    )

    reports = await _read_launches(
        _FakeLaunchStore(at_risk, healthy, resolved),
        _FakePlaybooks(playbook),
        _unrestricted(),
    )

    by_product = _by_product(reports)
    # SPECIFIED: every persisted launch position, and no more.
    assert set(by_product) == {at_risk_id, healthy_id, resolved_id}
    assert len(reports) == 3

    # SPECIFIED: each with its steps' due periods -- the -30-day offset
    # from 2027-04-15 is the single day 2027-03-16.
    due = _read(
        _entry_for(by_product[at_risk_id], "listing.title-conforms"), "due_period"
    )
    assert due is not None
    assert due.start == AT_RISK_STEP_DUE
    assert due.end == AT_RISK_STEP_DUE

    # SPECIFIED: each with its recorded progress -- per launch, not a
    # playbook-shaped blank.
    recorded = _read(
        _entry_for(by_product[resolved_id], "listing.title-conforms"), "outcome"
    )
    untouched = _read(
        _entry_for(by_product[at_risk_id], "listing.title-conforms"), "outcome"
    )
    assert recorded is not None
    assert recorded != untouched

    # SPECIFIED: each with its at-risk evaluation as of that date.
    assert _read(by_product[at_risk_id], "at_risk")
    assert not _read(by_product[healthy_id], "at_risk")
    assert not _read(by_product[resolved_id], "at_risk")


async def test_a_restricted_scope_enumerates_only_its_launches() -> None:
    """Scenario: A restricted scope enumerates only its launches.

    WHEN several launch positions exist and the launches are enumerated
    under a scope permitting some of their product identifiers but not
    others
    THEN exactly the launch positions of the permitted products SHALL be
    reported.

    Two permitted and one not, so an implementation reporting only the
    first permitted launch fails alongside one that reports everything.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    first_id, second_id, hidden_id = (
        _new_product_id(),
        _new_product_id(),
        _new_product_id(),
    )
    store = _FakeLaunchStore(
        _start(playbook, product_id=first_id, launch_date=AT_RISK_LAUNCH_DATE),
        _start(playbook, product_id=second_id, launch_date=HEALTHY_LAUNCH_DATE),
        _start(playbook, product_id=hidden_id, launch_date=HEALTHY_LAUNCH_DATE),
    )

    reports = await _read_launches(
        store, _FakePlaybooks(playbook), _permitting(first_id, second_id)
    )

    # SPECIFIED: exactly the permitted products' positions.
    assert set(_by_product(reports)) == {first_id, second_id}


async def test_no_launches_yields_an_empty_enumeration() -> None:
    """Scenario: No launches yields an empty enumeration.

    WHEN no launch position exists and the launches are enumerated
    THEN the system SHALL report an empty result, not an error.

    Enumerated under the unrestricted scope, so the empty result cannot be
    explained by the scope permitting nothing -- that is the next
    scenario's job.
    """
    playbook = _playbook()

    reports = await _read_launches(
        _FakeLaunchStore(), _FakePlaybooks(playbook), _unrestricted()
    )

    assert reports == ()


async def test_a_scope_permitting_nothing_enumerates_nothing() -> None:
    """Scenario: A scope permitting nothing enumerates nothing.

    WHEN launch positions exist and the launches are enumerated under a
    scope that permits no product identifier
    THEN the system SHALL report an empty result, not an error.

    Two positions exist, so the empty result is the scope's doing;
    reaching the assertion is the "not an error" half.
    """
    playbook = _playbook()
    store = _FakeLaunchStore(
        _start(playbook, product_id=_new_product_id(), launch_date=AT_RISK_LAUNCH_DATE),
        _start(playbook, product_id=_new_product_id(), launch_date=HEALTHY_LAUNCH_DATE),
    )

    reports = await _read_launches(store, _FakePlaybooks(playbook), _permitting())

    assert reports == ()
