## Why

Part of the launch playbook does not *check* work — it *produces* it. An
automated step runs a handler and returns a `StepResolution` whose
`result` is the thing it made: today the sub-category advisor's node
recommendation and the compliance fields that node demands, and by
design more to come, since `automation_brief` and `handler` are authored
fields on every step.

That produced content is retained and then goes dark.

- **It is stored, permanently.** `automated_step_results` holds
  `result_text` for every result, and its docstring is explicit —
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
- The admin header gains this surface.

No **BREAKING** changes: no existing route, write or stored shape
changes. One read is added to the automated-result repository.

## Capabilities

### New Capabilities

- `product-dossier`: the product page — what it renders of the catalog's
  product, what it renders of the produced record and in what order, how
  a `voided` result is distinguished from a `rejected` one, that it is
  addressable for a product with no launch, and that it is read-only.

### Modified Capabilities

- `launch-step-automation`: the retained results become readable as a
  product's accumulated record, not only as a pending decision awaiting
  one. The spec today describes retention as a property of the decision
  flow; this states that what is retained is legible afterwards, which is
  what makes "settled rows are kept, never deleted" worth more than
  storage.
This change carries **no** `roster-admin` or `playbook-admin` delta, and
that is deliberate rather than an omission. Both capabilities' header
requirements are generalized by `add-launch-tracking-pages` to name every
admin surface the session can reach, so once that change archives this
page is already covered and needs no requirement of its own. Writing one
here would be actively harmful: an OpenSpec `MODIFIED` block replaces a
requirement wholesale, so a delta drafted against the pre-generalization
text would silently delete the generalized wording on archive, and
`openspec validate` would not object.

`product-catalog` is deliberately **not** modified: the page reads
`get_product_by_id` through the catalog's public surface and asks it for
nothing it does not already answer. `launch-instance` is untouched — a
dossier is not a launch report.

## Impact

**Affected code**

- `launch/infrastructure/driven/automated_results.py` — one read
  returning every retained result for a product, ordered newest first.
- `launch/application/` — the use case exposing that read behind the
  module's public surface, with the caller's `AccessScope` applied as
  every other product-keyed read applies it.
- A new driving adapter and template for the page, shaped after
  `playbook_admin.py` and riding the same admin-session guard.
- `shared/infrastructure/driving/templates/_admin_header.html` — the
  new surface.

**Explicitly untouched**

The automation pass, the confirmation flow, the decision use cases, and
every stored shape. This change reads what already exists.

**Open, to settle in design**

Whether the page is reachable by SKU as well as by product id. The Slack
paths and the catalog both address products by SKU in practice, and an
admin looking a product up knows its SKU rather than its generated
identifier — but `get_product_by_sku` is a second read with its own
scope check, and the launch list links by id regardless.

**Coordination**

`add-launch-tracking-pages` proposes the launch list and detail pages,
whose rows link here, and it owns the admin header's generalization for
both capabilities that specify one — see *Modified Capabilities* for why
this change carries no header delta of its own.

**This change SHALL NOT archive before it.** The header requirements this
page relies on are generalized there; archiving first would leave this
surface named by a header requirement still written for two surfaces.
Neither change blocks the other for review or implementation: this page
is addressable and useful without the launch pages existing, and its own
requirements stand alone.
