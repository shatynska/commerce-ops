## Why

**A handler that blocks for a standing reason is re-asked every fifteen
minutes, for ever.** `launch-step-automation` says so outright — *"A step
reporting no progress is reconsidered on the next pass"* — and the pass
obeys it: `_is_open` skips a step only where its outcome is terminal for
its hazard, a pending result stands, or a rejection is inside the
cool-off. A non-terminal outcome passes all three, so the handler runs
again on the next pass, and the one after that.

That rule was written for a step whose situation changes. It does not fit
a handler whose answer is *the same answer*: the sub-category advisor
cannot categorise a product it has not been given enough information
about, and no amount of re-asking will change that until a person
supplies what is missing.

**The deployment is doing exactly this now, and the launch journal is how
we know.** Between 05:45 and 08:15 on 2026-08-28 the journal recorded 17
`step-outcome-recorded` entries for one step, `Blocked` every time, on
two products, at a clean fifteen-minute cadence — one LLM call per
product per pass, roughly 190 a day, each one failing the same way and
costing money to fail.

Before the journal, none of this was visible: `launch_step_progress`
holds one row per step and each pass overwrote it, so the table showed a
single `Blocked` and said nothing about it having happened seventeen
times. The repetition was invisible, which is why it has been running
unnoticed.

**And nobody is told.** A step the automation cannot resolve is a step
that needs a person — but the pass records `Blocked` and moves on, and
the only place the fact accumulates is a table nobody reads. The
seventeen blocks came to light because someone queried the journal by
hand.

## What Changes

- **A repeated non-terminal outcome cools the step off.** Where a
  handler proposes the same non-terminal outcome the step already
  carries, the outcome is still recorded, and the step's handler is not
  invoked again until a cool-off has elapsed.
- **A *changed* outcome does not.** A handler that moves a step from
  `Blocked` to `InProgress` — or the reverse — is reporting that
  something happened, and the step stays on the fifteen-minute cadence.
  Only a step saying the same thing twice goes quiet.
- **Sameness is judged on the outcome, not on its reason text.** Two
  `Blocked` outcomes are the same outcome even where their reasons differ
  word for word. This is not a simplification but the substance of the
  rule: the advisor is an LLM, and its reason is freshly worded on every
  call — *"I cannot confidently determine the appropriate sub-category"*
  one pass, *"I am unable to determine a specific sub-category node"* the
  next. A rule that compared reasons would never find two blocks alike
  and would cool nothing off, while appearing to work.
- **A step that has gone quiet is reported once**, naming the launch, the
  step and what the handler produced as its result — which for a
  `Blocked` outcome is also the reason it carries — so that the person
  who can supply what the handler is missing learns that it is missing.
  Reported once and not once per pass, on the `launch-clickup-sync`
  Custom Field gap's precedent: a wall of identical messages trains a
  team to ignore the channel.
- **The report is lifted by the step moving — and only by that.** A step
  whose outcome changes, or which reaches a terminal outcome, is eligible
  to be reported again if it later gets stuck again. The cool-off
  expiring does *not* lift it: a step stuck for a week is one message,
  not seven.
- **A fault in the backoff record degrades to the old behaviour — in
  both directions, which are opposite.** Where the system cannot read or
  write what it keeps this judgement in, the step is invoked as it would
  have been before this change, *and* no report is delivered for it on
  that pass, since a report that cannot be recorded as delivered cannot
  be delivered once. The failure itself is reported. This is a cost
  optimisation; it must never be the reason a step goes unresolved, never
  the reason a pass stops recording the outcomes behind it, and never the
  reason the channel fills up.

No **BREAKING** changes to any stored shape or route. Two requirements of
`launch-step-automation` are modified — the one deciding which steps a
pass invokes, which gains a fourth condition, and the one recording
non-terminal outcomes, which is narrowed. One scenario within the second
is narrowed with it: *A step reporting no progress is reconsidered on the
next pass* now covers the changed-outcome case only, because
unconditional re-invocation is the behaviour being changed. Its **name is
retained deliberately** — `openspec validate` requires a MODIFIED block
to carry every scenario name the served spec has, so renaming it reads as
a deletion and is refused. Verified by trying it.

## Capabilities

### Modified Capabilities

- `launch-step-automation`: the openness rule gains a fourth condition —
  a step whose handler repeated itself is inside a cool-off — and the
  scenario promising re-invocation on the next pass is narrowed to the
  changed-outcome case. A new requirement covers reporting the stuck step
  once.

### New Capabilities

None. This is a change to when an existing pass invokes a handler, and
to what it says when it stops.

## Impact

**Affected code**

- `launch/infrastructure/driving/automation_pass.py` — `_is_open` gains
  the repeat check; the walk gains the report.
- A suppression record for the report, on the
  `clickup_field_gap_suppression` precedent, plus its Alembic migration.
- `launch/infrastructure/driven/slack_notifier.py` or the pass's existing
  delivery seam — the destination for the report.

**What decides "the same outcome"**

The step's currently recorded outcome is already available to the pass:
`launch.progress_for(step.identifier)` is what `_is_settled` reads, so the
comparison itself needs nothing new — only the outcome the pass is about
to record, against the one already there.

The *cool-off clock* is a different matter, and `design.md` settles it as
a stored `noted_at` on the backoff row rather than the recorded
provenance's `when`. The provenance moves on every recording, including
the one that notes the repeat, so a clock read from it would restart on
each pass and never elapse.

**Explicitly untouched**

The handler contract, the pending-result lifecycle, the rejection
cool-off, and every terminal-outcome path. A handler is not told about
any of this and does not change; what changes is how often it is asked.

`automation_confirmation` is untouched too, and that is a constraint on
the design rather than a happy accident: it records outcomes for these
same steps, so the rule that lifts a cool-off is written to notice a
changed outcome on read rather than to be actively lifted by whoever
recorded it (design.md — Decision 4). Any surface that records an outcome
gets it right by doing nothing.

The 24-hour rejection cool-off is **not** reused. `design.md` Decision 6
gives the repeat its own constant at the same 24 hours: the two answer
different questions — a person disagreed, versus a machine repeated
itself — and sharing the constant would mean a later change to one
silently moving the other.

**Coordination**

Independent of the launch-journal work that surfaced this, and of the
pages that will render it. Nothing sequences before or after it.
