"""Authoring a step's metric identifier.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/playbook-authoring/spec.md`

Covers:

- ADDED requirement *A step's metric identifier is authorable* — all five
  scenarios.
- MODIFIED requirement *Authoring never touches the framework* — its
  rewritten scenario *The framework is not writable*, whose "or a metric
  condition" clause this delta strikes, and its new scenario *A threshold
  is editable as the step that states it*.
- MODIFIED requirement *A step can be created* — the metric-identifier
  leg of "the full authorable shape", which this delta adds to the list.
  Its four scenarios are otherwise unchanged by this delta and stay
  covered by
  `tests/unit/launch/application/test_playbook_authoring_new_field_set.py`.

## What "no validation SHALL be derived" means here, and what is not tested

`launch-playbook`'s naming paragraph — a lowercase hyphenated noun
phrase naming the quantity — **binds the seed, not this surface**, and
says so: "a write is rejected only on what the shared vocabulary
refuses, and no validation SHALL be derived from this paragraph".

So there is deliberately **no test here that a non-conforming identifier
is rejected**. `test_a_conventionally_wrong_identifier_is_still_accepted`
asserts the opposite, and exists because the absence of a rejection test
is otherwise indistinguishable from the absence of the thought: an
implementer reading the naming convention in the same delta could
reasonably add the validation, and nothing else in this suite would
notice.

## Level

The use cases over a step-store double: what an accepted write hands the
store, and what a rejected one does not. The "next read serves it" halves
are the adapter's and are integration-tier
(`tests/integration/launch/test_playbook_authoring_live.py`). This is the
level `test_playbook_authoring_new_field_set.py` records for the same two
requirements.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- `metric_id` as the field's name, accepted by `create_step` and
  `update_step`, "validated by the shared vocabulary and rejected only on
  its own malformedness" (`tasks.md` 2.4).
- What the shared vocabulary refuses: `MetricId` rejects an empty value
  and one carrying leading or trailing whitespace
  (`tests/unit/shared/domain/test_metric_id.py`), which is exactly the
  scenario's own list.
- `create_step` / `update_step` call shapes, and `REJECTED` as the tuple
  of acceptable refusal types — as
  `test_playbook_authoring_new_field_set.py` records them.

INVENTED: that a write may supply the identifier either as a `MetricId`
or as the string the form submits. The tests below supply a `MetricId`,
which is what `tasks.md` 2.1 types the field as; the invalid-identifier
test supplies the malformed **string**, because a `MetricId` cannot be
constructed from one at all and the rejection must therefore be reachable
from what a surface actually submits. Correction point: `_write_value`.

## Expected first-run state

Neither use case accepts `metric_id` (`tasks.md` 2.4), so every test here
is expected to fail on an absent target — `TypeError` from the unexpected
keyword, or the signature guard reporting the parameter missing. Per
`ai-toolkit:testing` that establishes absence only: none of the
assertions below has been exercised. *The framework is not writable*
fails on the same absence, through its `metric_id in parameters` half;
its gate/opening half is unchanged by this delta and already holds.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import inspect
from typing import Any, Final

import pytest

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
from commerce_ops.shared.domain.identity import MetricId
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "helen"
DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]

ALICE: Final = "prs_01HQ8Z6M4A"
BOHDAN: Final = "prs_01HQ8Z6M4B"

REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)

STOCK_METRIC: Final = MetricId("units-fulfillable")
ANOTHER_METRIC: Final = MetricId("sales-velocity")

#: SPECIFIED (scenario *An invalid metric identifier is rejected*):
#: "empty, or carrying leading or trailing whitespace" — exactly what the
#: shared vocabulary refuses.
MALFORMED_IDENTIFIERS: Final = ("", " units-fulfillable", "units-fulfillable ")

THRESHOLD: Final = (
    "INVENTORY GATE: do not make the listing live until 60-80, and hopefully "
    "100+, units are FULFILLABLE - not in transfer, not reserved, not inbound"
)
REVISED_THRESHOLD: Final = (
    "INVENTORY GATE: do not make the listing live until 100+ units are "
    "FULFILLABLE - not in transfer, not reserved, not inbound"
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
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


class _Member:
    def __init__(self, member_id: str, display_name: str) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = True


class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]:
        return (_Member(ALICE, "Alice Admin"), _Member(BOHDAN, "Bohdan Confirmer"))

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeHandlerRegistry:
    def __contains__(self, name: object) -> bool:
        return name == "price.buy_box_check"

    def __iter__(self) -> Any:
        return iter(("price.buy_box_check",))

    def names(self) -> frozenset[str]:
        return frozenset({"price.buy_box_check"})


def _store(extra: tuple[_Record, ...] = ()) -> _FakeStepStore:
    records = tuple(
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
    return _FakeStepStore(records + extra)


_CREATE_DEFAULTS: Final = {
    "name": "Hold the stock gate until the units are fulfillable",
    "description": None,
    "gate": "stock-ready",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-7),
    "blocking": True,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "hazard": Hazard.NONE,
    "assignees": (ALICE,),
    "handler": None,
}


async def _create(store: _FakeStepStore, **overrides: Any) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(
        steps=store,
        principal=PRINCIPAL,
        members=_FakeMembers(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


async def _update(store: _FakeStepStore, step_id: str, **fields: Any) -> Any:
    return await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id=step_id,
        members=_FakeMembers(),
        handlers=_FakeHandlerRegistry(),
        **fields,
    )


def _created_since(store: _FakeStepStore, before: set[str]) -> Any:
    created = [
        record for record in store.records if record.definition.identifier not in before
    ]
    assert len(created) == 1, f"expected exactly one created record, got {created}"
    return created[0]


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if record.definition.identifier == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _write_value(raw: str) -> Any:
    """What a write supplies for a *malformed* identifier.

    INVENTED — see the module docstring. A `MetricId` cannot be
    constructed from a malformed value at all, so a test that built one
    would fail in its own fixture and establish nothing about the write.
    The raw string is what a form submits, so it is what the rejection
    has to be reachable from.
    """
    return raw


# ---------------------------------------------------------------------------
# Requirement (ADDED): A step's metric identifier is authorable
# ---------------------------------------------------------------------------


async def test_a_step_is_created_declaring_a_metric_identifier() -> None:
    """Scenario: A step is created declaring a metric identifier.

    WHEN a step is created with a metric identifier the shared vocabulary
    accepts
    THEN the write is persisted and the served step reports that
    identifier.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(store, metric_id=STOCK_METRIC, description=THRESHOLD)

    definition = _created_since(store, before).definition
    # SPECIFIED: the served step reports that identifier.
    assert definition.metric_id == STOCK_METRIC
    # SPECIFIED (*A threshold is editable as the step that states it*):
    # the threshold travels as the description, not as a field of its own.
    assert definition.description == THRESHOLD


async def test_a_steps_metric_identifier_is_changed() -> None:
    """Scenario: A step's metric identifier is changed.

    WHEN an update supplies a metric identifier different from the one
    the step carries
    THEN the write is persisted and the served step reports the new
    identifier.
    """
    existing = _Record(
        _step(identifier="mg.strategy.001", gate="stock-ready", metric_id=STOCK_METRIC)
    )
    store = _store(extra=(existing,))

    await _update(store, "mg.strategy.001", metric_id=ANOTHER_METRIC)

    # SPECIFIED: the new identifier is what the step now carries.
    assert _record_named(store, "mg.strategy.001").definition.metric_id == (
        ANOTHER_METRIC
    )
    assert store.saves, "the update persisted nothing"


async def test_a_step_is_created_declaring_no_metric_identifier() -> None:
    """Scenario: A step is created declaring no metric identifier.

    WHEN a step is created supplying no metric identifier
    THEN the write is persisted and the served step reports none.

    Created without the keyword at all, so the write's own default is
    exercised: "almost every step declares none", and a field the write
    made mandatory would reject every other authored step.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(store)

    assert _created_since(store, before).definition.metric_id is None


@pytest.mark.parametrize(
    "malformed",
    [
        pytest.param(MALFORMED_IDENTIFIERS[0], id="empty"),
        pytest.param(MALFORMED_IDENTIFIERS[1], id="leading-whitespace"),
        pytest.param(MALFORMED_IDENTIFIERS[2], id="trailing-whitespace"),
    ],
)
async def test_an_invalid_metric_identifier_is_rejected(malformed: str) -> None:
    """Scenario: An invalid metric identifier is rejected.

    WHEN a write supplies a metric identifier the shared vocabulary
    rejects — empty, or carrying leading or trailing whitespace
    THEN the write is rejected and nothing is persisted.

    The three cases are exactly the vocabulary's own refusals, which is
    what "rejected only on its own malformedness" means: the write adds
    no rule of its own, so anything the vocabulary accepts, it accepts.
    """
    # Guard, not an assertion about the scenario: `TypeError` is among
    # `REJECTED`, so a `create_step` that does not accept `metric_id` at
    # all would satisfy `pytest.raises` for the wrong reason and report
    # coverage where there is none. This keeps the absent-target failure
    # legible as absence.
    assert "metric_id" in set(inspect.signature(create_step).parameters), (
        "`create_step` does not accept `metric_id`, so this test cannot yet "
        "distinguish a rejected malformed identifier from a rejected "
        "unexpected keyword (`tasks.md` 2.4)"
    )
    store = _store()

    with pytest.raises(REJECTED):
        await _create(store, metric_id=_write_value(malformed))

    # SPECIFIED: nothing is persisted.
    assert store.saves == []


async def test_an_identifier_naming_no_defined_metric_is_accepted() -> None:
    """Scenario: An identifier naming no defined metric is accepted.

    WHEN a write supplies a well-formed metric identifier naming a metric
    nothing defines
    THEN the write is persisted, because no registry exists against which
    to resolve it.

    Every metric identifier is in this state today, so the fixture names
    one no artifact of this project mentions — a familiar name could pass
    against an implementation that resolved against a hard-coded list.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}
    invented = MetricId("returns-rate-trailing-thirty-days")

    await _create(store, metric_id=invented)

    assert _created_since(store, before).definition.metric_id == invented


async def test_a_conventionally_wrong_identifier_is_still_accepted() -> None:
    """Requirement statement: "No write SHALL be rejected because the
    metric a valid identifier names is undefined", together with
    `launch-playbook`'s "It binds the seed, not the authoring surface: a
    write is rejected only on what the shared vocabulary refuses, and no
    validation SHALL be derived from this paragraph."

    SPECIFIED, and stated as a positive assertion rather than left as the
    absence of a rejection test. Both values below are the naming
    paragraph's own counterexamples — `stock-ready-units` names the gate,
    `sixty-to-eighty-units` names the threshold's value — and the shared
    vocabulary refuses neither, so the write must not either.
    """
    store = _store()
    before = {record.definition.identifier for record in store.records}

    await _create(store, metric_id=MetricId("stock-ready-units"))

    assert _created_since(store, before).definition.metric_id == (
        MetricId("stock-ready-units")
    )

    second = _store()
    second_before = {record.definition.identifier for record in second.records}
    await _create(second, metric_id=MetricId("sixty-to-eighty-units"))
    assert _created_since(second, second_before).definition.metric_id == (
        MetricId("sixty-to-eighty-units")
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Authoring never touches the framework
# ---------------------------------------------------------------------------


async def test_a_threshold_is_editable_as_the_step_that_states_it() -> None:
    """Scenario: A threshold is editable as the step that states it.

    WHEN a step declaring a metric identifier has its description updated
    through the authoring operations
    THEN the write is validated and persisted like any other step update,
    and the served step carries the new text.

    "Like any other step update" is the point: the threshold is not a
    protected field, and the identifier it sits beside is unaffected by
    editing the text.
    """
    existing = _Record(
        _step(
            identifier="mg.inventory.001",
            gate="stock-ready",
            description=THRESHOLD,
            metric_id=STOCK_METRIC,
        )
    )
    store = _store(extra=(existing,))

    await _update(store, "mg.inventory.001", description=REVISED_THRESHOLD)

    definition = _record_named(store, "mg.inventory.001").definition
    # SPECIFIED: the served step carries the new text...
    assert definition.description == REVISED_THRESHOLD
    # ...and nothing else about the step moved with it.
    assert definition.metric_id == STOCK_METRIC


def test_the_framework_is_not_writable() -> None:
    """Scenario: The framework is not writable — as rewritten.

    WHEN the authoring operations are enumerated
    THEN none of them accepts a gate or an opening mode as a writable
    target.

    The "or a metric condition" clause is struck by this delta, so it is
    deliberately not asserted here: after this change there is no such
    thing to refuse. What replaces it is the positive claim the same
    requirement now makes — "a threshold ... is therefore editable, as the
    description of the step that establishes it" — which the scenario
    above covers.
    """
    for operation in (create_step, update_step):
        parameters = set(inspect.signature(operation).parameters)
        # SPECIFIED: no operation takes the gate sequence or an opening
        # mode as a writable target.
        assert not parameters & {
            "gates",
            "gate_sequence",
            "opening",
            "opening_mode",
        }, f"{operation.__name__} exposes a framework target: {sorted(parameters)}"
        # SPECIFIED (the ADDED requirement): the metric identifier *is* a
        # writable field, so the narrowing is observable rather than
        # merely stated.
        assert "metric_id" in parameters, (
            f"{operation.__name__} does not accept `metric_id`; the delta "
            "makes it a writable field (`tasks.md` 2.4)"
        )
