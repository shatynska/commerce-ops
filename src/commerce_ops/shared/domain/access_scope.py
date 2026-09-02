"""The shared `AccessScope` vocabulary: which products a caller may see.

Implements `shared-vocabulary`'s access-scope requirement. Vocabulary only:
a scope carries visibility and answers `permits`, but nothing here derives a
scope from a member or a grant — that is the `access` context's work, the
way `LifecycleStage` carries `is_temporary` while its transition rules
belong to `catalog`.

Four modules speak this value: `access` derives it, `catalog` and `launch`
filter their reads by it, and `omni_agent` forwards an asker's scope
without privileges of its own. That is why it lives in the kernel rather
than in `access`.

Unrestricted is a distinct construction, never a set enumerating every
product: the set of all products is unknowable to a value object and grows
after a scope is built. `permitted is None` therefore reads as "no
restriction recorded", not "nothing permitted" — the scope permitting
nothing is the *empty set*, which `nothing()` builds and which is the
fail-closed default every unresolved asker lands on.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from commerce_ops.shared.domain.identity import ProductId


@dataclass(frozen=True, slots=True)
class AccessScope:
    """A caller's product visibility: unrestricted, or an explicit set."""

    permitted: frozenset[ProductId] | None

    @classmethod
    def unrestricted(cls) -> AccessScope:
        """Sees every product, including ones registered after this call."""
        return cls(permitted=None)

    @classmethod
    def permitting(cls, product_ids: Iterable[ProductId]) -> AccessScope:
        """Sees exactly `product_ids` and nothing else."""
        return cls(permitted=frozenset(product_ids))

    @classmethod
    def nothing(cls) -> AccessScope:
        """Sees nothing — what an unresolvable asker gets, by design."""
        return cls(permitted=frozenset())

    def permits(self, product_id: ProductId) -> bool:
        return self.permitted is None or product_id in self.permitted
