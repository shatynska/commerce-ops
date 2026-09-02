## Purpose

Defines the CI/CD pipeline that validates, builds, delivers, and verifies deploys of this application to the shared production host — what gates a merge, how the deploy reaches the host, and how the pipeline proves the deploy actually worked.

## Requirements

### Requirement: Pull Request Validation Gate
Every pull request SHALL trigger a GitHub Actions job that runs `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the `tests/unit`, `tests/agents` and `tests/integration` pytest tiers. This job SHALL be a required branch-protection status check on `main`, SHALL NOT declare access to the deploy SSH credential, and SHALL run without any connection to the deploy host.

The gate SHALL provision the database the integration tier requires as an ephemeral service reachable only from the validation job, and SHALL apply the schema to it before running that tier. A service running inside the job is not a connection to the deploy host, and needs no deploy secret.

A tier that does not run SHALL NOT be reported as a tier that passed. Where the gate runs a tier, an absent database configuration, or a failure to reach the database that tier is configured to run against, SHALL fail the gate rather than be skipped — so that a validation job cannot report success for work it never exercised. This governs the tier's own database, not a database a test deliberately points at in order to observe how the system behaves when one is unreachable.

#### Scenario: Pull request with a failing check is blocked
- **WHEN** a pull request fails `ruff`, `mypy`, `lint-imports`, or any pytest tier
- **THEN** the validation job SHALL fail and report the failure on the pull request, without attempting to reach the deploy host

#### Scenario: Validation requires no deploy secret
- **WHEN** the validation job runs on a pull request
- **THEN** it SHALL complete without reading the deploy SSH private key or any host-reachability secret

#### Scenario: The integration tier is exercised, not skipped
- **WHEN** the validation job runs the integration tier
- **THEN** the tier SHALL run against the job's own database, with the schema already applied
- **AND** the job SHALL NOT pass on a run in which that tier was skipped for want of a database

#### Scenario: A gate with no database configured fails rather than passing
- **WHEN** the validation job runs the integration tier with no database configured for it
- **THEN** the job SHALL fail and name the missing configuration as the reason
- **AND** SHALL NOT report the integration tier as passed

#### Scenario: A gate whose database is unreachable fails rather than passing
- **WHEN** the validation job cannot reach the database the integration tier is configured to run against
- **THEN** the job SHALL fail and name that database as the reason
- **AND** SHALL NOT report the integration tier as passed

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

The `app` service SHALL wait until the Postgres service reports healthy before starting, SHALL apply all pending database migrations to completion, SHALL then seed the first members admin, SHALL then run the playbook step-set preparation step, and SHALL then run the handler-registration report — in that order — before it begins serving HTTP requests. Naming the report in the ordering is what makes the preparation step's position checkable: the report describes the set the deployment is about to serve, so it SHALL follow the step that may replace it. The seeding steps SHALL run as their own processes rather than inside the serving process — `database-session` governs what that buys and what such a step owes as a session-obtaining process, and is not restated here so that the two cannot diverge — and SHALL run after the migrations, since they write to tables those migrations create. A failing migration and a failing seed SHALL each leave the container serving no requests, so a deployment nobody could administer is stopped at a named step whose failure is distinguishable from a server crash, rather than serving.

Both seeding steps may run on every start, and for the same reason: each is conditional on state it can read. The membership's step does nothing when an active admin already exists; the playbook step adds only what the stored set does not carry, so a start on which it has nothing to add writes nothing. Neither needs a signal delivered alongside the deployment — which matters, because a deployment cannot withdraw one: `.env` is rendered at deploy time, so a signal set for one deploy would stay set across every restart until the next.

Both are idempotent, so repetition is harmless in both cases — `launch-playbook` states what that means for the playbook step and why it is the property the chain depends on.

#### Scenario: App does not start before Postgres is healthy

- **WHEN** the stack starts and Postgres has not yet reported healthy
- **THEN** the `app` service SHALL NOT be started

#### Scenario: App serves no traffic until migrations complete

- **WHEN** the `app` container starts with pending migrations
- **THEN** it SHALL apply them to completion before accepting HTTP requests, and SHALL NOT begin serving requests if a migration fails

#### Scenario: App serves no traffic until the first admin is seeded

- **WHEN** the `app` container starts against a membership holding no active admin
- **THEN** the seeding step SHALL run after the migrations and before the server starts, and SHALL NOT begin serving requests if that step fails

#### Scenario: The seeding step is bound as a session-obtaining process

- **WHEN** either seeding step has obtained a database session and then exits, whether it succeeded or failed
- **THEN** it releases its connections rather than leaving them for the database to reclaim on its own timeouts, which `database-session` requires of every process that obtains a session

#### Scenario: An ordinary start does not touch the step set

- **WHEN** the `app` container starts against a step set that already carries every vendored step
- **THEN** the chain reaches the server with the stored step set unchanged

#### Scenario: The handler report follows the preparation step

- **WHEN** the chain runs a start on which the playbook step adds steps
- **THEN** the handler-registration report runs afterwards, over the set the step established

#### Scenario: A failing playbook step stops the chain

- **WHEN** the playbook step is asked to run and fails
- **THEN** the container serves no requests, and the failure is distinguishable from a server crash

### Requirement: A Container Starts From Its Image Alone

A container started from this application's image SHALL reach a working state using only what that image already contains. It SHALL NOT contact a package index, resolve dependencies, or install packages as part of starting.

This makes the image the unit that is built, tested and deployed — the property the pipeline's build step already assumes when it publishes an image tagged with a commit SHA. A start that installs packages is a start whose outcome depends on the state of an external index at that moment, which is neither the tested state nor a recorded one.

Dependency groups declared for development or testing rather than for running the application — today, the `dev` group — SHALL NOT be installed into a container at any point, whether at build time or at start.

#### Scenario: A container starts with no route to a package index

- **WHEN** a container is started from the application's image on a host that cannot reach any package index
- **THEN** it SHALL start and reach its normal working state
- **AND** it SHALL NOT fail, stall, or degrade because the index was unreachable

#### Scenario: Development-only dependencies are absent at runtime

- **WHEN** a running container's installed packages are inspected
- **THEN** the dependencies declared for development and testing only SHALL NOT be present

#### Scenario: The pipeline proves this before deploying

- **WHEN** the pipeline builds an image
- **THEN** it SHALL verify, before that image is deployed, that a container from it starts with no access to a package index
- **AND** a failure of that verification SHALL stop the deploy

#### Scenario: Starting a container installs nothing

- **WHEN** a container is started and the packages present at start are compared with those the image was built with
- **THEN** they SHALL be the same set

### Requirement: The Container's Health Probe Allows Its Start Chain to Finish

The application container's health probe SHALL declare a start-up grace window during which a failing probe does not count towards the consecutive failures that report the container unhealthy. That window SHALL be long enough for the whole start chain this specification mandates to run to completion and hand over to the server — the configuration check required by *Container Checks Its Runtime Configuration Before Migrating And Serving*, and the migrations, both seeding steps and the handler-registration report required by *Application Migrates the Database Before Serving Traffic*.

This exists because the chain is this specification's own doing. Those two requirements between them put five processes in front of the server, and each one is time the container spends not answering the probe. A window sized for a container that only migrated and served will, as steps are added to the chain, eventually report a working deployment dead — silently, until a deploy goes red for a reason that has nothing to do with the deployment. The window is therefore stated here, next to the chain that consumes it, rather than left as a literal in the image that nobody owns.

**Sizing.** The window SHALL exceed, by at least two probe intervals, the largest start-to-healthy interval reported by the three most recent successful deploys — and SHALL NOT be less than 60 seconds.

That interval is what the deploy reports on every run, so the figure the window is sized against is measured rather than assumed. It is not the chain's duration: it is the moment of the first *successful* probe, so it snaps up to the probe's cadence and over-states the chain by up to one startup probe interval. The margin is therefore stated as an addition rather than a multiple — doubling a figure that is already inflated would count that inflation twice, and would tighten the rule as the host got slower for reasons the probe cadence invented.

Two intervals rather than one, because the margin has two jobs. The first interval absorbs the measurement itself: the reading may equal the chain exactly, so only what is added beyond it is guaranteed clearance. The second is headroom for the chain to grow — and one interval is the right unit for that, because adding a single process to the chain is what moved the reading by one tick and produced this requirement. A one-interval margin would spend the whole allowance on the measurement and leave a chain that grows by one step immediately in breach.

Where fewer than three successful deploys exist, the largest reading among those that do governs; where none does, the floor alone governs. A change that adds a step to the start chain SHALL read that figure from its own deploy and confirm the window still satisfies this.

**Scope.** The window governs a container's start, and a restarted container is a starting container — it receives the window again. The window SHALL NOT be obtained by widening the probe's interval or its consecutive-failure count, which are what govern how quickly a container that has stopped answering without exiting is reported unhealthy; those SHALL remain a 10-second interval and 3 consecutive failures.

#### Scenario: A chain slower than the probe's failure budget still deploys

- **WHEN** the container's start chain takes longer to reach the serving process than the probe's interval and consecutive-failure count would tolerate on their own, but completes within the start-up grace window
- **THEN** the container SHALL be reported healthy once the server answers the probe
- **AND** the deploy SHALL be reported successful rather than failing on an unhealthy container

#### Scenario: The declared window meets its floor

- **WHEN** the image's health probe is inspected
- **THEN** its start-up grace window SHALL be at least 60 seconds

#### Scenario: The declared window clears the measured interval

- **WHEN** a change adds a step to the start chain and reads the start-to-healthy interval its own deploy reports
- **THEN** the window SHALL exceed the largest such interval from the three most recent successful deploys by at least two probe intervals
- **AND** where it does not, the window SHALL be widened rather than the reading set aside

#### Scenario: A start that never completes still fails the deploy

- **WHEN** a step of the start chain fails, or the chain otherwise never reaches the serving process
- **THEN** the container SHALL never be reported healthy, however long the grace window is
- **AND** the deploy SHALL fail rather than reporting success

#### Scenario: Start-up tolerance is not taken from the steady-state signal

- **WHEN** the image's health probe is inspected
- **THEN** its interval SHALL be 10 seconds and its consecutive-failure count SHALL be 3
- **AND** the start-up grace window SHALL NOT have been obtained by widening either of them

#### Scenario: A restarted container is granted the window again

- **WHEN** a container that had been serving exits and its restart policy starts it again
- **THEN** it SHALL receive the start-up grace window as any starting container does, because it is starting
- **AND** it SHALL be reported unhealthy only once that window has passed and the consecutive-failure count is then reached
