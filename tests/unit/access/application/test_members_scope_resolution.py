"""Resolving a Slack user identity against the membership (`access-scope`).

Derived strictly from the delta spec:
`openspec/changes/move-principals-to-roster/specs/access-scope/spec.md`

- ADDED *An active member resolves to the unrestricted scope*
  (all three scenarios)
- MODIFIED *An unknown asker resolves to the empty scope* (its one
  scenario, re-stated against the membership)

This file replaces nothing: `tests/unit/access/application/
test_resolve_scope.py` still stands, and this pass never edits it. The
manifest records it as an obsolete-test candidate, since the grant model
its assertions are built on is REMOVED by this change.

## Why the application level

Each scenario is stated about what *resolution* answers, and resolution
is `resolve_scope` over one collaborator — the members store. The store
is a double here, so this is the project's fast mocked unit tier.

## Members are built through the write use cases, deliberately

The same reasoning `test_members_writes.py` records: the only shape any
artifact fixes for a stored row is what a validated write produces. The
first write against an empty membership must create an admin, because the
last-admin floor rejects any outcome without one.

## The interface under test does not exist yet

Fixed by the artifacts, not invented: `resolve_scope` collapses to
"active member → unrestricted, deactivated or unknown → nothing", the
`SkuResolver` port is deleted, and a failed store read resolves to
`nothing()` rather than raising (`tasks.md` 2.2; delta text "never an
error toward the asker").

INVENTED, recorded in the manifest: the call shape
`resolve_scope(members, identity=...)` — one collaborator now, the
resolver argument gone. Correction point: `_resolve`. The store double
and row accessors are the ones `test_members_writes.py` records; the
files correct together. They are repeated rather than shared because
this pass may write only files matching `tests/**/test_*.py`.

## Expected first-run state

The membership use cases do not exist, so every test here is expected to
fail on an absent target (`ImportError`) — which establishes only
absence.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import pytest

from commerce_ops.access.application import (
    create_member,
    deactivate_member,
    resolve_scope,
)
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

# DERIVED sample values; no artifact fixes example identities.
ADMIN_IDENTITY: Final = "U01ALICE"
MEMBER_IDENTITY: Final = "U03CAROL"
STRANGER_IDENTITY: Final = "U99STRANGER"

PRINCIPAL: Final = "helen"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Store doubles and row accessors (see test_members_writes.py)
# ---------------------------------------------------------------------------


class _FakeMembersStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 3) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self.version
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


class _UnreadableMembersStore(_FakeMembersStore):
    """A store the resolution cannot read."""

    async def load(self) -> tuple[tuple[Any, ...], int]:
        raise ConnectionError("could not connect to the members store")


_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None:
            found.append(nested)
    return tuple(found)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored membership row exposes no {what} under any of {names} — "
        "correct this file's accessor names to the implemented row"
    )


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if str(_field(row, _SLACK_NAMES, "Slack identity")) == identity:
            return _field(row, _ID_NAMES, "generated identifier")
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


# ---------------------------------------------------------------------------
# Call shapes: the single correction points
# ---------------------------------------------------------------------------


async def _create(
    store: _FakeMembersStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
) -> Any:
    return await create_member(
        members=store,
        principal=PRINCIPAL,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _resolve(store: Any, identity: str) -> Any:
    """The one place to correct if `resolve_scope`'s call shape differs."""
    return await resolve_scope(store, identity=identity)


def _permits(scope: Any, product_id: ProductId) -> bool:
    """Reads the scope's `permits` predicate, failing loudly rather than
    defaulting, so no assertion below can be vacuously true."""
    assert hasattr(scope, "permits"), (
        "resolution did not answer with an access scope: the value it "
        "returned exposes no `permits` predicate"
    )
    return bool(scope.permits(product_id))


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


async def _members_with_a_member() -> _FakeMembersStore:
    """One active admin (forced by the last-admin floor) plus one
    ordinary active member."""
    store = _FakeMembersStore()
    await _create(
        store,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create(store, display_name="Carol Member", slack_identity=MEMBER_IDENTITY)
    return store


# ---------------------------------------------------------------------------
# Requirement: An active member resolves to the unrestricted scope
# ---------------------------------------------------------------------------


async def test_an_active_member_sees_every_product() -> None:
    """Scenario: An active member sees every product.

    WHEN the scope is resolved for a Slack user identity an active
    members entry carries
    THEN the resolved scope permits every product identifier.

    "Every" is exercised with three identifiers, none of which the
    members has ever heard of — the delta's "including ones registered
    after the resolution". An implementation enumerating a catalog to
    build the scope would permit none of them.

    The member is an ordinary non-admin entry: membership alone is what
    the delta says confers the unrestricted scope.
    """
    store = await _members_with_a_member()

    scope = await _resolve(store, MEMBER_IDENTITY)

    # SPECIFIED: permits every product identifier.
    assert _permits(scope, _new_product_id()) is True
    assert _permits(scope, _new_product_id()) is True
    assert _permits(scope, ProductId(str(uuid.uuid4()))) is True


async def test_a_deactivated_member_sees_nothing() -> None:
    """Scenario: A deactivated member sees nothing.

    WHEN the scope is resolved for a Slack user identity carried only by
    a deactivated membership entry
    THEN the resolved scope permits no product identifier, and the
    resolution succeeds.

    The same identity resolved to everything one write earlier, so the
    empty scope here is the deactivation at work rather than a constant
    answer — and the still-active admin makes it a per-entry decision
    rather than an empty-members artifact.
    """
    store = await _members_with_a_member()
    product = _new_product_id()
    assert _permits(await _resolve(store, MEMBER_IDENTITY), product) is True

    await deactivate_member(
        members=store, principal=PRINCIPAL, member_id=_id_of(store, MEMBER_IDENTITY)
    )

    scope = await _resolve(store, MEMBER_IDENTITY)

    # SPECIFIED: exactly as a stranger does — permits nothing, and the
    # resolution succeeds (reaching this assertion at all).
    assert _permits(scope, product) is False
    assert _permits(scope, _new_product_id()) is False
    # SPECIFIED: the still-active admin is unaffected.
    assert _permits(await _resolve(store, ADMIN_IDENTITY), product) is True


async def test_an_unreachable_store_fails_closed() -> None:
    """Scenario: An unreachable store fails closed.

    WHEN the scope is resolved while the members store cannot be read
    THEN the resolved scope permits no product identifier, and the
    resolution succeeds without surfacing an error to the asker.

    "Without surfacing an error" is asserted by reaching the assertions
    at all: a propagating `ConnectionError` fails the test before them.
    The answer must still be a scope — `_permits` fails loudly on a
    `None`, so a resolution that quietly answered "nothing at all"
    cannot pass as "the scope permitting nothing".
    """
    store = _UnreadableMembersStore()

    scope = await _resolve(store, ADMIN_IDENTITY)

    # SPECIFIED: fail-closed — no product identifier is permitted.
    assert _permits(scope, _new_product_id()) is False
    assert _permits(scope, _new_product_id()) is False


# ---------------------------------------------------------------------------
# MODIFIED Requirement: An unknown asker resolves to the empty scope
# ---------------------------------------------------------------------------


async def test_a_stranger_sees_nothing() -> None:
    """Scenario: A stranger sees nothing.

    WHEN the scope is resolved for a Slack user identity with no members
    entry
    THEN the resolved scope permits no product identifier, and the
    resolution succeeds.

    The membership is not empty — it holds an admin and a member — so the
    stranger's empty scope is the fail-closed rule at work and not the
    only answer an empty membership could give. "Never a distinct 'unknown'
    result" is asserted by the answer being a scope that answers
    `permits`, not `None`.
    """
    store = await _members_with_a_member()

    scope = await _resolve(store, STRANGER_IDENTITY)

    # SPECIFIED: the same scope type every resolution yields.
    assert scope is not None
    # SPECIFIED: permits no product identifier.
    assert _permits(scope, _new_product_id()) is False
    assert _permits(scope, _new_product_id()) is False
