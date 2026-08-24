"""Loading and validating the repo-owned principals directory
(`access-scope`).

Derived strictly from the ADDED requirement *A principals directory is
loaded from a repo-owned definition and validated* in
`openspec/changes/introduce-access-scope/specs/access-scope/spec.md`.

Covered here: the five load-time scenarios (a well-formed directory loads;
duplicate identity, both grant forms, neither grant form, and a malformed
SKU grant value are each rejected with an error naming the offending
entry), plus the empty/whitespace-padded identity the requirement statement
names without giving it a scenario.

The sixth scenario of that requirement -- *A malformed directory prevents
serving rather than failing resolutions* -- is accounted for across this
file and
`tests/unit/access/application/test_resolve_scope.py`; see the manifest,
which records the half of it no test here asserts and why.

## Why the loader boundary

Every one of these outcomes is stated about *the directory file*: a
duplicate entry, an entry declaring both grant forms, a SKU value carrying
whitespace. A domain model keyed by identity cannot even hold a duplicate,
and a validated value object cannot hold a padded SKU -- the file is the
only place those faults exist, so the loader over a real file is the
smallest unit that can observe them (`ai-toolkit:testing`'s level rule).
This is the same reasoning
`tests/unit/launch/infrastructure/test_playbook_loader.py` records for the
playbook's malformed-step scenario, and this file follows that file's
shape.

## The interface under test does not exist yet, and its shape is INVENTED

The `access` module is created by this change (`tasks.md` 2.1-2.3), so
every test here is expected to fail on an absent target
(`ModuleNotFoundError`). That failure establishes only absence.

Fixed by the artifacts, not invented: the directory is repo-owned YAML,
loaded and validated by an `access` infrastructure loader following the
playbook-loader precedent; it maps a Slack user identity to either an
all-products grant or a (possibly empty) list of SKU grants; the shipped
default file declares an empty principals list (`design.md` Decision 3,
`tasks.md` 2.3).

INVENTED, and recorded as unresolved project questions in the manifest:

- `commerce_ops.access.infrastructure.driven.principals_loader` exporting
  `load_principals(path)` and `load_shipped_principals()` -- the two names
  `launch`'s `playbook_loader` already uses, with the same split.
- `InvalidPrincipalsError` in `commerce_ops.access.domain.principals` as
  the single rejection signal, mirroring `InvalidPlaybookError`.
- The YAML document shape (`_directory` below): a `principals:` list of
  entries carrying `identity:` plus either `all_products: true` or
  `skus: [...]`. A list rather than a mapping because the spec requires a
  *duplicate identity* to be rejected, which a YAML mapping could not
  express.
- How a loaded directory reports that it knows an identity (`_knows`).

Correcting the import, the document shape, or `_knows` is a fixture
correction (failure state 3 in `ai-toolkit:testing`). What must survive
unweakened is what each test asserts: which directories load, which are
refused, and that the refusal names the offending entry rather than
silently trimming, skipping, or overwriting it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pytest

from commerce_ops.access.domain.principals import InvalidPrincipalsError
from commerce_ops.access.infrastructure.driven.principals_loader import (
    load_principals,
    load_shipped_principals,
)

# DERIVED sample values: no artifact fixes example identities or SKUs.
# Slack user IDs are of this shape; the SKUs match the `WIDGET-00n` form
# the catalog tests already use.
ALL_PRODUCTS_IDENTITY: Final = "U01ALICE"
SKU_GRANTED_IDENTITY: Final = "U02BOB"
FIRST_SKU: Final = "WIDGET-001"
SECOND_SKU: Final = "WIDGET-002"


def _directory(body: str) -> str:
    return f"principals:\n{body}"


def _write(tmp_path: Path, document: str) -> Path:
    path = tmp_path / "principals.yaml"
    path.write_text(document, encoding="utf-8")
    return path


def _knows(directory: Any, identity: str) -> bool:
    """Whether a loaded directory declares `identity`.

    Tries the spellings no artifact fixes, and fails loudly rather than
    answering False when none is present -- an accommodating default would
    make `test_a_well_formed_directory_loads` assert nothing.
    """
    for name in ("entry_for", "get", "principal_for", "declares"):
        accessor = getattr(directory, name, None)
        if accessor is not None and callable(accessor):
            entry = accessor(identity)
            return entry is not None and entry is not False
    entries = getattr(directory, "principals", None)
    if entries is not None:
        if isinstance(entries, dict):
            return identity in entries
        return any(getattr(entry, "identity", None) == identity for entry in entries)
    try:
        return identity in directory
    except TypeError:
        pytest.fail(
            "a loaded principals directory reports membership through none "
            "of `entry_for`/`get`/`principal_for`/`declares`, a `principals` "
            "collection, or `in` (see the module docstring's INVENTED shapes)"
        )


# ---------------------------------------------------------------------------
# Scenario: A well-formed directory loads
# ---------------------------------------------------------------------------


def test_a_well_formed_directory_loads(tmp_path: Path) -> None:
    """Scenario: A well-formed directory loads.

    WHEN the principals directory declares one identity with an
    all-products grant and another with a list of SKU grants
    THEN the directory loads and both principals are known.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {FIRST_SKU}
      - {SECOND_SKU}
"""
        ),
    )

    directory = load_principals(path)

    # SPECIFIED: it loads (reaching here at all) and *both* principals are
    # known -- an implementation that kept only the last entry fails.
    assert _knows(directory, ALL_PRODUCTS_IDENTITY) is True
    assert _knows(directory, SKU_GRANTED_IDENTITY) is True
    # DERIVED, so that `_knows` is discriminating rather than constant: an
    # identity the file never declared is not known.
    assert _knows(directory, "U99STRANGER") is False


def test_an_empty_grant_list_is_a_well_formed_entry(tmp_path: Path) -> None:
    """SPECIFIED (requirement statement): the SKU grant list "MAY be
    empty".

    Recorded separately from the rejection tests below because an
    implementation reading "an entry declaring neither grant form is
    rejected" too broadly would refuse this legitimate entry -- and the
    *An empty grant list resolves to the empty scope* scenario in
    `test_resolve_scope.py` presupposes such an entry can exist at all.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus: []
"""
        ),
    )

    directory = load_principals(path)

    assert _knows(directory, SKU_GRANTED_IDENTITY) is True


# ---------------------------------------------------------------------------
# Scenario: A duplicate identity is rejected at load
# ---------------------------------------------------------------------------


def test_a_duplicate_identity_is_rejected_naming_it(tmp_path: Path) -> None:
    """Scenario: A duplicate identity is rejected at load.

    WHEN the principals directory declares the same identity twice
    THEN the load fails with an error naming that identity.

    The two entries carry *different* grants, so an implementation that
    silently let the later entry win would produce a usable directory --
    exactly the quiet overwrite this scenario exists to forbid.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {ALL_PRODUCTS_IDENTITY}
    skus:
      - {FIRST_SKU}
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
"""
        ),
    )

    # SPECIFIED: the load fails. Scoped to the load call alone.
    with pytest.raises(InvalidPrincipalsError) as excinfo:
        load_principals(path)

    # SPECIFIED: the error names that identity.
    assert ALL_PRODUCTS_IDENTITY in str(excinfo.value)


# ---------------------------------------------------------------------------
# Scenario: An entry declaring both grant forms is rejected
# ---------------------------------------------------------------------------


def test_an_entry_declaring_both_grant_forms_is_rejected(tmp_path: Path) -> None:
    """Scenario: An entry declaring both grant forms is rejected.

    WHEN a principal entry declares an all-products grant and also lists
    SKU grants
    THEN the load fails with an error naming that entry.

    A second, well-formed entry stands beside the faulty one so that the
    error naming the offending entry is a real discrimination rather than
    the only identity in the file.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {FIRST_SKU}
  - identity: {ALL_PRODUCTS_IDENTITY}
    all_products: true
    skus:
      - {SECOND_SKU}
"""
        ),
    )

    with pytest.raises(InvalidPrincipalsError) as excinfo:
        load_principals(path)

    # SPECIFIED: the error names that entry.
    assert ALL_PRODUCTS_IDENTITY in str(excinfo.value)


# ---------------------------------------------------------------------------
# Scenario: An entry declaring no grant form is rejected
# ---------------------------------------------------------------------------


def test_an_entry_declaring_no_grant_form_is_rejected(tmp_path: Path) -> None:
    """Scenario: An entry declaring no grant form is rejected.

    WHEN a principal entry declares neither an all-products grant nor a SKU
    grant list
    THEN the load fails with an error naming that entry.

    Note the contrast with `test_an_empty_grant_list_is_a_well_formed_entry`
    above: *no* `skus` key at all is the fault; `skus: []` is not.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {FIRST_SKU}
  - identity: {ALL_PRODUCTS_IDENTITY}
"""
        ),
    )

    with pytest.raises(InvalidPrincipalsError) as excinfo:
        load_principals(path)

    # SPECIFIED: the error names that entry.
    assert ALL_PRODUCTS_IDENTITY in str(excinfo.value)


# ---------------------------------------------------------------------------
# Scenario: A malformed SKU grant value is rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("grant_line", "expected_in_message"),
    [
        pytest.param('      - ""', SKU_GRANTED_IDENTITY, id="empty"),
        pytest.param(f'      - " {FIRST_SKU}"', FIRST_SKU, id="leading-space"),
        pytest.param(f'      - "{FIRST_SKU} "', FIRST_SKU, id="trailing-space"),
    ],
)
def test_a_malformed_sku_grant_value_is_rejected(
    tmp_path: Path, grant_line: str, expected_in_message: str
) -> None:
    """Scenario: A malformed SKU grant value is rejected.

    WHEN a principal entry lists a SKU grant that is empty or padded with
    whitespace
    THEN the load fails rather than silently trimming or skipping it.

    A second, well-formed SKU sits beside the faulty one in each case, so a
    loader that skipped the bad value would still produce a usable
    directory -- "rather than silently ... skipping it" is what the
    rejection has to rule out. The quoted YAML scalars are deliberate:
    unquoted YAML would strip the padding before the loader ever saw it,
    and the fault under test is the loader's, not the file format's.

    The empty case asserts the identity is named rather than the value,
    since an empty string has no content to appear in a message -- the same
    reading `test_identity_value_objects.py` records for its empty-value
    scenario.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {SKU_GRANTED_IDENTITY}
    skus:
      - {SECOND_SKU}
{grant_line}
"""
        ),
    )

    # SPECIFIED: the load fails (a silent trim or skip would not raise).
    with pytest.raises(InvalidPrincipalsError) as excinfo:
        load_principals(path)

    # SPECIFIED (requirement statement): the error names the offending
    # entry.
    assert expected_in_message in str(excinfo.value)


# ---------------------------------------------------------------------------
# SPECIFIED (requirement statement, no scenario of its own): "an empty or
# whitespace-padded identity ... SHALL fail the load with an error naming
# the offending entry".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "identity_value",
    [
        pytest.param('""', id="empty"),
        pytest.param(f'" {ALL_PRODUCTS_IDENTITY}"', id="leading-space"),
        pytest.param(f'"{ALL_PRODUCTS_IDENTITY} "', id="trailing-space"),
    ],
)
def test_an_empty_or_padded_identity_is_rejected(
    tmp_path: Path, identity_value: str
) -> None:
    """SPECIFIED by the requirement statement. Without this, an identity
    read straight out of the file and trimmed on the way in would let two
    entries that look distinct resolve to the same principal.
    """
    path = _write(
        tmp_path,
        _directory(
            f"""\
  - identity: {identity_value}
    all_products: true
"""
        ),
    )

    with pytest.raises(InvalidPrincipalsError):
        load_principals(path)


# ---------------------------------------------------------------------------
# The shipped default file
# ---------------------------------------------------------------------------


def test_the_shipped_directory_loads_and_grants_nothing_to_anyone() -> None:
    """DERIVED from `tasks.md` 2.3 and `design.md` Decision 3 -- "the
    shipped default file declares an empty principals list with a commented
    example entry ... no real grant ships unreviewed" -- which no scenario
    states. Classified derived rather than specified for that reason, and
    recorded as such in the manifest.

    It is worth a test because the shipped file is the one the deploy
    actually validates: a file that does not parse would fail every
    startup, and a file carrying a real grant would ship unreviewed access.
    """
    directory = load_shipped_principals()

    assert _knows(directory, ALL_PRODUCTS_IDENTITY) is False
    assert _knows(directory, "U99ANYONE") is False
