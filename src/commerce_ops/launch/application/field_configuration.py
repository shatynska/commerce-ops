"""The Custom Field configuration: what resolves, and what is missing.

`record-gate-and-discipline-as-fields` records a step's gate and discipline
as values on two hand-configured ClickUp Custom Fields. This module answers
two questions about that configuration, once per pass and before any task is
written:

- **What resolves?** For each configured field, a map from each gate
  identifier and each discipline value to the option identifier a write of
  it should send.
- **What is missing?** Every way the configuration falls short, named
  together so one repair round closes them all.

It is deliberately pure -- it takes the field definitions a read already
fetched, plus the vocabularies the repository owns, and returns data. No
I/O, so the whole of the rule is testable without ClickUp.

Checking once rather than per task is what makes the check *complete*: a gap
in an option is a property of the configuration, identical for every task of
every launch, and discovering it only where a task happens to need it would
leave a gate whose steps are all resolved -- or a launch not yet reached --
unchecked, so a missing option for a late gate would stay invisible until a
launch arrived at it.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from commerce_ops.launch.domain.launch_playbook import GATE_SEQUENCE
from commerce_ops.shared.domain.clickup import ClickUpFieldDefinition
from commerce_ops.shared.domain.discipline import Discipline

# The one field type whose values this system writes: a single value drawn
# from an ordered set of options. The order is why a field is preferred to a
# tag at all, so a type that carries no declared order -- or carries several
# values at once -- is not what the writes assume, however well formed it is.
SUPPORTED_FIELD_TYPE = "drop_down"


class FieldRole(enum.Enum):
    """Which of the two fields a finding is about.

    Named by role rather than by the field's name in ClickUp, because the
    name is cosmetic: the system pins identifiers precisely so a rename
    cannot detach it from the field.
    """

    GATE = "gate"
    DISCIPLINE = "discipline"


class GapKind(enum.Enum):
    """One way a configured field falls short.

    Eight kinds. Exactly one of them -- `MISSING_OPTIONS` -- names something
    missing; the other seven name a fact about the field itself. That is why
    a gap's identity is taken over the whole finding rather than over the
    missing names alone: an identity over missing names would make seven of
    the eight indistinguishable, and a deployment repairing one into another
    would meet silence where the whole point was a report.
    """

    EMPTY_IDENTIFIER = "empty-identifier"
    ABSENT = "absent"
    UNINTERPRETABLE = "uninterpretable"
    WRONG_TYPE = "wrong-type"
    OPTIONLESS = "optionless"
    DUPLICATE_OPTION_NAME = "duplicate-option-name"
    MISSING_OPTIONS = "missing-options"
    WRONG_ORDER = "wrong-order"


# A fault at the level of the field itself. No value is written for a field
# found in one of these: for the first five nothing could resolve anyway,
# and for a duplicate no write is unambiguous, since "the option the match
# names" is then not a single option.
KINDS_THAT_WITHHOLD_WRITES = frozenset(
    {
        GapKind.EMPTY_IDENTIFIER,
        GapKind.ABSENT,
        GapKind.UNINTERPRETABLE,
        GapKind.WRONG_TYPE,
        GapKind.OPTIONLESS,
        GapKind.DUPLICATE_OPTION_NAME,
    }
)

# Deliberately *not* the same set. A field found in one of these yields no
# option-level or order finding, because those findings are that fault's
# consequences rather than separate repairs -- an optionless field would
# otherwise be reported as declaring no options *and* as missing all eight
# gates. The duplicate kind is excluded: such a field may still be missing
# options a repair must address, so only its *order* finding is withheld.
KINDS_THAT_WITHHOLD_OPTION_FINDINGS = KINDS_THAT_WITHHOLD_WRITES - {
    GapKind.DUPLICATE_OPTION_NAME
}


@dataclass(frozen=True, slots=True)
class FieldFinding:
    """Everything wrong with one configured field, and its identity.

    `order_observed` carries the gate options in the order the field
    declares them, so a report can name the order found rather than leaving
    someone to reconstruct it. It is omitted while a duplicate stands, along
    with the order kind: the order cannot be judged until the duplicate is
    resolved, and including it would make a reorder during an unrepaired
    duplicate change the identity and re-report the same gap.
    """

    role: FieldRole
    kinds: frozenset[GapKind]
    missing: tuple[str, ...] = ()
    duplicated: tuple[str, ...] = ()
    declared: tuple[str, ...] = ()
    order_observed: tuple[str, ...] = ()

    @property
    def withholds_writes(self) -> bool:
        return bool(self.kinds & KINDS_THAT_WITHHOLD_WRITES)

    def identity(self) -> tuple[object, ...]:
        """What decides whether this finding is the one already reported.

        Compared as a *set* where the thing itself is unordered -- the kinds
        a field is in, the names missing from it, the names duplicated on it
        -- and as a sequence only for the observed order, whose order is the
        finding.
        """
        return (
            self.role.value,
            tuple(sorted(kind.value for kind in self.kinds)),
            tuple(sorted(self.missing)),
            tuple(sorted(self.duplicated)),
            self.order_observed,
        )


@dataclass(frozen=True, slots=True)
class FieldConfiguration:
    """What one pass established about the two fields."""

    resolution: Mapping[FieldRole, Mapping[str, str]] = dataclass_field(
        default_factory=dict
    )
    findings: tuple[FieldFinding, ...] = ()

    @property
    def has_gap(self) -> bool:
        return bool(self.findings)

    def identity(self) -> tuple[object, ...]:
        """The whole gap's identity, over every field's finding."""
        return tuple(sorted(f.identity() for f in self.findings))

    def option_for(self, role: FieldRole, value: str) -> str | None:
        """The option identifier a write should send, or `None`.

        `None` where the field is unconfigured, withholds writes, or simply
        declares no option naming this value -- in every one of those cases
        the caller writes nothing rather than an approximation.
        """
        return self.resolution.get(role, {}).get(value)


def _expected(role: FieldRole) -> tuple[str, ...]:
    if role is FieldRole.GATE:
        return tuple(GATE_SEQUENCE)
    return tuple(discipline.value for discipline in Discipline)


def _assess(
    role: FieldRole,
    identifier: str | None,
    definitions: Mapping[str, ClickUpFieldDefinition],
) -> tuple[Mapping[str, str], FieldFinding | None]:
    """One field's resolution and its finding, in two tiers.

    The first tier is assessed for an identifier present at all; every other
    clause only for one present and non-empty. An identifier that is present
    but empty is reported as *configured with no value*, never as the field
    being *absent* -- the two call for different repairs, and reporting a
    rendering mistake as a missing field sends someone looking in the wrong
    place.
    """
    if identifier is None:
        # Not configured. A decline, answered with silence rather than a
        # report: silence means "not asked for", noise means "asked for and
        # broken", and each field is declined independently of the other.
        return {}, None

    if not identifier.strip():
        return {}, FieldFinding(role=role, kinds=frozenset({GapKind.EMPTY_IDENTIFIER}))

    definition = definitions.get(identifier)
    if definition is None:
        return {}, FieldFinding(role=role, kinds=frozenset({GapKind.ABSENT}))

    kinds: set[GapKind] = set()
    if definition.uninterpretable:
        # Reported as this and *not* additionally as declaring no options,
        # even though it declares none: every uninterpretable field
        # trivially does, and reporting both would leave a caller unable to
        # tell which fact to act on.
        kinds.add(GapKind.UNINTERPRETABLE)
    elif definition.type != SUPPORTED_FIELD_TYPE:
        kinds.add(GapKind.WRONG_TYPE)
    elif not definition.options:
        kinds.add(GapKind.OPTIONLESS)

    expected = _expected(role)
    declared = tuple(option.name for option in definition.options)

    duplicated = tuple(
        sorted({name for name in declared if declared.count(name) > 1} & set(expected))
    )
    if duplicated:
        kinds.add(GapKind.DUPLICATE_OPTION_NAME)

    if kinds & KINDS_THAT_WITHHOLD_OPTION_FINDINGS:
        # The fault at the level of the field is the one to repair; the
        # option-level findings it would generate are its consequences.
        return {}, FieldFinding(
            role=role, kinds=frozenset(kinds), declared=declared, duplicated=duplicated
        )

    by_name: dict[str, str] = {}
    for option in definition.options:
        # Exact on the identifier string -- no case-folding, no trimming, no
        # fuzzy match. A hand-typed option differing by case, spacing or
        # wording is a configuration gap rather than a match. First
        # occurrence wins, which only matters for a duplicate, and a
        # duplicate withholds the writes anyway.
        by_name.setdefault(option.name, option.id)

    missing = tuple(value for value in expected if value not in by_name)
    if missing:
        kinds.add(GapKind.MISSING_OPTIONS)

    order_observed: tuple[str, ...] = ()
    if role is FieldRole.GATE and not duplicated:
        # A subsequence test over the options *naming gates*: a field may
        # declare options the playbook knows nothing about, and those are
        # neither a gap nor a disturbance to the order. Gates the field does
        # not declare are already reported as missing, and must not also be
        # reported as an order fault.
        naming_gates = tuple(name for name in declared if name in set(expected))
        in_playbook_order = tuple(
            value for value in expected if value in set(naming_gates)
        )
        if naming_gates != in_playbook_order:
            kinds.add(GapKind.WRONG_ORDER)
            order_observed = naming_gates

    resolution = {value: by_name[value] for value in expected if value in by_name}
    if not kinds:
        return resolution, None
    return resolution, FieldFinding(
        role=role,
        kinds=frozenset(kinds),
        missing=missing,
        duplicated=duplicated,
        declared=declared,
        order_observed=order_observed,
    )


def check_field_configuration(
    *,
    gate_field_id: str | None,
    discipline_field_id: str | None,
    fields: Iterable[ClickUpFieldDefinition] | None,
) -> FieldConfiguration:
    """What resolves and what is missing, for both fields at once.

    `fields` is `None` where no read of the folder's fields was made or the
    read did not complete. Then only the empty-identifier finding is
    composed: it is established by the configuration alone and needs no
    network at all, so withholding it behind a reachability fault would make
    the catch depend on the very service whose configuration is in question.
    Every other kind is withheld, because nothing is known about the fields.
    """
    definitions: Mapping[str, ClickUpFieldDefinition] = (
        {} if fields is None else {definition.id: definition for definition in fields}
    )

    resolution: dict[FieldRole, Mapping[str, str]] = {}
    findings: list[FieldFinding] = []
    for role, identifier in (
        (FieldRole.GATE, gate_field_id),
        (FieldRole.DISCIPLINE, discipline_field_id),
    ):
        if fields is None:
            if identifier is not None and not identifier.strip():
                findings.append(
                    FieldFinding(role=role, kinds=frozenset({GapKind.EMPTY_IDENTIFIER}))
                )
            continue
        resolved, finding = _assess(role, identifier, definitions)
        if resolved:
            resolution[role] = resolved
        if finding is not None:
            findings.append(finding)

    return FieldConfiguration(resolution=resolution, findings=tuple(findings))


def describe_gap(configuration: FieldConfiguration) -> str:
    """The gap, as a message a person can act on.

    Names every finding rather than the first, so one repair round closes
    them all; names what the field *does* declare where an option is
    missing, so a hand-typed mismatch is diagnosable rather than merely
    reported; and names the order found where the order is wrong, so the
    repair is a reordering someone can perform.
    """
    lines: list[str] = []
    for finding in configuration.findings:
        role = finding.role.value
        for kind in sorted(finding.kinds, key=lambda k: k.value):
            if kind is GapKind.EMPTY_IDENTIFIER:
                lines.append(
                    f"the {role} field is configured with no value "
                    "(its identifier is present but empty, which is a "
                    "rendering fault rather than a missing field)"
                )
            elif kind is GapKind.ABSENT:
                lines.append(
                    f"the {role} field's configured identifier is not among "
                    "the launch folder's Custom Fields"
                )
            elif kind is GapKind.UNINTERPRETABLE:
                lines.append(
                    f"the {role} field could not be interpreted "
                    "(this is not the same as it declaring no options)"
                )
            elif kind is GapKind.WRONG_TYPE:
                lines.append(
                    f"the {role} field is not a drop-down, so it declares no "
                    "ordered set of options for a value to be drawn from"
                )
            elif kind is GapKind.OPTIONLESS:
                lines.append(f"the {role} field declares no options")
            elif kind is GapKind.DUPLICATE_OPTION_NAME:
                lines.append(
                    f"the {role} field declares more than one option named "
                    + ", ".join(repr(name) for name in finding.duplicated)
                )
            elif kind is GapKind.MISSING_OPTIONS:
                lines.append(
                    f"the {role} field declares no option named "
                    + ", ".join(repr(name) for name in finding.missing)
                    + "; it declares "
                    + (", ".join(repr(name) for name in finding.declared) or "nothing")
                )
            elif kind is GapKind.WRONG_ORDER:
                lines.append(
                    "the gate field's options are not in the playbook's gate "
                    "order; it declares "
                    + ", ".join(repr(name) for name in finding.order_observed)
                )
    return "\n".join(f"- {line}" for line in lines)


def resolvable_values(
    configuration: FieldConfiguration, role: FieldRole
) -> Sequence[str]:
    """The values this field can currently carry -- for reporting only."""
    return tuple(configuration.resolution.get(role, {}))
