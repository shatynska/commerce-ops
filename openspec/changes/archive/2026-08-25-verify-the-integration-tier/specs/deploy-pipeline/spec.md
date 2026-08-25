## MODIFIED Requirements

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
