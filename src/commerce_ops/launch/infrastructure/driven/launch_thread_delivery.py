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
(`launch/application/thread_establishment.py`) take their store, lock and
channel as injected ports precisely so the application layer never imports
a concrete repository or `transaction()` — that composition belongs on the
infrastructure side of the boundary the module-layers contract enforces.

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
from commerce_ops.launch.infrastructure.driven.slack_notifier import launches_channel
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import transaction

if TYPE_CHECKING:
    from commerce_ops.launch.domain.launch_playbook import StepDefinition

__all__ = ["establish_thread_and_resolve_mention"]


async def establish_thread_and_resolve_mention(
    product_id: ProductId,
    product_name: str,
    product_sku: str,
    product_marketplace: str,
    *,
    step: StepDefinition | None = None,
) -> tuple[str, str | None]:
    """Ensure the launch's thread exists and resolve who to tag in it.

    Opens its own transaction: acquires the thread-establishment lock,
    establishes the thread if it is not already set (or reuses it if it
    is), reloads the launch, and resolves the mention target against
    `step` (a step's named confirmer, or the launch's submitter where
    `step` is `None` or names none).

    Returns `(thread_ts, mention)`. The caller composes and posts its own
    message text and blocks against the result -- this only clears the way
    for that post, it does not make it.
    """
    async with transaction() as db_session:
        launch_store = LaunchRepository(db_session)
        thread_ts = await ensure_launch_thread(
            db_session,
            launch_store,
            product_id,
            product_name,
            product_sku,
            product_marketplace,
            hold_lock=hold_launch_thread_establishment_lock,
            channel=launches_channel,
        )
        launch = await launch_store.get_by_product_id(product_id)
        mention = await resolve_mention_target(launch, step=step) if launch else None
    return thread_ts, mention
