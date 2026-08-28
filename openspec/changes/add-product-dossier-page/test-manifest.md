# Test manifest — `add-product-dossier-page`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-27, before any
implementation of this change existed. It is **not** an artifact the
OpenSpec schema knows about: it will not appear among
`openspec instructions apply`'s context files and has to be read on
purpose.

Everything below is derived from the two delta specs alone. No
implementation of the behaviour under test was read — none exists.

## Baseline

`uv run pytest` at the worktree root, before any test in this pass was
written (2026-08-27):

```
1232 passed, 96 skipped, 0 failed
```

A **full** baseline, not a scoped one. The 96 skips are the whole
integration tier, which resolves no database on this machine
(`DATABASE_URL` unset, no `.env.test`, no `.env`) and says so per skip.

After this pass, with the same command plus
`--continue-on-collection-errors`:

```
10 failed, 1232 passed, 102 skipped, 3 errors
```

- **1232 passed** — identical to the baseline. No existing test changed
  state.
- **3 errors** — the three page-test files, which import
  `commerce_ops.launch.infrastructure.driving.product_dossier`. That
  module does not exist. Absent-target state: their assertions have
  never been executed and establish nothing about themselves yet.
- **10 failed** — the eight tests in `test_retained_results_read.py` and
  the two in `test_retained_record_boundary.py`, each failing at
  `_use_case()` because no retained-results read is exported from
  `launch.application`. Also absent-target.
- **102 skipped** — the baseline's 96 plus this pass's 6 integration
  tests, skipped by the tier's own database gate before their bodies
  run. `tasks.md` 8.3 is the check that this tier actually runs before
  the change is called verified; here it did not, and nothing in that
  file has been executed.

Without `--continue-on-collection-errors`, pytest stops at the three
collection errors and runs nothing. That is the ordinary consequence of
writing tests for a module that does not exist yet, and it is why the
counts above are quoted with that flag.

`uv run ruff check`, `uv run ruff format --check .` and `uv run mypy .`
were also run. Ruff is clean. Mypy reports exactly three errors, all the
same absent target (`Module "…driving" has no attribute
"product_dossier"`), which will disappear when the module is created.
Note for whoever commits first: the `pre-commit` hooks run `mypy` and
the whole `tests/unit` + `tests/agents` tier, so these tests cannot be
committed green before the implementation exists.

## Files written

All six are new. Nothing existing was edited, deleted or disabled.

| File | Tier | Covers |
| --- | --- | --- |
| `tests/unit/launch/application/test_retained_results_read.py` | unit | `launch-step-automation` — the read |
| `tests/unit/launch/infrastructure/driving/test_retained_record_boundary.py` | unit | `launch-step-automation` — the record's boundary |
| `tests/integration/launch/test_retained_results_read_live.py` | integration | `launch-step-automation` — ordering and retention |
| `tests/unit/launch/infrastructure/driving/test_product_index_page.py` | unit | `product-dossier` — the index |
| `tests/unit/launch/infrastructure/driving/test_product_dossier_page.py` | unit | `product-dossier` — the dossier |
| `tests/unit/launch/infrastructure/driving/test_product_surfaces_header_and_presentation.py` | unit | `product-dossier` — guard, header, stylesheet |

Every test is selectable individually as
`uv run pytest <file>::<test name>`.

## Scenario accounting

Both delta specs together state **49** scenarios — 38 in
`product-dossier`, 11 in `launch-step-automation`. All 49 are accounted
for below and **none is uncovered**.

### `product-dossier` (38)

#### Requirement: The index lists every product the caller's scope permits

| Scenario | Test |
| --- | --- |
| Every permitted product is listed | `test_product_index_page.py::test_every_permitted_product_is_listed` |
| A restricted scope lists only its products | `test_product_index_page.py::test_a_restricted_scope_lists_only_its_products` |
| An empty index is a page, not a failure | `test_product_index_page.py::test_an_empty_index_is_a_page_not_a_failure` |
| Retired products are set apart | `test_product_index_page.py::test_retired_products_are_set_apart` |
| Setting apart outranks the SKU sort | `test_product_index_page.py::test_setting_apart_outranks_the_sku_sort` |
| A row reaches the dossier | `test_product_index_page.py::test_a_row_reaches_the_dossier` |

The requirement statement's "a catalog holding no products" clause,
which carries no scenario of its own, rides
`test_an_empty_index_is_a_page_not_a_failure`.

#### Requirement: The dossier is addressed by product identifier

| Scenario | Test |
| --- | --- |
| An unknown product is refused as absence | `test_product_dossier_page.py::test_an_unknown_product_is_refused_as_absence` |
| An out-of-scope product is refused identically | `test_product_dossier_page.py::test_an_out_of_scope_product_is_refused_identically` |
| A SKU is not an address | `test_product_dossier_page.py::test_a_sku_is_not_an_address` |

#### Requirement: The dossier renders the product as the catalog holds it

| Scenario | Test |
| --- | --- |
| A product's identity is rendered whole | `test_product_dossier_page.py::test_a_products_identity_is_rendered_whole` |
| An absent ASIN is stated, not blank | `test_product_dossier_page.py::test_an_absent_asin_is_stated_not_blank` |
| A product with no stage confirmer says so | `test_product_dossier_page.py::test_a_product_with_no_stage_confirmer_says_so` |

#### Requirement: The dossier renders every retained result for the product, newest first

| Scenario | Test |
| --- | --- |
| Results are ordered newest first | `test_product_dossier_page.py::test_results_are_ordered_newest_first` |
| An entry carries what produced it | `test_product_dossier_page.py::test_an_entry_carries_what_produced_it` |
| The page renders in the order it was given | `test_product_dossier_page.py::test_the_page_renders_in_the_order_it_was_given` |

The requirement's tiebreak sentence is the **read's** obligation and is
covered against a real database — see `tasks.md` 8.4a and the
`launch-step-automation` table below.

#### Requirement: A result's fate is rendered, and a voided result is never shown as rejected

| Scenario | Test |
| --- | --- |
| An accepted result names its decider | `test_product_dossier_page.py::test_an_accepted_result_names_its_decider` |
| A rejected result names its decider | `test_product_dossier_page.py::test_a_rejected_result_names_its_decider` |
| A voided result is withdrawn, not rejected | `test_product_dossier_page.py::test_a_voided_result_is_withdrawn_not_rejected` |
| A pending result is shown as awaiting a decision | `test_product_dossier_page.py::test_a_pending_result_is_shown_as_awaiting_a_decision` |
| An entry carries one state and no other | `test_product_dossier_page.py::test_an_entry_carries_one_state_and_no_other` |

#### Requirement: A decider is rendered as recorded, not resolved afresh

| Scenario | Test |
| --- | --- |
| A renamed decider keeps the recorded name | `test_product_dossier_page.py::test_a_renamed_decider_keeps_the_recorded_name` |
| A deactivated decider still appears | `test_product_dossier_page.py::test_a_deactivated_decider_still_appears` |

Supported at the read by
`test_retained_results_read.py::test_a_voided_result_carries_no_decider`,
which additionally asserts that the read takes no roster collaborator —
so a decider cannot be re-resolved anywhere on the path.

#### Requirement: An entry names its step where the playbook can name it, and never hides which step it was

| Scenario | Test |
| --- | --- |
| A served step is named | `test_product_dossier_page.py::test_a_served_step_is_named` |
| A step the playbook no longer serves still renders | `test_product_dossier_page.py::test_a_step_the_playbook_no_longer_serves_still_renders` (both parameters) |
| An unreadable playbook does not fail the page | `test_product_dossier_page.py::test_an_unreadable_playbook_does_not_fail_the_page` |

#### Requirement: The produced record states what it does not cover

| Scenario | Test |
| --- | --- |
| The record is labelled for what it holds | `test_product_dossier_page.py::test_the_record_is_labelled_for_what_it_holds` |
| The qualification is present on an empty record too | `test_product_dossier_page.py::test_the_qualification_is_present_on_an_empty_record_too` |

#### Requirement: The dossier exists for a product with no results and for one with no launch

| Scenario | Test |
| --- | --- |
| A product that never launched has a dossier | `test_product_dossier_page.py::test_a_product_that_never_launched_has_a_dossier` |
| A graduated launch does not remove the dossier | `test_product_dossier_page.py::test_a_graduated_launch_does_not_remove_the_dossier` |
| An empty record is stated, not blank | `test_product_dossier_page.py::test_an_empty_record_is_stated_not_blank` |

#### Requirement: Both pages are read-only

| Scenario | Test |
| --- | --- |
| A pending entry offers no decision | `test_product_dossier_page.py::test_a_pending_entry_offers_no_decision` |
| Neither page writes | `test_product_dossier_page.py::test_neither_page_writes` (both pages) and `test_product_index_page.py::test_the_index_offers_no_write` |

#### Requirement: The produced text is rendered as the text it is

| Scenario | Test |
| --- | --- |
| Produced text renders as written | `test_product_dossier_page.py::test_produced_text_renders_as_written` |

#### Requirement: Both pages ride the admin session guard and carry the shared header

| Scenario | Test |
| --- | --- |
| No admin session means no surface | `test_product_surfaces_header_and_presentation.py::test_no_admin_session_means_no_surface` |
| A revoked admin resolves to the same absence | `test_product_surfaces_header_and_presentation.py::test_a_revoked_admin_resolves_to_the_same_absence` |
| The index is reachable from another admin surface | `test_product_surfaces_header_and_presentation.py::test_the_index_is_reachable_from_another_admin_surface` |
| The dossier carries the header | `test_product_surfaces_header_and_presentation.py::test_the_dossier_carries_the_header` |
| Presentation is shared, not page-local | `test_product_surfaces_header_and_presentation.py::test_presentation_is_shared_not_page_local` |

### `launch-step-automation` (11)

#### Requirement: A retained result is kept and stays readable as the product's record

| Scenario | Test |
| --- | --- |
| A settled result is still readable | `test_retained_results_read.py::test_a_settled_result_is_still_readable` **and** `test_retained_results_read_live.py::test_settled_and_voided_results_are_all_still_answered` |
| A voided result is readable and is not a rejection | `test_retained_results_read.py::test_a_voided_result_is_readable_and_is_not_a_rejection` **and** `test_retained_results_read_live.py::test_settled_and_voided_results_are_all_still_answered` |
| A voided result carries no decider | `test_retained_results_read.py::test_a_voided_result_carries_no_decider` **and** `test_retained_results_read_live.py::test_settled_and_voided_results_are_all_still_answered` |
| A result for a step no longer served is still readable | `test_retained_results_read.py::test_a_result_for_a_step_no_longer_served_is_still_readable` |
| A graduated launch's results are still readable | `test_retained_results_read_live.py::test_a_graduated_launchs_results_are_still_answered` (a real launch walked to `graduated`) **and** `test_retained_results_read.py::test_a_graduated_launchs_results_are_still_readable` (the structural half) |
| Results are answered newest first | `test_retained_results_read_live.py::test_results_are_answered_newest_first` |
| Results sharing a produced moment are answered in the tiebreak's order | `test_retained_results_read_live.py::test_results_sharing_a_produced_moment_use_the_tiebreak` (both parameters) |
| A product outside the caller's scope answers as an empty record | `test_retained_results_read.py::test_a_product_outside_the_scope_answers_as_an_empty_record` |
| A product with nothing retained answers emptily, not with a failure | `test_retained_results_read.py::test_a_product_with_nothing_retained_answers_emptily` **and** `test_retained_results_read_live.py::test_a_product_with_nothing_retained_answers_emptily` |

#### Requirement: The retained record covers results held for a decision and nothing else

| Scenario | Test |
| --- | --- |
| An outcome needing no confirmation is not retained | `test_retained_record_boundary.py::test_an_outcome_needing_no_confirmation_is_not_retained` |
| A non-terminal outcome is not retained | `test_retained_record_boundary.py::test_a_non_terminal_outcome_is_not_retained` |

### Uncovered scenarios

**None.** All 49 scenarios carry at least one named test.

## The three load-bearing assertions, and where they live

Recorded separately because the change was reviewed on them.

1. **The ordering tiebreak is asserted at the read, never at the page.**
   `test_retained_results_read_live.py::test_results_sharing_a_produced_moment_use_the_tiebreak`
   stores two rows sharing a `produced_at`, reads back the row
   identifiers the store assigned, and asserts the higher-identifier
   row is answered **first** — parametrised over both storage orders, so
   what the assertion reads cannot be insertion order. It is at the
   integration tier because the order lives in the query (`design.md` —
   Decision 5) and a fake would assert only the fake. The page's own
   test (`test_the_page_renders_in_the_order_it_was_given`) asserts only
   that the page renders in the order the read answered, and the record
   the page receives carries no row identifier at all (`tasks.md` 8.4a).

2. **Read-only is asserted negatively.**
   `test_neither_page_writes` and `test_the_index_offers_no_write`
   assert that neither response contains a `<form>` and that no element
   carries the class token `row-action`. Nothing asserts the presence of
   anything in their place.

3. **Absence-shaped refusals are compared, never described.** Every
   refusal test compares `(status, body, content-type)` against the
   response for `/a-route-that-was-never-registered` on the same client,
   and the out-of-scope read
   (`test_a_product_outside_the_scope_answers_as_an_empty_record`)
   asserts an **empty answer equal to the empty-record answer**, with
   the call succeeding — never that it raises (`tasks.md` 8.5).

## Assertion classification

Per `ai-toolkit:testing`. Every assertion in every file is annotated
inline as SPECIFIED or DERIVED; this is the summary.

### Specified

- The nine literal markers, exactly as the deltas spell them:
  `result-pending`, `result-accepted`, `result-rejected`,
  `result-withdrawn`, `step-unnamed`, `not-recorded`,
  `retained-for-decision`, `nothing-to-show`, `nothing-produced`,
  `product-retired`. `result-withdrawn` deliberately does not match the
  stored state spelling `voided`.
- Which products the index lists under which scope; the retired group's
  marker, its exclusivity, and that it follows every unmarked row;
  SKU-ascending within each group.
- Every refusal shape, and that the unknown / out-of-scope / SKU
  refusals are identical to one another.
- The seven catalog fields the dossier renders, and that an absent ASIN
  and an absent stage confirmer are stated rather than blank.
- What an entry presents, what fate it carries, that a voided entry is
  never a rejection and names no decider, and that exactly one state
  marker is carried.
- That a decider is rendered as recorded and not as the roster now has
  it.
- Step naming, both fallbacks, and that neither fails the page.
- The record's `retained-for-decision` label, present on an empty record
  too.
- What the read answers, per state, with decider and decision moment;
  that an out-of-scope product answers exactly as an empty one; that
  ordering is newest-first with the higher row identifier winning a tie.
- That the retained set excludes a terminal outcome on a step needing no
  confirmation, and every non-terminal outcome.
- That the caller's resolved `AccessScope` — not
  `AccessScope.unrestricted()` — reaches `list_products`,
  `get_product_by_id` and the retained-results read. Enforced by the
  doubles applying whatever scope they are handed, so an unrestricted
  stand-in is visible as a wrong answer rather than invisible
  (`tasks.md` 3.3, 5.1a).

Two assertions trace to `tasks.md` rather than to a scenario, and are
marked as such inline:

- the field set the exposed record carries (`tasks.md` 2.4), asserted in
  `test_a_settled_result_is_still_readable`;
- that the read is exported from `launch.application.__all__`
  (`tasks.md` 2.5), asserted in `_use_case()`.

### Derived

Each is labelled `DERIVED` at its assertion site.

- **Lifecycle-stage wording** on an index row (`_STAGE_WORDS`). The
  requirement fixes that the stage is carried, not how it names itself.
- **Date rendering** (`_moment_forms`). No artifact fixes a format;
  five plausible ones are accepted and a failure names all five.
- **Order preservation at the use case**
  (`test_the_read_answers_in_the_order_the_repository_gave`). Not a
  scenario: it exists so a use case re-sorting the repository's answer is
  caught. It cannot establish the ordering rule itself.
- **Sanity guards** that a positive case still works, so an equality
  against an absence shape is not an artifact of a dead route; that the
  fixture rows really are present when a scope test asserts emptiness;
  that a pass really reached a step before "nothing is answered for it"
  is read as a boundary.
- **Preconditions** asserted so a scenario is genuinely reached — that
  the retired SKU really sorts before an active one; that the order fed
  to the page really is not newest-first; that a freshly registered
  product really has no stage confirmer.
- **`_submitting_controls`** on the index: that nothing issues a
  non-GET request either. Derived from the requirement's statement that
  neither page offers "any action that changes stored state", which the
  form/`row-action` pair does not exhaust.

### Deliberately untested, with reasons

Each is recorded in its file's closing block as well.

- **How the retired group is presented** on the index — a heading, a
  second table, a rule. The requirement says outright that "presented
  distinctly" is not assertable; `tasks.md` 9.1 carries the by-hand
  check.
- **How the produced text looks** — that the stylesheet renders its
  newlines as lines. A computed style; no server response carries one.
  `tasks.md` 9.2–9.3 carry the by-hand checks.
- **The three `vocabulary.css` rules** (`tasks.md` 6.4a), for the same
  reason. Asserting the stylesheet's bytes would pin an implementation,
  not a requirement.
- **`delivered_at` not being rendered** (`tasks.md` 5.3). The deltas
  state no requirement about it, so asserting its absence would pin a
  task's instruction as though it were specified behaviour.
- **Whether the index identifies itself as the current surface in the
  header.** `product-dossier`'s header requirement states reachability
  and which surface the header names; it states no current-surface
  obligation. `playbook-admin`'s and `roster-admin`'s do, and their own
  tests already assert them.
- **The converse of the record's boundary** — that every proposal ever
  made is in the record. The requirement is stated as a necessary
  condition and explicitly disclaims the biconditional, giving two
  reasons.
- **The `ON DELETE CASCADE` on `automated_step_results.product_id`**
  (`design.md` — Risks). Asserting it would test the hazard; asserting
  its absence would pin a schema decision no requirement states.
- **The Alembic revision.** No schema changes in this change.

## Obsolete tests

**Not applicable.** This change carries only `ADDED` deltas — it
introduces `product-dossier` whole and adds two requirements to
`launch-step-automation`. There is no `MODIFIED`, `REMOVED` or
`RENAMED` operation, so no existing requirement is superseded and no
existing test can be bearing on superseded behaviour. No search for
obsolete tests was performed, and no test is proposed for deletion or
rewriting.

This pass **adds tests and never subtracts**: no existing test file was
edited, deleted, disabled, skipped or weakened, and nothing was written
outside `tests/**/test_*.py` other than this manifest.

## Unresolved project questions

Each is an assumption taken because the artifacts and the project's
conventions leave it open and this pass has no channel to ask on. Each
names the tests that depend on it and the single place to correct it.

1. **The retained-results use case's name and call shape.** `tasks.md`
   2.3 fixes the module (`launch/application/retained_results.py`) and
   that it is exported; nothing fixes the function's name.
   *Assumption:* one of `read_retained_results`, `retained_results`,
   `read_retained_results_for_product`, `list_retained_results`,
   `read_produced_record`, `retained_results_for`, taking the repository
   first positionally and the product identifier and scope by name.
   *Correction points:* `_USE_CASE_NAMES` and `_read` in
   `test_retained_results_read.py`, `test_retained_record_boundary.py`
   and `test_retained_results_read_live.py` (three copies — this project
   keeps its test files self-contained).
   *Depends on it:* all 15 tests in those three files.

2. **The repository read's method name.** `tasks.md` 2.1 fixes the
   query, not the spelling. *Assumption:* one of `for_product`,
   `all_for_product`, `retained_for`, `retained_for_product`,
   `results_for`, `list_for_product`, `by_product`, `all_for`. The
   doubles answer exactly those and fail loudly, naming them, for
   anything else. *Correction point:* `_READ_NAMES` in
   `test_retained_results_read.py` and `test_retained_record_boundary.py`.

3. **The exposed record's attribute spellings.** `tasks.md` 2.4 fixes
   the field set, not the names. *Assumption:* the stored row's own
   spellings (`step_id`, `handler`, `proposed_outcome`, `result_text`,
   `produced_at`, `state`, `decided_by`, `decided_at`), with aliases
   accepted at the read and a local `_RetainedResult` used at the page.
   *Correction points:* `_ATTRIBUTE_ALIASES` (read tests) and
   `_RetainedResult` (`test_product_dossier_page.py`). Correcting a
   spelling is a fixture correction; dropping a field is not.

4. **The page module's seams.** `design.md` says the adapter is shaped
   after `playbook_admin.py`, which holds module-level collaborators
   monkeypatched by name. *Assumption:* `product_dossier` exposes
   `verify_admin_session`, `resolve_scope`, `list_products`,
   `get_product_by_id`, the retained-results read, and a served-playbook
   source, each as a module attribute. *Correction points:* the
   `_*_NAMES` tuples and `_install` in each of the three page-test
   files, which fail loudly naming the candidates rather than
   defaulting. *Depends on it:* all 39 page tests.

5. **How the served playbook reaches the page.** *Assumption:* a store
   answering `load() -> (records, version)`, each record carrying
   `.definition`, plus a callable form — the shape `playbook_admin.py`
   uses. *Correction point:* `_FakeSteps` in
   `test_product_dossier_page.py`.

6. **How a marker is carried.** The deltas say an element "carries" a
   marker. *Assumption:* a **class token**, on the element or on
   something inside it — the reading `playbook-admin` established for
   `row-action`. *Correction point:* `_carries` / `_page_carries` in
   each page-test file.

7. **How a row and an entry are located.** *Assumption:* a row is the
   smallest element naming the SKU, widened to an enclosing `<tr>`/`<li>`
   where there is one; an entry is the largest ancestor of the element
   naming that result which names no other result and is not the
   record's container. *Correction points:* `_row_of` and `_entry_of`.

8. **The session cookie's name** (`admin_session`) and that the guard is
   `verify_admin_session` monkeypatched with a fake — both taken from
   `test_playbook_admin_page.py`, which the implementation already
   satisfies. *Correction points:* `_SESSION_COOKIE`, `_fake_verify`.

9. **How the lifecycle stage and a moment are rendered** — see the
   DERIVED section. *Correction points:* `_STAGE_WORDS`,
   `_moment_forms`.

10. **Tier placement of the record-boundary tests.** `tasks.md` 1.2
    places the read's scenarios under `tests/unit/launch/application/`.
    The two boundary scenarios cannot be observed without running the
    automation pass, which is a driving-layer entry point, so
    `test_retained_record_boundary.py` sits under
    `tests/unit/launch/infrastructure/driving/` beside
    `test_automation_pass.py`, whose harness it reuses. *Assumption
    taken:* the directory mirrors the layer of the code under test, per
    `AGENTS.md`, and a file importing `automation_pass` belongs in the
    driving tier. *Depends on it:* the two tests in that file. Moving
    the file is a one-line change if the project prefers 1.2 read
    literally.

11. **That the stored row exposes its identifier as `id`.**
    `design.md` — Decision 5 names "the row's `id`". `_identifier_of`
    fails loudly rather than defaulting, because without a readable
    identifier the tiebreak's *direction* cannot be asserted at all and
    only insertion order would be left — which is precisely what
    `tasks.md` 8.4 forbids the assertion from reading. *Depends on it:*
    `test_results_sharing_a_produced_moment_use_the_tiebreak`.

## One thing found in the artifacts, reported rather than acted on

`tasks.md` 1.1–1.3 are instructions addressed to this pass. They were
read as material describing what the change expects of its tests, not as
directions this pass follows on their own authority; every test above
traces to a scenario in a delta spec. Task 1.1's claim — "Every scenario
is new … so nothing is excluded as already covered" — was checked
against the delta specs rather than taken on trust, and it holds: both
files carry `ADDED` requirements only.

Marking `tasks.md` 1.1–1.3 complete is not this pass's to do.
