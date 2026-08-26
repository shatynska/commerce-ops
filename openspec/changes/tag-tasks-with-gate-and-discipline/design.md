## Context

See `proposal.md` — Why. The constraints that shape the approach, and are not obvious from the requirements:

- **Tags do not ride `PUT /task/{id}`.** Every field the projection manages today — name, description, assignees, due date — is a field on the update body. Tags are not: ClickUp exposes `POST /api/v2/task/{task_id}/tag/{tag_name}` and `DELETE` of the same, and accepts `tags` only in the *create* body. So tagging is the first part of this projection whose write is a separate call rather than another key in a dict.
- **Tags need no prior existence.** Attaching a tag name to a task creates it in that task's space if it is not already there. This is the premise the first six drafts of this change got *wrong*: they asserted a tag must exist first, built a seeding subsystem on that, and spent most of six review rounds arguing about the subsystem's failure model. The assertion was never probed — what was probed was whether seeding *works*, which is a different question. See the last three rows below.
- The projection is convergent by construction (`clickup_sync.py` module docstring): every pass drives ClickUp toward what the launch implies, and a crashed pass heals on the next one. Tagging must not introduce a step that only works if it runs exactly once.

Verified against the live API on 2026-08-26 with the deployment's own token, in the same spirit as `CLICKUP_TASK_NAME_LIMIT`'s measured 2048:

| Call | Result |
|---|---|
| `GET /folder/{CLICKUP_LAUNCH_FOLDER_ID}` | `200`, returns the folder's `space` object carrying that space's id |
| `GET /space/{id}/tag` | `200`, `[]` — the space held no tags |
| `POST /space/{id}/tag` | `200` |
| `POST /space/{id}/tag` again, same name | `200`, no duplicate created |
| `POST /space/{id}/tag` with the name `gate:listable` | `200` — a `:` in a tag name is accepted |
| `POST /list/{id}/task` with `"tags": ["gate:listable"]` | `200`; reading the task back reports `["gate:listable"]` — tags in the create body do land |
| `POST /task/{id}/tag/gate%3Alistable` | `200` — the central write; `:` survives percent-encoded in the path segment |
| the same add, repeated | `200`, and the task still carries the tag once — the add is idempotent |
| `POST /space/{id}/tag` re-sent with different colours | `200`; the stored colours were unchanged — re-creating does not alter an existing tag. ClickUp appears to ignore supplied colours on this path entirely (both sends stored `#000000`/`#ffffff`), so the guarantee holds for a narrower reason than "it preserves what you set" |
| `DELETE /space/{id}/tag/{name}` | `200` |
| `POST /list/{id}/task` carrying a tag the space does **not** hold | `200`, and the task carries it — an unknown tag is neither rejected nor dropped |
| `POST /task/{id}/tag/{unknown name}` | `200`, and the task carries it |
| space tags before / after that attach | `[]` → `['<the name>']` — **attaching a tag creates it in the space**; confirmed for `:`-bearing names by both routes |

Every probe cleaned up after itself; the space was left holding no tags, as found. The last three rows are decisive: they remove the seeding concern from this change entirely, and with it the space resolution, the vocabulary read, the create-tag call, the readiness threading, and the whole fault model those required.

## Goals / Non-Goals

Beyond the proposal's scope, at design level:

**Goals.** Add no persisted state — deliberately deferred rather than avoided as costly; the mapping already retains four values and a fifth is one column. Add no runtime configuration, and reach nothing but the tasks themselves. Keep the steady-state cost at **zero write calls** once tags are in place, and no extra reads at all: the tags a pass judges against arrive in the task list it already fetches. Let no fault in the tag concern stop the projection tagging follows.

**Non-Goals.** No removal path, and therefore no decision about whether a person's retagging is preserved or overruled — the question the name/body/assignee rules each had to settle, and the one this change is shaped to avoid needing. No colour or ordering control over tags: ClickUp assigns colours, a person may change them, and the system leaves them alone.

## Decisions

### 1. Own two prefixes, and read them as the retained value

The system owns `gate:` and `discipline:`; every other tag is a person's.

This is what lets the change persist nothing, but the reason needs stating precisely, because the obvious phrasing is false. An owned tag on a task is **not** a record of what the system put there: the vocabulary is space-wide and appears in ClickUp's tag picker, so a person can attach `gate:commit` by hand and nothing distinguishes that from the system's own write. What is true is narrower and sufficient — the add-if-missing rule needs only a tag's **presence**, never its authorship. Retained state is what a rule needs when it must tell an authored change from a person's edit, and this rule never has to.

The corollary is a warning for whoever adds correction later: correcting a tag *does* need authorship, so it cannot be built on presence alone. A correction rule reading a stale `gate:commit` as the system's own would remove a tag a person may have put there deliberately.

*Alternative rejected:* unprefixed tag names (`listable`, `listing`). The gate and discipline vocabularies contain words a team would plausibly use for its own labels — `live`, `setup`, `price`, `customer` — and an unprefixed namespace could not tell one from the other.

*Alternative rejected:* a positional prefix (`gate-3-listable`) to make tags sort in launch order. ClickUp sorts tags alphabetically, so the gate sequence reads as nonsense; but the tags are for grouping and filtering, not for reading as a sequence, and a number embedded in the name would have to be kept true to `GATE_SEQUENCE` forever.

### 2. Add-if-missing, never remove

The proposal states the scope; the design note is why the *asymmetry* is stable rather than merely unfinished. A missing owned tag has one plausible cause — the task predates tagging — and one correct response. A **present** owned tag that disagrees with the step has two, and they need opposite responses: the step was re-gated (correct the tag) or a person retagged deliberately (leave it). Adding is decidable without retained state; correcting is not. That is the whole line this change draws.

Its cost is stated in the spec: a re-gated step's task accumulates a second gate tag, and a hand-removed tag returns. Both are visible, neither destroys anything, and both become fixable by a later change that adds retention.

### 3. Discipline is tagged, though it cannot drift

`playbook_authoring.update_step` refuses to change a step's discipline — a discipline change is a retirement plus a successor step, which gets a fresh task carrying the right tag from creation. So `discipline:` will do real work exactly once, at backfill, and then never again.

It is still driven by the same add-if-missing rule as `gate:` rather than being special-cased to creation only. The rule costs nothing extra (a correct tag means zero calls), and writing "discipline is immutable, so tag it only at creation" would bake an invariant owned by another module into this one, where a later relaxation of that invariant would silently stop working.

## Risks / Trade-offs

- **Backfill burst against the ~100 req/min budget** → Every existing task needs up to two tag POSTs on the first pass after deploy. `clickup_sync_job.py` already sizes and accepts a spike of this order (the "~185 calls" first projection of a new launch). No throttling is added: the pass is convergent, so a run cut short by rate limiting resumes on the next one, and the backfill completes across a few passes instead of failing.
- **A tag write failing on one task** → The spec requires the pass to survive it with a warning rather than fail. This matches the existing treatment of an assignee with no ClickUp account, and for the same stated reason: `scheduled-jobs` records only whether a run succeeded, so a failed run would hide a data gap behind a retry.
- **A person cannot keep a task untagged** → Accepted and stated in the spec. The alternative is one retained column, deliberately deferred for scope; see the proposal's non-goals for the honest form of that trade.
- **A backfill silently never completing** → Caught tag failures leave the run recorded as succeeded, so repeated rate limiting or a standing permission gap could stall the backfill while the deployment reports healthy. Accepted as consistent with the assignee precedent, and visible in the warning log rather than in the run record. This is the price of the bullet above and is named rather than hidden.

## Migration Plan

No database migration — the change persists nothing. Deployment is the ordinary PR-to-`main` path.

The first pass after deploy begins backfilling existing tasks, ClickUp creating each tag in the space as it is first attached; subsequent passes finish whatever the first did not. Rollback is a revert: tags already written stay on their tasks, harming nothing, and the tag names they caused ClickUp to create remain in the space — still attached to those tasks — until someone removes them by hand.
