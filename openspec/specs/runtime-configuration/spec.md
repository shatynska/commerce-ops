# runtime-configuration Specification

## Purpose

Declares, in one place, every environment variable this application's runtime requires, so that an incomplete or malformed configuration is detected and reported in full before the application serves traffic, rather than surfacing later as a failure inside whichever capability happened to need the missing value first.

## Requirements

### Requirement: Every Variable The Runtime Requires Is Declared In One Place
The system SHALL declare, in a single definition, every environment variable the application's runtime requires — whether the application's own source reads it, or a dependency reads it on the application's behalf. Each declaration SHALL carry the variable's type and whether it is required or optional, and required variables MAY additionally be marked startup-critical.

A variable consumed only by the deployment's own machinery, and never by the application process — a Compose file's substitutions, or another container's startup script — is outside this declaration, because the application cannot check what it never receives.

This requirement governs the declaration's completeness. It does NOT require that every read go through the declaration: a module MAY read a variable directly where routing it through the declaration would defeat required behavior — as it does for the variable controlling logging, which must be readable while the rest of the configuration is faulty, and for the database connection setting, whose reader must fail on its own absence rather than on an unrelated variable's.

#### Scenario: Every declared variable is discoverable from one definition
- **WHEN** the set of environment variables the application's runtime requires is inspected
- **THEN** every such variable SHALL be declared in the single definition, with its type, whether it is required or optional, and whether it is startup-critical

#### Scenario: A variable read by the application but not declared is detected
- **WHEN** the application's own source reads an environment variable that the single definition does not declare
- **THEN** that omission SHALL be detected automatically, rather than depending on a reader noticing it

#### Scenario: A declared variable the application does not read carries a recorded reason
- **WHEN** the single definition declares a variable that the application's own source does not read
- **THEN** that variable SHALL carry a recorded reason naming what consumes it instead, or the absence of such a reason SHALL be detected automatically

### Requirement: Configuration Faults Are Detected And Reported Together
When the configuration is checked, the system SHALL detect every declared non-optional variable that is absent, empty, or unparseable as its declared type, and SHALL report every faulting variable by name in a single report rather than reporting only the first fault encountered. It SHALL ignore any variable present in the environment or environment file that it does not declare, rather than treating it as a fault.

#### Scenario: Several required variables are faulty at once
- **WHEN** the configuration is checked and more than one required variable is absent
- **THEN** the report SHALL name every absent variable, not only one of them

#### Scenario: A variable cannot be parsed as its declared type
- **WHEN** the configuration is checked and a variable's value cannot be parsed as the type it is declared with — such as a database URL whose scheme is not one the application can connect with
- **THEN** that variable SHALL be reported as faulting

#### Scenario: A variable is present but empty
- **WHEN** the configuration is checked and a declared non-optional variable is present but its value is empty
- **THEN** that variable SHALL be reported as faulting, the same as if it were absent

#### Scenario: An optional variable's absence is not a fault
- **WHEN** the configuration is checked and a variable declared optional is absent
- **THEN** it SHALL NOT be reported as faulting, and the value SHALL be reported as absent to any caller that asks for it

#### Scenario: An unrecognized variable in the environment is not a fault
- **WHEN** the configuration is checked and the environment or environment file carries a variable the definition does not declare
- **THEN** it SHALL be ignored rather than reported as a fault, since the deployment delivers variables the application does not consume

### Requirement: Only A Startup-Critical Fault Prevents Startup
A fault in a variable marked startup-critical SHALL cause the configuration check to fail. A fault in any other declared variable SHALL be reported without causing the check to fail, so that a capability-scoped misconfiguration degrades that capability rather than the whole application.

#### Scenario: A startup-critical variable is faulty
- **WHEN** the configuration is checked and a variable marked startup-critical is absent, empty, or unparseable
- **THEN** the check SHALL fail

#### Scenario: A capability-scoped variable is faulty
- **WHEN** the configuration is checked and a required variable that is not marked startup-critical is absent, empty, or unparseable
- **THEN** the check SHALL report it as faulting
- **AND** the check SHALL NOT fail on account of it

### Requirement: Checking Configuration Performs No Network Or Database Access
Reading and checking the configuration SHALL read only the process environment and, where present, a local environment file. It SHALL NOT contact Slack, the database, or any other external service, so that a configuration fault is distinguishable from a reachability fault.

#### Scenario: Configuration is checked with no external service reachable
- **WHEN** the configuration is checked in an environment where no external service is reachable
- **THEN** the check SHALL complete on the strength of the environment alone, and its outcome SHALL depend only on the declared variables' presence and parseability

### Requirement: Importing And Starting The Application Do Not Require Configuration To Be Present
Importing the application's modules, and starting its HTTP application object, SHALL succeed with the environment empty. Configuration SHALL be read no earlier than the point at which it is checked or first used.

#### Scenario: Application imports with an empty environment
- **WHEN** the application's modules are imported with every declared variable absent from the environment
- **THEN** the import SHALL succeed without raising

#### Scenario: HTTP application object starts with an empty environment
- **WHEN** the application's HTTP application object is started, including any startup hook it declares, with every declared variable absent from the environment
- **THEN** startup SHALL succeed, and endpoints that require no configuration SHALL serve normally
