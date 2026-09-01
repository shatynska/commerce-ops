"""The playbook preparation step: what it adds, and what it never touches.

Covers `seed-the-reference-step-set`'s tasks 3.12-3.17 and 3.19.

One property carries the change: the step **adds what is missing and never
touches what is there**. Identity is the only question it asks of the stored
set, because a stored row that differs from its vendored counterpart is
indistinguishable from a row an author edited — the difference is the edit.

That makes it idempotent, which is why nothing arms it: its condition is
readable from the stored set, the way the roster seeder's is from the roster.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepRecord
from commerce_ops.launch.domain.launch_playbook import StepStatus
from commerce_ops.seed_playbook import compose, vendored_definitions

_ROOT: Final = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def vendored() -> tuple[Any, ...]:
    return vendored_definitions()


@pytest.fixture(scope="module")
def by_identifier(vendored: tuple[Any, ...]) -> dict[str, Any]:
    return {definition.identifier: definition for definition in vendored}


def test_an_empty_set_receives_the_whole_vendored_set(
    vendored: tuple[Any, ...],
) -> None:
    """3.12 — a database carrying none of the vendored steps gets all of them."""
    candidate, added = compose([], vendored)

    assert added == len(vendored) == 358
    assert len(candidate) == 358


def test_running_again_changes_nothing(vendored: tuple[Any, ...]) -> None:
    """3.13 — SPECIFIED: running twice changes nothing the first run did not.

    This is the property the start chain depends on. The chain runs on every
    restart, every host reboot and every crash-loop, and this step writes; it
    is safe there only because a second run has nothing to do.
    """
    stored = [StepRecord(definition=definition) for definition in vendored]

    candidate, added = compose(stored, vendored)

    assert added == 0
    assert len(candidate) == len(stored)


def test_an_edited_step_is_left_exactly_as_it_stands(
    vendored: tuple[Any, ...], by_identifier: dict[str, Any]
) -> None:
    """3.14 — SPECIFIED: a stored step is never replaced, re-statused,
    de-activated or stripped of an assignee by a seeding run.

    The step under test differs from its vendored counterpart in every way an
    author can make it differ — renamed, activated, assigned — which is
    exactly the state an earlier design would have overwritten.
    """
    now = datetime.now(UTC)
    edited = StepRecord(
        definition=replace(
            by_identifier["lp.rank.001"],
            name="a name an author chose",
            status=StepStatus.ACTIVE,
            assignees=("a-roster-identifier",),
        ),
        updated_by="helen",
        updated_on=now,
    )

    candidate, added = compose([edited], vendored)

    kept = next(
        record for record in candidate if record.definition.identifier == "lp.rank.001"
    )
    assert kept.definition.name == "a name an author chose"
    assert kept.definition.status is StepStatus.ACTIVE
    assert kept.definition.assignees == ("a-roster-identifier",)
    assert kept.updated_by == "helen"
    assert kept.updated_on == now
    # Everything else the vendored set carries is still added.
    assert added == 357


def test_a_retired_step_is_not_returned_by_a_seeding_run(
    vendored: tuple[Any, ...], by_identifier: dict[str, Any]
) -> None:
    """3.15 — SPECIFIED: a retired seeded step keeps its reference identifier,
    so the vendored set does name it. Returning it to `draft` would erase the
    principal and date of its retirement — the unattributed exit from
    `retired` that `launch-playbook` and `playbook-authoring` both forbid.
    """
    retired_on = datetime.now(UTC)
    retired = StepRecord(
        definition=replace(by_identifier["lp.rank.012"], status=StepStatus.RETIRED),
        retired_by="helen",
        retired_on=retired_on,
    )
    # The premise, asserted rather than assumed.
    assert "lp.rank.012" in by_identifier

    candidate, _ = compose([retired], vendored)

    kept = next(
        record for record in candidate if record.definition.identifier == "lp.rank.012"
    )
    assert kept.definition.status is StepStatus.RETIRED
    assert kept.retired_by == "helen"
    assert kept.retired_on == retired_on


def test_a_step_the_vendored_set_does_not_name_survives(
    vendored: tuple[Any, ...], by_identifier: dict[str, Any]
) -> None:
    """3.16 — SPECIFIED: `playbook-authoring` states that no operation deletes
    a step, and outcomes recorded against one outlive its definition."""
    authored = StepRecord(
        definition=replace(
            by_identifier["lp.rank.001"],
            identifier="mg.rank.001",
            name="hand-made",
        ),
        created_by="helen",
        created_on=datetime.now(UTC),
    )

    candidate, added = compose([authored], vendored)

    survivor = next(
        record for record in candidate if record.definition.identifier == "mg.rank.001"
    )
    assert survivor.definition.name == "hand-made"
    assert survivor.created_by == "helen"
    assert added == 358
    assert len(candidate) == 359


def test_a_reference_row_added_later_is_delivered(
    vendored: tuple[Any, ...],
) -> None:
    """3.17 — SPECIFIED: a vendored step no stored step names is stored, and
    no other stored step is altered.

    This is what the rule buys over the migration's emptiness guard, which
    would require wiping the table to accept one new row.
    """
    stored = [
        StepRecord(definition=definition)
        for definition in vendored
        if definition.identifier != "lp.rank.001"
    ]

    candidate, added = compose(list(stored), vendored)

    assert added == 1
    assert any(record.definition.identifier == "lp.rank.001" for record in candidate)
    assert len(candidate) == len(vendored)


def test_nothing_stored_is_ever_absent_from_the_candidate(
    vendored: tuple[Any, ...], by_identifier: dict[str, Any]
) -> None:
    """3.14/3.16 — the net effect `save()` must produce. It clears the table
    and re-adds, so any row missing from the candidate is a row deleted."""
    stored = [
        StepRecord(
            definition=replace(by_identifier["lp.rank.001"], identifier="mg.a.1")
        ),
        StepRecord(
            definition=replace(by_identifier["lp.rank.012"], status=StepStatus.RETIRED),
            retired_by="helen",
        ),
        StepRecord(definition=by_identifier["lp.rank.002"]),
    ]

    candidate, _ = compose(list(stored), vendored)

    surviving = {record.definition.identifier for record in candidate}
    for record in stored:
        assert record.definition.identifier in surviving


def test_the_start_chain_runs_the_step_in_its_specified_position() -> None:
    """3.19 — SPECIFIED (`deploy-pipeline`): after the roster seed, and before
    the handler-registration report, so that report describes the set the
    deployment is about to serve.

    Asserted against the image's `CMD`, which is where the chain lives — `app`
    declares no `command` of its own, so `docker-compose.yml` cannot express
    this.
    """
    dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))

    order = [
        found
        for pair in re.findall(
            r"commerce_ops\.(\w+)|(?:exec uv run )(uvicorn)", command
        )
        for found in pair
        if found
    ]
    assert order.index("seed_admin") < order.index("seed_playbook")
    assert order.index("seed_playbook") < order.index("check_step_handlers")
    assert order.index("check_step_handlers") < order.index("uvicorn")


def test_the_step_takes_no_runtime_variable() -> None:
    """SPECIFIED (design): the step needs no arming signal, because its
    condition is readable from the stored set.

    Asserted because the absence is load-bearing: a signal would have to be
    delivered with the deployment, and `.env` is rendered only at deploy time,
    so one set for a single deploy would go on arming every restart until the
    next.
    """
    source = (_ROOT / "src" / "commerce_ops" / "seed_playbook.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert "get_settings" not in source
