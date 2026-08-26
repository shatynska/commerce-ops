## MODIFIED Requirements

### Requirement: Application Migrates the Database Before Serving Traffic

The `app` service SHALL wait until the Postgres service reports healthy before starting, SHALL apply all pending database migrations to completion, SHALL then seed the first roster admin, SHALL then run the playbook step-set preparation step, and SHALL then run the handler-registration report — in that order — before it begins serving HTTP requests. Naming the report in the ordering is what makes the preparation step's position checkable: the report describes the set the deployment is about to serve, so it SHALL follow the step that may replace it. The seeding steps SHALL run as their own processes rather than inside the serving process — `database-session` governs what that buys and what such a step owes as a session-obtaining process, and is not restated here so that the two cannot diverge — and SHALL run after the migrations, since they write to tables those migrations create. A failing migration and a failing seed SHALL each leave the container serving no requests, so a deployment nobody could administer is stopped at a named step whose failure is distinguishable from a server crash, rather than serving.

Both seeding steps may run on every start, and for the same reason: each is conditional on state it can read. The roster's step does nothing when an active admin already exists; the playbook step adds only what the stored set does not carry, so a start on which it has nothing to add writes nothing. Neither needs a signal delivered alongside the deployment — which matters, because a deployment cannot withdraw one: `.env` is rendered at deploy time, so a signal set for one deploy would stay set across every restart until the next.

Both are idempotent, so repetition is harmless in both cases — `launch-playbook` states what that means for the playbook step and why it is the property the chain depends on.

#### Scenario: App does not start before Postgres is healthy

- **WHEN** the stack starts and Postgres has not yet reported healthy
- **THEN** the `app` service SHALL NOT be started

#### Scenario: App serves no traffic until migrations complete

- **WHEN** the `app` container starts with pending migrations
- **THEN** it SHALL apply them to completion before accepting HTTP requests, and SHALL NOT begin serving requests if a migration fails

#### Scenario: App serves no traffic until the first admin is seeded

- **WHEN** the `app` container starts against a roster holding no active admin
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
