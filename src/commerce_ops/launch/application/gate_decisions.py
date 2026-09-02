"""Recording a member's decision on a confirmation gate.

Implements `launch-gate-progression`'s *Only a known, active member may
approve a gate* and the recording half of *A decision records the approval
and reports what it did*.

Modelled on `automated_decisions.py`, and for its reasons: a refusal is a
`Decision` handed back rather than an exception, because every refusal has
something to tell the member who pressed the control, and an adapter that
had to translate exception types into sentences would be inventing the
wording at the point furthest from the rule.

**This module records; it does not advance.** The cascade runs afterwards,
from the driving adapter, inside the product's advisory lock — and the
approval is committed *before* that lock is taken, deliberately. A
decision is a fact about what a member did, and a cascade that failed
must not discard it: the ask's cool-off record was written on an earlier
pass and outside any of this, so an approval lost with the cascade would
leave the gate neither advanced nor asked about again for a day.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from commerce_ops.launch.application.playbook_authoring import (
    MembersReader,
    UnreadableMembersError,
)
from commerce_ops.launch.application.ports import LaunchJournal, LaunchStore
from commerce_ops.launch.application.use_cases import approve_gate
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    PlaybookNotReadyError,
)
from commerce_ops.launch.domain.launch_run import ApprovalDecision, GateApproval
from commerce_ops.shared.domain.identity import ProductId

__all__ = [
    "GateDecision",
    "approve_gate_decision",
    "reject_gate_decision",
]

_FINAL_GATE = GATE_SEQUENCE[-1]


@dataclass(frozen=True, slots=True)
class GateDecision:
    """What became of a gate decision, and what to tell the decider.

    `refused` is the field the Slack reply reads; `reason` is written for
    a member, since it is what they will see. `gate_id` travels back so the
    adapter can run the cascade without re-deriving which gate it just
    recorded against.
    """

    refused: bool
    reason: str
    gate_id: str | None = None

    @property
    def accepted(self) -> bool:
        return not self.refused


def _refuse(reason: str) -> GateDecision:
    return GateDecision(refused=True, reason=reason)


async def _member_for(members: MembersReader, slack_identity: str) -> Any | None:
    """The member for a Slack identity, deactivated entries included.

    Both halves of "known **and** active" are decided here rather than by
    whatever supplies the membership: a reader that answered only active members
    would collapse two distinct refusals into one and tell a deactivated
    member the membership does not carry them — the incident
    `launch-step-automation`'s members requirement records.
    """
    lister = getattr(members, "list_members", None)
    if lister is None:
        raise UnreadableMembersError(
            f"the members collaborator is a {type(members).__name__!r}, which "
            f"cannot answer who the membership carries: a members reader must "
            f"provide `list_members()`, and this one does not. Pass a reader "
            f"rather than a members store — a decision cannot be judged "
            f"without one, and no decision may be refused as though the "
            f"members had been read"
        )
    for member in await lister():
        if getattr(member, "slack_identity", None) == slack_identity:
            return member
    return None


def _approver_name(member: Any) -> str:
    """What is written into the approval as its named approver.

    The membership's own identifier where it has one, so that correcting a
    member's display name never rewrites the approvals pointing at them.
    """
    for attribute in ("identifier", "id", "name"):
        value = getattr(member, attribute, None)
        if isinstance(value, str) and value:
            return value
    return str(member)


async def _decide(
    *,
    launches: LaunchStore,
    journal: LaunchJournal,
    members: MembersReader,
    suppression: Any,
    playbooks: Any,
    product_id: ProductId,
    gate_id: str,
    slack_identity: str,
    when: datetime,
    approving: bool,
) -> GateDecision:
    # The stand-down, first and independently of everything else. The pass
    # declines to act on a set that is being authored, and a decision
    # recorded against one would commit a member to a gate the system has
    # just declined to evaluate. The served read is what refuses, so it is
    # taken rather than assumed.
    if playbooks is not None:
        try:
            # Both shapes are live in this repository: `PlaybookRepository.get`
            # is a coroutine, `ServedPlaybooks.get` is not. Awaiting only what
            # is awaitable lets either satisfy the port.
            served = playbooks.get("live")
            if inspect.isawaitable(served):
                await served
        except PlaybookNotReadyError:
            return _refuse(
                "the playbook cannot hold a launch right now, so nothing was "
                "recorded; the gate will be asked about again once it can"
            )

    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        return _refuse(
            "that product has no launch record, so the decision was not recorded"
        )

    # Both refusals below are independent of the membership and are made first,
    # so that a decision already refused on grounds having nothing to do
    # with the decider keeps its own refusal rather than being answered
    # with a wiring fault.
    if gate_id == _FINAL_GATE:
        return _refuse(
            "this deployment does not obtain approval for the final gate; "
            "the decision was not recorded"
        )
    if gate_id != launch.current_gate:
        return _refuse(
            f"this launch now stands at '{launch.current_gate}', not "
            f"'{gate_id}', so the decision was not recorded"
        )

    # "Before the deciding identity is judged" is what the requirement
    # asks, and this is that point — not the top of the function.
    member = await _member_for(members, slack_identity)
    if member is None:
        return _refuse(
            "the membership does not know that Slack identity, so the decision "
            "was not recorded"
        )
    if not getattr(member, "active", False):
        return _refuse(
            "that member is not active on the membership, so the decision was not recorded"
        )

    decision = ApprovalDecision.APPROVING if approving else ApprovalDecision.REJECTING
    await approve_gate(
        launches,
        product_id=product_id,
        gate_id=gate_id,
        approval=GateApproval(
            decision=decision,
            approver=_approver_name(member),
            when=when,
            # Never a posture: the only gate whose approval names one is
            # the final gate, which is refused above.
            posture=None,
        ),
        journal=journal,
    )

    if not approving and suppression is not None:
        # The day runs from the decision rather than from the ask that
        # prompted it, or a member who declines at hour 23 is asked again
        # an hour later. This write and the approval above land together
        # under the transaction the adapter opens around both.
        await suppression.record_rejection(product_id, gate_id, when)

    verdict = "approved" if approving else "rejected"
    return GateDecision(
        refused=False,
        reason=f"Recorded — the {gate_id} gate was {verdict}.",
        gate_id=gate_id,
    )


async def approve_gate_decision(
    *,
    launches: LaunchStore,
    journal: LaunchJournal,
    members: MembersReader,
    playbooks: Any = None,
    product_id: ProductId,
    gate_id: str,
    slack_identity: str,
    when: datetime,
    suppression: Any = None,
) -> GateDecision:
    """Record an approving decision on a launch's current gate."""
    return await _decide(
        launches=launches,
        journal=journal,
        members=members,
        suppression=suppression,
        playbooks=playbooks,
        product_id=product_id,
        gate_id=gate_id,
        slack_identity=slack_identity,
        when=when,
        approving=True,
    )


async def reject_gate_decision(
    *,
    launches: LaunchStore,
    journal: LaunchJournal,
    members: MembersReader,
    playbooks: Any = None,
    product_id: ProductId,
    gate_id: str,
    slack_identity: str,
    when: datetime,
    suppression: Any = None,
) -> GateDecision:
    """Record a rejecting decision, and start the cool-off from it."""
    return await _decide(
        launches=launches,
        journal=journal,
        members=members,
        suppression=suppression,
        playbooks=playbooks,
        product_id=product_id,
        gate_id=gate_id,
        slack_identity=slack_identity,
        when=when,
        approving=False,
    )
