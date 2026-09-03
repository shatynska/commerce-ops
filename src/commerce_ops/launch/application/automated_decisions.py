"""Deciding a produced result: what a member's accept or reject does.

`launch-step-automation`'s four decision requirements — who may decide,
what accepting records, what rejecting records, and that a result is
decided once — plus the refusal owed when the step has left the served
set since the result was produced.

Three rules here are worth reading twice, because each is a place a
plausible implementation goes wrong:

- **Accepting keeps source `automated` while naming the accepter as the
  recorder.** The work was the handler's; the acceptance was the member's.
  Both facts fit in the one `Provenance`, so no new source value is owed
  and the launch's record answers both questions.
- **The evidence names the handler as well as the produced text.** Without
  it, "what produced the result this member accepted" is answerable only
  from the pending-result row, and the launch's own record would depend on
  a second store still holding it.
- **Rejecting records `Blocked`, never `Refused`.** `Refused` is reserved
  for a `prohibited-tactic` step and means the tactic itself was declined;
  a member declining one produced result has said nothing about the step's
  permissibility. `Blocked` is chosen from among the non-terminal outcomes
  because it is the one that carries a reason, and a rejection whose reason
  went unrecorded would leave the launch showing an unresolved step with
  nothing saying why.

Every refusal *of a decision* returns a `Decision` rather than raising:
the caller is a Slack interaction that must reply to the decider either
way, and an exception would make "tell them why" the adapter's problem
to reconstruct.

The one exception is not a refusal of a decision at all. A members
collaborator that cannot be read is a mis-wired deployment, and it
raises `UnreadableMembersError`, because there is nothing true to tell
the decider about *their* decision — see `_member_for`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from commerce_ops.launch.application.playbook_authoring import (
    MembersReader,
    UnreadableMembersError,
    member_identifier,
)
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    LaunchPlaybook,
    StepDefinition,
)
from commerce_ops.launch.domain.launch_run import (
    CarriedFinding,
    LaunchError,
    Provenance,
)
from commerce_ops.shared.domain.identity import ProductId

__all__ = [
    "Decision",
    "accept_automated_result",
    "reject_automated_result",
]

_AUTOMATED_SOURCE = "automated"


@dataclass(frozen=True, slots=True)
class Decision:
    """What became of a decision, and what to tell the decider.

    `refused` is the field the Slack reply reads. `reason` is written for
    a member, since it is what they will see.
    """

    refused: bool
    reason: str

    @property
    def accepted(self) -> bool:
        return not self.refused


def _refuse(reason: str) -> Decision:
    return Decision(refused=True, reason=reason)


async def _member_for(members: MembersReader, slack_identity: str) -> Any | None:
    """The member a Slack identity belongs to, or None.

    One shape, and anything else is refused by name. This once probed
    three spellings — `member_for_slack_identity`, `list_members`,
    `members` — and returned `None` when the collaborator answered to
    none of them. The composition root supplied a `MembersStore`, which
    answers `load()`/`save()` and so matched nothing, and every decision
    by every identity was refused as "the membership does not know that
    Slack identity". A collaborator that cannot be read is a defect of
    *wiring*; resolving it into a statement about the decider told
    active admins their members entry was at fault and sent them looking
    at data that was correct all along.

    So it raises rather than answering `None`. `None` here means one
    thing only: the membership was read, and it does not carry that
    identity.

    The whole membership is read, deactivated entries included, because
    "known" and "active" are two facts this module decides separately —
    a reader that answered only active members would collapse two
    distinct refusals into one.
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


def _serves(playbook: LaunchPlaybook, step_id: str) -> bool:
    return any(step.identifier == step_id for step in playbook.served_steps)


def _step_for(playbook: LaunchPlaybook, step_id: str) -> StepDefinition | None:
    return next(
        (step for step in playbook.served_steps if step.identifier == step_id), None
    )


async def _decide(
    *,
    results: Any,
    members: MembersReader,
    launches: Any,
    playbook: LaunchPlaybook,
    record_outcome: Any,
    product_id: ProductId,
    step_id: str,
    slack_identity: str,
    when: datetime,
    accept: bool,
) -> Decision:
    pending = await results.pending_for(product_id, step_id)
    if pending is None:
        # Already settled, or never produced. Either way there is nothing
        # to decide, and the outcome the first decision recorded stands —
        # a second decision that recorded again would let a rejection
        # silently overwrite an acceptance.
        return _refuse(
            "that result has already been decided; the decision recorded first stands"
        )

    # The membership is read *after* the pending lookup, deliberately. A
    # mis-wired deployment raises from here, so a repeat press on an
    # already-settled result keeps answering "already decided" rather
    # than reporting the wiring: that refusal does not depend on the
    # members, and it is still the true thing to say. "Before the
    # deciding identity is judged" is what the requirement asks, and
    # this is that point — not the top of the function.
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

    if not _serves(playbook, step_id):
        # Recording would be rejected for such a step anyway; leaving the
        # result pending would keep offering a decision that can never
        # take effect. Voiding it lets the step, if it returns, be
        # resolved afresh rather than settled by a proposal about a step
        # that has since changed.
        await results.void(pending)
        return _refuse(
            "the playbook no longer serves that step, so the result was "
            "withdrawn rather than recorded"
        )

    # Checked once the step is known to be served, so a step the playbook
    # no longer serves keeps the refusal above rather than this one — a
    # confirmer comparison against a step that no longer exists would be
    # meaningless anyway. Only a known, active *and* named member may
    # decide now: any other identity, active or not, is refused here.
    step = _step_for(playbook, step_id)
    if step is None or member_identifier(member) != step.confirmer:
        return _refuse(
            "that member is not this step's named confirmer, so the "
            "decision was not recorded"
        )

    who = getattr(member, "display_name", None) or getattr(member, "id", slack_identity)
    handler = getattr(pending, "handler", "an automated handler")
    produced = getattr(pending, "result_text", "")

    if accept:
        outcome: Any = _proposed_outcome(pending)
        evidence = f"{handler}: {produced}"
        state = "accepted"
        # Read off the pending result, never re-read from the sink: the
        # fact recorded is the one the member was shown and decided on,
        # and a value changed elsewhere meanwhile must not be substituted
        # for it (`launch-step-automation`). Unreadable carries none --
        # a decision must not be lost to a field beside it.
        carried = _carried_finding(pending)
    else:
        outcome = Blocked(
            reason=(f"{who} rejected the automated result produced by {handler}")
        )
        evidence = f"{handler}: {produced} — rejected by {who}"
        state = "rejected"
        # A rejection asserts nothing: the member declined the fact the
        # proposal carried, so the `Blocked` recorded from it must not
        # carry a finding asserting it anyway.
        carried = None

    await record_outcome(
        product_id=product_id,
        step_id=step_id,
        outcome=outcome,
        provenance=Provenance(
            source=_AUTOMATED_SOURCE,
            who=str(who),
            when=when,
            evidence=evidence,
        ),
        finding=carried,
    )
    # Settled only after the recording took effect: a settled result whose
    # outcome was never recorded would be undecidable and unrecoverable.
    await results.settle(pending, state=state, decided_by=str(who), decided_at=when)
    return Decision(refused=False, reason=f"recorded as {state}")


def _proposed_outcome(pending: Any) -> Any:
    """The outcome the handler proposed, as the domain spells it.

    The store keeps a name so a waiting proposal does not depend on the
    code that produced it; this maps it back.
    """
    from commerce_ops.launch.domain import launch_playbook

    proposed = getattr(pending, "proposed_outcome", None)
    if isinstance(proposed, str):
        return getattr(launch_playbook, proposed)
    return proposed


def _carried_finding(pending: Any) -> CarriedFinding | None:
    """The finding stored with a pending result, or nothing.

    Never raises. An unreadable stored finding reports as none rather
    than failing the acceptance: the recording and the settlement must
    both take effect or neither, so a member's decision must not be lost
    to a field beside the outcome they accepted.
    """
    stored = getattr(pending, "finding", None)
    if stored is None:
        return None
    if isinstance(stored, CarriedFinding):
        return stored
    if not isinstance(stored, Mapping):
        return None
    try:
        return CarriedFinding(
            field=stored["field"],
            value=stored["value"],
            comment=stored.get("comment"),
            reads_as=stored.get("reads_as"),
        )
    except (KeyError, TypeError, ValueError, AttributeError, LaunchError):
        # `AttributeError` is not hypothetical: `CarriedFinding` validates
        # its field with `.strip()`, so a stored `{"field": 17}` raises
        # there. Uncaught, that propagates out of the accept path and the
        # member's decision is neither recorded nor settled -- the one
        # thing `launch-step-automation` says an unreadable finding must
        # never cost.
        return None


async def accept_automated_result(
    *,
    results: Any,
    members: MembersReader,
    launches: Any,
    playbook: LaunchPlaybook,
    record_outcome: Any,
    product_id: ProductId,
    step_id: str,
    slack_identity: str,
    when: datetime,
) -> Decision:
    """Record exactly the outcome the handler proposed, naming the accepter."""
    return await _decide(
        results=results,
        members=members,
        launches=launches,
        playbook=playbook,
        record_outcome=record_outcome,
        product_id=product_id,
        step_id=step_id,
        slack_identity=slack_identity,
        when=when,
        accept=True,
    )


async def reject_automated_result(
    *,
    results: Any,
    members: MembersReader,
    launches: Any,
    playbook: LaunchPlaybook,
    record_outcome: Any,
    product_id: ProductId,
    step_id: str,
    slack_identity: str,
    when: datetime,
) -> Decision:
    """Record a non-terminal `Blocked` naming the rejecter, leaving the
    step live for a later pass."""
    return await _decide(
        results=results,
        members=members,
        launches=launches,
        playbook=playbook,
        record_outcome=record_outcome,
        product_id=product_id,
        step_id=step_id,
        slack_identity=slack_identity,
        when=when,
        accept=False,
    )
