## MODIFIED Requirements

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
