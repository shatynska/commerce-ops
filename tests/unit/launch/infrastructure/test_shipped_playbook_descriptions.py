"""The descriptions carried by the shipped `v1` playbook's authored steps.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-playbook/spec.md`

Covers the two scenarios the `MODIFIED` requirement *The shipped playbook
carries the authored step set* gains:

- *A step states its work without the source document* — every authored
  step's description is non-empty.
- *Every description re-derives from its reference row* — each equals the
  text of the reference row its identifier names, reduced by the trimming
  rule the requirement states.

The subject under test is *data*: the shipped `playbook_v1.yaml`. Nothing
here asserts anything about the loader or the step schema — those are
covered by `test_playbook_loader_description.py` and
`tests/unit/launch/domain/test_step_description.py`. The loader is used
only as the means of observing the file.

**The reference document is parsed, not transcribed**, the same choice
`test_shipped_playbook_steps.py` records and for the same reason: the
delta states the obligation *against that document* ("compared against
the text of the reference row its identifier names"), so transcribing 97
sentences into this file would make the test assert a copy rather than
the source. The row grammar — a metadata line carrying `**ID:** …`,
whose row text is the list item on the line above it — is DERIVED from
the document's own shape and is the grammar `test_shipped_playbook_steps
.py` already relies on for `SOURCE`/`ID`. A document reformatting would
be a fixture defect in this parser (failure state 3 in
`ai-toolkit:testing`), never grounds to weaken an assertion.

**The trimming rule is SPECIFIED**, not derived: the delta fixes it
("trailing whitespace SHALL be removed, and then any trailing character
in the closed set `;` `:` `,` `.` — repeating"), and `design.md`
Decision 3 fixes the closed set and states why a broader rule would
corrupt the rows ending in a closing quote, a closing parenthesis, or
`+`. `tasks.md` 5.1 requires this comparison to be made against the
*trimmed* text and names the trap: "not a raw-text comparison — roughly
17 rows are trimmed, and a raw comparison would fail on them and invite
weakening the assertion".

At the time of writing the shipped file carries no `description` key, so
these tests are expected to fail on an absent attribute rather than on a
wrong value. Per `ai-toolkit:testing` that failure establishes only
absence.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 584 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres, which is
not available here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from commerce_ops.launch.domain.launch_playbook import StepDefinition
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)

# DERIVED: the reference document's row grammar. An ID-bearing row is a
# metadata line ending in `**ID:** lp.<discipline>.<nnn>`; the row's own
# text is the markdown list item on the preceding line.
_ROW_ID: Final = re.compile(r"\*\*ID:\*\*\s*(\S+?)\s*$")
_BULLET: Final = re.compile(r"^\s*-\s+(.*?)\s*$")

# SPECIFIED (delta): "any trailing character in the closed set `;` `:`
# `,` `.`". Closed deliberately — see the module docstring.
_TERMINAL_MARKS: Final = ";:,."

# SPECIFIED (delta, by exclusion): "reference rows end variously in a
# closing quote, a closing parenthesis, or a `+` (as in 'A+'), and each
# of those is part of what the row says". These are the characters a
# broader trimming rule would silently eat.
_CONTENT_TERMINALS: Final = "\"')+"


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _trimmed(text: str) -> str:
    """The delta's trimming rule, applied exactly as stated.

    Trailing whitespace, then any trailing `;` `:` `,` `.`, repeating
    until neither whitespace nor one of those four characters remains at
    the end. Nothing else is stripped.
    """
    reduced = text.rstrip()
    while reduced and reduced[-1] in _TERMINAL_MARKS:
        reduced = reduced[:-1].rstrip()
    return reduced


def _reference_row_text() -> dict[str, str]:
    """Every ID-bearing reference row as `id -> raw row text`."""
    source_file = _repository_root() / "docs" / "reference" / "product-launch.md"
    lines = source_file.read_text(encoding="utf-8").splitlines()
    rows: dict[str, str] = {}
    for index, line in enumerate(lines):
        identifier = _ROW_ID.search(line)
        if identifier is None:
            continue
        if index == 0:
            pytest.fail(
                f"reference row {identifier.group(1)} has no text line above it"
            )
        bullet = _BULLET.match(lines[index - 1])
        if bullet is None:
            pytest.fail(
                f"reference row {identifier.group(1)} is not preceded by a row "
                f"text line: {lines[index - 1]!r}"
            )
        rows[identifier.group(1)] = bullet.group(1)
    if not rows:
        pytest.fail("no ID-bearing rows parsed from the reference document")
    return rows


REFERENCE_ROW_TEXT: Final = _reference_row_text()


def _shipped_steps() -> tuple[StepDefinition, ...]:
    """The shipped playbook's steps, guarded against a vacuous pass.

    Every assertion below quantifies over the step set; an empty set
    would satisfy all of them for the wrong reason, which
    `ai-toolkit:testing` classes as an alarm rather than a result.
    """
    steps = tuple(load_shipped_playbook().steps)
    assert steps, "the shipped playbook carries no steps"
    return steps


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): The shipped playbook carries the authored step set
# ---------------------------------------------------------------------------


def test_every_shipped_step_states_its_work() -> None:
    """Scenario: A step states its work without the source document.

    WHEN any authored step is read from the loaded playbook
    THEN its description is non-empty.

    Stated over *any* step, so this quantifies over the whole set rather
    than sampling one. Collected as a list so a failure names every step
    left undescribed rather than only the first.
    """
    undescribed = [step.identifier for step in _shipped_steps() if not step.description]

    # SPECIFIED: the description is required and is not empty.
    assert undescribed == []


def test_every_shipped_description_occupies_a_single_line() -> None:
    """Requirement statement: a description occupies "a single line".

    The loader rejects a multi-line description (covered in
    `tests/unit/launch/domain/test_step_description.py`), so a shipped
    file that loads already satisfies this. Asserted directly anyway,
    because the requirement states it as a property of the description
    itself and because a task name is a single line — the reason the rule
    exists.
    """
    multi_line = [
        step.identifier
        for step in _shipped_steps()
        if "\n" in step.description or "\r" in step.description
    ]

    assert multi_line == []


def test_every_description_re_derives_from_its_reference_row() -> None:
    """Scenario: Every description re-derives from its reference row.

    WHEN every authored step's description is compared against the text
    of the reference row its identifier names, reduced by the trimming
    rule
    THEN each description equals that row's trimmed text exactly.

    Equality, not containment: the delta says the row's text is
    "transcribed unaltered", with "nothing else changed — not the
    wording, the casing, or the order of clauses". A containment
    assertion would pass for a description that had been "improved",
    which is precisely the divergence this scenario exists to detect.
    """
    mismatched: list[tuple[str, str, str]] = []
    for step in _shipped_steps():
        raw = REFERENCE_ROW_TEXT.get(step.identifier)
        if raw is None:
            # A step whose identifier is not a reference row ID is
            # reported by `test_shipped_playbook_steps.py`; not restated
            # here, so that this test fails only on a description.
            continue
        expected = _trimmed(raw)
        if step.description != expected:
            mismatched.append((step.identifier, step.description, expected))

    # SPECIFIED: each description equals that row's trimmed text exactly.
    assert mismatched == []


def test_the_trimming_rule_is_actually_exercised_by_the_shipped_set() -> None:
    """Guard on the test above, not a scenario of its own.

    `design.md` Decision 3 measures the shipped rows: 14 end in `.` and 3
    in `:`. If no shipped row carried a terminal mark, the equality test
    above would hold for a transcription that ignored the trimming rule
    entirely, and the rule would be unverified while appearing covered.

    DERIVED from that measurement: this asserts only that *some* shipped
    row is trimmed, not the count, because which rows ship is a curation
    decision the delta leaves open.
    """
    shipped_ids = {step.identifier for step in _shipped_steps()}

    trimmed_rows = [
        identifier
        for identifier, raw in REFERENCE_ROW_TEXT.items()
        if identifier in shipped_ids and _trimmed(raw) != raw.rstrip()
    ]

    assert trimmed_rows != [], (
        "no shipped reference row ends in a terminal mark, so the trimming "
        "rule is not exercised by the equality assertion above"
    )


def test_content_terminal_characters_survive_transcription() -> None:
    """Scenario: Every description re-derives ... (the closed-set half).

    The delta states the stripped set is closed and "not 'trailing
    punctuation'": a row ending in a closing quote, a closing parenthesis
    or a `+` ends that way as content. `design.md` Decision 3 names the
    concrete casualty of a broader rule — `lp.creative.019` rendered as
    "…answered inside A".

    Asserted separately from the equality test because a broader trimming
    rule applied by *both* the authoring and this test's `_trimmed` would
    leave that test passing while the shipped text was corrupted.
    """
    steps = {step.identifier: step for step in _shipped_steps()}

    corrupted: list[tuple[str, str]] = []
    exercised: list[str] = []
    for identifier, raw in REFERENCE_ROW_TEXT.items():
        step = steps.get(identifier)
        if step is None:
            continue
        stripped = raw.rstrip()
        if not stripped or stripped[-1] not in _CONTENT_TERMINALS:
            continue
        exercised.append(identifier)
        if not step.description.endswith(stripped[-1]):
            corrupted.append((identifier, step.description))

    # Guard: with no such row shipped, the assertion below would hold
    # vacuously. `design.md` Decision 3 counts 5 closing quotes, 3
    # closing parentheses and 2 `+` across the shipped rows.
    assert exercised != [], (
        "no shipped reference row ends in a content character, so this "
        "assertion establishes nothing"
    )
    # SPECIFIED: no other character is stripped.
    assert corrupted == []


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The number of shipped descriptions (97), and which rows they belong
#   to. The delta states properties of the transcription, not a census;
#   `test_shipped_playbook_steps.py` already records why the step census
#   is left unasserted.
# - The wording of any individual description. Asserting one would
#   duplicate the reference document into this file — the thing the
#   parsed comparison above exists to avoid.
# - `lp.rank.003`, which `design.md` Decision 3 records as reading badly
#   under any rule because it is truncated in the source. The delta's
#   route for that is editing the reference document, so the equality
#   assertion above covers it like any other row and nothing special is
#   asserted here.
# - Any length bound on a shipped description. The length concern lives
#   on the composed task name, in the `launch-clickup-sync` delta, and is
#   covered in
#   `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py`.
