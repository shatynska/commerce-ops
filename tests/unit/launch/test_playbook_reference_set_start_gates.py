"""The vendored step set states when each of its steps starts
(`launch-playbook`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-playbook/spec.md`
— the ADDED requirement *The stored step set declares when its steps
start*, and the two scenarios of it that concern the **delivery path**
rather than the backfill:

- *A vendored step delivered later carries a start gate*
- *A vendored step missing a start gate is a fault*

`tasks.md` 9.5 asks for this file by name: "Add a unit-tier test over the
vendored file asserting every step states a start gate, so a generator or
hand-edit slip fails at commit time rather than as an unhealthy container
after merge."

The stored set's own scenarios need a database and live in
`tests/integration/launch/test_step_start_gate_backfill.py`. The manifest
at `openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
accounts for every scenario in the change.

## Level

The committed file, read as data, plus `vendored_definitions()` — the
same level `test_playbook_reference_set.py` and `test_seed_playbook.py`
sit at, and the smallest that can observe what the delivery path carries.

## What is SPECIFIED, and what is DERIVED

SPECIFIED by the requirement and enumerated by `tasks.md` 9.1:

- every vendored step states a start gate;
- the rule is the step's own gate, `ignition` for a final-gate step, and
  the earlier gate the anchor implies for the seven identifiers `tasks.md`
  8.2-8.4 name;
- delivery rejects a vendored step that does not carry one "rather than
  substituting a default".

DERIVED: the YAML key is `starts_at_gate`, matching the field name the
delta fixes and the spelling every other key in the file uses; and the
seven exception identifiers are read from `tasks.md` rather than
recomputed from the anchors, since the artifacts state them by
identifier.

## INVENTED, with correction points

How the missing-field fault is provoked: `_vendored_path()` finds the
module attribute naming the vendored file and points it at a temporary
copy with one step's `starts_at_gate` removed. It fails loudly rather
than skipping, so a delivery path that reads the file some other way is
reported instead of silently passing.

## Expected first-run state

The vendored file carries no `starts_at_gate`, so every test here is
expected to fail on a **wrong value** rather than at import — the file,
the loader and the module all exist.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from commerce_ops import seed_playbook
from commerce_ops.launch.domain.launch_playbook import (
    InvalidPlaybookError,
    LaunchPlaybook,
    framework_gates,
)
from commerce_ops.seed_playbook import vendored_definitions
from tests.support.playbook import SPECIFIED_GATE_ORDER

_ROOT: Final = Path(__file__).resolve().parents[3]
_VENDORED: Final = _ROOT / "alembic" / "data" / "playbook_reference.yaml"

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

#: SPECIFIED by `tasks.md` 8.5: a final-gate step defaults two gates back.
FINAL_GATE_DEFAULT: Final = "ignition"

#: SPECIFIED by `tasks.md` 8.2-8.4 and repeated by 9.1: the seven
#: reviewed steps whose calendar anchor falls before their own gate can
#: be reached, each with the earlier gate its anchor implies.
ANCHOR_EXCEPTIONS: Final[dict[str, str]] = {
    # `stock-ready` steps anchored T-30, which that gate cannot reach.
    "lp.inventory.019": "order",
    "lp.inventory.008": "order",
    "lp.inventory.018": "order",
    # `live` steps anchored T-14: campaign preparation precedes going live.
    "lp.ppc.001": "listable",
    "lp.ppc.002": "listable",
    "lp.ppc.004": "listable",
    # The same cluster at T-60, given `order` for the margin rather than
    # the discipline (`tasks.md` 8.4).
    "lp.ppc.003": "order",
}

_START_GATE_KEY: Final = "starts_at_gate"

#: The delta fixes that delivery *fails*, not which error it raises.
_REJECTED: Final = (InvalidPlaybookError, ValueError, KeyError, TypeError)


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    return list(yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))["steps"])


def _expected_start_gate(step: dict[str, Any]) -> str:
    identifier = str(step["identifier"])
    if identifier in ANCHOR_EXCEPTIONS:
        return ANCHOR_EXCEPTIONS[identifier]
    if step["gate"] == FINAL_GATE:
        return FINAL_GATE_DEFAULT
    return str(step["gate"])


# ---------------------------------------------------------------------------
# ADDED Requirement: The stored step set declares when its steps start
# (the delivery path)
# ---------------------------------------------------------------------------


def test_every_vendored_step_states_a_start_gate(steps: list[dict[str, Any]]) -> None:
    """Scenario: A vendored step delivered later carries a start gate.

    WHEN the vendored set is delivered and inserts a step the stored set
    did not name
    THEN that step carries a start gate, without a further backfill being
    run.

    Asserted over the file rather than over one insertion, because the
    scenario's "without a further backfill being run" is a property of
    what the file states: a step delivered afterwards can only carry what
    the file gives it.

    `tasks.md` 9.5 asks for exactly this, "so a generator or hand-edit
    slip fails at commit time rather than as an unhealthy container after
    merge".
    """
    missing = [
        step["identifier"]
        for step in steps
        if not str(step.get(_START_GATE_KEY) or "").strip()
    ]

    assert not missing, (
        f"{len(missing)} vendored steps state no {_START_GATE_KEY!r} "
        f"(first few: {missing[:5]}); every step the delivery path inserts "
        "must carry one"
    )


def test_every_vendored_start_gate_follows_the_stated_rule(
    steps: list[dict[str, Any]],
) -> None:
    """Requirement statement: each step "SHALL declare its own gate as its
    start gate, subject to two exceptions" — a final-gate step declaring
    at least two gates before it, and a reviewed anchor-conflicting step
    declaring the earlier gate its anchor implies.

    `tasks.md` 9.1 states the rule for the vendored file in those terms,
    and 8.6 states that the exceptions apply "to the seven identifiers
    named in 8.2, 8.3 and 8.4 and to no others".
    """
    wrong = {
        str(step["identifier"]): (step.get(_START_GATE_KEY), _expected_start_gate(step))
        for step in steps
        if step.get(_START_GATE_KEY) != _expected_start_gate(step)
    }

    assert not wrong, (
        "these vendored steps do not follow the stated rule (identifier: "
        f"declared, expected): {dict(list(wrong.items())[:8])}"
    )


def test_the_seven_anchor_exceptions_are_present_and_alone(
    steps: list[dict[str, Any]],
) -> None:
    """`tasks.md` 8.6: the anchor exceptions apply "to the seven
    identifiers named in 8.2, 8.3 and 8.4 and to no others. Do **not**
    derive further exceptions for the remaining drafts."

    Stated separately from the rule above because the rule alone is
    satisfied by a file carrying none of the seven — the exceptions are
    the part a regenerated file most easily loses, and the drafts are the
    part it most easily over-applies.
    """
    declared = {
        str(step["identifier"]): step.get(_START_GATE_KEY)
        for step in steps
        if str(step["identifier"]) in ANCHOR_EXCEPTIONS
    }

    # SPECIFIED: all seven are in the file, and each carries its stated
    # gate.
    assert set(declared) == set(ANCHOR_EXCEPTIONS), (
        "the vendored file does not carry all seven reviewed steps: missing "
        f"{sorted(set(ANCHOR_EXCEPTIONS) - set(declared))}"
    )
    assert declared == ANCHOR_EXCEPTIONS

    # SPECIFIED: and to no others — every other step takes the mechanical
    # default, which `test_every_vendored_start_gate_follows_the_stated_rule`
    # states positively and this restates as the count.
    departures = [
        str(step["identifier"])
        for step in steps
        if str(step["identifier"]) not in ANCHOR_EXCEPTIONS
        and step["gate"] != FINAL_GATE
        and step.get(_START_GATE_KEY) != step["gate"]
    ]
    assert not departures, (
        f"these steps depart from the mechanical default without being one "
        f"of the seven reviewed exceptions: {departures[:8]}"
    )


def test_no_vendored_start_gate_names_the_final_gate(
    steps: list[dict[str, Any]],
) -> None:
    """Requirement statement: "A `starts_at_gate` naming the final gate
    SHALL be rejected, for every step including those belonging to that
    gate."

    A file the loader refuses is a file that serves nothing, so this is
    the failure mode `tasks.md` 8.5 records ("the plain default would
    produce a set the loader rejects").

    **Expected to PASS on its first run, vacuously**: no vendored step
    declares a start gate at all today, so nothing can name the final
    one. It is recorded as such in the manifest rather than counted as
    coverage. `test_every_vendored_step_states_a_start_gate` above is
    what stops it staying vacuous — a file satisfying that one and this
    one together is the file the requirement asks for.
    """
    offending = [
        str(step["identifier"])
        for step in steps
        if step.get(_START_GATE_KEY) == FINAL_GATE
    ]

    assert not offending, (
        f"these vendored steps start at the final gate: {offending[:8]}"
    )


def test_the_vendored_set_still_constructs_a_playbook() -> None:
    """The load rules and the file must agree.

    Every load-time rule this change adds — an unknown start gate, one
    later than the step's own gate, one naming the final gate, a cycle, a
    transitive deadlock — is evaluated on construction, so this is where
    a vendored value that violates any of them surfaces.

    It restates `test_playbook_reference_set.py`'s own first assertion
    deliberately: that test constructs the same playbook, but nothing
    there would tell a reader *why* it went red once the start rules
    landed.

    **Expected to PASS on its first run**, and recorded as such in the
    manifest: the vendored set constructs today. It is a regression guard
    against the new load rules and the new vendored values disagreeing,
    not evidence that either landed.
    """
    playbook = LaunchPlaybook(
        version="reference-v1",
        gates=framework_gates(),
        steps=vendored_definitions(),
    )

    assert playbook.authored_steps


def test_every_vendored_definition_carries_its_start_gate_through_the_loader() -> None:
    """`tasks.md` 9.2: `seed_playbook.vendored_definitions` must *read*
    `starts_at_gate` rather than "letting the dataclass default apply".

    Asserted on the loaded definitions rather than on the file, because a
    loader that ignored the key would leave every definition at `None`
    while the file itself passed every test above.
    """
    unset = [
        definition.identifier
        for definition in vendored_definitions()
        if definition.starts_at_gate is None
    ]

    assert not unset, (
        f"{len(unset)} vendored definitions arrive with no start gate "
        f"(first few: {unset[:5]}); the loader is not reading "
        f"{_START_GATE_KEY!r} and the dataclass default is applying instead"
    )


# ---------------------------------------------------------------------------
# The missing-field fault
# ---------------------------------------------------------------------------

_PATH_ATTRIBUTES: Final = (
    "VENDORED",
    "VENDORED_PATH",
    "REFERENCE",
    "REFERENCE_PATH",
    "DATA",
    "DATA_PATH",
    "PLAYBOOK_PATH",
    "SOURCE",
    "_VENDORED",
)


def _vendored_path_attribute() -> str:
    """The module attribute naming the vendored file.

    Probed rather than assumed, and failing loudly rather than skipping:
    a delivery path that reads the file some other way is a finding, not
    a reason to pass.
    """
    for name in _PATH_ATTRIBUTES:
        value = getattr(seed_playbook, name, None)
        if isinstance(value, Path) and value.suffix in (".yaml", ".yml"):
            return name
    for name in dir(seed_playbook):
        value = getattr(seed_playbook, name)
        if isinstance(value, Path) and value.suffix in (".yaml", ".yml"):
            return name
    pytest.fail(
        "`commerce_ops.seed_playbook` exposes no path to the vendored file "
        f"under any of {_PATH_ATTRIBUTES} or any other `Path` attribute, so "
        "the missing-field fault cannot be provoked — correct this probe to "
        "how the delivery path reads the file"
    )


def test_a_vendored_step_missing_a_start_gate_is_a_fault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scenario: A vendored step missing a start gate is a fault.

    WHEN the vendored set carries a step that states no start gate
    THEN delivery fails, reporting the step and the missing field, and
    inserts nothing.

    SPECIFIED: "delivery SHALL reject a vendored step that does not carry
    one rather than substituting a default, a shape fault in a file this
    repository ships being reported as one." `tasks.md` 9.2 states the
    same.
    """
    document = yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))
    stripped = str(document["steps"][0]["identifier"])
    document["steps"][0].pop(_START_GATE_KEY, None)
    doctored = tmp_path / "playbook_reference.yaml"
    doctored.write_text(yaml.safe_dump(document), encoding="utf-8")

    monkeypatch.setattr(seed_playbook, _vendored_path_attribute(), doctored)

    with pytest.raises(_REJECTED) as caught:
        vendored_definitions()

    reported = str(caught.value)
    # SPECIFIED: reporting the step and the missing field.
    assert stripped in reported, (
        f"the fault does not name the offending step: {reported!r}"
    )
    assert _START_GATE_KEY in reported or "start" in reported.lower(), (
        f"the fault does not name the missing field: {reported!r}"
    )
