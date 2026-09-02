"""Two defects `/code-review` found in the compliance screen, pinned.

Not derived from the delta spec: these are regressions against faults the
implementation actually had and the spec-derived suite passed over. They
are in their own file rather than folded into the spec-derived ones so
that the mapping in `test-manifest.md` stays a mapping — every test there
answers to a `#### Scenario:`, and neither of these does.

Both faults reach the same place from opposite directions: a step
recorded `Satisfied`, or blocked forever, on a screen that never happened.

**1. The veto fired on ordinary clear-verdict prose.** The refused act was
matched as a bare word within sixty characters of the refusal verb, and
`screen`, `classify` and `determine` are exactly the words a *passing*
comment uses about the categories. "I cannot find anything in this
product that a hazmat **screen** would flag" matched, so a clear verdict
was recorded as a self-contradiction. Because the same prompt yields the
same shape for the same product, that is not a one-off: the step is
blocked on every pass, which is the failure the veto's own requirement
names and forbids.

The spec-derived suite could not catch it. Its negative fixture,
`CATEGORY_CALLED_INAPPLICABLE`, puts the *category* in the subject
position ("Supplements cannot apply…"), which never reaches
`_REFUSING_SUBJECT` at all — so the first-person-about-a-category
phrasing, which is what a model actually writes, was untested.

**2. A product the pass could not resolve was screened as the empty
string.** `automation_pass` reads the catalog through a call typed
`Product | None` and hands the result to the handler without a nil check,
so `context.product` is genuinely `None` sometimes. The prompt then read
`Product:` with nothing after it, the model answered anyway — plausibly
`clear` — and the step was satisfied for a product nobody could read.
This is the exact reasoning the blank-`description` guard already carries
("a model asked to screen against nothing would answer anyway"), applied
to the other half of the prompt.
"""

from __future__ import annotations

import pytest

from commerce_ops.launch.domain.launch_playbook import Blocked
from commerce_ops.step_handlers.strategy import compliance_screen as screen


def _reason(resolution: object) -> str:
    """The reason of a withheld outcome, narrowed for the type checker.

    `StepResolution.outcome` is the six-outcome union and only `Blocked`
    carries a reason, so the `isinstance` is what makes the attribute
    readable — and doubles as the assertion that satisfaction was not
    proposed.
    """
    outcome = getattr(resolution, "outcome", None)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome.reason


DESCRIPTION = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)

#: Clear-verdict comments whose prose uses the screening vocabulary about
#: the *categories*, in the first person. Every one of these was vetoed
#: before the fix, and every one is a comment a passing product would get.
CLEAR_PROSE_THE_VETO_MUST_NOT_FIRE_ON = [
    (
        "I cannot find anything in this product that a hazmat screen would "
        "flag; it is an untreated bamboo board and none of the named "
        "categories applies."
    ),
    ("I could not find any category that would classify this product as prohibited."),
    "I could not determine any hazard because there is none to determine.",
    "We cannot see a reason to classify this as a medical device.",
]

#: Comments that really do withhold the screen's own judgement. The veto
#: must still fire on these, or the fix has simply disabled it.
REFUSALS_THE_VETO_MUST_STILL_CATCH = [
    (
        "On reflection I cannot screen this product properly without knowing "
        "whether the unit contains a lithium battery or a pressurised cell."
    ),
    "I cannot determine whether this contains a magnet from the name alone.",
    "We are unable to classify this product without its materials list.",
    "I am unable to say whether the contents are ingestible.",
]


@pytest.mark.parametrize("comment", CLEAR_PROSE_THE_VETO_MUST_NOT_FIRE_ON)
def test_the_veto_does_not_fire_on_clear_prose_about_the_categories(
    comment: str,
) -> None:
    """A first-person sentence about what the *categories* do is not the
    screen refusing to screen.

    Asserted at the predicate rather than through the graph: the failure
    is entirely in what the sentence is read to mean, and going through a
    stubbed model would put the same assertion behind more machinery.
    """
    assert not screen._screen_refuses(comment), (
        "the veto fired on a clear verdict's ordinary prose, which blocks "
        f"the step on every pass for this product: {comment!r}"
    )


@pytest.mark.parametrize("comment", REFUSALS_THE_VETO_MUST_STILL_CATCH)
def test_the_veto_still_catches_the_screen_refusing_to_screen(
    comment: str,
) -> None:
    """The narrowing must not have turned the veto off.

    Paired with the test above deliberately: a fix that simply stopped
    matching would pass that one and fail this one.
    """
    assert screen._screen_refuses(comment), (
        "the veto no longer catches the screen stating it cannot do its "
        f"work, so a withheld verdict would reach a member as one to "
        f"accept: {comment!r}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("product_name", ["", "   ", "\n\t"])
async def test_a_product_with_no_name_is_never_screened(product_name: str) -> None:
    """A product the pass could not resolve reaches no model and no
    satisfying outcome.

    `propose` is called directly. The route under test is reached before a
    graph is built, so `graph=None` is safe here and is itself part of the
    assertion — a `graph` this test never supplies would have to be the
    production one, and building it would raise on the absent credential.
    """
    resolution = await screen.propose(
        product_name=product_name, categories=DESCRIPTION, graph=None
    )

    reason = _reason(resolution)
    assert "no product" in reason.lower(), (
        f"the reason does not state that no product was given: {reason!r}"
    )


@pytest.mark.anyio
async def test_a_nameless_product_is_not_reported_as_a_step_that_named_nothing() -> (
    None
):
    """The two guards state two different things, and must not share a
    reason.

    An operator reading "the step names no categories" where the truth was
    "the catalog row could not be read" goes and edits the playbook.
    """
    no_product = await screen.propose(
        product_name="", categories=DESCRIPTION, graph=None
    )
    no_categories = await screen.propose(
        product_name="Bamboo Cutting Board", categories=None, graph=None
    )

    assert _reason(no_product) != _reason(no_categories), (
        "an unresolvable product and a step naming no categories were "
        "recorded under the same reason"
    )


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"
