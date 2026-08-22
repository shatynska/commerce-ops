"""Driving adapter: Slack Events API endpoint for `omni_agent`, on Bolt.

Implements the `slack-trigger` capability. Bolt owns request verification,
the `url_verification` challenge, event dispatch and acknowledgement timing;
this module owns the listener, the credentials, and the predicate deciding
which requests need a reply credential.

Credentials are read directly from `os.environ` rather than through
`get_settings()`: `runtime-configuration` permits a direct read "where
per-request tolerance of absence is itself required behavior", and rejecting
an unverifiable request with 401 rather than raising is exactly that. Both
variables remain declared in the settings model, so the startup check still
reports them by name.
"""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Mapping
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from commerce_ops.omni_agent.application import answer_question
from commerce_ops.shared.infrastructure.driving.slack_app import (
    SlackAppSpec,
    get_slack_app,
    register_slack_app,
)

router = APIRouter()

_MENTION_TOKEN_RE = re.compile(r"<@[^>]+>\s*")

SLACK_APP_IDENTITY: Final = "omni_agent"
SIGNING_SECRET_VAR: Final = "OMNI_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR: Final = "OMNI_AGENT_SLACK_BOT_TOKEN"

# The only event type this module answers. Anything else it merely
# acknowledges, so it needs no reply credential.
_REPLYING_EVENT_TYPE: Final = "app_mention"

_FAILURE_MESSAGE: Final = "Sorry, I ran into an error while trying to answer that."


def _signing_secret() -> str | None:
    # The variable name is written as a literal here, and in every read
    # below, on purpose: the environment-drift check parses the source for
    # `os.environ[...]` / `.get(...)` with a *constant* argument, so passing
    # the module constant instead would make these reads invisible to it.
    return os.environ.get("OMNI_AGENT_SLACK_SIGNING_SECRET")


def _bot_token() -> str | None:
    """Reports absence as a falsy value, never by raising.

    The credential gate calls this inside a Bolt middleware, where a
    `KeyError` would escape to Bolt's outer handler and become a 500 -- the
    outcome the credential requirement forbids as explicitly as it forbids an
    acknowledgement.
    """
    return os.environ.get("OMNI_AGENT_SLACK_BOT_TOKEN")


def _is_bot_authored(event: Mapping[str, Any]) -> bool:
    """True when the event was authored by a program rather than a person.

    Keyed on how the message was authored, never on which person authored it,
    so it does not restrict which workspace members may trigger Omni.
    """
    return bool(event.get("bot_id")) or event.get("subtype") == "bot_message"


def will_reply(body: Mapping[str, Any]) -> bool:
    """Whether handling this request will attempt a reply.

    A predicate rather than a list of exempt cases: enumerating exemptions
    proved one case short three times over. Anything not recognised as
    reply-free is treated as replying, so a request class this module does
    not yet handle -- a slash command, an interactivity payload -- fails
    closed.
    """
    if body.get("type") != "event_callback":
        return True

    event = body.get("event") or {}
    if not isinstance(event, Mapping):
        return True

    if event.get("type") != _REPLYING_EVENT_TYPE:
        # No listener replies to this type, so it is only acknowledged.
        return False

    # A bot-authored mention is acknowledged and dropped, so it needs no
    # reply credential either.
    return not _is_bot_authored(event)


register_slack_app(
    SLACK_APP_IDENTITY,
    SlackAppSpec(
        signing_secret_provider=_signing_secret,
        bot_token_provider=_bot_token,
        will_reply=will_reply,
    ),
)


def _question_from_mention_text(text: str) -> str:
    return _MENTION_TOKEN_RE.sub("", text, count=1).strip()


@functools.lru_cache
def _get_handler() -> AsyncSlackRequestHandler:
    """Builds the Bolt app and its FastAPI handler once, on first request.

    Lazy because `test_main_slack_wiring.py` imports `commerce_ops.main` and
    runs its lifespan in a fresh interpreter with the Slack secrets absent,
    and requires both to succeed.
    """
    app = get_slack_app(SLACK_APP_IDENTITY)

    @app.event(_REPLYING_EVENT_TYPE)
    async def handle_app_mention(event: dict[str, Any], client: Any) -> None:
        if _is_bot_authored(event):
            # Bolt's own self-event filter cannot help here: it keys on
            # `auth_result.bot_user_id`/`bot_id`, which the fixed
            # AuthorizeResult supplies as None, so it never matches. This
            # guard is the sole defence against the bot answering itself.
            return

        channel = event["channel"]
        question = _question_from_mention_text(event.get("text", ""))

        try:
            answer = await answer_question(question)
            await client.chat_postMessage(channel=channel, text=answer)
        except Exception:  # noqa: BLE001 -- any omni-agent failure must surface in Slack
            await client.chat_postMessage(channel=channel, text=_FAILURE_MESSAGE)

    return AsyncSlackRequestHandler(app)


@router.post("/omni_agent/slack/events")
async def slack_events(request: Request) -> Response:
    try:
        # Read per request, before the cached factory is consulted: the
        # requirement is phrased per request, and a per-construction read
        # would leave a warm process verifying against a secret the
        # environment no longer has.
        secret = os.environ["OMNI_AGENT_SLACK_SIGNING_SECRET"]
    except KeyError:
        secret = ""

    if not secret:
        # Absent or empty: nothing about this request can be verified either
        # way, so fail closed, as `internal-trigger`'s guard does.
        #
        # Empty is handled here rather than left to Bolt. An earlier draft of
        # this change assumed Bolt answered 401 natively for an empty secret;
        # it does not -- `slack_sdk.signature.SignatureVerifier` raises
        # `ValueError("signing_secret must not be empty.")`, which escapes
        # Bolt's verification middleware and becomes a 500. That is the
        # outcome this capability's credential requirement forbids as
        # explicitly as it forbids an acknowledgement.
        return Response(
            status_code=401,
            media_type="application/json",
            content='{"error":"slack signing secret is not configured"}',
        )

    return await _get_handler().handle(request)
