"""The principals directory: who is declared, and what each may see.

Implements the coherence rules of `access-scope`'s requirement *A principals
directory is loaded from a repo-owned definition and validated*. Deterministic
and I/O-free: the YAML file itself is the loader's concern
(`access.infrastructure.driven.principals_loader`), which translates its
values into the ones these constructors expect and merges whatever they
raise into one reported failure — the shape `launch`'s playbook already uses.

Nothing here authenticates. A principal's identity is the opaque string an
adapter has already established; the domain never learns that it came from
Slack.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from commerce_ops.shared.domain.identity import Sku


class InvalidPrincipalsError(ValueError):
    """A principals directory (or an entry within one) fails coherence.

    Carries every fault found in one load attempt, not just the first, so a
    directory does not have to be corrected one error at a time.
    """

    def __init__(self, faults: Sequence[str]) -> None:
        self.faults: tuple[str, ...] = tuple(faults)
        super().__init__("; ".join(self.faults))


@dataclass(frozen=True, slots=True)
class Principal:
    """One declared identity and the single visibility grant it carries.

    `skus is None` means the entry declared no SKU list *at all*, which is a
    fault; an empty tuple means it declared an empty one, which is legitimate
    and resolves to the scope permitting nothing. The two are deliberately
    distinguishable: "missing is not fine" — absent and empty differ.

    `admin` is the optional admin declaration (`add-playbook-admin-ui`),
    orthogonal to the visibility grant: grants say what a principal may
    *see*, the declaration says it may hold the admin surface's *write*
    authority. No grant of any shape confers it — an admin who may see
    nothing is still an admin, and an all-products principal without the
    declaration is not.
    """

    identity: str
    all_products: bool
    skus: tuple[Sku, ...] | None
    admin: bool = False

    def __post_init__(self) -> None:
        faults: list[str] = []

        if not self.identity:
            faults.append("a principal entry declares an empty identity")
        elif self.identity != self.identity.strip():
            faults.append(
                "a principal identity must not carry leading or trailing "
                f"whitespace: {self.identity!r}"
            )

        if self.all_products and self.skus is not None:
            faults.append(
                f"principal '{self.identity}' declares both an all-products "
                "grant and a SKU grant list, and may declare only one"
            )
        elif not self.all_products and self.skus is None:
            faults.append(
                f"principal '{self.identity}' declares neither an all-products "
                "grant nor a SKU grant list, and must declare one"
            )

        if faults:
            raise InvalidPrincipalsError(faults)

    @property
    def granted_skus(self) -> tuple[Sku, ...]:
        """The SKUs granted, which is none when the grant is all-products."""
        return self.skus or ()


@dataclass(frozen=True, slots=True)
class PrincipalsDirectory:
    """Every declared principal, each identity appearing at most once."""

    principals: tuple[Principal, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        duplicated: list[str] = []
        for principal in self.principals:
            if principal.identity in seen and principal.identity not in duplicated:
                duplicated.append(principal.identity)
            seen.add(principal.identity)

        if duplicated:
            # A later entry silently winning is exactly what this forbids:
            # two entries granting different visibility to one identity have
            # no defensible resolution, so the directory is refused instead.
            raise InvalidPrincipalsError(
                [
                    f"principal '{identity}' is declared more than once"
                    for identity in duplicated
                ]
            )

    def entry_for(self, identity: str) -> Principal | None:
        """The entry declaring `identity`, or `None` for a stranger."""
        for principal in self.principals:
            if principal.identity == identity:
                return principal
        return None
