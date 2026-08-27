## ADDED Requirements

### Requirement: The Container's Health Probe Allows Its Start Chain to Finish

The application container's health probe SHALL declare a start-up grace window during which a failing probe does not count towards the consecutive failures that report the container unhealthy. That window SHALL be long enough for the whole start chain this specification mandates to run to completion and hand over to the server — the configuration check required by *Container Checks Its Runtime Configuration Before Migrating And Serving*, and the migrations, both seeding steps and the handler-registration report required by *Application Migrates the Database Before Serving Traffic*.

This exists because the chain is this specification's own doing. Those two requirements between them put five processes in front of the server, and each one is time the container spends not answering the probe. A window sized for a container that only migrated and served will, as steps are added to the chain, eventually report a working deployment dead — silently, until a deploy goes red for a reason that has nothing to do with the deployment. The window is therefore stated here, next to the chain that consumes it, rather than left as a literal in the image that nobody owns.

**Sizing.** The window SHALL exceed, by at least two probe intervals, the largest start-to-healthy interval reported by the three most recent successful deploys — and SHALL NOT be less than 60 seconds.

That interval is what the deploy reports on every run, so the figure the window is sized against is measured rather than assumed. It is not the chain's duration: it is the moment of the first *successful* probe, so it snaps up to the probe's cadence and over-states the chain by up to one startup probe interval. The margin is therefore stated as an addition rather than a multiple — doubling a figure that is already inflated would count that inflation twice, and would tighten the rule as the host got slower for reasons the probe cadence invented.

Two intervals rather than one, because the margin has two jobs. The first interval absorbs the measurement itself: the reading may equal the chain exactly, so only what is added beyond it is guaranteed clearance. The second is headroom for the chain to grow — and one interval is the right unit for that, because adding a single process to the chain is what moved the reading by one tick and produced this requirement. A one-interval margin would spend the whole allowance on the measurement and leave a chain that grows by one step immediately in breach.

Where fewer than three successful deploys exist, the largest reading among those that do governs; where none does, the floor alone governs. A change that adds a step to the start chain SHALL read that figure from its own deploy and confirm the window still satisfies this.

**Scope.** The window governs a container's start, and a restarted container is a starting container — it receives the window again. The window SHALL NOT be obtained by widening the probe's interval or its consecutive-failure count, which are what govern how quickly a container that has stopped answering without exiting is reported unhealthy; those SHALL remain a 10-second interval and 3 consecutive failures.

#### Scenario: A chain slower than the probe's failure budget still deploys

- **WHEN** the container's start chain takes longer to reach the serving process than the probe's interval and consecutive-failure count would tolerate on their own, but completes within the start-up grace window
- **THEN** the container SHALL be reported healthy once the server answers the probe
- **AND** the deploy SHALL be reported successful rather than failing on an unhealthy container

#### Scenario: The declared window meets its floor

- **WHEN** the image's health probe is inspected
- **THEN** its start-up grace window SHALL be at least 60 seconds

#### Scenario: The declared window clears the measured interval

- **WHEN** a change adds a step to the start chain and reads the start-to-healthy interval its own deploy reports
- **THEN** the window SHALL exceed the largest such interval from the three most recent successful deploys by at least two probe intervals
- **AND** where it does not, the window SHALL be widened rather than the reading set aside

#### Scenario: A start that never completes still fails the deploy

- **WHEN** a step of the start chain fails, or the chain otherwise never reaches the serving process
- **THEN** the container SHALL never be reported healthy, however long the grace window is
- **AND** the deploy SHALL fail rather than reporting success

#### Scenario: Start-up tolerance is not taken from the steady-state signal

- **WHEN** the image's health probe is inspected
- **THEN** its interval SHALL be 10 seconds and its consecutive-failure count SHALL be 3
- **AND** the start-up grace window SHALL NOT have been obtained by widening either of them

#### Scenario: A restarted container is granted the window again

- **WHEN** a container that had been serving exits and its restart policy starts it again
- **THEN** it SHALL receive the start-up grace window as any starting container does, because it is starting
- **AND** it SHALL be reported unhealthy only once that window has passed and the consecutive-failure count is then reached
