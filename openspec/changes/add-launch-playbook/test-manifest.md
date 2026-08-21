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

**This is a repeat pass.** The first pass was committed at `4320d96`. Between
that pass and this one, the delta spec grew two scenarios (a new *Track
names one of a fixed set of disciplines* requirement, and a sixth
coherence-rejection rule — a gate's opening mode disagreeing with the
specification) and `tasks.md` grew two matching tasks (5.4.1, 5.12.1). This
document **replaces** the first pass's manifest wholesale rather than
merging into it, per `ai-toolkit:openspec-test-writer`'s own rule for a
repeat pass: a manifest states the change as it now stands. The three test
files from the first pass were **not edited** — three new test functions
were appended to the tail of two of them, after everything the first pass
wrote, each clearly marked in its file's module docstring and in a comment
immediately above it. Nothing written on the first pass was touched.

## Baseline

**Full baseline taken**, both before the first pass and again before this
one, to confirm nothing had changed in between:

```
uv run pytest
→ 3 collection errors (tests/unit/products/domain/test_launch_playbook.py,
  tests/unit/products/domain/test_timing_anchor.py,
  tests/unit/products/infrastructure/test_playbook_loader.py), all
  ModuleNotFoundError: No module named
  'commerce_ops.products.domain.launch_playbook'; 21 items collected
  outside those three files
```

This is the same state the first pass's manifest recorded (adjusted only
for other, unrelated test files that have since landed elsewhere in the
repository — see `git status` at dispatch time: `tests/unit/shared/` is
untracked and outside this change's scope). Nothing in
`src/commerce_ops/products/` exists yet, so this pass's baseline is
identical in kind to the first pass's: every new test is expected to fail
at collection, not at assertion.

`uv run ruff check` and `uv run ruff format --check`, run against the two
edited files after this pass's tests were appended, both report clean.
`mypy` was not re-run in isolation for this pass beyond what `ruff` already
covers, since the added imports (`Track`, `Gate`, `GateOpening`,
`InvalidPlaybookError`) were already imported by the same files before this
pass — no new import-untyped surface was introduced.

## Files written

No new files. Three new test functions were **appended** to two files that
already existed from the first pass — nothing outside `tests/**/test_*.py`
except this manifest.

| Path | Test functions | Collected cases |
|---|---|---|
| `tests/unit/products/domain/test_timing_anchor.py` (unchanged) | 7 | 7 |
| `tests/unit/products/domain/test_launch_playbook.py` (+3 functions) | 23 → 26 | 23 → 37 (one new function parametrized over 12 track values) |
| `tests/unit/products/infrastructure/test_playbook_loader.py` (+1 function) | 8 → 9 | 14 → 15 |

**Totals: 42 test functions, 59 collected cases** (was 38 / 44). This pass
added tests and never subtracted: no existing test was edited, deleted,
disabled or weakened, and nothing was written outside `tests/**/test_*.py`
except this manifest.

### State after the pass

Both edited files still fail at **collection** with the same
`ModuleNotFoundError` as before — confirmed by running
`uv run pytest tests/unit/products --collect-only -q` after the edit (see
Baseline). Per `ai-toolkit:testing` that is **failure state 2 — the target
does not exist yet**. It establishes that the target is absent and
*nothing else*; none of the three new assertions' bodies has ever executed.
`uv run ruff check`/`ruff format --check` on both edited files: clean.

## Scenario accounting

**27 `#### Scenario:` blocks in the delta spec** (was 25; two added), all
27 accounted for below. Test names are given in `pytest` node-id form and
can be selected individually.

Path prefixes: `D/` = `tests/unit/products/domain/`, `I/` =
`tests/unit/products/infrastructure/`.

| # | Requirement / Scenario | Covering test(s) |
|---|---|---|
| 1 | Gate sequence — *Gates expose a stable order* | `D/test_launch_playbook.py::test_gates_expose_a_stable_order`; `I/test_playbook_loader.py::test_shipped_playbook_exposes_the_eight_gates_in_order` |
| 2 | Gate sequence — *Steps at the same gate are unordered* | `D/test_launch_playbook.py::test_steps_at_the_same_gate_carry_no_ordering` |
| 3 | Gate opening — *A discretionary gate is marked as requiring confirmation* | `I/test_playbook_loader.py::test_discretionary_gate_requires_confirmation[commit\|order\|phase-one-complete\|graduated]`; guard: `::test_the_two_opening_modes_are_distinct` |
| 4 | Gate opening — *An objective gate opens automatically* | `I/test_playbook_loader.py::test_objective_gate_opens_automatically[listable\|stock-ready\|live\|ignition]`; guard: `::test_the_two_opening_modes_are_distinct` |
| 5 | **NEW.** Track — *Track is restricted to the known disciplines* | `D/test_launch_playbook.py::test_track_outside_the_fixed_set_is_rejected`; loader-boundary counterpart (task 5.12.1): `I/test_playbook_loader.py::test_step_with_an_invalid_track_is_reported_alongside_a_coherence_violation`; permitted side (not itself a scenario): `D/test_launch_playbook.py::test_each_specified_track_value_is_accepted[strategy\|finance\|setup\|inventory\|creative\|listing\|rank\|price\|ppc\|customer\|external\|traffic]` |
| 6 | Step definition — *A step definition is read back with every declared attribute* | `D/test_launch_playbook.py::test_step_definition_is_read_back_with_every_declared_attribute`; `::test_unauthored_optional_attributes_are_absent` (the "present only if authored" clause) |
| 7 | Step definition — *Steps can be selected by gate and by scope* | `D/test_launch_playbook.py::test_steps_can_be_selected_by_gate_and_by_scope` |
| 8 | Hazard — *A compliance obligation may block a gate* | `D/test_launch_playbook.py::test_compliance_obligation_may_block_a_gate` |
| 9 | Hazard — *Classification is always present* | `D/test_launch_playbook.py::test_unauthored_optional_attributes_are_absent`; `::test_hazard_classification_has_exactly_the_three_specified_values` |
| 10 | Provenance — *Two steps cite the same source row* | `D/test_launch_playbook.py::test_two_steps_may_cite_the_same_provenance_reference` |
| 11 | Timing — *An offset anchor resolves to a single day* | `D/test_timing_anchor.py::test_offset_anchor_resolves_to_a_single_day` |
| 12 | Timing — *A window anchor resolves to a bounded span* | `D/test_timing_anchor.py::test_window_anchor_resolves_to_a_bounded_span` |
| 13 | Timing — *An open-ended anchor resolves to a start with no end* | `D/test_timing_anchor.py::test_open_ended_anchor_resolves_to_a_start_with_no_end` |
| 14 | Timing — *The launch day itself is offset zero* | `D/test_timing_anchor.py::test_offset_zero_resolves_to_the_launch_date_itself`; `::test_offset_one_is_the_day_after_launch` |
| 15 | Timing — *A recurring anchor has no due date* | `D/test_timing_anchor.py::test_recurring_anchor_produces_no_range_and_reports_its_cadence` |
| 16 | Timing — *A window with a reversed span is rejected* | `D/test_timing_anchor.py::test_window_with_a_reversed_span_is_rejected` |
| 17 | Versioning — *The loaded playbook reports its version* | `D/test_launch_playbook.py::test_playbook_reports_the_version_it_was_authored_with`; `I/test_playbook_loader.py::test_shipped_playbook_reports_its_version` |
| 18 | Rejection — *Gate sequence deviates from the specification* | `D/test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`; `::test_gate_sequence_with_an_extra_gate_is_rejected`; `::test_gate_sequence_in_the_wrong_order_is_rejected`; `::test_gate_sequence_repeating_a_position_is_rejected` (one per deviation the scenario names) |
| 19 | **NEW.** Rejection — *A gate's opening mode disagrees with the specification* | `D/test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected` |
| 20 | Rejection — *Duplicate step identifier* | `D/test_launch_playbook.py::test_duplicate_step_identifier_is_rejected` |
| 21 | Rejection — *Step references an unknown gate* | `D/test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected` |
| 22 | Rejection — *Automation without a decided rule* | `D/test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected`; `::test_ai_assisted_step_without_a_rule_policy_is_rejected`; permitted side: `::test_automated_step_with_a_rule_policy_is_accepted` |
| 23 | Rejection — *A prohibited tactic cannot block a gate* | `D/test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`; permitted side: `::test_prohibited_tactic_that_does_not_block_is_accepted` |
| 24 | Rejection — *Multiple violations are reported together* | `D/test_launch_playbook.py::test_two_distinct_violations_are_reported_together` |
| 25 | Rejection — *A malformed step is reported alongside a coherence violation* | `I/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation` |
| 26 | Rejection — *A coherent playbook loads* | `D/test_launch_playbook.py::test_a_coherent_playbook_loads`; `I/test_playbook_loader.py::test_a_coherent_playbook_file_loads` |
| 27 | Undecided rule — *Human-attested step with no rule policy* | `D/test_launch_playbook.py::test_human_attested_step_with_no_rule_policy_loads` |

**Uncovered scenarios: none.** All 27 are covered by at least one named
test. No scenario is reached through a `REMOVED` or `RENAMED` delta (this
change carries no such delta at all).

Tests that carry no scenario of their own, recorded here so their
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
- `D/test_launch_playbook.py::test_each_specified_track_value_is_accepted`
  — **new, this pass.** The permitted complement to scenario 5's rejection
  test; without it, an implementation that rejected every track (known or
  not) would still pass the rejection test alone.

## Level choice

The **six** coherence rules (five from the first pass, plus the new
gate-opening-mode rule) are exercised through `LaunchPlaybook`
**construction**, not through the YAML loader, because `tasks.md` 3.5 puts
them there ("Implement the six coherence rules as playbook construction
invariants") and construction is the smallest unit that can observe the
outcome. Three scenarios genuinely need the file boundary and only those
three sit in the infrastructure tier:

- **Scenario 25** — a malformed step cannot exist as a domain object (a
  reversed window is rejected at anchor construction), so only the loader
  can hold one; `tasks.md` 4.3 assigns it there.
- **Scenarios 3 and 4** — the opening modes are authored in data and are
  *also* checked by the sixth coherence rule at `LaunchPlaybook`
  construction (scenario 19) — but scenarios 3 and 4 ask what the *shipped*
  `v1` file actually declares, which only the loader, reading the real
  file, can answer.
- **Scenario 5 (new)**, additionally: the Track requirement is checked at
  `StepDefinition` construction (`tasks.md` 3.2), one layer below
  `LaunchPlaybook` — so its rejection is covered at that level in
  `D/test_launch_playbook.py`. Its loader-boundary counterpart
  (`I/test_playbook_loader.py::test_step_with_an_invalid_track_...`) is
  additional coverage per `tasks.md` 5.12.1, not required by the level
  rule alone, demonstrating that the fault survives the loader's
  aggregation together with a second, distinct violation — the same
  concern scenario 25 exists to cover, now exercised against the new fault
  type Track introduces.

**If the implementation puts the coherence rules in the loader instead of
in `LaunchPlaybook.__init__` (or the Track check outside `StepDefinition`
directly), the domain tests will fail on the absent behaviour rather than
on a defect in themselves.** That is a design conflict with `tasks.md` 3.2
/ 3.5, to be reported and settled — not resolved by weakening the tests.

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
| `InvalidPlaybookError` | raised by `StepDefinition` construction (new: the Track check), by `LaunchPlaybook` construction, *and* by the loader; `str(error)` names every offending step or gate | spec requires the naming; the type name is invented, and **this pass extends the assumption to cover the Track check too** — see Q9 |
| `OffsetAnchor(days=)`, `WindowAnchor(start=, end=)`, `OpenEndedAnchor(start=)`, `RecurringAnchor(cadence=)` | four variants with `.resolve(launch_date) -> range \| None` | `tasks.md` 2.2, 2.3 (shapes, not names) |
| `Gate.identifier` is a `str`, not an enum | required so that "a step declares a gate not in the sequence" is expressible at all | scenario 21 |
| `GateOpening.AUTOMATIC` / `.REQUIRES_CONFIRMATION` | two members | spec's two opening modes |
| `Hazard.NONE` / `.PROHIBITED_TACTIC` / `.COMPLIANCE_OBLIGATION` | three members | spec names the three wire values |
| `Track.STRATEGY` / `.FINANCE` / `.SETUP` / `.INVENTORY` / `.CREATIVE` / `.LISTING` / `.RANK` / `.PRICE` / `.PPC` / `.CUSTOMER` / `.EXTERNAL` / `.TRAFFIC` | twelve members, **new this pass** | spec now names the twelve wire values (`strategy`, `finance`, …); the Python member spelling is DERIVED by the same hyphen-to-underscore, upper-case convention already assumed for `Hazard` — see Q3 |

If a name differs, renaming it in the tests is a **fixture correction**, not
a weakening — but the correction should be recorded, because it means these
tests never constrained that name.

### Q3 — `Track`'s members, now named by the spec but not by Python identifier

The delta spec (as of this pass) lists all twelve wire values in full:
`strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`,
`price`, `ppc`, `customer`, `external`, `traffic`. This supersedes the
first pass's Q3 ("no artifact lists them"), which is why the earlier
`_any_track()` helper — kept as-is, still used by tests that need *some*
track and assert nothing about which — is no longer the only way a track
value is obtained: `test_each_specified_track_value_is_accepted` and
`test_track_outside_the_fixed_set_is_rejected`, added this pass, now name
tracks explicitly. What the spec still does not fix is the **Python member
name** for each — only the string. `getattr(Track, track_name.upper())` is
used to obtain it, assuming a direct upper-case mapping (`"strategy"` →
`Track.STRATEGY`); if the implementation spells members differently (e.g.
via `.value` matching the hyphenated forms `Track` doesn't need here, since
none of the twelve contain a hyphen), that is a fixture correction in the
new parametrized test, not a weakening.

### Q4 — The YAML document shape is undecided (`tasks.md` 4.1)

Affects four tests now (was two):
`I/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation`,
`::test_a_coherent_playbook_file_loads`, and, added this pass,
`::test_step_with_an_invalid_track_is_reported_alongside_a_coherence_violation`.
All build their input from `_GATES_YAML` / `_TWO_FAULTY_STEPS_YAML` /
`_INVALID_TRACK_AND_PROHIBITED_BLOCKING_YAML` in that file, which assume:

```yaml
version: v1
gates:  [{identifier, position, opening: automatic | requires-confirmation}]
steps:  [{identifier, gate, track, scope, timing_anchor: {kind, ...},
          binding, blocking, execution, hazard?, rule_policy?, provenance?}]
```

Loader tests were kept to the minimum that needs the file boundary
precisely to confine this invention. If the implemented shape differs, edit
the document constants — that is correcting the test's *input*, and is
distinct from changing what the test asserts about the resulting error,
which would be weakening it.

Note also: `track: inventory` / `track: ppc` / `track: customer` across
these YAML documents depend on Q3 continuing to hold (that these strings
are valid `Track` wire values, which the spec now fixes directly, so this
is a smaller risk than it was on the first pass).

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

Every existing test directory carries an `__init__.py`. The three test
directories under `tests/unit/products/` do **not**: `__init__.py` does not
match the dispatched test-path glob `tests/**/test_*.py`, and this pass
(like the first) writes nothing outside it. Collection was verified to work
without them (distinct module basenames, no collision), so this is a
consistency question for the project owner, not a defect.

### Q9 — NEW: the Track check raises at `StepDefinition` construction, not at `LaunchPlaybook` construction

`tasks.md` 3.2 places the "reject a track outside the fixed set of twelve"
check at `StepDefinition`'s own construction, distinct from the six
coherence rules `tasks.md` 3.5 places at `LaunchPlaybook` construction —
and design.md's "Coherence is enforced at load, and failure is fatal"
section enumerates exactly six rules, none of them the Track check. This
matters for level choice:
`test_track_outside_the_fixed_set_is_rejected` wraps the `_step(...)` call
itself in `pytest.raises`, not a subsequent `_playbook(steps=(step,))`
call — unlike the gate-reference rejection test, which needs a playbook's
gate sequence to judge against and so defers to `_playbook()`. If the
implementation instead defers the Track check to `LaunchPlaybook`
construction, this test will fail to raise where expected even though the
check exists — a design deviation from `tasks.md` 3.2 to report, not a test
defect, per the same reasoning as the Level choice section above.

A second assumption bundled into the same test: that an invalid track can
be *supplied* to `StepDefinition` as a raw string
(`track="not-a-recognised-track"`) at all, bypassing `Track`'s own type at
the call site. This is how Python typing works at runtime (a type hint is
not enforced), and is the only way to construct the fault the scenario
describes without going through the loader; if the implementation instead
makes this unreachable other than through the loader (e.g. `track` is
strictly `Track`-typed and validated only by the type system, with no
runtime check inside `StepDefinition` at all), only the loader-boundary
counterpart
(`test_step_with_an_invalid_track_is_reported_alongside_a_coherence_violation`)
would still exercise the scenario, and this domain-level test would be
reporting a design conflict rather than a code defect.

## Assertion classification

Recorded inline in every test — each assertion carries a `SPECIFIED`,
`DERIVED` or `DELIBERATELY UNTESTED` comment, and each test's docstring
quotes the scenario it comes from. Summary of what is *not* specified,
including what this pass added:

**Derived assertions, new this pass** (invented; no stated requirement
covers them):

- `test_each_specified_track_value_is_accepted`'s mapping from wire value to
  `Track` member name (Q3).
- `InvalidPlaybookError` as the type raised by the Track check at
  `StepDefinition` construction (Q9), by extension of the same assumption
  already made for the six coherence rules.
- The choice of `commit` (rather than any other gate) as the worked example
  for the gate-opening-mode rejection test, and `GateOpening.AUTOMATIC` as
  the wrong value authored for it — the spec fixes that `commit` requires
  confirmation, not which gate a test picks to demonstrate the rule with.
- The loader test's second, distinct fault for the invalid-track case
  (`prohibited-tactic` marked blocking) — chosen specifically to differ
  from the fault the existing malformed-step loader test already pairs
  with its first fault (an unknown gate), so as not to duplicate that
  test's evidence.

**Derived assertions carried over from the first pass** (see the previous
manifest for full detail, summarized here):

- Positions ascend with the gate sequence.
- `StepDefinition` exposes none of a probe list of ordering attribute
  names.
- The launch date and literal expected dates in timing-anchor tests.
- `Cadence.WEEKLY` as the cadence in the recurring-anchor test.
- `test_offset_one_is_the_day_after_launch`.
- The permitted-side tests for the automation and prohibited-tactic rules.
- `test_shipped_playbook_ships_with_no_step_definitions`.
- `str(error)` as the surface on which "the failure names the offending
  step or gate" is asserted.

**Deliberately untested**, recorded with reasons at the foot of each test
file (see those files for the full list; unchanged by this pass except
where noted):

- Gate position base (Q5).
- Immutability of the domain objects.
- That no domain module imports `yaml`, FastAPI or any I/O.
- Various unstated anchor edge cases (window `start == end`, open-ended
  anchor before launch, recurring anchor with an offset).
- The concrete type returned by `resolve()`.
- A dedicated single-step lookup on the playbook.
- Loader behaviour for a missing/unreadable/non-mapping file.
- Package-data presence in an installed build.
- The member sets of `Scope`, `Binding`, `ExecutionMode`, `Cadence` —
  **`Track`'s member set is no longer in this list**, since the spec now
  closes it and `test_each_specified_track_value_is_accepted` /
  `test_track_outside_the_fixed_set_is_rejected` together assert it.
- Exact error-message wording.

## Obsolete tests

**Not applicable.** Every delta in this change is `ADDED`, and no prior
`launch-playbook` spec exists, so no existing test can have been
superseded — including on this repeat pass: both new scenarios are
additions to the spec (a new requirement, and a sixth item in an existing
rejection list), not revisions of behavior any existing test already
covered. No search for bearing tests was performed and none was needed.

## Notes for whoever implements next

1. **These tests are red and will block `pre-commit`.** They were left
   plainly red — no `xfail`, no `importorskip` — matching the precedent set
   by `tests/unit/test_health.py`. Three checks are red until
   implementation lands: `pytest tests/unit` (3 collection errors), `mypy .`
   (4 `import-untyped` errors), and nothing else. **The commit strategy is
   the project owner's decision**, not one this pass made.
2. **Run `ruff check --fix` after implementation.** The edited files are
   currently `ruff`-clean, but `ruff`'s isort resolves first-party by
   checking whether the module exists under `src/` — so `commerce_ops.*`
   imports here are currently sorted as third-party. Once the modules exist
   they become first-party and want their own import block.
3. The tests do not tell you *how* to satisfy them beyond the API surface in
   Q1–Q3 and Q9. Where a name here is wrong for the design, change it in
   both places and note it; where an *assertion* is wrong, that is a spec
   question for `openspec-update-change`, not a test edit.
4. **This pass's three new tests are appended, not interleaved**, at the
   tail of `test_launch_playbook.py` (Track requirement's two tests placed
   in spec order, right after the *Gate sequence* section; the
   opening-mode rejection test placed inside the existing *An incoherent
   playbook is rejected at load time* section, next to the other
   gate-sequence-deviation tests it's most related to) and at the tail of
   `test_playbook_loader.py` (after the existing malformed-step test, in
   the same requirement section). Each file's module docstring says so.
