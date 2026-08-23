## Purpose

Defines the CI/CD pipeline that validates, builds, delivers, and verifies deploys of this application to the shared production host — what gates a merge, how the deploy reaches the host, and how the pipeline proves the deploy actually worked.

## Requirements

### Requirement: Pull Request Validation Gate
Every pull request SHALL trigger a GitHub Actions job that runs `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the `tests/unit` and `tests/agents` pytest tiers. This job SHALL be a required branch-protection status check on `main`, SHALL NOT declare access to the deploy SSH credential, and SHALL run without any host connection.

#### Scenario: Pull request with a failing check is blocked
- **WHEN** a pull request fails `ruff`, `mypy`, `lint-imports`, or either pytest tier
- **THEN** the validation job SHALL fail and report the failure on the pull request, without attempting to reach the deploy host

#### Scenario: Validation requires no deploy secret
- **WHEN** the validation job runs on a pull request
- **THEN** it SHALL complete without reading the deploy SSH private key or any host-reachability secret

### Requirement: Merge to Main Builds and Publishes an Image
On every merge to `main`, a GitHub Actions job SHALL build the application's Docker image and push it to GHCR, tagged at minimum with the triggering commit SHA.

#### Scenario: Successful merge produces a pulled-able image
- **WHEN** a pull request merges into `main`
- **THEN** an image tagged with that commit's SHA SHALL exist in GHCR before the deploy step runs

### Requirement: Deploy Reaches the Host Over a Private Tailnet Using an App-Scoped Key
The deploy job SHALL join the same private Tailscale tailnet the host is a member of before connecting, and SHALL authenticate over SSH using a deploy key scoped to this application specifically (a forced-command key bound to this application's name on the shared `deploy` account), never a key shared across other applications on the host. The deploy job SHALL deliver content and trigger the deploy within a single SSH connection over that key — it SHALL NOT send more than one command over the connection, since a forced-command key honors only the one invocation it is bound to.

#### Scenario: Deploy job joins the tailnet before SSH
- **WHEN** the deploy job runs
- **THEN** it SHALL establish tailnet connectivity before its first SSH attempt to the host

#### Scenario: Deploy key is scoped to this application only
- **WHEN** the deploy job authenticates to the host
- **THEN** it SHALL use a key that can trigger a deploy for this application only, and SHALL NOT be capable of triggering a deploy for any other application or the shared platform stack

#### Scenario: Deploy uses exactly one SSH connection
- **WHEN** the deploy job delivers content and triggers the deploy
- **THEN** it SHALL do so within one SSH connection over the deploy key, not a separate file-transfer connection followed by a separate trigger connection

### Requirement: Deploy Delivers the Compose File and Triggers the Host-Side Deploy Script
The deploy job SHALL package this application's `docker-compose.yml` together with a freshly rendered file naming the image tag built for the triggering commit and carrying this application's runtime secrets into an archive, and SHALL pipe that archive over standard input to the single SSH connection described above, which triggers the host's fixed deploy mechanism for this application — extracting the archive's contents and pulling and recreating the container from the image named by that tag, with the container's process environment populated from the rendered file's runtime secrets. `docker-compose.yml`'s image reference SHALL be parameterized by that tag, not hardcoded to a fixed or mutable (e.g. `latest`) value.

#### Scenario: Deploy step updates the running container
- **WHEN** the deploy job completes successfully
- **THEN** the host SHALL be running a container started from the image tagged with the triggering commit's SHA, not a previously deployed image

#### Scenario: Image tag reaches the host without being committed
- **WHEN** the deploy job renders the file naming the image tag
- **THEN** that file SHALL be generated fresh for that run from the triggering commit's SHA and SHALL NOT be committed to the repository

#### Scenario: Runtime secrets reach the container without being committed
- **WHEN** the deploy job renders the file carrying this application's runtime secrets
- **THEN** that file SHALL be generated fresh for that run from GitHub Actions secrets, SHALL NOT be committed to the repository, and its values SHALL be present in the running container's process environment after the deploy completes

### Requirement: Deploy Is Verified by Checking the Health Endpoint
After triggering the host-side deploy, the workflow SHALL request the application's public `GET /health` URL and SHALL fail the workflow run if it does not receive a successful response within a bounded number of retries.

#### Scenario: Deploy run fails if the health check does not succeed
- **WHEN** the post-deploy health check does not return a successful response after retrying
- **THEN** the workflow run SHALL be reported as failed, even if every preceding step succeeded

#### Scenario: Deploy run succeeds only once the health check passes
- **WHEN** the post-deploy health check returns a successful response
- **THEN** the workflow run SHALL be reported as successful

### Requirement: Serialized Deploys
The deploy job SHALL run under a GitHub Actions `concurrency` group so that two merges in quick succession queue rather than run concurrently.

#### Scenario: Two merges in quick succession deploy in order
- **WHEN** two pull requests merge to `main` within a short interval
- **THEN** the second deploy run SHALL queue until the first completes, and SHALL NOT run concurrently with it

### Requirement: Compose File Provisions a Persistent, Network-Isolated Postgres Service

The delivered `docker-compose.yml` SHALL include a Postgres service whose data is stored in a named Docker volume, so that data persists across the host's `docker compose pull && up -d` deploy cycle. The Postgres service SHALL NOT be attached to the external, Traefik-facing network the `app` service uses to receive public traffic; it SHALL be reachable only from this application's own services, over a network private to this application's compose file. That network SHALL NOT be declared external to this compose file, since an external network can be joined by services this application does not define.

The isolation this requires is from the shared, public-facing network and from other applications on the host — not from this application's own processes.

#### Scenario: Postgres data survives a redeploy

- **WHEN** a deploy runs `docker compose pull && up -d` against an already-running stack with existing Postgres data
- **THEN** the Postgres service SHALL start with that existing data intact, not an empty database

#### Scenario: Postgres is unreachable from the public-facing network

- **WHEN** the compose file's networks are inspected
- **THEN** the Postgres service SHALL NOT be a member of the network the `app` service uses for its Traefik-routed public traffic

#### Scenario: The network Postgres is reachable on is not external

- **WHEN** the compose file's networks are inspected
- **THEN** the network Postgres is attached to SHALL NOT be declared external, so that only services this compose file defines can join it
- **AND** every service attached to it SHALL be a service of this application's own compose file

### Requirement: Container Checks Its Runtime Configuration Before Migrating And Serving

The application container SHALL check its runtime configuration to completion before the database migration runs and before the HTTP server starts, reporting every faulting variable by name. A fault in a variable marked startup-critical SHALL fail the container's startup; any other fault SHALL be reported and startup SHALL continue.

#### Scenario: Container starts with a complete configuration

- **WHEN** the container starts and its runtime configuration is complete and parseable
- **THEN** the configuration check SHALL complete first, reporting no fault, and the migration and HTTP server SHALL then start as they do today

#### Scenario: Container starts with a startup-critical variable faulty

- **WHEN** the container starts and a runtime variable marked startup-critical is absent, empty, or unparseable
- **THEN** the container's startup SHALL fail, reporting every faulting variable
- **AND** the database migration SHALL NOT run and the HTTP server SHALL NOT start

#### Scenario: Container starts with a capability-scoped variable missing

- **WHEN** the container starts and a required runtime variable that is not startup-critical is absent from its environment
- **THEN** the check SHALL report that variable by name
- **AND** the migration and HTTP server SHALL still start, so that the capability which needs that variable is the only one affected

#### Scenario: A startup-critical fault leaves the deploy failed

- **WHEN** a deploy delivers a configuration whose startup-critical variables are faulty
- **THEN** the container SHALL never become healthy, and the deploy SHALL fail rather than reporting success

### Requirement: Application Migrates the Database Before Serving Traffic

The `app` service SHALL wait until the Postgres service reports healthy before starting, and SHALL apply all pending database migrations to completion before it begins serving HTTP requests.

#### Scenario: App does not start before Postgres is healthy

- **WHEN** the stack starts and Postgres has not yet reported healthy
- **THEN** the `app` service SHALL NOT be started

#### Scenario: App serves no traffic until migrations complete

- **WHEN** the `app` container starts with pending migrations
- **THEN** it SHALL apply them to completion before accepting HTTP requests, and SHALL NOT begin serving requests if a migration fails
