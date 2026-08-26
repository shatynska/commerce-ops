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

# Rows that restate a condition a gate already authors as a metric condition.
# One obligation is expressed once, so they are not seeded — the list
# `tests/integration/launch/test_playbook_seed.py` already records.
METRIC_RESTATEMENTS: frozenset[str] = frozenset(
    {
        "lp.inventory.040",
        "lp.inventory.041",
        "lp.strategy.033",
        "lp.strategy.025",
        "lp.ppc.048",
        "lp.finance.036",
    }
)

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


def build() -> dict[str, Any]:
    curated = {
        step["identifier"]: step
        for step in yaml.safe_load(_CURATED.read_text(encoding="utf-8"))["steps"]
    }
    steps: list[dict[str, Any]] = []
    tally: Counter[str] = Counter()
    for row in reference_rows():
        if row["id"] in METRIC_RESTATEMENTS:
            tally["excluded"] += 1
            continue
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
                "needs_confirmation": False,
                "status": "draft",
                "hazard": hazard,
                "assignees": [],
                "provenance": row["source"],
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
