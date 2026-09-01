# Implementation notes

Recorded during apply. Facts transcribed here because the code carrying them is
deleted by this change.

## Task 1.2 — the metric identifiers, transcribed before deletion

Transcribed verbatim from `_AUTHORED_METRIC_CONDITIONS`
(`src/commerce_ops/launch/domain/launch_playbook.py:454-469`) before task 4.1
deletes it. This was their only source.

| Gate | Metric identifier | Threshold text (becomes the step's description) |
|---|---|---|
| `stock-ready` | `units-fulfillable` | 60–80 fulfillable units, excluding Vine |
| `phase-one-complete` | `sales-velocity` | ~10 units/day sustained |
| `phase-one-complete` | `organic-share` | organic share above 40% |
| `graduated` | `tacos` | TACOS falling |
| `graduated` | `review-rating` | rating stable at 4.5 |

Five conditions. **Four** are carried forward onto steps; `review-rating` is
removed with no successor, no reference row restating it (design.md, Decision 8).

The threshold texts above are the *conditions'* wording, not the steps'. A
seeded step's description is its reference row transcribed, which the seeding
requirement governs; these are recorded only as the record of what each
condition said.

## The gate on task 1.1 is wider than the plan said

Recorded 2026-09-01, from the local Docker Postgres
(`commerce-ops-postgres-1`). The plan gates the drop on
`launch_metric_attestations` being empty. Two **other** places carry the
retired vocabulary, and both block a migration rather than the drop:

| Where | `commerce_ops` (dev) | `commerce_ops_test` |
|---|---|---|
| `launch_metric_attestations` rows | 116 | — |
| `launch_step_progress.source = 'attestation'` | 81 | 1655 |
| `launch_journal_entries.kind = 'metric-attested'` | 0 | 1 |

All of it is fixture residue — the evidence text reads
`"attested for this fixture"` and `"inventory dashboard export"`, dated
2027 — written by the integration tier, not by the application. **No
source file writes `source="attestation"`**; it was a permitted value
that only test fixtures ever used.

That matters for the deploy: `b8e402cf17a9` narrows both CHECK
constraints, and a constraint narrowing is refused by Postgres while any
row still carries the value. So **before this change deploys, production
must be checked for all three**, not just the attestation table. The
migration failing is the safe outcome; it is designed to refuse rather
than to rewrite a recorded provenance, since rewriting one would falsify
what was recorded and deleting the row would lose an outcome.

The test database was cleaned of exactly the rows the new constraints
forbid, and both migrations then applied cleanly.

## Task 1.1 — BLOCKED, not run

`SELECT count(*) FROM launch_metric_attestations` against production has **not**
been run. This worktree carries no `.env` and no `DATABASE_URL`, so there is no
database reachable from here, and pointing a query at production is not
something to do unasked.

**Task 5.8 (drop `launch_metric_attestations`) is therefore not done**, per
design.md Decision 7: the drop is gated on that count being zero, and a
non-zero count sends this change back to design rather than proceeding.

Whoever has production access runs the count, records it below, and only then
writes the drop migration.

> Result: _not yet recorded_ — and note the count above is from the local
> dev database, which is **not** production. The user has recorded that
> production currently holds test data too, so a non-zero count there is
> not the halt condition design.md Decision 7 assumed; what it gates is
> whether anything must be preserved, and test data need not be.

## Task 7.3 — BLOCKED, not run

The integration tier needs a database (`tests/integration/conftest.py` resolves
`DATABASE_URL`, else `.env.test`, else `.env`). None resolves here, so the
migrate-then-prepare assertion has never executed. It is written and will run
wherever a database is configured.
