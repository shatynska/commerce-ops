"""Outcome recording when the served playbook no longer defines a step.

Derived strictly from the delta spec:
`openspec/changes/move-playbook-steps-to-postgres/specs/launch-instance/spec.md`

Covers, from the MODIFIED requirement *A step outcome is recorded with
provenance*, the sentence this delta revises: "Recording an outcome for a
step identifier the served playbook does not define — an identifier that
never existed and a retired step's alike — SHALL be rejected; outcomes
already recorded against a step before its retirement remain stored and
readable." The never-existed half is already covered by
`tests/unit/launch/domain/test_launch_run.py` (*An unknown step
identifier is rejected*); what is new here is the retired half: an
identifier that *was* defined when its outcome was recorded, and is
absent from the playbook served for a later recording.

It also carries the domain half of `playbook-authoring`'s scenario *A
retired step's history stays readable* ("those recorded outcomes remain
readable and still name the step's identifier"): the aggregate keeps
serving recorded progress for an identifier the current playbook no
longer defines. The persistence half — the stored rows surviving — is
general rehydration behavior, already covered by
`tests/integration/launch/test_launch_repository.py`.

**Level.** `Launch.record_step_outcome(playbook, ...)` receives the
served playbook per call (the shape
`tests/unit/launch/domain/test_launch_run.py` records), so a plain
aggregate call can observe both outcomes: retirement, at this level, *is*
the step's absence from the playbook passed in — the served playbook
excludes retired steps (`tasks.md` 3.1), and `tasks.md` 5.1 routes
retired-identifier rejection through exactly this validation.

**Expected first-run state.** Both tests are expected to pass against the
current implementation: rejection of an identifier the passed playbook
does not define already exists, and this delta makes that same mechanics
mean "retired steps included" by changing what playbook is served — a
composition concern (`tasks.md` 3.3, 5.1), not a new aggregate branch.
Per `ai-toolkit:testing`, a first-run pass here is the target-exists
case: it establishes the aggregate already behaves as the revised
requirement states, pinning that behavior against regression while the
serving side changes around it.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 636 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres
(`DATABASE_URL` is unset here).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, LaunchError, Provenance
from tests.support.fixtures import product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step

PRODUCT_ID: Final = product_id()
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

# The step that will be "retired": present in the first served playbook,
# absent from the second.
RETIRED_STEP_ID: Final = "listing.title-conforms"


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": RETIRED_STEP_ID, **overrides})


def _holding_step(gate: str) -> StepDefinition:
    """One blocking step per gate, so fixtures satisfy the gate-holding
    floor this change promotes to a coherence rule (`tasks.md` 1.1)."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _holding_steps() -> tuple[StepDefinition, ...]:
    return tuple(_holding_step(gate) for gate in SPECIFIED_GATE_ORDER)


def _playbook(version: str, steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    return LaunchPlaybook(version=version, gates=_gates(), steps=steps)


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "screenshot in the launch Slack thread",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step outcome is recorded with provenance
# ---------------------------------------------------------------------------


def test_recording_for_a_step_absent_from_the_served_playbook_is_rejected() -> None:
    """Scenario: An unknown step identifier is rejected — the retired half.

    WHEN an outcome is recorded for a step identifier the served playbook
    does not define — here, an identifier the launch recorded under an
    earlier definition era, now absent
    THEN the recording is rejected.
    """
    step = _step()
    with_step = _playbook("set-v41", (*_holding_steps(), step))
    without_step = _playbook("set-v42", _holding_steps())

    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=with_step)
    launch.record_step_outcome(
        with_step,
        step_id=RETIRED_STEP_ID,
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # SPECIFIED: a retired step's identifier is rejected exactly as one
    # that never existed.
    with pytest.raises(LaunchError):
        launch.record_step_outcome(
            without_step,
            step_id=RETIRED_STEP_ID,
            outcome=Satisfied,
            provenance=_provenance(),
        )


def test_outcomes_recorded_before_retirement_stay_readable() -> None:
    """Scenario (playbook-authoring): A retired step's history stays
    readable — the aggregate half.

    WHEN outcomes were recorded against a step and the step is then
    retired (absent from every later-served playbook)
    THEN those recorded outcomes remain readable and still name the
    step's identifier.
    """
    step = _step()
    with_step = _playbook("set-v41", (*_holding_steps(), step))

    launch, _ = Launch.start(product_id=PRODUCT_ID, playbook=with_step)
    launch.record_step_outcome(
        with_step,
        step_id=RETIRED_STEP_ID,
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # The step is now "retired": no later interaction serves it. Reading
    # recorded progress takes no playbook at all, so absence from the
    # served set cannot erase it.
    progress = launch.progress_for(RETIRED_STEP_ID)

    # SPECIFIED: the recorded outcome remains stored and readable, under
    # the step's own identifier.
    assert progress is not None
    assert progress.outcome is Satisfied
