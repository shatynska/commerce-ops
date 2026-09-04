"""The six threshold rows, seeded as blocking metric steps.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-playbook/spec.md`

Covers, from the ADDED requirement *The seeded step set carries every
reference row*, the scenarios this change writes or rewrites:

- *Every area is fully represented*, whose "except those excluded for
  restating a gate's authored metric condition" this delta strikes in
  favour of "with no exception",
- *A threshold row is seeded as a blocking metric step* (new),
- *A row merely mentioning a number is an ordinary step* (new),
- *A metric identifier names the quantity alone* (new).

Its nine unchanged scenarios stay covered by
`tests/unit/launch/test_playbook_reference_set.py` (the vendored file)
and `tests/integration/launch/test_seeded_step_fields.py` (the served
set). Nothing here edits either; the assertion in the first of them that
the six identifiers are **absent** is superseded by this file and is
recorded in `test-manifest.md` as an obsolete-test candidate
(`tasks.md` 3.3 inverts it).

## The selection is editorial; only the resulting set is asserted

The delta says so in its own words: which rows qualify "is made when a
row is transcribed, by whoever transcribes it — it is an editorial
reading, not a computation — so what a test asserts is the resulting
set, not the selection".

So this file **never re-derives which rows condition a gate**. It names
the six identifiers the REMOVED requirement's Migration paragraph names,
and asserts what the seed did with them; and it asserts that no seventh
row declares a metric identifier, which is the resulting-set claim from
the other side. It does not read the reference document's wording to
decide whether a row qualifies, and a later change that adds a seventh
qualifying row corrects `SEEDED_METRIC_STEPS` here rather than being
caught out by a rule this file invented.

Likewise, **which metric identifier each of the six carries is not
asserted**. `tasks.md` 1.2 transcribes them out of
`_AUTHORED_METRIC_CONDITIONS` during implementation and 1.3 resolves
which gate each holds; neither answer exists in the change's artifacts,
so a test fixing them would be inventing the mapping rather than
checking it. What is asserted is that each carries one, and that what it
carries obeys the naming rule the delta does state.

## Level

The vendored `alembic/data/playbook_reference.yaml`, read as data. The
file is what the preparation step inserts, so it is the smallest unit
that can observe what the seed carries — no database is needed, and the
integration tier's sibling
(`tests/integration/launch/test_metric_steps_after_preparation.py`)
covers the same rows after they have been through Postgres.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the six identifiers (`tasks.md` 3.1, and the
REMOVED requirement's Migration paragraph); `blocking: true`, `status:
draft`, `kind: human` for each of them (`tasks.md` 3.1); `metric_id` as
the YAML key (`tasks.md` 3.2); 358 as the reference document's ID-bearing
row count and the vendored set's new size (`tasks.md` 3.4).

INVENTED: the number-word list in `_states_a_number`, used only to keep
the naming assertion from passing on `sixty-to-eighty-units` — the
delta's own counterexample, which carries no digit. Correction point:
`_NUMBER_WORDS`.

## Expected first-run state

The six rows are not in the vendored file and no step carries a
`metric_id`, so every test here is expected to fail on a wrong value —
the file exists and is readable, and what it holds is what this change
alters. Per `ai-toolkit:testing` that is the strongest failure state:
the assertions execute and discriminate.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from tests.support.playbook import SPECIFIED_GATE_ORDER

_ROOT: Final = Path(__file__).resolve().parents[3]
_VENDORED: Final = _ROOT / "alembic" / "data" / "playbook_reference.yaml"
_REFERENCE: Final = _ROOT / "docs" / "reference" / "product-launch.md"

#: SPECIFIED (`tasks.md` 3.1, and the REMOVED requirement *The seeded
#: step set carries the authored v1 definitions*' Migration paragraph):
#: the six rows this change stops excluding.
SEEDED_METRIC_STEPS: Final = (
    "lp.inventory.040",
    "lp.inventory.041",
    "lp.strategy.025",
    "lp.strategy.033",
    "lp.ppc.048",
    "lp.finance.036",
)


METRIC_BEARING_STEPS: Final[frozenset[str]] = frozenset(SEEDED_METRIC_STEPS) - {
    "lp.ppc.048"
}
"""Of the six, those whose words state a threshold on one named quantity.

`lp.ppc.048` is the exception and the only one: "Phase 1 graduated on
conversions, not time - all four must hold" conditions its gate on four
qualitative criteria, so there is no quantity for an identifier to name.
"""

#: SPECIFIED (`tasks.md` 3.4): the vendored set moves from 352 to 358 and
#: equals the reference document's ID-bearing row count.
SEEDED_COUNT: Final = 358

#: INVENTED — see the module docstring. Enough spelled-out numbers to
#: catch the delta's own counterexample, `sixty-to-eighty-units`.
_NUMBER_WORDS: Final = frozenset(
    {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "percent",
    }
)


def _reference_row_ids() -> set[str]:
    """Every ID-bearing row of the reference document, parsed here rather
    than imported — the same grammar
    `tests/unit/launch/test_playbook_reference_set.py` records, so the
    vendored file is checked against the document and not against the
    generator's reading of it."""
    lines = _REFERENCE.read_text(encoding="utf-8").split("\n")
    found: set[str] = set()
    for index, line in enumerate(lines):
        if not re.match(r"^\s+- (.*?)\s*$", line):
            continue
        meta = lines[index + 1] if index + 1 < len(lines) else ""
        if not meta.startswith("  **"):
            continue
        identifier = re.search(r"\*\*ID:\*\* (\S+)", meta)
        if identifier:
            found.add(identifier.group(1))
    return found


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    return list(yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))["steps"])


@pytest.fixture(scope="module")
def by_identifier(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {step["identifier"]: step for step in steps}


def _states_a_number(text: str) -> bool:
    if re.search(r"\d", text):
        return True
    words = set(re.findall(r"[a-z]+", text.lower()))
    return bool(words & _NUMBER_WORDS)


# ---------------------------------------------------------------------------
# Requirement (ADDED): The seeded step set carries every reference row
# ---------------------------------------------------------------------------


def test_every_area_is_fully_represented_with_no_exception(
    steps: list[dict[str, Any]],
) -> None:
    """Scenario: Every area is fully represented.

    WHEN the seeded step set is compared against the ID-bearing rows of
    every area of the reference document
    THEN every such row's ID appears as a step identifier, with no
    exception.

    The set equality is what carries the change: the previous revision of
    this scenario permitted exactly six missing identifiers, so an
    assertion of the count alone would not distinguish "six rows added"
    from "six different rows added".
    """
    seeded = {step["identifier"] for step in steps}
    expected = _reference_row_ids()

    # SPECIFIED: no exception.
    assert seeded == expected, (
        f"missing: {sorted(expected - seeded)}; extra: {sorted(seeded - expected)}"
    )
    # SPECIFIED (`tasks.md` 3.4): 358, and the same 358 as the document's.
    assert len(seeded) == SEEDED_COUNT
    assert set(SEEDED_METRIC_STEPS) <= seeded


def test_a_threshold_row_is_seeded_as_a_blocking_metric_step(
    by_identifier: dict[str, dict[str, Any]],
) -> None:
    """Scenario: A threshold row is seeded as a blocking metric step.

    WHEN a reference row conditioning a gate on a threshold is read from
    the seeded set
    THEN it appears as a step, is marked blocking, declares the gate its
    words condition, and declares a metric identifier naming the quantity
    the threshold is on.

    Which gate each row's words condition is `tasks.md` 1.3's answer and
    is not asserted here (see the module docstring); what is asserted is
    that each declares **a** gate in the framework's sequence, which a
    row seeded with no gate or a misspelled one would fail.

    `status: draft` and `kind: human` are asserted alongside because they
    are the same `tasks.md` 3.1 sentence, and because seeding these six
    `active` was considered and rejected (`design.md` — Decision 3): a
    seeded-active row would hold three live launches on a check nobody
    has yet judged ready to enforce.
    """
    for identifier in SEEDED_METRIC_STEPS:
        assert identifier in by_identifier, (
            f"{identifier} is not in the vendored set; `tasks.md` 3.1 seeds all six"
        )
        step = by_identifier[identifier]
        # SPECIFIED: marked blocking.
        assert step["blocking"] is True, identifier
        # SPECIFIED: declares the gate its words condition.
        assert step["gate"] in SPECIFIED_GATE_ORDER, identifier
        # SPECIFIED: declares a metric identifier — *where its words state
        # a threshold on one named quantity*. `lp.ppc.048` conditions its
        # gate on four qualitative criteria naming no single quantity, so
        # it blocks without one; the delta's own scenario *A
        # gate-conditioning row naming no single quantity blocks without
        # an identifier* is what says so, and `design.md` Decision 8
        # records why inventing a name for it would defeat the join the
        # field exists for. Written before that decision, this assertion
        # required all six to carry one.
        if identifier in METRIC_BEARING_STEPS:
            assert step.get("metric_id"), (
                f"{identifier} declares no metric identifier; it carries the "
                "one of the condition it restates (`tasks.md` 1.2, 3.1)"
            )
        else:
            assert not step.get("metric_id"), (
                f"{identifier} declares a metric identifier; its words name "
                "no single quantity, so it blocks without one "
                "(`design.md` — Decision 8)"
            )
        # SPECIFIED (`tasks.md` 3.1): draft and human, like every other
        # seeded row.
        assert step["status"] == "draft", identifier
        assert step["kind"] == "human", identifier


def test_a_row_merely_mentioning_a_number_is_an_ordinary_step(
    steps: list[dict[str, Any]],
) -> None:
    """Scenario: A row merely mentioning a number is an ordinary step.

    WHEN a reference row states a number without making a gate
    conditional on it
    THEN it is seeded as an ordinary step, neither blocking by virtue of
    the number nor declaring a metric identifier.

    Stated over the **resulting set**, which the delta says is what a test
    asserts: no row outside the six declares a metric identifier. The
    vacuity guard matters here — the reference document is full of rows
    stating numbers, and an assertion that found none would pass while
    proving nothing.
    """
    others = [step for step in steps if step["identifier"] not in SEEDED_METRIC_STEPS]

    numeric_others = [
        step for step in others if _states_a_number(step.get("description") or "")
    ]
    assert numeric_others, (
        "no seeded row outside the six states a number, so this check is "
        "vacuous — correct `_states_a_number` to the file as it stands"
    )

    for step in others:
        # SPECIFIED: declaring no metric identifier.
        assert not step.get("metric_id"), (
            f"{step['identifier']} declares a metric identifier and is not "
            "one of the six; the resulting set is the six and no other"
        )


def test_a_metric_identifier_names_the_quantity_alone(
    steps: list[dict[str, Any]],
) -> None:
    """Scenario: A metric identifier names the quantity alone.

    WHEN every seeded step declaring a metric identifier is read
    THEN each identifier is a lowercase hyphenated noun phrase naming the
    quantity its threshold is on, carrying no gate name and no threshold
    value.

    This is the one place the naming convention is checked, and it is
    checked **over the seed alone**: the delta states in the same
    paragraph that "it binds the seed, not the authoring surface" and
    that "no validation SHALL be derived from this paragraph". The
    authoring tests assert the converse — that a non-conforming
    identifier is accepted there.

    "Naming the quantity" itself is not machine-checkable and is not
    asserted; the three checkable clauses are the form, the absence of a
    gate name (`stock-ready-units`) and the absence of a threshold value
    (`sixty-to-eighty-units`) — the delta's own two counterexamples.
    """
    declared = [
        (step["identifier"], step["metric_id"])
        for step in steps
        if step.get("metric_id")
    ]
    assert declared, "no seeded step declares a metric identifier"

    for identifier, metric in declared:
        # SPECIFIED: a lowercase hyphenated noun phrase.
        assert re.fullmatch(r"[a-z]+(-[a-z]+)*", metric), (
            f"{identifier}'s metric identifier {metric!r} is not a lowercase "
            "hyphenated noun phrase"
        )
        segments = set(metric.split("-"))
        # SPECIFIED: carrying no gate name.
        for gate in SPECIFIED_GATE_ORDER:
            assert not set(gate.split("-")) <= segments, (
                f"{identifier}'s metric identifier {metric!r} names the "
                f"{gate!r} gate; the identifier names the quantity, not the "
                "gate it happens to hold"
            )
        # SPECIFIED: carrying no threshold value.
        assert not _states_a_number(metric), (
            f"{identifier}'s metric identifier {metric!r} states the "
            "threshold's value; the value belongs in the description"
        )
