## 1. Tests derived from the delta specs

Written before the implementation, from the deltas' scenarios rather than from the code, by an author other than whoever writes the implementation (`AGENTS.md`, *Test design before implementation*). Dispatched only after the reviewer's verdict permits proceeding and the approved plan is committed.

`pre-commit` runs the whole `tests/unit` + `tests/agents` tree, so these land in the same commit as the implementation they were written against.

### Catalog

- [ ] 1.1 `tests/unit/catalog/` — recording a non-empty set against a product with none recorded reads back as exactly that set; a later recording replaces it wholesale with no member of the earlier set surviving; recording succeeds for a product in `Retired`; and a read-back reports the recorded set and nothing about which categories the screening screened against (*A hazard-category finding can be recorded against a product*, *What was screened against is not recorded with the result*).
- [ ] 1.2 Recording an **empty** set against a product with none recorded reads back as *recorded and empty*, not as never recorded; and an empty set recorded over a non-empty one replaces it. These are the two rows that fail an implementation storing `NULL` for `[]`, which is the single most likely defect in this change (*An empty set is recorded as an empty set*, *An empty set replaces a recorded set*).
- [ ] 1.3 The three states are mutually distinguishable on read-back: never recorded, recorded-and-empty, recorded-and-non-empty, asserted pairwise rather than by asserting each against a literal — a test comparing each to an expected value passes for an implementation that reports two of them identically to a *caller* while differing internally (*A product reports its hazard categories in three states, never two*).
- [ ] 1.4 A product registered before the field existed — constructed without it — reports its hazard categories as never recorded, and not as an empty set (*A product predating the field reports the question as open*).
- [ ] 1.5 `tests/integration/catalog/` — the three states survive a Postgres round trip, `NULL` and `{}` included. This tier is where the storage decision is actually proved: the in-memory double cannot distinguish a column that stores `[]` as `NULL`.

### The screen

- [ ] 1.6 `tests/unit/step_handlers/strategy/` — extend the existing schema-conversion guard to the widened wire schema: obtained from the `with_structured_output` call site through the `build_graph(model)` seam as it already is, converted by `langchain_openai`'s and `langchain_core`'s own conversions, asserting **no `oneOf` anywhere** and that `categories` is an array of plain strings. The guard exists; what is being asserted is that the new field did not push the schema out of the accepted subset (*The structured-output schema is one the model provider's adapter accepts*, unchanged and re-exercised).
- [ ] 1.7 Every wire field, the new one included, carries a non-empty `description` in the generated JSON schema (*Wire fields state when they are to be populated*, unchanged and re-exercised).
- [ ] 1.8 `tests/agents/step_handlers/strategy/` — the finding table, one case per row, over a stubbed model. Assert the finding **and** that the outcome and rendered text are unchanged from what the same response produces today, so a regression in either is caught here rather than in the existing verdict table:
  - `clear` + non-blank comment + `[]` → satisfying outcome; finding present, value an empty sequence. Assert *present and empty*, distinguishable from absent — an assertion that merely tests falsiness passes for `finding=None` and is the defect this row exists to catch (*A clear verdict establishes an empty set of categories*)
  - `flagged` + non-blank comment + one or more categories → non-terminal; finding carries exactly those categories (*A flagged verdict establishes the categories it named*)
  - `undetermined`, any `categories` → non-terminal; **no** finding, and in particular not an empty one (*An undetermined verdict establishes nothing*)
  - a response validating against no schema → non-terminal; no finding (*An unreadable verdict establishes nothing*)
  - a verdict with an absent, empty or whitespace-only comment → non-terminal; no finding
  - no product resolvable, and a step whose description is blank → non-terminal; no finding, and for the blank description no model call is made (*A screen given nothing to work with establishes nothing*)
- [ ] 1.9 The two structural contradictions, each asserted on its own reason rather than only on its outcome:
  - `clear` + non-empty `categories` → non-terminal; **no finding**; rendered text carries both the clear verdict and the named categories; reason is textually distinct from the prose-contradiction reason (*A clear verdict naming categories is refused*, *The structural contradiction is not reported as the prose one*)
  - `flagged` + empty `categories` → non-terminal; no finding; reason textually distinct from **both** the flagged reason and the undetermined reason. Without the distinctness assertion an implementation routing it to either passes (*A flagged verdict naming no category establishes nothing*)
  - `clear` + a comment stating the screen could not screen the product → non-terminal, the prose-veto reason, and **no finding**. This row is not a re-exercise of the existing veto: it is the prose half of *A contradicted verdict establishes nothing about the product*, and without it an implementation that computes the finding on the `clear` branch before applying the veto passes every other row while violating the delta
  - the existing prose veto still reports its own reason, and a comment about a *category* being inapplicable still proposes satisfaction **and still carries the empty finding** — the row that stops the veto being reimplemented as a phrase list, extended so that a veto widened to catch it would also be caught by the finding assertion (unchanged requirement, re-exercised)
  - `clear` + non-empty `categories` + a blank comment, and `flagged` + empty `categories` + a blank comment → both treated as unreadable, carrying that route's reason rather than either contradiction's, and reporting no finding (*A blank comment outranks a structural contradiction*). These are the two combinations the widened schema newly admits into more than one destination
- [ ] 1.10 A product whose recorded categories are non-empty, screened again with a response that establishes nothing (undetermined), leaves the product's recorded categories unchanged — asserted against the recorder, which must not be invoked at all (*A prior flag survives a later screening that establishes nothing*).
- [ ] 1.11 Category naming: the prompt the model receives instructs it to use the step description's wording (*The model is instructed to use the description's wording*); a named category is carried through with surrounding whitespace and case normalised and nothing else altered (*A named category is carried through unaltered*); a category the description does **not** contain verbatim is still reported (*The description is not parsed to validate a name*) — this row is what fails an implementation that adds a validator; and no category appears that the response did not name (*No category is supplied that the response did not name*).
- [ ] 1.12 Two names normalising to the same value are reported once, in the first one's position; a name normalising to nothing is dropped; and a `flagged` response whose every name drops reaches the flagged-naming-nothing route rather than reporting an empty finding (*A repeated category is reported once*, *A blank category name is dropped*).
- [ ] 1.13 The finding names no field: the resolution the handler returns carries a value and a comment and nothing identifying where either goes (*The finding SHALL NOT name the field it is written to*).
- [ ] 1.14 Model failure still propagates, with no finding produced and no non-terminal reason — re-exercised because the new routes sit one branch away from it and a broad `except` added while widening the schema would land in one of them (*Model failure is surfaced, not masked*, unchanged).

### Wiring

- [ ] 1.15 `tests/unit/launch/` — the automation pass, given a sink registered for `lp.strategy.006` and a handler reporting a finding whose value is an empty sequence, invokes the recorder with that empty sequence and keeps the finding on what it stores. The generic path already has coverage; this row pins the *empty sequence* case for the second sink, which is the one `lp.listing.007` never exercised.
- [ ] 1.16 A stored finding whose value is an empty **sequence** reads back as present-and-empty, distinguishable from a recording carrying none — the `launch-instance` guarantee (*an absent finding is distinguishable from an empty value*) that this change is the first non-scalar consumer of. A read path treating a falsy value as "no finding" collapses it on the launch record while the catalog side stays correct, so this cannot be inferred from 1.2.
- [ ] 1.17 **The rejected value stands.** Rejecting a pending result for a step whose finding was already written leaves the product's recorded set unchanged — asserted for a recorded **non-empty** set and, separately, for a recorded **empty** set, since the empty case is the one where an erase-on-rejection implementation looks superficially correct (*A rejected proposal's recorded value stands*, *A rejected clear reading is still a screening, not an open question*). This requirement is satisfied by the system doing nothing, so it has no implementation task to hang a guard on; without this row a later author adding reconciliation breaks nothing the suite notices.
- [ ] 1.18 A subsequent screening's finding replaces a disputed value, the replacement being performed by the screening rather than by the earlier decision (*A later screening replaces a disputed value*).
- [ ] 1.19 Extend the existing cross-process registration check so both composition roots hold the second sink (`tests/unit/test_registrations_across_processes.py` — where two roots disagreeing is caught).

### The launch detail page

- [ ] 1.20 `tests/unit/launch/infrastructure/driving/` — a carried finding whose value carries several members renders every member, each readable and separated, with no bracket, quotation mark or type name from a collection's programming notation around them (*A value of several members renders as those members*); and a textual value renders as one value rather than as its characters (*A textual value is not rendered as its characters*). Both are expected to pass against the current renderer — see `design.md` Decision 8: they are regression guards on behaviour nothing currently specifies, and passing on the first run is the expected result, not a sign the rows are worthless.
- [ ] 1.21 The empty-value rendering still stands and still outranks member rendering: a finding whose value carries no members renders as visible text standing for emptiness (*An empty value renders as readable text*, unchanged and re-exercised for a sequence rather than a string).

### The dossier

- [ ] 1.22 `tests/unit/launch/infrastructure/driving/` — the region marked `established-by-automation` is present on every dossier render, distinct from the region marked `retained-for-decision`, and renders for a product with neither field recorded (*The region is present and marked*, *The region renders for a product with nothing established*).
- [ ] 1.23 A recorded sub-category is presented; an absent one carries `not-recorded` and is not blank (*A recorded sub-category is rendered*, *An absent sub-category carries the page's absence marker*).
- [ ] 1.24 The three hazard states render three ways, asserted **pairwise and by marker**, not by prose match:
  - never recorded → carries `not-recorded`, does **not** carry `screened-clear`
  - recorded and empty → carries `screened-clear`, does **not** carry `not-recorded`, and states the product was screened with no category found
  - recorded and non-empty → presents every category, **each readable and separated, with no bracket, quotation mark or type name** from a collection's programming notation, and carries neither marker (*A flagged product presents its categories*, *Categories are not presented in a collection's notation*). Unlike the launch page's equivalent this is new code rather than existing behaviour, so it is a real guard and not a regression guard
  - and the three rendered fields are pairwise distinguishable in the response (*The three states render three ways*). The middle row against `not-recorded` is the assertion the whole surface change exists for.
- [ ] 1.25 The field is presented as established by a screening and carries none of "confirmed", "approved" or "accepted" (*The field claims no ratification*).
- [ ] 1.26 The new region contains no form and no element carrying `row-action`, and the page carries no page-local style block when a `screened-clear` field is rendered (*The region is read-only*, *The new state's presentation is shared, not page-local*).

## 2. Storage

- [ ] 2.1 Alembic revision adding `hazard_categories text[] NULL` to `products` — no default, no check constraint, no backfill. Parent it on `b62d05f1ae37`; run `uv run alembic heads` first and confirm it is still the single head, and again before pushing (`design.md`, Migration Plan).
- [ ] 2.2 Add the column to `CatalogProduct` (`catalog/infrastructure/driven/models.py`) as a nullable `ARRAY(String)`, beside `sub_category`.
- [ ] 2.3 Map it in `catalog/infrastructure/driven/product_repository.py` in both directions, keeping `NULL` and `[]` distinct across the round trip. This is the one mapping where a falsy-value shortcut silently collapses the two states.

## 3. Catalog domain and use case

- [ ] 3.1 `Product` gains `hazard_categories: Sequence[str] | None = None` on `__init__`, defaulting to absent, and `record_hazard_categories(categories)` shaped exactly like `record_sub_category` — a standalone fact, no confirmer, any stage. Store as an immutable sequence so a caller cannot mutate what the aggregate holds.
- [ ] 3.2 `catalog/application/use_cases.py` gains `record_hazard_categories(store, product_id, categories)`, shaped like `record_sub_category`.
- [ ] 3.3 Export it from `catalog/application/__init__.py`'s `__all__` — the module's only public surface, enforced by `import-linter`.

## 4. The screen

- [ ] 4.1 `ScreenResponse` gains `categories: list[str]`, required, with a description stating what it is for and when it is populated — including that it is empty for `clear` and for `undetermined`, since the model reads that description as instruction. Keep the schema flat; add no union (`design.md`, Decision 2).
- [ ] 4.2 Extend `_PROMPT` to instruct the model to name each category using the wording the step's description uses, and to leave the list empty unless the verdict is `flagged`.
- [ ] 4.3 Add the normalisation: strip surrounding whitespace, drop names that normalise to nothing, and deduplicate case-insensitively while preserving the first occurrence's own casing and position. Nothing else is altered, and the description is never parsed (`design.md`, Decision 4).
- [ ] 4.4 Add the two structural contradiction routes with their own reason functions, beside the existing `_contradiction_reason` rather than folded into it: `clear` naming categories, and `flagged` naming none. Both check structure only. Keep the existing blank-comment check ahead of both, which is where it already sits — the delta now requires that order rather than leaving it to the implementation. Add a comment saying why the structural checks and the prose veto stay separate — a later author will try to unify them (`design.md`, Decision 3).
- [ ] 4.5 Return `finding=Success(value=[...], comment=comment)` on exactly two routes — a `clear` verdict neither contradiction refuses (empty list), and a `flagged` verdict naming at least one category (the normalised categories) — and `finding=None` on every other route, naming them so none is reached by omission: undetermined, unreadable, blank comment, the prose contradiction, the structural `clear`-naming-categories contradiction, `flagged` naming none, no product, and no categories. Compute the finding **after** the veto and contradiction checks have decided the route, not on the `clear` branch before them. Leave every existing outcome and every rendered text exactly as it is.
- [ ] 4.6 Update the module docstring: what the finding carries and on which routes, why the categories are not validated against the description, and the referenced-list limitation. The docstring is where this module's reasoning lives and it is load-bearing here.

## 5. Ports and wiring

- [ ] 5.1 Replace `SubCategoryRecorder` in `launch/application/ports.py` with `FindingRecorder` — `async def __call__(self, product_id: ProductId, value: Any) -> object` — with a docstring saying why the value type is loose (`design.md`, Decision 6).
- [ ] 5.2 Update `launch/application/__init__.py`'s import and `__all__`, and `worker.py`'s docstring reference, in the same commit — the public surface changes and both ends must move together.
- [ ] 5.3 `worker.py`: add `_record_hazard_categories` as the partial application over the catalog store, beside `_record_sub_category`, and register the second `FindingSink` for `lp.strategy.006` with `field="hazard_categories"` and `reads_as="Hazard categories"`.

## 6. The launch detail page

- [ ] 6.0 Expect **no change** to `launch_admin.py` or `templates/launch.html`. `_render_finding_value` already renders a sequence as its members and already refuses to treat a string as one; the delta specifies behaviour that exists. If the tests derived from 1.20–1.21 fail, the renderer is wrong and the fix belongs here; if they pass unchanged, that is the expected result (`design.md`, Decision 8). Do not edit the renderer to make a passing test look earned.

## 7. The dossier

- [ ] 7.1 `product_dossier.py`: carry `sub_category` and `hazard_categories` onto the view model the template renders, with the hazard field resolved to one of three states rather than to a value plus a truthiness test — an implementation branching on truthiness cannot express the middle state.
- [ ] 7.2 `templates/product.html`: the new region carrying `established-by-automation`, the sub-category field with `not-recorded` for absence, and the hazard field carrying `not-recorded`, `screened-clear` or the categories. No form, no `row-action`, no page-local `<style>`.
- [ ] 7.3 `shared/infrastructure/driving/static/vocabulary.css`: presentation for `screened-clear`, beside the page's other markers.

## 8. Verification

- [ ] 8.1 Configure this worktree's integration tier before relying on it — it inherits no `.env.test` and skips entirely without one, while `pre-push` reports the skipped tier as `Passed` (`AGENTS.md`, *Working in a git worktree*). Create a database whose name ends `_test`, `alembic upgrade head`, then `uv run python -m commerce_ops.seed_playbook`; migrated is not seeded.
- [ ] 8.2 `uv run pytest` green across all three tiers, with the integration tier confirmed to have actually run rather than skipped.
- [ ] 8.3 `ruff check`, `ruff format --check`, `mypy` clean. Clear `.mypy_cache` first if it reports phantom errors — a stale cache in a fresh worktree does.
- [ ] 8.4 `uv run alembic heads` reports one head.
- [ ] 8.5 `import-linter` contracts pass — the catalog use case is reached only through `catalog.application`'s public surface, and the port replacement did not open a new path.
- [ ] 8.6 `/code-review` over the change's diff, against this change's own specs (`AGENTS.md`, *Independent review before completion*). Not `openspec-change-reviewer`, which reviews plans and explicitly not the code that follows them.
- [ ] 8.7 Open the running admin surface and look at: a dossier in all three hazard states; the Outcome column for a `lp.strategy.006` recording carrying an **empty** finding; and the Outcome column for one carrying a **flagged** finding of several categories. The last is the first non-scalar value this surface has ever rendered — the rendering is now specified but how the members read beside a wording and a comment is the visual judgement `launch-admin` declines to fix. `design.md`'s open question is settled here.

## 9. Landing

- [ ] 9.1 PR to `main` — nothing deploys from a local machine, and merging to `main` is what triggers the deploy.
- [ ] 9.2 Archive in a **follow-up** PR (`openspec archive screen-for-hazard-categories --yes`).

  This deliberately departs from `AGENTS.md`, *Deployment and configuration*, which says to make the archive "the last commit before the merge". Two reasons, and the departure is recorded here rather than made silently:

  - The archive rewrites `openspec/specs/` by folding the deltas in. Including it in the implementation PR would put that rewrite inside the diff `/code-review` reads, and the code review's job is to check the code against *this change's own delta specs* — which the archive commit removes from `openspec/changes/` in the same diff.
  - It is what the repository actually does. `#136→#137` and `#157→#158` are both implementation-then-archive pairs, and `#158` is open at the time of writing, holding the archive of the two changes this one builds on.

  **This is a genuine conflict between `AGENTS.md` and the repository's own practice, and it is not this change's to resolve.** Raise it separately: either `AGENTS.md`'s sentence is stale and should describe the two-PR shape, or the practice is wrong and every recent change has been. Do not settle it by quietly following one of them.
