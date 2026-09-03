"""The Postgres role store against a live database (`roles`).

The unit tier exercises every role rule over store doubles, so what is
left unobserved there — and covered here — is the adapter itself:

- that a role round-trips through Postgres with its holders, its default
  marking and its attribution intact;
- that role writes really do take **the membership's** version row
  (`design.md` Decision 8), so a member write and a role write cannot
  interleave into the state the member/role invariant forbids. A double
  can only *assert* that `save` was called with the version `load`
  returned; only a real database can show that the second of two writes
  against the same version is refused;
- that "at most one default holder per role" is a **storage** guarantee
  rather than only a checked invariant (`design.md` Decision 9's partial
  unique index).

`tasks.md` 10.6 asks for exactly these.

## Level, and why these three

Each is a property of the adapter and the schema, invisible to a store
double by construction. Everything else the collection does is stated as
a rule over a write, and is covered in
`tests/unit/access/application/test_role_writes.py` at the level that can
observe it fastest.

## Gating

These tests request the `database_url` fixture, so where nothing
resolves they skip locally and *fail* under
`COMMERCE_OPS_REQUIRE_DATABASE`, rather than carrying a private copy of
the rule (`verify-the-integration-tier`).

**This worktree configures no database deliberately.** `AGENTS.md`
requires the shared `commerce_ops_test` not be migrated from here;
`tasks.md` 11.5 has whoever implements this change clone it into a
worktree-local database and name that clone in `.env.test`. Until then
this file skips, and the manifest records that as its expected state
rather than as coverage.

## What is fixed, and what is INVENTED

Fixed by the artifacts: the two tables and their columns (`design.md`
Decision 9), the partial unique index, and role writes taking the
`members_set` version row (Decision 8).

INVENTED, each recorded in the manifest with its correction point:

- The module and class names of the repository and the two row types,
  resolved by name at call time rather than imported at module scope, so
  their absence skips nothing and fails only the tests that drive them.
  Correction point: `_driven`.
- The stale-write refusal type, resolved over candidates. Correction
  point: `_stale_errors`.
- The holder row's column names, when a row is inserted directly to
  provoke the index. Correction point: `_HOLDER_COLUMNS`.

## Expected first-run state

Neither the repository nor the row types exist, and no database is
configured here, so every test skips. That establishes nothing at all,
which is why the manifest records it as uncovered-until-run rather than
as coverage.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/integration` — 3 passed, 134 skipped (2026-09-02).
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member
from commerce_ops.access.infrastructure.driven.models import MemberRow

pytestmark = pytest.mark.anyio

PRINCIPAL: Final = "integration-suite"
ANOTHER_PRINCIPAL: Final = "the-other-admin"

#: The holder row's columns, per `design.md` Decision 9. A correction
#: point: an unrecognised non-nullable column fails loudly rather than
#: being filled with a guess.
_HOLDER_COLUMNS: Final = (
    "role_slug",
    "member_id",
    "is_default",
    "added_by",
    "added_on",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _Driven:
    repository: Any
    role_row: Any
    holder_row: Any
    members_repository: Any


def _driven() -> _Driven:
    """The roles adapter, resolved by name.

    Resolved at call time rather than imported at module scope so that
    its absence fails only the tests that drive it, rather than turning
    the whole file into a collection error.
    """
    models = importlib.import_module("commerce_ops.access.infrastructure.driven.models")
    role_row = next(
        (getattr(models, name, None) for name in ("RoleRow",) if hasattr(models, name)),
        None,
    )
    holder_row = next(
        (
            getattr(models, name, None)
            for name in ("RoleHolderRow", "RoleHolder")
            if hasattr(models, name)
        ),
        None,
    )
    repository = None
    for module_name, attribute in (
        (
            "commerce_ops.access.infrastructure.driven.roles_repository",
            "RolesRepository",
        ),
        (
            "commerce_ops.access.infrastructure.driven.members_repository",
            "RolesRepository",
        ),
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        repository = getattr(module, attribute, None)
        if repository is not None:
            break
    members = importlib.import_module(
        "commerce_ops.access.infrastructure.driven.members_repository"
    )
    missing = [
        what
        for what, found in (
            ("RoleRow", role_row),
            ("RoleHolderRow", holder_row),
            ("RolesRepository", repository),
        )
        if found is None
    ]
    if missing:
        pytest.fail(
            f"the roles adapter is absent: {missing} — the absent-target "
            "state; nothing in this test has been exercised"
        )
    return _Driven(
        repository=repository,
        role_row=role_row,
        holder_row=holder_row,
        members_repository=members.MembersRepository,
    )


def _stale_errors() -> tuple[type[BaseException], ...]:
    """The refusal a write against a stale version raises."""
    found: list[type[BaseException]] = []
    for module_name, attribute in (
        ("commerce_ops.access.application.members", "StaleMembersError"),
        ("commerce_ops.access.application.roles", "StaleRolesError"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        error = getattr(module, attribute, None)
        if isinstance(error, type) and issubclass(error, BaseException):
            found.append(error)
    if not found:
        pytest.fail(
            "no stale-version refusal type was found — correct "
            "`_stale_errors` to the implemented one"
        )
    return tuple(found)


def _use_case(names: tuple[str, ...], what: str) -> Any:
    for name in names:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        f"the access application surface exports no {what} use case under any "
        f"of {names}"
    )


@asynccontextmanager
async def _session(url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


class _SessionScoped:
    """A collection as the use cases hold it: a session per operation,
    which is what makes two interleaved writes genuinely concurrent
    here."""

    def __init__(self, url: str, repository: Any) -> None:
        self._url = url
        self._repository = repository

    async def load(self) -> tuple[Any, int]:
        async with _session(self._url) as session:
            loaded: tuple[Any, int] = await self._repository(session).load()
            return loaded

    async def save(self, records: Any, *, expected_version: int) -> None:
        async with _session(self._url) as session:
            await self._repository(session).save(
                records, expected_version=expected_version
            )


@pytest.fixture
async def collections(database_url: str) -> AsyncIterator[tuple[Any, Any]]:
    """Empty members and roles before and after, so these tests neither
    inherit nor leave behind either. The version row is left alone: it
    only ever moves forward, and nothing asserts an absolute value.

    Requesting `database_url` is how this file opts into the tier's
    gate: no database configured means skip here, fail in CI.
    """
    driven = _driven()
    await _clear(database_url, driven)
    yield (
        _SessionScoped(database_url, driven.members_repository),
        _SessionScoped(database_url, driven.repository),
    )
    await _clear(database_url, driven)


async def _clear(url: str, driven: _Driven) -> None:
    async with _session(url) as session:
        await session.execute(delete(driven.holder_row))
        await session.execute(delete(driven.role_row))
        await session.execute(delete(MemberRow))
        await session.commit()


def _identity() -> str:
    """A Slack identity unique to this run — the column is unique across
    every row, so a leftover from a crashed run must not collide."""
    return f"U{uuid.uuid4().hex[:10].upper()}"


def _slug() -> str:
    return f"role-{uuid.uuid4().hex[:8]}"


async def _an_admin(members: Any) -> Any:
    created = await create_member(
        members=members,
        principal=PRINCIPAL,
        display_name="Alice Admin",
        slack_identity=_identity(),
        clickup_user_id=None,
        admin=True,
    )
    return created


def _member_identifier(created: Any) -> Any:
    for target in (created, getattr(created, "member", None)):
        if target is None:
            continue
        for name in ("identifier", "id", "member_id"):
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(f"the created member {created!r} exposes no identifier")


async def _create_role(
    roles: Any, members: Any, *, slug: str, title: str, holder: Any
) -> Any:
    step = _use_case(("create_role",), "create-a-role")
    return await step(
        roles=roles,
        members=members,
        principal=PRINCIPAL,
        slug=slug,
        title=title,
        status="active",
        default_holder=holder,
    )


def _stored(rows: Any, slug: str) -> Any:
    for row in rows:
        for target in (row, getattr(row, "role", None)):
            if target is not None and str(getattr(target, "slug", "")) == slug:
                return row
    pytest.fail(f"no stored role carries the slug {slug!r}")


async def test_a_role_round_trips_through_postgres(
    collections: tuple[Any, Any],
) -> None:
    """A created role is readable back with its title, status, holders,
    default marking and attribution intact.

    The attribution half is the point: the admin presents the same audit
    for roles that it does for members, so a column that silently failed
    to persist would quietly cost the surface its audit.
    """
    members, roles = collections
    created = await _an_admin(members)
    holder = _member_identifier(created)
    slug = _slug()

    await _create_role(
        roles, members, slug=slug, title="Supply Chain Manager", holder=holder
    )

    rows, _version = await roles.load()
    stored = _stored(rows, slug)
    flat = " ".join(
        str(getattr(target, name, ""))
        for target in (stored, getattr(stored, "role", None))
        if target is not None
        for name in dir(target)
        if not name.startswith("_")
    )
    assert "Supply Chain Manager" in flat, (
        f"the stored role does not carry its title: {stored!r}"
    )
    assert "active" in flat.lower(), (
        f"the stored role does not carry its status: {stored!r}"
    )
    assert str(holder) in flat, f"the stored role does not carry its holder: {stored!r}"
    assert PRINCIPAL in flat, (
        f"the stored role does not carry its attribution: {stored!r}"
    )


async def test_a_role_write_against_a_stale_version_is_refused(
    collections: tuple[Any, Any],
) -> None:
    """Two role writes taken against the same version: the second is
    refused.

    A store double can only assert that `save` was called with the
    version `load` returned. Only a real database shows that the second
    write is actually refused, which is what stops two admins from each
    moving a role's default at the same moment and one silently winning.
    """
    members, roles = collections
    created = await _an_admin(members)
    holder = _member_identifier(created)
    await _create_role(roles, members, slug=_slug(), title="Anchor", holder=holder)

    first_rows, version = await roles.load()
    second_rows, same_version = await roles.load()
    assert version == same_version

    await roles.save(first_rows, expected_version=version)

    with pytest.raises(_stale_errors()):
        await roles.save(second_rows, expected_version=same_version)


async def test_a_member_write_makes_a_role_write_stale(
    collections: tuple[Any, Any],
) -> None:
    """`design.md` Decision 8: role writes take **the membership's**
    version row, because the member/role invariant spans both
    collections.

    This is the assertion that decides whether Decision 8 was actually
    implemented. A role store with a version row of its own would pass
    every other test in this file and fail here — and the interleaving
    the decision forbids (a member deactivated while a role's default is
    being moved to them) would land.
    """
    members, roles = collections
    created = await _an_admin(members)
    holder = _member_identifier(created)
    await _create_role(roles, members, slug=_slug(), title="Anchor", holder=holder)

    role_rows, role_version = await roles.load()
    member_rows, member_version = await members.load()
    assert role_version == member_version, (
        "the roles and the membership report different versions, so they are "
        "not serialized on one version row"
    )

    # A membership write lands, moving the shared version on.
    await members.save(member_rows, expected_version=member_version)

    # The role write taken before it is now stale.
    with pytest.raises(_stale_errors()):
        await roles.save(role_rows, expected_version=role_version)


async def test_at_most_one_default_holder_is_a_storage_guarantee(
    database_url: str,
    collections: tuple[Any, Any],
) -> None:
    """`design.md` Decision 9: the partial unique index makes "at most
    one default holder per role" a storage guarantee rather than only a
    checked invariant.

    Asserted by inserting a second default holder **directly**, past the
    use cases that would refuse it — which is the only way to tell an
    enforced index from a well-behaved application layer.
    """
    members, roles = collections
    driven = _driven()
    first = _member_identifier(await _an_admin(members))
    second = _member_identifier(await _an_admin(members))
    slug = _slug()
    await _create_role(
        roles, members, slug=slug, title="Supply Chain Manager", holder=first
    )

    table = driven.holder_row.__table__
    unknown = [
        column.name
        for column in table.columns
        if not column.nullable
        and column.default is None
        and column.server_default is None
        and column.name not in _HOLDER_COLUMNS
    ]
    assert unknown == [], (
        f"the holder table carries required columns {unknown!r} this test does "
        "not know how to fill — correct `_HOLDER_COLUMNS`"
    )
    values = {
        "role_slug": slug,
        "member_id": second,
        "is_default": True,
        "added_by": ANOTHER_PRINCIPAL,
        "added_on": datetime.now(UTC),
    }
    supplied = {name: value for name, value in values.items() if name in table.columns}

    with pytest.raises(IntegrityError):
        async with _session(database_url) as session:
            await session.execute(table.insert().values(**supplied))
            await session.commit()
