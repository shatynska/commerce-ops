## 1. Dependencies

- [x] 1.1 Add `pyyaml` to `pyproject.toml` runtime dependencies (currently only present transitively), pinned to a conservative version range
- [x] 1.2 Add `types-PyYAML` to the dev dependency group so `mypy` can type the parsing boundary
- [x] 1.3 Run `uv sync` to update the lockfile and environment

## 2. Domain — value objects

- [x] 2.1 Add `Track`, `Scope`, `Binding`, `ExecutionMode`, `GateOpening` and `Hazard` as enumerations in the `products` domain layer, with `Hazard` taking `none`, `prohibited-tactic`, `compliance-obligation` and defaulting to `none`, and `Track` taking the twelve disciplines listed in the spec (`strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`, `price`, `ppc`, `customer`, `external`, `traffic`)
- [x] 2.2 Add `TimingAnchor` as a closed set of four immutable variants — offset, window, open-ended, recurring — with a `Cadence` enumeration for the recurring form
- [x] 2.3 Implement resolution against a launch date: offset yields a single day, window a bounded range, open-ended a range with a start and no end, recurring no range but its cadence
- [x] 2.4 Reject a window anchor whose end offset precedes its start offset at construction
- [x] 2.5 Document in the module that offset zero is the marketing launch date, that offsets are zero-based while the reference numbers days from one (so `Day N` transcribes to offset *N*−1 per the transcription table in `design.md`), and that reference `T-N` values are coarse planning buckets, not due dates

## 3. Domain — playbook model

- [x] 3.1 Add `Gate` as an immutable entity carrying its identifier, position in the sequence, and opening mode
- [x] 3.1.1 Add a lookup of the eight gates' specified opening modes (per the *Gates, not stages* table and the confirmation criterion in `design.md`), for the coherence rule in 3.5 to check declared gates against
- [x] 3.2 Add `StepDefinition` as an immutable entity carrying identifier, gate, track, scope, timing anchor, binding, blocking flag, execution mode, hazard classification, optional rule policy, optional provenance reference — reject a track outside the fixed set of twelve at construction
- [x] 3.3 Add `LaunchPlaybook` as the aggregate root holding a version identifier, its ordered gates, and its step definitions
- [x] 3.4 Implement playbook queries: gates in order, steps attached to a given gate, steps of a given scope
- [x] 3.5 Implement the six coherence rules as `LaunchPlaybook` construction invariants — pure domain code, no I/O, no dependency on the loader: gate sequence not exactly the eight specified gates in order with distinct positions; a gate's opening mode not matching the mode this specification assigns it; duplicate step identifier; unknown gate reference; automated or AI-assisted execution with no rule policy; `prohibited-tactic` step marked blocking
- [x] 3.6 Make load failure report every fault found together — malformed step definitions and invalid timing anchors alongside coherence-rule violations — each naming its offending step or gate, rather than failing on the first
- [x] 3.7 Confirm no domain module imports `yaml`, FastAPI, or any I/O

## 4. Playbook data and loader

- [x] 4.1 Define the YAML document shape for a playbook (version, gates, steps) and record it as a comment header in the data file
- [x] 4.2 Author the launch playbook data file with version `v1`, the eight gates in order with their opening modes per `design.md`, and no step definitions
- [x] 4.3 Implement the playbook loader as a driven adapter: read the file, parse it into the values `LaunchPlaybook`'s constructor expects, and construct it — the loader does not re-implement any of the six coherence rules, only translates the constructor's raised error and its own per-step shape/anchor parse faults into a single aggregated load failure
- [x] 4.4 Ensure the shipped data file is included as package data so it is present in an installed build, not only in a source checkout

## 5. Tests

- [x] 5.1 Create `tests/unit/products/` mirroring the module layer structure
- [x] 5.2 Test the gate sequence: eight gates in the defined order, positions unique, and the four discretionary gates report that they require confirmation while the other four open automatically
- [x] 5.3 Test that two steps declaring the same gate carry no ordering between them, and that querying by gate and by scope returns exactly the matching steps
- [x] 5.4 Test that a step definition round-trips every declared attribute, with rule policy and provenance absent when not authored
- [x] 5.4.1 Test that each of the twelve track values is accepted, and that a track outside the set is rejected with an error naming the step and the unrecognised track
- [x] 5.5 Test that two steps sharing a provenance reference load successfully
- [x] 5.6 Test timing-anchor resolution: offset −7 resolves to a single day, offset 0 resolves to the launch date itself, window 28–55 resolves to that span, open-ended offset 59 resolves to a start with no end, recurring produces no range, reversed window is rejected
- [x] 5.7 Test that a loaded playbook reports its version identifier
- [x] 5.8 Test each of the six rejection rules independently, constructing `LaunchPlaybook` directly, asserting the error names the offending step or gate — including a gate sequence that omits, adds, reorders, or repeats a position, and a gate whose declared opening mode contradicts the specification (e.g. `commit` marked as opening automatically, or `live` marked as requiring confirmation)
- [x] 5.9 Test that a playbook with two distinct violations fails once and names both, and that a malformed step definition is reported alongside a separate coherence violation in the same failure
- [x] 5.10 Test that a `compliance-obligation` step marked blocking loads successfully, while a `prohibited-tactic` step marked blocking is rejected
- [x] 5.11 Test that a human-attested step with no rule policy loads successfully
- [x] 5.12 Test that the shipped `v1` data file loads successfully through the real loader
- [x] 5.12.1 Test that the loader, given a file with an invalid step alongside a distinct coherence violation, surfaces both through the same aggregated load failure — the file-boundary counterpart to 5.9, which exercises `LaunchPlaybook` directly

## 6. Verification

- [x] 6.1 Run `uv run pytest` and confirm the new tests and the existing suite pass
- [x] 6.2 Run `ruff check` and `ruff format --check`
- [x] 6.3 Run `mypy`
- [x] 6.4 Run `openspec validate --strict` on this change

## 7. Repository housekeeping

- [x] 7.1 Commit `docs/reference/` — the four externally supplied reference documents moved out of the gitignored `.idea/` directory — with a short `README.md` in that directory stating they are external reference material, not project-authored, and are not to be edited
