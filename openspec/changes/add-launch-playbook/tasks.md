## 1. Dependencies

- [ ] 1.1 Add `pyyaml` to `pyproject.toml` runtime dependencies (currently only present transitively), pinned to a conservative version range
- [ ] 1.2 Add `types-PyYAML` to the dev dependency group so `mypy` can type the parsing boundary
- [ ] 1.3 Run `uv sync` to update the lockfile and environment

## 2. Domain — value objects

- [ ] 2.1 Add `Track`, `Scope`, `Binding`, `ExecutionMode`, `GateOpening` and `Hazard` as enumerations in the `products` domain layer, with `Hazard` taking `none`, `prohibited-tactic`, `compliance-obligation` and defaulting to `none`
- [ ] 2.2 Add `TimingAnchor` as a closed set of four immutable variants — offset, window, open-ended, recurring — with a `Cadence` enumeration for the recurring form
- [ ] 2.3 Implement resolution against a launch date: offset yields a single day, window a bounded range, open-ended a range with a start and no end, recurring no range but its cadence
- [ ] 2.4 Reject a window anchor whose end offset precedes its start offset at construction
- [ ] 2.5 Document in the module that offset zero is the marketing launch date, that offsets are zero-based while the reference numbers days from one (so `Day N` transcribes to offset *N*−1 per the transcription table in `design.md`), and that reference `T-N` values are coarse planning buckets, not due dates

## 3. Domain — playbook model

- [ ] 3.1 Add `Gate` as an immutable entity carrying its identifier, position in the sequence, and opening mode
- [ ] 3.2 Add `StepDefinition` as an immutable entity carrying identifier, gate, track, scope, timing anchor, binding, blocking flag, execution mode, hazard classification, optional rule policy, optional provenance reference
- [ ] 3.3 Add `LaunchPlaybook` as the aggregate root holding a version identifier, its ordered gates, and its step definitions
- [ ] 3.4 Implement playbook queries: gates in order, steps attached to a given gate, steps of a given scope
- [ ] 3.5 Implement the five coherence rules as playbook construction invariants: gate sequence not exactly the eight specified gates in order with distinct positions; duplicate step identifier; unknown gate reference; automated or AI-assisted execution with no rule policy; `prohibited-tactic` step marked blocking
- [ ] 3.6 Make load failure report every fault found together — malformed step definitions and invalid timing anchors alongside coherence-rule violations — each naming its offending step or gate, rather than failing on the first
- [ ] 3.7 Confirm no domain module imports `yaml`, FastAPI, or any I/O

## 4. Playbook data and loader

- [ ] 4.1 Define the YAML document shape for a playbook (version, gates, steps) and record it as a comment header in the data file
- [ ] 4.2 Author the launch playbook data file with version `v1`, the eight gates in order with their opening modes per `design.md`, and no step definitions
- [ ] 4.3 Implement the playbook loader as a driven adapter: read the file, parse it, and construct the domain `LaunchPlaybook`, collecting per-step shape and anchor errors rather than raising on the first, and surfacing them through the same aggregated load failure as the coherence rules
- [ ] 4.4 Ensure the shipped data file is included as package data so it is present in an installed build, not only in a source checkout

## 5. Tests

- [ ] 5.1 Create `tests/unit/products/` mirroring the module layer structure
- [ ] 5.2 Test the gate sequence: eight gates in the defined order, positions unique, and the four discretionary gates report that they require confirmation while the other four open automatically
- [ ] 5.3 Test that two steps declaring the same gate carry no ordering between them, and that querying by gate and by scope returns exactly the matching steps
- [ ] 5.4 Test that a step definition round-trips every declared attribute, with rule policy and provenance absent when not authored
- [ ] 5.5 Test that two steps sharing a provenance reference load successfully
- [ ] 5.6 Test timing-anchor resolution: offset −7 resolves to a single day, offset 0 resolves to the launch date itself, window 28–55 resolves to that span, open-ended offset 59 resolves to a start with no end, recurring produces no range, reversed window is rejected
- [ ] 5.7 Test that a loaded playbook reports its version identifier
- [ ] 5.8 Test each of the five rejection rules independently, asserting the error names the offending step or gate — including a gate sequence that omits, adds, reorders, or repeats a position
- [ ] 5.9 Test that a playbook with two distinct violations fails once and names both, and that a malformed step definition is reported alongside a separate coherence violation in the same failure
- [ ] 5.10 Test that a `compliance-obligation` step marked blocking loads successfully, while a `prohibited-tactic` step marked blocking is rejected
- [ ] 5.11 Test that a human-attested step with no rule policy loads successfully
- [ ] 5.12 Test that the shipped `v1` data file loads successfully through the real loader

## 6. Verification

- [ ] 6.1 Run `uv run pytest` and confirm the new tests and the existing suite pass
- [ ] 6.2 Run `ruff check` and `ruff format --check`
- [ ] 6.3 Run `mypy`
- [ ] 6.4 Run `openspec validate --strict` on this change

## 7. Repository housekeeping

- [ ] 7.1 Commit `docs/reference/` — the four externally supplied reference documents moved out of the gitignored `.idea/` directory — with a short `README.md` in that directory stating they are external reference material, not project-authored, and are not to be edited
