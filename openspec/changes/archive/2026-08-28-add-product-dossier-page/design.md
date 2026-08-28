## Context

See `proposal.md` — *Why*. What follows is only the state that shapes the approach.

The retained results live in `automated_step_results`, a single table behind `AutomatedResultRepository`. That repository holds no policy — "what may be stored, what a decision means and when a step becomes eligible again are the pass's and the use cases' business; this only reads and writes rows" — and every read it offers today serves the decision loop: `pending_for`, `by_id`, `undelivered`, `latest_rejection`.

Three properties of the stored row decide most of what follows.

- `product_id` is a foreign key to `launch_positions.product_id`, `ON DELETE CASCADE`. A result therefore cannot exist for a product that never had a launch, and the retained set is bounded by the launch positions that exist.
- `decided_by` is a `String`, written as `str(who)` where `who` is the decider's display name, falling back to their roster id and then to the raw Slack identity. It is a **snapshot taken at the decision**, not a reference the roster can later reinterpret.
- `proposed_outcome` is a `String` holding the outcome's *name*, deliberately: "the row is read back by a person's decision, possibly after a deploy, and a stored class reference would tie a waiting proposal to the code that produced it."
- `void` sets the state and the decision moment and leaves `decided_by` untouched, so a voided row carries no decider. That is what makes "voided is not a flavour of rejected" true in the data and not only in the prose.

One catalog fact was checked rather than assumed, because `product-catalog`'s read requirement does not enumerate it: `get_product_by_id` returns the `Product` aggregate, which carries `stage_confirmed_by`. The dossier's confirmer field therefore needs no `product-catalog` delta.

On the surface side, the admin pages already share two things through `shared.infrastructure.driving`: `TEMPLATES_DIR`, which holds `_admin_header.html`, and `admin_assets.router`, which serves `GET /admin/assets/{asset}` behind its own injected admin guard. `playbook_admin.py` and `roster_admin.py` both load templates through a `ChoiceLoader` over their own directory and that shared one.

## Goals / Non-Goals

**Goals:**

- One read that answers a product's retained results, added to the repository and exposed through `launch.application`, with the caller's scope applied where every other product-keyed read applies it.
- Two read-only pages that render what already exists, riding the guard and the presentation the other admin surfaces already ride.
- A record that is honest about its own boundary — what it holds, and what it does not.

**Non-Goals:**

- Changing anything the decision flow does. No write path, no stored shape, no migration.
- Giving the produced text a structure. `handler_contract.py` settled that it is plain text; this change is a third consumer that also wants text.
- A launch row linking to the dossier. `add-launch-tracking-pages` specifies no such link, and adding one here would mean editing that change's page.
- Search, filtering or pagination on either page.

## Decisions

### Decision 1 — The adapter lives in `launch.infrastructure.driving`, not in `catalog`

Both directions are permitted by `.importlinter`: `products-infrastructure-boundary` forbids `catalog.domain` and `catalog.infrastructure` to `launch.infrastructure` but not `catalog.application`, and `catalog-infrastructure-boundary` forbids `launch.domain` and `launch.infrastructure` but not `launch.application`. The boundary does not decide this; the ratio of reads does.

The page's substance is the retained record, which `launch` owns entirely. Its catalog half is two calls — `get_product_by_id` for the dossier, `list_products` for the index. Putting the adapter in `catalog` would invert that: the whole page would be read through `launch.application` from a module that has no other reason to know the automation exists.

It also matches the shape already in the repository. Each admin surface lives in the module owning the data it presents — `playbook_admin.py` in `launch`, `roster_admin.py` in `access` — and `playbook_admin.py` already reads `access.application` for the roster data it needs to render an assignee. `add-launch-tracking-pages` reaches the same arrangement independently for its own pages.

**Alternative considered:** `catalog.infrastructure.driving`, on the argument that the proposal makes at length — the dossier belongs to the product, not to the launch. That argument is about *addressing and lifetime*, and it is honoured by keying the page on the product identifier and rendering it for a graduated launch. Which bounded context owns the adapter is a different question, and the answer follows the data.

### Decision 2 — The dossier is addressed by product identifier alone

`get_product_by_sku` exists, takes a scope and reports absence identically, so accepting a SKU would be cheap in code. It is not cheap in semantics: a route accepting either has to decide what an identifier that could be both means, and the resolution order becomes part of the page's behaviour — something a reader of the URL cannot see and a future SKU format could silently change.

An admin who knows only a SKU is asking to *look a product up*. That is the index's job. Giving the address two meanings to avoid building the way in would have left both jobs half-done.

**Alternative considered:** a separate `/admin/products/by-sku/{sku}` redirecting to the canonical URL. Unambiguous, but it is a lookup route with no lookup interface, which is the index again with worse ergonomics.

### Decision 3 — The index exists because the header cannot name a per-product URL

`_admin_header.html` renders each surface as something reachable in one action. `/admin/products/{product_id}` has no id-less form, so the header has nothing to link to; and nothing else in the repository links here — `add-launch-tracking-pages` mentions this change only in a coordination task, not in a requirement.

Without the index, the dossier would ship reachable only by someone who already knew its URL — verbatim the defect `roster-admin`'s header requirement records against the roster page ("An admin who reaches it — which itself requires knowing the URL, since nothing links here — cannot get back"). The index is the smallest thing that makes the header's claim true, and it is built entirely from a read `product-catalog` already requires.

The index is the header entry; the dossier carries the header without being named in it.

**Alternative considered:** shipping the dossier unreachable and proposing reachability separately. Honest, but it ships a page nobody can open, and the follow-up would have to add the index anyway.

### Decision 4 — The scope check lives in the use case, not in the repository

`AutomatedResultRepository` gains one method — every result for a product, ordered — and no knowledge of access scope, keeping the repository as policy-free as its docstring claims. The `launch.application` use case that exposes it applies `scope.permits(product_id)` and answers emptily when it does not, the same shape `read_launch` and `read_launches` already use.

The adapter reads the product first. A product outside scope already reports absence from `get_product_by_id`, so the page refuses before the results read happens; the check in the use case is the one that has to hold for any *other* caller of the read, present or future.

### Decision 5 — Ordering is `produced_at` descending with the row identifier as tiebreak

`produced_at` alone is not a total order: two results produced within the same pass can share a timestamp, and a database is free to return equal keys in any order, so an unchanged page could re-render with its entries swapped. The row's `id` breaks the tie. It carries no meaning and is not presented — it is there so the order is a function of the data.

### Decision 6 — The decider is rendered as recorded, never re-resolved

This is the store's shape rather than a preference: `decided_by` holds the name written at the decision. Rendering it as stored is therefore the only honest option, and it is also the right one — a record of past decisions that silently re-renders itself as the roster changes is not a record.

The consequence to accept: a decider who has since been renamed appears under their old name, and a page cannot link a decision to a current roster entry. Attaching a stable person reference to a decision would be a change to the write path, which this change explicitly does not touch.

### Decision 7 — Step names come from one playbook read, and their absence never fails the page

The stored row carries `step_id` and nothing else, so rendering `lp.listing.007` is what the data alone supports. The served playbook is read once for the page and used to name the steps it defines.

Two failure modes are treated identically and deliberately: a step the playbook no longer defines — which is exactly the circumstance that voids a result, so it is expected rather than exceptional — and a playbook that cannot be read at all. Both fall back to the raw identifier. The record is the page's reason to exist; a name is an improvement on it, and an improvement that can fail the page is a worse page.

### Decision 8 — The record's boundary is stated on the page, not left to be inferred

Only a terminal proposal on a step whose confirmation flag is true is retained. Everything else — every non-terminal outcome, and every terminal outcome on a step needing no confirmation — is recorded against the launch and never reaches this table.

A page headed "what was produced for this product" would therefore be wrong, and wrong invisibly: nothing on it would reveal the omission, and the omission would be total for a product whose automated steps all need no confirmation. The page names the record for what it is — the results retained for a decision — which costs a line of prose and removes a class of misreading.

### Decision 9 — The capability is `product-dossier`, not `product-admin`

The one-capability-per-admin-surface shape (`playbook-admin`, `roster-admin`, and `launch-admin` when it lands) would suggest `product-admin`. Against it: this surface writes nothing, and `product-admin` standing beside `product-catalog` would read as the surface for editing products — which is the one thing it is not. The dossier is the substance and the index is the way in, so the capability is named for the dossier.

### Decision 10 — Presentation and the guard are taken, not rebuilt

Both pages load the shared stylesheet through `admin_assets`' `GET /admin/assets/{asset}` — the route `shared` owns and both existing surfaces reach on equal terms — and neither carries a page-local style block. Templates load through a `ChoiceLoader` over the module's own directory and `TEMPLATES_DIR`, as `playbook_admin.py` and `roster_admin.py` both do, so `_admin_header.html` stays one file.

The guard is `playbook_admin.py`'s `_require_admin` shape: a session cookie verified against an injected verifier, refusing with the app's own 404 whether the session is absent, expired, or belongs to a principal no longer admin-capable.

### Decision 11 — Rendering rules are fixed as literal markers, not as prose

Requirements that say a page "states" or "labels" something are not assertable, and the tests for this change are derived from the deltas by an author who does not read the implementation. Left as prose, the test author invents the wording and the implementer then matches a string neither of them chose deliberately — and on this page the highest-stakes rendering rule is precisely a label, since presenting a voided result as rejected attributes to a person a judgement they never made.

So the deltas fix literal markers: `result-pending` / `result-accepted` / `result-rejected` / `result-withdrawn` on an entry, `step-unnamed` on an entry falling back to its identifier, `not-recorded` on an absent catalog field, `retained-for-decision` on the record's container, `nothing-to-show` and `nothing-produced` for the two empty states, and `product-retired` on a retired index row. This is `playbook-admin`'s established discipline — it fixes `row-action`, `danger`, `just-created` and `write-failure-notice` for the same reason, and states it outright: the literal form is given "because it is the delta a test is derived from, and an intent is not assertable".

`result-withdrawn` deliberately does not match the stored `voided`: the marker names what the page says, and the store's vocabulary is not the page's.

Read-only is asserted the same way and negatively — no form, and no element carrying `row-action`. On a page with no actions, the absence of that marker is the entire claim.

### Decision 12 — The ordering tiebreak is asserted, not merely observed

A test that renders twice and compares will pass against an implementation with no tiebreak at all, because a database commonly returns equal keys in the same order twice. The scenarios therefore assert the *direction* — of two rows sharing `produced_at`, the higher row identifier comes first — and require it to hold whichever order the two were stored in, so insertion order cannot be what the assertion is reading.

## Risks / Trade-offs

**`_admin_header.html` is edited by both this change and `add-launch-tracking-pages`, in the same `{% if current == "playbook" %}` block** → A textual merge conflict is certain for whichever merges second. It is small and mechanical, but it must be resolved by hand rather than by taking one side: each change adds a distinct surface, and taking either side wholesale drops the other's. If `add-launch-tracking-pages` restructures the two-branch conditional into a loop, this change's entry should be folded into that shape rather than re-added as another branch.

**`vocabulary.css` is the second shared asset both changes edit** → Neither page may carry a page-local style block, and three rules are needed that no admin surface has needed yet: a retired index row set apart, an entry's state, and produced text whose line structure is preserved by styling rather than by markup. `add-launch-tracking-pages` requires its pages to *load* the same stylesheet, but its Impact list and tasks name only `_admin_header.html` and its own templates — it does not record the stylesheet as a file it edits. So a second conflict depends on what its implementation turns out to need, and is a possibility rather than the certainty the header's is. The discipline in task 6.4a holds either way: add rules, rewrite none.

**The archive-order constraint recorded at proposal time does not survive reading the served specifications** → Both header requirements already say the header names "the admin surfaces the session can reach"; only the trailing "and from it the *other* page SHALL be reachable in one action" clause is pair-specific, and `product-dossier` carries the index's reachability obligation itself. So a header naming the index satisfies both requirements as they stand, in either archive order, with no delta. The residual hazard is writing a `MODIFIED` header block here at all — which would replace the generalized wording if this change archived second — and that is guarded unconditionally by a task rather than by an ordering. No fallback is needed because no ordering is needed.

**The retained record can only be non-empty where a launch position exists**, since `automated_step_results.product_id` is a foreign key to `launch_positions` → Not a defect, but it makes one specified scenario empty by construction: a product that never launched renders its identity and the explicit "nothing has been produced" statement, never a populated record. The page is still worth serving for it — the identity half is real, and the product may launch later — but no test should expect otherwise.

**The same foreign key cascades on delete** → Nothing in the repository deletes a `LaunchPosition` today; `_update` deletes and re-adds only `LaunchStepProgress`, `LaunchGateApproval` and `LaunchMetricAttestation`. The retention this change specifies is therefore true in practice, but it is guaranteed by nothing deleting launch positions rather than by the schema. Anything that later deletes one silently destroys the compliance-adjacent record this page exists to surface, and would need to reckon with that.

**Neither page paginates** → `roster-admin` already accepts this for the roster ("on one page without pagination"), and the catalog is of comparable size today. The retained record is the one that grows without bound: it accumulates one row per confirmable automated step per product, for the life of the product. Nothing needs doing now, but the first product to accumulate an uncomfortable page is the signal, not a number chosen in advance.

**Produced text is attacker-influenced in principle** — it is model output stored verbatim → Rendered through Jinja's autoescaping with line structure preserved by styling rather than by markup, so it cannot introduce markup into the page. This is the same text already posted to Slack for the decision; the page is not a new trust boundary, only a second reader.

## Migration Plan

None. No schema change, no migration, no configuration variable, no change to any stored shape or write path. The change reaches the server the way every change does — a branch, a pull request, the archive as the last commit before the merge — and with no ordering constraint at all; see *Risks* for why the one recorded at proposal time did not survive reading the served specifications.

Rollback is reverting the merge: the added routes disappear, and nothing else was touched.

## Open Questions

- Whether a launch row should link to a product's dossier once `add-launch-tracking-pages` has landed. It is a one-line addition to that change's template and a requirement on `launch-admin`, and it belongs to whichever change owns that page after both are merged. Nothing here depends on the answer.
- Whether the index later grows a SKU or name filter. The narrowing discipline `playbook-admin` established — narrowing changes what is shown, never what is enumerated — is the shape to follow if it does.
