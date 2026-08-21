from __future__ import annotations

import functools
import os
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.omni_agent.application import answer_question

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

    try:
        answer = answer_question(question)
        client.chat_postMessage(channel=channel, text=answer)
    except Exception:  # noqa: BLE001 -- design.md: any omni-agent failure must surface in Slack
        client.chat_postMessage(
            channel=channel,
            text="Sorry, I ran into an error while trying to answer that.",
        )


@router.post("/omni_agent/slack/events")
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
