## Why

Nothing in this repository is deployable yet: `pyproject.toml` has zero runtime dependencies, there is no application code, and no CI/CD pipeline exists. Before any real domain logic is built, we want one thin, low-risk vertical slice — a FastAPI liveness endpoint — proven all the way through: committed, tested in CI, built into an image, delivered to the shared production host, and verifiably reachable over HTTPS. Standing this up now surfaces every seam in the pipeline (packaging, CI gates, the deploy credential, Traefik routing, post-deploy verification) while the cost of getting one of them wrong is negligible, rather than discovering a broken seam under a real feature later.

## What Changes

- Add FastAPI (and an ASGI server) as this project's first runtime dependencies, and scaffold a minimal application package with a single `GET /health` route returning a liveness status. No database dependency — this endpoint does not touch Postgres.
- Add a `Dockerfile` packaging the application.
- Add a `docker-compose.yml` for this application, joining the shared `platform_edge` Docker network (external, provided by the `/infrastructure` repo's platform stack) and carrying Traefik labels that route a to-be-supplied domain/subdomain to this service over HTTPS.
- Add a GitHub Actions workflow, the first CI/CD in this repository:
  - On every pull request: `ruff check`, `ruff format --check`, `mypy`, and the existing `tests/unit` + `tests/agents` pytest tiers (mirroring the local pre-commit gate).
  - On merge to `main`: build the Docker image and push it to GHCR (tagged with the commit SHA), then join the private Tailscale tailnet and deliver the deploy in one SSH connection: tar `docker-compose.yml` together with a freshly rendered, uncommitted file naming that SHA, and pipe the archive over stdin to this application's forced-command deploy key.
  - After deploy, the workflow curls the public health URL and fails the run if it does not return a successful liveness response — the concrete "everything actually works" check this change exists to establish.

**Depends on a companion change in the sibling `/infrastructure` repository** (a separate git root, out of scope for edits here): it must provision a forced-command SSH key for this application on the existing `deploy` account (bound to `/usr/local/bin/deploy-receive commerce-ops`), the `deploy-receive`/`app-deploy` scripts, an `/opt/commerce-ops` directory, and host-level GHCR pull authentication. Until that lands, this pipeline's deploy step has nothing on the host to connect to, or nothing it could successfully pull even if it did.

## Capabilities

### New Capabilities
- `health-check`: the `GET /health` endpoint's contract — what it checks, what it returns, and that it has no external dependency (no Postgres check).
- `deploy-pipeline`: the CI/CD behavior — what gates a merge, what triggers a build/push/deploy, how the deploy is delivered to the host, and how success is verified.

### Modified Capabilities
None — no existing specs exist yet in this repository to modify.

## Impact

- `pyproject.toml`: adds FastAPI + ASGI server as runtime dependencies (currently empty).
- New application source layout (the first product code committed to this repo).
- New `Dockerfile`, `docker-compose.yml`.
- New `.github/workflows/` (none exists today).
- New GitHub Actions secrets required in this repository: the commerce-ops deploy SSH private key (whose corresponding public key is forced-command-restricted on the host to `deploy-receive commerce-ops`), Tailscale OAuth client ID/secret, and the deploy host's tailnet address. GHCR push uses the workflow's built-in `GITHUB_TOKEN`; GHCR pull on the host side is the companion change's responsibility (see below), not a secret held here.
- Domain/DNS for the Traefik routing rule is not yet decided (tracked as an open item in design.md) — this blocks the deploy step actually resolving over HTTPS, but not the rest of this proposal.
- Blocked on the companion `/infrastructure` change described above for the deploy step to have a live target.
