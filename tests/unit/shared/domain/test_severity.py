"""Tests for the shared `Severity` vocabulary (`shared-vocabulary`).

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/shared-vocabulary/spec.md

Covers the ADDED requirement *Severity vocabulary names the reporting
tiers* -- both of its scenarios.

At the time of writing no `Severity` exists in `shared/domain` (the change
introduces it -- `tasks.md` 1.1), so every test here is expected to fail on
an absent target (`ModuleNotFoundError`). Per `ai-toolkit:testing`, that
failure establishes only absence -- the assertions never executed.

DERIVED / unresolved project questions (see `test-manifest.md` at the
change root):

- `commerce_ops.shared.domain.severity` as the module path. `tasks.md` 1.1
  fixes the file (`shared/domain/severity.py`) and the member spellings
  (`MONITOR`, `DIAGNOSE`, `CRITICAL`); nothing fixes the import path
  beyond the file layout this project already follows for
  `discipline.py` and `lifecycle_stage.py`.
- `Severity` as a Python `Enum` constructed by value
  (`Severity("critical")`), with rejection signalled by `ValueError` --
  the reading `test_discipline.py` already records for "the vocabulary's
  existing construction rules", which the requirement statement points at
  by name.
- The wire values `monitor` / `diagnose` / `critical` -- the spec names
  the tiers in lower case prose and `tasks.md` 1.1 names the membership in
  upper case; `Discipline`'s precedent is a lower-case value per member.

Correcting the import path or the construction call is a fixture
correction. What must survive unweakened: exactly these three tiers are
constructible, nothing outside them is, and the vocabulary is closed at
three (a fourth "noise" tier existing today would put the vocabulary
outside the specification, which says outright that below-threshold noise
is not a severity).
"""

from __future__ import annotations

from typing import Final

import pytest

from commerce_ops.shared.domain.severity import Severity

# SPECIFIED: "monitor, diagnose, and critical -- the tiers findings are
# graded into for reporting" (Requirement: Severity vocabulary names the
# reporting tiers).
SPECIFIED_SEVERITIES: Final = ("monitor", "diagnose", "critical")


def test_a_known_severity_is_constructed() -> None:
    """Scenario: A known severity is constructed.

    WHEN a severity is constructed from the value "critical"
    THEN the severity is created and reports its value.
    """
    severity = Severity("critical")

    # SPECIFIED: it is created and reports its value.
    assert severity.value == "critical"


@pytest.mark.parametrize("value", SPECIFIED_SEVERITIES)
def test_each_specified_tier_is_constructible(value: str) -> None:
    """Requirement statement: the vocabulary names monitor, diagnose and
    critical.

    The named scenario uses `critical` alone; an implementation carrying
    only two of the three tiers would still pass it.
    """
    # SPECIFIED: each named tier is a member of the vocabulary.
    assert Severity(value).value == value


def test_the_severity_set_is_exactly_the_three_reporting_tiers() -> None:
    """Requirement statement: "Below-threshold noise is not a severity:
    something not worth reporting produces no item at all."

    SPECIFIED: the vocabulary is closed at the three reporting tiers. A
    fourth member -- a "noise" tier in particular -- contradicts the
    requirement's own reason clause, which is why this is asserted as an
    exact set rather than as a subset.
    """
    assert {member.value for member in Severity} == set(SPECIFIED_SEVERITIES)


def test_an_unknown_severity_is_rejected() -> None:
    """Scenario: An unknown severity is rejected.

    WHEN a severity is constructed from a value outside monitor,
    diagnose, critical
    THEN construction SHALL be rejected.

    DERIVED: `ValueError` as the failure signal (see module docstring).
    `noise` is used deliberately: it is the one value the requirement
    statement singles out as *not* being a severity, so an implementation
    that added it as a fourth member fails here as well as above.
    """
    with pytest.raises(ValueError):
        Severity("noise")


def test_severity_values_compare_by_value_and_are_immutable() -> None:
    """Requirement statement: "Severity values SHALL follow the
    vocabulary's existing construction rules".

    DERIVED (from `shared-vocabulary`'s standing requirement *Value
    objects are immutable and compare by value*, which the delta's
    "existing construction rules" clause points at): two constructions of
    the same tier are the same value, and a tier cannot be mutated into
    another.
    """
    assert Severity("monitor") == Severity("monitor")
    assert Severity("monitor") != Severity("critical")

    with pytest.raises(AttributeError):
        Severity("monitor").value = "critical"  # type: ignore[misc]
