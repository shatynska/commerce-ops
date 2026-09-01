## Why

**A gate's metric condition is a step wearing a different type.**

`stock-ready` authors one metric condition (`launch_playbook.py:457`), satisfied only by a recorded attestation. `record_metric_attestation` is defined, exported and persisted — and no driving adapter calls it, so `launch_metric_attestations` holds zero rows and three live launches (`Disposable food trays 31`, `32`, `33`) sit at the fourth of eight gates waiting on a fact nobody can record.

The obvious repair is to give attestation a surface. This change argues the model is wrong instead, on the reference document's own evidence.

`author-playbook-steps`' design.md:73 enumerates six rows of `docs/reference/product-launch.md` that were **deliberately excluded** from the seed for *"restating a condition a gate already authors as a metric condition"* — `lp.inventory.040`/`041`, `lp.strategy.025`/`033`, `lp.ppc.048`, `lp.finance.036`. The exclusion is visible in `alembic/data/playbook_reference.yaml`: 358 ID-bearing rows in the reference document, 352 seeded, `lp.inventory.039` at line 3272 and `lp.inventory.042` at line 3492 with nothing between them.

`lp.inventory.040` reads, verbatim:

> *INVENTORY GATE: do not make the listing live until 60-80, and hopefully 100+, units are FULFILLABLE - not in transfer, not reserved, not inbound.* — **AGENT:** INVENTORY · **WHEN:** T-7 · **SOURCE:** 07/24/2024 Andrew's Launch Checklist

A step. With an identifier, a discipline, a timing anchor and a source citation. The source material never modeled these as a second kind of thing; the split was introduced by `complete-playbook-definition` and the reference rows were removed to avoid expressing one obligation twice.

Restoring them removes a concept rather than adding a surface, and unblocks production through machinery that already runs end to end — a blocking step converges to a ClickUp task, a person completes it, the gate opens.

## What Changes

- **Restore the six excluded rows as blocking steps**, each seeded `draft` and each carrying the `metric_id` of the condition it restates.
- **A step MAY declare a `metric_id`** — optional, opaque, absent on almost every step. This preserves the launch↔monitoring join that `MetricId` was made a shared value object to provide (`complete-playbook-definition` design.md:33), now carried by the step rather than by the gate.
- **BREAKING — a gate no longer carries authored metric conditions.** `MetricCondition`, `_AUTHORED_METRIC_CONDITIONS` and the `GateCondition` union are removed; `conditions_for_gate` answers step obligations alone.
- **BREAKING — metric attestation is removed entirely.** `MetricAttestation`, `Launch.record_metric_attestation`, its use case and export, the `launch_metric_attestations` table and its rehydration, the `metric-attested` journal kind, and `attestation` from `PROVENANCE_SOURCES`.
- The threshold text moves from the gate to the step's `description`, where it is admin-editable and displayed — a gate stalled on a stock check now states its own reason, which the gate condition never did.

## Capabilities

### New Capabilities
None. This change removes a modeling distinction; every obligation it touches is already expressible as a blocking step.

### Modified Capabilities
- `launch-playbook`: *A gate carries authored metric conditions* is REMOVED; the load-time coherence rules (spec:624, :644, :696) drop the empty-threshold fault; *Gate conditions unify step obligations and metric conditions* is MODIFIED to cover step obligations alone; a step's declared attributes gain an optional metric identifier; the seeding requirement's six-row exclusion (spec:290, :304) is MODIFIED to seed them.
- `launch-instance`: *A metric condition is satisfied by human attestation until live evaluation exists* is REMOVED; the persisted launch record (spec:11, :44) no longer carries attestations; *A gate opens only when every blocking condition attached to it is satisfied* (spec:99) drops its metric-condition clause; and *A step outcome is recorded with provenance* (spec:65) narrows its source set to `clickup` and `automated`.
- `launch-journal`: the `metric-attested` entry kind and its `gate_id` detail are REMOVED.
- `launch-admin`: the journal row rendering for `metric-attested` (spec:1076-1082, :1158) is REMOVED.
- `launch-gate-progression`: the two clauses of *A recurring pass advances every launch whose gate may open* that name metric attestations among the facts a gate is judged on are MODIFIED to drop them.
- `launch-clickup-sync`: the projection exclusion for gate metric conditions (spec:222) is MODIFIED, the excluded thing no longer existing.
- `playbook-authoring`: metric conditions leave the framework the capability may not write (spec:181), and the optional metric identifier joins *A step can be created*'s authorable shape (spec:10) and gains a requirement of its own.
- `playbook-admin`: *The step form carries every authorable field* (spec:569) gains the metric identifier, since a field the authoring capability accepts and the form omits is a field nobody can set.
- `launch-step-automation`: *A handler receives the step, the launch and the product, and attributes nothing* (spec:77) stops naming `attestation` among the sources a handler cannot claim.

## Impact

- **Domain**: one `else:` branch in `_unsatisfied_gate_conditions` (`launch_run.py:675-684`) and the types it reaches. No new rule.
- **Migration**: two schema migrations — the nullable `metric_id` column, then dropping `launch_metric_attestations`. The six rows arrive through the preparation step, not a migration (design.md, Decision 6). The drop is irreversible and rests on the table being empty — to be confirmed against production before it runs, not inherited from this document.
- **Tests**: `author-playbook-steps`' task 3.1 asserts the six identifiers are absent and inverts.
- **Three gates lose five conditions, and four of them gain a successor.** `stock-ready` loses `units-fulfillable`; `phase-one-complete` loses `sales-velocity` and `organic-share`; `graduated` loses `tacos` and `review-rating`. The six restored rows carry **four** distinct metric identifiers between them — `lp.inventory.040` and `lp.inventory.041` both restate `units-fulfillable`, and `lp.ppc.048` states four qualitative criteria rather than a threshold on one quantity, so it is blocking without an identifier (design.md, Decision 8).
- **`review-rating` is removed with no successor, deliberately.** `author-playbook-steps` design.md:73 records that no reference row restates it, so there is no step to seed for it and the change does not invent one. `graduated` requires human confirmation, so a person still weighs rating stability before that gate opens; what goes is the machine-checkable obligation, not the judgement. Recorded here rather than discovered during implementation.
- Each successor is a `draft` step holding nothing until activated, so the first progression pass after deploy may carry a launch further than `stock-ready` — as far as the next gate whose own blocking steps are unresolved, or that requires a confirmation nobody has given.
- **The three parked launches advance past `stock-ready` unchecked, permanently.** The six steps are seeded `draft`, consistent with every other seeded row, and a draft step holds no gate — so removing the condition leaves `stock-ready` with one fewer obligation and nothing replacing it until someone activates `lp.inventory.040`. Gate readiness reads only the launch's current gate (`launch_run.py:666`), so a launch already past `stock-ready` is never pulled back by that activation. This is accepted deliberately: the alternative is to seed the six `active`, which contradicts *Every seeded step is a draft nobody owns* and holds three real launches on a check whose surface this change is removing.
- No gate can be left unheld by the removal. The gate-holding floor makes a set that leaves a gate unheld unservable (`launch-playbook` spec:367); launches are running, so every gate already carries at least one active blocking step.
- `add-metric-attestation-surface` is superseded and should be abandoned rather than merged.

## Deferred, deliberately

Nothing records **what the number was**. An attestation required evidence; a completed ClickUp task records that someone completed it. Capturing the value needs an input the free ClickUp plan cannot provide, so it belongs to a later change using a Slack modal — the same mechanism the rejection-reason entry in `docs/deferred-work.md` needs. Until then a metric step is pass/fail, and no launch history carries the stock level its gate opened on.
