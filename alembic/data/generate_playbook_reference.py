"""Generate `playbook_reference.yaml` from the reference document.

Every field of a seeded step is either transcribed from
`docs/reference/product-launch.md`, derived from it by a rule
`seed-the-reference-step-set`'s design.md records, carried across from the
earlier human pass, or authored in `playbook_reference_names.py`. Nothing is
invented here that is not one of those four.

Run it to regenerate the vendored file:

    uv run python alembic/data/generate_playbook_reference.py

A test asserts that its output equals the committed file, so the rules and the
data cannot drift — which is what makes the rules reviewable, and what
justified deriving 255 gate placements rather than judging them one by one.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_REFERENCE = _ROOT / "docs" / "reference" / "product-launch.md"
_CURATED = _HERE / "playbook_v1.yaml"
_OUTPUT = _HERE / "playbook_reference.yaml"

sys.path.insert(0, str(_HERE))
from playbook_reference_names import NAMES

# Rows whose own words make passing a gate conditional on them. Until
# `replace-metric-conditions-with-steps` these six were *excluded* from the
# seed, each restating a condition a gate authored, so that one obligation was
# expressed once. Gates author no conditions now, so excluding them would leave
# the obligation expressed nowhere a launch can resolve: they are seeded,
# blocking on the gate their words condition.
#
# The mapping is `design.md` Decision 8's, transcribed from
# `_AUTHORED_METRIC_CONDITIONS` before that constant was deleted. Six rows,
# four identifiers: `lp.inventory.040` and `.041` state two readings of one
# quantity, and `lp.ppc.048` states four qualitative criteria naming no single
# quantity, so it blocks carrying none rather than an invented name no
# observation could ever resolve to.
GATE_CONDITIONING_ROWS: dict[str, tuple[str, str | None]] = {
    "lp.inventory.040": ("stock-ready", "units-fulfillable"),
    "lp.inventory.041": ("stock-ready", "units-fulfillable"),
    "lp.strategy.025": ("phase-one-complete", "sales-velocity"),
    "lp.strategy.033": ("phase-one-complete", "organic-share"),
    "lp.ppc.048": ("phase-one-complete", None),
    "lp.finance.036": ("graduated", "tacos"),
}

# `scope` is the one field the reference document does not speak to. Seven of
# these carry an `EU:` prefix; the other five name a marketplace without one,
# and no expression separates them from rows that merely mention a country —
# so they are listed, and checkable.
MARKET_SCOPED: frozenset[str] = frozenset(
    {
        "lp.finance.013",
        "lp.finance.014",
        "lp.finance.017",
        "lp.setup.014",
        "lp.setup.015",
        "lp.setup.017",
        "lp.setup.018",
        "lp.listing.018",
        "lp.listing.020",
        "lp.price.012",
        "lp.external.004",
        "lp.external.005",
    }
)

GATES: tuple[str, ...] = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)
_POSITION = {gate: index for index, gate in enumerate(GATES)}

# Stage 1 — the area proposes.
AREA_GATE: dict[int, str] = {
    1: "commit",
    2: "order",
    3: "listable",
    4: "listable",
    5: "stock-ready",
    6: "live",
    7: "ignition",
    8: "phase-one-complete",
    9: "phase-one-complete",
    10: "graduated",
}

# Stage 2 — the timing disposes. Each WHEN admits a set of gates and names the
# home it falls back to when the area's proposal is not among them.
WHEN_GATES: dict[str, tuple[frozenset[str], str | None]] = {
    "T-90": (frozenset({"commit", "order"}), "commit"),
    "T-60": (frozenset({"commit", "order", "listable"}), "order"),
    "T-30": (frozenset({"listable", "stock-ready"}), "listable"),
    "T-15": (frozenset({"listable", "stock-ready", "live"}), "listable"),
    "T-14": (frozenset({"listable", "stock-ready", "live"}), "listable"),
    "T-7": (frozenset({"live"}), "live"),
    "Day 1": (frozenset({"ignition"}), "ignition"),
    "Week 1": (frozenset({"ignition"}), "ignition"),
    "Week 1-2": (frozenset({"ignition"}), "ignition"),
    "Week 2-4": (frozenset({"phase-one-complete"}), "phase-one-complete"),
    "Week 5-8": (
        frozenset({"phase-one-complete", "graduated"}),
        "phase-one-complete",
    ),
    "Day 60+": (frozenset({"graduated"}), "graduated"),
    "Monthly": (frozenset({"graduated"}), "graduated"),
    # A cadence states no position, so it never overrides the area.
    "Daily": (frozenset(GATES), None),
    "Weekly": (frozenset(GATES), None),
    "Biweekly": (frozenset(GATES), None),
}


def gate_for(row: dict[str, Any]) -> str:
    """The three-stage rule: area proposes, timing disposes, discipline corrects."""
    gate = AREA_GATE[row["area"]]
    admitted, home = WHEN_GATES[row["when"]]
    if gate not in admitted:
        assert home is not None  # a cadence admits every gate, so never here
        gate = home
    pre_launch = row["when"].startswith("T-")
    # Campaigns are built before launch and armed at go-live (`lp.ppc.019`).
    if row["agent"] == "PPC" and pre_launch and _POSITION[gate] < _POSITION["live"]:
        gate = "live"
    # Physical stock cannot resolve before the stock gate.
    if (
        row["agent"] == "INVENTORY"
        and row["when"] in {"T-30", "T-15", "T-14"}
        and _POSITION[gate] < _POSITION["stock-ready"]
    ):
        gate = "stock-ready"
    return gate


def anchor_for(when: str) -> dict[str, Any]:
    """The WHEN column as a timing anchor.

    Zero-based, and the source is one-based: `Day 1` is the launch day, so
    offset 0; `Day 60+` starts on the sixtieth day, so 59; `Week 1` is the
    launch week, so days 0-6. Countdown values need no adjustment, being
    already relative to the launch day.
    """
    countdown = re.fullmatch(r"T-(\d+)", when)
    if countdown:
        return {"kind": "offset", "days": -int(countdown.group(1))}
    if when == "Day 1":
        return {"kind": "offset", "days": 0}
    if when == "Day 60+":
        return {"kind": "open-ended", "start": 59}
    if when == "Week 1":
        return {"kind": "window", "start": 0, "end": 6}
    if when == "Week 1-2":
        return {"kind": "window", "start": 0, "end": 13}
    if when == "Week 2-4":
        return {"kind": "window", "start": 7, "end": 27}
    if when == "Week 5-8":
        return {"kind": "window", "start": 28, "end": 55}
    if when in {"Daily", "Weekly", "Biweekly", "Monthly"}:
        return {"kind": "recurring", "cadence": when.lower()}
    raise ValueError(f"reference row carries an unmapped WHEN value {when!r}")


def trimmed(text: str) -> str:
    """The row's text under the closed trimming rule.

    Trailing whitespace, then any trailing `;` `:` `,` `.` — repeating until
    neither remains. Deliberately closed: rows end variously in a closing
    quote, a parenthesis, or a `+` (as in "A+"), and each is part of what the
    row says.
    """
    return re.sub(r"[;:,.\s]+$", "", text).strip()


def reference_rows() -> list[dict[str, Any]]:
    """Every ID-bearing row, with the area, agent and metadata it sits under."""
    lines = _REFERENCE.read_text(encoding="utf-8").split("\n")
    area: int | None = None
    agent: str | None = None
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        heading = re.match(r"^- (\d+)\. ", line)
        if heading:
            area = int(heading.group(1))
            continue
        bullet = re.match(r"^(\s+)- (.*?)\s*$", line)
        if not bullet:
            continue
        indent, text = len(bullet.group(1)), bullet.group(2)
        if indent == 4:
            agent = text
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if not following.startswith("  **"):
            continue
        identifier = re.search(r"\*\*ID:\*\* (\S+)", following)
        if not identifier:
            continue
        when = re.search(r"\*\*WHEN:\*\* (.+?) ·", following)
        source = re.search(r"\*\*SOURCE:\*\* (.+?) ·", following)
        rows.append(
            {
                "id": identifier.group(1),
                "area": area,
                "agent": agent,
                "text": text,
                "when": when.group(1).strip() if when else None,
                "source": source.group(1).strip() if source else None,
            }
        )
    return rows


# The gate sequence, duplicated here rather than imported: this script is a
# data generator run by hand and must not depend on the application's import
# graph, the same reason the seed migration vendors its own copy.
GATE_ORDER: tuple[str, ...] = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

# The seven steps whose calendar anchor falls before their own gate can be
# reached, each given the earlier gate its anchor implies
# (`let-a-step-say-when-it-starts`, tasks 8.2-8.4). Keyed on identifier and
# not on status: every step in this file is `draft`, so status cannot select
# them, and these are the same seven that are `active` in the stored set.
#
# Reviewed individually and never derived by a rule: the disagreement between
# the calendar and the gate sequence is a property of the authored playbook.
# The remaining sixteen anchor-conflicting steps take the default, because
# choosing a start gate for a step nobody has reviewed is an authoring
# judgement made once, at activation, by a person who can see it.
REVIEWED_START_GATES: dict[str, str] = {
    # `stock-ready` cannot be reached before T-7; goods must be ordered
    # before they can be stocked.
    "lp.inventory.019": "order",  # first-order sizing, T-30
    "lp.inventory.008": "order",  # pre-shipment inspection, T-30
    "lp.inventory.018": "order",  # barcode TOS, T-30
    # Campaign preparation deliberately precedes going live.
    "lp.ppc.001": "listable",  # naming convention, T-14
    "lp.ppc.002": "listable",  # keyword bucketing, T-14
    "lp.ppc.004": "listable",  # search-volume ceiling, T-14
    # `listable` is itself reachable only by T-60, so releasing this one
    # there would leave it no margin against its own anchor; `order` is
    # reachable by T-90.
    "lp.ppc.003": "order",  # never-keywords list, T-60
}


def start_gate_for(identifier: str, gate: str) -> str:
    """When a step may start: its own gate, with two exceptions.

    A step belonging to the **final gate** takes the gate two before it.
    Its own gate is refused as a start gate — every consumer stands down
    once a launch reaches it, so a step released only there is released
    where nothing will act on it — and a single-gate window can be
    crossed between two passes, since gate progression advances a launch
    as far as its recorded state permits in one run. Two gates is a
    margin, not a guarantee, and the nearest gate meeting it rather than
    the earliest: releasing work sooner than it needs to be is the harm
    this field exists to remove.

    A step whose anchor falls before its own gate can be reached takes the
    earlier gate that anchor implies, for the seven reviewed above.
    """
    reviewed = REVIEWED_START_GATES.get(identifier)
    if reviewed is not None:
        return reviewed
    # Only the final gate. Every other gate can serve as its own steps'
    # start gate, because a launch cannot leave a gate until that gate's
    # own blocking work is recorded — which is what makes even a
    # one-gate window survivable everywhere else.
    if gate == GATE_ORDER[-1]:
        return GATE_ORDER[-3]
    return gate


def build() -> dict[str, Any]:
    curated = {
        step["identifier"]: step
        for step in yaml.safe_load(_CURATED.read_text(encoding="utf-8"))["steps"]
    }
    steps: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    for row in reference_rows():
        conditioning = GATE_CONDITIONING_ROWS.get(row["id"])
        previous = curated.get(row["id"])
        if previous is not None:
            # The earlier human pass is carried across verbatim, not re-derived.
            gate = previous["gate"]
            scope = previous["scope"]
            blocking = previous["blocking"]
            hazard = previous.get("hazard", "none")
            tally["carried"] += 1
        else:
            gate = gate_for(row)
            scope = "market" if row["id"] in MARKET_SCOPED else "product"
            # `blocking` and `hazard` are never derived: blocking is a decision
            # made when a step is activated, and a wrong `prohibited-tactic`
            # produces work that can never be done, only refused.
            blocking = False
            hazard = "none"
            tally["derived"] += 1
        if conditioning is not None:
            # The row's own words condition this gate, so it holds it: gate and
            # blocking come from the mapping rather than from derivation, and
            # never from a carried-across earlier pass, which predates the
            # decision to seed these rows at all.
            gate, _ = conditioning
            blocking = True
            tally["conditioning"] += 1
        if hazard == "prohibited-tactic":
            blocking = False  # coherence: it can only ever terminate in Refused
        steps.append(
            {
                "identifier": row["id"],
                "name": NAMES[row["id"]],
                "description": trimmed(row["text"]),
                "gate": gate,
                "discipline": row["agent"].lower(),
                "scope": scope,
                "timing_anchor": anchor_for(row["when"]),
                "blocking": blocking,
                "kind": "human",
                "status": "draft",
                "hazard": hazard,
                "assignees": [],
                "starts_at_gate": start_gate_for(row["id"], gate),
                "provenance": row["source"],
                **(
                    {"metric_id": conditioning[1]}
                    if conditioning is not None and conditioning[1] is not None
                    else {}
                ),
            }
        )
    return {"version": "reference-v1", "steps": steps, "_tally": dict(tally)}


def main() -> int:
    built = build()
    tally = built.pop("_tally")
    _OUTPUT.write_text(
        yaml.safe_dump(built, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"wrote {len(built['steps'])} steps to {_OUTPUT.relative_to(_ROOT)}")
    print(f"  {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
