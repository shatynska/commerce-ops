# Test manifest — `add-launch-playbook`

Written by `openspec-test-writer` from the change's delta spec alone, before
any implementation exists. Not an artifact the OpenSpec schema knows about:
it will **not** appear among `openspec instructions apply`'s context files
and must be read on purpose.

Read this before implementing. It records the API surface the tests assume
(none of which any artifact fixes), which assertions trace to the spec and
which were invented, and which cases were knowingly left uncovered.

- **Delta spec:** `openspec/changes/add-launch-playbook/specs/launch-playbook/spec.md`
- **All deltas are `ADDED`.** No prior `launch-playbook` spec exists.
- **Test command:** `uv run pytest`
- **Test tier:** `tests/unit` (pure domain, no I/O), per `AGENTS.md`.

## Baseline

**Full baseline taken**, before any test was written:

```
uv run pytest
→ 8 passed in 0.98s   (tests/unit 3, tests/agents 4, tests/integration 1)
```

`uv run mypy .` and `uv run ruff check .` were also clean at that point, so
every check reported below is attributable to this pass.

## Files written

| Path | Tests |
|---|---|
| `tests/unit/products/domain/test_timing_anchor.py` | 7 |
| `tests/unit/products/domain/test_launch_playbook.py` | 23 |
| `tests/unit/products/infrastructure/test_playbook_loader.py` | 8 functions → 14 cases (two are parametrized over four gates each) |

38 test functions, 44 collected cases. **This pass added tests and never
subtracted**: no existing test was edited, deleted, disabled or weakened,
and nothing was written outside `tests/**/test_*.py` except this manifest.

### State after the pass

All three new files fail at **collection** with `ModuleNotFoundError: No
module named 'commerce_ops.products.domain.launch_playbook'`.

Per `ai-toolkit:testing` that is **failure state 2 — the target does not
exist yet**. It establishes that the target is absent and *nothing else*:
no assertion in these files has ever executed, so whether the assertions
are any good is still unverified. Treat the first green run as the moment
they become evidence, and read a test that passes trivially as an alarm.

`uv run mypy .` now reports 4 `import-untyped` errors, one per absent
import — the same absence, seen by a second tool. Both clear when the
modules land.

## Scenario accounting

25 `#### Scenario:` blocks in the delta spec; 25 accounted for below. Test
names are given in `pytest` node-id form and can be selected individually.

Path prefixes: `D/` = `tests/unit/products/domain/`, `I/` =
`tests/unit/products/infrastructure/`.

| # | Requirement / Scenario | Covering test(s) |
|---|---|---|
| 1 | Gate sequence — *Gates expose a stable order* | `D/test_launch_playbook.py::test_gates_expose_a_stable_order`; `I/test_playbook_loader.py::test_shipped_playbook_exposes_the_eight_gates_in_order` |
| 2 | Gate sequence — *Steps at the same gate are unordered* | `D/test_launch_playbook.py::test_steps_at_the_same_gate_carry_no_ordering` |
| 3 | Gate opening — *A discretionary gate is marked as requiring confirmation* | `I/test_playbook_loader.py::test_discretionary_gate_requires_confirmation[commit\|order\|phase-one-complete\|graduated]`; guard: `::test_the_two_opening_modes_are_distinct` |
| 4 | Gate opening — *An objective gate opens automatically* | `I/test_playbook_loader.py::test_objective_gate_opens_automatically[listable\|stock-ready\|live\|ignition]`; guard: `::test_the_two_opening_modes_are_distinct` |
| 5 | Step definition — *A step definition is read back with every declared attribute* | `D/test_launch_playbook.py::test_step_definition_is_read_back_with_every_declared_attribute`; `::test_unauthored_optional_attributes_are_absent` (the "present only if authored" clause) |
| 6 | Step definition — *Steps can be selected by gate and by scope* | `D/test_launch_playbook.py::test_steps_can_be_selected_by_gate_and_by_scope` |
| 7 | Hazard — *A compliance obligation may block a gate* | `D/test_launch_playbook.py::test_compliance_obligation_may_block_a_gate` |
| 8 | Hazard — *Classification is always present* | `D/test_launch_playbook.py::test_unauthored_optional_attributes_are_absent`; `::test_hazard_classification_has_exactly_the_three_specified_values` |
| 9 | Provenance — *Two steps cite the same source row* | `D/test_launch_playbook.py::test_two_steps_may_cite_the_same_provenance_reference` |
| 10 | Timing — *An offset anchor resolves to a single day* | `D/test_timing_anchor.py::test_offset_anchor_resolves_to_a_single_day` |
| 11 | Timing — *A window anchor resolves to a bounded span* | `D/test_timing_anchor.py::test_window_anchor_resolves_to_a_bounded_span` |
| 12 | Timing — *An open-ended anchor resolves to a start with no end* | `D/test_timing_anchor.py::test_open_ended_anchor_resolves_to_a_start_with_no_end` |
| 13 | Timing — *The launch day itself is offset zero* | `D/test_timing_anchor.py::test_offset_zero_resolves_to_the_launch_date_itself`; `::test_offset_one_is_the_day_after_launch` |
| 14 | Timing — *A recurring anchor has no due date* | `D/test_timing_anchor.py::test_recurring_anchor_produces_no_range_and_reports_its_cadence` |
| 15 | Timing — *A window with a reversed span is rejected* | `D/test_timing_anchor.py::test_window_with_a_reversed_span_is_rejected` |
| 16 | Versioning — *The loaded playbook reports its version* | `D/test_launch_playbook.py::test_playbook_reports_the_version_it_was_authored_with`; `I/test_playbook_loader.py::test_shipped_playbook_reports_its_version` |
| 17 | Rejection — *Gate sequence deviates from the specification* | `D/test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`; `::test_gate_sequence_with_an_extra_gate_is_rejected`; `::test_gate_sequence_in_the_wrong_order_is_rejected`; `::test_gate_sequence_repeating_a_position_is_rejected` (one per deviation the scenario names) |
| 18 | Rejection — *Duplicate step identifier* | `D/test_launch_playbook.py::test_duplicate_step_identifier_is_rejected` |
| 19 | Rejection — *Step references an unknown gate* | `D/test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected` |
| 20 | Rejection — *Automation without a decided rule* | `D/test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected`; `::test_ai_assisted_step_without_a_rule_policy_is_rejected`; permitted side: `::test_automated_step_with_a_rule_policy_is_accepted` |
| 21 | Rejection — *A prohibited tactic cannot block a gate* | `D/test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`; permitted side: `::test_prohibited_tactic_that_does_not_block_is_accepted` |
| 22 | Rejection — *Multiple violations are reported together* | `D/test_launch_playbook.py::test_two_distinct_violations_are_reported_together` |
| 23 | Rejection — *A malformed step is reported alongside a coherence violation* | `I/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation` |
| 24 | Rejection — *A coherent playbook loads* | `D/test_launch_playbook.py::test_a_coherent_playbook_loads`; `I/test_playbook_loader.py::test_a_coherent_playbook_file_loads` |
| 25 | Undecided rule — *Human-attested step with no rule policy* | `D/test_launch_playbook.py::test_human_attested_step_with_no_rule_policy_loads` |

**Uncovered scenarios: none.** All 25 are covered by at least one named
test. No scenario is reached through a `REMOVED` or `RENAMED` delta.

Two tests carry no scenario of their own and are recorded here so their
provenance is not mistaken for the spec's:

- `I/test_playbook_loader.py::test_the_two_opening_modes_are_distinct` — a
  guard. Scenarios 3 and 4 would both pass if `GateOpening` collapsed to a
  single value.
- `I/test_playbook_loader.py::test_shipped_playbook_ships_with_no_step_definitions`
  — **derived from `proposal.md` and `tasks.md` 4.2**, not from the delta
  spec, which says nothing about how many steps ship. It guards this
  change's stated scope ("Importing the 358 reference items is deliberately
  a follow-up change"). When that follow-up lands, this assertion is
  *superseded* and should be removed as part of it — not weakened to fit.

## Level choice

The five coherence rules are exercised through `LaunchPlaybook`
**construction**, not through the YAML loader, because `tasks.md` 3.5 puts
them there ("Implement the five coherence rules as playbook construction
invariants") and construction is the smallest unit that can observe the
outcome. Two scenarios genuinely need the file boundary and only those two
sit in the infrastructure tier:

- **Scenario 23** — a malformed step cannot exist as a domain object (a
  reversed window is rejected at anchor construction), so only the loader
  can hold one; `tasks.md` 4.3 assigns it there.
- **Scenarios 3 and 4** — the opening modes are authored in data and **no
  coherence rule validates them**. The spec's five rejection rules cover the
  gate *sequence* only. The shipped `v1` file is therefore the only place
  the specified assignment of opening modes is actually settled.

**If the implementation puts the coherence rules in the loader instead of
in `LaunchPlaybook.__init__`, the domain tests will fail on the absent
behaviour rather than on a defect in themselves.** That is a design
conflict with `tasks.md` 3.5, to be reported and settled — not resolved by
weakening the tests.

## Unresolved project questions

Each records the assumption taken and the tests that depend on it. None was
resolvable from `AGENTS.md`, `CLAUDE.md`, `README.md`, `proposal.md`,
`design.md`, `tasks.md` or the delta spec, and a dispatched subagent has no
channel to ask on.

### Q1 — Module paths (all tests in all three files)

Assumed:

- `commerce_ops.products.domain.launch_playbook` — every domain name
- `commerce_ops.products.infrastructure.driven.playbook_loader` — the loader

`launch_playbook` is imported as a dotted path, so it resolves identically
whether implemented as `launch_playbook.py` or as a `launch_playbook/`
package with `__init__.py`. The internal file layout is free.

### Q2 — Domain class and field names (all tests)

| Name | Assumed shape | Fixed by |
|---|---|---|
| `Track`, `Scope`, `Binding`, `ExecutionMode`, `GateOpening`, `Hazard`, `Cadence` | enums | `tasks.md` 2.1, 2.2 (names only) |
| `Gate` | `Gate(identifier: str, position: int, opening: GateOpening)` | `tasks.md` 3.1 (attributes, not names) |
| `StepDefinition` | `StepDefinition(identifier, gate, track, scope, timing_anchor, binding, blocking, execution, hazard=Hazard.NONE, rule_policy=None, provenance=None)` | `tasks.md` 3.2 (attributes, not names) |
| `LaunchPlaybook` | `LaunchPlaybook(version, gates, steps)`, with `.gates`, `.steps`, `.version`, `.steps_for_gate(gate: str)`, `.steps_with_scope(scope: Scope)` | `tasks.md` 3.3, 3.4 (queries, not names) |
| `InvalidPlaybookError` | raised by playbook construction *and* by the loader; `str(error)` names every offending step or gate | spec requires the naming; the type name is invented |
| `OffsetAnchor(days=)`, `WindowAnchor(start=, end=)`, `OpenEndedAnchor(start=)`, `RecurringAnchor(cadence=)` | four variants with `.resolve(launch_date) -> range \| None` | `tasks.md` 2.2, 2.3 (shapes, not names) |
| `Gate.identifier` is a `str`, not an enum | required so that "a step declares a gate not in the sequence" is expressible at all | scenario 19 |
| `GateOpening.AUTOMATIC` / `.REQUIRES_CONFIRMATION` | two members | spec's two opening modes |
| `Hazard.NONE` / `.PROHIBITED_TACTIC` / `.COMPLIANCE_OBLIGATION` | three members | spec names the three wire values |

If a name differs, renaming it in the tests is a **fixture correction**, not
a weakening — but the correction should be recorded, because it means these
tests never constrained that name.

### Q3 — `Track`'s members are nowhere enumerated

No artifact lists them. The tests need a track value to construct a step but
assert nothing about which, so `_any_track()` in
`D/test_launch_playbook.py` returns `next(iter(Track))` rather than naming a
member. Deliberate: hard-coding one would invent a constraint. The one place
a track is named by string is the invented YAML in Q4.

### Q4 — The YAML document shape is undecided (`tasks.md` 4.1)

Affects exactly two tests:
`I/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation`
and `::test_a_coherent_playbook_file_loads`. Both build their input from
`_GATES_YAML` / `_TWO_FAULTY_STEPS_YAML` in that file, which assume:

```yaml
version: v1
gates:  [{identifier, position, opening: automatic | requires-confirmation}]
steps:  [{identifier, gate, track, scope, timing_anchor: {kind, ...},
          binding, blocking, execution, hazard?, rule_policy?, provenance?}]
```

Loader tests were kept to the minimum that needs the file boundary
precisely to confine this invention. If the implemented shape differs, edit
the two document constants — that is correcting the test's *input*, and is
distinct from changing what the test asserts about the resulting error,
which would be weakening it.

Note also: `track: inventory` / `track: ppc` in `_TWO_FAULTY_STEPS_YAML`
depend on Q3. If `Track` has no such members, those steps carry a third
fault; the assertion still holds (both identifiers are named) but the test
no longer isolates the malformed-anchor/coherence pairing it was written
for.

### Q5 — Gate position base (0 or 1)

The spec numbers the gates 1–8 in a markdown list but does not state the
base, while timing offsets are explicitly zero-based. Test helpers author
positions from 1; **no assertion depends on it**. Both
`test_gates_expose_a_stable_order` and
`test_shipped_playbook_exposes_the_eight_gates_in_order` assert only that
positions are distinct and ascend with the sequence. Recorded as
deliberately untested rather than silently pinned.

### Q6 — The exception type for a reversed window

The spec says "rejected as invalid" and names no type.
`test_window_with_a_reversed_span_is_rejected` asserts `ValueError`, which
`pytest.raises` satisfies for any subclass — so a domain-specific error
deriving from `ValueError` passes without the test knowing its name.

### Q7 — The shipped version string is `v1`

From `tasks.md` 4.2, not from the spec, which requires only *a* version
identifier. Depended on by
`I/test_playbook_loader.py::test_shipped_playbook_reports_its_version`.

### Q8 — Test-package `__init__.py` files (deviation from repo convention)

Every existing test directory carries an `__init__.py`. The three new
directories do **not**: `__init__.py` does not match the dispatched
test-path glob `tests/**/test_*.py`, and this pass writes nothing outside
it. Collection was verified to work without them (distinct module
basenames, no collision), so this is a consistency question for the project
owner, not a defect.

## Assertion classification

Recorded inline in every test — each assertion carries a `SPECIFIED`,
`DERIVED` or `DELIBERATELY UNTESTED` comment, and each test's docstring
quotes the scenario it comes from. Summary of what is *not* specified:

**Derived assertions** (invented; no stated requirement covers them):

- Positions ascend with the gate sequence (`positions == sorted(positions)`).
  The spec requires distinct positions and a defined order, not that the two
  agree numerically.
- `StepDefinition` exposes none of a probe list of ordering attribute names
  (`position`, `order`, `depends_on`, …). The concept is forbidden by the
  spec; the list of spellings is a best-effort probe, not exhaustive.
- The launch date `2026-03-02` and the literal expected dates. Chosen so the
  offsets under test cross month boundaries in both directions, and written
  as literals so the test does not reuse the arithmetic it checks.
- `Cadence.WEEKLY` as the cadence in the recurring-anchor test. The spec
  fixes no cadence set; `design.md`'s transcription table names
  Daily/Weekly/Biweekly/Monthly.
- `test_offset_one_is_the_day_after_launch` — the spec states "the day after
  it is offset 1" in prose, inside the requirement rather than in a scenario.
- `test_automated_step_with_a_rule_policy_is_accepted` and
  `test_prohibited_tactic_that_does_not_block_is_accepted` — the permitted
  side of two rejection rules. Without them, an implementation that rejected
  *every* automated step, or *every* prohibited tactic, would pass.
- `test_shipped_playbook_ships_with_no_step_definitions` — from
  `proposal.md`, see above.
- `str(error)` as the surface on which "the failure names the offending step
  or gate" is asserted. The spec requires the naming, not a particular
  carrier; asserting on the message keeps the tests agnostic about whether
  the error also exposes a structured fault list.

**Deliberately untested**, recorded with reasons at the foot of each test
file:

- Gate position base (Q5).
- Immutability of the domain objects (`tasks.md` 3.1–3.3) — a task-level
  implementation decision, not a scenario; the mechanism is the
  implementer's choice.
- That no domain module imports `yaml`, FastAPI or any I/O (`tasks.md` 3.7)
  — an architectural check over the whole layer, better served by a lint or
  import-linter rule than by a unit test derived from these scenarios.
- Whether a window with `start == end` is accepted; whether an open-ended
  anchor may start before launch; whether a recurring anchor carries an
  offset. None is stated.
- The concrete type returned by `resolve()` — the scenarios describe only a
  start and an optional end, so no range type is imported.
- A dedicated single-step lookup on the playbook. "Addressable by its own
  identifier" is asserted through the `steps` collection so no lookup API is
  invented.
- Loader behaviour for a missing file, unreadable file, or non-mapping YAML.
  The spec's rejection rules concern playbook coherence, not I/O or parse
  failure.
- Package-data presence in an installed build (`tasks.md` 4.4) — observable
  only from a built wheel, not from the source-tree unit tier.
- The member sets of `Track`, `Scope`, `Binding`, `ExecutionMode`,
  `Cadence`. Only `Hazard`'s set is closed by the spec, and only it is
  asserted.
- Exact error-message wording. Only that the message names the offending
  step or gate.

## Obsolete tests

**Not applicable.** Every delta in this change is `ADDED`, and no prior
`launch-playbook` spec exists, so no existing test can have been superseded.
No search for bearing tests was performed and none was needed.

## Notes for whoever implements next

1. **These tests are red and will block `pre-commit`.** They were left
   plainly red — no `xfail`, no `importorskip` — matching the precedent set
   by `tests/unit/test_health.py`, which was written the same way against an
   absent `commerce_ops.main`. Marking them expected-to-fail would hide
   failure state 2, which is the one signal this pass exists to produce.
   Three checks are red until implementation lands: `pytest tests/unit`
   (3 collection errors), `mypy .` (4 `import-untyped` errors), and nothing
   else. **The commit strategy is the project owner's decision**, not one
   this pass made.
2. **Run `ruff check --fix` after implementation.** The new files are
   currently `ruff`-clean, but `ruff`'s isort resolves first-party by
   checking whether the module exists under `src/` — so `commerce_ops.*`
   imports here are currently sorted as third-party. Once the modules exist
   they become first-party and want their own import block.
3. The tests do not tell you *how* to satisfy them beyond the API surface in
   Q1–Q2. Where a name here is wrong for the design, change it in both
   places and note it; where an *assertion* is wrong, that is a spec
   question for `openspec-update-change`, not a test edit.
