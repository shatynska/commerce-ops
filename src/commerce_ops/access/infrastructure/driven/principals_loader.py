"""Driven adapter: reads a principals YAML file into a `PrincipalsDirectory`.

Translates, never re-implements: every coherence rule lives on `Principal`
and `PrincipalsDirectory` themselves, and the SKU rules live on the shared
`Sku` vocabulary. This module turns the file's values into the ones those
constructors expect, and merges every fault it encounters into a single
reported failure, so a directory does not have to be corrected one load
attempt at a time.

Unlike the playbook, which loads lazily on first use, this file is validated
eagerly at startup (`commerce_ops.preflight`): a malformed directory
discovered lazily would turn every asker's resolution into an error, and
resolution must never error toward the asker.

See the document-shape comment at the top of `principals.yaml`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from commerce_ops.access.domain.principals import (
    InvalidPrincipalsError,
    Principal,
    PrincipalsDirectory,
)
from commerce_ops.shared.domain.identity import Sku

_SHIPPED_PACKAGE = "commerce_ops.access.infrastructure.driven"
_SHIPPED_FILENAME = "principals.yaml"


def load_principals(path: Path) -> PrincipalsDirectory:
    """Load and validate a principals directory from a YAML file at `path`.

    Raises `InvalidPrincipalsError`, naming every fault found, if the file
    does not parse into a coherent directory.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    faults: list[str] = []
    principals: list[Principal] = []
    for raw in document.get("principals") or []:
        try:
            principals.append(_build_principal(raw))
        except InvalidPrincipalsError as exc:
            faults.extend(exc.faults)
        except ValueError as exc:
            # A fault the shared vocabulary raised — a malformed SKU grant.
            # Named against its entry, since the value alone would not say
            # which principal has to be corrected.
            identity = raw.get("identity", "<unknown>")
            faults.append(f"principal '{identity}': {exc}")

    try:
        directory = PrincipalsDirectory(tuple(principals))
    except InvalidPrincipalsError as exc:
        faults.extend(exc.faults)
        raise InvalidPrincipalsError(faults) from None

    if faults:
        raise InvalidPrincipalsError(faults)
    return directory


def load_shipped_principals() -> PrincipalsDirectory:
    """Load the principals directory this project ships, from package data.

    Uses `importlib.resources` rather than a hardcoded source-tree path, so
    this works the same way from a source checkout and from an installed
    build.
    """
    with resources.as_file(
        resources.files(_SHIPPED_PACKAGE) / _SHIPPED_FILENAME
    ) as path:
        return load_principals(path)


def _build_principal(raw: Mapping[str, Any]) -> Principal:
    identity = raw.get("identity")
    return Principal(
        identity="" if identity is None else str(identity),
        all_products=bool(raw.get("all_products", False)),
        # Absent and empty differ: a missing key is a fault the domain
        # rejects, an empty list is a legitimate grant of nothing.
        skus=_build_skus(raw.get("skus")),
    )


def _build_skus(raw: Sequence[Any] | None) -> tuple[Sku, ...] | None:
    if raw is None:
        return None
    # `Sku` rejects an empty or padded value, which is where the malformed
    # SKU-grant rule is enforced — never re-implemented here, and never
    # trimmed or skipped on the way in.
    return tuple(Sku("" if value is None else str(value)) for value in raw)
