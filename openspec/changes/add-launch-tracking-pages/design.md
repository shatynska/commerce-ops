## Context

See `proposal.md` — Why. The constraints that shape the approach, none of
them new to this change:

- **The read already exists and is complete.** `read_launches` /
  `read_launch` return everything the pages render except the product's
  own identity and the journal. No new launch query is needed.
- **The journal is another change's.** `add-launch-journal` adds the
  record and the read; this design treats both as given and decides only
  how the detail page renders them.
- **The step set is large.** `seed_playbook` inserts 352 rows, and
  `add-step-page` recorded that a list of 105 steps ran "roughly twenty
  screens". Whatever subset is `active`, a detail page rendering every
  served step is a long page by default rather than by accident.
- **`launch.infrastructure` may already call `catalog.application`.** The
  `products-infrastructure-boundary` contract forbids `catalog.domain`
  and `catalog.infrastructure` and does not forbid its public surface, so
  no `.importlinter` edit is required. *(Unverified against the source in
  this design; a task confirms it before the adapter is written.)*
- **Every admin-capable principal resolves to an unrestricted scope
  today** (`access-scope`). Product-level differentiation is deliberately
  absent, which shapes Decision 3.

## Goals / Non-Goals

**Goals**

- Pages whose data shaping is separable from their markup.
- A surface that is honest about what it cannot resolve rather than
  quietly shorter.

**Non-Goals**

- The journal itself — its storage, its append sites, its containment.
  All of it belongs to `add-launch-journal`.
- Any write path. Covered by the specs; named here only because the
  read-model decision below would otherwise look like the first half of
  an API.
- Retention, pagination. See Open Questions.

## Decisions

### 1. Product identity comes from the catalog, and a failed lookup shows the row anyway

The list renders SKU and name, which `LaunchReport` does not carry. It
resolves them through `catalog.application`'s `list_products` — one read
for the whole page rather than one per row — and joins by product id.

A read that fails **entirely** renders every row by its raw product id
rather than failing the page, and a launch whose individual product the
catalog does not resolve **is still rendered**, identified the same way.
The wholesale case is stated because it is the larger one: an outage
taking the catalog read down is exactly when someone opens this page. This copies `briefing`'s rule
deliberately: "a product the catalog cannot resolve is treated as active
and identified by its raw id — losing an item to a failed name lookup is
exactly the silent failure the briefing exists to prevent." A tracking
surface that dropped a launch because a join missed would be lying about
what is in launch, which is the one thing it is for.

The detail page resolves its single product through `get_product_by_id`,
under the same rule — and `launch-admin` R4 now carries that rule as a
requirement rather than leaving it here. It had to: R7 refuses a detail
page for an identifier naming nothing, and with the list now offering
every row's detail page in one action, an unresolvable row would have led
to a refusal in one click. R7 turns on the launch position instead.

### 2. The pages get a typed read model, and it is not `dict[str, Any]`

Between the use cases and the templates sits a small set of frozen
dataclasses — one per rendered thing (a list row, a detail page, a step
line, a journal line) — constructed in the driving module and iterated by
the templates.

This is the seam `docs/deferred-work.md` names under *The admin stays
server-rendered, in this repository*: "no read-model layer exists between
the use cases and the templates ... naming that layer as typed frozen
dataclasses when the next admin surface is built is better structure on
its own terms". This is that next surface.

It is adopted here for its own sake, not as API preparation.
`playbook_admin.py` is 1403 lines because shaping and rendering are not
separable in it, and its `_row(record, people) -> dict[str, Any]` is
untyped enough that mypy cannot check what the template then reads. A new
surface repeating that shape would double the problem rather than contain
it. That the same dataclasses would serialize cleanly if an API ever
arrives is a consequence, and explicitly not a reason to build one.

It also earns its place immediately here: the journal's entries carry a
`kind` and a schemaless detail, so composing an entry's rendering in one
typed place per kind is what makes a missing key fail where it can be
seen rather than render blank in a template.

### 3. The pages read under the session principal's resolved scope, never a scope they choose

The routes resolve an `AccessScope` from the session's principal identity
and pass it to every read.

The distinction is invisible today and will not stay so. `access-scope`
resolves every active roster member to an unrestricted scope, so passing
the unrestricted constant directly would satisfy every scenario in the
delta — and would silently stop being correct the moment product-level
scoping arrives, with no test failing. The spec states the provenance for
this reason, and this decision records that the implementation must
follow it rather than take the observationally identical shortcut.

A consequence for the task breakdown: the restricted-scope scenario in
`launch-admin` R1 and the forbidden-launch scenario in R7 are not
reachable end to end today. They are covered
**at the adapter**, against a scope resolver stubbed to return a
restricted scope with the real enumeration behind it, asserting the rows
actually rendered — not merely that the route passed the scope on, which
would establish less than the scenario states. Covering them at the use-case level instead would test the wrong
thing: the use case already filters correctly, and the defect this guards
against is an adapter that supplies its own scope.

### 4. `ReportedStep.name` is read straight from the step definition

`_report_for` already iterates `playbook.served_steps`, whose entries are
`StepDefinition`s carrying `name`. The field is populated there. No query
changes, no join, no second read — which is why this is a decision
recorded rather than a task with alternatives.

The blocking flag and the overdue judgement need no code at all:
`ReportedStep` already carries both. Their delta requirements close spec
gaps, not implementation ones, and their tasks are tests that pin the
behaviour rather than changes that produce it. The overdue one is the
sharper of the two: `briefing` already derives a monitor item from an
overdue non-blocking step, so that fact has been load-bearing for a
shipped capability with nothing requiring it.

### 5. Finished launches leave the default view rather than the enumeration

The stage the filter reads is already on the `list_products` result
Decision 1 fetches — `product-catalog` requires that read to carry each
product's current lifecycle stage — so this costs no extra query.

The shape is `playbook-admin`'s, not an invention: retired steps are
absent from its default view and reachable through an explicit control.
Applying it here keeps `launch-admin` R3's rule intact — the enumeration
stays whole and only the rendering narrows — and it keeps
`launch-instance`'s enumeration contract intact too, which does not
forbid filtering but directs the *consumer* to filter by the catalog's
stamp. This surface is that consumer.

An earlier draft forbade the filter outright, quoting `launch-instance`'s
reasoning for why the launch context cannot filter as though it were a
reason the page cannot. It is not: the page has the stamp and the launch
context does not, which is precisely why that sentence hands the job
here. The draft's protected case survives the filter anyway — graduation
stamps steady-state only after the advance persists, so a launch awaiting
its approval still has a launching product.

### 6. Everything the pages render comes from the report, grouping included

`ReportedStep` carries no gate today, and `GATE_SEQUENCE` is not on
`launch.application`'s public surface — so the gate grouping the next
decision argues for was, as first written, implementable only by reading
the playbook or the domain's gate framework from the page.

Both are refused, though the reason needs stating carefully: this page
lives at `launch/infrastructure/driving/`, **inside** the launch module,
so "re-derived outside the launch context" — the phrasing the other three
requirements lean on — does not describe it. What holds instead is that
the report is the launch context's answer for every consumer, and a fact
this page could reach around for is one `briefing` or any later consumer
could not. Adding `name`, `blocking` and `overdue` to the report and then
reaching past it for the gate would have put the exception in the one
place nobody checked.

So the report carries the step's gate, and names the gate sequence in
order. The sequence travels rather than being looked up because a
consumer that had to find it needs the gate *framework*, not merely the
step set — a heavier dependency than the one already refused, and one
carrying the order as well as the names.

### 7. Both pages evaluate as of the day they are rendered, and the read already allows it

`launch-admin` R1 and R4 both require the date-derived facts to be
evaluated as of the render date. `launch-instance` attaches a
caller-supplied evaluation date to its enumeration requirement and not to
its single-launch read, so the obligation could have rested on nothing —
the failure mode this change has closed four times over.

It does not: `read_launch` already takes `as_of: date` alongside the
product id and the scope, exactly as `read_launches` does. So the
requirement is satisfiable today, and what remains is a task that passes
the render date rather than a default. Recorded here rather than added to
the `launch-instance` delta because it is a property of the read's
signature, not of what the report carries — the four added requirements
are all about the latter.

### 8. One driving module, shaped after `playbook_admin`

`launch/infrastructure/driving/launch_admin.py` holds both routes, the
admin guard, and the narrowing read, following the conventions
`playbook_admin.py` established — narrowing carried in query parameters,
`hx-boost` inherited from `<body>`, the shared header and stylesheet
through the existing `ChoiceLoader`.

**The detail page groups steps by gate, in gate order**, rather than
rendering one flat list. With 352 seeded steps the flat form is unusable
regardless of how many are `active`, and the gate grouping is the
structure the page is already showing at the top. The current gate's
group is the page's anchor target, so opening a launch lands on where it
actually stands.

### 9. The header partial is edited once and three capabilities are satisfied by it

`_admin_header.html` is one shared partial, so naming the third surface
is a single edit. What is not single is the specification: `roster-admin`
and `playbook-admin` each carry their own header requirement, worded for
two surfaces, and both are generalized here.

Generalizing one alone was considered and is wrong in a way worth
recording: it would leave the launch surface reachable from the roster
page and not from the step list, the edit surface or the create surface —
the exact asymmetry the generalization exists to close, and one that a
test derived strictly from a single delta would not catch.

## Risks / Trade-offs

**A recorded outcome for a step that has left the served set is not
shown** → The report is built from served steps, so those outcomes are
outside what this surface can read. `launch-admin` R4 states the boundary
rather than leaving it to be discovered, and closing it would mean a
second read, which is its own change.

**The detail page is long even grouped** → Grouping by gate and anchoring
on the current one is what this design buys; it does not make the page
short. Narrowing on the detail page was considered and rejected as scope:
the list is where narrowing belongs, and a second narrowing vocabulary on
a second page is a cost this change does not need to pay to be useful.

**`list_products` reads the whole catalog to render one page** → One read
rather than one per row, which is the point, but it does not scale with a
catalog much larger than the launch set. Acceptable while products in
launch and products in the catalog are the same order of magnitude;
revisit with pagination, not before.

**A raw-id row is ugly** → Deliberately. Decision 1 trades appearance for
never silently shortening the list, and the specs require the row rather
than permitting it.

**The read model is one more layer to keep in step** → Accepted, and the
alternative is what `playbook_admin.py` became.

## Migration Plan

**None.** No schema changes, no data changes, no backfill. `ReportedStep`
gains a field whose only consumers this change adds; the routes are new,
so removing them removes nothing that existed before. Rollback is
reverting the commit.

The one ordering constraint is not a migration: the detail page's journal
section cannot be implemented before `add-launch-journal` lands.

## Open Questions

- **Whether the list paginates.** Decision 5 is what makes this
  deferrable: the default view holds launches in flight rather than every
  launch ever run, so it is bounded by how much is in play at once rather
  than growing monotonically. The finished-launch view is the one that
  grows without limit, and it is the one nobody opens daily. Answering
  this later changes nothing decided here.
- **Whether the detail page should narrow.** Named as a risk above and
  deferred; answering it later changes neither the specs nor the shape of
  what is built now.
