## MODIFIED Requirements

### Requirement: A step carries the brief and the handler its automation needs

An `automated` step SHALL be able to declare an automation brief — what the code must establish, in prose — and a handler naming the use case that resolves it.

Neither SHALL be required of a `draft` step. The brief SHALL be required to leave `draft`, because a step nobody can state the acceptance criterion for is not ready to be built. The handler SHALL be required to become `active`. That a handler is *present* is a property of the step set, and is checked whenever the playbook is loaded. That the running code actually **registers** it is not — it is a property of the deployed code, which changes without the step set changing — so it SHALL be checked when a step is activated and SHALL NOT be re-checked at load, for the same reason assignees are not: a rename in the registry would otherwise make every stored playbook unloadable, taking down launches to report a deployment fault. A deployment whose registry no longer answers for an `active` step's handler SHALL instead be reported at startup, where a deployment fault belongs.

That startup report SHALL be produced by a process in which every handler this deployment answers for is registered. A report produced against a registry holding none of them SHALL NOT satisfy this requirement: such a report answers identically for a deployment that registers a step's handler and one that does not, and so establishes nothing about either.

The report SHALL name every `active` `automated` step whose handler is unregistered, and SHALL NOT, on account of the faults it names, prevent the deployment from starting — one unresolvable step leaves every other part of a launch working.

A `human` step SHALL carry neither, and declaring either on one SHALL be rejected.

#### Scenario: A draft automated step needs neither

- **WHEN** an automated step is created as a draft with no brief and no handler
- **THEN** the write is accepted

#### Scenario: Leaving draft requires the brief

- **WHEN** an automated step with no automation brief is moved out of `draft`
- **THEN** the write is rejected with a fault naming the step and the missing brief

#### Scenario: A handler the code does not register cannot be activated

- **WHEN** an automated step naming a handler no registered use case answers to is made `active`
- **THEN** the write is rejected with a fault naming the step and the unknown handler

#### Scenario: The reporting process holds the deployment's own registrations

- **WHEN** the process that makes the startup report is started the way the deployment starts it
- **THEN** the registry it consults holds every handler this deployment answers for, and holds the same handlers as every other process of this deployment that consults the registry

#### Scenario: A registered handler draws no fault at startup

- **WHEN** the process that makes the startup report is started the way the deployment starts it, over a step set holding an `active` `automated` step whose handler this deployment's code registers
- **THEN** no fault is reported for that step

#### Scenario: An unregistered handler is named at startup

- **WHEN** the process that makes the startup report is started the way the deployment starts it, over a step set holding an `active` `automated` step whose handler this deployment's code does not register
- **THEN** the report names that step and the handler it could not resolve

#### Scenario: The faults the report names do not stop the deployment

- **WHEN** the startup report names one or more `active` `automated` steps whose handlers are unregistered
- **THEN** the deployment continues to start, and every step whose handler is registered is unaffected

#### Scenario: A human step carries no automation fields

- **WHEN** a `human` step is written with an automation brief or a handler
- **THEN** the write is rejected with a fault naming the step
