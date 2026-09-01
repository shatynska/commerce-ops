"""The pending-result ask's own fallback policy, and the form it names
identifiers in.

Derived strictly from the MODIFIED requirement *A pending result is
delivered for a decision, and delivery failure does not lose it* in
`openspec/changes/fix-launch-thread-mentions/specs/launch-step-automation/spec.md`.

Covers the ask's half of:

- *A tagged confirmer is mentioned by their Slack identity*
- *A confirmer the roster does not carry is not mentioned, and the gap is
  reported*
- *A deactivated confirmer is not mentioned, and the gap is reported*
- *A pending result is delivered untagged when the roster cannot be read*
- *An identifier in the message or its controls appears as its value*

## Why this file exists beside the resolver's own tests

The delta puts **two different fallback policies** on one resolution step,
and states each with its own reason:

    Where the named confirmer is not resolvable for tagging, the pending
    result SHALL still be delivered, carrying no mention […]. The launch's
    submitter SHALL NOT be tagged in the confirmer's place.

The stuck-step report does the opposite, and is covered from its own
requirement in `test_stuck_step_report_submitter_fallback.py` — never by
copying from here. A test asserting only that both callers reach the
shared resolver would pass whichever policy each one applied, which is the
shape of assertion the change's `proposal.md` identifies as how the defect
survived review.

So every test below is stated over what **this** message carries, and the
central one asserts an *absence*: no mention token at all, and specifically
not the submitter's.

## Level

Unit tests of `deliver_pending_result` over a captured Slack poster, with
the thread-and-mention preamble substituted at the module-level seam every
driving adapter shares (`establish_thread_and_resolve_mention`). That seam
returns `(thread_ts, mention)`, so "the confirmer is not resolvable" is
expressed here as the seam answering `None` for the mention while the step
still names a confirmer — which is exactly the condition `design.md` says
each caller derives its policy from ("`step.confirmer` is set and the
answer is `None`").

Resolution's own correctness is
`tests/unit/launch/application/test_mention_resolution_namespace.py`'s
concern and is not re-asserted here.

## The stub carries what a stored row carries

`_StoredRow.product_id` is a `uuid.UUID`, because
`AutomatedStepResult.product_id` is `Mapped[uuid.UUID]` and `undelivered()`
hands back ORM rows. The existing stubs in
`test_automation_confirmation_to_thread_reply.py` and
`test_automation_confirmation_delivery.py` declare `product_id: ProductId`
instead, which is the one form that satisfied a check the real store never
satisfies — `proposal.md`'s defect 4. Those files are not edited by this
pass; they are recorded in `test-manifest.md` as obsolete.

The `ProductId` the delivery needs now arrives as its own parameter, from
the caller that already builds one (`tasks.md` 2.1–2.3), which is why the
row's form and the parameter's form can differ here without either being
wrong.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: the `product_id: ProductId` keyword
parameter (`tasks.md` 2.1), the button payload composed from
`product_id.value` (2.2), the anchor fallback read as `.value` (2.4), the
untagged ask with no submitter substitution (3.8).

INVENTED, recorded in `test-manifest.md`:

- `deliver_pending_result`'s remaining call shape (`result`, `product`,
  `step_name`, `step`), read off the existing tests in this directory
  rather than off `src/`. Correction point: `_deliver`.
- The mention syntax `<@…>`, and that "carrying no mention" means the
  message contains no `<@` token at all.
- The `product_id` parameter's spelling. Probed against the real
  signature, so a different spelling fails loudly rather than silently
  falling through to a default.

## Expected first-run state

Every test is expected to FAIL, as failure state 2 (absent target):
`deliver_pending_result` accepts no `product_id` parameter today, so
`_deliver`'s signature probe fails before any assertion runs.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = (
    "commerce_ops.launch.infrastructure.driving.automation_confirmation"
)

#: The stored identifier, in both the forms the seam has to agree about:
#: the `uuid.UUID` an ORM row carries, and the `ProductId` the caller
#: builds from it (`ProductId(str(row.product_id))`).
STORED_UUID: Final = uuid.UUID("018f3a5c-9d21-7b4e-9a11-0f2c6d8e4a37")
PRODUCT_ID: Final = ProductId(str(STORED_UUID))

PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"
HANDLER_NAME: Final = "listing.subcategory_advisor"

#: A roster identifier, as a step's `confirmer` field actually holds one.
#: Deliberately not Slack-shaped, so a message carrying it is visibly wrong.
CONFIRMER_ROSTER_ID: Final = "3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30"
CONFIRMER_SLACK: Final = "U01ALICE"
SUBMITTER_SLACK: Final = "U0SUBMITTER"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SLACK_THREAD_TS: Final = "1700000000.000100"

RECOMMENDATION: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Cutting Boards."
)

_PRODUCT_ID_PARAMETER_NAMES: Final = ("product_id",)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:  # pragma: no cover -- absent-target guard
        pytest.fail(f"{MODULE_PATH} does not exist ({error})")


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


@dataclass(frozen=True)
class _Step:
    identifier: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_ROSTER_ID


@dataclass
class _StoredRow:
    """A pending result in the form the store hands it back: the
    identifier as the database spells it, a `uuid.UUID`."""

    product_id: uuid.UUID = STORED_UUID
    step_id: str = STEP_ID
    handler: str = HANDLER_NAME
    proposed_outcome: Any = Satisfied
    result_text: str = RECOMMENDATION
    produced_at: datetime = PRODUCED_AT
    state: str = "pending"
    delivered_at: datetime | None = None


class _CapturingPoster:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    @property
    def rendered(self) -> str:
        """Everything posted, whole — text and blocks alike. The mention
        and the identifier can each land in either, and asserting only on
        `text` would let a wrong value hide in a block."""
        return json.dumps(self.calls, default=str)

    @property
    def text(self) -> str:
        return "\n".join(str(call.get("text") or "") for call in self.calls)


@dataclass
class _ThreadSeam:
    """Substitutes `establish_thread_and_resolve_mention`.

    Answers whatever mention the test asked for, rather than deriving one
    from the step: deriving it would re-implement `resolve_mention_target`
    here and make every test below pass or fail on this file's copy of the
    rule instead of on the adapter's policy.
    """

    mention: str | None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[str, str | None]:
        self.calls.append(kwargs)
        return SLACK_THREAD_TS, self.mention


def _install(
    monkeypatch: pytest.MonkeyPatch, *, mention: str | None
) -> tuple[_ThreadSeam, _CapturingPoster]:
    module = _module()
    # `launches_channel()` still runs to build the `channel=` argument even
    # though the poster is a double, and it reads this variable by its
    # literal name. Setup only -- no assertion in this file touches the
    # channel -- and the same line every sibling test in this directory
    # carries. Added when the file was first run against the implementation;
    # the derivation pass had no way to observe the requirement.
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")
    seam = _ThreadSeam(mention=mention)
    poster = _CapturingPoster()
    for name, double in (
        ("establish_thread_and_resolve_mention", seam),
        ("post_monitoring_message", poster),
    ):
        if not hasattr(module, name):
            pytest.fail(
                f"{MODULE_PATH} exposes no substitutable `{name}` — correct "
                "this file's probe to the implemented collaborator"
            )
        monkeypatch.setattr(module, name, double)
    return seam, poster


async def _deliver(
    *,
    result: Any = None,
    product: Any = None,
    step: Any = None,
    product_id: ProductId = PRODUCT_ID,
) -> None:
    """INVENTED call shape — the single correction point.

    `product_id` is passed as its own keyword because that is what
    `tasks.md` 2.1 makes it: the seam names the form once, on the caller's
    side. Probed against the real signature so a different spelling — or a
    delivery that still digs the identifier out of `result` — fails by
    name rather than by a confusing downstream assertion.
    """
    entry = getattr(_module(), "deliver_pending_result", None)
    if not callable(entry):
        pytest.fail(f"{MODULE_PATH} has no `deliver_pending_result`")

    parameters = inspect.signature(entry).parameters
    for name in _PRODUCT_ID_PARAMETER_NAMES:
        if name in parameters:
            break
    else:
        pytest.fail(
            "`deliver_pending_result` accepts no product identifier under any "
            f"of {_PRODUCT_ID_PARAMETER_NAMES}; its parameters are "
            f"{tuple(parameters)}. `tasks.md` 2.1 requires it to take the "
            "identifier as a typed parameter instead of digging one out of "
            "the row and rejecting what it finds"
        )

    await entry(
        result=result if result is not None else _StoredRow(),
        product=product,
        step_name=STEP_NAME,
        step=step if step is not None else _Step(),
        **{name: product_id},
    )


# ---------------------------------------------------------------------------
# Scenario: A tagged confirmer is mentioned by their Slack identity
# ---------------------------------------------------------------------------


async def test_the_ask_mentions_the_slack_identity_and_never_the_roster_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A tagged confirmer is mentioned by their Slack identity.

    WHEN a pending result is delivered for a step naming a confirmer the
    roster carries, active and with a Slack identity
    THEN the message mentions that person by their Slack identity, and the
    roster's own identifier for them appears nowhere in it.

    SPECIFIED, both halves. The negative half is the one the shipped tests
    could not state: they passed a Slack-looking constant as the step's
    `confirmer` and asserted it appeared, which a mention nobody receives
    satisfies. Here the two strings differ, and the roster identifier is
    asserted absent from the *whole* payload — blocks included, since a
    control could carry it just as easily as the text.
    """
    _, poster = _install(monkeypatch, mention=CONFIRMER_SLACK)

    await _deliver(product=_CatalogProduct())

    assert poster.calls, "no Slack message was delivered for the pending result"
    # SPECIFIED: mentioned by their Slack identity.
    assert f"<@{CONFIRMER_SLACK}>" in poster.rendered, (
        f"the ask did not mention the confirmer's Slack identity: {poster.rendered!r}"
    )
    # SPECIFIED: the roster's own identifier appears nowhere in it.
    assert CONFIRMER_ROSTER_ID not in poster.rendered, (
        "the roster's own identifier for the confirmer reached the message; "
        "Slack leaves it as inert literal text and notifies nobody: "
        f"{poster.rendered!r}"
    )


async def test_the_ask_threads_the_step_through_to_mention_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: the system "SHALL resolve the step's
    confirmer through the roster to that person's Slack identity".

    SPECIFIED, in the half this adapter owns: it must hand the real step to
    resolution, since a resolution given no step cannot reach the confirmer
    branch at all. Kept as its own test because the assertion above would
    still pass if the adapter invented the mention itself.
    """
    seam, _ = _install(monkeypatch, mention=CONFIRMER_SLACK)
    step = _Step()

    await _deliver(product=_CatalogProduct(), step=step)

    assert seam.calls and seam.calls[0].get("step") is step, (
        f"the ask did not thread its own step through to resolution: {seam.calls!r}"
    )


# ---------------------------------------------------------------------------
# Scenarios: A confirmer the roster does not carry / a deactivated confirmer
# / the roster cannot be read — all three, at this caller, are one policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "why",
    [
        pytest.param("not carried by the roster", id="unknown-confirmer"),
        pytest.param("deactivated on the roster", id="deactivated-confirmer"),
        pytest.param("the roster could not be read", id="unreadable-roster"),
    ],
)
async def test_an_unresolvable_confirmer_leaves_the_ask_carrying_no_mention_at_all(
    why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenarios: *A confirmer the roster does not carry is not mentioned*,
    *A deactivated confirmer is not mentioned*, and *A pending result is
    delivered untagged when the roster cannot be read*.

    THEN the message is still delivered […] carrying no mention and not
    tagging the submitter.

    SPECIFIED. The three scenarios differ in *why* the confirmer did not
    resolve — a distinction the resolver owns and
    `test_mention_resolution_namespace.py` asserts — and are identical in
    what this caller must then do, which is what the parametrisation says:
    at this seam all three arrive as "the step names a confirmer and the
    mention is `None`", and no other information is available to tell them
    apart. Collapsing them into one test would hide that; three ids and
    one body states it.

    Asserted as an absence of **any** mention token, not merely of the
    submitter's. "Carrying no mention" is the requirement's wording, and a
    message tagging some third party would satisfy a narrower check.
    """
    _, poster = _install(monkeypatch, mention=None)

    await _deliver(product=_CatalogProduct(), step=_Step(confirmer=CONFIRMER_ROSTER_ID))

    # SPECIFIED: the pending result SHALL still be delivered.
    assert poster.calls, (
        f"the ask was not delivered at all when the confirmer was {why}; the "
        "delta requires the result to be delivered regardless"
    )
    # SPECIFIED: carrying no mention.
    assert "<@" not in poster.rendered, (
        f"the ask carried a mention when the confirmer was {why}: {poster.rendered!r}"
    )
    # SPECIFIED, and stated separately because it is the clause with the
    # reason attached: only the named confirmer may decide a pending
    # result, so tagging anyone else summons a person whose accept and
    # reject are certain to be refused.
    assert f"<@{SUBMITTER_SLACK}>" not in poster.rendered, (
        "the ask fell back to tagging the launch's submitter; their decision "
        "on it would be refused, and it makes 'this step names no confirmer' "
        "read identically to 'this confirmer cannot be reached'"
    )
    # SPECIFIED: and the roster identifier is not what got carried instead.
    assert CONFIRMER_ROSTER_ID not in poster.rendered


async def test_an_untagged_ask_still_names_the_product_the_step_and_the_produced_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: *A confirmer the roster does not carry is not mentioned* —
    its "the message is still delivered naming the product, the step and
    the produced text" clause.

    SPECIFIED, and the assertion that stops the test above from being
    satisfied by an empty message. An ask that carries no mention because
    it carries nothing would pass every absence check in this file.
    """
    _, poster = _install(monkeypatch, mention=None)

    await _deliver(product=_CatalogProduct())

    assert poster.calls
    rendered = poster.rendered
    assert PRODUCT_NAME in rendered, (
        f"the untagged ask did not name the product: {rendered!r}"
    )
    assert STEP_NAME in rendered, (
        f"the untagged ask did not name the step: {rendered!r}"
    )
    assert RECOMMENDATION in rendered, (
        f"the untagged ask did not carry the produced text: {rendered!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: An identifier in the message or its controls appears as its
# value
# ---------------------------------------------------------------------------


async def test_the_product_identifier_fallback_appears_as_its_own_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An identifier in the message or its controls appears as
    its value.

    WHEN a delivered pending result names the product by an identifier
    THEN the identifier appears as its own value, not as a rendering of
    the object carrying it.

    SPECIFIED. The catalog read returning nothing is what reaches the
    fallback — `product=None` here — and `shared-vocabulary` forbids the
    object's rendering being what lands. This one is not cosmetic: where
    this ask is a launch's first per-product message, the value it carries
    becomes the thread anchor's permanent heading, which
    `launch-instance`:513 forbids re-creating to correct.
    """
    _, poster = _install(monkeypatch, mention=CONFIRMER_SLACK)

    await _deliver(product=None)

    assert poster.calls
    rendered = poster.rendered
    # SPECIFIED: the identifier appears as its own value.
    assert PRODUCT_ID.value in rendered, (
        f"the ask did not name the product by its identifier's value: {rendered!r}"
    )
    # SPECIFIED: not as a rendering of the object carrying it.
    assert "ProductId" not in rendered, (
        f"the ask rendered the identifier's object rather than its value: {rendered!r}"
    )
    assert "value=" not in rendered


async def test_the_decision_controls_carry_the_identifier_the_result_was_stored_against(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: *An identifier in the message or its controls appears as
    its value*, and the requirement statement's "The accept and reject
    decisions SHALL name the launch and the step the pending result was
    stored against".

    SPECIFIED. This is the unit-tier half of the round trip: the controls
    carry the stored identifier's value and the stored step, in a form a
    decision can parse. Whether a decision on them actually *resolves* the
    stored row cannot be seen from a hand-built result — supplying the
    convenient form is exactly the mistake — so that half is pinned in the
    integration tier, in
    `tests/integration/launch/test_pending_result_delivery_seam_live.py`.

    The row here carries a `uuid.UUID` and the parameter a `ProductId`;
    both spell the same value, so an implementation reading either gets
    the same string. What it must not do is render the object.
    """
    _, poster = _install(monkeypatch, mention=CONFIRMER_SLACK)

    await _deliver(product=_CatalogProduct())

    assert poster.calls
    rendered = poster.rendered
    assert PRODUCT_ID.value in rendered, (
        "the controls do not carry the product identifier the result was "
        f"stored against: {rendered!r}"
    )
    assert STEP_ID in rendered, (
        f"the controls do not carry the step the result was stored against: "
        f"{rendered!r}"
    )
    assert "ProductId" not in rendered, (
        "a control payload carries a rendering of the identifier's object; a "
        "payload is parsed rather than read, so this is unresolvable rather "
        f"than merely ugly: {rendered!r}"
    )


# ---------------------------------------------------------------------------
# Requirement statement: delivery works from the form the store hands back
# ---------------------------------------------------------------------------


async def test_delivery_is_not_refused_because_of_the_form_the_stored_row_carries(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Requirement statement: "Delivery SHALL work from a pending result in
    the form the store hands it back. A delivery path that requires an
    identifier in a form the store does not produce delivers nothing at
    all, while satisfying any test that supplies the form it wants."

    SPECIFIED. The scenario this sentence carries — *A stored pending
    result is delivered in the form it was stored* — is accounted for in
    the integration tier, against a row genuinely read back through
    `undelivered()`, because a unit stub cannot establish it: the stub *is*
    the thing under suspicion.

    What this test adds is narrower and still worth having: a row whose
    `product_id` is a `uuid.UUID` — the form `Mapped[uuid.UUID]` produces —
    is delivered rather than refused. It is the same assertion the
    integration test makes, run against the form rather than against the
    store, so a regression is visible at commit time rather than only at
    push time.
    """
    _, poster = _install(monkeypatch, mention=CONFIRMER_SLACK)
    row = _StoredRow()
    assert isinstance(row.product_id, uuid.UUID), (
        "precondition: this row must carry the identifier in the form a "
        "stored row carries it, or the test establishes nothing"
    )

    with caplog.at_level(logging.WARNING):
        await _deliver(result=row, product=_CatalogProduct())

    assert poster.calls, (
        "a pending result carrying its identifier in the form the store "
        "produces was not delivered"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED here, recorded rather than omitted
#
# - *A pending result reaches Slack*, *Undelivered is not undone*, *An
#   undelivered result is delivered again later* and *A pending result for
#   a launch with no thread yet establishes one*. Unchanged in substance by
#   this delta and covered by `test_automation_confirmation_delivery.py`,
#   `test_automation_confirmation_to_thread_reply.py` and
#   `test_automation_pass.py`. Re-asserting them here would duplicate
#   coverage while adding nothing this delta introduces.
# - Where the unresolvable confirmer is *reported*. The delta requires it,
#   and `design.md` places the report in `resolve_mention_target`, which is
#   the only party that knows which of the three failure points was
#   reached. Asserted there, in
#   `tests/unit/launch/application/test_mention_resolution_namespace.py`,
#   and not duplicated at a caller that cannot tell them apart.
# ---------------------------------------------------------------------------
