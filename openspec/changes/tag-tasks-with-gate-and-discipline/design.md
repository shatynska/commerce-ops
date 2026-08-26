## Context

See `proposal.md` — Why. The constraints that shape the approach, and are not obvious from the requirements:

- **Tags do not ride `PUT /task/{id}`.** Every field the projection manages today — name, description, assignees, due date — is a field on the update body. Tags are not: ClickUp exposes `POST /api/v2/task/{task_id}/tag/{tag_name}` and `DELETE` of the same, and accepts `tags` only in the *create* body. So tagging is the first part of this projection whose write is a separate call rather than another key in a dict.
- **Tags are space-scoped.** A tag must exist in the space before it can be attached to a task in it. The launch space held **zero** tags when this change was written, so nothing works until the vocabulary is seeded.
- The projection is convergent by construction (`clickup_sync.py` module docstring): every pass drives ClickUp toward what the launch implies, and a crashed pass heals on the next one. Tagging must not introduce a step that only works if it runs exactly once.

Verified against the live API on 2026-08-26 with the deployment's own token, in the same spirit as `CLICKUP_TASK_NAME_LIMIT`'s measured 2048:

| Call | Result |
|---|---|
| `GET /folder/{CLICKUP_LAUNCH_FOLDER_ID}` | `200`, returns the folder's `space` object carrying that space's id |
| `GET /space/{id}/tag` | `200`, `[]` — the space held no tags |
| `POST /space/{id}/tag` | `200` |
| `POST /space/{id}/tag` again, same name | `200`, no duplicate created |
| `DELETE /space/{id}/tag/{name}` | `200` |

The probe created and then deleted a scratch tag; the space was left exactly as found.

## Goals / Non-Goals

Beyond the proposal's scope, at design level:

**Goals.** Add no persisted state. Add no runtime configuration. Keep the per-pass cost at zero calls once tags are in place.

**Non-Goals.** No removal path, and therefore no decision about whether a person's retagging is preserved or overruled — the question the name/body/assignee rules each had to settle, and the one this change is shaped to avoid needing. No colour or ordering control over tags: ClickUp assigns colours, a person may change them, and the system leaves them alone.

## Decisions

### 1. Derive the space from the folder rather than configuring it

`CLICKUP_LAUNCH_FOLDER_ID` is already configured, and `GET /folder/{id}` returns the folder's space. Resolving through it costs one extra GET, cacheable for the life of a pass.

*Alternative rejected:* a `CLICKUP_SPACE_ID` secret. `AGENTS.md` makes every new runtime value a four-part obligation — Environment secret, `deploy.yml` from `secrets`, the settings model, and the drift test's declared set — and records a deploy already broken by getting exactly that wrong for `BOOTSTRAP_ADMIN_IDENTITY`. A value derivable from one already present is not worth that surface.

### 2. Seed by reading the space's tags and creating only what is missing

Duplicate creation is harmless (`200`, no duplicate), so blind creation would also be correct. Reading first is chosen anyway because it makes the steady-state cost of seeding **one GET rather than twenty POSTs**, on a pass that runs every ten minutes against a documented ~100 req/min budget.

*Alternative rejected:* seeding once at worker startup. A pass must not depend on having been preceded by a successful startup step — a space edited after startup, or a worker that started before the space existed, would leave the vocabulary incomplete with nothing to repair it. Ensuring per pass is convergent; ensuring at startup is not.

### 3. Own two prefixes, and read them as the retained value

The system owns `gate:` and `discipline:`; every other tag is a person's. This is what lets the change persist nothing: for name, body and assignees the system must retain what it last wrote in order to tell an authored change from a person's edit, but an owned prefix is self-describing — the `gate:` tag currently on the task *is* the record of what the system put there.

*Alternative rejected:* unprefixed tag names (`listable`, `listing`). The gate and discipline vocabularies contain words a team would plausibly use for its own labels — `live`, `setup`, `price`, `customer` — and an unprefixed namespace could not tell one from the other.

*Alternative rejected:* a positional prefix (`gate-3-listable`) to make tags sort in launch order. ClickUp sorts tags alphabetically, so the gate sequence reads as nonsense; but the tags are for grouping and filtering, not for reading as a sequence, and a number embedded in the name would have to be kept true to `GATE_SEQUENCE` forever.

### 4. Add-if-missing, never remove

The proposal states the scope; the design note is why the *asymmetry* is stable rather than merely unfinished. A missing owned tag has one plausible cause — the task predates tagging — and one correct response. A **present** owned tag that disagrees with the step has two, and they need opposite responses: the step was re-gated (correct the tag) or a person retagged deliberately (leave it). Adding is decidable without retained state; correcting is not. That is the whole line this change draws.

Its cost is stated in the spec: a re-gated step's task accumulates a second gate tag, and a hand-removed tag returns. Both are visible, neither destroys anything, and both become fixable by a later change that adds retention.

### 5. Discipline is tagged, though it cannot drift

`playbook_authoring.update_step` refuses to change a step's discipline — a discipline change is a retirement plus a successor step, which gets a fresh task carrying the right tag from creation. So `discipline:` will do real work exactly once, at backfill, and then never again.

It is still driven by the same add-if-missing rule as `gate:` rather than being special-cased to creation only. The rule costs nothing extra (a correct tag means zero calls), and writing "discipline is immutable, so tag it only at creation" would bake an invariant owned by another module into this one, where a later relaxation of that invariant would silently stop working.

## Risks / Trade-offs

- **Backfill burst against the ~100 req/min budget** → Every existing task needs up to two tag POSTs on the first pass after deploy. `clickup_sync_job.py` already sizes and accepts a spike of this order (the "~185 calls" first projection of a new launch). No throttling is added: the pass is convergent, so a run cut short by rate limiting resumes on the next one, and the backfill completes across a few passes instead of failing.
- **A tag write failing mid-task** → The spec requires the pass to survive it with a warning rather than fail. This matches the existing treatment of an assignee with no ClickUp account, and for the same stated reason: `scheduled-jobs` records only whether a run succeeded, so a failed run would hide a data gap behind a retry.
- **A person cannot keep a task untagged** → Accepted and stated in the spec. The alternative is retained state, which is the machinery this change exists to avoid.
- **`GET /folder/{id}` failing makes the space unresolvable** → The pass fails, as it already does when the folder is unconfigured. A launch projected without its tags would otherwise look correct while being silently incomplete.

## Migration Plan

No database migration — the change persists nothing. Deployment is the ordinary PR-to-`main` path.

The first pass after deploy seeds twenty tags and begins backfilling existing tasks; subsequent passes finish whatever the first did not. Rollback is a revert: tags already written stay on their tasks, harming nothing, and the vocabulary sits unused in the space until removed by hand.
