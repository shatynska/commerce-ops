"""Deciding a produced result: what a person's accept or reject does.

`launch-step-automation`'s four decision requirements — who may decide,
what accepting records, what rejecting records, and that a result is
decided once — plus the refusal owed when the step has left the served
set since the result was produced.

Three rules here are worth reading twice, because each is a place a
plausible implementation goes wrong:

- **Accepting keeps source `automated` while naming the accepter as the
  recorder.** The work was the handler's; the acceptance was the person's.
  Both facts fit in the one `Provenance`, so no new source value is owed
  and the launch's record answers both questions.
- **The evidence names the handler as well as the produced text.** Without
  it, "what produced the result this person accepted" is answerable only
  from the pending-result row, and the launch's own record would depend on
  a second store still holding it.
- **Rejecting records `Blocked`, never `Refused`.** `Refused` is reserved
  for a `prohibited-tactic` step and means the tactic itself was declined;
  a person declining one produced result has said nothing about the step's
  permissibility. `Blocked` is chosen from among the non-terminal outcomes
  because it is the one that carries a reason, and a rejection whose reason
  went unrecorded would leave the launch showing an unresolved step with
  nothing saying why.

Every refusal returns a `Decision` rather than raising: the caller is a
Slack interaction that must reply to the decider either way, and an
exception would make "tell them why" the adapter's problem to reconstruct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from commerce_ops.launch.domain.launch_playbook import Blocked, LaunchPlaybook
from commerce_ops.launch.domain.launch_run import Provenance
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
    a person, since it is what they will see.
    """

    refused: bool
    reason: str

    @property
    def accepted(self) -> bool:
        return not self.refused


def _refuse(reason: str) -> Decision:
    return Decision(refused=True, reason=reason)


async def _person_for(roster: Any, slack_identity: str) -> Any | None:
    """The roster person a Slack identity belongs to, or None.

    Reached through whichever read the roster offers: `access` owns that
    surface, and this module may only use it, not shape it.
    """
    direct = getattr(roster, "person_for_slack_identity", None)
    if callable(direct):
        return await direct(slack_identity)
    lister = getattr(roster, "list_people", None) or getattr(roster, "people", None)
    if callable(lister):
        for person in await lister():
            if getattr(person, "slack_identity", None) == slack_identity:
                return person
    return None


def _serves(playbook: LaunchPlaybook, step_id: str) -> bool:
    return any(step.identifier == step_id for step in playbook.served_steps)


async def _decide(
    *,
    results: Any,
    roster: Any,
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

    person = await _person_for(roster, slack_identity)
    if person is None:
        return _refuse(
            "the roster does not know that Slack identity, so the decision "
            "was not recorded"
        )
    if not getattr(person, "active", False):
        return _refuse(
            "that person is not active on the roster, so the decision was not recorded"
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

    who = getattr(person, "display_name", None) or getattr(person, "id", slack_identity)
    handler = getattr(pending, "handler", "an automated handler")
    produced = getattr(pending, "result_text", "")

    if accept:
        outcome: Any = _proposed_outcome(pending)
        evidence = f"{handler}: {produced}"
        state = "accepted"
    else:
        outcome = Blocked(
            reason=(f"{who} rejected the automated result produced by {handler}")
        )
        evidence = f"{handler}: {produced} — rejected by {who}"
        state = "rejected"

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


async def accept_automated_result(
    *,
    results: Any,
    roster: Any,
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
        roster=roster,
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
    roster: Any,
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
        roster=roster,
        launches=launches,
        playbook=playbook,
        record_outcome=record_outcome,
        product_id=product_id,
        step_id=step_id,
        slack_identity=slack_identity,
        when=when,
        accept=False,
    )
