"""Write use cases of the `playbook-authoring` capability.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/playbook-authoring/spec.md`
with the write half of `launch-playbook`'s MODIFIED requirement
*Playbooks are versioned* (the accepted-write half of *An authored change
changes the served version identifier*).

Covers, at this level, the store-visible halves of every scenario of the
ADDED requirements:

- *A step can be created* — both scenarios' persistence outcomes
  (generated identifier, namespace, authorship provenance).
- *A step can be updated* — all three scenarios.
- *A step can be retired and un-retired* — the persistence outcomes of
  the first and third scenarios (the history scenario's aggregate half
  lives in `tests/unit/launch/domain/test_outcomes_after_retirement.py`).
- *Every write is validated as the playbook it would produce* — all
  three scenarios.
- *Authoring never touches the framework* — its one scenario.

The "the next read of the playbook serves it" halves are the Postgres
adapter's behavior and are covered in
`tests/integration/launch/test_playbook_authoring_live.py`; here the
smallest observable unit is what an accepted write hands the step store
and what a rejected write does not.

## The interface under test does not exist yet, and its shape is INVENTED

Fixed by the artifacts, not invented: the four use-case names
`create_step`, `update_step`, `retire_step`, `unretire_step`, exported
through `commerce_ops.launch.application` (`tasks.md` 4.1–4.5); the
generated-identifier namespace `mg.<discipline>.<seq>` (`tasks.md` 4.1,
spec example `mg.creative.001`); rejection carrying every fault exactly
as loading does (the spec sentence "exactly as loading an incoherent
playbook does" is why `InvalidPlaybookError` — the domain's own
aggregated error — is asserted for coherence rejections).

INVENTED, each recorded in the manifest as an unresolved project
question, with the single correction point named:

- The step-store seam: each use case takes the store as `steps=` plus
  `principal=` (a plain string), mirroring how `advance_gate` takes
  `launches=`/`playbooks=` in `test_graduation.py`. Correction point:
  `_create`/`_update`/`_retire`/`_unretire` below.
- The store protocol `_FakeStepStore`: `load() -> (records, version)`
  and `save(records, *, expected_version)`. Correction point: the fake
  itself.
- The stored-record attribute spellings (`definition`, `created_by`,
  `created_on`, `updated_by`, `updated_on`, `retired_by`, `retired_on`,
  `unretired_by`, `unretired_on`). Correction point: the accessor
  helpers `_definition`/`_is_retired`/etc. below. What must survive any
  correction are the postconditions: what was persisted, what was not,
  and who is recorded as having done what.
- `update_step` accepting the authorable fields as keyword arguments
  (partial update), and the discipline-change rejection surfacing as a
  raised exception — `REJECTED` below is the tuple of acceptable types,
  following the `REJECTED` precedent in
  `tests/integration/launch/test_launch_repository.py`.

## Expected first-run state

`commerce_ops.launch.application` exports none of the four use cases
yet, so every test here is expected to fail on an absent target
(`ImportError`). Per `ai-toolkit:testing` that failure establishes only
absence — the assertions have not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.application import (
    create_step,
    retire_step,
    unretire_step,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

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

PRINCIPAL: Final = "helen"

# A discipline read from the shared vocabulary, plus a second, different
# one for the discipline-change rejection.
DISCIPLINES: Final = tuple(Discipline)
A_DISCIPLINE: Final = DISCIPLINES[0]
ANOTHER_DISCIPLINE: Final = DISCIPLINES[1]

# INVENTED rejection surface for the non-coherence rejections (discipline
# change): the delta fixes the outcome ("the update is rejected and the
# step is unchanged"), not the exception type. Correcting the tuple is a
# fixture correction; the store-unchanged assertion is not.
REJECTED: Final = (InvalidPlaybookError, ValueError, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
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
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": None,
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
        automation_brief="Held until the automated check reports green.",
        handler="fixture.holding_check",
    )


def _holding_steps() -> tuple[StepDefinition, ...]:
    """One blocking step per gate: the minimal set the gate-holding floor
    accepts, so every fixture below starts from a coherent stored set."""
    return tuple(_holding_step(gate) for gate in SPECIFIED_GATE_ORDER)


# ---------------------------------------------------------------------------
# The step store double and record accessors (INVENTED — see docstring)
# ---------------------------------------------------------------------------


class _SeededRecord:
    """A stored step as the seed leaves it: definition plus its
    reference-row citation carried on `definition.provenance`, no
    authoring attribution yet."""

    def __init__(self, definition: StepDefinition) -> None:
        self.definition = definition
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None


class _FakeStepStore:
    """In-memory step-set store with the optimistic set-version.

    `load()` returns every stored record — retired included, per
    `design.md` Decision 4 — together with the current set-version.
    `save()` persists a replacement set conditionally on the version it
    was loaded at, then bumps the version (`design.md` Decision 7).
    """

    def __init__(self, records: tuple[Any, ...], version: int = 41) -> None:
        self.records = records
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


def _seeded_store(extra: tuple[Any, ...] = (), version: int = 41) -> _FakeStepStore:
    records = tuple(_SeededRecord(step) for step in _holding_steps()) + extra
    return _FakeStepStore(records, version=version)


# -- record accessors: the single correction point for attribute
#    spellings (see the module docstring) -----------------------------------


def _definition(record: Any) -> StepDefinition:
    definition: StepDefinition = record.definition
    return definition


def _identifier(record: Any) -> str:
    return _definition(record).identifier


def _is_retired(record: Any) -> bool:
    """Read off the *status*, not the attribution.

    `redesign-step-fields` (design.md Decision 2) made the status the one
    answer to "is this step in play"; the attribution columns stay,
    recording who moved the step and when."""
    return record.definition.status is StepStatus.RETIRED


def _is_active(record: Any) -> bool:
    """Whether the step is served — and so whether it holds a slot."""
    return record.definition.status is StepStatus.ACTIVE


def _record_named(store: _FakeStepStore, identifier: str) -> Any:
    for record in store.records:
        if _identifier(record) == identifier:
            return record
    pytest.fail(f"no stored record carries identifier {identifier!r}")


def _live_definitions(store: _FakeStepStore) -> tuple[StepDefinition, ...]:
    return tuple(
        _definition(record) for record in store.records if not _is_retired(record)
    )


# -- use-case call shapes: the single correction point ----------------------


_CREATE_DEFAULTS: Final = {
    "name": "Refresh the hero image ahead of ignition",
    "gate": "ignition",
    "discipline": A_DISCIPLINE,
    "scope": Scope.PRODUCT,
    "timing_anchor": OffsetAnchor(days=-3),
    "blocking": False,
    "kind": StepKind.HUMAN,
    "status": StepStatus.ACTIVE,
    "needs_confirmation": False,
    "hazard": Hazard.NONE,
    "automation_brief": None,
}


async def _create(store: _FakeStepStore, **overrides: Any) -> Any:
    fields = {**_CREATE_DEFAULTS, **overrides}
    return await create_step(steps=store, principal=PRINCIPAL, **fields)


async def _update(store: _FakeStepStore, step_id: str, **fields: Any) -> Any:
    return await update_step(
        steps=store, principal=PRINCIPAL, step_id=step_id, **fields
    )


async def _retire(store: _FakeStepStore, step_id: str) -> Any:
    return await retire_step(steps=store, principal=PRINCIPAL, step_id=step_id)


async def _unretire(store: _FakeStepStore, step_id: str) -> Any:
    return await unretire_step(steps=store, principal=PRINCIPAL, step_id=step_id)


# ---------------------------------------------------------------------------
# Requirement: A step can be created
# ---------------------------------------------------------------------------


async def test_a_created_step_is_persisted_with_identifier_and_authorship() -> None:
    """Scenario: A created step joins the served set — the write half.

    WHEN a step is created with valid authorable fields
    THEN the persisted set carries it under a generated identifier whose
    second segment is its discipline
    AND its provenance records who created it and when.

    The serving half ("the next read of the playbook serves it") is
    integration-tier, in `test_playbook_authoring_live.py`.
    """
    store = _seeded_store()
    before = {_identifier(record) for record in store.records}

    await _create(store, discipline=A_DISCIPLINE)

    created = [record for record in store.records if _identifier(record) not in before]
    assert len(created) == 1
    record = created[0]

    definition = _definition(record)
    # SPECIFIED: the system generates the identifier — `mg.<discipline>.
    # <seq>` (tasks.md 4.1) — with the discipline as its second segment.
    assert re.fullmatch(r"mg\.[^.]+\.\S+", definition.identifier), definition.identifier
    assert definition.identifier.split(".")[1] == A_DISCIPLINE.value
    # The authorable fields round-trip as given.
    assert definition.name == _CREATE_DEFAULTS["name"]
    assert definition.gate == "ignition"
    # SPECIFIED: provenance records the authoring principal and date.
    assert record.created_by == PRINCIPAL
    assert record.created_on is not None


async def test_created_identifiers_never_collide_retired_included() -> None:
    """Scenario: Created identifiers never collide with the seeded
    namespace.

    WHEN a step is created
    THEN its generated identifier is not in the seeded set's namespace
    and equals no existing step's identifier, retired steps included.
    """
    live_authored = _SeededRecord(
        _step(
            identifier=f"mg.{A_DISCIPLINE.value}.001",
            name="An earlier authored step",
            gate="ignition",
        )
    )
    retired_authored = _SeededRecord(
        _step(
            identifier=f"mg.{A_DISCIPLINE.value}.002",
            name="A retired authored step",
            gate="ignition",
            status=StepStatus.RETIRED,
        )
    )
    retired_authored.retired_by = "olena"
    retired_authored.retired_on = "2026-08-01"
    store = _seeded_store(extra=(live_authored, retired_authored))
    before = {_identifier(record) for record in store.records}

    await _create(store, discipline=A_DISCIPLINE)

    created = [record for record in store.records if _identifier(record) not in before]
    assert len(created) == 1
    identifier = _identifier(created[0])
    # SPECIFIED: outside the seeded namespace...
    assert not identifier.startswith("lp.")
    # ...and colliding with nothing, the retired identifier included.
    assert identifier not in before


# ---------------------------------------------------------------------------
# Requirement: A step can be updated
# ---------------------------------------------------------------------------


async def test_an_update_replaces_fields_under_the_unchanged_identifier() -> None:
    """Scenario: An edit is served on the next read — the write half.

    WHEN a step's description is updated
    THEN the persisted set carries the step with the new description
    under its unchanged identifier.
    """
    store = _seeded_store()

    await _update(store, "hold.ignition", name="Hold ignition until QA signs off")

    record = _record_named(store, "hold.ignition")
    assert _definition(record).name == "Hold ignition until QA signs off"


async def test_a_discipline_change_is_rejected() -> None:
    """Scenario: A discipline change is rejected.

    WHEN an update attempts to change a step's discipline
    THEN the update is rejected and the step is unchanged.
    """
    store = _seeded_store()
    before = _definition(_record_named(store, "hold.ignition"))

    with pytest.raises(REJECTED):
        await _update(store, "hold.ignition", discipline=ANOTHER_DISCIPLINE)

    # SPECIFIED: the step is unchanged — nothing was persisted.
    assert store.saves == []
    after = _definition(_record_named(store, "hold.ignition"))
    assert after.discipline == before.discipline
    assert after == before


async def test_an_edit_to_a_seeded_step_keeps_its_citation_and_is_attributed() -> None:
    """Scenario: An edit to a seeded step keeps its citation and gains
    attribution.

    WHEN a seeded step is updated
    THEN its provenance still carries the reference row's source citation
    AND the update's principal and date are recorded.
    """
    seeded = _SeededRecord(
        _step(
            identifier=f"lp.{A_DISCIPLINE.value}.008",
            name="The reference row's own wording",
            gate="listable",
            provenance="product-launch.md · BUILD THE LISTING · row 8",
        )
    )
    store = _seeded_store(extra=(seeded,))

    await _update(
        store,
        seeded.definition.identifier,
        name="The reference row's wording, corrected",
    )

    record = _record_named(store, f"lp.{A_DISCIPLINE.value}.008")
    definition = _definition(record)
    assert definition.name == "The reference row's wording, corrected"
    # SPECIFIED: the seed citation survives the edit...
    assert definition.provenance == "product-launch.md · BUILD THE LISTING · row 8"
    # ...while the edit itself is attributed.
    assert record.updated_by == PRINCIPAL
    assert record.updated_on is not None


# ---------------------------------------------------------------------------
# Requirement: A step can be retired and un-retired
# ---------------------------------------------------------------------------


async def test_retiring_marks_the_step_and_deletes_nothing() -> None:
    """Scenario: A retired step leaves the served set — the write half.

    WHEN a step is retired
    THEN its stored definition and identifier persist, with the
    retirement's principal and date recorded — no operation deletes a
    step.

    The serving half ("the next read does not serve it") is
    integration-tier.
    """
    extra = _SeededRecord(
        _step(
            identifier="listing.a-plus-content",
            name="Optional A+ content ahead of launch",
            gate="listable",
            blocking=False,
        )
    )
    store = _seeded_store(extra=(extra,))
    count_before = len(store.records)

    await _retire(store, "listing.a-plus-content")

    # SPECIFIED: retired, never deleted — the record and identifier stay.
    assert len(store.records) == count_before
    record = _record_named(store, "listing.a-plus-content")
    assert _is_retired(record)
    assert record.retired_by == PRINCIPAL
    assert record.retired_on is not None


async def test_unretiring_restores_the_step_and_is_attributed() -> None:
    """Scenario: An un-retired step rejoins the served set — the write
    half.

    WHEN a retired step is un-retired
    THEN it is no longer marked retired, under its original identifier,
    and the un-retirement's principal and date are recorded.
    """
    retired = _SeededRecord(
        _step(
            identifier="listing.a-plus-content",
            name="Optional A+ content ahead of launch",
            gate="listable",
            blocking=False,
            status=StepStatus.RETIRED,
        )
    )
    retired.retired_by = "olena"
    retired.retired_on = "2026-08-01"
    store = _seeded_store(extra=(retired,))

    await _unretire(store, "listing.a-plus-content")

    record = _record_named(store, "listing.a-plus-content")
    assert not _is_retired(record)
    # SPECIFIED: a reversal of retirement is as attributed as the
    # retirement was.
    assert record.unretired_by == PRINCIPAL
    assert record.unretired_on is not None


# ---------------------------------------------------------------------------
# Requirement: Every write is validated as the playbook it would produce
# ---------------------------------------------------------------------------


async def test_retiring_a_gates_last_blocking_step_is_rejected() -> None:
    """Scenario: Retiring a gate's last blocking step is rejected.

    WHEN a retire targets the only blocking step attached to a gate
    THEN the write is rejected, naming the gate that would be left unheld.
    """
    store = _seeded_store()  # every gate held by exactly one blocking step

    with pytest.raises(InvalidPlaybookError) as caught:
        await _retire(store, "hold.live")

    # SPECIFIED: the rejection names the gate, per the gate-holding floor.
    assert "live" in str(caught.value)
    assert store.saves == []
    assert not _is_retired(_record_named(store, "hold.live"))


async def test_the_set_after_accepted_writes_loads_coherently() -> None:
    """Scenario: What a write cannot persist, a load cannot see.

    WHEN a sequence of accepted writes has been applied
    THEN loading the playbook succeeds — the served set is coherent by
    construction.

    "Loading" here is what the adapter does on read (`tasks.md` 3.1):
    constructing `LaunchPlaybook` from the live stored definitions and
    the code-owned gates. Interleaved concurrent writes are out of this
    test's reach and are recorded as deliberately untested in the
    manifest (`design.md` Decision 7's race is not deterministically
    observable through this seam).
    """
    store = _seeded_store()
    before = {_identifier(record) for record in store.records}

    await _create(store, name="First authored step", gate="ignition")
    created_id = next(
        _identifier(record)
        for record in store.records
        if _identifier(record) not in before
    )
    await _update(store, created_id, name="First authored step, reworded")
    await _create(store, name="Second authored step", gate="commit")
    await _retire(store, created_id)

    playbook = LaunchPlaybook(
        version=f"set-v{store.version}",
        gates=_gates(),
        steps=_live_definitions(store),
    )
    served_ids = {step.identifier for step in playbook.steps}
    assert created_id not in served_ids


async def test_an_accepted_write_persists_conditionally_on_the_loaded_version() -> None:
    """Requirement statement (*Playbooks are versioned*, MODIFIED): the
    served version "is, or is derived from, the step-set version that
    serializes writes".

    WHEN a write is accepted
    THEN it persists exactly once, conditionally on the set-version it
    loaded — the mechanism `design.md` Decision 7 fixes. The
    version-identifier change across *reads* is asserted at the
    integration tier (*An authored change changes the served version
    identifier*).
    """
    store = _seeded_store(version=41)

    await _create(store)

    assert len(store.saves) == 1
    _, expected_version = store.saves[0]
    assert expected_version == 41


# ---------------------------------------------------------------------------
# Requirement: Authoring never touches the framework
# ---------------------------------------------------------------------------


async def test_the_authoring_surface_offers_no_framework_write() -> None:
    """Scenario: The framework is not writable.

    WHEN the authoring operations are enumerated
    THEN none of them accepts a gate, an opening mode, or a metric
    condition as a writable target.

    Read as two checks over the public surface (`tasks.md` 4.5 makes
    `application/__init__.py` the whole doorway): the authoring
    operations are exactly the four step writes, and no exported
    operation names a framework element as its write target. A step's
    own `gate` attachment is an authorable *step* field (the spec's
    "full authorable shape" includes it) and is not a framework write.
    """
    exported = set(launch_application.__all__)

    # SPECIFIED (tasks.md 4.5): the four step writes are the authoring
    # surface.
    assert {"create_step", "update_step", "retire_step", "unretire_step"} <= exported

    # DERIVED enumeration: no exported name pairs a write verb with a
    # framework noun (gates, opening modes, metric conditions).
    framework_writes = [
        name
        for name in exported
        if re.match(r"(create|update|retire|unretire|delete|remove|set)_", name)
        and re.search(r"gate|opening|metric|condition", name)
    ]
    assert framework_writes == []

    # DERIVED signature check: no step-write operation takes the gate
    # sequence, an opening mode, or metric conditions as a parameter.
    import inspect

    for operation in (create_step, update_step, retire_step, unretire_step):
        parameters = set(inspect.signature(operation).parameters)
        assert not parameters & {
            "gates",
            "gate_sequence",
            "opening",
            "opening_mode",
            "metric_condition",
            "metric_conditions",
        }, f"{operation.__name__} exposes a framework target: {sorted(parameters)}"
