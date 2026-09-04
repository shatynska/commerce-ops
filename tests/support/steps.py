"""Building a step definition, and the blocking filler that holds a gate.

135 files declared a `_step` of their own, in 77 distinct forms -- but all 135
had the same body::

    attributes: dict[str, Any] = { ...17 keys... }
    attributes.update(overrides)
    return StepDefinition(**attributes)

One design with 77 default sets, not 77 designs. The canonical set below is
each key's modal value across the 121 declarations whose signature is
`**overrides`-only; the other 14 require `identifier` positionally and take a
one-line wrapper instead of a partial.

Against this set, 69 of the 121 need two overrides or fewer and 94 need four or
fewer, so a migrated file keeps::

    _step = functools.partial(step, discipline=Discipline.STRATEGY, gate="commit")

`functools.partial` gives the right precedence -- a keyword passed at the call
site wins over the partial's -- so every existing `_step(...)` call keeps
working untouched.

**A key no caller sets is not defaulted here.** `confirmer`, `starts_at_gate`,
`after_steps` and `metric_id` are omitted rather than given a value, so
`StepDefinition`'s own defaults still apply. The four partially-set keys that
*are* canonicalised (`description`, `assignees`, `handler`) carry exactly the
dataclass's own default, which is what keeps that rule consistent rather than
merely convenient.
"""

from __future__ import annotations

from typing import Any

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from tests.support.fixtures import any_discipline


def step(**overrides: Any) -> StepDefinition:
    """A step definition, with `overrides` applied over the canonical set."""
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def hold(gate: str, **overrides: Any) -> StepDefinition:
    """A blocking step holding `gate`.

    **Three defaults, and no more.** 104 files declared a `_hold`, and the
    temptation is to give this every keyword they pass. That is the wrong
    count: a keyword a variant *omits* is not absent, it resolves to `step()`'s
    canonical value, and that value has to compete. Counted over all 104 with
    omissions scored as the value they actually produce, only three keys have a
    majority that differs from `step()`:

        blocking    True                                      89 of 104
        identifier  f"hold.{gate}"                            86
        name        f"Blocking work holding the {gate} gate"  57

    Everything else inherits. `kind` looks like `AUTOMATED` if you count only
    the 75 files that pass it (49 do) -- but 29 more inherit `HUMAN`, so
    `HUMAN` wins 55 to 49. `handler` looks like `"fixture.holding_check"` (41
    of 74) and loses to `None` 51 to 41 the same way. `assignees` and
    `timing_anchor` invert outright, 79 to 19 and 87 to 10.

    **All 104 now compose over this** (`share-the-playbook-builders`,
    2026-09-04). The 73 that `share-the-unit-test-harness` left local were
    blocked on their file's `_step` being opaque; once all 135 `_step`
    declarations reached the shared builder, each file's own defaults became a
    readable keyword set and reconciling them was forwarding that set. Proved
    at every call site by a plugin that wrapped all 73 in place and compared
    whole objects: 8,373 comparisons, zero divergences.

    Two things that proof caught, worth keeping in view for the next slice.
    **A delta must be derived by running the local, never by reading it**: a
    static pass over the same 73 over-reports `discipline` at 26 against 13 and
    `confirmer` at 22 against 4, because it cannot see that
    `next(iter(Discipline))` and `any_discipline()` evaluate equal. And **an
    expression harvested from a file may not be evaluable outside it**:
    `test_launch_report_carried_finding` spells `name` as
    `f"Work {identifier} asks for"`, where `identifier` is a parameter of that
    file's `_step`. Harvest it without validating and the harness fails at the
    call site instead of at build time.
    """
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "blocking": True,
    }
    attributes.update(overrides)
    return step(**attributes)
