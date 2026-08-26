## Context

See proposal.md — *Why*. The constraints that shape the approach:

- `LaunchPlaybook.__post_init__` gathers four fault sources and raises
  `InvalidPlaybookError` with all of them. Three concern the set's internal
  consistency; `_gate_holding_faults` concerns whether the set is finished.
- `playbook_authoring._validate` reconstructs the aggregate over the whole
  candidate set on every write, so any construction rule is automatically a
  write rule. This is why the all-draft state is not merely invalid but
  inescapable.
- Two reads already exist on `PlaybookRepository` and divide by purpose:
  `load()` returns records for authoring (used by `playbook_admin`), `get()`
  constructs the aggregate for serving (used by `slack_entry`,
  `clickup_sync_job`, `clickup_webhook`, `worker`, `check_step_handlers`).
  The division is *almost* the one this change needs: two of those five
  callers are not serving a launch at all — see the consumer table below.
- `reorder_step` does not route through `_accept`: it calls `_validate`
  directly (`playbook_authoring.py:634`), because a reorder changes only
  `display_order`. That exemption is correct and must survive.
- The precedent for this split is stated twice in `launch-playbook`'s own
  spec: handler registration is checked at activation and reported at
  startup, and assignee rules are write-time only — both because a rule
  whose subject is not the step set would otherwise make stored playbooks
  unloadable.

## Goals / Non-Goals

**Goals:**

- An all-`draft` step set is a representable, loadable, editable state.
- Every path taken on a launch's behalf refuses a playbook that
  cannot hold one, and says which gates are missing.
- Recovery from a not-ready set is always possible through the ordinary
  authoring surface — no state requires a migration or a manual edit to
  escape.

**Non-Goals:**

- Weakening what a gate means. A gate with no blocking obligations still
  must not open; this change moves *where* that is prevented, not whether.
- Any change to the readiness rules for individual steps (brief, handler,
  assignees). Those already sit at activation and stay there.
- Turning readiness into a stored flag. It is derived from the step set on
  every read.

## Decisions

### Readiness is derived, never stored

The unheld gates are computed from the step set each time the aggregate is
built — the same computation `_gate_holding_faults` performs today, moved
from the fault list to a property. Nothing persists a "ready" bit.

A stored flag would need maintaining on every write and could disagree with
the steps it summarises; the derivation is eight set-membership tests over
a collection already in memory. *Alternative considered:* a column on
`playbook_step_set` updated by each write — rejected as a second source of
truth for a fact the first source answers in microseconds.

### The enforcement point is the serving read, not a convention

`PlaybookRepository.get()` — documented as "the live playbook" — raises
`PlaybookNotReadyError` carrying the unheld gate identifiers.
`PlaybookRepository.load()` is untouched, so the authoring surface never
sees the error.

This needs no new seam: the split already exists. Its callers are *nearly*
correct — `check_step_handlers` moves to `load()` because it reads the
authored set, not a served one, which leaves `get()` meaning exactly "a read
taken on a launch's behalf: advancing one, projecting one, or reporting on
one". The briefing's report read is the third kind, which is why `worker`
belongs here and the startup handler check does not.

Putting the check in the use cases instead would mean every future use case
has to remember it, which is exactly the kind of rule that gets forgotten.

*Alternative considered:* change `get()`'s return type to
`LaunchPlaybook | NotReady`, so `mypy` forces each caller to narrow rather
than relying on a caught exception. Rejected because the `Playbooks` port
that the application layer consumes is synchronous and returns a
`LaunchPlaybook`; widening it would push the not-ready case into every use
case that takes the port, when the whole point is that a use case should
only ever receive a playbook that can serve. The four serving reads that
remain after `check_step_handlers` moves — `slack_entry`,
`clickup_sync_job`, `clickup_webhook` (three driving adapters) and
`worker` (the composition root's briefing reader) — handle it at their own
entry points instead, and each gets a test.

### Not ready is a distinct error, not a fault list

`PlaybookNotReadyError` is its own type, not an `InvalidPlaybookError`. A
consumer must be able to tell "this playbook is broken and someone should
be paged" from "this playbook is still being written and will serve when it
is finished" — the first is a defect, the second is an expected state of a
system being set up.

### Each consumer declines in the idiom it already has

| caller | behaviour when not ready |
|---|---|
| `slack_entry` | refuse the start where the request was made, naming the unheld gates — the capability already requires rejections to surface in Slack |
| `clickup_sync_job` | stand the pass down, run recorded as succeeded, stand-down logged |
| `clickup_webhook` | acknowledge, record nothing; leave the retained observed state alone for a **served** step, advance it for one that is **not** |
| `worker` | not a sync pass — this is the briefing's launch-report read; behaviour belongs to `briefing` |
| `check_step_handlers` | **moves off `get()` entirely** — it wants the authored set |

Three of these needed correcting against the code rather than against the
shape the split suggested, and each correction is load-bearing.

**A refusal carries the playbook, because declining is not the same as
having nothing to say about the set.** The webhook owes two opposite
obligations depending on the step: a *served* step's task must be left
unobserved so reconciliation can recover the completion, while a *non-served*
step's task must be observed so the closure is consumed and never replayed —
`launch-clickup-sync` spec:263 requires the second in as many words, and the
one-directional rule this change introduces makes a step leaving `active`
easier, so it widens exactly that window. A blanket non-observation rule
would fabricate a `Satisfied` outcome for a closure that happened while the
step was outside the launch's obligations.

Telling the two apart needs the playbook, which under this change `get()`
refuses to return. So `PlaybookNotReadyError` carries it, alongside the
unheld gates. The set is coherent — the only thing wrong with it is that it
cannot hold a launch — so there is nothing unsafe about handing it back with
the refusal.

*Alternative considered:* amend spec:263 to say a stand-down consumes
nothing, accepting that such a closure may be replayed. Rejected: it trades
away a guarantee that exists specifically to prevent fabricated completions,
to save a field on an error.

*Alternative considered:* a second read (`get_even_if_unready()`). Rejected
as a method whose only correct use is inside a refusal handler, and which
reads as a way around the refusal everywhere else.

This does not reopen the rejected `LaunchPlaybook | NotReady` return type.
That rejection was about the synchronous `Playbooks` port the application
layer consumes, which still only ever yields a servable playbook; the
webhook is a driving adapter and never holds the port.

**The webhook's ordering is the whole of the "not lost" claim.** Today
`clickup_webhook.py:181` calls `mapping.observe(...)` — which commits
(`clickup_mapping.py:150`) — and only then reads the playbook at `:183`. A
decline dropped in at the existing call site would leave the retained state
already advanced, so the later reconciliation sees no transition and records
nothing: the completion vanishes with nobody told. Reconciliation recovers a
missed completion *only* as a transition of retained state, so the readiness
check must precede the observation. This is why the delta states the
non-observation as a requirement rather than leaving it to the implementation
— it is the premise the decision to acknowledge rather than fail rests on.

**`worker`'s read is the briefing's, not the sync's.** Its `get()` sits in
`_read_launch_reports`, assigned to `daily_briefing_job.read_launch_reports`
at `worker.py:129`. "Skip the pass" there means the briefing assembles from
nothing, and `briefing`'s own rule that a clean briefing is not delivered
turns that into silence — a not-ready playbook reading as a clean day, every
day of the bootstrap. So `briefing` gets a delta of its own rather than being
changed by implication.

**`check_step_handlers` should never have been a `get()` caller.** It reads
`playbook.authored_steps` purely to report unregistered handlers. Putting
readiness on its read would suppress the startup report that `launch-playbook`
requires, in exactly the state this change makes reachable — an `active`
`automated` step can exist in a not-ready set, since activation checks the
brief, the handler and the registry but never the gate holdings. It moves to
the authoring read, which is what it always wanted, and leaves the serving-read
caller set at four.

### The briefing learns the condition through a type briefing owns

Two constraints stack here, and only the first is mechanical.
`.importlinter`'s `briefing-application-boundary` and
`briefing-infrastructure-boundary` forbid `commerce_ops.launch.domain` and
`commerce_ops.launch.infrastructure` — but *not* `launch.application`, whose
public surface briefing would be permitted to call. `PlaybookNotReadyError`
is a `launch.domain` type (task 1.3), so catching it directly is forbidden
outright; re-exporting it from `launch.application` would satisfy the linter.

The second constraint is why we do not do that. `briefing` names nothing
from `launch` at all today, by its own deliberate convention: the
`LaunchReports` port is typed `Sequence[Any]`, its docstring saying that
naming launch's report type "would make briefing's ports depend on launch's
application module for a type alone". Threading an exception type through
the same boundary would give up exactly what that docstring is protecting,
for a type alone.

The seam is the one this codebase already uses for every other launch fact
the briefing needs. `worker.py` sits outside every `.importlinter`
container — which is why it may name both sides at all — and already
composes `read_launch_reports`, `read_product` and `read_people` across the
boundary. It gains one more translation: catch `PlaybookNotReadyError` and
raise a briefing-owned condition carrying the gate identifiers as opaque
strings.

That condition is a sibling of `BriefingError`, which already lives in
`briefing.domain.attention` and is already re-exported from
`briefing.application`. `daily_briefing` handles it ahead of its generic
assembly-failure branch, so the succeeded-run path is chosen before the
failed-run path can claim it.

*Alternative considered:* have `worker.py` post the message itself and
return `()`. It needs no new type — `worker.py` already holds the Slack
notifier. Rejected because the briefing would then genuinely be assembled
and genuinely be clean, so the run would stay green by the clean-day rule
rather than by a decision anyone made, and the requirement would have to be
rewritten to permit the very silence it exists to prevent.

*Alternative considered:* report the condition from a separate scheduled
check instead of through the briefing. Rejected: it duplicates a schedule
and reopens the once-per-outage question this design has already settled.

Note what the requirement is careful to say: the source reports that it
**cannot supply reports**, not that a playbook is unready. Briefing never
learns what a gate is; it treats the carried identifiers as opaque strings
and names them in the message. The adapter translates.

A note on one scenario title. Under *An incoherent playbook is rejected
against each step's status*, the scenario *A gate with no active blocking
step is rejected* keeps a title that reads like the old load-time rule while
its body says the rejection happens at the serving read. The title is not a
choice: `openspec validate` requires a MODIFIED requirement to carry every
scenario the live spec has, matched by title, so renaming it would drop it.
The body is where the contract lives.

That the recognising type is briefing's own is a source-structure property
rather than a behaviour, so it is recorded here and not as a scenario. What
guards it is `lint-imports` for the two forbidden edges, plus review for the
convention the linter does not encode.

The live *A failure to assemble is surfaced, not treated like a delivery
failure* is amended in the same delta rather than left to be distinguished
by prose: its antecedent ("the data it derives from cannot be read") would
otherwise cover this condition and demand a failed run, giving the
capability two requirements a reader could apply to one event with opposite
outcomes.

### One voice reports the condition; the rest stand down quietly

A stood-down sync pass is recorded as **succeeded**, because `scheduled-jobs`
records only success or failure and a failure would put a working deployment
into retry and overdue reporting for something retrying cannot fix.

The cost is real and is accepted rather than worked around: each stood-down
pass refreshes the work's last success, so overdue reporting never fires while
the playbook is not ready. The sync would look permanently healthy while
nothing syncs.

What makes that acceptable is that the condition is reported elsewhere, loudly
and on a schedule: the daily briefing posts a message naming the unheld gates
on every run while they persist. That is deliberately not suppressed to
once-per-outage — no state is kept to tell a continuing condition from a new
one, and the proposal admits none. A daily "these gates still hold no active
blocking step" during a bootstrap is a true and actionable statement, not an
alarm, and it is what stops the deployment being silent.

*Alternative considered:* a third run outcome for `scheduled-jobs` so a
stand-down is neither success nor failure and overdue detection survives.
Rejected as a change to a second capability's core record shape, for a
condition another capability already reports; if stand-downs ever become long
enough for the sync's own staleness signal to matter, that is the follow-up.

### The write-path rule is a ratchet, not a removal

A write is refused for leaving a gate unheld **only when the set it starts
from is already ready**. Against a not-ready set the same write is accepted.

The bootstrap only needs the second half. Dropping the first half as well
would be a larger behaviour change than the problem calls for, and would
give up the protection today's rule genuinely buys: a running launch cannot
have its playbook pulled out from under it by one authoring action.
Concretely, the ratchet is what makes an all-draft set reachable —

```
358 drafts        not ready → not ready    accepted (7 gates still unheld)
… activate #8     not ready → ready        accepted (moving toward served)
un-activate one   ready     → not ready    REFUSED
```

*Alternative considered:* remove the rule from the write path entirely and
let a stall be the feedback. Rejected: it discards a protection for no gain,
since every state the bootstrap needs is already reachable under the ratchet.

The objection that argued against a ratchet earlier does not survive this
change. It would have made the gate-holding rule a function of the prior set
as well as the candidate, breaking "the same rules at load and at write" —
but once the rule is no longer a load rule at all, there is no symmetry left
for it to break. It is a write-path rule now, and a write is exactly the
place where a prior state is available to compare against.

Cost: `playbook_authoring._accept` must judge the loaded set as well as the
candidate. Both are already in hand at that point — the write loaded the set
it is mutating — so this is one extra readiness computation, not extra I/O.

### `launch-instance`'s gate rule is unchanged and now genuinely protected

`launch-instance` requires that a gate opens only when every blocking
condition attached to it is satisfied. A gate with zero conditions
satisfies that vacuously — which is the hazard the floor was written for.
That hazard does not return: a launch can only be advanced through a
playbook obtained from `get()`, and `get()` refuses a set that leaves any
gate unheld. The protection moves from "this set cannot exist" to "this set
cannot be served", and every path that could open a gate goes through the
second.

## Risks / Trade-offs

- [A set can still reach not-ready without a write — nothing else changes it,
  but a future feature might] → Readiness is derived on every read, so any
  path that reaches the state is caught at the serving boundary rather than
  depending on the writes that produced it. The ratchet is a convenience for
  authors, not the thing the guarantee rests on.
- [The ratchet refuses a write whose recovery is a second write the author
  may not know to make] → The refusal names the gate that would be left
  unheld. This is today's behaviour and today's message; the change does not
  make it worse.
- [Overdue reporting cannot see a sync that stands down indefinitely] →
  Accepted and recorded above; the daily briefing reports the condition on
  every run instead.
- [A completion is lost if the readiness check lands after the observation]
  → The delta states the non-observation as a requirement, and a test covers
  the close-during-stand-down then reconcile sequence end to end, so the
  ordering cannot regress silently.
- [The webhook's membership check tests the authored set, not the served set,
  so a retired step's delivery is refused downstream rather than acknowledged]
  → Pre-existing and deliberately out of scope; task 4.3 records it so the
  implementer does not "fix" it while moving the readiness check, and test
  5.10 uses a step absent from the authored set rather than a retired one.
- [A future `get()` caller forgets to handle not-ready and crashes] → The
  call sites are enumerable (four after this change) and each is covered by
  a test. A crash here is loud and localised to one caller, not a corrupted
  launch.
- [Removing a construction rule weakens a domain invariant] → The invariant
  it protected is preserved at the serving boundary, which is the only place
  it was ever load-bearing. A playbook that cannot serve is now simply
  unserved rather than unloadable, and the incoherence rules that describe
  the set's own consistency are untouched.
- [`playbook-admin` describes the unheld-gate refusal in three places that
  this change does not modify] → All three were checked. *A blocked
  retirement explains itself* (spec:345) and *A fault about the step set
  marks no field* (spec:733) both open "WHEN … is rejected because", so they
  are conditional on a refusal occurring and the ratchet does not touch them.
  Spec:599 is weaker: its appositive enumerates what a refused change *is* —
  "an activation whose step lacks what its kind requires, or a de-activation
  that would leave a gate unheld" — and after this change the second is
  refused only from a ready set. Nothing observable on the page changes, so
  the wording is accepted as stale rather than amended; recorded here so a
  later reader sees both the check and what it found.

## Migration Plan

None. No schema change, no data change, no migration revision.

On deploy the current set — 95 `active` `human` steps covering all eight
gates — is already ready, so `get()` returns exactly what it returns today
and no consumer takes the new path. The change is only observable once a set
that leaves a gate unheld exists, which no shipped state produces.

Rollback is the ordinary revert: restoring `_gate_holding_faults` to the
constructor's fault list restores today's behaviour, and any set stored
under the new rules that leaves a gate unheld would then fail to load. Under
the ratchet that state is not reachable from a ready set by any accepted
write, so a rollback taken before the reference step set is seeded finds the
database exactly as it left it. After that seed, a rollback would strand an
all-draft set as unloadable — which is the dependency the seed change
carries, and the reason it is sequenced after this one rather than beside
it.
