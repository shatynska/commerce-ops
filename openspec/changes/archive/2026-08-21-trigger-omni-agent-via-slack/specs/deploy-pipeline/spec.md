## MODIFIED Requirements

### Requirement: Deploy Delivers the Compose File and Triggers the Host-Side Deploy Script
The deploy job SHALL package this application's `docker-compose.yml` together with a freshly rendered file naming the image tag built for the triggering commit and carrying this application's runtime secrets into an archive, and SHALL pipe that archive over standard input to the single SSH connection described above, which triggers the host's fixed deploy mechanism for this application — extracting the archive's contents and pulling and recreating the container from the image named by that tag, with the container's process environment populated from the rendered file's runtime secrets. `docker-compose.yml`'s image reference SHALL be parameterized by that tag, not hardcoded to a fixed or mutable (e.g. `latest`) value.

#### Scenario: Deploy step updates the running container
- **WHEN** the deploy job completes successfully
- **THEN** the host SHALL be running a container started from the image tagged with the triggering commit's SHA, not a previously deployed image

#### Scenario: Image tag reaches the host without being committed
- **WHEN** the deploy job renders the file naming the image tag
- **THEN** that file SHALL be generated fresh for that run from the triggering commit's SHA and SHALL NOT be committed to the repository

#### Scenario: Runtime secrets reach the container without being committed
- **WHEN** the deploy job renders the file carrying this application's runtime secrets
- **THEN** that file SHALL be generated fresh for that run from GitHub Actions secrets, SHALL NOT be committed to the repository, and its values SHALL be present in the running container's process environment after the deploy completes
