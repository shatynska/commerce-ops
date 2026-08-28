## Why

**A launch's history is not retained.** `launch_step_progress` is keyed
`(product_id, step_id)` and replaced on every recording — `launch_run.py`
states the rule plainly, "a later recording replaces the stored outcome"
— so a step's earlier states are gone the moment a new one is recorded.
Gate approvals and metric attestations are likewise one row per gate and
per (gate, metric): the current answer survives, the sequence that
produced it does not.

One table escapes this. `automated_step_results` keeps every settled row
("Settled rows are kept, never deleted"), so the steps that run
themselves have a full record and the steps people do have none. The
asymmetry is backwards: a person's work is the part nobody can
reconstruct afterwards.

Meanwhile **the occurrences already exist and are thrown away.** Every
command on the `Launch` aggregate returns the events it produced, every
write use case propagates them, and `launch_run.py` records the state of
affairs exactly: "**Events are returned, not collected** ... no dispatch
infrastructure exists yet." Nothing consumes them.

What this costs is not only history. A refused advance carries
`GateBlocked.unsatisfied` — the precise list of what a launch was waiting
for at that moment — and it is unrecoverable afterwards, because
unsatisfied conditions are recomputed from current state. Once a
condition is satisfied there is no way to learn that it once blocked an
advance, or when, or for how long. That is the single most diagnostic
thing a launch produces, and it is discarded as it is raised.

## What Changes

- **A launch journal**: an append-only record of what happened to one
  launch, retained independently of the state that produced it.
- **Every command the launch context accepts appends an entry** — a
  launch started, a step outcome recorded, a metric condition attested, a
  gate approval recorded, a gate opened, a graduation, a launch date
  moved. Coverage is deliberately not limited to the commands that
  already return an event: recording an approval, recording an
  attestation and recording a non-terminal step outcome each produce
  none today, and each is a moment someone reading a history needs. An
  approval that was recorded and a gate that has not opened are the two
  facts that together explain a launch standing still.
- **A refused advance is journaled too**, naming the gate and every
  unsatisfied condition, for the reason given above. The command still
  fails exactly as it does now.
- **Entries carry the labels the occurrence concerned, captured when it
  happened** — the step's name, not only its identifier. An entry must
  stay readable after the served playbook has moved on: a step retired
  later would otherwise read as `lp.listing.007` for the rest of that
  launch's life, unrecoverably, which is the same defect the launch
  report is separately being fixed for. A label is a fact about the
  occurrence, not a rendered sentence. **One exception, taken
  deliberately:** a refused advance's unsatisfied conditions are stored
  as the domain composes them, and those names identify a step by
  identifier. Carrying names there would mean reshaping the occurrence
  the domain raises for a blocked advance, which this change leaves
  alone — see design.md Decision 7 for what a later change would do
  instead.
- **Entries store structure, never rendered prose.** Wording is composed
  at read time from what the entry carries, so improving how an entry
  reads improves every past entry rather than leaving history phrased the
  way it was first written.
- **Entries are appended, never replaced or deleted.** A second
  occurrence of the same kind on the same step appends; it does not
  overwrite. That is the whole difference between the journal and the
  state it records.
- **A failed append never fails the command it records, and never
  disturbs that command's own work.** Containment is not only catching
  the exception: a failed write must not leave the command unable to
  finish what follows it — most sharply the catalog stamp that
  `launch-instance` requires *after* a graduating advance is persisted. A
  journal that could break a graduation would be the outage this
  guarantee exists to forbid, caused by the mechanism meant to prevent
  it. A failure is reported to the application log at error severity,
  naming the launch and the occurrence that went unrecorded.
- **One launch's journal is readable**, most recent first, under the
  caller's access scope.

No **BREAKING** changes. No existing route, stored shape or write
behaviour changes; every command keeps its arguments, its effect and its
failure modes, and additionally *requires* the journal it appends to —
a required argument, not an optional one, so that no caller can omit the
journal silently (design.md — Decision 1). The migration is additive.

**Every recording path already funnels through one use case** — verified:
the ClickUp reconciliation job, the ClickUp webhook intake, the
automation pass and the automation confirmation all record through
`record_step_outcome` rather than reaching the aggregate themselves. So
journal coverage of automated and ClickUp-sourced recordings follows from
a single append site, and no recording path is rerouted.

## Capabilities

### New Capabilities

- `launch-journal`: the append-only record — which occurrences are
  journaled, what an entry carries and for how long it stays legible,
  that entries are never replaced or deleted, that a failed append
  neither fails nor disturbs the command it records, and how one
  launch's journal is read.

### Modified Capabilities

None. `launch-instance` keeps every requirement unchanged: the commands
this change journals keep their arguments, their effects and their
returned events, and the journal observes them without altering what any
of them guarantees.

## Impact

**Affected code**

- `launch/application/use_cases.py` — an append at each accepted command,
  and one at the refused advance, built from the arguments, returned
  events and caught exception the use case already holds.
- `launch/application/ports.py` — the journal port.
- `launch/application/` — the entry the append site builds, and the read
  that composes an entry's wording from what it carries.
- `launch/infrastructure/driven/models.py` and a new Alembic migration —
  the journal table.
- `launch/infrastructure/driven/` — the journal repository.
- **One composition line in each of the five adapters that build a launch
  write** — `slack_entry.py`, `clickup_sync_job.py`, `clickup_webhook.py`,
  `automation_pass.py`, `automation_confirmation.py`. Each already builds
  `LaunchRepository(db_session)` itself, and now builds the journal
  repository beside it. Nothing else in them changes: no recording path
  is rerouted, no request handling moves, no behaviour differs. The
  journal is a required argument rather than a defaulted one precisely so
  that a sixth adapter cannot omit it silently (design.md — Decision 1).

**Explicitly untouched**

`launch/domain/` gains nothing. The domain's events are occurrences other
contexts act on — `LaunchGraduated` stamps the catalog — while the
journal's entries are occurrences a person reads; emitting a domain event
so that a history table has something to store would make the domain
serve a persistence concern. Every entry this change records can be built
from what the application layer already has.

Also untouched in behaviour: the ClickUp projection and its intake, the
automation pass and its confirmation path, every authoring write, and
every admin surface. Four of those five adapters — the ClickUp intake and
projection, the automation pass and its confirmation path; `slack_entry`
is the fifth — gain the one composition line named above and nothing
more. Their diffs are a line each, and the journal is invisible to what
they do.

**Coordination — this change is sequenced before `add-launch-tracking-pages`**

That change's launch detail page renders this journal, and its
requirement to do so is written against the read this change adds. It
carries no other dependency on this one, so the two are reviewable
separately, but the pages cannot be implemented until this lands.

This change exists because `add-launch-tracking-pages` was reviewed and
found to bundle two concerns — an append-only journal that changes the
write path of every accepted command, and two read-only pages that cannot
break a live launch. The journal is the half that carries the risk, and
it is split out so that risk is reviewed on its own.
