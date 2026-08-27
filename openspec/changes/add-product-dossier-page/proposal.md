## Why

Part of the launch playbook does not *check* work — it *produces* it. An
automated step runs a handler and returns a `StepResolution` whose
`result` is the thing it made: today the sub-category advisor's node
recommendation and the compliance fields that node demands, and by
design more to come, since `automation_brief` and `handler` are authored
fields on every step.

That produced content is retained and then goes dark.

- **It is stored, permanently.** `automated_step_results` holds
  `result_text` for every result that was *held for a decision* — a
  terminal proposal on a step whose confirmation flag is true, the only
  kind that reaches the table — and its docstring is explicit —
  "Settled rows are kept, never deleted ... what a person accepted, and
  when, is the record of a compliance-adjacent decision."
- **It is readable exactly once.** `automation_confirmation.py` posts it
  to Slack for an accept-or-reject decision. After that decision nothing
  surfaces it again: the repository offers `pending_for`, `by_id`,
  `undelivered` and `latest_rejection` — every read serving the decision
  loop, none serving "what has this product accumulated".
- **The recording keeps only the latest.** An accepted result becomes the
  `evidence` on `launch_step_progress`, which is keyed
  `(product_id, step_id)` and replaced on the next recording.

So the answer to "what did we generate for this product, and what did we
accept" exists in the database and is reachable only by SQL.

**It belongs to the product, not to the launch.** `docs/domain-map.md`
is unambiguous: "Launch is a *temporary product state* ... an overlay on
one continuously observed product, not a stage before observation
begins." A gate timeline ends at graduation; a sub-category choice and a
compliance field list stay true afterwards, and monitoring's observations
will attach to the same object at slice 7. A dossier hung off the launch
would be a permanent record on a temporary page.

## What Changes

- **A product page** at `/admin/products/{product_id}`, carrying two
  things: the product as the catalog knows it — SKU, name, marketplace,
  ASIN, lifecycle stage, when it entered that stage and who confirmed it
  — and everything produced about it.
- **The produced record, newest first**: every retained result, each with
  the step and handler that produced it, the outcome proposed, when it
  was produced, what became of it (`pending`, `accepted`, `rejected`,
  `voided`) and who decided and when. A `voided` entry stays visible and
  is labelled as voided rather than as rejected — `models.py` records why
  the two are distinct states, and collapsing them on a page would
  misattribute a refused decision to the person who made it.
- **The page exists for a product with no launch**, and for one that has
  graduated. It is addressed by product, so it neither appears nor
  disappears with a launch position — which is the whole reason it is
  its own page.
- **Read-only.** Accepting and rejecting keep their Slack path.
- The result text renders as text. `handler_contract.py` records the
  decision that `StepResolution.result` is "plain text rather than a
  structure because both its consumers want text", and this change does
  not reopen it — it renders honestly what is stored rather than
  inventing structure the producers never wrote.
- **A product index** at `/admin/products`, listing every product the
  caller's scope permits — SKU, name and lifecycle stage, which is what
  `list_products` already answers — each row opening that product's
  dossier. Retired products are set apart rather than interleaved, the
  shape `roster-admin` established for deactivated people.

  It exists because the dossier alone cannot be reached. The header names
  the surfaces the session can reach *in one action*, and
  `/admin/products/{product_id}` has no id-less form to name; nothing else
  in the repository links here either. Shipping the dossier without an
  index would reproduce exactly the defect `roster-admin`'s header
  requirement was written to close — a page reachable only by someone who
  already knows its URL.
- **The admin header gains the product index**, which is the surface it
  can name. The dossier itself is not a header entry: it is a page about
  one product, reached from the index, and it carries the header as every
  other admin page does.

No **BREAKING** changes: no existing route, write or stored shape
changes. One read is added to the automated-result repository.

## Capabilities

### New Capabilities

- `product-dossier`: the two product surfaces — what the index
  enumerates and how it is ordered; and, for the dossier itself, what it
  renders of the catalog's product, what it renders of the produced
  record and in what order, how a `voided` result is distinguished from a
  `rejected` one, what the record does **not** cover, that it is
  addressable for a product with no launch, and that both are read-only.

  Named for the dossier rather than `product-admin`, which the
  one-capability-per-admin-surface shape would otherwise suggest: this
  surface edits nothing, and `product-admin` sitting beside
  `product-catalog` would read as the surface for editing products, which
  it is emphatically not.

### Modified Capabilities

- `launch-step-automation`: the retained results become readable as a
  product's accumulated record, not only as a pending decision awaiting
  one. The spec today describes retention as a property of the decision
  flow; this states that what is retained is legible afterwards, which is
  what makes "settled rows are kept, never deleted" worth more than
  storage.

This change carries **no** `roster-admin` or `playbook-admin` delta, and
that is deliberate rather than an omission. Both capabilities' header
requirements *already* oblige the header to name "the admin surfaces the
session can reach" — that clause is in force today, not something
`add-launch-tracking-pages` introduces. What that change generalizes is
the trailing clause each requirement carries naming the *other* page as
reachable in one action, which is pair-specific and which this change does
not rely on: `product-dossier` states the index's reachability itself.

So a header naming the product index satisfies both requirements as they
stand. Writing a delta here would be actively harmful and never necessary:
an OpenSpec `MODIFIED` block replaces a requirement wholesale, so one
drafted here would silently delete wording it did not intend to touch —
the generalized clause if written before that change lands, or that
change's own additions if written after — and `openspec validate` would
not object.

`product-catalog` is deliberately **not** modified: both pages read
`get_product_by_id` and `list_products` through the catalog's public
surface and ask them for nothing they do not already answer. The index
renders three of the four things `list_products` is required to answer;
the fourth, the product identifier, is the row's link target rather than
a column.

One dossier field deserved checking rather than inferring, because
`product-catalog`'s read requirement enumerates "identity, name, current
stage, and stage-entry time" and does not name the **stage confirmer**.
It is answered: `get_product_by_id` returns the `Product` aggregate, which
carries `stage_confirmed_by` — `None` for a product still in
`Development`, which is why the page states its absence rather than
leaving it blank. No `product-catalog` delta is needed. `launch-instance` is untouched — a
dossier is not a launch report.

## Impact

**Affected code**

- `launch/infrastructure/driven/automated_results.py` — one read
  returning every retained result for a product, ordered newest first.
- `launch/application/` — the use case exposing that read behind the
  module's public surface, with the caller's `AccessScope` applied as
  every other product-keyed read applies it.
- A new driving adapter and two templates — the index and the dossier —
  shaped after `playbook_admin.py` and riding the same admin-session
  guard. It reads `list_products` and `get_product_by_id` through
  `catalog.application`; `.importlinter`'s
  `products-infrastructure-boundary` already permits that edge, forbidding
  `catalog.domain` and `catalog.infrastructure` and not the public
  surface, so no contract changes.
- `shared/infrastructure/driving/templates/_admin_header.html` — the
  new surface.
- `shared/infrastructure/driving/static/vocabulary.css` — the shared admin
  vocabulary, which both pages load and neither may substitute with a
  page-local block. Three things need rules there that no admin surface
  has needed yet: a retired row set apart, an entry's state, and produced
  text rendered with its line structure preserved by styling rather than
  by markup.

**Explicitly untouched**

The automation pass, the confirmation flow, the decision use cases, and
every stored shape. This change reads what already exists.

**Settled since proposing**

The dossier is addressed by product id alone. `get_product_by_sku` exists
and is cheap, but a route accepting either must decide what an identifier
that could be both means, and that ambiguity becomes route semantics; an
admin who knows only a SKU is asking to *look a product up*, which is the
index's job rather than the address's.

**Coordination**

`add-launch-tracking-pages` proposes the launch list and detail pages,
and it owns the admin header's generalization for both capabilities that
specify one — see *Modified Capabilities* for why this change carries no
header delta of its own.

It does **not** *specify* a link from a launch row to this page: its
`launch-admin` delta requires each row to offer "that launch's detail page
in one action" and nothing further. Its prose says otherwise — it calls
this "the product page this change's list rows link to" — so the two
changes' records disagree, and it is the delta that was checked and the
delta that governs. A launch row linking here is therefore a later
change's business, and this change does not depend on one, which is the
second reason the index exists.

**This change may archive in either order, and carries no header delta in
either case.** The constraint recorded when this change was proposed was
stronger than the served specifications turn out to warrant, and re-reading
them settles it.

Both header requirements *already* oblige the header to name "the admin
surfaces the session can reach" — that clause is in force today, in
`roster-admin` and in `playbook-admin` alike. What is pair-specific in each
is only the trailing clause naming the *other* page as reachable in one
action, and the requirement titles. A header that also names the product
index therefore satisfies both requirements as they stand, with no delta,
today; and `product-dossier` carries the index's own reachability
obligation, with its own scenario, rather than borrowing one.

So there is nothing to sequence. Archiving first cannot delete the
generalized wording, because this change writes no `MODIFIED` block;
archiving second finds that wording already generalized and still needs
none. The hazard the original constraint guarded against — a block drafted
against pre-generalization text silently replacing the generalized wording
— is avoided by writing no such block **at all**, unconditionally, which is
what this change does and what its tasks check. Neither change blocks the
other for review, implementation or archive: this page is addressable and
useful without the launch pages existing, and its own requirements stand
alone.
