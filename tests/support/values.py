"""The value doubles the suite arranges around.

A type here stands in for a production collaborator and **is not one**. It never
imports a value from production and never validates: `access.domain.members`'s
own `Member` is `@dataclass(frozen=True, slots=True)` with a `__post_init__`
that rejects an empty `slack_identity`, and 42 of the 52 local member doubles
this module replaces never supply one. Using the real type would edit every
construction site in the suite, which is a different change --
`unify-launch-adapter-dependencies` owns it.

**Every type here declares one form, and the form is part of the contract.** A
local declaration migrates onto a shared type only where the two agree on
dataclass-ness, `frozen`, `eq` and any `__repr__` the file relies on -- field
equality says nothing about those, and this suite disagrees on all of them for
real reasons. That is why `Member` and `MemberValue` are two types rather than
one bent across two equality semantics.

**The field spellings are the locals', and the production spellings arrive as
properties.** Production reads a member's identifier through a shape probe at
six sites, first branch `identifier`; all 52 locals spell that field `id`. So
`id` stays the field -- ten files pass it as a keyword and a read-only property
cannot receive one -- and `identifier` is derived from it. The two carry the
same string by construction rather than by inspection, which is what lets
`unify-launch-adapter-dependencies` delete the probe's remaining branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from commerce_ops.launch.domain.launch_playbook import StepDefinition
from commerce_ops.shared.domain.identity import Sku
from tests.support.fixtures import PRODUCT_NAME, PRODUCT_SKU

#: What a member double's ClickUp identity is, absent a reason to differ.
CLICKUP_USER_ID = "clickup-1"


class Member:
    """One known human, as the suite's plain-class doubles model them.

    A plain class, so equality is identity and instances are hashable --
    matching the 42 local declarations this replaces. `MemberValue` is the
    same subject in `@dataclass` form, for the ten that compare by field.

    `slack_identity` and `admin` are modelled here and are declared by none of
    the 42. Both are supersets rather than displacements: no `getattr` probe in
    `src/` reads either, `admin` being read only as a direct attribute on
    production's own type. `slack_identity` defaults to `None` because that is
    what its absence produced at the three sites that do read it by shape --
    `gate_decisions.py:94`, `automated_decisions.py:125` and
    `thread_establishment.py:224` -- and a truthy default would start matching
    the two `==` comparisons among them.
    """

    def __init__(
        self,
        member_id: str,
        display_name: str,
        *,
        slack_identity: str | None = None,
        clickup_user_id: str | None = CLICKUP_USER_ID,
        admin: bool = False,
        active: bool = True,
    ) -> None:
        self.id = member_id
        self.display_name = display_name
        self.slack_identity = slack_identity
        self.clickup_user_id = clickup_user_id
        self.admin = admin
        self.active = active

    @property
    def identifier(self) -> str:
        """The spelling every production probe reads first.

        The same string as `id`, because it *is* `id`. Production cannot name
        `access`'s type from `launch` -- `.importlinter` forbids it -- so it
        reads a shape instead, and every double modelling only `id` is why that
        probe still carries an `id` branch to fall through to.
        """
        return self.id


@dataclass
class MemberValue:
    """One known human, for the files that compare members by field.

    `@dataclass`, so equality is structural and instances are unhashable --
    matching the ten local declarations this replaces, which are exactly the
    ten that construct with `id=` as a keyword.

    `clickup_user_id` defaults to `None` here and to `CLICKUP_USER_ID` on
    `Member`, because the two populations genuinely disagree and the
    disagreement falls along the same line as the form split. Neither type has
    to compromise, which is the second thing two types buy.
    """

    id: str
    display_name: str
    slack_identity: str | None
    active: bool = True
    clickup_user_id: str | None = None
    admin: bool = False

    @property
    def identifier(self) -> str:
        """As `Member.identifier`, and for the same reason."""
        return self.id


@dataclass(frozen=True)
class CatalogProduct:
    """The catalog product a launch is about, as far as `launch` reads it.

    `frozen=True`, matching the 31 frozen declarations this replaces -- so
    equality is structural and instances are hashable, which
    `test_step_handler_contract.py` relies on. The seven plain-class
    declarations keep their own: two say in their docstrings that the plain form
    is deliberate, because `catalog.domain.product.Product` is plain and `!r`
    must leak `<... object at 0x...>` exactly as it would in production. A
    shared dataclass renders fields instead, so form is part of the contract
    rather than an implementation detail.

    The defaults are `fixtures`' values because seven declarations already
    default to exactly those -- six by importing the names, one by spelling the
    literals. `fixtures.py`'s own rule is that migration matches on the value,
    never on the identifier.

    `stage` is **not** modelled. Two declarations carry it and only `briefing`
    reads it, directly rather than by shape; adding it would hand 31
    launch-facing doubles an attribute whose absence previously raised, to suit
    two tests in another bounded context. Those two keep their own declaration.
    """

    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


class Record:
    """A stored playbook step: its definition, its position, its provenance.

    A plain class, which all 30 declarations are. It holds a production
    `StepDefinition` -- a type, never a value, which is the line
    `AGENTS.md` draws -- so Decision 2's comparison over it is shallow: two
    references to one `StepDefinition` are equal by identity, and recursing
    would compare production against itself.

    **`display_order` defaults to `10`, and the measurement decided it.** 16 of
    the 30 declare exactly that default and their calls exercise it, so it is
    inside the compared intersection and anything else fails their proof
    loudly. 13 more require the argument and are indifferent. The one
    declaration carrying no `display_order` at all --
    `test_launch_report_step_facts.py` -- keeps its own: production reads the
    field at four sites as `getattr(row, "display_order", 0)`, so its absence
    yields `0` there, and a shared `10` would move an exercised read *silently*,
    the field being outside the intersection. Lowering the shared default to `0`
    to recover that one file would instead break 16 loudly.

    The eight provenance fields default to `None`, which is what every
    declaration carrying them uses. `src/` reads them only as direct attributes
    on ORM rows, never off a double.
    """

    def __init__(self, definition: StepDefinition, display_order: int = 10) -> None:
        self.definition = definition
        self.display_order = display_order
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None
