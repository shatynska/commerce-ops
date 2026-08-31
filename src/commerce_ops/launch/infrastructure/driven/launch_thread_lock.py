"""Serialising concurrent establishment of a launch's Slack thread.

`thread-launch-slack-notifications` establishes a launch's Slack thread
once, the first time any per-product message about it is delivered. Multiple
call sites (entry confirmation, gate asks, pending-result asks, stuck-step
reports) might each try to establish the thread at the same time, and the
race must produce exactly one anchor message.

A Postgres advisory lock keyed on the product satisfies this: it is held in
the database, so it crosses processes, and taken inside `transaction()` it
is held for the whole cascade.

**Transaction-scoped, never session-scoped.** `pg_advisory_xact_lock`
releases when the transaction ends. Its session-scoped sibling would
outlive the transaction on a *pooled* connection and travel to whichever
caller borrowed that connection next, deadlocking both paths for that
product — the drift a shared key alone would not prevent, which is why the
acquire is shared here and not only the key.

See `launch_advisory_lock.py` for the same rationale applied to gate
advancement — this is structured identically but with a separate namespace
so the two concerns cannot contend with each other by accident.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from commerce_ops.shared.domain.identity import ProductId

__all__ = ["hold_launch_thread_establishment_lock", "thread_establishment_lock_key"]

# A namespace constant, distinct from `launch_advisory_lock`'s, so a key
# derived here can never collide with the advance lock on the same product.
# Postgres advisory locks live in one global space; two concerns hashing to
# the same bigint would block each other for no reason anybody could find.
_NAMESPACE = 0x7468_7265  # "thre"

_ACQUIRE = text("SELECT pg_advisory_xact_lock(:key)")


def thread_establishment_lock_key(product_id: ProductId) -> int:
    """The lock key for thread establishment on one product, as a signed 64-bit integer.

    Derived from the product's UUID rather than from a counter, so the two
    paths reach the same key with nothing shared between them but this
    function. Folded into the signed range Postgres accepts.
    """
    raw = uuid.UUID(product_id.value).int ^ (_NAMESPACE << 32)
    # `pg_advisory_xact_lock` takes a signed bigint; wrap rather than
    # truncate so distinct products stay distinct across the fold.
    return (raw % (2**64)) - 2**63


async def hold_launch_thread_establishment_lock(
    db_session: Any, product_id: ProductId
) -> None:
    """Hold the product's thread-establishment lock until the caller's transaction ends.

    Blocks rather than failing where the other path holds it: the caller
    wants to establish or reuse the thread, and waiting for the other path to
    finish is exactly the outcome — it then reads the launch as that path
    left it.

    Must be called inside `transaction()`. Under plain `session()` the
    repositories' own commits would end the transaction and release the
    lock mid-cascade, which is the failure this exists to prevent.
    """
    await db_session.execute(_ACQUIRE, {"key": thread_establishment_lock_key(product_id)})
