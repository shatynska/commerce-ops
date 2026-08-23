# scheduled-jobs Specification

## Purpose
Runs the application's recurring work on a schedule from inside the deployment — retrying a failed run with backoff, and recording every run's outcome so that "did it run, and did it succeed" can be answered afterwards — so that scheduled work is not something the system merely hopes occurred.

## Requirements

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

### Requirement: Each Piece Of Recurring Work Declares Its Schedule And Tolerance In One Place

Each piece of recurring work SHALL declare its schedule and its tolerance in a **single act of registration**, from a single schedule value — so that the schedule the work is run on and the schedule its tolerance is checked against cannot become different values. Every consumer that needs to know what is overdue — the check that reports it, and the interface that reports freshness — SHALL read that same registration, so that no two consumers can hold different opinions about the same work.

A tolerance SHALL exceed the longest gap between consecutive scheduled runs of its work, computed over a bounded horizon rather than assumed uniform, so that a schedule with unequal gaps — weekdays only, or monthly — does not report itself overdue across its longest gap.

#### Scenario: Every piece of work the runner will run has a tolerance

- **WHEN** the pieces of recurring work the job runner will actually run on a schedule are enumerated
- **THEN** each SHALL have a declared tolerance
- **AND** none SHALL be absent from the declaration the overdue check and the freshness interface read

#### Scenario: The schedule run and the schedule checked are the same value

- **WHEN** a piece of work's schedule as given to the job runner is compared to the schedule its tolerance was checked against
- **THEN** they SHALL be the same value

#### Scenario: A tolerance exceeds its work's longest scheduling gap

- **WHEN** a piece of recurring work's tolerance is compared to the longest gap between consecutive scheduled runs over a bounded horizon
- **THEN** the tolerance SHALL be the longer of the two

#### Scenario: Every consumer reads the same declaration

- **WHEN** the reporting check and the freshness interface each determine whether a given piece of work is overdue
- **THEN** both SHALL reach the same verdict, having read the same declared tolerance

#### Scenario: Every process holds the same registration

- **WHEN** the registrations visible to the process running scheduled work and to the process serving HTTP requests are compared
- **THEN** they SHALL contain the same pieces of work with the same tolerances
- **AND** neither SHALL be missing a piece of work the other holds

### Requirement: Work Is Overdue Relative To Its Last Success Or To When It Was First Known

A piece of recurring work SHALL be considered overdue when its declared tolerance has elapsed since it last succeeded.

Work that has never succeeded SHALL be considered overdue only once its tolerance has elapsed **since the system first knew of its schedule**. The system SHALL record when it first knew of each piece of work.

That record SHALL be written by the freshness interface when it serves a request, as well as by the process running scheduled work — so that a deployment whose worker never started still acquires an anchor for every registered piece of work, and does not report healthy indefinitely, which is the very failure this capability exists to expose. The write SHALL be idempotent: the recorded time is the first one observed and SHALL NOT be advanced by a later observation.

The record of when work was first known SHALL persist for as long as the work is registered, and SHALL NOT be cleared when the work succeeds.

A freshly deployed system therefore SHALL NOT report work as overdue before that work has had its tolerance in which to run for the first time.

#### Scenario: Work is overdue after its tolerance elapses since its last success

- **WHEN** a piece of recurring work's declared tolerance has elapsed since its most recent successful run
- **THEN** it SHALL be considered overdue

#### Scenario: Work that has never succeeded becomes overdue after its tolerance

- **WHEN** a piece of recurring work has never succeeded and its declared tolerance has elapsed since the system first knew of its schedule
- **THEN** it SHALL be considered overdue, on the basis that it has never succeeded

#### Scenario: A freshly deployed system does not report work as overdue immediately

- **WHEN** the system has just started for the first time, knows of a piece of recurring work, and that work has not yet run
- **THEN** it SHALL NOT be considered overdue until its tolerance has elapsed since the system first knew of it

#### Scenario: Work within its tolerance is not overdue

- **WHEN** a piece of recurring work last succeeded within its declared tolerance
- **THEN** it SHALL NOT be considered overdue

#### Scenario: A worker that never started still produces an anchor

- **WHEN** the freshness interface has served a request and the process running scheduled work has never started
- **THEN** each registered piece of work SHALL have a recorded first-known time
- **AND** SHALL become overdue once its tolerance has elapsed since that time

#### Scenario: A later observation does not advance the anchor

- **WHEN** a piece of work already has a recorded first-known time and is observed again
- **THEN** the recorded time SHALL be unchanged

#### Scenario: A success does not erase the first-known time

- **WHEN** a piece of recurring work succeeds
- **THEN** its recorded first-known time SHALL be unchanged

### Requirement: Overdue Work Is Reported To Slack From Inside The Deployment

When a piece of recurring work is overdue, the system SHALL post a message to the team's Slack channel naming the work and when it last succeeded, or that it has never succeeded.

The system SHALL NOT report a piece of work that has no declared schedule.

Note, as context rather than obligation: this check runs inside the process that runs scheduled work, so it cannot observe that process's own absence. Detecting an absent worker is the role of "Run Freshness Is Reportable Over HTTP" below, together with a checker outside the deployment.

#### Scenario: Overdue work is reported

- **WHEN** a piece of recurring work is overdue and the process running scheduled work is alive
- **THEN** the system SHALL post a message to the team's Slack channel naming that work and when it last succeeded, or that it has never succeeded

#### Scenario: Work within its tolerance is not reported

- **WHEN** a piece of recurring work is not overdue
- **THEN** the system SHALL NOT report it

#### Scenario: Work with no declared schedule is never reported

- **WHEN** a piece of work has no declared schedule
- **THEN** the system SHALL NOT report it as overdue, however long ago it last succeeded

#### Scenario: Overdueness during an absent worker remains visible

- **WHEN** no process running scheduled work is available and a piece of recurring work becomes overdue
- **THEN** that overdueness SHALL be reported by the freshness interface below

### Requirement: The Process Running Scheduled Work Is Itself Monitored Work

The process running scheduled work SHALL record a successful run frequently enough to serve as evidence that it is alive, and that evidence SHALL be subject to the same overdue determination as any other piece of recurring work, with a tolerance substantially shorter than that of the work it runs.

Without this, the absence of the worker becomes observable only once the work it was supposed to run is itself overdue — which for daily work means roughly a day, by which time a run has already been missed.

**This liveness evidence SHALL NOT depend on the reporting channel.** A run of the overdue check that completed its evaluation SHALL be recorded as successful whether or not it succeeded in delivering a report. A failed delivery is expressed solely by not recording suppression, never by failing the run — otherwise an outage of the reporting channel would make the liveness evidence stale and cause the freshness interface to report an absent worker while that worker is running normally.

#### Scenario: A completed evaluation records a successful run despite a failed delivery

- **WHEN** the overdue check completes its evaluation and its attempt to deliver a report fails
- **THEN** its run SHALL be recorded as successful
- **AND** its liveness evidence SHALL remain fresh

#### Scenario: The freshness interface is unaffected by a reporting-channel outage

- **WHEN** the reporting channel is unavailable and the process running scheduled work is running normally
- **THEN** the freshness interface SHALL NOT report that process as absent

#### Scenario: The worker's own liveness is monitored work

- **WHEN** the pieces of recurring work subject to overdue determination are enumerated
- **THEN** they SHALL include evidence of the worker process's own liveness

#### Scenario: An absent worker becomes visible well before the work it runs is overdue

- **WHEN** the process running scheduled work becomes unavailable
- **THEN** its liveness evidence SHALL become overdue before any work it runs on a longer schedule does

### Requirement: A Continuing Outage Is Reported Once, Not Repeatedly

The system SHALL report a given piece of overdue work once per period of overdueness rather than on every check. A period of overdueness SHALL end when the work next succeeds.

The record that suppresses further reports SHALL be written only after a report has been delivered successfully. A report that could not be delivered SHALL leave the work eligible to be reported on the next check — otherwise a transient failure of the reporting channel would silence the period's only alarm permanently, since suppression is lifted by the work succeeding and not by the channel recovering.

The record SHALL be persisted, so that restarting the process running scheduled work does not cause the reports to resume.

#### Scenario: A continuing outage is not reported repeatedly

- **WHEN** a piece of recurring work has been reported as overdue and remains overdue at the next check
- **THEN** the system SHALL NOT post a further message for that same period of overdueness

#### Scenario: A failed delivery leaves the work eligible to be reported again

- **WHEN** a report for an overdue piece of work could not be delivered, and the work is still overdue at the next check
- **THEN** the system SHALL attempt to report it again

#### Scenario: A restart does not resume reporting

- **WHEN** a piece of recurring work has been reported as overdue, the process running scheduled work restarts, and the work is still overdue
- **THEN** the system SHALL NOT post a further message for that same period of overdueness

#### Scenario: Overdueness recurring after a success is reported again

- **WHEN** a piece of recurring work was reported as overdue, subsequently succeeded, and later becomes overdue again
- **THEN** the system SHALL report it again

### Requirement: Run Freshness Is Reportable Over HTTP

The system SHALL expose, over HTTP from the process serving HTTP requests, how recently each piece of recurring work last succeeded, so that a checker outside the deployment can determine whether scheduled work is still happening.

The response SHALL be derived from recorded state alone, and SHALL NOT require the process running scheduled work to be available — that process's absence is the condition this interface exists to make visible.

Where the recorded state cannot be read, the system SHALL indicate an unhealthy state rather than a previously computed healthy one, and SHALL do so within a bounded time.

#### Scenario: Freshness is reported

- **WHEN** the freshness endpoint is requested
- **THEN** the system SHALL report, for each piece of recurring work, when it last succeeded or that it has never succeeded

#### Scenario: Unhealthy is signalled so an automated checker can act on it

- **WHEN** the freshness endpoint is requested and at least one piece of recurring work is overdue
- **THEN** the response SHALL indicate an unhealthy state in a way an automated checker can act on without parsing prose

#### Scenario: Freshness is reported while no worker is running

- **WHEN** the freshness endpoint is requested and no process running scheduled work is available
- **THEN** the system SHALL respond, reporting the resulting overdueness, rather than failing or hanging

#### Scenario: A freshly deployed system reports healthy

- **WHEN** the freshness endpoint is requested in a deployment where the recorded state is readable, no work has yet run, and no work's tolerance has elapsed since the system first knew of it
- **THEN** the system SHALL report each piece of work as never having succeeded
- **AND** SHALL indicate a healthy state, since nothing is yet overdue

#### Scenario: The endpoint does not consult the process running scheduled work

- **WHEN** the freshness endpoint serves a request
- **THEN** it SHALL NOT make any request to the process running scheduled work

#### Scenario: Recorded state that cannot be read is not reported as healthy

- **WHEN** the freshness endpoint is requested and the recorded state cannot be read
- **THEN** the system SHALL indicate an unhealthy state in a way an automated checker can act on without parsing prose
- **AND** SHALL NOT report any piece of work as being within its tolerance
- **AND** SHALL respond within a bounded time rather than waiting indefinitely on the unreadable state

#### Scenario: A recent healthy answer is not repeated once the state cannot be read

- **WHEN** the freshness endpoint has recently reported a healthy state and the recorded state then becomes unreadable, including where that earlier answer is still recent enough that the system need not re-evaluate it
- **THEN** the system SHALL indicate an unhealthy state, rather than repeating the earlier healthy answer

#### Scenario: A repeated request still anchors work that has no first-known time

- **WHEN** the freshness endpoint is requested, and requested again soon enough that it need not re-evaluate
- **THEN** the system SHALL perform the first-known recording for every registered piece of recurring work on the repeated request regardless, rather than serving a previously computed answer without having done so
- **AND** SHALL record a time for any registered piece of work that has none at that moment
