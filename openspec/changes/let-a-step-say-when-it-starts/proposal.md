## Why

**Nothing in the step set governs when a step becomes eligible.** `blocking`
says what a gate waits for before it opens — an exit condition — and no
field says what a step waits for before it starts. So every consumer starts
everything at once, and each carries exactly one gate check, both of them
the same one: `automation_pass._walk_launch` returns early only when the
launch is at `graduated`, and `clickup_sync.converge_launch` likewise.
Between them they invoke every `active` automated step's handler and project
every `active` human step into the launch's ClickUp list, whatever gate
those steps belong to.

**Seen in production.** A launch standing at `commit` had step
`lp.listing.007` — a `listable`-gate step, gate 3, anchored T-60, resolved by
the `listing.subcategory_advisor` handler — recorded at 10:00, 10:15 and
10:30. `commit` is gate 1, so it ran two gates early; `docs/deferred-work.md`'s
"gate-8 work runs during gate 1" states the width of the class rather than
this incident's. (The *repetition* half of the symptom is already fixed:
`cool-off-a-repeatedly-blocked-step` capped a handler repeating itself at one
call per 24 hours. This change is the ran-early half, and only that.)

**The ClickUp half is the larger one, and it is not evenly spread.** Of the
95 steps the deployment serves today, **64 sit on `listable` alone**. A
launch's ClickUp list therefore opens on day one with two thirds of the
served playbook in it, while the launch stands at `commit` and none of that
work can begin. Everything projected carries a due date, so `overdue` marks
accrue against work nobody was permitted to start.

**And the served set is the small one.** The vendored reference set
(`alembic/data/playbook_reference.yaml`, delivered by `seed_playbook` on
every container start) carries **352 steps**, of which 255 stand as `draft`
awaiting activation — a backlog roughly three times the size of what is
served. Activation is an authoring action, one step at a time, with nothing
to stop it: each activation adds a step that is projected into every active
launch's list on the next pass, whatever gate it belongs to and whatever
gate that launch stands at. Without a way for a step to say when it starts,
working through that backlog means a launch's list growing toward several
hundred open tasks on its first day. This change is what makes the backlog
safe to activate.

**It is unblocked as of 2026-08-28.** `advance-gates-and-confirm-in-slack`
wired the gate ratchet, so `current_gate` actually moves. Before that, a
gate-released step would have waited on a gate that never advanced and
frozen every launch permanently — which is why this was deferred rather than
done first (`docs/deferred-work.md`, "A step cannot say when it may start,
so gate-8 work runs during gate 1").

## What Changes

- **A step declares when it may start, in two independent authored
  fields.** `starts_at_gate` names a gate the launch must have reached;
  `after_steps` names steps that must be resolved first. Two fields rather
  than one mode, because all four combinations are meaningful — including
  both at once ("once we are in `listable`, and once the photos are
  approved").

- **`starts_at_gate` is a gate identifier, not a flag.** The step set needs
  it to be: seven of the 95 served steps are anchored to calendar dates
  *earlier* than their own gate can plausibly be reached, and each wants to
  name a different, earlier gate. The three `lp.inventory.*` steps on
  `stock-ready` (T-30 — first-order sizing, pre-shipment inspection, barcode
  TOS) want to start at `order`; the four `lp.ppc.*` steps on `live` (T-60
  to T-14 — never-keywords list, naming convention, keyword bucketing,
  search-volume ceiling) want to start at `listable`. A boolean "wait for my
  own gate" cannot say either. Across the whole 352-step authored set the
  same measure finds 23 such steps, in those same two gates.

- **`after_steps` is a set, not a single reference.** A step founded on data
  from three others depends on all three, and a single reference would force
  an author to encode that fan-in as a chain — which asserts an ordering
  between the three that does not exist, serialising work that could run in
  parallel and carrying that false ordering into every downstream view. The
  set is conjunctive: **all** named steps must be resolved. Empty means no
  dependency; there is no second way to spell it.

- **One release predicate, and every consumer asks it.** `converge_launch`
  does not create a task for an unreleased step; `_walk_launch` does not
  invoke an unreleased step's handler. The two see disjoint populations —
  projection is `human`-only, invocation is `automated`-only — so one field
  governs both without any step being subject to a conflict.

- **Release compares gate *positions*, and never an equality.** A step is
  released once the launch has reached **or passed** its start gate.
  Equality would abandon every unfinished step the moment its gate was
  left — the 64 `listable` steps going dark when a launch reaches `stock-ready`.

- **Release consults no clock and performs no I/O.** Its inputs are the
  launch's gate position, its recorded outcomes, and the definitions of the
  steps a dependency names. Timing anchors continue to govern due dates and
  overdue reporting and take no part in eligibility.

- **A start gate later than the step's own gate is refused at load**, and so
  is one naming the **final gate**. The first is a permanent deadlock: a
  `blocking` step at `listable` starting at `live` holds a gate that cannot
  open until it resolves, and it cannot start until a gate the launch will
  never reach. The second is the same failure by another route — every
  consumer stands down at `graduated`, so a step released only there is
  released into a state where nothing acts on it, and one of the three
  served final-gate steps blocks its gate.

- **The dependency rule is transitive, and is stated over start gates.**
  For a `blocking` step, every step in its transitive `after_steps` closure
  must start at or before that step's own gate. Stated pairwise, or stated
  over the depended-on step's *own* gate rather than its start gate, the
  rule is both wrong and needlessly strict — a step at `live` that starts
  immediately is perfectly safe to depend on, and a two-hop chain can
  deadlock while every pairwise check passes.

- **A `prohibited-tactic` step may not be depended upon at all.** Its only
  terminal outcome is `Refused` — the record that the system declined to do
  the thing — and sequencing other work behind a refusal is the wrong shape
  for a dependency. Refused at write time, and satisfied vacuously where a
  depended-on step is re-classified afterwards.

- **`after_steps` may only name `active` steps, and that is a write-time
  refusal.** Never a load-time one: a load rule would make retiring a step
  render every stored playbook unloadable, the exact mistake
  `serve-only-a-ready-playbook` was written to undo.

- **A reference to a step that has *since* become non-active is satisfied
  vacuously.** Write validation cannot prevent this — retiring a step
  touches that step, not its dependents — so the predicate meets it at
  runtime and must say which way it falls. Retiring a step releases what
  waited on it, rather than stranding it for ever.

- **The stored set is backfilled, drafts included.** Every step takes its
  own gate as its start gate, with two exceptions: a step belonging to the
  final gate takes `ignition`, since its own gate is refused as a start gate
  and a single-gate window can be crossed between two passes; and each of the seven
  `active` steps whose calendar anchor was reviewed and found to fall before
  its own gate can be reached takes the earlier gate that anchor implies. A
  draft takes the default: the same measure flags 16 more, but choosing a
  start gate for a step nobody has reviewed is an authoring judgement made at
  activation, not one a migration makes in bulk. Without it the fields exist and change nothing, since nobody will
  hand-edit hundreds of rows. Drafts are backfilled too, and that is the
  point rather than an afterthought: a draft left with no start gate becomes,
  on the day someone activates it, a step that projects into every launch at
  once — the very failure this change exists to end, re-entering through the
  backlog.

- **The admin marks an unreleased step; it does not hide it.** A launch's
  detail page shows the whole plan, which is what it is for.

**Not in this change.** ClickUp supports task-to-task dependencies over its
API (`POST /api/v2/task/{id}/dependency`), and projecting `after_steps` onto
those edges is worth doing — the existing list read already returns each
task's `dependencies`, so convergence over them would cost no extra request.
It is deliberately left out: it is independent of the release predicate,
touches no domain code, and ClickUp's dependencies only *warn* on early
completion rather than preventing it, so it can never be the enforcement
mechanism and does not belong in the change that builds one.

## Capabilities

### New Capabilities

None. This extends the existing step vocabulary and the passes that read it.

### Modified Capabilities

- `launch-playbook`: a step definition gains `starts_at_gate` and
  `after_steps`; new coherence rules for the start gate's position, the
  transitive dependency closure and cycles; the stored set gains an
  obligation to declare a start gate on every step, drafts included.
- `playbook-authoring`: a step's authorable shape gains both fields;
  `after_steps` may only name `active` steps that are not classified
  `prohibited-tactic`, refused at write time and per named element.
- `launch-clickup-sync`: a step is projected only once released.
- `launch-step-automation`: a handler is invoked only once its step is
  released.
- `launch-admin`: a launch's detail page distinguishes a step that has not
  yet started, and says what it is waiting for.
- `launch-instance`: the launch report carries release on each step entry,
  with what an unreleased step waits for; a step **whose start gate the
  launch has not reached** is neither overdue nor a reason to report the
  launch date at risk. A step held only by an unresolved dependency stays in
  both — it is the shape a real hold-up takes, and nothing else would report
  it.
- `playbook-admin`: the step form carries both new fields, and every rule
  they can provoke attributes its fault.

## Impact

**Domain.** `StepDefinition` gains two fields — `starts_at_gate: str | None`
and `after_steps: tuple[str, ...] = ()`, the latter normalised in
`__post_init__` exactly as `assignees` already is. New load-time faults in
`_step_faults`, plus one traversal answering cycles and the transitive gate
rule together. The release predicate lands on `Launch` beside
`unsatisfied_conditions`, where there is no clock.

**Application.** `playbook_authoring` gains a per-element `after_steps`
check alongside `assignee_faults` and `_registration_faults`.

**Infrastructure.** `converge_launch` and `_walk_launch` each consult the
predicate. `PlaybookStep` gains a nullable `starts_at_gate` column and an
`after_steps` JSONB column defaulting to a list, mirroring `assignees`. Two
Alembic revisions: the schema, then the curated backfill. The playbook admin
form gains a gate select and a multi-select over the `active` steps — the
latter grouped by gate and excluding the step being edited, since it ranges
over ~95 options rather than the roster's handful.

**Presentation.** `launch.html` renders a mark on an unreleased step. The
page already carries `blocking` as "Blocks its gate" and the `Blocked`
outcome label; a third sense of "blocked" would make the surface unreadable,
so the wording is *starts*, never *blocked*.

**Documentation.** `docs/deferred-work.md`'s "A step cannot say when it may
start" entry is removed on archive, the field having been named `after_steps`
in every artifact here rather than the entry's singular `after_step`.
