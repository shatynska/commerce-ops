## Context

commerce-ops has an established architecture (modular monolith, FastAPI, Postgres, LangGraph — see README's Architecture section) and code-quality tooling (ruff/mypy/pytest/pre-commit/gitlint), but zero runtime dependencies and no CI. The sibling `/infrastructure` repository already runs a production Hetzner host with a shared platform Compose stack (Traefik with ACME TLS, one shared Postgres instance) and a proven deploy pattern for that stack: GitHub Actions joins a private Tailscale tailnet, authenticates over SSH as a restricted `deploy` account, and triggers one fixed, argument-free wrapper script.

The cloud firewall on that host opens only 22 (SSH, restricted CIDR), 80, and 443 — no arbitrary application port is reachable, so this application must be routed through Traefik via Docker labels on the shared `platform_edge` network, the same way `platform/README.md` documents for any application joining the host.

This change's deploy step depends on host-side plumbing that does not exist yet: a forced-command SSH key for this application on the `deploy` account (bound to `/usr/local/bin/deploy-receive commerce-ops`), the `deploy-receive`/`app-deploy` scripts, an `/opt/commerce-ops` directory, and host-level GHCR pull authentication. That plumbing is provisioned by a companion change in `/infrastructure`'s own OpenSpec store (a separate git root, out of this change's edit scope) and is a hard prerequisite for the deploy step to have anywhere to connect, or anything it could successfully pull once connected.

## Goals / Non-Goals

**Goals:**
- Prove the full pipeline end-to-end — commit, CI gate, image build, delivery to the shared host, HTTPS routing, and automated post-deploy verification — using the smallest possible piece of application behavior.
- Reuse the shared platform stack (Traefik, tailnet-based deploy access) exactly as `/infrastructure` already establishes it, rather than introducing a second, parallel mechanism.

**Non-Goals:**
- No database. `/health` has no Postgres dependency; provisioning this application's own database inside the shared Postgres instance is explicitly deferred (it's marked as undefined follow-up work in `/infrastructure`'s own `platform/README.md` too).
- No Slack integration, no domain modules, no LangGraph agents. This change exists purely to prove the deploy path.
- No staging environment. Deploys go straight to the single `prod` host, matching `/infrastructure`'s current single-environment reality.

## Decisions

**Deploy credential: a forced-command SSH key on the shared `deploy` account, scoped to this application.** Rather than a dedicated Unix account per application, or a single key shared across every application, each application gets its own keypair added to `deploy`'s `authorized_keys` with a `command=` forced-command binding it to that application's name — the app name is fixed at the SSH layer, never supplied as CI input. This was chosen (see conversation leading to this proposal) specifically to avoid a shared secret whose leak from any one of several application repositories would compromise every application plus the shared platform stack, while still avoiding a full new Unix account/sudoers rule per application. It is provisioned in `/infrastructure`, not here.

**Deploy delivery: one SSH connection, content piped over stdin — not `scp` plus a separate trigger.** Caught on review: a forced command restricts a key's session to exactly one invocation, which makes a two-step "copy the file, then separately trigger the deploy" sequence impossible to express safely over a forced-command key — `scp` and the trigger would be two different commands sent over the same session, and the forced command can only ever honor one of them. Instead, the deploy job tars `docker-compose.yml` and the rendered `.env` and pipes that archive over stdin to a single `ssh` invocation; the host-side forced command (`/infrastructure`'s `deploy-receive`) extracts it and triggers the deploy within that same session. This repository's own deploy job never sends more than one command over the key at all.

**Reverse proxy: Traefik via Docker labels, no dedicated port.** The host's cloud firewall does not open any port besides 22/80/443, so this is the only viable routing path; it also means this application gets ACME-issued TLS for free, consistent with how `/infrastructure`'s `platform/README.md` expects every application on the host to be reached.

**Deploy gate: no manual approval, unlike `/infrastructure`'s `production` Environment gate on the platform stack.** The platform stack's gate protects shared state (the reverse proxy every application depends on, and the database every application's data lives in) — a bad platform deploy affects everything on the host. This application's deploy only affects its own container; a bad deploy here does not touch the platform stack or any other application. Merges to `main` deploy automatically once CI passes. Revisit if this application later becomes something a bad deploy of would have wider blast radius (e.g., once it starts writing to the shared Postgres instance).

**Image tagging: commit SHA, not just `latest`.** Tagging by SHA gives the deploy step (and any future rollback) a concrete, addressable artifact rather than relying on GHCR's mutable `latest` tag pointing at whatever was pushed most recently. The tag reaches the host via a freshly rendered, uncommitted `.env` file (`IMAGE_TAG=<commit SHA>`) delivered in the same tarred, stdin-piped payload as `docker-compose.yml` (see the Deploy delivery decision above), with `docker-compose.yml`'s `image:` field referencing `${IMAGE_TAG}` rather than a hardcoded value. Caught on review: the SHA tag alone doesn't help unless it's threaded all the way to the compose file the host actually runs; this is that mechanism.

**GHCR image pull authentication is the companion `/infrastructure` change's responsibility, not this one's.** Caught on a later review pass: getting the right tag to the host and the host being able to pull that (private-by-default) image are two different problems. This repository has no host-level credentials to manage; the fix (a shared, read-only GHCR pull token configured on the host) is host-side plumbing and lives in `add-per-app-deploy-keys` alongside the SSH keys and `/opt/commerce-ops` directory it already provisions — task 5.1 below now names it explicitly as part of what to confirm before proceeding.

**Health check verification lives in the workflow itself, not a separate scheduled job.** The whole point of this change is proving the pipeline works synchronously, at deploy time — a workflow run that reports green is the signal "this deploy is live and healthy." Ongoing monitoring (e.g., a scheduled uptime check) is future work, not part of proving the walking skeleton.

## Risks / Trade-offs

- [No manual approval gate on this application's deploy] → Mitigated by the blast radius being confined to this application's own container (see Decisions above); the pull-request validation gate (lint/type/test) still runs before any merge, and the post-deploy health check fails the run — and therefore is visible — if the deploy didn't actually come up healthy.
- [This change is blocked on a companion `/infrastructure` change landing first] → Both changes are being drafted together in this session specifically to avoid this becoming an untracked dependency; `tasks.md` calls out the ordering explicitly.
- [Domain/DNS for the Traefik `Host()` rule is not yet decided] → Tracked as an open question below; does not block writing the pipeline itself, only actually exercising it end-to-end.

## Migration Plan

This is new infrastructure, not a migration — there is no prior deployed state to preserve or roll back from. Two layers guard against a bad deploy, but neither is a rollback mechanism — both only make a bad deploy fail loudly rather than silently: the `Dockerfile`'s `HEALTHCHECK` (task 2.1) gives `docker compose up -d --wait` a real readiness signal, so a container that starts but never becomes healthy causes that command — and therefore the host-side deploy script and the SSH session running it — to exit non-zero rather than reporting success; and the workflow's own post-deploy health check (task 6.1) independently verifies the public URL and fails the run, visibly, if it doesn't get a successful response, catching anything the first layer wouldn't (e.g. Traefik routing/DNS issues outside the container itself). Neither layer keeps the previous container running or provides automatic rollback — `docker compose up` replaces the running service as part of recreating it, with no built-in blue/green or rollback-on-failure behavior. If that stronger guarantee is ever needed, it's explicit future work, not something this change provides.

## Open Questions

- **Domain/subdomain for this application.** Not yet decided; the Traefik label in `docker-compose.yml` and the URL the workflow curls both need a concrete value before the deploy-verification step can actually run. Filling this in doesn't change any requirement, decision, or task above — only a literal string in the compose file and the workflow.
