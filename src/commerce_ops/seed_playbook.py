"""The playbook step set's pre-serving preparation step.

Runs as its own process in the container's start chain, between
`seed-admin` and the handler-registration report:

    preflight && alembic upgrade head && seed-admin
      && seed-playbook && check-step-handlers && exec uvicorn

Deliberately *not* part of the serving process, for the reason `seed_admin`
records: reading or writing the step set there would make the server open a
database connection before its first request, which `database-session`
requires not to happen.

**It adds what is missing and never touches what is there.** A stored step
whose identifier the vendored set names is left exactly as it stands —
whatever its status, whoever edited it, whatever it is now called. Only rows
no stored step names are inserted.

That single rule is what makes this safe to run on every container start.
The chain above runs on every restart, every host reboot and every
crash-loop, so a step that writes needs a condition that can be read from
the data — and "which of these rows do I already have" is exactly such a
condition, in the way "should I overwrite this row" is not: a stored row
that differs from the vendored one is indistinguishable from an authored
edit. Running twice in a row is therefore a no-op, and nothing arms it.

It is also the rule the original seed migration already chose, for the same
reason: `d2f8b3c64e17` guards on the table being empty, so that "a
`playbook_steps` table that already holds rows — authored edits included —
is never re-seeded and never overwritten". This step widens that guard from
the whole table to each row, so a reference document that gains a row can
still deliver it, and narrows nothing.

The cost, stated plainly: a **corrected** vendored definition never reaches
a row that already exists. Correcting a seeded step is an authoring act,
made through the admin surface by someone who can see what they are
changing. A wholesale refresh means emptying the table first, which is a
deliberate destructive act and looks like one.

Exit status is the whole interface: zero when the set is established,
non-zero with the reason on stderr when it cannot be.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from commerce_ops.launch.application import StepRecord, authored_definitions
from commerce_ops.launch.domain.launch_playbook import (
    Cadence,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
    TimingAnchor,
    WindowAnchor,
    framework_gates,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.infrastructure.driven.database import dispose_engine, session
from commerce_ops.shared.infrastructure.logging import configure_logging

_logger = logging.getLogger(__name__)

_VENDORED = (
    Path(__file__).resolve().parent.parent.parent
    / "alembic"
    / "data"
    / "playbook_reference.yaml"
)


def _anchor(raw: dict[str, Any]) -> TimingAnchor:
    kind = raw["kind"]
    if kind == "offset":
        return OffsetAnchor(days=int(raw["days"]))
    if kind == "window":
        return WindowAnchor(start=int(raw["start"]), end=int(raw["end"]))
    if kind == "open-ended":
        return OpenEndedAnchor(start=int(raw["start"]))
    if kind == "recurring":
        return RecurringAnchor(cadence=Cadence(raw["cadence"]))
    raise ValueError(f"vendored timing anchor has unknown kind '{kind}'")


def vendored_definitions(path: Path = _VENDORED) -> tuple[StepDefinition, ...]:
    """The vendored set, as domain values.

    A shape fault here is a fault in a file this repository ships, so it is
    reported as one rather than being allowed to reach the database.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return tuple(
        StepDefinition(
            identifier=step["identifier"],
            name=step["name"],
            description=step["description"],
            gate=step["gate"],
            discipline=Discipline(step["discipline"]),
            scope=Scope(step["scope"]),
            timing_anchor=_anchor(step["timing_anchor"]),
            blocking=step["blocking"],
            kind=StepKind(step["kind"]),
            needs_confirmation=step["needs_confirmation"],
            status=StepStatus(step["status"]),
            hazard=Hazard(step["hazard"]),
            assignees=tuple(step["assignees"]),
            provenance=step["provenance"],
        )
        for step in document["steps"]
    )


def compose(
    stored: list[Any], vendored: tuple[StepDefinition, ...]
) -> tuple[list[StepRecord], int]:
    """The candidate set a run would persist, and how many rows it adds.

    Every stored record is carried across untouched — its definition, its
    status, its attribution, whatever an author has since made of it. A
    vendored step no stored record names is appended.

    Nothing here is conditional on what a stored row *contains*, and that is
    the point: a row that differs from its vendored counterpart looks exactly
    like an authored edit, so there is no reading of the data that tells the
    two apart. Identity is the only question this step is entitled to ask.
    """
    stored_identifiers = {record.definition.identifier for record in stored}
    candidate = list(stored)
    added = 0
    for definition in vendored:
        if definition.identifier in stored_identifiers:
            continue
        candidate.append(StepRecord(definition=definition))
        added += 1
    return candidate, added


async def _establish() -> None:
    async with session() as db_session:
        repository = PlaybookRepository(db_session)
        stored, version = await repository.load()
        candidate, added = compose(list(stored), vendored_definitions())

        if not added:
            _logger.info(
                "every vendored step is already stored (%d step(s)); nothing to add",
                len(stored),
            )
            return

        # Judge the whole set before any of it is persisted, reporting every
        # fault at once rather than one per run.
        LaunchPlaybook(
            version=f"seed-{version + 1}",
            gates=framework_gates(),
            steps=authored_definitions(candidate),
        )
        await repository.save(candidate, expected_version=version)
        _logger.info(
            "added %d step(s) the stored set did not carry; %d existing "
            "step(s) left exactly as they were",
            added,
            len(stored),
        )


async def _run() -> None:
    try:
        await _establish()
    finally:
        # This process opened its own engine; the chain that follows gets a
        # clean one.
        await dispose_engine()


def main() -> int:
    configure_logging()
    try:
        asyncio.run(_run())
    except InvalidPlaybookError as rejected:
        print(
            "playbook seeding refused; the vendored set would not load:",
            file=sys.stderr,
        )
        for fault in rejected.faults:
            print(f"  - {fault}", file=sys.stderr)
        return 1
    except Exception as failure:  # noqa: BLE001 — the exit status is the interface
        print(f"playbook seeding failed: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
