## Why

**A production container cannot start without reaching PyPI**, and what it reaches for is test tooling it never runs.

`Dockerfile:11` builds the environment correctly — `uv sync --frozen --no-dev`. But every `uv run` at runtime re-syncs the environment before running anything, and uv's default includes the dev dependency group. So the runtime undoes the build's `--no-dev` on first use, downloading `pytest`, `mypy`, `ruff`, `grimp` and `virtualenv` into a running production container.

Verified directly:

```
$ docker run --rm --network none <image> sh -c 'uv run python -c "print(1)"'
  ├─▶ client error (Connect)
  ├─▶ dns error
  ╰─▶ failed to lookup address information: Try again
  help: `pluggy` (v1.6.0) was included because `commerce-ops:dev` (v0.1.0)
        depends on `pytest` (v9.1.1) which depends on `pluggy`
```

With `UV_NO_SYNC=1` the same image starts offline and imports the application, including the worker.

This is an availability property, not a tidiness one. The deploy already survives a GHCR outage — the image is pulled once and cached. It does not survive a PyPI outage, a yanked transitive dev dependency, or a host whose egress is restricted, because every container start re-resolves and re-downloads a dependency set that has nothing to do with serving.

It is also slow. The observed worker start spent one to two minutes downloading dev packages before its first log line — delaying scheduled work, though not threatening a health gate, since `worker` disables its healthcheck and `--wait` treats it as ready once running. The timing pressure falls on `app`, whose chain begins `uv run python -m commerce_ops.preflight` inside a healthcheck configured `--interval=10s --start-period=5s --retries=3`, and it is `app`'s health that `docker compose up -d --wait` blocks the deploy on.

## What Changes

- **`UV_NO_SYNC=1` is set in the image**, so no `uv run` anywhere re-syncs at runtime — covering the `CMD` chain, the `HEALTHCHECK`, `docker-compose.yml`'s `worker` command, and any manual `docker compose exec … uv run …` an operator types. A single environment variable rather than a flag on each call site, so the next `uv run` added somewhere cannot silently reintroduce the fault.
- **The `HEALTHCHECK` stops going through `uv run` entirely**, calling the image's own interpreter instead. It runs every 10 seconds for the life of every `app` container — `worker` disables it, having no HTTP to probe — and process-launching uv to answer "is HTTP up" buys nothing once syncing is off.
- **The build job proves it before deploying.** After the merge-to-`main` job builds the image and before the deploy step runs, it starts a container from that image with no network and fails the deploy if that does not work. Without this the property holds only until someone changes the `Dockerfile`, a base image, or `uv` — and the whole point of the change is that nothing was watching.
- **`deploy-pipeline` gains a requirement** that a container starts from what its image already contains, with no access to a package index, and that the pipeline verifies this before deploying. Nothing states this today, which is why nothing caught it.

## Capabilities

### Modified Capabilities

- `deploy-pipeline`: gains one requirement — a container starts using only what its image contains, and reaches no package index at runtime. The existing requirements are untouched; this states a property the pipeline was assumed to have and did not.

## Impact

- **Modified**: `Dockerfile` — one `ENV` line, the `HEALTHCHECK` command, and two explanatory comments (tasks 1.1 and 2.3). `.github/workflows/deploy.yml` — one step in the build job, running the built image with no network before the deploy job takes it.
- **New**: a small unit test module guarding the `Dockerfile`'s two text-level properties, beside `tests/unit/test_compose_worker_service.py`.
- **Not modified**: `docker-compose.yml`. Its `worker` and `app` commands keep using `uv run`, which is now inert with respect to syncing. Changing them is a separate concern and would duplicate the guarantee in a second place.
- **Not modified**: `pyproject.toml`, `uv.lock`, or the dev dependency group. Dev tooling stays exactly as it is for local work and CI; this change only stops the *runtime* installing it.
- **Deploy**: the first deploy after this lands is the one that proves it — containers start from the image alone. Rollback is reverting the commit; the previous behaviour returns with it, including its dependency on PyPI.
- **Interacts with `replace-cron-with-job-runner`**, just deployed: that change added a second container from the same image, doubling the number of starts that reach for PyPI, and its worker has no healthcheck to notice a slow one. The fault predates it, but that change is what made it visible.
