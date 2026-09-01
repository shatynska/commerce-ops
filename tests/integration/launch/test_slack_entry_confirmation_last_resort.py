"""A started launch is never left unreported (`launch-entry`).

Derived strictly from the MODIFIED requirement *A launch is started from
Slack in one interaction* in
`openspec/changes/fix-launch-thread-mentions/specs/launch-entry/spec.md`,
and specifically from the paragraph and the scenario it adds:

    **A started launch SHALL NOT be left unreported.** Where the threaded
    confirmation cannot be delivered — the thread cannot be established, or
    the reply cannot be posted — the system SHALL tell the submitter
    directly that the launch started, by the same direct message a failed
    start already uses, and SHALL report the delivery failure.

    #### Scenario: A confirmation that cannot reach the thread reaches the
    submitter
    - **WHEN** the modal is submitted, the product and its launch are
      persisted, and establishing the launch's thread or posting the
      confirmation reply within it fails
    - **THEN** the submitter is told directly that the launch started, and
      the failure to deliver the threaded confirmation is reported

## Why the integration tier, and why a new file

`tasks.md` 6.7 records the reason: `test_slack_entry_ack_and_failure_
visibility.py`, the natural unit-tier home, is database-gated for a
pre-existing reason — `_register_and_start` reads the live playbook for
real regardless of how its registrar is mocked — so the real assertion
belongs beside its siblings in this directory. The scenario's WHEN also
says the product and its launch **are persisted**, which is an outcome
only a real store read can observe.

This is a new file rather than an addition to
`test_slack_entry_start.py` because this pass is additive only: it adds
tests and never edits, deletes or disables an existing one. Everything
below follows that file's conventions — unique SKUs, no truncate fixture,
`alembic upgrade head` assumed applied, a skip where no database is
configured — deliberately duplicated rather than imported, per this
project's no-shared-helper convention for test plumbing.

## How "the threaded delivery fails" is engineered

The requirement names two ways, and both are exercised, because they fail
at different points and an implementation can easily guard one and not the
other:

- the **anchor** cannot be posted, so no thread is established at all;
- the anchor is posted and the **reply within it** cannot be.

Both are engineered by failing `chat.postMessage` selectively, by the
channel and thread it targets, rather than by failing the method outright.
That distinction is what this whole file turns on: a double that failed
every `chat.postMessage` would also fail the direct message the fallback
depends on, and the test could then pass only by asserting that nothing
happened.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the fallback is
`_confirmation_text(submission)` posted to the submitter by the same
`_post(client, submitter, …)` call the failure path uses (`tasks.md` 4.1),
that the text is **not** altered to mention the missing thread (4.3), and
that the failure is logged (4.1, 4.4).

INVENTED, recorded in `test-manifest.md`:

- The Slack plumbing constants (route, signing secret and bot token
  variables, callback id, modal block/action ids), copied wholesale from
  `test_slack_entry_start.py` rather than re-derived.
- That a direct message to the submitter is a `chat.postMessage` whose
  `channel` is the submitter's own identity. Correction point:
  `_direct_messages`.
- That "the failure is reported" means a record at `WARNING` or above.
  Correction point: `_reports`.
- That the confirmation is recognisable by its ClickUp-cadence wording,
  which `launch-entry`'s own requirement fixes as part of the confirmation
  ("naming that tracked work appears in ClickUp on the sync cadence") and
  which the sibling file already asserts on the threaded reply.

## Expected first-run state

Where no database is configured — as in the environment this file was
written in — this tier skips, and these assertions have never executed at
all. Recorded in `test-manifest.md`.

Against a database, both tests are expected to FAIL: today the threaded
confirmation sits inside a `try` whose `except Exception` logs and
continues, so nothing reaches the submitter at all. That is failure state
1 — the code runs and produces the wrong outcome.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import time
import urllib.parse
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from commerce_ops.catalog.application import get_product_by_sku
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.application import read_launch
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.main import app
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import Sku

pytestmark = pytest.mark.anyio

SLACK_ENTRY_PATH: Final = "/product_agent/slack/events"
SIGNING_SECRET: Final = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN: Final = "xoxb-test-product-agent-not-a-real-token"  # not a real credential
SIGNING_SECRET_VAR: Final = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR: Final = "PRODUCT_AGENT_SLACK_BOT_TOKEN"
LAUNCHES_CHANNEL_VAR: Final = "PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"
LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"  # not a real channel
CALLBACK_ID: Final = "start_launch_modal"
SUBMITTER_ID: Final = "U0SUBMITTER"

SLACK_ENTRY_MODULE: Final = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES: Final = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

_DRAIN_TIMEOUT_SECONDS: Final = 5.0


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# Database plumbing (mirrors test_slack_entry_start.py)
# --------------------------------------------------------------------------


def unique_sku() -> Sku:
    return Sku(f"LASTRESORT-{uuid.uuid4().hex[:10].upper()}")


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


class _ServedPlaybooks:
    def __init__(self, playbook: Any) -> None:
        self._playbook = playbook

    def get(self, version: str) -> Any:
        return self._playbook


async def _reread_product(engine: AsyncEngine, sku: Sku) -> Any:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        store = CatalogProductRepository(session)
        return await get_product_by_sku(store, sku, scope=AccessScope.unrestricted())


async def _reread_launch(engine: AsyncEngine, product_id: Any) -> Any:
    from commerce_ops.launch.infrastructure.driven.playbook_repository import (
        PlaybookRepository,
    )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        store = LaunchRepository(session)
        playbook = await PlaybookRepository(session).get("live")
        return await read_launch(
            store,
            _ServedPlaybooks(playbook),
            product_id=product_id,
            as_of=datetime.now(UTC).date(),
            scope=AccessScope.unrestricted(),
        )


# --------------------------------------------------------------------------
# Slack ASGI plumbing (mirrors test_slack_entry_start.py)
# --------------------------------------------------------------------------


class _DrainsDeferredListeners:
    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        before = asyncio.all_tasks()
        await self.inner(scope, receive, send)
        spawned = asyncio.all_tasks() - before - {asyncio.current_task()}
        if spawned:
            await asyncio.wait(spawned, timeout=_DRAIN_TIMEOUT_SECONDS)


class _FakeSlackResponse(dict[str, Any]):
    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class _SelectivelyFailingSlackApi:
    """Records outbound Slack calls, and fails `chat.postMessage`
    selectively by what the post targets.

    Failing the *method* outright — as the sibling file's delivery-failure
    test does — would also fail the direct message the fallback depends on,
    and this file could then only assert that nothing happened. So the
    predicate reads the payload: `only_threaded=False` fails every post to
    the launches channel (the anchor never lands, so no thread is
    established), and `only_threaded=True` fails only those carrying a
    `thread_ts` (the anchor lands, the reply within it does not).

    A distinct, deterministic `ts` per successful call, for the same reason
    the sibling file gives: `ensure_launch_thread` reads `response["ts"]`
    from a real `chat.postMessage` reply, and a response missing it would
    make thread establishment fail for a reason this test did not choose.
    """

    def __init__(self, *, only_threaded: bool) -> None:
        self.calls: list[dict[str, Any]] = []
        self.only_threaded = only_threaded

    @property
    def posts(self) -> list[dict[str, Any]]:
        return [
            {**call["payload"], "ts": call["response_ts"], "failed": call["failed"]}
            for call in self.calls
            if call["api_method"] == "chat.postMessage"
        ]

    def _should_fail(self, api_method: str, payload: Any) -> bool:
        if api_method != "chat.postMessage" or not isinstance(payload, dict):
            return False
        if payload.get("channel") != LAUNCHES_CHANNEL_ID:
            return False
        if self.only_threaded:
            return bool(payload.get("thread_ts"))
        return True

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        payload = dict(payload) if isinstance(payload, dict) else payload
        response_ts = f"1700000000.{len(self.calls):06d}"
        failed = self._should_fail(api_method, payload)
        self.calls.append(
            {
                "api_method": api_method,
                "payload": payload,
                "response_ts": response_ts,
                "failed": failed,
            }
        )
        if failed:
            raise ConnectionError(
                f"simulated threaded-delivery failure for {api_method}"
            )
        return _FakeSlackResponse({"ok": True, "ts": response_ts})


def _looks_like_a_reset_hook(value: Any) -> bool:
    if not callable(value):
        return False
    name = getattr(value, "__name__", "")
    if not name.startswith(("reset_", "clear_")):
        return False
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return False
    return all(
        p.default is not inspect.Parameter.empty
        or p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in signature.parameters.values()
    )


def _reset_slack_caches() -> None:
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
            elif _looks_like_a_reset_hook(value):
                value()


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)
    _reset_slack_caches()
    yield
    _reset_slack_caches()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(
        _DrainsDeferredListeners(app), raise_server_exceptions=False
    ) as test_client:
        yield test_client


def _install_slack(
    monkeypatch: pytest.MonkeyPatch, *, only_threaded: bool
) -> _SelectivelyFailingSlackApi:
    async_client = importlib.import_module("slack_sdk.web.async_client")
    recorder = _SelectivelyFailingSlackApi(only_threaded=only_threaded)
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", recorder.api_call)
    return recorder


def _signed_headers(body: bytes) -> dict[str, str]:
    stamp = str(int(time.time()))
    signature = SignatureVerifier(SIGNING_SECRET).generate_signature(
        timestamp=stamp, body=body
    )
    assert signature is not None
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _view_submission_form(*, sku: str, name: str = "Widget") -> dict[str, str]:
    payload = {
        "type": "view_submission",
        "team": {"id": "T0TEAM", "domain": "test-team"},
        "user": {"id": SUBMITTER_ID, "username": "submitter"},
        "api_app_id": "A0PRODUCTAGENT",
        "token": "verification-token",
        "trigger_id": "1234.5678.abcdef",
        "view": {
            "id": "V0VIEW",
            "type": "modal",
            "callback_id": CALLBACK_ID,
            "private_metadata": "",
            "hash": "156772938.1827394",
            "state": {
                "values": {
                    "sku": {"sku": {"type": "plain_text_input", "value": sku}},
                    "name": {"name": {"type": "plain_text_input", "value": name}},
                    "asin": {"asin": {"type": "plain_text_input", "value": None}},
                    "launch_date": {
                        "launch_date": {
                            "type": "datepicker",
                            "selected_date": None,
                        }
                    },
                    "marketplace": {
                        "marketplace": {
                            "type": "static_select",
                            "selected_option": {
                                "value": "ATVPDKIKX0DER",
                                "text": {"type": "plain_text", "text": "Amazon US"},
                            },
                        }
                    },
                }
            },
        },
    }
    return {"payload": json.dumps(payload)}


def _post_view_submission(client: TestClient, **fields: Any) -> Any:
    body = urllib.parse.urlencode(_view_submission_form(**fields)).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


def _direct_messages(slack: _SelectivelyFailingSlackApi) -> list[dict[str, Any]]:
    """Every post addressed to the submitter themselves.

    INVENTED (see the module docstring): a Slack direct message is a
    `chat.postMessage` whose `channel` is the recipient's own identity,
    which is how `_post(client, submitter, …)` reaches them on the failure
    path this fallback reuses.
    """
    return [post for post in slack.posts if post.get("channel") == SUBMITTER_ID]


def _reports(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# --------------------------------------------------------------------------
# Scenario: A confirmation that cannot reach the thread reaches the
# submitter
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("only_threaded", "how"),
    [
        pytest.param(False, "the thread could not be established", id="anchor-fails"),
        pytest.param(
            True, "the reply within the thread could not be posted", id="reply-fails"
        ),
    ],
)
async def test_a_confirmation_that_cannot_reach_the_thread_reaches_the_submitter(
    only_threaded: bool,
    how: str,
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A confirmation that cannot reach the thread reaches the
    submitter.

    WHEN the modal is submitted, the product and its launch are persisted,
    and establishing the launch's thread or posting the confirmation reply
    within it fails
    THEN the submitter is told directly that the launch started, and the
    failure to deliver the threaded confirmation is reported.

    SPECIFIED, and parametrised over the two failures the requirement
    names in its own clause ("the thread cannot be established, or the
    reply cannot be posted"). They fail at different points, and an
    implementation guarding only the second would leave the first silent —
    which is the asymmetry `proposal.md` describes: a launch that fails is
    reported and a launch that succeeds may not be.
    """
    slack = _install_slack(monkeypatch, only_threaded=only_threaded)
    sku = unique_sku()

    with caplog.at_level(logging.WARNING):
        response = _post_view_submission(client, sku=sku.value)
        _drain(client)

    assert response.status_code == 200, (
        "the submission must still be acknowledged; the acknowledgement is "
        "independent of delivery"
    )

    # Precondition, from the scenario's own WHEN: the threaded delivery
    # really was attempted and really did fail. Without it, "the submitter
    # was told directly" could be true of a run that never threaded at all.
    assert any(post.get("failed") for post in slack.posts), (
        f"no threaded delivery failed, so this run does not exercise the "
        f"scenario ({how}): {slack.posts!r}"
    )

    # Precondition, from the scenario's own WHEN: the product and its
    # launch are persisted. The confirmation is owed *because* they are.
    product = await _reread_product(engine, sku)
    assert product is not None, (
        "the product was not registered, so no confirmation is owed and this "
        "test establishes nothing"
    )
    launch = await _reread_launch(engine, product.id)
    assert launch is not None, "the launch was not started"

    # SPECIFIED: the submitter is told directly that the launch started.
    direct = _direct_messages(slack)
    assert direct, (
        f"the launch was started and persisted, but nothing reached the "
        f"submitter directly when {how}. A submitter told nothing cannot tell "
        f"a silent success from a silent failure: {slack.posts!r}"
    )
    # SPECIFIED: "that the launch started" — the confirmation, not some
    # other message. `launch-entry` fixes the confirmation as naming that
    # tracked work appears in ClickUp on the sync cadence, which is what
    # distinguishes it from the failure text the same call is used for.
    told = "\n".join(str(post.get("text") or "") for post in direct)
    assert "clickup" in told.lower(), (
        f"the direct message does not read as the launch-started confirmation: {told!r}"
    )

    # SPECIFIED: and the failure to deliver the threaded confirmation is
    # reported.
    assert _reports(caplog), (
        f"the threaded delivery failed and nothing was reported when {how}; "
        "the requirement asks for both the fallback and the report"
    )


async def test_the_fallback_confirmation_is_not_rewritten_to_mention_the_thread(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    client: TestClient,
) -> None:
    """`tasks.md` 4.3, from the requirement's "by the same direct message a
    failed start already uses" and `design.md`'s reasoning: "The text is not
    altered to mention the missing thread: the submitter needs to know the
    launch started, and a line about Slack plumbing they can do nothing
    about is noise on the one message that has to land."

    DERIVED as an assertion — the requirement fixes *which* message is sent
    ("the same direct message a failed start already uses"), and this
    reads that as the text being unaltered, which is a stronger claim than
    the requirement states outright. Recorded as derived in
    `test-manifest.md`; if the project decides a line about the thread is
    wanted after all, this is the test to revisit, not the requirement.

    Asserted as an absence of Slack-plumbing vocabulary rather than by
    pinning the exact confirmation wording, which no artifact fixes.
    """
    slack = _install_slack(monkeypatch, only_threaded=False)
    sku = unique_sku()

    _post_view_submission(client, sku=sku.value)
    _drain(client)

    product = await _reread_product(engine, sku)
    assert product is not None, "precondition: the launch must have been persisted"

    direct = _direct_messages(slack)
    assert direct, "precondition: the fallback confirmation must have been sent"
    told = "\n".join(str(post.get("text") or "") for post in direct).lower()

    for noise in ("thread", "could not be posted", "channel"):
        assert noise not in told, (
            f"the fallback confirmation mentions Slack plumbing ({noise!r}) "
            f"the submitter can do nothing about: {told!r}"
        )


# --------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - *A launch is started with a date*, *A launch is started without a date*
#   and *The playbook version is never user input*. Unchanged by this delta
#   — it adds a paragraph about what happens when the threaded delivery
#   fails, and leaves the specified delivery alone — and already covered by
#   `tests/integration/launch/test_slack_entry_start.py` and
#   `tests/unit/launch/infrastructure/driving/test_slack_entry_modal_contract.py`.
# - `tasks.md` 4.4's guard on the fallback itself (where the direct message
#   also fails, log and continue). Engineering it needs *every*
#   `chat.postMessage` to fail, which makes "the submitter was told" and
#   "the launch stands" indistinguishable from a run that never got that
#   far; and the surrounding behaviour — a delivery failure never unwinds a
#   commit — is already covered by
#   `test_slack_entry_start.py::test_a_post_commit_delivery_failure_leaves_the_commit_standing`.
# --------------------------------------------------------------------------
