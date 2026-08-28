> Symbols are named without line numbers: `_admin_header.html` is rewritten
> by `add-launch-tracking-pages` in the same block this change edits, so a
> line number recorded now is likely wrong by the time the task is worked
> (`design.md` — Risks).

## 1. Tests derived from the delta specs

- [x] 1.1 Dispatch `ai-toolkit:openspec-test-writer` over both delta specs. Every scenario is new — this change introduces `product-dossier` whole and adds two requirements to `launch-step-automation` — so nothing is excluded as already covered
- [x] 1.2 Place them by the tier rules in `AGENTS.md`: the read's scenarios under `tests/unit/launch/application/`, the two pages' under `tests/unit/launch/infrastructure/driving/`, and the repository read's ordering and retention against a real database under `tests/integration/launch/`. **One deliberate departure**, taken and recorded: the two *retained record covers … and nothing else* scenarios sit in the driving tier instead, because each one's WHEN is a handler resolving a step — a test that seeded no row and read nothing back would assert nothing at all — so the pass must run, and the file reuses `test_automation_pass.py`'s harness
- [x] 1.3 Record the baseline: run `uv run pytest` and confirm each new test fails for the reason the scenario states, not for a missing import or fixture

## 2. The read

- [x] 2.1 Add one method to `AutomatedResultRepository` (`launch/infrastructure/driven/automated_results.py`) answering every row for a product, ordered `produced_at DESC, id DESC`. The identifier is the tiebreak and is never presented — without it two results produced in the same pass can re-render swapped (`design.md` — Decision 5)
- [x] 2.2 Give it no state filter, no step filter and no knowledge of access scope. It answers rows; the repository holds no policy, which its own docstring is explicit about (`design.md` — Decision 4)
- [x] 2.3 Add a `launch/application/retained_results.py` use case exposing that read, applying `scope.permits(product_id)` and answering emptily — never raising — where the scope does not permit it, the shape `read_launch` and `read_launches` already use
- [x] 2.4 Return a frozen dataclass per result rather than the ORM row: the step identifier, handler, proposed outcome, produced text, produced moment, state, decider and decision moment. A driving adapter reading `AutomatedStepResult` attributes would reach through the application layer into `launch.infrastructure.driven`, which is exactly what the module's public surface exists to prevent
- [x] 2.5 Export the use case and its result type from `launch/application/__init__.py` and add both to `__all__`. `import-linter` enforces that surface as the module's only public one, so an adapter cannot reach the use case without it
- [x] 2.6 Carry the voided row's absent decider through as absent. `void` sets only the state and the decision moment, leaving `decided_by` untouched — verified in `automated_results.py` — so a voided result answers with no decider and the page has one less thing to special-case
- [x] 2.7 Do **not** re-resolve the decider against the roster anywhere in this path. `decided_by` is the name recorded at the decision, and rendering it as stored is both the store's shape and the requirement (`design.md` — Decision 6)

## 3. The product index

- [x] 3.1 Create `launch/infrastructure/driving/product_dossier.py` with an `APIRouter`, its templates loaded through a `ChoiceLoader` over its own `templates/` and `shared`'s `TEMPLATES_DIR`, exactly as `playbook_admin.py` and `roster_admin.py` both do — so `_admin_header.html` stays one file
- [x] 3.2 Add `GET /admin/products` behind the same `_require_admin` shape `playbook_admin.py` uses: a session cookie verified against an injected verifier, refusing with the app's own 404 when the session is absent, expired, or its principal no longer resolves admin-capable
- [x] 3.3 Resolve the caller's `AccessScope` from the session principal via `resolve_scope` and pass it to `list_products`. Do **not** pass `AccessScope.unrestricted()`: it is observationally identical today and silently wrong the moment product-level scoping exists
- [x] 3.4 Render one row per product with its SKU, name and lifecycle stage — the four things `product-catalog` requires `list_products` to answer, minus the identifier, which is the row's link target rather than a column
- [x] 3.5 Order rows by SKU ascending **within each group**, and present products in the `Retired` stage set apart from the rest rather than interleaved. The qualification is not decorative: a single ascending sort across the whole page and the set-apart rule cannot both hold once a retired product's SKU sorts first — `roster-admin`'s shape for deactivated people. Set apart, not hidden: no reveal control is specified here, and adding one would be a narrowing this change has not designed
- [x] 3.6 Render an empty scope and an empty catalog as a page with no rows that says there is nothing to show. A blank region is the anti-default the requirement exists to forbid
- [x] 3.7 Make each row open `/admin/products/{product_id}` in one action, and keep the link un-boosted for the reason `_admin_header.html` already records: `hx-boost` is inherited from `<body>`, so htmx would swap the target into this page's body and discard the new page's own body attributes

## 4. The dossier page

- [x] 4.1 Add `GET /admin/products/{product_id}` on the same guard, reading the product through `catalog.application`'s `get_product_by_id` with the caller's scope
- [x] 4.2 Refuse absence-shaped when the read reports absence, which covers both an identifier naming no product and a product outside the scope — `get_product_by_id` already collapses the two, so no code here distinguishes them and none may
- [x] 4.3 Turn the page on the **product**, never on whether a launch position exists. A product that never launched renders; only its record is empty
- [x] 4.4 Accept no SKU at this address. One canonical URL per product; a SKU arriving here is an identifier naming no product and is refused as absence like any other (`design.md` — Decision 2)
- [x] 4.5 Render the product's SKU, name, marketplace, ASIN, lifecycle stage, stage-entry moment and stage confirmer — all seven from the `Product` aggregate `get_product_by_id` returns, which was checked to carry `stage_confirmed_by` because `product-catalog`'s read requirement does not enumerate it. State an absent ASIN and an absent confirmer explicitly — `Product.register` leaves `stage_confirmed_by` as `None` for every product still in `Development`, so the empty confirmer is the common case, not the edge one
- [x] 4.6 Offer no control on either page that changes stored state, and no accept or reject on a pending entry. The decision flow's once-only settlement, roster checks and refusals are all specified against the Slack path; a second door would put them behind something nothing has specified

## 5. The produced record

- [x] 5.1 Render every retained result for the product, in the order the read answers them — reordering nothing on the page — each carrying its step, handler, proposed outcome, produced text and produced moment
- [x] 5.1a Pass the caller's resolved `AccessScope` to the retained-results read, never `AccessScope.unrestricted()`, for exactly the reason 3.3 gives for the index. The use case applies `scope.permits` either way; what this fixes is the argument the adapter hands it
- [x] 5.2 Carry exactly one of the literal markers `result-pending`, `result-accepted`, `result-rejected` and `result-withdrawn` on each entry, and label a `voided` result as withdrawn — never as rejected, and with no decider, because none is recorded for it. `models.py` records why the two states are distinct; collapsing them attributes to a person a judgement they never made. `result-withdrawn` deliberately does not match the stored `voided`: the marker names what the page says (`design.md` — Decision 11)
- [x] 5.2a Carry the other literal markers the deltas fix, exactly as spelled: `step-unnamed` on an entry falling back to its step identifier, `retained-for-decision` on the record's container, `nothing-produced` on an empty record, `not-recorded` on an absent ASIN or stage confirmer, `nothing-to-show` on an empty index, `product-retired` on a retired index row. They are what the derived tests assert; a synonym is a failing test, not a stylistic choice
- [x] 5.3 Render a `pending` result as awaiting a decision, with no decider. Do not render `delivered_at`: whether a proposal has reached Slack is the decision loop's plumbing, and the page is the record
- [x] 5.4 Read the served playbook once for the page and name each step it defines. Fall back to the raw step identifier for a step the playbook no longer defines — the circumstance that voids a result, so expected rather than exceptional — and for a playbook that cannot be read at all. Neither may fail the page (`design.md` — Decision 7)
- [x] 5.5 Label the record as the results retained **for a decision**, not as everything produced for the product. Only a terminal proposal on a confirmable step reaches the table; a page implying otherwise is wrong invisibly, and totally so for a product whose automated steps all need no confirmation (`design.md` — Decision 8)
- [x] 5.6 Render a product with no retained results as the identity plus an explicit statement that nothing has been produced, never as an empty record region
- [x] 5.7 Render the produced text with its line structure preserved by styling rather than by markup, through Jinja's autoescaping. It is model output stored verbatim; the page must not become the place it is first interpreted

## 6. The header and shared presentation

- [x] 6.1 Add the product index to `shared/infrastructure/driving/templates/_admin_header.html` as a named surface, with a `current` value of its own, keeping the outbound links un-boosted for the reason the partial records
- [x] 6.2 Have the index identify itself as current in the header, and the dossier carry the header **without** being a named entry in it — it is a page about one product and has no address the header could name (`design.md` — Decision 3)
- [x] 6.3 Load the shared admin stylesheet on both pages through `admin_assets`' `/admin/assets/{asset}` — the route `shared` owns and every admin surface reaches on equal terms. Not through `playbook_admin.py`'s `/admin/static/{asset}`: that route belongs to another admin surface, and depending on it is what `roster-admin`'s presentation requirement forbids
- [x] 6.4 Carry no page-local style block on either template
- [x] 6.4a Add the rules both pages need to `shared/infrastructure/driving/static/vocabulary.css` — a retired index row set apart, an entry's state, and produced text whose line structure is preserved by styling rather than by markup. Three rules no admin surface has needed yet, and the reason the shared stylesheet is an affected file rather than an untouched one. Add rules; rewrite none, since `add-launch-tracking-pages` edits the same file (`design.md` — Risks)
- [x] 6.5 Register the new router in `main.py` beside the other admin routers
- [x] 6.6 Add the header test where `playbook-admin` and `roster-admin` are already tested, not only under the new capability — a test derived from this change alone would not catch an existing surface's header failing to offer the index

## 7. Boundaries and sequencing

- [x] 7.1 Confirm `import-linter` still passes with no contract edit. `products-infrastructure-boundary` forbids `catalog.domain` and `catalog.infrastructure` to `launch.infrastructure` and not `catalog.application`, so the two catalog reads are already permitted — verify rather than assume, and if it fails, stop and reconsider rather than widening the contract
- [x] 7.2 Confirm `git diff` touches nothing under `launch/domain/`, nothing in the automation pass, the confirmation flow or the decision use cases, and no `alembic/` migration. This change reads what already exists
- [x] 7.3 Merge `main` before the final review and re-read `_admin_header.html` as it stands. If `add-launch-tracking-pages` has landed, resolve the header by folding this surface into the shape it left — if it turned the two-branch conditional into a loop, add an entry to the loop rather than re-adding a branch. Taking either side of that conflict wholesale drops the other change's surface
- [ ] 7.4 Confirm this change carries **no** `roster-admin` and no `playbook-admin` delta. Unconditional, in either archive order, and the only thing this change has to get right about the header requirements. A block written here would replace the requirement wholesale on archive — silently, since `openspec validate` does not object — and it is never needed: both requirements already oblige the header to name "the admin surfaces the session can reach", so a header naming the index satisfies them as they stand. This is the counterpart of `add-launch-tracking-pages`' task 6.3
- [ ] 7.4a Archive in whichever order the two changes land. Confirm before archiving that `openspec/specs/roster-admin/spec.md` and `openspec/specs/playbook-admin/spec.md` each still carry the clause *naming the admin surfaces the session can reach* — the one in force today, **not** whatever `add-launch-tracking-pages` adds to it. Verify rather than assume, since the whole argument for needing no delta rests on that clause; and note that it holds whether or not that change has landed, so this check never waits on it. If either has *lost* that clause, stop: that is a different situation than the one this change was reviewed against
- [ ] 7.5 Confirm `product-dossier`'s own header requirement carries the index's reachability obligation, so nothing this change needs is borrowed from a requirement another change owns

## 8. Verify against the specification

- [x] 8.1 Run `uv run pytest` and confirm the tests from section 1 now pass, with no previously passing test weakened, skipped or deleted
- [x] 8.2 Run `ruff check`, `ruff format --check`, `mypy` and `import-linter`
- [x] 8.3 Confirm the integration tier actually ran rather than skipping for want of a database — `tests/integration/conftest.py` skips and says why when none resolves, and a skipped tier is not a verified one
- [x] 8.4 Confirm the tiebreak is asserted **at the read**, in the integration tier, and can actually fail without it. Two renders compared against each other cannot: a query with no tiebreak commonly returns equal keys in the same order twice, so that test passes against the defect. It must assert the **direction** — of two rows sharing a `produced_at`, the higher row identifier comes first — and must hold whichever order the two were stored in, so insertion order is not what the assertion is reading (`design.md` — Decision 12)
- [x] 8.4a Do not attempt the same assertion at the page: task 2.4's exposed dataclass carries no row identifier, so the page cannot see what the tiebreak turns on. The page's own test asserts only that it renders in the order it was given
- [x] 8.4b Confirm the derived tests assert the literal markers as spelled in the deltas, and that the read-only test asserts the *absence* of a form and of `row-action` rather than the presence of nothing in particular
- [x] 8.5 Confirm the out-of-scope read is tested as answering *emptily*, indistinguishably from a product with nothing retained — an assertion that it raises would encode the opposite of the requirement

## 9. Confirm against the deployment

- [ ] 9.1 Exercise both pages by hand: the index lists in SKU order within each group, with retired products set apart and following the rest; a row opens its dossier; the header offers the index from the playbook and roster surfaces and back
- [ ] 9.2 Open the dossier for a product with no launch, one mid-launch and one graduated — the first states that nothing has been produced, the other two render their records
- [ ] 9.3 Confirm a voided entry reads as withdrawn with no decider, an accepted one names its decider, and a pending one offers no decision control
- [ ] 9.4 Confirm both pages 404 identically with no session cookie, and that the stylesheet does too
