"""A carried finding travels on the launch report (`launch-instance`).

Derived strictly from the delta spec of the change
`separate-the-result-from-the-comment`:
`openspec/changes/separate-the-result-from-the-comment/specs/launch-instance/spec.md`

Covers one scenario of its ADDED requirement *A recording may carry the
finding that produced it* (`tasks.md` 1.8):

    #### Scenario: A carried finding reaches the launch report
    - **WHEN** a launch report is produced for a launch whose step
      recording carries a finding
    - **THEN** that step's entry on the report carries the finding,
      without a consumer re-deriving it

The requirement's other eight scenarios live in
`tests/unit/launch/domain/test_recorded_finding.py` and
`tests/unit/launch/infrastructure/driven/test_launch_progress_finding_rows.py`.
See `test-manifest.md` at the change root for the full accounting.

## Level

The application tier, per `tasks.md` 1.8's own instruction — "assert
against the report, not against the page — the page reads only what the
report carries". `read_launch` over fakes is the smallest unit that can
observe a report at all, which is the level
`test_launch_report_step_facts.py` established for exactly this question.

`design.md` records (Context) that the report's step entry already
carries the recording whole, so this scenario may be satisfied by
`ReportedStep.progress` with no new projection. That is a fact about the
*implementation route*, not about the assertion: the delta states the
report obligation explicitly, and this test asserts it explicitly, so a
later change that swapped `progress` for a narrowed projection would be
caught rather than silently dropping the finding.

## What is fixed, and what is INVENTED

Fixed: that the finding travels on the step entry the recording belongs
to, and that a consumer does not re-derive it.

INVENTED, and recorded in `test-manifest.md`:

- How a recording is given a finding, and how a carried finding is
  spelled — the same two correction points as
  `tests/unit/launch/domain/test_recorded_finding.py`, duplicated here
  rather than imported because this project shares no test-helper module
  between test files.
- **How the report exposes it.** `_reported_finding()` accepts either
  route: the finding read off the entry's own `progress`, or a finding
  carried directly on the entry. Both satisfy the scenario; neither is
  fixed by an artifact.
- The fakes, the fixture playbook and the dates, carried from
  `test_launch_report_step_facts.py`'s own documented assumptions.

## Expected first-run state

**Absent target.** No recording can carry a finding today, so this test
is expected to fail through `_finding_kwarg()`'s loud probe. Per
`ai-toolkit:testing` that establishes absence and nothing more.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2167 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 137 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import read_launch
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
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import STEP_ID, product_id
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
OTHER_STEP_ID: Final = "listing.title-drafted"
AS_OF: Final = date(2027, 1, 6)
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


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(identifier: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": identifier,
        "name": f"Work {identifier} asks for",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
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
    return _build_hold(
        gate,
        assignees=("prs_01HQ8Z6M4A",),
        name=f"Work hold.{gate} asks for",
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        _step(STEP_ID),
        _step(OTHER_STEP_ID),
        version="finding-report-v1",
        filler=_hold,
    )


def _launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=playbook, launch_date=None)
    return launch


def _provenance(evidence: str = EVIDENCE) -> Provenance:
    return Provenance(
        source="automated",
        who="listing.subcategory_advisor",
        when=WHEN,
        evidence=evidence,
    )


class _FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self._launches = list(launches)

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        for launch in self._launches:
            if launch.product_id == product_id:
                return launch
        return None

    async def save(self, launch: Launch) -> None:
        self._launches.append(launch)

    async def list_all(self) -> Sequence[Launch]:
        return tuple(self._launches)


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# Correction points — duplicated from the domain file, plus this file's own
# ---------------------------------------------------------------------------

_FINDING_KWARGS: Final = ("finding", "carried_finding", "kept_finding")
_FINDING_TYPES: Final = (
    "CarriedFinding",
    "RecordedFinding",
    "KeptFinding",
    "Finding",
)
_FINDING_ATTRS: Final = ("finding", "carried_finding", "kept_finding")


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


def _record(
    launch: Launch,
    playbook: LaunchPlaybook,
    *,
    step_id: str,
    finding: Any = _UNSET,
) -> None:
    kwargs: dict[str, Any] = {
        "step_id": step_id,
        "outcome": Satisfied,
        "provenance": _provenance(),
    }
    if finding is not _UNSET:
        kwargs[_finding_kwarg()] = finding
    launch.record_step_outcome(playbook, **kwargs)


def _part(raw: Any, key: str) -> Any:
    if isinstance(raw, Mapping):
        return raw.get(key, _ABSENT)
    return getattr(raw, key, _ABSENT)


def _normalise(raw: Any) -> _Carried | None:
    if raw is None:
        return None
    comment = _part(raw, "comment")
    return _Carried(
        field=_part(raw, "field"),
        value=_part(raw, "value"),
        comment=_ABSENT if comment is None else comment,
    )


def _entry(report: Any, step_id: str) -> Any:
    for candidate in report.steps:
        if candidate.step_id == step_id:
            return candidate
    pytest.fail(f"the report carries no entry for {step_id!r}")


def _reported_finding(entry: Any) -> _Carried | None:
    """The finding the report's step entry carries.

    INVENTED route, and the single correction point for it: either the
    entry carries the recording whole (`design.md`, Context) and the
    finding is read off that, or the entry carries a finding of its own.
    Both satisfy the scenario; failing loudly is what keeps a report that
    carries neither from reading as "carries nothing".
    """
    for name in _FINDING_ATTRS:
        if hasattr(entry, name):
            return _normalise(getattr(entry, name))
    if hasattr(entry, "progress"):
        # The entry carries recordings. `None` here is a step with nothing
        # recorded against it, which carries no finding by definition --
        # distinct from a report that carries no recordings at all, which
        # is what the failure below is for. Corrected during
        # implementation: the original probe failed on the unrecorded
        # case, which a correct implementation must produce.
        progress = entry.progress
        if progress is None:
            return None
        for name in _FINDING_ATTRS:
            if hasattr(progress, name):
                return _normalise(getattr(progress, name))
        pytest.fail(
            "the report's step entry carries the recording, but the "
            f"recording exposes no finding under any of {list(_FINDING_ATTRS)}"
        )
    pytest.fail(
        "the report's step entry carries neither a finding of its own "
        f"(under any of {list(_FINDING_ATTRS)}) nor a recording to read one "
        "off — a page cannot read a recording the report did not carry"
    )


async def _report(launch: Launch, playbook: LaunchPlaybook) -> Any:
    found = await read_launch(
        _FakeLaunchStore(launch),
        _FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        as_of=AS_OF,
        scope=AccessScope.unrestricted(),
    )
    assert found is not None, "no report was produced for the launch"
    return found


# ---------------------------------------------------------------------------
# Scenario: A carried finding reaches the launch report (tasks.md 1.8)
# ---------------------------------------------------------------------------


async def test_a_carried_finding_reaches_the_launch_report() -> None:
    """WHEN a launch report is produced for a launch whose step recording
    carries a finding THEN that step's entry on the report carries the
    finding, without a consumer re-deriving it.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, step_id=STEP_ID, finding=_carry(FIELD, VALUE, COMMENT))

    report = await _report(launch, playbook)

    carried = _reported_finding(_entry(report, STEP_ID))
    assert carried is not None, "the step's report entry carries no finding"
    assert carried.field == FIELD
    assert carried.value == VALUE
    assert carried.comment == COMMENT


async def test_the_finding_reaches_the_entry_the_recording_belongs_to() -> None:
    """The scenario's "that step's entry" clause.

    Two recorded steps, one carrying a finding and one not: the finding
    must reach the first entry and no other. An implementation that hung
    the finding off the report rather than the entry would pass a test
    that only looked for the value somewhere.
    """
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, step_id=STEP_ID, finding=_carry(FIELD, VALUE, COMMENT))
    _record(launch, playbook, step_id=OTHER_STEP_ID)

    report = await _report(launch, playbook)

    assert _reported_finding(_entry(report, STEP_ID)) is not None
    assert _reported_finding(_entry(report, OTHER_STEP_ID)) is None


async def test_an_unrecorded_step_entry_carries_no_finding() -> None:
    """The absent case at the report boundary, so that "carries the
    finding" is falsifiable: a served step nothing has been recorded for
    must not read as carrying one."""
    playbook = _playbook()
    launch = _launch(playbook)
    _record(launch, playbook, step_id=STEP_ID, finding=_carry(FIELD, VALUE, COMMENT))

    report = await _report(launch, playbook)

    entry = _entry(report, OTHER_STEP_ID)
    assert entry.progress is None
    assert _reported_finding(entry) is None
