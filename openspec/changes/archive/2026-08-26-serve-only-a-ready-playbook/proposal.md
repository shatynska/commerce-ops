## Why

A step set that is coherent but not yet finished cannot be represented. The
gate-holding floor — *every gate has at least one `active` blocking step* —
is enforced inside `LaunchPlaybook`'s constructor, so a playbook whose steps
are all `draft` does not merely fail to serve a launch: it fails to **exist**.

That makes the obvious way to adopt a large step set impossible. Seeding the
reference document's 358 rows as `draft` and activating them after review is
the workflow the four-status vocabulary was introduced for — `draft` means
"written down, not yet in play" — and it is unreachable. Worse, it is
unreachable in a way that cannot be climbed out of: write validation
reconstructs the whole candidate set, so activating the *first* step of an
all-draft set still leaves seven gates unheld and the write is refused with
seven faults. The set freezes. The only escape is to seed a hand-picked
active spine, which pre-commits exactly the review the seed exists to enable.

The floor is a good rule in the wrong place. Its subject is not whether the
step set is internally consistent — it is whether the set is *complete enough
to hold a launch*, which is a fact about readiness, not coherence. This
project has already drawn that distinction twice, and drawn it the other way:
handler registration is checked at activation and reported at startup rather
than at load, and assignee rules are write-time only, both because — in the
specification's own words — a rename or a deactivation "would otherwise make
every stored playbook unloadable, taking down launches to report a
deployment fault". The gate-holding floor is the one rule of that kind still
enforced at construction.

## What Changes

- **The gate-holding floor stops being a coherence rule.** `LaunchPlaybook`
  construction continues to enforce every other rule in the incoherence list
  — identifiers, gates, names, the automation pair, the prohibited-tactic
  rule, metric-condition thresholds — and no longer rejects a set for leaving
  a gate unheld. A playbook of 358 drafts loads.
- **Readiness becomes a query on the playbook.** The set of gates holding no
  `active` blocking step is readable from the aggregate. Empty means the
  playbook is ready to serve; non-empty names exactly what is missing.
- **Serving a launch requires a ready playbook; authoring does not.** The two
  reads that already exist divide along this line and keep their present
  callers: the authoring surface reads the whole authored set and is never
  refused, while every read taken on a launch's behalf — advancing one,
  projecting one, or reporting on one — requires
  readiness and declines when it is absent. Declining is distinct from
  failing: a playbook that is *absent* remains an error, exactly as it is
  today.
- **A refusal names the gates, and carries the set it declined to serve.**
  Not-ready is reported as its own condition, distinguishable from
  incoherence, carrying the unheld gate identifiers so the message says which
  gates still need a blocking step activated. It carries the playbook too: a
  consumer that is declining to act may still owe an obligation that turns on
  what the set contains, and the alternative is a second read or a guess.
- **The floor becomes one-directional on the write path.** A write against a
  set that is already ready is still refused when it would leave a gate
  unheld — so a running launch cannot lose its playbook to one authoring
  action, which is the protection today's rule actually buys. A write against
  a set that is *not* ready is not refused for that reason, which is what
  makes an all-draft set reachable from its own starting state. It is always
  permitted to move toward being served, never to move a served set away from
  it in one write.

Explicitly not in scope: seeding the reference document's step set, and any
change to the gate sequence, the opening modes, or the step field set. This
change makes that seed possible; it does not perform it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-playbook`: the gate-holding floor moves out of the coherence rules
  and becomes a property of the served set — a playbook that leaves a gate
  unheld loads, and is not served. Gains a requirement for how readiness is
  established and what a not-ready playbook does to a consumer that asks for
  one. The lifecycle-status requirement is amended in step, since it states
  the un-activation refusal unconditionally today.
- `playbook-authoring`: the gate-holding rule leaves the coherence set and
  becomes one-directional — enforced against a set that is already ready,
  and not against one still being built. Retiring or un-activating a gate's
  last blocking step stays refused in a ready set, and is permitted in one
  that is not.
- `launch-entry`: starting a launch against a playbook that is not ready is
  refused where the request was made, naming the gates that hold no active
  blocking step, rather than surfacing a load failure.
- `launch-clickup-sync`: the projection and reconciliation passes decline
  against a playbook that is not ready, recorded as succeeded rather than
  failed. Webhook intake during a stand-down records nothing, and what it does
  to the task's retained observed state splits by whether the step is served:
  a served step's task is left untouched, so the completion is recovered by
  reconciliation rather than silently lost; a non-served step's task is
  observed exactly as outside a stand-down, so a closure that happened while
  the step was out of the served set is consumed and never replayed. Three
  requirements of the capability gain a clause naming the stand-down, as the
  retired-step carve-out is already named in them.
- `briefing`: a launch source that cannot supply reports at all is reported as
  such rather than assembling into a briefing with no items, which the
  clean-day rule would otherwise deliver as silence. The assembly-failure
  requirement is amended in step, so the new condition is carved out of it by
  name rather than distinguished only in prose.

## Impact

- `launch/domain/launch_playbook.py` — `_gate_holding_faults` leaves the
  constructor's fault list; the aggregate gains the readiness query and a
  distinct not-ready error type, which carries the unheld gates and the
  playbook it was built from.
- `launch/infrastructure/driven/playbook_repository.py` — `get()` (the
  serving read) enforces readiness; `load()` (the authoring read) does not.
- `launch/infrastructure/driving/slack_entry.py`, `clickup_sync_job.py` and
  `clickup_webhook.py` — three of the serving-read callers, each handling
  not-ready as a decline. In the webhook the readiness check must precede the
  observation that advances a task's retained state, which today is committed
  first.
- `src/commerce_ops/worker.py` — outside the `.importlinter` containers, which
  is why it may name both sides. Its serving read is the daily briefing's
  launch-report source, not a sync pass, so it translates the not-ready
  condition into one `briefing` owns.
- `briefing/domain/attention.py`, `briefing/application/__init__.py`,
  `briefing/application/ports.py` and
  `briefing/infrastructure/driving/daily_briefing_job.py` — a briefing-owned
  condition meaning "the launch source cannot supply reports", exported,
  documented beside the port it belongs to, and handled ahead of the
  assembly-failure branch. `briefing` goes on naming nothing from `launch`,
  which is its own convention rather than something the linter checks: the
  contracts forbid only `launch.domain` and `launch.infrastructure`.
- `src/commerce_ops/check_step_handlers.py` — moves off the serving read
  entirely. It wants the *authored* set to report unregistered handlers, so it
  reads through the authoring read and keeps reporting them in a state this
  change makes reachable. A consequence to accept: it no longer constructs the
  aggregate, so an incoherent stored set no longer aborts the container start
  chain. No accepted write can persist one, but a hand-edit or a rollback
  could, and this is where that would previously have been caught.
- `launch/infrastructure/driving/playbook_admin.py` — unchanged; it already
  reads through `load()`.
- `launch/application/activation_readiness.py` — `report_unregistered_handlers`
  gains a caller reading the authored set. The activation-blocker report is
  deliberately untouched: it has no production caller today, so extending it
  would add a requirement nobody can observe. Where an operator meets the
  wall — starting a launch, and the daily briefing — the unheld gates are
  named directly.

No schema change, no migration, no data change, and no new `import-linter`
contract.

## Sequencing

Blocks the seed of the reference document's step set, which depends on an
all-`draft` set being representable. That seed must arrive outside the
authoring use cases: under the one-directional rule no accepted write takes
today's ready set to a not-ready one, so the all-`draft` state is reachable
only by a seeding path that writes the set directly — a constraint the seed
change carries, and the reason it is sequenced after this one.

Independent of `admin-presentation-vocabulary`, which touches only
presentation.
