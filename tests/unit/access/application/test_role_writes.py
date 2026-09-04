"""The role collection's validated, attributed write use cases (`roles`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/roles/spec.md` — five
of its six ADDED requirements, twenty-five scenarios:

- *A role is a declared position with coherent data* (5)
- *Every role write is validated whole and attributed* (4)
- *An active role always has a default holder* (3)
- *Holders are managed as a set and the default is moved deliberately* (6)
- *A role is retired, never deleted* (6)

The sixth requirement (*The roles are seeded before the application
serves*) is covered in `test_role_seeding.py`; the member/role invariant
`members` states from its own side is covered in
`test_member_deactivation_role_invariant.py`.

## Why the application level

Every scenario above is stated about a *write* and what the collection
holds afterwards — "nothing is persisted", "a subsequent read observes
the collection exactly as it was", "records who retired it and when".
The domain alone cannot observe persistence, so the smallest observing
unit is the write use case over store doubles: no Postgres, no I/O, the
project's fast mocked unit tier. This is the level
`tests/unit/access/application/test_members_writes.py` established for
the membership's identical rules, and this file is shaped after it.

`tasks.md` 10.1 asks for domain-level tests of the role entity and 10.2
for use-case tests. Both are written here, at one level, because every
scenario the delta states is stated over a write: splitting them would
oblige an invented `Role` constructor API that no artifact fixes, in
order to re-assert the same rules one layer down. Recorded in the
manifest as a deliberate deviation from the task list's split, not from
its coverage.

## Seed state is built through the use cases, deliberately

The only shape any artifact fixes for a stored role is whatever the write
use cases produce, so these tests build their starting roles by *calling*
`create_role` rather than by inventing a row class. The trade — a
`create_role` defect fails tests written for `retire`/`move default` too
— is the one `test_members_writes.py` recorded for the membership, and is
recorded again in the manifest.

Members are likewise built through `create_member`, which already exists.

## What is fixed, and what is INVENTED

Fixed by the delta: the slug rules; the three statuses and the four
transitions; that `create` takes the initial status and, where `active`,
the default holder in one write; that only the title is updatable; that
holders are a set with at most one default; that no holder is ever
promoted implicitly; that every rejected write persists nothing and
reports every fault; that every landed write records a principal and a
time.

INVENTED, each recorded in the manifest with its correction point:

- The use-case names, resolved over candidates by `_use_case`, which
  fails loudly naming them. Correction point: the `_*_NAMES` tuples.
- Their call shapes — `roles=`, `members=`, `principal=`, `slug=`,
  `title=`, `status=`, `default_holder=`, `member_id=` — attempted in
  order, only argument-shape `TypeError`s falling through, so a genuine
  refusal is never mistaken for a wrong signature. Correction points:
  the `_*` call helpers.
- Whether a status is passed as a string or a domain enum: the string is
  tried first and the enum resolved from the domain module if the string
  is refused. Correction point: `_status`.
- The stored role's attribute spellings, read through `_field` with
  candidate names. Correction points: the `_*_NAMES` accessor tuples.
- `REFUSED`, the tuple of acceptable exception types where the delta
  fixes the outcome ("refused", "rejected") but not the type — the
  precedent `test_members_writes.py` set.
- That the roles port mirrors the membership's `load() -> (rows,
  version)` / `save(rows, expected_version=...)`, over a version cell
  shared with the membership store (`design.md` Decision 8). Correction
  point: `_FakeRolesStore` and `_Version`.

What must survive any of those corrections is what each test asserts:
what was persisted, what was not, and who is recorded as having done it.

## Expected first-run state

`commerce_ops.access.application` exports none of these use cases, so
every test here is expected to fail on an absent target — the use-case
resolver fails naming its candidates, before any assertion below has run.
Per `ai-toolkit:testing` that failure establishes only absence.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02). `uv run pytest tests/integration` — 3 passed, 134 skipped:
this worktree configures no database, deliberately, since the shared
`commerce_ops_test` must not be migrated from here.
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Final

import pytest

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member, deactivate_member
from tests.support.admin import ADMIN_IDENTITY
from tests.support.fixtures import PRINCIPAL

pytestmark = pytest.mark.anyio

SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
THIRD_IDENTITY: Final = "U04DAVE"
FOURTH_IDENTITY: Final = "U05ERIN"

ADMIN_NAME: Final = "Alice Admin"
SECOND_ADMIN_NAME: Final = "Bob Admin"
MEMBER_NAME: Final = "Carol Member"
THIRD_NAME: Final = "Dave Deputy"
FOURTH_NAME: Final = "Erin Elsewhere"

ANOTHER_PRINCIPAL: Final = "the-second-admin"

DRAFT: Final = "draft"
ACTIVE: Final = "active"
RETIRED: Final = "retired"


def _refused_types() -> tuple[type[BaseException], ...]:
    """The acceptable refusal types. The delta fixes the outcome, not the
    type; the domain's own aggregated error is included where it exists."""
    found: list[type[BaseException]] = [ValueError, TypeError]
    for module_name, attribute in (
        ("commerce_ops.access.domain.roles", "InvalidRolesError"),
        ("commerce_ops.access.domain.members", "InvalidMembersError"),
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        error = getattr(module, attribute, None)
        if isinstance(error, type) and issubclass(error, BaseException):
            found.append(error)
    return tuple(found)


REFUSED: Final = _refused_types()

#: A refusal *or* an argument-shape rejection. A signature that cannot
#: express a forbidden write refuses it as surely as a validator does, so
#: both count where a test asserts that something is not accepted.
REFUSED_OR_UNEXPRESSIBLE: tuple[type[BaseException], ...] = (*REFUSED, TypeError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# The store doubles
# ---------------------------------------------------------------------------


class _Version:
    """The single write version the two collections share.

    `design.md` Decision 8: role writes take the same version row
    membership writes take, because the member/role invariant spans both
    and two version rows would let a deactivation and a default move
    interleave into the state the invariant forbids.
    """

    def __init__(self, value: int = 7) -> None:
        self.value = value


class _FakeMembersStore:
    """In-memory whole-set members store — the port
    `test_members_writes.py` fixed, with its version cell now shared."""

    def __init__(self, version: _Version | None = None) -> None:
        self.rows: tuple[Any, ...] = ()
        self._version = version or _Version()
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    @property
    def version(self) -> int:
        return self._version.value

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self._version.value

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self._version.value, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self._version.value}"
        )
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1


class _FakeRolesStore:
    """The roles half of the same boundary, shaped after the membership's
    port because nothing in the artifacts suggests a different one."""

    def __init__(self, version: _Version | None = None) -> None:
        self.rows: tuple[Any, ...] = ()
        self._version = version or _Version()
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    @property
    def version(self) -> int:
        return self._version.value

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self._version.value

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self._version.value, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self._version.value}"
        )
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1

    # Aliases, so an implementation naming the roles port's operations
    # apart from the membership's is still exercised rather than failing
    # at the seam. Correction point for a differently named port.
    async def load_roles(self) -> tuple[tuple[Any, ...], int]:
        return await self.load()

    async def save_roles(self, rows: Any, *, expected_version: int) -> None:
        await self.save(rows, expected_version=expected_version)


class _Collections:
    """The pair, with one shared version."""

    def __init__(self) -> None:
        version = _Version()
        self.members = _FakeMembersStore(version)
        self.roles = _FakeRolesStore(version)


# ---------------------------------------------------------------------------
# Accessors: the single correction point for attribute spellings
# ---------------------------------------------------------------------------

_MEMBER_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_MEMBER_ACTIVE_NAMES: Final = ("active", "is_active")
_MEMBER_ADMIN_NAMES: Final = ("admin", "is_admin")

_SLUG_NAMES: Final = ("slug", "identifier", "id")
_TITLE_NAMES: Final = ("title", "name")
_STATUS_NAMES: Final = ("status", "state", "lifecycle_status")
_HOLDERS_NAMES: Final = ("holders", "role_holders", "members")
_DEFAULT_NAMES: Final = (
    "default_holder",
    "default_holder_id",
    "default_member_id",
    "default",
)

_CREATED_BY: Final = ("created_by",)
_CREATED_ON: Final = ("created_on", "created_at")
_UPDATED_BY: Final = ("updated_by",)
_UPDATED_ON: Final = ("updated_on", "updated_at")
_RETIRED_BY: Final = ("retired_by",)
_RETIRED_ON: Final = ("retired_on", "retired_at")
_UNRETIRED_BY: Final = ("unretired_by", "un_retired_by", "reactivated_by")
_UNRETIRED_ON: Final = ("unretired_on", "un_retired_on", "reactivated_on")


def _targets(row: Any) -> tuple[Any, ...]:
    """The row itself plus any nested record object, since no artifact
    fixes whether attribution sits beside the data or wraps it."""
    found = [row]
    for attribute in ("role", "member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _has(row: Any, names: tuple[str, ...]) -> bool:
    return any(hasattr(target, name) for target in _targets(row) for name in names)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    """Reads one field of a stored row, failing loudly rather than
    defaulting, so no assertion below can pass vacuously."""
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored row exposes no {what} under any of {names} — correct "
        "this file's accessor names to the implemented row"
    )


def _scalar(value: Any) -> str:
    return str(getattr(value, "value", value))


# --- members ---------------------------------------------------------------


def _member_id(row: Any) -> Any:
    return _field(row, _MEMBER_ID_NAMES, "generated identifier")


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _member_row(store: _FakeMembersStore, identity: str) -> Any:
    for row in store.rows:
        if _slack(row) == identity:
            return row
    pytest.fail(f"no stored row carries the Slack identity {identity!r}")


def _id_of(store: _FakeMembersStore, identity: str) -> Any:
    return _member_id(_member_row(store, identity))


def _is_member_active(store: _FakeMembersStore, identity: str) -> bool:
    return bool(
        _field(_member_row(store, identity), _MEMBER_ACTIVE_NAMES, "active flag")
    )


def _is_member_admin(store: _FakeMembersStore, identity: str) -> bool:
    return bool(_field(_member_row(store, identity), _MEMBER_ADMIN_NAMES, "admin flag"))


# --- roles -----------------------------------------------------------------


def _slug(row: Any) -> str:
    return str(_field(row, _SLUG_NAMES, "slug"))


def _title(row: Any) -> str:
    return str(_field(row, _TITLE_NAMES, "title"))


def _status_of(row: Any) -> str:
    return _scalar(_field(row, _STATUS_NAMES, "lifecycle status")).lower()


def _holder_identifier(holder: Any) -> str:
    """One holder's member identifier, whatever a holder is: a bare
    identifier, or a record carrying one."""
    if isinstance(holder, (str, bytes, uuid.UUID)):
        return str(holder)
    for name in ("member_id", "member", "id", "identifier", "holder"):
        if hasattr(holder, name):
            value = getattr(holder, name)
            if isinstance(value, (str, bytes, uuid.UUID, int)):
                return str(value)
            if value is not None and name in ("member", "holder"):
                return _holder_identifier(value)
    pytest.fail(
        f"a stored holder {holder!r} exposes no member identifier — correct "
        "`_holder_identifier` to the implemented holder record"
    )


def _holders(row: Any) -> set[str]:
    carried = _field(row, _HOLDERS_NAMES, "holders")
    return {_holder_identifier(holder) for holder in carried}


def _default_holder(row: Any) -> str | None:
    """The role's default holder identifier, or `None` where it has
    none — read off a dedicated field where the row carries one, and off
    the holder marked default otherwise."""
    if _has(row, _DEFAULT_NAMES):
        value = _field(row, _DEFAULT_NAMES, "default holder")
        return None if value is None else _holder_identifier(value)
    carried = _field(row, _HOLDERS_NAMES, "holders")
    marked = [
        holder
        for holder in carried
        if any(
            bool(getattr(holder, name, False))
            for name in ("is_default", "default", "is_the_default")
        )
    ]
    if len(marked) > 1:
        pytest.fail(
            f"{len(marked)} holders of {_slug(row)!r} are marked default; at "
            "most one may be"
        )
    return _holder_identifier(marked[0]) if marked else None


def _role(store: _FakeRolesStore, slug: str) -> Any:
    for row in store.rows:
        if _slug(row) == slug:
            return row
    pytest.fail(
        f"no stored role carries the slug {slug!r} (stored: "
        f"{sorted(_slug(row) for row in store.rows)})"
    )


def _slugs(store: _FakeRolesStore) -> set[str]:
    return {_slug(row) for row in store.rows}


def _faults(error: BaseException) -> tuple[str, ...]:
    """Every fault the rejection reports, however the aggregated error
    carries them."""
    for attribute in ("faults", "errors", "messages", "reasons"):
        carried = getattr(error, attribute, None)
        if isinstance(carried, (list, tuple)) and carried:
            return tuple(str(fault) for fault in carried)
    if error.args and isinstance(error.args[0], (list, tuple)):
        return tuple(str(fault) for fault in error.args[0])
    return tuple(line for line in str(error).splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Use-case resolution and call shapes: the single correction point
# ---------------------------------------------------------------------------

_CREATE_NAMES: Final = ("create_role",)
_UPDATE_NAMES: Final = ("update_role", "rename_role")
_RETIRE_NAMES: Final = ("retire_role",)
_UNRETIRE_NAMES: Final = (
    "unretire_role",
    "un_retire_role",
    "restore_role",
    "reinstate_role",
    "activate_role",
)
_ACTIVATE_NAMES: Final = ("activate_role", "unretire_role", "un_retire_role")
_ADD_HOLDER_NAMES: Final = ("add_role_holder", "add_holder", "add_role_member")
_REMOVE_HOLDER_NAMES: Final = (
    "remove_role_holder",
    "remove_holder",
    "remove_role_member",
)
_MOVE_DEFAULT_NAMES: Final = (
    "move_role_default",
    "move_default_holder",
    "move_default",
    "set_role_default",
    "set_default_holder",
)


def _use_case(names: tuple[str, ...], what: str) -> Any:
    for name in names:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        f"the access application surface exports no {what} use case under "
        f"any of {names} — correct this file's candidate names to the "
        "implemented one"
    )


def _is_argument_shape_error(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _invoke(step: Any, attempts: tuple[Callable[[], Any], ...], what: str) -> Any:
    """Runs the first call shape the use case's signature accepts.

    Only argument-shape `TypeError`s fall through, so a genuine refusal
    is never mistaken for a wrong signature — the rule
    `test_members_bootstrap.py` established.
    """
    last: TypeError | None = None
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _is_argument_shape_error(error):
                raise
            last = error
    pytest.fail(
        f"no attempted call shape matched the {what} use case's signature; "
        f"last argument error: {last}"
    )


def _status(value: str) -> Any:
    """The status as the use case wants it: the plain string, or the
    domain enum member where the domain declares one."""
    try:
        module = importlib.import_module("commerce_ops.access.domain.roles")
    except ModuleNotFoundError:
        return value
    for name in ("RoleStatus", "Status", "RoleLifecycle"):
        enum = getattr(module, name, None)
        members = getattr(enum, "__members__", None)
        if not members:
            continue
        for member in members.values():
            if _scalar(member).lower() == value:
                return member
    return value


async def _create_role(
    collections: _Collections,
    *,
    slug: str,
    title: str,
    status: str = DRAFT,
    default_holder: Any = None,
    principal: str = PRINCIPAL,
) -> Any:
    step = _use_case(_CREATE_NAMES, "create-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": principal,
        "slug": slug,
        "title": title,
    }
    return await _invoke(
        step,
        (
            lambda: step(
                **common, status=_status(status), default_holder=default_holder
            ),
            lambda: step(**common, status=status, default_holder=default_holder),
            lambda: step(
                **common, status=_status(status), default_holder_id=default_holder
            ),
            lambda: step(**common, status=_status(status), holder=default_holder),
            lambda: step(**common, status=_status(status)),
        ),
        "create-a-role",
    )


async def _update_role(
    collections: _Collections,
    slug: str,
    *,
    principal: str = PRINCIPAL,
    **fields: Any,
) -> Any:
    step = _use_case(_UPDATE_NAMES, "update-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": principal,
    }
    return await _invoke(
        step,
        (
            lambda: step(**common, slug=slug, **fields),
            lambda: step(**common, role_slug=slug, **fields),
            lambda: step(
                roles=collections.roles, principal=principal, slug=slug, **fields
            ),
        ),
        "update-a-role",
    )


async def _role_action(
    names: tuple[str, ...],
    what: str,
    collections: _Collections,
    slug: str,
    *,
    principal: str = PRINCIPAL,
    member_id: Any = None,
) -> Any:
    step = _use_case(names, what)
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": principal,
    }
    if member_id is None:
        attempts: tuple[Callable[[], Any], ...] = (
            lambda: step(**common, slug=slug),
            lambda: step(**common, role_slug=slug),
            lambda: step(roles=collections.roles, principal=principal, slug=slug),
        )
    else:
        attempts = (
            lambda: step(**common, slug=slug, member_id=member_id),
            lambda: step(**common, role_slug=slug, member_id=member_id),
            lambda: step(**common, slug=slug, holder=member_id),
            lambda: step(**common, slug=slug, member=member_id),
            lambda: step(**common, slug=slug, default_holder=member_id),
        )
    return await _invoke(step, attempts, what)


async def _retire(collections: _Collections, slug: str, **kwargs: Any) -> Any:
    return await _role_action(
        _RETIRE_NAMES, "retire-a-role", collections, slug, **kwargs
    )


async def _activate(collections: _Collections, slug: str, **kwargs: Any) -> Any:
    return await _role_action(
        _ACTIVATE_NAMES, "activate-a-role", collections, slug, **kwargs
    )


async def _unretire(collections: _Collections, slug: str, **kwargs: Any) -> Any:
    return await _role_action(
        _UNRETIRE_NAMES, "un-retire-a-role", collections, slug, **kwargs
    )


async def _add_holder(
    collections: _Collections, slug: str, member_id: Any, **kwargs: Any
) -> Any:
    return await _role_action(
        _ADD_HOLDER_NAMES,
        "add-a-holder",
        collections,
        slug,
        member_id=member_id,
        **kwargs,
    )


async def _remove_holder(
    collections: _Collections, slug: str, member_id: Any, **kwargs: Any
) -> Any:
    return await _role_action(
        _REMOVE_HOLDER_NAMES,
        "remove-a-holder",
        collections,
        slug,
        member_id=member_id,
        **kwargs,
    )


async def _move_default(
    collections: _Collections, slug: str, member_id: Any, **kwargs: Any
) -> Any:
    return await _role_action(
        _MOVE_DEFAULT_NAMES,
        "move-the-default",
        collections,
        slug,
        member_id=member_id,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Starting states
# ---------------------------------------------------------------------------


async def _create_member(
    store: _FakeMembersStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
    principal: str = PRINCIPAL,
) -> Any:
    return await create_member(
        members=store,
        principal=principal,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


async def _membership() -> _Collections:
    """Two active admins and three ordinary active members — enough for
    a role to hold several people and for one of them to be deactivated
    without meeting the last-admin floor."""
    collections = _Collections()
    await _create_member(
        collections.members,
        display_name=ADMIN_NAME,
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name=SECOND_ADMIN_NAME,
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    for name, identity in (
        (MEMBER_NAME, MEMBER_IDENTITY),
        (THIRD_NAME, THIRD_IDENTITY),
        (FOURTH_NAME, FOURTH_IDENTITY),
    ):
        await _create_member(
            collections.members, display_name=name, slack_identity=identity
        )
    return collections


def _snapshot(collections: _Collections) -> tuple[Any, ...]:
    return (
        collections.roles.rows,
        collections.roles.version,
        len(collections.roles.saves),
        collections.members.rows,
        len(collections.members.saves),
    )


def _assert_unchanged(collections: _Collections, before: tuple[Any, ...]) -> None:
    """SPECIFIED across many scenarios: a rejected write persists
    nothing — asserted as the stored roles, the shared version, the
    number of role saves and the membership all standing exactly where
    they stood."""
    assert _snapshot(collections) == before, (
        "a rejected write reached a store: the collection must be left "
        "exactly as it was"
    )


# ===========================================================================
# Requirement: A role is a declared position with coherent data
# ===========================================================================


async def test_a_role_is_identified_by_its_slug() -> None:
    """Scenario: A role is identified by its slug.

    WHEN a role is created with a slug and a title
    THEN the role is retrievable by that slug, and no separate generated
    identifier is issued for it.

    "Retrievable by that slug" is asserted twice over: the slug locates
    the stored role, and a subsequent `update` addressed by that slug
    lands on the same role. Without the second half, an implementation
    storing a slug it cannot address by would pass.

    "No separate generated identifier" is asserted as the absence of any
    UUID-shaped field on the stored role — the discriminating shape,
    since `members` generates exactly that and the delta says roles
    deliberately do not.
    """
    collections = await _membership()

    await _create_role(collections, slug="supply-chain", title="Supply Chain Manager")

    # SPECIFIED: retrievable by that slug.
    role = _role(collections.roles, "supply-chain")
    assert _title(role) == "Supply Chain Manager"

    await _update_role(collections, "supply-chain", title="Supply Chain Lead")
    assert _title(_role(collections.roles, "supply-chain")) == "Supply Chain Lead"
    assert _slugs(collections.roles) == {"supply-chain"}

    # SPECIFIED: no separate generated identifier is issued.
    generated = []
    for target in _targets(role):
        for name in dir(target):
            if name.startswith("_"):
                continue
            try:
                value = getattr(target, name)
            except Exception:  # noqa: BLE001,S112 - a property may refuse
                continue
            if isinstance(value, uuid.UUID):
                generated.append(name)
            elif isinstance(value, str):
                try:
                    uuid.UUID(value)
                except (ValueError, AttributeError, TypeError):
                    continue
                generated.append(name)
    assert generated == [], (
        f"the stored role carries generated identifier(s) {generated!r}; the "
        "delta states the slug is the role's identifier and there is no "
        "second, generated one"
    )


@pytest.mark.parametrize(
    "slug",
    [
        pytest.param("Supply-Chain", id="uppercase"),
        pytest.param("-supply-chain", id="leading-hyphen"),
        pytest.param("  supply-chain  ", id="surrounding-whitespace"),
        pytest.param("supply--chain", id="doubled-interior-hyphen"),
        pytest.param("supply-chain-", id="trailing-hyphen"),
        pytest.param("", id="empty"),
        pytest.param("supply chain", id="interior-space"),
    ],
)
async def test_a_malformed_slug_is_rejected(slug: str) -> None:
    """Scenario: A malformed slug is rejected.

    WHEN a role is created with a slug carrying an uppercase letter, a
    leading hyphen, or surrounding whitespace
    THEN the write is rejected with a fault naming the slug, and nothing
    is persisted.

    The scenario names three malformations; the requirement's own
    sentence fixes four more (non-empty, single interior hyphens, begins
    and ends alphanumeric), and each is parametrized here rather than
    left to one representative — a validator catching the case is not
    evidence it catches the class.
    """
    collections = await _membership()
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _create_role(collections, slug=slug, title="Supply Chain Manager")

    # SPECIFIED: a fault naming the slug. An empty slug has no text to
    # name, so the fault is required to name the field instead.
    text = str(excinfo.value).lower()
    if slug.strip():
        assert slug.strip().lower() in text or slug.lower() in text, (
            f"the refusal does not name the offending slug {slug!r}: {excinfo.value}"
        )
    else:
        assert "slug" in text, f"the refusal does not name the slug: {excinfo.value}"
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)


@pytest.mark.parametrize(
    "existing_status", [DRAFT, ACTIVE, RETIRED], ids=["draft", "active", "retired"]
)
async def test_a_duplicate_slug_is_rejected(existing_status: str) -> None:
    """Scenario: A duplicate slug is rejected.

    WHEN a role is created with a slug an existing role already carries
    — even a retired one
    THEN the write is rejected with a fault naming that slug, and
    nothing is persisted.

    Parametrized over all three statuses: the retired case is the
    discriminating one, since an implementation checking uniqueness
    against only the live collection passes the other two and fails it.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="ppc",
        title="PPC Manager",
        status=ACTIVE if existing_status != DRAFT else DRAFT,
        default_holder=holder if existing_status != DRAFT else None,
    )
    if existing_status == RETIRED:
        await _retire(collections, "ppc")
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _create_role(collections, slug="ppc", title="Pay Per Click Manager")

    # SPECIFIED: a fault naming that slug.
    assert "ppc" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)
    assert len([r for r in collections.roles.rows if _slug(r) == "ppc"]) == 1


async def test_a_deactivated_member_cannot_be_added_as_a_holder() -> None:
    """Scenario: A deactivated member cannot be added as a holder.

    WHEN a deactivated member is added as a holder of a role
    THEN the write is rejected with a fault naming that member, and
    nothing is persisted.

    Asserted on both routes into holding: adding a holder to an existing
    role, and naming the deactivated member as a new role's default in
    the create write. A rule enforced on one route only would leave the
    other as a way in.
    """
    collections = await _membership()
    departed = _id_of(collections.members, FOURTH_IDENTITY)
    await deactivate_member(
        members=collections.members, principal=PRINCIPAL, member_id=departed
    )
    assert _is_member_active(collections.members, FOURTH_IDENTITY) is False
    await _create_role(collections, slug="brand", title="Brand Manager")
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _add_holder(collections, "brand", departed)

    # SPECIFIED: a fault naming that member.
    assert str(departed) in str(excinfo.value) or FOURTH_NAME in str(excinfo.value)
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)
    assert _holders(_role(collections.roles, "brand")) == set()

    # SPECIFIED (the same rule, the other route in): a create naming the
    # deactivated member as its default holder is refused too.
    before = _snapshot(collections)
    with pytest.raises(REFUSED):
        await _create_role(
            collections,
            slug="catalog",
            title="Catalog Manager",
            status=ACTIVE,
            default_holder=departed,
        )
    _assert_unchanged(collections, before)


async def test_multiple_faults_are_reported_together() -> None:
    """Scenario: Multiple faults are reported together.

    WHEN a role is created with an empty title and a malformed slug
    THEN the write is rejected reporting both faults at once, and
    nothing is persisted.

    "Both at once" is asserted structurally — the rejection carries two
    or more faults, and one of them mentions the malformed slug — so an
    implementation that stopped at the first fault fails. DERIVED: which
    words a fault uses; the delta fixes that each fault names the
    offending role, not its wording.
    """
    collections = await _membership()
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _create_role(collections, slug="Bad Slug", title="")

    faults = _faults(excinfo.value)
    # SPECIFIED: every fault at once, not the first one only.
    assert len(faults) >= 2, (
        f"the rejection reported one fault where the role carries two: {faults!r}"
    )
    # SPECIFIED: the faults name the offending role.
    assert any("bad slug" in fault.lower() for fault in faults), (
        f"no fault names the malformed slug: {faults!r}"
    )
    assert any("title" in fault.lower() for fault in faults), (
        f"no fault names the empty title: {faults!r}"
    )
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)


# ===========================================================================
# Requirement: Every role write is validated whole and attributed
# ===========================================================================


async def test_a_landed_write_is_attributed() -> None:
    """Scenario: A landed write is attributed.

    WHEN a role is created by an authenticated admin principal
    THEN the stored role records that principal as its creator with the
    time of creation.

    The creating principal differs from the one every other write in the
    file uses, so "records that principal" is a per-write decision rather
    than a store-wide constant.
    """
    collections = await _membership()

    await _create_role(
        collections,
        slug="controller",
        title="Financial Controller",
        principal=ANOTHER_PRINCIPAL,
    )
    role = _role(collections.roles, "controller")

    # SPECIFIED: which principal made the write.
    assert _field(role, _CREATED_BY, "creator attribution") == ANOTHER_PRINCIPAL
    # SPECIFIED: and when. DERIVED: that "when" is a datetime.
    assert isinstance(_field(role, _CREATED_ON, "creation time"), datetime)
    # SPECIFIED: through the validated write path — a real persisted write.
    assert collections.roles.saves, "the create persisted nothing"


async def test_a_rejected_write_leaves_the_collection_unchanged() -> None:
    """Scenario: A rejected write leaves the collection unchanged.

    WHEN a write would produce an incoherent collection
    THEN the write is rejected with its faults and a subsequent read
    observes the collection exactly as it was.

    The incoherent write chosen is the one the delta's own prose calls
    out — removing an active role's default holder — and the read
    afterwards goes back through the store's `load`, not through a
    remembered object, so an implementation that mutated its in-memory
    role and merely declined to persist it fails here.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="creative",
        title="Creative Manager",
        status=ACTIVE,
        default_holder=holder,
    )
    before_rows, before_version = await collections.roles.load()
    before_saves = len(collections.roles.saves)

    with pytest.raises(REFUSED) as excinfo:
        await _remove_holder(collections, "creative", holder)

    # SPECIFIED: rejected with its faults.
    assert _faults(excinfo.value), "the rejection carried no fault at all"
    # SPECIFIED: a subsequent read observes the collection exactly as it was.
    after_rows, after_version = await collections.roles.load()
    assert (after_rows, after_version) == (before_rows, before_version)
    assert len(collections.roles.saves) == before_saves
    assert _holders(_role(collections.roles, "creative")) == {str(holder)}
    assert _default_holder(_role(collections.roles, "creative")) == str(holder)


async def test_a_slug_cannot_be_updated() -> None:
    """Scenario: A slug cannot be updated.

    WHEN an update names a role's slug as a field to change
    THEN the update is refused, explaining that the slug is not
    updatable.

    Two spellings of "names the slug as a field to change" are attempted
    — a `new_slug` and a second `slug` value — because an implementation
    whose signature simply has no slug parameter refuses one shape by
    `TypeError` while silently accepting the other as the addressing
    argument. Either a refusal or an argument-shape rejection satisfies
    the requirement; what fails is the slug actually changing.
    """
    collections = await _membership()
    await _create_role(collections, slug="marketing", title="Marketing Manager")
    before = _snapshot(collections)

    step = _use_case(_UPDATE_NAMES, "update-a-role")
    refused = False
    for shape in (
        {"slug": "marketing", "new_slug": "growth"},
        {"slug": "marketing", "title": "Marketing Manager", "new_slug": "growth"},
    ):
        try:
            await step(
                roles=collections.roles,
                members=collections.members,
                principal=PRINCIPAL,
                **shape,
            )
        except REFUSED_OR_UNEXPRESSIBLE as error:
            refused = True
            if not isinstance(error, TypeError):
                # SPECIFIED: explaining that the slug is not updatable.
                assert "slug" in str(error).lower(), (
                    f"the refusal does not explain that the slug is not "
                    f"updatable: {error}"
                )

    # SPECIFIED: the update is refused.
    assert refused, (
        "an update naming the slug as a field to change was accepted; the "
        "slug is chosen once and never changes"
    )
    # SPECIFIED: and nothing changed.
    _assert_unchanged(collections, before)
    assert _slugs(collections.roles) == {"marketing"}


async def test_a_title_is_corrected_freely() -> None:
    """Scenario: A title is corrected freely.

    WHEN an update changes a role's title
    THEN the update lands, is attributed, the role is still retrievable
    by the same slug, and nothing else is rewritten.

    "Nothing else is rewritten" is asserted over the role's own holders,
    status and creation attribution *and* over a second role, so a
    rename that rewrote the collection rather than one entry is caught.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="customer-service",
        title="Customer Service Manager",
        status=ACTIVE,
        default_holder=holder,
        principal=ANOTHER_PRINCIPAL,
    )
    await _create_role(collections, slug="it", title="IT Manager")
    untouched = _role(collections.roles, "it")

    await _update_role(
        collections, "customer-service", title="Head of Customer Service"
    )
    role = _role(collections.roles, "customer-service")

    # SPECIFIED: the update lands, under the same slug.
    assert _title(role) == "Head of Customer Service"
    assert _slug(role) == "customer-service"
    # SPECIFIED: and is attributed.
    assert _field(role, _UPDATED_BY, "updater attribution") == PRINCIPAL
    assert isinstance(_field(role, _UPDATED_ON, "update time"), datetime)
    # SPECIFIED: nothing else is rewritten — not this role's other data …
    assert _status_of(role) == ACTIVE
    assert _holders(role) == {str(holder)}
    assert _default_holder(role) == str(holder)
    assert _field(role, _CREATED_BY, "creator attribution") == ANOTHER_PRINCIPAL
    # … nor any other role.
    assert _title(_role(collections.roles, "it")) == _title(untouched)
    assert _status_of(_role(collections.roles, "it")) == _status_of(untouched)


# ===========================================================================
# Requirement: An active role always has a default holder
# ===========================================================================


async def test_an_active_role_cannot_be_left_without_a_default_holder() -> None:
    """Scenario: An active role cannot be left without a default holder.

    WHEN a write would remove the default holder of an active role
    THEN the write is rejected explaining that an active role must have
    a default holder, and nothing is persisted.

    The role holds nobody else, so this is the active-role obligation
    itself rather than the "move the default first" refusal — which the
    holder requirement's own scenario covers separately with three
    holders.

    The other route to the same outcome is asserted alongside: creating
    a role `active` with no default holder at all.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="supply-chain",
        title="Supply Chain Manager",
        status=ACTIVE,
        default_holder=holder,
    )
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _remove_holder(collections, "supply-chain", holder)

    # SPECIFIED: explaining that an active role must have a default holder.
    assert "default" in str(excinfo.value).lower(), (
        f"the refusal does not explain the obligation it failed: {excinfo.value}"
    )
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)

    # SPECIFIED (same obligation, at creation): an `active` role created
    # with no default holder is refused.
    before = _snapshot(collections)
    with pytest.raises(REFUSED) as second:
        await _create_role(collections, slug="ppc", title="PPC Manager", status=ACTIVE)
    assert (
        "default" in str(second.value).lower() or "holder" in str(second.value).lower()
    )
    _assert_unchanged(collections, before)


async def test_a_draft_role_may_hold_nobody() -> None:
    """Scenario: A draft role may hold nobody.

    WHEN a role is created with status `draft` and no holders
    THEN the write lands, and the role is readable with no holders and
    no default.

    This is the whole of the difference between `draft` and `retired`,
    and it is what lets the collection record a position the company
    intends to staff but has not.
    """
    collections = await _membership()

    await _create_role(
        collections, slug="managing-director", title="Managing Director", status=DRAFT
    )

    role = _role(collections.roles, "managing-director")
    # SPECIFIED: the write lands …
    assert _status_of(role) == DRAFT
    assert collections.roles.saves, "the create persisted nothing"
    # SPECIFIED: … with no holders and no default.
    assert _holders(role) == set()
    assert _default_holder(role) is None


async def test_a_retired_role_keeps_its_holders() -> None:
    """Scenario: A retired role keeps its holders.

    WHEN an active role holding several members is retired
    THEN the role retains those holders and its default marking, and the
    active-role obligation is no longer enforced against it.

    The last clause is what makes this more than a data-retention
    assertion: after retirement the default holder is removed, which the
    active-role obligation would have refused — so the obligation really
    stopped applying rather than merely not being met.
    """
    collections = await _membership()
    first = _id_of(collections.members, MEMBER_IDENTITY)
    second = _id_of(collections.members, THIRD_IDENTITY)
    await _create_role(
        collections,
        slug="operations",
        title="Operations Manager",
        status=ACTIVE,
        default_holder=first,
    )
    await _add_holder(collections, "operations", second)

    await _retire(collections, "operations")

    role = _role(collections.roles, "operations")
    # SPECIFIED: the role retains those holders and its default marking.
    assert _status_of(role) == RETIRED
    assert _holders(role) == {str(first), str(second)}
    assert _default_holder(role) == str(first)
    # SPECIFIED: and the obligation is no longer enforced against it.
    await _remove_holder(collections, "operations", first)
    retired = _role(collections.roles, "operations")
    assert _holders(retired) == {str(second)}
    assert _default_holder(retired) is None


# ===========================================================================
# Requirement: Holders are managed as a set and the default is moved
# deliberately
# ===========================================================================


async def test_a_member_holds_several_roles() -> None:
    """Scenario: A member holds several roles.

    WHEN one member is added as a holder of two different roles and is
    the default of both
    THEN both writes land, and each role resolves its default to that
    member.

    The requirement's own sentence — that holding a role confers no
    authority, permission remaining the member's admin flag — is
    asserted alongside, since a member who became an admin by holding a
    role would satisfy this scenario while breaking that sentence.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    assert _is_member_admin(collections.members, MEMBER_IDENTITY) is False
    # The baseline is the setup's own writes, not zero: `_membership()`
    # creates five members through `create_member`, each of which saves. What
    # this scenario guards is that the *role* writes below add none.
    membership_writes = len(collections.members.saves)

    await _create_role(
        collections,
        slug="brand",
        title="Brand Manager",
        status=ACTIVE,
        default_holder=member,
    )
    await _create_role(
        collections,
        slug="catalog",
        title="Catalog Manager",
        status=ACTIVE,
        default_holder=member,
    )

    # SPECIFIED: both writes land, each resolving its default to that member.
    for slug in ("brand", "catalog"):
        role = _role(collections.roles, slug)
        assert _default_holder(role) == str(member)
        assert str(member) in _holders(role)
    # SPECIFIED (requirement prose): holding a role confers no authority.
    assert _is_member_admin(collections.members, MEMBER_IDENTITY) is False
    assert len(collections.members.saves) == membership_writes, (
        "a role write altered the membership; holding a role confers nothing "
        "and this collection does not touch the admin flag"
    )


async def test_removing_the_default_of_an_active_role_is_refused() -> None:
    """Scenario: Removing the default of an active role is refused.

    WHEN the default holder of an active role holding three members is
    removed
    THEN the write is rejected explaining that the default must be moved
    to another holder first, and no holder is promoted in their place.

    "No holder is promoted in their place" is the assertion that
    distinguishes this from a rule that merely refuses: after the
    refusal the *same* member is still the default, so nothing was
    silently re-pointed at somebody nobody chose.
    """
    collections = await _membership()
    first = _id_of(collections.members, MEMBER_IDENTITY)
    second = _id_of(collections.members, THIRD_IDENTITY)
    third = _id_of(collections.members, FOURTH_IDENTITY)
    await _create_role(
        collections,
        slug="creative",
        title="Creative Manager",
        status=ACTIVE,
        default_holder=first,
    )
    await _add_holder(collections, "creative", second)
    await _add_holder(collections, "creative", third)
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _remove_holder(collections, "creative", first)

    # SPECIFIED: explaining that the default must be moved first.
    assert "default" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted …
    _assert_unchanged(collections, before)
    # SPECIFIED: … and no holder is promoted in their place.
    role = _role(collections.roles, "creative")
    assert _default_holder(role) == str(first)
    assert _holders(role) == {str(first), str(second), str(third)}


async def test_a_non_default_holder_leaves_freely() -> None:
    """Scenario: A non-default holder leaves freely.

    WHEN a holder who is not the default is removed from an active role
    THEN the write lands, is attributed, and the role's default is
    unchanged.

    This is what stops the refusal above from being implemented as
    "holders of an active role cannot be removed".
    """
    collections = await _membership()
    default = _id_of(collections.members, MEMBER_IDENTITY)
    other = _id_of(collections.members, THIRD_IDENTITY)
    await _create_role(
        collections,
        slug="marketing",
        title="Marketing Manager",
        status=ACTIVE,
        default_holder=default,
    )
    await _add_holder(collections, "marketing", other)

    await _remove_holder(collections, "marketing", other, principal=ANOTHER_PRINCIPAL)

    role = _role(collections.roles, "marketing")
    # SPECIFIED: the write lands.
    assert _holders(role) == {str(default)}
    # SPECIFIED: the role's default is unchanged.
    assert _default_holder(role) == str(default)
    # SPECIFIED: and is attributed.
    assert _field(role, _UPDATED_BY, "updater attribution") == ANOTHER_PRINCIPAL
    assert isinstance(_field(role, _UPDATED_ON, "update time"), datetime)


async def test_the_default_moves_to_another_holder() -> None:
    """Scenario: The default moves to another holder.

    WHEN the default of an active role is moved to another active holder
    of that role
    THEN the write lands and that member is the role's default holder.

    The role is left with exactly one default afterwards — asserted
    through `_default_holder`, which fails where more than one holder
    carries the marking, so a move implemented as an addition is caught.
    """
    collections = await _membership()
    first = _id_of(collections.members, MEMBER_IDENTITY)
    second = _id_of(collections.members, THIRD_IDENTITY)
    await _create_role(
        collections,
        slug="controller",
        title="Financial Controller",
        status=ACTIVE,
        default_holder=first,
    )
    await _add_holder(collections, "controller", second)

    await _move_default(collections, "controller", second)

    role = _role(collections.roles, "controller")
    # SPECIFIED: that member is the role's default holder.
    assert _default_holder(role) == str(second)
    # SPECIFIED: the write lands — and the former default remains a holder,
    # since moving the default is not removing anybody.
    assert _holders(role) == {str(first), str(second)}


async def test_the_default_cannot_move_to_a_non_holder() -> None:
    """Scenario: The default cannot move to a non-holder.

    WHEN a move names a member who is not a holder of that role
    THEN the write is rejected explaining that the default must be one
    of the role's holders.

    The member named is an active member of the membership, so what is
    refused is non-holding rather than non-existence or inactivity.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    stranger = _id_of(collections.members, THIRD_IDENTITY)
    await _create_role(
        collections,
        slug="customer-service",
        title="Customer Service Manager",
        status=ACTIVE,
        default_holder=holder,
    )
    assert _is_member_active(collections.members, THIRD_IDENTITY) is True
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _move_default(collections, "customer-service", stranger)

    # SPECIFIED: explaining that the default must be one of the holders.
    assert "holder" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)
    assert _default_holder(_role(collections.roles, "customer-service")) == str(holder)


async def test_a_draft_roles_default_may_be_removed() -> None:
    """Scenario: A draft role's default may be removed.

    WHEN the default holder of a draft role is removed
    THEN the write lands and the role is left with no default.

    A draft role is not bound by the active-role obligation, so the
    refusal that governs an active role's default does not reach here —
    and the delta is explicit that no holder is promoted in their place
    on any status, which is asserted as the role being left with *no*
    default rather than a different one.
    """
    collections = await _membership()
    first = _id_of(collections.members, MEMBER_IDENTITY)
    second = _id_of(collections.members, THIRD_IDENTITY)
    await _create_role(collections, slug="it", title="IT Manager", status=DRAFT)
    await _add_holder(collections, "it", first)
    await _add_holder(collections, "it", second)
    await _move_default(collections, "it", first)
    assert _default_holder(_role(collections.roles, "it")) == str(first)

    await _remove_holder(collections, "it", first)

    role = _role(collections.roles, "it")
    # SPECIFIED: the write lands …
    assert _holders(role) == {str(second)}
    # SPECIFIED: … and the role is left with no default.
    assert _default_holder(role) is None


# ===========================================================================
# Requirement: A role is retired, never deleted
# ===========================================================================


async def test_activating_a_draft_role_requires_a_default_holder() -> None:
    """Scenario: Activating a draft role requires a default holder.

    WHEN a draft role holding nobody is activated
    THEN the write is rejected explaining that an active role must have
    a default holder, and the role remains `draft`.
    """
    collections = await _membership()
    await _create_role(
        collections, slug="operations", title="Operations Manager", status=DRAFT
    )
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _activate(collections, "operations")

    # SPECIFIED: explaining that an active role must have a default holder.
    assert "default" in str(excinfo.value).lower()
    # SPECIFIED: nothing is persisted, and the role remains draft.
    _assert_unchanged(collections, before)
    assert _status_of(_role(collections.roles, "operations")) == DRAFT


async def test_a_draft_role_with_a_default_holder_activates() -> None:
    """Scenario: A draft role with a default holder activates.

    WHEN a draft role whose default holder is an active member is
    activated
    THEN the write lands, is attributed, and the role is `active`.

    This is what stops the refusal above from being implemented as
    "draft roles do not activate".
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections, slug="operations", title="Operations Manager", status=DRAFT
    )
    await _add_holder(collections, "operations", holder)
    await _move_default(collections, "operations", holder)

    await _activate(collections, "operations", principal=ANOTHER_PRINCIPAL)

    role = _role(collections.roles, "operations")
    # SPECIFIED: the role is active.
    assert _status_of(role) == ACTIVE
    assert _default_holder(role) == str(holder)
    # SPECIFIED: and the write is attributed — the transition carries its
    # own attribution, per the requirement's own sentence.
    attribution = [
        str(_field(role, names, what))
        for names, what in ((_UPDATED_BY, "updater"), (_CREATED_BY, "creator"))
        if _has(role, names)
    ]
    assert ANOTHER_PRINCIPAL in attribution, (
        "the activation records no principal of its own; the transition "
        f"carries its own attribution (read: {attribution!r})"
    )


async def test_an_abandoned_draft_is_retired() -> None:
    """Scenario: An abandoned draft is retired.

    WHEN a draft role is retired
    THEN the write lands and the role is `retired`, retaining its slug,
    title and any holders.

    `draft -> retired` is permitted deliberately: the collection offers
    no deletion, so without it a position sketched and then abandoned
    would sit in the draft group forever.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections, slug="managing-director", title="Managing Director", status=DRAFT
    )
    await _add_holder(collections, "managing-director", holder)

    await _retire(collections, "managing-director")

    role = _role(collections.roles, "managing-director")
    # SPECIFIED: the role is retired, retaining slug, title and holders.
    assert _status_of(role) == RETIRED
    assert _slug(role) == "managing-director"
    assert _title(role) == "Managing Director"
    assert _holders(role) == {str(holder)}


async def test_un_retiring_a_role_whose_default_is_deactivated_is_refused() -> None:
    """Scenario: Un-retiring a role whose default is deactivated is
    refused.

    WHEN a retired role whose default holder has since been deactivated
    is un-retired
    THEN the write is rejected explaining that an active role's default
    holder must be an active member, and the role remains `retired`.

    This is the retired-side half of the entry check, and it is not
    redundant with the draft-side one: a retired role keeps its holders
    unenforced, so its default may have been deactivated in the meantime
    — which is exactly the state built here.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="brand",
        title="Brand Manager",
        status=ACTIVE,
        default_holder=holder,
    )
    await _retire(collections, "brand")
    await deactivate_member(
        members=collections.members, principal=PRINCIPAL, member_id=holder
    )
    assert _is_member_active(collections.members, MEMBER_IDENTITY) is False
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _unretire(collections, "brand")

    # SPECIFIED: explaining that the default holder must be an active member.
    text = str(excinfo.value).lower()
    assert "active" in text and ("holder" in text or "default" in text), (
        f"the refusal does not explain the obligation it failed: {excinfo.value}"
    )
    # SPECIFIED: nothing is persisted, and the role remains retired.
    _assert_unchanged(collections, before)
    assert _status_of(_role(collections.roles, "brand")) == RETIRED


async def test_a_retired_role_cannot_return_to_draft() -> None:
    """Scenario: A retired role cannot return to draft.

    WHEN a write names `draft` as the status a retired role should take
    THEN the write is refused, explaining that no role returns to
    `draft`.

    Every route by which a status could be named is attempted — the
    update use case and each transition use case, given `draft` — and a
    signature that has no such parameter counts as a refusal, since a
    transition that cannot be expressed cannot be taken. What fails is
    the role's status actually becoming `draft`.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="ppc",
        title="PPC Manager",
        status=ACTIVE,
        default_holder=holder,
    )
    await _retire(collections, "ppc")
    before = _snapshot(collections)

    attempted = 0
    for names, what in (
        (_UPDATE_NAMES, "update"),
        (_ACTIVATE_NAMES, "activate"),
        (_RETIRE_NAMES, "retire"),
    ):
        step = getattr(access_application, names[0], None)
        if step is None:
            continue
        attempted += 1
        try:
            await step(
                roles=collections.roles,
                members=collections.members,
                principal=PRINCIPAL,
                slug="ppc",
                status=_status(DRAFT),
            )
        except REFUSED_OR_UNEXPRESSIBLE:
            continue
        # A landed write is only a failure if it actually reached `draft`.
        assert _status_of(_role(collections.roles, "ppc")) != DRAFT, (
            f"the {what} use case returned a retired role to `draft`; once a "
            "role has been in play, `retired` is what records that it no "
            "longer is"
        )
    assert attempted, (
        "no use case accepting a status was found to attempt the transition "
        "against — correct this file's candidate names"
    )

    # SPECIFIED: the role never becomes `draft`, and nothing is persisted
    # by a refused transition.
    assert _status_of(_role(collections.roles, "ppc")) == RETIRED
    _assert_unchanged(collections, before)


async def test_retirement_is_attributed_and_reversible() -> None:
    """Scenario: Retirement is attributed and reversible.

    WHEN an active role is retired and later un-retired
    THEN the same slug resolves throughout, and the role records who
    retired it and when, and who un-retired it and when.

    The two writes use different principals, so "who retired it" and
    "who un-retired it" are separate readings rather than one value read
    twice.
    """
    collections = await _membership()
    holder = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="catalog",
        title="Catalog Manager",
        status=ACTIVE,
        default_holder=holder,
    )

    await _retire(collections, "catalog", principal=PRINCIPAL)
    # SPECIFIED: the same slug resolves throughout.
    retired = _role(collections.roles, "catalog")
    assert _status_of(retired) == RETIRED
    # SPECIFIED: records who retired it and when.
    assert _field(retired, _RETIRED_BY, "retirer attribution") == PRINCIPAL
    assert isinstance(_field(retired, _RETIRED_ON, "retirement time"), datetime)

    await _unretire(collections, "catalog", principal=ANOTHER_PRINCIPAL)
    restored = _role(collections.roles, "catalog")
    # SPECIFIED: un-retiring restores the same role under the same slug.
    assert _status_of(restored) == ACTIVE
    assert _title(restored) == "Catalog Manager"
    assert _default_holder(restored) == str(holder)
    assert len([r for r in collections.roles.rows if _slug(r) == "catalog"]) == 1
    # SPECIFIED: records who un-retired it and when.
    assert _field(restored, _UNRETIRED_BY, "un-retirer attribution") == (
        ANOTHER_PRINCIPAL
    )
    assert isinstance(_field(restored, _UNRETIRED_ON, "un-retirement time"), datetime)
    # SPECIFIED: the retirement attribution is retained, not overwritten —
    # the trail is intact.
    assert _field(restored, _RETIRED_BY, "retirer attribution") == PRINCIPAL


def test_the_collection_offers_no_deletion() -> None:
    """Requirement text: "The collection SHALL offer no deletion." — no
    scenario states it, so this is the requirement's own sentence
    asserted structurally.

    DERIVED mechanism: the public application surface exports no
    delete/purge verb for a role, and no `remove_role` that is not a
    holder operation. Removing a *holder* is a stated use case and is
    deliberately not caught here. A deletion reachable only through the
    store adapter would not be caught either; that bound is recorded in
    the manifest.
    """
    exported = tuple(getattr(access_application, "__all__", ()))
    assert exported, "the access application surface declares no __all__"

    offending = [
        name
        for name in exported
        if ("delete" in name.lower() or "purge" in name.lower())
        or (name.lower().startswith("remove_role") and "holder" not in name.lower())
    ]
    # SPECIFIED: no deletion is offered.
    assert offending == [], (
        f"the role collection's public surface offers deletion verbs "
        f"{offending!r}; a role is retired, never deleted"
    )
