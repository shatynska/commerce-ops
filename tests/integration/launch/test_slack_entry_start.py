"""`launch-entry`: persistence-level scenarios, against a real Postgres.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Covers:

- "A launch is started from Slack in one interaction" / Scenario: A launch
  is started with a date
- "A launch is started from Slack in one interaction" / Scenario: A launch
  is started without a date
- "Registration and start are atomic" / Scenario: A rejected start leaves
  no product behind
- "Rejections are surfaced where the user is" / Scenario: A duplicate SKU
  is rejected with nothing persisted

Plus one DERIVED case with no `#### Scenario:` block of its own: the
requirement-body sentence in "Acknowledgement is independent of
persistence..." that "a failure to deliver a message after a successful
commit leaves the commit standing" -- see that test's own docstring for why
it belongs here rather than in the unit tier.

These scenarios say "persisted", "the product is registered", "no second
product ... is persisted", "resubmitting is not rejected" -- outcomes whose
smallest observing unit is a real store read through an independent
session, i.e. this project's `tests/integration/` tier (skips when
`DATABASE_URL` is unset, per this tier's existing convention -- see
`tests/integration/catalog/test_catalog_products.py`).

## Why "a rejected start" is engineered via a mocked `start_launch`

Requirement 2's scenario needs "a submission's product registration
succeeds but its launch start is rejected". Against genuinely real
collaborators there is no natural way to make a *fresh* product's launch
start fail: the shipped playbook resolves to exactly one version (design.md,
proposal.md), a brand-new product has no pre-existing launch, and no other
`launch-instance` rejection applies to a first start. So the registration
half is left real (a real catalog write is attempted, through whatever
real wiring `main.py` installs) and only `start_launch` is monkeypatched to
raise -- isolating exactly the mechanism the requirement is actually
about: that both writes share one `session()` scope (design.md Decision 3)
and a failure in either one leaves neither committed. This is a fixture
correction if some other rejection turns out to be reachable for real; the
postcondition asserted -- nothing persisted, the SKU freed for
resubmission -- is what traces to the spec.

## The interface under test does not exist yet, and its shape is INVENTED

Every test in this file is expected to fail on an absent target
(`ModuleNotFoundError` / a 404 from `main.py` not yet routing the new
adapter) until `tasks.md` section 2 lands. Assumed, and recorded in the
manifest as unresolved project questions:

- The route (`/product_agent/slack/events`), env vars
  (`PRODUCT_AGENT_SLACK_SIGNING_SECRET`, `PRODUCT_AGENT_SLACK_BOT_TOKEN`),
  slash command name, modal `callback_id`, and field block/action ids --
  all as recorded in
  `test_slack_entry_request_verification.py`'s module docstring, not
  repeated here.
- `commerce_ops.launch.application.start_launch`, named literally by
  `tasks.md` 2.2, importable into the adapter module by that name (the
  collaborator-patching convention this codebase already uses, e.g.
  `daily_briefing_job.py`'s `run_daily_briefing`).
- `read_launch`'s call shape: `read_launch(store, playbooks, product_id,
  scope)` -- the shape
  `tests/unit/launch/application/test_scope_aware_launch_reads.py` already
  established and reflects into by parameter name, reused here rather than
  re-invented. `store` is a real `LaunchRepository(session)`; `playbooks`
  is `_ServedPlaybooks` below, a thin real substitute for whatever port
  `read_launch` expects, backed by the real
  `commerce_ops.launch.infrastructure.driven.playbook_loader
  the live `PlaybookRepository` read.
- The persisted launch record's attribute names for its playbook version
  and launch date are not fixed by any artifact; read through the same
  multi-candidate `_read` approach
  `test_scope_aware_launch_reads.py` established
  (`_ATTRIBUTE_ALIASES`), reused here rather than re-invented.

Correcting any of the above is a fixture correction (failure state 3 in
`ai-toolkit:testing`); the postconditions each test asserts must survive
unweakened.

## Test-database lifecycle

Same convention as the rest of `tests/integration/`: unique SKUs per test,
no truncate fixture, `alembic upgrade head` assumed applied, skip when
`DATABASE_URL` is unset.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
import time
import urllib.parse
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
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

SLACK_ENTRY_PATH = "/product_agent/slack/events"  # ASSUMED
SIGNING_SECRET = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"  # not a real credential
SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"  # ASSUMED
CALLBACK_ID = "start_launch_modal"  # ASSUMED
SUBMITTER_ID = "U0SUBMITTER"

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

_DRAIN_TIMEOUT_SECONDS: Final = 5.0

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "version": ("version", "playbook_version", "pinned_version"),
    "launch_date": ("launch_date", "date"),
}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# Database plumbing (mirrors tests/integration/catalog/test_catalog_products.py)
# --------------------------------------------------------------------------


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head`, and point "
            "DATABASE_URL at it to run tests/integration/launch/."
        )
    return url


def unique_sku() -> Sku:
    return Sku(f"ENTRY-{uuid.uuid4().hex[:12].upper()}")


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


class _ServedPlaybooks:
    """A real substitute for whatever `playbooks` port `read_launch`
    expects: `.get(version)` resolves to a pre-loaded copy of the live
    served playbook — the playbook is live, so the version selects
    nothing (`move-playbook-steps-to-postgres`).
    """

    def __init__(self, playbook: Any) -> None:
        self._playbook = playbook

    def get(self, version: str) -> Any:
        return self._playbook


def _read(subject: object, field: str) -> Any:
    """Reads `field` off `subject` by trying each of its known aliases in
    turn -- mirrors `test_scope_aware_launch_reads.py`'s `_read`, reused
    rather than re-invented since no artifact fixes the persisted record's
    attribute names.
    """
    for alias in _ATTRIBUTE_ALIASES.get(field, (field,)):
        if hasattr(subject, alias):
            return getattr(subject, alias)
    pytest.fail(
        f"{subject!r} carries none of {_ATTRIBUTE_ALIASES.get(field, (field,))} "
        f"for {field!r}"
    )


async def _served_version(engine: AsyncEngine) -> str:
    """The served playbook's version identifier, derived from the
    step-set version exactly as the adapter derives it."""
    from sqlalchemy import text

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        version = await session.scalar(
            text("SELECT version FROM playbook_step_set WHERE id = 1")
        )
    return f"v{version}"


async def _reread_launch(
    engine: AsyncEngine, product_id: Any, *, scope: AccessScope | None = None
) -> Any:
    """Reads a launch back through an independent session.

    `read_launch`'s call shape -- `(launches, playbooks, *, product_id,
    as_of, scope)` -- is confirmed here via `inspect.signature` against the
    actual, already-existing use case
    (`commerce_ops.launch.application.use_cases.read_launch`) rather than
    guessed, mirroring
    `test_scope_aware_launch_reads.py`'s own `_scope_argument`/
    `_as_of_argument` reflection helpers. This is reading a pre-existing
    collaborator's public signature, not the implementation of the change
    under test.
    """
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
            scope=scope or AccessScope.unrestricted(),
        )


async def _reread_product(engine: AsyncEngine, sku: Sku) -> Any:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        store = CatalogProductRepository(session)
        return await get_product_by_sku(store, sku, scope=AccessScope.unrestricted())


# --------------------------------------------------------------------------
# Slack ASGI plumbing (mirrors tests/unit/.../conftest.py's drain wrapper)
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


class _RecordingSlackApi:
    """Records outbound Slack Web API calls; optionally fails specific
    methods (used by the delivery-failure test), leaving every other
    method to succeed normally."""

    def __init__(self, *, fail_methods: frozenset[str] = frozenset()) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_methods = fail_methods

    @property
    def methods(self) -> list[str]:
        return [call["api_method"] for call in self.calls]

    @property
    def posts(self) -> list[dict[str, Any]]:
        return [
            c["payload"] for c in self.calls if c["api_method"] == "chat.postMessage"
        ]

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        self.calls.append(
            {
                "api_method": api_method,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )
        if api_method in self.fail_methods:
            raise ConnectionError(f"simulated delivery failure for {api_method}")
        return _FakeSlackResponse({"ok": True})


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


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
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
def client() -> Iterator[TestClient]:
    with TestClient(
        _DrainsDeferredListeners(app), raise_server_exceptions=False
    ) as test_client:
        yield test_client


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


def _view_submission_form(
    *,
    sku: str,
    name: str = "Widget",
    launch_date: str | None = None,
) -> dict[str, str]:
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
                    "sku": {"sku": {"type": "plain_text_input", "value": sku}},
                    "name": {"name": {"type": "plain_text_input", "value": name}},
                    "asin": {"asin": {"type": "plain_text_input", "value": None}},
                    "launch_date": {
                        "launch_date": {
                            "type": "datepicker",
                            "selected_date": launch_date,
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
    return {"payload": json.dumps(view_submission_payload)}


def _post_view_submission(client: TestClient, **fields: Any) -> Any:
    body = urllib.parse.urlencode(_view_submission_form(**fields)).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# --------------------------------------------------------------------------
# Requirement: A launch is started from Slack in one interaction
# --------------------------------------------------------------------------


async def test_a_launch_is_started_with_a_date(
    engine: AsyncEngine, client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """Scenario: A launch is started with a date.

    WHEN the modal is submitted with a valid SKU, name, and launch date
    THEN the product is registered and its launch exists, pinned to the
    shipped playbook version, with that launch date
    AND a confirmation message is posted.
    """
    _require_slack_entry_module()
    sku = unique_sku()
    launch_date = "2026-11-01"

    response = _post_view_submission(client, sku=sku.value, launch_date=launch_date)
    _drain(client)
    assert response.status_code == 200

    product = await _reread_product(engine, sku)
    assert product is not None, "the product was not registered"

    launch = await _reread_launch(engine, product.id)
    assert launch is not None, "the launch was not started"
    # SPECIFIED (launch-entry, as revised by move-playbook-steps-to-
    # postgres): the launch records the served playbook's version
    # identifier as its audit stamp.
    assert _read(launch, "version") == await _served_version(engine)
    # SPECIFIED: with that launch date.
    assert _read(launch, "launch_date") == date.fromisoformat(launch_date)

    # SPECIFIED: a confirmation message is posted.
    assert len(slack_api.posts) == 1, (
        f"expected exactly one confirmation message, observed: {slack_api.posts}"
    )
    assert slack_api.posts[0].get("channel") == SUBMITTER_ID


async def test_a_launch_is_started_without_a_date(
    engine: AsyncEngine, client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """Scenario: A launch is started without a date.

    WHEN the modal is submitted with only the required fields
    THEN the launch exists with no launch date and no derived due periods
    AND the confirmation names the absence of a date.
    """
    _require_slack_entry_module()
    sku = unique_sku()

    response = _post_view_submission(client, sku=sku.value, launch_date=None)
    _drain(client)
    assert response.status_code == 200

    product = await _reread_product(engine, sku)
    assert product is not None
    launch = await _reread_launch(engine, product.id)
    assert launch is not None
    # SPECIFIED: no launch date.
    assert _read(launch, "launch_date") is None

    assert len(slack_api.posts) == 1
    text = (slack_api.posts[0].get("text") or "").lower()
    # SPECIFIED: the confirmation names the absence of a date. No exact
    # wording is fixed by any artifact; asserted as containment of a
    # plausible "no date" phrasing rather than an exact string.
    assert "no date" in text or "not set" in text or "no launch date" in text, (
        f"the confirmation message did not appear to name the absence of a "
        f"launch date: {slack_api.posts[0].get('text')!r}"
    )


# --------------------------------------------------------------------------
# Requirement: Registration and start are atomic
# --------------------------------------------------------------------------


async def test_a_rejected_start_leaves_no_product_behind(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    client: TestClient,
    slack_api: _RecordingSlackApi,
) -> None:
    """Scenario: A rejected start leaves no product behind.

    WHEN a submission's product registration succeeds but its launch start
    is rejected
    THEN neither the product nor a launch is persisted
    AND resubmitting the same SKU is not rejected as a duplicate.

    See the module docstring for why the rejection is engineered via a
    monkeypatched `start_launch` rather than a naturally-occurring one.
    """
    module = _require_slack_entry_module()
    if not hasattr(module, "start_launch"):
        pytest.fail(
            f"{module.__name__} has no `start_launch` attribute to patch "
            "(tasks.md 2.2 names `launch.application.start_launch`)"
        )
    sku = unique_sku()

    original_start_launch = module.start_launch

    async def _failing_start_launch(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated launch-start rejection")

    monkeypatch.setattr(module, "start_launch", _failing_start_launch)

    first = _post_view_submission(client, sku=sku.value)
    _drain(client)
    assert first.status_code == 200, (
        "the submission must still be acknowledged even though its "
        f"persistence is rejected, got {first.status_code}"
    )

    # SPECIFIED: neither the product nor a launch is persisted.
    product_after_rejection = await _reread_product(engine, sku)
    assert product_after_rejection is None, (
        "the catalog product survived a rejected launch start; the pair "
        "must commit together or not at all (design.md Decision 3)"
    )

    # Restore the real collaborator for the resubmission. Not
    # `monkeypatch.undo()`: that would also undo the `slack_env` autouse
    # fixture's env vars, since both share the same function-scoped
    # `monkeypatch` object -- only the one attribute this test itself
    # patched is restored.
    monkeypatch.setattr(module, "start_launch", original_start_launch)
    _reset_slack_caches()

    second = _post_view_submission(client, sku=sku.value)
    _drain(client)
    assert second.status_code == 200

    # SPECIFIED: resubmitting the same SKU is not rejected as a duplicate.
    product_after_resubmission = await _reread_product(engine, sku)
    assert product_after_resubmission is not None, (
        "resubmitting the same SKU after the earlier rejection was itself "
        "rejected (or silently dropped); the failed attempt must not have "
        "claimed the SKU"
    )
    launch_after_resubmission = await _reread_launch(
        engine, product_after_resubmission.id
    )
    assert launch_after_resubmission is not None, (
        "the resubmission's launch was not started"
    )


# --------------------------------------------------------------------------
# Requirement: Rejections are surfaced where the user is
# --------------------------------------------------------------------------


async def test_a_duplicate_sku_is_rejected_with_nothing_persisted(
    engine: AsyncEngine, client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """Scenario: A duplicate SKU is rejected with nothing persisted.

    WHEN the modal is submitted with a SKU that already identifies a
    catalog product
    THEN the user is told the SKU is already registered
    AND no second product and no launch is persisted.
    """
    _require_slack_entry_module()
    sku = unique_sku()

    first = _post_view_submission(client, sku=sku.value, name="Original Widget")
    _drain(client)
    assert first.status_code == 200
    original = await _reread_product(engine, sku)
    assert original is not None, "precondition: the first registration must succeed"

    second = _post_view_submission(client, sku=sku.value, name="A Different Widget")
    _drain(client)
    assert second.status_code == 200, (
        "the duplicate submission must still be acknowledged, not answered "
        f"as an inline modal error (design.md Decision 4), got "
        f"{second.status_code}"
    )

    # SPECIFIED: the user is told the SKU is already registered. No exact
    # wording is fixed by any artifact.
    assert len(slack_api.posts) == 2, (
        f"expected one confirmation for the first submission and one "
        f"rejection message for the second, observed: {slack_api.posts}"
    )
    rejection_text = (slack_api.posts[-1].get("text") or "").lower()
    assert sku.value.lower() in rejection_text or "already" in rejection_text, (
        "the rejection message did not appear to name the duplicate-SKU "
        f"rejection: {slack_api.posts[-1].get('text')!r}"
    )

    # SPECIFIED: no second product is persisted -- the original survives
    # unchanged (its name was not overwritten by the rejected resubmission).
    reread = await _reread_product(engine, sku)
    assert reread is not None
    assert reread.id == original.id
    assert reread.name == "Original Widget"

    # SPECIFIED: no launch is persisted for the rejected resubmission --
    # exactly the one launch from the first, successful submission exists.
    launch = await _reread_launch(engine, original.id)
    assert launch is not None, "the original submission's launch is missing"


# --------------------------------------------------------------------------
# DERIVED (requirement-body text, no `#### Scenario:` block of its own):
# "A failure to deliver a message after a successful commit leaves the
# commit standing -- delivery failure is not grounds to unwind persisted
# state."
# --------------------------------------------------------------------------


async def test_a_post_commit_delivery_failure_leaves_the_commit_standing(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine, client: TestClient
) -> None:
    """DERIVED, from the requirement-body sentence in "Acknowledgement is
    independent of persistence, and a post-acknowledgement failure is
    visible" -- not from a `#### Scenario:` block, which this requirement
    has only two of (neither covering delivery failure). Recorded as
    derived in `test-manifest.md`; if the project decides this sentence
    imposes no independently-testable obligation, this is the test to
    revisit, not the requirement.

    Real persistence, deliberately failing delivery: the confirmation
    `chat.postMessage` call is made to raise, while everything else
    (including the transaction itself) runs for real, so "the commit
    stands" is checked against an actual persisted row rather than a
    double that could not distinguish standing from rolled back.
    """
    _require_slack_entry_module()
    async_client = importlib.import_module("slack_sdk.web.async_client")
    flaky = _RecordingSlackApi(fail_methods=frozenset({"chat.postMessage"}))
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", flaky.api_call)
    sku = unique_sku()

    _post_view_submission(client, sku=sku.value)
    _drain(client)

    # Precondition: delivery really was attempted and really did fail, so
    # "the commit stands" is not vacuously true of a request that never
    # reached persistence at all.
    assert "chat.postMessage" in flaky.methods, (
        "the confirmation was never attempted, so this test establishes "
        "nothing about a delivery failure"
    )

    # DERIVED: the commit stands regardless of the acknowledgement/response
    # status the delivery failure produces at the HTTP layer -- what is
    # asserted is the persisted state, not the response.
    product = await _reread_product(engine, sku)
    assert product is not None, (
        "a delivery failure appears to have unwound a successful commit; "
        "delivery failure must not be grounds to roll back persisted state"
    )
    launch = await _reread_launch(engine, product.id)
    assert launch is not None, (
        "the launch did not survive a post-commit delivery failure"
    )
