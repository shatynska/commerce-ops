"""The handler contract: what a handler is given, and what it may not say.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirement *A handler receives the step, the
launch and the product, and attributes nothing*:

- The statement's shape clauses — a context carrying the step, a read of
  the launch, the catalog product and the moment the pass is running as
  of; a resolution carrying an outcome from the `launch-playbook`
  vocabulary and the produced text; and "The produced text SHALL NOT be
  empty: it becomes the recorded evidence, which `launch-instance`
  requires of every recording."
- Scenario *A handler cannot claim another source*, in the half the
  contract itself enforces: a resolution has no place to put provenance,
  so a handler attempting to supply one is rejected. The other half —
  "the provenance the system constructed stands" — is observable only
  where a recording happens, and is asserted at the pass level in
  `tests/unit/launch/infrastructure/driving/test_automation_pass.py`
  (*A smuggled provenance does not displace the constructed one*).

Its two remaining scenarios (*The product is supplied, not fetched*, *A
produced outcome is attributed to the handler*) are stated over a pass
invoking a handler and live in that same file.

See `test-manifest.md` at the change root for the full accounting.

## Level

`StepContext` and `StepResolution` are frozen dataclasses in
`launch/application/` (`tasks.md` 2.1) with no I/O, so constructing them
is the smallest unit that can observe every clause above.

## What is fixed, and what is INVENTED

Fixed by `design.md`'s own declaration of the contract:

    StepContext:     step, launch, product, as_of
    StepResolution:  outcome, result

— the field names are transcribed from it, not invented — and by
`tasks.md` 2.1 that both are **frozen** dataclasses exported from
`launch/application/`.

INVENTED, recorded in `test-manifest.md`:

- `ValueError` as the empty-text rejection signal, matching the
  construction-time validation convention the shared vocabulary and
  `Blocked`/`NotApplicable` already follow
  (`tests/unit/launch/domain/test_step_outcome.py`).
- `TypeError` as what a dataclass raises for an argument it does not
  declare. This is Python's own behaviour rather than a choice, but it
  is what the assertion reads, so it is named.

## Expected first-run state

Neither type exists (`tasks.md` 2.1), so every test here is expected to
fail on an absent target (`ImportError`). Per `ai-toolkit:testing`, that
establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
"""

from __future__ import annotations

import dataclasses
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepContext, StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    InProgress,
    LaunchPlaybook,
    NotApplicable,
    NotStarted,
    OffsetAnchor,
    Refused,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.playbook import SPECIFIED_GATE_ORDER

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
STEP_ID: Final = "listing.sub-category"
HANDLER_NAME: Final = "listing.subcategory_advisor"
ALICE: Final = "prs_01HQ8Z6M4A"

AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home Decor."
)

# The whole `launch-playbook` outcome vocabulary: a handler returns "an
# outcome from the `launch-playbook` outcome vocabulary", so the contract
# must accept every one of them, not only the terminal ones.
EVERY_OUTCOME: Final = (
    NotStarted,
    InProgress,
    Blocked("the category tree gave no confident answer"),
    Satisfied,
    Refused,
    NotApplicable("single-marketplace product; the node is EU-only"),
)


@dataclass(frozen=True)
class _CatalogProduct:
    """Stands in for the catalog product the pass resolves and supplies."""

    name: str = "Bamboo Cutting Board"
    sku: Sku = dataclasses.field(default_factory=lambda: Sku("BCB-2027-01"))


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "confirmer": ALICE,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": HANDLER_NAME,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
    )


def _playbook() -> LaunchPlaybook:
    step = _step()
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(step, *fillers))


def _launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=_playbook(), launch_date=LAUNCH_DATE
    )
    return launch


def _context(**overrides: Any) -> StepContext:
    attributes: dict[str, Any] = {
        "step": _step(),
        "launch": _launch(),
        "product": _CatalogProduct(),
        "as_of": AS_OF,
    }
    attributes.update(overrides)
    return StepContext(**attributes)


# ---------------------------------------------------------------------------
# What a handler is given
# ---------------------------------------------------------------------------


def test_a_context_carries_the_step_the_launch_the_product_and_the_moment() -> None:
    """Requirement statement: "A handler SHALL be given the step
    definition it is resolving, a read of the launch it is resolving
    against, the catalog product that launch is for, and the moment the
    pass is running as of."

    SPECIFIED: all four, reachable by the handler. The field spellings
    are transcribed from `design.md`'s own declaration of the contract.
    """
    step = _step()
    launch = _launch()
    product = _CatalogProduct()

    context = StepContext(step=step, launch=launch, product=product, as_of=AS_OF)

    assert context.step is step
    assert context.launch is launch
    assert context.product is product
    assert context.as_of == AS_OF


def test_a_context_is_frozen() -> None:
    """`tasks.md` 2.1: "frozen dataclasses".

    DERIVED with respect to the spec, which fixes what a handler is given
    but not that it cannot alter it. Recorded as derived; what it guards
    is the requirement's own reasoning — "a handler is a function of the
    context it is given and nothing else" — which a handler mutating its
    context would defeat for whatever ran after it.
    """
    context = _context()

    assert dataclasses.is_dataclass(type(context))
    # Written through a non-literal attribute name so the assertion is
    # about frozen-ness rather than about a spelling the type checker
    # would reject before the test ever ran.
    frozen_field = "as_of"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(context, frozen_field, AS_OF)


def test_a_context_carries_no_repository_or_store() -> None:
    """Requirement statement: "The catalog product SHALL be resolved by
    the system and supplied to the handler, never fetched by the handler
    itself — a handler is a function of the context it is given and
    nothing else, which is what allows it to be exercised without a
    database".

    DERIVED probe, not exhaustive: the spec fixes that the handler does
    not fetch, and this pins the seam that would let it. Its list is
    recorded in `test-manifest.md` as derived so it is reviewable rather
    than mistaken for a stated requirement.
    """
    fields = {field.name for field in dataclasses.fields(_context())}

    assert not fields & {
        "session",
        "repository",
        "repositories",
        "store",
        "stores",
        "read_product",
        "catalog",
        "launches",
        "playbooks",
        "handlers",
        "registry",
    }, (
        f"the handler context carries a collaborator it could fetch with: {sorted(fields)}"
    )


# ---------------------------------------------------------------------------
# What a handler returns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome", EVERY_OUTCOME, ids=lambda value: type(value).__name__
)
def test_a_resolution_carries_an_outcome_from_the_vocabulary_and_its_text(
    outcome: Any,
) -> None:
    """Requirement statement: "A handler SHALL return an outcome from the
    `launch-playbook` outcome vocabulary together with the result it
    produced, expressed as text a member can read."

    SPECIFIED, over the whole vocabulary: a contract accepting only the
    terminal outcomes would make the requirement's own "A handler with
    nothing conclusive to report SHALL say so through a **non-terminal**
    outcome" unexpressible.
    """
    resolution = StepResolution(outcome=outcome, result=RECOMMENDATION)

    assert resolution.outcome is outcome
    assert resolution.result == RECOMMENDATION


def test_a_resolution_is_frozen() -> None:
    """`tasks.md` 2.1: "frozen dataclasses". DERIVED, as above."""
    resolution = StepResolution(outcome=Satisfied, result=RECOMMENDATION)

    assert dataclasses.is_dataclass(type(resolution))
    frozen_field = "result"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(resolution, frozen_field, "rewritten after the fact")


def test_a_resolution_refuses_empty_produced_text() -> None:
    """Requirement statement: "The produced text SHALL NOT be empty: it
    becomes the recorded evidence, which `launch-instance` requires of
    every recording."

    SPECIFIED. DERIVED: `ValueError` as the signal — the convention
    `Blocked("")` and `NotApplicable("")` already follow.
    """
    with pytest.raises(ValueError):
        StepResolution(outcome=Satisfied, result="")


def test_a_resolution_refuses_produced_text_that_is_only_whitespace() -> None:
    """DERIVED, recorded as such: the spec says the text SHALL NOT be
    empty, and a string of spaces is empty to the member who has to read
    it as the evidence for a compliance-relevant decision, but no
    artifact says so. If the implementation deliberately admits it, this
    is the assertion to reconsider — not the one above.
    """
    with pytest.raises(ValueError):
        StepResolution(outcome=Satisfied, result="   \n\t ")


# ---------------------------------------------------------------------------
# Requirement scenario: A handler cannot claim another source
# ---------------------------------------------------------------------------


def test_a_resolution_has_no_place_to_put_provenance() -> None:
    """Scenario: A handler cannot claim another source.

    WHEN a handler attempts to supply provenance of its own
    THEN the system rejects it.

    `design.md`: "This is a rule the spec states and the contract
    enforces by simply not accepting one." SPECIFIED: the rejection.
    DERIVED: `TypeError`, which is what a dataclass raises for an
    argument it does not declare.
    """
    smuggled = Provenance(
        source="clickup",
        who="a member who never saw this",
        when=AS_OF,
        evidence=RECOMMENDATION,
    )

    # Called through an untyped alias: the contract's *runtime* refusal
    # is what this asserts, and the type checker's refusal of the same
    # call is `tasks.md` 2.2's separate obligation.
    constructor: Any = StepResolution

    with pytest.raises(TypeError):
        constructor(
            outcome=Satisfied,
            result=RECOMMENDATION,
            provenance=smuggled,
        )


def test_no_field_of_the_contract_is_a_provenance_in_disguise() -> None:
    """Requirement statement: "A handler SHALL NOT supply its own
    recording provenance ... A handler therefore cannot record work as
    having come from a member, from ClickUp, or from an attestation."

    DERIVED probe, not exhaustive: the rejection above covers the field
    named `provenance`; this covers the field named something else that
    would carry the same claim. Recorded as derived in
    `test-manifest.md`.
    """
    declared = {
        field.name for field in dataclasses.fields(StepResolution(Satisfied, "x"))
    }

    assert not declared & {
        "provenance",
        "source",
        "who",
        "recorder",
        "recorded_by",
        "attribution",
        "attested_by",
    }, f"the resolution carries an attribution field: {sorted(declared)}"


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - `tasks.md` 2.2 ("type `StepHandlerRegistry`'s callables against that
#   contract, so a handler with the wrong shape fails type checking
#   rather than at run time"). It is a static-analysis obligation whose
#   whole point is that it fails before run time; `uv run mypy`
#   (`tasks.md` 8.4) is the check that observes it, and a runtime
#   assertion over `__annotations__` would pin a spelling no scenario
#   states.
# ---------------------------------------------------------------------------
