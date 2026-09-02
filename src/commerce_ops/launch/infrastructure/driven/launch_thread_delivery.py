"""Driven adapter: the DB-touching half every threaded launch message shares.

`thread-launch-slack-notifications` gives four driving adapters
(`slack_entry.py`, `gate_confirmation.py`, `automation_confirmation.py`,
`automation_pass.py`) the same two-step preamble before they can post a
threaded, tagged message about a launch: ensure the launch's Slack thread
exists (posting its anchor the first time), then resolve who to tag. Each
call site differs only in which product/step it names and what message it
then composes and posts — the preamble itself is identical, so it lives
here once rather than four times.

This module is `infrastructure/driven`, not `application`, on purpose:
`ensure_launch_thread` and `resolve_mention_target`
(`launch/application/thread_establishment.py`) take their store, lock,
channel, anchor poster and product read as injected ports precisely so the
application layer never imports a concrete repository, a Slack client, a
credential, `transaction()`, or the catalog — that composition belongs on
the infrastructure side of the boundary the module-layers contract
enforces.

That sentence used to name only the repository and `transaction()`, and it
was false of everything else: `ensure_launch_thread` built its own
`AsyncWebClient` from `os.environ` and took the anchor's product facts from
whichever caller reached it first. `inject-the-thread-anchor-poster` made
the claim true as written rather than narrowing it.

Imported at module level by every call site rather than reached for inside
each function, the way `post_monitoring_message` already is: that is what
lets a unit test substitute it with `monkeypatch.setattr`, the same
mechanism that already substitutes the poster.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commerce_ops.launch.application.thread_establishment import (
    ensure_launch_thread,
    resolve_mention_target,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.launch_thread_lock import (
    hold_launch_thread_establishment_lock,
)
from commerce_ops.launch.infrastructure.driven.slack_notifier import (
    launches_channel,
    post_monitoring_message,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import transaction

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from typing import Any

    from commerce_ops.launch.application.playbook_authoring import RosterReader
    from commerce_ops.launch.domain.launch_playbook import StepDefinition

__all__ = ["establish_thread_and_resolve_mention", "read_people", "read_product"]

# Injected by `main.py` and `worker.py`, never imported: resolving a step's
# confirmer to a Slack identity means reading the roster, and `.importlinter`
# forbids `launch` from naming `access`'s store. Only a composition root may
# construct one, which is what makes the injection legal there and not here --
# the same seam `automation_confirmation.read_people`,
# `gate_confirmation.read_people` and `clickup_sync_job.read_people` already
# use, and reached at module level so a test can substitute it.
#
# Absent, mention resolution degrades rather than failing: a step naming no
# confirmer still tags the submitter, and one naming a confirmer is reported
# and delivered untagged. That is deliberate -- a mention is an embellishment
# on a message whose substance does not depend on the roster.
read_people: RosterReader | None = None

# Injected by `main.py` and `worker.py` the same way and for the same
# boundary reason as `read_people` above -- and alike in nothing else. Two
# differences, both deliberate, because these globals sit four lines apart
# and must not be read as one pattern.
#
# **Its absence policy is the opposite.** A missing roster degrades an
# embellishment, so mention resolution reports and carries on. A missing
# product reader means the anchor's facts cannot be resolved at all, and the
# anchor is permanent -- so establishment refuses rather than writing a
# header no later message can correct.
#
# **Its shape is the opposite too: it takes the caller's session.** The five
# other `read_product` globals in this codebase (`gate_confirmation`,
# `slack_entry`, `automation_pass`, `clickup_sync_job`,
# `gate_progression_job`) are called outside any transaction, and the
# readers wired into them open their own `session()`. This one is called
# *inside* `transaction()` while `pg_advisory_xact_lock` is held, so a
# reader opening its own session would check out a second connection from a
# pool of 5 (+10 overflow) while holding the first and the lock. It runs on
# the connection this function already has.
read_product: Callable[[Any, ProductId], Awaitable[Any]] | None = None


async def establish_thread_and_resolve_mention(
    product_id: ProductId,
    *,
    step: StepDefinition | None = None,
) -> tuple[str, str | None]:
    """Ensure the launch's thread exists and resolve who to tag in it.

    Opens its own transaction: acquires the thread-establishment lock,
    establishes the thread if it is not already set (or reuses it if it
    is), reloads the launch, and resolves the mention target against
    `step` (a step's named confirmer, or the launch's submitter where
    `step` is `None` or names none).

    Takes the product's *identifier* and nothing else about it. Its four
    callers used to assemble the anchor's name, SKU and marketplace from
    whatever their own catalog read had returned -- three of them falling
    back to empty strings -- so a launch's permanent thread header depended
    on which delivery path happened to fire first. The establishment path
    resolves the product itself now, once, at the moment it is about to
    write something permanent.

    Returns `(thread_ts, mention)`. The caller composes and posts its own
    message text and blocks against the result -- this only clears the way
    for that post, it does not make it.
    """
    async with transaction() as db_session:
        launch_store = LaunchRepository(db_session)
        thread_ts = await ensure_launch_thread(
            launch_store,
            product_id,
            # Both session-bound collaborators reach the application layer
            # the same way: bound here, where the session is, so the layer
            # itself names neither it nor SQLAlchemy. Binding the lock to
            # the same session as the store is also what makes the lock
            # work at all, and it is now a local fact rather than a
            # parameter's implied contract.
            hold_lock=lambda: hold_launch_thread_establishment_lock(
                db_session, product_id
            ),
            channel=launches_channel,
            post_anchor=_post_anchor,
            read_product=(
                None
                if read_product is None
                else lambda: read_product(db_session, product_id)
            ),
        )
        launch = await launch_store.get_by_product_id(product_id)
        mention = (
            await resolve_mention_target(launch, step=step, roster=read_people)
            if launch
            else None
        )
    return thread_ts, mention


async def _post_anchor(channel: str, text: str) -> str:
    """The anchor poster port: a top-level message, returning its `ts`.

    Adapts `post_monitoring_message`'s keyword shape to the positional
    `(channel, text) -> ts` the application layer declares, and passes no
    `thread_ts` -- the anchor *is* the thread's first message, which is the
    one fact about it this side of the boundary has to get right.
    """
    return await post_monitoring_message(channel=channel, text=text)
