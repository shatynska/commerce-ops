## ADDED Requirements

### Requirement: Compose File Provisions a Persistent, Network-Isolated Postgres Service

The delivered `docker-compose.yml` SHALL include a Postgres service whose data is stored in a named Docker volume, so that data persists across the host's `docker compose pull && up -d` deploy cycle. The Postgres service SHALL NOT be attached to the external, Traefik-facing network the `app` service uses to receive public traffic; it SHALL be reachable only from the `app` service, over a network private to this application's compose file.

#### Scenario: Postgres data survives a redeploy

- **WHEN** a deploy runs `docker compose pull && up -d` against an already-running stack with existing Postgres data
- **THEN** the Postgres service SHALL start with that existing data intact, not an empty database

#### Scenario: Postgres is unreachable from the public-facing network

- **WHEN** the compose file's networks are inspected
- **THEN** the Postgres service SHALL NOT be a member of the network the `app` service uses for its Traefik-routed public traffic

### Requirement: Application Migrates the Database Before Serving Traffic

The `app` service SHALL wait until the Postgres service reports healthy before starting, and SHALL apply all pending database migrations to completion before it begins serving HTTP requests.

#### Scenario: App does not start before Postgres is healthy

- **WHEN** the stack starts and Postgres has not yet reported healthy
- **THEN** the `app` service SHALL NOT be started

#### Scenario: App serves no traffic until migrations complete

- **WHEN** the `app` container starts with pending migrations
- **THEN** it SHALL apply them to completion before accepting HTTP requests, and SHALL NOT begin serving requests if a migration fails
