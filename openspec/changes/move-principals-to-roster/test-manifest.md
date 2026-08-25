# Test manifest — move-principals-to-roster

Written by the test-authoring pass, **before** any implementation of this
change existed. This file is not part of the OpenSpec schema: it will not
appear among `openspec instructions apply`'s context files and must be read
on purpose.

The pass is **additive only**. It created six new test files and edited,
deleted or disabled nothing. Every existing test still stands, including
the ones listed under *Obsolete-test candidates* below — those are
candidates for a human decision, not actions taken.

## Baseline

| What | Command | Result |
| --- | --- | --- |
| Test baseline (full commit-time tier) | `uv run pytest tests/unit tests/agents` | **665 passed, 0 failed** (2026-08-25) |
| Type baseline | `uv run mypy .` | **1 pre-existing error**, unrelated to this pass: `tests/unit/access/infrastructure/test_admin_link_exchange_route.py:71: Module "commerce_ops.access.infrastructure.driving" has no attribute "admin_link"` |
| Lint / format | `uv run ruff check` / `ruff format --check` over the new files | clean |

The `tests/integration` tier was **not** run: it needs a live Postgres
(`DATABASE_URL` unset here) and another session held that directory during
this pass. Nothing under `tests/integration/` and nothing in
`pyproject.toml` was read for writing, modified, or executed.

### First run of the new tests

`uv run pytest tests/unit/access` — all six new files fail at collection
with `ImportError: cannot import name 'create_person' from
'commerce_ops.access.application'` (and the page module's absence).

Per `ai-toolkit:testing` this is **failure state 2 — the target does not
exist yet**. It establishes that the target is absent and *nothing more*:
none of the assertions below has been exercised. No test passed on its
first run, so no state-4 alarm was raised.

Re-running the pre-existing suite with the six new files ignored still
gives **665 passed** — the pass added tests and subtracted nothing.

**Note for the implementation step:** until the roster use cases exist, the
`pytest-unit` pre-commit hook is red, because collection errors abort the
whole tier (the project's known full-suite hook behaviour). That is the
expected pre-implementation state, not a defect in the tests.

## Files written

| File | Covers |
| --- | --- |
| `tests/unit/access/application/test_roster_writes.py` | `roster` — requirements 1–4 (12 scenarios) |
| `tests/unit/access/application/test_roster_bootstrap.py` | `roster` — requirement 5, the startup seed (6 scenarios) |
| `tests/unit/access/application/test_roster_scope_resolution.py` | `access-scope` — ADDED scope resolution (3) + MODIFIED unknown asker (1) |
| `tests/unit/access/application/test_roster_admin_capability.py` | `access-scope` — ADDED admin capability (5 scenarios) |
| `tests/unit/access/application/test_admin_session_over_roster.py` | `admin-session` — MODIFIED, the roster-side scenarios (5) |
| `tests/unit/access/infrastructure/driving/test_roster_admin_page.py` | `roster-admin` (7 scenarios) + `admin-session`'s *No session means no surface* over the new routes |

No file outside `tests/**/test_*.py` was written except this manifest. A
shared `conftest.py` would have been the natural home for the roster-store
double, but `conftest.py` is not inside the dispatched test-path glob, so
the double and its row accessors are repeated per file instead. **They must
be corrected together.**

## Scenario coverage

Every `#### Scenario:` block in the change's four delta specs is accounted
for exactly once. **40 scenarios in the deltas; 40 accounted for here.**

### `roster` (NEW capability) — 18 scenarios

| Scenario | Test |
| --- | --- |
| A created person carries a generated identifier | `test_roster_writes.py::test_a_created_person_carries_a_generated_identifier` |
| A duplicate Slack identity is rejected | `test_roster_writes.py::test_a_duplicate_slack_identity_is_rejected` (parametrized `active`, `deactivated`) |
| Multiple faults are reported together | `test_roster_writes.py::test_multiple_faults_are_reported_together` |
| A landed write is attributed | `test_roster_writes.py::test_a_landed_write_is_attributed` |
| A rejected write leaves the roster unchanged | `test_roster_writes.py::test_a_rejected_write_leaves_the_roster_unchanged` |
| A Slack identity cannot be updated | `test_roster_writes.py::test_a_slack_identity_cannot_be_updated` |
| A deactivated entry can be corrected in place | `test_roster_writes.py::test_a_deactivated_entry_can_be_corrected_in_place` |
| Deactivating the last active admin is refused | `test_roster_writes.py::test_deactivating_the_last_active_admin_is_refused` |
| Withdrawing the last active admin's flag is refused | `test_roster_writes.py::test_withdrawing_the_last_active_admins_flag_is_refused` |
| An admin among admins can step down | `test_roster_writes.py::test_an_admin_among_admins_can_step_down` |
| A deactivated person remains on the roster | `test_roster_writes.py::test_a_deactivated_person_remains_on_the_roster` |
| Reactivation restores the same entry | `test_roster_writes.py::test_reactivation_restores_the_same_entry` |
| An empty roster is seeded | `test_roster_bootstrap.py::test_an_empty_roster_is_seeded` |
| An existing entry is promoted rather than duplicated | `test_roster_bootstrap.py::test_an_existing_entry_is_promoted_rather_than_duplicated` |
| A rostered admin makes the variable inert | `test_roster_bootstrap.py::test_a_rostered_admin_makes_the_variable_inert` |
| A mis-seeded first admin is corrected by redeploying | `test_roster_bootstrap.py::test_a_mis_seeded_first_admin_is_corrected_by_redeploying` |
| No admin and no variable stops startup | `test_roster_bootstrap.py::test_no_admin_and_no_variable_stops_startup` (partial — see *Uncovered*) |
| An unconfigured or unreachable store defers the bootstrap | `test_roster_bootstrap.py::test_an_unconfigured_or_unreachable_store_defers_the_bootstrap` (parametrized `unconfigured`, `unreachable`; partial — see *Uncovered*) |

Requirement sentences with no scenario of their own, also asserted:

- "The roster SHALL offer no deletion" → `test_roster_writes.py::test_the_roster_offers_no_deletion` (structural: the public surface exports no delete/remove/purge verb).
- The seed's "attributed to a reserved system principal" → asserted inside `test_an_empty_roster_is_seeded`.
- `design.md` Decision 4's "the bound expires the moment any admin beyond the lone seed exists" → `test_roster_bootstrap.py::test_the_bound_expires_once_an_admin_beyond_the_seed_exists` (DERIVED).

### `roster-admin` (NEW capability) — 7 scenarios

| Scenario | Test (all in `test_roster_admin_page.py`) |
| --- | --- |
| An entry's attribution is readable | `test_an_entrys_attribution_is_readable` |
| The whole active roster is one page | `test_the_whole_active_roster_is_one_page` |
| Deactivated people are reachable but set apart | `test_deactivated_people_are_reachable_but_set_apart` |
| A created person appears on the page | `test_a_created_person_appears_on_the_page` |
| A rejected write shows every fault with the typed values | `test_a_rejected_write_shows_every_fault_with_the_typed_values` |
| A deactivation lands and the person is set apart | `test_a_deactivation_lands_and_the_person_is_set_apart` |
| A blocked deactivation explains itself | `test_a_blocked_deactivation_explains_itself` |

Requirement sentences with no scenario, asserted as DERIVED:

- "editing an existing person's updatable fields" → `test_an_edit_from_the_page_lands_through_the_use_cases`.
- "reactivating a deactivated one" → `test_a_reactivation_from_the_page_restores_the_person`.

### `access-scope` — 9 scenarios (ADDED ×8, MODIFIED ×1)

| Scenario | Test |
| --- | --- |
| An active member sees every product | `test_roster_scope_resolution.py::test_an_active_member_sees_every_product` |
| A deactivated member sees nothing | `test_roster_scope_resolution.py::test_a_deactivated_member_sees_nothing` |
| An unreachable store fails closed (scope) | `test_roster_scope_resolution.py::test_an_unreachable_store_fails_closed` |
| A stranger sees nothing (MODIFIED) | `test_roster_scope_resolution.py::test_a_stranger_sees_nothing` |
| A declared entry resolves admin-capable | `test_roster_admin_capability.py::test_a_declared_entry_resolves_admin_capable` |
| Membership confers nothing | `test_roster_admin_capability.py::test_membership_confers_nothing` |
| A deactivated admin fails closed | `test_roster_admin_capability.py::test_a_deactivated_admin_fails_closed` |
| An unknown identity fails closed | `test_roster_admin_capability.py::test_an_unknown_identity_fails_closed` |
| An unreachable store fails closed (admin) | `test_roster_admin_capability.py::test_an_unreachable_store_fails_closed` |

The four **REMOVED** requirements in this delta carry no scenarios of their
own (only `Reason` and `Migration`), so nothing is enumerated for them.
Their consequence is the obsolete list below.

### `admin-session` (MODIFIED) — 6 scenarios

| Scenario | Test |
| --- | --- |
| An admin-capable principal receives a link | `test_admin_session_over_roster.py::test_an_admin_capable_principal_receives_a_link` (partial — see *Uncovered*) |
| A visibility-only principal is refused like an unknown one | `test_admin_session_over_roster.py::test_a_visibility_only_principal_is_refused_like_an_unknown_one` (partial) |
| An unknown caller's refusal confirms nothing | same test (partial) |
| No session means no surface | `test_roster_admin_page.py::test_no_session_means_no_surface` |
| Removal from the directory revokes access on the next request | `test_admin_session_over_roster.py::test_deactivation_revokes_access_on_the_next_request` |
| Withdrawing the admin declaration revokes access likewise | `test_admin_session_over_roster.py::test_withdrawing_the_admin_declaration_revokes_likewise` |

Requirement sentence with no scenario, asserted as DERIVED:
"whether unknown to the roster, **deactivated**, or an active member
without the admin declaration" →
`test_admin_session_over_roster.py::test_a_deactivated_admin_is_refused_a_link`.

## Uncovered, and why

Recorded so the absence of a test is distinguishable from the absence of
the thought.

1. **That the lifespan actually calls the bootstrap step** (`roster`
   scenarios *No admin and no variable stops startup* and *An unconfigured
   or unreachable store defers the bootstrap*, their "startup" halves).
   The tests assert the step's own outcomes — it raises naming
   `BOOTSTRAP_ADMIN_IDENTITY`, or returns normally having logged a fault
   and written nothing. Whether `main.py`'s lifespan invokes it is
   unobservable at this tier: no artifact fixes the call site beyond
   "in the lifespan" (`tasks.md` 3.4), and driving a real lifespan needs
   the composition root plus a configured database.
   **Recommendation:** an integration-tier test in
   `tests/integration/access/` (this pass was barred from writing there).
   The existing `tests/unit/test_startup_without_configuration.py` and
   `tests/unit/test_main_database_lifespan.py` already guard the two
   startup guarantees the delta says are preserved, and must stay green.
2. **The ephemeral-delivery halves of `admin-session`'s link scenarios** —
   "the reply is visible only to them", "does not confirm that an admin
   surface exists". These are the Slack handler's behavior, and no adapter
   test exists for that handler in this repository. The previous pass
   recorded the same gap for the same reason; this change does not alter
   the handler.
3. **The Postgres roster store itself** (`tasks.md` 3.1–3.2) — the store
   port is a double everywhere here. The scenarios are stated about writes
   and resolutions, not about persistence mechanics, so nothing is left
   uncovered at the *scenario* level; but the adapter satisfying the port
   has no test.
   **Recommendation:** an integration-tier test mirroring whatever
   `tests/integration/launch/test_playbook_authoring_live.py` does for the
   step store, including the stale-version race (`tasks.md` 5.5 already
   asks for this).
4. **The optimistic-versioning retry on a lost race** (`tasks.md` 2.1). No
   delta scenario states it — `design.md` Decision 5 explicitly declines
   to promise it in the page spec — so no test asserts it here.
5. **The ClickUp user id** is carried through the create/update call shapes
   but no scenario states behavior for it, so no assertion depends on it
   beyond its presence in the call.

## Assertion classification

Every assertion in the six files is commented inline as one of the three.
Summary:

- **SPECIFIED** — the great majority: each scenario's THEN clause, plus
  requirement sentences quoted in the test docstring (the deletion
  prohibition, the ten-minute token expiry, "attributed to a reserved
  system principal").
- **DERIVED** — invented by this pass and marked as such in the source:
  - that a stored "when" is a `datetime` (`test_roster_writes.py`);
  - the marker word `"admin"` standing for the last-admin refusal's
    explanation, and `"slack"` for the not-updatable refusal — the deltas
    fix that a refusal explains itself, never its wording;
  - `"bootstrap"` appearing in the reserved seed principal's spelling (the
    spec fixes only its reserved-ness; `tasks.md` 3.4 spells it
    `system:bootstrap`);
  - the current year standing for "and when" on the roster page;
  - the admin flag being shown as *some* token in the admin's page region
    that no ordinary member's region carries;
  - the bound-expiry test, the deactivated-caller refusal test, and the
    page's edit and reactivate tests (each named above);
  - discrimination guards ("the same call answers `True` for the other
    identity"), which exist so a constant-answer implementation cannot
    pass a `False`-only test.
- **DELIBERATELY UNTESTED** — the five items in *Uncovered, and why*.

## Unresolved project questions

`AGENTS.md` was read and answers the tier layout, the runner, the test
command and the path glob. It answers none of the following, and this pass
has no channel on which to ask, so each is recorded with the assumption
taken and the tests that depend on it. **Each has one named correction
point; correcting it is a fixture correction (failure state 3), not a
weakening of what the test asserts.**

| Question | Assumption taken | Depends on it | Correction point |
| --- | --- | --- | --- |
| Write use-case call shape | `create_person(roster=store, principal=..., display_name=..., slack_identity=..., clickup_user_id=..., admin=...)`, and siblings addressed by `person_id=` — collaborator-first with a keyword principal, mirroring `create_step(steps=…, principal=…)` | all six files | `_create`/`_update`/`_deactivate`/`_reactivate` in each file |
| Roster store port | `load() -> (rows, version)` / `save(rows, *, expected_version)`, per `design.md` Decision 1 | all six files | `_FakeRosterStore` |
| Stored row attribute spellings | `id`/`display_name`/`slack_identity`/`clickup_user_id`/`admin`/`active` plus `created_by`/`created_on`, `updated_*`, `deactivated_*`, `reactivated_*`; searched on the row and on a nested `person`/`entry` object | all six files | the `_*_NAMES` tuples and `_field` |
| Aggregated error | `InvalidRosterError` in `commerce_ops.access.domain.principals`, carrying a list of faults (`tasks.md` 1.1) | `test_roster_writes.py` | `REFUSED`, `_faults` |
| Refusal exception types | `(InvalidRosterError, ValueError, TypeError)` where the delta fixes the outcome but not the type | `test_roster_writes.py` | `REFUSED` |
| Bootstrap step's exported name | resolved over `seed_bootstrap_admin`, `bootstrap_admin`, `ensure_bootstrap_admin`, `seed_first_admin`, `bootstrap_first_admin`, `run_admin_bootstrap`; fails loudly naming all six | `test_roster_bootstrap.py` | `_BOOTSTRAP_NAMES` |
| Bootstrap call shape | `await step(roster=store, identity=<str\|None>)` with `BOOTSTRAP_ADMIN_IDENTITY` also set in the environment, so an env-reading implementation passes too; only argument-shape `TypeError`s fall through to the next shape | `test_roster_bootstrap.py` | `_seed` |
| What an unconfigured / unreachable store raises | `RuntimeError("DATABASE_URL is not configured")` and `ConnectionError` | `test_roster_bootstrap.py` | `_UNREADABLE_FAILURES` |
| Deferred-bootstrap logging | stdlib `logging` at `WARNING` or above (the idiom `tests/unit/briefing/application/test_briefing_delivery.py` uses) | `test_roster_bootstrap.py` | the `caplog` assertion |
| Resolution call shapes | `resolve_scope(roster, identity=...)` and `resolve_admin_capability(roster, identity=...)`, both async, resolver argument gone | scope / capability / writes files | `_resolve`, `_resolves_admin` |
| Admin-session collaborator | `mint_admin_link` and `verify_admin_session` take the roster store in the position the loaded directory held | `test_admin_session_over_roster.py` | `_mint`, `_verify` |
| What a token binds | *not pinned* — every assertion round-trips mint → exchange → verify rather than comparing to a Slack identity or a person id | `test_admin_session_over_roster.py` | n/a (deliberate) |
| Page module and store binding | `commerce_ops.access.infrastructure.driving.roster_admin` exposing `router`, with the store as a module-level `roster` name (the `steps` convention in `test_playbook_admin_page.py`) | `test_roster_admin_page.py` | the import and `_app` |
| Session cookie name | `admin_session` | `test_roster_admin_page.py` | `_SESSION_COOKIE` |
| Page control vocabulary | a deactivate control mentions "deactivate", reactivate "reactivate", edit "edit"; a create form offers a display-name field and a Slack-identity field; deactivated people are on the page or one control mentioning "deactivat"/"inactive"/"former"/"archived" away | `test_roster_admin_page.py` | `_control`, `_person_control`, `_create_form`, `_edit_form`, `_reachable_text` |

One further recorded trade, not a question: **seed state is built by
calling the write use cases** rather than by inventing a row class, the
pattern `test_resolve_scope.py` established for building directories
through the loader. The cost is that a `create_person` defect fails tests
written for `update`, `deactivate` and the page too. Where the delta makes
a state unreachable through ordinary writes — a readable roster with no
active admin — `test_roster_bootstrap.py::_drop` removes a row from the
*store double's* state; that is store-state construction, not roster
behavior, and it is documented in that file.

## Obsolete-test candidates

The change carries `MODIFIED` and `REMOVED` deltas, so this list applies.
The search was bounded to the dispatched glob `tests/**/test_*.py`; no
earlier `test-manifest.md` was supplied to this pass, so no
scenario-to-test index outside the current tree was consulted. **These are
candidates for human confirmation, not conclusions — and this pass edited
none of them.**

### Superseded outright — the requirement they cover is REMOVED

| Test (runner-selectable) | Superseding delta | Evidence |
| --- | --- | --- |
| `tests/unit/access/infrastructure/test_principals_loader.py` — all 8 tests (`test_a_well_formed_directory_loads`, `test_an_empty_grant_list_is_a_well_formed_entry`, `test_a_duplicate_identity_is_rejected_naming_it`, `test_an_entry_declaring_both_grant_forms_is_rejected`, `test_an_entry_declaring_no_grant_form_is_rejected`, `test_a_malformed_sku_grant_value_is_rejected`, `test_an_empty_or_padded_identity_is_rejected`, `test_the_shipped_directory_loads_and_grants_nothing_to_anyone`) | `access-scope` REMOVED *A principals directory is loaded from a repo-owned definition and validated* | Every test imports `load_principals` from `commerce_ops.access.infrastructure.driven.principals_loader`, which `tasks.md` 3.3 deletes, and asserts load-time validation of the YAML file the change removes. The last test additionally asserts on the shipped `principals.yaml`, deleted by the same task. |
| `tests/unit/access/application/test_resolve_scope.py` — all 6 tests | `access-scope` REMOVED *A known principal's scope derives from its grants*, REMOVED *A grant naming an unregistered SKU confers nothing…*, REMOVED directory-load requirement; MODIFIED *An unknown asker resolves to the empty scope* | Asserts `all_products` / `skus` grant resolution (`test_an_all_products_principal_resolves_to_the_unrestricted_scope`, `test_sku_grants_resolve_to_exactly_those_products`, `test_an_empty_grant_list_resolves_to_the_empty_scope`, `test_a_stale_grant_is_skipped_and_the_rest_stand`) over a `_FakeSkuResolver` — `tasks.md` 2.2 deletes both the grant model and the `SkuResolver` port. `test_a_malformed_directory_yields_no_directory_to_resolve_against` asserts on `InvalidPrincipalsError` from the deleted loader. `test_a_stranger_sees_nothing_and_the_resolution_succeeds` covers a requirement that *survives* as MODIFIED, but builds its directory through the deleted loader; its replacement is `test_roster_scope_resolution.py::test_a_stranger_sees_nothing`. |
| `tests/unit/access/application/test_admin_capability.py` — all 4 tests (one parametrized ×3) | `access-scope` REMOVED *A principal can be declared admin-capable*, re-stated as ADDED *Admin capability resolves from the roster* | Builds directories through `load_principals`; calls `resolve_admin_capability` **synchronously**, which `tasks.md` 2.3 makes async; `test_a_malformed_admin_declaration_is_rejected_at_load` asserts a load-time fault, and the delta's Reason says that scenario "has no load to attach to". Replacement: `test_roster_admin_capability.py`. |
| `tests/unit/test_main_principals_validation.py` — both tests (`test_a_malformed_principals_directory_prevents_http_startup`, `test_the_http_root_holds_the_validated_directory`) | `access-scope` REMOVED directory-load requirement; `proposal.md` Impact ("the eager YAML load-and-validate is replaced by the bootstrap-admin check") | Patches `principals_loader.load_shipped_principals` and asserts `commerce_ops.main.principals` is a `PrincipalsDirectory`; `tasks.md` 3.3 removes `load_shipped_principals` from `main.py` and 1.2 replaces `PrincipalsDirectory`. |

### Requires adaptation, **not** deletion — the requirement stands, the collaborator goes

| Test | Superseding delta | Evidence |
| --- | --- | --- |
| `tests/unit/access/application/test_admin_session_use_cases.py::test_removal_from_the_directory_revokes_on_the_next_request` and `::test_withdrawing_the_admin_declaration_revokes_likewise` | `admin-session` MODIFIED *Admin access fails closed and absence-shaped* | Both express revocation as *editing the directory YAML* (`_directory(tmp_path, …)` with the entry removed / the `admin:` line dropped). The delta re-states removal as roster deactivation. Replacements exist in `test_admin_session_over_roster.py`; these two are superseded in substance. |
| `tests/unit/access/application/test_admin_session_use_cases.py::test_minting_for_an_admin_capable_principal_binds_a_short_lived_token` and `::test_a_visibility_only_caller_is_refused_exactly_like_an_unknown_one` | `admin-session` MODIFIED *An admin-capable principal can request an admin link from Slack* | Same requirement, re-stated against the roster; both build a directory through the deleted loader. Replacements exist in `test_admin_session_over_roster.py`. |
| `tests/unit/access/application/test_admin_session_use_cases.py::test_a_token_exchanges_once_for_a_bounded_session`, `::test_a_spent_token_is_refused_like_one_that_never_existed`, `::test_an_expired_token_is_refused_identically`, `::test_a_session_outlives_its_lifetime_and_stops_working` | **none** | These cover `admin-session` requirements this change does **not** modify (single-use tokens, bounded sessions). They are listed only because the module-level `_directory_with_admin` helper they share is built on the deleted loader, so they will not import once it is gone. **Adapt the helper; do not delete these tests** — they are the only coverage those requirements have. |
| `tests/unit/access/infrastructure/test_admin_link_exchange_route.py` — all 6 tests | **none** | Covers the link-exchange route, unmodified by this change, but calls `load_principals` at line 132 to build the directory it mints from. Same treatment: adapt the fixture, keep the tests. |

### Searched and found nothing

`tests/unit/catalog/application/test_scope_aware_reads.py` and
`tests/unit/launch/application/test_scope_aware_launch_reads.py` match the
string `all_products`, but only as a candidate *factory name* for
`AccessScope.unrestricted()`; they never touch the principals directory or
its grants. Consistent with `proposal.md` Impact ("**`catalog` / `launch`
read use cases**: no change"). **No test outside `tests/unit/access/` and
`tests/unit/test_main_principals_validation.py` was found to bear on the
removed requirements** — stated as a finding of this bounded search, not as
proof that none exists anywhere.

`tests/integration/` was **not** searched: another session held it during
this pass. Two integration files
(`test_playbook_authoring_live.py`, `test_playbook_ordering_live.py`)
matched a `principal` grep from outside, but as an authoring-attribution
argument, not as directory usage. **A human should confirm the integration
tier separately.**
