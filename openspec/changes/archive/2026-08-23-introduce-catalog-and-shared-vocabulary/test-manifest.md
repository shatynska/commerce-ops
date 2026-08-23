# Test manifest — introduce-catalog-and-shared-vocabulary

Written by the test-derivation pass on 2026-08-23, strictly from this
change's delta specs, before any implementation. This file is **not** an
artifact the OpenSpec schema knows about — it will not appear among
`openspec instructions apply`'s context files and must be read on
purpose by whoever implements the change.

**This pass was additive only.** No existing test was edited, deleted, or
disabled; no implementation code was written. The tests below are new
files; everything else in `tests/` is untouched.

## Baseline

Full-suite baseline, taken before any new file was written:
`uv run pytest` → **263 passed, 32 skipped, 0 failed** (2026-08-23).
The 32 skips are the entire `tests/integration/` tier skipping on unset
`DATABASE_URL`, its recorded convention.

Caveat: a parallel session on another branch is concurrently adding its
own uncommitted test files to this working tree. Between this pass's
first and second full runs, that session added
`tests/unit/shared/infrastructure/driven/test_recurring_work_registry.py`,
which fails collection on its own absent target
(`commerce_ops.registrations`). Full-suite results taken after this pass
therefore entangle that session's files; attribute failures using the
scoped runs below, not a full run.

Scoped post-writing run of only this pass's six files:
all six fail at collection with `ModuleNotFoundError`
(`commerce_ops.shared.domain.identity`,
`commerce_ops.shared.domain.lifecycle_stage`, `commerce_ops.catalog`) —
failure state 2 of `ai-toolkit:testing`: the targets are absent, which is
the expected outcome of a tests-before-implementation pass. The
assertions have never executed; nothing about their quality is yet
established. `ruff check` and `ruff format --check` are clean on all six.

## Test files written (all new)

- `tests/unit/shared/domain/test_identity_value_objects.py`
- `tests/unit/shared/domain/test_lifecycle_stage.py`
- `tests/unit/catalog/domain/test_product_lifecycle.py`
- `tests/unit/catalog/application/test_list_products_empty_catalog.py`
- `tests/integration/catalog/test_catalog_products.py`
- `tests/integration/products/test_launch_position_repository.py`

Run an individual file/test with, e.g.:
`uv run pytest tests/unit/catalog/domain/test_product_lifecycle.py::test_a_legal_transition_is_applied_and_attributed`

## Scenario accounting

Every `#### Scenario:` block in the three delta specs, accounted exactly
once. 40 scenarios total: 12 (`shared-vocabulary`) + 19
(`product-catalog`) + 9 (`launch-instance`). All 40 are covered by at
least one named test; one (the empty catalog) is covered at the
application level rather than the integration tier, with the reason
recorded in its row. The two REMOVED requirements carry no scenario blocks in the delta;
they are accounted for in the obsolete list below.

### shared-vocabulary (delta: ADDED only)

| Scenario | Test (runner-selectable) |
| --- | --- |
| A valid SKU is constructed | `tests/unit/shared/domain/test_identity_value_objects.py::test_a_valid_sku_is_constructed_and_reports_its_value` |
| An empty identity value is rejected | `...test_identity_value_objects.py::test_an_empty_identity_value_is_rejected[product-id\|sku\|asin\|marketplace-id]` |
| A padded identity value is rejected | `...test_identity_value_objects.py::test_a_padded_identity_value_is_rejected_not_trimmed[*]` |
| A malformed ASIN is rejected | `...test_identity_value_objects.py::test_a_malformed_asin_is_rejected_with_the_value_named[*]` |
| Two value objects with the same value are equal | `...test_identity_value_objects.py::test_two_skus_with_the_same_value_are_equal_and_hash_equal` |
| Mutation is not possible | `...test_identity_value_objects.py::test_mutation_of_a_constructed_value_object_fails[*]` and `tests/unit/shared/domain/test_lifecycle_stage.py::test_mutation_of_a_stage_value_fails` |
| A launching stage carries its phase | `tests/unit/shared/domain/test_lifecycle_stage.py::test_a_launching_stage_carries_its_phase` |
| An out-of-range launch phase is rejected | `...test_lifecycle_stage.py::test_an_out_of_range_launch_phase_is_rejected[0\|5]` |
| A steady-state stage carries its posture | `...test_lifecycle_stage.py::test_a_steady_state_stage_carries_its_posture` |
| Launching is temporary | `...test_lifecycle_stage.py::test_launching_is_temporary_at_every_phase[1-4]` |
| Inventory override is temporary | `...test_lifecycle_stage.py::test_inventory_override_is_temporary` |
| Ordinary steady state is not temporary | `...test_lifecycle_stage.py::test_ordinary_steady_state_is_not_temporary[scale\|optimize\|hold\|recover]` |

### product-catalog (delta: ADDED only)

| Scenario | Test |
| --- | --- |
| A product is registered with required fields only | `tests/integration/catalog/test_catalog_products.py::test_a_product_is_registered_with_required_fields_only` |
| A duplicate SKU is rejected | `...test_catalog_products.py::test_registering_a_duplicate_sku_is_rejected_without_persisting` |
| An ASIN is recorded later | `...test_catalog_products.py::test_an_asin_recorded_later_is_reported_on_read_back` |
| Registration stamps Development | `tests/unit/catalog/domain/test_product_lifecycle.py::test_registration_stamps_development` (persistence-level supplement inside `test_a_product_is_registered_with_required_fields_only`) |
| Registration provenance | `...test_product_lifecycle.py::test_registration_provenance_is_the_registration_time_and_no_confirmer` |
| A legal transition is applied and attributed | `...test_product_lifecycle.py::test_a_legal_transition_is_applied_and_attributed` (persistence supplement: `test_catalog_products.py::test_a_confirmed_stage_change_is_persisted`) |
| A phase is skipped | `...test_product_lifecycle.py::test_a_skipped_phase_is_rejected` |
| An illegal transition is rejected | `...test_product_lifecycle.py::test_development_straight_to_steady_state_is_rejected` (persistence supplement: `test_catalog_products.py::test_a_rejected_stage_change_leaves_the_stored_stage_unchanged`) |
| Graduation requires an explicit posture | `...test_product_lifecycle.py::test_graduation_without_a_posture_is_rejected` — see that test's docstring: under the sum-type shape design.md Decision 4 fixes, a posture-less `SteadyState` is only expressible as a construction attempt |
| A same-stage change is rejected | `...test_product_lifecycle.py::test_a_same_stage_change_is_rejected_and_entry_time_kept` |
| A successful change yields a stage-changed notification | `...test_product_lifecycle.py::test_a_successful_change_yields_a_stage_changed_notification` |
| A retired product cannot change stage | `...test_product_lifecycle.py::test_a_retired_product_cannot_change_stage[*]` |
| An unconfirmed change is rejected | `...test_product_lifecycle.py::test_an_unconfirmed_change_is_rejected[none\|empty-string]` |
| Stage entry time is reported | `...test_product_lifecycle.py::test_stage_entry_time_is_reported_after_a_change` |
| A product is retrieved by identifier | `tests/integration/catalog/test_catalog_products.py::test_a_product_is_retrieved_by_identifier_with_every_field` |
| A product is retrieved by SKU | `...test_catalog_products.py::test_a_product_is_retrieved_by_sku` |
| An unknown product reports absence | `...test_catalog_products.py::test_an_unknown_product_reports_absence[by-unknown-identifier\|by-unknown-sku]` |
| Products are listed | `...test_catalog_products.py::test_products_are_listed_with_identifier_sku_name_and_stage` |
| An empty catalog lists nothing | `tests/unit/catalog/application/test_list_products_empty_catalog.py::test_an_empty_catalog_lists_nothing` — covered at the application level against a store double, **not** in the integration tier: this tier's recorded convention has no truncate/rollback fixture, so "no products exist" is unobservable against the shared database (same determination `tests/integration/products/test_product_repository_list_names.py` records for the pre-change list) |

Unlabelled level note: the stage-machine scenarios say "the stored stage
is unchanged"; they are primarily accounted at the aggregate level
because the aggregate's stage *is* the stored stage's source of truth and
the smallest observing unit, with two persistence-level supplements (one
legal, one rejected change) confirming the store round-trip.

### launch-instance (delta: ADDED + MODIFIED + REMOVED)

| Scenario (ADDED/MODIFIED) | Test |
| --- | --- |
| A launch position is created for an existing product | `tests/integration/products/test_launch_position_repository.py::test_a_launch_position_is_created_for_an_existing_product` |
| A launch position for an unknown product is rejected | `...::test_a_launch_position_for_an_unknown_product_is_rejected` |
| A second launch position for the same product is rejected | `...::test_a_second_launch_position_for_the_same_product_is_rejected` |
| A launch position is retrieved | `...::test_a_launch_position_is_retrieved_with_every_field` |
| A product without a launch position reports absence | `...::test_a_product_without_a_launch_position_reports_absence` |
| A new product defaults to the first gate (MODIFIED, as revised) | `...::test_a_new_launch_position_defaults_to_the_first_gate` |
| An unrecognized gate is rejected (MODIFIED, as revised) | `...::test_creating_with_an_unrecognized_gate_is_rejected` and `...::test_updating_to_an_unrecognized_gate_is_rejected` (the scenario's "created or updated" halves) |
| A product's current gate is updated to a valid gate (MODIFIED, as revised) | `...::test_updating_the_current_gate_to_a_valid_gate_persists` |
| Updating a nonexistent product is rejected (MODIFIED, as revised) | `...::test_updating_a_product_with_no_launch_position_is_rejected` |

REMOVED requirements (no scenario blocks; accounted as uncovered with
the operation as the reason — removed behavior is not to be tested):

- *A product is persisted with its catalog identity* — REMOVED; identity
  moves to `product-catalog`, covered there by the tests above.
- *A product can be read back by identifier or by SKU* — REMOVED;
  superseded by the by-product-identifier read; by-SKU lookup now covered
  in `product-catalog`'s `test_a_product_is_retrieved_by_sku`.

## Assertion classification

Every assertion in the six files carries an inline `SPECIFIED` /
`DERIVED` marker (or a docstring stating it), per `ai-toolkit:testing`.
Summary of the derived/deliberate items:

**Derived assertions (invented, flagged for review):**

- Rejection mechanisms throughout: `ValueError` for vocabulary
  construction failures; `StageTransitionError` for illegal transitions;
  `DuplicateSkuError` / `LaunchPositionError` as single
  per-rejected-operation-family exceptions (this project's recorded
  precedent); `(AttributeError, TypeError)` for immutability;
  `(StageTransitionError, ValueError, TypeError)` for an unconfirmed
  change. The specs say only "rejected"/"fails".
- `test_a_valid_asin_is_constructed`, `test_two_skus_with_different_values_are_not_equal`,
  the eight-gate acceptance parametrization, and the "entry time tracks
  the *current* stage" second assertion — each justified in its docstring.
- Assertions labeled "SPECIFIED by the requirement statement" trace to a
  requirement's SHALL text that no named scenario reaches (legal phase
  advance, legal graduation, re-posturing, any-stage → Retired, the
  five-member posture set, phases 1/4 accepted, Development/Retired not
  temporary, other same-stage rejections). They are specified, not
  derived — the requirement text states them — but are listed here so a
  reviewer sees which tests exceed the named scenarios.

**Deliberately untested (recorded, with reasons):**

- The empty-catalog case at the integration level — see its scenario row.
- Exact stage-entry timestamps at the persistence level — the use case
  stamps its own clock there; presence and ordering are asserted, exact
  instants are asserted at the aggregate level where the time is passed
  in.
- "Naming the offending value" for the *empty*-value rejection — an empty
  string has no content for a message to name; the naming clause is
  asserted on the malformed-ASIN scenario, where it is meaningful.
- **Migration verification (tasks.md 4.1/4.3: seeded-data split, paired
  downgrade, catalog-only rows dropped on downgrade).** No `#### Scenario:`
  block states it — it is design.md Migration Plan material. It is not
  covered by this pass because exercising `alembic downgrade`/`upgrade`
  from a test would rewrite the schema of the shared `DATABASE_URL`
  database out from under the rest of the integration tier, and the
  migration's revision id does not exist yet to target. Task 4.3's
  migration test remains owed by the implementation step, which can seed
  a dedicated database. This is the one tasks.md-named test this pass
  does not deliver.

## Obsolete tests — candidates for human confirmation

Superseded by this change's MODIFIED/REMOVED `launch-instance` deltas.
Search scope: `tests/**/test_*.py` only (no earlier `test-manifest.md`
path was supplied to this pass, so no archived manifest informed the
search). **Every entry is a candidate for human confirmation, not a
conclusion** — none was edited, deleted, or disabled by this pass.

All in `tests/integration/products/test_product_repository.py` (each id
runner-selectable as `tests/integration/products/test_product_repository.py::<name>`):

| Test | Superseding delta | Evidence |
| --- | --- | --- |
| `test_creating_with_only_required_fields_persists_absent_optionals` | REMOVED: *A product is persisted with its catalog identity* | asserts `create(sku=, name=, playbook_version=)` persists SKU/ASIN/name on the flat record — identity now owned by `product-catalog` |
| `test_creating_with_every_field_persists_all_five_values` | REMOVED: same | same flat identity+launch shape (`sku`, `name`, `asin` alongside `playbook_version`, `launch_date`) |
| `test_creating_with_a_duplicate_sku_is_rejected` | REMOVED: same | SKU uniqueness moves to `product-catalog` ("Registering a product whose SKU already belongs..."), covered there anew |
| `test_a_product_is_retrieved_by_its_identifier` | REMOVED: *A product can be read back by identifier or by SKU* | asserts read-back of the flat record incl. `sku`/`asin`/`name`; replacement path is catalog resolve + launch-position read |
| `test_a_product_is_retrieved_by_its_sku` | REMOVED: same | by-SKU read explicitly removed; delta's Migration text names the replacement |
| `test_reading_an_unknown_product_reports_absence[by-unknown-identifier]`, `[by-unknown-sku]` | REMOVED: same | absence semantics carried into the new ADDED read-back requirement, covered anew |
| `test_a_new_product_defaults_to_the_first_gate` | MODIFIED: *current gate is restricted...* | behavior carries over but onto the launch-position record; the test constructs the superseded flat record (`create(sku=..., name=...)`) |
| `test_creating_with_an_unrecognized_gate_is_rejected` | MODIFIED: same | same — new test covers the revised create path |
| `test_creating_with_each_of_the_eight_gate_ids_is_accepted[*]` | MODIFIED: same | same (derived parametrization; re-derived on the new record) |
| `test_updating_to_an_unrecognized_gate_is_rejected` | MODIFIED: same | update half; re-covered against the launch position |
| `test_updating_current_gate_to_a_valid_gate_persists_the_change` | MODIFIED: *current gate can be updated* | re-covered as `test_updating_the_current_gate_to_a_valid_gate_persists` |
| `test_updating_a_nonexistent_product_is_rejected` | MODIFIED: same | re-covered as `test_updating_a_product_with_no_launch_position_is_rejected` |

And in `tests/integration/products/test_product_repository_list_names.py`:

| Test | Superseding delta | Evidence |
| --- | --- | --- |
| `test_list_names_includes_every_created_products_name` | REMOVED identity requirement + proposal ("digest's product-name read is re-pointed at catalog"; design Decision 9: products repository "shrinks to the launch-position record") | exercises `ProductRepository.list_names()` and `create(sku=, name=)`, both of which leave the products module |
| `test_list_names_reflects_products_written_by_another_session` | same | same |

The two `list_names` entries rest partly on proposal/design text rather
than a delta requirement (the digest's own `product-monitoring` spec is
untouched) — flagged as the weaker-evidence entries in this list.

**Not obsolete, but will need fixture correction during implementation:**
`tests/unit/products/application/test_daily_digest.py` asserts digest
behavior the change explicitly preserves ("digest behavior unchanged",
tasks.md 5.1); its import of `ProductNameReader` from
`products.application` is what tasks.md 5.1 rewires. Correcting that
import when the wiring moves is a fixture correction, not a
supersession — it is deliberately excluded from the obsolete list.
`tests/integration/products/conftest.py` builds the pre-change
`ProductRepository` and will need the same kind of correction; it is test
infrastructure, outside this pass's write scope.

## Unresolved project questions

Recorded because this pass has no channel to ask on; each assumption is
inline in the depending file's docstring too.

1. **No stack skill beyond `python` exists in the library for
   SQLAlchemy/pytest-anyio specifics** — proceeded on `ai-toolkit:testing`
   + `python` plus this repo's own integration-tier precedent.
2. **Module paths and API shapes are invented throughout** (no artifact
   fixes them): `commerce_ops.shared.domain.identity` /
   `.lifecycle_stage`; `commerce_ops.catalog.domain.product`
   (`Product.register`, `change_stage(new_stage, confirmed_by, at)`,
   `StageChanged` attribute spellings); the six use-case functions and
   `DuplicateSkuError` on `commerce_ops.catalog.application`;
   `CatalogProductRepository(session)`;
   `LaunchPositionRepository(session)` and its three methods. Depending
   tests: all six files. Divergence is a fixture correction, not an
   assertion change.
3. **Rejection signal types** — see the derived list above. Depending
   tests: every `pytest.raises` site.
4. **Whether use cases take the store port as first positional argument**
   (assumed from `run_daily_digest(reader)` precedent). Depending tests:
   both integration files and the application-level unit test.
5. **The list use case's port method name (`list()`)** — the fake in
   `test_list_products_empty_catalog.py` implements only it.
6. **Integration-tier DB conventions** (env var `DATABASE_URL`, skip on
   absence, `alembic upgrade head` pre-applied, no truncation, unique
   SKUs) — read off this tier's existing test files, not off a recorded
   project convention document. Depending tests: both integration files.
7. **Clock handling** — aggregate tests assume the change time is passed
   in (`at=`); if the aggregate stamps its own clock, exact-time
   assertions relax to windows (fixture correction, recorded in the
   file's docstring).

## What the implementation step must make pass

All six files above, green, without editing them except for the recorded
fixture-correction latitude (paths, names, signatures — never the
asserted postconditions), plus keeping the pre-existing suite green
except where a test appears in the obsolete list and a human confirms
its retirement. The migration-verification test (tasks.md 4.3) is owed by
the implementation step and is not among these files.
