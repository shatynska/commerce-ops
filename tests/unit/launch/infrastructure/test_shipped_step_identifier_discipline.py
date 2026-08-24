"""A shipped step's identifier carries its discipline as its second segment.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-playbook/spec.md`

Covers the clause the `MODIFIED` requirement *The shipped playbook carries
the authored step set* gained on the change's third review pass:

    A shipped step's identifier SHALL carry its declared discipline as its
    second segment (`lp.creative.008` is a `creative` step). This is what
    allows a surface composed from the identifier to omit the discipline
    without losing it, and it holds for every step of the authored set.

and the `AND` the same pass added to *Scenario: A step traces to its source
row*:

    AND the second segment of that identifier is the step's declared
    discipline.

**Why this is a load-bearing test rather than an observation.** The
`launch-clickup-sync` delta drops the discipline from a projected task's
name, and `design.md` Decision 4 justifies that solely by this property:
the discipline is "recoverable from the identifier's own second segment".
If a later authoring session added a step whose identifier and discipline
disagreed, the task name for that step would lose its discipline with
nothing anywhere reporting it. `tasks.md` 3.3 asks for exactly this
assertion, "rather than left as an observation".

**This test is expected to PASS on its first run, and that is the correct
result here — not the alarm `ai-toolkit:testing` describes.** That alarm
covers a test written against a target that does not exist yet. This test's
target *does* exist: the shipped `playbook_v1.yaml` already carries all 97
identifiers and disciplines, and `design.md` Decision 4 records the property
as verified across them on 2026-08-24. The test asserts nothing about the
`description` field this change adds. What it establishes is that the
property holds now, and — because `describe-playbook-steps` rewrites all 97
of those rows to add descriptions — that it still holds after that edit.

**Level.** The subject is shipped *data*; the loader is used only as the
means of reading it, exactly as `test_shipped_playbook_steps.py` records.
No I/O beyond reading the packaged file, so the fast unit tier is the
smallest level that can observe it.

Baseline recorded before this test was written:
`uv run pytest tests/unit tests/agents` — 585 passed, 23 failed. All 23
failures are the first test-writing pass's own tests, failing on the absent
`description` field; none is in this file's subject area.
"""

from __future__ import annotations

from commerce_ops.launch.domain.launch_playbook import StepDefinition
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)


def _shipped_steps() -> tuple[StepDefinition, ...]:
    return tuple(load_shipped_playbook().steps)


def _second_segment(identifier: str) -> str | None:
    """The identifier's second dot-separated segment, or `None`.

    DERIVED: that an identifier's segments are dot-separated. The delta
    names the segments only through its example (`lp.creative.008`), and
    the shipped identifiers are dotted slugs. Returning `None` rather than
    raising keeps a malformed identifier reportable alongside every other
    mismatch instead of aborting the comparison on the first one.
    """
    segments = identifier.split(".")
    if len(segments) < 2:
        return None
    return segments[1]


def test_every_shipped_identifier_carries_its_discipline_as_its_second_segment() -> (
    None
):
    """Scenario: A step traces to its source row (third THEN).

    WHEN any authored step is read from the loaded playbook
    THEN the second segment of that identifier is the step's declared
    discipline.

    Quantified over the whole authored set, because the requirement states
    it over every step ("it holds for every step of the authored set"), and
    reported as a full list of mismatches so a failure names every offending
    step rather than only the first.
    """
    steps = _shipped_steps()

    # Guard against a vacuous pass: an empty step list would satisfy every
    # assertion below. Non-emptiness is separately SPECIFIED by *The shipped
    # playbook loads with steps* and covered in
    # `test_shipped_playbook_steps.py`; it is restated here only so this
    # test cannot hold over nothing.
    assert steps, "the shipped playbook carries no steps to compare"

    mismatches = [
        (step.identifier, _second_segment(step.identifier), step.discipline.value)
        for step in steps
        if _second_segment(step.identifier) != step.discipline.value
    ]

    # SPECIFIED: "A shipped step's identifier SHALL carry its declared
    # discipline as its second segment".
    assert mismatches == []


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The identifier's *first* and *third* segments (`lp`, and the row
#   number). The delta constrains only the second one; asserting a shape
#   for the others would impose a constraint nobody stated.
# - That the property holds for a non-shipped, hand-authored playbook. The
#   requirement states it of "the authored set" — the shipped `v1` file —
#   and the load-time coherence rules deliberately do not include it, so a
#   test-authored playbook is free to violate it and many existing test
#   files do.
# - Whether the discipline could be *derived* from the identifier rather
#   than declared. The requirement keeps both and asserts they agree; it
#   does not make one the source of the other.
