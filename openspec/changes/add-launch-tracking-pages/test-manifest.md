# Test manifest — `add-launch-tracking-pages`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-27, before any
implementation of this change existed. **Not an artifact the OpenSpec
schema knows about**, so it does not appear among the context files
`openspec instructions apply` surfaces — it has to be read on purpose.

This pass **adds tests and never subtracts**. No existing test file was
edited, deleted or disabled, and nothing outside `tests/**/test_*.py` was
written except this manifest.

## Baseline

`uv run pytest` at `/home/shatynska/projects/commerce-ops-launch-pages`,
taken before the first test below was written:

```
1133 passed, 0 failed, 94 skipped in 40.89s
```

The 94 skips are the whole integration tier: `DATABASE_URL` is unset and
neither `.env.test` nor `.env` carries it, so `tests/integration` skips
by design. **Full-suite in name, unit + agents in effect** — no claim
below rests on an integration-tier result.

After this pass, the same command reports:

```
61 failed, 1141 passed, 94 skipped
```

`1141 = 1133 + 8`: eight of the new tests pass on their first run, all of
them in the "target already exists" half described below. The 61
failures are all new tests; **no pre-existing test changed state**.

`uv run ruff check`, `uv run ruff format --check`, `uv run mypy .` and
`uv run lint-imports --config .importlinter` are all clean over the new
files.

## Files written

| File | Covers |
| --- | --- |
| `tests/unit/launch/application/test_launch_report_step_facts.py` | `launch-instance`, 5 requirements / 12 scenarios |
| `tests/unit/launch/infrastructure/driving/test_launch_admin_list.py` | `launch-admin` R1–R3, 28 scenarios |
| `tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py` | `launch-admin` R4–R9, 25 scenarios |
| `tests/unit/launch/infrastructure/driving/test_admin_header_names_every_surface.py` | `playbook-admin`, the 2 scenarios the delta adds |
| `tests/unit/access/infrastructure/driving/test_roster_header_names_every_surface.py` | `roster-admin`, the 2 scenarios the delta adds |

Tier placement follows `AGENTS.md`: application-layer behaviour under
`tests/unit/<module>/application/`, driving adapters under
`tests/unit/<module>/infrastructure/driving/`. Nothing here touches real
I/O, so nothing belongs in `tests/integration`.

No `conftest.py` was added: the dispatched test-path glob is
`tests/**/test_*.py`, which a `conftest.py` does not match. The HTML-tree
and header helpers are therefore duplicated across the adapter files
rather than shared, which is also the convention the existing suite
records ("this project shares no test-helper module between test files").

## Expected first-run state, per file

- **`test_launch_report_step_facts.py` — two halves.** The eight
  scenarios of *states whether each step blocks*, *states whether each
  step is overdue* and *carries one entry per served step, in the served
  order* pin behaviour the report already has (`tasks.md` 1.4) and
  **pass on first run**, which is the expected result in the
  target-exists situation. The four scenarios of *names each step* and
  *places each step in its gate and names the gate sequence* fail on an
  absent target: `ReportedStep` carries neither `name` nor `gate` and
  `LaunchReport` names no gate sequence.
- **Every other file** fails on an absent target:
  `commerce_ops.launch.infrastructure.driving.launch_admin` does not
  exist. Each resolves it by name (`_page_module()` / `_launch_module()`)
  so that every scenario fails on its own with a readable message rather
  than the file failing to collect — a collection error would establish
  nothing about any individual assertion.
- **Three tests are additionally blocked on another change** — see
  *Blocked coverage*.

## Scenario accounting

75 scenarios in the delta specs; 75 accounted for below. 72 covered by a
named test written here, 6 of those in the two MODIFIED requirements'
*new* scenarios; 6 further scenarios (the MODIFIED requirements' carried-
forward ones) covered by existing tests named below; 0 uncovered.

> 53 (`launch-admin`) + 12 (`launch-instance`) + 6 (`playbook-admin`) +
> 4 (`roster-admin`) = 75. Of the 10 in the two MODIFIED requirements, 4
> are new (tests written here) and 6 are carried forward verbatim (tests
> already exist).

### `launch-instance` — `tests/unit/launch/application/test_launch_report_step_facts.py`

| Scenario | Test | First run |
| --- | --- | --- |
| A step entry carries its name | `test_every_step_entry_carries_the_served_playbooks_name` | fails, absent field |
| The name follows the served playbook | `test_a_step_entry_carries_the_name_the_authoring_write_left` | fails, absent field |
| A step entry states whether it blocks | `test_every_step_entry_states_whether_it_blocks_its_gate` | **passes** |
| An overdue non-blocking step is reported overdue | `test_an_overdue_non_blocking_step_on_a_healthy_launch_is_reported_overdue` | **passes** |
| An overdue blocking step is reported overdue on its own entry | `test_the_overdue_blocking_step_the_at_risk_evaluation_names_is_marked` | **passes** |
| A step resolved under its own hazard is not overdue | `test_a_step_resolved_under_its_own_hazard_is_not_overdue` | **passes** |
| A step with no due period is not overdue | `test_no_step_is_overdue_on_a_launch_with_no_date` | **passes** |
| A recurring-anchor step on a dated launch is not overdue | `test_a_recurring_anchor_step_on_a_dated_launch_is_not_overdue` | **passes** |
| A step entry carries its gate | `test_every_step_entry_carries_the_gate_the_playbook_attaches_it_to` | fails, absent field |
| The report names the gates in order | `test_the_report_names_the_gate_sequence_in_order` | fails, absent field |
| The report carries an entry for a step with no recorded outcome | `test_a_served_step_with_no_recorded_outcome_still_gets_an_entry` | **passes** |
| Step entries arrive in the served playbook's order | `test_step_entries_arrive_in_the_served_playbooks_order` | **passes** — but read *Finding 1* |

### `launch-admin` R1–R3 — `tests/unit/launch/infrastructure/driving/test_launch_admin_list.py`

All fail on the absent module.

| Scenario | Test |
| --- | --- |
| Every permitted launch is listed | `test_every_permitted_launch_is_listed_with_its_facts` |
| The list is evaluated as of the day it is rendered | `test_the_list_is_evaluated_as_of_the_day_it_is_rendered` |
| A row opens its launch | `test_a_row_opens_its_launch` |
| A row opens its launch however many are shown | `test_a_row_opens_its_launch_however_many_are_shown` |
| A restricted scope lists only its launches | `test_a_restricted_scope_lists_only_its_launches` |
| A launch with no date renders the absence | `test_a_launch_with_no_date_renders_the_absence` |
| A finished launch leaves the default view | `test_a_finished_launch_leaves_the_default_view` |
| A finished launch stays reachable | `test_a_finished_launch_stays_reachable_and_is_marked_by_its_stage` |
| Revealing when nothing is out of play says so | `test_revealing_when_nothing_is_out_of_play_says_so` |
| An unresolvable product's launch stays in the default view | `test_an_unresolvable_products_launch_stays_in_the_default_view` |
| A launch at the final gate is still listed | `test_a_launch_at_the_final_gate_is_still_listed` |
| Product identities cannot be read at all | `test_product_identities_cannot_be_read_at_all` |
| A launch whose product cannot be resolved is still listed | `test_a_launch_whose_product_cannot_be_resolved_is_still_listed` |
| No launches renders a page, not an error | `test_no_launches_renders_a_page_not_an_error` |
| A narrowing's empty state governs when both apply | `test_a_narrowings_empty_state_governs_when_both_apply` |
| A default view emptied by the filter says which state it is in | `test_a_default_view_emptied_by_the_filter_says_which_state_it_is_in` |
| An at-risk launch precedes one awaiting confirmation | `test_an_at_risk_launch_precedes_one_awaiting_confirmation` |
| Revealed rows order most recent first | `test_revealed_rows_order_most_recent_first` |
| Launches no longer in play stand outside the bands | `test_launches_no_longer_in_play_stand_outside_the_bands` |
| A launch in both bands appears once | `test_a_launch_in_both_bands_appears_once` |
| Unchanged data renders in the same order | `test_unchanged_data_renders_in_the_same_order` |
| Arrival order does not reach the page | `test_arrival_order_does_not_reach_the_page` |
| A launch with no date sorts last within its band | `test_a_launch_with_no_date_sorts_last_within_its_band` |
| A gate narrowing hides without removing | `test_a_gate_narrowing_hides_without_removing` |
| A narrowing reaches the revealed rows too | `test_a_narrowing_reaches_the_revealed_rows_too` |
| Narrowing to launches needing attention | `test_narrowing_to_launches_needing_attention` |
| Narrowing preserves the attention order | `test_narrowing_preserves_the_attention_order` |
| A narrowing matching nothing says so | `test_a_narrowing_matching_nothing_says_so` |

### `launch-admin` R4–R9 — `tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py`

All fail on the absent module; the three journal ones are additionally
blocked (see *Blocked coverage*).

| Scenario | Test |
| --- | --- |
| The page names its product | `test_the_page_names_its_product` |
| An unresolvable product falls back to its identifier | `test_an_unresolvable_product_falls_back_to_its_identifier` |
| The gate sequence shows the launch's position | `test_the_gate_sequence_shows_the_launchs_position` |
| A launch whose playbook serves no step says so | `test_a_launch_whose_playbook_serves_no_step_says_so` |
| Steps are grouped by gate and the page lands on the current one | `test_steps_are_grouped_by_gate_and_the_page_lands_on_the_current_one` |
| A step renders its name, not only its identifier | `test_a_step_renders_its_name_not_only_its_identifier` |
| A recorded step renders its provenance | `test_a_recorded_step_renders_its_provenance` |
| An unrecorded step is distinct from one recorded not-started | `test_an_unrecorded_step_is_distinct_from_one_recorded_not_started` |
| A step renders its discipline, whether it blocks, and its due period | `test_a_step_renders_its_discipline_blocking_flag_and_due_period` |
| The page is evaluated as of the day it is rendered | `test_the_detail_page_is_evaluated_as_of_the_day_it_is_rendered` |
| A step the report does not mark overdue is not rendered overdue | `test_a_step_the_report_does_not_mark_overdue_is_not_rendered_overdue` |
| An overdue step is marked | `test_an_overdue_step_is_marked` |
| An entry names what occurred, when, and what caused it | `test_a_journal_entry_names_what_occurred_when_and_what_caused_it` — **blocked** |
| Entries render newest first | `test_journal_entries_render_newest_first` — **blocked** |
| An empty journal says so | `test_an_empty_journal_says_so` — **blocked** |
| The pages present no launch-changing control | `test_the_pages_present_no_launch_changing_control` |
| A product with no launch is refused as absent | `test_a_product_with_no_launch_is_refused_as_absent` |
| A forbidden launch is refused identically | `test_a_forbidden_launch_is_refused_identically` |
| A launch whose product cannot be resolved is served | `test_a_launch_whose_product_cannot_be_resolved_is_served` |
| An unknown identifier is refused identically | `test_an_unknown_identifier_is_refused_identically` |
| A request without a session is refused as absent | `test_a_request_without_a_session_is_refused_as_absent` |
| The header names the other surfaces | `test_the_header_names_the_other_surfaces` |
| The pages carry no styling of their own | `test_the_pages_carry_no_styling_of_their_own` |
| The stylesheet is not reached through another surface's route | `test_the_stylesheet_is_not_reached_through_another_surfaces_route` |
| A vocabulary change reaches these pages | `test_a_vocabulary_change_reaches_these_pages` |

### `playbook-admin` (MODIFIED)

| Scenario | Test | Written here? |
| --- | --- | --- |
| Departing from the create surface carries nothing forward | `tests/unit/launch/infrastructure/driving/test_admin_surface_navigation_and_assets.py::test_departing_from_the_create_surface_carries_nothing_forward` | no — carried forward verbatim, existing test still green and still correct |
| The roster page is reachable from the step list | same file, `::test_the_roster_page_is_reachable_from_the_step_list` | no — as above |
| The header does not depend on how many steps are shown | same file, `::test_the_header_does_not_depend_on_how_many_steps_are_shown` | no — as above |
| The authoring surfaces carry the header too | same file, `::test_the_authoring_surfaces_carry_the_header_too` | no — as above |
| Every other admin surface is reachable from the step list | `tests/unit/launch/infrastructure/driving/test_admin_header_names_every_surface.py::test_every_other_admin_surface_is_reachable_from_the_step_list` | **yes** |
| A surface added later is named by the header | same file, `::test_a_surface_added_later_is_named_by_the_header` | **yes** |

The four carried-forward scenarios are byte-identical in the delta and in
`openspec/specs/playbook-admin/spec.md`, and the requirement body only
**widens** (from "the roster page" to "each admin surface the session can
reach"). Writing duplicate tests for them would add no evidence; naming
the existing ones keeps the count honest. They must stay green through
this change — that is the check, and it is stated as a task below.

### `roster-admin` (MODIFIED)

| Scenario | Test | Written here? |
| --- | --- | --- |
| The playbook page is reachable from the roster | `tests/unit/access/infrastructure/driving/test_roster_admin_presentation_vocabulary.py::test_the_playbook_page_is_reachable_from_the_roster` | no — carried forward verbatim |
| The header is rendered on a roster holding nobody | same file, `::test_the_header_is_rendered_on_a_roster_holding_nobody` | no — as above |
| Every other admin surface is reachable from the roster | `tests/unit/access/infrastructure/driving/test_roster_header_names_every_surface.py::test_every_other_admin_surface_is_reachable_from_the_roster` | **yes** |
| A surface added later is named by the header | same file, `::test_a_surface_added_later_is_named_by_the_roster_header` | **yes** |

## Blocked coverage

Three tests are written and **cannot pass until the sibling change
`add-launch-journal` lands**, which is on a different branch and provides
the journal read. `tasks.md` 4.8 and 7.1 record the same sequencing.

- `test_launch_admin_detail.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it`
- `test_launch_admin_detail.py::test_journal_entries_render_newest_first`
- `test_launch_admin_detail.py::test_an_empty_journal_says_so`

Each fails through `_journal_seam()`, whose message names
`add-launch-journal` explicitly, so the failure reads as the dependency
it is rather than as a defect in this change. **They become a defect in
this change once that change has landed, and not before.** They stub the
journal read at a module seam whose name is invented
(`read_journal` / `journal` / `read_launch_journal` / `journal_entries`)
and whose entry shape is invented (`.what`, `.when`, `.cause`) — see the
project questions below. `tasks.md` 4.8's instruction to confirm that
change's read actually carries a **cause** is exactly what the first of
the three asserts.

## Obsolete tests

**Not applicable — and established by search, not by assumption.**

The two MODIFIED deltas are the only place obsolescence could arise.
Searching the dispatched test-path glob `tests/**/test_*.py` for tests
bearing on either header requirement found six, all named in the
accounting tables above. Each was read against the delta:

- Both deltas carry **every** pre-existing requirement title and scenario
  title *and body* forward unchanged (the deltas say so in an inline HTML
  comment, and the texts were compared against
  `openspec/specs/playbook-admin/spec.md` and
  `openspec/specs/roster-admin/spec.md`).
- Both requirement bodies only **widen**: "the roster page" / "the
  playbook page" become "each admin surface the session can reach". A
  widening supersedes nothing an existing assertion makes.

So there is no obsolete-test entry to make: **no such test exists**, as
distinct from none having been found. Nothing here is a candidate for
deletion or rewriting.

One near-miss, recorded so it is not mistaken for obsolescence later.
`test_admin_surface_navigation_and_assets.py::test_departing_from_the_create_surface_carries_nothing_forward`
asserts `not urlsplit(href).query` with an inline comment justifying it
by "the roster page has no narrowing of its own". The delta replaces that
justification ("another surface may well have narrowing of its own, and
that is beside the point") while keeping the obligation identical — none
of *this capability's* narrowing state travels. **The assertion is still
correct and must not be touched.** Only the comment's reasoning is stale,
and a stale comment is not grounds for editing a test.

## Findings — read these before implementing

### Finding 1 (specification gap): the report echoes the served playbook's construction order; it does not impose a gate order

`launch-instance`'s new requirement says entries "SHALL arrive in the
served playbook's own order: gate sequence order, and within a gate the
authored order". Observed against the current code: `read_launch` /
`read_launches` hand entries over in **exactly** the order the
`LaunchPlaybook` object was constructed in. Handed a playbook whose steps
arrive out of gate order, the entries come out ungrouped.

That matches `design.md` Decision 4 and `tasks.md` 1.4 (no code needed,
because `served_steps` "is already ordered by gate then authored slot") —
but that premise rests on the **serving layer**, and nothing in
`openspec/specs/` requires the playbook repository to hand `served_steps`
over gate-first. `launch-playbook` obliges consumers to follow a gate's
authored order; no requirement obliges the served set to arrive gate-first.

`test_step_entries_arrive_in_the_served_playbooks_order` therefore builds
its fixture the way the serving layer builds one and asserts both halves
against it. It **passes**. It does not manufacture a stricter obligation
than the artifacts state — that would be inventing a requirement nobody
agreed to. Closing the gap is a change to the artifacts, not to this
test; it is flagged here for `openspec-update-change`.

### Finding 2: `tasks.md` 1.4's premise otherwise holds

`blocking`, `overdue` and one-entry-per-served-step are all carried by
the report today; the eight tests pinning them pass on first run against
unmodified code. The overdue judgement is correct for every case the
delta names, including the `prohibited-tactic`-at-`Refused` case and the
recurring-anchor case. Nothing in group 1 needs implementing beyond
`name` and `gate` on `ReportedStep` and the gate sequence on
`LaunchReport`.

### Finding 3: `design.md` Decision 7's premise confirmed

`read_launch(launches, playbooks, *, product_id, as_of, scope)` already
takes `as_of`, exactly as `read_launches` does. The render-date
obligation is satisfiable today; what remains is passing the render date
rather than a default.

### Finding 4: the page needs a seam for the day it renders on

Both render-date scenarios (`launch-admin` R1 and R4) require rendering
the same launch on two different days. `_render_on` accepts either a
module-level clock callable (`today` / `current_date` / `now` / `clock` /
`render_date`) **or** the module's own `date` name, which covers the
ordinary `from datetime import date` + `date.today()` shape. A module
with neither cannot have this behaviour observed at all, and those two
tests will say so rather than work around it.

### Finding 5: `tasks.md` 7.4a is not derived from any scenario

"Exercise the row and detail shaping without rendering a template" is a
task, not a delta requirement — `tasks.md` says so itself ("No delta
requires it"). This pass derives tests from the delta specs only, so
nothing here covers it. Recorded so its absence is a decision rather than
an oversight.

## Assertion classification

Per `ai-toolkit:testing`, every assertion is **specified**, **derived**
or **deliberately untested**. Each test marks its assertions inline with
`# SPECIFIED:` or `# DERIVED guard:`; the summary:

- **Specified** — every assertion tracing to a delta requirement's own
  words: which rows are rendered and in what order, which facts each row
  and each step row carries, which of the four empty states is stated,
  which refusals are identical, what the header offers, where the
  stylesheet comes from, and every field the report must carry. These
  are not repair candidates: a specified assertion that does not match
  means the code is wrong.
- **Derived guards** — assertions that establish a test's own premise
  rather than the requirement: that a fixture launch really is at risk,
  that a narrowing really shortened the list, that a due period really
  has passed, that a control set really holds one of each kind. They
  exist so no specified assertion can pass vacuously. Marked
  `# DERIVED guard:` throughout.
- **Derived operationalisations** — where a scenario states an outcome
  that HTML can express many ways, the reading is invented and named:
  * *read-only* is read as "no control on either page submits anything
    that is not a GET" (narrowing is carried in query parameters per
    `design.md` Decision 8, so this is strictly stronger than hunting for
    verbs in labels);
  * *set apart* is read as "an element holds every revealed row and no
    row in play", plus non-interleaving in document order;
  * *the two marks differ* is read as a token difference between two rows
    whose product name, gate and launch date are identical by
    construction and whose identity tokens are subtracted;
  * *the page's landing position* is read as a URL fragment, reached
    either by the detail route's redirect or by the list's row link,
    since a server-rendered page lands nowhere else without scripting;
  * *a vocabulary change reaches these pages* is read as identity of
    source — the bytes each page loads are the bytes an app mounting the
    shared asset router **alone** serves.
- **Deliberately untested** — nothing about how either page *looks*
  (spacing, colour, layout); `tasks.md` 8.1–8.3 carry those as manual
  post-deploy checks. Also untested: the `.importlinter` confirmation
  (`tasks.md` 6.1), the archive ordering (`6.2`) and the
  `add-product-dossier-page` check (`6.3`) — none is a delta scenario and
  none is observable from a test.

## Unresolved project questions

Answered here by assumption, because a dispatched subagent has no channel
to ask on. Each has a single named correction point in the code; changing
one is a **fixture correction**, not a weakening.

1. **Every seam of `launch_admin`.** No artifact fixes what the module
   exposes for the launch store, the playbook port, the roster, the
   session guard, the scope resolver, or the two catalog reads. `_SEAMS`
   (in both adapter files, and `_LAUNCH_SEAMS` in the two header files)
   probes several spellings each and fails loudly. *Depends on it:* every
   test in `test_launch_admin_list.py`, `test_launch_admin_detail.py`,
   and both header files.
2. **The render-date seam.** See Finding 4. *Depends on it:* the two
   render-date scenarios, and — because `_render_on` runs in every
   `_surface()` — every adapter test in both files.
3. **The wording of every mark and statement**: at risk, awaiting
   confirmation, no launch date, steady state versus retired, no launch
   is in play, no product is in launch, none are out of play, the
   narrowing matched nothing, offer to clear, overdue, blocks its gate,
   no step is served, unrecorded. `_WORDS` in each adapter file.
   *Depends on it:* most of R1, R3, R4.
4. **How the narrowing and reveal controls are driven.** Discovered from
   the rendered page first (`_live_control_saying`, `_gate_params`,
   `_attention_params`, `_reveal`), with invented query parameters as
   fallback — the pattern `test_playbook_admin_page.py` records for the
   retired-step reveal. *Depends on it:* R1's reveal scenarios and all of
   R3.
5. **How a row, a step row, a gate group and a header are located.**
   `_rows`, `_step_row`, `_gate_group`, `_header_of`,
   `_identifies_current`. The row locator leans on the one structural
   fact R1 fixes: every rendered row offers its detail page in one
   action. The step-row locator additionally requires the row to hold the
   step's **name**, so a `<td>` holding only the identifier is not
   mistaken for it.
6. **The report's new field names** — `name` and `gate` on a step entry,
   and the gate sequence on the report. `_ATTRIBUTE_ALIASES` in
   `test_launch_report_step_facts.py`. The existing spellings
   (`step_id`, `progress`, `due_period`, `blocking`, `overdue`,
   `at_risk`, `awaiting_confirmation`, `current_gate`, `launch_date`)
   were read off the running code and are not assumptions.
7. **The journal read's seam and entry shape** — owned by
   `add-launch-journal`. `_JOURNAL_SEAM_NAMES` and the stub entry's
   `.what` / `.when` / `.cause`. *Depends on it:* the three blocked
   tests.
8. **How *The name follows the served playbook* is exercised.** The
   scenario says "through the authoring writes"; the serving repository
   that turns stored records into a `LaunchPlaybook` is infrastructure
   and is not reachable at the application tier. The test drives the real
   `update_step` and then rebuilds the served playbook from the store —
   the same composition `test_playbook_authoring.py` already uses.
   Recorded as a deviation from the scenario's literal wording; the
   normative sentence it establishes ("the served playbook's name for the
   step at the time the report is produced") is covered exactly.

## What the implementation step must make pass

Run, in this order:

```
uv run pytest tests/unit/launch/application/test_launch_report_step_facts.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_admin_list.py
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py
uv run pytest tests/unit/launch/infrastructure/driving/test_admin_header_names_every_surface.py
uv run pytest tests/unit/access/infrastructure/driving/test_roster_header_names_every_surface.py
```

Per task group:

- **Group 1** (report facts) → the four currently-failing tests in
  `test_launch_report_step_facts.py`; the other eight must **stay**
  green, and a regression in them means group 1 broke behaviour it was
  told not to touch.
- **Groups 2–3** (read model, launch list) → all 28 in
  `test_launch_admin_list.py`.
- **Group 4** (detail page) → the 12 R4 tests in
  `test_launch_admin_detail.py`; task 4.8's three journal tests only
  after `add-launch-journal` lands.
- **Group 5** (header, three capabilities) →
  `test_launch_admin_detail.py::test_the_header_names_the_other_surfaces`,
  both tests in `test_admin_header_names_every_surface.py`, and both in
  `test_roster_header_names_every_surface.py`. Task 5.2's stylesheet half
  → the three R9 tests. **And** the six pre-existing header tests named
  in the accounting tables must stay green.
- **Group 7** (verification) → the whole suite. 7.2's four
  pinned-behaviour tests are already green and must remain so; 7.3's two
  scope scenarios are
  `test_a_restricted_scope_lists_only_its_launches` and
  `test_a_forbidden_launch_is_refused_identically`; 7.4's two render-date
  scenarios are `test_the_list_is_evaluated_as_of_the_day_it_is_rendered`
  and `test_the_detail_page_is_evaluated_as_of_the_day_it_is_rendered`.

## Addendum — the blocked tests are marked, not merely described

Added during implementation (`openspec-apply-change`), because the
pre-commit hook runs the whole unit + agents tree and refuses a commit
while anything is red — so "blocked" had to become something the runner
understands rather than a sentence in this file.

The two journal tests that cannot pass until `add-launch-journal` lands
carry `@pytest.mark.xfail(strict=True)` naming that change. **Strict is
the point**: the moment the journal lands they stop failing, and a strict
xfail turns an unexpected pass into a failure — so the marker cannot
outlive the block it records, and nobody has to remember to remove it.

The third journal test, *An empty journal says so*, is **not** marked: it
passes today, because a launch with no journal renders the empty-journal
statement whether the journal exists or not, which is exactly what a
launch predating the journal will show for ever.

Nothing else was weakened, skipped or deleted. The suite reads
`1202 passed, 2 xfailed`.
