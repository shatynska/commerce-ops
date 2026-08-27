## Why

Every deploy since `seed-the-reference-step-set` has failed, and none of them failed because anything was wrong with the deployment. The image builds, the host pulls it, the container starts, the start chain runs to completion and the application serves traffic — but `docker compose up -d --wait` has already declared the container unhealthy and exited non-zero before that happens. `https://fuperia.shatynska.com/health` answered `{"status":"ok"}` while all three runs sat red.

The image's `HEALTHCHECK` is `--start-period=5s --interval=10s --retries=3`, which gives the container roughly 25 seconds to bind port 8000 before the third consecutive failure marks it unhealthy. It has been passing on the last of those probes for some time: the last four successful deploys each took **exactly 26.50s** from `Started` to `Healthy` — `32943840745`, `32949905323`, `32956273524`, `32958746253`, four for four. Four identical readings to the centisecond are the signature of a probe tick, not of four chains of equal length, so what they establish is *which probe* the container passed on — the final permitted one — and not how long the chain took. That distinction matters later, and `design.md` — Context carries it. `seed-the-reference-step-set` then added a fifth process to the start chain (`commerce_ops.seed_playbook`, the only line it changed in the `Dockerfile`), and that was enough to miss it. Runs `32982970163`, `33004377012` and `33006961404` are all declared unhealthy at 26.5s with the identical message:

```
dependency failed to start: container commerce-ops-app-1 is unhealthy
```

The five-second start period is the fault. It was sized for a container that migrated and served; `deploy-pipeline` has since required that same container to migrate, seed the roster, prepare the playbook step set and report on handler registration — all to completion, all before the server starts — and never revisited the window the probe allows for it. Each step `deploy-pipeline` adds to the chain moves the container closer to being reported dead for the time it spends doing what that spec requires of it, and nothing in the pipeline notices until a deploy goes red.

This is worth fixing beyond the immediate red: a deploy that fails for a reason unrelated to the deployment teaches everyone to disbelieve the signal, which is the one thing a deploy gate cannot afford.

## What Changes

- Widen the image's `HEALTHCHECK` start period from `5s` to `60s`, so the probe tolerates a start chain that takes as long as `deploy-pipeline` requires it to take. The interval, timeout and retry count are unchanged — the steady-state liveness signal after startup stays exactly as it is.
- Record in `deploy-pipeline` that the container's health probe SHALL allow the start chain that same spec mandates to run to completion before reporting the container unhealthy, so the window is a stated obligation with a reason attached rather than a literal nobody owns. The window is sized against the start-to-healthy interval the deploy reports on every run, so a future step added to the chain has a measured figure to check against rather than a derivation nobody can evaluate.
- Preserve, explicitly, what the start period must not cost: a container whose chain genuinely fails still never becomes healthy and still fails the deploy. The start period delays that verdict; it does not remove it. The probe's interval and retry count are fixed by the same requirement, so start-up tolerance cannot later be taken out of the steady-state liveness signal.
- State what the window does cost, rather than claiming it is free: a restarted container is a starting container, so it receives the window again.

No application code changes. No change to `docker-compose.yml`, to `deploy.yml`, or to what the start chain does.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deploy-pipeline`: adds a requirement that the container's health probe accommodate the start chain the spec already mandates, and restates — as a scenario on the new requirement — that a genuinely failing start is still caught and still fails the deploy.

## Impact

- `Dockerfile` — the `HEALTHCHECK` instruction's `--start-period` value, and the comment above it, which currently explains the probe's command choice but says nothing about its timing.
- The deploy job's failure latency for a genuinely broken container grows from 26.5s to roughly 87s (60s start period, then the three 10s probes that follow it). This is a deliberate trade and is argued in `design.md`; a deploy that is failing is not a deploy anyone is waiting on to the second.
- Nothing else in the pipeline. The `Verify the public health endpoint` step already retries for 30s of its own and is untouched.

### Out of scope

**Why the chain is slow on the host.** It takes ~25s there against **1.8s** locally on a real database (`alembic upgrade head` 0.59s, `preflight` 0.11s, `seed_admin` 0.31s, `seed_playbook` 0.50s inserting all 352 rows, `check_step_handlers` 0.31s). That is a real question and not this change's; it is what made the budget tight enough for one added process to break it, so it is recorded in `docs/deferred-work.md` rather than left to be rediscovered the next time a step joins the chain.

**Making the seeding step conditional or moving it out of the chain.** Considered and measured, not assumed: the seeder's no-op path costs 0.48s against 0.50s for the full insert, an empty-table gate would save ~0.2s locally, and it would permanently prevent a reference document that gains a row from ever delivering it — the capability `seed-the-reference-step-set` was deliberately designed for one day before this. It would also leave the deploy back at 26.50s against a ~25s budget. `design.md` — "Do not fold in the seeding question" records the reasoning. Taking one-time data work out of the start chain entirely is a defensible change; it is a different one, and it contradicts a requirement currently in force.

**`seed_playbook` and `check_step_handlers` emit no `INFO` records.** Both run as `python -m`, so their module logger is `__main__`, which inherits root's `WARNING` instead of `commerce_ops`'s `INFO` — verified directly. Their `ERROR` records still surface, so a failing step still names itself, but a successful run says nothing at all: the 352-row seeding reached production silently. A genuine defect, found while measuring for this change, and left to its own change rather than folded in. Recorded in `docs/deferred-work.md`.
