"""Serialising the two paths that advance one launch's gates.

`launch-gate-progression` gives a launch two advancing paths: the recurring
pass, and a member's decision in Slack. A gate crossing is not idempotent —
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

**Two shapes of caller, both correct, for different reasons.** `_advance_one`
(`gate_progression_job.py`), `_advance_after_approval` (`gate_confirmation.py`)
and `launch_thread_lock.py`'s callers all bind the guarded repository write to
the *same* session that holds the lock — the lock's transaction ending rolls
back an unfinished cascade along with releasing the lock, which is exactly
what a gate crossing (cheap, redone by the next pass) wants.

`trigger-clickup-projection-on-launch-events` adds a second shape, reusing
this same lock to also serialize `converge_launch` (ClickUp list/task
creation) between the periodic pass and an eager single-launch trigger — but
does **not** bind `converge_launch`'s writes to the lock's session. A
`converge_launch` call is many ClickUp requests against a rate budget, and
`launch-clickup-sync` guarantees a launch's partial progress survives its own
failure; rebinding those writes to the lock's transaction would turn
`ClickUpMappingRepository`'s per-write commits into savepoints the lock
transaction's own rollback could undo, silently reversing that guarantee.
`pg_advisory_xact_lock` does not care which session performs the guarded
work, only that the lock is held for as long as that work is in flight — a
`transaction()` opened solely to acquire the lock, with the guarded call
awaited to completion before the block exits, gives genuine mutual exclusion
against another same-shaped caller without adopting the same-session shape's
rollback-on-failure semantics. **Do not "fix" this shape by rebinding
`converge_launch`'s collaborators to the lock transaction** — that would
reintroduce exactly the regression this note exists to prevent. See
`trigger-clickup-projection-on-launch-events`'s `design.md`.
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
