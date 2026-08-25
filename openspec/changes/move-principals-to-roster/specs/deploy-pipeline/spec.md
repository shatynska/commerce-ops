## MODIFIED Requirements

### Requirement: Application Migrates the Database Before Serving Traffic

The `app` service SHALL wait until the Postgres service reports healthy before starting, SHALL apply all pending database migrations to completion, and SHALL then seed the first roster admin — in that order — before it begins serving HTTP requests. The seeding step SHALL run as its own process rather than inside the serving process — `database-session` governs what that buys and what the step owes as a session-obtaining process, and is not restated here so that the two cannot diverge — and SHALL run after the migrations, since it writes to tables those migrations create. A failing migration and a failing seed SHALL each leave the container serving no requests, so a deployment nobody could administer is stopped at a named step whose failure is distinguishable from a server crash, rather than serving.

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

- **WHEN** the seeding step has obtained a database session and then exits, whether it succeeded or failed
- **THEN** it releases its connections rather than leaving them for the database to reclaim on its own timeouts, which `database-session` requires of every process that obtains a session
