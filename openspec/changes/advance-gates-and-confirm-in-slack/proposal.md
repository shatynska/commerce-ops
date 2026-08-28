## Why

A launch's gate never moves. `Launch.advance_gate` and `Launch.approve_gate` are fully specified in `launch-instance`, fully implemented in `launch_run.py`, and covered by tests — but no driving adapter, route, Slack handler or scheduled job calls either one. Grepping every production import of `commerce_ops.launch.application` finds `start_launch`, `record_step_outcome`, `read_launch` and `read_launches` wired; `advance_gate`, `approve_gate` and `record_metric_attestation` have zero production callers.

The consequence is that every launch in the deployment sits at `commit` forever. ClickUp completions flow back and are recorded correctly, steps reach `Satisfied`, and `launch_positions.current_gate` never changes. The admin page is honest — it renders the stored gate — so a launch with its first two gates' work complete still highlights `commit`, and there is no action anywhere in the system that would move it.

This also leaves `current_gate` as a label rather than a valve: because it never advances, nothing can safely be made conditional on it. Making step release conditional on the gate (the follow-on change) is only sound once gates actually move, which is why this change comes first and alone.

## What Changes

- A new scheduled pass walks every launch short of the final gate and advances it past its current gate wherever that gate may open, repeating while gates keep opening — so the `AUTOMATIC` gates (`listable`, `stock-ready`, `live`, `ignition`) open on their own once their conditions are met, without anything having to notice the moment they were.
- The pass establishes that a gate may open **before** commanding the advance. `launch-journal` requires every refused advance to be journaled with the conditions that blocked it, so a pass that commanded blindly would append hundreds of identical entries per launch per day to the record kept for people to read.
- The pass stands down while the served playbook cannot hold a launch, recording the run as **succeeded** — the treatment `launch-clickup-sync` gives the same condition, and for its reason: a deployment still being set up must not be put into retry and overdue alerting for something retrying cannot fix.
- When a launch's current gate is `commit`, `order` or `phase-one-complete` and every condition except the approval is satisfied, the pass asks for that approval in Slack — a message naming the product and the gate, carrying approve and reject controls.
- Pressing the approving control resolves the presser's Slack identity through the roster, records an approving `GateApproval` naming them, and attempts the advance immediately so the presser is told what their decision did; pressing the rejecting control records the decision and leaves the gate closed.
- An ask is made only when no ask for that launch and gate was delivered within the last 24 hours. One rule covers three cases: a gate is asked about once rather than every pass; a gate left unanswered is asked about again the next day; and a *rejected* gate is not re-proposed until a day has passed, mirroring the cool-off `launch-step-automation` already applies to a rejected automated result.
- **`graduated` is out of scope.** Wiring it needs a persisted graduation marker the launch record does not carry, and the gate is unreachable in production regardless — see Impact, and `docs/deferred-work.md`.
- No change to the launch's **rules**. `advance_gate` still takes no target and opens exactly one gate; cascading through consecutive open gates is the pass calling it again, not a new domain operation. One additive domain change is needed and no more: the launch's readiness computation, today private, becomes a public read so the pass can ask whether a gate may open before commanding it.

## Capabilities

### New Capabilities
- `launch-gate-progression`: what causes a launch to advance and how a confirmation gate's approval is obtained — the recurring advance pass, its stand-down and its containment, the Slack ask for a gate awaiting confirmation and when one is owed, the approval decision intake and who may make it, and the ask cool-off.

### Modified Capabilities
<!-- None. `launch-instance` already specifies gate advancement, approval and
     `awaiting_confirmation` in full; this change supplies the trigger those
     requirements were written for and changes none of them. `briefing` already
     reports launches awaiting confirmation and needs no change to serve as the
     reminder for an ask left unanswered. -->

## Impact

- **New**: a scheduled gate-progression pass registered on the worker, alongside the ClickUp sync and automation passes; a driving adapter for the Slack gate ask and its action listeners, following `automation_confirmation.py`'s established shape; a driven adapter and table for the ask cool-off, following `field_gap_suppression.py`'s.
- **Unchanged**: `record_step_outcome` and its four call sites (`clickup_webhook.py`, `clickup_sync_job.py`, `automation_pass.py`, `automation_confirmation.py`). Advancement is a convergence pass rather than a consequence of recording, so no recording path gains a dependency on the catalog stamper or the Slack notifier. The cost is that a gate opens up to one pass-interval after its last condition is met, which is immaterial against a launch measured in days.
- **Wired for the first time**: the `advance_gate` and `approve_gate` use cases, and with them the `KIND_GATE_OPENED` and `KIND_GATE_APPROVAL_RECORDED` journal kinds. `KIND_ADVANCE_REFUSED` stays rare: the pass does not command an advance it expects to be refused, so it is reached only when a condition regresses between the pass's read and its command. A decision meeting a gate that regressed after the ask issues no command either, and is reported to the presser rather than journaled as a refusal.
- **Where launches will actually come to rest**: `stock-ready`, gate 4 of 8, because it authors a metric condition and attestation has no surface. The automatic gates open on their own up to that point; nothing reaches gate 5 until the deferred attestation work lands. Read `_AUTHORED_METRIC_CONDITIONS` in `launch_playbook.py` rather than trusting a gate list here.
- **Not reached**: `LaunchGraduated` and the catalog steady-state stamp. `graduated` authors metric conditions, `record_metric_attestation` still has no surface, and the persisted launch cannot distinguish a graduated launch from one standing at the final gate — a latent defect this change would be the first to expose. Recorded in `docs/deferred-work.md` as its own future change, together with the attestation surface it depends on.
- **Migration**: one new table for the ask cool-off. No data migration — every existing launch is test data, so stranded launches advance on the first pass or are reset by hand, and no approval is ever synthesized for an audit record.
- **Deferred to a follow-on change**: per-step release conditions (`starts_at_gate`, `after_step`), which stop gate-3 work from starting during gate 1. That change is unsafe before this one: gate-released steps against a gate that never advances would freeze every launch permanently.
