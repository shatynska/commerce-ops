## ADDED Requirements

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
