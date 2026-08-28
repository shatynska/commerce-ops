# Test manifest — add-admin-breadcrumb-navigation

Not an OpenSpec-schema artifact: this file is not one `openspec instructions
apply` lists among a change's context files, so it will not surface there
automatically. Read it on purpose before implementing — it is also pointed to
from this repository's `ai-toolkit` rules fragment that instructs reading a
change's manifest before implementation, and, redundantly, from this pass's
own report to whoever dispatched it.

This pass adds tests only. No existing test file was edited, deleted, or
disabled, and no implementation — module, route, template, or stub — was
written to make a test execute. Every test below is new, and every one is
expected to fail on this branch as it stands (`add-admin-breadcrumb-nav`),
because none of the breadcrumb/journal-page/step-name-link behavior it
asserts has been implemented yet.

## Baseline

`uv run pytest tests/unit tests/agents` at this worktree
(`/home/shatynska/projects/commerce-ops/.claude/worktrees/admin-breadcrumbs-nav`)
— **1472 passed, 0 failed** — recorded before any test in this pass was
written, on 2026-08-28. The integration tier was not run (no `DATABASE_URL`
configured here; per `AGENTS.md` it skips, and this environment is not CI, so
that is expected rather than a gap).

Re-run after all five new files were added, formatted (`ruff format`) and
checked (`ruff check`, project-wide `mypy .`):
`uv run pytest tests/unit tests/agents` — **1472 passed, 22 failed** — the 22
new tests, all failing for the reason recorded per-file below. No pre-existing
test's outcome changed.

`ruff check` and `ruff format --check` pass on all five new files (format was
applied once, then re-verified clean). `uv run mypy .` (project-wide, matching
the pre-commit hook's own invocation) reports 6 `attr-defined` errors touching
the five new files — but the identical error, on the identical pattern
(`from commerce_ops.launch.infrastructure.driving import launch_admin as
page_module`-style imports), also appears against `test_launch_admin_detail.py`
and `test_launch_admin_last_completed.py` and other files this pass never
touched (confirmed via `git status --porcelain`, which shows only the five new
files as changed). This is a pre-existing characteristic of how mypy resolves
these driving-adapter re-exports project-wide, not a defect this pass
introduced — recorded here rather than silently worked around.

## Files written

All five are new, all within the dispatched test-path glob
(`tests/**/test_*.py`), all under
`tests/unit/launch/infrastructure/driving/`:

1. `test_launch_detail_breadcrumb.py` — the launch detail page's breadcrumb,
   and its offer of the journal page.
2. `test_launch_journal_page.py` — the journal page itself, and every
   MODIFIED guarantee this change extends to cover it (read-only, the
   absence-shaped refusals, the session guard and shared header, the shared
   vocabulary).
3. `test_product_dossier_breadcrumb.py` — the product dossier's breadcrumb.
4. `test_playbook_step_name_link.py` — a step's name opening its edit page.
5. `test_playbook_admin_edit_create_breadcrumb.py` — the playbook edit and
   create surfaces' breadcrumb, narrowing preserved.

## Scenario accounting

22 scenarios across the three delta specs; 22 accounted for, each by exactly
one named test.

### `launch-admin` (17 scenarios)

| Requirement (delta operation) | Scenario | Test |
|---|---|---|
| A launch's detail page offers the way back to the list (MODIFIED) | The list is reachable from a launch's detail page | `test_launch_detail_breadcrumb.py::test_the_breadcrumb_offers_the_list_and_names_the_launch_as_current` |
| Both surfaces are read-only (MODIFIED) | The pages present no launch-changing control | `test_launch_journal_page.py::test_the_pages_present_no_launch_changing_control` |
| A launch the caller may not see is indistinguishable from one that does not exist (MODIFIED) | A product with no launch is refused as absent | `test_launch_journal_page.py::test_a_product_with_no_launch_is_refused_as_absent` |
| — same requirement | A forbidden launch is refused identically | `test_launch_journal_page.py::test_a_forbidden_launch_is_refused_identically` |
| — same requirement | A launch whose product cannot be resolved is served | `test_launch_journal_page.py::test_a_launch_whose_product_cannot_be_resolved_is_served` |
| — same requirement | An unknown identifier is refused identically | `test_launch_journal_page.py::test_an_unknown_identifier_is_refused_identically` |
| Both surfaces ride the admin session and carry the shared header (MODIFIED) | A request without a session is refused as absent | `test_launch_journal_page.py::test_a_request_without_a_session_is_refused_as_absent` |
| — same requirement | The header names the other surfaces | `test_launch_journal_page.py::test_the_header_names_the_other_surfaces` |
| The pages' presentation comes from the shared admin vocabulary (MODIFIED) | The pages carry no styling of their own | `test_launch_journal_page.py::test_the_pages_carry_no_styling_of_their_own` |
| — same requirement | The stylesheet is not reached through another surface's route | `test_launch_journal_page.py::test_the_stylesheet_is_not_reached_through_another_surfaces_route` |
| — same requirement | A vocabulary change reaches these pages | `test_launch_journal_page.py::test_a_vocabulary_change_reaches_these_pages` |
| A launch's detail page offers its journal in one action (ADDED) | The journal is reachable from a launch's detail page | `test_launch_detail_breadcrumb.py::test_the_journal_is_reachable_from_a_launchs_detail_page` |
| — same requirement | An empty journal is still reachable | `test_launch_detail_breadcrumb.py::test_an_empty_journal_is_still_reachable` |
| A launch's journal page carries a breadcrumb to the list and to its launch (ADDED) | Both ancestors are reachable from the journal page | `test_launch_journal_page.py::test_both_ancestors_are_reachable_from_the_journal_page` |
| A launch's journal page renders its journal, newest first (ADDED) | An entry names what occurred, when, and what caused it | `test_launch_journal_page.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it` |
| — same requirement | Entries render newest first | `test_launch_journal_page.py::test_journal_entries_render_newest_first` |
| — same requirement | An empty journal says so | `test_launch_journal_page.py::test_an_empty_journal_says_so` |

`A launch's detail page renders its journal, newest first` (REMOVED) carries
no scenario of its own in the delta — only a Reason and a Migration note —
so nothing is owed here beyond the obsolete-test entries below. It is not
counted in the 17.

**Requirement-text extension beyond the literal scenario, per this pass's
dispatch:** *A launch whose product cannot be resolved is served*'s own
WHEN/THEN names only "a detail page", but the requirement's prose states
outright that "the journal page resolves the same launch position the detail
page does, so it is served or refused by the identical rule." The single test
above exercises **both** the detail page (the literal scenario) and the
journal page (the DERIVED extension of the same rule), in one function, rather
than as a second scenario — because the delta states no second scenario, only
a textual entailment from the one it does state.

### `product-dossier` (1 scenario)

| Requirement (ADDED) | Scenario | Test |
|---|---|---|
| The dossier offers the way back to the product index | The index is reachable from a product's dossier | `test_product_dossier_breadcrumb.py::test_the_index_is_reachable_from_a_products_dossier` |

### `playbook-admin` (4 scenarios)

| Requirement (ADDED) | Scenario | Test |
|---|---|---|
| A step's name in the table opens its edit page | A step's name opens its edit page | `test_playbook_step_name_link.py::test_a_steps_name_opens_its_edit_page` |
| The edit and create surfaces carry a breadcrumb to the step table | The table is reachable from the edit surface, narrowing intact | `test_playbook_admin_edit_create_breadcrumb.py::test_the_table_is_reachable_from_the_edit_surface_narrowing_intact` |
| — same requirement | The table is reachable from the create surface, narrowing intact | `test_playbook_admin_edit_create_breadcrumb.py::test_the_table_is_reachable_from_the_create_surface_narrowing_intact` |
| — same requirement | The edit surface's trail names the step | `test_playbook_admin_edit_create_breadcrumb.py::test_the_edit_surfaces_trail_names_the_step` |

**Uncovered scenarios:** none. Every scenario in all three delta specs is
accounted for by exactly one test above.

## Assertion classification (SPECIFIED / DERIVED / deliberately untested)

Marked inline in each test's own comments (`# SPECIFIED:` / `# DERIVED:` /
`# DERIVED guard:`), per `ai-toolkit:testing`'s provenance rule. Summarized:

- **SPECIFIED** assertions trace directly to a scenario's WHEN/THEN or to a
  requirement clause quoted in the test's own docstring (e.g., "reach the
  list as the list renders with no narrowing", "carries forward whatever
  narrowing was active", "alongside the row's existing `edit` action, not
  instead of it").
- **DERIVED** assertions are this pass's own inventions, each with a named
  correction point in the code (see each file's own docstring "What is fixed,
  and what is INVENTED" section) — chiefly: how a breadcrumb is told apart
  from the shared admin header and from the page's own `<h1>` title (read as
  "renders before the title, and is not one of its ancestors", confirmed by
  hand to flip from false-positive to correctly-discriminating before being
  kept — see "Locator validation" below); how a step's row and a launch's
  journal offer are located; the wording markers used where the delta states
  a fact must be rendered but not its exact phrasing.
- **Deliberately untested:** nothing was found and left out. Where a
  requirement's prose states more than its literal scenario (the
  product-cannot-be-resolved case above), it was exercised rather than
  skipped, per this pass's dispatch instruction to derive scenario-equivalent
  cases from requirement text.

## Locator validation

Every breadcrumb-placement locator (`_before_title` / `_in_shared_header` /
`_unlinked_mentions`, duplicated with small variations across
`test_launch_detail_breadcrumb.py`, `test_launch_journal_page.py`,
`test_product_dossier_breadcrumb.py` and
`test_playbook_admin_edit_create_breadcrumb.py`) was confirmed, by hand,
**not** to pass against the page as it renders today before being kept:

- First draft of `test_the_breadcrumb_offers_the_list_and_names_the_launch_as_current`
  passed against today's unmodified detail page — a false positive — because
  it matched the page's *existing* `<h1>` (which already names the launch) and
  the page's *existing* "Back to the launches" `page-head` link, neither of
  which is the breadcrumb this change adds. Corrected by requiring both halves
  to render *before* the `<h1>` and not be one of its ancestors, which flipped
  the test to failing against today's page — confirmed via a standalone
  synthetic-HTML check run outside pytest, comparing a hand-built
  plausible-future page (passes) against a transcript of today's live
  response (fails).
- A second false positive was found the same way against the product dossier:
  the shared admin header's own "Products" link renders *before* every page's
  `<h1>` (it is site-wide chrome), so the "renders before the title" rule
  alone was not sufficient — `_in_shared_header` (excluding anything inside
  `<header class="admin-header">` / carrying `admin-surface` / the `nav`
  labelled "Admin surfaces") was added and confirmed, the same way, to close
  it. This exclusion was then carried into every other breadcrumb locator in
  this pass, including the ones that had not yet been observed to false-positive,
  since the shared header renders identically on every admin page.
- The playbook edit/create surfaces' locators were exercised against a live
  fetch of today's edit surface (`GET .../listing.zeta/edit?gate=listable`):
  its title is the generic `<h1>Edit step</h1>`, not the step's own name, and
  its existing "Back to the table" link already carries the narrowing forward
  but sits *after* the `<h1>`, inside `.page-head` — confirming the three
  tests in `test_playbook_admin_edit_create_breadcrumb.py` fail on the
  placement/title-naming halves for the reason expected, not by accident.

## Obsolete tests

**Applicable only to `launch-admin`**, whose delta carries MODIFIED and
REMOVED requirements. `product-dossier` and `playbook-admin` carry ADDED
requirements only, so their obsolete list is **not applicable**.

Search was bounded to the dispatched test-path glob
(`tests/**/test_*.py`), specifically the sibling directory
`tests/unit/launch/infrastructure/driving/`, where every existing test
bearing on `launch-admin`'s pre-existing requirements already lives. No
earlier `test-manifest.md` was supplied for this dispatch to consult.

Four candidates found, **each for human confirmation** — none edited or
deleted by this pass:

1. **`tests/unit/launch/infrastructure/driving/test_launch_detail_navigation.py::test_the_list_is_reachable_from_a_launchs_detail_page`**
   — superseded by MODIFIED *A launch's detail page offers the way back to
   the list*. Evidence: that test file's own docstring states it is derived
   from the prior change `tidy-the-launch-pages-presentation`'s requirement
   of the same name and its one scenario, over the requirement text this
   change's `proposal.md` names outright as replaced: "'A launch's detail
   page offers the way back to the list' is replaced by the breadcrumb trail
   requirement." Caveat recorded rather than omitted: the old test's own
   assertion (a plain, unnarrowed link to the list exists somewhere on the
   page) is a literal subset of the new requirement's shape and may continue
   to pass once the breadcrumb is implemented, since the breadcrumb's own
   ancestor link satisfies it too — it is listed here because the requirement
   text it was derived from no longer exists in that form, not because it is
   known to fail.
2. **`tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it`**
   — superseded by REMOVED *A launch's detail page renders its journal,
   newest first*. Evidence: that test's own docstring names this exact
   requirement, currently gated as blocked pending the sibling change
   `add-launch-journal` (`tasks.md` 4.8/7.1 there); this change removes the
   requirement it was written against outright, moving the rendering it
   asserts onto the new journal page's own requirement instead (covered fresh
   by this pass's `test_launch_journal_page.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it`).
3. **`tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py::test_journal_entries_render_newest_first`**
   — same superseding requirement and evidence as (2).
4. **`tests/unit/launch/infrastructure/driving/test_launch_admin_detail.py::test_an_empty_journal_says_so`**
   — same superseding requirement and evidence as (2).

**Deliberately not listed, with reason:** the pre-existing bearing tests for
the other four MODIFIED requirements — *Both surfaces are read-only*, *A
launch the caller may not see is indistinguishable...*, *Both surfaces ride
the admin session and carry the shared header*, and *The pages' presentation
comes from the shared admin vocabulary* — in `test_launch_admin_detail.py`
(e.g. `test_the_pages_present_no_launch_changing_control`,
`test_a_product_with_no_launch_is_refused_as_absent`,
`test_a_request_without_a_session_is_refused_as_absent`,
`test_the_header_names_the_other_surfaces`,
`test_the_pages_carry_no_styling_of_their_own`, and their siblings). Compared
against the delta: each of these four requirements' WHEN clause is *widened*
from "either page" / "both pages" to "any of the three pages" / "all three
pages", while the THEN clause is unchanged. Nothing these existing tests
assert about the list and the detail page becomes false under the new
wording — they remain true, narrower-scoped statements the new tests in
`test_launch_journal_page.py` extend to the journal page, not statements the
new wording contradicts. This is a considered determination, not an
unsearched gap: the search was made, and it found extension rather than
supersession.

## Unresolved project questions

- **No project-specific testing-stack skill was found for this project's
  stack** (pytest + FastAPI `TestClient` + hand-parsed HTML via
  `html.parser.HTMLParser`, as every sibling test in this directory already
  does). `ai-toolkit:python` and `ai-toolkit:testing` were loaded and
  followed; no further stack-specific skill applies. Recorded per this
  pass's own dispatch contract rather than silently proceeding on the floor
  alone without saying so.
- **Whether the four "obsolete, deliberately not listed" tests above should
  eventually be extended to the journal page themselves, or left as
  list+detail-only regression coverage while `test_launch_journal_page.py`
  carries the three-page guarantee going forward**, is a project decision
  this pass did not need to make (both files can coexist without
  contradiction) but that whoever implements — or a later pass — may want to
  settle explicitly, since two files asserting overlapping-but-differently-
  scoped guarantees over the same pages is a standing invitation to drift if
  one is edited and the other is not. Assumption taken: leave both, and treat
  `test_launch_journal_page.py`'s three-page versions as canonical for the
  *scope* named by this change, without touching the pre-existing narrower
  tests (which the additive-only rule forbids anyway).
- **The route path a journal route will actually use** is assumed to contain
  the literal substring "journal" (`tasks.md` 2.3 names
  `/admin/launches/{product_id}/journal`) — `_journal_template`'s own
  `pytest.fail` message says so explicitly if that assumption is wrong, so a
  wrongly-guessed path surfaces as a named locator failure rather than a
  silent false negative. Every test depending on it: all of
  `test_launch_journal_page.py`, and the journal-offer half of
  `test_launch_detail_breadcrumb.py`.

## What the implementation step must make pass

All 22 tests named in the Scenario accounting table above, run via:

```
uv run pytest tests/unit/launch/infrastructure/driving/test_launch_detail_breadcrumb.py \
  tests/unit/launch/infrastructure/driving/test_launch_journal_page.py \
  tests/unit/launch/infrastructure/driving/test_product_dossier_breadcrumb.py \
  tests/unit/launch/infrastructure/driving/test_playbook_step_name_link.py \
  tests/unit/launch/infrastructure/driving/test_playbook_admin_edit_create_breadcrumb.py
```

— or any subset, individually selectable by the runner-recognised names in
the table, for a task scoped to fewer than all of them (e.g. `tasks.md` 2.x
touches only the launch-surface files; 4.x touches only the two
playbook-admin files). None of the four "obsolete, deliberately not listed"
tests, nor the four listed obsolete candidates, need to change for this
pass's own tests to pass — they are independent unless and until a human
confirms retiring or rewriting one of the four listed candidates.
