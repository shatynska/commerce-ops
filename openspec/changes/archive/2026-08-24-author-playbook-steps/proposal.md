## Why

The shipped launch playbook (`playbook_v1.yaml`) defines the eight gates but carries `steps: []` — every mechanism that consumes steps (ClickUp task projection, due-date derivation, overdue detection, gate blocking, briefing items) is built and tested but has no data to act on, so the launch process cannot be exercised end to end. The ops team's active work is listing-building, so the reference plan's BUILD THE LISTING area needs full fidelity now; the rest of the playbook needs enough coverage to test every mechanism.

## What Changes

- Author step definitions into the shipped `playbook_v1.yaml`, edited in place under the recorded versioning cut-off (no launch has pinned `v1`; see `docs/domain-map.md`, "Versioning cut-off").
- **Full coverage of the reference plan's BUILD THE LISTING area** (`docs/reference/product-launch.md`, area 3): all 72 ID-bearing rows become steps — 65 attached to the `listable` gate, 7 reassigned to the gate their own timing serves (`live`, `stock-ready`, `ignition`).
- **A representative subset (25 steps) across the other seven gates**, curated so that every timing-anchor kind (offset, window, open-ended, recurring), all twelve disciplines, both hazards (`prohibited-tactic`, `compliance-obligation`), and all three execution modes appear in the playbook, and every gate holds at least one blocking step.
- Rule policies authored for the one `automated` and one `ai-assisted` step (a load-time coherence requirement); every other step ships policy-less and therefore appears in the undecided-rule-policies report, which is the intended authoring-in-progress state.
- Reference rows that restate a gate's authored metric condition (e.g. the 60–80 fulfillable-units inventory gate, the 40% organic-share gate) are deliberately **not** duplicated as steps.
- Step identifiers are the reference document's own IDs (`lp.strategy.001`); `provenance` carries the SOURCE citation, so every step traces back to its row.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `launch-playbook`: gains a requirement that the shipped `v1` playbook carries the authored step set — full representation of the reference plan's BUILD THE LISTING area, at least one blocking step per gate, TOS-risk tactics represented as non-blocking `prohibited-tactic` steps, and identifiers/provenance traceable to the reference document. The existing schema and coherence requirements are unchanged; this makes the shipped *content* a specified behavior the way the gate sequence already is.

## Impact

- `src/commerce_ops/launch/infrastructure/driven/playbook_v1.yaml` — the only production file that changes. No code changes.
- New unit tests asserting the shipped playbook's coverage properties (loads coherently, per-gate step presence, discipline/anchor/hazard coverage, blocking counts).
- Operational consequence, named rather than hidden: 95 of the 97 steps are human-attested, and 92 of those project into ClickUp tasks (a `prohibited-tactic` step is never projected), so the first convergence pass after a launch starts will create ~92 tasks in that launch's list, most of them in the listing block.
- `docs/domain-map.md` — the playbook section's "steps are a follow-up change" note is closed out.
