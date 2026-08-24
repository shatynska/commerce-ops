"""Resolving admin capability from the principals directory
(`access-scope`, ADDED *A principal can be declared admin-capable*).

Derived strictly from the delta spec:
`openspec/changes/add-playbook-admin-ui/specs/access-scope/spec.md`
All four scenarios of the one ADDED requirement.

Directories are built through `load_principals`, the pattern
`test_resolve_scope.py` in this directory records: the YAML file is the
only shape any artifact describes for a directory, so building through
the loader keeps one invented shape in play. The malformed-declaration
scenario is stated about the file itself, so the loader is its smallest
observing unit — the reasoning `test_principals_loader.py` records.

## What is fixed, and what is INVENTED

Fixed by the artifacts, not invented: an optional per-entry admin
declaration, orthogonal to visibility grants; entries without it mean
exactly what they mean today; malformed values fail the load naming the
entry; resolution is fail-closed for unknown identities and undeclared
entries (`tasks.md` 2.1, `design.md` Decision 4).

INVENTED, recorded in the manifest as unresolved project questions:

- The YAML spelling of the declaration: `admin: true` on an entry.
  A non-boolean value (`admin: "yes"`, quoted string) is the malformed
  case — YAML would hand a loader a string where the declaration is a
  boolean, the closest analogue of the loader's existing padded-SKU
  faults. Correction point: the `_entry` bodies below.
- `resolve_admin_capability(directory, identity=...) -> bool`, exported
  from `commerce_ops.access.application`, sync — unlike `resolve_scope`
  it consults no async port, only the loaded directory. Correction
  point: `_resolves_admin` below.

## Expected first-run state

`commerce_ops.access.application` exports no `resolve_admin_capability`
and the loader knows no admin field, so every test fails at import or on
the loader's treatment of the unknown key — the absent-target state.
NOTE for the implementation step: if the current loader silently
*ignores* unknown entry keys, the two resolution tests asserting
`False` could pass vacuously before the capability exists; the
declared-entry test (`True`) is the discriminating one and cannot.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.access.application import resolve_admin_capability
from commerce_ops.access.domain.principals import InvalidPrincipalsError
from commerce_ops.access.infrastructure.driven.principals_loader import (
    load_principals,
)

# DERIVED sample values; no artifact fixes example identities.
ADMIN_IDENTITY: Final = "U01ALICE"
VISIBILITY_ONLY_IDENTITY: Final = "U02BOB"
STRANGER_IDENTITY: Final = "U99STRANGER"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "principals.yaml"
    path.write_text(f"principals:\n{body}", encoding="utf-8")
    return path


def _resolves_admin(directory: Any, identity: str) -> bool:
    """The single correction point for the resolution call shape."""
    answer = resolve_admin_capability(directory, identity=identity)
    assert isinstance(answer, bool), (
        "admin-capability resolution answered something other than a "
        f"boolean: {answer!r} — fail-closed resolution must answer the "
        "question, not defer it"
    )
    return answer


# ---------------------------------------------------------------------------
# Scenario: A declared entry resolves admin-capable
# ---------------------------------------------------------------------------


def test_a_declared_entry_resolves_admin_capable(tmp_path: Path) -> None:
    """Scenario: A declared entry resolves admin-capable.

    WHEN admin capability is resolved for an identity whose entry
    carries the admin declaration
    THEN the identity resolves as admin-capable.

    The entry's visibility grant is deliberately the *empty* SKU list —
    the spec'd case `design.md` Decision 4 leans on: admin capability is
    orthogonal to what the principal may see, so an admin who can see
    nothing is still an admin.
    """
    path = _write(
        tmp_path,
        f"""\
  - identity: {ADMIN_IDENTITY}
    skus: []
    admin: true
""",
    )

    directory = load_principals(path)

    # SPECIFIED: the declaration confers the capability.
    assert _resolves_admin(directory, ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: Visibility grants confer nothing
# ---------------------------------------------------------------------------


def test_visibility_grants_confer_nothing(tmp_path: Path) -> None:
    """Scenario: Visibility grants confer nothing.

    WHEN admin capability is resolved for an identity whose entry
    carries the all-products grant but no admin declaration
    THEN the identity resolves as not admin-capable.

    The all-products grant is the *widest* visibility grant, so this is
    the strongest instance of "no visibility grant of any shape SHALL by
    itself confer admin capability". A declared admin stands beside the
    entry, so `False` here is a per-entry decision rather than a
    directory-wide constant.
    """
    path = _write(
        tmp_path,
        f"""\
  - identity: {VISIBILITY_ONLY_IDENTITY}
    all_products: true
  - identity: {ADMIN_IDENTITY}
    skus: []
    admin: true
""",
    )

    directory = load_principals(path)

    # SPECIFIED: the widest visibility grant confers no admin capability.
    assert _resolves_admin(directory, VISIBILITY_ONLY_IDENTITY) is False
    # DERIVED discrimination guard: the same resolution answers True for
    # the declared entry, so False above is not a constant answer.
    assert _resolves_admin(directory, ADMIN_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: An unknown identity fails closed
# ---------------------------------------------------------------------------


def test_an_unknown_identity_fails_closed(tmp_path: Path) -> None:
    """Scenario: An unknown identity fails closed.

    WHEN admin capability is resolved for an identity the directory does
    not know
    THEN the identity resolves as not admin-capable.

    The directory is not empty — it declares an admin — so the
    stranger's refusal is the fail-closed rule at work. Resolving (to
    False) rather than raising is itself asserted by reaching the
    assertion: fail-closed, not fail-loud, matching the directory's
    existing unknown-asker behavior.
    """
    path = _write(
        tmp_path,
        f"""\
  - identity: {ADMIN_IDENTITY}
    skus: []
    admin: true
""",
    )

    directory = load_principals(path)

    # SPECIFIED: an identity the directory does not know is not
    # admin-capable.
    assert _resolves_admin(directory, STRANGER_IDENTITY) is False


# ---------------------------------------------------------------------------
# Scenario: A malformed admin declaration is rejected at load
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "admin_value",
    [
        pytest.param('"yes"', id="string-not-boolean"),
        pytest.param('"true"', id="quoted-true"),
        pytest.param("1", id="number"),
    ],
)
def test_a_malformed_admin_declaration_is_rejected_at_load(
    tmp_path: Path, admin_value: str
) -> None:
    """Scenario: A malformed admin declaration is rejected at load.

    WHEN the principals directory declares an entry whose admin
    declaration carries a malformed value
    THEN the load fails with an error naming that entry.

    A well-formed entry stands beside the faulty one, so naming the
    offending entry is a real discrimination — the convention every
    loader rejection test in `test_principals_loader.py` follows. The
    malformed values are what YAML would actually deliver for a
    mistyped declaration: strings and numbers where the declaration is
    a boolean. DERIVED, recorded: the delta fixes "malformed value"
    without enumerating the malformed shapes; these three follow from
    the invented boolean spelling.
    """
    path = _write(
        tmp_path,
        f"""\
  - identity: {ADMIN_IDENTITY}
    skus: []
    admin: true
  - identity: {VISIBILITY_ONLY_IDENTITY}
    skus: []
    admin: {admin_value}
""",
    )

    # SPECIFIED: the load fails, like every other directory fault.
    with pytest.raises(InvalidPrincipalsError) as excinfo:
        load_principals(path)

    # SPECIFIED: the error names the offending entry.
    assert VISIBILITY_ONLY_IDENTITY in str(excinfo.value)
