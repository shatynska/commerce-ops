## Why

The system holds a complete picture of every launch and shows it to
nobody. `read_launches` (`use_cases.py:251`) already returns, per launch,
the current gate, the launch date, every served step's recorded outcome
with its provenance, each step's due period, discipline and blocking
flag, the overdue judgement its hazard decides, the at-risk evaluation
and whether the current gate is held open only by a human decision. Two
consumers read it: the daily briefing, and nothing else.

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

Underneath that sits a second gap. **A launch's history is not
retained.** `launch_step_progress` is keyed `(product_id, step_id)` and
replaced on every recording, so a step's earlier states are gone;
`launch_run.py` states the rule plainly — "a later recording replaces the
stored outcome". Only `automated_step_results` keeps its rows ("Settled
rows are kept, never deleted"), so automated steps have a full record and
human ones have none. Meanwhile the occurrences themselves already exist:
every command on the aggregate returns its events, every write use case
propagates them, and `launch_run.py` records that "**Events are returned,
not collected** ... no dispatch infrastructure exists yet". They are
produced and discarded at the application boundary.

## What Changes

- **A launches list** at `/admin/launches`: every launch position the
  caller's scope permits, one row each — product, current gate, launch
  date, at-risk, awaiting-confirmation. Ordered by attention (at-risk,
  then awaiting-confirmation, then the rest) rather than alphabetically.
- **The list is not filtered by lifecycle**, matching the deliberate
  choice `launch-instance` already records: a launch waiting at
  `graduated` for its approval is precisely something to show, and the
  persisted shape cannot distinguish it from one already through. A
  filter narrows what is *shown* without changing what is enumerated —
  the discipline `playbook-admin`'s narrowing requirement established.
- **A launch detail page** at `/admin/launches/{product_id}`: the gate
  sequence with the launch's position in it, every served step with its
  outcome, provenance, discipline, due period, blocking flag and overdue
  judgement, and the launch's journal.
- **A launch journal** — an append-only record of what happened on a
  launch, newest first, covering **every** command the aggregate accepts,
  not only the ones that currently return an event. It is written where
  the events already are (the application layer) and read by the detail
  page. Retention is the point: a journal that replaced entries would
  reproduce the defect it exists to close.
- **`ReportedStep` grows a `name`.** It carries `step_id` today, so a
  page renders `lp.listing.007`. The precedent is settled: `docs/domain-map.md`
  records that slice 5 "grew `LaunchReport` accordingly instead of giving
  briefing a playbook reader", and the same reasoning applies to any
  consumer of the report.
- **Read-only.** Approving a gate, accepting an automated result and
  moving a launch date keep their existing Slack paths. Every use case
  they need is already exported, so adding them later is additive; doing
  it here would double the change and settle interaction questions before
  anyone has used the pages.
- The admin header gains the third surface.

No **BREAKING** changes. Nothing existing is removed, no route changes,
no write behaviour changes. `ReportedStep` gains a field; every current
construction site is inside `launch.application`.

**Where this change splits, if review finds it too large.** The journal
is the seam: it is the only part touching the application layer and the
schema, and the two pages read it through one port. Splitting means
landing the journal first and the pages second, with the detail page's
journal section arriving with the pages.

## Capabilities

### New Capabilities

- `launch-admin`: the two launch-tracking pages — what the list
  enumerates and how it is ordered, what the detail page renders, how
  narrowing behaves, and that both are read-only. Named to sit beside
  `playbook-admin` and `roster-admin`, which follow the same
  one-capability-per-admin-surface shape.
- `launch-journal`: the append-only record — which occurrences are
  journaled, what each entry carries, that entries are never replaced or
  deleted, and that a journal write never fails the command it records.

### Modified Capabilities

- `launch-instance`: `ReportedStep` carries the step's `name` alongside
  its identifier, so a consumer of the report can render a step without a
  playbook reader. The launch's accepted commands additionally produce a
  journal entry.
- `roster-admin`: its requirement *The page carries a header from which
  the other admin surface is reachable* is written for exactly two
  surfaces — "the other admin surface", "the playbook page SHALL be
  reachable in one action". A third surface makes that wording false
  rather than merely incomplete, so it generalizes to the admin surfaces
  the session can reach.

`admin-session` is deliberately **not** modified: the new pages ride the
existing guard unchanged and refuse identically. `playbook-authoring`,
`launch-playbook` and `launch-clickup-sync` are untouched — nothing here
changes what a write accepts, what the playbook serves, or what reaches
ClickUp.

## Impact

**Affected code**

- `launch/domain/launch_run.py` — the occurrences a journal records that
  no event currently names (a recorded approval, a recorded attestation,
  a non-terminal step recording).
- `launch/application/use_cases.py` — `ReportedStep.name`; journal
  writes at each accepted command; a read for one launch's journal.
- `launch/application/ports.py` — the journal port.
- `launch/infrastructure/driven/models.py` + a new Alembic migration —
  the journal table.
- `launch/infrastructure/driven/` — the journal repository.
- `launch/infrastructure/driving/launch_admin.py` — new; the two routes
  and their guard, shaped after `playbook_admin.py`.
- `launch/infrastructure/driving/templates/` — the two page templates.
- `shared/infrastructure/driving/templates/_admin_header.html` — the
  third surface.

**Explicitly untouched**

The ClickUp projection and its webhook intake; the automation pass and
its confirmation path; every authoring write.

**Coordination**

`add-product-dossier-page` proposes the product page this change's list
rows link to, and touches the same admin header for the same reason.
Whichever archives second reconciles the header requirement rather than
reproducing it. Neither change depends on the other to be reviewable, and
the link is one-directional: this change may render a link the other
change will serve.
