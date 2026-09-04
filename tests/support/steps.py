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
    """
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "blocking": True,
    }
    attributes.update(overrides)
    return step(**attributes)
