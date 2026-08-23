"""Tests for the shared `MetricId` identity value object (`shared-vocabulary`).

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/shared-vocabulary/spec.md

Covers the `MetricId` legs of the MODIFIED requirement *Identity value
objects validate at construction*: the empty-value and padded-value
rejection scenarios (extended by the delta to name a metric identifier)
and the new scenario *A metric identifier does not require a defined
metric*. The four pre-existing identity VOs' legs of those scenarios are
unchanged by the delta and remain covered by
`tests/unit/shared/domain/test_identity_value_objects.py`, which this pass
does not touch (additive only).

At the time of writing `MetricId` does not exist (`tasks.md` 2.2), so
every test here is expected to fail on an absent target (`ImportError`).
Per `ai-toolkit:testing`, that failure establishes only absence.

DERIVED / unresolved project questions (see the manifest at the change
root):

- `commerce_ops.shared.domain.identity` as the module — `tasks.md` 2.2
  places `MetricId` "next to the existing identity VOs", which live there.
- Construction from a single positional string exposed as `.value`, and
  rejection via `ValueError` — the shape every existing identity VO's
  tests already assume.
"""

from __future__ import annotations

import pytest

from commerce_ops.shared.domain.identity import MetricId

# ---------------------------------------------------------------------------
# Requirement (MODIFIED): Identity value objects validate at construction
# ---------------------------------------------------------------------------


def test_an_empty_metric_identifier_is_rejected() -> None:
    """Scenario: An empty identity value is rejected (metric-identifier leg).

    WHEN a metric identifier is constructed from an empty value
    THEN construction fails with an error naming the offending value.

    As with the existing empty-value tests, only the rejection itself is
    asserted: an empty string has no content for a message to name
    (recorded in the manifest as the same deliberately narrower reading
    the previous pass took for this case).
    """
    with pytest.raises(ValueError):
        MetricId("")


@pytest.mark.parametrize(
    "padded",
    [
        pytest.param(" units-fulfillable", id="leading"),
        pytest.param("units-fulfillable ", id="trailing"),
    ],
)
def test_a_padded_metric_identifier_is_rejected_not_trimmed(padded: str) -> None:
    """Scenario: A padded identity value is rejected (metric-identifier leg).

    WHEN a metric identifier is constructed from a string with leading or
    trailing whitespace
    THEN construction fails rather than silently trimming.
    """
    # SPECIFIED: construction fails (a silent trim would not raise).
    with pytest.raises(ValueError):
        MetricId(padded)


def test_a_metric_identifier_does_not_require_a_defined_metric() -> None:
    """Scenario: A metric identifier does not require a defined metric.

    WHEN a metric identifier is constructed from a non-empty, unpadded
    value naming no known metric
    THEN it is created, because resolution against a metric registry is
    not this vocabulary's concern.

    No metric registry exists at all yet (slice 7), so *every* value names
    no known metric; the value used here is simply a plausible one.
    """
    metric_id = MetricId("no-registry-defines-this")

    # SPECIFIED: it is created and carries the value unchanged.
    assert metric_id.value == "no-registry-defines-this"


# ---------------------------------------------------------------------------
# Requirement (main spec, unchanged by this delta): Value objects are
# immutable and compare by value — "every vocabulary value object", which
# `MetricId` now is. Not a delta scenario; asserted because the main-spec
# requirement statement covers the new VO from the moment it exists.
# ---------------------------------------------------------------------------


def test_two_metric_identifiers_with_the_same_value_are_equal() -> None:
    """SPECIFIED (main spec: *Value objects are immutable and compare by
    value*): equal exactly when their values are equal, usable as set
    members.
    """
    a = MetricId("units-fulfillable")
    b = MetricId("units-fulfillable")

    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
    # DERIVED from the requirement statement's "exactly when": the unequal
    # half, without which a constant-True `__eq__` would pass.
    assert MetricId("units-fulfillable") != MetricId("organic-share")


def test_mutation_of_a_metric_identifier_fails() -> None:
    """SPECIFIED (main spec: *Value objects are immutable and compare by
    value*): immutable after construction.

    DERIVED mechanism: frozen dataclasses raise an `AttributeError`
    subclass, other immutability schemes raise `TypeError`; either is "the
    attempt fails" — the same reading the existing identity-VO tests take.
    """
    metric_id = MetricId("units-fulfillable")

    with pytest.raises((AttributeError, TypeError)):
        metric_id.value = "something-else"  # type: ignore[misc]
