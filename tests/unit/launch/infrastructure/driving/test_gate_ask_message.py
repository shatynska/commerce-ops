"""What the Slack message asking for a gate's approval says, and offers.

Originally derived from the OpenSpec change `advance-gates-and-confirm-in-slack`.
The delivery half of the requirement it covered was since MODIFIED by
`thread-launch-slack-notifications`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`
— the ask now goes to `launches_channel()` as a reply within the launch's
thread (establishing it first if needed) and tags the launch's submitter,
superseding this file's earlier "posted to `monitoring_channel` as a
top-level message" assertions per that change's own `test-manifest.md`
("launch-gate-progression obsolete tests"). This file is that update, not a
rewrite from scratch: the message-content assertions (product, gate, two
controls, the button value) are unchanged, only delivery is.

Covers the message half of the requirement's main scenario:

    #### Scenario: A satisfied confirmation gate is asked about
    - **WHEN** the pass runs against a launch whose current gate requires
      confirmation, has every blocking condition satisfied, and has no
      approving approval recorded
    - **THEN** a message naming the product and the gate, tagging the
      launch's submitter, is posted as a reply within the launch's Slack
      thread, carrying the decision controls

and, from `launch-instance`'s ADDED requirement, the entry point's share of
establishing that thread on first use (the operation itself is covered
directly in `tests/unit/launch/application/test_thread_establishment_race.py`;
this file only checks that `post_gate_ask` reaches it and uses what it
returns).

*When* an ask is owed, and when it is withheld, is the pass's and is in
`tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`.
The requirement's remaining clause about a failed delivery is stated over
the pass and is there too; its adapter half — that a failed post reaches
the caller rather than being swallowed — is asserted here, because a pass
cannot leave a delivery unrecorded if the adapter never tells it the post
failed.

See `test-manifest.md` at the change root for the full accounting.

## Level

The ask adapter over a captured Slack poster, with thread establishment
substituted at the module-level seam `launch_thread_delivery.py` gives
every driving adapter (`establish_thread_and_resolve_mention`, imported at
module scope in `gate_confirmation.py` for exactly this reason). The
message's content is decided here and nowhere else, so this is the
smallest unit that can observe it — and the only one that can observe what
was actually sent.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the message carries the product,
the gate, an approve control and a reject control; that the button value
carries `{product_id, gate_id}` (`design.md` — Decision 9, from
`advance-gates-and-confirm-in-slack`); that delivery is a thread reply in
`launches_channel()`, tagging the submitter (`thread-launch-slack-notifications`).

INVENTED, each recorded in `test-manifest.md` with its correction point:

- The ask function's name (`_ask_callable`) and its call shape
  (`_post_ask`), which probes the implemented signature and supplies only
  what it accepts.
- The name of the module-level Slack poster it reaches through
  (`_install_poster`), substituted at `monkeypatch.setattr`'s default
  `raising=True` so a differently named collaborator fails loudly here
  rather than leaving a test green against an unpatched real client — the
  convention `test_clickup_webhook.py` records.
- The name of the module-level thread-establishment collaborator
  (`_install_thread_establishment`), same convention.

Deliberately **not** pinned: the message's layout, wording, or whether it
is plain text or Block Kit. Everything is read off a flattened rendering
of whatever was posted, so an implementation is free to choose the shape;
what it is not free to do is omit the product, omit the gate, or offer
fewer than two decisions.
"""

from __future__ import annotations

import importlib
import inspect
import json
import uuid
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Final

import pytest

from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_confirmation"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

GATE_ID: Final = "commit"

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SUBMITTER_ID: Final = "U0SUBMITTER"
SLACK_THREAD_TS: Final = "1700000000.000100"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _module() -> ModuleType:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` 5.1 creates "
            "it. This is the absent-target state, not a defect in this file."
        )


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


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

    async def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
        return await self(**kwargs)

    @property
    def rendered(self) -> str:
        """Everything posted, flattened to one searchable string.

        Shape-agnostic on purpose: plain text, Block Kit, attachments or
        any mix render the same here, so nothing below pins a layout.
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
    module = _module()
    for name in _POSTER_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, poster)
            return poster
    pytest.fail(
        "the gate ask adapter exposes no substitutable Slack poster under "
        f"any of {_POSTER_NAMES} — correct this file's probe to the "
        "implemented collaborator, rather than letting these tests post "
        "against a real client"
    )


_THREAD_NAMES: Final = ("establish_thread_and_resolve_mention",)


def _install_thread_establishment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mention: str | None = SUBMITTER_ID,
    thread_ts: str = SLACK_THREAD_TS,
) -> None:
    """Substitute the thread-and-mention preamble with a canned result.

    This file's own concern is what `post_gate_ask` composes and posts
    once it has a thread reference and a mention -- not thread
    establishment itself, which `test_thread_establishment_race.py` covers
    directly against the real operation.
    """
    module = _module()
    for name in _THREAD_NAMES:
        if hasattr(module, name):

            async def _fake(*args: Any, **kwargs: Any) -> tuple[str, str | None]:
                return thread_ts, mention

            monkeypatch.setattr(module, name, _fake)
            return
    pytest.fail(
        "the gate ask adapter exposes no substitutable thread-establishment "
        f"collaborator under any of {_THREAD_NAMES} — correct this file's "
        "probe to the implemented collaborator"
    )


_ASK_NAMES: Final = (
    "post_gate_ask",
    "deliver_gate_ask",
    "ask_for_confirmation",
    "request_confirmation",
    "post_ask",
    "deliver",
)


def _ask_callable() -> Any:
    module = _module()
    for name in _ASK_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no ask entry point found on {module.__name__} under any of "
        f"{_ASK_NAMES} — correct this file's probe to the implemented name"
    )


async def _post_ask() -> tuple[Any, set[str]]:
    """INVENTED call shape — the single correction point.

    Returns what the ask returned together with the names it accepted, so
    the assertions can hold the adapter to naming whichever form of the
    product it was actually handed.
    """
    entry = _ask_callable()
    pool: dict[str, Any] = {
        "product": _CatalogProduct(),
        "product_id": PRODUCT_ID,
        "gate_id": GATE_ID,
        "gate": GATE_ID,
    }
    accepted = set(inspect.signature(entry).parameters)
    supplied = {key: value for key, value in pool.items() if key in accepted}
    assert accepted & {"gate_id", "gate"}, (
        "the ask entry point names no gate among its parameters "
        f"({sorted(accepted)}); the message must name the gate, so correct "
        "`_post_ask` to the implemented parameter names"
    )
    assert accepted & {"product", "product_id"}, (
        "the ask entry point names no product among its parameters "
        f"({sorted(accepted)}); correct `_post_ask`"
    )
    return await entry(**supplied), set(supplied)


# ---------------------------------------------------------------------------
# Requirement: A gate awaiting only confirmation is asked about in Slack
# ---------------------------------------------------------------------------


async def test_the_ask_names_the_product_and_the_gate_and_carries_the_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A satisfied confirmation gate is asked about — its message
    half.

    THEN a message naming the product and the gate is posted, carrying the
    decision controls.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    _, supplied = await _post_ask()

    assert poster.posts, "no Slack message was delivered for the gate ask"
    rendered = poster.rendered

    # SPECIFIED: it names the product — in whichever form the adapter was
    # handed one, so this holds whether it takes a catalog product or a
    # bare identifier.
    expected_product = PRODUCT_NAME if "product" in supplied else PRODUCT_ID.value
    assert expected_product in rendered, (
        f"the ask did not name the product ({expected_product!r}): {rendered!r}"
    )
    # SPECIFIED: it names the gate.
    assert GATE_ID in rendered, (
        f"the ask did not name the gate ({GATE_ID!r}): {rendered!r}"
    )
    # SPECIFIED: it carries the decision controls — two of them,
    # distinguishable from one another, which is what makes a *decision*
    # possible rather than an acknowledgement.
    lowered = rendered.lower()
    assert "approve" in lowered or "accept" in lowered, (
        f"the ask offers no approving control: {rendered!r}"
    )
    assert "reject" in lowered or "decline" in lowered, (
        f"the ask offers no rejecting control: {rendered!r}"
    )


async def test_the_ask_carries_the_product_and_gate_in_its_control_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 5.1 and `design.md` — Decision 9: "the button value
    carrying `{product_id, gate_id}`" — the pair rather than a row id,
    "because a control that named a row would keep working after that row
    was settled".

    DERIVED with respect to the delta, which states what the message names
    but not what its controls carry. Recorded as derived in
    `test-manifest.md`. It matters because the decision intake refuses a
    gate that is not the launch's current one (delta R7), and it can only
    do that if the press says which gate it was for.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    await _post_ask()

    rendered = poster.rendered
    assert PRODUCT_ID.value in rendered, (
        "the ask's controls do not carry the product identifier, so a press "
        f"cannot say which launch it decided: {rendered!r}"
    )
    assert GATE_ID in rendered, (
        "the ask's controls do not carry the gate identifier, so a press "
        f"cannot be refused for naming a gate the launch has left: {rendered!r}"
    )


async def test_the_ask_goes_to_the_launches_channel_as_a_thread_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`thread-launch-slack-notifications`, `launch-gate-progression`
    MODIFIED: "posted as a reply within that launch's Slack thread ...
    established first if it does not yet exist" — supersedes this file's
    earlier `monitoring_channel` assertion per that change's
    `test-manifest.md` ("launch-gate-progression obsolete tests").
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    await _post_ask()

    assert LAUNCHES_CHANNEL_ID in poster.rendered, (
        "the gate ask was not posted to the launches channel this change "
        f"moved per-launch messages to: {poster.rendered!r}"
    )
    assert SLACK_THREAD_TS in poster.rendered, (
        "the gate ask did not carry the established thread's reference, so "
        f"it was not posted as a reply within it: {poster.rendered!r}"
    )


async def test_the_ask_tags_the_launchs_submitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`thread-launch-slack-notifications`, `launch-gate-progression`
    MODIFIED: "SHALL tag the launch's submitter: a gate carries no
    confirmer of its own." `post_gate_ask` resolves the mention with no
    step (`test_the_ask_calls_the_mention_resolver_with_no_step` covers
    that it asks for the submitter fallback specifically); this asserts
    what the message does with whatever the resolver returns.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch, mention=SUBMITTER_ID)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    await _post_ask()

    assert f"<@{SUBMITTER_ID}>" in poster.rendered, (
        f"the gate ask did not tag the launch's submitter: {poster.rendered!r}"
    )


async def test_the_ask_calls_the_mention_resolver_with_no_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "a gate carries no confirmer of its own" — `design.md`'s shared
    mention-resolution function falls back to the launch's submitter
    exactly when it is asked about no step at all. `post_gate_ask` must
    call it that way rather than with some invented stand-in step, or a
    gate could end up tagging a stray confirmer no gate has.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_poster(monkeypatch, _CapturingPoster())
    module = _module()
    calls: list[dict[str, Any]] = []

    async def _recording_establish(*args: Any, **kwargs: Any) -> tuple[str, str | None]:
        calls.append(kwargs)
        return SLACK_THREAD_TS, SUBMITTER_ID

    for name in _THREAD_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, _recording_establish)
            break
    else:
        pytest.fail(f"no thread-establishment collaborator under {_THREAD_NAMES}")

    await _post_ask()

    assert calls, "post_gate_ask never reached the thread-establishment collaborator"
    assert calls[0].get("step") is None, (
        "post_gate_ask passed a step to mention resolution; a gate has no "
        f"confirmer of its own and must resolve with no step: {calls[0]!r}"
    )


async def test_a_delivery_failure_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement, R4: "A delivery that fails SHALL be reported
    and SHALL leave the gate eligible to be asked about again, SHALL NOT be
    recorded as though the ask had been delivered".

    The adapter's own share of that: a failed post must be visible to
    whoever called it. An adapter swallowing the failure would let the pass
    write a cool-off record for a message nobody received, silencing the
    gate for a day with nobody having been asked — the loss `design.md` —
    Decision 5 writes the record after delivery to prevent. The pass-side
    half is asserted in `test_gate_progression_pass.py`.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    _install_poster(monkeypatch, _CapturingPoster(failing=True))

    with pytest.raises(Exception):  # noqa: B017 -- any failure, not a chosen type
        await _post_ask()


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The message's layout, ordering and wording beyond the facts the
#   scenario names. The reading `test_automation_confirmation_delivery.py`
#   and `test_briefing_delivery.py` both record: asserting a phrasing
#   would impose a contract nobody agreed to.
# - The action identifiers the two controls carry. That pairing is
#   internal to the adapter; what a press then does is covered in
#   `tests/unit/launch/application/test_gate_decision.py` and
#   `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`.
# - Whether the gate is named by its identifier or by a human label. No
#   requirement states a vocabulary for it, and the identifier is what the
#   controls must carry in any case.
# ---------------------------------------------------------------------------
