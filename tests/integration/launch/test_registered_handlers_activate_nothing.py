"""Registering handlers activates nothing on its own.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-playbook/spec.md`

Covers the one scenario the MODIFIED requirement *The authored set
exercises the full step vocabulary* adds:

    #### Scenario: A registered runtime does not activate a seeded step
    - **WHEN** a deployment registers step handlers and the seeded step
      set is read back
    - **THEN** the seeded `automated` steps are still `in-development`,
      having been activated by no one

The requirement's five carried-forward scenarios are unchanged in
statement and behaviour, and are already covered in
`tests/integration/launch/test_seeded_step_fields.py` and
`tests/unit/launch/application/test_report_activation_blockers.py`; they
are accounted for against those tests in `test-manifest.md`, and this
pass does not edit them.

## Why this scenario exists, and why it needs its own test

The delta's whole content in this capability is that a stated
justification expires: the requirement used to say the seeded automated
steps are `in-development` because "no automation runtime exists yet, so
no handler can be registered for them". After this change a runtime does
exist and a handler *is* registered — and the statuses must not move.
`design.md`'s Migration Plan step 2 says the same: "`check_step_handlers`
now reports one registered handler instead of zero, and no step changes
status", and step 3 makes activation "a separate, manual, post-deploy
act".

`tests/integration/launch/test_seeded_step_fields.py` already asserts
the statuses, but it asserts them of a process that registers no handler,
so it cannot observe the thing this scenario is about. What is new here
is the **WHEN**: a deployment that has registered its handlers.

## Level

The seeded set lives in Postgres and is read back through the authored
read, so the integration tier is the smallest level that can observe the
scenario. Handler registration is a process-global effect of importing a
composition root, which this file performs by import.

## INVENTED

- The authored read. `_authored_steps()` is transcribed from
  `tests/integration/launch/test_seeded_step_fields.py`, which records it
  as invented there; re-declared rather than imported because that file
  must not be edited by this pass and this directory carries no shared
  test helper module.
- How the registered handler names are read back. `_registered_names()`
  probes `launch.application`'s handler registry for a `names()` or a
  container, and fails loudly rather than defaulting — a vacuous pass
  (no handlers registered at all) is exactly what would make this test
  worthless, so it is refused explicitly.

## These assertions run in the gate

They did not always. This file was written against an empty `HANDLERS` and
a machine with no database configured, so its original docstring recorded
that the assertions had never been executed — true then, and false since
`restore-the-skipped-integration-tests` named CI's database for the
suffix the tier checks. `COMMERCE_OPS_REQUIRE_DATABASE` now also arms the
no-skip guard in `tests/conftest.py` over this tier, so a skip here fails
the validation job rather than passing quietly. Anything below that cannot
run must be deleted with its reason, not skipped — see the note at the foot
of this file for the one that was.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.registrations import register_all

pytestmark = pytest.mark.anyio

SEEDED_PREFIX: Final = "lp."


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _requires_database(database_url: str) -> None:
    """This file's opt-in to the tier's database gate."""


@pytest.fixture(autouse=True)
def _a_deployment_that_registers_its_handlers() -> None:
    """The scenario's **WHEN**: a deployment that has registered step
    handlers.

    `registrations.py` is the one list both composition roots import
    (`tasks.md` 4.7, 7.4), so calling it is what a deployed process does
    on the way up. Idempotent by construction — the existing
    registry-divergence guard already relies on importing a root twice
    being safe.
    """
    register_all()


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


_AUTHORED_ON_PLAYBOOK: Final = ("authored_steps", "all_steps")
_AUTHORED_ON_REPOSITORY: Final = (
    "authored_steps",
    "all_steps",
    "list_authored",
    "load",
)


async def _authored_steps() -> tuple[StepDefinition, ...]:
    """Every authored step definition, whatever its status.

    The read `tests/integration/launch/test_seeded_step_fields.py`
    records — the served queries answer active steps only, and this
    file's subject is precisely the two steps that are *not* active.
    """
    async with _session() as session:
        result = await _resolve(
            PlaybookRepository(session).get("any-version-read-through")
        )
        assert isinstance(result, LaunchPlaybook)
        playbook = result
    for name in _AUTHORED_ON_PLAYBOOK:
        carried = getattr(playbook, name, None)
        if carried is not None:
            steps = await _resolve(carried() if callable(carried) else carried)
            return tuple(steps)
    async with _session() as session:
        repository = PlaybookRepository(session)
        for name in _AUTHORED_ON_REPOSITORY:
            reader = getattr(repository, name, None)
            if reader is None:
                continue
            answered = await _resolve(reader())
            rows = answered[0] if isinstance(answered, tuple) else answered
            steps = [
                row if isinstance(row, StepDefinition) else row.definition
                for row in rows
            ]
            if steps:
                return tuple(steps)
    pytest.fail(
        "no authored read was found on the playbook or the repository — "
        "correct this file's probe to the implemented read"
    )


_REGISTRY_NAMES: Final = ("HANDLERS", "STEP_HANDLERS", "handlers", "handler_registry")


def _registered_names() -> tuple[str, ...]:
    """The handler names this process registers.

    Probed on `launch.application` and on its `handler_registry` module,
    failing loudly rather than defaulting — a probe that quietly found
    nothing would make the test below pass for the wrong reason.
    """
    import importlib

    candidates: list[Any] = [launch_application]
    try:
        candidates.append(
            importlib.import_module("commerce_ops.launch.application.handler_registry")
        )
    except ImportError:
        pass

    for module in candidates:
        for name in _REGISTRY_NAMES:
            registry = getattr(module, name, None)
            if registry is None:
                continue
            reader = getattr(registry, "names", None)
            if callable(reader):
                return tuple(reader())
            if hasattr(registry, "__iter__"):
                return tuple(str(item) for item in registry)
    pytest.fail(
        "no step-handler registry found on `commerce_ops.launch.application` "
        f"under any of {_REGISTRY_NAMES} — correct this file's probe to the "
        "implemented registry"
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The authored set exercises the full step
# vocabulary
# ---------------------------------------------------------------------------


async def test_a_registered_runtime_does_not_activate_a_seeded_step() -> None:
    """Scenario: A registered runtime does not activate a seeded step.

    WHEN a deployment registers step handlers and the seeded step set is
    read back
    THEN the seeded `automated` steps are still `in-development`, having
    been activated by no one.
    """
    # The scenario's WHEN, made non-vacuous: this process really has
    # registered at least one handler. Without this the assertion below
    # would hold trivially in a deployment that registers nothing, which
    # is exactly the state the change moves away from.
    registered = _registered_names()
    assert registered, (
        "this deployment registers no step handler, so the scenario's "
        "precondition does not hold and the assertion below would pass "
        "for the wrong reason"
    )

    seeded = tuple(
        step
        for step in await _authored_steps()
        if step.identifier.startswith(SEEDED_PREFIX)
    )
    assert seeded, "no seeded (lp.*) steps were read back"

    automated = tuple(step for step in seeded if step.kind is StepKind.AUTOMATED)
    # The requirement's own coverage clause: the seed carries automated
    # steps at all. Asserted here so the status check below cannot pass
    # over an empty set.
    assert automated, "the seeded set carries no automated step"

    # SPECIFIED: still `in-development`, having been activated by no one.
    still_in_development = [
        step for step in automated if step.status is StepStatus.IN_DEVELOPMENT
    ]
    assert len(still_in_development) == len(automated), (
        "registering handlers moved a seeded automated step out of "
        "`in-development`: "
        f"{[(step.identifier, step.status) for step in automated]}"
    )


async def test_no_seeded_human_step_is_in_development_after_registration() -> None:
    """The other half of the pair above, and the reason that test is not
    satisfiable by a deployment which simply broke the status read: an
    implementation returning `in-development` for everything would pass
    it and fail here.

    **This used to assert that every seeded human step is `active`, and
    that is no longer what the specification says.** It cited
    `introduce-automation-runtime`'s "Every seeded `human` step SHALL be
    `active`", written when the seeded set was the 97 rows the seed
    migration wrote. `seed-the-reference-step-set` superseded it:
    `launch-playbook` now requires that "Every seeded step SHALL be
    `draft` and SHALL be `human`, and SHALL name no assignee", and
    `seed_playbook` delivers 255 such rows into the same `lp.` namespace
    on every container start. So a database prepared the way the
    deployment prepares one carries hundreds of seeded human steps that
    are legitimately not active, and the old assertion listed them all
    back as a failure.

    The guard is kept and only its subject corrected. What it exists to
    catch is a uniformly broken status read, and *no seeded human step is
    `in-development`* catches exactly that — the two seeded steps in that
    status are `automated`, which is the pair's other assertion — while
    saying nothing the current requirement contradicts.
    """
    _registered_names()

    seeded = tuple(
        step
        for step in await _authored_steps()
        if step.identifier.startswith(SEEDED_PREFIX)
    )
    human = tuple(step for step in seeded if step.kind is StepKind.HUMAN)
    assert human, "the seeded set carries no human step"

    in_development = [
        step.identifier for step in human if step.status is StepStatus.IN_DEVELOPMENT
    ]
    assert in_development == [], (
        "these seeded human steps read as `in-development`, a status the "
        f"seed gives only to automated steps: {in_development}"
    )


# `test_no_seeded_automated_step_is_activated_by_its_handler_existing` stood
# here, and `restore-the-skipped-integration-tests` deleted it rather than
# repairing it. What it was for is worth keeping; the test was not.
#
# It asserted the sharper form of the requirement above -- that a seeded
# automated step stays `in-development` *even when this deployment registers
# the handler it names* -- and skipped when no seeded step named a registered
# one. That reads as an occasional coincidence. It is structural: the backfill
# migration writes `handler = NULL` for every row, `_automation_faults`
# obliges a handler only once a step is `active`, and
# `handler_registry.py` says so outright -- "One handler is registered, and no
# step names it." So its subject was empty on every run of every correctly
# prepared database and its assertion never executed anywhere.
#
# Nothing was lost by deleting it.
# `test_a_registered_runtime_does_not_activate_a_seeded_step` above asserts
# over `automated`, and the deleted test's `resolvable` was a filtered subset
# of exactly that tuple -- so the assertion over the whole set entails the one
# over the subset. `launch-playbook`'s only scenario for this behaviour, *A
# registered runtime does not activate a seeded step*, is the one that sibling
# is named for.
#
# **The finding, which outlives the test.** The requirement's negative half --
# activation is "never something seeding or deploying does on an author's
# behalf" -- has no integration-level subject in this system. The only writer
# in the container's start chain is `seed_playbook`; `check_step_handlers`
# only reports, every read scoped to `active`. And seeding cannot re-status
# anything: `_establish()` returns before writing when no vendored identifier
# is missing, and `compose()` "carries across untouched" every stored record,
# with no branch on what one contains. That half is held at unit level, by
# `tests/unit/test_seed_playbook.py`'s
# `test_an_edited_step_is_left_exactly_as_it_stands`.
#
# Two replacement tests were drafted and rejected as tautologies before the
# deletion was chosen; `design.md` Decision 3 of that change records both, so
# a third is not attempted here. Integration coverage of the requirement's
# *positive* half -- that `activate_step` refuses a step naming an
# unregistered handler, via `_registration_faults` -- is a real gap and a
# separate change.
