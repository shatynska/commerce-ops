## 1. Tests derived from the specs

- [x] 1.1 Dispatch `ai-toolkit:openspec-test-writer` against the approved delta specs, producing tests and `test-manifest.md` before any implementation code is written (per `AGENTS.md` — Test design before implementation)
- [x] 1.2 Confirm the manifest covers every scenario in `specs/launch-gate-progression/spec.md`, and record a baseline run showing the new tests failing for the right reason

## 2. Ask cool-off storage

- [x] 2.1 Add a `launch_gate_ask_suppression` model in `launch/infrastructure/driven/models.py` — `(product_id, gate_id)` as the primary key, `delivered_at` timestamp, gate constrained to `GATE_IDS` the way `launch_positions.current_gate` is
- [x] 2.2 Write the Alembic migration creating the table (no data migration, no backfill)
- [x] 2.3 Add the driven adapter in `launch/infrastructure/driven/gate_ask_suppression.py`, following `field_gap_suppression.py`: read the record for a launch and gate, and record a delivery **or a rejection** — a delivery written only after it succeeds, never before

## 3. The progression use case

- [x] 3.1 Make `Launch._unsatisfied_conditions` a public read, unchanged in behaviour, so the pass and `advance_gate` judge a gate by the same computation (design.md — Decision 3). No other domain change belongs to this task or to this change
- [x] 3.2 Add a `progress_launch` use case to `launch/application/use_cases.py` taking the **product identifier** and reading the launch itself under the lock — never one the caller loaded before it, and treating an absent launch record as a no-op for that product rather than a contained failure, since a launch may be deleted by hand between the walk's read and the lock — that asks the launch whether the current gate may open — the public read task 3.1 exposes, never the launch report, which cannot answer it — and commands `advance_gate` only for a gate that read says may open, repeats while gates keep opening, and stops when the gate may not open **or the launch reaches the final gate** — the launch can arrive there mid-cascade, which the walk's launch set cannot govern (design.md — Decisions 3 and 4)
- [x] 3.3 Treat a gate declining to open as the cascade's stop, committing the crossings already made and the refusal `advance_gate` journaled; let any other exception unwind the transaction and reach the pass's containment (design.md — Decision 6)
- [x] 3.4 Have it take the served playbook as an argument rather than reading one per launch, so the readiness the pass determined once before the walk is the readiness every launch is judged against
- [x] 3.5 Have it return, alongside the events, whether the launch is now awaiting confirmation and on which gate, so a caller can decide whether an ask is owed without re-reading the launch
- [x] 3.6 Export `progress_launch` from `launch/application/__init__.py`'s `__all__`
- [x] 3.7 Add a gate-decision use case that resolves a Slack identity through the roster, refuses an unknown, inactive or stale-gate decision with a distinct reason for each, refuses a decision naming the final gate, and records the `GateApproval` in its own transaction — **not** inside the cascade's, so a cascade that fails cannot discard a decision a person actually made (design.md — Decision 6); modelled on `automated_decisions.py`'s `Decision` return shape rather than raising
- [x] 3.8 Require the roster reader to answer who the roster carries *including deactivated entries*, so an inactive person is refused as inactive rather than as unknown — the incident `launch-step-automation`'s roster requirement records
- [x] 3.9 Raise the wiring refusal — for an unreadable collaborator and for no collaborator at all — **before** the deciding identity is judged, so a decision already refused on grounds independent of the roster keeps its own refusal
- [x] 3.10 Add a shared advisory-lock helper for a product in `launch/infrastructure/driven/` — the key derivation **and** the acquire, using the transaction-scoped lock so it is released by the transaction ending. Sharing only the key would let the two adapters differ on scope, and a session-scoped lock on a pooled connection outlives its transaction and travels to the next borrower of that connection
- [x] 3.11 Refresh the ask cool-off record when a **rejecting** decision is recorded, so the day runs from the decision — the decision use case therefore holds the suppression port too; the transaction that makes the two writes land together is opened by the adapter (task 5.5), since `transaction()` is shared infrastructure the application layer may not import

## 4. The scheduled pass

- [x] 4.1 Add `launch/infrastructure/driving/gate_progression_job.py` with `PROGRESSION_SCHEDULE = "*/10 * * * *"` and a tolerance exceeding the longest gap between consecutive runs, which is what `scheduled-jobs` requires — comfortably longer than the worker's own liveness tolerance as well, so an absent worker becomes visible before the work it failed to run
- [x] 4.2 Determine readiness once, before the walk begins, rather than per launch; stand down when the served playbook read is refused as not ready: advance nothing, post nothing, log the unheld gates, and record the run as **succeeded** — following `clickup_sync_job.py`'s stand-down, not only its containment
- [x] 4.3 Walk `LaunchRepository.list_active` for the candidate product identifiers — `list_active` already excludes launches at the final gate, which is what keeps the graduation exclusion true of the walk as well as of the ask (design.md — Decision 8) — and for each open `transaction()`, take the product's advisory lock, and call `progress_launch` inside it — `transaction()` is shared **infrastructure** and an application-layer import of it breaks the module boundary task 6.4 checks, so the lock is taken here and in tasks 5.5 and 5.6, never in the use case (design.md — Decision 6)
- [x] 4.4 Post the ask outside the lock, so a slow or failing delivery never holds a launch against the decision path (design.md — Decision 6)
- [x] 4.5 Contain a per-launch failure, report each one as it happens naming the product, and fail the run in aggregate naming every launch that failed — following `clickup_sync_job.py`'s containment, including letting a cancellation propagate rather than recording it against a product
- [x] 4.6 Restore the shared store after a contained failure so the next launch can be attempted, and end the walk where it cannot be restored — `clickup_sync_job.py`'s `_restore_after_store_fault` shape, which applies here because this pass also writes as it walks
- [x] 4.7 For a launch left awaiting confirmation, post the ask unless a suppression record younger than 24 hours exists; record the delivery only after it succeeds
- [x] 4.8 Report a failed ask delivery without failing the run, leaving the gate eligible for the next pass
- [x] 4.9 Add `ASK_COOL_OFF = timedelta(hours=24)` as a module constant with the reasoning `automation_pass.COOL_OFF` records — never configuration

## 5. The Slack ask and its decisions

- [x] 5.1 Add `launch/infrastructure/driving/gate_confirmation.py` composing the ask message: the product, the gate, an approve and a reject control, the button value carrying `{product_id, gate_id}` (design.md — Decision 9)
- [x] 5.2 Register the action listeners through `contribute_listeners`, acknowledging within Slack's timeout independently of the work the press triggers, as `automation_confirmation.py` does
- [x] 5.3 Reply to the presser with what the decision did, derived from the launch as it stands once the lock is held: whether the gate they approved opened — it may have been the pass that crossed it — or, where it did not, the condition that now blocks it
- [x] 5.4 Refuse a decision arriving while the served playbook cannot hold a launch, recording no approval and telling the decider why, so the decision path stands down where the pass does
- [x] 5.5 Wrap the **rejecting** path in `transaction()` at the adapter, so the rejecting approval and the cool-off refresh land together — delta R5 requires it, and a torn write either re-proposes a gate a person has just declined or silences one for a day with no decision recorded
- [x] 5.6 After the approval is recorded, run the advance from the adapter: open `transaction()`, take the product's advisory lock, and call `progress_launch` inside it, so a press landing inside a pass window waits rather than crossing the same gate twice. The approval write has already committed by then and is untouched by this transaction's outcome (design.md — Decision 6)
- [x] 5.7 Handle `UnreadableRosterError` by its own type: tell the presser their decision was not processed without implicating their roster entry, and log the wiring fault where operators see it
- [x] 5.8 Enforce the final-gate exclusion in the ask and in the decision intake, so the scope boundary Decision 8 draws holds even if the pass is later given a launch set that includes the final gate

## 6. Wiring

- [x] 6.1 Register the new job in `worker.py` and inject its collaborators after `register_all()` — never at import — following how `clickup_sync_job.read_product` and `read_people` are injected
- [x] 6.2 Register the Slack listeners in the HTTP process alongside `automation_confirmation`'s; the worker runs the job, the HTTP process does not, and neither registers the other's concern
- [x] 6.3 Confirm both processes' schedule registrations hold the new work with the same tolerance, as `scheduled-jobs` requires — a schedule only one process knows about makes the freshness endpoint disagree with the worker
- [x] 6.4 Confirm `import-linter` contracts still pass — in particular that no `application` layer imports an infrastructure layer, and that `launch` names neither `briefing` nor another bounded context's internals. The shared kernel is the stated exception and is why the driving adapters in tasks 4.3, 5.5 and 5.6 may import `transaction()`, exactly as `clickup_sync_job.py` already does

## 7. Verification

- [x] 7.1 `uv run pytest tests/unit tests/agents` green
- [x] 7.2 `uv run pytest tests/integration` green, including the new table's migration applying to a fresh database
- [x] 7.3 `ruff check`, `ruff format --check`, `mypy` clean
- [x] 7.4 Confirm the settings drift check passes — this change adds no runtime variable, so `tests/unit/shared/application/test_settings.py` should need no edit; if one is needed, the four obligations in `AGENTS.md` — Deployment and configuration apply
- [ ] 7.5 Before the first run against a deployment, count the launches `list_active` returns there and how many stand at a satisfied confirmation gate — the first pass takes an empty cool-off table, so every one of them is asked in a single run, and no requirement caps asks per run
- [ ] 7.6 Verify by hand against a test launch: satisfy a `commit` step, watch the pass ask in Slack, approve, and confirm the gate opens and the journal records the approval and the crossing
- [x] 7.7 Confirm the expected stall — a launch advancing until it meets the first gate authoring a metric condition and stopping there, because attestation has no surface (design.md — Risks). This is the change working, not failing
- [x] 7.8 Confirm the journal stays readable: after the pass has run repeatedly against a launch it cannot advance, its journal holds no refused-advance entries from the pass (design.md — Decision 3)
- [x] 7.9 Cover the stand-down with an integration test over a step set that has not yet become ready, rather than by hand against a deployment: `playbook-authoring`'s ratchet refuses any write that would make a *ready* set unready, so the state cannot be produced on a working deployment without editing the database directly
- [x] 7.10 Re-check against `launch_playbook.py` that `phase-one-complete` still authors a metric condition, which is what makes the final gate unreachable and Decision 8's exclusion free of cost; if it no longer does, the deferral in `docs/deferred-work.md` becomes urgent rather than latent
