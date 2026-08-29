## Context

See `proposal.md` — Why. What follows is the state the design has to fit.

**Three consumers, each with the same single gate check.** Both passes
return early only at `graduated`, then range over the whole served set:

```
playbook.served_steps
   ├── converge_launch      is_projectable(step)  = HUMAN     ∧ active ∧ ¬prohibited
   ├── _walk_launch         _automated_steps(...) = AUTOMATED ∧ active
   └── launch_admin         every step, grouped by gate (presentation only)
```

The first two filter on `kind` and are therefore **disjoint** — no step is
ever seen by both. `is_projectable` is explicit that `needs_confirmation` is
"not a way back into this projection", so even a confirmed automated step
stays out. This is what lets one field govern both passes.

**Two step sets, and only one of them is served.** The step content lives in
Postgres. Two vendored YAML files feed it, and they are not
interchangeable:

- `alembic/data/playbook_v1.yaml` (97 steps) is read *only* by migration
  `d2f8b3c64e17`, whose own docstring records why the copy is vendored: the
  source tree's loader was removed when the database took ownership, and a
  fresh environment must still be able to run that migration. It is a
  historical artefact and not a description of the live set.
- `alembic/data/playbook_reference.yaml` (352 steps) is the live vendored
  set, delivered by `seed_playbook` on every container start, which inserts
  only rows no stored step names and never overwrites one. Its identifiers
  are a strict superset of v1's.

After `b8e5c04a1d39` mapped the v1 `execution` values onto the current
fields (`human-attested` → `active`, everything else →
`in-development`), the 352 stored steps stand as **95 `active`**, **2
`in-development`** and **255 `draft`**. Only the 95 are served.

**The playbook's calendar and its gate spine already disagree.** Anchors per
gate across the 95 served steps:

```
commit              -90×4
order               -90×2 -60×1
listable            -60×20 -30×33 -15×2 -14×8 -7×1     (64 of 95 steps)
stock-ready         -30×3
live                -60×1  -14×3  -7×5
ignition              0×6  recurring×1
phase-one-complete    7×1  recurring×1
graduated            59×3
```

`listable`'s blocking steps run out to T-7, so nothing downstream of gate 3
can plausibly begin before T-7 — while gates 4 and 5 carry work anchored at
T-30 and T-60. Seven served steps are anchored before their own gate can be
reached (23 across the whole authored set, in those same two gates). That
disagreement is a property of the authored playbook, not something this
change resolves; the design's job is to give an author a way to express it.

**Where rules already live, and why.** `LaunchPlaybook.__post_init__` holds
every rule that is a function of the step set alone. `assignee_faults`
(roster) and `_registration_faults` (handler registry) sit at write time
instead, because each is a function of something that changes *without the
step set changing* — were they load rules, a write in another module would
break a capability that accepted no write.

## Goals / Non-Goals

**Goals:**

- One predicate, asked by every consumer, so no pass keeps a private idea of
  when work starts.
- Keep the predicate pure: gate position and recorded outcomes, no clock, no
  I/O, so it is a domain function testable without a database or a fixed
  date.
- Preserve the existing rule taxonomy — a new rule joins load-time or
  write-time on the same test the existing ones were sorted by, not on
  convenience.

**Non-Goals:**

- Reconciling the calendar spine with the gate spine in general. The fields
  let an author state the exception, and the backfill states it for the seven
  `active` steps whose anchors have been reviewed — each justified
  individually in `tasks.md`, which is an authoring judgement this change
  does make and should be read as making. What it declines is making that
  judgement in bulk: the sixteen `draft` steps the same measure flags take
  the mechanical default, and choosing a start gate for one is left to
  whoever activates it.
- Gating reconciliation. If a person completes work early, recording it
  stays correct — see Decisions.
- ClickUp dependency edges (proposal.md — Not in this change).

## Decisions

### Release is a pure function of gate position and recorded outcomes

```
released(launch, step) :=
      pos(launch.current_gate) >= pos(step.starts_at_gate or GATE_SEQUENCE[0])
  AND all(resolved(b) for b in step.after_steps if counts(b))

counts(b) := b names a step in the set
             AND that step is active
             AND that step is not classified prohibited-tactic
```

The three conditions on `counts` are one rule wearing three faces: a
dependency only holds a step back while it is something the launch is
actually still owed. An identifier naming nothing, a step no longer served,
and a step whose classification means the system will decline to do it are
all things nobody is waiting for.

It lands on `Launch`, beside `unsatisfied_conditions` and the private
`_resolved` it can reuse — the aggregate already holds both the gate
position and the recorded progress, and holds no clock.

*Alternative considered: fold the timing anchor in*, releasing a step only
once its anchor's start has arrived. Rejected. It makes the predicate depend
on `today()`, which makes it untestable without freezing a clock and
non-deterministic across a pass that spans midnight; and it would silently
re-purpose the anchor, which the capability defines as a due date. The seven
conflicting steps are better served by an authored exception than by a
second implicit rule.

### `>=`, never `==`

A step is released once the launch has reached **or passed** its start gate.
This is where the freeze that deferred the whole change actually lives:
under equality, a launch reaching `stock-ready` would abandon every
unfinished `listable` step, and 64 steps would go dark mid-flight. Stated
here because it is a one-character difference with a per-launch blast
radius.

### `starts_at_gate` is a gate identifier

*Alternative considered: a boolean* meaning "wait for my own gate". Rejected
on the data — the seven anchor-conflicting steps each want a *different*
earlier gate (`lp.inventory.*` → `order`, `lp.ppc.*` → `listable`), and a
boolean can express neither. It also makes the backfill impossible to state:
the great majority want their own gate, and 23 want another.

The cost is a second gate-valued field on a step that already has `gate`.
They are distinguished in the form and on the detail page by wording —
*belongs to* versus *starts at* — never by proximity.

### `after_steps` is a second ordering primitive, and the spec said there was one

`launch-playbook` states that "Gates SHALL remain the only *commitment*
ordering primitive in the playbook", and carefully separates the within-gate
`display_order`, which "SHALL never affect when a gate opens, which steps
block it, or how step completion is evaluated". `after_steps` is neither: it
orders two steps *and* carries consequence, so the requirement as written
forbids it. It is amended rather than worked around.

What the amendment preserves is the distinction the original clause exists to
draw. A gate still opens exactly when its own blocking steps are resolved and
its conditions are met; `after_steps` cannot move a step between gates, add or
remove an obligation, or change a gate's evaluation given the same recorded
outcomes. It governs **when work is asked for**, not when a commitment is
reached — which is why gate evaluation is explicitly outside the release
predicate (see *Both passes consult the predicate*), and why the existing
"steps at the same gate are unordered" guarantee survives intact.

This was found while reading the test the domain already carries for that
clause, `test_steps_at_the_same_gate_carry_no_ordering`, after six review
rounds had passed over it. Recorded because the near-miss is the point: a
change that adds a primitive to a system whose specification says there is
only one will not necessarily contradict anything the change itself says.

### `after_steps` is a conjunctive set

*Alternative considered: a single reference.* Rejected: it forces a fan-in
to be encoded as a chain, which asserts an ordering between the depended-on
steps that does not exist and serialises work that could run in parallel.

The set is modelled on `assignees` feature for feature — `tuple[str, ...] =
()` normalised in `__post_init__`, a non-nullable JSONB column defaulting to
a list, a `multiple` select in `_fields.html`, per-element faults naming the
step and the offending identifier. Empty set and "no dependency" are one
fact, so there is no `None` case.

*Alternative considered: an `any` mode.* Rejected as unbuilt-until-needed. A
data dependency is conjunctive by nature, and a disjunctive mode would
double the deadlock analysis below for a case nobody has.

Because empty and "no dependency" are one fact, **omission is the empty
set** wherever the field can be omitted — the vendored file included. This
is the one field where that is safe, and `starts_at_gate` is not: an absent
start gate is also a meaningful value ("starts immediately"), and one the
backfill exists to replace, so the vendored file must state it and delivery
must refuse a step that does not.

### The load-time rules, and why they are load-time

Both are functions of the step set plus the code-owned framework gates
alone. Nothing outside the step set can invalidate either, which is exactly
the test `assignee_faults` was sorted by — so they belong in
`__post_init__`, and a write is judged by them because write validation
reconstructs the whole candidate set.

**1. A start gate no later than the step's own gate.** Otherwise a
`blocking` step at `listable` starting at `live` deadlocks permanently:
`listable` cannot open until it resolves, and it cannot start until a gate
the launch will never reach. Forbidden for non-blocking steps too — such a
step is released only after its own gate has passed, so it is overdue from
the moment it appears, a representable state with no sensible reading.

**2. The transitive dependency rule.** For a `blocking` step A, every step
in A's transitive `after_steps` closure must have a start gate no later than
`A.gate`. Two things about this are easy to get wrong:

*It is stated over the depended-on step's start gate, not its own gate.*

```
A blocking @ listable, after_steps: {B}
   B @ live, starts_at_gate: ⌀      → B resolvable immediately.  FINE
   B @ live, starts_at_gate: live   → B unreleased until live.   DEADLOCK
```

Same `B.gate`, opposite outcomes. A rule stated over `B.gate` forbids the
first, which is legitimate authoring.

*It is transitive, not pairwise.*

```
A blocking @ listable ──▶ B @ graduated (starts: commit) ──▶ C (starts: live)

   pairwise: pos(B.starts)=commit ≤ listable   ✓
             pos(C.starts)=live   ≤ graduated  ✓
   actual:   A waits on C; C releases at live; listable never opens.  DEADLOCK
```

**3. Cycles.** `after_steps` makes the set a graph. One depth-first
traversal answers cycles and rule 2 together — the closure it walks is the
same closure — so this is a single traversal reported as two fault kinds,
not two passes.

The traversal ranges over `authored_steps`, so a retired step's own edges
are still validated; an edge *to* a non-active step is rule 4's business.

### `after_steps` may only name an `active` step — at write time

A load rule would make retiring a step render every stored playbook
unloadable, which is the mistake `serve-only-a-ready-playbook` was written
to undo.

The justification `assignee_faults` records does not transfer, and the spec
says so rather than borrowing it: an assignee is a function of the *roster*,
which changes independently, whereas `after_steps` is a function of the step
set — the load category. The reason it sits at write time anyway is
different and narrower: **retiring is a legitimate authoring action, and its
blast radius must not be "no playbook loads anywhere".**

This leaves a case write validation structurally cannot catch. Retiring step
C touches C; `_precondition_faults` is deliberately scoped to touched steps
("set-wide evaluation would mean the migrated step set … refuses every
subsequent write"), and widening it here would reintroduce exactly that.
So a stored set legitimately holds an edge to a non-active step, and the
predicate meets it at runtime.

### A dependency nobody is still owed is satisfied vacuously

Retiring a step releases what waited on it — and so does re-classifying one
`prohibited-tactic`, on the same reasoning and by the same clause. The alternative — blocking for
ever — freezes every dependent on every launch in flight, triggered by a
routine authoring action. It is also what the rest of the module already
says: `is_projectable` holds that a non-`active` step "is not part of the
launch's obligations at all", and an obligation nobody holds cannot be one
another step waits on.

Stated as a requirement rather than left to the traversal, because both
readings fall naturally out of an implementation and the wrong one fails
silently.

The `prohibited-tactic` case is the one that would be missed. Authoring such
a dependency is refused at write time — sequencing work behind a refusal is
the wrong shape for a dependency, whatever a handler could in principle
record — but re-classifying an existing dependency reaches the predicate the
same way retirement does, and an implementation that judged it by the
hazard's permitted terminal outcomes would wait for a `Refused` that, for a
`human` step, no surface produces. Hence the third face of `counts` above.

### Both passes consult the predicate; reconciliation does not

The two passes see disjoint populations (Context), so one field governs both
with no step subject to a conflict. Gating only the projection would leave
`_walk_launch` with a private idea of when work starts — the very thing the
single predicate exists to end — and would mean no author could ever stop a
handler firing at gate 1.

**The backfill pulls the lever for the advisor, and that is the fix rather
than a side effect.** The step is `lp.listing.007` (gate `listable`, anchor
T-60), resolved by the `listing.subcategory_advisor` handler; the backfill
gives it its own gate and it stops running at `commit`. That is the production incident `proposal.md` opens with, and it
is what closing it looks like.

Pre-computation was considered and is not what this step wants. The advisor
was recording `Blocked` because it could not categorise a product that had
not been set up yet: running it two gates early did not produce an early
answer, it produced a repeated non-answer. A handler whose inputs really are
available early can be given no start gate deliberately, and that remains an
authoring decision recorded on the step — but it is a decision to be made
per handler, on evidence, and the default is the step's own gate.

What gating the pass buys, separately from the backfill, is that the lever
exists at all: without it no author could stop any handler firing at gate 1,
and the next handler-runs-too-early fault would need a code change rather
than an authoring action.

**Reconciliation is deliberately not gated.** `reconcile_launch` records an
outcome when a task's closed state changes. If a person completes work
early, recording it is correct — the fields say what work is *asked for*
when, not what may be accepted. Gating reconciliation would discard real
work on the grounds that it arrived early.

### The admin marks, never hides

A launch's detail page renders the whole plan; hiding unreleased steps would
make it show less than the playbook, which is the opposite of what the page
is for. The mark's wording is *starts*, never *blocked*: the page already
carries `blocking` as "Blocks its gate" and the `Blocked` outcome label, and
a third sense of "blocked" would make the surface unreadable.

## Risks / Trade-offs

**A curated backfill can be wrong in a way an empty default cannot.** →
It is derived from the anchors, and the exceptions are individually named
with the anchor that justifies each. A wrong value delays work; it cannot
deadlock, because the load rules refuse a start gate later than a step's own
gate. The backfill is reversible by an authoring write, needing no
migration.

**The backlog is where this fails quietly if the backfill covers only what
is served.** 255 of the 352 stored steps are `draft`. A draft backfilled to
nothing becomes, on the day it is activated, exactly the step this change
was written to prevent — projected into every launch at once. → The backfill
ranges over the stored set irrespective of status. This is also why the
obligation is stated in the spec as covering the authored set rather than
the served one.

**A too-late start gate on a draft would fail silently.** A step whose start
gate the launch has not reached is passed over by the automation pass without
a report, is not projected, and — by this change's own rule — is not marked
overdue. A wrong value is
therefore invisible until someone notices work that never arrived. → Only
the seven reviewed `active` steps get an anchor exception; drafts take the
default, which withholds nothing today's behaviour grants, and the judgement
is made per step at activation by a person who can see it.

**The final gate is where the default breaks, twice.** Both consumers stand
down once a launch reaches `graduated`, so a step whose start gate is the
final gate is released into a state where nothing will act on it — and one of
the three served final-gate steps is `blocking`, which would make graduation
impossible. → The final gate is refused as a start gate at load, so the value
is unrepresentable rather than merely avoided by a careful backfill.

That fixes the value and leaves the *window*. `launch-gate-progression`
advances a launch "as far as the furthest gate its recorded state permits
within one pass", so a default of the single gate before the final one can be
entered and left between two runs of the passes that act on steps, and the
step is never acted on — the same failure reached by the width of the window
instead of by the value. → Final-gate steps default two gates back, to
`ignition`. Two gates is a **margin, not a guarantee** — no width can be
proved sufficient, since how long a launch stands anywhere depends on
schedules this specification does not fix. What it buys is that a gate's own
blocking work is released only at that gate, so leaving `ignition` takes
recorded work rather than a signature, and closing the whole window now takes
two coincidences instead of one.

**The integration database is not the stored set this design describes.**
The 352/95/2/255 figures describe the set after `seed_playbook` has delivered
the vendored file, which is what a deployed container does on every start.
The configured integration database has never had that step run against it —
it holds 95 `active` and 2 `in-development` rows, matching this design
exactly, plus 680 `retired` `mg.*` rows left by authoring tests, and **no
drafts at all**. So `tasks.md` 8.8 cannot be observed there, and its test says
so rather than passing vacuously. The active gate distribution does match the
table above, which is what task 8.7's re-derivation needs.

**The live table may have diverged from both vendored files.** The counts
above are computed from the YAML; authoring writes since have not been read.
→ The backfill revision keys on step identifier, skips a row it does not
find, and writes only where the column is null, so an authored value is
never overwritten. The exception set is re-derived against the live table
before the backfill is run, not taken from the file on trust.

**`playbook_v1.yaml` reads as current and is not.** It sits beside the live
reference set with a name suggesting it is the playbook, and this design had
to establish which of the two was authoritative before it could count
anything. → Out of scope here: it is a comment on a file this change does
not otherwise touch, and it cannot be deleted, since migration
`d2f8b3c64e17` reads it at runtime. Recorded in `docs/deferred-work.md`
instead.

**Two gate-valued fields on one step invite confusion.** → Distinguished by
wording in both surfaces, and by the load rule that makes an incoherent pair
unrepresentable rather than merely discouraged.

**The dependency multi-select ranges over ~95 options**, where its
`assignees` model ranges over a handful. → Grouped by gate with `optgroup`,
options rendered as `identifier — name`. It offers the `active` steps only,
and never the step being edited: the write refuses a dependency on any other
kind of step, and refuses a self-reference as the 1-cycle it is, so offering
either would invite a refusal the form exists to prevent.

**A launch already in flight sees steps disappear from ClickUp's future.** →
Nothing is deleted: `converge_launch` re-projects unfinished work and leaves
finished work alone, and a task already created for a now-unreleased step is
not removed. The change affects what is created next, not what exists.

## Migration Plan

1. **Schema revision.** `playbook_steps` gains `starts_at_gate` (nullable
   String) and `after_steps` (JSONB, non-null, default list), mirroring
   `assignees`. Both defaults reproduce today's behaviour exactly, so the
   revision is inert on its own.
2. **The schema revision is inert on its own.** With every row still at the
   defaults, every step is released immediately and every consumer behaves as
   it does today — so the two revisions may ship in one deploy without an
   intermediate state anyone has to reason about. This is a property of the
   revision, not a deployment phase to be sequenced.
3. **Backfill revision.** `starts_at_gate` is set to each stored step's own
   gate, whatever its status, with the two exceptions the requirement states
   and `tasks.md` enumerates: a step belonging to the final gate takes
   `ignition` — its own gate is **refused** as a start gate, so the plain
   default would produce a set the loader rejects and no launch would be
   served — and the seven reviewed anchor-conflicting steps take the earlier
   gate their anchor implies. Applied only where the column is null.

**Rollback.** Downgrading the backfill revision returns every
`starts_at_gate` to null, which is "starts immediately" — today's behaviour
— so a rollback cannot strand a launch. Authored values set after the
backfill are lost with it, the same data-loss the seed revision's rollback
already records.
