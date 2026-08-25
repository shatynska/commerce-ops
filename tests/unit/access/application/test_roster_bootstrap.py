"""Seeding the first admin before the application serves (`roster`).

Derived strictly from the delta spec:
`openspec/changes/move-principals-to-roster/specs/roster/spec.md`, the
ADDED requirement *The first admin is seeded before the application
serves*.

REVISED after implementation: the requirement originally placed the seed
in `main.py`'s lifespan. Verification found that reading the roster there
made the serving process open a database connection before its first
request — which `database-session` forbids, and which broke two
`scheduled-runs` freshness tests. The seed now runs as its own step
between the migration and the server, so the deferral scenario became a
failure scenario (an unreadable store is a deployment fault for a step
that runs right after the migrations wrote to it).

## Why this level, and what it does not reach

Each scenario is stated about "the process starts", but what the
scenarios *assert* is what the roster holds afterwards and whether
the step continued — and both are decided by the seeding step itself,
which `design.md` Decision 4 places in its own process between
`alembic upgrade head` and the server. The step over a store double is
therefore the smallest unit that can observe every stated outcome.

DELIBERATELY UNTESTED here: that the container's start chain actually
runs the step. That is a Dockerfile `CMD`, observable only by running
the image. Its converse *is* covered —
`tests/unit/test_startup_without_configuration.py` asserts that starting
the server builds no engine, which is what fails if the seed ever
returns to the lifespan.

Two guarantees this change explicitly preserves already have tests that
must stay green: `tests/unit/test_startup_without_configuration.py`
(starting requires no configuration) and
`tests/unit/test_main_database_lifespan.py` (no connection before first
need). Nothing here duplicates them.

## Reaching the states ordinary writes cannot

Three scenarios begin from a *readable roster with no active admin* —
a state the last-admin floor makes unreachable through the write use
cases, which is exactly why the seed exists (`design.md` Decision 4).
These tests reach it by removing a row from the store double's own
state, never by inventing a row: every row still originates from a real
write or from the seed under test. `_drop` is that operation, and it is
a store-state construction, not an assertion about roster behavior.

## The interface under test does not exist yet

Fixed by the artifacts, not invented: the variable name
`BOOTSTRAP_ADMIN_IDENTITY` (`tasks.md` 3.4); the seed landing through
the validated write path as one atomic create-or-promote attributed to
a reserved system principal (delta, second requirement); the six
outcomes below.

INVENTED, recorded in the manifest as unresolved project questions:

- The bootstrap step's exported name — resolved over candidates by
  `_bootstrap_use_case`, which fails loudly naming them. Correction
  point: `_BOOTSTRAP_NAMES`.
- Its call shape: `await step(roster=store, identity=<str|None>)`, with
  the environment variable also set, so an implementation reading the
  variable itself passes too. Correction point: `_seed`.
- The failure types standing for an unconfigured and an unreachable
  store (`RuntimeError` naming the database variable; `ConnectionError`).
  Correction point: `_UNREADABLE_FAILURES`.
- The row attribute spellings, as in `test_roster_writes.py`; the two
  files correct together. They are repeated rather than shared because
  this pass may write only files matching `tests/**/test_*.py` — a
  shared `conftest.py` was not available to it.

## Expected first-run state

`commerce_ops.access.application` exports no bootstrap step and no write
use cases, so every test here is expected to fail on an absent target
(`ImportError`), which establishes only absence.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 665 passed, 0 failed
(2026-08-25).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import pytest

import commerce_ops.access.application as access_application
from commerce_ops.access.application import create_person, deactivate_person

pytestmark = pytest.mark.anyio

BOOTSTRAP_VARIABLE: Final = "BOOTSTRAP_ADMIN_IDENTITY"

# DERIVED sample values; no artifact fixes example identities.
SEEDED_IDENTITY: Final = "U01ALICE"
CORRECTED_IDENTITY: Final = "U02BOB"
ROSTERED_ADMIN_IDENTITY: Final = "U03CAROL"
UNRELATED_IDENTITY: Final = "U04DAVE"

PRINCIPAL: Final = "helen"

_BOOTSTRAP_NAMES: Final = (
    "seed_bootstrap_admin",
    "bootstrap_admin",
    "ensure_bootstrap_admin",
    "seed_first_admin",
    "bootstrap_first_admin",
    "run_admin_bootstrap",
)

# INVENTED: what an unconfigured and an unreachable store raise.
_UNREADABLE_FAILURES: Final = (
    pytest.param(RuntimeError("DATABASE_URL is not configured"), id="unconfigured"),
    pytest.param(
        ConnectionError("could not connect to the database"), id="unreachable"
    ),
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Store doubles
# ---------------------------------------------------------------------------


class _FakeRosterStore:
    def __init__(self, rows: tuple[Any, ...] = (), version: int = 0) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.rows, self.version

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


class _UnreadableRosterStore(_FakeRosterStore):
    """A store that cannot be read — unconfigured or unreachable."""

    def __init__(self, failure: Exception) -> None:
        super().__init__()
        self.failure = failure

    async def load(self) -> tuple[tuple[Any, ...], int]:
        raise self.failure

    async def save(self, rows: Any, *, expected_version: int) -> None:
        raise self.failure


# ---------------------------------------------------------------------------
# Row accessors: the single correction point (mirrors test_roster_writes.py)
# ---------------------------------------------------------------------------

_ID_NAMES: Final = ("id", "person_id", "identifier")
_NAME_NAMES: Final = ("display_name", "name")
_SLACK_NAMES: Final = ("slack_identity", "slack_user_id", "slack_id")
_ADMIN_NAMES: Final = ("admin", "is_admin")
_ACTIVE_NAMES: Final = ("active", "is_active")
_CREATED_BY: Final = ("created_by",)


def _targets(row: Any) -> tuple[Any, ...]:
    found = [row]
    for attribute in ("person", "entry", "definition", "record"):
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
        f"a stored roster row exposes no {what} under any of {names} — "
        "correct this file's accessor names to the implemented row"
    )


def _id(row: Any) -> Any:
    return _field(row, _ID_NAMES, "generated identifier")


def _slack(row: Any) -> str:
    return str(_field(row, _SLACK_NAMES, "Slack identity"))


def _name(row: Any) -> str:
    return str(_field(row, _NAME_NAMES, "display name"))


def _is_admin(row: Any) -> bool:
    return bool(_field(row, _ADMIN_NAMES, "admin flag"))


def _is_active(row: Any) -> bool:
    return bool(_field(row, _ACTIVE_NAMES, "active flag"))


def _rows_for(store: _FakeRosterStore, identity: str) -> tuple[Any, ...]:
    return tuple(row for row in store.rows if _slack(row) == identity)


def _row_for(store: _FakeRosterStore, identity: str) -> Any:
    rows = _rows_for(store, identity)
    if len(rows) != 1:
        pytest.fail(
            f"expected exactly one row carrying {identity!r}, found {len(rows)}"
        )
    return rows[0]


def _active_admins(store: _FakeRosterStore) -> tuple[Any, ...]:
    return tuple(row for row in store.rows if _is_active(row) and _is_admin(row))


def _drop(store: _FakeRosterStore, identity: str) -> None:
    """Removes a row from the store's own state — see the docstring; this
    constructs a store state, it exercises no roster behavior."""
    remaining = tuple(row for row in store.rows if _slack(row) != identity)
    assert len(remaining) < len(store.rows), (
        f"no row carrying {identity!r} to remove from the store state"
    )
    store.rows = remaining
    store.version += 1


# ---------------------------------------------------------------------------
# Call shapes: the single correction points
# ---------------------------------------------------------------------------


def _bootstrap_use_case() -> Any:
    for name in _BOOTSTRAP_NAMES:
        found = getattr(access_application, name, None)
        if found is not None:
            return found
    pytest.fail(
        "the access application surface exports no startup bootstrap step "
        f"under any of {_BOOTSTRAP_NAMES} — correct this file's candidate "
        "names to the implemented one"
    )


def _is_argument_shape_error(error: TypeError) -> bool:
    text = str(error).lower()
    return any(
        marker in text for marker in ("argument", "positional", "keyword", "parameter")
    )


async def _seed(
    monkeypatch: pytest.MonkeyPatch,
    store: Any,
    identity: str | None,
) -> Any:
    """Runs the startup bootstrap once.

    The variable is set in the environment *and* offered as an argument,
    so an implementation reading it either way is exercised. Only
    argument-shape `TypeError`s fall through to the next call shape, so
    a genuine refusal is never mistaken for a wrong call signature.
    """
    if identity is None:
        monkeypatch.delenv(BOOTSTRAP_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(BOOTSTRAP_VARIABLE, identity)

    step: Any = _bootstrap_use_case()
    attempts: tuple[Callable[[], Any], ...] = (
        lambda: step(roster=store, identity=identity),
        lambda: step(roster=store),
        lambda: step(store, identity=identity),
        lambda: step(store),
    )
    last: TypeError | None = None
    for attempt in attempts:
        try:
            return await attempt()
        except TypeError as error:
            if not _is_argument_shape_error(error):
                raise
            last = error
    raise AssertionError(
        "no attempted call shape matched the bootstrap step's signature; "
        f"last argument error: {last}"
    )


async def _create(
    store: _FakeRosterStore,
    *,
    display_name: str,
    slack_identity: str,
    admin: bool = False,
    principal: str = PRINCIPAL,
) -> Any:
    return await create_person(
        roster=store,
        principal=principal,
        display_name=display_name,
        slack_identity=slack_identity,
        clickup_user_id=None,
        admin=admin,
    )


# ---------------------------------------------------------------------------
# Scenario: An empty roster is seeded
# ---------------------------------------------------------------------------


async def test_an_empty_roster_is_seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: An empty roster is seeded.

    WHEN the process starts with a readable, empty roster and the
    bootstrap variable naming a Slack identity
    THEN the roster afterward holds that identity as an active admin
    entry whose display name is the Slack identity itself.

    The attribution assertion is the requirement's "attributed to a
    reserved system principal" (second requirement of the delta): the
    seed's creator is *not* a human principal. DERIVED: that the
    reserved principal's spelling mentions "bootstrap" —
    `design.md` Decision 4 and `tasks.md` 3.4 both spell it
    `system:bootstrap`, but the spec fixes only its reserved-ness.
    """
    store = _FakeRosterStore()

    await _seed(monkeypatch, store, SEEDED_IDENTITY)

    # SPECIFIED: the identity is on the roster, active and admin.
    row = _row_for(store, SEEDED_IDENTITY)
    assert _is_active(row) is True
    assert _is_admin(row) is True
    # SPECIFIED: its display name is the Slack identity itself.
    assert _name(row) == SEEDED_IDENTITY
    # SPECIFIED: through the validated write path, as a real write.
    assert store.saves, "the seed persisted nothing"
    # SPECIFIED: attributed to a reserved system principal, not a human.
    creator = str(_field(row, _CREATED_BY, "creator attribution"))
    assert creator not in ("", PRINCIPAL, SEEDED_IDENTITY)
    assert "bootstrap" in creator.lower()


# ---------------------------------------------------------------------------
# Scenario: An existing entry is promoted rather than duplicated
# ---------------------------------------------------------------------------


async def test_an_existing_entry_is_promoted_rather_than_duplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An existing entry is promoted rather than duplicated.

    WHEN the process starts with no active admin on the readable roster
    and the bootstrap variable naming a Slack identity an existing
    deactivated entry carries
    THEN that entry becomes active and admin, and no second entry with
    that identity exists.

    The starting state — a deactivated entry and no active admin — is
    built by seeding, creating a second admin, deactivating the first
    through an ordinary write, then removing the second admin's row from
    the store state (see the module docstring). The person's identifier
    is captured beforehand, so "promoted rather than duplicated" is
    asserted as the *same* entry surviving, not merely as a row count.
    """
    store = _FakeRosterStore()
    await _seed(monkeypatch, store, SEEDED_IDENTITY)
    await _create(
        store,
        display_name="Carol Admin",
        slack_identity=ROSTERED_ADMIN_IDENTITY,
        admin=True,
    )
    person_id = _id(_row_for(store, SEEDED_IDENTITY))
    await deactivate_person(roster=store, principal=PRINCIPAL, person_id=person_id)
    _drop(store, ROSTERED_ADMIN_IDENTITY)
    assert _active_admins(store) == ()

    await _seed(monkeypatch, store, SEEDED_IDENTITY)

    # SPECIFIED: no second entry with that identity exists.
    assert len(_rows_for(store, SEEDED_IDENTITY)) == 1
    row = _row_for(store, SEEDED_IDENTITY)
    # SPECIFIED: that entry becomes active and admin.
    assert _is_active(row) is True
    assert _is_admin(row) is True
    # SPECIFIED: *that* entry — the same one, under the same identifier.
    assert _id(row) == person_id


# ---------------------------------------------------------------------------
# Scenario: A rostered admin makes the variable inert
# ---------------------------------------------------------------------------


async def test_a_rostered_admin_makes_the_variable_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rostered admin makes the variable inert.

    WHEN the process starts with the readable roster holding an active
    admin beyond a lone seed-attributed entry
    THEN the roster is not altered, whatever the bootstrap variable
    names.

    "Beyond a lone seed-attributed entry" is built as the seeded admin
    plus a second admin created by an ordinary attributed write — the
    state in which `design.md` Decision 4 says the bound expires. The
    variable then names a third, unrelated identity: an implementation
    still honouring it would add a row.
    """
    store = _FakeRosterStore()
    await _seed(monkeypatch, store, SEEDED_IDENTITY)
    await _create(
        store,
        display_name="Carol Admin",
        slack_identity=ROSTERED_ADMIN_IDENTITY,
        admin=True,
    )
    before_rows, before_version = store.rows, store.version
    before_saves = len(store.saves)

    await _seed(monkeypatch, store, UNRELATED_IDENTITY)

    # SPECIFIED: the roster is not altered.
    assert store.rows == before_rows
    assert store.version == before_version
    assert len(store.saves) == before_saves
    # SPECIFIED: the variable confers nothing.
    assert _rows_for(store, UNRELATED_IDENTITY) == ()


# ---------------------------------------------------------------------------
# Scenario: A mis-seeded first admin is corrected by redeploying
# ---------------------------------------------------------------------------


async def test_a_mis_seeded_first_admin_is_corrected_by_redeploying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A mis-seeded first admin is corrected by redeploying.

    WHEN the process starts with the readable roster's only active admin
    being the single seed-attributed entry, and the variable now names a
    different Slack identity
    THEN the newly named identity becomes an active admin alongside it,
    and nothing is deactivated by the seed.

    The starting state is exactly what the first scenario leaves behind,
    so no state construction is needed. "Nothing is deactivated by the
    seed" is the clause that makes the correction path safe: the
    mis-typed entry stays active until an ordinary write retires it,
    which is what keeps the last-admin floor from stranding the roster.
    """
    store = _FakeRosterStore()
    await _seed(monkeypatch, store, SEEDED_IDENTITY)
    mis_typed_id = _id(_row_for(store, SEEDED_IDENTITY))

    await _seed(monkeypatch, store, CORRECTED_IDENTITY)

    # SPECIFIED: the newly named identity becomes an active admin.
    corrected = _row_for(store, CORRECTED_IDENTITY)
    assert _is_active(corrected) is True
    assert _is_admin(corrected) is True
    # SPECIFIED: alongside it — nothing is deactivated by the seed.
    mis_typed = _row_for(store, SEEDED_IDENTITY)
    assert _id(mis_typed) == mis_typed_id
    assert _is_active(mis_typed) is True
    assert _is_admin(mis_typed) is True
    assert len(_active_admins(store)) == 2


async def test_the_bound_expires_once_an_admin_beyond_the_seed_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED, the negative half of the same bound: once the corrected
    admin has been seeded, the variable is inert again.

    `design.md` Decision 4 states the bound expires "the moment any admin
    beyond the lone seed exists ... so the variable never becomes the
    standing overlay this decision rejects". Without this, an
    implementation re-seeding on every start whenever the variable names
    an unrostered identity would satisfy every scenario above.
    """
    store = _FakeRosterStore()
    await _seed(monkeypatch, store, SEEDED_IDENTITY)
    await _seed(monkeypatch, store, CORRECTED_IDENTITY)
    before_rows, before_version = store.rows, store.version

    await _seed(monkeypatch, store, UNRELATED_IDENTITY)

    # DERIVED: two seed-attributed admins are no longer "a lone seed".
    assert store.rows == before_rows
    assert store.version == before_version
    assert _rows_for(store, UNRELATED_IDENTITY) == ()


# ---------------------------------------------------------------------------
# Scenario: No admin and no variable stops startup
# ---------------------------------------------------------------------------


async def test_no_admin_and_no_variable_stops_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No admin and no variable stops startup.

    WHEN the process starts with a readable roster holding no active
    admin and no bootstrap variable
    THEN startup fails with an error naming the missing variable.

    Naming the variable is the whole value of the refusal — it is what
    tells a deployer which variable to set. An empty roster is the
    simplest readable admin-less roster, and reaching it needs no
    construction.

    DELIBERATELY UNTESTED (manifest): that the raised error actually
    stops *startup*, which depends on the lifespan wiring this tier
    cannot observe.
    """
    store = _FakeRosterStore()

    # The refusal's exception type is not fixed by any artifact, so the
    # catch is broad and the discrimination is the message assertion.
    with pytest.raises(Exception) as excinfo:
        await _seed(monkeypatch, store, None)

    # SPECIFIED: the error names the missing variable.
    assert BOOTSTRAP_VARIABLE in str(excinfo.value)
    # SPECIFIED (from the requirement's refusal shape): nothing was
    # written to a roster nobody can administer.
    assert store.saves == []


# ---------------------------------------------------------------------------
# An unreadable store fails the step
#
# REWRITTEN, not weakened. The requirement this was derived from moved the
# seed out of the serving process's startup and into a step of its own
# after the migrations (`roster` spec, "The first admin is seeded before
# the application serves"), because seeding in the lifespan made the
# server open a database connection before its first request — which
# `database-session` forbids, and which broke two `scheduled-runs`
# freshness tests that simulate an unreachable database.
#
# Deferring made sense only while the seed rode startup: it was what kept
# an application with no database configured able to start. A step that
# runs immediately after the migrations that wrote to that same store has
# no such case to protect, so an unreadable store is now a deployment
# fault. The assertion is correspondingly *stronger* — the failure must
# propagate rather than be swallowed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failure", _UNREADABLE_FAILURES)
async def test_an_unreadable_store_fails_the_step(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    """Scenario: an unreadable store fails the step.

    WHEN the step runs against a store that cannot be read
    THEN it fails rather than passing silently, and writes nothing.

    The variable *is* set here, so the failure cannot be the missing-
    variable refusal wearing another error's clothes.
    """
    store = _UnreadableRosterStore(failure)

    with pytest.raises(Exception) as excinfo:
        await _seed(monkeypatch, store, SEEDED_IDENTITY)

    # SPECIFIED: the store's own failure reaches the caller, so the
    # container's start chain stops on it.
    assert excinfo.value is failure or failure.__class__ is excinfo.type
    # SPECIFIED: nothing was written.
    assert store.saves == []
