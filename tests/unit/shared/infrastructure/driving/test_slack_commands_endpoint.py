"""Tests for the diagnostic `/slack/commands` endpoint.

Not derived from any spec -- this route is a temporary diagnostic tool (see
its docstring in slack.py) added to isolate whether Slack can reach this
server at all, independent of Events API delivery.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.main import app
from commerce_ops.shared.infrastructure.driving import slack as slack_adapter

SLACK_COMMANDS_PATH = "/slack/commands"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("OMNI_AGENT_SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("OMNI_AGENT_SLACK_BOT_TOKEN", "xoxb-test-not-a-real-token")
    slack_adapter.get_signature_verifier.cache_clear()
    slack_adapter.get_slack_client.cache_clear()
    yield
    slack_adapter.get_signature_verifier.cache_clear()
    slack_adapter.get_slack_client.cache_clear()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
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


def test_valid_signed_request_gets_a_pong(client: TestClient) -> None:
    body = b"command=%2Fomni-ping&text=&user_id=U0TEST"

    response = client.post(
        SLACK_COMMANDS_PATH, content=body, headers=_signed_headers(body)
    )

    assert response.status_code == 200
    assert "pong" in response.json()["text"]


def test_unsigned_request_is_rejected(client: TestClient) -> None:
    body = b"command=%2Fomni-ping&text=&user_id=U0TEST"

    response = client.post(
        SLACK_COMMANDS_PATH,
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert 400 <= response.status_code < 500
