from __future__ import annotations

import functools
import os
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from langchain_core.messages import HumanMessage
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.omni_agent.application.graph import build_production_graph

router = APIRouter()

_MENTION_TOKEN_RE = re.compile(r"<@[^>]+>\s*")


@functools.lru_cache
def get_signature_verifier() -> SignatureVerifier:
    return SignatureVerifier(os.environ["OMNI_AGENT_SLACK_SIGNING_SECRET"])


@functools.lru_cache
def get_slack_client() -> WebClient:
    return WebClient(token=os.environ["OMNI_AGENT_SLACK_BOT_TOKEN"])


def _question_from_mention_text(text: str) -> str:
    return _MENTION_TOKEN_RE.sub("", text, count=1).strip()


def handle_app_mention(event: dict[str, Any]) -> None:
    client = get_slack_client()
    channel = event["channel"]
    question = _question_from_mention_text(event.get("text", ""))

    # Posted before the (potentially slow) omni-agent call, so the channel
    # sees a near-instant response confirming the mention was received and
    # posting works -- independent of how long generation takes or whether
    # it succeeds.
    client.chat_postMessage(
        channel=channel, text=":hourglass_flowing_sand: Working on it..."
    )

    try:
        graph = build_production_graph()
        result = graph.invoke({"messages": [HumanMessage(content=question)]})
        answer = result["messages"][-1].content
        client.chat_postMessage(channel=channel, text=answer)
    except Exception:  # noqa: BLE001 -- design.md: any omni-agent failure must surface in Slack
        client.chat_postMessage(
            channel=channel,
            text="Sorry, I ran into an error while trying to answer that.",
        )


@router.post("/slack/events")
async def slack_events(
    request: Request, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    body = await request.body()

    try:
        is_valid = get_signature_verifier().is_valid_request(
            body, dict(request.headers)
        )
    except (KeyError, ValueError):
        # OMNI_AGENT_SLACK_SIGNING_SECRET absent or malformed -- can't verify,
        # so the request can't be trusted either.
        is_valid = False

    if not is_valid:
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        if event.get("type") == "app_mention":
            background_tasks.add_task(handle_app_mention, event)

    return {"ok": True}


@router.post("/slack/commands")
async def slack_commands(request: Request) -> dict[str, Any]:
    """Diagnostic slash command endpoint.

    Not part of any current spec -- added to test whether Slack can reach
    this server at all, since a slash command surfaces a clear
    "dispatch_failed" error in Slack's own UI on failure, unlike the Events
    API's silent delivery failures. Remove once /slack/events delivery is
    confirmed working, or formalize via a proper spec change if kept.
    """
    body = await request.body()

    try:
        is_valid = get_signature_verifier().is_valid_request(
            body, dict(request.headers)
        )
    except (KeyError, ValueError):
        is_valid = False

    if not is_valid:
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    return {
        "response_type": "ephemeral",
        "text": "pong -- commerce-ops reached this request successfully.",
    }
