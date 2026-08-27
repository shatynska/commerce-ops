## Context

See `proposal.md` — Why for the motivation and the evidence. What matters for the approach is the shape of the machinery, and specifically which parts of it this repository can reach.

The host runs a fixed deploy mechanism: `app-deploy` executes `docker compose pull && up -d --wait`. That script lives in the `/infrastructure` repository, not this one, and `deploy.yml` triggers it through a forced-command key that honours exactly one invocation — this repository cannot pass it a flag, cannot change its timeout, and cannot make it stop treating an unhealthy container as a failed deploy. Nor should it want to: `--wait` is the mechanism that makes a genuinely broken deploy fail, and `deploy-pipeline`'s *A startup-critical fault leaves the deploy failed* depends on it.

So the container's own declared health probe is the only lever in reach, which is convenient, because it is also the correct one. The probe is what is mis-sized.

Docker's health monitor works this way: during the start period a failing probe leaves the container `starting` and does not increment the consecutive-failure count; a *succeeding* probe marks the container healthy immediately, start period or not. So a longer start period costs a healthy container nothing — it does not delay the transition, it only widens the tolerance for not having made it yet. These semantics have been Docker's since `--start-period` was introduced in 17.05, which the host cannot plausibly predate; the approach assumes nothing newer.

Two measurements bound the decision. On the deploy host, `Started` → `Healthy` was **26.50s** on each of the last four successful deploys (`32943840745`, `32949905323`, `32956273524`, `32958746253`), and the three failures were declared unhealthy at the same 26.5s. Locally, against a real Postgres, the whole chain runs in **1.8s** — `alembic upgrade head` 0.59s, `preflight` 0.11s, `seed_admin` 0.31s, `seed_playbook` 0.50s while inserting all 352 rows, `check_step_handlers` 0.31s. The chain is not slow; the host is, by a factor of roughly fourteen.

One qualification on "the probe's cadence", which matters in two places below. Docker 25.0 added `--start-interval` and gave it a default of 5s, applied inside the start period whether or not the flag is declared. So on an engine at 25.0 or later the startup cadence is 5s and the over-statement bound is 5s; before it, both are `--interval`, i.e. 10s. This repository does not establish the host's engine version. The rule the delta states is safe either way — a margin of two 10s intervals over-provisions when the real bound is 5s — but the *predicted* first reading differs, which the Migration Plan now says outright.

Read those host figures carefully, because the change turns on what they do and do not say. `Started` → `Healthy` is not the chain's duration: it is the moment of the first *successful probe*, so it snaps up to the probe's cadence. Four readings of exactly 26.50s are the signature of a tick, not of four chains of identical length — what they establish is that the chain finished somewhere in the interval before that probe. On the three failing runs the same figure is only a lower bound: the chain took longer than 26.5s by an unknown margin. **The chain's duration on the host, with `seed_playbook` in it, has never been measured and is not measured by this change.**

That is survivable because start-to-healthy is the right quantity to size the window against anyway — it is what has to fit inside the window, it errs upward, and the deploy reports it on every single run. It is not survivable as an input to a "twice the chain's duration" rule, which is why the delta states the floor against the measured interval instead. See Decisions — "60 seconds".

## Goals / Non-Goals

**Goals:**

- A deploy of a working container is reported successful.
- The window is expressed as an obligation with a reason attached, so the next step added to the chain has something to be checked against instead of a literal to silently outgrow.
- The steady-state liveness signal is untouched.

**Non-Goals:**

- Making the start chain faster, or explaining why the host is fourteen times slower than a laptop. Recorded in `docs/deferred-work.md`; see `proposal.md` — Out of scope.
- Changing what the start chain does, or the order it does it in. `deploy-pipeline`'s *Application Migrates the Database Before Serving Traffic* settles that, and this change deliberately does not reopen it.
- Any change to `app-deploy`, `docker-compose.yml`, or `deploy.yml`.

## Decisions

### Widen the start period rather than the retry count or the interval

`--retries` and `--interval` govern the steady-state liveness signal — how long a container that has *stopped* answering is allowed to keep receiving traffic. Buying start-up tolerance from either of them makes a container that dies in production take proportionally longer to be noticed, which is paying for a startup problem with a runtime one. `--start-period` is the parameter that exists for exactly this, and it expires.

Rejected: `--retries=9`. It reaches the same tolerance at start and triples the time a dead container is left in the load balancer, permanently and in every state.

One limit on that argument, which an earlier draft of this document got wrong and which the delta's *A restarted container is granted the window again* now states outright. Docker measures the start period from the container's `StartedAt` and resets health status to `starting` on every start, so a **restarted** container is granted the window afresh. `docker-compose.yml` declares `restart: unless-stopped` for `app`, so this path is live in production: a container that becomes healthy, later crashes, and is restarted is reported `unhealthy` after about **87s** of each cycle — 60s of window, then the three 10s probes that follow it — where today the same container reaches that verdict in **26.5s**, measured, not derived: it is the figure the three failing runs were declared unhealthy at. So `--start-period` is not free of steady-state cost in the way "it expires" suggests; it is free of it only for a container that stays up. It remains much the better trade than `--retries=9`, which pays that cost in every state rather than only after a crash, but the distinction is real and is carried into Risks below.

### 60 seconds

The container reached healthy at 26.50s on the last four successful deploys. 60s clears that by more than 30 seconds — enough that the next step added to the chain, or a slow morning on a shared host, does not put the deploy back where it started, and not so much that a broken container's verdict is deferred unreasonably. (Stated as a clearance rather than a ratio deliberately; the next subsection is about why ratios are the wrong frame here.)

Rejected: 30s, as too close to the observed figure to be a margin at all — it is the current situation with one probe's more room, and the current situation is what this change exists to stop repeating. Rejected: 300s, which would leave a crash-looping container reported `starting` for five minutes and make a broken deploy genuinely tedious to diagnose.

Rejected too: raising the number blind. Without a measurement of the chain itself, 90s or 120s is exactly the same guess as 60s dressed up as caution, and the argument against 300s applies to them in proportion. The honest move is to size against the quantity that *is* measured on every run.

**Why the margin is additive and not a multiple.** An earlier draft of this document wrote the rule as "at least twice the observed interval", and that was wrong in a way worth recording, because it is an easy mistake to repeat. The observed interval is already inflated: it snaps up to the next probe tick, so it over-states the chain by up to one full interval. Doubling it counts that inflation twice. Concretely — the 26.50s readings come from the **four**-process chain; the five-process chain has no successful observation at all, and its three failures place it above 26.5s, so the first reading after this change is most likely the next tick at ~36.5s. A doubling rule would then demand ≥73s, and the 60s this change ships would violate the requirement it introduces, on its very first deploy. That is the same "a literal silently outgrew its justification" failure this change exists to end, restaged one iteration later.

A multiple has a second defect: it tightens as the host slows, including when the slowing is an artefact of the probe cadence rather than of the chain. An additive margin does not.

So the spec states the floor as "exceeds the largest start-to-healthy interval from the three most recent successful deploys by at least two probe intervals, and never less than 60 seconds".

Two intervals is derived, not picked, and the derivation is worth writing out because an earlier draft of this paragraph got its extremes backwards. Let `C` be the chain's true duration, `I` the startup probe interval, and `R` the reported interval. Because `R` is the first *successful* probe, `R ∈ [C, C+I)`. With a margin `M`, the window `W = R + M` clears the chain by `W − C = (R − C) + M ∈ [M, M+I)`. So the *guaranteed* clearance is `M` exactly — and it is guaranteed at the extreme where the observation over-states **least** (`R = C`), not most. A one-interval margin therefore guarantees only one interval of clearance, all of which is consumed by absorbing the measurement; it leaves nothing for the chain to grow into, and a chain that gains one step would breach immediately. Two intervals buys one for the measurement and one for growth, where a single added process is precisely what moved the reading by a tick and produced this change.

At the expected ~36.5s reading the rule requires ≥56.5s, which 60s satisfies; against the historical 26.5s readings it requires ≥46.5s, also satisfied; if the host slows to a ~46.5s reading it requires ≥66.5s, and the window must grow. Naming three deploys rather than "the observed interval" closes the other gap in the earlier draft — an unqualified "observed" lets a future change satisfy the rule by choosing a favourable run.

The alternative — stating 60s as a bare absolute — was rejected because it concedes the goal: a literal with no derivation is exactly what the chain silently outgrew this time. The rule above keeps the derivation while being satisfiable by the value actually shipped.

### Do not fold in the seeding question

The obvious cheaper-looking fix is to stop running `seed_playbook` on every start — gate it on an empty table, or take it out of the chain. Measured, it does not pay: the seeder's no-op path costs **0.48s** locally against **0.50s** for the full 352-row insert, because the cost is process start, imports and loading the rows, not the writing. An empty-table gate would still start a process and query the table, saving perhaps 0.2s locally.

It also costs something real. `seed-the-reference-step-set` widened the rule from the whole table to each row precisely "so a reference document that gains a row can still deliver it"; an empty-table gate takes that back permanently, since the table is never empty again. And it would not fix this: removing the step returns the deploy to 26.50s against a ~25s budget — green, with the same zero margin that produced this failure.

Taking one-time data work out of the container start chain altogether is a legitimate design position, but it is a different change with a different spec impact, and *Application Migrates the Database Before Serving Traffic* currently mandates the opposite.

### Leave `--start-interval` unset

`--start-interval` probes more frequently while starting, and would shave a few seconds off a successful deploy — and would shorten the restart-path window noted above. It is declined because it requires Docker 25.0 or newer, where the start-period semantics this design rests on require only 17.05 (Context). This repository does not establish the host's version, and an unrecognised flag in a `HEALTHCHECK` is a build-time failure rather than a graceful degradation, so the two are not equivalent bets: one assumes a floor the host is certain to clear, the other assumes a ceiling it may not. The gain is a handful of seconds on a path that already works.

Consequence, stated as the opportunity cost it is rather than a regression: a container is reported healthy at the first probe tick after it is ready, so up to 10s of the deploy is spent waiting for a probe that a start-interval would have delivered within a second. That is true today and stays true after this change — declining `--start-interval` forgoes an improvement, it does not make anything slower than it currently is.

### Guard the value with a text-level test, and say what it does not prove

`tests/unit/test_dockerfile_runtime_sync.py` already reads the `Dockerfile` as text and is explicit in its own docstring that such a test establishes only that a line is present. The new guard follows it exactly, including that honesty: no pytest tier here has a built image, so no test in this repository can observe a container becoming healthy. The scenario about a slow chain still deploying is verified by the deploy itself, and `test-manifest.md` will record it as such rather than claiming a unit test covers it.

Rejected: an integration test that builds the image and starts a container. The integration tier runs at `pre-push` against Postgres, has no built image, and adding a Docker build to it would make every push pay for it.

## Risks / Trade-offs

- **A genuinely broken container now takes ~87s to fail the deploy instead of 26.5s** (60s of window, then the three 10s probes that follow it) → Accepted deliberately. Nobody watches a failing deploy to the second, and the failure is no less certain — only later. The *A start that never completes still fails the deploy* scenario exists to keep this explicit, so a future reader does not mistake the wider window for a weakened gate.
- **A crash-looping container in production takes ~87s per cycle to be reported `unhealthy`, where today it takes 26.5s** → Accepted, and stated in the delta rather than hidden, because `restart: unless-stopped` makes it a live path. Nothing in this deployment routes or alerts on container health today — Traefik routes on the container being up, and `report-overdue-scheduled-runs` watches from outside — so the cost is to a person reading `docker compose ps`, not to traffic. That claim is worth re-checking if anything ever does alert on health. It is the strongest argument for `--start-interval`, and the reason that decision is recorded as declined-for-now rather than rejected.
- **A container that hangs mid-chain reads as `starting` for ~87s**, which looks like "still working" to someone watching `docker compose ps` → Only partly mitigated, and the two halves must not be run together. A step that *fails* names itself, which `deploy-pipeline` already requires and which the next bullet confirms still works, since `ERROR` records survive. A step that *hangs* emits nothing at all — and for `seed_playbook` and `check_step_handlers` the logs are silent even on success, so a hang in either is invisible in both the health status and the logs, and is diagnosable only by `docker exec` against the running container. Accepted, and named here rather than papered over; the logging defect that makes it worse is recorded by task 3.2 and belongs to its own change.
- **60s is sized against start-to-healthy, not against the chain, and the chain has never been measured on the host** → Mitigated by the direction of the error: start-to-healthy over-states the chain, so sizing against it is conservative, and it is reported by every deploy so the rule stays checkable. Not eliminated: nothing in this change bounds the chain from above, so if it exceeds 60s on the host the deploy stays red with the identical message. The local figures put that well outside the expected range, and task 4.4 is where the first real reading is taken.
- **The margin is derived from the probe cadence, which this change also fixes at 10s** → If a future change alters the interval, "two probe intervals" moves with it, which is the intended behaviour but is not obvious from the number alone. The delta states the margin in intervals rather than seconds for exactly that reason.
- **`app-deploy`'s wait timeout is unknown to this repository, and this change roughly triples the time to a verdict** (26.5s → ~87s) → Context notes the script has a timeout this repository cannot change; it does not establish its value, and `/infrastructure` was not consulted for this change. If it sits between the two figures, a genuinely broken container fails the deploy by wait-timeout rather than by `container ... is unhealthy`. The gate still fails closed either way, so nothing is weakened — but the message `proposal.md` — Why teaches a reader to recognise would not be the one they see, which is worth knowing before someone diagnoses the next red deploy against the wrong string.
- **The two steps most worth reading during a slow start are silent** → `seed_playbook` and `check_step_handlers` are run as `python -m`, so their module logger is `__main__` rather than `commerce_ops.*`; `configure_logging` sets root to `WARNING`, so every `INFO` record from them is dropped. Verified: `__main__` resolves to an effective level of 30 and `isEnabledFor(INFO)` is `False`, and both processes emit nothing on a successful run. Their `ERROR` records still appear, so the "a failing step names itself" mitigation above holds; what is lost is the successful narration. This is a pre-existing defect, not one this change introduces, and it is not folded in — see `proposal.md` — Out of scope.

## Migration Plan

No migration. The value takes effect on the next image build, which is the merge that carries it; no host state, no data, and nothing else in the pipeline depends on the old value.

Rollback is reverting the commit. Doing so returns the deploy to failing on every merge, so the meaningful rollback is not this change but the chain it accommodates.

Verification is the deploy that carries this change: it is the first one expected to pass since `32958746253`, and the `Started` → `Healthy` figure in its log is the measurement. Two readings matter — that the deploy passes at all, and that the figure stays at or below 40s, since the delta requires the window to exceed it by two probe intervals and the window is 60s.

The expected figure depends on the host's engine, which this repository does not establish. On an engine before Docker 25.0 the startup cadence is `--interval`, so expect ~36.5s: the tick after the 26.5s the four-process chain passed on. On 25.0 or later the default 5s start-interval applies inside the window even though the flag is not declared, so expect something nearer ~30s. Either satisfies the rule; the point of naming both is that a reading of ~30s is a correct result on a modern engine, not an anomaly to investigate.

That reading necessarily happens *after* the merge, and the archive commit precedes the merge, so it cannot be a checkbox ticked while this change is open. It lands in `docs/deferred-work.md` alongside the host-slowness entry task 3.1 creates — that file exists precisely so a fact recorded only in a change's artifacts is not lost when they move to `archive/`. If the figure exceeds 40s, the entry is what turns the next window change from a rediscovery into a follow-up.
