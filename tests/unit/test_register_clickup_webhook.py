"""The ClickUp webhook registration step (`launch-clickup-sync`).

Derived strictly from the delta spec:
`openspec/changes/shift-clickup-completions-to-webhook/specs/launch-clickup-sync/spec.md`,
the single ADDED requirement *The webhook subscription is registered as an
idempotent, non-blocking deploy step*. Covers all eight of its scenarios:

- *A first registration creates a subscription and surfaces its secret* --
  `test_a_first_registration_creates_a_subscription_and_surfaces_its_secret`
- *An existing matching subscription is not recreated* --
  `test_an_existing_matching_subscription_is_not_recreated`
- *A recreated subscription surfaces its secret exactly as a first
  registration does* --
  `test_a_recreated_subscription_surfaces_its_secret_exactly_as_a_first_registration_does`
- *A changed launch folder gets its own fresh subscription* --
  `test_a_changed_launch_folder_gets_its_own_fresh_subscription`
- *An ambiguous workspace takes no action* --
  `test_an_ambiguous_workspace_takes_no_action` (parametrized: zero teams,
  more than one team)
- *A missing public endpoint takes no action* --
  `test_a_missing_public_endpoint_takes_no_action`
- *A registration failure does not block the deployment* --
  `test_a_registration_failure_does_not_block_the_deployment`, plus DERIVED
  extra coverage of a second call site,
  `test_a_registration_failure_at_the_create_call_does_not_block_the_deployment_either`
- *Starting the server performs no registration* --
  `test_starting_the_server_performs_no_registration_of_its_own`

See `test-manifest.md` at this change's root for the full
specified/derived/deliberately-untested accounting.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- Module `src/commerce_ops/register_clickup_webhook.py` (`proposal.md`'s
  Impact section, `design.md`'s Decisions, `tasks.md` 1.1), "mirroring
  `seed_admin.py`'s shape" -- which fixes a `main() -> int` CLI entry
  (`seed_admin.py` literally declares one, and `tasks.md` 1.8 wires this
  step into `Dockerfile`'s CMD chain the same way).
- The idempotency check compares an existing subscription's `endpoint`
  **and** `folder_id` against the currently configured values -- matching
  on the endpoint alone is explicitly ruled out by the requirement's own
  prose.
- The endpoint composition `f"{admin_base_url}/webhooks/clickup/tasks"`
  (`design.md`, "The endpoint URL reuses `admin_base_url`"), and that
  `/webhooks/clickup/tasks` is this deployment's real, already-mounted
  completion route (`launch/infrastructure/driving/clickup_webhook.py`'s
  `WEBHOOK_PATH`, read directly rather than assumed).
- The event subscribed to is `taskStatusUpdated` (`tasks.md` 1.5).
- Every create -- first-ever or a recreation -- logs the ClickUp-generated
  secret at warning level, naming that `CLICKUP_WEBHOOK_SECRET` must be
  set/updated to match (requirement prose, restated by every one of
  scenarios 1/3/4).
  the step "SHALL NOT ... block the deployment ... or prevent the server
  from serving" (requirement prose) -- read the same way
  `test_clickup_sync_job_schedule.py` and `test_clickup_sync_job_stand_down.py`
  already read an equivalent outcome clause for a CLI-style entry point
  (mirroring `test_preflight.py`'s exit-code convention): *the step's own
  outcome signal is its process exit status*, so "does not block the
  deployment" is read as `main()` returning `0` regardless of what failed.
- `GET /api/v2/team` resolving the workspace, and the step doing nothing
  beyond logging where it returns zero or more than one team
  (`design.md`, "The workspace (`team_id`) is resolved at registration
  time, not configured").

INVENTED, each with a correction point named:

- **The HTTP interception seam.** No artifact fixes whether this module
  builds its own cached `httpx.AsyncClient` (mirroring
  `clickup_client.get_client()`) or reuses that adapter's own client, or
  something else entirely. Rather than guess a factory name, every test
  here patches `httpx.AsyncClient.send` directly -- the same seam
  `test_clickup_client.py`'s `forbid_network` fixture already uses for the
  same reason, and one that holds regardless of how the real client is
  constructed, as long as it is an `httpx.AsyncClient` (the only HTTP
  client this codebase's ClickUp-facing code has ever used). Correction
  point: `install_transport`.
- **Whether settings are read through `get_settings()` or directly from
  `os.environ`.** `design.md`'s prose writes `settings.admin_base_url` /
  `settings.clickup_launch_folder_id`, which reads as `get_settings()`
  usage: but `launch/infrastructure/driving/clickup_webhook.py` -- this
  step's own explicitly-named sibling and model, handling the *other*
  half of this same capability -- reads its one optional, capability-scoped
  setting (`CLICKUP_WEBHOOK_SECRET`) directly from `os.environ` "rather
  than through `get_settings()`", for a reason (`runtime-configuration`'s
  "a module may read a variable directly where routing it through the
  declaration would defeat required behavior") that applies identically to
  this step's three optional settings. Nothing here commits to either
  reading path: `_baseline_environment()` below sets every *other*
  required `Settings` field to a disposable value regardless, so a test's
  outcome turns on the one thing each scenario actually states rather than
  on an unrelated required field this step's implementation happens to
  touch through `get_settings()`'s whole-model validation. Correction
  point: none needed either way -- environment variables satisfy both
  reading paths at once.
- **The realistic ClickUp response shapes.** `GET /api/v2/team` answering
  `{"teams": [...]}`, `GET .../webhook` answering `{"webhooks": [...]}`
  with `endpoint`/`folder_id` fields (`tasks.md` 1.2/1.4's own wording),
  and the create response carrying the generated `secret` are this file's
  best-effort reconstruction of ClickUp's public API, not fixed by any
  project artifact. The create response below carries `secret` at *both*
  the payload's top level and nested under a `webhook` key, deliberately:
  no artifact fixes which of the two a real implementation reads from, and
  duplicating the value removes that guess from what each test actually
  constrains (that the secret ClickUp returned ends up in the warning
  log), without weakening it. Correction point: `_create_response`,
  `_team_response`, `_webhook_list_response`.
- **`main()` imported lazily, per test, rather than at module level.**
  Every sibling file that tests an absent target under this project's own
  convention (`test_clickup_client.py`, `test_clickup_webhook.py`) imports
  it at module scope, so the whole file fails at collection until the
  target lands. This file instead imports `register_clickup_webhook.main`
  inside the `register_main` fixture, used only by the seven tests that
  need it. `test_starting_the_server_performs_no_registration_of_its_own`
  does not depend on the missing module at all -- it is a `main.py`-level
  regression guard, exactly like the two tests
  `test_clickup_sync_job_containment.py`'s own docstring records as
  "expected to pass before the implementation lands" -- and the deferred
  import lets it keep running and passing today, rather than being swept
  into a whole-file collection error alongside the seven tests that
  legitimately have nothing to assert yet.

## At the time this pass was written, the module does not exist

`src/commerce_ops/register_clickup_webhook.py` is created by `tasks.md`
1.1. Every test that depends on `register_main` fails today with
`ModuleNotFoundError` raised from that fixture's own import -- a
per-test failure, not a whole-file collection error (see above). Per
`ai-toolkit:testing`, that failure establishes only that the target is
absent, nothing about whether the assertions below are well-formed.

Baseline recorded before this file was added: `uv run pytest tests/unit
tests/agents` -- 1689 passed, 0 failed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

TOKEN = "test-clickup-api-token-not-a-real-credential"
TEAM_ID = "900200300"
FOLDER_ID = "701122334455"
STALE_FOLDER_ID = "600011122233"
ADMIN_BASE_URL = "https://admin.example.com"
# `clickup_webhook.py`'s own `WEBHOOK_PATH` -- read from source, not
# assumed, so this file breaks loudly if that route is ever renamed.
COMPLETION_PATH = "/webhooks/clickup/tasks"
ENDPOINT = f"{ADMIN_BASE_URL}{COMPLETION_PATH}"
SECRET = "sk_generated_by_clickup_1a2b3c4d5e6f"

TEAM_PATH = "/api/v2/team"


def _webhook_path(team_id: str = TEAM_ID) -> str:
    return f"/api/v2/team/{team_id}/webhook"


def _confirm_completion_path() -> None:
    from commerce_ops.launch.infrastructure.driving.clickup_webhook import (
        WEBHOOK_PATH,
    )

    assert WEBHOOK_PATH == COMPLETION_PATH, (
        "clickup_webhook.py's WEBHOOK_PATH changed; correct COMPLETION_PATH "
        f"above to match (found {WEBHOOK_PATH!r})"
    )


_confirm_completion_path()


# ---------------------------------------------------------------------------
# Settings environment
# ---------------------------------------------------------------------------


def _baseline_environment() -> dict[str, str]:
    """Every `Settings` field this change never touches, filled with
    disposable values -- transcribed from `tests/unit/test_preflight.py`'s
    own `_complete_environment()`/`REQUIRED_NOT_STARTUP_CRITICAL`. See the
    module docstring's INVENTED section for why this is set regardless of
    which reading path the real implementation takes.
    """
    return {
        "DATABASE_URL": "postgresql+asyncpg://commerce_ops:pw@postgres:5432/commerce_ops",
        "OPENAI_API_KEY": "value-for-openai_api_key",
        "OMNI_AGENT_SLACK_SIGNING_SECRET": "value-for-omni_agent_slack_signing_secret",
        "OMNI_AGENT_SLACK_BOT_TOKEN": "value-for-omni_agent_slack_bot_token",
        "PRODUCT_AGENT_SLACK_BOT_TOKEN": "value-for-product_agent_slack_bot_token",
        "PRODUCT_AGENT_MONITORING_CHANNEL_ID": (
            "value-for-product_agent_monitoring_channel_id"
        ),
        "PRODUCT_AGENT_SLACK_SIGNING_SECRET": (
            "value-for-product_agent_slack_signing_secret"
        ),
    }


def _clear_settings_cache() -> None:
    from commerce_ops.shared.application.settings import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _baseline(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key, value in _baseline_environment().items():
        monkeypatch.setenv(key, value)
    _clear_settings_cache()
    yield
    _clear_settings_cache()


@pytest.fixture()
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The three optional settings this step reads, all present."""
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLICKUP_LAUNCH_FOLDER_ID", FOLDER_ID)
    monkeypatch.setenv("ADMIN_BASE_URL", ADMIN_BASE_URL)
    _clear_settings_cache()


@pytest.fixture()
def register_main() -> Callable[[], int]:
    """`register_clickup_webhook.main`, imported lazily -- see the module
    docstring's INVENTED section for why this is a fixture rather than a
    module-level import."""
    from commerce_ops.register_clickup_webhook import main

    return main


# ---------------------------------------------------------------------------
# The ClickUp API double
# ---------------------------------------------------------------------------


def _team_response(teams: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"teams": teams})


def _webhook_list_response(webhooks: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"webhooks": webhooks})


def _create_response(
    secret: str = SECRET, webhook_id: str = "wh-created"
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": webhook_id,
            # Duplicated at both plausible locations -- see the module
            # docstring.
            "secret": secret,
            "webhook": {
                "id": webhook_id,
                "endpoint": ENDPOINT,
                "secret": secret,
                "status": "active",
            },
        },
    )


@dataclass
class ClickUpDouble:
    """Stands in for ClickUp's team/webhook endpoints.

    Records every request it receives, in order, before deciding how to
    answer it -- so a request that provokes a simulated failure is still
    visible to a test that only inspects `captured`.
    """

    teams: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    create_response: httpx.Response = field(default_factory=_create_response)
    team_failure: Exception | None = None
    create_failure: Exception | None = None
    captured: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.captured.append(request)
        path = request.url.path

        if request.method == "GET" and path == TEAM_PATH:
            if self.team_failure is not None:
                raise self.team_failure
            return _team_response(self.teams)

        if request.method == "GET" and path == _webhook_path():
            return _webhook_list_response(self.webhooks)

        if request.method == "POST" and path == _webhook_path():
            if self.create_failure is not None:
                raise self.create_failure
            return self.create_response

        return httpx.Response(
            404, json={"err": f"unmapped path in test double: {request.method} {path}"}
        )


def install_transport(monkeypatch: pytest.MonkeyPatch, double: ClickUpDouble) -> None:
    """Substitutes every `httpx.AsyncClient` this process constructs with
    one whose requests are answered by `double`. See the module docstring's
    INVENTED section for why this patches `httpx.AsyncClient.send` directly
    rather than a guessed factory name."""

    async def _send(
        self: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        return double.handle(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", _send)


def _requests(double: ClickUpDouble, method: str, path: str) -> list[httpx.Request]:
    return [r for r in double.captured if r.method == method and r.url.path == path]


def _created_requests(double: ClickUpDouble) -> list[httpx.Request]:
    return _requests(double, "POST", _webhook_path())


def _warning_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


# ---------------------------------------------------------------------------
# Scenario: A first registration creates a subscription and surfaces its
# secret
# ---------------------------------------------------------------------------


def test_a_first_registration_creates_a_subscription_and_surfaces_its_secret(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A first registration creates a subscription and surfaces
    its secret.

    WHEN the step runs and no subscription targets this deployment's
    endpoint
    THEN a subscription is created, scoped to the configured launch folder
    and to task status change events
    AND the secret ClickUp returns for it is logged at warning level,
    naming that the deployment's signing secret must be set to match.
    """
    double = ClickUpDouble(teams=[{"id": TEAM_ID, "name": "Only Team"}], webhooks=[])
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    # DERIVED: "does not block the deployment" read as exit 0 -- see module
    # docstring. Not itself this scenario's outcome, but a guard that the
    # happy path is not itself somehow reported as a fault.
    assert result == 0

    created = _created_requests(double)
    # SPECIFIED: a subscription is created.
    assert len(created) == 1, (
        f"expected exactly one create request, got {len(created)}: "
        f"{[r.url for r in double.captured]}"
    )
    body = json.loads(created[0].content)
    # SPECIFIED: scoped to the configured launch folder...
    assert body.get("folder_id") == FOLDER_ID
    # SPECIFIED: ...and to task status change events. The specific event
    # name is DERIVED from `tasks.md` 1.5 ("taskStatusUpdated"); the spec
    # text itself says only "task status change events".
    assert body.get("events") == ["taskStatusUpdated"]
    # SPECIFIED (requirement prose): the endpoint composed from
    # `admin_base_url`.
    assert body.get("endpoint") == ENDPOINT
    # DERIVED (`design.md`'s Decisions, "Registration ships as ... never
    # sends [a secret]"): the create request itself carries no
    # caller-supplied secret.
    assert "secret" not in body

    # SPECIFIED: the secret ClickUp returns is logged at warning level,
    # naming that the deployment's signing secret must be set to match.
    warnings = " ".join(_warning_messages(caplog))
    assert SECRET in warnings, (
        f"the ClickUp-generated secret was not logged at warning level: "
        f"{caplog.records!r}"
    )
    assert "CLICKUP_WEBHOOK_SECRET" in warnings, (
        "the warning did not name the deployment's signing secret that "
        f"must be set to match: {warnings!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: An existing matching subscription is not recreated
# ---------------------------------------------------------------------------


def test_an_existing_matching_subscription_is_not_recreated(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
) -> None:
    """Scenario: An existing matching subscription is not recreated.

    WHEN the step runs and a subscription already targets both this
    deployment's endpoint and the configured launch folder
    THEN no new subscription is created.
    """
    double = ClickUpDouble(
        teams=[{"id": TEAM_ID}],
        webhooks=[{"id": "wh-existing", "endpoint": ENDPOINT, "folder_id": FOLDER_ID}],
    )
    install_transport(monkeypatch, double)

    result = register_main()

    assert result == 0
    # SPECIFIED: no new subscription is created.
    assert _created_requests(double) == [], (
        "a subscription was created despite an existing one already "
        f"matching endpoint and folder: {[r.url for r in double.captured]}"
    )


# ---------------------------------------------------------------------------
# Scenario: A recreated subscription surfaces its secret exactly as a first
# registration does
# ---------------------------------------------------------------------------


def test_a_recreated_subscription_surfaces_its_secret_exactly_as_a_first_registration_does(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A recreated subscription surfaces its secret exactly as a
    first registration does.

    WHEN the step runs, no subscription currently targets both this
    deployment's endpoint and the configured launch folder, and one
    matching both previously did before being removed
    THEN a subscription is created and its ClickUp-generated secret is
    logged at warning level, exactly as on a first registration -- the
    step does not distinguish the two, since it has no record of a
    subscription ever having existed before.

    Modelled as: the list ClickUp answers with carries one subscription
    that matches neither this endpoint nor this folder (standing in for
    "some other integration's registration, unrelated to the one that was
    removed") -- proving the create-and-log behaviour is not conditioned on
    the webhook list being empty overall, only on the absence of a match.
    """
    double = ClickUpDouble(
        teams=[{"id": TEAM_ID}],
        webhooks=[
            {
                "id": "wh-unrelated",
                "endpoint": "https://unrelated-deploy.example.com/webhooks/clickup/tasks",
                "folder_id": "999888777",
            }
        ],
    )
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    assert result == 0
    created = _created_requests(double)
    # SPECIFIED: a subscription is created ...
    assert len(created) == 1
    # ... and its secret is logged, exactly as scenario 1 asserts.
    warnings = " ".join(_warning_messages(caplog))
    assert SECRET in warnings and "CLICKUP_WEBHOOK_SECRET" in warnings, (
        "a recreated subscription's secret was logged differently than a "
        f"first registration's: {warnings!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A changed launch folder gets its own fresh subscription
# ---------------------------------------------------------------------------


def test_a_changed_launch_folder_gets_its_own_fresh_subscription(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A changed launch folder gets its own fresh subscription.

    WHEN the step runs, the configured launch folder differs from the one
    a prior subscription was scoped to, and that prior subscription still
    exists in ClickUp
    THEN a new subscription is created scoped to the currently configured
    folder, and its secret is logged exactly as on a first registration
    AND the prior subscription is left as it is -- the step neither
    deletes it nor treats it as satisfying the check.
    """
    double = ClickUpDouble(
        teams=[{"id": TEAM_ID}],
        # Endpoint matches exactly; folder does not -- explicitly not a
        # match per the requirement's own prose.
        webhooks=[
            {
                "id": "wh-stale-folder",
                "endpoint": ENDPOINT,
                "folder_id": STALE_FOLDER_ID,
            }
        ],
    )
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    assert result == 0
    created = _created_requests(double)
    # SPECIFIED: a new subscription is created scoped to the currently
    # configured folder.
    assert len(created) == 1
    body = json.loads(created[0].content)
    assert body.get("folder_id") == FOLDER_ID

    warnings = " ".join(_warning_messages(caplog))
    # SPECIFIED: its secret is logged exactly as on a first registration.
    assert SECRET in warnings and "CLICKUP_WEBHOOK_SECRET" in warnings

    # SPECIFIED: the prior subscription is left as it is -- neither deleted
    # nor modified. Every captured request is a GET or the one POST create
    # above; nothing targets `wh-stale-folder` with a mutating method.
    non_get_post = [r for r in double.captured if r.method not in {"GET", "POST"}]
    assert non_get_post == [], (
        "a request other than GET/POST reached ClickUp, so the prior "
        f"subscription may have been modified or deleted: {non_get_post!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: An ambiguous workspace takes no action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "teams",
    [
        pytest.param([], id="zero-teams"),
        pytest.param([{"id": "1"}, {"id": "2"}], id="more-than-one-team"),
    ],
)
def test_an_ambiguous_workspace_takes_no_action(
    teams: list[dict[str, Any]],
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: An ambiguous workspace takes no action.

    WHEN the step runs and the configured credentials resolve to no
    ClickUp workspace or to more than one
    THEN no subscription is created or checked for
    AND the ambiguity is logged.
    """
    double = ClickUpDouble(teams=teams)
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    assert result == 0
    # SPECIFIED: no subscription is created or checked for -- neither the
    # existing-subscription read nor a create ever reaches the webhook
    # path.
    webhook_calls = [r for r in double.captured if r.url.path == _webhook_path()]
    assert webhook_calls == [], (
        "the step checked for or created a subscription despite an "
        f"ambiguous workspace: {webhook_calls!r}"
    )
    # SPECIFIED: the ambiguity is logged.
    assert _warning_messages(caplog), (
        "an ambiguous workspace produced no warning-level log record"
    )


# ---------------------------------------------------------------------------
# Scenario: A missing public endpoint takes no action
# ---------------------------------------------------------------------------


def test_a_missing_public_endpoint_takes_no_action(
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A missing public endpoint takes no action.

    WHEN the step runs and this deployment's own public endpoint is not
    configured
    THEN no subscription is created
    AND the gap is logged.
    """
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLICKUP_LAUNCH_FOLDER_ID", FOLDER_ID)
    monkeypatch.delenv("ADMIN_BASE_URL", raising=False)
    _clear_settings_cache()

    # A resolvable, unambiguous workspace, so a create-suppressing effect
    # is attributable to the missing endpoint alone, not to an incidental
    # workspace-ambiguity fault too.
    double = ClickUpDouble(teams=[{"id": TEAM_ID}], webhooks=[])
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    assert result == 0
    # SPECIFIED: no subscription is created.
    assert _created_requests(double) == [], (
        "a subscription was created despite no public endpoint being "
        f"configured: {[r.url for r in double.captured]}"
    )
    # SPECIFIED: the gap is logged.
    assert _warning_messages(caplog), (
        "a missing public endpoint produced no warning-level log record"
    )


# ---------------------------------------------------------------------------
# Scenario: A registration failure does not block the deployment
# ---------------------------------------------------------------------------


def test_a_registration_failure_does_not_block_the_deployment(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A registration failure does not block the deployment.

    WHEN the step runs and the call to ClickUp fails for any reason
    THEN the failure is logged as a warning naming the reason
    AND the deployment proceeds and the server begins serving, exactly as
    if the step had succeeded -- read as `main()` returning `0` (see
    module docstring).
    """
    failure = httpx.ConnectError("simulated ClickUp outage")
    double = ClickUpDouble(team_failure=failure)
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    # SPECIFIED: the deployment proceeds -- never a non-zero exit, never a
    # propagated exception.
    assert result == 0, (
        "a ClickUp API failure was allowed to fail the step's own exit "
        "status, which would block the deployment"
    )
    # SPECIFIED: the failure is logged as a warning naming the reason.
    warnings = " ".join(_warning_messages(caplog))
    assert warnings, "a ClickUp API failure produced no warning-level log record"
    assert "simulated ClickUp outage" in warnings or "ConnectError" in warnings, (
        f"the warning did not name the reason the call failed: {warnings!r}"
    )


def test_a_registration_failure_at_the_create_call_does_not_block_the_deployment_either(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    register_main: Callable[[], int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DERIVED extra coverage of the same scenario at a second call site.

    The scenario's WHEN clause names "the call to ClickUp" generically,
    without pinning which of the step's three calls (team resolution,
    existing-subscription read, create) it covers.
    `test_clickup_client.py` gives the same generic wording extra coverage
    across its own create/update paths for the identical reason; this
    mirrors that, covering the create call specifically -- reachable only
    once team resolution and the existing-subscription read have both
    already succeeded.
    """
    failure = httpx.HTTPStatusError(
        "500 Internal Server Error",
        request=httpx.Request("POST", f"https://api.clickup.com{_webhook_path()}"),
        response=httpx.Response(500),
    )
    double = ClickUpDouble(teams=[{"id": TEAM_ID}], webhooks=[], create_failure=failure)
    install_transport(monkeypatch, double)

    with caplog.at_level(logging.WARNING):
        result = register_main()

    assert result == 0
    assert _warning_messages(caplog), (
        "a failed create call produced no warning-level log record"
    )


# ---------------------------------------------------------------------------
# Scenario: Starting the server performs no registration
# ---------------------------------------------------------------------------


class _UnexpectedNetworkAttempt(AssertionError):
    """Raised by the patched `send` below if reached -- proof a request was
    attempted during server startup or a request cycle."""


@pytest.fixture()
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _blocked_send(
        self: httpx.AsyncClient, request: httpx.Request, **kwargs: Any
    ) -> httpx.Response:
        raise _UnexpectedNetworkAttempt(
            f"unexpected outbound request during server startup/serving: "
            f"{request.method} {request.url}"
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", _blocked_send)


def test_starting_the_server_performs_no_registration_of_its_own(
    forbid_network: None,
) -> None:
    """Scenario: Starting the server performs no registration.

    WHEN the serving process starts
    THEN it performs no webhook registration of its own, leaving that
    entirely to the step that already ran before it.

    Does not depend on the not-yet-written `register_clickup_webhook`
    module at all -- see the module docstring's INVENTED section. Expected
    to pass already, today: `commerce_ops.main` does not reference this
    step, and this test's job is to catch a regression the moment it
    might, not to establish new behaviour.
    """
    from commerce_ops.main import app

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The exact internal collaborator/helper names `main()` is built from
#   (`tasks.md` calls only for "a thin main()/CLI entry over testable
#   helper functions", naming none of them). Every test here observes the
#   step only from its two edges -- the HTTP calls it makes and the
#   process exit status/log records it produces -- which needs no name.
# - Which of `get_settings()` or direct `os.environ` reads the step's three
#   optional settings, and the exact internal call order between team
#   resolution and the `admin_base_url` guard (`tasks.md` 1.2 before 1.3,
#   but that ordering is `tasks.md`'s only, not the spec text's). Recorded
#   as an unresolved project question in `test-manifest.md`.
# - What token scope/permission `CLICKUP_API_TOKEN` needs for webhook
#   management. `design.md`'s own Open Questions leaves this open
#   deliberately, stating no branch of the answer changes this design.
# - Retry behaviour on a failed ClickUp call. No scenario states one, and
#   the requirement's own "does not block the deployment" reads as
#   "attempted once, then given up on for this run" -- `design.md` names
#   no retry.
# ---------------------------------------------------------------------------
