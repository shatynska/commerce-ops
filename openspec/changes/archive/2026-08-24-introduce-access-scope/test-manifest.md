# Test manifest — introduce-access-scope

Written by the test-writing pass, before any implementation of this change
exists. It records what was written, what was not, what each assertion
traces to, and which existing tests this change supersedes.

**This file is not part of the OpenSpec schema.** It will not appear among
`openspec instructions apply`'s context files, so whoever implements this
change has to open it on purpose.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted, or disabled. Nothing outside `tests/**/test_*.py` was
written except this manifest.

## Baseline

Taken before any file was written, with `uv run pytest`:

| Scope | Result |
| --- | --- |
| `tests/unit tests/agents` (the commit-time tier) | 521 passed, 0 failed |
| `tests/integration` | 3 passed, 37 skipped (`DATABASE_URL` unset) |

That is a full baseline, not a scoped one: every tier the project defines
was run. After this pass, the same commit-time run reports **521 passed, 5
errors** — the five new modules failing at collection on absent targets
(`ModuleNotFoundError`), with no change to any pre-existing test.

Note for the implementation step: pytest aborts the session on a collection
error unless `--continue-on-collection-errors` is passed, so the pre-commit
pytest hook will refuse commits until the new modules exist. That is the
expected red-first state, not a defect in the hook.

The other two commit-time checks were run as well:

- `uv run ruff check` and `uv run ruff format --check` — **clean** on all
  five new files.
- `uv run mypy .` — 12 errors, every one a consequence of the four absent
  modules: eight `import-untyped` "module is installed, but missing library
  stubs" lines for `commerce_ops.shared.domain.access_scope` and
  `commerce_ops.access.*`, and four `unused-ignore` warnings on
  `# type: ignore` comments that are unused only because the module they
  refer to is unresolvable. No genuine type defect remains. Two that mypy
  did surface were corrected as fixture defects before this manifest was
  written: `_FakeCatalogStore` was missing the `CatalogStore` protocol's
  `add`/`save` members, and `_read_launch` passed more positional
  arguments than `read_launch` accepts.

## Test files written

| File | Tests |
| --- | --- |
| `tests/unit/shared/domain/test_access_scope.py` | 9 |
| `tests/unit/access/infrastructure/test_principals_loader.py` | 8 |
| `tests/unit/access/application/test_resolve_scope.py` | 6 |
| `tests/unit/catalog/application/test_scope_aware_reads.py` | 8 |
| `tests/unit/launch/application/test_scope_aware_launch_reads.py` | 7 |

All five are unit-tier. No `tests/agents` file is called for (this change
adds no graph), and no `tests/integration` file: every scenario the delta
states is about what a use case, a value object, or a loader answers, which
is the smallest unit that can observe it. The existing integration coverage
of catalog persistence is unaffected in what it asserts — see *Obsolete
tests*, class B.

No `__init__.py` was created for the new `tests/unit/access/...`
directories. The repository is inconsistent about them (`tests/unit/launch/`
has them, `tests/unit/catalog/` does not), and they fall outside this pass's
dispatched write glob (`tests/**/test_*.py`). Collection works without them
because every new file's basename is unique.

## Scenario accounting

29 `#### Scenario:` blocks across the four delta specs; 29 accounted for.
Test identifiers are given in the form `uv run pytest` selects.

### `access-scope` (ADDED, 11 scenarios)

Requirement: *A principals directory is loaded from a repo-owned definition
and validated*

| Scenario | Covered by |
| --- | --- |
| A well-formed directory loads | `tests/unit/access/infrastructure/test_principals_loader.py::test_a_well_formed_directory_loads` |
| A duplicate identity is rejected at load | `...test_principals_loader.py::test_a_duplicate_identity_is_rejected_naming_it` |
| An entry declaring both grant forms is rejected | `...test_principals_loader.py::test_an_entry_declaring_both_grant_forms_is_rejected` |
| An entry declaring no grant form is rejected | `...test_principals_loader.py::test_an_entry_declaring_no_grant_form_is_rejected` |
| A malformed SKU grant value is rejected | `...test_principals_loader.py::test_a_malformed_sku_grant_value_is_rejected` (params `empty`, `leading-space`, `trailing-space`) |
| A malformed directory prevents serving rather than failing resolutions | **Partially covered** — `tests/unit/access/application/test_resolve_scope.py::test_a_malformed_directory_yields_no_directory_to_resolve_against` asserts the second clause (no resolution can observe a malformed directory, because the load produces no directory value). The first clause — *startup* fails — is **deliberately untested**; see the unresolved question below. |

Two further tests in this file carry no scenario of their own:

- `test_an_empty_grant_list_is_a_well_formed_entry` — SPECIFIED by the
  requirement statement ("which MAY be empty"). It exists because a
  too-broad reading of *An entry declaring no grant form is rejected* would
  refuse `skus: []`, which the *An empty grant list resolves to the empty
  scope* scenario presupposes can exist.
- `test_an_empty_or_padded_identity_is_rejected` — SPECIFIED by the
  requirement statement, which names this fault without giving it a
  scenario.
- `test_the_shipped_directory_loads_and_grants_nothing_to_anyone` —
  DERIVED from `tasks.md` 2.3 / `design.md` Decision 3, not from any
  scenario. Marked derived for that reason.

Requirement: *A known principal's scope derives from its grants*

| Scenario | Covered by |
| --- | --- |
| An all-products principal resolves to the unrestricted scope | `tests/unit/access/application/test_resolve_scope.py::test_an_all_products_principal_resolves_to_the_unrestricted_scope` |
| SKU grants resolve to exactly those products | `...test_resolve_scope.py::test_sku_grants_resolve_to_exactly_those_products` |
| An empty grant list resolves to the empty scope | `...test_resolve_scope.py::test_an_empty_grant_list_resolves_to_the_empty_scope` |

Requirement: *An unknown asker resolves to the empty scope*

| Scenario | Covered by |
| --- | --- |
| A stranger sees nothing | `...test_resolve_scope.py::test_a_stranger_sees_nothing_and_the_resolution_succeeds` |

Requirement: *A grant naming an unregistered SKU confers nothing without
failing the resolution*

| Scenario | Covered by |
| --- | --- |
| A stale grant is skipped, the rest stand | `...test_resolve_scope.py::test_a_stale_grant_is_skipped_and_the_rest_stand` |

### `shared-vocabulary` (ADDED, 3 scenarios)

| Scenario | Covered by |
| --- | --- |
| The unrestricted scope permits every product | `tests/unit/shared/domain/test_access_scope.py::test_the_unrestricted_scope_permits_every_product` |
| An explicit-set scope permits exactly its members | `...test_access_scope.py::test_an_explicit_set_scope_permits_exactly_its_members`, reinforced by `::test_a_two_member_scope_permits_both_and_nothing_else` |
| The empty scope permits nothing | `...test_access_scope.py::test_the_empty_scope_permits_nothing` |

Also in that file, tracing to the requirement statement rather than to a
scenario: `test_the_unrestricted_scope_is_not_an_enumeration_of_products`
(SPECIFIED — "a distinct construction, not a set enumerating all
products"), `test_two_scopes_over_the_same_products_are_equal_and_hash_equal`
and `test_mutation_of_a_constructed_scope_fails` (SPECIFIED — "follows the
vocabulary's existing immutability and value-equality rules").

### `product-catalog` (MODIFIED, 8 scenarios)

All eight are covered **as revised** in
`tests/unit/catalog/application/test_scope_aware_reads.py`:

| Scenario | Covered by |
| --- | --- |
| A product is retrieved by identifier | `::test_a_product_is_retrieved_by_identifier_under_a_permitting_scope` |
| A product is retrieved by SKU | `::test_a_product_is_retrieved_by_sku_under_a_permitting_scope` |
| An unknown product reports absence | `::test_an_unknown_product_reports_absence_under_any_scope` (params `unrestricted`, `empty`) |
| An out-of-scope product reports the same absence | `::test_an_out_of_scope_product_reports_the_same_absence` |
| Products are listed | `::test_products_are_listed_under_the_unrestricted_scope` |
| A restricted scope lists only its products | `::test_a_restricted_scope_lists_only_its_products` |
| An empty catalog lists nothing | `::test_an_empty_catalog_lists_nothing` |
| A scope permitting nothing lists nothing | `::test_a_scope_permitting_nothing_lists_nothing` |

### `launch-instance` (MODIFIED, 7 scenarios)

All seven are covered **as revised** in
`tests/unit/launch/application/test_scope_aware_launch_reads.py`:

| Scenario | Covered by |
| --- | --- |
| A launch position is retrieved | `::test_a_launch_position_is_retrieved_under_a_permitting_scope` |
| A product without a launch position reports absence | `::test_a_product_without_a_launch_position_reports_absence` (params `unrestricted`, `empty`) |
| An out-of-scope launch reports the same absence | `::test_an_out_of_scope_launch_reports_the_same_absence` |
| All launch positions are reported | `::test_all_launch_positions_are_reported_under_the_unrestricted_scope` |
| A restricted scope enumerates only its launches | `::test_a_restricted_scope_enumerates_only_its_launches` |
| No launches yields an empty enumeration | `::test_no_launches_yields_an_empty_enumeration` |
| A scope permitting nothing enumerates nothing | `::test_a_scope_permitting_nothing_enumerates_nothing` |

The enumeration requirement's standing clause "Enumeration SHALL NOT filter
by lifecycle" keeps its existing coverage in
`tests/unit/launch/application/test_launch_reports.py::test_enumeration_does_not_filter_by_lifecycle`;
the delta does not restate it as a scenario, and no new test duplicates it.

## Assertion classification

Every assertion carries its classification inline, next to the assertion
(`# SPECIFIED:` / `# DERIVED:` / a docstring paragraph). Summarised:

**SPECIFIED** — the substance of every test named in the accounting above:
what each scope permits, which products each read returns, that an
out-of-scope read is indistinguishable from a nonexistent one, which
directories load and which are refused, and that a refusal names the
offending entry.

**DERIVED** — recorded here so each is reviewable rather than mistaken for
a stated requirement:

- Sample values throughout (identities `U01ALICE`/`U02BOB`/`U03CAROL`/
  `U99STRANGER`, SKUs `WIDGET-00n`, launch dates, `AS_OF`, the fixed
  timestamps). No artifact fixes any of them; the launch dates reuse the
  construction `test_launch_reports.py` already records.
- `test_a_two_member_scope_permits_both_and_nothing_else`,
  `test_scopes_over_different_products_are_not_equal`,
  `test_two_unrestricted_scopes_are_equal` — each closes a hole a
  constant-answering implementation would otherwise slip through.
- `test_the_shipped_directory_loads_and_grants_nothing_to_anyone` — traces
  to `tasks.md` 2.3, not to a scenario.
- The "the permitted product/launch is still readable under this scope"
  assertions in the two out-of-scope tests: they keep the absence
  assertions from passing by everything being absent.
- Reading approvals, attestations and step provenance through their
  rendered text in
  `test_a_launch_position_is_retrieved_under_a_permitting_scope`, so a
  tuple of value objects and a richer projection both satisfy it.
- The immutability mechanism (`AttributeError` / `TypeError`), the
  rejection signal being an exception at all, and `None` as the absence
  answer — the project's existing conventions, not stated in any spec.

**DELIBERATELY UNTESTED**

- *A malformed directory prevents serving rather than failing resolutions*,
  first clause: that **startup** fails. No artifact fixes where the eager
  validation is invoked, and the principals path is repo-owned rather than
  environment-injectable, so a malformed file cannot be handed to a real
  startup from a test the way `tests/unit/test_preflight.py` hands one a
  constructed environment. Recorded as an unresolved project question
  below; the implementation step should decide the entry point and add the
  startup-level test there.
- Whether `resolve_scope` logs the unresolved grant (`design.md` Decision
  5, `tasks.md` 2.4 — "logged, resolution succeeds"). The spec's scenario
  states only that the grant confers nothing and the resolution succeeds;
  asserting a log line would pin an emission no requirement states.
- Whether the SKU resolver is consulted at all for an all-products
  principal. No requirement constrains it, and asserting it would fix an
  implementation strategy.

## Unresolved project questions

Each was resolved by an assumption because this pass runs non-interactively
with no channel to ask on. Each is a fixture-level assumption: correcting it
is a fixture correction, never a change to what a test asserts.

| # | Question | Assumption taken | Tests depending on it |
| --- | --- | --- | --- |
| 1 | Where `AccessScope` lives and how its two constructions are spelled | `commerce_ops.shared.domain.access_scope.AccessScope`; `_unrestricted()` / `_permitting()` helpers try several spellings and fail loudly | all five files |
| 2 | The `access` module's paths and names | `access.domain.principals.InvalidPrincipalsError`; `access.infrastructure.driven.principals_loader.load_principals` / `load_shipped_principals`; `access.application.resolve_scope` — mirroring `launch`'s `playbook_loader` / `InvalidPlaybookError` split | `test_principals_loader.py`, `test_resolve_scope.py` |
| 3 | The principals YAML document shape | a `principals:` **list** of entries with `identity:` plus either `all_products: true` or `skus: [...]`. A list, not a mapping, because the spec requires a duplicate identity to be rejected — a YAML mapping could not express one | `test_principals_loader.py`, `test_resolve_scope.py` |
| 4 | How a loaded directory reports that it knows an identity | `_knows()` tries `entry_for`/`get`/`principal_for`/`declares`, a `principals` collection, then `in`; fails loudly if none works | `test_principals_loader.py` |
| 5 | `resolve_scope`'s call shape | `await resolve_scope(directory, resolve_sku, *, identity)`, async, ports first (the project's `run_daily_digest(reader)` precedent); identity a plain `str`, since `design.md` keeps Slack out of the domain | `test_resolve_scope.py` |
| 6 | The SKU-resolver port's shape | an async callable taking a SKU and answering `ProductId \| None`, shaped like briefing's `_FakeCatalog` | `test_resolve_scope.py` |
| 7 | Where the principals directory is eagerly validated at startup | **unresolved, and untested** — preflight, FastAPI lifespan and `worker.py` are all plausible | none; see *deliberately untested* above |
| 8 | `read_launch`'s argument order, and whether it takes a playbook port or `as_of` | **not guessed** — `_read_launch` assembles the call from `inspect.signature(read_launch)`: the store first, then playbooks / product identifier / scope / `as_of` matched by parameter name, and only where declared. `read_launch` already exists (mypy resolves it in `launch.application.use_cases`) and takes fewer positionals than a first draft assumed, which is what motivated the signature-driven call | `test_scope_aware_launch_reads.py` |
| 9 | The launch record's attribute spellings | `_ATTRIBUTE_ALIASES`, extending the table `test_launch_reports.py` already uses | `test_scope_aware_launch_reads.py` |
| 10 | The catalog and launch store ports' method names | the fakes answer to several spellings and ignore extra arguments | `test_scope_aware_reads.py`, `test_scope_aware_launch_reads.py` |
| 11 | Which parameter carries the scope on each read use case | `_scope_argument()` finds the parameter whose name contains "scope" and passes by that name; a use case with **no** such parameter fails the test by name — that part is SPECIFIED, not an accommodation | both scope-aware read files |
| 12 | Whether the new `tests/unit/access/` directories need `__init__.py` | none created — the repo is inconsistent, and they are outside this pass's write glob | collection of the two `access` files |
| 13 | `ruff`'s isort grouping while the target modules do not exist | ruff currently classifies `commerce_ops.shared.domain.access_scope` and `commerce_ops.access.*` as third-party (the files do not exist), and grouped those imports next to `pytest`. `ruff check` and `ruff format --check` pass **as of this pass**; once the modules land, `ruff check --fix` will regroup them into the first-party block. Mechanical, and not a change to any test | all five files |

Also worth stating: `test_resolve_scope.py` builds its principals
directories through the loader rather than through a domain constructor.
That keeps one invented shape in play instead of two, at the cost of
coupling those tests to the loader — a loader defect fails them too.

## Obsolete tests

Every entry below is a **candidate for human confirmation**, not a
conclusion. This pass edited none of them.

**Search bound.** Only `tests/**/test_*.py` was searched (the dispatched
glob), by grepping for the five changed use-case names. No earlier
`test-manifest.md` was supplied to this pass, so no requirement-to-test
index informed the search beyond that grep.

### Class A — assertions superseded by a MODIFIED delta

| Test | Superseded by | Evidence |
| --- | --- | --- |
| `tests/unit/catalog/application/test_list_products_empty_catalog.py::test_an_empty_catalog_lists_nothing` | `product-catalog` → *Products can be listed with their stages* | calls `await list_products(_EmptyStore())` with no scope; the delta requires the list to be "filtered by the caller's access scope", and restates this scenario as one a scope must be supplied to. What it asserts (empty in → empty out, not an error) survives unchanged; `tests/unit/catalog/application/test_scope_aware_reads.py::test_an_empty_catalog_lists_nothing` now covers it under the new contract, so the older file is a candidate for **removal as a duplicate** rather than rewriting. |
| `tests/unit/launch/application/test_launch_reports.py::test_all_launch_positions_are_reported` | `launch-instance` → *Launch positions are enumerable with their reports* | calls `read_launches(store, playbooks, as_of=AS_OF)` and asserts every persisted position is reported unconditionally; the delta conditions that on the unrestricted scope. Replacement coverage: `test_scope_aware_launch_reads.py::test_all_launch_positions_are_reported_under_the_unrestricted_scope`. |
| `tests/unit/launch/application/test_launch_reports.py::test_no_launches_yields_an_empty_enumeration` | same requirement | same call convention; the delta restates the scenario with a scope in the call. Replacement coverage: `test_scope_aware_launch_reads.py::test_no_launches_yields_an_empty_enumeration`. |

### Class B — call convention superseded, assertions still stand

These bear on requirements this change does **not** modify (or on
persistence behavior it does not touch), but they call a use case whose
signature gains a scope. `tasks.md` 3.3 already anticipates them: "Update
every existing call site and test of the changed signatures." They are
listed so no call site is missed — **not** as candidates for deletion.

| Test | Call to update |
| --- | --- |
| `tests/unit/launch/application/test_launch_reports.py::test_enumeration_does_not_filter_by_lifecycle` | `read_launches` |
| `...test_launch_reports.py::test_a_step_entry_carries_its_owning_discipline` | `read_launches` |
| `...test_launch_reports.py::test_the_at_risk_evaluation_names_its_overdue_blocking_steps` | `read_launches` |
| `...test_launch_reports.py::test_a_satisfied_confirmation_gate_without_an_approval_awaits` | `read_launches` (via `_report_for`) |
| `...test_launch_reports.py::test_unsatisfied_blocking_conditions_mean_not_awaiting` | `read_launches` (via `_report_for`) |
| `...test_launch_reports.py::test_a_recorded_approving_approval_ends_the_wait` | `read_launches` (via `_report_for`) |
| `...test_launch_reports.py::test_an_automatic_gate_never_awaits_confirmation` | `read_launches` (via `_report_for`) |
| `tests/unit/briefing/application/test_briefing_assembly.py` (module helper `_reports_for`, line 310) | `read_launches` — used to build fixture reports; briefing's own spec is untouched |
| `tests/unit/briefing/application/test_briefing_delivery.py` (module helper, line 288) | `read_launches` — same |
| `tests/integration/catalog/test_catalog_products.py::test_a_product_is_registered_with_required_fields_only` | `get_product_by_id` |
| `...::test_registering_a_duplicate_sku_is_rejected_without_persisting` | `get_product_by_sku` |
| `...::test_an_asin_recorded_later_is_reported_on_read_back` | `get_product_by_id` |
| `...::test_a_product_is_retrieved_by_identifier_with_every_field` | `get_product_by_id` — this one also covers a MODIFIED scenario, now covered as revised at the unit tier; its persistence assertions are what keep it in class B rather than A |
| `...::test_a_product_is_retrieved_by_sku` | `get_product_by_sku` — same reasoning |
| `...::test_an_unknown_product_reports_absence` | `get_product_by_id`, `get_product_by_sku` — same reasoning |
| `...::test_products_are_listed_with_identifier_sku_name_and_stage` | `list_products` — same reasoning |
| `...::test_a_confirmed_stage_change_is_persisted` | `get_product_by_id` |
| `...::test_a_rejected_stage_change_leaves_the_stored_stage_unchanged` | `get_product_by_id` |

No test bearing on `read_launch` was found: **no such test exists** — the
grep over the whole glob returns no call to it, only docstring mentions in
briefing and ClickUp-sync tests.

## Artifacts read as data

Nothing in `proposal.md`, `design.md`, `tasks.md` or the four delta specs
addressed an instruction to the test author (no "skip this", "no tests
needed", "already covered"). Recorded because the absence is itself a
finding.
