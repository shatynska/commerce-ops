## MODIFIED Requirements

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
