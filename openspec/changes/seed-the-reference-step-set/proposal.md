## Why

The stored step set is a sampler, not the launch plan. It carries 97 of the
reference document's 358 ID-bearing rows: the BUILD THE LISTING area complete,
and a curated handful on every other gate chosen to exercise each anchor kind,
each discipline and both hazards. That was the honest thing to ship when the
seed's job was to prove the vocabulary works. It is the wrong thing to run a
launch against, because seven of the eight gates carry between three and nine
steps where the reference document has between 15 and 69.

Until now the missing 255 rows could not simply be added as drafts. The
gate-holding floor was a construction rule, so a set whose steps were all
`draft` did not merely fail to serve a launch — it failed to load, and no
sequence of writes could climb out of that state.
`serve-only-a-ready-playbook` moved the floor to the serving read, which is
what makes an all-`draft` set representable and this change possible.

The seed also cannot be re-run. Its migration guards on an empty table, and
that revision is already stamped, so the only way to replace the set today is
to edit the database by hand.

## What Changes

- **The whole reference document becomes the step set.** Its 358 ID-bearing
  rows, less the six that restate a condition a gate already authors as a
  metric condition, give **352 seeded steps** in place of the 97-row sampler.
  Every gate carries what the reference document actually puts behind it.
- **Every seeded step is `draft`, `human`, and unowned.** Nothing is served
  until someone reviews it and activates it, which is the workflow the
  four-status vocabulary exists for. The playbook is therefore *not ready*
  immediately after seeding, and says so: launches cannot start, the ClickUp
  passes stand down, and the daily briefing names the unheld gates.
- **BREAKING (data):** the reference row's text moves from `name` to
  `description`, and `name` becomes an authored line of at most 80 characters.
  The current rule — transcribe the row verbatim into `name` — produces names
  with a median of 114 characters and a maximum of 253, and `name` is what is
  composed into a ClickUp task's title. The verbatim text is not lost; it moves
  to the field shaped for it.
- **BREAKING (data):** the seeded set no longer exercises `kind`, `status` or
  `needs_confirmation`. With every step `human` and `draft` there is no
  `automated` step and none that needs confirmation, so that part of the
  coverage requirement cannot hold. Hazard coverage is **kept**: the human
  pass already classified rows carrying both hazards, so requiring one of each
  costs nothing and classifies nothing new.
- **The seed adds what is missing and never touches what is there.** A
  preparation step joins the container's start chain beside the one that seeds
  the first admin. It inserts every vendored step no stored step names, and
  leaves every stored step exactly as it stands — whatever its status,
  whatever an author has since made of it.
- **Which makes it idempotent, so nothing arms it.** Running twice changes
  nothing the first run did not, so its condition is readable from the data
  the way the roster's admin seeding is. It is the rule the original seed
  migration already chose — guarding on the table being empty so "a table that
  already holds rows, authored edits included, is never re-seeded and never
  overwritten" — widened from the whole table to each row, so a reference
  document that gains a row can still deliver it.
- **A corrected vendored definition therefore never reaches an existing
  step.** Correcting a stored step is an authoring act, made through the admin
  surface by someone who can see what they are changing and whose change is
  attributed. A wholesale refresh means emptying the step set first, which is
  deliberate and looks it.

Explicitly not in scope: assigning owners, deciding which steps block their
gate, classifying the hazard of rows the earlier human pass did not reach, and
activating anything. Each is a judgement made through the authoring surface,
on a set that now exists to be judged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deploy-pipeline`: the start chain gains the playbook preparation step in
  its stated ordering, and the requirement records why one seeding step may
  run unconditionally while this one may not.
- `launch-playbook`: the two requirements describing the seed both change. The
  set's *content* requirement now covers every ID-bearing row rather than one
  complete area plus a subset, and inverts which field carries the reference
  text — `description` verbatim, `name` authored and short. The *coverage*
  requirement narrows to `kind`, `status` and `needs_confirmation` only: a set
  that is entirely `draft` and `human` cannot exercise those, and requiring it
  to would forbid the reviewable starting state this change exists to deliver.
  Hazard coverage is kept. Gains a requirement for the preparation step itself
  — that it adds what the stored set does not carry, never alters a stored
  step, and is therefore idempotent.

## Impact

- `alembic/data/` — a new vendored file carries the 352 steps. The old
  `playbook_v1.yaml` stays exactly where it is: `d2f8b3c64e17` reads it, and
  that revision runs on any database built from scratch, so deleting it breaks
  a clean bring-up.
- `src/commerce_ops/seed_playbook.py` — the new preparation step, modelled on
  `seed_admin.py`: its own process, its own engine, exit status as the whole
  interface, invoked as `python -m commerce_ops.seed_playbook` like its two
  neighbours rather than through a console script.
- `Dockerfile` — the start chain is the image's `CMD`, not a `command` in
  `docker-compose.yml`; the step is added there, after `seed_admin` and
  **before** `check_step_handlers`, so that check reports against the set the
  deployment is about to serve.
  `.env` from an Environment secret, the four-part obligation `AGENTS.md`
  `app` already takes every rendered value through `env_file: .env`.
- No schema change, no migration, and no new runtime variable. The step
  needs none: its condition is the stored set itself.

## Sequencing

Depends on `serve-only-a-ready-playbook`, merged 2026-08-26. Without it a
seeded set of 352 drafts would not load at all.

**Sequence this against launches in flight.** While the set is unready every
read taken on a launch's behalf is refused, and the 95 active steps and 2
in-development ones become drafts — so a ClickUp task closed during the review window is
observed and never replayed, per `launch-clickup-sync`'s rule for a step
outside the served set. Run the step when no launch is in flight, or accept
that completions recorded in that window are lost.

Unblocks, and does not include: rendering a step's hazard as a mark on the
admin surface, which is what a manager scanning for `TOS RISK` needs and which
the presentation vocabulary already has tokens for.
