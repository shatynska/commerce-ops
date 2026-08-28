# Test manifest — `tidy-the-launch-pages-presentation`

Written by `openspec-test-writer` **before implementation**, from this
change's delta spec alone
(`specs/launch-admin/spec.md`) plus its `proposal.md`, `design.md` and
`tasks.md`. No implementation source was read: neither template, neither
route, and **not** `vocabulary.css` — the stylesheet is the thing three
of these scenarios are read against, so reading it would be shaping the
assertions to the code under test. Where a fact about the stylesheet's
present state was needed, it was taken from `design.md` — Context, which
records it, and the reliance is named below.

This file is **not** part of the OpenSpec schema. It will not appear
among `openspec instructions apply`'s context files and has to be opened
on purpose before implementing.

## Files written

Both are new; nothing existing was edited, deleted or disabled.

- `tests/unit/launch/infrastructure/driving/test_launch_admin_list_presentation.py`
  — requirements 1 and 2 (13 scenarios).
- `tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py`
  — requirement 3 (6 scenarios).

Placement follows `AGENTS.md` — Testing Strategy: `tests/unit/<module>/<layer>/`,
mirroring `launch/infrastructure/driving/`, in the commit-time tier. Both
sit inside the dispatched test-path glob `tests/**/test_*.py`.

## Baseline

Taken **before** any test here was written, full suite, at the worktree
root `/home/shatynska/projects/commerce-ops-launch-pages`:

```
uv run pytest
1356 passed, 0 failed, 102 skipped, 2 xfailed in 45.03s   (2026-08-28)
```

The 102 skips are the whole integration tier: no `DATABASE_URL`, no
`.env.test`, so the tier skips and says so. Nothing was failing
beforehand, so every failure reported below is attributable to the new
tests.

After the two files were added, same command:

```
12 failed, 1363 passed, 102 skipped, 2 xfailed in 45.98s  (2026-08-28)
```

1356 → 1363 passing: the seven new tests that pass on their first run
(see below). No previously passing test changed state.

Verification also run on the two new files: `uv run ruff check` clean,
`uv run ruff format --check` clean, `uv run mypy .` — "Success: no
issues found in 338 source files".

## Scenario accounting

The delta carries **19** `#### Scenario:` blocks across three ADDED
requirements. All 19 are accounted for below, each covered by a named
test; none is left uncovered.

### Requirement: The list's narrowing is one bar of peer controls (9)

All in `tests/unit/launch/infrastructure/driving/test_launch_admin_list_presentation.py`.

| Scenario | Test | First run |
| --- | --- | --- |
| The narrowing renders as one marked bar | `::test_the_narrowing_renders_as_one_marked_bar` | FAILS — no element carries `narrowing-bar` |
| The reveal control is distinguished, not amplified | `::test_the_reveal_control_is_distinguished_not_amplified` | FAILS — same |
| A gate narrowing is requested as it was | `::test_a_gate_narrowing_is_requested_as_it_was` | FAILS — same |
| A needs-attention narrowing is requested as it was | `::test_a_needs_attention_narrowing_is_requested_as_it_was` | FAILS — same |
| An empty narrowing parameter narrows nothing | `::test_an_empty_narrowing_parameter_narrows_nothing` | **PASSES** — regression guard, see below |
| The bar shows the narrowing it submitted | `::test_the_bar_shows_the_narrowing_it_submitted` | FAILS — no bar |
| A narrowing submitted from the bar keeps the reveal | `::test_a_narrowing_submitted_from_the_bar_keeps_the_reveal` | FAILS — no bar |
| Clearing a narrowing keeps the reveal | `::test_clearing_a_narrowing_keeps_the_reveal` | FAILS — no bar |
| The reveal control still reveals | `::test_the_reveal_control_still_reveals` | FAILS — no bar |

Seven of these nine fail through `_bar`, which reports the markers the
page does carry. That is failure state 1 (the code ran and produced a
value the requirement forbids), not an absent target: the page, its
route and its narrowing all exist and render. Once `narrowing-bar` is
marked, each will start failing (or passing) on its own assertion, and
the messages are written for that second pass.

### Requirement: A row names its product, and falls back to the raw identifier only when it must (4)

Same file.

| Scenario | Test | First run |
| --- | --- | --- |
| A resolved product's row carries no raw identifier | `::test_a_resolved_products_row_carries_no_raw_identifier` | FAILS — the row prints the UUID beside the name |
| A resolved product's row still opens its launch | `::test_a_resolved_products_row_still_opens_its_launch` | **PASSES** — regression guard |
| An unresolvable product's row still renders its identifier | `::test_an_unresolvable_products_row_still_renders_its_identifier` | FAILS — renders it **twice** |
| A wholesale identity outage still renders identifiers | `::test_a_wholesale_identity_outage_still_renders_identifiers` | FAILS — renders each twice |

The two "renders it twice" failures are the doubled-identifier defect
`tasks.md` 4.1 predicts in advance: the fallback label *is* the
identifier, and the `product-id` span prints it again.

### Requirement: The shared vocabulary carries rules for what these surfaces render (6)

All in `tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py`.

| Scenario | Test | First run |
| --- | --- | --- |
| The list's rows are marked as rows | `::test_the_lists_rows_are_marked_as_rows` | **PASSES** — regression guard |
| The detail page's rows are marked as rows | `::test_the_detail_pages_rows_are_marked_as_rows` | **PASSES** — regression guard |
| No fact is lost to the vocabulary | `::test_no_fact_is_lost_to_the_vocabulary` | **PASSES** — regression guard |
| The vocabulary carries a rule for each region | `::test_the_vocabulary_carries_a_rule_for_each_region` | FAILS — no rule reaches any of the five regions |
| No selector this change adds reaches another surface | `::test_no_selector_this_change_adds_reaches_another_surface` | **PASSES** — vacuously today, see below |
| A reused class name is never selected unqualified | `::test_a_reused_class_name_is_never_selected_unqualified` | **PASSES** — regression guard |

## Tests that pass on their first run

`ai-toolkit:testing` treats a first-run pass as an alarm where no
implementation exists. Seven tests here pass, and none of them is
evidence that anything was implemented — each covers a scenario the
delta **restates or protects** rather than introduces. They are recorded
as regression guards, not as coverage of new behaviour. Investigated
individually:

1. **An empty narrowing parameter narrows nothing.** The delta says
   outright this "is not a new licence: it is how the surface already
   reads both". It is stated so that a control which always submits its
   name is a legitimate way to offer a narrowing. Guards the
   checkbox-to-select substitution (`tasks.md` 2.4, 2.8).
2. **A resolved product's row still opens its launch.** The row opens
   its launch today; the guard is that removing the identifier from the
   row's facts (`tasks.md` 4.1) does not take the link with it, which is
   the one way that removal could break the row.
3. **The list's rows are marked as rows** and 4. **the detail page's
   rows are marked as rows.** Both templates already carry `launch-row`
   and `step-row` — `proposal.md` — Impact says the detail template
   needs no edit at all. The guard is that the markup edits in
   `tasks.md` groups 2 and 4 do not move a fact out of its marked row.
5. **No fact is lost to the vocabulary.** Nothing hides anything today
   (0 rules in the served sheet declare `display:none`,
   `visibility:hidden` or `content-visibility:hidden`). This is the
   requirement's negative obligation, and its whole purpose is to fail
   when group 3's rules land wrong.
6. **No selector this change adds reaches another surface.** Passes
   **vacuously** today: no rule in the served sheet reaches inside any
   of the five regions while naming a launch-only class, so the
   candidate set is empty (measured: 0 candidates, of 84 rules parsed).
   It acquires content the moment group 3 adds a rule.
7. **A reused class name is never selected unqualified.** Passes with
   zero offenders today, which is what makes the stronger whole-sheet
   reading safe (below).

A **failure** on 1–5 would mean the change broke something it was never
about. A failure on 6–7 would mean a new rule reached where it must not.

## Assertion classification

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. Each is also labelled inline in the test files;
this is the summary.

### Specified — traces to a stated requirement

- The literal marker tokens `narrowing-bar`, `row-action`, `quiet`,
  `launch-row`, `step-row`, given by the delta itself "because they are
  what a test is derived from".
- That the submit and the reveal control are the bar's action controls
  and carry `row-action`; that the reveal control also carries `quiet`
  and nothing else in the bar does; that the controls **selecting** a
  narrowing carry no action marker (requirement prose, a `SHALL NOT`).
- The query contract: `gate` for the gate narrowing, `attention=1` for
  the needs-attention narrowing, and empty-equals-absent.
- That the bar renders each active narrowing as the state of the control
  that sets it.
- That a narrowing submitted from the bar leaves a revealed set
  revealed, narrowed within itself and set apart; that the clear offer
  leaves it revealed; that the reveal control still reveals, marked and
  set apart.
- That a resolved row names its product and renders no identifier among
  its facts; that it still opens its launch; that a fallback row renders
  the identifier **once** (requirement prose); that a wholesale outage
  renders every row's identifier.
- That each launch sits in one `launch-row` holding its facts, each
  served step in one `step-row` holding its facts.
- That every fact the capability requires is present and none is
  rendered as not displayed.
- That the sheet carries a rule for each of the five regions; that no
  added selector reaches a sibling surface; that no reused name is
  selected unqualified.

### Derived — inferred, no stated requirement covers it

Each is labelled `DERIVED guard` in the code. They exist to stop a
specified assertion passing for the wrong reason, never to add a
constraint of their own:

- That the unnarrowed list renders rows at all, before comparing
  narrowed and unnarrowed row sets.
- That the empty-narrowing page is not the "matched nothing" page — the
  reading that makes the row-set equality mean *narrowed nothing*.
- That the bar's controls are not simply stuck in the narrowed state:
  each reads unset on an unnarrowed rendering.
- That the reveal really revealed before a narrowing is submitted over
  it, and that the chosen narrowing really matched nothing before the
  clear offer is used.
- That the resolvable row is still named when a sibling row falls back,
  so the page has not fallen back wholesale.
- That the launch pages render at least one class no sibling renders,
  without which the added-selector filter would select nothing and the
  test would be silently vacuous.
- That the served stylesheet parses to at least one rule and that
  **every** selector in it was readable (`_readable`): an unparseable
  selector fails the test rather than being skipped, so no check can
  quietly step over one.

### Deliberately untested — identified and knowingly left uncovered

- **That the bar occupies one line, that no control runs to the
  container's width, and that a control is sized to its word.** The
  requirement says so itself: not scenarios, "SHALL be confirmed by
  direct inspection of the rendered page" (`tasks.md` 6.1). No server
  response carries it.
- **That a row reads as a row.** Same, per the third requirement's own
  closing sentence (`tasks.md` 6.3, 6.4).
- **The legibility half of the negative obligation** ("less legible than
  the surface's ordinary text"). A dim is a computed style; only "not
  displayed" is asserted. This is the same line
  `test_playbook_admin_presentation_vocabulary.py` drew for the same
  vocabulary.
- **The journal region.** Excluded from the delta's own region list:
  `read_journal` is `None` until `add-launch-journal` lands, so no entry
  renders. What *is* asserted is that the empty-journal statement is
  still rendered and not hidden.
- **`tasks.md` 3.5's comment amendment** (the `.narrowing-bar` block's
  "Both narrow the same set."). A comment in a stylesheet is not
  observable from a response; it is a code-review obligation.
- **That the archive order is honoured** (`tasks.md` 7.1–7.3). A
  sequencing constraint on merging, not a behaviour of the surface.

## Obsolete tests

**Not applicable, and this is a stated reason rather than an empty
list.** The delta is `ADDED`-only — three ADDED requirements, no
`MODIFIED`, no `REMOVED`, no `RENAMED` — so no requirement is
superseded and no existing test can be asserting superseded behaviour.
Nothing was searched for, nothing is proposed for deletion, and no
existing test file was edited, deleted or disabled by this pass.

Two related observations that are **not** obsolescence, recorded so they
are not mistaken for it:

- `test_launch_admin_list.py` drives the needs-attention narrowing
  through `_attention_params`, which discovers the control from the
  rendered page, and reads a `<select>`'s selected option through
  `_form_of` / `_selected_of`. `proposal.md` — Impact and `tasks.md` 5.2
  both expect the checkbox-to-select substitution to be absorbed by
  that discovery rather than to break it. If it is not absorbed, the
  break is a **defect in the implementation or a fixture correction in
  that file's probes** — not a superseded assertion, and not licence to
  weaken what it asserts.
- `test_launch_admin_list.py::test_a_launch_whose_product_cannot_be_resolved_is_still_listed`
  and `::test_product_identities_cannot_be_read_at_all` assert the
  identifier is **present** on fallback rows. Requirement 2 keeps that
  true and only forbids the second rendering, so both stay correct as
  written.

## Unresolved project questions

Recorded rather than resolved silently; each names the assumption taken
and the tests that depend on it. No channel exists to ask on — this pass
runs as a dispatched subagent — so these surface here and in the report.

1. **No library skill covers stylesheet-level testing.**
   `ai-toolkit:testing` was loaded for the standard and
   `ai-toolkit:python` for the pytest idiom (both apply). Nothing in the
   library covers asserting over CSS selectors, so the parser and
   matcher in `test_launch_surface_vocabulary_rules.py`
   (`_parse_rules`, `_parse_complex`, `_matches`) are written from
   scratch against the selector subset an admin stylesheet uses.
   *Assumption:* a hand-rolled subset matcher is acceptable here rather
   than a new dependency (`tinycss2`, `cssselect`) — `design.md` —
   Non-Goals forbids a build step and adds no dependency, and
   `AGENTS.md` keeps the project pure-Python with one lockfile.
   *Depends on it:* the three stylesheet scenarios (17, 18, 19) and the
   stylesheet half of scenario 16. Unreadable selectors fail loudly
   rather than being skipped, so the assumption cannot degrade a check
   into a silent pass.

2. **What "carries the marker `X`" means.** Read as a **class token** on
   the element. The delta says only "marker"; `design.md` — Decision 1
   and `tasks.md` 2.2–2.3 spell `class="row-action quiet"`, and
   `test_playbook_admin_presentation_vocabulary.py` already established
   the class-token reading for this same vocabulary. *Correction point:*
   `_carries` in both files. *Depends on it:* scenarios 1, 2, 14, 15.

3. **What counts as "rendered as a fact".** Read as the row's visible
   text plus `title` / `aria-label` / `alt` / `value`; an `href`, an
   `id` and a `data-` attribute are excluded, because the requirement
   itself says the identifier "stays in the row's link target".
   *Correction point:* `_rendered_facts`. *Depends on it:* scenarios 10,
   12, 13.

4. **What counts as "a selector this change adds".** A test cannot read
   a diff, so scenario 18 operationalises it: a selector matching an
   element inside one of the five regions that either names a class the
   launch pages render and no sibling surface renders, or is a bare
   unqualified selector on one of the five reused names. *Blind spot:* a
   newly added rule keyed only on a token the siblings also render
   (`.mark`, `.row-action`) is not flagged. `tasks.md` 3.4 and 6.5 carry
   that, and 6.5 already says direct comparison "is the only check that
   can actually catch a stylesheet rule reaching a sibling surface".

5. **Scenario 19 is read over the whole sheet, not only over added
   selectors.** Strictly stronger than the scenario as written, and safe
   only because the sheet carries no such selector today. The basis is
   `design.md` — Context: of everything the two launch pages render, the
   vocabulary matches only `mark`, `container` and `form.narrowing`, and
   both pages render `gate`, `finished`, `empty`, `launch-date` and
   `current`. Confirmed empirically at zero offenders on the first run.
   *If that basis is ever wrong*, the test fails on a pre-existing
   selector, which is a finding about the sheet rather than about this
   change — and must not be answered by narrowing the test.

6. **Whether these tests may be committed while red.** They may not, on
   this project: `AGENTS.md` — Development Tooling runs the whole
   `tests/unit` + `tests/agents` tier at commit time, so the 12 failing
   tests block a commit until the implementation lands. *Assumption
   taken:* they land in the same commit as (or after) the
   implementation, which is how the dispatch framed it. Nothing here was
   weakened, skipped or `xfail`-marked to make an earlier commit
   possible.

7. **The render-date and module seams** are inherited wholesale from
   `test_launch_admin_list.py` / `test_launch_admin_detail.py`
   (`_SEAMS`, `_render_on`, `_install`), which the implemented module
   already satisfies. Correcting one is a fixture correction (failure
   state 3), not a licence to change what a test asserts.

## What the implementation must make pass

Run exactly these while working through `tasks.md`:

```
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_admin_list_presentation.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py
```

Task-group mapping:

- **Group 2 (the narrowing bar)** → the nine narrowing scenarios in
  `test_launch_admin_list_presentation.py`. 2.6 and 2.7 in particular
  are the two composition tests
  (`::test_a_narrowing_submitted_from_the_bar_keeps_the_reveal`,
  `::test_clearing_a_narrowing_keeps_the_reveal`).
- **Group 3 (the vocabulary rules)** →
  `::test_the_vocabulary_carries_a_rule_for_each_region` is the one that
  fails today; 3.4 is checked by
  `::test_no_selector_this_change_adds_reaches_another_surface`, 3.6 by
  `::test_no_fact_is_lost_to_the_vocabulary`, and Decision 5a's scoping
  by `::test_a_reused_class_name_is_never_selected_unqualified`.
- **Group 4 (the raw identifier)** → the four row-identity scenarios.
- **Group 5.2** stays as written: the whole existing
  `test_launch_admin_list.py` and `test_launch_admin_detail.py` suites
  must still pass, unedited.

Nothing in these files may be edited to reach green. Where an assertion
labelled SPECIFIED does not match, the code is wrong; where a probe,
seam or wording constant is wrong, that is a fixture correction and is
recorded as such.
