# product-monitoring delta — introduce-launch-briefing

The daily product-name listing is superseded by the launch briefing (`briefing` capability, this change). Its cadence and failure-handling obligations are not lost: each is re-expressed over the briefing report in the `briefing` spec. This empties `product-monitoring`; the capability returns in slice 7 as the metric registry and evaluation engine, specified fresh.

## REMOVED Requirements

### Requirement: Daily Cadence Lists Existing Product Names

**Reason**: The daily message is now the launch briefing — attention items derived from launch state, silent when clean — rather than an unconditional listing of product names. Two daily messages would dilute the briefing's silent-when-clean discipline.
**Migration**: The briefing takes the daily schedule slot (`briefing` — "The daily briefing runs on a schedule"). "Which products exist" is answerable on demand through Omni; no scheduled listing replaces it.

### Requirement: Report Delivery Failure Is Decoupled From The Trigger

**Reason**: The obligation survives, but its subject — the daily listing's report — is retired with the listing.
**Migration**: Re-expressed verbatim in substance over the briefing: `briefing` — "Delivery failure is decoupled from the run".

### Requirement: Database Read Failure Is Surfaced, Not Treated Like A Delivery Failure

**Reason**: The obligation survives, but its subject — the daily listing's product read — is retired with the listing.
**Migration**: Re-expressed over the briefing's assembly: `briefing` — "A failure to assemble is surfaced, not treated like a delivery failure".

### Requirement: The Daily Cadence Runs On A Schedule

**Reason**: The daily cadence's content is now the briefing, whose schedule is specified where the briefing lives.
**Migration**: `briefing` — "The daily briefing runs on a schedule" carries the same schedule-governed, not-externally-startable obligations under `scheduled-jobs`.
