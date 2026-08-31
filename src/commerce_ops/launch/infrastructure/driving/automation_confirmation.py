"""Driving adapter: putting a produced result in front of a person.

`launch-step-automation`'s "A pending result is delivered for a decision"
and the decision half of "Only the step's named confirmer may decide a
pending result". A pending result becomes a Slack message naming the
product, the step, the outcome the handler proposed and the produced
text **in full**, carrying an accept and a reject control; pressing one
runs the matching use case, which is where the confirmer identity is
actually checked — this adapter stays a thin relay of whichever Slack
identity pressed the button.

The produced text goes in whole rather than truncated. It is the thing
being decided — a person asked to accept a recommendation they can only
half-read is being asked to accept it unread, and the message is also the
only place it is legible before it becomes a launch record.

Delivery reaches Slack through `post_monitoring_message`, imported into
this module's namespace and called as a bare global — `daily_briefing_job`'s
pattern, and what lets a test substitute it. It is launch's own notifier
rather than the briefing's: `.importlinter` forbids this module from
naming `briefing`, and the two share the variables, not the code. A
failure propagates: the pass is what decides that an undelivered result
stays pending and is tried again, and swallowing the exception here would
tell it the delivery succeeded.
"""

from __future__ import annotations

import functools
import json
import logging
from datetime import UTC, datetime
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from commerce_ops.launch.application import (
    RosterReader,
    UnreadableRosterError,
    accept_automated_result,
    record_step_outcome,
    reject_automated_result,
)
from commerce_ops.launch.infrastructure.driven.automated_results import (
    AutomatedResultRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.launch.infrastructure.driven.slack_notifier import (
    monitoring_channel,
    post_monitoring_message,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driving.slack_app import contribute_listeners

__all__ = [
    "ACCEPT_ACTION",
    "REJECT_ACTION",
    "SLACK_APP_IDENTITY",
    "attach_listeners",
    "compose_blocks",
    "deliver_pending_result",
    "monitoring_channel",
    "post_monitoring_message",
]

_logger = logging.getLogger(__name__)

SLACK_APP_IDENTITY = "product_agent"

# Injected by `main.py`, never imported: resolving a Slack identity means
# reading the roster, and `.importlinter` forbids this module from naming
# `access`'s *store*. Only a composition root may construct one, which is
# what makes the injection legal there and not here.
#
# A **reader** is what belongs here -- something answering `list_people()`
# -- and the type says so. It was `Any`, and the root assigned it the
# `PostgresRoster` store, which answers `load()`/`save()`: nothing
# objected, and every decision by every identity was refused as though
# the roster did not carry them. Typed, that assignment is a `mypy`
# error at the line where the mistake is made.
read_people: RosterReader | None = None

ACCEPT_ACTION = "automation_result_accept"
REJECT_ACTION = "automation_result_reject"


def _outcome_name(outcome: Any) -> str:
    if isinstance(outcome, str):
        return outcome
    kind = outcome if isinstance(outcome, type) else type(outcome)
    return str(getattr(kind, "__name__", outcome))


def compose_message(*, result: Any, product: Any, step_name: str | None) -> str:
    """The message a person decides on.

    Plain text rather than Block Kit: the produced text is the substance
    and is already prose, and a layout would only wrap it. The two
    decisions are named in the text so that what is being asked stays
    legible even where the controls do not render.
    """
    product_name = getattr(product, "name", None) or "an unnamed product"
    step_id = getattr(result, "step_id", "?")
    step = step_name or step_id
    handler = getattr(result, "handler", "an automated handler")
    proposed = _outcome_name(getattr(result, "proposed_outcome", "?"))
    produced = getattr(result, "result_text", "")

    return (
        f"Automated result for *{product_name}* — {step} (`{step_id}`)\n"
        f"Handler `{handler}` proposes: *{proposed}*\n\n"
        f"{produced}\n\n"
        f"Accept to record it against the launch, or reject to leave the "
        f"step unresolved."
    )


async def deliver_pending_result(
    *,
    result: Any,
    product: Any = None,
    step_name: str | None = None,
) -> None:
    """Post one pending result for a decision.

    Raises on a delivery failure rather than reporting it here: what a
    failed delivery means — the result still stands, nothing is recorded,
    try again next pass — is the pass's rule, and it can only apply it if
    it learns the post did not happen.
    """
    message = compose_message(result=result, product=product, step_name=step_name)
    # Establish thread and get mention target (step's confirmer)
    from commerce_ops.launch.application.thread_establishment import (
        ensure_launch_thread,
        resolve_mention_target,
    )
    from commerce_ops.launch.infrastructure.driven.launch_repository import (
        LaunchRepository,
    )
    from commerce_ops.launch.infrastructure.driven.launch_thread_lock import (
        hold_launch_thread_establishment_lock,
    )
    from commerce_ops.launch.infrastructure.driven.slack_notifier import (
        launches_channel,
    )
    from commerce_ops.shared.infrastructure.driven.database import transaction

    product_id = getattr(result, "product_id", None)
    step_id = getattr(result, "step_id", None)

    if not isinstance(product_id, ProductId):
        raise TypeError(f"product_id must be ProductId, got {type(product_id)}")

    async with transaction() as db_session:
        sku_value = ""
        marketplace_value = ""
        if product:
            sku = getattr(product, "sku", None)
            sku_value = sku.value if sku else ""
            marketplace = getattr(product, "marketplace_id", None)
            marketplace_value = marketplace.value if marketplace else ""
        thread_ts = await ensure_launch_thread(
            db_session,
            LaunchRepository(db_session),
            product_id,
            product.name if product else str(product_id),
            sku_value,
            marketplace_value,
            hold_lock=hold_launch_thread_establishment_lock,
            channel=launches_channel(),
        )
        launch = await LaunchRepository(db_session).get_by_product_id(product_id)
        # Get step definition to pass to resolver for confirmer lookup
        step_def = None
        if launch and step_id and hasattr(launch, "playbook_version"):
            # Note: would need playbook access to get step_def; for now use None
            pass
        mention = (
            await resolve_mention_target(launch, step=step_def) if launch else None
        )
        mention_tag = f" <@{mention}>" if mention else ""
        await post_monitoring_message(
            channel=launches_channel(),
            text=mention_tag + message,
            blocks=compose_blocks(result=result, message=message),
            thread_ts=thread_ts,
        )
    _logger.info(
        "automation confirmation: delivered the pending result for step "
        "'%s' on product '%s' for a decision",
        getattr(result, "step_id", "?"),
        getattr(result, "product_id", "?"),
    )


def _decision_value(result: Any) -> str:
    """What a button carries back: which launch, and which step.

    The pair, not the row id: the use case looks the pending result up by
    (product, step) anyway, and a button that named a row would keep
    working after that row was settled.
    """
    return json.dumps(
        {
            "product_id": str(getattr(result, "product_id", "")),
            "step_id": str(getattr(result, "step_id", "")),
        }
    )


def compose_blocks(*, result: Any, message: str) -> list[dict[str, Any]]:
    """The message plus its two controls."""
    value = _decision_value(result)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACCEPT_ACTION,
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Accept"},
                    "value": value,
                },
                {
                    "type": "button",
                    "action_id": REJECT_ACTION,
                    "text": {"type": "plain_text", "text": "Reject"},
                    "value": value,
                },
            ],
        },
    ]


async def _handle_decision(body: dict[str, Any], accept: bool) -> str:
    """Run the decision and return what to tell the decider.

    Every path returns a sentence for the reply: the requirement obliges a
    refused decision to tell the decider it was refused, and the adapter
    cannot say why unless the use case hands it a reason.
    """
    actions = body.get("actions") or [{}]
    try:
        carried = json.loads(actions[0].get("value") or "{}")
    except ValueError:
        return "that control carried nothing this deployment could read."

    product_id = carried.get("product_id")
    step_id = carried.get("step_id")
    if not product_id or not step_id:
        return "that control named no launch step."

    slack_identity = str((body.get("user") or {}).get("id") or "")

    try:
        async with session() as db_session:
            launches = LaunchRepository(db_session)
            playbook = await PlaybookRepository(db_session).get("live")
            use_case = accept_automated_result if accept else reject_automated_result
            decision = await use_case(
                results=AutomatedResultRepository(db_session),
                roster=_roster_or_fail(),
                launches=launches,
                playbook=playbook,
                record_outcome=functools.partial(
                    record_step_outcome,
                    launches,
                    ServedPlaybooks(playbook),
                    journal=LaunchJournalRepository(db_session),
                ),
                product_id=ProductId(str(product_id)),
                step_id=str(step_id),
                slack_identity=slack_identity,
                when=datetime.now(UTC),
            )
    except UnreadableRosterError:
        # Caught by its own type, never a bare `except Exception`: every
        # genuine refusal comes back as a `Decision`, so a broad catch
        # here would report unrelated bugs as a mis-wired deployment.
        #
        # Logged because this is a fault an operator must see and a
        # decider can do nothing about, and answered because the
        # alternative -- letting it escape after `ack()` -- leaves the
        # press unanswered. The sentence says nothing about the decider:
        # their identity, their roster entry and their authority are all
        # irrelevant to what went wrong, and the previous behaviour of
        # blaming the roster for a wiring fault is what sent an active
        # admin looking at correct data.
        _logger.exception(
            "automation confirmation: a decision on step '%s' could not be "
            "judged because the roster collaborator cannot be read; this is "
            "a deployment wiring fault, not a fact about the decider",
            step_id,
        )
        return (
            "That decision could not be processed: this deployment cannot "
            "read the roster right now. Nothing was recorded, the result is "
            "still waiting, and the fault has been reported."
        )
    if decision.refused:
        return f"That decision was refused: {decision.reason}"
    verdict = "accepted" if accept else "rejected"
    return f"Recorded — the automated result was {verdict}."


def attach_listeners(app: AsyncApp) -> None:
    """Register the accept and reject controls on the `product_agent` app.

    Contributed rather than registered inside `slack_entry`'s factory:
    this capability's listeners belong in this capability's module, and
    the seam in `slack_app.py` is what makes that possible without a
    second Slack app and a second set of credentials.
    """

    @app.action(ACCEPT_ACTION)
    async def _accept(ack: Any, body: dict[str, Any], respond: Any) -> None:
        # Acknowledged first and always: Slack's timeout is independent of
        # how long recording takes, and a refused decision is still a
        # well-formed interaction.
        await ack()
        await respond(await _handle_decision(body, accept=True))

    @app.action(REJECT_ACTION)
    async def _reject(ack: Any, body: dict[str, Any], respond: Any) -> None:
        await ack()
        await respond(await _handle_decision(body, accept=False))


contribute_listeners(SLACK_APP_IDENTITY, attach_listeners)


def _roster_or_fail() -> RosterReader:
    """The injected reader, or the wiring error owed when there is none.

    `UnreadableRosterError` rather than the `RuntimeError` this used to
    raise, and the type is the whole point: a collaborator that is absent
    and one that is the wrong shape are one mistake made in two places,
    and a decider cannot act differently on them. Raising two types meant
    `_handle_decision` caught one and let the other escape the Bolt
    listener after `ack()` -- leaving the decider with a button that did
    nothing, which is the one outcome worse than a wrong answer.

    The message is unchanged: it already named the fault and where the
    injection belongs.
    """
    if read_people is None:
        raise UnreadableRosterError(
            "a decision arrived on an automated result, but no roster "
            "reader was injected; `main.py` supplies one after the routers "
            "are mounted"
        )
    return read_people
