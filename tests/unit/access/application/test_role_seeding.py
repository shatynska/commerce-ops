"""Seeding the eleven roles before the application serves (`roles`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/roles/spec.md`, the
ADDED requirement *The roles are seeded before the application serves* —
all seven of its scenarios, plus the four sentences of its prose that
carry no scenario of their own:

- the eleven slugs, titles and seeded statuses (asserted as an explicit
  expected set, never as a count — `tasks.md` 10.9);
- seeded roles attributed to the same reserved system principal the
  admin seeding uses;
- that naming the seeding administrator confers no authority and alters
  no membership entry;
- that the roles are seeded by the step that seeds the first admin,
  before the HTTP server begins serving.

## Why this level

Every scenario is stated about what the collection holds after the step
runs and whether the step continued — both decided by the step itself,
over store doubles. That is the level
`tests/unit/access/application/test_members_bootstrap.py` established for
the admin seeding this one extends, and this file is shaped after it.

DELIBERATELY UNTESTED here: that the container's start chain actually
runs the step, which is a Dockerfile `CMD` observable only by running the
image. Its *ordering* is asserted against the `CMD` line, the way
`tests/unit/test_seed_playbook.py` does.

## The two branches, and why both are here

`design.md` Decision 7 and the requirement's own prose resolve a
**seeding administrator** in two branches, and the second is the branch
every already-administered deployment takes — including the first
deployment of this change against the existing production database. A
test covering only a freshly seeded admin would leave the branch that
actually runs uncovered, which is where the plan review found the
original draft defective.

`test_the_choice_is_deterministic` and
`test_the_earliest_created_active_admin_is_chosen_not_the_first_row` are
what make the second branch's assertion discriminating rather than true
by construction: the correct answer is deliberately neither the first
stored row, nor the last created, nor the alphabetically first identity.

## What is fixed, and what is INVENTED

Fixed by the delta: the eleven slugs, titles and statuses; add-only
seeding; the resolution order for the seeding administrator; that the
step fails on an unusable store; that seeded roles carry the reserved
system principal.

INVENTED, each recorded in the manifest with its correction point:

- The seed's exported name, resolved over candidates by
  `_role_seed`, which fails loudly naming them. Correction point:
  `_SEED_NAMES`.
- Its call shape, including how the member the admin seeding established
  *on this run* reaches it. Correction point: `_seed_roles`.
- The store doubles and role accessors, as `test_role_writes.py` records;
  the two files correct together. They are repeated rather than shared
  because this pass may write only files matching `tests/**/test_*.py`.

## Expected first-run state

No role seed is exported, so every test here is expected to fail on an
absent target — the resolver fails naming its candidates before any
assertion runs, which establishes only absence.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import importlib
import re
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import pytest

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member
from tests.support.fixtures import PRINCIPAL

pytestmark = pytest.mark.anyio

_ROOT: Final = Path(__file__).resolve().parents[4]

BOOTSTRAP_VARIABLE: Final = "BOOTSTRAP_ADMIN_IDENTITY"

# DERIVED sample values; no artifact fixes example identities.
SEEDED_IDENTITY: Final = "U01ALICE"
CORRECTED_IDENTITY: Final = "U02BOB"
EARLIEST_ADMIN_IDENTITY: Final = "U03BEATRICE"
LATER_ADMIN_IDENTITY: Final = "U04ANNA"
LATEST_ADMIN_IDENTITY: Final = "U05CLARA"
ORDINARY_IDENTITY: Final = "U06DEREK"

DRAFT: Final = "draft"
ACTIVE: Final = "active"

#: SPECIFIED: the eight roles seeded `active`, holding the seeding
#: administrator as their sole holder and default.
SEEDED_ACTIVE: Final[tuple[tuple[str, str], ...]] = (
    ("supply-chain", "Supply Chain Manager"),
    ("ppc", "PPC Manager"),
    ("brand", "Brand Manager"),
    ("catalog", "Catalog Manager"),
    ("controller", "Financial Controller"),
    ("creative", "Creative Manager"),
    ("customer-service", "Customer Service Manager"),
    ("marketing", "Marketing Manager"),
)

#: SPECIFIED: the three roles seeded `draft`, holding nobody.
SEEDED_DRAFT: Final[tuple[tuple[str, str], ...]] = (
    ("operations", "Operations Manager"),
    ("managing-director", "Managing Director"),
    ("it", "IT Manager"),
)

#: The whole seeded set as an explicit expectation. `tasks.md` 10.9: a
#: gate asserting a count would pass on eleven wrong roles, and a prior
#: change in this repository shipped exactly that defect.
SEEDED_SET: Final[frozenset[tuple[str, str, str]]] = frozenset(
    [(slug, title, ACTIVE) for slug, title in SEEDED_ACTIVE]
    + [(slug, title, DRAFT) for slug, title in SEEDED_DRAFT]
)


def _refused_types() -> tuple[type[BaseException], ...]:
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


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Store doubles (see test_role_writes.py)
# ---------------------------------------------------------------------------


class _Version:
    def __init__(self, value: int = 7) -> None:
        self.value = value


class _FakeMembersStore:
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
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1


class _FakeRolesStore:
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
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self._version.value += 1

    async def load_roles(self) -> tuple[tuple[Any, ...], int]:
        return await self.load()

    async def save_roles(self, rows: Any, *, expected_version: int) -> None:
        await self.save(rows, expected_version=expected_version)


class _UnusableRolesStore:
    """A role store that cannot be read or written."""

    def __init__(self, failure: BaseException) -> None:
        self._failure = failure
        self.rows: tuple[Any, ...] = ()
        self.saves: list[Any] = []

    @property
    def version(self) -> int:
        return 0

    async def load(self) -> tuple[tuple[Any, ...], int]:
        raise self._failure

    async def save(self, rows: Any, *, expected_version: int) -> None:
        raise self._failure

    async def load_roles(self) -> tuple[tuple[Any, ...], int]:
        raise self._failure

    async def save_roles(self, rows: Any, *, expected_version: int) -> None:
        raise self._failure


class _Collections:
    def __init__(self) -> None:
        version = _Version()
        self.members = _FakeMembersStore(version)
        self.roles = _FakeRolesStore(version)


# ---------------------------------------------------------------------------
# Accessors (see test_role_writes.py)
# ---------------------------------------------------------------------------

_MEMBER_ID_NAMES: Final = ("id", "member_id", "identifier")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_MEMBER_ACTIVE_NAMES: Final = ("active", "is_active")
_MEMBER_ADMIN_NAMES: Final = ("admin", "is_admin")
_MEMBER_CREATED_ON: Final = ("created_on", "created_at")

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


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("role", "member", "entry", "definition", "record"):
        nested = getattr(row, attribute, None)
        if nested is not None and not isinstance(nested, (str, bytes)):
            found.append(nested)
    return tuple(found)


def _has(row: Any, names: tuple[str, ...]) -> bool:
    return any(hasattr(target, name) for target in _targets(row) for name in names)


def _field(row: Any, names: tuple[str, ...], what: str) -> Any:
    for target in _targets(row):
        for name in names:
            if hasattr(target, name):
                return getattr(target, name)
    pytest.fail(
        f"a stored row exposes no {what} under any of {names} — correct this "
        "file's accessor names to the implemented row"
    )


def _scalar(value: Any) -> str:
    return str(getattr(value, "value", value))


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


def _slug(row: Any) -> str:
    return str(_field(row, _SLUG_NAMES, "slug"))


def _title(row: Any) -> str:
    return str(_field(row, _TITLE_NAMES, "title"))


def _status_of(row: Any) -> str:
    return _scalar(_field(row, _STATUS_NAMES, "lifecycle status")).lower()


def _holder_identifier(holder: Any) -> str:
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
    return {
        _holder_identifier(holder) for holder in _field(row, _HOLDERS_NAMES, "holders")
    }


def _default_holder(row: Any) -> str | None:
    if _has(row, _DEFAULT_NAMES):
        value = _field(row, _DEFAULT_NAMES, "default holder")
        return None if value is None else _holder_identifier(value)
    marked = [
        holder
        for holder in _field(row, _HOLDERS_NAMES, "holders")
        if any(
            bool(getattr(holder, name, False))
            for name in ("is_default", "default", "is_the_default")
        )
    ]
    if len(marked) > 1:
        pytest.fail(f"{len(marked)} holders of {_slug(row)!r} are marked default")
    return _holder_identifier(marked[0]) if marked else None


def _role(store: _FakeRolesStore, slug: str) -> Any:
    for row in store.rows:
        if _slug(row) == slug:
            return row
    pytest.fail(
        f"no stored role carries the slug {slug!r} (stored: "
        f"{sorted(_slug(row) for row in store.rows)})"
    )


def _seeded_triples(store: _FakeRolesStore) -> frozenset[tuple[str, str, str]]:
    return frozenset((_slug(row), _title(row), _status_of(row)) for row in store.rows)


# ---------------------------------------------------------------------------
# Call shapes: the single correction points
# ---------------------------------------------------------------------------

_SEED_NAMES: Final = (
    "seed_roles",
    "seed_role_collection",
    "ensure_seeded_roles",
    "seed_the_roles",
    "bootstrap_roles",
)

_BOOTSTRAP_NAMES: Final = (
    "seed_bootstrap_admin",
    "bootstrap_admin",
    "ensure_bootstrap_admin",
    "seed_first_admin",
    "bootstrap_first_admin",
    "run_admin_bootstrap",
)


def _resolve(names: tuple[str, ...], what: str) -> Any:
    for name in names:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        f"the access application surface exports no {what} under any of "
        f"{names} — correct this file's candidate names to the implemented one"
    )


def _is_argument_shape_error(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _first_matching(
    attempts: tuple[tuple[str, Callable[[], Any]], ...], what: str
) -> tuple[str, Any]:
    last: TypeError | None = None
    for label, attempt in attempts:
        try:
            return label, await attempt()
        except TypeError as error:
            if not _is_argument_shape_error(error):
                raise
            last = error
    pytest.fail(
        f"no attempted call shape matched the {what}'s signature; last "
        f"argument error: {last}"
    )


async def _seed_admin(
    monkeypatch: pytest.MonkeyPatch, collections: _Collections, identity: str | None
) -> Any:
    """Runs the existing admin seeding step once — the step this change
    extends, and the step whose outcome the role seed depends on."""
    step = _resolve(_BOOTSTRAP_NAMES, "admin bootstrap step")
    if identity is None:
        monkeypatch.delenv(BOOTSTRAP_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(BOOTSTRAP_VARIABLE, identity)
    _, result = await _first_matching(
        (
            ("kw", lambda: step(members=collections.members, identity=identity)),
            ("kw-no-identity", lambda: step(members=collections.members)),
            ("pos", lambda: step(collections.members, identity=identity)),
            ("pos-only", lambda: step(collections.members)),
        ),
        "admin bootstrap step",
    )
    return result


async def _seed_roles(
    collections: _Collections,
    *,
    established: Any = None,
    roles: Any | None = None,
    require_established: bool = False,
) -> Any:
    """Runs the role seed once.

    `established` is the member the admin seeding created or promoted on
    *this run*, which the requirement makes the first branch of the
    seeding-administrator resolution. Where the implemented signature
    takes no such argument the shape without it is used — except where
    `require_established` says the test under way is specifically about
    that branch, in which case a signature that cannot express it is
    itself the failure.
    """
    step = _resolve(_SEED_NAMES, "role seeding step")
    store = collections.roles if roles is None else roles
    carrying: tuple[tuple[str, Callable[[], Any]], ...] = (
        (
            "seeding_administrator",
            lambda: step(
                roles=store,
                members=collections.members,
                seeding_administrator=established,
            ),
        ),
        (
            "seeded_admin",
            lambda: step(
                roles=store, members=collections.members, seeded_admin=established
            ),
        ),
        (
            "established_admin",
            lambda: step(
                roles=store,
                members=collections.members,
                established_admin=established,
            ),
        ),
        (
            "administrator",
            lambda: step(
                roles=store, members=collections.members, administrator=established
            ),
        ),
        (
            "admin",
            lambda: step(roles=store, members=collections.members, admin=established),
        ),
    )
    bare: tuple[tuple[str, Callable[[], Any]], ...] = (
        ("bare-kw", lambda: step(roles=store, members=collections.members)),
        ("bare-pos", lambda: step(store, collections.members)),
    )
    attempts = carrying + (() if require_established else bare)
    label, result = await _first_matching(attempts, "role seeding step")
    if require_established and label in ("bare-kw", "bare-pos"):  # pragma: no cover
        pytest.fail("the established-admin shape was expected to match")
    return result


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


def _reorder(store: _FakeMembersStore, order: tuple[str, ...]) -> None:
    """Rewrites the store's own row order — a store-state construction,
    not a membership write.

    It exists so that "the earliest-created active admin" cannot be
    satisfied by an implementation that simply takes the first stored
    row: after this, the correct answer sits in the middle.
    """
    by_identity = {_slack(row): row for row in store.rows}
    assert set(order) == set(by_identity), (
        f"reorder named {sorted(order)} against stored {sorted(by_identity)}"
    )
    store.rows = tuple(by_identity[identity] for identity in order)


async def _already_administered() -> _Collections:
    """A membership holding three active admins and one ordinary member,
    where the earliest-created active admin is deliberately neither the
    first stored row, nor the last created, nor the alphabetically first
    identity.

    Creation order: the ordinary member, then Beatrice, Anna, Clara.
    Row order afterwards: Anna, Clara, the ordinary member, Beatrice.
    The earliest-created *active admin* is therefore Beatrice — the last
    stored row and the second-created entry.
    """
    collections = _Collections()
    await _create_member(
        collections.members,
        display_name="Derek Ordinary",
        slack_identity=ORDINARY_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Beatrice Admin",
        slack_identity=EARLIEST_ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Anna Admin",
        slack_identity=LATER_ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Clara Admin",
        slack_identity=LATEST_ADMIN_IDENTITY,
        admin=True,
    )
    # The first entry is demoted rather than created non-admin, so the
    # membership never passes through a state with no active admin.
    from commerce_ops.access.application import update_member

    await update_member(
        members=collections.members,
        principal=PRINCIPAL,
        member_id=_id_of(collections.members, ORDINARY_IDENTITY),
        admin=False,
    )
    _reorder(
        collections.members,
        (
            LATER_ADMIN_IDENTITY,
            LATEST_ADMIN_IDENTITY,
            ORDINARY_IDENTITY,
            EARLIEST_ADMIN_IDENTITY,
        ),
    )
    _assert_creation_times_are_distinct(collections.members)
    return collections


def _assert_creation_times_are_distinct(store: _FakeMembersStore) -> None:
    """Guards the discrimination below: where two entries share a
    creation time the delta's tie-break by identifier decides, and the
    expectation this file states would be arbitrary rather than wrong."""
    times = [_field(row, _MEMBER_CREATED_ON, "creation time") for row in store.rows]
    assert len(set(times)) == len(times), (
        "two membership entries share a creation time, so 'earliest-created' "
        f"is decided by the identifier tie-break rather than by time: {times}"
    )


def _admin_seed_principal(collections: _Collections, identity: str) -> str:
    return str(
        _field(
            _member_row(collections.members, identity),
            _CREATED_BY,
            "creator attribution",
        )
    )


# ===========================================================================
# Scenario: An empty collection is seeded with eleven roles
# ===========================================================================


async def test_an_empty_collection_is_seeded_with_eleven_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An empty collection is seeded with eleven roles.

    WHEN the step runs against a collection holding no roles
    THEN the collection afterward holds the eleven roles, the eight
    `active` with the seeding administrator as their sole holder and
    default, and the three `draft` holding nobody.

    Asserted against the explicit expected set of (slug, title, status),
    not against a count: a count passes on eleven wrong roles, and
    `tasks.md` 10.9 records a prior change in this repository shipping
    exactly that defect. The reserved-principal sentence of the
    requirement's prose is asserted here too, as equality with the
    principal the admin seeding wrote on the same run — "the same
    reserved system principal the admin seeding uses" read literally.
    """
    collections = _Collections()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    admin_id = _id_of(collections.members, SEEDED_IDENTITY)

    await _seed_roles(collections, established=established)

    # SPECIFIED: the eleven roles, by slug, title and seeded status.
    assert _seeded_triples(collections.roles) == SEEDED_SET

    # SPECIFIED: the eight active ones hold the seeding administrator as
    # their sole holder and default.
    for slug, _title_text in SEEDED_ACTIVE:
        role = _role(collections.roles, slug)
        assert _holders(role) == {str(admin_id)}, (
            f"{slug!r} does not hold the seeding administrator alone"
        )
        assert _default_holder(role) == str(admin_id)

    # SPECIFIED: the three draft ones hold nobody.
    for slug, _title_text in SEEDED_DRAFT:
        role = _role(collections.roles, slug)
        assert _holders(role) == set(), f"{slug!r} was seeded holding somebody"
        assert _default_holder(role) is None

    # SPECIFIED (requirement prose): seeded roles are attributed to the
    # same reserved system principal the admin seeding uses.
    reserved = _admin_seed_principal(collections, SEEDED_IDENTITY)
    assert reserved not in ("", PRINCIPAL, SEEDED_IDENTITY)
    for slug, _title_text in SEEDED_ACTIVE + SEEDED_DRAFT:
        role = _role(collections.roles, slug)
        assert str(_field(role, _CREATED_BY, "creator attribution")) == reserved, (
            f"{slug!r} is not attributed to the reserved system principal "
            f"{reserved!r} the admin seeding used"
        )
        assert isinstance(_field(role, _CREATED_ON, "creation time"), datetime)


# ===========================================================================
# Scenario: A seeded role that was edited is not reset
# ===========================================================================


async def _edit_a_seeded_role(
    collections: _Collections, someone_else: Any
) -> tuple[str, str, set[str]]:
    """Renames, re-holds and retires `ppc` through the write use cases,
    answering what the role then looks like.

    All three edits at once, because a seed that restored any one of them
    would discard an operator's work at the next deployment.
    """
    update = _resolve(("update_role", "rename_role"), "update-a-role")
    add = _resolve(("add_role_holder", "add_holder", "add_role_member"), "add-a-holder")
    move = _resolve(
        (
            "move_role_default",
            "move_default_holder",
            "move_default",
            "set_role_default",
            "set_default_holder",
        ),
        "move-the-default",
    )
    retire = _resolve(("retire_role",), "retire-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": PRINCIPAL,
    }
    await update(**common, slug="ppc", title="Paid Media Manager")
    await add(**common, slug="ppc", member_id=someone_else)
    await move(**common, slug="ppc", member_id=someone_else)
    await retire(**common, slug="ppc")
    role = _role(collections.roles, "ppc")
    return _title(role), _status_of(role), _holders(role)


async def test_a_seeded_role_that_was_edited_is_not_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A seeded role that was edited is not reset.

    WHEN the step runs against a collection in which a seeded slug has
    since been renamed, retired, or given different holders
    THEN that role is left exactly as it stands, and no second role with
    that slug is created.

    All three edits are applied to one role at once. The edits are made
    through the write use cases, so the state under test is one a real
    admin could have produced.
    """
    collections = _Collections()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    await _create_member(
        collections.members,
        display_name="Clara Admin",
        slack_identity=LATEST_ADMIN_IDENTITY,
        admin=True,
    )
    await _seed_roles(collections, established=established)
    someone_else = _id_of(collections.members, LATEST_ADMIN_IDENTITY)

    edited = await _edit_a_seeded_role(collections, someone_else)
    before = tuple(collections.roles.rows)

    await _seed_roles(collections, established=established)

    # SPECIFIED: no second role with that slug is created.
    assert len([r for r in collections.roles.rows if _slug(r) == "ppc"]) == 1
    # SPECIFIED: that role is left exactly as it stands.
    after = _role(collections.roles, "ppc")
    assert (_title(after), _status_of(after), _holders(after)) == edited, (
        "the seed reset a role an operator had edited"
    )
    # SPECIFIED: and nothing else moved either — the seed is add-only.
    assert collections.roles.rows == before
    # DERIVED guard: the edit really did take the role away from its
    # seeded shape, so the assertion above is not satisfied by a seed
    # that reset it.
    assert _seeded_triples(collections.roles) != SEEDED_SET


# ===========================================================================
# Scenario: Roles missing from an edited collection are added
# ===========================================================================


async def test_roles_missing_from_an_edited_collection_are_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Roles missing from an edited collection are added.

    WHEN the step runs against a collection holding some of the eleven
    slugs but not others
    THEN only the absent ones are added, and the present ones are
    untouched.

    The partial collection is built by seeding, then dropping four
    slugs from the store's own state — the way
    `test_members_bootstrap.py` reaches states ordinary writes cannot.
    The four dropped span both statuses, so a seed that added back only
    the active ones fails.
    """
    collections = _Collections()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    await _seed_roles(collections, established=established)

    dropped = ("ppc", "marketing", "operations", "it")
    kept = tuple(row for row in collections.roles.rows if _slug(row) not in dropped)
    collections.roles.rows = kept
    assert len(kept) == 7

    await _seed_roles(collections, established=established)

    # SPECIFIED: only the absent ones are added.
    assert _seeded_triples(collections.roles) == SEEDED_SET
    assert len(collections.roles.rows) == 11
    # SPECIFIED: the present ones are untouched — the same row objects,
    # not re-created equivalents.
    surviving = {_slug(row): row for row in collections.roles.rows}
    for row in kept:
        assert surviving[_slug(row)] is row, (
            f"{_slug(row)!r} was rewritten by a seed that should have left it "
            "exactly as it stands"
        )


# ===========================================================================
# Scenario: The newly seeded admin holds the eight active roles
# ===========================================================================


async def test_the_newly_seeded_admin_holds_the_eight_active_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The newly seeded admin holds the eight active roles.

    WHEN the step runs against an empty membership, the admin seeding
    having just created the first admin
    THEN each of the eight active roles resolves its default holder to
    that member.

    Against an empty membership both branches of the resolution coincide
    — the freshly created admin is also the earliest-created active
    admin — so this scenario alone cannot discriminate between them.
    `test_the_admin_established_on_this_run_wins` is what does.
    """
    collections = _Collections()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    admin_id = _id_of(collections.members, SEEDED_IDENTITY)
    assert len(collections.members.rows) == 1

    await _seed_roles(collections, established=established)

    # SPECIFIED: each of the eight resolves its default to that member.
    for slug, _title_text in SEEDED_ACTIVE:
        assert _default_holder(_role(collections.roles, slug)) == str(admin_id), (
            f"{slug!r} does not resolve its default holder to the admin the "
            "seeding just created"
        )


async def test_the_admin_established_on_this_run_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED from the requirement's prose, which carries no scenario
    of its own: the seeding administrator is "the member the admin
    seeding established on this run, where it created or promoted one;
    otherwise the earliest-created active admin".

    The two branches only differ where the admin seeding establishes a
    member who is *not* the earliest-created active admin — which
    `members` produces on exactly one path: the mis-seeded-first-admin
    correction, where the variable names a different identity and the
    newly named one becomes an active admin *alongside* the seed entry.

    Without this test the resolution could be implemented as
    "earliest-created active admin" alone and every stated scenario would
    still pass, because on an empty membership the two coincide.
    """
    collections = _Collections()
    await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    established = await _seed_admin(monkeypatch, collections, CORRECTED_IDENTITY)

    first = _id_of(collections.members, SEEDED_IDENTITY)
    corrected = _id_of(collections.members, CORRECTED_IDENTITY)
    assert first != corrected, (
        "the correction path did not produce a second admin, so this test has "
        "no distinction to make"
    )

    await _seed_roles(collections, established=established, require_established=True)

    # SPECIFIED: the member the admin seeding established on *this* run,
    # not the earliest-created active admin.
    for slug, _title_text in SEEDED_ACTIVE:
        assert _default_holder(_role(collections.roles, slug)) == str(corrected), (
            f"{slug!r} resolved its default to the earliest-created active "
            "admin rather than to the member the admin seeding established on "
            "this run"
        )


# ===========================================================================
# Scenario: An already-administered membership resolves a seeding
# administrator
# ===========================================================================


async def test_an_already_administered_membership_resolves_a_seeding_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An already-administered membership resolves a seeding
    administrator.

    WHEN the step runs against a membership that already holds an active
    admin, so the admin seeding altered nothing
    THEN the eight active roles are seeded holding the earliest-created
    active admin, and no membership entry is altered.

    This is the branch the first deployment of this change against the
    existing production database takes, and the one on which "the
    bootstrap admin" names nobody. The admin seeding really is run first
    and really does alter nothing — asserted, not assumed — so the
    starting state is the one the scenario describes rather than one
    this test declared.
    """
    collections = await _already_administered()
    before_rows = collections.members.rows
    before_saves = len(collections.members.saves)

    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    # The scenario's premise: the admin seeding altered nothing.
    assert collections.members.rows == before_rows, (
        "the admin seeding altered the membership, so this is not the branch "
        "the scenario describes"
    )
    assert len(collections.members.saves) == before_saves

    await _seed_roles(collections, established=established)

    earliest = _id_of(collections.members, EARLIEST_ADMIN_IDENTITY)
    # SPECIFIED: the earliest-created active admin holds the eight.
    for slug, _title_text in SEEDED_ACTIVE:
        assert _default_holder(_role(collections.roles, slug)) == str(earliest), (
            f"{slug!r} resolved its default to somebody other than the "
            "earliest-created active admin"
        )
    # SPECIFIED: and no membership entry is altered.
    assert collections.members.rows == before_rows
    assert len(collections.members.saves) == before_saves


async def test_the_earliest_created_active_admin_is_chosen_not_the_first_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The discrimination `tasks.md` 10.9 asks for, stated as its own
    test so that the scenario above cannot pass by construction.

    The membership is arranged so the correct answer — Beatrice — is
    none of the answers a wrong implementation would reach: not the
    first stored row, not the last stored row, not the last-created
    entry, not the alphabetically first identity, and not the first
    entry created (which is a *deactivated-from-admin* ordinary member).
    """
    collections = await _already_administered()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)

    await _seed_roles(collections, established=established)

    chosen = _default_holder(_role(collections.roles, "supply-chain"))
    rows = collections.members.rows
    wrong = {
        "the first stored row": str(_member_id(rows[0])),
        "the last stored row": str(_member_id(rows[-1])),
        "the last-created entry": str(
            _id_of(collections.members, LATEST_ADMIN_IDENTITY)
        ),
        "the first-created entry": str(_id_of(collections.members, ORDINARY_IDENTITY)),
        "the alphabetically first identity": str(
            _id_of(collections.members, LATER_ADMIN_IDENTITY)
        ),
    }
    correct = str(_id_of(collections.members, EARLIEST_ADMIN_IDENTITY))
    assert chosen == correct, (
        "the seeding administrator is not the earliest-created active admin; "
        f"chosen {chosen!r} against {correct!r}"
    )
    for what, identifier in wrong.items():
        if identifier == correct:
            continue
        assert chosen != identifier, f"the seed chose {what} instead"


# ===========================================================================
# Scenario: The choice is deterministic
# ===========================================================================


async def test_the_choice_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The choice is deterministic.

    WHEN the seeding administrator is resolved twice against a
    membership holding several active admins and no role the seed
    established
    THEN both resolutions name the same member.

    "No role the seed established" is why each run gets its own empty
    role store: a second run reading back the first run's roles would
    agree with itself without having resolved anything.
    """
    collections = await _already_administered()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)

    first_store = _FakeRolesStore()
    second_store = _FakeRolesStore()
    await _seed_roles(collections, established=established, roles=first_store)
    await _seed_roles(collections, established=established, roles=second_store)

    first = _default_holder(_role(first_store, "supply-chain"))
    second = _default_holder(_role(second_store, "supply-chain"))
    # DERIVED guard: both runs resolved somebody at all, so the equality
    # below is not two `None`s agreeing.
    assert first is not None
    # SPECIFIED: both resolutions name the same member.
    assert first == second, (
        "two resolutions against the same membership named different members"
    )
    # SPECIFIED (the same determinism, across all eight): every active
    # role in both runs holds that one member.
    for store in (first_store, second_store):
        for slug, _title_text in SEEDED_ACTIVE:
            assert _default_holder(_role(store, slug)) == first


# ===========================================================================
# Scenario: An unusable store fails the step
# ===========================================================================


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(RuntimeError("DATABASE_URL is not configured"), id="unconfigured"),
        pytest.param(
            ConnectionError("could not connect to the database"), id="unreachable"
        ),
    ],
)
async def test_an_unusable_store_fails_the_step(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    """Scenario: An unusable store fails the step.

    WHEN the step runs against a role store that cannot be read or
    written
    THEN the step fails rather than passing silently, and the
    application does not begin serving.

    "Does not begin serving" is the start chain's own consequence of the
    step failing, which
    `test_the_start_chain_seeds_the_roles_before_the_server_serves`
    covers from the `CMD` side; what is asserted here is the first half,
    that the step does not return normally.
    """
    collections = _Collections()
    established = await _seed_admin(monkeypatch, collections, SEEDED_IDENTITY)
    unusable = _UnusableRolesStore(failure)

    with pytest.raises(Exception) as excinfo:
        await _seed_roles(collections, established=established, roles=unusable)

    # SPECIFIED: the step fails rather than passing silently. The raised
    # error is the store's own or one carrying it — what is refused is a
    # normal return.
    raised = excinfo.value
    assert (
        raised is failure
        or type(failure).__name__
        in (
            type(raised).__name__,
            str(raised),
        )
        or str(failure) in str(raised)
    ), (
        f"the step failed with {raised!r}, which does not report the store "
        f"fault {failure!r}"
    )
    # SPECIFIED: nothing was seeded.
    assert unusable.saves == []


# ===========================================================================
# Requirement prose: the step that seeds the first admin also seeds the
# roles, before the HTTP server begins serving
# ===========================================================================


def test_the_start_chain_seeds_the_roles_before_the_server_serves() -> None:
    """SPECIFIED from the requirement's first sentence: "The step that
    seeds the first admin SHALL also seed the roles, after the admin
    exists and before the HTTP server begins serving".

    Asserted against the image's `CMD`, which is where the chain lives —
    the same reading `tests/unit/test_seed_playbook.py` takes for its own
    step. Two things follow from "the step that seeds the first admin":
    the admin seed runs before the server, and the chain gains **no
    separate role-seeding process**, since the roles are seeded inside
    the step that already runs.
    """
    dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))

    order = [
        found
        for pair in re.findall(
            r"commerce_ops\.(\w+)|(?:exec uv run )(uvicorn)", command
        )
        for found in pair
        if found
    ]
    # SPECIFIED: after the admin exists and before the server serves.
    assert "seed_admin" in order, f"the start chain runs no admin seed: {order}"
    assert order.index("seed_admin") < order.index("uvicorn")
    # SPECIFIED: the roles are seeded by *that* step, so the chain grows
    # no separate role-seeding process.
    role_steps = [name for name in order if "role" in name.lower()]
    assert role_steps == [], (
        f"the start chain runs a separate role-seeding process {role_steps!r}; "
        "the delta places the role seed inside the step that seeds the first "
        "admin"
    )
