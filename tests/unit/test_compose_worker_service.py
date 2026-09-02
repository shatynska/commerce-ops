"""What the delivered `docker-compose.yml` declares after cron is retired.

Derived from the delta specs of the OpenSpec change
`replace-cron-with-job-runner`:

- `specs/deploy-pipeline/spec.md`, MODIFIED "Compose File Provisions a
  Persistent, Network-Isolated Postgres Service" / Scenarios: Postgres
  data survives a redeploy; Postgres is unreachable from the
  public-facing network; The network Postgres is reachable on is not
  external
- `specs/scheduled-jobs/spec.md`, "A Worker Failure Does Not Prevent The
  Application From Serving" -- the compose-level half of "The process
  running scheduled work SHALL be separate from the process serving HTTP
  requests"

plus a group of DERIVED assertions, each labelled, tracing to design.md's
"The worker is a separate service from the same image, with the
healthcheck overridden" and to tasks.md 3.1-3.6 rather than to any
`#### Scenario:` block.

See `test-manifest.md` at the change root for the full accounting.

## Level

Two of the three deploy-pipeline scenarios say "WHEN the compose file's
networks are inspected", so inspecting the compose file *is* the
scenario, and reading it here is the smallest unit that observes it. The
third scenario ("data survives a redeploy") describes a runtime outcome
that no unit test can observe; what is asserted here is the declaration
that outcome depends on -- a named volume rather than an anonymous or
bind-mounted one -- and the runtime half is recorded as uncovered in the
manifest, assigned to the change's own deploy verification (tasks 6.4,
6.5).

Nothing about the file's location or its service names is invented: the
file is `docker-compose.yml` at the repository root, `app` and `postgres`
are the services it declares today, and `worker` is the name tasks.md 3.2
gives the new service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    text = (_repository_root() / "docker-compose.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture()
def services(compose: dict[str, Any]) -> dict[str, Any]:
    section: dict[str, Any] = compose.get("services", {})
    return section


@pytest.fixture()
def networks(compose: dict[str, Any]) -> dict[str, Any]:
    section: dict[str, Any] = compose.get("networks", {})
    return section


@pytest.fixture()
def worker(services: dict[str, Any]) -> dict[str, Any]:
    """The worker service, or a clear failure naming its absence.

    Every assertion below it would otherwise raise `KeyError: 'worker'`,
    which says the same thing far less legibly.
    """
    assert "worker" in services, (
        "no `worker` service is declared in docker-compose.yml; services: "
        f"{list(services)}"
    )
    return dict(services["worker"])


def _service_networks(service: dict[str, Any]) -> list[str]:
    declared = service.get("networks") or []
    if isinstance(declared, dict):
        return list(declared)
    return list(declared)


def _is_external(networks: dict[str, Any], name: str) -> bool:
    definition = networks.get(name) or {}
    return bool(definition.get("external", False))


# --------------------------------------------------------------------------
# deploy-pipeline: Compose File Provisions a Persistent, Network-Isolated
# Postgres Service
# --------------------------------------------------------------------------


def test_postgres_data_is_stored_in_a_named_volume(
    compose: dict[str, Any], services: dict[str, Any]
) -> None:
    """Scenario: Postgres data survives a redeploy.

    SPECIFIED: "a Postgres service whose data is stored in a named Docker
    volume, so that data persists across the host's
    `docker compose pull && up -d` deploy cycle".

    What is asserted is the declaration the outcome rests on. The
    redeploy itself is uncovered here and recorded as such in the
    manifest -- it is deploy-time verification, not a unit test.
    """
    volumes = services["postgres"].get("volumes") or []
    named = [
        entry.split(":")[0]
        for entry in volumes
        if isinstance(entry, str) and ":" in entry
    ]

    declared = compose.get("volumes") or {}
    assert any(name in declared for name in named), (
        "the postgres service's data is not stored in a volume this "
        f"compose file declares by name; mounts: {volumes}, declared "
        f"volumes: {list(declared)}"
    )


def test_postgres_is_not_on_the_network_app_receives_public_traffic_on(
    services: dict[str, Any], networks: dict[str, Any]
) -> None:
    """Scenario: Postgres is unreachable from the public-facing network.

    WHEN the compose file's networks are inspected
    THEN the Postgres service SHALL NOT be a member of the network the
    `app` service uses for its Traefik-routed public traffic.

    The public-facing network is identified as the external network `app`
    joins, rather than by transcribing its name: an external network is
    exactly the one "an external network can be joined by services this
    application does not define" refers to, and it is the one Traefik
    itself is on.
    """
    app_networks = _service_networks(services["app"])
    public = [name for name in app_networks if _is_external(networks, name)]
    assert public, (
        "the `app` service joins no external network, so this test can no "
        f"longer identify the public-facing one; app networks: {app_networks}"
    )

    postgres_networks = _service_networks(services["postgres"])

    assert not set(public) & set(postgres_networks), (
        "the postgres service is a member of the public-facing network "
        f"{public}; postgres networks: {postgres_networks}"
    )


def test_the_network_postgres_is_on_is_not_external(
    services: dict[str, Any], networks: dict[str, Any]
) -> None:
    """Scenario: The network Postgres is reachable on is not external.

    WHEN the compose file's networks are inspected
    THEN the network Postgres is attached to SHALL NOT be declared
    external, so that only services this compose file defines can join it
    AND every service attached to it SHALL be a service of this
    application's own compose file.
    """
    postgres_networks = _service_networks(services["postgres"])
    assert postgres_networks, "the postgres service declares no network at all"

    for name in postgres_networks:
        assert name in networks, (
            f"the network {name!r} postgres is attached to is not declared "
            "in this compose file"
        )
        assert not _is_external(networks, name), (
            f"the network {name!r} postgres is attached to is declared "
            "external, so services this compose file does not define can "
            "join it"
        )

    # The second clause: every service on that network is one this file
    # defines. True by construction for a non-external network, and
    # asserted so that a later `external: true` fails here with the reason
    # rather than only above.
    attached = [
        service_name
        for service_name, service in services.items()
        if set(_service_networks(service)) & set(postgres_networks)
    ]
    assert set(attached) <= set(services), (
        f"services attached to postgres' network are not all defined here: {attached}"
    )


# --------------------------------------------------------------------------
# scheduled-jobs: A Worker Failure Does Not Prevent The Application From
# Serving -- the compose-level half
# --------------------------------------------------------------------------


def test_the_worker_is_a_service_of_its_own(services: dict[str, Any]) -> None:
    """Scenario: HTTP is served while no worker is running.

    SPECIFIED: "The process running scheduled work SHALL be separate from
    the process serving HTTP requests, such that the failure or absence of
    the former does not stop the latter from serving." A worker declared
    as its own compose service is what makes its failure a separate
    container's failure.
    """
    assert "worker" in services, (
        "no `worker` service is declared, so scheduled work has no process "
        f"of its own; services: {list(services)}"
    )
    assert services["worker"].get("command") != services["app"].get("command"), (
        "the worker service runs the same command as `app`, so it is not "
        "running scheduled work"
    )


def test_the_application_service_does_not_depend_on_the_worker(
    services: dict[str, Any],
) -> None:
    """Scenario: HTTP is served while no worker is running.

    SPECIFIED: the absence of the worker does not stop HTTP being served.
    A `depends_on` from `app` to `worker` would make the serving container
    wait on -- or, with a health condition, refuse to start without -- the
    process whose absence this requirement says it must tolerate.
    """
    depends_on = services["app"].get("depends_on") or {}

    assert "worker" not in depends_on, (
        "the `app` service depends on `worker`, so the worker's absence "
        "would hold up serving HTTP"
    )


# --------------------------------------------------------------------------
# DERIVED: design.md's worker-service decisions and tasks.md 3.1-3.6.
# None of these is a `#### Scenario:` block; each traces to a recorded
# decision, and each is labelled here so it is reviewable as an invented
# constraint rather than a specified one.
# --------------------------------------------------------------------------


def test_the_cron_service_and_its_network_are_gone(
    services: dict[str, Any], networks: dict[str, Any]
) -> None:
    """DERIVED (tasks.md 3.1). The `cron` service is replaced, not kept
    alongside; `app_cron` goes with it, including `app`'s own membership
    of it -- which tasks.md 3.1 flags as a separate line whose omission
    leaves a stack that will not start.
    """
    assert "cron" not in services, "the retired `cron` service is still declared"
    assert "app_cron" not in networks, "the `app_cron` network is still declared"

    for name, service in services.items():
        assert "app_cron" not in _service_networks(service), (
            f"service {name!r} still joins the removed `app_cron` network"
        )


def test_the_worker_runs_the_same_image_as_the_application(
    worker: dict[str, Any], services: dict[str, Any]
) -> None:
    """DERIVED (design.md, "Same image because the worker imports the same
    application code, and a second image would let the two drift")."""
    assert worker.get("image") == services["app"].get("image")


def test_the_workers_inherited_http_healthcheck_is_disabled(
    worker: dict[str, Any],
) -> None:
    """DERIVED (tasks.md 3.3; design.md, "The image's `HEALTHCHECK` must
    be overridden").

    The image's healthcheck polls `http://localhost:8000/health`, which
    the worker does not serve, so an inherited healthcheck reports
    unhealthy for the worker's entire life.
    """
    healthcheck = worker.get("healthcheck")

    assert healthcheck is not None, (
        "the worker service does not override the image's HEALTHCHECK, so "
        "it will report unhealthy for its entire life"
    )
    assert healthcheck.get("disable") is True, (
        f"expected the worker's healthcheck to be disabled, got {healthcheck}"
    )


def test_the_worker_waits_for_both_postgres_and_the_migrating_app(
    worker: dict[str, Any],
) -> None:
    """DERIVED (tasks.md 3.4). `app` becomes healthy only after its
    `alembic upgrade head` completes, so the second condition is schema
    readiness -- what stops the worker crash-looping against a database
    with no runner schema on first deploy."""
    depends_on = worker.get("depends_on") or {}

    assert set(depends_on) >= {"postgres", "app"}, (
        f"the worker's depends_on is {depends_on}; both `postgres` and "
        "`app` must be waited on"
    )
    for name in ("postgres", "app"):
        assert depends_on[name].get("condition") == "service_healthy", (
            f"the worker waits on {name} without a health condition, so it "
            "may start before it is ready"
        )


def test_the_worker_has_no_public_http_surface(
    worker: dict[str, Any], networks: dict[str, Any]
) -> None:
    """DERIVED (design.md, "The worker joins `app_db` only -- no HTTP
    surface, so no `platform_edge`"). Also the compose-level restatement
    of `scheduled-jobs`' "Scheduled Work Is Not Reachable From Outside The
    Deployment": a worker on the public-facing network, or carrying
    Traefik labels, would be reachable from it."""
    worker_networks = _service_networks(worker)

    external = [name for name in worker_networks if _is_external(networks, name)]
    assert external == [], (
        f"the worker joins the external network(s) {external}, giving "
        "scheduled work a surface outside the deployment"
    )
    labels = worker.get("labels") or []
    assert not any("traefik" in str(label) for label in labels), (
        f"the worker carries Traefik labels: {labels}"
    )


@pytest.mark.parametrize("service_name", ("app", "worker"))
def test_the_schedule_reading_services_declare_their_timezone(
    service_name: str, services: dict[str, Any]
) -> None:
    """DERIVED (tasks.md 3.6; design.md, "`TZ` is set explicitly to UTC").

    Recorded by design.md as being for log timestamps rather than for
    scheduling -- the schedule's own timezone lives in code (tasks.md
    2.4), asserted in
    `tests/unit/products/infrastructure/driving/test_daily_digest_job.py`.
    This asserts the recorded decision is actually in the file, so "no
    `TZ` is set, and nothing records it either way" does not return.
    """
    environment = services[service_name].get("environment") or {}
    if isinstance(environment, list):
        environment = dict(
            entry.split("=", 1) for entry in environment if "=" in str(entry)
        )

    assert environment.get("TZ") == "UTC", (
        f"service {service_name!r} does not declare TZ=UTC; environment: {environment}"
    )


def test_the_members_of_the_network_postgres_is_on_are_this_applications_own(
    services: dict[str, Any], networks: dict[str, Any]
) -> None:
    """Scenario: The network Postgres is reachable on is not external.

    "... AND every service attached to it SHALL be a service of this
    application's own compose file."

    `test_the_network_postgres_is_on_is_not_external` above asserts the
    non-external half and that every attached service is one this file
    defines. This asserts *which* services those are, which is what
    tasks.md 5.15 asks for and what the clause is worth once a second
    service joins that network: `worker` needs Postgres (the runner's
    queue lives in the same database), and joining it must not have been
    achieved by putting `worker` somewhere else, or by widening the
    network to a service that has no business on it.

    SPECIFIED: the non-external requirement and the every-service clause.
    DERIVED: the membership set itself -- `app`, `postgres` and `worker`
    are the services tasks.md 3.2 and 3.4 put on that network, not a
    `#### Scenario:` block. A sixth service added later fails here on
    purpose: whether it belongs on Postgres' network is a decision, and
    this is where it gets made rather than assumed.
    """
    postgres_networks = _service_networks(services["postgres"])
    assert postgres_networks, "the postgres service declares no network at all"

    for name in postgres_networks:
        assert not _is_external(networks, name), (
            f"the network {name!r} postgres is attached to is declared "
            "external, so its membership is not this compose file's to state"
        )

        attached = {
            service_name
            for service_name, service in services.items()
            if name in _service_networks(service)
        }
        assert attached == {"app", "postgres", "worker"}, (
            f"the membership of {name!r} are {sorted(attached)}, not exactly "
            "the application, its database and its worker"
        )
