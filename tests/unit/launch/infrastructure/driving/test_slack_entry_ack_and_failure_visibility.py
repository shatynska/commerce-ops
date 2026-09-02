"""`launch-entry`: acknowledgement is independent of persistence, and a
post-acknowledgement failure is visible.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Covers, from the ADDED requirement
"Acknowledgement is independent of persistence, and a post-acknowledgement
failure is visible":

- Scenario: A slow transaction does not miss the acknowledgement window
- Scenario: A post-acknowledgement failure reaches the user

"Nothing is persisted" (part of the second scenario's THEN clause) is a
persistence outcome a mocked collaborator can only satisfy vacuously --
nothing is ever persisted through a double regardless of correctness. The
persistence half is exercised for real in
`tests/integration/launch/test_slack_entry_start.py`; this file covers what
IS observable at this level: response timing, and that a message reaches
the submitting user.

The requirement's further sentence -- "A failure to deliver a message
after a successful commit leaves the commit standing" -- names no
`#### Scenario:` block of its own, so it is not counted as a scenario here.
It is nonetheless tested, as a DERIVED case, at the integration tier, where
"the commit stands" is actually observable (real persisted state surviving
a real delivery failure); see that file's docstring.

## The interface under test does not exist yet, and its shape is INVENTED

See `test_slack_entry_request_verification.py`'s module docstring for the
route, env vars, and cache-reset assumptions shared by every file in this
directory. Additionally INVENTED here:

- The outcome message -- success or failure alike -- is delivered as a
  `chat.postMessage` call whose `channel` is the submitting user's id
  (design.md Decision 6: "delivered to the submitting user directly (a DM
  through the bot token), not to the invoking channel"). No artifact fixes
  the exact call sequence Slack DM delivery takes (a direct
  `chat.postMessage(channel=<user id>)`, vs. an explicit `conversations.open`
  first) so only the DM's eventual `channel` value is asserted, not the
  call sequence that produced it.
- The ack-timing assertion is a wall-clock proxy (the HTTP round trip
  returns well before a deliberately slow collaborator does), not a proof
  Slack's own 3-second window specifically was met -- no test can prove a
  timing bound holds inside a fixed CI budget without either an actual
  3-second wait or a proxy. The proxy carries a small, inherent flakiness
  risk under extreme scheduler contention; it is chosen over a real 3-second
  sleep to keep this file fast, consistent with `tests/unit`'s own tier
  convention.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import time
import urllib.parse
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, Sku

SLACK_ENTRY_PATH = "/product_agent/slack/events"  # ASSUMED
SIGNING_SECRET = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"  # not a real credential

SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"  # ASSUMED
LAUNCHES_CHANNEL_VAR = "PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"
LAUNCHES_CHANNEL_ID = "C0LAUNCHES"  # not a real channel

CALLBACK_ID = "start_launch_modal"  # ASSUMED
SUBMITTER_ID = "U0SUBMITTER"

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
    # `ensure_launch_thread` posts the anchor through its own `lru_cache`d
    # `AsyncWebClient`. This file is the first in the tier to construct it,
    # and it is built while `AsyncWebClient.api_call` is patched -- so
    # without resetting it here the cached client outlives these tests.
    "commerce_ops.launch.application.thread_establishment",
)

REGISTRAR_ATTRIBUTES: tuple[str, ...] = (
    "register_catalog_product",
    "catalog_registrar",
    "register_product",
)

# Deliberately slow, relative to a normal test's runtime, but under Slack's
# real 3-second ack window -- large enough that a response gated on it would
# be trivially distinguishable from one that was not.
#
# Scaled up from 0.3s after CI failed at 0.190s against a 0.15s threshold.
# The behaviour was correct there -- 0.190s is well under the delay, so the
# acknowledgement plainly had not waited on persistence -- but roughly 0.19s
# of fixed framework overhead on a slower runner consumed most of a 0.15s
# budget. Enlarging the delay leaves that overhead a small fraction of the
# signal instead of most of it.
SLOW_PERSISTENCE_SECONDS = 1.5

# Half the delay, exactly as before the rescale: what this asserts is
# unchanged in relative terms -- the round trip returned well before the
# collaborator did -- and only the absolute scale moved, so the threshold
# is not a number that can be quietly relaxed away from the delay it
# derives from.
ACK_SHOULD_RETURN_WITHIN_SECONDS = SLOW_PERSISTENCE_SECONDS / 2

# Generous relative to the delay; a ceiling on waiting, never an assertion
# about timing.
_DEFERRED_WORK_TIMEOUT_SECONDS = SLOW_PERSISTENCE_SECONDS + 5.0


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _FakeSlackResponse(dict[str, Any]):
    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class _RecordingSlackApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def methods(self) -> list[str]:
        return [call["api_method"] for call in self.calls]

    @property
    def posts(self) -> list[dict[str, Any]]:
        return [
            call["payload"]
            for call in self.calls
            if call["api_method"] == "chat.postMessage"
        ]

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        self.calls.append(
            {
                "api_method": api_method,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )
        # `ts` because `ensure_launch_thread` reads `response["ts"]` to record
        # the thread reference. Without it the `KeyError` is swallowed by
        # `slack_entry` into the fallback DM, and the test fails on the
        # channel assertion rather than on anything it is about.
        return _FakeSlackResponse({"ok": True, "ts": THREAD_TS})


class _SlowRegistrar:
    """Registers successfully, after a deliberate async delay."""

    def __init__(self, *, delay: float) -> None:
        self.delay = delay
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        await asyncio.sleep(self.delay)
        return None


class _RecordingStartLaunch:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[Any] = []
        self.failure = failure

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.failure is not None:
            raise self.failure
        return None


class _SimulatedPersistenceFailure(RuntimeError):
    """A stand-in for any post-acknowledgement persistence failure -- the
    requirement says "a domain rejection or an infrastructure failure
    alike", so no specific exception type is significant here."""


# --------------------------------------------------------------------------
# Cache-reset discovery
# --------------------------------------------------------------------------


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
        parameter.default is not inspect.Parameter.empty
        or parameter.kind
        in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for parameter in signature.parameters.values()
    )


def _reset_slack_caches() -> int:
    reset = 0
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
                reset += 1
            elif _looks_like_a_reset_hook(value):
                value()
                reset += 1
    return reset


def _require_slack_entry_module() -> Any:
    try:
        return importlib.import_module(SLACK_ENTRY_MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{SLACK_ENTRY_MODULE} does not exist yet (tasks.md 2.1); this "
            f"test's target is absent. Underlying error: {exc}"
        )


def _install_registrar(module: Any, monkeypatch: pytest.MonkeyPatch, fake: Any) -> None:
    installed = [name for name in REGISTRAR_ATTRIBUTES if hasattr(module, name)]
    assert installed, (
        f"{module.__name__} exposes none of {REGISTRAR_ATTRIBUTES}, so the "
        "adapter has no discoverable catalog-registrar injection point "
        "(design.md Decision 2 / tasks.md 2.3)"
    )
    for name in installed:
        monkeypatch.setattr(module, name, fake)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@asynccontextmanager
async def _fake_transaction() -> AsyncIterator[None]:
    """Stands in for the adapter's `transaction()` provider.

    Yields `None`: the collaborators that would use the session -- the
    catalog registrar and `start_launch` -- are themselves substituted in
    every test here, so nothing issues a query. This keeps the file
    unit-tier: no `DATABASE_URL`, no Postgres.

    Fixture correction made while implementing tasks.md 2.2, following the
    convention `test_clickup_webhook.py` records for the same seam. It adds
    a substitute for a real collaborator; it weakens no assertion.
    """
    yield None


THREAD_TS = "1700000000.000100"


class _ThreadlessLaunch:
    """The launch `ensure_launch_thread` reads: no thread established yet."""

    def __init__(self) -> None:
        self.slack_thread_id: str | None = None
        self.launch_date = None
        self.submitter = SUBMITTER_ID


class _FakeLaunchStore:
    """`LaunchRepository`, for the thread-establishment read and write.

    One launch, shared per instantiation of the fixture, because
    `establish_thread_and_resolve_mention` reads it twice -- once inside
    `ensure_launch_thread` and once for `resolve_mention_target` -- and the
    thread reference written by the first read must be visible to the
    second. `product_id` is ignored: this file's registrar double returns
    `None`, so there is no identity to key on and none is needed.
    """

    launch: _ThreadlessLaunch

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    async def get_by_product_id(self, product_id: Any) -> Any:
        return type(self).launch

    async def save(self, launch: Any) -> None:
        """`ensure_launch_thread` persists the thread reference through this.

        Absent, the `AttributeError` lands in `slack_entry`'s swallowing
        `except` and the test observes the fallback DM instead of the
        threaded reply -- failing on the channel assertion, with nothing in
        the failure naming the cause.
        """


async def _no_lock(*args: Any, **kwargs: Any) -> None:
    """`hold_launch_thread_establishment_lock`, which needs a real session."""


async def _resolves_a_product(*args: Any, **kwargs: Any) -> Any:
    """`launch_thread_delivery.read_product`, the anchor's own catalog read.

    Substituted for the same reason as the three collaborators beside it,
    and it became necessary with `inject-the-thread-anchor-poster`: the
    anchor's facts are resolved at establishment time now rather than
    supplied by the caller, so without this the composition root's real
    reader runs against this file's registrar double -- which returns
    `None` for the product identifier -- and establishment refuses, leaving
    the fallback DM where the test asserts a threaded reply.

    Answers the real `Product`, not a stand-in with fewer fields: the
    anchor reads `name`, `sku` and `marketplace_id` off it directly, and a
    double modelling less than the aggregate could satisfy a check the real
    store would fail.
    """
    return Product.register(
        sku=Sku("SKU-0002"),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module(SLACK_ENTRY_MODULE)
    monkeypatch.setattr(module, "transaction", _fake_transaction)

    # `establish_thread_and_resolve_mention` opens its *own* `transaction()`,
    # imported into its own module, so substituting `slack_entry.transaction`
    # above does not reach it -- which is why this file was gated on
    # `DATABASE_URL` and skipped wholesale.
    #
    # The seam substituted is the one *beneath* the preamble, not the
    # preamble itself: the anchor message is posted inside
    # `ensure_launch_thread`, and this file asserts on an anchor *and* a
    # threaded reply, so substituting `establish_thread_and_resolve_mention`
    # would remove the anchor and force that assertion down to one post.
    delivery = importlib.import_module(
        "commerce_ops.launch.infrastructure.driven.launch_thread_delivery"
    )
    _FakeLaunchStore.launch = _ThreadlessLaunch()
    monkeypatch.setattr(delivery, "transaction", _fake_transaction)
    monkeypatch.setattr(delivery, "LaunchRepository", _FakeLaunchStore)
    monkeypatch.setattr(delivery, "hold_launch_thread_establishment_lock", _no_lock)
    monkeypatch.setattr(delivery, "read_product", _resolves_a_product)


class _FakePlaybookRepository:
    """The served-playbook read (`move-playbook-steps-to-postgres`),
    substituted like the other collaborator globals: serves a minimal
    coherent playbook (every gate held, as the gate-holding floor
    requires) without touching any database."""

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> Any:
        from commerce_ops.launch.domain.launch_playbook import (
            Gate,
            GateOpening,
            Hazard,
            LaunchPlaybook,
            OffsetAnchor,
            Scope,
            StepDefinition,
            StepKind,
            StepStatus,
        )
        from commerce_ops.shared.domain.discipline import Discipline

        gate_order = (
            "commit",
            "order",
            "listable",
            "stock-ready",
            "live",
            "ignition",
            "phase-one-complete",
            "graduated",
        )
        confirmation = {"commit", "order", "phase-one-complete", "graduated"}
        gates = tuple(
            Gate(
                identifier=identifier,
                position=position,
                opening=(
                    GateOpening.REQUIRES_CONFIRMATION
                    if identifier in confirmation
                    else GateOpening.AUTOMATIC
                ),
            )
            for position, identifier in enumerate(gate_order, start=1)
        )
        steps = tuple(
            StepDefinition(
                identifier=f"hold.{gate}",
                name=f"Blocking work holding the {gate} gate",
                gate=gate,
                discipline=next(iter(Discipline)),
                scope=Scope.PRODUCT,
                timing_anchor=OffsetAnchor(days=0),
                blocking=True,
                kind=StepKind.AUTOMATED,
                status=StepStatus.ACTIVE,
                hazard=Hazard.NONE,
                handler="fixture.holding_check",
                provenance=None,
            )
            for gate in gate_order
        )
        return LaunchPlaybook(version="test-v1", gates=gates, steps=steps)


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.import_module(SLACK_ENTRY_MODULE),
        "PlaybookRepository",
        _FakePlaybookRepository,
    )


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    # thread-launch-slack-notifications: a successful submission's anchor
    # and confirmation reply both land in the launches channel.
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)
    _reset_slack_caches()
    yield
    _reset_slack_caches()


@pytest.fixture()
def slack_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingSlackApi:
    async_client = importlib.import_module("slack_sdk.web.async_client")
    recorder = _RecordingSlackApi()
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", recorder.api_call)
    return recorder


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    with TestClient(slack_asgi_app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def undrained_client() -> Iterator[TestClient]:
    """A client that does NOT wait for a request's deferred work.

    Fixture correction made while implementing tasks.md 2.2. The timing
    scenario below cannot be observed through `slack_asgi_app`: that wrapper
    awaits every task a request spawned before returning, so the round trip
    would necessarily include the deliberately slow collaborator, and the
    "nothing posted yet" assertion could never hold either. Measuring the
    acknowledgement requires a client that returns when Bolt returns.

    What the scenario asserts is unchanged -- acknowledged fast, no outcome
    delivered at that moment, exactly one delivered afterwards. Only the
    harness the assertions run against is corrected.
    """
    from commerce_ops.main import app as undrained_app

    with TestClient(undrained_app, raise_server_exceptions=False) as test_client:
        yield test_client


def _wait_for_posts(recorder: _RecordingSlackApi, *, count: int) -> None:
    """Lets the deferred listener finish, without pinning how long it takes.

    Replaces `_drain` for the undrained client: the listener runs on the
    TestClient portal's own loop, so the wait is a bounded poll rather than
    a fixed sleep.
    """
    deadline = time.monotonic() + _DEFERRED_WORK_TIMEOUT_SECONDS
    while len(recorder.posts) < count and time.monotonic() < deadline:
        time.sleep(0.01)


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------


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


def _view_submission_form() -> dict[str, str]:
    view_submission_payload = {
        "type": "view_submission",
        "team": {"id": "T0TEAM", "domain": "test-team"},
        "user": {"id": SUBMITTER_ID, "username": "submitter"},
        "api_app_id": "A0PRODUCTAGENT",
        "token": "verification-token",
        "trigger_id": "1234.5678.abcdef",
        "view": {
            "id": "V0VIEW",
            # Slack's own view object always carries this; Bolt reads
            # `body["view"]["type"]` unconditionally (payload_utils'
            # `is_workflow_step_save`), so omitting it is a 500 rather than
            # anything this change's spec is about. Fixture correction made
            # while implementing tasks.md 2.2.
            "type": "modal",
            "callback_id": CALLBACK_ID,
            "private_metadata": "",
            "hash": "156772938.1827394",
            "state": {
                "values": {
                    "sku": {"sku": {"type": "plain_text_input", "value": "SKU-0002"}},
                    "name": {"name": {"type": "plain_text_input", "value": "Widget"}},
                    "asin": {"asin": {"type": "plain_text_input", "value": None}},
                    "launch_date": {
                        "launch_date": {"type": "datepicker", "selected_date": None}
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
    return {"payload": json.dumps(view_submission_payload)}


def _post_view_submission(client: TestClient) -> Any:
    body = urllib.parse.urlencode(_view_submission_form()).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# --------------------------------------------------------------------------
# Scenario: A slow transaction does not miss the acknowledgement window
# --------------------------------------------------------------------------


def test_a_slow_transaction_does_not_miss_the_acknowledgement_window(
    monkeypatch: pytest.MonkeyPatch,
    undrained_client: TestClient,
    slack_api: _RecordingSlackApi,
) -> None:
    """Scenario: A slow transaction does not miss the acknowledgement window.

    WHEN a valid submission's persistence outlasts Slack's acknowledgement
    window
    THEN the submission was already acknowledged within the window, and the
    outcome is delivered afterwards as a message.

    thread-launch-slack-notifications, `launch-entry` MODIFIED: a
    successful outcome is no longer a DM (design.md Decision 6 covered only
    the *failure* path, which is unchanged) -- it is an anchor message plus
    a tagged reply within the launch's thread, both in the launches
    channel. Updated per this file's own module docstring instruction
    (`tasks.md` 8.3) and the change's `test-manifest.md`, which named this
    scenario's success-path assertion as a candidate for exactly this. Not
    independently verified against a real database here; the full, DB-backed
    scenario is verified for real in
    `tests/integration/launch/test_slack_entry_start.py`.

    This file was previously recorded as "gated on `DATABASE_URL`", and
    skipped wholesale on that basis. It never needed a database:
    `restore-the-skipped-unit-tests` found that the only thing reaching one
    was `establish_thread_and_resolve_mention` opening its own
    `transaction()`, which the `sessionless` fixture now substitutes at the
    seam beneath it. The file runs in the commit-time tier.
    """
    module = _require_slack_entry_module()
    slow_registrar = _SlowRegistrar(delay=SLOW_PERSISTENCE_SECONDS)
    _install_registrar(module, monkeypatch, slow_registrar)
    start_launch = _RecordingStartLaunch()
    if hasattr(module, "start_launch"):
        monkeypatch.setattr(module, "start_launch", start_launch)

    started = time.monotonic()
    response = _post_view_submission(undrained_client)
    elapsed = time.monotonic() - started

    # SPECIFIED: acknowledged within Slack's window, independent of how
    # long persistence takes -- proxied here as "the HTTP round trip
    # returned well before the deliberately slow collaborator did" (see
    # module docstring).
    assert response.status_code == 200, (
        f"expected the submission to be acknowledged, got {response.status_code}"
    )
    assert elapsed < ACK_SHOULD_RETURN_WITHIN_SECONDS, (
        f"the acknowledgement took {elapsed:.3f}s, which is not "
        f"comfortably under the {SLOW_PERSISTENCE_SECONDS}s the "
        "collaborator was made to take; the response appears to have "
        "waited on persistence rather than acknowledging independently "
        "of it"
    )

    # SPECIFIED: the outcome is delivered afterwards, as a message -- not
    # yet, at the moment of acknowledgement.
    assert slack_api.posts == [], (
        "an outcome message was already posted at acknowledgement time, "
        "before the slow persistence had even completed"
    )

    _wait_for_posts(slack_api, count=2)

    assert len(slack_api.posts) == 2, (
        "expected an anchor message and a threaded confirmation reply once "
        f"the slow persistence completed, observed: {slack_api.posts}"
    )
    anchor, reply = slack_api.posts
    assert anchor.get("channel") == LAUNCHES_CHANNEL_ID, (
        f"the anchor message did not go to the launches channel: {anchor!r}"
    )
    assert reply.get("channel") == LAUNCHES_CHANNEL_ID, (
        f"the confirmation reply did not go to the launches channel: {reply!r}"
    )
    assert f"<@{SUBMITTER_ID}>" in (reply.get("text") or ""), (
        f"the confirmation reply did not tag the submitter: {reply!r}"
    )


# --------------------------------------------------------------------------
# Scenario: A post-acknowledgement failure reaches the user
# --------------------------------------------------------------------------


def test_a_post_acknowledgement_failure_reaches_the_user(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
) -> None:
    """Scenario: A post-acknowledgement failure reaches the user.

    WHEN persistence fails after the submission was acknowledged and the
    modal closed
    THEN the submitting user receives an error message naming the failure
    AND nothing is persisted.

    "Nothing is persisted" is not asserted here -- see the module
    docstring; a mocked registrar can only satisfy that vacuously. Its real
    assertion lives in the integration tier.
    """
    module = _require_slack_entry_module()
    registrar = _SlowRegistrar(delay=0.0)
    _install_registrar(module, monkeypatch, registrar)
    failure = _SimulatedPersistenceFailure("simulated duplicate launch rejection")
    start_launch = _RecordingStartLaunch(failure=failure)
    if hasattr(module, "start_launch"):
        monkeypatch.setattr(module, "start_launch", start_launch)
    else:
        pytest.fail(
            f"{module.__name__} has no `start_launch` attribute to patch "
            "(tasks.md 2.2 names `launch.application.start_launch` as the "
            "collaborator this handler calls)"
        )

    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200, (
        f"expected the submission to still be acknowledged even though its "
        f"persistence later fails, got {response.status_code}"
    )

    # Precondition: the failure really was reached, so the assertions below
    # cannot pass for the wrong reason (e.g. the handler never got that far).
    assert start_launch.calls, (
        "start_launch was never called, so this test proves nothing about "
        "what happens when it fails"
    )

    # SPECIFIED: an error message naming the failure reaches the submitting
    # user -- it does NOT pass silently.
    assert len(slack_api.posts) == 1, (
        "expected exactly one message delivered after a post-"
        f"acknowledgement failure, observed: {slack_api.posts}"
    )
    posted = slack_api.posts[0]
    assert posted.get("channel") == SUBMITTER_ID, (
        "the failure message must reach the submitting user directly "
        f"(design.md Decision 6), got channel={posted.get('channel')!r}"
    )
    text = posted.get("text") or ""
    assert text.strip(), "the failure message posted carried no text"
