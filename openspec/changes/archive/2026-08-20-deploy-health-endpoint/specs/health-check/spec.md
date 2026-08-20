## Purpose

Defines the contract of the application's liveness endpoint — what it checks, what it returns, and what it deliberately does not depend on — so it can serve as a stable target for deploy-verification and future monitoring.

## ADDED Requirements

### Requirement: Liveness Endpoint Available
The system SHALL expose an HTTP `GET /health` endpoint that returns a successful response whenever the application process is running and able to serve HTTP requests.

#### Scenario: Health check returns success when the service is running
- **WHEN** a client sends `GET /health` while the application is running
- **THEN** the response SHALL have HTTP status `200` and a JSON body indicating the service is healthy

### Requirement: Health Check Has No External Dependencies
`GET /health` SHALL report only that the application process itself is up — it SHALL NOT check connectivity to Postgres or any other external service, and its response SHALL NOT depend on any such service being reachable or configured.

#### Scenario: Health check succeeds independent of database availability
- **WHEN** `GET /health` is requested and no database connection exists or is configured
- **THEN** the endpoint SHALL still return the successful response described above
