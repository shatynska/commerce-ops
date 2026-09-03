"""The `launch_step_progress` row mapping for a carried finding
(`launch-instance`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-instance/spec.md`

Covers two scenarios of its ADDED requirement *A recording may carry the
finding that produced it* (`tasks.md` 1.5 and 1.9):

- *An unreadable stored finding does not fail the read*
- *A recording made before this capability reads as carrying nothing*

together with the storage half of *An absent finding is distinguishable
from an empty value* and of *A finding with no comment is carried as
such*, both of which the mapping is where an implementation actually goes
wrong (`tasks.md` 2.8).

`tasks.md` groups 1.5 under `tests/unit/launch/domain/`. It is written
here instead: the domain carries no *stored* representation that can be
unreadable and no *read* that could fail, and `tasks.md` 2.8 assigns both
obligations to "Both repositories and their row mappings". Per
`ai-toolkit:testing`'s level rule, the row mapping is the smallest unit
that can observe either. The deviation is recorded in `test-manifest.md`.

The pending-result store's own half of the same rules (`tasks.md` 1.18a)
lives in
`tests/unit/launch/application/test_accepted_result_carried_finding.py`;
both columns against a real Postgres live in
`tests/integration/launch/test_carried_finding_columns_live.py`
(`tasks.md` 1.21). See `test-manifest.md` at the change root for the full
accounting.

## Level

The repository's own read and write, over a fake `AsyncSession` that
answers `get`, `scalars` and `add` — no database. That is the smallest
unit that can observe a *stored* `NULL`, a *stored* unreadable payload,
and a read that must not fail on one. It exercises the real mapping code
rather than a re-implementation of it, which is what distinguishes this
from an assertion about a dict.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- The column is `finding jsonb NULL` on `launch_step_progress`
  (`tasks.md` 2.1; `design.md`, *One `jsonb` column per store*).
- Its payload is `{"field": ..., "value": ..., "comment": ...}`
  (`tasks.md` 2.5).
- `NULL` is the whole of "carries nothing"; an empty value lives inside a
  finding that exists (`design.md`; delta).
- The mapping maps `NULL` to "carries nothing", treats an absent-or-null
  **value** as no finding, keeps an absent **comment** distinct from
  empty text, and reports an unreadable stored finding as none *without
  failing the read* (`tasks.md` 2.8).

INVENTED, each recorded in `test-manifest.md`:

- The ORM attribute name for the column (`_COLUMN_NAMES`), and the
  domain-side attribute for the carried finding (`_FINDING_ATTRS`) — the
  same correction point as
  `tests/unit/launch/domain/test_recorded_finding.py`.
- The keyword `record_step_outcome` accepts (`_FINDING_KWARGS`), likewise.
- Which stored payloads count as "unreadable". The delta names the state
  but no shape, so `_UNREADABLE_PAYLOADS` enumerates what a `jsonb`
  column can hold that is not the three-key object the writer produces.
  Each row is DERIVED; what is SPECIFIED is only that such a row reads as
  carrying none and does not fail the read.
- The fake session, and that `_add_children` is the write mapping's entry
  point.

## Expected first-run state

**Absent target.** `LaunchStepProgress` has no `finding` column and
`StepProgress` no finding to map (`tasks.md` 2.1, 2.5, 2.8), so every
test here is expected to fail through a loud probe or a `TypeError` from
the ORM constructor rejecting an unmapped keyword. Per
`ai-toolkit:testing` that establishes absence and nothing about whether
these assertions are any good.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.domain import launch_run
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
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.models import (
    LaunchGateApproval,
    LaunchPosition,
    LaunchStepProgress,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import STEP_ID
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

ROW_ID: Final = uuid.uuid4()
PRODUCT_ID: Final = ProductId(str(ROW_ID))
WHEN: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

EVIDENCE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards."
FIELD: Final = "sub_category"
VALUE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = "Rejected alternative: Home & Kitchen > Home Decor."

_ABSENT: Final = object()
_UNSET: Final = object()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": "listing.subcategory_advisor",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=("prs_01HQ8Z6M4A",),
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(
        version="finding-rows-v1", gates=_gates(), steps=(_step(STEP_ID), *fillers)
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook, launch_date=None)
    return launch


def _provenance() -> Provenance:
    return Provenance(
        source="automated",
        who="listing.subcategory_advisor",
        when=WHEN,
        evidence=EVIDENCE,
    )


# ---------------------------------------------------------------------------
# Correction points
# ---------------------------------------------------------------------------

_FINDING_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_FINDING_TYPES: Final = (
    "CarriedFinding",
    "RecordedFinding",
    "KeptFinding",
    "Finding",
)
_FINDING_ATTRS: Final = ("finding", "carried_finding", "kept_finding")
#: The ORM attribute the `jsonb` column is assumed to be mapped under.
_COLUMN_NAMES: Final = ("finding", "carried_finding", "kept_finding")


@dataclass(frozen=True)
class _Carried:
    field: Any
    value: Any
    comment: Any


def _carry(field: str, value: Any, comment: Any = _ABSENT) -> Any:
    parts: dict[str, Any] = {"field": field, "value": value}
    if comment is not _ABSENT:
        parts["comment"] = comment
    for name in _FINDING_TYPES:
        found = getattr(launch_run, name, None)
        if isinstance(found, type):
            return found(**parts)
    return parts


def _finding_kwarg() -> str:
    accepted = set(inspect.signature(Launch.record_step_outcome).parameters)
    for name in _FINDING_KWARGS:
        if name in accepted:
            return name
    pytest.fail(
        "`Launch.record_step_outcome` accepts no keyword for a carried "
        f"finding among {list(_FINDING_KWARGS)}; its parameters are "
        f"{sorted(accepted)} — correct `_FINDING_KWARGS`"
    )


def _record(launch: Launch, playbook: LaunchPlaybook, *, finding: Any = _UNSET) -> None:
    kwargs: dict[str, Any] = {
        "step_id": STEP_ID,
        "outcome": Satisfied,
        "provenance": _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg()] = finding
    launch.record_step_outcome(playbook, **kwargs)


def _column_name() -> str:
    mapped = set(LaunchStepProgress.__mapper__.attrs.keys())
    for name in _COLUMN_NAMES:
        if name in mapped:
            return name
    pytest.fail(
        "`LaunchStepProgress` maps no carried-finding column under any of "
        f"{list(_COLUMN_NAMES)}; its columns are {sorted(mapped)} — correct "
        "`_COLUMN_NAMES` to the implemented column"
    )


def _part(raw: Any, key: str) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(key, _ABSENT)
    return getattr(raw, key, _ABSENT)


def _read(progress: Any) -> _Carried | None:
    for name in _FINDING_ATTRS:
        if hasattr(progress, name):
            raw = getattr(progress, name)
            break
    else:
        pytest.fail(
            "a hydrated `StepProgress` exposes no carried finding under any "
            f"of {list(_FINDING_ATTRS)} — correct `_FINDING_ATTRS`"
        )
    if raw is None:
        return None
    comment = _part(raw, "comment")
    return _Carried(
        field=_part(raw, "field"),
        value=_part(raw, "value"),
        comment=_ABSENT if comment is None else comment,
    )


# ---------------------------------------------------------------------------
# A session that holds rows rather than a database
# ---------------------------------------------------------------------------


class _Scalars(list[Any]):
    """What `AsyncSession.scalars` hands back, as far as this repository
    uses it: something iterable."""


class _FakeSession:
    """The narrowest stand-in for `AsyncSession` this repository's read and
    child-write paths touch.

    INVENTED, and the correction point for the harness: `get` answers the
    position row, `scalars` answers by the entity the statement selects,
    and `add` collects what the write mapping produced.
    """

    def __init__(
        self,
        *,
        position: LaunchPosition | None = None,
        progress_rows: tuple[Any, ...] = (),
        approval_rows: tuple[Any, ...] = (),
    ) -> None:
        self.position = position
        self.progress_rows = progress_rows
        self.approval_rows = approval_rows
        self.added: list[Any] = []

    async def get(self, model: Any, key: Any) -> Any:
        if model is LaunchPosition:
            return self.position
        return None

    async def scalars(self, statement: Any) -> _Scalars:
        entity = statement.column_descriptions[0]["entity"]
        if entity is LaunchStepProgress:
            return _Scalars(self.progress_rows)
        if entity is LaunchGateApproval:
            return _Scalars(self.approval_rows)
        return _Scalars()

    def add(self, row: Any) -> None:
        self.added.append(row)


def _as_session(session: _FakeSession) -> AsyncSession:
    """The fake, told to `mypy` it is the port it stands in for.

    A `cast` rather than a subclass: `AsyncSession`'s surface is far
    larger than the three methods this repository's read and child-write
    paths touch, and subclassing it would drag a real engine in.
    """
    return cast("AsyncSession", session)


def _position() -> LaunchPosition:
    return LaunchPosition(
        product_id=ROW_ID,
        playbook_version="finding-rows-v1",
        current_gate="commit",
        launch_date=None,
        submitter=None,
        slack_thread_id=None,
    )


def _progress_row(**overrides: Any) -> LaunchStepProgress:
    attributes: dict[str, Any] = {
        "product_id": ROW_ID,
        "step_id": STEP_ID,
        "outcome_kind": "satisfied",
        "outcome_reason": None,
        "source": "automated",
        "who": "listing.subcategory_advisor",
        "recorded_at": WHEN,
        "evidence": EVIDENCE,
    }
    attributes.update(overrides)
    return LaunchStepProgress(**attributes)


async def _hydrate(row: LaunchStepProgress) -> Any:
    session = _FakeSession(position=_position(), progress_rows=(row,))
    launch = await LaunchRepository(_as_session(session)).get_by_product_id(PRODUCT_ID)
    assert launch is not None, "the repository read no launch back"
    progress = launch.progress_for(STEP_ID)
    assert progress is not None, "the hydrated launch carries no recording"
    return progress


def _written_row(launch: Launch) -> LaunchStepProgress:
    session = _FakeSession()
    LaunchRepository(_as_session(session))._add_children(ROW_ID, launch)
    rows = [row for row in session.added if isinstance(row, LaunchStepProgress)]
    assert len(rows) == 1, f"the write mapping produced {len(rows)} progress rows"
    return rows[0]


# ---------------------------------------------------------------------------
# Scenario: A recording made before this capability reads as carrying
# nothing (tasks.md 1.9)
# ---------------------------------------------------------------------------


async def test_a_null_column_reads_as_carrying_nothing() -> None:
    """WHEN a recording stored before this capability existed is read back
    THEN it reports that it carries no finding, rather than reporting an
    empty one.

    Every row written before the migration has `NULL` here, so this is the
    reading the great majority of stored rows depend on.
    """
    row = _progress_row(**{_column_name(): None})

    progress = await _hydrate(row)

    assert _read(progress) is None
    # Every other fact about the recording is still what the row said.
    assert progress.outcome is Satisfied
    assert progress.provenance.evidence == EVIDENCE
    assert progress.provenance.who == "listing.subcategory_advisor"


async def test_a_stored_empty_value_is_not_a_null_column() -> None:
    """The storage half of *An absent finding is distinguishable from an
    empty value*.

    `NULL` and `{"field": ..., "value": []}` are two different rows and
    must read as two different facts. An implementation that normalised an
    empty value to `NULL` on write, or `NULL` to an empty finding on read,
    passes every other test in this file — which is why both directions
    are asserted, here and in the round-trip test below.
    """
    column = _column_name()
    absent = await _hydrate(_progress_row(**{column: None}))
    empty = await _hydrate(
        _progress_row(**{column: {"field": FIELD, "value": [], "comment": COMMENT}})
    )

    assert _read(absent) is None
    carried = _read(empty)
    assert carried is not None, (
        "a stored finding whose value is `[]` read back as carrying nothing"
    )
    assert carried.field == FIELD
    assert carried.value == []


async def test_a_carried_finding_round_trips_through_the_row() -> None:
    """The write mapping and the read mapping agree.

    Written from a recording that carries a finding, read back from the
    row that write produced — so a column written in one shape and read in
    another is caught here rather than at the page.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, finding=_carry(FIELD, VALUE, COMMENT))

    row = _written_row(launch)
    stored = getattr(row, _column_name())
    assert stored is not None, "the write mapping stored no finding"
    assert _part(stored, "field") == FIELD
    assert _part(stored, "value") == VALUE
    assert _part(stored, "comment") == COMMENT

    carried = _read(await _hydrate(row))
    assert carried is not None
    assert carried.field == FIELD
    assert carried.value == VALUE
    assert carried.comment == COMMENT


async def test_a_recording_carrying_nothing_writes_a_null_column() -> None:
    """The other direction of the same distinction: a recording that
    carries nothing must write `NULL`, never an empty object — `NULL` is
    the whole of "carries nothing" (`design.md`)."""
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook)

    assert getattr(_written_row(launch), _column_name()) is None


async def test_an_empty_value_round_trips_as_a_present_finding() -> None:
    """`tasks.md` 1.3 at the storage boundary: an empty value survives the
    write and comes back as a finding that exists."""
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, finding=_carry(FIELD, [], COMMENT))

    row = _written_row(launch)
    assert getattr(row, _column_name()) is not None, (
        "an empty value was written as `NULL`, collapsing the one "
        "distinction this change exists to draw"
    )
    carried = _read(await _hydrate(row))
    assert carried is not None
    assert carried.value == []


async def test_an_absent_comment_survives_the_row_as_absent() -> None:
    """*A finding with no comment is carried as such*, at the mapping —
    the layer where an absent comment is most easily normalised to `""`.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, finding=_carry(FIELD, VALUE))

    carried = _read(await _hydrate(_written_row(launch)))
    assert carried is not None
    assert carried.comment is _ABSENT, (
        f"an absent comment came back as {carried.comment!r}"
    )


async def test_an_empty_comment_survives_the_row_as_empty() -> None:
    """The counterpart: `""` must not be normalised to absent either."""
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, finding=_carry(FIELD, VALUE, ""))

    carried = _read(await _hydrate(_written_row(launch)))
    assert carried is not None
    assert carried.comment == ""


# ---------------------------------------------------------------------------
# Scenario: An unreadable stored finding does not fail the read
# (tasks.md 1.5)
# ---------------------------------------------------------------------------

#: DERIVED. The delta names the *state* — a stored finding that cannot be
#: read — but no shape. These are what a `jsonb` column can hold that is
#: not the three-key object the writer produces. Each row is an invented
#: instance of a specified rule; what is SPECIFIED is only the outcome.
_UNREADABLE_PAYLOADS: Final = (
    pytest.param("just a string", id="bare-string"),
    pytest.param(17, id="number"),
    pytest.param(True, id="boolean"),
    pytest.param([FIELD, VALUE], id="array"),
    pytest.param({}, id="empty-object"),
    pytest.param({"value": VALUE}, id="no-field"),
    pytest.param({"field": FIELD}, id="no-value"),
    pytest.param({"field": FIELD, "value": None}, id="null-value"),
    pytest.param({"field": None, "value": VALUE}, id="null-field"),
)


@pytest.mark.parametrize("payload", _UNREADABLE_PAYLOADS)
async def test_an_unreadable_stored_finding_does_not_fail_the_read(
    payload: Any,
) -> None:
    """WHEN a recording whose stored finding cannot be read is read back
    THEN it reports carrying no finding, and every other fact about the
    recording is returned.

    "One unreadable row must not deny a reader every other fact about the
    launch." The read must not raise, and the outcome, evidence and
    provenance must all come back — a page that lost a whole launch to one
    malformed column would be the failure the surface exists to prevent.
    """
    row = _progress_row(**{_column_name(): payload})

    progress = await _hydrate(row)

    assert _read(progress) is None, (
        f"the stored payload {payload!r} was read back as a present finding"
    )
    assert progress.outcome is Satisfied
    assert progress.provenance.source == "automated"
    assert progress.provenance.who == "listing.subcategory_advisor"
    assert progress.provenance.when == WHEN
    assert progress.provenance.evidence == EVIDENCE


async def test_an_unreadable_row_does_not_deny_a_readable_one() -> None:
    """The clause's real cost, stated over two steps: an unreadable
    finding on one recording must not take the launch's other recordings
    with it.
    """
    column = _column_name()
    unreadable = _progress_row(**{column: "just a string"})
    readable = _progress_row(
        step_id="hold.commit",
        **{column: {"field": FIELD, "value": VALUE, "comment": COMMENT}},
    )
    session = _FakeSession(position=_position(), progress_rows=(unreadable, readable))

    launch = await LaunchRepository(_as_session(session)).get_by_product_id(PRODUCT_ID)

    assert launch is not None
    assert _read(launch.progress_for(STEP_ID)) is None
    other = _read(launch.progress_for("hold.commit"))
    assert other is not None
    assert other.value == VALUE
