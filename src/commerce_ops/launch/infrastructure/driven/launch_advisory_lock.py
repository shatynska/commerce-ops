"""Serialising the two paths that advance one launch's gates.

`launch-gate-progression` gives a launch two advancing paths: the recurring
pass, and a person's decision in Slack. A gate crossing is not idempotent —
it emits `GateOpened` and journals it — so the two must not cross the same
gate at once.

The obvious mechanisms do not work here, which is why this one exists:

- An **in-process lock** spans neither path. The pass runs in the worker,
  the decision listener in the HTTP process.
- A **row lock taken when the launch is loaded** does not span a cascade.
  `LaunchRepository.save` commits its own write, so the lock would be
  released at the first crossing and the second would race.

A Postgres advisory lock keyed on the product satisfies both: it is held in
the database, so it crosses processes, and taken inside `transaction()` it
is held for the whole cascade.

**Transaction-scoped, never session-scoped.** `pg_advisory_xact_lock`
releases when the transaction ends. Its session-scoped sibling would
outlive the transaction on a *pooled* connection and travel to whichever
caller borrowed that connection next, deadlocking both paths for that
product — the drift a shared key alone would not prevent, which is why the
acquire is shared here and not only the key.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from commerce_ops.shared.domain.identity import ProductId

__all__ = ["advisory_lock_key", "hold_launch_advance_lock"]

# A namespace constant, so a key derived here can never collide with an
# advisory lock some other concern takes on the same database. Postgres
# advisory locks live in one global space; two concerns hashing to the same
# bigint would block each other for no reason anybody could find.
_NAMESPACE = 0x6C61_756E  # "laun"

_ACQUIRE = text("SELECT pg_advisory_xact_lock(:key)")


def advisory_lock_key(product_id: ProductId) -> int:
    """The lock key for one product, as a signed 64-bit integer.

    Derived from the product's UUID rather than from a counter, so the two
    paths reach the same key with nothing shared between them but this
    function. Folded into the signed range Postgres accepts.
    """
    raw = uuid.UUID(product_id.value).int ^ (_NAMESPACE << 32)
    # `pg_advisory_xact_lock` takes a signed bigint; wrap rather than
    # truncate so distinct products stay distinct across the fold.
    return (raw % (2**64)) - 2**63


async def hold_launch_advance_lock(db_session: Any, product_id: ProductId) -> None:
    """Hold the product's advance lock until the caller's transaction ends.

    Blocks rather than failing where the other path holds it: the caller
    wants to advance the launch, and waiting for the other path to finish
    is exactly the outcome — it then reads the launch as that path left it.

    Must be called inside `transaction()`. Under plain `session()` the
    repositories' own commits would end the transaction and release the
    lock mid-cascade, which is the failure this exists to prevent.
    """
    await db_session.execute(_ACQUIRE, {"key": advisory_lock_key(product_id)})
