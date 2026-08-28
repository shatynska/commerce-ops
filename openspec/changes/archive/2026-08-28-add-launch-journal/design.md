## Context

See `proposal.md` — Why, for the motivation. What shapes the approach is
the code as it stands:

- **Every launch command is a plain async function over ports** in
  `launch/application/use_cases.py`, taking `LaunchStore` and, where it
  needs definitions, `Playbooks`. There is no unit-of-work object, no
  command bus and no dispatch: `launch_run.py` states it plainly —
  "**Events are returned, not collected** … no dispatch infrastructure
  exists yet."
- **Repositories commit their own writes.** `LaunchRepository.save`
  calls `commit()`; `database.transaction()` exists precisely as the
  stopgap that makes two such writes land together, by joining them to
  one outer transaction with `join_transaction_mode="create_savepoint"`.
  `docs/deferred-work.md` records the proper fix as deferred.
- **Five adapters compose a launch write**: `slack_entry.py`,
  `clickup_sync_job.py`, `clickup_webhook.py`, `automation_pass.py` and
  `automation_confirmation.py`. Each builds `LaunchRepository(db_session)`
  itself; `worker.py`'s sixth construction is a read.
- **Every recording path funnels through `record_step_outcome`** — the
  reconciliation job, the webhook intake, the automation pass and the
  automation confirmation all call it rather than reaching the aggregate.
- **The application layer holds no clock.** `advance_gate`,
  `start_launch` and `move_launch_date` take no timestamp; the commands
  that do (`record_step_outcome`, `approve_gate`,
  `record_metric_attestation`) carry one inside the value the caller
  supplies.
- **`launch.application` may not import `launch.infrastructure`**
  (`.importlinter`'s `module-layers` contract), which is why ports exist
  at all.

## Goals / Non-Goals

**Goals** (design-level, beyond the proposal's scope):

- One append site per command, in the application layer, reached without
  global state and without an adapter being able to forget it silently.
- Containment strong enough to survive a database fault, not only an
  exception: the command's session must stay usable for the work that
  follows the append.
- A stored shape that keeps entries legible for the life of a launch
  without depending on the playbook still serving what they name.

**Non-Goals:**

- Dispatch infrastructure. This change does not introduce an event bus,
  and does not turn the returned events into something subscribed to;
  the journal is written where the command runs.
- Journaling anything outside the launch context's own commands —
  playbook authoring writes, roster writes, admin surfaces, and the
  automation runtime's own pending-result lifecycle, which already keeps
  every settled row.
- Pagination, filtering or search over a journal. One launch's journal
  is read whole.
- Rendering. How a page or a Slack message lays entries out belongs to
  whoever reads them; this change composes the sentence, not the markup.

## Decisions

### 1. The journal is its own port, passed explicitly to each command

`LaunchJournal` joins `LaunchStore` and `Playbooks` in
`launch/application/ports.py`, and each journaled command takes it as a
**required keyword argument**. The five write-composing adapters gain one
line each — `journal=LaunchJournalRepository(db_session)`.

*Alternatives considered.*

- **Fold the append onto `LaunchStore`.** `LaunchRepository` already
  holds the session, so no adapter would change and `proposal.md`'s
  "explicitly untouched" list would stand as written. Rejected: it puts
  a launch's history behind the port that persists the aggregate's
  current state, which is exactly the distinction this capability
  exists to draw, and it would make roughly thirteen test files grow a
  method on their in-memory launch stores.
- **A keyword argument defaulting to a journal that appends nowhere.**
  Rejected: an adapter that forgets the wiring then journals nothing,
  silently, and no test catches it — the failure the containment
  requirement exists to prevent, arriving through the back door. A
  required argument makes the omission a type error and a test failure.
- **A module-level provider configured at composition time**, on the
  `HANDLERS` registry precedent. Rejected: `HANDLERS` is a registry of
  named, statically-declared handlers; a mutable global holding a
  session-bound repository is a different thing, and it would make the
  append site untestable without monkeypatching module state.

*This corrects `proposal.md`.* Its Impact section is amended: the five
adapters' recording paths, request handling and behaviour are untouched,
but each gains the one composition line above.

### 2. The append happens in the use case, after the command's own persistence, before anything cross-module

Order inside a command is: invoke the domain → `launches.save(...)` →
append the entry (contained) → any cross-module work. Concretely, in
`advance_gate`: save the advanced launch, append the entry, then stamp
the catalog.

Appending after the save is what lets containment discard a failed
append without risking the command's own work: by the time the append
runs, that work is already committed. Appending before the cross-module
stamp is what makes the containment requirement's sharpest scenario
checkable at all — a journal failure between the two must leave the
stamp performed.

The refused advance is the one exception to "after the save", because
there is nothing to save: `advance_gate` catches `GateBlockedError`,
appends, and re-raises unchanged.

### 3. Containment rolls the session back, then logs

The append is wrapped in `except Exception`, and the handler does two
things before returning: it rolls the session back through the journal
port, and it logs at `error` naming the launch and the occurrence.

The rollback is the part that is easy to omit and impossible to do
without. A failed `INSERT` leaves the `AsyncSession` in a state where
every later statement raises `PendingRollbackError`; catching the
exception alone would leave the graduation's catalog stamp failing on a
poisoned session — the journal breaking a graduation, which is the exact
outage the containment guarantee forbids. `contain-a-failing-launch`
(archived, 2026-08-27) established the same rollback-then-continue shape
for the completion pass, and its task 1.2 records the trap this creates
for tests: *a fake that merely raises reproduces the exception but not
the failed transaction state the rollback exists for*, so a test built on
one passes whether or not the rollback was written. The tests for this
change inherit that constraint (see `tasks.md`).

Where the rollback itself raises, that too is caught and logged; the
command still returns. There is nothing further this layer can do, and a
journal must never be the reason a launch command fails.

### 4. One table, `launch_journal_entries`, ordered by an append sequence

| column | type | note |
| --- | --- | --- |
| `sequence` | `BIGINT` identity, PK | append order, and the tie-break for equal moments |
| `product_id` | `UUID` FK → `launch_positions.product_id`, `ON DELETE CASCADE` | the launch the entry belongs to |
| `occurred_at` | `TIMESTAMPTZ NOT NULL` | the moment the entry names |
| `kind` | `VARCHAR NOT NULL`, checked | the occurrence vocabulary below |
| `actor` | `VARCHAR NULL` | who the occurrence named, where it named anyone |
| `source` | `VARCHAR NULL` | the provenance source, where the occurrence carried one |
| `subject_id` | `VARCHAR NULL` | the step, gate or metric identifier the occurrence concerned |
| `subject_label` | `TEXT NULL` | that subject's label, captured at append time |
| `details` | `JSONB NOT NULL` | the values distinguishing this occurrence from another of its kind |

*The subject, per kind.* An occurrence concerning two identifiers still
has one subject. For `metric-attested` the subject is the **metric
condition** — `subject_id` its metric identifier, `subject_label` its
threshold text — and the gate travels in `details`; the attestation is
about the condition, and the gate is which gate it was attested against.
`step-outcome-recorded` takes the step; `gate-approval-recorded`,
`gate-opened`, `launch-graduated` and `advance-refused` take the gate;
`launch-started` and `launch-date-moved` concern the launch itself and
carry no subject.

*Which kinds carry an `actor`.* Four do not, and the reason is the same
one Decision 6 gives for timestamps: the use case is never told. A
command that carries a person carries them inside a value —
`Provenance.who`, `GateApproval.approver`, `MetricAttestation.attester` —
so `step-outcome-recorded`, `gate-approval-recorded`, `metric-attested`
and `launch-graduated` (the graduation approver) have an actor, and
`launch-started`, `gate-opened`, `launch-date-moved` and
`advance-refused` have none. The proposal's Why calls a person's work the
part nobody can reconstruct, which will disappoint a reader expecting the
journal to say who *started* a launch: `slack_entry` knows the submitter
and `start_launch` is not told. Not fixed here, deliberately — passing an
actor down would change what those commands accept, which is a wider
change than a journal, and R7's "the command that produced it where the
occurrence names nobody" is written to be honest about the gap rather
than to paper over it.

`kind` vocabulary, one per accepted command plus the refusal:
`launch-started`, `step-outcome-recorded`, `metric-attested`,
`gate-approval-recorded`, `gate-opened`, `launch-graduated`,
`launch-date-moved`, `advance-refused`.

*Why a sequence rather than a UUID key.* Every other launch table keys
on what it is about; this one is about order. Two entries can name the
same moment — a batch reconciliation recording several steps with one
timestamp is the ordinary case, not the edge — and "most recent first"
has to be total. A monotonic sequence gives that for free and costs
nothing else.

*Why `ON DELETE CASCADE`.* The journal is a fact about a launch, not
about a product; a launch record that is gone leaves nothing for its
journal to be the history of, and an orphan row would outlive the
foreign key it is keyed by. The retention requirement is written to
match: retained for the life of the launch record.

*Why `details` is `JSONB` and the rest are columns.* What every entry has
in common is queryable and constrained; what distinguishes one kind from
another — an outcome and its reason, a decision and its posture, two
dates, a list of unsatisfied conditions — differs per kind and is read
only through the composer that already knows the kind. Modelling eight
shapes as eight nullable column groups would buy nothing the composer
uses. The precedent is `playbook_steps.timing_anchor`.

### 5. Wording is composed in the application layer, at read time

`read_launch_journal` returns frozen `JournalEntry` read models carrying
`kind`, `what`, `when` and `cause` — `what` and `cause` composed from the
stored facts on the way out.

Composing in `launch.application` rather than in each reader is what makes
the proposal's promise true: one place to improve, and every past entry
improves with it. Putting it in the page instead would give the Slack
surface and the briefing their own second and third wordings for the same
occurrence.

The read model carries the composed sentence and not the raw `details`
mapping, deliberately: `dict[str, Any]` on a module's public surface is
the shape `add-launch-tracking-pages`' design.md rejects, and mypy cannot
check what a reader pulls out of one. A reader that later needs structure
gets a typed field added for it, by the change that needs it.

*Field names.* `what` / `when` / `cause` are the names
`add-launch-tracking-pages` guessed at when it stubbed this read
(`test_launch_admin_detail.py::_JOURNAL_SEAM_NAMES`, and its
test-manifest's project question 7). Adopting them costs nothing and
unblocks that change's three blocked tests without a second round of
naming.

### 6. Entries that name no moment are stamped by the store

`start_launch`, `advance_gate` and `move_launch_date` carry no timestamp
and the application layer holds no clock. Their entries are stamped by
the journal repository from the database clock — the same `func.now()`
default `launch_positions.created_at` already uses. Where the occurrence
does carry a moment — a `Provenance.when`, a `GateApproval.when`, a
`MetricAttestation.when` — the entry names *that* moment, not the moment
of the append, because that is when the work happened.

### 7. A refused advance stores its unsatisfied conditions as the domain names them

`GateBlocked.unsatisfied` is a tuple of condition names the domain
composes — `"blocking step 'lp.listing.007'"`, `"a recorded approval"` —
and the entry stores that tuple, in `details`, as a list of strings.

This is the one place the change falls short of its own "labels, not
identifiers" rule, and it is deliberate. Making those names carry step
*names* would mean reshaping `GateBlocked` into structured conditions —
a domain event this change explicitly leaves alone, and one whose string
form is already part of the rejection message callers read today.
Parsing the strings back apart in the application layer to re-enrich them
would be worse than storing them. The list is still structure rather than
prose — it is condition names, not a sentence — so the composer can
render it however it later wants to. Recorded as a limitation in Risks,
and worth a follow-up change if the diagnostic value proves to need it.

### 8. The domain gains nothing

No domain event is added, and `launch/domain/` is untouched. Every entry
this change appends is buildable from what the use case already holds:
its arguments, the loaded playbook, the returned events, and the caught
`GateBlockedError`. Emitting a domain event so that a history table has
something to store would make the domain serve a persistence concern —
`proposal.md`'s Impact section states the same, and this design does not
depart from it.

## Risks / Trade-offs

- **A journal entry for a command whose transaction later rolls back.**
  Repositories commit their own writes, so the append commits on its
  own; under `database.transaction()` it joins the outer transaction and
  unwinds with it, but under a plain `session()` it does not. → Appending
  *after* the command's own save narrows the window to the work that
  follows the append, which for every command but the graduating advance
  is nothing. A journal that occasionally over-reports is the right side
  of this trade for an append-only history whose purpose is diagnosis.

- **A test that fakes the append failure with a plain `raise` proves
  nothing about the rollback**, and would pass against an implementation
  that omits it — the trap `contain-a-failing-launch` recorded. → The
  containment tests must either run against a real session, or use a
  fake that refuses every write after it raises until `rollback()` is
  called. `tasks.md` 1.2 carries this.

- **Doubling the writes per command.** Every accepted command now
  performs a second `INSERT`. → One row, no index beyond the primary key
  and the foreign key, on a workload of a handful of commands per launch
  per day. Not a concern at this scale; noted so that it is a known cost
  rather than a discovered one.

- **The `kind` vocabulary is a check constraint.** A ninth occurrence
  needs a migration alongside the code. → Accepted, and consistent with
  every other checked vocabulary in `models.py`
  (`OUTCOME_KINDS`, `PROVENANCE_SOURCES`, `APPROVAL_DECISIONS`). The
  constraint is what stops a typo'd kind from becoming an entry nobody
  can compose.

- **An unbounded read.** A long-lived launch's journal is returned
  whole. → At a few entries per step per launch this is small; a launch
  that outgrows it wants pagination, which is a change of its own.

- **A refused advance's conditions carry identifiers, not names** —
  Decision 7. → Contained to one field of one kind of entry; every other
  entry carries its label. Recorded as an exception in the delta spec's
  labels requirement, so a test derived from that spec does not demand
  what Decision 8 forbids.

- **`rollback()` is safe only while repositories commit their own
  writes.** Containment rolls the shared session back from inside a use
  case, which discards nothing of the caller's *because*
  `launches.save(...)` — and every other repository write reached before
  the append — has already committed. `docs/deferred-work.md`'s
  "Repositories commit their own writes, so a caller cannot own a
  transaction" schedules exactly that convention for removal: once
  `LaunchRepository.save` becomes commit-neutral, this rollback would
  discard the command's own persistence, violating the requirement it
  exists to uphold. → The R6 tests go red if it happens, which is the
  safety net; but the coupling must be signposted where the fix will be
  made, so `tasks.md` 5.5 adds `LaunchJournal.rollback` to that deferred
  entry's list of dependents.

- **Ordering is by named moment, and is therefore not causal.**
  `occurred_at` mixes two clocks (Decision 6): the database clock for the
  five kinds naming no moment, and an externally supplied timestamp for
  the three that do. A ClickUp-sourced `Provenance.when` running ahead of
  the database clock — skew, or a webhook carrying an event time — sorts
  a step recording *after* the gate opening it unblocked. → Not a
  violation of "most recent first", which is satisfied either way, and
  not worth a second clock to fix. Noted so that whoever renders the
  journal does not read the order as cause and effect.

## Migration Plan

One additive Alembic revision on top of `e4b91c73a2d5`, creating
`launch_journal_entries` and nothing else. No table is altered, no data
is backfilled, and no existing row changes.

There is nothing to backfill *from*: the occurrences this journal records
were discarded as they were raised, which is the change's premise.
Launches that predate the migration therefore have empty journals for
ever, which the read reports as an empty journal rather than an error —
`add-launch-tracking-pages` R5 depends on exactly that, and is why its
empty-journal section must not vanish when empty.

Rollback: the downgrade drops the table, losing the history recorded
since the upgrade. Nothing else depends on it — no launch state is
derived from a journal entry, and every command behaves identically with
the table absent, since a failed append is contained.

## Open Questions

None. The two that would have belonged here — how the port reaches the
use cases, and whether the composed wording lives in the application or
in each reader — are settled in Decisions 1 and 5, because both change
the task breakdown.
