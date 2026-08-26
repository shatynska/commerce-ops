"""What the team is asked to look at, and how findings collapse into it.

Implements the `briefing` capability's *Attention items are derived from
every active launch* and *Findings collapse by cause and the causal item
leads*.

Deliberately stage-generic: nothing here knows what a launch is. A
`Finding` is "something worth reporting about a product, attributed to a
cause"; the cause vocabulary and its ranking arrive as *data* (a
`CauseOrder`), so monitoring's eight-level order plugs into the same
collapse in a later slice without this module changing. The order is
data; the collapse is code.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.severity import Severity


class BriefingError(Exception):
    """A briefing rule was violated."""


class LaunchReportsUnavailableError(Exception):
    """The source the briefing reads its launch items from cannot supply
    reports at all — which is a different thing from supplying none.

    Supplying no reports is a clean day and posts nothing. Being unable to
    supply any is a source that is not yet able to answer, and reporting it
    as a clean day would let a deployment still being set up read as an
    all-clear, every day, for as long as it lasts.

    It is also not a failure to read data: retrying cannot resolve it, so
    it is neither retried nor recorded as a failed run, which is what
    separates it from an assembly failure.

    `identifiers` says *why*, and briefing treats it as opaque. Whatever
    satisfies the port is responsible for translating its own module's
    condition into this one — today that is a launch playbook that cannot
    hold a launch, and the identifiers are the gates holding no active
    blocking step. Briefing never learns what a gate is, which is what
    keeps it from naming another module's types.
    """

    def __init__(self, *, identifiers: Sequence[str] = ()) -> None:
        self.identifiers: tuple[str, ...] = tuple(identifiers)
        super().__init__(
            "the launch source cannot supply reports"
            + (f": {', '.join(self.identifiers)}" if self.identifiers else "")
        )


@dataclass(frozen=True, slots=True, repr=False)
class Evidence:
    """One fact an item rests on, naming its source.

    `fact` is the identifier the fact is about — a step id, a gate id —
    and never prose: an item's traceability is the whole reason the
    briefing is trusted, so a reader must be able to find what it refers
    to. `__repr__` renders it for a human because these are read in
    Slack, not in a debugger.
    """

    fact: str
    start: date | None = None
    end: date | None = None

    def __repr__(self) -> str:
        if self.start is None and self.end is None:
            return self.fact
        if self.start == self.end or self.end is None:
            return f"{self.fact} (due {(self.start or self.end)})"
        if self.start is None:
            return f"{self.fact} (due by {self.end})"
        return f"{self.fact} (due {self.start}..{self.end})"


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """One thing to look at: product · discipline · severity · evidence.

    The shape both the TASK side (launch) and the CHECK side (monitoring)
    converge on. `discipline` is optional because not every cause belongs
    to one — a launch date at risk is the launch's, not any single
    discipline's.
    """

    product_id: ProductId
    cause: str
    severity: Severity
    evidence: tuple[Evidence, ...]
    discipline: Discipline | None = None

    def __post_init__(self) -> None:
        if not self.evidence:
            raise BriefingError(
                f"attention item '{self.cause}' for product "
                f"'{self.product_id.value}' carries no evidence; an item "
                "whose numbers cannot be traced is rejected, not reported"
            )


@dataclass(frozen=True, slots=True)
class Finding:
    """A raw observation, before collapse: one cause, one product.

    `absorbs` names the *facts* this finding already accounts for — a
    launch date at risk names the overdue blocking steps that produced
    it, so those appear as its evidence instead of as items of their own.
    Absorption is by fact rather than by cause on purpose: the same cause
    (an overdue step) is absorbed when it is one of the blocking steps
    behind the at-risk date and stands on its own when it is not.
    """

    product_id: ProductId
    cause: str
    severity: Severity
    evidence: tuple[Evidence, ...]
    discipline: Discipline | None = None
    absorbs: tuple[str, ...] = ()


class CauseOrder:
    """The ranking of causes, root cause first — pure data.

    Launch supplies one order, monitoring will supply another; the
    collapse below reads whichever it is given and has no opinion of its
    own about which cause outranks which.
    """

    def __init__(self, causes: Sequence[str]) -> None:
        if len(set(causes)) != len(causes):
            raise BriefingError(f"cause order repeats a cause: {tuple(causes)}")
        self._ranks = {cause: rank for rank, cause in enumerate(causes)}

    def rank(self, cause: str) -> int:
        try:
            return self._ranks[cause]
        except KeyError:
            raise BriefingError(
                f"'{cause}' is not a cause this order ranks: {tuple(self._ranks)}"
            ) from None

    def __contains__(self, cause: object) -> bool:
        return cause in self._ranks


def collapse(
    findings: Iterable[Finding], order: CauseOrder
) -> tuple[AttentionItem, ...]:
    """Turn raw findings into the items the team actually sees.

    Three rules, applied per product: a finding whose cause is absorbed by
    a higher-ranked finding on the same product becomes that one's
    evidence rather than an item; findings sharing a cause *and* a
    discipline merge into one item carrying every piece of evidence; and
    what remains is ordered by cause rank, so the causal thing leads.

    One stockout is one item with symptoms attached, not five alerts.
    """
    by_product: dict[ProductId, list[Finding]] = {}
    for finding in findings:
        order.rank(finding.cause)  # reject an unrankable cause at the boundary
        by_product.setdefault(finding.product_id, []).append(finding)

    items: list[AttentionItem] = []
    for product_findings in by_product.values():
        items.extend(_collapse_one_product(product_findings, order))
    return tuple(items)


def _collapse_one_product(
    findings: list[Finding], order: CauseOrder
) -> list[AttentionItem]:
    absorbed: set[str] = {fact for finding in findings for fact in finding.absorbs}

    merged: dict[tuple[str, Discipline | None], Finding] = {}
    for finding in sorted(findings, key=lambda f: order.rank(f.cause)):
        if finding.absorbs == () and all(
            piece.fact in absorbed for piece in finding.evidence
        ):
            # Every fact it names already travels on the absorbing
            # finding's evidence, so reporting it again would be the
            # duplication this exists to prevent.
            continue
        key = (finding.cause, finding.discipline)
        existing = merged.get(key)
        if existing is None:
            merged[key] = finding
        else:
            merged[key] = _merge(existing, finding)

    return [
        AttentionItem(
            product_id=finding.product_id,
            cause=finding.cause,
            severity=finding.severity,
            evidence=finding.evidence,
            discipline=finding.discipline,
        )
        for finding in merged.values()
    ]


def _merge(first: Finding, second: Finding) -> Finding:
    """Two findings of one cause and discipline, as one — every piece of
    evidence kept, since dropping one would lose the fact it names."""
    return Finding(
        product_id=first.product_id,
        cause=first.cause,
        severity=first.severity,
        evidence=first.evidence + second.evidence,
        discipline=first.discipline,
        absorbs=first.absorbs + second.absorbs,
    )
