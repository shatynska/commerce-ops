"""Driven adapter: reads a launch-playbook YAML file into a `LaunchPlaybook`.

Translates, never re-implements. Every coherence rule lives on
`LaunchPlaybook` and `StepDefinition` themselves (see
`products.domain.launch_playbook`); this module's job is to turn the file's
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

from commerce_ops.products.domain.launch_playbook import (
    Binding,
    Cadence,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    Scope,
    StepDefinition,
    TimingAnchor,
    Track,
    WindowAnchor,
)

_SHIPPED_PACKAGE = "commerce_ops.products.infrastructure.driven"
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


def _parse_track(raw: str) -> Track | str:
    # Coerce when possible; on failure, hand the raw value through so
    # `StepDefinition`'s own validation rejects it and formats the error —
    # this loader does not duplicate that rule.
    try:
        return Track(raw)
    except ValueError:
        return raw


def _build_step_definition(raw: Mapping[str, Any]) -> StepDefinition:
    return StepDefinition(
        identifier=raw["identifier"],
        gate=raw["gate"],
        track=_parse_track(raw["track"]),  # type: ignore[arg-type]
        scope=Scope(raw["scope"]),
        timing_anchor=_parse_timing_anchor(raw["timing_anchor"]),
        binding=Binding(raw["binding"]),
        blocking=bool(raw["blocking"]),
        execution=ExecutionMode(raw["execution"]),
        hazard=Hazard(raw.get("hazard", "none")),
        rule_policy=raw.get("rule_policy"),
        provenance=raw.get("provenance"),
    )
