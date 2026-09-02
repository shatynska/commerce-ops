# Playbooks as a shared step library — transition plan

**Status: program plan.** This is the designed end state for the playbook
framework and the order the changes reaching it must be worked in. It is not a
specification: authoritative behaviour lives in `openspec/specs/`, and each
change below states its own requirements when it is proposed. Delete this file
when the last change in it is archived, per `docs/proposed-change-order.md`'s
rule.

Distinct from `docs/proposed-change-order.md`, which is a working queue of
seven already-proposed changes from one review. Nothing here is proposed yet.
Where the two touch the same code, see *Conflicts with the working queue*.

Decided in session on 2026-09-02, against `origin/main` at `30264a9`.

---

## What is wrong today

The system asserts at four levels that exactly one playbook exists and that it
*is* the launch:

| Assertion | Where |
|---|---|
| Steps carry no playbook reference | `playbook_steps` |
| One step set, by constraint | `playbook_step_set`, `CHECK (id = 1)` |
| One run per product, by primary key | `launch_positions`, PK `product_id` |
| The spine is a code literal | `GATE_SEQUENCE`, `CHECK`ed in three tables |

None of it is deferred work. It is the model saying there is one process and
every product walks it once.

Two naming faults follow from the same root. A step declares `starts_at_gate`
and `gate` — it lives in the *interval between two gates*, which is a
**stage**; the model names that interval by its right-hand edge and hangs the
work off the door, which is why `launch-playbook`'s spec has to keep
explaining that "opening a gate grants permission for the work beyond it and
does not itself perform that work". And **graduation is not a position** — it
is a set of obligations (choose a posture, stamp the catalog, stop the ClickUp
loop, never ask in Slack) that six modules implement by matching the literal
string `"graduated"`.

## Constraints that do *not* apply

Recorded because they shaped an earlier draft of this plan and their absence
is what makes it short.

**Production data is test data.** Nothing in the production database needs to
survive. Tables may be dropped and recreated rather than altered, and the runs
currently in flight need no migration path. This removes the whole class of
careful `ALTER`-plus-backfill work — the pattern that produced
`add_step_field_columns` → `backfill_step_fields` → `drop_legacy_step_columns`
and then the same three-step shape again for start gates.

**Meaning-preserving migration is not required.** An earlier version of this
plan split the model change in two so that each half's migration could be
proved 1:1 against live data. That reasoning is void, and the halves are
merged below.

**The step set may be curated, not only reshaped.** Steps that are no longer
wanted are dropped at the reseed rather than retired afterwards.

The consequence for the deploy pipeline is real and must be handled once: the
container's `CMD` runs `alembic upgrade head` on every start, so a schema
recreated from scratch means the production database is dropped, or its
`alembic_version` cleared, at the deploy that carries Change 5.

## The end state

```
  Playbook ────────┐                         Step  ◀── the library object,
   id, name        │                          id, identifier,       shared
   status          │                          name, description,    across
                   │                          discipline, scope,    playbooks
                   ▼                          kind, hazard,
  Stage  ◀── the folder                       handler, confirmer,
   id, playbook_id, key, label                provenance, metric_id
   exit_mode: automatic | requires-confirm            ▲
   status: draft | active | retired                   │
   successors: [stage_id]  ◀── the graph              │
                   ▲                                  │
                   └──────────┐          ┌────────────┘
                              │          │
                          Placement  ◀── this playbook's use of that step
                           playbook_id, stage_id, step_id
                           display_order, blocking, starts_at_stage
                           after_steps[], timing_anchor, status, assignees

  Run
   id, product_id, playbook_id, current_stage_id
```

Four things this buys, each impossible today:

- **Several playbooks.** Category A and category B run different variants.
- **A stage is editable data** — add, rename, reorder, retire — instead of a
  literal `CHECK`ed in three tables.
- **A spine is a graph.** The launch's eight are the degenerate case, a path.
  A spine that fans out needs no second mechanism, and where a stage has more
  than one successor the confirmation names which — the graduation approval
  already carries an approver-chosen posture, which is exactly that.
- **A step is defined once and placed many times.** Correcting a description
  corrects it everywhere it is used.

## Decisions this rests on

**No versioning. Cloning replaces it.** Versions exist to answer "what happens
to a run in flight when the definition changes". The answer here is that you
do not change the playbook a run is on — you clone it and change the clone.
The clone *is* the version, except it has a name, appears in a list, and needs
no publish workflow, no draft/published state machine and no re-pinning
feature. What is given up is history ("what did this playbook look like in
January"); the launch journal already records what actually *happened* per
run, which is the thing that would ever be audited.

**Edits stay live.** An accepted write takes effect on the next read, for
every run including those in flight — which is what `launch-playbook`'s
*Playbooks are versioned* already specifies and what a correction should do.

**A step edit prompts only when a second playbook holds it.** One playbook
holding a step means an edit can surprise nobody, so it is applied without a
question. Two or more means the write must offer *change everywhere* or *fork
here*. The prompt is a function of the placement count, not a mode the user
turns on.

**Cloning links rather than copies.** Category variants share the great
majority of their steps, so a clone's placements point at the same library
steps; divergence happens per step, deliberately, through the fork half of the
prompt above. A deep-copying clone would create exactly the duplication the
library exists to remove.

**Field ownership is split between the step and its placement.** Roughly half
the current `playbook_steps` columns describe *the work* and half describe
*where the work sits*. This split is the core design of Change 5 and the table
below is a first cut, not a settled answer:

| Belongs to the **Step** | Belongs to the **Placement** | Undecided |
|---|---|---|
| `name`, `description` | which stage | `status` — `in-development` reads as a property of the work, `active` as a property of its use here |
| `discipline`, `scope` | `display_order` | |
| `kind`, `hazard` | `blocking` | |
| `handler`, `confirmer` | `after_steps` | |
| `assignees` | `starts_at_stage`, `timing_anchor` | |
| `provenance`, `metric_id` | | |

`assignees` sits with the step because roles make it person-independent (see
below): a step assigned to `controller` carries no one's identity into the
three playbooks that place it. Were assignment still by person, this row would
be the table's hardest question.

**The people directory is `members`, not `roster`.** The word is already what
the shipped specs reach for whenever they need a human noun — *"An active
roster member resolves to the unrestricted scope"*, *"a deactivated member sees
nothing"*, *"membership says what a person may see"* — so the rename promotes
existing vocabulary rather than inventing any, and lets that prose drop a
redundant qualifier. `employee` was rejected because the company head confirms
steps and is not one; `collaborator` because 26 uses across four specs already
mean a supplied port, not a person. The admin page is titled **Team**, which
supplies the container that makes "members" read naturally.

**A step is assigned to a role, not to a person — but may name a person.** A
role reference always means *that role's default holder*, exactly one person,
so `confirmer` resolves cleanly and there is no "all holders" mode. Non-default
holders exist to be picked by hand for a particular step. The field is
therefore a union of a role reference and a person reference, stored in the
`JSONB` column `assignees` already is:

```
assignees: [ {role: "controller"} ]     ← the usual case, follows whoever holds it
assignees: [ {person: "<uuid>"} ]       ← the override, always this person
```

This is what makes the step library person-independent, and it is why changing
who holds a role reassigns their open ClickUp tasks on the next pass —
`clickup_sync._assignee_change` already reconciles assignment continuously
rather than setting it once. That retroactive reassignment is **deliberate**,
and deliberately unlike the task-*name* rule, which is set at creation and
never rewritten because a person may legitimately have edited it.

**A draft holds a slot.** `playbook-authoring:246` currently holds that "slots
belong to the served order", so a `draft` step has none and a step entering
`active` "SHALL take the last slot of its gate rather than reclaiming a
remembered position". That is reopened: **every** step holds an authored slot in
its gate whatever its status, and the *served* order is that order restricted to
active steps. There is still one order — it simply also covers the steps not yet
served. Activating therefore stops moving anything, which removes the cause of
the reordering problem rather than giving it a better UI.

The consequence to design for: the admin's gate listing now interleaves drafts
with active steps in one order, so the served set must stay visually
distinguishable — today it is separated into two tables, which no longer
expresses the ordering.

**Roles are a managed collection, seeded with nine.** They are created, renamed
and retired in the admin like any other content — nobody can guess today which
roles this company will actually need, and a vocabulary fixed in code would have
to be guessed correctly the first time. What the nine below are is a *starting
set*, seeded because step seeding needs roles to reference, not a closed list.

**A role's identifier is a slug, chosen once and never changed; its title is
editable.** This differs deliberately from a member, whose identifier is a
generated `uuid4` precisely so it can never be re-pointed at a different human.
A role is vocabulary rather than a person: the slug is what steps store and what
the vendored file names, so it must be stable *and* nameable in advance — a
`uuid4` generated at seed time is neither. Steps carry meaningful string
identifiers (`lp.strategy.001`) for the same reason. Renaming *Financial
Controller* to *Head of Finance* is therefore free and rewrites nothing.

**A role is retired, never deleted, and cannot be left without a default.**
Both mirror rules the member directory already carries. Deleting a role that
steps reference would strand them, exactly as deleting a person would — so
`roster`'s *deactivated, never deleted* applies unchanged. And an active role
whose default holder is removed resolves to nobody, which silently breaks every
step assigned to it; removing the last holder of an active role is refused the
way the last active admin already is. A retired role takes no new assignments,
and the steps still naming one are reported rather than failing a load — the
shape *What blocks a step from being activated is reported* already uses.

**The seed is the member directory's bootstrap, not the playbook's.** Roles must
exist before steps can reference them, and the container chain already runs
`seed_admin` before `seed_playbook`. So seeding the nine roles and pointing every
default at the bootstrap admin belongs there — one step with one concern, that
the member directory is usable, rather than a new link in the chain.

Each role is a position a marketplace company actually staffs, so the directory
reads as an org chart rather than as a re-spelling of the discipline enum. The
identifier is a short slug and the display name is the full title. Every one of
the 358 steps is covered and none is counted twice:

| Identifier | Position | Steps | From disciplines |
|---|---|---|---|
| `supply-chain` | Supply Chain Manager | 78 | `inventory`, `setup` — suppliers, MOQ, cartons, HS codes, freight, packaging spec |
| `ppc` | PPC Manager | 77 | `ppc`, `rank`, `traffic` — campaign structure, launch keyword strategy, spend |
| `brand` | Brand Manager | 65 | `strategy`, `price` — product selection gates, price ladder, competitive position |
| `catalog` | Catalog Manager | 39 | `listing` — flat files, browse paths, variation families |
| `controller` | Financial Controller | 36 | `finance` — CM1/CM2/CM3, landed cost, fee tiers |
| `creative` | Creative Manager | 26 | `creative` — photography, A+, packaging artwork, CTR assets |
| `customer-service` | Customer Service Manager | 22 | `customer` — reviews, feedback, 1-star response |
| `marketing` | Marketing Manager | 15 | `external` — email, influencers, affiliates, off-Amazon |
| `operations` | Operations Manager | — | maps to no discipline; the cross-cutting **confirmer** role |

Two naming choices worth keeping. **Brand Manager**, not Category Manager: both
are real titles, but in a private-label marketplace business the person clearing
the demand and revenue gates owns a brand's P&L, which is what a brand manager
does. **Financial Controller**, giving the identifier `controller` — a
distinct word for free, where `finance` would read ambiguously against the
`finance` discipline. `ppc` and `creative` do overlap with their disciplines;
that is accepted rather than fixed, since the alternative is a worse job title
and the two vocabularies are separate namespaces.

Three merges carry the reasoning and are the ones to revisit first if they feel
wrong. `rank` folds into `ppc` because launch ranking here *is* ad
strategy — keyword families, never-keywords, Titan Tools — not a separate craft;
`traffic` is one step. `setup` folds into `supply-chain` because its steps are
packaging and production spec (shrink wrap, in-box inserts, batch codes), which
the sourcing owner decides with the supplier. `price` folds into
`brand` because whoever clears the demand and revenue gates sets the
price those gates were computed from — though at 31 steps it is the most
plausible candidate to split out later.

`operations` exists because a confirmer is often not the discipline owner: it
is the role that accepts someone else's work, and it maps to no discipline
deliberately. **Open:** whether capital commitments want a tenth role —
*Managing Director* — rather than being confirmed by the Operations Manager.
The company head confirms some steps and is not an employee, which is one of
the reasons the directory is `members` rather than `employees`.

**`LifecycleStage` is renamed `LifecycleState`.** A product is in a *state*; a
playbook has *stages*. The rename exists solely to free the word.

## The seed set, and why it comes first

Independent of the model work below, and worth landing ahead of it: the
vendored step set is not in the state the team wants, and the two files
describing it already misled one change.

**One file, not two.** `alembic/data/playbook_v1.yaml` is stale — it still
carries `binding`, `execution` and `metric_conditions`, vocabulary
`redesign-step-fields` and `replace-metric-conditions-with-steps` removed. One
thing reads it: migration `d2f8b3c64e17`. `docs/deferred-work.md` records that
this split has **already cost a wrong analysis** — `let-a-step-say-when-it-starts`
was scoped and argued against `v1` on the assumption it was the seed, claiming
97 steps with 65 on `listable` against a real 358 stored and 95 served — and
names "the step set needing a status correction" as its trigger to close. That
is now.

**Two of the three intended corrections are already true.** All 358 steps are
`kind: human`, and none names a `confirmer` — and per `launch-playbook:410`,
"naming a confirmer is what makes a step's result require confirmation … a
step naming no confirmer needs none". Only the status is wrong.

**Activating the set is three changes, not one.** Each is required; the first
alone produces the failure the assignee rule exists to name.

| Field | From | To |
|---|---|---|
| `status` | `draft` ×358 | `active` |
| `assignees` | `[]` ×358 | a **role** reference, from the step's discipline |
| `display_order` | unset (defaults to `0`) | the file's own row order, per gate |

*Why the assignee is not optional.* `launch-playbook:503` requires an `active`
`human` step to name an active assignee, because "a projected task nobody is
assigned is the shape that failure takes today". The seed **would not be
refused** if it ignored this — it validates by constructing `LaunchPlaybook`,
which runs load-time coherence rules only, and the assignee rule is
deliberately a write-time precondition — but that is a loophole, not a
licence: 355 of the 358 steps project as ClickUp tasks, and the result would
be a set the authoring surface itself could never have created.

*Why a role and not a person.* Member identifiers are `uuid4` generated at
insert, so a vendored file cannot name a person at all — but it does not want
to. Writing one person's identifier into 358 rows is exactly what roles exist
to prevent, and every one of those rows would be rewritten the first time
someone changed job. A role reference is stable, and every role's default
holder starts as the bootstrap admin — created by `seed_admin`, which the
container's start chain already runs before `seed_playbook` — so a fresh
deployment is coherent from the first boot and real people are named later, one
roster row at a time.

*Which role each step gets.* Roles are their own vocabulary, not disciplines —
a `founder` role need map to no discipline at all. But the 358 steps already
carry a discipline each, and those twelve values read as job functions
(`finance` 36, `ppc` 58, `listing` 39, …), so the seed uses discipline as the
**initial guess** for a step's role. That is a starting arrangement to refine
in the admin, not a structural identity between the two vocabularies.

*Why the slot must be written.* `display_order` lives on `StepRecord` with
default `0` and the seed does not set it. Left alone, all 358 share a slot and
the served order falls back to identifier — `lp.<discipline>.<nnn>`, which
groups by discipline rather than by the document's own sequence. Computing the
slot from the file's row order makes the file's order the authored order,
which is what a person reading it already assumes.

Because `seed_playbook` adds only what is missing and never touches a stored
row, none of this reaches the existing database without emptying the table
first — which the disposable-data licence above permits.

## Ordering after activation, and the rule behind it

Activating a draft appends it to the end of its gate. With 83 steps on
`listable`, moving it back to where it belongs is the problem the admin makes
hardest. Three separable fixes, in increasing cost:

**The seed removes the immediate pain.** Steps seeded active and ordered are
never activated one at a time, so the append behaviour is not exercised at
all for the initial set.

**The page jumps to the top on every move, and that is nearly free to fix.**
`page.html` sets `hx-boost="true"` on `<body>` and the move controls are plain
POST forms boosted by inheritance, so htmx swaps the whole body and scrolls to
top as it does for a navigation. Giving the two move forms
`hx-target`/`hx-select` on the steps table plus `hx-swap="… show:none"` swaps
only the table and leaves the scroll alone — **no route change**, since `move`
already returns a full page render for `hx-select` to pick from.

**The root cause is a specified rule, and it is worth reopening.**
`playbook-authoring:246` holds that a step entering `active` "SHALL take the
last slot of its gate rather than reclaiming a remembered position", because
"slots belong to the served order". The alternative is that every step holds an
authored slot in its gate whatever its status, and the *served* order is that
order restricted to active steps — one order still, and activation stops
moving anything. **Open:** the cost is that the admin's gate listing then
interleaves drafts with active steps, so the served set must stay visually
distinguishable.

Drag-and-drop is a fourth option and is cheaper than it looks — `move` already
takes a *neighbour* (`after=`) plus a version token rather than an index,
which is exactly what a drop handler produces — but it is only worth building
if the three above prove insufficient.

## The changes, in order

### 1. `rebuild-the-member-directory`

The people directory, done properly — one module (`access`), one concept, four
commits.

- **Rename** `roster` to `members` throughout: the `roster` and `roster-admin`
  specs, the `roster_people` and `roster_set` tables, "roster identifier" →
  "member identifier", and the references `launch` makes to them. This also
  settles a live inconsistency — the page's own `<h1>` already reads *Users*
  while every spec says *roster*.
- **Roles**, as `move-principals-to-roster` predicted: it put "roles /
  information-kind access" out of scope explicitly, to be added by "a later
  change **when there is behavior to hang on it**". Steps assigned by role is
  that behaviour. A role carries an immutable slug, an editable title and its
  holders, exactly one of them the default; the `admin` boolean stays exactly
  where it is, because permission and work-ownership are different axes and
  `roster`'s last-active-admin invariant is built on the boolean.
- **Managing roles**, since the nine seeded are a starting guess rather than a
  known answer: create, rename and retire them from the admin, with holders
  added and the default moved. Carries three rules that mirror ones the member
  directory already has — retired never deleted, an active role may not lose its
  last holder, and a retired role takes no new assignments while the steps still
  naming it are reported rather than failing a load.
- **The admin page**, rebuilt to the pattern `move-step-actions-into-step-pages`
  already shipped and specified for steps. Today the page opens with a
  full-width *Add a person* form, and its `actions` column holds two `<form>`s
  containing three unlabelled `<input>`s — an edit-in-place crammed into a table
  cell, with a `td.actions form { display: contents }` CSS hack working around
  it. Target: a **Team** page that is a read-only list whose name column links
  to the member's own page; adding moves to its own page as `/steps/new` did;
  editing, deactivating and reactivating move onto the member's page as step
  status did. Roles get the same treatment — a list, and a role's own page —
  rather than being edited inline in a cell, which is the mistake this change
  exists to undo.

*First*, because it depends on nothing, and Changes 2 and 3 both need roles to
exist. It is the largest of the three preceding changes and the one whose scope
is most worth watching: rename, roles, role management and a page rebuild are
four commits, and if it stops being reviewable in one sitting the role-management
half is what splits out.

### 2. `assign-steps-by-role`

`assignees` and `confirmer` accept a role reference or a person reference, per
the union above. Resolution at projection and display; the step picker renders
the two groups described below.

**The one spec consequence.** `launch-playbook:513` rejects a step whose *only*
assignee is also its confirmer — "a single actor confirming their own work is
not a second opinion" — and it is a **load-time** rule today precisely because
it is a pure function of the step set. Roles break that purity: `controller`
and `operations` are plainly different references, yet resolve to the same person
if one member holds both. The check splits — references differing stays
load-time and pure; resolved people colliding becomes a roster-dependent fault,
reported the way a deactivated confirmer already is (`launch-playbook:509`),
not a load failure.

**The picker.** A union field's hard problem is that its user cannot see what
will be stored. Two labelled groups solve it structurally, where a badge or a
flag would not:

```
  ── By role ──  follows whoever holds it
     default Operations Manager (Helen)
     default Financial Controller (Sven)

  ── By person ──  always this person
     Helen (Operations Manager)
     Marko (Operations Manager)
     Sven (Financial Controller)
```

A member appearing in both groups is the point, not a defect: the parenthetical
means *who holds this now* above and *what they hold* below. The group headers
state the consequence rather than leaving it to be inferred from that
inversion. A role with no default set, or whose default is deactivated, renders
unavailable rather than as a pickable "default manager (nobody)".

### 3. `activate-the-seeded-step-set`

The seed corrections and the file consolidation above: one vendored file,
`playbook_v1.yaml` deleted, migration `d2f8b3c64e17` collapsed, and the set
seeded `active`, role-assigned and ordered. Includes the htmx scroll fix, which
is too small to be its own change and belongs with the ordering work.

Independent of the model work, and it unblocks a recorded deferred item and
puts the step set into the state every later change reads.

### 4. `rename-lifecycle-stage-to-state`

Mechanical rename across `shared`, `catalog`, `launch`, `briefing` and their
specs. No behaviour change.

*First*, because every change after it writes the word "stage" in the new
sense; doing it later means writing the whole framework in the wrong word and
renaming twice.

### 5. `introduce-playbooks-stages-and-placements`

The whole model, in one change, because the disposable database lets the
migration drop and recreate rather than alter and backfill.

- `playbooks`, `playbook_stages`, `steps` and `playbook_step_placements`
  tables; `playbook_steps` and `playbook_step_set` dropped outright.
- A stage carries `status` (`draft` / `active` / `retired`), which answers the
  standing hazard that creating an empty stage takes every launch surface
  down: a draft stage is not part of a served spine.
- The playbook declares its **exit effect**, replacing the six hard-coded
  `"graduated"` sites. A playbook with no terminal stage declares none.
- `GATE_SEQUENCE`, `gate_position()`, `_FINAL_GATE` and the three `CHECK`
  constraints on gate identifiers are removed.
- `launch_positions` re-keyed from `product_id` to a run, gaining a playbook
  reference, so a product may hold one active run per playbook. Every table
  cascading from it follows.
- Every coherence rule — acyclic dependencies, a `prohibited-tactic` never
  blocks, an automated step carries a handler, every stage is held by an
  active blocking step — is re-scoped to evaluate per playbook over
  placements.
- The seed writes the launch playbook, its eight stages, and the curated step
  set as steps plus placements.
- The step admin reads real stages instead of deriving `{gate: [steps]}` by
  grouping, and a stage's exit mode becomes editable. Structural stage editing
  is Change 8.

**The largest change in the program.** What keeps it reviewable is that its
migration is one file describing a schema, not a chain of corrections to an
existing one — and that at the end there is still exactly one playbook, so the
system's observable behaviour is unchanged apart from the admin's stage view.

**Open question to settle when it is proposed:** whether the reseed is
faithful (the same 97 steps in the new shape) with curation following as its
own change, or curated in place. Faithful is easier to review — a reviewer can
tell a modelling defect from an intended content edit — but it means writing
rows that are known to be unwanted. Curating in place is what the disposable
database is *for*; the cost is that the change carries two kinds of judgement
at once.

### 6. `create-a-playbook-from-another`

- Clone: a new playbook, copied stages, and placements pointing at the **same**
  library steps.
- Starting a launch selects which playbook the product runs.

The first change that delivers the actual goal.

### 7. `prompt-before-changing-a-shared-step`

- A step write counts the playbooks holding a placement of it. One, and it is
  applied. More, and the write offers *change everywhere* or *fork here*.
- The offer states what it affects — *used in 3 playbooks, 14 running
  launches, 6 of which already recorded an outcome for this step* — because
  "change everywhere" is unanswerable without it.
- Fork creates a library step from the original, repoints this playbook's
  placement, and rewrites `after_steps` references **within that playbook**.

### 8. `edit-the-stage-graph`

Add, rename, reorder and retire stages in the admin, with the in-flight guard
(H3 below). Depends only on Change 5 and may be worked in parallel with 6–7.

### 9. `squash-the-migration-history`

One baseline replacing the tree, once the schema has stopped moving.

**Last, deliberately.** Squashing before Change 5 would be squashing a history
that Change 5 immediately rewrites. Doing it after means one baseline that
describes the settled schema and never described anything else.

It also retires `docs/deferred-work.md`'s *Migration `1a2b3c4d5e6f` carries a
hand-invented revision id*, whose "must not be corrected" reasoning — that
renaming would strand databases at a revision that no longer exists — stops
applying when every revision is replaced and the database is recreated
anyway.

## Hazards that need answering before the change that hits them

Two hazards from the earlier draft are gone with the live-data constraint: the
double migration over runs in flight, and the need to prove each migration
meaning-preserving. Two more are now decided and have moved up into *Decisions
this rests on*: whether a draft holds a slot, and what the starting role list
is. Those below survive.

| # | Hazard | Due by |
|---|---|---|
| H1 | **A fork orphans a run's recorded progress.** `launch_step_progress` and `launch_clickup_tasks` are keyed by step identifier. Forking repoints the placement, but a run already holds rows against the original. Forbid forking a step with a run in progress against it, or repoint those rows. Harmless today; not once launches are real. | 7 |
| H2 | **Identifier provenance.** Identifiers are reference-document row IDs and carry a trace to `docs/reference/product-launch.md`. A fork needs a new identifier without destroying that trace. | 7 |
| H3 | **Reordering or retiring a stage under a live run** silently changes what that run's stored position means, with no versioning to fall back on. Needs a refusal, or a confirmation naming the affected runs. | 8 |
| H4 | **Prompt fatigue.** The first clone makes every subsequent edit to any shared step prompt. Mitigated by defaulting the prompt to *change everywhere* as a single click, not a modal requiring thought. | 7 |
| H5 | **Is `status` per step or per placement?** See the field table above. `assignees` is settled by roles. | 5 |
| H6 | **The served set must stay distinguishable** now that a draft holds a slot and the listing interleaves them. Today the admin separates served from not-served into two tables, which no longer expresses one order. | 3 |
| H7 | **May one member hold several roles?** Likely yes for a small team — and if the same member is the default for both a step's assignee role and its confirmer role, that step resolves to one person confirming their own work, reported as a resolution fault rather than a load failure. | 2 |

## Conflicts with the working queue

Three entries in `docs/proposed-change-order.md` touch launch infrastructure
this program rewrites: `defer-eager-clickup-convergence`,
`unify-launch-adapter-dependencies` and `unify-the-launch-advisory-locks`.
Two of them are in flight now. `share-the-unit-test-harness` is already marked
*last* there because it touches nearly every test file; this program touches
many of the same ones.

Land the queue's launch-infrastructure entries **before** Change 5, or accept
rebasing them onto a re-keyed `launch_positions`.

## Out of scope

The monitoring playbook's own content, and a recurring/cadence spine kind for
a playbook whose runs never advance. Both become straightforward once the
framework is data, and neither is needed to reach the goal above — the
playbooks this program is built for are category variants of the launch.
