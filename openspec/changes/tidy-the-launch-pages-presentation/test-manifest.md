# Test manifest — `tidy-the-launch-pages-presentation`

Written by `openspec-test-writer`. **Replaced wholesale on a second
pass** (2026-08-28), because the change's delta grew from three
requirements to seven after the first pass ran: four were added at the
admin's direction and have since been through a third
`openspec-change-reviewer` pass (`design.md` — Decisions 7, 8, 9;
`tasks.md` 4a.5, 4b.7). A manifest states the change as it now stands,
so the earlier one is superseded rather than merged into; nothing it
recorded about the first three requirements is lost, and all of it is
restated below against the tests that still carry those scenarios.

Derived from this change's delta spec alone
(`specs/launch-admin/spec.md`) plus its `proposal.md`, `design.md` and
`tasks.md`. **No implementation source was read** on either pass:
neither template, neither route, not `launch_admin.py`, and not
`vocabulary.css` — the stylesheet is the thing four of these scenarios
are read against, so reading it would be shaping the assertions to the
code under test. Where a fact about the stylesheet's present state was
needed, it was taken from `design.md` — Context, which records it.

This file is **not** part of the OpenSpec schema. It will not appear
among `openspec instructions apply`'s context files and has to be opened
on purpose before implementing.

## The order this change ran in, and what that changes

For the first three requirements, tests came before implementation, as
`AGENTS.md` requires. For the four added later they did not: the
implementation is in the working tree ahead of them, at the admin's
explicit direction with the reviewer and test writer not re-run
(`design.md` — Decision 7). `ai-toolkit:testing` reads a first-run pass
oppositely in the two situations, and the difference governs how this
manifest is read:

- For an absent target, a pass is an alarm.
- For a target that already exists, a pass is the expected result and
  establishes that the code currently behaves as asserted.

Every test written on this second pass passes on its first run, and that
is the second case, not the fourth failure state. **A pass does not
establish that an assertion discriminates**, so each was separately
re-run against the same real response with the behaviour's evidence
removed. That record is under *Falsifiability*, below, and it is the
part of this manifest doing the work a red-then-green run would
otherwise have done.

## Files

Written on this pass — all new; nothing existing was edited, deleted or
disabled:

- `tests/unit/launch/infrastructure/driving/test_launch_list_last_completed_column.py`
  — *The list names the completion recorded most recently* (6 scenarios,
  plus 2 normative clauses of its prose that carry no scenario).
- `tests/unit/launch/infrastructure/driving/test_launch_step_outcome_tags.py`
  — *A step's outcome is rendered as a tag carrying its state* (7
  scenarios).
- `tests/unit/launch/infrastructure/driving/test_launch_detail_navigation.py`
  — *A launch's detail page offers the way back to the list* (1) and
  *The gate a reader navigated to is distinct from the gate the launch
  stands at* (1).

Written on the first pass and **not touched** by this one:

- `tests/unit/launch/infrastructure/driving/test_launch_admin_list_presentation.py`
  — requirements 1 and 2 (13 scenarios).
- `tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py`
  — requirement 3 (6 scenarios).

Existing and written by neither pass, but bearing on requirement 4 — see
*Its relationship to the tests written alongside the implementation*,
below:

- `tests/unit/launch/infrastructure/driving/test_launch_admin_last_completed.py`

Placement follows `AGENTS.md` — Testing Strategy:
`tests/unit/<module>/<layer>/`, mirroring `launch/infrastructure/driving/`,
in the commit-time tier. All sit inside the dispatched test-path glob
`tests/**/test_*.py`.

## Baseline

Taken **before** any test on this pass was written, at
`/home/shatynska/projects/commerce-ops-launch-pages`, on branch
`launch-detail-back-link` at `470d0b2`:

```
uv run pytest tests/unit tests/agents
1427 passed, 0 failed, 2 xfailed in 37.98s          (2026-08-28)
```

**Scoped, and the scope is stated:** the two commit-time tiers, which
are the tiers these files join and the ones `AGENTS.md` runs at commit
time. The integration tier was **not** run — no `DATABASE_URL` and no
`.env.test` are configured on this machine, so it would have skipped
rather than executed, and a skip is not a baseline. Nothing was failing
beforehand in the scope taken, so every result reported below is
attributable to the new tests.

After the three new files:

```
uv run pytest tests/unit tests/agents
1444 passed, 0 failed, 2 xfailed in 38.11s          (2026-08-28)
```

1427 → 1444: the seventeen new tests, all passing. No previously passing
test changed state.

Verification also run, whole-project, as `.pre-commit-config.yaml`
invokes each:

```
uv run ruff check .            All checks passed!
uv run ruff format --check .   728 files already formatted
uv run mypy .                  Success: no issues found in 351 source files
uv run lint-imports            Contracts: 18 kept, 0 broken.
```

## Scenario accounting

The delta carries **34** `#### Scenario:` blocks across seven ADDED
requirements. All 34 are accounted for below — 19 by the first pass, 15
by this one — each covered by a named test. **None is left uncovered.**

Two claims of the delta are recorded as deliberately untested rather
than as uncovered scenarios, because they are not scenarios: they appear
only in requirement prose that sends them to direct inspection. They are
listed under *Deliberately untested*.

### 1. The list's narrowing is one bar of peer controls (9) — first pass

All in `test_launch_admin_list_presentation.py`.

| Scenario | Test |
| --- | --- |
| The narrowing renders as one marked bar | `::test_the_narrowing_renders_as_one_marked_bar` |
| The reveal control is distinguished, not amplified | `::test_the_reveal_control_is_distinguished_not_amplified` |
| A gate narrowing is requested as it was | `::test_a_gate_narrowing_is_requested_as_it_was` |
| A needs-attention narrowing is requested as it was | `::test_a_needs_attention_narrowing_is_requested_as_it_was` |
| An empty narrowing parameter narrows nothing | `::test_an_empty_narrowing_parameter_narrows_nothing` |
| The bar shows the narrowing it submitted | `::test_the_bar_shows_the_narrowing_it_submitted` |
| A narrowing submitted from the bar keeps the reveal | `::test_a_narrowing_submitted_from_the_bar_keeps_the_reveal` |
| Clearing a narrowing keeps the reveal | `::test_clearing_a_narrowing_keeps_the_reveal` |
| The reveal control still reveals | `::test_the_reveal_control_still_reveals` |

### 2. A row names its product, and falls back to the raw identifier only when it must (4) — first pass

Same file.

| Scenario | Test |
| --- | --- |
| A resolved product's row carries no raw identifier | `::test_a_resolved_products_row_carries_no_raw_identifier` |
| A resolved product's row still opens its launch | `::test_a_resolved_products_row_still_opens_its_launch` |
| An unresolvable product's row still renders its identifier | `::test_an_unresolvable_products_row_still_renders_its_identifier` |
| A wholesale identity outage still renders identifiers | `::test_a_wholesale_identity_outage_still_renders_identifiers` |

### 3. The shared vocabulary carries rules for what these surfaces render (6) — first pass

All in `test_launch_surface_vocabulary_rules.py`.

| Scenario | Test |
| --- | --- |
| The list's rows are marked as rows | `::test_the_lists_rows_are_marked_as_rows` |
| The detail page's rows are marked as rows | `::test_the_detail_pages_rows_are_marked_as_rows` |
| No fact is lost to the vocabulary | `::test_no_fact_is_lost_to_the_vocabulary` |
| The vocabulary carries a rule for each region | `::test_the_vocabulary_carries_a_rule_for_each_region` |
| No selector this change adds reaches another surface | `::test_no_selector_this_change_adds_reaches_another_surface` |
| A reused class name is never selected unqualified | `::test_a_reused_class_name_is_never_selected_unqualified` |

### 4. The list names the completion recorded most recently (6) — this pass

All in `test_launch_list_last_completed_column.py`.

| Scenario | Test |
| --- | --- |
| The most recently recorded completion is named | `::test_the_most_recently_recorded_completion_is_named` |
| Recording time governs, not playbook order | `::test_recording_time_governs_not_playbook_order` |
| Only a completion counts | `::test_only_a_completion_counts` |
| A tie is broken in a stated direction | `::test_a_tie_is_broken_in_a_stated_direction` |
| A launch with nothing completed says so | `::test_a_launch_with_nothing_completed_says_so` |
| The column does not change what is listed | `::test_the_column_does_not_change_what_is_listed` |

Two normative clauses of the same requirement carry no scenario, are
stated as `SHALL`, and are readable from a response, so each has a test
of its own in the same file:

| Clause | Test |
| --- | --- |
| "The row SHALL name the step by its **name**, never by its identifier" | `::test_the_row_names_the_step_by_name_never_by_identifier` |
| "The recording time SHALL be rendered no coarser than the minute" | `::test_the_recording_time_is_rendered_no_coarser_than_the_minute` |

### 5. A step's outcome is rendered as a tag carrying its state (7) — this pass

All in `test_launch_step_outcome_tags.py`.

| Scenario | Test |
| --- | --- |
| An outcome renders as a tag carrying its state | `::test_an_outcome_renders_as_a_tag_carrying_its_state` |
| Unrecorded stays distinguishable from not started | `::test_unrecorded_stays_distinguishable_from_not_started` |
| A mark names what it is about | `::test_a_mark_names_what_it_is_about` |
| A recording time keeps its zone | `::test_a_recording_time_keeps_its_zone` |
| An outcome renders as words, not as its token | `::test_an_outcome_renders_as_words_not_as_its_token` |
| An unknown outcome still renders | `::test_an_unknown_outcome_still_renders` |
| Long evidence is bounded, not truncated | `::test_long_evidence_is_bounded_not_truncated` |

*A recording time keeps its zone* says "either page", so its one test
reads both — the detail page's provenance and the list's last-completed
column — rather than picking one.

*An unknown outcome still renders* is exercised at the page's mapping,
as its own note directs: the vocabulary is closed at six members, so an
out-of-vocabulary class (`_Postponed`) is recorded straight onto the
aggregate by the fixture. `record_step_outcome` restricts only which
*terminal* outcomes a hazard permits, so it is stored as given. No
member is added to `StepOutcome` and nothing outside the fixture can
reach the state.

### 6. A launch's detail page offers the way back to the list (1) — this pass

| Scenario | Test |
| --- | --- |
| The list is reachable from a launch's detail page | `test_launch_detail_navigation.py::test_the_list_is_reachable_from_a_launchs_detail_page` |

### 7. The gate a reader navigated to is distinct from the gate the launch stands at (1) — this pass

| Scenario | Test |
| --- | --- |
| The stylesheet distinguishes the two | `test_launch_detail_navigation.py::test_the_stylesheet_distinguishes_the_two` |

**Count reconciled:** 9 + 4 + 6 + 6 + 7 + 1 + 1 = **34**, which is the
number of `#### Scenario:` blocks in the delta.

## Its relationship to the tests written alongside the implementation

`test_launch_admin_last_completed.py` already exists and covers four of
requirement 4's six scenarios — the latest recording, recording time
over playbook order, only `Satisfied` counting, and the tie. It was
written **alongside the implementation** rather than derived from the
delta ahead of it, which `tasks.md` 4a.4 and the file's own docstring
record.

Its coverage was treated as suspect and every scenario derived again
independently. The finding is that it covers them **at a different
level**, not that it covers them wrongly:

- It exercises `_last_completed` and `_rows_for` over stand-in report
  objects. Every scenario is stated about what a **row** names.
- A choosing function returning the right answer while the page renders
  none of it satisfies no scenario in the delta. That file's own comment
  records a preview where exactly that happened — every launch read
  "Nothing completed yet" while the choosing was correct.

So the six scenarios are covered by the new page-level file, and the
existing file remains a genuine, non-duplicative unit-level pin on the
same reading. It is neither obsolete nor edited by this pass. Two of its
tests have no page-level counterpart because they are about the choosing
rather than the rendering
(`::test_an_instance_outcome_is_read_like_a_type`,
`::test_a_completion_with_no_recorded_time_is_not_named`), and they stay
where they are.

## Assertion classification

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. Each is labelled inline in the test files; this
is the summary, and the entries for requirements 1–3 are carried over
unchanged from the superseded manifest.

### Specified — traces to a stated requirement

Requirements 1–3 (first pass):

- The literal marker tokens `narrowing-bar`, `row-action`, `quiet`,
  `launch-row`, `step-row`.
- That the submit and the reveal control are the bar's action controls;
  that the reveal control also carries `quiet` and nothing else in the
  bar does; that the controls **selecting** a narrowing carry no action
  marker.
- The query contract: `gate`, `attention=1`, and empty-equals-absent.
- That the bar renders each active narrowing as the state of the control
  that sets it; that a narrowing submitted from the bar leaves a
  revealed set revealed and set apart; that the clear offer leaves it
  revealed; that the reveal control still reveals.
- That a resolved row names its product and renders no identifier among
  its facts; that it still opens its launch; that a fallback row renders
  the identifier **once**; that a wholesale outage renders every row's.
- That each launch sits in one `launch-row` and each served step in one
  `step-row`; that every fact the capability requires is present and
  none is rendered as not displayed; that the sheet carries a rule for
  each of the five regions; that no added selector reaches a sibling
  surface; that no reused name is selected unqualified.

Requirements 4–7 (this pass):

- That the row names the completion recorded **most recently**, and not
  the one recorded earlier; and that it says when.
- That "most recently" is by recording time, not playbook order — the
  case the two candidate readings disagree on.
- That only a `Satisfied` outcome counts, excluding both the unresolved
  outcomes and the terminal-but-not-completed ones (`Refused`,
  `NotApplicable`) the requirement excludes by name.
- That a same-instant tie is broken toward the **later** step in the
  report's order, on every rendering.
- That a launch with nothing completed states the absence and names no
  step.
- That the launches enumerated, their order and any active narrowing are
  what they would be without the column.
- That the row names the step by name, never by identifier; that the
  recording time is no coarser than the minute.
- `outcome-tag` on the element the outcome is rendered within, and
  `state-` plus the outcome's own name lowercased on the element holding
  the step — asserted over **every** member of the vocabulary the
  fixture can record, and computed from the domain classes rather than
  restated.
- That a step recorded not-started and a step with nothing recorded
  differ in words **and** carry `state-notstarted` against
  `state-unrecorded`, never one shared marker.
- That each launch mark names the thing it is a fact about: the gate for
  awaiting confirmation, the date for the launch date's own mark.
- That a recording time on either page carries the zone it is read in.
- That the vocabulary's token is not what the page renders.
- That an outcome the page holds no wording for renders under its own
  name.
- That the whole of a several-sentence evidence is present, and that no
  ellipsis stands where the rest of it should be.
- That the detail page offers the list in one action without scripting,
  to a destination carrying no query.
- That the served stylesheet carries a rule applying to the navigated-to
  gate group, and that it does not share a declaration block with the
  rule marking the gate the launch stands at.

### Derived — inferred, no stated requirement covers it

Labelled `DERIVED` or `DERIVED guard` in the code. Almost all exist to
stop a specified assertion passing for the wrong reason, never to add a
constraint of their own.

Requirements 1–3, carried over: that the unnarrowed list renders rows at
all; that the empty-narrowing page is not the "matched nothing" page;
that the bar's controls are not stuck in the narrowed state; that the
reveal really revealed and the narrowing really matched nothing before
the clear offer is used; that the resolvable row is still named when a
sibling falls back; that the launch pages render at least one class no
sibling renders; that the served stylesheet parses to at least one rule
and that **every** selector in it was readable.

This pass:

- That a rendered time is read as an `H:MM` token (`_TIME_TOKEN`), so
  "no coarser than the minute" is observable without knowing the zone
  the page renders in.
- That "the report's own order" is the served order — gate-sequence
  order, then the authored order within a gate — computed from the
  playbook rather than restated, which is what `design.md` means by "the
  authored order `launch-playbook` obliges".
- That a zone designator is `UTC`, `GMT`, a bare `Z`, a numeric offset,
  an abbreviation ending in `T`, or an IANA name, rendered on the
  element carrying the time or on its parent (`_ZONE`,
  `_time_and_zone`).
- That "the element holding the step" is the step's own row, or the
  nearest ancestor holding no *other* served step (`_state_element`).
- The **words** each outcome may be rendered as (`_WORDING`), and the
  wording of the nothing-completed statement
  (`_WORDS["nothing_completed"]`). A bare em-dash is deliberately
  excluded from the latter: an em-dash in the cell *is* the empty cell
  the requirement forbids.
- That "a rule applying to the gate group a reader has navigated to" is
  a rule whose selector uses `:target` — CSS offers no other mechanism
  for "the element the reader navigated to", so this is derived by
  elimination rather than by preference.
- That "distinct" additionally means the two do not declare *exactly*
  the same thing, applied **only** where a current-gate rule reaches a
  gate group — the same element the navigated-to rule reaches. A rule
  marking a *sequence entry* is excluded, since the two never render on
  one element and requiring them to differ would be a constraint nobody
  stated.
- Two guards in the gate test: that the sequence's entries really are
  anchors into the page (without a target, a `:target` rule could never
  apply), and that a current-gate mark and a rule for it exist at all
  (without both, "distinct from" has nothing to be distinct from).
- Two guards in the column test: that the populated world really names a
  completion and the unpopulated one really names none. **These caught a
  defect in the test itself** — see *Defects this pass found in its own
  tests*.

### Deliberately untested — identified and knowingly left uncovered

- **That the bar occupies one line, that no control runs to the
  container's width, and that a control is sized to its word.** Not
  scenarios; the requirement says "SHALL be confirmed by direct
  inspection of the rendered page" (`tasks.md` 6.1).
- **That a row reads as a row.** Same (`tasks.md` 6.3, 6.4).
- **The legibility half of the negative obligation** ("less legible than
  the surface's ordinary text"). A dim is a computed style; only "not
  displayed" is asserted.
- **The journal region.** Excluded from the delta's own region list:
  `read_journal` is `None` until `add-launch-journal` lands. What *is*
  asserted is that the empty-journal statement is rendered and not
  hidden.
- **That the evidence is laid out within a bounded measure.** A rendered
  width, which no response carries — the requirement's own sentence
  sends it to inspection. Its testable half (the whole evidence present,
  untruncated) *is* covered.
- **That the two gate treatments read as different at a glance.** Same:
  the requirement states it and sends it to inspection. What a response
  carries — that the rule exists and is a separate rule — is covered.
- **`tasks.md` 3.5's comment amendment.** A comment in a stylesheet is
  not observable from a response; a code-review obligation.
- **That the archive order is honoured** (`tasks.md` 7.1–7.3). A
  sequencing constraint on merging, not a behaviour of a surface.

## Falsifiability

Every test written on this pass passes on its first run, because the
implementation is already there. That establishes the code behaves as
asserted and nothing about whether the assertion could fail — the exact
defect two earlier review passes on this change caught.

So each predicate was re-run against the **same real response** with the
behaviour's evidence removed from it — a mutation applied to the
response text held in memory, touching nothing in the repository. A
predicate that holds on the real response and fails on the mutant
discriminates; one that holds on both asserts nothing.

**25 of 25 predicates flip.** The mutations, by requirement:

- **R4** — swap the two completed steps' names (does the row really name
  the later one?); render one fixed time on every row (does the time
  track the recording?); name the step further along the playbook (is
  the reading recording-time?); name the blocked step and then the
  not-applicable step (are non-completions really excluded?); break the
  tie the other way; empty the nothing-completed cell; append the
  identifier to the row; round every time to the hour.
- **R5** — rename the `outcome-tag` class; rename `state-satisfied`;
  give the not-started and the unrecorded step one marker, and then one
  wording; render the `NotStarted` token as text; truncate the evidence
  span with an ellipsis; strip the zone from the rendered time, on each
  page; blank the unknown outcome's tag; reduce each mark to the state
  alone ("Awaiting confirmation", "At risk").
- **R6** — remove every anchor to the list; replace the back link's
  `href` with an `hx-get`.
- **R7** — delete every `:target` rule from the served stylesheet; add a
  selector group pairing the navigated-to selector with the current-gate
  selector on one declaration block.

The last of those is the one worth naming: two selectors in one group
are one rule and give the two gates one treatment, which is how this
requirement is most plausibly satisfied on paper and defeated in fact.
The test's primary reading of "distinct" is aimed at exactly it.

The harness is not committed — it is a scratch script, not a test, and a
test asserting over mutated HTML would assert about the mutation rather
than about the page.

## Defects this pass found in its own tests

Recorded because a manifest that only reports success is not evidence of
care, and because both were caught by DERIVED guards rather than by
review.

1. **The two-worlds comparison was a page against itself.** The test for
   *The column does not change what is listed* built two surfaces from
   one `monkeypatch`, so the second world's seams replaced the first's
   on the same module object before the first had been read. Both
   renderings came from the same store, the row sets compared equal, and
   the test passed having observed nothing. The guard asserting the
   populated world actually names a completion failed and exposed it.
   Each world is now rendered inside its own
   `pytest.MonkeyPatch.context()` and its responses captured before the
   next is built.
2. **The at-risk fixture was never at risk.** The mark-wording test
   built a launch whose only overdue step was non-blocking, so no
   at-risk mark was rendered and the locator failed by name. Corrected
   by making the overdue step blocking — a fixture correction (failure
   state 3), which establishes nothing about the code and is recorded as
   such rather than absorbed silently.

## Obsolete tests

**Not applicable, and this is a stated reason rather than an empty
list.** The delta is `ADDED`-only — seven ADDED requirements, no
`MODIFIED`, no `REMOVED`, no `RENAMED` — so no requirement is superseded
and no existing test can be asserting superseded behaviour. Nothing is
proposed for deletion or rewriting, and **no existing test file was
edited, deleted or disabled by either pass.** This pass adds tests and
subtracts none.

Four related observations that are **not** obsolescence, recorded so
they are not mistaken for it:

- `test_launch_admin_last_completed.py` covers four of requirement 4's
  scenarios at the choosing rather than at the row. It is not superseded
  by the new page-level file: the two observe different things, and the
  section above sets out why both stand.
- `test_launch_admin_list.py` drives the needs-attention narrowing
  through `_attention_params`, discovering the control from the rendered
  page. If the checkbox-to-select substitution ever stops being absorbed
  by that discovery, the break is a defect in the implementation or a
  fixture correction in that file's probes — not a superseded assertion.
- `test_launch_admin_list.py::test_a_launch_whose_product_cannot_be_resolved_is_still_listed`
  and `::test_product_identities_cannot_be_read_at_all` assert the
  identifier is **present** on fallback rows. Requirement 2 keeps that
  true and forbids only the second rendering.
- `test_launch_admin_detail.py` asserts every fact the detail page
  renders about a step. Requirement 5 re-lays those facts out and
  removes none, and that suite passes unedited alongside the new one.

## Unresolved project questions

Recorded rather than resolved silently; each names the assumption taken
and the tests that depend on it. No channel exists to ask on — this pass
runs as a dispatched subagent — so these surface here and in the report.

1. **No library skill covers stylesheet-level testing.**
   `ai-toolkit:testing` supplies the standard and `ai-toolkit:python`
   the pytest idiom; neither covers asserting over CSS selectors. The
   parser and matcher in `test_launch_detail_navigation.py` are
   therefore hand-rolled against the selector subset an admin stylesheet
   uses, following the ones `test_launch_surface_vocabulary_rules.py`
   established on the first pass. *Assumption:* a hand-rolled subset
   matcher is acceptable rather than a new dependency (`tinycss2`,
   `cssselect`) — `design.md` — Non-Goals adds no dependency and
   `AGENTS.md` keeps the project pure-Python with one lockfile.
   *Depends on it:* requirement 7's scenario, and requirement 3's three
   stylesheet scenarios from the first pass. Unreadable selectors fail
   loudly rather than being skipped.
2. **What "carries the marker `X`" means.** Read as a **class token**,
   the reading `test_playbook_admin_presentation_vocabulary.py`
   established for this same vocabulary. *Correction point:* `_carries`
   in each file. *Depends on it:* requirement 1's first two scenarios,
   requirement 3's first two, and requirement 5's first two.
3. **What counts as "rendered as a fact"** (first pass). Read as the
   row's visible text plus `title` / `aria-label` / `alt` / `value`;
   `href`, `id` and `data-` excluded. *Correction point:*
   `_rendered_facts`. *Depends on it:* requirement 2's scenarios.
4. **What counts as "a selector this change adds"** (first pass).
   Operationalised, since a test cannot read a diff; the blind spot is a
   rule keyed only on a token the siblings also render, carried by
   `tasks.md` 3.4 and 6.5.
5. **How the project wants a recording time's zone read.** No convention
   is recorded anywhere in `AGENTS.md` or `CLAUDE.md` for how a
   timestamp is rendered on an admin surface, and the delta fixes only
   that a zone is carried, never in what form. *Assumption taken:* the
   `_ZONE` alternation above, deliberately broad. *Depends on it:*
   *A recording time keeps its zone*, on both pages. A page that names
   its zone some other way fails here as a fixture correction, not as a
   defect.
6. **Whether an outcome outside the vocabulary may be put on the
   aggregate by a fixture.** The delta directs that the unknown-outcome
   obligation be "exercised at the mapping, not through a launch", but
   names no mechanism, and the project records no convention on reaching
   past a domain's own vocabulary in a test. *Assumption taken:* record
   `_Postponed` straight onto the aggregate, which `record_step_outcome`
   accepts because it restricts only terminal outcomes. The alternative
   — probing the page module for its mapping by name — was rejected as
   more fragile and more coupled to the implementation's shape.
   *Depends on it:* *An unknown outcome still renders*.
7. **Whether these tests may be committed as they stand.** They may:
   they pass, and `AGENTS.md` runs the whole `tests/unit` +
   `tests/agents` tier at commit time. Nothing here was weakened,
   skipped or `xfail`-marked.
8. **The render-date and module seams** are inherited wholesale from
   `test_launch_admin_list.py` / `test_launch_admin_detail.py`
   (`_SEAMS`, `_render_on`, `_install`). Correcting one is a fixture
   correction (failure state 3), not a licence to change what a test
   asserts.

## What the implementation must make pass

Run exactly these:

```
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_admin_list_presentation.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_list_last_completed_column.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_step_outcome_tags.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_detail_navigation.py
```

Task-group mapping:

- **Group 2 (the narrowing bar)** → the nine narrowing scenarios in
  `test_launch_admin_list_presentation.py`.
- **Group 3 (the vocabulary rules)** →
  `test_launch_surface_vocabulary_rules.py`, whole file.
- **Group 4 (the raw identifier)** → the four row-identity scenarios in
  `test_launch_admin_list_presentation.py`.
- **Group 4a (the last-completed column)** →
  `test_launch_list_last_completed_column.py`, whole file. 4a.2's three
  readings are `::test_only_a_completion_counts`,
  `::test_recording_time_governs_not_playbook_order` and
  `::test_a_tie_is_broken_in_a_stated_direction`; 4a.3's absence
  statement is `::test_a_launch_with_nothing_completed_says_so`.
- **Group 4b (the state treatment)** →
  `test_launch_step_outcome_tags.py`, whole file, plus
  `test_launch_detail_navigation.py` for 4b.8 and 4b.9. 4b.2 is
  `::test_unrecorded_stays_distinguishable_from_not_started`; 4b.3 is
  `::test_an_outcome_renders_as_words_not_as_its_token` and
  `::test_an_unknown_outcome_still_renders`; 4b.4's no-truncation half
  is `::test_long_evidence_is_bounded_not_truncated`; 4b.10 is
  `::test_a_mark_names_what_it_is_about`; 4b.11 is
  `::test_a_recording_time_keeps_its_zone`.
- **Group 5.2** stays as written: the whole existing
  `test_launch_admin_list.py` and `test_launch_admin_detail.py` suites
  must still pass, unedited. They do.
- **Group 5.1a** is what this pass discharges.

Nothing in these files may be edited to reach green. Where an assertion
labelled SPECIFIED does not match, the code is wrong; where a probe,
seam or wording constant is wrong, that is a fixture correction and is
recorded as such.
