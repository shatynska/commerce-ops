"""Pending result delivery moves to thread reply with confirmer tagging.

Derived strictly from the MODIFIED requirement in `launch-step-automation`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

Covers:
- Scenario: A pending result reaches Slack (now as thread reply with confirmer tag)
- Scenario: A pending result for a launch with no thread yet establishes one
- Confirmer tagging (derived): the message tags the step's named confirmer

The modified behavior: pending results are delivered as replies within the
launch's thread in the launches channel, establishing that thread first if
needed. They tag the step's named confirmer (or the submitter if the step
names no confirmer).

## Level

Unit tests of the automation confirmation adapter over a captured Slack poster.
The adapter decides what channel and thread to post to, and who to tag.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Pending results are posted to launches channel as thread replies (not monitoring)
- The message tags the step's named confirmer
- The adapter establishes the thread if needed before posting the result

INVENTED, recorded in `test-manifest.md`:
- The thread-ts parameter and how it is passed to the Slack API
- The mention format for the confirmer (e.g., <@USERID> or other)
- How the adapter receives the confirmer information (from step field)
- The call signature of the delivery adapter (probed dynamically)

## Level, and how thread establishment is substituted

Unit tests of the automation confirmation adapter over a captured Slack
poster, with the thread-and-mention preamble substituted at the
module-level seam every driving adapter shares
(`establish_thread_and_resolve_mention`, `launch_thread_delivery.py`,
imported at module scope in `automation_confirmation.py` for exactly this
reason). Thread establishment's own behavior — first caller posts the
anchor, a concurrent race produces exactly one, reuse skips it — is
covered directly against the real operation in
`tests/unit/launch/application/test_thread_establishment_race.py`; this
file only checks that `deliver_pending_result` reaches that collaborator,
threads `step` through it correctly, and uses what it returns.
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = (
    "commerce_ops.launch.infrastructure.driving.automation_confirmation"
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"
HANDLER_NAME: Final = "listing.subcategory_advisor"

CONFIRMER_ID: Final = "U0CONFIRMER"
SUBMITTER_ID: Final = "U0SUBMITTER"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SLACK_THREAD_TS: Final = "1700000000.000100"

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


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` creates it. "
            "This is the absent-target state per ai-toolkit:testing."
        )


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


@dataclass
class _StepWithConfirmer:
    id: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_ID


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
    """Captures Slack API calls made by the confirmation adapter.

    `deliver_pending_result` reaches `post_monitoring_message` (imported at
    module scope, called with keyword arguments — `channel`, `text`,
    `blocks`, `thread_ts`), so this is substituted in place of that
    function directly, and each call's kwargs recorded as-is.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    @property
    def rendered(self) -> str:
        return json.dumps(self.calls, default=str)


_POSTER_NAMES: Final = ("post_monitoring_message",)


def _install_poster(
    monkeypatch: pytest.MonkeyPatch, poster: _CapturingPoster
) -> _CapturingPoster:
    module = _module()
    for name in _POSTER_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, poster)
            return poster
    pytest.fail(
        "the automation confirmation adapter exposes no substitutable "
        f"Slack poster under any of {_POSTER_NAMES} — correct this file's "
        "probe to the implemented collaborator"
    )


_THREAD_NAMES: Final = ("establish_thread_and_resolve_mention",)


def _install_thread_establishment(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    """Substitute the thread-and-mention preamble, recording each call's
    arguments so a test can confirm `step` was threaded through correctly.

    Returns a mention derived from `step.confirmer` when the caller passed
    a step naming one, mirroring `resolve_mention_target`'s own rule —
    that rule's correctness is `test_thread_establishment_race.py`'s
    concern; this file only checks that the adapter asks for it right.
    """
    module = _module()
    calls: list[dict[str, Any]] = []

    async def _fake(*args: Any, **kwargs: Any) -> tuple[str, str | None]:
        calls.append(kwargs)
        step = kwargs.get("step")
        mention = getattr(step, "confirmer", None) or SUBMITTER_ID
        return SLACK_THREAD_TS, mention

    for name in _THREAD_NAMES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, _fake)
            return calls
    pytest.fail(
        "the automation confirmation adapter exposes no substitutable "
        f"thread-establishment collaborator under any of {_THREAD_NAMES} — "
        "correct this file's probe to the implemented collaborator"
    )


async def test_pending_result_goes_to_launches_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED: the pending result is posted to launches channel, not monitoring.

    The modified behavior delivers to the launches channel (where the thread
    lives) instead of the monitoring channel. This is a channel change required
    by "delivered as a reply within that launch's Slack thread".
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    entry = _module().deliver_pending_result
    await entry(result=_PendingRow(), product=_CatalogProduct(), step_name=STEP_NAME)

    assert poster.calls, "no Slack message was delivered for the pending result"
    assert poster.calls[0].get("channel") == LAUNCHES_CHANNEL_ID, (
        f"the pending result was not posted to the launches channel: "
        f"{poster.calls[0]!r}"
    )


async def test_pending_result_tags_confirmer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario part: A pending result reaches Slack (with confirmer tag).

    WHEN a pending result is stored
    THEN a Slack message ... is delivered as a reply within the launch's
    thread, ... tagging the step's named confirmer.

    SPECIFIED: the message tags the step's confirmer. Asserted two ways:
    the adapter threads the real `step` through to mention resolution (not
    just its name), and it uses whatever mention that resolution returns.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    calls = _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    step = _StepWithConfirmer()
    entry = _module().deliver_pending_result
    await entry(
        result=_PendingRow(), product=_CatalogProduct(), step_name=STEP_NAME, step=step
    )

    assert calls and calls[0].get("step") is step, (
        "deliver_pending_result did not thread the pending result's own "
        f"step through to mention resolution: {calls!r}"
    )
    assert f"<@{CONFIRMER_ID}>" in poster.rendered, (
        f"the pending result did not tag the step's confirmer: {poster.rendered!r}"
    )


async def test_pending_result_with_no_confirmer_still_threads_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`resolve_mention_target`'s fallback (a step naming no confirmer tags
    the launch's submitter instead) is `test_thread_establishment_race.py`'s
    concern; this file's share is narrower — that `deliver_pending_result`
    still passes the real step through even when it names no confirmer,
    rather than substituting `None` and silently losing the fallback path.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    calls = _install_thread_establishment(monkeypatch)
    _install_poster(monkeypatch, _CapturingPoster())

    step = _StepWithConfirmer(confirmer=None)
    entry = _module().deliver_pending_result
    await entry(
        result=_PendingRow(), product=_CatalogProduct(), step_name=STEP_NAME, step=step
    )

    assert calls and calls[0].get("step") is step, (
        f"deliver_pending_result did not thread the step through when it "
        f"names no confirmer: {calls!r}"
    )


async def test_pending_result_is_thread_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """DERIVED: the pending result is posted as a reply (with thread_ts parameter).

    A thread reply requires the `thread_ts` parameter to be passed to Slack's
    API. This derives from "delivered as a reply within that launch's Slack
    thread". Asserted structurally -- the literal `thread_ts` kwarg, not the
    value's mere presence somewhere in the rendered text -- and that it is
    exactly what thread establishment returned, not a value the adapter
    invented.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    _install_thread_establishment(monkeypatch)
    poster = _install_poster(monkeypatch, _CapturingPoster())

    entry = _module().deliver_pending_result
    await entry(result=_PendingRow(), product=_CatalogProduct(), step_name=STEP_NAME)

    assert poster.calls, "no Slack message was delivered for the pending result"
    assert poster.calls[0].get("thread_ts") == SLACK_THREAD_TS, (
        "the pending result was not posted with the established thread's "
        f"reference: {poster.calls[0]!r}"
    )
