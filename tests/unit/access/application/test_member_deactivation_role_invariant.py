"""The member/role invariant, stated from the membership's side
(`members`).

Derived strictly from the delta spec
`openspec/changes/rebuild-the-member-directory/specs/members/spec.md` —
its one ADDED requirement, *A member holding an active role's default may
not be deactivated*, all six scenarios, plus the two sentences of its
prose that carry no scenario of their own:

- that the refusal names **every** blocking role rather than the first;
- that the system moves no default and retires no role implicitly on the
  member's behalf.

The same invariant stated from the roles' side — that no write may leave
an active role without an active default holder — is covered in
`test_role_writes.py`. This file covers only the deactivation route into
it, which is the one `members` owns.

## Why this level

Every scenario is stated about a *write* and what is persisted
afterwards, so the smallest observing unit is `deactivate_member` over
store doubles, the level `test_members_writes.py` established for the
membership's other refusals.

## What is fixed, and what is INVENTED

Fixed by the delta: that the deactivation is refused; that every
blocking active role is named; that a non-default holder and a default
of draft or retired roles deactivate freely; that moving the default
unblocks it; that this refusal composes with the last-active-admin one
rather than replacing it.

INVENTED, recorded in the manifest with its correction point:

- That `deactivate_member` reaches the role collection through a `roles=`
  argument. It must reach it somehow — the refusal cannot be decided
  without reading the roles — and no artifact fixes how. Correction
  point: `_deactivate`.
- The role use-case names, call shapes and row accessors, as
  `test_role_writes.py` records; the two files correct together. They
  are repeated rather than shared because this pass may write only files
  matching `tests/**/test_*.py`.
- `REFUSED`, the acceptable refusal types, as `test_members_writes.py`
  records.

## Expected first-run state

No role use cases exist, so every test here is expected to fail on an
absent target — the use-case resolver fails naming its candidates,
before any assertion has run. That establishes only absence.

Baseline recorded before these tests were written, at commit `8c25749`:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed
(2026-09-02).
"""

from __future__ import annotations

import importlib
import uuid
from collections.abc import Callable
from typing import Any, Final

import pytest

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_member, deactivate_member
from tests.support.admin import ADMIN_IDENTITY
from tests.support.fixtures import PRINCIPAL

pytestmark = pytest.mark.anyio

#: Called through an untyped alias deliberately: the `roles` argument
#: this file passes does not exist on the signature yet, and a checker
#: reading the *current* signature would report the very absence these
#: tests are written to report. The alias goes when the parameter lands.
_deactivate_member: Any = deactivate_member

SECOND_ADMIN_IDENTITY: Final = "U02BOB"
MEMBER_IDENTITY: Final = "U03CAROL"
OTHER_IDENTITY: Final = "U04DAVE"

DRAFT: Final = "draft"
ACTIVE: Final = "active"


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


def _is_active(store: _FakeMembersStore, identity: str) -> bool:
    return bool(
        _field(_member_row(store, identity), _MEMBER_ACTIVE_NAMES, "active flag")
    )


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
    pytest.fail(f"a stored holder {holder!r} exposes no member identifier")


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
    pytest.fail(f"no stored role carries the slug {slug!r}")


def _faults(error: BaseException) -> tuple[str, ...]:
    for attribute in ("faults", "errors", "messages", "reasons"):
        carried = getattr(error, attribute, None)
        if isinstance(carried, (list, tuple)) and carried:
            return tuple(str(fault) for fault in carried)
    if error.args and isinstance(error.args[0], (list, tuple)):
        return tuple(str(fault) for fault in error.args[0])
    return tuple(line for line in str(error).splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Call shapes: the single correction points
# ---------------------------------------------------------------------------

_CREATE_NAMES: Final = ("create_role",)
_ADD_HOLDER_NAMES: Final = ("add_role_holder", "add_holder", "add_role_member")
_MOVE_DEFAULT_NAMES: Final = (
    "move_role_default",
    "move_default_holder",
    "move_default",
    "set_role_default",
    "set_default_holder",
)
_RETIRE_NAMES: Final = ("retire_role",)


def _use_case(names: tuple[str, ...], what: str) -> Any:
    for name in names:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        f"the access application surface exports no {what} use case under any "
        f"of {names} — correct this file's candidate names to the implemented "
        "one"
    )


def _is_argument_shape_error(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _invoke(attempts: tuple[Callable[[], Any], ...], what: str) -> Any:
    last: TypeError | None = None
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _is_argument_shape_error(error):
                raise
            last = error
    pytest.fail(
        f"no attempted call shape matched the {what}'s signature; last "
        f"argument error: {last}"
    )


async def _create_member(
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


async def _deactivate(collections: _Collections, member_id: Any) -> Any:
    """Deactivates a member.

    INVENTED: that the use case reaches the role collection through a
    `roles=` argument. It must reach it somehow — the new refusal cannot
    be decided without reading the roles — but no artifact fixes how, so
    the shape without it is attempted as a fallback for an
    implementation that reaches the roles some other way.
    """
    return await _invoke(
        (
            lambda: _deactivate_member(
                members=collections.members,
                roles=collections.roles,
                principal=PRINCIPAL,
                member_id=member_id,
            ),
            lambda: _deactivate_member(
                members=collections.members,
                principal=PRINCIPAL,
                member_id=member_id,
            ),
        ),
        "deactivate-a-member",
    )


async def _create_role(
    collections: _Collections,
    *,
    slug: str,
    title: str,
    status: str,
    default_holder: Any = None,
) -> Any:
    step = _use_case(_CREATE_NAMES, "create-a-role")
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": PRINCIPAL,
        "slug": slug,
        "title": title,
    }
    return await _invoke(
        (
            lambda: step(**common, status=status, default_holder=default_holder),
            lambda: step(**common, status=status, default_holder_id=default_holder),
            lambda: step(**common, status=status, holder=default_holder),
            lambda: step(**common, status=status),
        ),
        "create-a-role",
    )


async def _role_action(
    names: tuple[str, ...], what: str, collections: _Collections, slug: str, **kw: Any
) -> Any:
    step = _use_case(names, what)
    common: dict[str, Any] = {
        "roles": collections.roles,
        "members": collections.members,
        "principal": PRINCIPAL,
    }
    member_id = kw.get("member_id")
    if member_id is None:
        attempts: tuple[Callable[[], Any], ...] = (
            lambda: step(**common, slug=slug),
            lambda: step(**common, role_slug=slug),
        )
    else:
        attempts = (
            lambda: step(**common, slug=slug, member_id=member_id),
            lambda: step(**common, role_slug=slug, member_id=member_id),
            lambda: step(**common, slug=slug, holder=member_id),
            lambda: step(**common, slug=slug, default_holder=member_id),
        )
    return await _invoke(attempts, what)


async def _add_holder(collections: _Collections, slug: str, member_id: Any) -> Any:
    return await _role_action(
        _ADD_HOLDER_NAMES, "add-a-holder", collections, slug, member_id=member_id
    )


async def _move_default(collections: _Collections, slug: str, member_id: Any) -> Any:
    return await _role_action(
        _MOVE_DEFAULT_NAMES,
        "move-the-default",
        collections,
        slug,
        member_id=member_id,
    )


async def _retire(collections: _Collections, slug: str) -> Any:
    return await _role_action(_RETIRE_NAMES, "retire-a-role", collections, slug)


# ---------------------------------------------------------------------------
# Starting states
# ---------------------------------------------------------------------------


async def _membership() -> _Collections:
    """Two active admins and two ordinary members — two admins so that
    an ordinary deactivation never meets the last-admin floor, which is
    a separate refusal and must not be what these tests observe."""
    collections = _Collections()
    await _create_member(
        collections.members,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Bob Admin",
        slack_identity=SECOND_ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Carol Member",
        slack_identity=MEMBER_IDENTITY,
    )
    await _create_member(
        collections.members,
        display_name="Dave Deputy",
        slack_identity=OTHER_IDENTITY,
    )
    return collections


def _snapshot(collections: _Collections) -> tuple[Any, ...]:
    return (
        collections.members.rows,
        len(collections.members.saves),
        collections.roles.rows,
        len(collections.roles.saves),
    )


def _assert_unchanged(collections: _Collections, before: tuple[Any, ...]) -> None:
    assert _snapshot(collections) == before, (
        "a rejected deactivation reached a store: nothing is persisted"
    )


# ===========================================================================
# Scenario: Deactivating an active role's default holder is refused
# ===========================================================================


async def test_deactivating_an_active_roles_default_holder_is_refused() -> None:
    """Scenario: Deactivating an active role's default holder is refused.

    WHEN a member who is the default holder of an active role is
    deactivated
    THEN the write is rejected explaining that the role would be left
    without a default holder, and nothing is persisted.

    The member deactivated is an ordinary member and the membership
    holds two active admins, so the last-admin refusal plays no part in
    this outcome — what is observed is the role refusal alone.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    await _create_role(
        collections,
        slug="supply-chain",
        title="Supply Chain Manager",
        status=ACTIVE,
        default_holder=member,
    )
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _deactivate(collections, member)

    # SPECIFIED: explaining that the role would be left without a default.
    text = str(excinfo.value).lower()
    assert "supply-chain" in text or "supply chain manager" in text, (
        f"the refusal does not name the blocking role: {excinfo.value}"
    )
    assert "default" in text or "holder" in text
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)
    assert _is_active(collections.members, MEMBER_IDENTITY) is True


# ===========================================================================
# Scenario: Every blocking role is named at once
# ===========================================================================


async def test_every_blocking_role_is_named_at_once() -> None:
    """Scenario: Every blocking role is named at once.

    WHEN a member who is the default holder of several active roles is
    deactivated
    THEN the refusal names all of those roles, not only one of them.

    Three blocking roles, and one further active role the member merely
    holds — so a refusal listing every role the member touches would be
    wrong in the other direction, and is caught here too.

    The requirement's reason is operational: a member who deactivates
    while holding eight such roles should learn that in one refusal
    rather than in eight attempts.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    other = _id_of(collections.members, OTHER_IDENTITY)
    blocking = ("supply-chain", "ppc", "brand")
    for slug in blocking:
        await _create_role(
            collections,
            slug=slug,
            title=slug.replace("-", " ").title(),
            status=ACTIVE,
            default_holder=member,
        )
    await _create_role(
        collections,
        slug="marketing",
        title="Marketing Manager",
        status=ACTIVE,
        default_holder=other,
    )
    await _add_holder(collections, "marketing", member)
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _deactivate(collections, member)

    reported = str(excinfo.value) + " " + " ".join(_faults(excinfo.value))
    # SPECIFIED: all of those roles, not only one of them.
    missing = [slug for slug in blocking if slug not in reported.lower()]
    assert missing == [], (
        f"the refusal names only some of the blocking roles; missing "
        f"{missing!r}. Reported: {reported!r}"
    )
    # DERIVED discrimination: a role the member merely holds is not a
    # blocking role, so naming it would be a different fault.
    assert "marketing" not in reported.lower(), (
        "the refusal names a role the member holds without being its default; "
        "only the roles that would be left without a default block"
    )
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)


# ===========================================================================
# Scenario: A non-default holder deactivates freely
# ===========================================================================


async def test_a_non_default_holder_deactivates_freely() -> None:
    """Scenario: A non-default holder deactivates freely.

    WHEN a member who holds active roles but is the default of none is
    deactivated
    THEN the write lands and the member leaves the active membership.

    This is what stops the refusal from being implemented as "a holder
    of an active role cannot be deactivated". The member holds two
    active roles, so the distinction being made is default-ness rather
    than the count of roles held.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    other = _id_of(collections.members, OTHER_IDENTITY)
    for slug in ("supply-chain", "ppc"):
        await _create_role(
            collections,
            slug=slug,
            title=slug.replace("-", " ").title(),
            status=ACTIVE,
            default_holder=other,
        )
        await _add_holder(collections, slug, member)

    await _deactivate(collections, member)

    # SPECIFIED: the write lands and the member leaves the active membership.
    assert _is_active(collections.members, MEMBER_IDENTITY) is False
    # DERIVED: the roles are untouched — the deactivation is not a
    # holder removal.
    for slug in ("supply-chain", "ppc"):
        assert _default_holder(_role(collections.roles, slug)) == str(other)


# ===========================================================================
# Scenario: Holding only draft or retired roles does not block
# ===========================================================================


async def test_holding_only_draft_or_retired_roles_does_not_block() -> None:
    """Scenario: Holding only draft or retired roles does not block.

    WHEN a member who is the default holder of draft and retired roles
    only is deactivated
    THEN the write lands.

    Both statuses are present in the one starting state, because the
    scenario names both and an implementation exempting only one of them
    would otherwise pass. The retired role is built by retiring an
    active one the member is the default of — the state the collection
    actually produces — rather than by creating a retired role directly.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)

    await _create_role(
        collections,
        slug="managing-director",
        title="Managing Director",
        status=DRAFT,
    )
    await _add_holder(collections, "managing-director", member)
    await _move_default(collections, "managing-director", member)

    await _create_role(
        collections,
        slug="operations",
        title="Operations Manager",
        status=ACTIVE,
        default_holder=member,
    )
    await _retire(collections, "operations")

    assert _status_of(_role(collections.roles, "managing-director")) == DRAFT
    assert _status_of(_role(collections.roles, "operations")) == "retired"
    assert _default_holder(_role(collections.roles, "managing-director")) == str(member)
    assert _default_holder(_role(collections.roles, "operations")) == str(member)

    await _deactivate(collections, member)

    # SPECIFIED: the write lands.
    assert _is_active(collections.members, MEMBER_IDENTITY) is False


# ===========================================================================
# Scenario: Moving the default unblocks the deactivation
# ===========================================================================


async def test_moving_the_default_unblocks_the_deactivation() -> None:
    """Scenario: Moving the default unblocks the deactivation.

    WHEN the default of each blocking active role is moved to another
    holder, and the member is deactivated again
    THEN the write lands.

    "Each" is the point: the first of two roles is moved, the
    deactivation is attempted and still refused, and only after the
    second is moved does it land. Without the intermediate attempt this
    would pass on an implementation that stopped blocking as soon as
    *any* default moved.

    The requirement's own sentence — that the system moves no default
    and retires no role implicitly on the member's behalf — is asserted
    at the intermediate step, where the still-blocking role is observed
    unchanged after the refusal.
    """
    collections = await _membership()
    member = _id_of(collections.members, MEMBER_IDENTITY)
    successor = _id_of(collections.members, OTHER_IDENTITY)
    for slug in ("supply-chain", "ppc"):
        await _create_role(
            collections,
            slug=slug,
            title=slug.replace("-", " ").title(),
            status=ACTIVE,
            default_holder=member,
        )
        await _add_holder(collections, slug, successor)

    await _move_default(collections, "supply-chain", successor)
    before = _snapshot(collections)

    with pytest.raises(REFUSED):
        await _deactivate(collections, member)

    # SPECIFIED (requirement prose): the system does neither implicitly
    # on the member's behalf — the still-blocking role is untouched.
    _assert_unchanged(collections, before)
    still = _role(collections.roles, "ppc")
    assert _default_holder(still) == str(member)
    assert _status_of(still) == ACTIVE

    await _move_default(collections, "ppc", successor)
    await _deactivate(collections, member)

    # SPECIFIED: the write lands.
    assert _is_active(collections.members, MEMBER_IDENTITY) is False


# ===========================================================================
# Scenario: Both refusals report together
# ===========================================================================


async def test_both_refusals_report_together() -> None:
    """Scenario: Both refusals report together.

    WHEN the membership's last active admin is also the default holder
    of an active role and that member is deactivated
    THEN the write is rejected reporting both the last-admin fault and
    the role fault, and nothing is persisted.

    "Both" is asserted as two distinguishable faults — one naming the
    role, one about the admin floor — so an implementation that reported
    whichever it checked first fails. The delta's own sentence is that
    the two refusals are independent and compose: a write may be refused
    by either, by both, or by neither.
    """
    collections = _Collections()
    await _create_member(
        collections.members,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Carol Member",
        slack_identity=MEMBER_IDENTITY,
    )
    admin = _id_of(collections.members, ADMIN_IDENTITY)
    await _create_role(
        collections,
        slug="controller",
        title="Financial Controller",
        status=ACTIVE,
        default_holder=admin,
    )
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _deactivate(collections, admin)

    faults = _faults(excinfo.value)
    reported = str(excinfo.value) + " " + " ".join(faults)
    # SPECIFIED: both faults, reported together.
    assert len(faults) >= 2, (
        f"the rejection reported one fault where the write breaks two rules: {faults!r}"
    )
    assert "controller" in reported.lower(), (
        f"no fault names the blocking role: {reported!r}"
    )
    assert "admin" in reported.lower(), (
        f"no fault reports the last-active-admin floor: {reported!r}"
    )
    # SPECIFIED: nothing is persisted.
    _assert_unchanged(collections, before)
    assert _is_active(collections.members, ADMIN_IDENTITY) is True


async def test_an_admin_holding_no_active_default_is_refused_by_the_floor_alone() -> (
    None
):
    """SPECIFIED from the requirement's prose: the two refusals are
    independent and compose — "a write may be refused by either, by both,
    or by neither".

    Recorded as its own test because `test_both_refusals_report_together`
    cannot distinguish "both faults" from "one fault mentioning two
    things" unless the two are also observed apart. Here the last active
    admin holds no active role's default, so only the pre-existing floor
    refuses, and its fault does not name a role.
    """
    collections = _Collections()
    await _create_member(
        collections.members,
        display_name="Alice Admin",
        slack_identity=ADMIN_IDENTITY,
        admin=True,
    )
    await _create_member(
        collections.members,
        display_name="Carol Member",
        slack_identity=MEMBER_IDENTITY,
    )
    member = _id_of(collections.members, MEMBER_IDENTITY)
    admin = _id_of(collections.members, ADMIN_IDENTITY)
    await _create_role(
        collections,
        slug="creative",
        title="Creative Manager",
        status=ACTIVE,
        default_holder=member,
    )
    before = _snapshot(collections)

    with pytest.raises(REFUSED) as excinfo:
        await _deactivate(collections, admin)

    reported = str(excinfo.value) + " " + " ".join(_faults(excinfo.value))
    # SPECIFIED: refused by the last-admin floor …
    assert "admin" in reported.lower()
    # … and not by the role rule, which this member does not meet.
    assert "creative" not in reported.lower(), (
        "the refusal names a role whose default this member is not; the two "
        "refusals are independent"
    )
    _assert_unchanged(collections, before)


def test_the_membership_moves_no_default_and_retires_no_role_implicitly() -> None:
    """SPECIFIED from the requirement's prose: "To deactivate a member
    who is an active role's default, the default is first moved to
    another holder or the role is retired; the system SHALL NOT do either
    implicitly on the member's behalf."

    DERIVED mechanism: the membership's own use cases expose no verb that
    would do it. The behavioural half — that a refused deactivation
    leaves the blocking role exactly as it stands — is asserted in
    `test_moving_the_default_unblocks_the_deactivation`; this asserts the
    structural half, that no `deactivate_member(..., force=...)`-shaped
    escape hatch is offered.
    """
    import inspect

    signature = inspect.signature(deactivate_member)
    escapes = [
        name
        for name in signature.parameters
        if any(
            word in name.lower()
            for word in ("force", "cascade", "promote", "retire", "reassign")
        )
    ]
    assert escapes == [], (
        f"`deactivate_member` offers {escapes!r}, which would move a default "
        "or retire a role on the member's behalf"
    )
