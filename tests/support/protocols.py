"""The shapes the shared fakes are checked against.

**Populated for the value doubles, still empty for the stateful fakes.**
`share-the-value-doubles` added `MemberShape` and `CatalogProductShape` below,
each with the `_conforms` assignment that makes it bite. The doubles with
behaviour -- `FakeMembers`, `FakeStepStore` and their neighbours -- are deferred
to `share-the-stateful-fakes`, and their protocols arrive with them. The rules
below bind those too, and are recorded here rather than in that change so the
first stateful fake is written against them rather than after them.


A `Protocol` declared beside a fake checks nothing on its own: `mypy` compares
a class to a protocol only where a value is assigned to a protocol-annotated
target. So every fake in this package carries, beside it::

    _conforms: SomeProtocol = TheFake()

That assignment -- not this module's existence -- is what makes a double which
has stopped matching its subject a type error rather than something a reader
has to notice. `uv run mypy .` already runs strict over `tests/`, so it costs
one line per fake and nothing at runtime.

**Completeness carries the same-value invariant with it.** Production reads
several of these shapes by probing attribute names in order --
`gate_progression_job._awaiting_gate` returns the first of
`("awaiting_gate", "gate_id", "current_gate")` that is a non-empty string, and
`clickup_sync._members` tries `list_members()`, then a callable, then a plain
iterable. Modelling every name a probe reads is only safe if the added
spellings agree with the one they displace; otherwise completeness silently
redirects the probe to an earlier branch and the test exercises a path it did
not before. So:

    Where a fake adds a spelling a production probe reads earlier in its
    branch order than the spelling the local variants populated, the added
    spelling carries the same value as the one it displaces. An added
    attribute the probe reads as a guard or as a sequence defaults to the
    value the fall-through produced.

These protocols are **temporary**. `unify-launch-adapter-dependencies` defines
the boundary collaborators as protocols in `src/`, and when it lands these are
replaced by imports of the real ones -- two definitions of one boundary is the
disagreement this change exists to end. They live here rather than in `src/`
only because that change has not landed yet.

Each protocol is added by the task that adds its double, never up front: the
shape comes from reading the local variants being replaced, so authoring one
before that reading would be guessing at it.

A protocol here declares what production *reads*, and declares it as a
`@property` rather than as a variable. `mypy` treats a protocol variable as
settable, so a read-only property on a double does not satisfy `name: str` --
and the derived spellings these doubles expose (`Member.identifier`,
`FakeTask.custom_field_values`) are exactly read-only properties.
"""

from __future__ import annotations

from typing import Protocol

from commerce_ops.shared.domain.identity import Sku
from tests.support.values import CatalogProduct, Member, MemberValue


class MemberShape(Protocol):
    """What production reads off a member, and nothing more.

    `identifier` is declared as a **property, not a variable**. `mypy` treats a
    protocol variable as settable, so `identifier: str` would make the
    `_conforms` assignments below type errors -- the read-only property on the
    doubles does not satisfy a settable member. The property form is also the
    truthful one: the six shape probes in `src/` read this name and no
    production site assigns to it.
    """

    @property
    def identifier(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def active(self) -> bool: ...


_member_conforms: MemberShape = Member("prs_01HQ8Z6M4A", "Alice Admin")
_member_value_conforms: MemberShape = MemberValue(
    id="prs_01HQ8Z6M4A", display_name="Alice Admin", slack_identity="U-ALICE"
)


class CatalogProductShape(Protocol):
    """What a launch reads off a catalog product."""

    @property
    def name(self) -> str: ...

    @property
    def sku(self) -> Sku: ...


_catalog_product_conforms: CatalogProductShape = CatalogProduct()
