## Context

See proposal.md — Why. Facts that shape the approach:

- **The image already builds the right environment.** `Dockerfile:11` runs `uv sync --frozen --no-dev`, producing `/app/.venv` with runtime dependencies only. Nothing about the build needs changing; the fault is entirely in what happens afterwards.
- **`uv run` syncs before running, and its default group set includes `dev`.** That is documented uv behaviour, not a misconfiguration — `uv run` is designed to keep an environment current, which is right for a developer and wrong for a container built from a lock.
- **There are four call sites, and they are not all in this repository's control at once**: the `Dockerfile`'s `CMD` chain (three `uv run` calls), the `Dockerfile`'s `HEALTHCHECK`, `docker-compose.yml`'s `worker` command, and whatever an operator types into `docker compose exec`. The last one has no fixed text to edit.
- **The healthcheck is on the deploy's critical path.** `deploy-receive` runs `docker compose pull && up -d --wait`, which blocks on health. A healthcheck that cannot execute fails the deploy rather than degrading quietly.
- **`uv` itself remains in the image.** It is the base image (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), so removing uv from the runtime is not on the table and is not the goal.

## Goals / Non-Goals

**Goals:**

- A container start that touches no package index, provably, under a test that removes the network rather than trusting configuration.
- One place where that is enforced, rather than one per call site.
- No change to how anyone develops, tests, or locks dependencies.

**Non-Goals:**

- **Removing `uv` from the runtime.** It is the base image and it is a reasonable launcher once it stops syncing.
- **Shrinking the image.** The dev group is not installed at build time already, so there is nothing to remove; this change stops it being *added* at runtime. Any further size work is separate.
- **Changing `docker-compose.yml`.** Its commands use `uv run`, which becomes inert here. Editing them too would state the same guarantee in a second place, where it could later disagree with the first.
- **Auditing other images.** Only this application's image is in scope.

## Decisions

### Set `UV_NO_SYNC=1` in the image, not flags at each call site

`ENV UV_NO_SYNC=1` in the `Dockerfile` applies to every process in every container from that image: the `CMD` chain, the `HEALTHCHECK`, the compose `command:` override, and an operator's `docker compose exec … uv run …`.

That last one is the deciding argument. During the `replace-cron-with-job-runner` verification, the documented way to trigger a job by hand was `docker compose exec worker uv run python -m procrastinate … defer`. That command re-synced too. No amount of editing this repository's files would have covered it, because the text is typed by a person at the time. An environment variable in the image covers it without anyone having to know.

Instruction order does not matter for that: image environment is image configuration, so a `HEALTHCHECK` reads it whether it is declared above or below. Verified directly against a probe image whose `ENV` follows its `HEALTHCHECK` — the probe read the variable and the container reported healthy. What *does* constrain placement is the build: the `ENV` belongs after the build-time `uv sync`, so that a variable meant for the runtime cannot alter how the image is built.

**Alternative considered — `--no-sync --no-dev --frozen` on each `uv run`.** Equivalent for the three calls that live in files, useless for the fourth, and it establishes a convention that every future `uv run` must remember three flags. The failure mode of forgetting is silent: the container still starts, just slower and with a network dependency nobody notices until the index is down.

**Alternative considered — replace `uv run` with `/app/.venv/bin/python` everywhere.** Removes uv from the runtime path entirely and is the most direct expression of "use what the image contains". Rejected as the general answer for the same reason: it cannot reach the operator's typed command, and it hard-codes the venv path into four places where uv already knows it. It *is* adopted for the healthcheck specifically — see below, where the reasoning inverts.

**Also considered — `UV_FROZEN=1` alongside.** It prevents `uv.lock` being updated at runtime. Not adopted, because the state it guards is unreachable here: rewriting the lock requires `pyproject.toml` and `uv.lock` to disagree, and both are copied into an image whose build ran `uv sync --frozen` against them. A second variable guarding a state the build makes impossible invites the belief that both are load-bearing.

An earlier draft argued instead that "the offline test demonstrates uv performs no resolution". That claimed more than the evidence: the test demonstrates no *index contact*, and a lock already consistent with `pyproject.toml` can be validated without querying any index. The decision survives on the argument above, which does not depend on an inference the test cannot support.

### The healthcheck calls the interpreter directly

The `HEALTHCHECK` becomes `/app/.venv/bin/python -c …` rather than `uv run python -c …`.

Here the argument that rejected the direct-path approach above does not apply: the healthcheck is a fixed string in the `Dockerfile`, never typed by an operator, so there is no coverage gap to worry about. What it has instead is frequency — every 10 seconds, for the entire life of every `app` container, in perpetuity. (`worker` overrides it to `disable: true`, having no HTTP surface, so this is an `app`-only cost and an `app`-only risk.) Launching uv to discover a venv it will not modify is pure overhead on the one command that runs more often than any other in the deployment.

It also takes uv out of the liveness signal. A healthcheck should fail when the application is unhealthy and at no other time; each additional layer between the probe and the HTTP request is another way for it to report the wrong thing.

**The path is fixed by the build**, not guessed: `uv sync` creates `/app/.venv` under the `WORKDIR`, and the deployed container's own tracebacks name `/app/.venv/lib/python3.12/site-packages/…`. The implementation asserts it rather than assuming it, because a wrong path here makes every container permanently unhealthy and hangs `up -d --wait` on the next deploy.

### The offline check runs in the build job, not only by hand

An earlier draft of this design claimed the offline test as the standing guard against a future `uv` changing what `UV_NO_SYNC` covers, while the task list provided it only as a one-time manual command. That was incoherent, and in a way worth naming: it reproduced, one level up, the exact gap the proposal identifies as the root cause — a property everyone believed held, with nothing repeatable asserting it.

So the check lives in the merge-to-`main` build job, immediately after the image is built and before the deploy job takes it. The image already exists at that point, so the step costs seconds, and a regression fails the deploy rather than reaching the host. It also lands in `deploy-pipeline`, which is the capability the requirement was added to.

**Alternative considered — the integration test tier.** Matches this project's own tiering and runs at `pre-push`. Rejected on cost: every push would build a Docker image, and the tier's existing cost is already a local Postgres. The check needs a *built image*, which is a thing the pipeline has and a developer's push does not.

**Alternative considered — leave it manual and say so.** Honest and cheap, and it would have been acceptable if the design stopped claiming a standing guard. Rejected because the requirement is about a property that decays silently: nothing about a container that has started tells you whether it phoned an index to get there.

**One scenario is deliberately left as a one-time check, and it is worth saying which and why.** "Starting a container installs nothing" compares the package set before and after a real start, and the second capture requires a container whose `CMD` chain has completed `preflight && alembic upgrade head` — which means a reachable Postgres. Putting that in the build job would mean standing a database service up there purely to observe a package list, where the offline check needs nothing but the image. So it stays a local check (task 4.4), and the standing guard covers the case that motivated the change — a start that reaches an index — while the cache-served variant is verified once, at implementation. That is a real gap, recorded rather than papered over: a start-time install served entirely from the image's own uv cache would not be caught again after this change lands.

### Verification removes the network rather than reading the configuration

The acceptance check is `docker run --network none <image> …`, not an inspection of environment variables. A container that starts with no route to any index has demonstrated the requirement; a container whose `ENV` looks correct has demonstrated that someone wrote an `ENV` line.

This matters because the failure being fixed was invisible in exactly that way: the `Dockerfile` said `--no-dev` and everyone reading it, including the change that introduced the worker, believed the runtime honoured it.

**What the offline check substitutes, and why.** The requirement's scenario says a container "SHALL start and reach its normal working state" with no route to an index. The check asserts something narrower: that the application imports under `--network none`. The substitution is forced — `--network none` is stricter than the scenario's condition, severing Postgres along with the index, so the real `CMD` chain cannot complete its migration and could never pass. The import is the largest part of a start that is observable under those conditions, and it is where every dependency resolution would occur. The full start with the network present is covered separately by `up -d --wait` (task 4.6) and after deploy by task 6.3. Recorded so that a reader — or a test author working from the scenario text — does not go looking for coverage of "normal working state" and conclude it was forgotten.

## Risks / Trade-offs

- **A wrong interpreter path makes every `app` container permanently unhealthy** — and `worker`, which declares `depends_on: app: condition: service_healthy`, then never starts either, so an `app`-only probe fault stops all scheduled work too. Stated in full, because "hangs the deploy" understates it: `docker compose up -d --wait` has already recreated the container by the time health is evaluated, so the previous, working one is gone before the failure is known. → The riskiest line in the change, and the reason it is worth naming that this rewrite satisfies no requirement in the delta — `UV_NO_SYNC` alone does that. It is kept in this change rather than split out because its mitigation runs entirely before anything reaches the host: task 2.1 confirms the path inside the built image, 4.5 runs the probe by hand against a live container in both its healthy and unhealthy states, and 4.6 runs `up -d --wait` against the real compose file locally. Those three, not the reasoning, are what make bundling acceptable; without them this belongs in its own change.
- **`UV_NO_SYNC` masks a genuinely stale environment.** If someone edits `pyproject.toml` and the image is not rebuilt, the container silently runs the previously built environment instead of correcting itself. → Accepted, and arguably the point: an image should run what it was built with. The pipeline rebuilds on every merge to `main`, so a stale runtime environment implies a stale image, which is a deploy problem with its own signal.
- **A future `uv` could change what `UV_NO_SYNC` covers.** → The offline test is the guard: it asserts the property, not the mechanism, so a uv upgrade that reintroduced any network access at start fails it.
- **The dev group still installs during local development and CI**, where it should. → No trade-off, stated only because "stop installing dev dependencies" could be misread as a global change.

## Migration Plan

1. Set `ENV UV_NO_SYNC=1`, rewrite the `HEALTHCHECK` to call the venv's interpreter, and add the offline check to `deploy.yml`'s build job.
2. Build the image locally and verify it starts with `--network none`, that the package set is unchanged by a start, and that the healthcheck command succeeds against a running container **and fails against one that is not serving**. The riskiest line is tested here, before anything reaches the host — that is what makes bundling the healthcheck rewrite acceptable.
3. Merge. The build job builds the image, proves it starts offline, and only then does the deploy job take it; the host's `up -d --wait` is the first test on the *real host*, not the first test of the line.
4. After deploy, confirm `app` is healthy, `worker` is up, its first log line arrives in seconds rather than after a download, and the healthcheck is genuinely being evaluated rather than never running.
5. If step 4 fails, revert and redeploy rather than debugging on the host: `up -d --wait` has already replaced the working container by the time a health failure is known.

**Rollback.** Revert the commit and redeploy. The previous behaviour returns, including its dependency on a reachable package index. Nothing persists outside the image, so no data or schema step is involved.
