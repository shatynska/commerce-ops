## Context

See proposal.md — *Why*. The constraints that shape the approach:

- `d2f8b3c64e17` seeds `playbook_steps` from a vendored
  `alembic/data/playbook_v1.yaml`, guarded on the table being empty. That
  revision is stamped in every environment, so it will not run again and its
  vendored file must stay readable where it is.
- `PlaybookRepository.save()` persists a full replacement conditionally on the
  optimistic set-version — it issues `delete(PlaybookStep)` over the whole
  table and re-adds. That is the right *transaction* shape whatever the rule:
  the step composes the candidate it wants and hands the whole thing over, so
  "adds a row" and "changes nothing" are the same atomic operation.
- `playbook_authoring` already loads the stored records and hands `save()` a
  candidate set. The step composes its candidate the same way: stored records,
  with the vendored ones substituted in.
- `seed_admin.py` is the shape a preparation step takes here: its own process
  between `alembic upgrade head` and the server, its own engine disposed
  before it exits, exit status as the whole interface.
- `serve-only-a-ready-playbook` (merged) makes an all-`draft` set loadable and
  the playbook not-ready rather than unloadable. Every consumer already
  declines gracefully, so the state this seed lands in is one the system
  describes rather than one it breaks on.

## Goals / Non-Goals

**Goals:**

- The reference document's rows exist as steps — 352 of its 358, the six
  metric restatements excluded — each traceable to its row.
- Seeding is repeatable, so correcting the vendored set is a deploy rather
  than a hand-edit.
- What the seed cannot know is left visibly unknown, not guessed.

**Non-Goals:**

- Ownership, blocking decisions, hazard classification beyond what a human
  already did, and activation. Each is a judgement the authoring surface
  exists for.
- Delivering a corrected vendored definition to a step that already exists.
  That correction is an authoring act, not a seeding one.
- Any change to the step schema or to the authoring rules.

## Decisions

### Gates come from an area+timing rule, checked against the human pass

The reference document's ten areas are thematic groupings, not an execution
sequence, so an area does not map to a gate on its own. The rule is recorded
here in full, because a rule stated only in summary is not the reviewable
thing the alternative was rejected in favour of.

**Stage 1 — the area proposes.**

| area | gate | | area | gate |
|---|---|---|---|---|
| 1. VALIDATE & COMMIT | `commit` | | 6. PRE-LAUNCH GATE | `live` |
| 2. SOURCE & COMPLY | `order` | | 7. LAUNCH | `ignition` |
| 3. BUILD THE LISTING | `listable` | | 8. RANK & REVIEWS | `phase-one-complete` |
| 4. SET THE PRICE | `listable` | | 9. EXTERNAL TRAFFIC | `phase-one-complete` |
| 5. GET STOCK IN | `stock-ready` | | 10. GRADUATE | `graduated` |

**Stage 2 — the timing disposes.** Each `WHEN` value admits a set of gates and
names the *home* it falls back to when the area's proposal is not in that set.
"Incompatible" means exactly: the proposed gate is not in the admits column.

| WHEN | admits | home |
|---|---|---|
| `T-90` | commit, order | commit |
| `T-60` | commit, order, listable | order |
| `T-30` | listable, stock-ready | listable |
| `T-15` `T-14` | listable, stock-ready, live | listable |
| `T-7` | live | live |
| `Day 1` `Week 1` `Week 1-2` | ignition | ignition |
| `Week 2-4` | phase-one-complete | phase-one-complete |
| `Week 5-8` | phase-one-complete, graduated | phase-one-complete |
| `Day 60+` `Monthly` | graduated | graduated |
| `Daily` `Weekly` `Biweekly` | *(all)* | — never overrides |

**Stage 3 — two discipline corrections the source states outright.**

- `PPC` at any pre-launch `T-*`, proposed earlier than `live` → `live`
  (`lp.ppc.019`: campaigns are built before launch, armed at go-live).
- `INVENTORY` at `T-30`/`T-15`/`T-14`, proposed earlier than `stock-ready` →
  `stock-ready` (physical stock cannot resolve before the stock gate).

Checked against the 97 rows an earlier human pass placed by hand, the rule
agrees on **96**. The one disagreement is recorded as data rather than prose:

| identifier | area | WHEN | human | rule | resolution |
|---|---|---|---|---|---|
| `lp.listing.015` | 3 | `T-7` | `listable` | `live` | human's answer kept |

It names a real ambiguity: `T-7` is both the go-live window and where late
listing-completion work lands. The rule stays strict, because loosening `T-7`
would misplace the 13 area-4 price rows that correctly move to `live`.

An earlier version of the rule snapped an inadmissible proposal to the gate
*nearest* the area's. That silently filed six rows about the first purchase
order behind the listing gate, because `stock-ready` is adjacent to `listable`.
Timing is a position in time; when the area disagrees with it, the timing wins
at its own position.

*Alternative considered:* place all 352 by hand. Rejected on cost against a
rule that reproduces the human pass at 96/97, and because a rule is reviewable
where 352 individual judgements are not.

### The reference row ID is the identifier, and it is permanent

A seeded step's identifier is its reference document row ID — `lp.creative.008`
— and that identifier is **unique and immutable**. Both properties already
hold: the column is the table's primary key, and `playbook-authoring` states
that "a step's identifier SHALL NOT be updatable", enforced by `update_step`
refusing the field outright. This decision does not add them; it commits to
them, because everything below depends on the identifier never moving.

**It carries a decision the other way.** `add-launch-playbook`'s design.md
chose the opposite in as many words: identifiers were to be slugs in a
namespace we own, with reference IDs "retained as provenance only: not
unique, not addressable, and free to change upstream without moving our
keys". The implementation did the reverse, and the seeded set has used
`lp.*` as its key ever since. This change makes that permanent rather than
leaving two records disagreeing.

The reason to prefer the reference ID is that it is the only key that makes
the seed *checkable*. Every guarantee this change offers — that each step
traces to exactly one row, that each description re-derives from its row,
that the human pass is carried across unchanged, that a re-run recognises a
row it has already seeded — is a join between the vendored file and the
reference document on that ID. Under our own slugs each of those becomes a
lookup table somebody maintains by hand, and a divergence between the two
documents stops being detectable, which is the property the seed exists to
have.

The risk `add-launch-playbook` named is real and is accepted: the reference
document is not ours, and an upstream renumbering would break the join. Two
things bound it. The document is a delivered artifact rather than a live
feed — `docs/reference/README.md` records it as supplied, not to be edited —
so a renumbering is an event someone performs, not one that happens. And the
identifier being immutable means such an event cannot silently rewrite
history: the old identifier keeps naming the step, every outcome recorded
against it stays interpretable, and reconciling the two is an authoring
decision made deliberately.

What this forecloses, deliberately: a step's identifier is never corrected,
never re-namespaced, and never re-pointed at a different row. A step that
should have been a different row is retired and its successor created, which
is the same remedy `playbook-authoring` already prescribes for changing a
step's discipline.

### Timing anchors come from the `WHEN` column, on a closed mapping

`WHEN` is a closed vocabulary — sixteen values over all 358 rows, every one of
which the gate rule's stage-2 table already enumerates — so the anchor is a
sixteen-row table rather than 352 judgements.

| `WHEN` | anchor |
|---|---|
| `T-90` `T-60` `T-30` `T-15` `T-14` `T-7` | `offset(-n)` |
| `Day 1` | `offset(0)` |
| `Day 60+` | `open-ended(59)` |
| `Week 1` | `window(0, 6)` |
| `Week 1-2` | `window(0, 13)` |
| `Week 2-4` | `window(7, 27)` |
| `Week 5-8` | `window(28, 55)` |
| `Daily` `Weekly` `Biweekly` `Monthly` | `recurring(cadence)` |

The two forward-counting rows carry the hazard `launch_playbook`'s own module
docstring warns about at length: the convention is **zero-based** and the
source is one-based. `Day 1` is the launch day, so offset **0**, not 1;
`Day 60+` starts on the sixtieth day, so **59**. Countdown values need no
adjustment, being already relative to the launch day. Getting this wrong
shifts every post-launch anchor by one day, uniformly — invisible by
inspection, and visible only as work scheduled a day late, forever. Windows
take the same treatment: `Week 1` is the launch week, days 0-6.

### The reference text moves to `description`, and `name` is authored

The current requirement puts the row's text in `name`. Measured over all 358
rows that yields a median of 114 characters and a maximum of 253 — and `name`
is what is composed into a ClickUp task's title.

So `name` becomes authored: at most 80 characters, imperative where the row
asks for work and state-form where it states a threshold, with any leading
marker (`TOS RISK:`, `EU:`, `NOTE:`) and any numeric threshold preserved. The
authored set has a median of 54 and a maximum of 70.

The cost is real and is accepted: an authored name is not re-derivable from
the reference document, so a divergence in the *name* is no longer detectable
by comparison. The description keeps that property, which is where the text
the reference owns actually lives.

*Alternative considered:* truncate mechanically at the first `-` or `:`.
Rejected — it produces fragments that read as broken rather than as titles,
and the marker-bearing rows would lose exactly the marker that matters.

### `blocking` is not derived, and `hazard` is not invented

`add-launch-playbook`'s design proposed `FRAMEWORK` binding blocks and
`LESSON` is advisory as "a defensible starting default". It is not in the
reference document — it is our derivation — and applied to 358 rows it marks
151 blocking, including a row whose text begins `NOTE:`. A gate cannot wait on
a note.

So `blocking` is `true` only for the 24 rows the earlier human pass marked,
and `false` elsewhere. Blocking becomes a decision made when a step is
activated, which is where someone is already looking at it.

`hazard` is carried across for the 7 curated rows and `none` everywhere else.
The classification is semantic rather than mechanical — of the reference's ten
`TOS RISK` rows, four are tactics to refuse, four are compliance obligations
and two are hazard warnings, and separately `lp.listing.013` is a prohibited
tactic that carries no `TOS RISK` marker at all. A wrong `prohibited-tactic`
produces a step whose only terminal outcome is `Refused` — work that can never
be done. Six `TOS RISK` rows outside the curated set therefore arrive as
`none`, and the words stay visible in both `name` and `description`.

### `scope` defaults to `product`, and the market rows are enumerated

This is the one field the reference document does not speak to at all, so
there is no column to read. **12** of the 352 seeded rows are `market`; every
other row is `product`.

Seven are found by an `EU:` prefix — `lp.finance.013`, `lp.finance.014`,
`lp.finance.017`, `lp.setup.014`, `lp.setup.015`, `lp.setup.017`,
`lp.setup.018`. A prefix rule alone would stop there, and would be wrong about
five more that name a marketplace without carrying the marker:

| identifier | why it is `market` |
|---|---|
| `lp.listing.018` | "EU rollout: existing US reviews PORT to other marketplaces" |
| `lp.listing.020` | "Non-US marketplaces: RESCALE the volume tier" |
| `lp.price.012` | "the same tier structure across ALL marketplaces" |
| `lp.external.004` | Creator Connections is US-sellers-only |
| `lp.external.005` | Levanta replaces it for UK, DE, FR, IT, ES |

They are listed rather than described because a marker set broad enough to
catch them also catches rows that merely mention a country, and a list of five
is checkable where a regular expression is not. Same shape as the one
gate-rule disagreement: recorded as data rather than prose.

### The seeder adds what is missing, and asks only about identity

The step inserts every vendored step no stored step names, and leaves every
stored step exactly as it stands.

**Two earlier designs were wrong, and the second was wrong subtly.** The first
replaced the whole table, which would have deleted `mg.*` steps and every
retired one — against `playbook-authoring`'s flat "No operation SHALL delete a
step", and orphaning `launch_step_progress` rows that carry no foreign key.
The second replaced only the rows the vendored set names, minus retired ones,
which fixed the deletion but not the underlying mistake: it still asked *"does
this stored row differ from the vendored one?"*, and that question has no
honest answer. A row that differs is indistinguishable from a row an author
edited — the difference **is** the edit. Every exclusion bolted onto that rule
was an attempt to enumerate which edits mattered, and the list was never going
to close: retired, then un-retired, then active, then assigned, then renamed.

Identity is the only question this step is entitled to ask. `playbook-authoring`
makes the identifier unique and never updatable, so it is a key that cannot
move underneath the comparison, and "have I already got this row" is a fact
about the stored set rather than a judgement about someone's work.

**That the rule is idempotent is the whole payoff.** Running twice changes
nothing the first run did not, so the condition is readable from the data —
exactly as `roster`'s admin seeding condition is, which is why that step may
sit unconditionally in a chain that runs on every restart. A step that
replaced would have needed a signal delivered from outside the data, and a
signal is precisely what a deployment cannot withdraw: `deploy.yml` renders
`.env` at deploy time and delivers it, so a signal set for one deploy goes on
arming every restart until the next. An earlier draft of this design carried
an arming token, a nullable column to consume it, a migration to add the
column and four scenarios to govern it. All of it existed to work around not
having a readable condition. Insert-missing has one, so all of it is gone.

It is also the rule this project already chose. `d2f8b3c64e17` guards on the
table being empty, so that "a `playbook_steps` table that already holds rows —
authored edits included — is never re-seeded and never overwritten". This step
widens that guard from the whole table to each row, and narrows nothing: a
reference document that gains a row can still deliver it, where an
emptiness guard would require wiping the table to accept one new step.

**The cost, stated plainly.** A corrected vendored definition never reaches a
row that already exists. Correcting a seeded step is an authoring act through
the admin surface, by someone who can see what they are changing and whose
change is attributed — which is where a correction to a step somebody has
already reviewed belongs anyway. A wholesale refresh means emptying the step
set first: destructive, deliberate, and looking like both.

*Alternative considered:* replace the named rows, excluding retired ones. This
is the design two review rounds refined, and it fails on the case it never
reached — activation. `introduce-automation-runtime` ships one registered
handler and expects an admin to activate the step naming it; that step is
named by the vendored set and is not retired, so a run would return it to
`human`/`draft` and silently disable the only automation the system has. The
handler report that would notice runs *after* the seeding step by this
change's own ordering, and an empty set of active automated steps reports
nothing.

*Alternative considered:* refuse to run at all where the table holds any row,
which is `d2f8b3c64e17`'s guard verbatim. Equally safe, and strictly less
useful: a reference document that gains a row could not deliver it without a
wipe. Insert-missing degenerates to this rule whenever the stored set is
already complete.

### The old vendored file stays

`alembic/data/playbook_v1.yaml` is not deleted. `d2f8b3c64e17` reads it, and
that revision runs on any environment built from scratch. A new file is added
beside it rather than replacing it in place.

## Risks / Trade-offs

- [A corrected vendored definition never reaches an existing step] → Accepted,
  and the reason the rule is drawn where it is. Correcting a stored step is an
  authoring act through the admin surface. A wholesale refresh means emptying
  the step set first, which is destructive and deliberate.
- [The stored set can drift from the vendored file, row by row, and nothing
  reports the drift] → Real. A step someone edits is thereafter governed by
  its recorded authorship rather than by re-derivability from the reference
  document, which `launch-playbook` already states of any edited seeded step.
  What this change adds is that the same becomes true of a row the *vendored
  file* changed. No signal exists for it; noted rather than mitigated.
- [255 gate placements are derived, not judged] → The rule is recorded in full
  above, checked against the human pass at 96/97, and every step lands as a
  `draft` — so a wrong gate is corrected during the review that has to happen
  before anything is served.
- [Derived anchors follow `WHEN`, which occasionally disagrees with the row's
  own prose] → `lp.rank.009` reads "Day 2 check…" while carrying `WHEN: Day 1`,
  so it anchors at offset 0. Corrected in the same review, for the same
  reason: every step lands a draft.
- [Launches in flight lose completions during the review window] → The 95
  active steps and 2 in-development ones are untouched by this step, so unlike
  earlier drafts of this change nothing is de-activated by seeding. A launch
  in flight keeps its served set. This risk, which two earlier designs carried,
  is removed rather than mitigated.
- [After seeding, no step is active, so `playbook-admin` renders 352 drafts in
  an order it leaves undefined] → The surface the review happens on presents
  the set in identifier order rather than reference-document order. Recorded
  rather than fixed; giving the non-active list a defined order is its own
  change.
- [Nothing bounds how long the deployment stays unready] → Readiness needs one
  active blocking step per gate, activating a `human` step needs an active
  assignee, and assigning owners is out of scope here. The exit condition is
  therefore a follow-up change, not this one.

## Migration Plan

No schema change, no Alembic revision, and no new runtime variable. The step
needs none: its condition is the stored set itself.

Order matters in one direction only: the deployment must already be running
`serve-only-a-ready-playbook` before a 352-draft set exists, because against
the previous code an all-`draft` set is unloadable and the container's start
chain aborts. That change is merged and deployed, so the constraint is
satisfied — but it is what makes the rollback below a one-way door.

To apply: deploy. The step runs in the chain, inserts what the stored set does
not carry, and is inert on every subsequent start. Nothing is armed and
nothing needs clearing afterwards.

Rollback: the step deletes nothing, so a run is not destructive and needs no
rollback of its own. Removing the 352 seeded rows means deleting them
deliberately — leaving `playbook_step_set` in place, since without its row
`_version()` raises "the playbook step set has no version row", a hard failure
everywhere rather than a graceful one. Reverting the *code* of
`serve-only-a-ready-playbook` while a 352-draft set is stored would make the
playbook unloadable and the deployment unable to start; that ordering is
recorded here because nothing in the code enforces it.
