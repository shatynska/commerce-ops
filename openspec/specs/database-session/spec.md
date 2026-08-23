# database-session Specification

## Purpose

Provides database sessions to every caller in a process — those serving an HTTP request and those that are not — from a single connection pool per process, whose lifetime is bounded by that process's own, so that work outside the request cycle reaches the database through one owner of the engine, the connection setting and its validation, rather than by importing another module's driving adapter or duplicating engine construction.

## Requirements

### Requirement: One Connection Pool Per Process Serves Every Application Session

Every database session the application obtains within a process SHALL be drawn from a single connection pool, regardless of how many callers request one and regardless of whether those callers are serving an HTTP request.

This requirement governs sessions used to reach the application's own domain data. It does NOT forbid a piece of infrastructure from holding a connection **or pool** of its own, provided that connection or pool is used solely for that infrastructure's own bookkeeping and never to reach domain data — a task queue's own tables and its long-lived `LISTEN` are bookkeeping in this sense, and would warrant separate connections even under a single driver. What the requirement forbids is a second route to domain data.

The axis is what the connection is used for, not how many connections there are. An exempt component's connection use is therefore NOT bounded by this requirement; see the note on aggregate connections below.

#### Scenario: Repeated session requests share one pool

- **WHEN** sessions are requested more than once in a process
- **THEN** every session SHALL be drawn from the same connection pool

#### Scenario: Request-scoped and standalone callers share one pool

- **WHEN** a session is requested while serving an HTTP request, and another is requested by a caller that is not serving an HTTP request
- **THEN** both SHALL be drawn from the same connection pool

#### Scenario: Infrastructure holding its own connection or pool is not a second route to domain data

- **WHEN** a piece of infrastructure within the process holds a database connection or pool of its own, used solely for that infrastructure's own bookkeeping
- **THEN** that SHALL NOT be treated as a violation, provided every session reaching domain data still comes from the single pool

#### Scenario: An exempt component reaching domain data is a violation

- **WHEN** a piece of infrastructure holding its own connection or pool uses it to read or write the application's domain data
- **THEN** that SHALL be treated as a violation of this requirement, the exemption covering bookkeeping only

### Requirement: A Session Is Available Outside An HTTP Request

The application SHALL provide a way to obtain a database session that does not require an HTTP request to be in progress, and that does not require importing any module's HTTP adapter. The session SHALL be released when the caller is finished with it, including when the caller's work raises.

#### Scenario: Work that is not an HTTP request obtains a session

- **WHEN** a caller that is not serving an HTTP request requests a session
- **THEN** a usable session SHALL be provided

#### Scenario: A session is released after the caller's work completes

- **WHEN** a caller that obtained a session outside an HTTP request finishes its work
- **THEN** the session SHALL be released back to the pool

#### Scenario: A session is released when the caller's work raises

- **WHEN** a caller that obtained a session outside an HTTP request raises an exception before finishing
- **THEN** the session SHALL be released back to the pool, and the exception SHALL propagate to the caller unchanged

### Requirement: A Process That Obtained A Session Closes Its Pool Before Exiting

A process that has obtained a database session SHALL close its connection pool before exiting, releasing its connections rather than leaving them for the database to reclaim on its own timeouts. This binds each process that obtains sessions — the one serving HTTP today, and any other added later — rather than the application as a whole.

Exiting SHALL succeed whether or not any session was ever requested during the process's lifetime.

#### Scenario: The HTTP process releases connections when it stops

- **WHEN** the process serving HTTP has obtained a session, and that process is then stopped
- **THEN** its connection pool SHALL be closed as part of stopping

#### Scenario: Shutdown with no database use is not an error

- **WHEN** a process exits without any session having been requested
- **THEN** exiting SHALL succeed without raising

### Requirement: The Connection Setting Is Read No Earlier Than The First Session Request

The provider SHALL read the database connection setting no earlier than the first request for a session, so that importing the application's modules and starting and stopping its HTTP application object succeed with that setting absent.

This requirement adds only the read-timing guarantee. The import-and-start guarantee itself belongs to `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" and is not restated here, so that the two cannot diverge.

#### Scenario: The connection setting is read only when a session is first requested

- **WHEN** the application has started but no session has yet been requested
- **THEN** the database connection setting SHALL NOT have been read

#### Scenario: Starting and stopping with the database unconfigured

- **WHEN** the application's HTTP application object is started and then stopped with the database connection setting absent, without any session being requested
- **THEN** both SHALL succeed without raising, and endpoints requiring no database SHALL serve normally

### Requirement: An Absent Or Malformed Connection Setting Is Reported At The Point Of Use

When a session is requested and the database connection setting is absent, empty, or not a connection string the application can connect with, the request for a session SHALL fail with a report naming the setting, rather than failing with an error that names neither the setting nor the cause.

#### Scenario: A session is requested with the setting absent

- **WHEN** a session is requested and the database connection setting is absent from the environment
- **THEN** the request SHALL fail with a report naming that setting

#### Scenario: A session is requested with a setting the application cannot connect with

- **WHEN** a session is requested and the database connection setting carries a scheme the application cannot connect with
- **THEN** the request SHALL fail with a report naming that setting and the scheme required
