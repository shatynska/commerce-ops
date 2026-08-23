# shared-vocabulary delta — introduce-launch-briefing

## ADDED Requirements

### Requirement: Severity vocabulary names the reporting tiers

The shared vocabulary SHALL name the severities an attention item can carry: monitor, diagnose, and critical — the tiers findings are graded into for reporting. Below-threshold noise is not a severity: something not worth reporting produces no item at all. Severity values SHALL follow the vocabulary's existing construction rules: a known tier is constructible, an unknown one is rejected.

#### Scenario: A known severity is constructed

- **WHEN** a severity is constructed from the value "critical"
- **THEN** the severity is created and reports its value

#### Scenario: An unknown severity is rejected

- **WHEN** a severity is constructed from a value outside monitor, diagnose, critical
- **THEN** construction SHALL be rejected
