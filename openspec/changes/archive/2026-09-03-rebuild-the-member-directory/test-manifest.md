# Test manifest — `rebuild-the-member-directory`

Written before any of this change's implementation exists, by an author
with no sight of it. Derived from the four delta specs under
`openspec/changes/rebuild-the-member-directory/specs/`, read from disk,
against the committed plan at **`8c25749`**.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and must
be read on purpose before implementing.

**This pass adds tests and never subtracts.** Eight files were created;
no existing test was edited, deleted or disabled, and nothing outside
`tests/**/test_*.py` was written except this manifest. `git status`
after the pass shows eight untracked files and no modifications.

---

## Baseline

Taken at `8c25749`, before any test below was written (2026-09-02):

| Command | Result |
|---|---|
| `uv run pytest tests/unit tests/agents` | **2090 passed, 0 failed** |
| `uv run pytest tests/integration` | **3 passed, 134 skipped** |

The integration tier skips wholesale because this worktree configures no
database — deliberately, since `AGENTS.md` forbids migrating the shared
`commerce_ops_test` from here and `tasks.md` 11.5 has the implementer
clone it into a worktree-local database first. There is no `.env.test`.

## After this pass

| Command | Result |
|---|---|
| `uv run pytest tests/unit tests/agents` | 105 failed, **2093 passed** |
| `uv run pytest tests/integration` | 3 passed, 138 skipped |
| `uv run ruff check` / `ruff format --check` | clean |
| `uv run mypy .` | clean (476 files) |

2093 = the 2090 baseline passes, untouched, plus three new tests that
pass on their first run (see *Tests that pass on their first run*). All
105 failures are new tests; **no pre-existing test changed state**.

---

## Files written

| File | Capability | Tier |
|---|---|---|
| `tests/unit/access/application/test_role_writes.py` | `roles` reqs 1–5 | unit |
| `tests/unit/access/application/test_role_seeding.py` | `roles` req 6 | unit |
| `tests/unit/access/application/test_member_deactivation_role_invariant.py` | `members` | unit |
| `tests/unit/access/infrastructure/driving/test_roles_admin_page.py` | `roles-admin` reqs 1–5 | unit |
| `tests/unit/access/infrastructure/driving/test_roles_admin_navigation_and_vocabulary.py` | `roles-admin` reqs 6–8 | unit |
| `tests/unit/access/infrastructure/driving/test_members_surface_rebuild.py` | `members-admin` reqs 1–3 + breadcrumb | unit |
| `tests/unit/access/infrastructure/driving/test_members_surface_vocabulary_rebuild.py` | `members-admin` vocabulary + header | unit |
| `tests/integration/access/test_roles_store_live.py` | `roles` adapter and schema | integration |

Every test is named so the runner can select it individually, e.g.

```
uv run pytest "tests/unit/access/application/test_role_writes.py::test_a_duplicate_slug_is_rejected"
```

---

## Scenario accounting

**93 scenarios in the delta specs; 93 accounted for below.** 88 covered by
a new test, 5 covered by an existing test the revision does not touch, 0
uncovered.

### `roles` — 31 scenarios, all ADDED

All in `tests/unit/access/application/`.

| Scenario | Test |
|---|---|
| A role is identified by its slug | `test_role_writes.py::test_a_role_is_identified_by_its_slug` |
| A malformed slug is rejected | `test_role_writes.py::test_a_malformed_slug_is_rejected` (7 params) |
| A duplicate slug is rejected | `test_role_writes.py::test_a_duplicate_slug_is_rejected` (3 params) |
| A deactivated member cannot be added as a holder | `test_role_writes.py::test_a_deactivated_member_cannot_be_added_as_a_holder` |
| Multiple faults are reported together | `test_role_writes.py::test_multiple_faults_are_reported_together` |
| A landed write is attributed | `test_role_writes.py::test_a_landed_write_is_attributed` |
| A rejected write leaves the collection unchanged | `test_role_writes.py::test_a_rejected_write_leaves_the_collection_unchanged` |
| A slug cannot be updated | `test_role_writes.py::test_a_slug_cannot_be_updated` |
| A title is corrected freely | `test_role_writes.py::test_a_title_is_corrected_freely` |
| An active role cannot be left without a default holder | `test_role_writes.py::test_an_active_role_cannot_be_left_without_a_default_holder` |
| A draft role may hold nobody | `test_role_writes.py::test_a_draft_role_may_hold_nobody` |
| A retired role keeps its holders | `test_role_writes.py::test_a_retired_role_keeps_its_holders` |
| A member holds several roles | `test_role_writes.py::test_a_member_holds_several_roles` |
| Removing the default of an active role is refused | `test_role_writes.py::test_removing_the_default_of_an_active_role_is_refused` |
| A non-default holder leaves freely | `test_role_writes.py::test_a_non_default_holder_leaves_freely` |
| The default moves to another holder | `test_role_writes.py::test_the_default_moves_to_another_holder` |
| The default cannot move to a non-holder | `test_role_writes.py::test_the_default_cannot_move_to_a_non_holder` |
| A draft role's default may be removed | `test_role_writes.py::test_a_draft_roles_default_may_be_removed` |
| Activating a draft role requires a default holder | `test_role_writes.py::test_activating_a_draft_role_requires_a_default_holder` |
| A draft role with a default holder activates | `test_role_writes.py::test_a_draft_role_with_a_default_holder_activates` |
| An abandoned draft is retired | `test_role_writes.py::test_an_abandoned_draft_is_retired` |
| Un-retiring a role whose default is deactivated is refused | `test_role_writes.py::test_un_retiring_a_role_whose_default_is_deactivated_is_refused` |
| A retired role cannot return to draft | `test_role_writes.py::test_a_retired_role_cannot_return_to_draft` |
| Retirement is attributed and reversible | `test_role_writes.py::test_retirement_is_attributed_and_reversible` |
| An empty collection is seeded with eleven roles | `test_role_seeding.py::test_an_empty_collection_is_seeded_with_eleven_roles` |
| A seeded role that was edited is not reset | `test_role_seeding.py::test_a_seeded_role_that_was_edited_is_not_reset` |
| Roles missing from an edited collection are added | `test_role_seeding.py::test_roles_missing_from_an_edited_collection_are_added` |
| The newly seeded admin holds the eight active roles | `test_role_seeding.py::test_the_newly_seeded_admin_holds_the_eight_active_roles` |
| An already-administered membership resolves a seeding administrator | `test_role_seeding.py::test_an_already_administered_membership_resolves_a_seeding_administrator` |
| The choice is deterministic | `test_role_seeding.py::test_the_choice_is_deterministic` |
| An unusable store fails the step | `test_role_seeding.py::test_an_unusable_store_fails_the_step` (2 params) |

Requirement sentences carrying no scenario, covered anyway:

| Sentence | Test |
|---|---|
| "The collection SHALL offer no deletion" | `test_role_writes.py::test_the_collection_offers_no_deletion` |
| "the member the admin seeding established on this run … otherwise the earliest-created active admin" | `test_role_seeding.py::test_the_admin_established_on_this_run_wins`, `::test_the_earliest_created_active_admin_is_chosen_not_the_first_row` |
| "The step that seeds the first admin SHALL also seed the roles … before the HTTP server begins serving" | `test_role_seeding.py::test_the_start_chain_seeds_the_roles_before_the_server_serves` |
| "holding a role SHALL confer no authority of its own" | asserted inside `test_role_writes.py::test_a_member_holds_several_roles` |
| Postgres round-trip, shared version row, one-default index | `tests/integration/access/test_roles_store_live.py` (4 tests) |

### `roles-admin` — 29 scenarios, all ADDED

All in `tests/unit/access/infrastructure/driving/`.

| Scenario | Test |
|---|---|
| The whole collection is one page | `test_roles_admin_page.py::test_the_whole_collection_is_one_page` |
| The three statuses are set apart | `test_roles_admin_page.py::test_the_three_statuses_are_set_apart` |
| A role with no default holder is listed without one | `test_roles_admin_page.py::test_a_role_with_no_default_holder_is_listed_without_one` |
| A role's row carries no actions | `test_roles_admin_page.py::test_a_roles_row_carries_no_actions` (4 params) |
| A role's title opens its page | `test_roles_admin_page.py::test_a_roles_title_opens_its_page` |
| The slug is shown but is not a link | `test_roles_admin_page.py::test_the_slug_is_shown_but_is_not_a_link` |
| Creating is reached from the list | `test_roles_admin_page.py::test_creating_is_reached_from_the_list` |
| An active role is created with its default holder in one submission | `test_roles_admin_page.py::test_an_active_role_is_created_with_its_default_holder_in_one_submission` |
| A draft role is created holding nobody | `test_roles_admin_page.py::test_a_draft_role_is_created_holding_nobody` |
| An active role submitted without a holder is rejected | `test_roles_admin_page.py::test_an_active_role_submitted_without_a_holder_is_rejected` |
| The slug is not editable | `test_roles_admin_page.py::test_the_slug_is_not_editable` |
| Only permitted transitions are offered | `test_roles_admin_page.py::test_only_permitted_transitions_are_offered` |
| A draft role is offered activation | `test_roles_admin_page.py::test_a_draft_role_is_offered_activation` |
| Holders are managed from the role's page | `test_roles_admin_page.py::test_holders_are_managed_from_the_roles_page` |
| The role's attribution is readable | `test_roles_admin_page.py::test_the_roles_attribution_is_readable` |
| A rejected write shows every fault with the typed values | `test_roles_admin_page.py::test_a_rejected_write_shows_every_fault_with_the_typed_values` |
| A refused activation explains its own obligation | `test_roles_admin_page.py::test_a_refused_activation_explains_its_own_obligation` |
| A refused default removal explains its own obligation | `test_roles_admin_page.py::test_a_refused_default_removal_explains_its_own_obligation` |
| A role's page offers the list | `test_roles_admin_navigation_and_vocabulary.py::test_a_roles_page_offers_the_list` |
| The create page offers the list | `test_roles_admin_navigation_and_vocabulary.py::test_the_create_page_offers_the_list` |
| The breadcrumb needs no scripting | `test_roles_admin_navigation_and_vocabulary.py::test_the_breadcrumb_needs_no_scripting` |
| Every other admin surface is reachable from the roles surface | `test_roles_admin_navigation_and_vocabulary.py::test_every_other_admin_surface_is_reachable_from_the_roles_surface` |
| The header is rendered on an empty collection | `test_roles_admin_navigation_and_vocabulary.py::test_the_header_is_rendered_on_an_empty_collection` |
| A role's own page carries the header too | `test_roles_admin_navigation_and_vocabulary.py::test_a_roles_own_page_carries_the_header_too` |
| The create page carries the header too | `test_roles_admin_navigation_and_vocabulary.py::test_the_create_page_carries_the_header_too` |
| The pages carry no styling of their own | `test_roles_admin_navigation_and_vocabulary.py::test_the_pages_carry_no_styling_of_their_own` |
| The destructive action is distinguished, not amplified | `test_roles_admin_navigation_and_vocabulary.py::test_the_destructive_action_is_distinguished_not_amplified` |
| Un-retiring is not destructive | `test_roles_admin_navigation_and_vocabulary.py::test_un_retiring_is_not_destructive` |
| Removing a holder is not destructive | `test_roles_admin_navigation_and_vocabulary.py::test_removing_a_holder_is_not_destructive` |

### `members` — 6 scenarios, one ADDED requirement

All in `tests/unit/access/application/test_member_deactivation_role_invariant.py`.

| Scenario | Test |
|---|---|
| Deactivating an active role's default holder is refused | `::test_deactivating_an_active_roles_default_holder_is_refused` |
| Every blocking role is named at once | `::test_every_blocking_role_is_named_at_once` |
| A non-default holder deactivates freely | `::test_a_non_default_holder_deactivates_freely` |
| Holding only draft or retired roles does not block | `::test_holding_only_draft_or_retired_roles_does_not_block` |
| Moving the default unblocks the deactivation | `::test_moving_the_default_unblocks_the_deactivation` |
| Both refusals report together | `::test_both_refusals_report_together` |

Requirement prose with no scenario:

| Sentence | Test |
|---|---|
| "independent … a write may be refused by either, by both, or by neither" | `::test_an_admin_holding_no_active_default_is_refused_by_the_floor_alone` |
| "the system SHALL NOT do either implicitly on the member's behalf" | `::test_the_membership_moves_no_default_and_retires_no_role_implicitly` and the intermediate step of `::test_moving_the_default_unblocks_the_deactivation` |

### `members-admin` — 27 scenarios, 5 MODIFIED requirements + 1 ADDED

New tests are in `tests/unit/access/infrastructure/driving/test_members_surface_rebuild.py`
(`rebuild`) and `…/test_members_surface_vocabulary_rebuild.py` (`vocab`).

| Requirement | Scenario | Test |
|---|---|---|
| MODIFIED *shows the membership whole* | An entry's attribution is readable | `rebuild::test_an_entrys_attribution_is_readable_on_the_members_page` |
| | The whole active membership is one page | **existing**: `test_members_admin_page.py::test_the_whole_active_members_is_one_page` |
| | Deactivated members are reachable but set apart | **existing**: `test_members_admin_page.py::test_deactivated_members_are_reachable_but_set_apart` |
| | A member's row carries no actions | `rebuild::test_a_members_row_carries_no_actions` (2 params) |
| | A member's name opens their own page | `rebuild::test_a_members_name_opens_their_own_page` |
| MODIFIED *created and edited* | A created member appears on the page | `rebuild::test_a_created_member_appears_on_the_page` |
| | Creating is reached from the list | `rebuild::test_creating_is_reached_from_the_list` |
| | A rejected write shows every fault with the typed values | `rebuild::test_a_rejected_write_shows_every_fault_with_the_typed_values` |
| | Editing happens on the member's page | `rebuild::test_editing_happens_on_the_members_page` |
| MODIFIED *deactivation and reactivation* | A deactivation lands and the member is set apart | `rebuild::test_a_deactivation_lands_and_the_member_is_set_apart` |
| | A blocked deactivation explains itself | `rebuild::test_a_blocked_deactivation_explains_itself` |
| | A role-blocked deactivation names every blocking role | `rebuild::test_a_role_blocked_deactivation_names_every_blocking_role` |
| MODIFIED *shared admin vocabulary* | The page carries no styling of its own | `vocab::test_every_team_surface_page_carries_no_styling_of_its_own` |
| | The stylesheet is refused without an admin session | **existing**: `test_members_admin_presentation_vocabulary.py::test_the_stylesheet_is_refused_without_an_admin_session` |
| | The destructive action is distinguished, not amplified | `vocab::test_the_destructive_action_is_distinguished_not_amplified` |
| | A deactivated member's action is not destructive | `vocab::test_a_deactivated_members_action_is_not_destructive` |
| | The create control speaks the same vocabulary | `vocab::test_the_create_control_speaks_the_same_vocabulary` |
| | A row carries neither marker | `vocab::test_a_row_carries_neither_marker` (2 params) |
| | The workaround rule is gone | `vocab::test_the_workaround_rule_is_gone` — see **Defect 1** |
| MODIFIED *header* | The playbook page is reachable from the membership | **existing**: `test_members_admin_presentation_vocabulary.py::test_the_playbook_page_is_reachable_from_the_members` |
| | Every other admin surface is reachable from the membership | **existing**: `test_members_header_names_every_surface.py::test_every_other_admin_surface_is_reachable_from_the_members` |
| | The header is rendered on a membership holding nobody | **existing**: `test_members_admin_presentation_vocabulary.py::test_the_header_is_rendered_on_a_members_holding_nobody` |
| | A surface added later is named by the header | `vocab::test_the_roles_surface_is_named_by_the_members_header` |
| | The create page and a member's page carry the header too | `vocab::test_the_create_page_and_a_members_page_carry_the_header_too` |
| ADDED *breadcrumb* | A member's page offers the list | `rebuild::test_a_members_page_offers_the_list` |
| | The create page offers the list | `rebuild::test_the_create_page_offers_the_list` |
| | The breadcrumb needs no scripting | `rebuild::test_the_breadcrumb_needs_no_scripting` |

**Why five scenarios keep their existing tests.** Each is carried
forward by the MODIFIED requirement with its text unchanged, and what it
observes is untouched by the rebuild — the list still lists the whole
active membership, deactivated members are still set apart, the
stylesheet guard is unchanged, and the three header scenarios concern
the *list*, which keeps its header. Writing a second test asserting the
same thing about the same page would add no evidence. *A surface added
later is named by the header* is the exception: its existing test covers
the launch and product surfaces, and the roles surface is the case the
requirement's own prose now names, so it gets its own test.

**No scenario is uncovered.** There is no `REMOVED` or `RENAMED` delta in
this change, so no scenario is accounted for by that route.

---

## Assertion classification

Every test file's module docstring carries its own "What is fixed, and
what is INVENTED" section, and every assertion in the bodies is marked
inline `# SPECIFIED:` or `# DERIVED:`. Summary of what is **not**
specified:

### Derived assertions

| Assertion | Where | Why derived |
|---|---|---|
| The reactivation half of the member surface (no scenario states it) | `rebuild::test_a_reactivation_is_offered_on_the_members_page` | The requirement's own sentence offers it; no scenario does. Without it a rebuild offering no way back from deactivation passes. |
| No rule selecting a form in an actions cell remains at all | `vocab::test_the_workaround_rule_is_gone` | The scenario names `display: contents` only; see Defect 1. |
| "when" renders carrying the current year | attribution tests in `roles_admin_page`, `rebuild` | The delta fixes that a time is presented, not its format. |
| The row of `supply-chain` names its default and not its non-default holder | `test_roles_admin_page.py::test_the_whole_collection_is_one_page` | Discrimination guard; the delta says "its default holder", not "not its other holders". |
| A refusal naming a role the member merely holds is wrong | `test_member_deactivation_role_invariant.py::test_every_blocking_role_is_named_at_once` | Discrimination guard, inferred from "would be left without a default holder". |
| Fault wording markers ("default", "holder", "admin", "slug", "title") | throughout | The deltas fix that an explanation is given, not its words. Each is a **locator**, and each test fails loudly if it cannot find one. |
| The seed's created-on is a `datetime`; the role's attribution fields are datetimes | `test_role_seeding.py`, `test_role_writes.py` | "and when" fixes that a time is recorded, not its type. |
| A generated identifier is UUID-shaped | `test_role_writes.py::test_a_role_is_identified_by_its_slug` | "no separate generated one" is specified; recognising one by UUID shape is the invented mechanism. |
| The membership's use cases expose no force/cascade escape hatch | `test_member_deactivation_role_invariant.py::test_the_membership_moves_no_default_and_retires_no_role_implicitly` | Structural stand-in for a behavioural sentence. |
| The application surface exports no role deletion verb | `test_role_writes.py::test_the_collection_offers_no_deletion` | Structural stand-in for "offers no deletion". |

### Deliberately untested

| Case | Reason |
|---|---|
| Inline `style` attributes on individual elements | The scenarios say "carries no page-local style **block**". Asserting the absence of every inline attribute would oblige an implementer to a constraint nobody stated. The same bound `test_members_admin_presentation_vocabulary.py` already recorded. |
| How anything looks — row density, whether status groups read as visually distinct | `tasks.md` 9.1–9.3 carry these as a manual presentation pass with the user. A server response cannot establish them. |
| That the container's start chain actually executes the seeding step | A Dockerfile `CMD`, observable only by running the image (`tasks.md` 11.8). Its *ordering* is asserted against the `CMD` line. |
| A role deletion reachable only through the store adapter, bypassing the application surface | The no-deletion test reads the public surface only. A repository method deleting a row would not be caught. |
| The Alembic migration in both directions | `tasks.md` 11.7; needs the worktree-local database clone that does not exist yet. |
| Column order on the Team list | The change's own Open Question, left to the presentation pass; it changes no requirement. |
| Concurrency between two *role* writes at the unit tier | A store double can only assert that `save` was called with the version `load` returned. The real property is covered in the integration file. |

---

## Obsolete tests — candidates for human confirmation

The change carries five `MODIFIED` requirements, all in `members-admin`,
and every one of them moves where a behaviour is observed: from the Team
list onto the create page or the member's own page. The tests below
observe the superseded location.

**Search bound.** Only `tests/**/test_*.py` — the dispatched glob — was
searched. No earlier `test-manifest.md` was supplied, so the mapping was
made by reading each candidate test's own docstring and assertions
against the shipped `openspec/specs/members-admin/spec.md` and the delta.
No test outside that glob was considered.

**Every entry below is a candidate for human confirmation, not a
conclusion.** This pass edited, deleted and disabled none of them.

| # | Test (runner-selectable) | Superseding delta | Evidence |
|---|---|---|---|
| 1 | `tests/unit/access/infrastructure/driving/test_members_admin_page.py::test_an_entrys_attribution_is_readable` | MODIFIED *The Team page shows the membership whole* — attribution "SHALL be readable from the **member's own page** rather than from the list"; scenario's WHEN changed from "views a member's entry on the Team page" to "opens a member's own page" | Its docstring quotes the superseded WHEN verbatim; it asserts `THE_CREATING_ADMIN in entry` where `entry = _segment(region, RETIRED_IDENTITY, anchors)` is a region of the list page returned by `_get_page(client)`. Replaced by `rebuild::test_an_entrys_attribution_is_readable_on_the_members_page`, which additionally asserts the list no longer carries it. |
| 2 | `…test_members_admin_page.py::test_a_deactivation_lands_and_the_member_is_set_apart` | MODIFIED *Deactivation and reactivation are available from the page* — "SHALL be offered on that member's own page, not on their row"; plus the new scenario *A member's row carries no actions* | Discovers its control with `_member_control(html, …, verb="deactivate")` where `html = _get_page(client)` — the list. After the rebuild no such control exists on the list. Replaced by `rebuild::test_a_deactivation_lands_and_the_member_is_set_apart`. |
| 3 | `…test_members_admin_page.py::test_a_blocked_deactivation_explains_itself` | same as #2 | Same `_member_control(html, …, verb="deactivate")` discovery against the list page. Replaced by `rebuild::test_a_blocked_deactivation_explains_itself`. |
| 4 | `…test_members_admin_page.py::test_a_reactivation_from_the_page_restores_the_member` | same as #2 | `_member_control(view, …, verb="reactivate")` where `view` is the list or a view one list control away. Replaced by `rebuild::test_a_reactivation_is_offered_on_the_members_page`. |
| 5 | `…test_members_admin_page.py::test_an_edit_from_the_page_lands_through_the_use_cases` | MODIFIED *A member can be created and edited from the page* — "Editing … SHALL happen on that member's own page, rather than through inputs carried in a row's cells" | Its docstring quotes the superseded requirement sentence ("The Team page SHALL offer creating a member and editing…"); `_edit_form` accepts an inline form on the list as its first candidate and otherwise follows a per-row `edit` control. Replaced by `rebuild::test_editing_happens_on_the_members_page`. |
| 6 | `…test_members_admin_page.py::test_a_created_member_appears_on_the_page` | MODIFIED *A member can be created and edited from the page* — scenario's WHEN changed to "from the **create page**"; plus the new scenario *Creating is reached from the list* | `_create_form(client, html)` takes an inline form on the list as its **first** candidate, which is exactly the layout this change removes; it may keep passing through its fallback branch, but it no longer discriminates. Replaced by `rebuild::test_a_created_member_appears_on_the_page`. **Lower confidence than #1–#5** — confirm whether it is worth keeping as a weaker duplicate. |
| 7 | `…test_members_admin_page.py::test_a_rejected_write_shows_every_fault_with_the_typed_values` | same as #6, plus the revision's new sentence "A rejection SHALL NOT return the admin to the list" | Same `_create_form(client, html)` first-candidate problem, and it asserts nothing about not returning to the list. Replaced by `rebuild::test_a_rejected_write_shows_every_fault_with_the_typed_values`, which adds that assertion. |
| 8 | `tests/unit/access/infrastructure/driving/test_members_admin_presentation_vocabulary.py::test_the_destructive_action_is_distinguished_not_amplified` | MODIFIED *The page's presentation comes from the shared admin vocabulary* — scenario's WHEN changed from "an active member's **row**" to "an active member's own **page**"; plus the new scenario *A row carries neither marker* | Reads `row = _member_row(_tree(_get_page(client)), MEMBER_IDENTITY)`, and that file's `_member_row` requires the row to hold *at least one action control* — after the rebuild a row holds none, so the locator itself can no longer resolve. Replaced by `vocab::test_the_destructive_action_is_distinguished_not_amplified`. |
| 9 | `…test_members_admin_presentation_vocabulary.py::test_a_deactivated_members_action_is_not_destructive` | same as #8 | Same `_member_row` locator, same row→page move. Replaced by `vocab::test_a_deactivated_members_action_is_not_destructive`. |
| 10 | `…test_members_admin_presentation_vocabulary.py::test_the_create_control_speaks_the_same_vocabulary` | MODIFIED, same requirement — scenario's WHEN changed from "the page's add-a-member form" to "the **create page**" | `_create_form(_tree(_get_page(client)))` searches the list page only and `pytest.fail`s if no add-a-member form is on it. Replaced by `vocab::test_the_create_control_speaks_the_same_vocabulary`. |

**No test bearing on these deltas was found outside that list.** Ten
entries were found; the list is not empty, and this is a positive
finding rather than an unsearched one.

### A collision, not a supersession — needs a decision

`tests/unit/access/application/test_members_writes.py::test_the_members_offers_no_deletion`
asserts that **no** name in `commerce_ops.access.application.__all__`
contains `delete`, `remove` or `purge`:

```python
offending = [
    name
    for name in exported
    if any(verb in name.lower() for verb in ("delete", "remove", "purge"))
]
assert offending == []
```

The `roles` requirement *Holders are managed as a set and the default is
moved deliberately* requires a remove-a-holder use case, and `tasks.md`
4.6 exports the role use cases from that same `__all__`. A use case named
`remove_role_holder` or `remove_holder` **will make this existing test
fail**, on a change that does not supersede what it asserts — the
membership still offers no deletion.

This is not an obsolete-test entry: the test's subject survives, its
*mechanism* over-reaches into a surface this change extends. It is
recorded here because whoever implements will meet it, and because the
resolution is a decision, not a repair: narrow the scan, or name the use
case so it does not trip. This pass did not edit it, and the new
`test_role_writes.py::test_the_collection_offers_no_deletion` deliberately
excludes holder verbs from its own scan for the same reason.

---

## Tests that pass on their first run

`ai-toolkit:testing` treats a first-run pass as an alarm, not a result.
Three of the 108 new tests pass at `8c25749`, each for a stated reason:

| Test | Why it passes now | What it will catch |
|---|---|---|
| `test_role_writes.py::test_the_collection_offers_no_deletion` | The surface exports no role use cases at all, so it has none to offend | A `delete_role`/`purge_role` verb added later |
| `test_member_deactivation_role_invariant.py::test_the_membership_moves_no_default_and_retires_no_role_implicitly` | `deactivate_member` has no `force`/`cascade`/`promote` parameter today | Such a parameter being added to satisfy the new refusal |
| `test_role_seeding.py::test_the_start_chain_seeds_the_roles_before_the_server_serves` | `seed_admin` already precedes `uvicorn` and the chain has no role process | A *separate* role-seeding process being added to the chain instead of extending `seed_admin` |

Each asserts an absence and cannot fail on an absent target. They are
recorded as guards, not as coverage of behaviour this change adds.

The remaining 105 fail. Two distinct states, which establish different
things:

- **Absent target** — the role use cases, the `roles_admin` module and the
  roles adapter do not exist. The assertions below the resolver never
  ran, so nothing is established about whether they are any good. This
  covers `test_role_writes.py`, `test_role_seeding.py`,
  `test_member_deactivation_role_invariant.py`, both roles-admin files,
  `rebuild::test_a_role_blocked_deactivation_names_every_blocking_role`
  and `vocab::test_the_roles_surface_is_named_by_the_members_header`.
- **Wrong value** — the Team page renders and what is asserted of it is
  not there. This covers the rest of `test_members_surface_rebuild.py`
  and `test_members_surface_vocabulary_rebuild.py`. These assertions
  *have* been exercised.

Two gates were confirmed to fire against the current implementation
rather than merely to pass later (`tasks.md` 10.9):

- `rebuild::test_a_members_row_carries_no_actions` fails with
  *"'U03CAROL''s row encloses 2 form(s)"* — it really sees today's row
  actions.
- `vocab::test_the_workaround_rule_is_gone` fails naming
  `td.actions form` in the served stylesheet.

**A locator defect was found and corrected during this pass, and is
recorded because it is the exact failure mode `tasks.md` 10.9 names.**
`_member_row` and `_role_row` were first written as the *smallest*
element naming one record — the idiom the existing vocabulary test uses.
Read that way, `test_a_members_row_carries_no_actions` **passed** on the
current implementation, because the smallest element naming a member is a
leaf cell that carries no controls whatever the page does: a property
true by construction. Both locators now take the **largest** element
naming one record and no other that encloses none of the structures a row
never encloses (`_NOT_A_ROW`). The corrected locator fails, and fails
naming the two forms it found.

---

## Unresolved project questions

Each was resolved by assumption because this pass has no channel to ask
on. Each names the assumption taken and the tests that depend on it.

| # | Question | Assumption taken | Tests depending on it |
|---|---|---|---|
| 1 | `tasks.md` 10.7 asks for **integration** tests of both admin surfaces' routes; every existing admin-surface test in this repository is in `tests/unit/.../driving/` over store doubles | Followed the repository's precedent and `testing`'s level rule — the smallest unit that can observe the outcome — and wrote the admin-surface tests at the **unit** tier. Only the adapter and schema properties a double cannot show went to `tests/integration/` | all four admin-surface files, and `tests/integration/access/test_roles_store_live.py` |
| 2 | `tasks.md` 10.1 asks for domain-level tests of the role entity and 10.2 for use-case tests | Folded both into the application tier: every `roles` scenario is stated over a write and what is persisted, which the domain alone cannot observe. Splitting would oblige an invented `Role` constructor API no artifact fixes | `test_role_writes.py` (whole file) |
| 3 | The roles **port** shape. `design.md` Decision 8 fixes the shared version row but not the port | Mirrored the membership's `load() -> (rows, version)` / `save(rows, expected_version=…)`, over a version cell shared with the members store. `load_roles`/`save_roles` aliases are offered too | every unit file's `_FakeRolesStore` |
| 4 | The role use cases' **names** | Resolved over candidate tuples (`create_role`, `update_role`, `retire_role`, `unretire_role`/`activate_role`, `add_role_holder`, `remove_role_holder`, `move_role_default`, …), failing loudly with the candidate list | all role tests; correction points are the `_*_NAMES` tuples |
| 5 | The role use cases' **call shapes** | `roles=`, `members=`, `principal=`, `slug=`, `title=`, `status=`, `default_holder=`, `member_id=` — attempted in order, only argument-shape `TypeError`s falling through | all role tests; correction points are the `_create_role`/`_role_action` helpers |
| 6 | Whether a status crosses the use-case boundary as a string or a domain enum | String first, then the enum resolved from `commerce_ops.access.domain.roles` if one exists | `test_role_writes.py::_status` |
| 7 | How `deactivate_member` reaches the role collection | A `roles=` keyword, with a no-`roles` shape attempted as a fallback. Called through an untyped alias so `mypy --strict` does not report the absence these tests exist to report | `test_member_deactivation_role_invariant.py` (whole file) |
| 8 | How the **Team page** reaches the role collection to surface the role-blocked refusal | A module-level `roles` name, bound with `monkeypatch.setattr(..., raising=False)` | `rebuild::test_a_role_blocked_deactivation_names_every_blocking_role` |
| 9 | The Roles page module's name and seams | `commerce_ops.access.infrastructure.driving.roles_admin`, exposing `router` and module-level `roles`, `members`, `verify_admin_session` — the seams `members_admin` uses | both roles-admin files |
| 10 | What "carries the marker `X`" means in the response | A class token, per `design.md`'s `class="row-action"` | every `_carries` assertion |
| 11 | What counts as an **action control** on a record's own page | A submit control inside a form. Every change these surfaces offer changes state, so each is a submitted form; reading every anchor as one would sweep in the header and breadcrumb links, which the requirement does not speak about | `_page_actions` in both vocabulary files |
| 12 | How the member the admin seeding established **on this run** reaches the role seed | An argument, tried under five keyword spellings. `test_the_admin_established_on_this_run_wins` requires one of them to match, because a signature that cannot express the first branch cannot implement it | `test_role_seeding.py::test_the_admin_established_on_this_run_wins` |
| 13 | The roles repository's module and class names, and the stale-write refusal type | `roles_repository.RolesRepository`; `StaleMembersError`/`StaleRolesError`. Resolved at call time so their absence fails only the tests that drive them | `tests/integration/access/test_roles_store_live.py` |
| 14 | The role-holder table's column names for the direct insert that provokes the partial unique index | `design.md` Decision 9's names. An unrecognised required column fails loudly rather than being guessed | `…test_roles_store_live.py::test_at_most_one_default_holder_is_a_storage_guarantee` |
| 15 | No database is configured in this worktree, and `AGENTS.md` forbids migrating the shared `commerce_ops_test` from here | The integration file was written and left skipping. `tasks.md` 11.5 has the implementer clone the database and name it in `.env.test` | all four tests in `tests/integration/access/test_roles_store_live.py` |
| 16 | No skill in the library covers the FastAPI/HTML admin-surface idiom these tests drive | Loaded `ai-toolkit:testing` and `ai-toolkit:python` (with its pytest reference), and followed this repository's own established harness for admin pages | the four admin-surface files |

---

## Defects found in the change's artifacts

Reported, not acted on. This pass never edits `proposal.md`,
`design.md`, `tasks.md` or the delta specs.

### Defect 1 — the CSS rule named for removal does not exist

`members-admin`'s MODIFIED presentation requirement, `proposal.md` ("The
`display: contents` hack goes with it"), `design.md` Decision 10's
context and `tasks.md` 8.5 all name the rule to be removed as:

```css
td.actions form { display: contents }
```

The rule the served shared stylesheet actually carries is:

```css
td.actions form {
  display: inline;
  margin: 0;
}
```

and its own comment records that `display: contents` "was the first
approach — it collapses…" and was replaced. The scenario as literally
stated is therefore **already satisfied** and would pass whether or not
this change happened — the fourth failure state, an assertion that
establishes nothing.

`vocab::test_the_workaround_rule_is_gone` asserts the scenario literally
*and*, alongside it, the requirement's own qualifier ("rather than left
behind as a rule matching nothing", `tasks.md` 8.5's "confirm no rule
matching nothing is left behind"): that **no** rule selecting a form
inside a table's actions cell remains. That second assertion is marked
DERIVED and is the one that fails today. If the artifacts are corrected
to name `display: inline`, the literal assertion should be corrected with
them; the derived one stands either way.

### Defect 2 — an existing test collides with an added requirement

See *A collision, not a supersession* above:
`test_members_writes.py::test_the_members_offers_no_deletion` will fail
once a `remove_*` role use case is exported from
`access/application/__init__.py`'s `__all__`, on a change that does not
supersede what that test asserts.

---

## What the implementation step must make pass

Run the new tests in this order; each group is a coherent unit of work.

```bash
# 1. the role model and its write use cases
uv run pytest tests/unit/access/application/test_role_writes.py

# 2. the seed, both branches of the seeding administrator
uv run pytest tests/unit/access/application/test_role_seeding.py

# 3. the member/role invariant, from the membership's side
uv run pytest tests/unit/access/application/test_member_deactivation_role_invariant.py

# 4. the Roles admin surface
uv run pytest tests/unit/access/infrastructure/driving/test_roles_admin_page.py \
              tests/unit/access/infrastructure/driving/test_roles_admin_navigation_and_vocabulary.py

# 5. the Team surface rebuild
uv run pytest tests/unit/access/infrastructure/driving/test_members_surface_rebuild.py \
              tests/unit/access/infrastructure/driving/test_members_surface_vocabulary_rebuild.py

# 6. the adapter and schema — needs the worktree-local database clone
#    (tasks.md 11.5), then:
COMMERCE_OPS_REQUIRE_DATABASE=1 uv run pytest tests/integration/access/test_roles_store_live.py
```

And the whole suite must stay green apart from these: the 2090 baseline
passes are the floor, and Defect 2 is the one place where a baseline test
is expected to be confronted rather than left alone.
