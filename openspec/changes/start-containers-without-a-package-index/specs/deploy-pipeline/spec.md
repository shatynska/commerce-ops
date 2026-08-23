## ADDED Requirements

### Requirement: A Container Starts From Its Image Alone

A container started from this application's image SHALL reach a working state using only what that image already contains. It SHALL NOT contact a package index, resolve dependencies, or install packages as part of starting.

This makes the image the unit that is built, tested and deployed — the property the pipeline's build step already assumes when it publishes an image tagged with a commit SHA. A start that installs packages is a start whose outcome depends on the state of an external index at that moment, which is neither the tested state nor a recorded one.

Dependency groups declared for development or testing rather than for running the application — today, the `dev` group — SHALL NOT be installed into a container at any point, whether at build time or at start.

#### Scenario: A container starts with no route to a package index

- **WHEN** a container is started from the application's image on a host that cannot reach any package index
- **THEN** it SHALL start and reach its normal working state
- **AND** it SHALL NOT fail, stall, or degrade because the index was unreachable

#### Scenario: Development-only dependencies are absent at runtime

- **WHEN** a running container's installed packages are inspected
- **THEN** the dependencies declared for development and testing only SHALL NOT be present

#### Scenario: The pipeline proves this before deploying

- **WHEN** the pipeline builds an image
- **THEN** it SHALL verify, before that image is deployed, that a container from it starts with no access to a package index
- **AND** a failure of that verification SHALL stop the deploy

#### Scenario: Starting a container installs nothing

- **WHEN** a container is started and the packages present at start are compared with those the image was built with
- **THEN** they SHALL be the same set
