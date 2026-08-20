## 1. Application scaffold

- [x] 1.1 Add FastAPI and an ASGI server (e.g. uvicorn) as runtime dependencies in `pyproject.toml`.
- [x] 1.2 Create the application package at `src/commerce_ops/` (the FastAPI app instance in `src/commerce_ops/main.py`) and a `GET /health` route returning a `200` JSON response, with no dependency on Postgres or any other external service. This endpoint is cross-cutting, not owned by any of the four domain modules (catalog, orders/inventory, support, analytics) — it lives at this top level, not nested under one of them.
- [x] 1.3 Add a unit test under `tests/unit/` asserting `GET /health` returns `200` and the expected body, run with no database configured — asserting the "no external dependency" requirement, not just the happy path.

## 2. Packaging

- [x] 2.1 Add a `Dockerfile` that installs dependencies via `uv`, runs the ASGI server, and declares a `HEALTHCHECK` hitting `GET /health` — gives `docker compose up -d --wait` something real to wait on, rather than just "process started." (Triggered on the host by `deploy-receive` invoking `app-deploy`, which runs `docker compose up -d --wait` — see design.md's Migration Plan.)
- [x] 2.2 Add `docker-compose.yml` for this application: joins the external `platform_edge` network, carries Traefik labels routing `GET /health` (and the app generally) to the domain from design.md's open question, once supplied. The `image:` field SHALL reference a `${IMAGE_TAG}` variable (Compose's built-in `.env`-file substitution), not a hardcoded or `latest` tag — see task 5.2.

## 3. CI: pull request validation

- [x] 3.1 Add `.github/workflows/ci.yml` (or similar) running `ruff check`, `ruff format --check`, `mypy`, and the `tests/unit` + `tests/agents` pytest tiers on every pull request.
- [ ] 3.2 Confirm this check is configured as a required branch-protection status check on `main`. **BLOCKED**: attempted via `gh api`, blocked by the auto-mode safety classifier on mutating GitHub branch-protection settings. Needs either a manual step in repo settings, or a Bash permission rule allowing this call so it can be retried.

## 4. CI: build and publish

- [x] 4.1 On merge to `main`, add a job (with `permissions: packages: write`) that builds the Docker image and pushes it to GHCR tagged with the commit SHA, using the workflow's built-in `GITHUB_TOKEN`.

## 5. CI: deploy

- [x] 5.1 Confirm the companion `/infrastructure` change has landed: the `deploy` account's `authorized_keys` accepts this application's key bound to `command="/usr/local/bin/deploy-receive commerce-ops"`, `/opt/commerce-ops` exists on the host, and the host is authenticated to GHCR (root's Docker credential store has a pull-capable `ghcr.io` entry) so `docker compose pull` can succeed against this application's private image. **CONFIRMED**: `/infrastructure`'s `add-per-app-deploy-keys` change archived 2026-08-20, all 22 tasks complete — task 2.1/2.2 provisioned a `commerce-ops` entry in `deploy_apps` (keypair generated, public half on the host), 1.6/2.3/3.3 configured and verified GHCR pull auth, 5.1 ran the playbook against real `prod`. Could not independently SSH-verify `/opt/commerce-ops` from here (no host access from this session) — relying on the archived change's own verified task record.
- [x] 5.2 Render a `.env` file (not committed — generated fresh each run) containing `IMAGE_TAG=<triggering commit SHA>`, for `docker-compose.yml`'s `${IMAGE_TAG}` reference (task 2.2) to resolve against on the host.
- [x] 5.3 Add the deploy job: join the Tailscale tailnet, then in one step, `tar -czf - docker-compose.yml .env | ssh -i <key> deploy@<host>` — a single SSH connection piping both files to this application's forced-command deploy key, which triggers `deploy-receive commerce-ops` on the host. Do not `scp` and separately trigger the deploy; the forced-command key only ever honors one command per connection.
- [x] 5.4 Add the `concurrency` group so overlapping deploys queue rather than race.
- [x] 5.5 Add the required GitHub Actions secrets to the commerce-ops repository: the deploy SSH private key, the Tailscale OAuth client ID/secret, and the deploy host's tailnet address. **CONFIRMED**: all four already exist (`COMMERCE_OPS_DEPLOY_SSH_KEY`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, `DEPLOY_HOST`), scoped to a `production` GitHub Environment rather than the repository directly. That Environment carries no protection rules (verified via the API), so referencing it from the deploy job (`environment: production`, added to `.github/workflows/deploy.yml`) does not introduce the manual-approval gate design.md's "Deploy gate" decision explicitly rejected — it's declared solely to reach these Environment-scoped secrets.

## 6. CI: post-deploy verification

- [x] 6.1 Add a step after the deploy trigger that requests the public `GET /health` URL (domain from task 7.1, once supplied) with retries, and fails the workflow run if it does not receive a successful response.

## 7. Domain

- [x] 7.1 Fill in the domain/subdomain for this application (design.md's open question) in both the Traefik label (task 2.2) and the health-check URL (task 6.1).

## 8. Verification

- [x] 8.1 Run `uv run pytest`, `ruff check`, `ruff format --check`, and `mypy` locally; confirm all pass.
- [ ] 8.2 Merge to `main` and confirm the workflow run reports success, including the post-deploy health check.
- [ ] 8.3 Manually request the public health URL from outside the pipeline and confirm it returns a successful response.
