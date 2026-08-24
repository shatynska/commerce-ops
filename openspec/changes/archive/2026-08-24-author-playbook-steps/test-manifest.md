# Test manifest — author-playbook-steps

Written by `ai-toolkit:openspec-test-writer` from the change's delta specs,
before any implementation of the change. **Not an OpenSpec schema artifact** —
`openspec instructions apply` will not surface it; it has to be read on purpose.

Delta spec:
`openspec/changes/author-playbook-steps/specs/launch-playbook/spec.md`
(three ADDED requirements, ten scenarios, no MODIFIED / REMOVED / RENAMED).

Test command: `uv run pytest` (inside the uv-managed environment).

## Baseline

Scoped baseline, taken before any test was written:

```
uv run pytest tests/unit/launch tests/unit/shared/domain/test_discipline.py
178 passed, 0 failed
```

Scope: the whole `launch` unit tier plus the shared `Discipline` vocabulary —
every existing test that bears on the playbook, its loader, its domain types,
or the vocabulary the new tests quantify over. Nothing was failing beforehand,
so every failure reported below is attributable to the new tests.

After the new tests were added, `uv run pytest tests/unit tests/agents` reports
**18 failed, 567 passed** — the 18 failures are exactly the 18 new tests.

## Failure state of the new tests

All 18 fail today, and all 18 fail in **failure state 1** (`ai-toolkit:testing`):
the imports resolve, the loader runs, the assertions execute, and the shipped
`playbook_v1.yaml` produces a wrong value (`steps: []`). This is **not** an
absent-target failure — the loader, the domain types, the report use case and
the data file all exist.

Every test that quantifies over the step set routes through a `_shipped_steps()`
helper that fails loudly on an empty step list, so none of them can pass
vacuously while the file carries no steps.

The tests were additionally verified to *discriminate*: a scratch harness
(written outside the repository, in the session scratchpad, and not committed)
built a synthetic playbook satisfying `design.md`'s stated properties, patched
it in place of the shipped one, and ran all 18 — **0 failures**. So the current
failures come from the data, not from a defect in the tests.

## Files written

- `tests/unit/launch/infrastructure/test_shipped_playbook_steps.py` (new)
- `tests/unit/launch/application/test_shipped_playbook_undecided_policies.py` (new)

Nothing else was written. No existing test was edited, deleted, or disabled;
no implementation was written. **This pass adds tests and never subtracts.**

## Scenario accounting — 10 scenarios, 10 accounted for

| # | Requirement | Scenario | Covered by |
|---|---|---|---|
| 1 | The shipped playbook carries the authored step set | The shipped playbook loads with steps | `tests/unit/launch/infrastructure/test_shipped_playbook_steps.py::test_the_shipped_playbook_loads_with_a_non_empty_step_list`, `…::test_every_gate_has_at_least_one_step_attached` |
| 2 | " | BUILD THE LISTING is fully represented | `…test_shipped_playbook_steps.py::test_build_the_listing_is_fully_represented` |
| 3 | " | A step traces to its source row | `…test_shipped_playbook_steps.py::test_every_step_identifier_is_a_reference_row_id`, `…::test_every_step_provenance_carries_its_row_source_citation` |
| 4 | " | A gate-authored condition is not duplicated as a step | `…test_shipped_playbook_steps.py::test_metric_condition_restatements_do_not_appear_as_steps` |
| 5 | Every gate is held by at least one blocking step | No gate opens for free | `…test_shipped_playbook_steps.py::test_no_gate_opens_for_free` (+ `…::test_every_blocking_step_is_framework_bound` for the requirement's prose) |
| 6 | The authored set exercises the full step vocabulary | Anchor kinds are all present | `…test_shipped_playbook_steps.py::test_every_timing_anchor_kind_is_represented` |
| 7 | " | Every discipline appears | `…test_shipped_playbook_steps.py::test_every_discipline_is_represented` |
| 8 | " | Execution modes and the compliance hazard are represented | `…test_shipped_playbook_steps.py::test_every_execution_mode_is_represented`, `…::test_steps_requiring_a_rule_policy_carry_one`, `…::test_at_least_one_compliance_obligation_step_exists` |
| 9 | " | Prohibited tactics are present and never block | `…test_shipped_playbook_steps.py::test_prohibited_tactic_steps_exist_and_never_block` |
| 10 | " | Outstanding rule-policy decisions stay visible | `tests/unit/launch/application/test_shipped_playbook_undecided_policies.py::test_the_report_lists_exactly_the_shipped_steps_without_a_rule_policy` (+ `…::test_every_reported_step_is_human_attested`, `…::test_reported_rows_identify_the_shipped_steps_they_stand_for`) |

**Uncovered scenarios: none.** Every scenario in the delta is covered by at
least one named test.

Two requirement *statements* carry no scenario of their own and are covered
anyway, named here so the coverage is visible rather than incidental:

- "Blocking steps SHALL be `framework`-bound" → `…::test_every_blocking_step_is_framework_bound`.
- "a row that is a caution about a mistake SHALL remain an ordinary step" → `…::test_tos_risk_cautions_remain_ordinary_steps`.

## Which tests each task must turn green

`tasks.md` 2.1–2.4 author the steps; 3.1 is the test task this manifest
discharges. Selecting by task:

- **2.1–2.4 collectively** (the whole authored set): every test in both files.
  No single authoring subtask turns a whole test green on its own, because
  every assertion here is a property of the *complete* set — that is what the
  delta specifies. Run the two files as the check:

  ```
  uv run pytest tests/unit/launch/infrastructure/test_shipped_playbook_steps.py \
                tests/unit/launch/application/test_shipped_playbook_undecided_policies.py
  ```

- **2.2 specifically** (the BUILD THE LISTING groups) is the largest single
  contributor to `…::test_build_the_listing_is_fully_represented`, which will
  keep failing with a *shrinking* list of missing identifiers until 2.3 lands
  too. A shrinking failure list is progress, not a broken test.
- **2.5** (load once, resolve coherence faults): `…::test_the_shipped_playbook_loads_with_a_non_empty_step_list`
  and the pre-existing `tests/unit/launch/infrastructure/test_playbook_loader_completion.py::test_the_shipped_playbook_still_loads_coherently`.
- **3.1** is satisfied by these two files existing and being run.

## Assertion classification

**Specified** — traces to a delta scenario or requirement statement:

- non-empty step list; every gate has a step; every gate has a blocking step
- every BUILD THE LISTING row ID appears as a step identifier
- every step identifier is a reference-document row ID; every step's provenance
  is that row's source citation
- no metric-restatement row ID appears as a step identifier
- all four anchor kinds, all twelve disciplines, all three execution modes present
- every automated / AI-assisted step carries a rule policy
- at least one `compliance-obligation` step; at least one `prohibited-tactic`
  step; no `prohibited-tactic` step blocks
- every blocking step is `framework`-bound
- the undecided-rule-policies report lists exactly the policy-less steps, and
  every reported step is human-attested
- TOS-risk caution rows are not classified `prohibited-tactic`

**Specified by the delta's rule, enumerated by `design.md`** — the delta states
the rule, the design states which reference rows it selects. Recorded separately
because a reviewer reading only the delta will not find these six/two IDs there:

- the six metric-restatement IDs (`lp.inventory.040`, `lp.inventory.041`,
  `lp.strategy.033`, `lp.strategy.025`, `lp.ppc.048`, `lp.finance.036`) —
  `design.md` Decision 8, named by `tasks.md` 3.1
- the two TOS-risk caution IDs (`lp.setup.020`, `lp.inventory.018`) —
  `design.md` Decision 5

**Derived** — inferred, no stated requirement covers it:

- The reference document's row grammar (`**SOURCE:** … · **ID:** …` on one
  metadata line, areas as top-level `- <n>. <NAME>` items). The document is
  *parsed* rather than transcribed, so that the test asserts against the source
  the delta names rather than against a copy of it. A reformatting of
  `docs/reference/product-launch.md` would be a fixture defect in the parser
  (failure state 3), never grounds to weaken an assertion. Corroboration: the
  parser finds 358 unique IDs overall and 72 in BUILD THE LISTING, matching
  `design.md`'s own counts.
- Non-emptiness guards (`_shipped_steps()` asserting the step list is not
  empty; `assert rows != []` in the report tests). These exist to prevent a
  vacuous pass, not to assert an additional requirement.
- Grouping by anchor *type* (`OffsetAnchor`, `WindowAnchor`, `OpenEndedAnchor`,
  `RecurringAnchor`) as the way "grouped by timing-anchor kind" is observed.
  The model has no separate kind discriminator exposed in the existing tests.

**Deliberately untested** — identified and knowingly left uncovered, with the
reason (also recorded in-file, at the foot of each test module):

- The total step count (97), per-gate counts, and each reassigned area-3 row's
  gate. The delta states coverage properties, not a census, and `design.md`
  explicitly leaves gate/blocking choices as one-line YAML edits.
- Which particular rows are `prohibited-tactic` (design names three). The delta
  requires *at least one*, and requires cautions not to be tactics — the latter
  is tested; pinning the tactic set's membership would assert a curation
  decision the delta does not state.
- Each individual step's binding, scope, and timing anchor — specified per-step
  only by `design.md`'s table.
- The two authored rule-policy strings' wording (`design.md` Decision 7 calls
  them a conservative statement of current practice, not a specified value).
- The count of undecided steps (95 of 97). Set equality against the shipped
  data is asserted instead.
- That the other seven gates' subsets are "representative" in any sense beyond
  the vocabulary coverage the third requirement fixes — the delta settles the
  meaning of representative through that requirement, which is asserted directly.

## Obsolete tests — candidates for human confirmation

The dispatch expected none (the delta is all-ADDED). **One was found anyway**,
and its own author anticipated it.

| Test (runner-selectable) | Superseded by | Evidence |
|---|---|---|
| `tests/unit/launch/infrastructure/test_playbook_loader.py::test_shipped_playbook_ships_with_no_step_definitions` | ADDED requirement *The shipped playbook carries the authored step set* — "The shipped `v1` playbook SHALL carry authored step definitions, not an empty step list" | The test asserts `list(load_shipped_playbook().steps) == []`, the exact negation of the new requirement. Its own docstring says so: "if the import change lands, this assertion is superseded and should be removed with that change, not weakened to fit." |

**Candidate for human confirmation, not a conclusion.** It has not been edited,
deleted, or disabled by this pass. The recommended disposition — matching the
docstring's own instruction — is deletion as part of implementing this change,
not an edit of its assertion.

**Search bound.** The search covered the dispatched test-path glob
`tests/**/test_*.py` and nowhere else, by grepping for `load_shipped_playbook`,
`shipped`, and `.steps` across it. No earlier `test-manifest.md` was supplied to
the dispatch and none was sought. Within that bound, the one entry above is the
only bearing test: every other test touching step definitions builds its own
synthetic `LaunchPlaybook` and is unaffected by the shipped file's contents;
`test_playbook_loader_completion.py`'s shipped-file tests concern gate metric
conditions, which this change does not touch. **This is "none other found by
this search", not "no other exists".**

## Unresolved project questions

No channel exists to ask on (dispatched subagent), so each is recorded with the
assumption taken and the tests that depend on it.

1. **Is `provenance` the SOURCE citation verbatim, or a wrapped reference?**
   The delta says provenance "SHALL carry that row's source citation";
   `design.md` Decision 2 maps `SOURCE → provenance` "verbatim". *Assumption:*
   verbatim string equality. *Depends on it:*
   `…test_shipped_playbook_steps.py::test_every_step_provenance_carries_its_row_source_citation`.
   If the authoring wraps the citation (a document path, an `lp.` prefix, a
   joined multi-source form), that is a disagreement between `design.md` and
   the authored data to be **reported and settled**, not an assertion to loosen.

2. **Is `design.md`'s enumeration authoritative for the delta's two
   by-substance rules?** The delta states the rules; only `design.md` names the
   rows. *Assumption:* yes — `tasks.md` 3.1 names the same six IDs for the
   metric-restatement rule, which corroborates it. *Depends on it:*
   `…::test_metric_condition_restatements_do_not_appear_as_steps`,
   `…::test_tos_risk_cautions_remain_ordinary_steps`.

3. **Where do tests for shipped *data* belong in the tier layout?**
   `AGENTS.md` fixes `tests/unit/<module>/<layer>/`, and the shipped YAML lives
   in `launch/infrastructure/driven/`, but the existing shipped-file tests sit
   directly in `tests/unit/launch/infrastructure/` rather than in its `driven/`
   subdirectory. *Assumption:* follow the existing placement (alongside
   `test_playbook_loader.py`). The report-based scenario went to
   `tests/unit/launch/application/`, matching where the report's own tests live.
   *Depends on it:* the location of both new files (not any assertion).

4. **Should the report test assert the shipped playbook is *not* fully
   decided?** The delta's scenario has "while any human-attested step lacks a
   decided rule policy" as its precondition, and its closing note says a
   follow-up change amends this once every policy is decided. *Assumption:*
   assert non-emptiness now, so the test cannot pass by both sides being empty
   — and flag in-file that the assertion is superseded by that follow-up change
   rather than weakened. *Depends on it:*
   `…test_shipped_playbook_undecided_policies.py::test_the_report_lists_exactly_the_shipped_steps_without_a_rule_policy`,
   `…::test_every_reported_step_is_human_attested`.

5. **`tasks.md` 1.1's pre-authoring check is untestable here.** Whether a real
   launch has pinned `v1` is a property of a deployment's database, not of this
   source tree, and the fallback (ship as `v2`) would invalidate the version
   assertions in the *existing* `test_playbook_loader.py`. *Assumption:* the
   in-place `v1` edit proceeds. If the fallback is taken, these new tests still
   hold (none asserts a version), but `…test_playbook_loader.py::test_shipped_playbook_reports_its_version`
   and the shipped-file tests become a separate question to settle.

## Conventions read

`AGENTS.md` (authoritative: three-tier layout, `uv run pytest`, ruff/mypy/
import-linter, pre-commit runs `tests/unit` + `tests/agents`), `CLAUDE.md`
(a pointer to `AGENTS.md`), `README.md`. Skills loaded: `ai-toolkit:testing`
(the floor) and `ai-toolkit:python` (the stack idiom).

Verification run on the new files: `uv run ruff format`, `uv run ruff check`
(clean), `uv run mypy .` (clean, 196 source files).
