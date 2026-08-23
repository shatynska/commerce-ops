## Purpose

Runs the application's recurring work on a schedule from inside the deployment — retrying a failed run with backoff, and recording every run's outcome so that "did it run, and did it succeed" can be answered afterwards — so that scheduled work is not something the system merely hopes occurred.

## ADDED Requirements

### Requirement: Recurring Work Runs On Its Declared Schedule

The system SHALL run each piece of recurring work according to a schedule declared for it, without requiring a request from outside the deployment.

The schedule SHALL be interpreted in UTC on every host, regardless of the host's default timezone. This is structural rather than preferential: the runner evaluates cron expressions from absolute instants and accepts no timezone, so UTC is the only zone available. It is also the right one — a zone that observes DST produces daily windows that run twice or not at all.

#### Scenario: Work runs when its schedule is due

- **WHEN** a piece of recurring work has a declared schedule and that schedule becomes due
- **THEN** the system SHALL run that work

#### Scenario: Work with no declared schedule does not run

- **WHEN** a piece of work exists but has no declared schedule
- **THEN** the system SHALL NOT run it on a schedule

#### Scenario: The schedule's timezone does not depend on the host

- **WHEN** a schedule is evaluated on a host whose default timezone is not UTC
- **THEN** it SHALL be evaluated in UTC — a schedule declared for 06:00 SHALL become due at 06:00 UTC
- **AND** it SHALL produce the same due moments as on a host whose default is UTC

### Requirement: A Window Missed While No Worker Was Available Is Run Once On Return

When a piece of recurring work's due moment passes while no process is available to run it, the system SHALL run that work once when a process next becomes available, rather than skipping it silently.

When several due moments for the same work pass while no process is available, the system SHALL run that work once on return, not once per missed moment — a report is a statement about the present, and replaying a backlog of them produces a burst of stale reports rather than one useful one.

"While no process is available" means no process is running scheduled work at all — the case where the worker is stopped, crashed or being replaced. A live process whose own scheduling loop has stalled while it keeps running is a different failure, and one this capability does not govern.

#### Scenario: A single missed window is run on return

- **WHEN** a piece of recurring work's due moment passes with no process available, and a process then becomes available
- **THEN** the system SHALL run that work

#### Scenario: Several missed windows produce one run

- **WHEN** more than one due moment for the same piece of recurring work passes with no process available, and a process then becomes available
- **THEN** the system SHALL run that work exactly once, not once per missed moment

### Requirement: Scheduled Work Is Not Reachable From Outside The Deployment

Recurring work SHALL be started from within the deployment. The system SHALL NOT expose an externally reachable interface whose purpose is to start a piece of recurring work.

#### Scenario: No external interface starts scheduled work

- **WHEN** the system's externally reachable interfaces are enumerated
- **THEN** none of them SHALL exist for the purpose of starting a piece of recurring work

### Requirement: A Failed Run Is Retried With Increasing Delay

When a run fails, the system SHALL retry it, waiting longer before each successive attempt, up to a declared maximum number of attempts. When the maximum is reached without success, the system SHALL record the run as failed and SHALL stop retrying it.

#### Scenario: A failing run is retried

- **WHEN** an attempt fails and the run's declared maximum number of attempts has not been reached
- **THEN** the system SHALL retry it

#### Scenario: Successive retries wait longer

- **WHEN** a run fails more than once
- **THEN** each successive retry SHALL be attempted after a longer delay than the one before it

#### Scenario: Retries stop at the declared maximum

- **WHEN** a run has failed on its declared maximum number of attempts
- **THEN** the system SHALL record the run as failed
- **AND** SHALL NOT attempt it again

#### Scenario: A retried run that succeeds is recorded as succeeded

- **WHEN** a run fails, is retried, and the retry succeeds
- **THEN** the run SHALL be recorded as succeeded

### Requirement: Every Run's Outcome Is Recorded And Can Be Asked About Afterwards

The system SHALL record, for every run of a piece of recurring work: which work it was, when the run started, when it ended, and whether it succeeded or failed. This record SHALL survive the process that produced it, and SHALL be queryable afterwards.

A run spans its retries: a piece of work that fails and is retried is one run, not several. Its start is the first attempt's start, its end is the moment of the outcome that stopped it, and its outcome is that final outcome — consistent with a retried run that succeeds being recorded as succeeded, above.

#### Scenario: A completed run is recorded

- **WHEN** a run completes, whether it succeeded or failed
- **THEN** the system SHALL record which work it was, when it started, when it ended, and its outcome

#### Scenario: A run's record outlives the process

- **WHEN** the process that ran a piece of work has exited
- **THEN** that run's record SHALL still be available

#### Scenario: The most recent successful run can be identified

- **WHEN** the system is asked when a given piece of recurring work last succeeded
- **THEN** it SHALL report the time of that work's most recent successful run, or report that it has never succeeded

### Requirement: A Worker Failure Does Not Prevent The Application From Serving

The process running scheduled work SHALL be separate from the process serving HTTP requests, such that the failure or absence of the former does not stop the latter from serving.

#### Scenario: HTTP is served while no worker is running

- **WHEN** no process running scheduled work is available
- **THEN** the application SHALL continue to serve HTTP requests
