"""The vendored reference step set, checked against its own rules.

Covers `seed-the-reference-step-set`'s tasks 3.1-3.11 and 3.20: that the
committed `playbook_reference.yaml` is what the recorded rules produce, that
every field either transcribes, derives, carries across or is authored, and
that the file loads through the domain's own rulebook.

The last of those matters most: 3.20 asserts the generator's output equals the
committed file, so the rules `design.md` records and the data cannot drift.
That equality is what justified deriving 255 gate placements rather than
judging them one at a time.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    framework_gates,
)
from commerce_ops.seed_playbook import vendored_definitions
from commerce_ops.shared.domain.discipline import Discipline

_ROOT: Final = Path(__file__).resolve().parents[3]
_VENDORED: Final = _ROOT / "alembic" / "data" / "playbook_reference.yaml"
_REFERENCE: Final = _ROOT / "docs" / "reference" / "product-launch.md"

# SPECIFIED (delta): rows that restate a gate's authored metric condition are
# not seeded — one obligation is expressed once.
METRIC_RESTATEMENTS: Final = frozenset(
    {
        "lp.inventory.040",
        "lp.inventory.041",
        "lp.strategy.033",
        "lp.strategy.025",
        "lp.ppc.048",
        "lp.finance.036",
    }
)

# SPECIFIED (delta): the closed trimming set.
_TERMINAL: Final = ";:,."

_MARKERS: Final = ("TOS RISK:", "EU:", "NOTE:")


def _reference_rows() -> dict[str, dict[str, str]]:
    """Every ID-bearing row of the reference document, parsed here rather
    than imported, so the file is checked against the document and not
    against the generator's reading of it."""
    lines = _REFERENCE.read_text(encoding="utf-8").split("\n")
    rows: dict[str, dict[str, str]] = {}
    for index, line in enumerate(lines):
        bullet = re.match(r"^\s+- (.*?)\s*$", line)
        if not bullet:
            continue
        meta = lines[index + 1] if index + 1 < len(lines) else ""
        if not meta.startswith("  **"):
            continue
        identifier = re.search(r"\*\*ID:\*\* (\S+)", meta)
        if not identifier:
            continue
        when = re.search(r"\*\*WHEN:\*\* (.+?) ·", meta)
        source = re.search(r"\*\*SOURCE:\*\* (.+?) ·", meta)
        rows[identifier.group(1)] = {
            "text": bullet.group(1),
            "when": when.group(1).strip() if when else "",
            "source": source.group(1).strip() if source else "",
        }
    return rows


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    return list(yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))["steps"])


@pytest.fixture(scope="module")
def rows() -> dict[str, dict[str, str]]:
    return _reference_rows()


def test_the_vendored_set_constructs_a_playbook() -> None:
    """3.1 — SPECIFIED: the seeded set loads through the same rulebook every
    load and every write applies."""
    playbook = LaunchPlaybook(
        version="reference-v1",
        gates=framework_gates(),
        steps=vendored_definitions(),
    )
    assert len(playbook.authored_steps) == 352
    # SPECIFIED: every step is a draft, so none is served and the playbook is
    # not ready — the state `serve-only-a-ready-playbook` made representable.
    assert playbook.served_steps == ()
    assert not playbook.is_ready
    assert len(playbook.unheld_gates) == 8


def test_every_reference_row_appears_except_the_restatements(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """3.2 — SPECIFIED: every ID-bearing row of every area appears, except
    those excluded for restating a gate's authored metric condition."""
    seeded = {step["identifier"] for step in steps}
    expected = set(rows) - METRIC_RESTATEMENTS

    assert seeded == expected, (
        f"missing: {sorted(expected - seeded)}; extra: {sorted(seeded - expected)}"
    )
    assert len(seeded) == 352
    assert not (seeded & METRIC_RESTATEMENTS)


def test_every_description_re_derives_from_its_row(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """3.3 — SPECIFIED: the description is the row's text under the closed
    trimming rule. This is the property that keeps the reference text
    checkable now that the name no longer carries it."""
    for step in steps:
        expected = rows[step["identifier"]]["text"].rstrip()
        while expected and expected[-1] in _TERMINAL + " ":
            expected = expected[:-1].rstrip()
        assert step["description"] == expected, step["identifier"]


def test_no_other_character_is_stripped(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """3.3 — the closed set is closed: a row ending in a quote, a parenthesis
    or a `+` keeps it, because each is part of what the row says."""
    kept = [
        step
        for step in steps
        if step["description"] and step["description"][-1] in "'\")+"
    ]
    assert kept, "no row exercises the closed-set boundary; the check is vacuous"
    for step in kept:
        raw = rows[step["identifier"]]["text"].rstrip()
        # Nothing but trailing whitespace and the four terminal marks was
        # removed, so the description is a prefix of the row's own text.
        assert raw.startswith(step["description"]), step["identifier"]
        assert set(raw[len(step["description"]) :]) <= set(_TERMINAL + " ")


def test_every_name_is_a_single_short_line(steps: list[dict[str, Any]]) -> None:
    """3.4 — SPECIFIED: a name is one line and at most 80 characters, because
    it is composed into a task tracker's title."""
    for step in steps:
        name = step["name"]
        assert name and name.strip(), step["identifier"]
        assert "\n" not in name and "\r" not in name, step["identifier"]
        assert len(name) <= 80, f"{step['identifier']}: {len(name)} chars"


def test_a_rows_leading_marker_survives_into_its_name(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """3.5 — SPECIFIED: markers are what a reader scans for, and two of the
    ten `TOS RISK` rows carry `hazard: none`, so the marker is the only place
    the warning is visible."""
    marked = 0
    for step in steps:
        text = rows[step["identifier"]]["text"]
        for marker in _MARKERS:
            if text.startswith(marker):
                assert step["name"].startswith(marker), step["identifier"]
                marked += 1
    assert marked >= 8, f"only {marked} marker rows checked"


def test_a_numeric_threshold_survives_into_its_name(
    steps: list[dict[str, Any]],
) -> None:
    """3.6 — SPECIFIED: a threshold is the work, not a detail of it.

    Checked over the rows whose own name states a bare percentage or a
    money/day figure: where the authored name kept a number at all, it is one
    the description also states, so no threshold was invented.
    """
    checked = 0
    for step in steps:
        numbers = set(re.findall(r"\d[\d,]*", step["name"]))
        if not numbers:
            continue
        in_description = set(re.findall(r"\d[\d,]*", step["description"]))
        assert numbers <= in_description, (
            f"{step['identifier']}: name states {numbers - in_description} "
            f"which its description does not"
        )
        checked += 1
    assert checked >= 50, f"only {checked} names carry a number"


def test_every_step_is_an_unowned_human_draft(steps: list[dict[str, Any]]) -> None:
    """3.7 — SPECIFIED: nothing is served until someone reviews and activates
    it, which is the workflow the four-status vocabulary exists for."""
    for step in steps:
        assert step["status"] == "draft", step["identifier"]
        assert step["kind"] == "human", step["identifier"]
        assert step["assignees"] == [], step["identifier"]
        # A human step may carry neither; the domain rejects a set that does.
        assert "confirmer" not in step
        assert "handler" not in step
        # SPECIFIED (design): a slot belongs to an active step, so a seeded
        # draft carries none.
        assert "display_order" not in step, step["identifier"]


def test_both_hazards_are_present_and_prohibited_tactics_never_block(
    steps: list[dict[str, Any]],
) -> None:
    """3.8 — SPECIFIED: hazard coverage is kept, because the human pass
    already classified rows carrying both, so requiring one of each
    classifies nothing new."""
    hazards = [step["hazard"] for step in steps]
    assert Hazard.PROHIBITED_TACTIC.value in hazards
    assert Hazard.COMPLIANCE_OBLIGATION.value in hazards
    for step in steps:
        if step["hazard"] == Hazard.PROHIBITED_TACTIC.value:
            assert step["blocking"] is False, step["identifier"]


def test_every_anchor_kind_and_discipline_is_represented(
    steps: list[dict[str, Any]],
) -> None:
    """3.9 — SPECIFIED: no part of the vocabulary the playbook defines goes
    unrepresented by the work it ships with."""
    kinds = {step["timing_anchor"]["kind"] for step in steps}
    assert kinds == {"offset", "window", "open-ended", "recurring"}
    disciplines = {step["discipline"] for step in steps}
    assert disciplines == {member.value for member in Discipline}


def test_each_identifier_carries_its_discipline(
    steps: list[dict[str, Any]],
) -> None:
    """3.10 — SPECIFIED: this is what lets a surface composed from the
    identifier omit the discipline without losing it."""
    for step in steps:
        assert step["identifier"].split(".")[1] == step["discipline"], step[
            "identifier"
        ]


def test_the_human_pass_is_carried_across_unchanged(
    steps: list[dict[str, Any]],
) -> None:
    """3.11 — SPECIFIED: where the reference document's rows have already
    been classified by a human pass, those classifications are carried across
    unchanged rather than re-derived."""
    curated = {
        step["identifier"]: step
        for step in yaml.safe_load(
            (_ROOT / "alembic" / "data" / "playbook_v1.yaml").read_text(
                encoding="utf-8"
            )
        )["steps"]
    }
    seeded = {step["identifier"]: step for step in steps}
    compared = 0
    for identifier, previous in curated.items():
        if identifier in METRIC_RESTATEMENTS:
            continue
        current = seeded[identifier]
        assert current["gate"] == previous["gate"], identifier
        assert current["scope"] == previous["scope"], identifier
        assert current["blocking"] == previous["blocking"], identifier
        assert current["hazard"] == previous.get("hazard", "none"), identifier
        compared += 1
    assert compared >= 90, f"only {compared} carried rows compared"


def test_the_timing_anchor_follows_its_rows_when(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """3.9 (anchor half) — SPECIFIED (design): the closed WHEN mapping, with
    the zero-based correction the domain's own docstring warns about.

    `Day 1` is the launch day, so offset 0 — not 1. `Day 60+` starts on the
    sixtieth day, so 59. Getting this wrong shifts every post-launch anchor
    by one day, uniformly, which is invisible by inspection.
    """
    expected: dict[str, dict[str, Any]] = {
        "Day 1": {"kind": "offset", "days": 0},
        "Day 60+": {"kind": "open-ended", "start": 59},
        "Week 1": {"kind": "window", "start": 0, "end": 6},
        "Week 1-2": {"kind": "window", "start": 0, "end": 13},
        "Week 2-4": {"kind": "window", "start": 7, "end": 27},
        "Week 5-8": {"kind": "window", "start": 28, "end": 55},
        "Daily": {"kind": "recurring", "cadence": "daily"},
        "Weekly": {"kind": "recurring", "cadence": "weekly"},
        "Biweekly": {"kind": "recurring", "cadence": "biweekly"},
        "Monthly": {"kind": "recurring", "cadence": "monthly"},
    }
    for step in steps:
        when = rows[step["identifier"]]["when"]
        countdown = re.fullmatch(r"T-(\d+)", when)
        want = (
            {"kind": "offset", "days": -int(countdown.group(1))}
            if countdown
            else expected[when]
        )
        assert step["timing_anchor"] == want, f"{step['identifier']} ({when})"


def test_provenance_is_the_rows_source_citation(
    steps: list[dict[str, Any]], rows: dict[str, dict[str, str]]
) -> None:
    """SPECIFIED: every seeded step traces to exactly one reference row."""
    for step in steps:
        assert step["provenance"] == rows[step["identifier"]]["source"], step[
            "identifier"
        ]


def test_the_committed_file_is_what_the_generator_produces() -> None:
    """3.20 — SPECIFIED (design): the rules and the data cannot drift.

    This is what makes the recorded rules reviewable, and what justified
    deriving 255 gate placements rather than judging them one at a time. If
    this fails, either the generator changed or the file was hand-edited, and
    the rules `design.md` records no longer describe what ships.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_playbook_reference",
        _ROOT / "alembic" / "data" / "generate_playbook_reference.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    built = module.build()
    built.pop("_tally")
    committed = yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))
    assert built == committed
