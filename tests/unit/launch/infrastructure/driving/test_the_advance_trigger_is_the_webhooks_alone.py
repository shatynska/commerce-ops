"""The carve-out reaches one call site, and the other three stay bound.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-from-clickup-webhook`:
`openspec/changes/advance-gates-from-clickup-webhook/specs/launch-gate-progression/spec.md`

Covers the half of the MODIFIED scenario that states what must **not**
change:

    #### Scenario: Recording an outcome does not itself advance a launch
    - **WHEN** a step outcome is recorded that satisfies the last
      outstanding condition on a launch's current gate
    - **THEN** the launch's current gate is unchanged until a pass or a
      recorded decision advances it, **unless it was recorded through the
      ClickUp webhook**

and the requirement sentence that scopes it:

    This exception is narrow and procedural — it names one call site, not
    a new advancement rule — and does not generalize: every other path
    that records a step outcome (the ClickUp reconciliation pass, the
    automation pass, and an automated result's confirmation) remains
    fully bound by the SHALL NOT, exactly as before.

The other half of the same scenario — that recording *itself* advances
nothing — is unchanged by this amendment and is already asserted at the
application tier in
`tests/unit/launch/application/test_recording_does_not_advance_a_launch.py`.
That file is left exactly as it stands; this one adds what the amendment
newly makes assertable, which is the **exclusivity** of the carve-out.

See `test-manifest.md` at the change root for the full accounting.

## Why this is a structural guard rather than a behavioural one

"Every other path remains bound" is a claim about three passes not doing
something. Driving each of them to observe an absence would mean standing
up three full pass harnesses — `test_clickup_sync_job_containment.py`,
`test_automation_pass.py` and `test_automation_confirmation_delivery.py`
each carry one — for an assertion that would then be satisfied by any run
in which the pass happened to reach no launch at all. What actually
enforces the boundary is that those three modules cannot reach the
trigger: it is not on their surface, under any name, and no attribute of
theirs is it. That is what is asserted here, and it is falsifiable by
exactly the edit the requirement forbids.

Its limit is stated plainly, and recorded in the manifest: a pass that
imported the trigger *inside a function body* would pass this guard. That
is a real gap, and the reason it is accepted is that it would also
contradict this repository's own bare-global convention, which
`clickup_webhook.py`'s docstring records and `proposal.md` — Impact
reaffirms for exactly this import.

## Expected first-run state

Expected to **PASS**, before the implementation lands and after. It states
behaviour the change must **preserve**, not introduce — the same shape and
the same reason as
`tests/unit/launch/application/test_recording_does_not_advance_a_launch.py`,
which records why such a guard must not probe for an absent target: a
change that wired advancement into a fourth call site would otherwise go
uncaught for as long as the trigger itself was missing.

Baseline recorded before this test was written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `96303a7`: `uv run pytest tests/unit tests/agents` — 1727 passed,
0 failed.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Final

import pytest

DRIVING: Final = "commerce_ops.launch.infrastructure.driving"

#: The three recording call sites `proposal.md` — What Changes and the
#: amended requirement both name as staying bound by the SHALL NOT.
STILL_BOUND: Final = (
    f"{DRIVING}.clickup_sync_job",
    f"{DRIVING}.automation_pass",
    f"{DRIVING}.automation_confirmation",
)

#: The one call site the exception names.
EXEMPT: Final = f"{DRIVING}.clickup_webhook"

#: Where the cascade lives (`design.md` — Decision 1).
CASCADE: Final = f"{DRIVING}.gate_progression_job"

#: The names the trigger may carry. Kept in step with
#: `test_advance_and_ask.py` and
#: `test_clickup_webhook_triggers_the_advance_cascade.py`, which are the
#: correction points.
TRIGGER_NAMES: Final = (
    "advance_and_ask",
    "advance_and_ask_for",
    "advance_one_and_ask",
    "trigger_advance_and_ask",
    "advance_launch_and_ask",
)


def _module(path: str) -> ModuleType:
    return importlib.import_module(path)


def _trigger_object() -> Any | None:
    """The trigger callable, or `None` while it does not yet exist.

    Deliberately tolerant of absence: this file is a guard on the three
    modules that must never reach it, and that claim is as meaningful
    before the trigger exists as after.
    """
    cascade = _module(CASCADE)
    for name in TRIGGER_NAMES:
        found = getattr(cascade, name, None)
        if callable(found):
            return found
    return None


@pytest.mark.parametrize("path", STILL_BOUND)
def test_a_still_bound_call_site_carries_no_advance_trigger_by_name(path: str) -> None:
    """SPECIFIED by the amended requirement: "every other path that records
    a step outcome ... remains fully bound by the SHALL NOT, exactly as
    before".

    `proposal.md` — What Changes says the same as a scope statement: the
    trigger is added "at the ClickUp webhook call site only ... and not at
    the other three call sites (`clickup_sync_job`, `automation_pass`,
    `automation_confirmation`), which keep today's convergence-only
    behavior".
    """
    module = _module(path)
    reachable = [name for name in TRIGGER_NAMES if hasattr(module, name)]
    assert reachable == [], (
        f"{path} carries an advance-and-ask trigger ({reachable}); the "
        "exception this change carves names the ClickUp webhook call site "
        "alone, and every other recording path stays bound by the SHALL NOT"
    )


@pytest.mark.parametrize("path", STILL_BOUND)
def test_a_still_bound_call_site_holds_no_alias_of_the_trigger(path: str) -> None:
    """The same clause, closed against a rename.

    Asserted separately from the name check because the name check alone
    is evaded by `from ... import advance_and_ask as _kick`: this compares
    attribute *values* against the trigger object itself, so an alias
    under any spelling is caught. Vacuous while the trigger does not exist
    — which the guard above is not — and that is why both are here.
    """
    trigger = _trigger_object()
    if trigger is None:
        pytest.skip(
            "the cascade trigger does not exist yet (`tasks.md` 1.1), so no "
            "module can hold an alias of it; the name guard beside this one "
            "carries the claim in the meantime"
        )
    module = _module(path)
    aliases = [name for name, value in vars(module).items() if value is trigger]
    assert aliases == [], (
        f"{path} holds the advance-and-ask trigger under {aliases}; renaming "
        "the import does not move the call site out of the SHALL NOT"
    )


def test_the_exception_names_the_webhook_and_the_recording_use_case_is_untouched() -> (
    None
):
    """SPECIFIED by the amended requirement, read for where the exception
    is *not*: it is "narrow and procedural — it names one call site, not a
    new advancement rule".

    The use case every recording path shares is the place a "new
    advancement rule" would land, and `proposal.md` — Impact puts it out
    of scope explicitly ("Explicitly not in scope: touching
    `record_step_outcome`"). A trigger reachable from
    `launch.application`'s public surface would mean exactly the
    generalization the requirement refuses, whichever call site invoked
    it.
    """
    application = importlib.import_module("commerce_ops.launch.application")
    reachable = [name for name in TRIGGER_NAMES if hasattr(application, name)]
    assert reachable == [], (
        "commerce_ops.launch.application exposes an advance-and-ask trigger "
        f"({reachable}); the exception is procedural and belongs to one "
        "driving adapter, not to the recording use case's own module surface"
    )


def test_the_exempt_call_site_and_the_bound_ones_are_distinct_modules() -> None:
    """Fixture guard, not a requirement.

    Every assertion above is vacuous if one of the module paths is wrong —
    a typo would import nothing and the parametrization would fail loudly,
    but a path that resolved to the *webhook* would make a bound call site
    silently exempt. Cheap to rule out, and it also keeps this file honest
    if a module is ever renamed.
    """
    assert EXEMPT not in STILL_BOUND
    for path in (*STILL_BOUND, EXEMPT, CASCADE):
        assert _module(path).__name__ == path


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - A trigger reached by an import *inside* a function body in one of the
#   three bound modules. It would evade both guards above. Accepted for
#   the reason in this module's docstring: it would break the repository's
#   own bare-global convention, which this change's `proposal.md` — Impact
#   reaffirms for exactly this import, so the guard's failure mode is a
#   convention violation that review sees rather than a silent one.
# - Driving each of the three passes to observe that no launch advanced.
#   The reason is in the docstring: three full pass harnesses for an
#   assertion satisfiable by a pass that reached no launch at all.
# - That the webhook call site *does* carry the trigger. That is the
#   change's positive claim, and it is asserted where it belongs, in
#   `test_clickup_webhook_triggers_the_advance_cascade.py`. Asserting it
#   here as well would make this preserve-the-boundary guard fail on an
#   absent target, which is precisely the failure mode
#   `test_recording_does_not_advance_a_launch.py` records having designed
#   its own file to avoid.
# ---------------------------------------------------------------------------
