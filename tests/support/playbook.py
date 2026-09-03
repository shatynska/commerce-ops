"""The gate specification, restated once for the whole suite.

These are **not** convenience constants. They are an independently written
statement of what the launch specification says the gates are, and tests assert
production's behaviour *against* them --
`test_playbook_coherence_by_status.py` reads
`assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)`.

So there is an obvious-looking change here that must never be made::

    # WRONG -- makes every such assertion vacuous
    from commerce_ops.launch.domain.launch_playbook import GATE_SEQUENCE
    SPECIFIED_GATE_ORDER = GATE_SEQUENCE

That test would then assert that production equals itself. Declaring the
literal **once** here instead of in 159 files changes nothing about its
independence; sourcing it from production destroys it. If the specification
changes, this file is edited by hand to match the specification -- never
regenerated from `launch_playbook.py`.

**The prohibition is on values, not on the module.** `gates()` below imports
`Gate` and `GateOpening`, and must: they are the subject's own types and there
is no other way to construct one. What is banned is any name carrying the
sequence or its openings -- `GATE_SEQUENCE`, `gate_position`,
`_SPECIFIED_GATES`, `_SPECIFIED_GATE_IDS`, `_GATE_POSITION`, `_FINAL_GATE`. A
test may use production's types freely and must never take production's answer
to the question it is asking.
"""

from __future__ import annotations

from typing import Final

from commerce_ops.launch.domain.launch_playbook import Gate, GateOpening

#: The eight gate identifiers in the order the specification fixes them.
#: Hand-maintained against the specification, never imported from production.
SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

#: The gates the specification says open only on a confirmation.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

#: The gate past which nothing acts on a launch.
FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]


def opening_for(identifier: str) -> GateOpening:
    """How the specification says the named gate opens."""
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def gates() -> tuple[Gate, ...]:
    """The eight gates in the specified order.

    A gate carries its identifier, position and opening mode and nothing else
    since `replace-metric-conditions-with-steps`: what it waits on is stated by
    the steps attached to it.

    Positions are numbered from one, matching `Gate.position`.
    """
    return tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
