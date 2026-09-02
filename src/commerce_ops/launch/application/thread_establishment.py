"""Operations for establishing and using a launch's Slack thread.

`thread-launch-slack-notifications` consolidates per-launch messages into
dedicated Slack threads. This module provides:

1. Lazy thread establishment: the first per-product message posts an anchor
   (product name, SKU, marketplace, launch date) and records the thread ID
   for reuse by subsequent messages; concurrent callers race under an
   advisory lock and produce exactly one anchor. The anchor's facts are
   resolved **here**, once, from the launch's own product — not supplied by
   whichever delivery path got there first — and where they cannot be
   resolved, establishment is *refused* rather than anchored with blanks.
   The anchor is permanent (`launch-instance`: never re-created once set),
   so a delayed thread is recoverable and a degraded one is not.

2. Mention resolution: who to tag in a message — the step's confirmer if
   it names one, else the launch's submitter.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from commerce_ops.launch.application.playbook_authoring import (
    RosterReader,
    person_identifier,
)
from commerce_ops.launch.application.ports import LaunchStore
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from commerce_ops.launch.domain.launch_playbook import StepDefinition

__all__ = ["ensure_launch_thread", "resolve_mention_target"]


async def ensure_launch_thread(
    launch_store: LaunchStore,
    product_id: ProductId,
    *,
    hold_lock: Callable[[], Awaitable[None]],
    channel: Callable[[], str],
    post_anchor: Callable[[str, str], Awaitable[str]],
    read_product: Callable[[], Awaitable[Any]] | None = None,
) -> str:
    """Establish or reuse a launch's Slack thread, returning its reference.

    Posts an anchor message naming the product, SKU, marketplace, and launch
    date the first time this is called for a launch; concurrent callers race
    under an advisory lock and produce exactly one anchor. Later callers
    reuse the existing thread reference without posting a second anchor.

    Every collaborator is an injected port, `post_anchor` included. This
    module is the application layer, and it used to build its own
    `AsyncWebClient` from the environment — the third copy of six lines
    whose other two live where a Slack client belongs. It also used to take
    the anchor's product facts as three loose strings from its caller, and
    to name `AsyncSession` in this signature for a value it only handed on.

    The anchor's facts are resolved here instead, through `read_product`,
    **after** the lock is held and after the early return for a launch that
    already has a thread. That placement is the requirement rather than an
    optimisation: `launch-instance` says a launch carrying a thread
    reference never resolves its product for the anchor, and it is what
    keeps every message after the first untouched by whether the catalog is
    answering.

    Refuses — raises — where the product cannot be resolved, rather than
    anchoring a thread with blanks in it. The anchor is permanent, so a
    degraded one has no repair path short of editing the database, while a
    delayed one costs one message that each caller already knows how to
    handle: three of the four retry, and the launch confirmation tells its
    submitter directly (`launch-entry`).

    Returns the thread reference (`ts`) as a string.
    """
    # Acquire the lock, reload the launch to re-check the thread reference
    # under lock, and post if absent.
    await hold_lock()
    launch = await launch_store.get_by_product_id(product_id)
    if launch is None:
        raise RuntimeError(f"no launch found for product {product_id.value}")
    if launch.slack_thread_id is not None:
        # Another caller won the race and established it first. Nothing is
        # resolved on this path -- not the product, not the anchor.
        return launch.slack_thread_id
    # Only now, with something permanent about to be written, is the product
    # resolved.
    product = await _product_or_refuse(product_id, read_product=read_product)
    anchor_text = _compose_anchor_message(product, launch.launch_date)
    # The anchor is posted as a top-level message in launches_channel;
    # the returned ts becomes the thread reference for this and all future
    # per-product messages.
    thread_ts = await post_anchor(channel(), anchor_text)
    launch.slack_thread_id = thread_ts
    await launch_store.save(launch)
    return thread_ts


async def _product_or_refuse(
    product_id: ProductId, *, read_product: Callable[[], Awaitable[Any]] | None
) -> Any:
    """The launch's product, or a refusal naming which of three gaps occurred.

    A reader that was never injected, one that fails, and one that answers
    nothing are one case — the system cannot say what the product is — and
    each refuses. They are still named apart in the message, because the
    repairs differ entirely: the first is a composition root that forgot a
    collaborator, the second a catalog that is down, the third a launch
    whose product is not there to be read.

    `RuntimeError` rather than a type of its own: no caller distinguishes
    this from any other delivery failure, each having one rule for "the post
    did not happen". The neighbouring impossible-state above raises the same
    way.
    """
    if read_product is None:
        raise RuntimeError(
            f"cannot establish the launch thread for product "
            f"{product_id.value}: no product reader is wired into this "
            f"process, so the anchor's facts cannot be resolved; the anchor "
            f"is permanent, so it is not posted with what is missing"
        )
    try:
        product = await read_product()
    except Exception as error:
        raise RuntimeError(
            f"cannot establish the launch thread for product "
            f"{product_id.value}: the catalog product could not be read "
            f"({error!r}); the anchor is permanent, so it is not posted with "
            f"what is missing"
        ) from error
    if product is None:
        raise RuntimeError(
            f"cannot establish the launch thread for product "
            f"{product_id.value}: the catalog holds no product for it, so "
            f"the anchor's facts cannot be resolved; the anchor is "
            f"permanent, so it is not posted with what is missing"
        )
    return product


async def resolve_mention_target(
    launch: Launch,
    step: StepDefinition | None = None,
    *,
    roster: RosterReader | None = None,
) -> str | None:
    """Resolve who to tag in a launch message, as a Slack identity or nothing.

    Given a step naming a confirmer, resolves that confirmer **through the
    roster** to their Slack identity; otherwise returns the launch's
    `submitter`, which is already one (`slack_entry.py` records
    `body["user"]["id"]` at launch start).

    The returned value is a Slack identity usable in `<@identity>` syntax
    without further translation, or `None`. That is what this docstring
    always claimed and what the confirmer branch did not do: `step.confirmer`
    holds the roster's own generated identifier, which Slack cannot resolve
    and renders as inert literal text, so the two messages whose entire
    purpose is to notify a named person notified nobody.

    A named confirmer is resolvable for tagging only where the roster carries
    them, carries them with a Slack identity, and carries them **active**.
    The active condition is the one that occurs durably: deactivation keeps
    the entry's Slack identity intact, and a decision is accepted only from
    an active confirmer, so tagging a deactivated one summons a person whose
    accept and reject are certain to be refused.

    A gap resolves to `None` and is reported, never raised: what each caller
    does about a missing tag differs (the pending-result ask carries none,
    the stuck-step report substitutes the submitter and says so), and both
    need the message itself to go out regardless. This is deliberately the
    opposite disposition from `automation_confirmation._roster_or_fail`,
    which raises — there the roster read *is* the decision, here it is an
    embellishment on a message whose substance does not depend on it.
    """
    if step is None or not step.confirmer:
        # The submitter needs no translation, so this branch never reads the
        # roster. That is what keeps the gate ask, the launch confirmation
        # and every step naming no confirmer working through a roster outage
        # or a composition root that never injected a reader.
        return launch.submitter
    return await _slack_identity_of(
        step.confirmer, launch=launch, step=step, roster=roster
    )


async def _slack_identity_of(
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    roster: RosterReader | None,
) -> str | None:
    """One roster identifier translated to a Slack identity, or `None` and a report.

    Every gap names the step, the launch and the confirmer that could not be
    resolved — the trade `clickup_sync._clickup_users` already makes for an
    assignee with no ClickUp account, and for the same reason: a failure
    here would hide a data gap behind a retry, and the run record only says
    whether the pass succeeded.
    """
    people = await _people_or_none(confirmer, launch=launch, step=step, roster=roster)
    if people is None:
        return None

    for person in people:
        try:
            identifier = person_identifier(person)
        except ValueError:
            continue
        if identifier != confirmer:
            continue
        slack_identity = getattr(person, "slack_identity", None)
        if not slack_identity:
            # Defence-in-depth, not a state the specifications say occurs:
            # `roster` requires every entry to carry a non-empty Slack
            # identity and `Person.faults()` enforces it. Kept because it
            # costs one condition and is what a reader looks for.
            _report_gap(
                "the roster carries them without a Slack identity",
                confirmer,
                launch=launch,
                step=step,
            )
            return None
        if not getattr(person, "active", True):
            _report_gap(
                "they are deactivated on the roster, so a decision could not "
                "be accepted from them in any case",
                confirmer,
                launch=launch,
                step=step,
            )
            return None
        return str(slack_identity)

    _report_gap("the roster does not carry them", confirmer, launch=launch, step=step)
    return None


async def _people_or_none(
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    roster: RosterReader | None,
) -> tuple[Any, ...] | None:
    """Everyone the roster carries, or `None` and a report where it cannot be read.

    Covers all three ways the delta names — no reader at all, a reader of the
    wrong shape, and one that fails — because they fail at three different
    points and catching one is not catching the others.
    """
    if roster is None:
        _report_gap(
            "no roster reader is wired into this process, so nothing could "
            "translate the identifier",
            confirmer,
            launch=launch,
            step=step,
        )
        return None
    lister = getattr(roster, "list_people", None)
    if lister is None:
        _report_gap(
            f"the roster collaborator {type(roster).__name__} answers no "
            "`list_people()`, which is a wiring fault rather than a fact "
            "about the confirmer",
            confirmer,
            launch=launch,
            step=step,
        )
        return None
    try:
        return tuple(await lister())
    except Exception:  # noqa: BLE001 — an unreadable roster still sends the message
        _report_gap(
            "the roster could not be read",
            confirmer,
            launch=launch,
            step=step,
            with_traceback=True,
        )
        return None


def _report_gap(
    why: str,
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    with_traceback: bool = False,
) -> None:
    _logger.warning(
        "step '%s' on product '%s' names confirmer '%s', who cannot be tagged: "
        "%s; the message is delivered without that mention",
        step.identifier,
        launch.product_id.value,
        confirmer,
        why,
        exc_info=with_traceback,
    )


def _compose_anchor_message(product: Any, launch_date: Any) -> str:
    """Compose the anchor message for a launch thread.

    Reads the product's fields directly rather than through `getattr`
    defaults. The four call sites needed that tolerance because each
    accepted a product that might be `None`; refusing on an unresolvable
    product is what makes it unnecessary here, and keeping it would let a
    test double satisfy a check the real store does not -- which is how the
    pending-result delivery seam shipped broken.

    The wording is unchanged and out of this change's scope: `launch-entry`
    governs what the anchor names.
    """
    date_str = launch_date.isoformat() if launch_date else "TBD"
    return (
        f"*{product.name}*\n"
        f"SKU: {product.sku.value}\n"
        f"Marketplace: {product.marketplace_id.value}\n"
        f"Launch Date: {date_str}"
    )
