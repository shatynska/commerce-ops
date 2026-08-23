# application-logging Specification

## Purpose

Ensures log records are actually emitted, at a configurable threshold for the application's own records and a separate fixed threshold for its dependencies', with enough context to place a record in time and attribute it to a module, from every entrypoint the application starts through — rather than depending on whichever server or runner happens to host the process to have configured logging on its behalf.

## Requirements

### Requirement: The Application Emits Its Own Log Records

Once logging has been configured in a process, the application SHALL emit a record on its own logger hierarchy, at or above the configured threshold, to that process's standard error stream. Records emitted before configuration — during the import of an entrypoint's own modules — are outside this, as "Logging Is Configured From Every Entrypoint" records. This SHALL NOT depend on the process being hosted by any particular server or runner.

A record the application emits below the configured threshold SHALL NOT be emitted.

#### Scenario: A record at the configured threshold is emitted

- **WHEN** the application's logging is configured, and the application emits a record at the configured threshold
- **THEN** that record SHALL reach the process's standard error stream

#### Scenario: An informational record is emitted under the default threshold

- **WHEN** the application's logging is configured with no threshold specified, and the application emits a record at informational level
- **THEN** that record SHALL reach the process's standard error stream

#### Scenario: An application record below the configured threshold is suppressed

- **WHEN** the application's logging is configured at a given threshold, and the application emits a record below it
- **THEN** that record SHALL NOT reach the process's standard error stream

### Requirement: Dependency Records Are Formatted But Not Governed By The Application's Threshold

Records emitted on a logger outside the application's own hierarchy, where **neither that logger nor any of its ancestors below the root logger carries a handler or sets a level**, SHALL be emitted at and above a fixed threshold of warning level, carrying the same formatting as the application's own records. That fixed threshold SHALL NOT change when the application's configured threshold changes.

The ancestor clause is load-bearing rather than pedantic: a level and a handler are both resolved up the logger hierarchy, so a logger that configures nothing itself but descends from one that does is governed by its ancestor, not by this requirement.

This separation is required behavior, not an implementation detail: a single shared threshold would either bury the application's records in dependency noise at informational level, or silence the application's own records in order to quiet the dependencies.

The scope is deliberately stated by mechanism rather than by "installed libraries". A library that configures its own logger — attaching a handler, setting a level, or both — is one this capability does not **gate or suppress**: a record is gated by its originating logger's own effective level and delivered to that logger's own handlers. Such a record may still additionally reach this capability's handler, where that logger propagates, which is what the third scenario below states. The hosting HTTP server is the case where it does not: it sets `propagate: false`, so its records never reach this capability's handler and are governed instead by "The Hosting Server's Own Logging Is Left Intact" below.

#### Scenario: An unconfigured dependency's informational record is suppressed

- **WHEN** logging is configured at any threshold and a library whose logger carries no handler and sets no level of its own emits a record at informational level
- **THEN** that record SHALL NOT reach the process's standard error stream

#### Scenario: An unconfigured dependency's warning is emitted and formatted

- **WHEN** a library whose logger carries no handler and sets no level of its own emits a record at warning level or above
- **THEN** that record SHALL reach the process's standard error stream, formatted the same way as the application's own records

#### Scenario: A library that configures its own logger still emits its own records

- **WHEN** a library sets its own logger's level to informational, attaches its own handler, and emits an informational record
- **THEN** that record SHALL be emitted by the library's own handler
- **AND** it SHALL additionally reach this capability's handler if that logger propagates, so such a record appears twice rather than being suppressed

#### Scenario: Lowering the application's threshold does not turn on dependency logging

- **WHEN** the configured threshold is set below warning level
- **THEN** the records of a library whose logger carries no handler and sets no level of its own SHALL still NOT be emitted below warning level

#### Scenario: Raising the application's threshold does not silence dependency warnings

- **WHEN** the configured threshold is set above warning level
- **THEN** the records of a library whose logger carries no handler and sets no level of its own SHALL still be emitted at warning level and above

### Requirement: Every Emitted Record Carries Time, Level, And Origin

Every record emitted **through the logging this capability configures** SHALL carry the time at which it was emitted, its severity level, and the name of the logger that emitted it, in addition to the message itself. A record whose emission includes exception information SHALL carry that exception's traceback.

A record delivered by a handler this capability did not install is formatted by that handler. The hosting HTTP server's own records are the case in point: they never reach this capability's handler, and they are governed by "The Hosting Server's Own Logging Is Left Intact" below, not by this requirement.

#### Scenario: A record emitted through the configured logging identifies when, how severe, and from where

- **WHEN** a record is emitted through the logging this capability configures
- **THEN** the emitted output SHALL carry the time of emission, the record's level, and the emitting logger's name alongside the message

#### Scenario: An exception's traceback is preserved

- **WHEN** a record that includes exception information is emitted through the logging this capability configures
- **THEN** the emitted output SHALL carry that exception's traceback

### Requirement: The Threshold Is Configurable And Defaults To Informational

The application's threshold SHALL be configurable through the environment, and SHALL be deliverable to the running deployment without an application code change. When it is not configured, the threshold SHALL be informational level.

A configured value that is absent or empty SHALL be treated as not configured. A configured value that is present, non-empty, and does not name a recognized severity level SHALL NOT prevent logging from being configured: the application SHALL fall back to the default threshold and SHALL report the unrecognized value, rather than starting with logging unconfigured or failing to start. A value that is numeric rather than a level name SHALL be treated as unrecognized.

Recognition SHALL be case-insensitive, so that an operator writing a level name in lower case gets the level they asked for. A value naming the zero level (`NOTSET`) SHALL be treated as unrecognized rather than applied: it is a real level name, but setting it defers the application's records to the root threshold, silently restoring the very suppression this capability exists to remove — in the one situation where someone was deliberately adjusting logging.

#### Scenario: The threshold is configured explicitly

- **WHEN** the threshold is configured to a recognized severity level
- **THEN** application records at or above that level SHALL be emitted, and application records below it SHALL NOT

#### Scenario: The threshold is not configured

- **WHEN** the threshold is absent from the environment
- **THEN** the threshold SHALL be informational level

#### Scenario: The threshold is configured as an empty value

- **WHEN** the threshold is present in the environment but empty
- **THEN** it SHALL be treated as not configured, the threshold SHALL be informational level, and no unrecognized-value report SHALL be made

#### Scenario: A level name in lower case is recognized

- **WHEN** the threshold is configured to a recognized severity level written in lower case
- **THEN** it SHALL be applied as that level, and no unrecognized-value report SHALL be made

#### Scenario: The zero level is treated as unrecognized

- **WHEN** the threshold is configured to a value naming the zero level
- **THEN** logging SHALL be configured at the default threshold
- **AND** the value SHALL be reported as unrecognized

#### Scenario: The configured threshold is not a recognized level

- **WHEN** the threshold is configured to a non-empty value that does not name a recognized severity level, including a numeric value
- **THEN** logging SHALL be configured at the default threshold
- **AND** the unrecognized value SHALL be reported
- **AND** the application SHALL NOT fail to start on account of it

#### Scenario: The threshold can be set in the deployment without changing application code

- **WHEN** an operator sets the threshold for the deployment
- **THEN** the next deploy SHALL deliver it to the deployed process, without any change to the application's own source

### Requirement: Logging Is Configured From Every Entrypoint

Every entrypoint through which the application starts SHALL configure logging before performing its own work. This SHALL hold for entrypoints not hosted by the HTTP server, so that an entrypoint's log records do not depend on the HTTP server having started.

Two exclusions, both deliberate:

- Records emitted during the import of the modules an entrypoint imports are outside this guarantee. Closing that window would require configuring logging above an entrypoint's own imports, which the project's lint rules forbid; nothing emits at import today, and the trade is recorded in the change's design.
- A process that runs its own tooling rather than starting the application, and that configures logging from its own configuration file — the database migration step does both — is outside this requirement. Adding a second configuration there would fight the one it already has.

#### Scenario: A non-HTTP entrypoint emits records

- **WHEN** the application starts through an entrypoint that does not run the HTTP server, and a record at or above the configured threshold is emitted after that entrypoint has run
- **THEN** that record SHALL reach the process's standard error stream

#### Scenario: Configuring logging more than once does not duplicate records

- **WHEN** logging is configured more than once in a single process
- **THEN** a subsequently emitted record SHALL be emitted once, not once per configuration

### Requirement: The Hosting Server's Own Logging Is Left Intact

Configuring the application's logging SHALL NOT suppress the records the hosting HTTP server emits on its own behalf, and SHALL NOT cause them to be emitted more than once. This SHALL hold regardless of whether the server configures its logging before or after the application configures its own.

#### Scenario: Server request logs continue to be emitted exactly once

- **WHEN** the application's logging is configured and the hosting HTTP server emits a request record
- **THEN** that record SHALL be emitted exactly once

#### Scenario: The application's records survive the server configuring its own logging

- **WHEN** the hosting HTTP server applies its own logging configuration after the application has configured logging
- **THEN** a subsequently emitted application record SHALL still reach the process's standard error stream

### Requirement: Configuring Logging Requires No Configuration To Be Present

Configuring logging SHALL succeed with the environment empty, and SHALL NOT read or validate any environment variable other than the threshold. This preserves `runtime-configuration`'s requirement that importing the application's modules and starting its HTTP application object succeed with the environment empty.

#### Scenario: Logging is configured with an empty environment

- **WHEN** logging is configured with every environment variable absent
- **THEN** configuring SHALL succeed without raising, at the default threshold
