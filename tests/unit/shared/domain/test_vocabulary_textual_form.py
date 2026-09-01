"""A value object's textual form is its value (`shared-vocabulary`).

Derived strictly from the ADDED requirement in
`openspec/changes/fix-launch-thread-mentions/specs/shared-vocabulary/spec.md`
— *A value object's textual form is its value* — and all four of its
scenarios:

- *Rendering a single-valued vocabulary object yields its value*
- *A rendered value object round-trips*
- *A value with no single value is not rendered as an object*
- *A debugging representation is still available*

No implementation was read while writing this file. The seven types the
requirement names are named by the requirement itself ("the product
identifier, the SKU, the ASIN, the marketplace identifier, the metric
identifier, the discipline and the severity"); their module paths and
construction shapes are read off this directory's existing tests
(`test_identity_value_objects.py`, `test_metric_id.py`,
`test_discipline.py`, `test_severity.py`, `test_lifecycle_stage.py`,
`test_access_scope.py`), not off `src/`.

## Level

The value objects themselves, called directly. Rendering a value is
observable in a plain function call, so no higher level buys anything —
`ai-toolkit:testing`'s level rule. The *prohibition* half of the
requirement ("no message, prompt, log line, persisted record or control
payload SHALL be composed from a rendering of the object") is a property
of call sites, not of these objects, and is covered where those call
sites live: `test_pending_result_ask_untagged_policy.py` and
`test_stuck_step_report_submitter_fallback.py` in
`tests/unit/launch/infrastructure/driving/`, and the integration seam
test. Recorded in `test-manifest.md` rather than duplicated here.

## Expected first-run state

Every test asserting the *textual form* is expected to FAIL: today these
objects carry no `__str__`, so a frozen dataclass renders as
`ProductId(value='…')` and an enum as `Discipline.LISTING`. That is
failure state 1 — the code runs and produces a wrong value — not an
absent target: the objects exist and the assertions execute.

`test_a_value_with_no_single_value_keeps_naming_its_type` and the two
`repr` tests are expected to PASS. They are regression guards on the
requirement's own scoping (a lifecycle stage and an access scope stay
*outside* the first paragraph) and on its last scenario (the debugging
form survives), and a change to either would be the tempting
over-application of this requirement rather than its fulfilment.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import (
    Asin,
    MarketplaceId,
    MetricId,
    ProductId,
    Sku,
)
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    Posture,
    Retired,
    SteadyState,
)

# The values each of the seven objects is constructed from. Chosen so that
# no value contains a type name, the substring "value", or a bracket or
# quote — otherwise an assertion that the rendering carries none of those
# could not tell a correct rendering from a wrong one.
PRODUCT_ID_VALUE: Final = "018f3a5c-9d21-7b4e-9a11-0f2c6d8e4a37"
SKU_VALUE: Final = "BCB-2027-01"
ASIN_VALUE: Final = "B0EXAMPLE1"
MARKETPLACE_VALUE: Final = "ATVPDKIKX0DER"
METRIC_ID_VALUE: Final = "sessions"
DISCIPLINE_VALUE: Final = "listing"
SEVERITY_VALUE: Final = "critical"


def _severity() -> Any:
    from commerce_ops.shared.domain.severity import Severity

    return Severity(SEVERITY_VALUE)


#: The seven objects the requirement names, each paired with the single
#: value it carries. Built lazily inside each test's parametrisation via
#: `pytest.param` so an import failure in one does not hide the rest.
def _single_valued() -> tuple[tuple[str, Any, str], ...]:
    return (
        ("product-id", ProductId(PRODUCT_ID_VALUE), PRODUCT_ID_VALUE),
        ("sku", Sku(SKU_VALUE), SKU_VALUE),
        ("asin", Asin(ASIN_VALUE), ASIN_VALUE),
        ("marketplace-id", MarketplaceId(MARKETPLACE_VALUE), MARKETPLACE_VALUE),
        ("metric-id", MetricId(METRIC_ID_VALUE), METRIC_ID_VALUE),
        ("discipline", Discipline(DISCIPLINE_VALUE), DISCIPLINE_VALUE),
        ("severity", _severity(), SEVERITY_VALUE),
    )


def _params() -> list[Any]:
    return [
        pytest.param(subject, value, id=name)
        for name, subject, value in _single_valued()
    ]


# ---------------------------------------------------------------------------
# Scenario: Rendering a single-valued vocabulary object yields its value
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("subject", "value"), _params())
def test_rendering_a_single_valued_object_yields_exactly_its_value(
    subject: Any, value: str
) -> None:
    """Scenario: Rendering a single-valued vocabulary object yields its
    value.

    WHEN a product identifier, SKU, ASIN, marketplace identifier, metric
    identifier, discipline or severity is rendered as text
    THEN the result is exactly the value it carries, with no type name or
    field name around it.

    SPECIFIED, and asserted over the three renderings the requirement's
    prohibition half is about — `str()`, an f-string, and `%s`
    interpolation. Asserting only `str()` would leave the other two free
    to disagree with it, which is exactly the split `_decision_value` and
    `deliver_pending_result` currently have over one identifier.
    """
    assert str(subject) == value, (
        f"str() rendered {subject!r} as {str(subject)!r}, not as the value it "
        f"carries ({value!r})"
    )
    assert f"{subject}" == value, (
        f"f-string interpolation rendered {subject!r} as {f'{subject}'!r}"
    )
    # `%s` is one of the three renderings the requirement is stated over;
    # rewriting it as an f-string would delete the case rather than
    # modernise it, so the lint rule is suppressed rather than obeyed.
    percent_rendered = "%s" % subject  # noqa: UP031
    assert percent_rendered == value, (
        f"%s interpolation rendered {subject!r} as {percent_rendered!r}"
    )


@pytest.mark.parametrize(("subject", "value"), _params())
def test_a_rendering_carries_no_type_name_field_name_or_punctuation(
    subject: Any, value: str
) -> None:
    """Scenario (same one, its second clause): "with no type name or field
    name around it", and the requirement statement's "no type name, no
    field name, no punctuation around it".

    SPECIFIED. Stated separately from the equality above because the
    equality alone reads as a single opaque check, and this is the clause
    a reader of a failure needs named: the two spellings that have
    actually shipped are `ProductId(value='…')` (type name, field name and
    punctuation) and `Discipline.LISTING` (type name and punctuation).

    Each fixture value above is chosen to contain none of these markers,
    so a match can only come from the rendering rather than from the value.
    """
    rendered = str(subject)
    type_name = type(subject).__name__

    assert type_name not in rendered, f"the rendering names the type: {rendered!r}"
    assert "value" not in rendered, f"the rendering names the field: {rendered!r}"
    for mark in ("(", ")", "'", '"', "<", ">", "="):
        assert mark not in rendered, (
            f"the rendering carries punctuation around the value ({mark!r}): "
            f"{rendered!r}"
        )
    assert rendered == value


# ---------------------------------------------------------------------------
# Scenario: A rendered value object round-trips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "subject"),
    [
        pytest.param(ProductId, ProductId(PRODUCT_ID_VALUE), id="product-id"),
        pytest.param(Sku, Sku(SKU_VALUE), id="sku"),
        pytest.param(Asin, Asin(ASIN_VALUE), id="asin"),
        pytest.param(
            MarketplaceId, MarketplaceId(MARKETPLACE_VALUE), id="marketplace-id"
        ),
        pytest.param(MetricId, MetricId(METRIC_ID_VALUE), id="metric-id"),
        pytest.param(Discipline, Discipline(DISCIPLINE_VALUE), id="discipline"),
    ],
)
def test_a_rendered_value_object_round_trips(kind: Any, subject: Any) -> None:
    """Scenario: A rendered value object round-trips.

    WHEN a single-valued vocabulary object is rendered as text and a value
    object of the same kind is constructed from the result
    THEN it compares equal to the original.

    SPECIFIED. This is the clause that makes the first half *checkable*
    rather than merely stated: a rendering that dropped, padded or
    reformatted the value would satisfy "no type name" and still fail
    here.

    `Severity` is covered by its own test below rather than in this
    parametrisation, only so that its import stays inside a function —
    see `_severity`'s note.
    """
    assert kind(str(subject)) == subject, (
        f"constructing a {kind.__name__} from {str(subject)!r} did not "
        f"reproduce {subject!r}"
    )


def test_a_rendered_severity_round_trips() -> None:
    """Scenario: A rendered value object round-trips — the severity leg.

    SPECIFIED, exactly as above.
    """
    from commerce_ops.shared.domain.severity import Severity

    subject = Severity(SEVERITY_VALUE)

    assert Severity(str(subject)) == subject


# ---------------------------------------------------------------------------
# Scenario: A value with no single value is not rendered as an object
# ---------------------------------------------------------------------------


def _composite() -> tuple[tuple[str, Any], ...]:
    return (
        ("launching", Launching(phase=2)),
        ("steady-state", SteadyState(posture=Posture.HOLD)),
        ("development", Development()),
        ("retired", Retired()),
        ("unrestricted-scope", AccessScope.unrestricted()),
        ("set-scope", AccessScope.permitting((ProductId(PRODUCT_ID_VALUE),))),
    )


@pytest.mark.parametrize(
    ("subject",),
    [pytest.param(subject, id=name) for name, subject in _composite()],
)
def test_a_value_with_no_single_value_keeps_naming_its_type(subject: Any) -> None:
    """Scenario: A value with no single value is not rendered as an object.

    WHEN a lifecycle stage or an access scope is named to a person
    THEN it is named by its parts, and no rendering of the object is
    composed into the text.

    SPECIFIED, in its checkable half: the requirement scopes its first
    paragraph to *exactly seven* objects and says outright that "inventing
    a textual form for any of [the rest] would be this requirement
    choosing a format rather than stating one". So a lifecycle stage and
    an access scope must **not** acquire a single-value textual form.

    That is what keeps the prohibition enforceable. If these gained one,
    `f"{stage}"` at a call site would start producing plausible-looking
    text and the "named by its parts" rule would become unobservable —
    which is precisely the silent failure mode the requirement's own
    reasoning describes ("each time silently").

    DERIVED: the mechanism asserted — that the rendering still names the
    type — is the consequence of leaving these objects alone rather than a
    format the requirement chooses. Expected to PASS on its first run; a
    guard against over-applying the change, not coverage of new behaviour.
    """
    rendered = str(subject)
    type_name = type(subject).__name__

    assert type_name in rendered, (
        f"a value with no single value rendered as {rendered!r}, which no "
        "longer names the object it is — the requirement scopes its textual "
        "form to the seven single-valued objects and to no others"
    )


@pytest.mark.parametrize(
    ("subject", "parts"),
    [
        pytest.param(Launching(phase=2), ("phase",), id="launching"),
        pytest.param(
            SteadyState(posture=Posture.HOLD), ("posture",), id="steady-state"
        ),
    ],
)
def test_a_composite_stage_can_be_named_by_its_parts(
    subject: Any, parts: tuple[str, ...]
) -> None:
    """Scenario: A value with no single value is not rendered as an object
    — its "it is named by its parts" clause.

    SPECIFIED that such a value is named by its parts; DERIVED that the
    parts are reachable as named attributes, which is the mechanism by
    which a call site can obey the rule at all. Without this, the test
    above would forbid one spelling while establishing nothing about
    whether a correct spelling is available.

    Expected to PASS on its first run.
    """
    for part in parts:
        assert hasattr(subject, part), (
            f"{subject!r} carries no reachable {part!r}, so a caller has no "
            "way to name it by its parts"
        )


# ---------------------------------------------------------------------------
# Scenario: A debugging representation is still available
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("subject", "value"), _params())
def test_a_debugging_representation_names_the_type_and_the_value(
    subject: Any, value: str
) -> None:
    """Scenario: A debugging representation is still available.

    WHEN a value object is inspected for a diagnostic rather than rendered
    into text a person reads or a machine parses
    THEN a representation naming the type and its value is still
    available, and remains distinct from the textual form.

    SPECIFIED. This is the scenario that stops the change being
    implemented by overriding `__repr__` — which would make the textual
    form correct everywhere and delete the diagnostic in the same stroke,
    including from `use_cases.py:342`, the one audited site that wants it.
    """
    representation = repr(subject)

    assert type(subject).__name__ in representation, (
        f"the diagnostic representation no longer names the type: {representation!r}"
    )
    assert value in representation, (
        f"the diagnostic representation no longer names the value: {representation!r}"
    )


@pytest.mark.parametrize(("subject", "value"), _params())
def test_the_debugging_representation_is_distinct_from_the_textual_form(
    subject: Any, value: str
) -> None:
    """Scenario: A debugging representation is still available — its
    "remains distinct from the textual form" clause.

    SPECIFIED, and stated as its own test because it is the assertion that
    fails in *both* directions of the mistake: `repr` collapsed onto the
    value (the diagnostic lost), and `str` left as `repr` (the change not
    made). One of those is today's state and the other is the plausible
    over-correction.
    """
    assert repr(subject) != str(subject), (
        f"the diagnostic representation and the textual form are the same "
        f"string ({repr(subject)!r}); one of the two is wrong"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The prohibition half of the requirement stated over *every* call site
#   in `src/` ("no message, prompt, log line, persisted record or control
#   payload"). A test cannot read a diff, and a source sweep asserting the
#   absence of a spelling would pass for any expression whose variable
#   happens to be named otherwise. `design.md`'s audit and `tasks.md` 1.5's
#   re-run carry it instead. The four sites that audit found are covered as
#   behaviour where they live: the two `str(product_id)` message sites and
#   the control payload in the two driving-adapter files this pass adds,
#   and `use_cases.py:342` by the distinctness test above.
# - `Posture` itself, which is an enum but is not among the seven the
#   requirement names, and is reached only as a `SteadyState`'s part.
# ---------------------------------------------------------------------------
