"""Loader-boundary tests for the step description this change adds.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-playbook/spec.md`

This file holds the one half of Scenario *A step with no description is
rejected by name* that cannot be observed below the file boundary: a
playbook that **omits the description entirely**. A required dataclass
field cannot be missing, so an absent key exists only in the authored
file — `tasks.md` 2.2 places that case in the loader, and records that a
missing key today raises an uncaught `KeyError` that "aborts the whole
load unnamed". The *empty* description, the multi-line description and
the aggregated-report property are covered at the domain level in
`tests/unit/launch/domain/test_step_description.py`.

**The YAML document shape below is inherited, not invented.** It is the
one `tests/unit/launch/infrastructure/test_playbook_loader.py` already
uses — that file records the shape as DERIVED/INVENTED, and this file
adds only the `description` key `tasks.md` 2.2 names. If the implemented
key differs, the documents below are wrong in their *input* and
correcting the key is a fixture correction (failure state 3 in
`ai-toolkit:testing`); changing what these tests assert about the
resulting error would be weakening them.

At the time of writing the loader does not read a `description` key at
all, so these tests are expected to fail — the absent-key tests on the
uncaught `KeyError` `tasks.md` 2.2 describes, the read-back test on the
absent attribute. Per `ai-toolkit:testing` those failures establish only
that the target is absent.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 584 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres, which is
not available here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from commerce_ops.launch.domain.launch_playbook import InvalidPlaybookError
from commerce_ops.launch.infrastructure.driven.playbook_loader import load_playbook

# Inherited from `test_playbook_loader.py` — the eight gates in the
# specified order, with the opening modes the main spec assigns.
_GATES_YAML: Final = """\
version: v1
gates:
  - identifier: commit
    position: 1
    opening: requires-confirmation
  - identifier: order
    position: 2
    opening: requires-confirmation
  - identifier: listable
    position: 3
    opening: automatic
  - identifier: stock-ready
    position: 4
    opening: automatic
  - identifier: live
    position: 5
    opening: automatic
  - identifier: ignition
    position: 6
    opening: automatic
  - identifier: phase-one-complete
    position: 7
    opening: requires-confirmation
  - identifier: graduated
    position: 8
    opening: requires-confirmation
"""

# One step carrying no `description` key at all — the case only the file
# boundary can express — and a second step carrying a separate, ordinary
# coherence fault (a gate outside the sequence), so the assertion can
# tell the two faults apart by identifier.
_MISSING_DESCRIPTION_AND_UNKNOWN_GATE_YAML: Final = """\
steps:
  - identifier: lp.listing.019
    gate: listable
    discipline: listing
    scope: market
    timing_anchor:
      kind: offset
      days: -7
    binding: framework
    blocking: false
    execution: human-attested
  - identifier: lp.ppc.048
    description: Campaigns armed and budgets set before the launch fires
    gate: pre-launch
    discipline: ppc
    scope: market
    timing_anchor:
      kind: offset
      days: -7
    binding: framework
    blocking: false
    execution: human-attested
"""

# The same two steps, both well formed: the permitted side, and the
# document the read-back assertion observes.
_TWO_DESCRIBED_STEPS_YAML: Final = """\
steps:
  - identifier: lp.listing.019
    description: >-
      Title written to the category's own convention, leading with the
      term the shopper searches for
    gate: listable
    discipline: listing
    scope: market
    timing_anchor:
      kind: offset
      days: -7
    binding: framework
    blocking: false
    execution: human-attested
  - identifier: lp.ppc.048
    description: Campaigns armed and budgets set before the launch fires
    gate: ignition
    discipline: ppc
    scope: market
    timing_anchor:
      kind: offset
      days: -1
    binding: framework
    blocking: false
    execution: human-attested
"""


def _write_playbook(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "playbook.yaml"
    path.write_text(_GATES_YAML + body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


def test_a_step_omitting_the_description_is_rejected_by_name(tmp_path: Path) -> None:
    """Scenario: A step with no description is rejected by name (omitted).

    WHEN a playbook declares a step ... omits the description entirely
    THEN loading fails with an error naming that step, in the same
    aggregated report as any other fault.

    Both halves are asserted: the failure is the playbook's own
    rejection type (so an absent key is a *fault*, not an unhandled
    `KeyError` aborting the load — `tasks.md` 2.2), and it names the step
    the key is missing from.
    """
    source = _write_playbook(tmp_path, _MISSING_DESCRIPTION_AND_UNKNOWN_GATE_YAML)

    # SPECIFIED: loading fails with the playbook's rejection, reporting
    # the fault rather than aborting on a raw key error.
    with pytest.raises(InvalidPlaybookError) as caught:
        load_playbook(source)

    # SPECIFIED: the error names that step.
    assert "lp.listing.019" in str(caught.value)


def test_a_missing_description_is_reported_alongside_another_fault(
    tmp_path: Path,
) -> None:
    """Scenario: A step with no description is rejected by name (aggregated).

    "...in the same aggregated report as any other fault."

    This is the property `tasks.md` 2.2 says is missing today: the loader
    catches only `InvalidPlaybookError` and `ValueError` around building a
    step, so an absent key escapes as a `KeyError` and the second fault is
    never reached. A single load must surface both.
    """
    source = _write_playbook(tmp_path, _MISSING_DESCRIPTION_AND_UNKNOWN_GATE_YAML)

    # SPECIFIED: loading fails *once* — one raised error carrying both
    # faults, not one error per fault.
    with pytest.raises(InvalidPlaybookError) as caught:
        load_playbook(source)

    message = str(caught.value)
    # SPECIFIED: the failure names both — the step missing a description
    # and the step declaring a gate outside the sequence.
    assert "lp.listing.019" in message
    assert "lp.ppc.048" in message


def test_a_described_playbook_file_loads_and_reads_its_descriptions_back(
    tmp_path: Path,
) -> None:
    """Scenario: A step definition is read back ... (file boundary).

    WHEN a step definition is read from a loaded playbook
    THEN its ... description ... is present.

    Asserted through the file boundary as well as the domain, because a
    loader that never read the key would leave the domain-level tests
    passing while every authored description silently disappeared. Also
    the permitted side of the rejection tests above: a file whose steps
    each carry a description must load.
    """
    source = _write_playbook(tmp_path, _TWO_DESCRIBED_STEPS_YAML)

    playbook = load_playbook(source)

    descriptions = {step.identifier: step.description for step in playbook.steps}
    # SPECIFIED: the authored description reaches the loaded step,
    # unaltered. The first is authored as a folded YAML scalar, so this
    # also establishes that a wrapped authored value arrives as one line.
    assert descriptions == {
        "lp.listing.019": (
            "Title written to the category's own convention, leading with "
            "the term the shopper searches for"
        ),
        "lp.ppc.048": "Campaigns armed and budgets set before the launch fires",
    }


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - An empty (`description: ""`) or multi-line description through the
#   file boundary. Both are observable at playbook construction and are
#   covered there; the loader adds nothing to either, whereas the absent
#   key exists only in the file.
# - Whether an absent key is reported with the same wording as an empty
#   one. The delta requires the step to be named, not a particular
#   message.
# - Every other required key the `KeyError` fix in `tasks.md` 2.2 also
#   protects. That protection is a welcome consequence of the fix, not a
#   behaviour this delta states.
