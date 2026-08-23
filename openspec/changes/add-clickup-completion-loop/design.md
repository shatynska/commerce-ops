# add-clickup-completion-loop — Design

## Context

See proposal.md — Why. The constraints that shape the approach:

- Slice 3 left the exact seam this slice plugs into: `record_step_outcome` accepts `Provenance(source="clickup", ...)`, re-recording replaces without reversing an opened gate, and hazard restrictions apply on every recording. The domain and application layers need no change.
- There is **no event bus and no driving adapter for launch commands yet** — use cases return their events to a caller that does not exist outside tests. Nothing can "react to `LaunchStarted`" today.
- The launch module's ports (`LaunchStore`) expose only `get_by_product_id`/`save`; nothing enumerates launches.
- The shared ClickUp client writes (create/update task) but cannot read, and cannot create lists.
- `scheduled-jobs` machinery (schedule + tolerance in one registry, retries with backoff, run recording) and the `registrations.py` one-list pattern already exist; `runtime-configuration` requires new variables to be declared in `Settings`.
- User decisions recorded 2026-08-23: **a list per launch** (not one shared list), and **closed → `Satisfied` only** (no custom-status mapping in this slice).

## Goals / Non-Goals

**Goals:**

- Convergent, idempotent synchronization: every pass drives ClickUp toward the state the launch schedule implies, and drives recorded outcomes toward what ClickUp says — so a crashed pass, a missed webhook, or a moved launch date all heal on the next pass with no special cases.
- All completion recording flows through `launch.application`'s public use cases; the sync never touches launch tables' outcome rows directly.

**Non-Goals:**

- Two-way status: the system never writes task status to ClickUp (a step Satisfied via a non-ClickUp path leaves its task open — accepted for this slice).
- `Blocked`/`NotApplicable` from ClickUp, tasks for `ai-assisted`/`automated` steps or metric conditions, webhook self-registration, task description content beyond a name (richer task bodies can come with the briefing slice).

## Decisions

### One convergence pass owns projection; the webhook is only the fast completion path

The reconciliation job does all structural work — create the launch's list, create missing tasks, correct drifted due dates — *and* pulls missed completions, every run, by diffing desired state (pinned playbook × launch date) against the mapping table and ClickUp's actual task list. The webhook route does exactly one thing: translate a verified status change into the same recording call, sooner.

- *Alternative — react to `LaunchStarted`/`LaunchDateMoved` where they are emitted*: rejected. No driving adapter emits them yet, and handling them in the use cases would couple `launch.application` to ClickUp, inverting the ports direction. Desired-state convergence also subsumes every event case (start, date move, playbook task gaps) with one mechanism.
- *Consequence*: a new launch's tasks appear on the next pass, not instantly. Acceptable — launch work is planned in days, not minutes.

### Mapping lives in two launch-infrastructure tables

`launch_clickup_lists` (product_id → list_id, one row per launch) and `launch_clickup_tasks` (product_id + step_id → task_id, unique on both sides, plus the task's last observed closed state — the column the transition-based recording decision below rests on), owned by `launch/infrastructure/driven/models.py` with an Alembic migration. Per the domain map's open question, ClickUp mapping stays module infrastructure until it grows rules of its own; no domain object learns of task ids.

### Enumeration is a repository method, not a port extension

The job needs "every active launch" (current gate short of `graduated`). `LaunchRepository` gains `list_active()` used directly by the sync job — driving and driven adapters share the infrastructure layer, so `.importlinter` permits it, and `LaunchStore` (the port) stays exactly what the use cases need. Recording still goes through `record_step_outcome` with the repository satisfying the port.

### The webhook trusts its verified payload; reconciliation reads ClickUp

ClickUp's `taskStatusUpdated` delivery carries the new status (and its `closed`/`open` type) plus the acting user in its history items. Since the delivery is HMAC-verified, the route acts on the payload without a read-back call — the reconciliation pass is the authoritative pull that corrects anything a payload got wrong or a delivery missed. Signature check: HMAC-SHA256 of the raw request body with `CLICKUP_WEBHOOK_SECRET`, constant-time compare against the `X-Signature` header, mirroring the Slack adapter's verifier discipline.

### Recording is transition-based, keyed on the last observed state — never on the recorded outcome

Each `launch_clickup_tasks` row retains the closed state last observed for its task; **every** observation — webhook delivery and reconciliation read alike — updates it. An outcome is recorded only on a transition of that observed state: not-closed → closed records `Satisfied`, closed → open records `InProgress`; no transition records nothing, whatever outcome the step carries. One translation function serves both paths.

- *Why not compare against the step's recorded outcome (skip-if-agreeing)*: rejected — reviewed 2026-08-23. A read exposes state, not history, so "open" cannot be told apart from "reopened": comparing against the recorded outcome would overwrite `NotStarted`, `Blocked`, `NotApplicable`, and attested `Satisfied` outcomes with `InProgress` on every pass — and the one-way-status non-goal *guarantees* an attested `Satisfied` sits next to a still-open task. The observed-state column is what makes reopening detection sound.
- *Why not completions-only on the pull side*: it would shrink the spec's "completion or reopening" reconciliation promise; the one extra column honors it in full, with no extra ClickUp calls.
- *Consequence for duplicates*: a re-delivered webhook shows no transition against the already-updated observed state and records nothing — the spec's "repeated delivery changes nothing" falls out of the same mechanism.

Actor provenance: the ClickUp user from the webhook's history items; the reconciliation pass, which cannot see who closed a task, records the same source (`clickup`) and evidence with the reconciliation's own identity (`clickup-reconciliation`) as recorder — the delta spec words provenance exactly this way.

### Due dates and the closed-type judgement

A task's due date is the **end** of the step's resolved `AnchorPeriod` (the date by which the work must be done); no launch date, an open-ended anchor, or a recurring anchor → no due date, and the pass clears a stale one if the date becomes unresolvable. Drift is detected by *reading* each task's due date back (the client's read model carries it — see the `clickup-task-client` delta) and updating only tasks whose value differs, which is what keeps the pass at one read per launch plus writes proportional to actual drift. ClickUp statuses are compared by their `type` field (`closed` vs anything else), never by status name — the team can rename statuses freely.

### A vanished task heals unless the work is finished

The list read doubles as existence check: a mapped task absent from the read is re-projected (new task, mapping row replaced, observed state reset) when the step's recorded outcome is non-terminal — deleting a task is not a sanctioned way to complete work, and the convergence goal demands the hole heal. A terminal step's vanished task is left alone: recreating a task for finished work would be noise.

### List names come from the catalog, through its public surface

`ProductId` is contractually opaque ("generated, never parsed for meaning"), so the per-launch list is named from the catalog product's name and SKU, read via `catalog.application.get_product_by_id` — the same public-surface crossing slice 3 already uses for the graduation stamp, so no new kind of module dependency appears.

### Configuration

Two new optional `Settings` fields: `clickup_launch_folder_id`, `clickup_webhook_secret`. Optional keeps `runtime-configuration`'s "importing and starting do not require configuration" intact and degrades only this capability when absent: the route rejects deliveries (spec'd), the job fails its run visibly (spec'd) — never a silent skip.

## Risks / Trade-offs

- [ClickUp rate limits (~100 req/min) vs ~100–150 task creations for a new launch] → the pass creates sequentially and is convergent: a rate-limited run fails visibly, `scheduled-jobs` retries with backoff, and the next run resumes where the mapping table says it left off. No pass is ever "partially applied" in a way that needs repair.
- [Create-then-record crash window: a task created in ClickUp before its mapping row commits] → order each unit as create → record mapping → continue; a crash between the two leaks at most one duplicate task per step into ClickUp (visible, human-deletable), never a lost completion. Listing ClickUp before creating narrows the window per pass.
- [A reopened task racing gate advancement] → already absorbed by slice 3: re-recording never reverses an opened gate; the reopen records `InProgress` and simply blocks *future* evaluation if the gate had not advanced.
- [Webhook endpoint is internet-facing] → signature verification before any parse-dependent behavior; unverified requests are rejected with no side effects; no secret configured means everything is rejected, not accepted.
- [Reconciliation reads every active launch's list every run] → bounded: MVP concurrency is a handful of launches; one `GET` per launch list per run (plus pagination) is far under limits. Cadence: every 30 minutes, tolerance sized per the `scheduled-jobs` overdue conventions.

## Migration Plan

1. Alembic migration adds the two mapping tables (no changes to existing tables) — reversible with a plain drop.
2. Deploy; without the two new variables the app behaves exactly as before (route rejects, job fails visibly — configure vars to activate).
3. Operationally: create the ClickUp webhook (one `POST /team/{team_id}/webhook` with the route's public URL, `taskStatusUpdated` events), store the returned secret and the chosen folder id in the environment.
4. Rollback: unset the variables (loop goes quiet, launches keep working through other recording paths), or revert the deploy; the mapping tables are inert without the loop.
