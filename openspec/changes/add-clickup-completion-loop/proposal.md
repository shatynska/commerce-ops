# add-clickup-completion-loop

## Why

Slice 3 (`introduce-launch-aggregate`) built the launch engine: outcomes are recorded against steps, gates evaluate blocking conditions, and every recording carries provenance — including a `clickup` source no adapter yet produces. The ops team completes launch work in ClickUp, but nothing creates their tasks there and nothing brings completion back, so today a person would have to re-report every completion by hand — exactly the "depends on a person remembering it" failure the system exists to remove. This change closes the loop the README's state-ownership split promises: ClickUp owns human completion, Postgres records it, and the known webhook-drift obligation is discharged by a periodic reconciliation pass (domain map, slice 4).

## What Changes

- The launch module gains a ClickUp synchronization capability in its infrastructure layer — the domain and application layers are untouched; completion enters through the existing `record_step_outcome` use case with `Provenance(source="clickup", ...)`.
- **Per-launch list projection**: each launch gets its own ClickUp list, created in a configured folder; every human-attested, non-prohibited step of the pinned playbook version is projected as one task in that list, with its due date derived from the launch date and the step's timing anchor.
- **Step↔task mapping**: a launch-infrastructure Postgres table records which ClickUp task represents which step of which launch (and which list represents the launch), so webhook payloads and reconciliation reads can be resolved back to steps.
- **Webhook intake**: a FastAPI route (the launch module's first driving adapter) verifies ClickUp's webhook signature against a configured secret and records task status changes — a task reaching a closed status records `Satisfied`; a reopened task records `InProgress`. No other outcome is producible from ClickUp in this slice.
- **Reconciliation pass**: a scheduled job (existing `scheduled-jobs` machinery) that converges each active launch toward its desired ClickUp state — creates the list and any missing tasks, updates due dates that drifted (a moved launch date cascades here), and records completions the webhook missed by reading task state back.
- Two new optional environment variables declared in the existing settings model: the parent folder for per-launch lists and the webhook signing secret.

## Capabilities

### New Capabilities

- `launch-clickup-sync`: the completion loop between a launch's step schedule and ClickUp — per-launch list and task projection with due dates, the step↔task mapping record, webhook intake mapping ClickUp status changes to recorded step outcomes, and the periodic reconciliation pass that covers task creation, due-date drift, and missed webhooks.

### Modified Capabilities

- `clickup-task-client`: the shared client gains the operations the loop needs beyond create/update task — creating a list inside a folder, and reading task state back (the tasks of a list, each with its identity, status, closed-type judgement, and due date) — under the same authentication and error-propagation requirements.

## Impact

- **Code**: new `launch/infrastructure/driven/` sync components and mapping model + Alembic migration; new `launch/infrastructure/driving/` webhook route (mounted in `main.py`) and reconciliation job module (added to `registrations.py`'s one list); extended `shared/infrastructure/driven/clickup_client.py`; two new optional fields in `shared/application/settings.py`.
- **Specs**: `launch-instance`, `scheduled-jobs`, and `runtime-configuration` requirements are unchanged — recording semantics, job registration, and variable declaration all follow their existing requirements.
- **External**: the ClickUp webhook itself is registered once, operationally (ClickUp's webhook-creation endpoint, outside this application); the application only verifies and consumes deliveries. Task topology beyond one list per launch (statuses beyond closed/open, `Blocked`/`NotApplicable` from ClickUp, tasks for `ai-assisted` or metric-attestation work) is deliberately out of scope.
