## Why

`lp.strategy.006` screens a product against the prohibited and high-compliance
categories its own description names, and since `screen-a-product-for-compliance` it
does so honestly: three verdicts, a structured discriminant, and reasons that say which
of three different things happened. What it produces reaches exactly two places — the
launch's `evidence` text and the Slack message a member decides on — and both are prose
addressed to a person.

Nothing keeps the fact.

That has two costs, and they are the reason for this change rather than a refinement of
the last one:

- **The screen's answer dies with the launch.** A launch is a temporary state over a
  continuously observed product. When it graduates, the record that this product was
  screened, and against what, is a paragraph inside a step recording on a launch nobody
  opens again. The product itself carries nothing. A second launch for the same product
  re-screens from nothing, and a buyer asking "has this been screened?" has no field to
  read.
- **"Clear" and "not screened" are the same absence.** This is the sharper one. A
  product nothing has ever screened and a product screened and found clear are the same
  blank today, and they are opposite facts: one is an open question, the other is an
  answered one. Every future step that would branch on compliance — a sourcing gate, a
  supplier brief, a hazmat shipping flag — needs to tell them apart, and none can.

`separate-the-result-from-the-comment` built the mechanism that carries a typed finding
from a handler to a product and onto the recording it produced. It shipped with one sink
registered, for `lp.listing.007`. This change is the second sink, and the first one whose
value is not a scalar — which is what makes it worth doing now rather than later, while
the mechanism's author's reasoning is still legible in the specs.

`screen-a-product-for-compliance` deliberately closed the door this change opens, and
said so in the requirement it wrote: *the screen SHALL report no typed finding … nothing
downstream reads a compliance verdict from a product today, and reporting a finding no
sink accepts would record nothing while implying something was recorded.* Both halves of
that reason are about to stop being true. This change is that requirement's stated
successor, not a reversal of it.

## What Changes

- **A product carries the hazard categories it was screened against, in three states.**
  Never screened, screened and clear, and screened and flagged are three distinguishable
  facts on the product, not two. The middle one is the whole point: it is the state that
  does not exist today and the state every consumer of this field will branch on.

- **The screen reports what it found as a typed finding, on the two routes that
  establish something.** `clear` establishes that the product falls in none of the named
  categories — an empty finding, which `launch-instance` already admits one spelling of.
  `flagged`, **naming at least one category**, establishes which categories it falls in.
  `undetermined`, an unreadable response, a blank comment, either self-contradiction, a
  flagged verdict naming no category, an absent product and a step naming no categories
  all establish nothing about the product and SHALL report no finding at all — leaving
  what the product already carries untouched, including a prior flag.

- **The wire schema gains a categories field, and two structural contradictions come
  with it.** The model answers with a verdict *and* the categories it is answering about.
  The schema requirement governing that wire is not itself changed — see *Modified
  Capabilities* below for why adding a field does not modify it.
  A `flagged` verdict naming no category, and a `clear` verdict naming one, are responses
  that contradict themselves in the same way `screen-a-product-for-compliance`'s
  comment-veto catches — but structurally, so no prose is inspected to find them. Each
  gets its own withheld reason, because this capability already requires that three
  different things that happened read as three different sentences.

- **The categories are named as the step's description names them, and this is a
  prompting obligation that no code enforces.** The model is instructed to reuse the
  description's own wording; nothing parses the description to check that it did.
  `screen-a-product-for-compliance` refuses to extract anything from that prose and gives
  its reasons at length; this change does not start. The consequence — that the values
  are exactly as stable as the authored description, and that a category reached through
  a list the description *references* rather than enumerates has no wording to be
  verbatim to — is stated in the specification rather than left to be discovered.

- **The product dossier renders what a product's automated steps established about it.**
  The dossier renders identity and retained results and, today, no finding field at all —
  not even the sub-category `lp.listing.007` has been writing since
  `write-the-advisors-finding-to-the-product`, which `product-catalog` specifies a read
  for and which no surface has ever shown. Both are rendered, because rendering one of
  two finding-backed fields and not the other makes the next author guess which is the
  convention.

- **The launch's carrying of a finding is untouched; its rendering of one gains a
  clause.** `launch-instance` already carries a finding whose value is empty as distinct
  from a recording carrying none, and `launch-step-automation`'s whole finding mechanism
  is written without any constraint on a value's type. Both were written generically, on
  purpose, one change ago, and this change adds nothing to either. `launch-admin` was
  not: it fixes how a field, a wording, an **empty** value and the result/comment
  structure render, and says nothing about a value carrying several members. That was
  correct when the only finding was a string, and this change makes the first non-scalar
  one — so the requirement gains a clause stating that members render as members, each
  readable, in no programming language's notation for a collection, and that a string is
  one member rather than a sequence of characters.

- **`SubCategoryRecorder` is replaced by the port it was always standing in for.**
  `separate-the-result-from-the-comment` left it named and typed as it was, recording in
  its own tasks that *widening it belongs to the change that adds a second sink with a
  different value type*. This is that change.

### Non-goals

- **No new step, no new handler, and no change to which step the screen resolves.**
  `lp.strategy.006` keeps its handler, its confirmer and its authored description.
- **No consumer of the new field.** Nothing branches on hazard categories yet. This
  change makes the fact available and readable; the sourcing gate or shipping flag that
  reads it is a later change, and inventing one here would be a requirement nobody asked
  for.
- **No reconciliation between a rejected proposal and the value already written.** The
  write is provisional by design, `launch-step-automation` says so, and it explicitly
  delegates what a written-then-rejected value means to `product-catalog`. This change
  answers that question in `product-catalog` and builds no reconciliation machinery.
- **No change to the finding mechanism itself.** No new hook, no accept-time sink
  invocation, no per-sink flag. The one mechanism-shaped edit is the port replacement
  above, which changes no behaviour.
- **No closed vocabulary of categories.** Rejected during exploration in favour of the
  authored description, for the reasons `design.md` records.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `compliance-screen`: the requirement *The screen reads only what it is given, and
  reports no finding* is split — what it says about reading only the context is
  unchanged and stays; what it says about reporting no finding is replaced by a
  requirement that the screen reports a typed finding on exactly the two routes that
  establish something about the product, and none on the routes that do not. The
  Two new structural contradictions join the comment-veto that already exists, each with
  its own reason, and the requirement that resolves a blank comment gains a stated
  precedence over both. The wire schema requirement itself is **not** modified: it
  already demands that acceptance be established by the provider's own conversion at the
  call site's schema, and that every combination the wire can express have a defined
  destination. Adding a field widens that combination space and changes nothing about
  what the requirement asks, so the new destinations are supplied by the contradiction
  requirements rather than by editing it (`design.md`, Decision 2).
- `product-catalog`: gains hazard categories as a recordable, three-state fact about a
  product — recorded independently of lifecycle stage as the sub-category already is,
  replaced wholesale by a later screening, reported back in a way that distinguishes
  never-screened from screened-and-clear, and explicitly provisional: a value written
  from a proposal a member later rejected stands, and this capability says why.
- `launch-admin`: the requirement governing how a carried finding's result renders gains
  a clause for a value carrying several members — every member rendered, each readable
  and separated, with none of a collection's programming notation around them — together
  with the clause that keeps a string from being rendered as its characters, and the
  statement that an empty value stays governed by the emptiness clause already there.
  Nothing else about that requirement changes.
- `product-dossier`: the dossier renders what the product's automated steps have
  established about it — its recorded sub-category and its hazard categories — with the
  three-state reading given its own literal marker, since the page's existing
  `not-recorded` marker covers only two states and collapsing "screened, nothing found"
  into it would erase exactly the distinction this change exists to create.

## Impact

- `alembic/versions/` — one migration adding a nullable `text[]` column to `products`.
  Parented on `b62d05f1ae37`, which is both the current single head and what production
  runs.
- `src/commerce_ops/catalog/domain/product.py` — the field on the aggregate and the
  recording method, shaped like `record_sub_category` and `record_asin`.
- `src/commerce_ops/catalog/infrastructure/driven/models.py`,
  `product_repository.py` — the column and its mapping.
- `src/commerce_ops/catalog/application/use_cases.py` — `record_hazard_categories`.
- `src/commerce_ops/step_handlers/strategy/compliance_screen.py` — the wire schema's new
  field, the two structural contradiction routes and their reasons, and the finding on
  the two routes that carry one.
- `src/commerce_ops/launch/application/ports.py`,
  `launch/application/__init__.py` — `SubCategoryRecorder` replaced; the public surface
  changes, so both the export list and `worker.py`'s reference to it move together.
- `src/commerce_ops/worker.py` — the second `FindingSink` registration, and the partial
  application satisfying it, beside the one that exists.
- `src/commerce_ops/launch/infrastructure/driving/launch_admin.py`,
  `templates/launch.html` — the value renderer already handles a sequence and a string
  correctly; what changes is that a requirement now says so, and a test derives from it.
- `src/commerce_ops/launch/infrastructure/driving/product_dossier.py`,
  `templates/product.html` — the rendered fields.
- `src/commerce_ops/shared/infrastructure/driving/static/vocabulary.css` — the marker
  the new state's rendering carries, added where the page's other markers live rather
  than as page-local styling, which `product-dossier` forbids.
