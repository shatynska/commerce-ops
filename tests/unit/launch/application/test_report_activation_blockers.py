"""What blocks a step from being activated, reported over the authored set.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers the ADDED requirement *What blocks a step from being activated is
reported* — both scenarios — and the report half of
`playbook-authoring`'s scenario *A membership change does not break an
accepted set* ("the step is reported as needing an assignee"), whose
load half is in `test_step_assignee_preconditions.py`.

This requirement replaces *Undecided rule policies are reported*, whose
REMOVED entry says why: "the report's subject changes. 'Which steps have
not decided a rule policy' becomes 'which steps cannot yet be made
`active`', which covers the brief, the handler, and an active human
step's assignees rather than one field."

The existing report and its two tests
(`tests/unit/launch/application/test_report_undecided_rule_policies.py`)
are superseded by this file and are recorded as such in
`test-manifest.md`. They are not edited or deleted here.

**Level.** The report is a use case over the authored set, with the
members and the handler registry as collaborators — the same seam every
other use case of this capability takes them on.

## INVENTED shapes

- The report's exported name. `_report()` probes the public surface and
  fails loudly rather than defaulting; `tasks.md` 2.5 fixes that
  `undecided_rule_policies.py` is *replaced*, not the replacement's
  spelling.
- Its call shape: the authored step definitions as `steps=`, plus
  `members=` and `handlers=`. `report_undecided_rule_policies` took a
  loaded `LaunchPlaybook`; this report's subject is the **authored** set,
  which includes drafts the served playbook does not carry, so the
  definitions are passed directly. Correction point: `_blockers()`.
- Row field spellings (`identifier`, `gate`, `discipline`, `status`,
  and whatever names what is missing). `_row_text()` reads a row
  whole-cloth via `repr` for the "what it is missing" assertions, so
  only the four SPECIFIED identifying fields are addressed by name.

## Expected first-run state

The report does not exist, so every test here fails on an absent target
(`ImportError`, or `_report()`'s loud failure) — absence, and nothing
more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
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
BOHDAN: Final = "prs_01HQ8Z6M4B"


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


def _members(*, bohdan_active: bool = True) -> _FakeMembers:
    return _FakeMembers(
        (
            _Member(ALICE, "Alice Admin", active=True),
            _Member(BOHDAN, "Bohdan Colleague", active=bohdan_active),
        )
    )


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
        f"activation under any of {_REPORT_NAMES} — `tasks.md` 2.5 "
        "replaces `undecided_rule_policies.py` with one; correct this "
        "file's probe to the implemented name"
    )


def _blockers(
    steps: tuple[StepDefinition, ...],
    *,
    members: _FakeMembers | None = None,
    handlers: _FakeHandlerRegistry | None = None,
) -> list[Any]:
    """The single correction point for the report's call shape."""
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
# Requirement: What blocks a step from being activated is reported
# ---------------------------------------------------------------------------


def test_steps_that_cannot_be_activated_are_listed_with_their_reason() -> None:
    """Scenario: Steps that cannot be activated are listed with their
    reason.

    WHEN the report is requested against a set holding one ready step and
    one automated draft with no handler
    THEN exactly the draft is reported, with its identifier, gate,
    discipline and status, and the missing handler named.
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

    # SPECIFIED: exactly the draft is reported.
    assert [getattr(row, "identifier", None) for row in rows] == ["price.buy-box-check"]
    row = rows[0]
    # SPECIFIED: with its identifier, gate, discipline and status.
    assert row.identifier == "price.buy-box-check"
    assert row.gate == "live"
    assert row.discipline is ANOTHER_DISCIPLINE
    assert row.status is StepStatus.DRAFT
    # SPECIFIED: and the missing handler named. DERIVED wording marker —
    # correcting the substring to the implemented spelling is a fixture
    # correction; dropping the assertion is not, because "what it is
    # missing" is the whole reason this report replaced the last one.
    assert "handler" in _row_text(row).lower()


def test_a_set_of_ready_steps_reports_nothing() -> None:
    """Scenario: A set of ready steps reports nothing.

    WHEN the report is requested against a set in which every step can be
    made `active`
    THEN the report is empty.

    "Ready" spans both kinds here — an owned human step and an automated
    step with a registered handler — so a report that over-reported
    either kind fails.
    """
    ready_human = _step(
        identifier="listing.title-conforms",
        status=StepStatus.IN_DEVELOPMENT,
        assignees=(ALICE,),
    )
    ready_automated = _step(
        identifier="price.buy-box-check",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.IN_DEVELOPMENT,
        handler=REGISTERED_HANDLER,
        assignees=(),
    )
    already_active = _step(
        identifier="listing.a-plus-content",
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
    )

    assert _blockers((ready_human, ready_automated, already_active)) == []


def test_a_step_missing_a_registered_handler_is_reported() -> None:
    """Requirement statement: the report says "what it is missing — a
    registered handler, or an active assignee".

    The handler case is stated in the requirement but in neither
    scenario, and it is the one that reaches outside the step set: a step
    carrying a handler name is only *missing* one in the sense that the
    deployed registry does not answer for it.
    """
    unregistered = _step(
        identifier="price.buy-box-check",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.IN_DEVELOPMENT,
        handler="price.nothing_answers_for_this",
        assignees=(),
    )

    rows = _blockers((unregistered,))

    row = _row_for(rows, "price.buy-box-check")
    assert "handler" in _row_text(row).lower()


def test_a_step_whose_only_assignee_was_deactivated_is_reported() -> None:
    """Scenario (playbook-authoring): A membership change does not break an
    accepted set — the report half.

    WHEN the sole assignee of an `active` `human` step is deactivated on
    the membership
    THEN ... the step is reported as needing an assignee.

    This is what makes the load-side relaxation honest: the step keeps
    loading and keeps being served (asserted in
    `test_step_assignee_preconditions.py`), and *this* report is where
    the gap surfaces instead. A report that only looked at non-`active`
    steps would leave it invisible, which is the failure the relaxation
    would otherwise buy.
    """
    accepted = _step(
        identifier="listing.owned-by-a-leaver",
        status=StepStatus.ACTIVE,
        assignees=(BOHDAN,),
    )

    rows = _blockers((accepted,), members=_members(bohdan_active=False))

    row = _row_for(rows, "listing.owned-by-a-leaver")
    assert row.status is StepStatus.ACTIVE
    assert "assign" in _row_text(row).lower()


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The report's ordering. Neither scenario states one, and asserting an
#   order would invent a constraint; the tests above address rows by
#   identifier except where exactly one row is expected.
# - Whether a `retired` step ever appears. The requirement's subject is
#   "the authored step set's definitions [that] cannot yet be made
#   `active`", and a retired step is not work anyone is getting ready —
#   but the spec does not say so, so nothing here asserts either way.
