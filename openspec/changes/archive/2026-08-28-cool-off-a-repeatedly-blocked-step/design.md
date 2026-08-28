## Context

See `proposal.md` — Why. What shapes the approach is the pass as it
stands:

- **`_is_open` is the one place invocation is decided**, and it already
  holds three conditions in the shape this change extends: settled,
  pending, and the rejection cool-off (`COOL_OFF`, 24 hours).
- **A non-terminal outcome is recorded directly** — `_settle` sends it
  straight to `record_outcome` whatever the confirmation flag says, so
  there is no pending row to hang state off, as the rejection path has.
- **The pass already has the recorded outcome**:
  `launch.progress_for(step.identifier)`, carrying the outcome and a
  `Provenance` with `who`, `source` and `when`.
- **`clickup-sync` already solves report-once**, and its
  `field_gap_suppression` docstring records the traps: write suppression
  only *after* a successful delivery; key it on content so a *changed*
  fault reports again; use a table, because a restart must not resume the
  flood; and give it its own table rather than borrowing one whose
  lifecycle clears on the passes it exists to suppress.
- **Reports reach Slack through `notifier.post_monitoring_message`**, via
  a seam that returns whether delivery actually happened.

## Goals / Non-Goals

**Goals:**

- Stop paying for a handler that has nothing new to say, without slowing
  down one that does.
- Tell a person that a step is stuck, once, with what the handler last
  said, so the missing input can be supplied.
- Keep the decision in `_is_open`, where the other three conditions live.

**Non-Goals:**

- Changing the handler contract, the pending-result lifecycle, the
  rejection cool-off, or any terminal path.
- Deciding *why* a handler blocked, or acting on the reason. The system
  reports what the handler said; judging it is the reader's.
- Detecting that the underlying situation changed (new product data, an
  edited playbook) and re-running early. A cool-off that expires is
  enough; change detection is its own problem.

## Decisions

### 1. The repeat is detected across two recordings, not predicted before one

To know that a handler will say the same thing again you must ask it. So
the rule cannot be "skip because it might repeat" — it is:

1. Pass *n*: the step has no outcome. Invoke. The handler says `Blocked`.
   Record it. Nothing is known yet.
2. Pass *n+1*: the step carries `Blocked`. Invoke — this is the one call
   the rule deliberately still pays for. The handler says `Blocked`
   again. Record it, **and note the repeat**.
3. Passes *n+2* onward, within the cool-off: `_is_open` sees the noted
   repeat and does not invoke.

The cost is one extra call per stuck step per cool-off period, and that
call is what distinguishes a stuck step from a progressing one. Backing
off on the *first* non-terminal outcome would save it, and would also
slow every legitimately-polling handler from four checks an hour to one —
the trade this change deliberately refuses.

For the observed advisor loop this turns ~96 calls per product per day
into 2.

### 2. Sameness is the outcome kind, never the reason text

`Blocked("I cannot confidently determine…")` and `Blocked("I am unable to
determine…")` are the same outcome. Comparing reasons would be strictly
more precise and completely useless: the advisor is an LLM and rewords
its reason on every call, so no two blocks would ever compare equal, the
cool-off would never engage, and the rule would look implemented while
changing nothing. This is the single most load-bearing decision here, and
the tests must pin it — a repeat with two differently-worded reasons must
still cool off.

### 3. The repeat is stored, not derived from the journal

`launch_journal_entries` now holds every recording, so "were the last two
automated recordings the same?" is answerable from it. **It must not be
answered from there.**

Stated precisely, because the loose version overstates it:
`launch-journal`'s guarantee is scoped to *the command being recorded* —
a failed append does not fail or disturb that command — and a later pass
reading the journal would not break that clause literally. What it would
break is the principle the clause exists to serve. Today a dropped entry
costs a line of history; if the pass read the journal, a dropped entry
would silently change what the system *does* on some later pass, and the
containment guarantee would be true as written while no longer meaning
what it was written to mean. The journal is a record for people, not a
control input, and it stays cheap to lose precisely because nothing
depends on it.

So: one row per (launch, step), on the `clickup_field_gap_suppression`
model — the noted outcome kind, when it was noted, and whether it has
been reported. Its own table, for the reason that precedent records.

### 4. One row carries both the backoff and the report suppression

They key on the same thing and are lifted by the same event — the step
saying something different, or reaching terminal. Two tables would need
the same writes and could disagree. The row means: *this step repeated
outcome K at time T, and the report was delivered at R (or not yet)*.

**Lifting is lazy, not swept.** The row records *which* outcome it was
noted against, so a row whose noted outcome is not the step's currently
recorded one governs nothing — neither the cool-off nor the report
suppression. Nobody has to remember to delete it.

That matters because the pass is not the only thing that records an
outcome for these steps: `automation_confirmation` records too (an
acceptance terminally, a rejection as `Blocked`), and the proposal leaves
that path untouched. A rule that lifted the row by *deleting it where the
outcome changes* would have to be taught to every recording surface, and
each new surface would owe it silently. Comparing on read costs one
column and covers every path that exists or ever will.

### 5. A failed backoff access degrades to the old behaviour, and restores the session

The precedent's docstring records four traps and its *caller* carries a
fifth, which this design initially missed. `clickup_sync_job` wraps every
access to the field-gap record and calls `_restore_after_store_fault`
before continuing, because the record shares the launches' session: a
failed statement leaves that session refusing everything behind it, and
`c8bca97` ("keep a gap-record fault from poisoning the pass") exists
because that happened.

**The exposure here is strictly worse than the precedent's.** The field
gap is read once, ahead of the walk. The backoff row is touched per step,
*inside* `_walk_launch`, where a poisoned session would make every
subsequent `record_outcome` in the pass fail — writing nothing while the
pass reports success.

**The row carries two decisions, and they degrade in opposite
directions.** Getting this wrong is easy, because one row invites one
default:

- **Invocation degrades toward running.** A failed read leaves the step
  eligible and the pass invokes as it would have before this change. The
  backoff is a cost optimisation; a fault in it must degrade to spending
  money, never to automation silently stopping. This is the opposite
  default from the field gap's read, deliberately — *there* the risk of
  proceeding is a duplicate message, *here* it is a step nobody ever
  resolves.
- **Reporting degrades toward silence.** The same failed read means the
  pass cannot know whether this step has already been reported, and a
  report it cannot record as delivered is a report it cannot deliver
  *once*. So it delivers none. Here the precedent's reasoning applies
  unchanged — "this pass reports no gap rather than risk repeating one
  already delivered" — and inverting it would turn a store outage into
  one message per stuck step every fifteen minutes: the exact flood the
  report-once rule exists to prevent, arriving by the other door.

  Nothing is lost by the silence: the access failure is itself reported
  to operators, which is the more actionable signal, and the step is
  reported normally on the first pass that can read the row again.

  The two halves fail asymmetrically, which is what decides it.
  Over-invoking spends an LLM call. Over-reporting spends the team's
  attention on the channel, and the report-once rule exists on the
  finding that attention is the more expensive of the two.

- **A failed write leaves the step eligible too**, logged; the next pass
  notices the repeat again and re-notes it. One further invocation, not a
  lost guarantee.
- **Either failure restores the shared store before the walk
  continues**, so the fault stays inside the step it belongs to. **Where
  the restore itself fails, the walk ends and the run fails** — the
  precedent's own judgement, recorded in `_restore_after_store_fault`:
  continuing against a store that cannot record is worse than not
  continuing. A pass that walked on would record nothing while reporting
  success, which is the one outcome worse than stopping.

A second session for the backoff row is *not* the answer, for the reason
`reported_field_gap`'s docstring already gives: a second session is a
second transaction, and a write there escapes whatever isolation its
caller runs under.

### 6. The cool-off is its own constant, at the same 24 hours

Not a reuse of `COOL_OFF`. The two answer different questions — a person
disagreed with a proposal, versus a machine repeated itself — and sharing
the constant means a future change to one silently moves the other. Same
value today, separate name, and `launch-step-automation`'s existing
reasoning carries over: a fixed property of the system, not a configured
one, so `runtime-configuration` needs no new variable.

### 7. Report after recording, never before delivery

The report is delivered first and the delivery's success decides whether
the row is written, exactly as the field-gap path does. Recording first
and failing to deliver would silence the step permanently, since the row
is lifted by the step *moving* rather than by Slack recovering. A write
that fails after a successful delivery means one duplicate message on the
next pass — the accepted trade, and the same one `scheduled-jobs` makes.

A delivery failure never fails the pass and never stops the walk: this
sits inside the per-launch loop, and `contain-a-failing-launch` already
established that one launch's fault must not starve the ones behind it.

## Risks / Trade-offs

- **A handler that alternates never cools off.** One proposing `Blocked`,
  then `InProgress`, then `Blocked` looks like progress to this rule and
  keeps its full cadence. → Accepted. Alternation is a handler that is
  reporting *something*, and a rule that caught it would also catch
  genuine progress. If an alternating handler appears in practice, an
  attempt count is the answer, and it is a change of its own.

- **The cool-off expires blind.** After 24 hours the handler is asked
  again with nothing having necessarily changed, and if it repeats it is
  cooled off again. → Judged acceptable against the alternative of never
  re-checking; a step whose missing input arrives should recover on its
  own. The cost is one invocation per stuck step per cool-off, which is
  the price already accepted in Decision 1. It produces **no** second
  report: reporting is lifted by the step *moving*, not by the cool-off
  expiring, so a step stuck for a week is one message and not seven.

- **Two same-kind outcomes may have had different causes.**
  `subcategory-advisor` requires the recorded reason to distinguish a
  product finding from a system fault — a verdict never reported, an
  unrecognised value, a genuine refusal. Decision 2 treats all of them as
  one repeat, and the report quotes only the last one. → Accepted, and
  the reason travels in the report so the distinction is still legible to
  the person reading it; what is lost is the *pair*, which the launch
  journal retains in full for anyone who looks.

- **One extra call per stuck step per cool-off**, by construction
  (Decision 1). → The price of not slowing every polling handler down.

- **The report names a reason the handler wrote**, which for an LLM
  handler is free text of unbounded length and unverified content. → It
  is quoted as what the handler said, never asserted as fact, and the
  message is what a person reads before acting rather than something the
  system acts on itself.

## Migration Plan

One additive Alembic revision creating the backoff table. No existing
table is altered, nothing is backfilled.

There is nothing to backfill from, and it does not matter: every
currently-looping step will note its repeat on the pass after the deploy
and cool off from there. The two products blocking now go quiet within
one cool-off of the release, and each produces one report on the way.

Rollback drops the table, and every step returns to the fifteen-minute
cadence — the behaviour before this change, which is a cost problem
rather than an outage.

## Open Questions

None. The three that would have belonged here — how a repeat can be
detected without invoking, whether the journal can supply it, and whether
the rejection cool-off's constant should be reused — are settled in
Decisions 1, 3 and 6, because each changes the task breakdown.
