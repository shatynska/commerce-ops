## MODIFIED Requirements

### Requirement: Pull Request Validation Gate
Every pull request SHALL trigger a GitHub Actions job that runs `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the `tests/unit`, `tests/agents` and `tests/integration` pytest tiers. This job SHALL be a required branch-protection status check on `main`, SHALL NOT declare access to the deploy SSH credential, and SHALL run without any connection to the deploy host.

The gate SHALL provision the database the integration tier requires as an ephemeral service reachable only from the validation job, and SHALL bring it to the state a deployment serves before running that tier — applying the schema, and applying the seed the deployed application applies on start. A tier run against a schema alone meets a step set no deployment ever serves. A service running inside the job is not a connection to the deploy host, and needs no deploy secret.

A test that does not run SHALL NOT be reported as a test that passed. Where the gate runs a tier, **any** test skipped in that tier SHALL fail the gate, whatever the skip's stated reason — an absent database configuration, a failure to reach the database the tier is configured to run against, a database the test declines to accept, or a precondition the test finds unmet — so that a validation job cannot report success for work it never exercised. The gate SHALL name each skipped test and its reason, so that the failure identifies what stopped being checked rather than only that something did.

A test recorded as an expected failure is not a skipped test for the purpose of this requirement. An expected failure is a named, visible expectation carried in the run's own report, not a check withdrawn without notice.

The reachability clause above governs the tier's own database, not a database a test deliberately points at in order to observe how the system behaves when one is unreachable; a test of that kind SHALL run, and is subject to the skip rule like any other.

This obligation belongs to the gate, and does not extend to a run outside it. Where the gate's own marker is absent — a developer's machine — the integration tier SHALL skip as it does today, and a skip there SHALL NOT fail the run. The population that has configured no database is the one least able to act on a failure, and this requirement does not reach it.

#### Scenario: Pull request with a failing check is blocked
- **WHEN** a pull request fails `ruff`, `mypy`, `lint-imports`, or any pytest tier
- **THEN** the validation job SHALL fail and report the failure on the pull request, without attempting to reach the deploy host

#### Scenario: Validation requires no deploy secret
- **WHEN** the validation job runs on a pull request
- **THEN** it SHALL complete without reading the deploy SSH private key or any host-reachability secret

#### Scenario: The integration tier is exercised, not skipped
- **WHEN** the validation job runs the integration tier
- **THEN** the tier SHALL run against the job's own database, with the schema and the deployed seed already applied
- **AND** the job SHALL NOT pass on a run in which that tier was skipped for want of a database

#### Scenario: A gate with no database configured fails rather than passing
- **WHEN** the validation job runs the integration tier with no database configured for it
- **THEN** the job SHALL fail and name the missing configuration as the reason
- **AND** SHALL NOT report the integration tier as passed

#### Scenario: A gate whose database is unreachable fails rather than passing
- **WHEN** the validation job cannot reach the database the integration tier is configured to run against
- **THEN** the job SHALL fail and name that database as the reason
- **AND** SHALL NOT report the integration tier as passed

#### Scenario: A test the gate's database does not satisfy fails rather than skipping
- **WHEN** the validation job runs the integration tier against a database that is present, reachable and prepared, and a test in that tier declines to run against it
- **THEN** the job SHALL fail
- **AND** SHALL name that test and the reason it declined
- **AND** SHALL NOT report the integration tier as passed

#### Scenario: A test skipped for an unmet precondition fails rather than passing
- **WHEN** a test in the integration tier skips in the validation job because a precondition it needs is unmet, for a reason unrelated to the database
- **THEN** the job SHALL fail and name that test and its reason
- **AND** SHALL NOT report the integration tier as passed

#### Scenario: An expected failure is not treated as a skip
- **WHEN** a test in the integration tier is recorded in the validation job as an expected failure
- **THEN** the job SHALL NOT fail on account of it
- **AND** SHALL report it as an expected failure rather than as a skip

#### Scenario: A developer's run is not held to the gate's rule
- **WHEN** the integration tier runs outside the validation gate, on a machine where the gate's marker is not set, and a test skips
- **THEN** the run SHALL report the skip and its reason
- **AND** SHALL NOT fail on account of the skip
