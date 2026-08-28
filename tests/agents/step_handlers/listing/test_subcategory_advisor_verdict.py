"""The advisor's verdict, and what may and may not establish support.

Derived strictly from the delta spec of the change
`separate-the-verdict-from-the-prose`:
`openspec/changes/separate-the-verdict-from-the-prose/specs/subcategory-advisor/spec.md`

One MODIFIED requirement — *The advisor proposes satisfaction only where
it can support a node choice* — carrying twelve scenarios. Eleven are
covered here. The twelfth, *A supported choice proposes satisfaction*, is
reproduced verbatim from the served requirement and is already covered by
`test_a_supported_choice_proposes_satisfaction` in
`test_subcategory_advisor_graph.py`; it is not re-derived here. See
`test-manifest.md` at the change root for the full accounting, including
why *An unsupported choice proposes no satisfaction* **is** re-derived
despite also being reproduced verbatim.

A separate file rather than additions to the existing one, because this
pass is additive only: `test_subcategory_advisor_graph.py` is not edited,
deleted or weakened by it. Two of its stubs need updating for the new
mechanism (`tasks.md` 4.1 and 4.1a) and that is the implementer's task,
not this pass's.

## The distinction every test here turns on

Support is established **only** by the verdict the advisor reports as a
value alongside the recommendation, never by the recommendation's
wording. The wording may still *withhold* support — a verdict reporting
support whose own prose states the advisor cannot assign a node is
treated as unsupported — but no phrasing may produce the satisfying
outcome. That asymmetry is why the fixtures below are built in pairs: the
same prose reaches opposite outcomes depending on the verdict, and
opposite prose reaches the same outcome under one verdict.

## Level

`propose()` is the smallest unit that can observe eleven of these twelve
scenarios: each states an outcome or a recorded reason as a function of
the verdict and the recommendation, and `propose()` is where a verdict
becomes an outcome. So most tests here drive `propose()` over a stubbed
graph returning state directly, rather than over a stubbed chat model.

That choice is deliberate and worth naming. Driving a chat model would
additionally exercise how the graph *parses* a verdict out of the model's
answer — but the artifacts fix no answer format for it, so a test written
that way would assert an invented wire format rather than the
requirement, which is the same defect `design.md`'s Decision 4 indicts in
the existing unsupported-path test. Two scenarios do need more:

- *A response that is not text still fails visibly* runs the real
  compiled graph over a stubbed model, since a non-string response
  content is a property of the model call.
- *An unsupported recommendation still says so in prose* asserts the
  **prompt** instructs the prose refusal (`tasks.md` 1.2a). Against a
  stubbed model the recommendation is whatever the stub was told to say,
  so reading it back would pass against any implementation at all.

## Correction points — INVENTED, each recorded in `test-manifest.md`

Nothing in the artifacts fixes how the verdict is spelled. Three
constants carry every assumption about it, and each is the single place
to correct:

- `_verdict_field()` — the `AdvisorState` key the verdict is written to.
  It reads `AdvisorState`'s own declared fields rather than hard-coding a
  name: a known candidate name if one is declared, otherwise the single
  field declared beyond the three that exist today. It fails loudly, and
  says what it saw, rather than guessing.
- `SUPPORTED_VERDICT` / `UNSUPPORTED_VERDICT` — the two values. Taken
  from the delta's own wording, "a value that is neither supported nor
  unsupported". If the implementation spells them as enum members these
  two constants are the only edit needed.
- `UNRECOGNISED_VERDICT` — a value that is neither of those.

What must survive any correction is what each test asserts: which outcome
each verdict reaches, that prose cannot establish support, that prose can
withhold it, that a refusal is recognised however worded, that a rejected
alternative called unsupportable is not a refusal, that each withheld
path records its own distinct reason, and that a non-text response still
fails visibly instead of resolving to unsupported.

## Expected first-run state

No implementation exists (`tasks.md` sections 2 and 3 are unstarted), so
every test here is expected to fail, in one of two ways:

- Tests needing the verdict field fail on an absent target — the field is
  not declared, so `_verdict_field()` fails and says so. Per
  `ai-toolkit:testing` that establishes absence only: their assertions
  have not been exercised.
- Tests that supply no verdict at all — the missing-verdict scenarios —
  reach today's `propose()` and fail on a wrong value: it proposes
  `Satisfied` where the fail-safe requires a non-terminal outcome.

One test is exempt and is expected to **pass** on its first run:
*An unsupported recommendation still says so in prose* asserts a prompt
clause the pre-change prompt already carries and this change requires be
kept (`tasks.md` 2.2), so it is a regression guard on an existing
instruction rather than coverage of new behaviour. `tasks.md` 1.3 names
that exemption.

Baseline recorded before these tests were written:
`uv run pytest tests/agents` — 14 passed, 0 failed. Scoped to the agent
tier, which is the tier `AGENTS.md` places this subject in and the only
tier this change touches.
"""

from __future__ import annotations

import re
from typing import Any, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    InProgress,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"

# The four literal substrings today's `_is_unsupported` searches for, and
# which this change deletes as the *decider*. Quoted here because the
# delta names them itself, in *A refusal is recognised however it is
# worded*: a refusal phrased so that searching it for these finds nothing
# must still reach a non-terminal outcome.
OLD_MARKERS: Final = (
    "cannot support",
    "can not support",
    "no confident answer",
    "unable to support",
)

# --- The verdict's spelling: the file's three correction points ---------

SUPPORTED_VERDICT: Final = "supported"
UNSUPPORTED_VERDICT: Final = "unsupported"
UNRECOGNISED_VERDICT: Final = "probably"

_BASE_STATE_FIELDS: Final = frozenset({"product_name", "marketplace", "recommendation"})
_VERDICT_FIELD_CANDIDATES: Final = (
    "verdict",
    "support_verdict",
    "node_verdict",
    "support",
    "supported",
    "can_support",
)

# --- Recommendations ----------------------------------------------------

# A well-formed recommendation: node path, demands, rejected alternative,
# and nothing that reads as a refusal. The recommendation the fail-safe
# scenarios pair with a verdict that is missing or unreadable — the model
# wrote a usable answer and simply did not report its verdict.
WELL_FORMED_RECOMMENDATION: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative "
    "Trays — higher keyword volume, but it understates this product's "
    "compliance surface."
)

# The delta's carve-out, and the one fixture a naive detector reusing the
# deleted marker list would trip on: the rejected *alternative* is
# described as unable to support something, which is a statement about
# that alternative and not about the advisor's ability to choose. It
# contains a literal old marker on purpose.
ALTERNATIVE_CALLED_UNSUPPORTABLE: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative "
    "Trays. That node cannot support a food-contact claim at all, which "
    "is why it was rejected here."
)

# The production phrasing, from `proposal.md`'s *Why*: the wording known
# to have defeated the deleted matcher, and therefore the wording an
# unsupported-path test has to use to assert the requirement rather than
# the mechanism.
REFUSAL_WITHOUT_MARKERS: Final = (
    "To give an accurate reply I would need specific details about this "
    "item; without them I cannot confidently assign a sub-category node, "
    "nor the compliance obligations that follow from one."
)

# A second refusal, sharing no wording with the first — and containing an
# old marker, so the pair spans both sides of the deleted matcher.
REFUSAL_WITH_A_MARKER: Final = (
    "Amazon's browse tree is too ambiguous here, so the advisor is "
    "unable to support a placement for this listing."
)


# ---------------------------------------------------------------------------
# Resolving the verdict field, and building state around it
# ---------------------------------------------------------------------------


def _verdict_field() -> str:
    """The `AdvisorState` key carrying the verdict.

    Read off `AdvisorState`'s own declared fields rather than assumed, so
    a name this file did not anticipate still resolves. Fails loudly and
    names what it saw where it cannot decide — never defaults.
    """
    declared: list[str] = list(advisor_graph.AdvisorState.__annotations__)
    for candidate in _VERDICT_FIELD_CANDIDATES:
        if candidate in declared:
            return candidate
    added: list[str] = [name for name in declared if name not in _BASE_STATE_FIELDS]
    if len(added) == 1:
        return added[0]
    pytest.fail(
        "cannot tell which `AdvisorState` field carries the verdict. "
        f"Declared fields: {declared}. Expected one of "
        f"{list(_VERDICT_FIELD_CANDIDATES)}, or exactly one field beyond "
        f"{sorted(_BASE_STATE_FIELDS)} — correct "
        "`_VERDICT_FIELD_CANDIDATES` to the implemented name."
    )


_ABSENT: Final = object()


def _state(recommendation: str, verdict: object = _ABSENT) -> dict[str, object]:
    """The state a graph run leaves behind, with or without a verdict.

    `verdict` left at its default produces state carrying no verdict key
    at all, which is what *A missing verdict is unsupported, not
    supported* requires and what `AdvisorState`'s `total=False` makes
    representable. That path never asks for the field's name, so it
    exercises `propose()` even before the field exists.
    """
    state: dict[str, object] = {"recommendation": recommendation}
    if verdict is not _ABSENT:
        state[_verdict_field()] = verdict
    return state


class _StubbedAdvisorGraph:
    """A graph that returns prepared state, invoking no model at all.

    The seam is `propose(graph=...)`, the same one the handler uses to
    inject the production graph.
    """

    def __init__(self, state: dict[str, object]) -> None:
        self._state = state
        self.invocations: list[dict[str, object]] = []

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        self.invocations.append(dict(payload))
        return {**payload, **self._state}


def _propose_over(state: dict[str, object]) -> Any:
    """Run the advisor's proposing entry point over prepared state."""
    return advisor_graph.propose(
        product_name=PRODUCT_NAME,
        marketplace=MARKETPLACE,
        graph=_StubbedAdvisorGraph(state),
    )


# ---------------------------------------------------------------------------
# Reading a proposal
# ---------------------------------------------------------------------------


def _outcome_of(proposal: Any) -> Any:
    for attribute in ("outcome", "proposed_outcome"):
        carried = getattr(proposal, attribute, None)
        if carried is not None:
            return carried
    pytest.fail(f"the advisor's proposal carries no outcome: {proposal!r}")


def _text_of(proposal: Any) -> str:
    for attribute in ("result", "recommendation", "text"):
        carried = getattr(proposal, attribute, None)
        if isinstance(carried, str):
            return carried
    pytest.fail(f"the advisor's proposal carries no produced text: {proposal!r}")


def _reason_of(proposal: Any) -> str:
    """The reason recorded on the outcome.

    Only the outcome's own reason, with no fallback to the produced text:
    the delta speaks of "the reason recorded", and the four
    reason-bearing scenarios are about what an operator reads on the
    launch's record, which is the outcome's reason.
    """
    outcome = _outcome_of(proposal)
    reason = getattr(outcome, "reason", None)
    if isinstance(reason, str) and reason.strip():
        return reason
    pytest.fail(f"the advisor's proposed outcome carries no reason: {outcome!r}")


def _assert_withheld(proposal: Any) -> Any:
    """Assert the proposal withholds satisfaction, and return its outcome.

    SPECIFIED: it "proposes a non-terminal outcome and does not propose a
    satisfying outcome". `permissible_terminal_outcomes` makes `Satisfied`,
    `NotApplicable` and `Refused` the terminal three, so all three are
    excluded rather than only `Satisfied` — `NotApplicable` would close
    the step just as firmly.

    DERIVED, and narrower than the scenario's own words: `Blocked`
    specifically. Of the three non-terminal outcomes it is the only one
    carrying a reason, and every one of these scenarios requires a reason
    to be recorded, so the outcome vocabulary leaves nothing else the
    requirement could mean. Recorded as derived because the scenarios say
    "non-terminal", not "Blocked".
    """
    outcome = _outcome_of(proposal)
    assert outcome is not Satisfied
    assert outcome not in (Satisfied, Refused, NotApplicable)
    assert not isinstance(outcome, (Satisfied, Refused, NotApplicable))
    assert not isinstance(outcome, (NotStarted, InProgress)), (
        f"expected a non-terminal outcome carrying a reason, got {outcome!r}"
    )
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal outcome carrying a reason, got {outcome!r}"
    )
    return outcome


def _significant_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= 5}


def _assert_free_of_old_markers(text: str) -> None:
    """Guard on this file's own fixtures, not on the implementation.

    A test whose stub recites one of the deleted matcher's phrases proves
    nothing about the new mechanism even when it is green
    (`tasks.md` 4.2). This makes that property of the fixture an assertion
    rather than a comment, so an edit that reintroduces a marker phrase
    fails rather than silently hollowing the test out.
    """
    lowered = text.lower()
    recited = [marker for marker in OLD_MARKERS if marker in lowered]
    assert not recited, (
        f"this fixture recites the deleted matcher's phrasing {recited}, so "
        "it would pass against the substring matcher this change removes"
    )


# ---------------------------------------------------------------------------
# A stubbed model, for the one scenario that needs a real graph run
# ---------------------------------------------------------------------------


class _NonStringContentChatModel(BaseChatModel):
    """A chat model whose response content is not a plain string.

    The shape a multimodal or content-block response actually takes — a
    list of blocks — rather than an invented sentinel.
    """

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=[{"type": "text", "text": WELL_FORMED_RECOMMENDATION}]
                    )
                )
            ]
        )

    @property
    def _llm_type(self) -> str:
        return "non-string-content-fake-chat-model"


# ---------------------------------------------------------------------------
# The verdict is a value, reported alongside the recommendation
# ---------------------------------------------------------------------------


def test_the_verdict_is_reported_as_a_value_alongside_the_recommendation() -> None:
    """Requirement statement: "Support SHALL be established only by a
    verdict the advisor reports as a **value alongside** the
    recommendation, and never by the recommendation's wording."

    Not a scenario of its own; the structural precondition every scenario
    below reads through. Asserted separately so that a run where the
    verdict field is simply absent says so once, plainly, instead of
    eleven times through a helper.

    SPECIFIED: the verdict is a value the advisor reports, and it is
    *alongside* the recommendation rather than inside it — so a state
    schema carrying only `recommendation` does not satisfy it.
    """
    declared: set[str] = set(advisor_graph.AdvisorState.__annotations__)

    assert "recommendation" in declared, (
        "the recommendation must still be carried as its own value: "
        f"declared fields are {sorted(declared)}"
    )
    field = _verdict_field()
    assert field != "recommendation", (
        "the verdict must be a value alongside the recommendation, not "
        "something read back out of it"
    )


# ---------------------------------------------------------------------------
# Scenario: An unsupported choice proposes no satisfaction
# ---------------------------------------------------------------------------


def test_an_unsupported_choice_proposes_no_satisfaction() -> None:
    """Scenario: An unsupported choice proposes no satisfaction.

    WHEN the advisor cannot support a confident node choice for the given
    product and marketplace
    THEN it proposes a non-terminal outcome whose reason states that it
    cannot support a choice, and does not propose a satisfying outcome.

    Reproduced verbatim from the served requirement, and re-derived
    anyway (`tasks.md` 1.1). The existing test for it passes only because
    its stub recites `cannot support` — the very inference this change
    rejects — so it establishes the matcher, not the requirement. This one
    refuses in wording containing none of the four deleted markers.
    """
    _assert_free_of_old_markers(REFUSAL_WITHOUT_MARKERS)

    proposal = _propose_over(_state(REFUSAL_WITHOUT_MARKERS, UNSUPPORTED_VERDICT))

    # SPECIFIED: a non-terminal outcome, and not a satisfying one.
    outcome = _assert_withheld(proposal)

    # SPECIFIED: whose reason states that it cannot support a choice.
    # DERIVED: the keywords. The delta fixes what the reason must say and
    # `tasks.md` 3.4 keeps today's wording for this path — it "already
    # names the product and marketplace and states that no node choice
    # could be supported" — but no exact string is specified.
    reason = outcome.reason.lower()
    assert "support" in reason
    assert "node" in reason or "choice" in reason or "categor" in reason
    assert PRODUCT_NAME.lower() in reason
    assert MARKETPLACE.lower() in reason

    # SPECIFIED: the recommendation still reaches the reader whole.
    assert _text_of(proposal) == REFUSAL_WITHOUT_MARKERS


# ---------------------------------------------------------------------------
# Scenario: A refusal is recognised however it is worded
# ---------------------------------------------------------------------------


def test_a_refusal_is_recognised_however_it_is_worded() -> None:
    """Scenario: A refusal is recognised however it is worded.

    WHEN the advisor reports that it cannot support a node choice in two
    invocations whose recommendations share no wording, one of them
    phrased so that searching it for `cannot support`, `can not support`,
    `no confident answer` or `unable to support` finds nothing
    THEN both propose a non-terminal outcome.

    The scenario's whole content is that the two reach the *same*
    outcome, so both halves are asserted in one test rather than split —
    separated, each half is just another unsupported-path test and the
    equivalence nobody asserts is the thing the requirement is about.
    """
    # Guards on the fixtures, so the scenario's own preconditions hold
    # rather than being asserted in a comment.
    _assert_free_of_old_markers(REFUSAL_WITHOUT_MARKERS)
    shared = _significant_words(REFUSAL_WITHOUT_MARKERS) & _significant_words(
        REFUSAL_WITH_A_MARKER
    )
    assert not shared, (
        f"the two refusals were meant to share no wording, but share {sorted(shared)}"
    )
    assert any(marker in REFUSAL_WITH_A_MARKER.lower() for marker in OLD_MARKERS), (
        "the second refusal was meant to span the other side of the deleted "
        "matcher by containing one of its phrases"
    )

    marker_free = _propose_over(_state(REFUSAL_WITHOUT_MARKERS, UNSUPPORTED_VERDICT))
    marker_laden = _propose_over(_state(REFUSAL_WITH_A_MARKER, UNSUPPORTED_VERDICT))

    # SPECIFIED: both propose a non-terminal outcome.
    free_outcome = _assert_withheld(marker_free)
    laden_outcome = _assert_withheld(marker_laden)

    # SPECIFIED: "Two refusals that mean the same thing SHALL therefore
    # reach the same outcome, whatever words each uses." Same outcome,
    # not merely two outcomes each independently non-terminal.
    assert free_outcome == laden_outcome, (
        "two refusals differing only in wording reached different outcomes: "
        f"{free_outcome!r} and {laden_outcome!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: The recommendation's wording does not establish the outcome
# ---------------------------------------------------------------------------


def test_the_recommendations_wording_does_not_establish_the_outcome() -> None:
    """Scenario: The recommendation's wording does not establish the
    outcome.

    WHEN the advisor reports that it can support a node choice and
    returns a recommendation naming a node, its demands and a rejected
    alternative
    THEN it proposes the satisfying outcome, whatever the recommendation's
    prose contains short of a statement that the advisor cannot assign a
    node — including a rejected alternative described as unsupportable,
    which is a statement about that alternative and not about the
    advisor's ability to choose.

    The boundary case for the veto, and the one case where a detector
    reusing the deleted marker list would wrongly block the step — on
    every pass, not once, because the same prompt over the same product
    yields prose of the same shape (`design.md` — Decision 1a).
    """
    assert any(
        marker in ALTERNATIVE_CALLED_UNSUPPORTABLE.lower() for marker in OLD_MARKERS
    ), (
        "this fixture only bounds the veto if it contains a phrase the "
        "deleted matcher would have fired on"
    )

    proposal = _propose_over(
        _state(ALTERNATIVE_CALLED_UNSUPPORTABLE, SUPPORTED_VERDICT)
    )

    # SPECIFIED: it proposes the satisfying outcome.
    assert _outcome_of(proposal) is Satisfied, (
        "a rejected alternative described as unsupportable was read as the "
        "advisor refusing, which blocks the step on every pass for this "
        "product"
    )
    # SPECIFIED: together with the recommendation, whole.
    assert _text_of(proposal) == ALTERNATIVE_CALLED_UNSUPPORTABLE


# ---------------------------------------------------------------------------
# Scenario: A verdict contradicting its own prose withholds satisfaction
# ---------------------------------------------------------------------------


def test_a_verdict_contradicting_its_own_prose_withholds_satisfaction() -> None:
    """Scenario: A verdict contradicting its own prose withholds
    satisfaction.

    WHEN the advisor reports that it can support a node choice but the
    recommendation states that it cannot assign one
    THEN it proposes a non-terminal outcome and does not propose a
    satisfying outcome.

    The prose that refuses here contains none of the four deleted
    markers, so the veto cannot be satisfied by keeping the old list
    under a new name (`tasks.md` 3.3): it must detect the production
    phrasing the old list missed, while still not firing on the rejected
    alternative in the test above.
    """
    _assert_free_of_old_markers(REFUSAL_WITHOUT_MARKERS)

    proposal = _propose_over(_state(REFUSAL_WITHOUT_MARKERS, SUPPORTED_VERDICT))

    # SPECIFIED: a non-terminal outcome, and not a satisfying one — this
    # is the served prohibition on "a satisfying one accompanied by text
    # admitting there is no answer", and the exact shape of the 2026-08-27
    # production defect.
    _assert_withheld(proposal)


# ---------------------------------------------------------------------------
# Scenario: A missing verdict is unsupported, not supported
# ---------------------------------------------------------------------------


def test_a_missing_verdict_is_unsupported_not_supported() -> None:
    """Scenario: A missing verdict is unsupported, not supported.

    WHEN the advisor produces a recommendation but reports no verdict at
    all
    THEN it proposes a non-terminal outcome and does not propose a
    satisfying outcome.

    The recommendation here is well-formed and says nothing about being
    unable to choose, so nothing but the verdict's absence can reach the
    outcome. That also makes this the one shape where reading support out
    of a default would be invisible: "Absence is not evidence of a
    supportable node choice."
    """
    proposal = _propose_over(_state(WELL_FORMED_RECOMMENDATION))

    # SPECIFIED: unsupported, not supported.
    _assert_withheld(proposal)


# ---------------------------------------------------------------------------
# Scenario: An unreadable verdict is unsupported, not supported
# ---------------------------------------------------------------------------


def test_an_unreadable_verdict_is_unsupported_not_supported() -> None:
    """Scenario: An unreadable verdict is unsupported, not supported.

    WHEN the advisor reports a verdict that is neither supported nor
    unsupported
    THEN it proposes a non-terminal outcome and does not propose a
    satisfying outcome.
    """
    assert UNRECOGNISED_VERDICT not in (SUPPORTED_VERDICT, UNSUPPORTED_VERDICT)

    proposal = _propose_over(_state(WELL_FORMED_RECOMMENDATION, UNRECOGNISED_VERDICT))

    # SPECIFIED: unsupported, not supported.
    _assert_withheld(proposal)


# ---------------------------------------------------------------------------
# Scenario: A fail-safe reason names what was wrong
# ---------------------------------------------------------------------------


def test_a_fail_safe_reason_names_what_was_wrong() -> None:
    """Scenario: A fail-safe reason names what was wrong.

    WHEN the advisor proposes a non-terminal outcome because it reported
    no verdict
    THEN the reason states that no verdict was reported, and does not
    assert that a node choice could not be supported for the product.

    The negative half is the load-bearing one: recording a model
    shortfall as a finding about the product is the substitution
    `launch-step-automation` refuses.
    """
    proposal = _propose_over(_state(WELL_FORMED_RECOMMENDATION))
    reason = _reason_of(proposal).lower()

    # SPECIFIED: the reason states that no verdict was reported.
    # DERIVED: the keywords. The delta fixes what must be said, not how.
    assert "verdict" in reason, (
        f"the reason does not name the missing verdict: {reason!r}"
    )
    assert any(
        absence in reason
        for absence in ("no verdict", "without", "missing", "absent", "did not", "none")
    ), f"the reason does not say the verdict was not reported: {reason!r}"

    # SPECIFIED: and does not assert that a node choice could not be
    # supported for the product — only a classification considered and
    # declined is a finding about the product at all.
    assert "could not support" not in reason
    assert "cannot support" not in reason
    assert "unable to support" not in reason


# ---------------------------------------------------------------------------
# Scenario: An unrecognised verdict is not reported as an absent one
# ---------------------------------------------------------------------------


def test_an_unrecognised_verdict_is_not_reported_as_an_absent_one() -> None:
    """Scenario: An unrecognised verdict is not reported as an absent one.

    WHEN the advisor proposes a non-terminal outcome because its verdict
    carried an unrecognised value
    THEN the reason says so, and does not state that no verdict was
    reported.
    """
    proposal = _propose_over(_state(WELL_FORMED_RECOMMENDATION, UNRECOGNISED_VERDICT))
    reason = _reason_of(proposal)
    lowered = reason.lower()

    # SPECIFIED: the reason says the verdict's value was unrecognised.
    # DERIVED: the keywords, and that the offending value itself appears —
    # the delta requires the reason to "name what was actually wrong",
    # and the value is what was wrong.
    assert "verdict" in lowered, f"the reason does not name the verdict: {reason!r}"
    assert any(
        word in lowered
        for word in (
            "unrecognis",
            "unrecogniz",
            "unreadable",
            "not recognis",
            "neither",
        )
    ), f"the reason does not say the verdict's value was unrecognised: {reason!r}"
    assert UNRECOGNISED_VERDICT in lowered, (
        f"the reason does not name the value that was unrecognised: {reason!r}"
    )

    # SPECIFIED: and does not state that no verdict was reported.
    for absence in ("no verdict", "without a verdict", "missing verdict"):
        assert absence not in lowered, (
            f"an unrecognised verdict was reported as an absent one: {reason!r}"
        )


# ---------------------------------------------------------------------------
# Scenario: A vetoed verdict names the contradiction
# ---------------------------------------------------------------------------


def test_a_vetoed_verdict_names_the_contradiction() -> None:
    """Scenario: A vetoed verdict names the contradiction.

    WHEN the advisor proposes a non-terminal outcome because a supporting
    verdict was contradicted by its own recommendation
    THEN the reason names that contradiction, and does not assert that
    the advisor considered and declined a classification.
    """
    proposal = _propose_over(_state(REFUSAL_WITHOUT_MARKERS, SUPPORTED_VERDICT))
    reason = _reason_of(proposal)
    lowered = reason.lower()

    # SPECIFIED: the reason names the contradiction — a verdict reporting
    # support against a recommendation that refuses.
    # DERIVED: the keywords.
    assert "verdict" in lowered, (
        f"the reason does not name the verdict at all: {reason!r}"
    )
    assert any(
        word in lowered
        for word in ("contradict", "conflict", "disagree", "inconsistent")
    ), f"the reason does not name the contradiction: {reason!r}"
    assert "recommendation" in lowered or "prose" in lowered, (
        f"the reason does not name what contradicted the verdict: {reason!r}"
    )

    # SPECIFIED: and does not assert that the advisor considered and
    # declined a classification. Today's genuine-refusal wording is
    # exactly that assertion, so it must not be reused here.
    assert "could not support a node choice" not in lowered, (
        "a self-contradicting verdict was recorded as the advisor having "
        f"considered and declined a classification: {reason!r}"
    )


# ---------------------------------------------------------------------------
# The four withheld paths, read together
# ---------------------------------------------------------------------------


def test_each_withheld_path_records_its_own_reason() -> None:
    """Requirement statement: "the reason recorded SHALL name what was
    actually wrong — a verdict that was never reported, a verdict
    reported with an unrecognised value, or a verdict reporting support
    that its own recommendation contradicts — rather than assert that no
    node choice could be supported for the product. An operator reading
    the launch record SHALL be able to tell each of those from a
    classification the advisor considered and declined."

    The three scenarios above each check one path against one other
    thing it must not say. This checks the property they add up to and
    none of them can see alone: four paths, four distinct reasons. A
    single shared fail-safe wording would satisfy parts of each scenario
    while defeating the clause.

    The fixtures are deliberately paired so prose cannot supply the
    distinctness: the two fail-safe paths carry the *same* recommendation
    and differ only in the verdict, and the refusal and veto paths carry
    the same recommendation and differ only in the verdict too. Anything
    that tells them apart has to come from the reason itself.
    """
    reasons = {
        "genuine refusal": _reason_of(
            _propose_over(_state(REFUSAL_WITHOUT_MARKERS, UNSUPPORTED_VERDICT))
        ),
        "no verdict reported": _reason_of(
            _propose_over(_state(WELL_FORMED_RECOMMENDATION))
        ),
        "unrecognised verdict value": _reason_of(
            _propose_over(_state(WELL_FORMED_RECOMMENDATION, UNRECOGNISED_VERDICT))
        ),
        "verdict contradicted by its prose": _reason_of(
            _propose_over(_state(REFUSAL_WITHOUT_MARKERS, SUPPORTED_VERDICT))
        ),
    }

    # SPECIFIED: an operator can tell each of the four apart.
    distinct = {reason for reason in reasons.values()}
    assert len(distinct) == len(reasons), (
        "two or more withheld paths recorded the same reason, so an "
        "operator cannot tell a model shortfall from a finding about the "
        f"product: {reasons}"
    )


# ---------------------------------------------------------------------------
# Scenario: A response that is not text still fails visibly
# ---------------------------------------------------------------------------


def test_a_response_that_is_not_text_still_fails_visibly() -> None:
    """Scenario: A response that is not text still fails visibly.

    WHEN the model answers with content that is not plain text
    THEN the failure is surfaced as a model failure, and no outcome is
    proposed for the step.

    The one scenario needing a real graph run, because a non-string
    response content is a property of the model call rather than of the
    state a run leaves behind. It is the fail-safe's boundary: "A verdict
    the model was asked for and did not give is a shortfall the fail-safe
    answers; a response that is not text at all is a fault, and the two
    SHALL be distinguishable on the launch's record." Resolving this to
    unsupported would enter a client or prompt fault on the launch as the
    advisor's judgement about a product.

    SPECIFIED: that it fails, and that no outcome is proposed.
    DERIVED-adjacent: nothing in the delta fixes the exception type, so
    any visible failure satisfies it — which is why this asserts a raise
    rather than a named class. What it does assert precisely is the
    negative: no `Blocked`, and no proposal of any kind.
    """
    graph = advisor_graph.build_graph(_NonStringContentChatModel())

    try:
        proposal = advisor_graph.propose(
            product_name=PRODUCT_NAME,
            marketplace=MARKETPLACE,
            graph=graph,
        )
    except AssertionError:  # pragma: no cover - a defect in this test, not a pass
        raise
    except Exception:  # noqa: BLE001 - the specified path: any visible failure
        return

    outcome = _outcome_of(proposal)
    pytest.fail(
        "a response whose content is not plain text was absorbed into a "
        f"proposal ({outcome!r}) instead of failing visibly"
        + (
            " — it was resolved to unsupported, which the fail-safe "
            "explicitly does not extend to"
            if isinstance(outcome, Blocked)
            else ""
        )
    )


# ---------------------------------------------------------------------------
# Scenario: An unsupported recommendation still says so in prose
# ---------------------------------------------------------------------------


def _prompt_text() -> str:
    """Every prompt template the advisor module declares, joined.

    Found by shape rather than by name, so a renamed or split prompt
    still resolves.
    """
    templates = [
        value
        for value in vars(advisor_graph).values()
        if isinstance(value, str) and "{product_name}" in value
    ]
    if not templates:
        pytest.fail(
            "no prompt template found on the advisor module — no "
            "module-level string interpolates `{product_name}`"
        )
    return "\n".join(templates)


def test_an_unsupported_recommendation_still_says_so_in_prose() -> None:
    """Scenario: An unsupported recommendation still says so in prose.

    WHEN the advisor cannot support a node choice
    THEN the recommendation it returns states that it cannot support one,
    readable without reference to the verdict value.

    Verified against the **prompt**, not against a stub's output
    (`tasks.md` 1.2a). Against a stubbed model the recommendation is
    whatever the stub was told to say, so a test reading it back would
    pass against any implementation — including one that dropped the
    prose instruction entirely, which is precisely what this scenario
    exists to forbid.

    `tasks.md` 1.3 exempts this test from the absent-target baseline: the
    prompt clause it guards already exists and `tasks.md` 2.2 requires it
    be kept, so this is a regression guard rather than coverage of new
    behaviour. It is expected to pass on its first run, and that is not
    the alarm a first-run pass usually is.

    SPECIFIED: the prompt instructs the model to state the refusal in the
    recommendation's own prose.
    DERIVED: the verb and refusal-phrase vocabularies below. Nothing
    fixes the prompt's wording; what is fixed is that an instruction to
    say it is there.
    """
    prompt = _prompt_text()
    sentences = re.split(r"[.\n]", prompt.lower())

    instruction_verbs = ("say", "state", "tell", "write", "explain", "report")
    refusal_phrasings = (
        "cannot support",
        "can not support",
        "cannot confidently",
        "cannot assign",
        "unable to support",
        "no confident answer",
    )

    instructing = [
        sentence
        for sentence in sentences
        if any(phrase in sentence for phrase in refusal_phrasings)
        and any(verb in sentence for verb in instruction_verbs)
    ]

    assert instructing, (
        "the prompt does not instruct the model to state its refusal in "
        "prose, so a reader of the Slack message or the product's record "
        "would have to infer the refusal from a field neither surface "
        f"renders. Prompt:\n{prompt}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - *A supported choice proposes satisfaction*. Reproduced verbatim from
#   the served requirement and covered by
#   `test_a_supported_choice_proposes_satisfaction` in
#   `test_subcategory_advisor_graph.py` (`tasks.md` 1.1). That test's stub
#   needs a verdict added to it (`tasks.md` 4.1a), which is the
#   implementer's task; this pass does not edit it.
# - That `_is_unsupported` and `_UNSUPPORTED_MARKERS` are gone rather than
#   relocated. `tasks.md` 5.4 discharges it by inspection, and asserting
#   the absence of a private symbol would assert the mechanism rather than
#   the requirement — the defect this whole change is about.
# - How the graph node parses a verdict out of the model's answer. No
#   artifact fixes an answer format, so a test of it would assert an
#   invented wire format. Covered indirectly: every test above reads the
#   verdict from state, and the state field's existence is asserted by
#   `test_the_verdict_is_reported_as_a_value_alongside_the_recommendation`.
# - Whether a proposed browse node is a real Amazon node, or the right
#   one. No deterministic test can establish it and the delta does not
#   claim it.
# ---------------------------------------------------------------------------
