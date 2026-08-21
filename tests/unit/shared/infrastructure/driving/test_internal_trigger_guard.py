"""Tests for the `internal-trigger` capability's shared guard dependency.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/add-product-agent-daily-digest/specs/internal-trigger/spec.md`:

- "Trigger Secret Is Required" / Scenario: Missing secret is rejected
- "Trigger Secret Is Required" / Scenario: Incorrect secret is rejected
- "Correct Secret Is Accepted" / Scenario: Matching secret is accepted
- "Guard Fails Closed When Unconfigured" / Scenario: Trigger secret is not
  configured

See `test-manifest.md` at this change's root for the full
specified/derived/deliberately-untested accounting, including why
"Secret Comparison Is Constant-Time" / Scenario: Comparison uses
constant-time equality is recorded as uncovered rather than tested here.

## The guard's module path and callable name are INVENTED

No artifact in this change fixes a module path or a callable name for the
guard -- `tasks.md` 1.1 says only "Add a `TRIGGER_SECRET`-backed FastAPI
dependency in `shared/infrastructure/`". This file assumes:

- Module: `commerce_ops.shared.infrastructure.driving.trigger_guard` (the
  `driving` layer, alongside `shared/infrastructure/driving/health.py`,
  since the guard exists specifically to protect a *driving* HTTP endpoint).
- Callable: `require_trigger_secret`, an async FastAPI dependency that
  raises `fastapi.HTTPException(status_code=401)` on rejection and returns
  normally (invoking nothing further itself -- FastAPI's own dependency
  resolution is what then proceeds to the route handler) on acceptance.
- The configured secret is read from the `TRIGGER_SECRET` environment
  variable -- this part is SPECIFIED, by name, in `proposal.md`'s "New
  runtime secrets" bullet.
- The presented value arrives via an `Authorization: Bearer <value>` header
  -- SPECIFIED by the delta spec's own Purpose and requirement text ("a
  bearer-secret header").

If the real implementation differs in module path, callable name, or how
the dependency is attached to a route, correcting the import or the
`_build_app` helper below is a **fixture correction** (failure state 3 in
`ai-toolkit:testing`), not a change to what each test asserts: the
observable pass/reject outcome and whether the handler ran are what trace
to the spec, and those must survive any such correction unweakened.

At the time this pass was written, `shared/infrastructure/driving/` (and
the underlying `commerce_ops.shared.infrastructure.driving` package) does
not yet declare a `trigger_guard` module, so every test in this file is
expected to fail on that absence (`ModuleNotFoundError`) until Task 1
lands. Per `ai-toolkit:testing`'s failure-state taxonomy, that failure
establishes only that the target is absent, nothing about whether the
assertions below are well-formed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from commerce_ops.shared.infrastructure.driving.trigger_guard import (
    require_trigger_secret,
)

TRIGGER_SECRET = "test-trigger-secret-not-a-real-credential"


def _build_app(handler_calls: list[str]) -> FastAPI:
    """A minimal app with one route guarded by the dependency under test.

    The smallest unit that can observe "the handler was/was not invoked" is
    an actual wired route -- the guard is a `Depends()` dependency, not a
    freestanding function whose return value alone says whether a handler
    would run.
    """
    app = FastAPI()

    @app.post("/guarded", dependencies=[Depends(require_trigger_secret)])
    def guarded() -> dict[str, bool]:
        handler_calls.append("handled")
        return {"handled": True}

    return app


@pytest.fixture()
def handler_calls() -> list[str]:
    return []


@pytest.fixture()
def client(handler_calls: list[str]) -> Iterator[TestClient]:
    with TestClient(_build_app(handler_calls)) as test_client:
        yield test_client


@pytest.fixture()
def configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ambient environment the guard reads its configured secret from."""
    monkeypatch.setenv("TRIGGER_SECRET", TRIGGER_SECRET)


# ---------------------------------------------------------------------------
# Requirement: Trigger Secret Is Required
# ---------------------------------------------------------------------------


def test_missing_authorization_header_is_rejected(
    configured_secret: None, client: TestClient, handler_calls: list[str]
) -> None:
    """Scenario: Missing secret is rejected.

    WHEN a request to an internal-trigger-guarded endpoint carries no
    `Authorization` header
    THEN the system SHALL reject the request with a 401 response and SHALL
    NOT invoke the endpoint's handler.
    """
    response = client.post("/guarded")

    # SPECIFIED: rejected with exactly 401.
    assert response.status_code == 401
    # SPECIFIED: the handler was not invoked.
    assert handler_calls == []


def test_incorrect_secret_is_rejected(
    configured_secret: None, client: TestClient, handler_calls: list[str]
) -> None:
    """Scenario: Incorrect secret is rejected.

    WHEN a request carries an `Authorization` bearer value that does not
    match the configured trigger secret
    THEN the system SHALL reject the request with a 401 response and SHALL
    NOT invoke the endpoint's handler.
    """
    response = client.post(
        "/guarded", headers={"Authorization": "Bearer an-entirely-wrong-secret"}
    )

    assert response.status_code == 401
    assert handler_calls == []


def test_secret_that_is_a_prefix_of_the_real_one_is_still_rejected(
    configured_secret: None, client: TestClient, handler_calls: list[str]
) -> None:
    """DERIVED, not itself a named scenario.

    A prefix of the configured secret is still an incorrect secret. This
    guards specifically against an implementation that accidentally accepts
    any value sharing the configured secret's first N characters -- a
    plausible bug shape for a hand-rolled comparison, distinct from the
    constant-*timing* property recorded as uncovered above.
    """
    response = client.post(
        "/guarded",
        headers={
            "Authorization": f"Bearer {TRIGGER_SECRET[: len(TRIGGER_SECRET) - 1]}"
        },
    )

    assert response.status_code == 401
    assert handler_calls == []


# ---------------------------------------------------------------------------
# Requirement: Correct Secret Is Accepted
# ---------------------------------------------------------------------------


def test_matching_secret_is_accepted(
    configured_secret: None, client: TestClient, handler_calls: list[str]
) -> None:
    """Scenario: Matching secret is accepted.

    WHEN a request carries an `Authorization` bearer value equal to the
    configured trigger secret
    THEN the system SHALL invoke the endpoint's handler.
    """
    response = client.post(
        "/guarded", headers={"Authorization": f"Bearer {TRIGGER_SECRET}"}
    )

    # DERIVED: the handler ran and its own response came back -- the
    # spec asserts only that the handler is invoked, not any particular
    # status code, but a 2xx with the handler's own body is the direct
    # observable consequence of invocation in this fixture app.
    assert response.status_code == 200
    assert handler_calls == ["handled"]


# ---------------------------------------------------------------------------
# Requirement: Guard Fails Closed When Unconfigured
# ---------------------------------------------------------------------------


def test_every_request_is_rejected_when_secret_is_unconfigured_and_no_header_sent(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, handler_calls: list[str]
) -> None:
    """Scenario: Trigger secret is not configured (no header sent).

    WHEN the trigger secret is absent from the running environment
    THEN the system SHALL reject every request to a guarded endpoint.
    """
    monkeypatch.delenv("TRIGGER_SECRET", raising=False)

    response = client.post("/guarded")

    assert response.status_code == 401
    assert handler_calls == []


def test_every_request_is_rejected_when_secret_is_unconfigured_even_with_a_header(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, handler_calls: list[str]
) -> None:
    """Scenario: Trigger secret is not configured (a bearer value is sent
    anyway).

    "SHALL reject every request" is read as covering a request that does
    present some bearer value, not only the no-header case above --
    otherwise an implementation could pass this requirement's scenario
    while accepting any presented value once unconfigured, which is exactly
    the "allowing requests through" the requirement says must not happen.
    """
    monkeypatch.delenv("TRIGGER_SECRET", raising=False)

    response = client.post(
        "/guarded", headers={"Authorization": "Bearer whatever-value-a-caller-sends"}
    )

    assert response.status_code == 401
    assert handler_calls == []
