"""Tests for the shared `Discipline` vocabulary (`shared-vocabulary`).

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/shared-vocabulary/spec.md

Covers the ADDED requirement *Discipline vocabulary names the owning
disciplines*.

At the time of writing no `Discipline` exists in `shared/domain` (the
change introduces it — `tasks.md` 2.1), so every test here is expected to
fail on an absent target (`ModuleNotFoundError`). Per `ai-toolkit:testing`,
that failure establishes only absence — the assertions never executed.

DERIVED / unresolved project questions (see the manifest at the change
root):

- `commerce_ops.shared.domain.discipline` as the module path, mirroring the
  one-module-per-concept convention `identity.py` and `lifecycle_stage.py`
  already follow. No artifact fixes the module name.
- `Discipline` as a Python `Enum` constructed by value
  (`Discipline("inventory")`), with rejection signalled by `ValueError` —
  the standard-library behaviour for by-value enum lookup, and the natural
  reading of "constructing a discipline from a value outside this set
  SHALL fail". The spec fixes the twelve wire values, not the Python
  member names, so nothing here touches a member name.
"""

from __future__ import annotations

from typing import Final

import pytest

from commerce_ops.shared.domain.discipline import Discipline

# SPECIFIED: "one of a closed set of twelve" (Requirement: Discipline
# vocabulary names the owning disciplines).
SPECIFIED_DISCIPLINES: Final = (
    "strategy",
    "finance",
    "setup",
    "inventory",
    "creative",
    "listing",
    "rank",
    "price",
    "ppc",
    "customer",
    "external",
    "traffic",
)


def test_a_known_discipline_is_constructed() -> None:
    """Scenario: A known discipline is constructed.

    WHEN a discipline is constructed from the value `inventory`
    THEN it is created and reports `inventory` as its value.
    """
    discipline = Discipline("inventory")

    # SPECIFIED: it reports `inventory` as its value.
    assert discipline.value == "inventory"


@pytest.mark.parametrize("value", SPECIFIED_DISCIPLINES)
def test_each_specified_discipline_is_constructible(value: str) -> None:
    """Scenario: A known discipline is constructed (all twelve).

    The named scenario uses `inventory`; the requirement statement closes
    the set at exactly these twelve, so each must be constructible — an
    implementation carrying eleven of them would still pass the named
    scenario alone.
    """
    # SPECIFIED: each of the twelve is a member of the vocabulary.
    assert Discipline(value).value == value


def test_the_discipline_set_is_exactly_twelve() -> None:
    """Requirement statement: "a closed set of twelve".

    SPECIFIED: the set is closed at twelve — a thirteenth member present
    today would put the vocabulary outside the specification (the
    deliberate extension point is a future change adding a member, not a
    member existing now).
    """
    assert len(set(Discipline)) == 12
    assert {member.value for member in Discipline} == set(SPECIFIED_DISCIPLINES)


def test_an_unknown_discipline_is_rejected() -> None:
    """Scenario: An unknown discipline is rejected.

    WHEN a discipline is constructed from a value outside the defined set
    THEN construction fails.

    DERIVED: `ValueError` as the failure signal (see module docstring).
    `warehouse` is used because it is a plausible-looking discipline that
    the set deliberately does not contain.
    """
    with pytest.raises(ValueError):
        Discipline("warehouse")
