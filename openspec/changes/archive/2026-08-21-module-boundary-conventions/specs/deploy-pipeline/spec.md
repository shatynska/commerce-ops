## MODIFIED Requirements

### Requirement: Pull Request Validation Gate
Every pull request SHALL trigger a GitHub Actions job that runs `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the `tests/unit` and `tests/agents` pytest tiers. This job SHALL be a required branch-protection status check on `main`, SHALL NOT declare access to the deploy SSH credential, and SHALL run without any host connection.

#### Scenario: Pull request with a failing check is blocked
- **WHEN** a pull request fails `ruff`, `mypy`, `lint-imports`, or either pytest tier
- **THEN** the validation job SHALL fail and report the failure on the pull request, without attempting to reach the deploy host

#### Scenario: Validation requires no deploy secret
- **WHEN** the validation job runs on a pull request
- **THEN** it SHALL complete without reading the deploy SSH private key or any host-reachability secret
