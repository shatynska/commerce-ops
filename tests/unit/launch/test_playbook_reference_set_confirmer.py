"""The seeded reference step set names no confirmer.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`

Covers the MODIFIED requirement *The authored set exercises the full step
vocabulary*:

- "It follows that the seeded set SHALL NOT be required to exercise
  `kind`, `status` or name a `confirmer`."
- Scenario: *Execution modes and the compliance hazard are represented*
  (restated) — "grouped by kind and confirmer and filtered by hazard ...
  every step is `human` and none names a confirmer, so no coverage of
  `automated` is required of the seed."

The "every step is `human`" half of that scenario, and the sibling
scenarios *Anchor kinds are all present*, *Every discipline appears*,
*Prohibited tactics are present and never block*, *Every seeded step is a
draft nobody owns*, *A seeded playbook is not ready*, *A registered
runtime does not activate a seeded step* and *Outstanding rule-policy
decisions stay visible* are all unaffected by this delta's wording change
and are covered by the existing
`tests/unit/launch/test_playbook_reference_set.py` (and its integration
sibling `tests/integration/launch/test_seeded_step_fields.py`) —
recorded as such in `test-manifest.md` rather than duplicated here.

`test_playbook_reference_set.py::test_every_step_is_an_unowned_human_draft`
asserts `step["needs_confirmation"] is False` directly against the field
this change removes; it is recorded in `test-manifest.md`'s obsolete list
rather than edited here.

**Level.** Reads the same committed vendored file
(`alembic/data/playbook_reference.yaml`)
`test_playbook_reference_set.py` reads, for the reason that file's own
docstring gives: checking the *data*, not the generator's reading of it.

## Expected first-run state

The committed file still carries `"needs_confirmation": false` on every
step and no `confirmer` key at all yet (`tasks.md` 6.1 has not run), so
`test_no_seeded_step_names_a_confirmer` currently passes vacuously (no
step has ever had `confirmer` truthy) and is retested here as the
positive statement of what the delta requires going forward, not as
evidence of anything already built.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest
import yaml

_ROOT: Final = Path(__file__).resolve().parents[3]
_VENDORED: Final = _ROOT / "alembic" / "data" / "playbook_reference.yaml"


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    return list(yaml.safe_load(_VENDORED.read_text(encoding="utf-8"))["steps"])


def test_no_seeded_step_names_a_confirmer(steps: list[dict[str, Any]]) -> None:
    """Scenario: Execution modes and the compliance hazard are represented
    (the confirmer half).

    WHEN the seeded step set is grouped by kind and confirmer and filtered
    by hazard
    THEN every step is `human` and none names a confirmer, so no coverage
    of `automated` is required of the seed.

    SPECIFIED: "the seeded set SHALL NOT be required to exercise `kind`,
    `status` or name a `confirmer`" — and task 6.1 fixes what that means
    for the generated data: the `needs_confirmation` literal is removed
    and nothing is added in its place, so a seeded step carries no
    `confirmer` key at all rather than an explicit `null`.
    """
    for step in steps:
        assert step.get("confirmer") is None, (
            f"{step['identifier']} names a confirmer: {step.get('confirmer')!r} "
            "— the seed is entirely human drafts, and none is required to "
            "name a confirmer"
        )
