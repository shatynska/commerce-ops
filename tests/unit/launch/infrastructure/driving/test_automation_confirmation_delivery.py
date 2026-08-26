"""What the Slack message offering a decision says, and what it offers.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirement *A pending result is delivered for a
decision, and delivery failure does not lose it*, its first scenario:

    #### Scenario: A pending result reaches Slack
    - **WHEN** a pending result is stored
    - **THEN** a Slack message is delivered naming the product, the step,
      the proposed outcome and the produced text in full, offering an
      accept and a reject decision

Its other two scenarios turn on a *pass* retrying a failed delivery and
are covered in
`tests/unit/launch/infrastructure/driving/test_automation_pass.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The message's content is decided by the delivery adapter and by nothing
else, so calling it over a captured Slack poster is the smallest unit
that can observe the scenario — and the only one that can observe "in
full", which is a property of the text as sent.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 6.1: the module
`launch/infrastructure/driving/automation_confirmation.py`; that it posts
to `PRODUCT_AGENT_MONITORING_CHANNEL_ID`; that it names the product, the
step, the proposed outcome and the produced text **in full**; and that it
carries accept and reject actions.

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The delivery function's name. `_delivery_callable()` probes the
  module's surface and fails loudly rather than defaulting.
- Its call shape. `_deliver` is the single correction point.
- The name of the module-level Slack poster it reaches through.
  `_install_poster` substitutes it with `monkeypatch.setattr` at its
  default `raising=True`, so a differently named collaborator fails
  loudly here rather than leaving a test green against an unpatched real
  one — the convention `tests/unit/launch/infrastructure/driving/
  test_clickup_webhook.py` records.

Deliberately **not** pinned: the message's layout, wording, or whether it
is plain text or Block Kit. Everything asserted below is read off a
flattened rendering of whatever was posted, so an implementation is free
to choose the shape; what it is not free to do is omit one of the four
facts the scenario names, or offer fewer than two decisions.

## Expected first-run state

`automation_confirmation.py` does not exist (`tasks.md` 6.1), so every
test here is expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing`, that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
"""

from __future__ import annotations

import inspect
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.launch.infrastructure.driving import automation_confirmation
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"
HANDLER_NAME: Final = "listing.subcategory_advisor"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

CHANNEL_ID: Final = "C0MONITORING"

# Long enough, and specific enough, that a truncating implementation
# loses the tail: "in full" is what the scenario asks for, and the tail
# is where a recommendation puts its rejected alternative.
RECOMMENDATION: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration; CPSIA general "
    "certificate of conformity where the board is marketed for children; "
    "a country-of-origin mark on the product itself.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative "
    "Trays, preferred by keyword volume but carrying no food-contact "
    "obligation, which would understate the compliance surface this "
    "product actually has."
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


@dataclass
class _PendingRow:
    product_id: ProductId = PRODUCT_ID
    step_id: str = STEP_ID
    handler: str = HANDLER_NAME
    proposed_outcome: Any = Satisfied
    result_text: str = RECOMMENDATION
    produced_at: datetime = PRODUCED_AT
    state: str = "pending"
    delivered_at: datetime | None = None


class _CapturingPoster:
    """Captures whatever the adapter posts, whole."""

    def __init__(self, *, failing: bool = False) -> None:
        self.posts: list[dict[str, Any]] = []
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.posts.append({"args": args, "kwargs": kwargs})
        if self.failing:
            raise RuntimeError("simulated Slack delivery failure")
        return {"ok": True, "ts": "1700000000.000100"}

    # Slack's own client spelling, in case the adapter calls a client
    # object rather than a bare function.
    async def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
        return await self(**kwargs)

    @property
    def rendered(self) -> str:
        """Everything posted, flattened to one searchable string.

        Deliberately shape-agnostic: plain text, Block Kit, attachments
        or any mix render the same here, so nothing below pins a layout.
        """
        return json.dumps(self.posts, default=str)


_POSTER_NAMES: Final = (
    "post_monitoring_message",
    "post_message",
    "post",
    "notifier",
    "slack_client",
    "get_slack_client",
)


def _install_poster(
    monkeypatch: pytest.MonkeyPatch, poster: _CapturingPoster
) -> _CapturingPoster:
    """Substitute the adapter's Slack poster, failing loudly if none of
    the probed names is the one it reaches through."""
    for name in _POSTER_NAMES:
        if hasattr(automation_confirmation, name):
            monkeypatch.setattr(automation_confirmation, name, poster)
            return poster
    pytest.fail(
        "the confirmation adapter exposes no substitutable Slack poster "
        f"under any of {_POSTER_NAMES} — correct this file's probe to the "
        "implemented collaborator, rather than letting these tests post "
        "against a real client"
    )


_DELIVERY_NAMES: Final = (
    "deliver_pending_result",
    "deliver",
    "post_pending_result",
    "request_confirmation",
)


def _delivery_callable() -> Any:
    for name in _DELIVERY_NAMES:
        found = getattr(automation_confirmation, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no delivery entry point found on "
        f"{automation_confirmation.__name__} under any of {_DELIVERY_NAMES} "
        "— correct this file's probe to the implemented name"
    )


async def _deliver(
    *, row: _PendingRow | None = None, product: _CatalogProduct | None = None
) -> Any:
    """INVENTED call shape — the single correction point."""
    entry = _delivery_callable()
    supplied: dict[str, Any] = {
        "result": row if row is not None else _PendingRow(),
        "product": product if product is not None else _CatalogProduct(),
        "step_name": STEP_NAME,
    }
    accepted = set(inspect.signature(entry).parameters)
    supplied = {key: value for key, value in supplied.items() if key in accepted}
    assert "result" in supplied or "pending" in accepted, (
        "the delivery entry point takes no pending result; correct "
        "`_deliver` to the implemented parameter names"
    )
    return await entry(**supplied)


# ---------------------------------------------------------------------------
# Requirement: A pending result is delivered for a decision
# ---------------------------------------------------------------------------


async def test_a_pending_result_reaches_slack(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A pending result reaches Slack.

    WHEN a pending result is stored
    THEN a Slack message is delivered naming the product, the step, the
    proposed outcome and the produced text in full, offering an accept
    and a reject decision.
    """
    monkeypatch.setenv("PRODUCT_AGENT_MONITORING_CHANNEL_ID", CHANNEL_ID)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    await _deliver()

    assert poster.posts, "no Slack message was delivered for the pending result"
    rendered = poster.rendered

    # SPECIFIED: it names the product.
    assert PRODUCT_NAME in rendered
    # SPECIFIED: it names the step.
    assert STEP_ID in rendered or STEP_NAME in rendered
    # SPECIFIED: it names the outcome the handler proposed.
    assert "Satisfied" in rendered
    # SPECIFIED: it carries the produced text **in full** — every line of
    # it, including the rejected alternative the tail carries.
    for line in RECOMMENDATION.splitlines():
        assert line.strip() in rendered.replace("\\n", "\n"), (
            f"the produced text was not delivered in full; missing: {line!r}"
        )
    # SPECIFIED: it offers an accept and a reject decision — two of them,
    # distinguishable from one another.
    lowered = rendered.lower()
    assert "accept" in lowered
    assert "reject" in lowered


async def test_the_message_goes_to_the_monitoring_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 6.1: posted to `PRODUCT_AGENT_MONITORING_CHANNEL_ID`.

    DERIVED with respect to the spec, which says only that the result is
    delivered to Slack; the channel is fixed by the artifacts and by the
    proposal's commitment to no new configuration (the briefing notifier
    already reads this pair). Recorded as derived in `test-manifest.md`.
    """
    monkeypatch.setenv("PRODUCT_AGENT_MONITORING_CHANNEL_ID", CHANNEL_ID)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    await _deliver()

    assert CHANNEL_ID in poster.rendered, (
        "the confirmation request was posted somewhere other than the "
        "monitoring channel the change commits to reusing"
    )


async def test_a_delivery_failure_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "A failure to deliver SHALL NOT discard the
    pending result and SHALL NOT record an outcome. The failure SHALL be
    reported, and the pending result SHALL remain available to be
    delivered again".

    The adapter's own share of that: a failed post must be visible to
    whoever called it, since it is the pass that must leave the result
    undelivered and report. An adapter swallowing the failure would let
    the pass stamp `delivered_at` on a message nobody received — the
    silent loss the requirement's decoupling exists to prevent. The
    pass-side half is asserted in
    `tests/unit/launch/infrastructure/driving/test_automation_pass.py`.
    """
    monkeypatch.setenv("PRODUCT_AGENT_MONITORING_CHANNEL_ID", CHANNEL_ID)
    _install_poster(monkeypatch, _CapturingPoster(failing=True))

    with pytest.raises(Exception):  # noqa: B017 -- any failure, not a chosen type
        await _deliver()


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The message's layout, ordering and wording beyond the four facts the
#   scenario names. The same reading `tests/unit/briefing/application/
#   test_briefing_delivery.py` records: asserting a phrasing would impose
#   a contract nobody agreed to.
# - That the accept and reject controls carry action identifiers the
#   listener then matches on. That pairing is internal to the adapter and
#   no scenario states it; what a decision does once it arrives is
#   covered in `tests/unit/launch/application/
#   test_automated_result_decisions.py`.
# ---------------------------------------------------------------------------
