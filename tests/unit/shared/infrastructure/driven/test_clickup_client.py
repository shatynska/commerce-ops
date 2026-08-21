"""Tests for the `clickup-task-client` capability's driven adapter.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/add-clickup-task-client/specs/clickup-task-client/spec.md`:

- "A task can be created in a given list" / Scenario: Task created with a
  name only
- "A task can be created in a given list" / Scenario: Task created with a
  name and description
- "An existing task can be updated with caller-supplied fields" / Scenario:
  Task updated with one field
- "An existing task can be updated with caller-supplied fields" / Scenario:
  Task updated with multiple fields
- "An existing task can be updated with caller-supplied fields" / Scenario:
  Task updated with no fields
- "A failed ClickUp request is surfaced to the caller" / Scenario: ClickUp
  rejects a create request
- "A failed ClickUp request is surfaced to the caller" / Scenario: ClickUp
  rejects an update request
- "A failed ClickUp request is surfaced to the caller" / Scenario: ClickUp
  is unreachable
- "Authentication is configured independently of any one caller" /
  Scenario: Credential absent until first use
- "Authentication is configured independently of any one caller" /
  Scenario: Credential absent at call time

See `test-manifest.md` at this change's root for the full
specified/derived/deliberately-untested accounting.

## Names and shapes used here are INVENTED, except where noted as SPECIFIED

`tasks.md`/`design.md` fix, by name:

- Module `shared/infrastructure/driven/clickup_client.py`, exposing
  `create_task(list_id, name, description=None) -> ClickUpTask` (Task 4.2,
  `POST /api/v2/list/{list_id}/task`) and
  `update_task(task_id, fields) -> ClickUpTask` (Task 4.3,
  `PUT /api/v2/task/{task_id}`).
- `shared/domain/clickup.py`'s `ClickUpTask` (`id`, `url`) (Task 2.1).
- `shared/application/ports.py`'s `ClickUpTaskWriter` Protocol, exported
  from `shared/application/__init__.py` (Tasks 3.1/3.2).
- The `CLICKUP_API_TOKEN` env var (`proposal.md`'s Impact section).

Not fixed by any artifact, and therefore INVENTED here, following the
closest existing precedent in this repo
(`omni_agent/infrastructure/driving/slack.py`'s `get_slack_client()`,
a `functools.lru_cache`-wrapped factory design.md explicitly says this
change's own lazy/cached client construction "mirrors"):

- A module-level `get_client() -> httpx.AsyncClient` cached factory in
  `clickup_client.py`, read by `create_task`/`update_task` and reading
  `CLICKUP_API_TOKEN` at call time. This is the seam these tests substitute
  a `httpx.MockTransport`-backed client through, exactly as
  `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`
  substitutes a fake through `get_slack_client()`. If the real factory has a
  different name (or the client is constructed inline per call instead),
  correcting the `getattr(clickup_client, "get_client", ...)` lookups below
  is a fixture correction, not a change to what each test asserts.
- Exactly which of `get_client()` vs. `create_task`/`update_task` themselves
  reads `CLICKUP_API_TOKEN` is also left open by every artifact; the
  "Credential absent" tests below invoke the real, unpatched `create_task`/
  `update_task` (see `forbid_network` below) precisely so this is exercised
  through whichever path the real implementation takes.

## What "an exception is raised" means for the three failure scenarios

`A failed ClickUp request is surfaced to the caller` and `Credential absent
at call time` both state only that the caller receives *an error* -- no
artifact names a specific exception type (design.md's Risks section
mentions `httpx.HTTPStatusError`/`KeyError` as the *expected mechanism*,
but Risks is not a requirement). Every `pytest.raises` below is therefore
scoped to `Exception` broadly, narrowly around the single call under test,
per `ai-toolkit:testing`'s `pytest.raises`-scoping rule -- asserting "some
exception, not a returned `ClickUpTask`" is what the spec actually commits
to; narrowing to a specific type would impose a contract nobody agreed to.

## At the time this pass was written, nothing under test exists

`shared/domain/`, `shared/application/`, and `shared/infrastructure/driven/`
currently declare no `clickup`/`ports`/`clickup_client` modules (only empty
`__init__.py` files). Every test in this file is expected to fail on that
absence (`ModuleNotFoundError`/`ImportError`) until Tasks 2-4 land. Per
`ai-toolkit:testing`'s failure-state taxonomy, that failure establishes only
that the target is absent, nothing about whether the assertions below are
well-formed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from commerce_ops.shared.application import ClickUpTaskWriter
from commerce_ops.shared.domain.clickup import ClickUpTask
from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import (
    create_task,
    update_task,
)

pytestmark = pytest.mark.anyio

TOKEN = "test-clickup-api-token-not-a-real-credential"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio -- see tests/integration/products/conftest.py's own
    # anyio_backend fixture for the reasoning (no trio dependency installed,
    # nothing in this project's artifacts calls for trio support).
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixtures / test doubles
# ---------------------------------------------------------------------------


def _clear_client_cache() -> None:
    """Drops anything the (presumed) `lru_cache`-wrapped `get_client`
    factory memoised, so one test's substituted/real client can't leak into
    the next -- mirrors `test_slack_events_endpoint.py`'s
    `_clear_factory_caches()`.
    """
    factory = getattr(clickup_client, "get_client", None)
    cache_clear = getattr(factory, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


@pytest.fixture(autouse=True)
def _reset_client_cache() -> Iterator[None]:
    _clear_client_cache()
    yield
    _clear_client_cache()


@pytest.fixture()
def configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ambient environment a real, unpatched `get_client()` would read.

    Set defensively for every test that substitutes the client via
    `install_transport` below -- covering the case where `create_task`/
    `update_task` also check the token themselves, not only `get_client()`.
    """
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Substitutes the cached client factory with one backed by
    `httpx.MockTransport(handler)`, so `create_task`/`update_task` never
    reach the real network -- the seam `test_slack_events_endpoint.py`
    documents as "Both substitution points are covered on purpose", applied
    to this adapter's own (invented) factory name.
    """
    original = getattr(clickup_client, "get_client", None)
    assert original is not None, (
        "expected a `get_client()` cached factory in "
        "`shared/infrastructure/driven/clickup_client.py` (design.md: a "
        "lazy, functools.lru_cache-wrapped factory mirroring "
        "omni_agent/infrastructure/driving/slack.py's `get_slack_client()` "
        "is the seam these tests substitute a MockTransport-backed client "
        "through)"
    )
    monkeypatch.setattr(
        clickup_client,
        "get_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def recording_handler(
    response: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """A `MockTransport` handler that records every request it receives and
    always returns `response`."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response

    return handler, captured


def raising_handler(
    exc: Exception,
) -> Callable[[httpx.Request], httpx.Response]:
    """A `MockTransport` handler simulating a transport-level failure (no
    response received at all) -- e.g. a connection error or timeout."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


class _UnexpectedNetworkAttempt(AssertionError):
    """Raised by `forbid_network`'s patched `send` if reached -- proof a
    request was attempted despite the credential being absent."""


@pytest.fixture()
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards the "Credential absent at call time" tests: the real,
    unpatched `create_task`/`update_task` are called (so whichever internal
    path actually reads `CLICKUP_API_TOKEN` is exercised), and this fixture
    fails loudly -- distinguishably from the expected credential failure --
    if any request nonetheless reaches `httpx.AsyncClient.send`.
    """

    async def _blocked_send(
        self: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        raise _UnexpectedNetworkAttempt(
            "a request reached httpx.AsyncClient.send despite "
            "CLICKUP_API_TOKEN being absent from the environment"
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", _blocked_send)


# ---------------------------------------------------------------------------
# Requirement: A task can be created in a given list
# ---------------------------------------------------------------------------


async def test_create_task_with_name_only(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task created with a name only.

    WHEN a task is created with a list identifier and a name, and no
    description
    THEN ClickUp receives a create-task request for that list containing
    the name
    AND the caller receives the created task's identifier and URL.
    """
    response = httpx.Response(
        200, json={"id": "9hz-created", "url": "https://app.clickup.com/t/9hz-created"}
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    task = await create_task(list_id="901234002", name="New product SKU launch")

    # SPECIFIED: ClickUp receives a create-task request for that list.
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v2/list/901234002/task"
    body = json.loads(request.content)
    # SPECIFIED: containing the name.
    assert body["name"] == "New product SKU launch"

    # SPECIFIED: the caller receives the created task's identifier and URL.
    # DERIVED: the returned value is a `ClickUpTask` (design.md's Decisions
    # names this type; the spec text itself only says "identifier and URL").
    assert isinstance(task, ClickUpTask)
    assert task.id == "9hz-created"
    assert task.url == "https://app.clickup.com/t/9hz-created"


async def test_create_task_with_name_and_description(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task created with a name and description.

    WHEN a task is created with a list identifier, a name, and a
    description
    THEN ClickUp receives a create-task request for that list containing
    both the name and the description
    AND the caller receives the created task's identifier and URL.
    """
    response = httpx.Response(
        200,
        json={"id": "9hz-created-2", "url": "https://app.clickup.com/t/9hz-created-2"},
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    task = await create_task(
        list_id="901234002",
        name="New product SKU launch",
        description="Launch the Q3 widget SKU across all marketplaces.",
    )

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v2/list/901234002/task"
    body = json.loads(request.content)
    # SPECIFIED: containing both the name and the description.
    assert body["name"] == "New product SKU launch"
    assert body["description"] == "Launch the Q3 widget SKU across all marketplaces."

    assert task.id == "9hz-created-2"
    assert task.url == "https://app.clickup.com/t/9hz-created-2"


# ---------------------------------------------------------------------------
# Requirement: An existing task can be updated with caller-supplied fields
# ---------------------------------------------------------------------------


async def test_update_task_with_one_field(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task updated with one field.

    WHEN a task is updated by its identifier with one field
    THEN ClickUp receives an update request for that task containing
    exactly that field
    AND the caller receives the updated task's identifier and URL.
    """
    response = httpx.Response(
        200, json={"id": "8x2-updated", "url": "https://app.clickup.com/t/8x2-updated"}
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    task = await update_task(task_id="8x2-updated", fields={"status": "in progress"})

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/api/v2/task/8x2-updated"
    body = json.loads(request.content)
    # SPECIFIED: containing exactly that field.
    assert body == {"status": "in progress"}

    assert task.id == "8x2-updated"
    assert task.url == "https://app.clickup.com/t/8x2-updated"


async def test_update_task_with_multiple_fields(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task updated with multiple fields.

    WHEN a task is updated by its identifier with more than one field
    THEN ClickUp receives an update request for that task containing
    exactly those fields
    AND the caller receives the updated task's identifier and URL.
    """
    response = httpx.Response(
        200,
        json={"id": "8x2-updated-2", "url": "https://app.clickup.com/t/8x2-updated-2"},
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    fields = {"status": "complete", "priority": 2}
    task = await update_task(task_id="8x2-updated-2", fields=fields)

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/api/v2/task/8x2-updated-2"
    body = json.loads(request.content)
    # SPECIFIED: containing exactly those fields.
    assert body == {"status": "complete", "priority": 2}

    assert task.id == "8x2-updated-2"
    assert task.url == "https://app.clickup.com/t/8x2-updated-2"


async def test_update_task_with_no_fields(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task updated with no fields.

    WHEN a task is updated by its identifier with an empty set of fields
    THEN ClickUp receives an update request for that task with an empty
    body
    AND the caller receives the updated task's identifier and URL.

    DERIVED: "an empty body" is read as an empty JSON object (`{}`), the
    natural encoding of an empty `fields` mapping sent as this endpoint's
    JSON body -- the spec text does not itself pin the wire encoding of
    "empty".
    """
    response = httpx.Response(
        200,
        json={"id": "8x2-updated-3", "url": "https://app.clickup.com/t/8x2-updated-3"},
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    task = await update_task(task_id="8x2-updated-3", fields={})

    assert len(captured) == 1
    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/api/v2/task/8x2-updated-3"
    body = json.loads(request.content) if request.content else {}
    assert body == {}

    assert task.id == "8x2-updated-3"
    assert task.url == "https://app.clickup.com/t/8x2-updated-3"


# ---------------------------------------------------------------------------
# Requirement: A failed ClickUp request is surfaced to the caller
# ---------------------------------------------------------------------------


async def test_create_task_rejected_by_clickup_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a create request.

    WHEN ClickUp responds to a create-task request with a non-success
    status
    THEN the caller receives an error and no task identifier.
    """
    response = httpx.Response(
        400, json={"err": "Team not authorized", "ECODE": "OAUTH_017"}
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no specific type is specified, see module docstring
        await create_task(list_id="901234002", name="Rejected task")

    # SPECIFIED precondition: the request was actually attempted, so the
    # failure below traces to ClickUp's rejection, not an earlier problem.
    assert len(captured) == 1
    # SPECIFIED: no task identifier is returned -- `pytest.raises` above
    # already establishes the call never returned a value at all.


async def test_update_task_rejected_by_clickup_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects an update request.

    WHEN ClickUp responds to an update-task request with a non-success
    status
    THEN the caller receives an error and no updated task identifier.
    """
    response = httpx.Response(422, json={"err": "Field not recognized"})
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no specific type is specified, see module docstring
        await update_task(task_id="8x2-rejected", fields={"unknown_field": "value"})

    assert len(captured) == 1


async def test_create_task_when_clickup_is_unreachable_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable (create path).

    WHEN a create-task request cannot reach ClickUp at all (a connection
    failure or timeout, with no response received)
    THEN the caller receives an error and no task identifier.
    """
    install_transport(
        monkeypatch, raising_handler(httpx.ConnectError("simulated ClickUp outage"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- no specific type is specified, see module docstring
        await create_task(list_id="901234002", name="Unreachable task")


async def test_update_task_when_clickup_is_unreachable_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable (update path).

    DERIVED extra coverage: the spec's single "ClickUp is unreachable"
    scenario names both "a create-task or update-task request" in its WHEN
    clause; `tasks.md` 5.4 likewise says "on create or update". The test
    above covers the create path named first; this test covers the update
    path the same scenario also names, so a transport-level failure isn't
    left unverified on whichever path the create-only test doesn't reach.
    """
    install_transport(
        monkeypatch,
        raising_handler(httpx.TimeoutException("simulated ClickUp timeout")),
    )

    with pytest.raises(Exception):  # noqa: B017 -- no specific type is specified, see module docstring
        await update_task(task_id="8x2-unreachable", fields={"status": "done"})


# ---------------------------------------------------------------------------
# Requirement: Authentication is configured independently of any one caller
# ---------------------------------------------------------------------------


def test_importing_the_module_does_not_require_a_configured_credential() -> None:
    """Scenario: Credential absent until first use (import half).

    WHEN the client module is imported ... and no ClickUp credential is
    configured
    THEN nothing fails as a result.

    Run in a fresh interpreter on purpose: within this pytest process the
    module is already imported (see the module-level import above), so an
    in-process import would be a no-op cache hit and would assert nothing
    about import-time behaviour -- mirrors
    `test_main_slack_wiring.py::test_main_imports_without_slack_secrets_in_environment`.

    The scenario's other half ("or the application starts") is inapplicable
    to this change: `proposal.md`'s Impact section states this change adds
    "no FastAPI routes, no `main.py` wiring" -- there is no application
    startup path that reaches this module yet for a later change to regress.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLICKUP_API_TOKEN"}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import commerce_ops.shared.infrastructure.driven.clickup_client",
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing "
        "commerce_ops.shared.infrastructure.driven.clickup_client with "
        "CLICKUP_API_TOKEN absent failed; the client must be constructed "
        "lazily behind a cached factory, never at module import time.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


async def test_create_task_without_a_configured_credential_raises_before_any_request(
    monkeypatch: pytest.MonkeyPatch, forbid_network: None
) -> None:
    """Scenario: Credential absent at call time (create path).

    WHEN a task is created ... and no ClickUp credential is configured
    THEN the caller receives an error, and no request is sent to ClickUp.
    """
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    with pytest.raises(Exception) as caught:
        await create_task(list_id="901234002", name="No credential configured")

    # SPECIFIED: no request is sent to ClickUp -- `forbid_network` raises a
    # distinguishable failure if `httpx.AsyncClient.send` is ever reached;
    # this asserts the *credential* failure was what actually propagated,
    # not that network guard.
    assert not isinstance(caught.value, _UnexpectedNetworkAttempt), (
        "create_task attempted to contact ClickUp despite no credential "
        "being configured"
    )


async def test_update_task_without_a_configured_credential_raises_before_any_request(
    monkeypatch: pytest.MonkeyPatch, forbid_network: None
) -> None:
    """Scenario: Credential absent at call time (update path).

    DERIVED extra coverage, for the same reason as
    `test_update_task_when_clickup_is_unreachable_raises` above: the
    scenario's WHEN clause names "a task is created or updated"
    generically, and `update_task` is a distinct code path from
    `create_task` that could independently fail to check the credential.
    """
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)

    with pytest.raises(Exception) as caught:
        await update_task(task_id="8x2-no-credential", fields={"status": "done"})

    assert not isinstance(caught.value, _UnexpectedNetworkAttempt), (
        "update_task attempted to contact ClickUp despite no credential "
        "being configured"
    )


# ---------------------------------------------------------------------------
# DERIVED, not itself a `#### Scenario:` block (tasks.md 5.6)
# ---------------------------------------------------------------------------


def test_clickup_client_module_satisfies_the_writer_port_structurally() -> None:
    """DERIVED precondition check, matching `tasks.md` 5.6 ("Verify
    `ClickUpTaskWriter` structurally accepts the concrete adapter ...
    matching how `ProductRepository`/`ProductNameReader` is verified").

    Unlike `ProductRepository` (a class instance), design.md's Decisions
    describe this adapter as module-level functions (`create_task`,
    `update_task`) rather than a class -- mypy supports a module satisfying
    a `Protocol` the same way an instance does, so the module object itself
    is assigned to a `ClickUpTaskWriter`-typed variable here, mirroring
    `test_daily_digest.py`'s `reader: ProductNameReader = _FakeReader(...)`.
    If the real adapter is instead a class, correcting this assignment to
    an instance is a fixture correction.
    """
    adapter: ClickUpTaskWriter = clickup_client
    assert hasattr(adapter, "create_task")
    assert hasattr(adapter, "update_task")
