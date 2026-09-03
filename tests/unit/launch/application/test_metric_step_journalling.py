"""A metric step in the journal: an ordinary step outcome, and no kind
of its own.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-journal/spec.md`

Covers the scenarios this change writes or rewrites:

- ADDED requirement *The journal covers every accepted launch command* —
  its new scenario *A metric step's outcome is journaled as a step
  outcome*, and the command list itself, from which "a metric condition
  attested" is struck. The requirement's other nine scenarios carry the
  same words as the REMOVED requirement it replaces and stay covered by
  `tests/unit/launch/application/test_launch_journal_appends.py`, whose
  fixtures this change supersedes (recorded in `test-manifest.md`).
- MODIFIED requirement *An entry carries the labels the occurrence
  concerned* — its new scenario *A metric step is labelled by its name*.
  Its four unchanged scenarios stay covered by that same file.
- MODIFIED requirement *One launch's journal is readable, most recent
  first* — its rewritten scenario *A kind's distinguishing facts are
  absent from an entry of another kind*, whose fact list drops `gate_id`
  because the kind that populated it is gone (`journal.py:104`,
  `tasks.md` 5.5). Its fourteen unchanged scenarios stay covered by
  `tests/unit/launch/application/test_launch_journal_read.py`.
- REMOVED requirement *Every accepted launch command appends exactly one
  journal entry* — asserted as the absence of the `metric-attested` kind
  and of `gate_id` from the entry shape.

## Level

The write use cases over an in-memory journal double, plus one composed
read. What is appended for a command is observable at the use case and
nowhere below it — the aggregate does not know a journal exists — which
is the level `test_launch_journal_appends.py` already holds.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the kind strings (`step-outcome-recorded` and
the rest, as `test_launch_journal_appends.py` records them); that
`metric-attested` and its `gate_id` detail are deleted (`tasks.md` 5.5);
that a step is a step-outcome entry's subject, labelled with the name
the served playbook gave it.

INVENTED: nothing beyond the collaborator doubles and the fact-reading
helpers this directory's sibling files already carry, reproduced here
because the project keeps its test files self-contained.

## Expected first-run state

`StepDefinition` takes no `metric_id`, so the two metric-step scenarios
are expected to fail on an absent target (`TypeError`). The two removal
tests are expected to fail on a wrong value — `metric-attested`, its use
case and `gate_id` all still exist. Per `ai-toolkit:testing` an
absent-target failure establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId, ProductId
from tests.support.fixtures import product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

KIND_STEP_OUTCOME_RECORDED: Final = "step-outcome-recorded"

#: The kind this change removes. Named as a literal so the assertion
#: below states what must not exist rather than reading it from wherever
#: it is declared, which after this change is nowhere.
KIND_METRIC_ATTESTED: Final = "metric-attested"

PRODUCT_ID: Final = product_id()
RECORDED_AT: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 9, 1)
RECORDER: Final = "Dana"

STOCK_METRIC: Final = MetricId("units-fulfillable")

METRIC_STEP: Final = "lp.inventory.040"
METRIC_STEP_NAME: Final = "INVENTORY GATE: 60-80+ units fulfillable before going live"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=0),
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": "fixture.holding_check",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _metric_step() -> StepDefinition:
    return _step(
        identifier=METRIC_STEP,
        name=METRIC_STEP_NAME,
        description=(
            "INVENTORY GATE: do not make the listing live until 60-80, and "
            "hopefully 100+, units are FULFILLABLE - not in transfer, not "
            "reserved, not inbound"
        ),
        gate="stock-ready",
        kind=StepKind.HUMAN,
        handler=None,
        metric_id=STOCK_METRIC,
    )


def _playbook() -> LaunchPlaybook:
    """The eight gates, one holding step each, plus the metric step on
    `stock-ready` — where `launch_playbook.py` authors a condition today
    and where `lp.inventory.040` lands."""
    holds = tuple(
        _step(
            identifier=f"hold.{gate}",
            name=f"Blocking work holding the {gate} gate",
            gate=gate,
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return LaunchPlaybook(
        version="journal-metric-v1", gates=_gates(), steps=(*holds, _metric_step())
    )


def _started(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": RECORDER,
        "when": RECORDED_AT,
        "evidence": "72 fulfillable units confirmed in Seller Central",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


# ---------------------------------------------------------------------------
# Collaborators
# ---------------------------------------------------------------------------


class FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())


class FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self.playbook


class FakeJournal:
    def __init__(self) -> None:
        self.appended: list[Any] = []
        self.rollbacks = 0

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        self.rollbacks += 1


# ---------------------------------------------------------------------------
# Reading an entry's facts without inventing a `details` key
# ---------------------------------------------------------------------------


def _normalised(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _flatten(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [text for held in value.values() for text in _flatten(held)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [text for held in value for text in _flatten(held)]
    return [str(value)]


def _facts(entry: object) -> list[str]:
    values: list[str] = []
    for name in ("subject_id", "subject_label", "actor", "source"):
        held = getattr(entry, name, None)
        if held is not None:
            values.append(str(held))
    values.extend(_flatten(getattr(entry, "details", None)))
    return values


def _names(entry: object, token: object) -> bool:
    needle = _normalised(token)
    return any(needle in _normalised(fact) for fact in _facts(entry))


def _only(journal: FakeJournal) -> Any:
    assert len(journal.appended) == 1, (
        f"expected exactly one appended entry, got {len(journal.appended)}: "
        f"{[getattr(entry, 'kind', entry) for entry in journal.appended]}"
    )
    return journal.appended[0]


async def _record_metric_step(journal: FakeJournal) -> Any:
    playbook = _playbook()
    await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        step_id=METRIC_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )
    return _only(journal)


# ---------------------------------------------------------------------------
# Requirement (ADDED): The journal covers every accepted launch command
# ---------------------------------------------------------------------------


async def test_a_metric_steps_outcome_is_journaled_as_a_step_outcome() -> None:
    """Scenario: A metric step's outcome is journaled as a step outcome.

    WHEN an outcome is recorded for a blocking step declaring a metric
    identifier
    THEN one entry is appended naming the step and the outcome, with no
    kind of its own for the metric.

    "With no kind of its own" is the operative clause: an implementation
    that kept a separate kind for a metric-declaring step would satisfy
    "one entry naming the step and the outcome" and still reintroduce
    the second mechanism this change removes.
    """
    journal = FakeJournal()

    entry = await _record_metric_step(journal)

    # SPECIFIED: one entry, of the ordinary step-outcome kind.
    assert entry.kind == KIND_STEP_OUTCOME_RECORDED
    # SPECIFIED: naming the step and the outcome.
    assert entry.subject_id == METRIC_STEP
    assert _names(entry, "Satisfied"), (
        f"the entry does not name the outcome recorded; the facts it "
        f"carries are {_facts(entry)!r}"
    )
    # SPECIFIED: no kind of its own for the metric — the identifier does
    # not reach the entry as a kind, and no metric-specific kind appears.
    assert entry.kind != KIND_METRIC_ATTESTED


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An entry carries the labels the occurrence
# concerned, captured when it happened
# ---------------------------------------------------------------------------


async def test_a_metric_step_is_labelled_by_its_name() -> None:
    """Scenario: A metric step is labelled by its name.

    WHEN an entry is appended for a blocking step declaring a metric
    identifier
    THEN its label is the name the served playbook gave that step,
    exactly as for any other step.

    Not its identifier and not its metric identifier: the requirement's
    one exception to labelling is a refused advance's condition list, and
    a metric step is not that.
    """
    journal = FakeJournal()

    entry = await _record_metric_step(journal)

    # SPECIFIED: the label is the served playbook's name for the step.
    assert entry.subject_label == METRIC_STEP_NAME
    assert entry.subject_label != METRIC_STEP
    assert entry.subject_label != STOCK_METRIC.value


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): One launch's journal is readable, most recent
# first — and the REMOVED requirement it follows
# ---------------------------------------------------------------------------


async def test_gate_id_leaves_the_entry_shape_with_its_only_populator() -> None:
    """Scenario: A kind's distinguishing facts are absent from an entry of
    another kind — as rewritten, with `gate_id` struck from the list.

    `tasks.md` 5.5 deletes the `metric-attested` kind and the `gate_id`
    entry field, "its only populator". A `gate_id` left on the composed
    entry would be `None` on every entry ever read — a field the read
    contract still promises and nothing can ever fill.

    Asserted over a step-outcome entry, which is a kind that carries none
    of the distinguishing facts named for other kinds.
    """
    journal = FakeJournal()

    entry = await _record_metric_step(journal)

    # SPECIFIED: `gate_id` is no longer part of what an entry carries.
    assert not hasattr(entry, "gate_id"), (
        "the composed entry still carries `gate_id`; `tasks.md` 5.5 removes "
        "it with the only kind that ever populated it"
    )


def test_the_metric_attested_kind_and_its_command_are_gone() -> None:
    """REMOVED requirement *Every accepted launch command appends exactly
    one journal entry*, and `tasks.md` 5.2 / 5.5.

    "The set of commands the launch context accepts no longer includes
    attesting a metric condition." Asserted as the absence of the use
    case on the module's public surface and of the kind in whatever
    vocabulary the journal declares — a kind left declared would leave
    the read side free to keep a branch for rows nothing can write.
    """
    from commerce_ops.launch import application
    from commerce_ops.launch.application import journal as journal_module

    assert not hasattr(application, "record_metric_attestation"), (
        "`record_metric_attestation` is still exported from the launch "
        "module's public surface (`tasks.md` 5.2)"
    )

    declared = " ".join(
        str(getattr(journal_module, name, ""))
        for name in dir(journal_module)
        if not name.startswith("__")
    )
    assert KIND_METRIC_ATTESTED not in declared, (
        f"the journal still declares the {KIND_METRIC_ATTESTED!r} kind; "
        "`tasks.md` 5.5 deletes it, no entry of it having ever been written"
    )
