"""The post-`/start-launch` confirmation no longer promises a stale cadence.

Derived strictly from the delta spec's own supporting text and
`proposal.md`/`tasks.md` of the OpenSpec change
`trigger-clickup-projection-on-launch-events`
(`openspec/changes/trigger-clickup-projection-on-launch-events/`).

This is not one of the delta spec's nine `#### Scenario:` blocks — the
requirement itself states no wording — but `tasks.md` 5.1 names it as a
concrete correction this change carries: `CLICKUP_SYNC_CADENCE_DESCRIPTION`
in `slack_entry.py` currently promises tasks will "appear within about 10
minutes", which was accurate before `shift-clickup-completions-to-webhook`
widened the periodic pass's cadence to twice daily and is false regardless
of what this change does; this change's own eager trigger makes the true
answer "near-immediately, barring the same per-launch failure modes
`launch-clickup-sync` already contains" rather than any fixed number of
minutes. `proposal.md` — Why: "understating the real wait by up to ~70x
regardless of what this change does" is the defect this test guards
against reappearing.

## Level

The constant's own value, read off the module rather than transcribed —
the same convention `test_advance_and_ask.py`'s `_cool_off()` already
uses for a module-owned constant, so a future change to the exact wording
does not make this file assert text nobody wrote. Reading a public
constant's runtime value is not reading the module's implementation; the
constant's *content* is the thing `tasks.md` 5.1 asks this file to
constrain.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 5.1: the string must stop claiming "the pass runs
every ten minutes" or an equivalent fixed short cadence, and must instead
describe near-immediate appearance.

INVENTED: the constant's exact final wording — no artifact fixes it, only
what it must no longer claim and what it should now convey. This file
asserts the negative (no stale minute-count survives) and a light positive
(the replacement text reads as "soon", not as silence on the subject) —
guessing an exact phrase would impose a contract nobody agreed to.

## Expected first-run state

The constant exists today and still carries its stale wording, so this
test is expected to fail on a **wrong value**, not an absent target.

Baseline recorded before this test was written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import importlib
import re
from typing import Final

import pytest

SLACK_ENTRY_MODULE: Final = "commerce_ops.launch.infrastructure.driving.slack_entry"
CONSTANT_NAME: Final = "CLICKUP_SYNC_CADENCE_DESCRIPTION"

#: Any of these, read as a whole number of minutes, is the stale claim
#: `tasks.md` 5.1 removes. Matched loosely (digits or a spelled-out small
#: number followed by "minute(s)") so a rewording that keeps the same
#: false number under different phrasing still fails here.
_STALE_MINUTE_PATTERN: Final = re.compile(
    r"\b(\d{1,3}|ten|five|fifteen|twenty|thirty)\s+minutes?\b", re.IGNORECASE
)

#: Words a near-immediate replacement plausibly uses. Not exhaustive by
#: design — the exact wording is INVENTED — only enough to establish the
#: replacement says *something* about promptness rather than falling
#: silent on the subject the original sentence existed to address.
_NEAR_IMMEDIATE_MARKERS: Final = (
    "immediately",
    "shortly",
    "momentarily",
    "right away",
    "soon",
    "moments",
    "quickly",
)


def _constant() -> str:
    module = importlib.import_module(SLACK_ENTRY_MODULE)
    value = getattr(module, CONSTANT_NAME, None)
    if value is None:
        pytest.fail(
            f"{module.__name__} exposes no `{CONSTANT_NAME}`; if it has been "
            "renamed, correct `CONSTANT_NAME` to match — do not remove the "
            "constant to make this pass, its wording is what "
            "`slack_entry.py`'s confirmation still needs to show."
        )
    assert isinstance(value, str), (
        f"{CONSTANT_NAME} is not a string ({type(value)!r}); correct this "
        "file's reading of it"
    )
    return value


def test_the_cadence_description_no_longer_promises_a_fixed_minute_count() -> None:
    """`tasks.md` 5.1: the description must stop claiming a fixed short
    cadence ("within about 10 minutes") that has been false since
    `shift-clickup-completions-to-webhook` widened the pass to twice daily,
    and would remain false regardless of what this change does to the
    creation direction — this change's own point is that the true answer
    is no longer a number of minutes at all.
    """
    description = _constant()
    match = _STALE_MINUTE_PATTERN.search(description)
    assert match is None, (
        f"{CONSTANT_NAME} still promises a fixed minute count "
        f"({match.group(0)!r}), which has been false since the pass's "
        f"cadence was widened to twice daily: {description!r}"
    )


def test_the_cadence_description_now_reads_as_near_immediate() -> None:
    """DERIVED from `proposal.md`'s own stated fix: "tasks appear
    immediately, barring the same per-launch failure modes
    `launch-clickup-sync` already contains". No scenario fixes an exact
    phrase, so this asserts only that the replacement conveys promptness
    rather than describing a wait at all.
    """
    description = _constant().lower()
    assert any(marker in description for marker in _NEAR_IMMEDIATE_MARKERS), (
        f"{CONSTANT_NAME} does not read as describing near-immediate "
        f"appearance under any of {_NEAR_IMMEDIATE_MARKERS}: {description!r}"
    )
