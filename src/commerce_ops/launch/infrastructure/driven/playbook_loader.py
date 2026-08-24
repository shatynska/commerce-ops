"""Driven adapter: reads a launch-playbook YAML file into a `LaunchPlaybook`.

Translates, never re-implements. Every coherence rule lives on
`LaunchPlaybook` and `StepDefinition` themselves (see
`launch.domain.launch_playbook`); this module's job is to turn the file's
values into the ones those constructors expect, and to merge every fault it
encounters — its own parse/shape faults alongside whatever the domain
constructors raise — into a single reported failure, so a large playbook
does not have to be corrected one load attempt at a time.

See the document-shape comment at the top of `playbook_v1.yaml` for the
YAML shape this loader parses.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    Cadence,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    MetricCondition,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Scope,
    StepDefinition,
    TimingAnchor,
    WindowAnchor,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId

_SHIPPED_PACKAGE = "commerce_ops.launch.infrastructure.driven"
_SHIPPED_FILENAME = "playbook_v1.yaml"


def load_playbook(path: Path) -> LaunchPlaybook:
    """Load and validate a playbook from a YAML file at `path`.

    Raises `InvalidPlaybookError`, naming every fault found, if the file
    does not parse into a coherent playbook.
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8"))

    gates = tuple(_parse_gate(raw) for raw in document.get("gates", []))

    faults: list[str] = []
    steps: list[StepDefinition] = []
    for raw_step in document.get("steps", []):
        try:
            steps.append(_build_step_definition(raw_step))
        except InvalidPlaybookError as exc:
            faults.extend(exc.faults)
        except KeyError as exc:
            # A required key absent from the document. Caught here rather
            # than left to escape, because a `KeyError` is a `LookupError`
            # and so matches neither of the other handlers: without this the
            # whole load aborts on the first such step, naming neither the
            # step nor the key.
            identifier = raw_step.get("identifier", "<unknown>")
            faults.append(f"step '{identifier}': missing required key {exc}")
        except ValueError as exc:
            identifier = raw_step.get("identifier", "<unknown>")
            faults.append(f"step '{identifier}': {exc}")

    try:
        playbook = LaunchPlaybook(
            version=document["version"], gates=gates, steps=tuple(steps)
        )
    except InvalidPlaybookError as exc:
        faults.extend(exc.faults)
        raise InvalidPlaybookError(faults) from None

    if faults:
        raise InvalidPlaybookError(faults)
    return playbook


def load_shipped_playbook() -> LaunchPlaybook:
    """Load the playbook this project ships, from package data.

    Uses `importlib.resources` rather than a hardcoded source-tree path, so
    this works the same way from a source checkout and from an installed
    build.
    """
    with resources.as_file(
        resources.files(_SHIPPED_PACKAGE) / _SHIPPED_FILENAME
    ) as path:
        return load_playbook(path)


def _parse_gate(raw: Mapping[str, Any]) -> Gate:
    return Gate(
        identifier=raw["identifier"],
        position=int(raw["position"]),
        opening=GateOpening(raw["opening"]),
        metric_conditions=tuple(
            _parse_metric_condition(condition)
            for condition in raw.get("metric_conditions", [])
        ),
    )


def _parse_metric_condition(raw: Mapping[str, Any]) -> MetricCondition:
    # An empty threshold description passes through: rejecting it, naming
    # the gate, is the playbook's own coherence rule.
    return MetricCondition(
        metric_id=MetricId(raw["metric_id"]),
        threshold=raw["threshold"],
    )


def _parse_timing_anchor(raw: Mapping[str, Any]) -> TimingAnchor:
    kind = raw["kind"]
    if kind == "offset":
        return OffsetAnchor(days=int(raw["days"]))
    if kind == "window":
        return WindowAnchor(start=int(raw["start"]), end=int(raw["end"]))
    if kind == "open-ended":
        return OpenEndedAnchor(start=int(raw["start"]))
    if kind == "recurring":
        return RecurringAnchor(cadence=Cadence(raw["cadence"]))
    raise ValueError(f"unknown timing anchor kind '{kind}'")


def _parse_discipline(raw: str) -> Discipline | str:
    # Coerce when possible; on failure, hand the raw value through so
    # `StepDefinition`'s own validation rejects it and formats the error —
    # this loader does not duplicate that rule.
    try:
        return Discipline(raw)
    except ValueError:
        return raw


def _build_step_definition(raw: Mapping[str, Any]) -> StepDefinition:
    return StepDefinition(
        identifier=raw["identifier"],
        description=raw["description"],
        gate=raw["gate"],
        discipline=_parse_discipline(raw["discipline"]),  # type: ignore[arg-type]
        scope=Scope(raw["scope"]),
        timing_anchor=_parse_timing_anchor(raw["timing_anchor"]),
        binding=Binding(raw["binding"]),
        blocking=bool(raw["blocking"]),
        execution=ExecutionMode(raw["execution"]),
        hazard=Hazard(raw.get("hazard", "none")),
        rule_policy=raw.get("rule_policy"),
        provenance=raw.get("provenance"),
    )
