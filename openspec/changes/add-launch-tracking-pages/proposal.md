## Why

The system holds a complete picture of every launch and shows it to
nobody. `read_launches` already returns, per launch, the current gate, the
launch date, every served step's recorded outcome with its provenance,
each step's due period, discipline and blocking flag, the overdue
judgement its hazard decides, the at-risk evaluation and whether the
current gate is held open only by a human decision. Two consumers read
it: the daily briefing, and nothing else.

Neither existing surface answers "which products are launching, where is
each one, and what is done".

- **ClickUp holds tasks, not gates.** The projection gives a launch a
  list and a step a task. The gate sequence, the blocking conditions
  attached to each gate, the at-risk derivation and the
  awaiting-confirmation state are facts the launch aggregate computes and
  ClickUp has no shape for.
- **The briefing reports only exceptions,** and `briefing`'s own spec
  makes a clean briefing send nothing at all. A launch progressing
  normally is invisible by design — correct for a digest, useless for
  "where are we".
- **The admin has surfaces for the playbook and the roster** — the two
  things that *configure* launches — and none for the launches
  themselves.

## What Changes

- **A launches list** at `/admin/launches`: every launch position the
  caller's scope permits, one row each — product, current gate, launch
  date, at-risk, awaiting-confirmation, and opening that launch's detail
  page in one action. Ordered by attention (at-risk, then
  awaiting-confirmation, then the rest) rather than alphabetically.
- **The list enumerates every launch and does not render the finished
  ones by default.** A launch whose product is steady-state or retired
  leaves the default view and stays reachable through an explicit
  control that marks it: the predicate is `briefing`'s for a launch no
  longer active, the shape is `playbook-admin`'s for retired steps. A launch
  waiting at `graduated` for its approval still shows, because the
  product is stamped steady-state only *after* that advance persists;
  one whose product the catalog cannot resolve shows too, failing toward
  visibility. Nothing is dropped from the enumeration: narrowing changes
  what is *shown* without changing what is enumerated, the discipline
  `playbook-admin`'s narrowing requirement established.

  `launch-instance` enumerates without a lifecycle filter because the
  launch context does not own a product's stage — and directs whoever
  consumes the enumeration to filter by the catalog's stamp. This surface
  is that consumer, and already reads the stamp.
- **A launch detail page** at `/admin/launches/{product_id}`: the gate
  sequence with the launch's position in it, and every served step —
  grouped by gate — with its name, outcome, provenance, discipline, due
  period, blocking flag and overdue judgement. It also renders the
  launch's journal, which `add-launch-journal` provides.
- **The report carries each step's gate, names the gate sequence, holds
  one entry per served step whether or not an outcome was recorded, and
  hands those entries over in the served playbook's order** — gate
  sequence order, then each gate's authored order. Only the first two are
  new behaviour; the rest are relied on today with nothing requiring
  them. Without the set, the detail page's grouping and its within-gate
  order would have to come from a playbook read, which is the arrangement
  the report's own governing principle exists to prevent, and
  `launch-playbook` separately obliges every consumer that lists a gate's
  steps to follow that order.
- **`ReportedStep` grows a `name`,** and two facts the report already
  carries with no requirement behind them — whether a step blocks, and
  whether it is overdue — gain one each. The overdue judgement is the
  load-bearing of the two: `briefing` already derives a monitor item from
  an overdue non-blocking step, so a shipped capability depends on a fact
  nothing requires, and this page's most useful column would otherwise
  rest on the same nothing. The report holds
  `step_id` today, so a page renders `lp.listing.007`. The precedent is
  settled: `docs/domain-map.md` records that slice 5 "grew `LaunchReport`
  accordingly instead of giving briefing a playbook reader".
- **A refusal is absence-shaped and turns on the launch position.** A
  detail page for a launch that does not exist, for one the caller's
  scope forbids, and for an identifier naming nothing are refused
  identically, in the shape of a route that does not exist — telling them
  apart would confirm the existence of a launch the caller may not see.
  It turns on the launch position and never on whether the catalog can
  name the product, so a launch the list renders by raw identifier opens
  rather than dead-ends.
- **Read-only.** Approving a gate, accepting an automated result and
  moving a launch date keep their existing Slack paths. Every use case
  they need is already exported, so adding them later is additive; doing
  it here would settle interaction questions before anyone has used the
  pages.
- The admin header gains the third surface, on **both** existing
  capabilities that specify one.

No **BREAKING** changes. Nothing existing is removed, no route changes,
no write behaviour changes, and no migration. `ReportedStep` gains a
field; every current construction site is inside `launch.application`.

## Capabilities

### New Capabilities

- `launch-admin`: the two launch-tracking pages — what the list
  enumerates and how it is ordered, what the detail page renders, how
  narrowing behaves, where the pages' presentation comes from, and that
  both are read-only. Named to sit beside `playbook-admin` and
  `roster-admin`, which follow the same one-capability-per-admin-surface
  shape.

### Modified Capabilities

- `launch-instance`: `ReportedStep` carries the step's `name` alongside
  its identifier, so a consumer of the report can render a step without a
  playbook reader; and two facts it already carries that no requirement
  demands — whether a step blocks, and whether it is overdue as of the
  evaluation date — each gain one. The overdue requirement covers
  blocking and non-blocking steps alike and holds whether or not the
  launch is at risk, which is what the existing at-risk requirement does
  not do. A fourth requirement places each step in its gate and names the
  gate sequence, neither of which the report carries today.
- `roster-admin`: its requirement *The page carries a header from which
  the other admin surface is reachable* is written for exactly two
  surfaces. A third makes that wording false rather than merely
  incomplete, so it generalizes to the admin surfaces the session can
  reach.
- `playbook-admin`: its requirement of the same name, worded for the same
  two surfaces, generalizes identically. Both are modified or neither:
  generalizing one alone would leave the launch surface reachable from
  the roster and not from the step list, which is the asymmetry the
  generalization exists to close.

`admin-session` is deliberately **not** modified: the new pages ride the
existing guard unchanged and refuse identically. `playbook-authoring`,
`launch-playbook` and `launch-clickup-sync` are untouched — nothing here
changes what a write accepts, what the playbook serves, or what reaches
ClickUp.

## Impact

**Affected code**

- `launch/application/use_cases.py` — `ReportedStep.name` and its gate,
  both populated from the step definition `_report_for` already iterates,
  and the gate sequence named on the report from the playbook it already
  holds. Per-served-step coverage and the entries' served order need no
  code either: `_report_for` iterates the served step set, which is
  already ordered by gate then authored slot. The blocking flag and the overdue judgement need no code: the
  report carries them today, and their requirements close spec gaps
  rather than produce behaviour.
- `launch/infrastructure/driving/launch_admin.py` — new; the two routes,
  their guard and their read model, shaped after `playbook_admin.py`.
- `launch/infrastructure/driving/templates/` — the two page templates.
- `shared/infrastructure/driving/templates/_admin_header.html` — the
  third surface.
- `.importlinter` — **conditionally**. The new adapter calls
  `catalog.application` from `launch.infrastructure`, which the
  `products-infrastructure-boundary` contract is believed to permit
  already, since it forbids `catalog.domain` and `catalog.infrastructure`
  and not the public surface. A task confirms this before the adapter is
  written; if the belief is wrong, an exemption in the shape the contract
  already carries for `access` is added here.

**Explicitly untouched**

`launch/domain/` — nothing here reaches the domain layer. The ClickUp
projection and its webhook intake; the automation pass and its
confirmation path; every authoring write; every stored shape. This change
adds one field to a read and renders what already exists.

**Coordination**

- **`add-launch-journal` is a prerequisite.** The detail page renders the
  journal that change adds, and this change's requirement to do so is
  written against the read it provides. Nothing else here depends on it,
  so the two are reviewable separately, but the detail page cannot be
  implemented until it lands — **and this change SHALL NOT archive before
  it**. Archiving is the last commit before a merge here, so archiving
  first would fold R5 into `openspec/specs/` naming a capability that has
  no spec, which `openspec validate` would not object to. The journal was split out of this change on
  review: it changes the write path of every accepted launch command,
  while these pages cannot break a live launch, and the two risks
  deserved separate review.
- **`add-product-dossier-page` SHALL NOT carry a `roster-admin` or a
  `playbook-admin` header delta.** It proposes the product page this
  change's list rows link to. Once this change archives, both header
  requirements already oblige the header to name **every** surface the
  session can reach, so that change needs no delta of its own — and a
  delta written against the pre-generalization text would silently
  replace the generalized wording on archive, which `openspec validate`
  would not object to.
