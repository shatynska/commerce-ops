"""Driving adapter: putting a launch gate to a person for confirmation.

Implements the Slack half of `launch-gate-progression` — *A gate awaiting
only confirmation is asked about in Slack*, *Only a known, active person
may approve a gate* and *A decision records the approval and reports what
it did*.

`automation_confirmation.py`'s shape throughout: a message naming what is
being decided, an approve and a reject control carrying a JSON subject,
the presser resolved through the roster, and every refusal returned as a
reasoned `GateDecision` rather than raised — the wording belongs where the
rule is, not at the point furthest from it.

**Two transactions per approving press, in this order.** The approval is
recorded and committed first, in its own transaction; only then is the
advisory lock taken and the cascade run. A decision is a fact about what a
person did: a cascade that failed must not discard it, or the gate is left
neither advanced nor -- the ask cool-off having been written on an earlier
pass -- asked about again for a day.

A **rejecting** press is the opposite: its approval and its cool-off
refresh are one unit, under one `transaction()`, because a torn write
either re-proposes a gate a person has just declined or silences one for a
day with no decision recorded.

Delivery reaches Slack through `post_monitoring_message`, imported into
this module's namespace and called as a bare global -- `daily_briefing_job`'s
pattern, and what lets a test substitute it.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from commerce_ops.launch.application import (
    UnreadableRosterError,
    approve_gate_decision,
    progress_launch,
    reject_gate_decision,
)
from commerce_ops.launch.domain.launch_playbook import GATE_SEQUENCE
from commerce_ops.launch.infrastructure.driven.gate_ask_suppression import (
    GateAskSuppressionRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_advisory_lock import (
    hold_launch_advance_lock,
)
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.launch.infrastructure.driven.slack_notifier import (
    monitoring_channel,
    post_monitoring_message,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import session, transaction
from commerce_ops.shared.infrastructure.driving.slack_app import contribute_listeners

__all__ = [
    "APPROVE_ACTION",
    "REJECT_ACTION",
    "SLACK_APP_IDENTITY",
    "attach_listeners",
    "compose_blocks",
    "compose_message",
    "handle_gate_decision",
    "monitoring_channel",
    "post_gate_ask",
    "post_monitoring_message",
]

_logger = logging.getLogger(__name__)

SLACK_APP_IDENTITY = "product_agent"
APPROVE_ACTION = "launch_gate_approve"
REJECT_ACTION = "launch_gate_reject"

_FINAL_GATE = GATE_SEQUENCE[-1]

# Injected by the composition root after `register_all()`, never at import.
# `None` where nothing has been wired, in which case the ask names the
# product by its identifier rather than declining to be sent.
read_product: Any = None


class FinalGateNotAsked(RuntimeError):
    """The final gate is never put to a person by this capability.

    Its approval must name a steady-state posture and its opening stamps
    the catalog, and this change obtains neither. Enforced here as well as
    in the pass's launch set, so the boundary holds even if the pass is
    later handed a launch standing there.
    """


def _product_label(product: Any, product_id: ProductId) -> str:
    """What the message calls the launch: the catalog's own words where
    they are available, the identifier where they are not."""
    if product is None:
        return product_id.value
    name = getattr(product, "name", None)
    sku = getattr(product, "sku", None)
    sku_text = getattr(sku, "value", sku)
    if name and sku_text:
        return f"{name} ({sku_text})"
    return str(name or sku_text or product_id.value)


def compose_message(*, product: Any, product_id: ProductId, gate_id: str) -> str:
    """The sentence the ask leads with."""
    return (
        f"*{_product_label(product, product_id)}* is waiting on the "
        f"*{gate_id}* gate.\n"
        f"Everything that gate waits on is satisfied; it needs a decision "
        f"before the launch moves on."
    )


def _decision_value(product_id: ProductId, gate_id: str) -> str:
    """What a control carries back: which launch, and which gate.

    The pair, not a row id, following `automation_confirmation`'s reasoning:
    the decision is looked up by (product, gate) anyway, and a control that
    named a row would keep working after that row was settled.
    """
    return json.dumps({"product_id": product_id.value, "gate_id": gate_id})


def compose_blocks(*, product_id: ProductId, gate_id: str, message: str) -> list[Any]:
    """The message plus its two controls."""
    value = _decision_value(product_id, gate_id)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": APPROVE_ACTION,
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve"},
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


async def post_gate_ask(
    *,
    product_id: ProductId,
    gate_id: str,
    product: Any = None,
) -> None:
    """Ask for one gate's approval.

    Raises on a delivery failure rather than reporting it here: what a
    failed delivery means -- nothing recorded, the gate still eligible, try
    again next pass -- is the pass's rule, and it can only apply it if it
    learns the post did not happen.
    """
    if gate_id == _FINAL_GATE:
        raise FinalGateNotAsked(
            f"the final gate '{gate_id}' is not put to a person by this "
            f"deployment; its approval names a posture this capability does "
            f"not obtain"
        )
    if product is None and read_product is not None:
        try:
            product = await read_product(product_id)
        except Exception:
            # The message names the launch by identifier instead. A catalog
            # read failing must not withhold the ask: the decision is about
            # the gate, and the identifier is enough to act on.
            _logger.warning(
                "gate confirmation: the catalog product for %s could not be "
                "read; the ask names it by identifier",
                product_id.value,
                exc_info=True,
            )
            product = None
    message = compose_message(product=product, product_id=product_id, gate_id=gate_id)
    # Establish thread and get mention target (gates have no confirmer, so always submitter)
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
            product.name if product else product_id.value,
            sku_value,
            marketplace_value,
            hold_lock=hold_launch_thread_establishment_lock,
            channel=launches_channel(),
        )
        launch = await LaunchRepository(db_session).get_by_product_id(product_id)
        mention = await resolve_mention_target(launch, step=None) if launch else None
        mention_tag = f" <@{mention}>" if mention else ""
        await post_monitoring_message(
            channel=launches_channel(),
            text=mention_tag + message,
            blocks=compose_blocks(
                product_id=product_id, gate_id=gate_id, message=message
            ),
            thread_ts=thread_ts,
        )
    _logger.info(
        "gate confirmation: asked for the '%s' gate on product %s",
        gate_id,
        product_id.value,
    )


async def _advance_after_approval(product_id: ProductId, gate_id: str) -> str:
    """Run the cascade the approval unblocked, and say what it did.

    A separate transaction from the approval's, taken *after* it committed,
    and holding the product's advisory lock so a press landing inside a
    pass window waits rather than crossing the same gate twice.
    """
    async with transaction() as db_session:
        await hold_launch_advance_lock(db_session, product_id)
        playbook = await PlaybookRepository(db_session).get("live")
        launches = LaunchRepository(db_session)
        progressed = await progress_launch(
            launches=launches,
            playbook=playbook,
            product_id=product_id,
            journal=LaunchJournalRepository(db_session),
        )
        launch = await launches.get_by_product_id(product_id)

    # Read from the launch as it stands once the cascade under the lock has
    # finished -- not from this path's own crossings. Where the pass crossed
    # the approved gate first, the gate *did* open, and a reply built from
    # this path's advance alone would tell the decider their decision failed
    # when it did not.
    if launch is None or launch.current_gate != gate_id:
        return f"Recorded — the {gate_id} gate opened."
    blocking = launch.unsatisfied_conditions(playbook)
    if blocking:
        return f"Recorded — but the {gate_id} gate did not open: {', '.join(blocking)}."
    _ = progressed
    return f"Recorded — the {gate_id} gate is ready but did not open."


async def _handle_decision(body: dict[str, Any], approve: bool) -> str:
    """Run the decision and return what to tell the decider."""
    actions = body.get("actions") or [{}]
    try:
        carried = json.loads(actions[0].get("value") or "{}")
    except ValueError:
        return "that control carried nothing this deployment could read."

    raw_product = carried.get("product_id")
    gate_id = carried.get("gate_id")
    if not raw_product or not gate_id:
        return "that control named no launch gate."
    product_id = ProductId(str(raw_product))
    slack_identity = str((body.get("user") or {}).get("id") or "")
    when = datetime.now(UTC)

    try:
        if approve:
            # The approval commits in its own transaction, before the lock.
            async with session() as db_session:
                decision = await approve_gate_decision(
                    launches=LaunchRepository(db_session),
                    journal=LaunchJournalRepository(db_session),
                    roster=_roster_or_fail(),
                    playbooks=PlaybookRepository(db_session),
                    product_id=product_id,
                    gate_id=gate_id,
                    slack_identity=slack_identity,
                    when=when,
                )
            if decision.refused:
                return f"That decision was refused: {decision.reason}"
            return await _advance_after_approval(product_id, gate_id)

        # A rejection's two writes are one unit.
        async with transaction() as db_session:
            decision = await reject_gate_decision(
                launches=LaunchRepository(db_session),
                journal=LaunchJournalRepository(db_session),
                roster=_roster_or_fail(),
                playbooks=PlaybookRepository(db_session),
                suppression=GateAskSuppressionRepository(db_session),
                product_id=product_id,
                gate_id=gate_id,
                slack_identity=slack_identity,
                when=when,
            )
    except UnreadableRosterError:
        # Caught by its own type, never a bare `except Exception`: every
        # genuine refusal comes back as a `GateDecision`, so a broad catch
        # would report unrelated bugs as a mis-wired deployment.
        #
        # The sentence says nothing about the decider: their identity, their
        # roster entry and their authority are all irrelevant to what went
        # wrong, and blaming the roster for a wiring fault is what sent an
        # active admin looking at correct data.
        _logger.exception(
            "gate confirmation: a decision on gate '%s' could not be judged "
            "because the roster collaborator cannot be read; this is a "
            "deployment wiring fault, not a fact about the decider",
            gate_id,
        )
        return (
            "That decision could not be processed: this deployment cannot "
            "read the roster right now. Nothing was recorded, the gate is "
            "still waiting, and the fault has been reported."
        )

    if decision.refused:
        return f"That decision was refused: {decision.reason}"
    return f"Recorded — the {gate_id} gate stays closed."


def _roster_or_fail() -> Any:
    """The roster reader the composition root injected.

    Absent is refused the same way an unreadable one is, and for the same
    reason: neither is a fact about the decider.
    """
    if read_people is None:
        raise UnreadableRosterError(
            "no roster reader is wired into the gate-confirmation adapter, so "
            "no decision can be judged; this is a deployment wiring fault"
        )
    return read_people


# Injected by the composition root, the same way and for the same reason as
# `read_product`: the launch module may reach `access` only through its
# public application surface.
read_people: Any = None


async def handle_gate_decision(
    *, ack: Any, body: dict[str, Any], respond: Any, approve: bool
) -> None:
    """Acknowledge a press, act on it, and always answer the presser.

    One function for both controls rather than one per listener, so that
    "acknowledged first and always" and "the presser is always answered"
    are each stated once.

    The acknowledgement goes first and unconditionally: Slack's timeout is
    independent of how long recording and advancing take, and a refused
    decision is still a well-formed interaction.

    Every fault below it is caught. After `ack()` an escaping exception is
    a button that silently does nothing -- the presser sees a decision
    apparently accepted and no outcome ever -- so a fault becomes a
    sentence rather than a traceback.
    """
    await ack()
    try:
        message = await _handle_decision(body, approve=approve)
    except Exception:
        _logger.exception(
            "gate confirmation: a %s press could not be completed",
            "approve" if approve else "reject",
        )
        message = (
            "That decision could not be processed — something went wrong on "
            "our side. Nothing was recorded, the gate is still waiting, and "
            "the fault has been reported."
            if not approve
            else "Your approval was recorded, but the gate could not be "
            "advanced just now — something went wrong on our side. The "
            "fault has been reported, and the next pass will try again."
        )
    await respond(message)


def attach_listeners(app: AsyncApp) -> None:
    """Register the approve and reject controls on the `product_agent` app."""

    @app.action(APPROVE_ACTION)
    async def _approve(ack: Any, body: dict[str, Any], respond: Any) -> None:
        await handle_gate_decision(ack=ack, body=body, respond=respond, approve=True)

    @app.action(REJECT_ACTION)
    async def _reject(ack: Any, body: dict[str, Any], respond: Any) -> None:
        await handle_gate_decision(ack=ack, body=body, respond=respond, approve=False)


contribute_listeners(SLACK_APP_IDENTITY, attach_listeners)
