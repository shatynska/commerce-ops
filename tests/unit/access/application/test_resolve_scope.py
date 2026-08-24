"""Resolving a Slack user identity to an access scope (`access-scope`).

Derived strictly from three ADDED requirements in
`openspec/changes/introduce-access-scope/specs/access-scope/spec.md`:

- *A known principal's scope derives from its grants* (all 3 scenarios)
- *An unknown asker resolves to the empty scope* (1 scenario)
- *A grant naming an unregistered SKU confers nothing without failing the
  resolution* (1 scenario)

plus the resolution-side half of *A malformed directory prevents serving
rather than failing resolutions*, whose startup half no test here asserts
-- see `test-manifest.md` at the change root, which records that gap and
its reason.

## Why the application level

Each scenario is stated about what *resolution* answers, and resolution is
the `access` application layer's `resolve_scope` use case over two
collaborators: a loaded principals directory and a SKU-to-product resolver
port. Both are supplied as doubles here, so this is the project's fast
mocked unit tier -- no catalog, no Postgres, no I/O beyond a `tmp_path`
YAML file the loader reads.

## Directories are built through the loader, deliberately

`resolve_scope` needs a loaded directory, and the only shape any artifact
describes for one is the YAML file the loader validates. Building these
directories through `load_principals` keeps a single invented shape in play
rather than two (the file *and* a guessed domain constructor), at the cost
of coupling this file to the loader: a loader defect fails these tests too.
The trade is recorded in the manifest.

## The interface under test does not exist yet, and its shape is INVENTED

The `access` module is created by this change (`tasks.md` 2.1-2.4), so
every test here is expected to fail on an absent target
(`ModuleNotFoundError`). That failure establishes only absence.

Fixed by the artifacts, not invented: a `resolve_scope` use case exported
from the module's `application/__init__.py`, depending on a consumer-owned
SKU-resolver port, mapping an all-products grant to the unrestricted scope,
SKU grants to the resolved products' identifiers, and an unknown identity
to the empty scope (`tasks.md` 2.4, `design.md` Decisions 4-6).

INVENTED, and recorded as unresolved project questions in the manifest:

- `resolve_scope(directory, resolve_sku, *, identity)`, async -- ports
  first, following this project's `run_daily_digest(reader)` /
  `read_launches(launches, playbooks, *, as_of)` precedent; async because
  the resolver port is implemented over catalog's async
  `get_product_by_sku`. `_resolve` below is the single correction point.
- The identity is passed as a plain string. `design.md`'s "nothing in any
  `domain/` layer knows what a Slack user is" rules out a Slack-specific
  value object in the domain, and no artifact names one elsewhere.
- The resolver port is an async callable taking a SKU and answering the
  product identifier or `None`, shaped like briefing's `_FakeCatalog`
  double (`tests/unit/briefing/application/test_briefing_assembly.py`).
- The scope construction spellings, for the assertions' side (`_permits`).

Correcting any of those is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: which product identifiers each resolution permits, and that a
stranger and a stale grant both produce a scope rather than an error.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.access.application import resolve_scope
from commerce_ops.access.domain.principals import InvalidPrincipalsError
from commerce_ops.access.infrastructure.driven.principals_loader import (
    load_principals,
)
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

# DERIVED sample values; no artifact fixes example identities or SKUs.
ALL_PRODUCTS_IDENTITY: Final = "U01ALICE"
SKU_GRANTED_IDENTITY: Final = "U02BOB"
EMPTY_GRANT_IDENTITY: Final = "U03CAROL"
STRANGER_IDENTITY: Final = "U99STRANGER"

FIRST_SKU: Final = Sku("WIDGET-001")
SECOND_SKU: Final = Sku("WIDGET-002")
THIRD_SKU: Final = Sku("WIDGET-003")
UNREGISTERED_SKU: Final = Sku("WIDGET-GONE")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here: no trio
    # dependency is installed.
    return "asyncio"


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _write(tmp_path: Path, body: str) -> Path:
    """Writes a principals document and hands back its path.

    The document shape is the one
    `tests/unit/access/infrastructure/test_principals_loader.py` records as
    INVENTED; both files must be corrected together if it differs.
    """
    path = tmp_path / "principals.yaml"
    path.write_text(f"principals:\n{body}", encoding="utf-8")
    return path


class _FakeSkuResolver:
    """The consumer-owned SKU-to-product resolver port
    (`design.md` Decision 4), closed over the registered products.

    A SKU no product has is answered with `None` -- the reading
    `design.md` Decision 5 requires ("a grant naming a SKU no product has
    confers nothing"). Accepts either a `Sku` value object or a plain
    string, since no artifact fixes which the port carries.
    """

    def __init__(self, products: dict[str, ProductId]) -> None:
        self._products = products
        self.calls: list[str] = []

    async def __call__(self, sku: Any) -> ProductId | None:
        key = str(getattr(sku, "value", sku))
        self.calls.append(key)
        return self._products.get(key)


def _resolver(**products: ProductId) -> _FakeSkuResolver:
    """Registered products, keyed by SKU string."""
    return _FakeSkuResolver(products)


async def _resolve(directory: Any, resolver: _FakeSkuResolver, identity: str) -> Any:
    """The one place to correct if `resolve_scope`'s call shape differs."""
    return await resolve_scope(directory, resolver, identity=identity)


def _permits(scope: Any, product_id: ProductId) -> bool:
    """Reads the scope's `permits` predicate, which `proposal.md` fixes by
    name. Fails loudly rather than defaulting, so no assertion below can be
    vacuously true.
    """
    assert hasattr(scope, "permits"), (
        "resolution did not answer with an access scope: the value it "
        "returned exposes no `permits` predicate"
    )
    return bool(scope.permits(product_id))


# ---------------------------------------------------------------------------
# Requirement: A known principal's scope derives from its grants
# ---------------------------------------------------------------------------


async def test_an_all_products_principal_resolves_to_the_unrestricted_scope(
    tmp_path: Path,
) -> None:
    """Scenario: An all-products principal resolves to the unrestricted
    scope.

    WHEN the scope is resolved for an identity whose entry carries the
    all-products grant
    THEN the resolved scope permits every product identifier.

    "Every" is exercised with three identifiers, one of them a product the
    resolver has never heard of: an implementation that built the scope by
    enumerating the catalog would permit only the registered two, which is
    the failure `design.md` Decision 2 describes ("the set of all products
    is unknowable to a value object and grows after the scope is built").
    """
    first, second = _new_product_id(), _new_product_id()
    path = _write(
        tmp_path,
        f"""\
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
""",
    )
    resolver = _resolver(
        **{FIRST_SKU.value: first, SECOND_SKU.value: second},
    )

    scope = await _resolve(load_principals(path), resolver, ALL_PRODUCTS_IDENTITY)

    # SPECIFIED: permits every product identifier.
    assert _permits(scope, first) is True
    assert _permits(scope, second) is True
    assert _permits(scope, _new_product_id()) is True


async def test_sku_grants_resolve_to_exactly_those_products(tmp_path: Path) -> None:
    """Scenario: SKU grants resolve to exactly those products.

    WHEN the scope is resolved for an identity granted two SKUs, both
    belonging to registered products
    THEN the resolved scope permits exactly those two products'
    identifiers and no other.

    A third registered product the principal was not granted is what makes
    "and no other" discriminating -- without it, an implementation
    resolving to the unrestricted scope would pass.
    """
    granted_first, granted_second = _new_product_id(), _new_product_id()
    ungranted = _new_product_id()
    path = _write(
        tmp_path,
        f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {FIRST_SKU.value}
      - {SECOND_SKU.value}
""",
    )
    resolver = _resolver(
        **{
            FIRST_SKU.value: granted_first,
            SECOND_SKU.value: granted_second,
            THIRD_SKU.value: ungranted,
        },
    )

    scope = await _resolve(load_principals(path), resolver, SKU_GRANTED_IDENTITY)

    # SPECIFIED: exactly those two products' identifiers ...
    assert _permits(scope, granted_first) is True
    assert _permits(scope, granted_second) is True
    # SPECIFIED: ... and no other.
    assert _permits(scope, ungranted) is False
    assert _permits(scope, _new_product_id()) is False


async def test_an_empty_grant_list_resolves_to_the_empty_scope(
    tmp_path: Path,
) -> None:
    """Scenario: An empty grant list resolves to the empty scope.

    WHEN the scope is resolved for an identity whose entry carries an empty
    SKU grant list
    THEN the resolved scope permits no product identifier.

    A registered product exists, so "permits nothing" is a decision about
    this principal rather than an artefact of an empty catalog.
    """
    registered = _new_product_id()
    path = _write(
        tmp_path,
        f"""\
  - identity: {EMPTY_GRANT_IDENTITY}
    skus: []
""",
    )
    resolver = _resolver(**{FIRST_SKU.value: registered})

    scope = await _resolve(load_principals(path), resolver, EMPTY_GRANT_IDENTITY)

    # SPECIFIED: permits no product identifier.
    assert _permits(scope, registered) is False
    assert _permits(scope, _new_product_id()) is False


# ---------------------------------------------------------------------------
# Requirement: An unknown asker resolves to the empty scope
# ---------------------------------------------------------------------------


async def test_a_stranger_sees_nothing_and_the_resolution_succeeds(
    tmp_path: Path,
) -> None:
    """Scenario: A stranger sees nothing.

    WHEN the scope is resolved for a Slack user identity with no entry in
    the principals directory
    THEN the resolved scope permits no product identifier, and the
    resolution succeeds.

    The directory is not empty -- it declares an all-products principal --
    so the stranger's empty scope is the fail-closed rule at work and not
    the only answer an empty file could give. "The resolution succeeds" is
    asserted by reaching the assertions at all: no exception, and the
    requirement's "never a distinct 'unknown' result" is asserted by the
    answer being a scope that answers `permits`, not `None`.
    """
    registered = _new_product_id()
    path = _write(
        tmp_path,
        f"""\
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
""",
    )
    resolver = _resolver(**{FIRST_SKU.value: registered})

    scope = await _resolve(load_principals(path), resolver, STRANGER_IDENTITY)

    # SPECIFIED: never a distinct "unknown" result -- the same scope type
    # every resolution yields.
    assert scope is not None
    # SPECIFIED: permits no product identifier.
    assert _permits(scope, registered) is False
    assert _permits(scope, _new_product_id()) is False


# ---------------------------------------------------------------------------
# Requirement: A grant naming an unregistered SKU confers nothing without
# failing the resolution
# ---------------------------------------------------------------------------


async def test_a_stale_grant_is_skipped_and_the_rest_stand(tmp_path: Path) -> None:
    """Scenario: A stale grant is skipped, the rest stand.

    WHEN the scope is resolved for an identity granted one SKU belonging to
    a registered product and one SKU no product has
    THEN the resolved scope permits exactly the registered product's
    identifier, and the resolution succeeds.

    The stale grant is listed *first*, so an implementation that stopped at
    the first unresolvable grant -- or raised on it -- cannot pass by
    accident of ordering. Reaching any assertion establishes the "never
    turns into an error for the asker" half.
    """
    registered = _new_product_id()
    other = _new_product_id()
    path = _write(
        tmp_path,
        f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {UNREGISTERED_SKU.value}
      - {FIRST_SKU.value}
""",
    )
    resolver = _resolver(**{FIRST_SKU.value: registered, SECOND_SKU.value: other})

    scope = await _resolve(load_principals(path), resolver, SKU_GRANTED_IDENTITY)

    # SPECIFIED: the remaining grant is honored -- one stale line does not
    # lock the principal out of what they may legitimately see.
    assert _permits(scope, registered) is True
    # SPECIFIED: the stale grant confers nothing, so the scope is not
    # widened to everything as a fallback.
    assert _permits(scope, other) is False
    assert _permits(scope, _new_product_id()) is False


# ---------------------------------------------------------------------------
# Requirement: A principals directory is loaded ... and validated
# (the resolution-side half of its sixth scenario)
# ---------------------------------------------------------------------------


async def test_a_malformed_directory_yields_no_directory_to_resolve_against(
    tmp_path: Path,
) -> None:
    """Scenario: A malformed directory prevents serving rather than failing
    resolutions -- second half only.

    WHEN the process starts against a malformed principals directory
    THEN startup fails with the load error naming the offending entry, and
    no scope resolution ever observes the malformed directory.

    This test asserts the second clause structurally: a malformed file
    produces no directory value at all, so there is nothing for
    `resolve_scope` to be called with and no path by which a malformed
    directory could reach an asker's resolution. Every resolution above
    takes a loaded directory as its argument, which is what makes that
    structural claim binding.

    DELIBERATELY UNTESTED here: the first clause, that *startup* fails. No
    artifact fixes where the eager validation is invoked (`tasks.md` 2.3
    says only "eagerly at startup"; `design.md` Decision 3 says "in the
    spirit of the existing preflight check"), and the directory path is
    repo-owned rather than environment-injectable, so a malformed file
    cannot be fed to a real startup from a test. Recorded in the manifest
    as an unresolved project question for the implementation step.
    """
    path = _write(
        tmp_path,
        f"""\
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
  - identity: {ALL_PRODUCTS_IDENTITY}
    skus:
      - {FIRST_SKU.value}
""",
    )

    directory = None
    with pytest.raises(InvalidPrincipalsError):
        directory = load_principals(path)

    # SPECIFIED: no resolution can observe the malformed directory,
    # because the load hands back nothing to resolve against.
    assert directory is None
