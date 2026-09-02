"""What blocks activation, restated without the automation brief.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`

Covers the MODIFIED requirement *What blocks a step from being
activated is reported*:

- Requirement statement: "together with what it is missing — a
  registered handler, or an active assignee" (the automation-brief
  branch is dropped).
- Scenario: *Steps that cannot be activated are listed with their reason*
  (restated) — "against a set holding one ready step and one automated
  draft with no handler ... THEN exactly the draft is reported ... and
  the missing handler named" (previously "no brief" / "the missing brief
  named").

`test_report_activation_blockers.py`'s existing
`test_steps_that_cannot_be_activated_are_listed_with_their_reason` builds
its draft with `automation_brief=None` and asserts `"brief" in
_row_text(row)` — it bears directly on the removed field and is recorded
in `test-manifest.md`'s obsolete list rather than edited here. That same
file's `test_a_step_missing_a_registered_handler_is_reported` covers a
different case (a handler *named but unregistered*, not *absent
entirely*) and is unaffected by this delta.

*A set of ready steps reports nothing* and *A membership change does not
break an accepted set* (the report half) are unaffected by this delta's
wording and stay covered by the existing file.

**Level.** The report use case over an authored-step tuple, with the
members and handler registry as collaborators — the same level and the
same `_report()`/`_blockers()` probing pattern
`test_report_activation_blockers.py` already uses.

## Expected first-run state

`automation_brief` still gates leaving `draft` and the report still names
a missing brief rather than accepting a handler-only requirement, so
`test_a_draft_missing_only_a_handler_is_reported_by_the_handler_alone`
fails either on the absent `confirmer`/no-`automation_brief` field set or
on the report naming the wrong thing missing.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline

A_DISCIPLINE: Final = Discipline("strategy")
ANOTHER_DISCIPLINE: Final = Discipline("price")

REGISTERED_HANDLER: Final = "price.buy_box_check"

ALICE: Final = "prs_01HQ8Z6M4A"


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
        "confirmer": None,
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


class _Member:
    def __init__(self, member_id: str, display_name: str, *, active: bool) -> None:
        self.id = member_id
        self.display_name = display_name
        self.clickup_user_id: str | None = "clickup-1"
        self.active = active


class _FakeMembers:
    def __init__(self, members: tuple[_Member, ...]) -> None:
        self._members = members

    async def list_members(self) -> tuple[_Member, ...]:
        return self._members

    members = list_members

    async def __call__(self) -> tuple[_Member, ...]:
        return await self.list_members()


class _FakeHandlerRegistry:
    def __init__(self, names: frozenset[str]) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def __iter__(self) -> Any:
        return iter(self._names)

    def names(self) -> frozenset[str]:
        return self._names


def _members() -> _FakeMembers:
    return _FakeMembers((_Member(ALICE, "Alice Admin", active=True),))


_REPORT_NAMES: Final = (
    "report_activation_blockers",
    "report_what_blocks_activation",
    "report_blocked_activations",
    "report_steps_not_ready_to_activate",
)


def _report() -> Any:
    for name in _REPORT_NAMES:
        found = getattr(launch_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        "the launch application surface exports no report of what blocks "
        f"activation under any of {_REPORT_NAMES} — correct this file's "
        "probe to the implemented name"
    )


def _blockers(
    steps: tuple[StepDefinition, ...],
    *,
    members: _FakeMembers | None = None,
    handlers: _FakeHandlerRegistry | None = None,
) -> list[Any]:
    return list(
        _report()(
            steps=steps,
            members=members or _members(),
            handlers=handlers or _FakeHandlerRegistry(frozenset({REGISTERED_HANDLER})),
        )
    )


def _row_text(row: Any) -> str:
    return f"{row!r} {row}"


def _row_for(rows: list[Any], identifier: str) -> Any:
    for row in rows:
        if getattr(row, "identifier", None) == identifier:
            return row
    pytest.fail(f"the report carries no row for {identifier!r}: {rows!r}")


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): What blocks a step from being activated is
# reported
# ---------------------------------------------------------------------------


def test_a_draft_missing_only_a_handler_is_reported_by_the_handler_alone() -> None:
    """Scenario: Steps that cannot be activated are listed with their
    reason (restated).

    WHEN the report is requested against a set holding one ready step and
    one automated draft with no handler
    THEN exactly the draft is reported, with its identifier, gate,
    discipline and status, and the missing handler named.

    SPECIFIED restatement: what a draft is missing is now only ever "a
    registered handler, or an active assignee" — never a brief, because
    the field no longer exists to be missing.
    """
    ready = _step(
        identifier="listing.title-conforms",
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
    )
    draft_without_handler = _step(
        identifier="price.buy-box-check",
        gate="live",
        discipline=ANOTHER_DISCIPLINE,
        kind=StepKind.AUTOMATED,
        status=StepStatus.DRAFT,
        handler=None,
        assignees=(),
    )

    rows = _blockers((ready, draft_without_handler))

    assert [getattr(row, "identifier", None) for row in rows] == ["price.buy-box-check"]
    row = rows[0]
    assert row.identifier == "price.buy-box-check"
    assert row.gate == "live"
    assert row.discipline is ANOTHER_DISCIPLINE
    assert row.status is StepStatus.DRAFT
    # SPECIFIED: the missing handler is named, and no wording about a
    # brief survives — the field the old report could name is gone.
    lowered = _row_text(row).lower()
    assert "handler" in lowered
    assert "brief" not in lowered


def test_a_draft_naming_neither_handler_nor_confirmer_reports_only_the_handler() -> (
    None
):
    """Requirement statement, negative half: a step's *confirmer* is
    never among what the report names missing — naming none is always
    permitted (*A step names who confirms an automated result*), so an
    absent confirmer is never a blocker.
    """
    draft = _step(
        identifier="price.buy-box-check",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.DRAFT,
        handler=None,
        confirmer=None,
        assignees=(),
    )

    rows = _blockers((draft,))

    row = _row_for(rows, "price.buy-box-check")
    lowered = _row_text(row).lower()
    assert "handler" in lowered
    assert "confirm" not in lowered
