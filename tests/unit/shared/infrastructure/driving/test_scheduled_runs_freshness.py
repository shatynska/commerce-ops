"""Run freshness, reported over HTTP for a checker outside the deployment.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Run Freshness Is Reportable Over HTTP" / Scenarios: Freshness is
  reported; Unhealthy is signalled so an automated checker can act on it;
  Freshness is reported while no worker is running; A freshly deployed
  system reports healthy; The endpoint does not consult the process running
  scheduled work
- "Overdue Work Is Reported To Slack From Inside The Deployment" /
  Scenario: Overdueness during an absent worker remains visible
- "The Process Running Scheduled Work Is Itself Monitored Work" / Scenario:
  The freshness interface is unaffected by a reporting-channel outage
- "Work Is Overdue Relative To Its Last Success Or To When It Was First
  Known" / Scenario: A worker that never started still produces an anchor

Recorded state that cannot be read, and the cache that must not outlive it,
are in `test_scheduled_runs_freshness_unreadable.py`. See
`test-manifest.md` at the change root for the full accounting.

## What is not invented

The path `/health/scheduled-runs` (design.md and tasks.md 5.1); the
response's fixed JSON shape -- `status`, and a `work` array sorted by `id`
whose entries carry `id`, `last_success`, `tolerance_seconds` and
`overdue` (design.md, "The freshness response is a fixed JSON shape");
200 healthy and 503 when any work is overdue (design.md and tasks.md 5.4).
`commerce_ops.registrations.register_all` is fixed by tasks.md 1.3, and
`commerce_ops.main` is where tasks.md 5.2 requires the router registered
-- the endpoint is reached here only through `main.app`, so a router that
was never registered fails here rather than at deploy time.

## What is invented: the route module's seams

The route module itself is never named. It is reached through
`main.app.routes` -- the one route whose path is `/health/scheduled-runs`
-- and then through its endpoint function's `__module__`. What is assumed
is that it reaches its collaborators by the same by-name import pattern
the rest of this project's driving adapters use, under these names:

- `registered_work()` (sync), `last_successful_run(name)` (async),
  `first_known_times()` (async), `record_first_known(identifiers)` (async)
- `CACHE_SECONDS` -- the brief response cache of tasks.md 5.7, set to zero
  here so one test's answer cannot be served to the next. Substituted with
  `raising=False`: an implementation with no cache at all has nothing to
  disable, which is fine, but one whose cache is named otherwise will
  produce puzzling cross-test staleness. This is the correction point for
  that.

`_substitute` fails with an instructive message rather than an
`AttributeError` when a name is absent. Correcting these names is a
fixture correction; the assertions below are about the response.

At the time this pass was written neither the route nor the registry
exists, so every test here is expected to fail on an absent target until
tasks 1.1, 1.3, 5.1, 5.2 and 5.3 land.
"""

from __future__ import annotations

import dataclasses
import datetime
import os
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

import commerce_ops.briefing.infrastructure.driven.slack_notifier as briefing_slack_notifier
import commerce_ops.main as main_module
from commerce_ops.registrations import register_all

FRESHNESS_PATH = "/health/scheduled-runs"
WORKER_MODULE = "commerce_ops.worker"

SEAM_MESSAGE = (
    "the freshness route's module {module} exposes no module-level name "
    "{name!r}, so a test cannot substitute it. This file assumes the "
    "by-name collaborator pattern this project's driving adapters already "
    "use; see the docstring and test-manifest.md's unresolved project "
    "questions. Correcting the name is a fixture correction."
)

register_all()

_NOW = datetime.datetime.now(datetime.UTC)
# Every time in this module is an offset from this reference, so it has to
# be the same "now" the implementation reads. Pinning it to a fixed past
# date made every offset stale the moment the clock moved past it: work
# placed "10 minutes ago" was really two days ago, and scenarios written
# as within-tolerance evaluated as overdue. No collaborator substitutes a
# clock, so the reference must be the real one.
TOLERANCE = datetime.timedelta(hours=4)

DIGEST_ID = "products.monitoring.daily"
LIVENESS_ID = "shared.scheduled-runs.overdue-check"


# --------------------------------------------------------------------------
# Reaching the route
# --------------------------------------------------------------------------


def _app_routes(app: Any) -> list[Any]:
    """Every route registered on the application, flattened.

    FastAPI 0.141 wraps each `include_router` in an `_IncludedRouter` that
    carries no `path` of its own, so a flat scan of `app.routes` finds only
    the built-in docs routes and would report a correctly registered router
    as missing. The underlying `APIRouter` is `original_router`.

    This is a fixture correction, not a weakening: what is asserted is still
    that exactly one route answers at the path, reached through the
    application object rather than by importing the module directly.
    """
    routes: list[Any] = []
    for entry in app.routes:
        original = getattr(entry, "original_router", None)
        if original is not None:
            routes.extend(original.routes)
        else:
            routes.append(entry)
    return routes


def _freshness_route() -> Any:
    matching = [
        route
        for route in _app_routes(main_module.app)
        if getattr(route, "path", None) == FRESHNESS_PATH
    ]
    assert len(matching) == 1, (
        f"expected exactly one route at {FRESHNESS_PATH} on commerce_ops."
        f"main.app, found {len(matching)}. tasks.md 5.2 requires the "
        "router to be registered in main.py -- a green unit suite does not "
        "catch an unregistered router, which is why the endpoint is reached "
        "only through the application object here. Registered paths: "
        f"{sorted(getattr(route, 'path', '?') for route in _app_routes(main_module.app))}"
    )
    return matching[0]


def _route_module() -> ModuleType:
    return sys.modules[_freshness_route().endpoint.__module__]


def _substitute(
    monkeypatch: pytest.MonkeyPatch, name: str, value: Any, *, required: bool = True
) -> None:
    module = _route_module()
    if not hasattr(module, name):
        if not required:
            return
        pytest.fail(SEAM_MESSAGE.format(module=module.__name__, name=name))
    monkeypatch.setattr(module, name, value, raising=required)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Registration:
    identifier: str
    task_name: str
    schedule: str
    tolerance: datetime.timedelta


class _RecordedState:
    """The recorded state the endpoint reads, held in memory.

    The endpoint's real reads go to Postgres; this tier is I/O-free by
    `AGENTS.md`'s testing strategy, and the durable half is covered in
    `tests/integration/shared/`.
    """

    def __init__(
        self,
        *,
        registry: Mapping[str, _Registration],
        last_success: Mapping[str, datetime.datetime] | None = None,
        first_known: Mapping[str, datetime.datetime] | None = None,
    ) -> None:
        self.registry = dict(registry)
        self.last_success = dict(last_success or {})
        self.first_known = dict(first_known or {})
        self.anchored: list[list[str]] = []

    def registered_work(self) -> Mapping[str, _Registration]:
        return self.registry

    async def last_successful_run(self, name: str) -> datetime.datetime | None:
        return self.last_success.get(name)

    async def first_known_times(self) -> Mapping[str, datetime.datetime]:
        return dict(self.first_known)

    async def record_first_known(self, identifiers: Iterable[str]) -> None:
        recorded = list(identifiers)
        self.anchored.append(recorded)
        for identifier in recorded:
            self.first_known.setdefault(identifier, _NOW)


def _two_pieces_of_work(
    *,
    last_success: Mapping[str, datetime.datetime] | None = None,
    first_known: Mapping[str, datetime.datetime] | None = None,
) -> _RecordedState:
    return _RecordedState(
        registry={
            DIGEST_ID: _Registration(
                DIGEST_ID, DIGEST_ID, "0 6 * * *", datetime.timedelta(hours=30)
            ),
            LIVENESS_ID: _Registration(
                LIVENESS_ID, LIVENESS_ID, "0 * * * *", TOLERANCE
            ),
        },
        last_success=last_success,
        first_known=first_known,
    )


@pytest.fixture()
def client() -> Iterator[TestClient]:
    # `raise_server_exceptions=False` so a handler that fails instead of
    # answering is observed as a status code, which is what the scenarios
    # are stated in terms of, rather than as an exception escaping the
    # client.
    with TestClient(main_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def install(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _install(state: _RecordedState) -> _RecordedState:
        _substitute(monkeypatch, "registered_work", state.registered_work)
        _substitute(monkeypatch, "last_successful_run", state.last_successful_run)
        _substitute(monkeypatch, "first_known_times", state.first_known_times)
        _substitute(monkeypatch, "record_first_known", state.record_first_known)
        # Zero so that one test's cached answer is never served to the next.
        _substitute(monkeypatch, "CACHE_SECONDS", 0, required=False)
        return state

    return _install


# --------------------------------------------------------------------------
# Shape helpers
# --------------------------------------------------------------------------


def _entries(body: Any) -> list[dict[str, Any]]:
    assert isinstance(body, dict), f"the response body is not an object: {body!r}"
    assert "work" in body, f"the response carries no `work` array: {body!r}"
    work = body["work"]
    assert isinstance(work, list), f"`work` is not an array: {work!r}"
    return work


def _by_id(body: Any) -> dict[str, dict[str, Any]]:
    return {entry["id"]: entry for entry in _entries(body)}


# --------------------------------------------------------------------------
# Requirement: Run Freshness Is Reportable Over HTTP
# --------------------------------------------------------------------------


def test_freshness_is_reported_for_each_piece_of_recurring_work(
    client: TestClient, install: Any
) -> None:
    """Scenario: Freshness is reported.

    WHEN the freshness endpoint is requested
    THEN the system SHALL report, for each piece of recurring work, when it
    last succeeded or that it has never succeeded.

    SPECIFIED, in the fixed shape design.md settles and tasks.md 6.11
    requires be asserted as a shape rather than as "the body mentions the
    identifiers": `id`, `last_success` (RFC 3339 UTC, or `null` where the
    work has never succeeded), `tolerance_seconds` and `overdue`, sorted by
    `id`, under a top-level `status`. `null` *is* how "never" is expressed
    -- not a sentinel string a checker would have to know about.
    """
    succeeded_at = _NOW - datetime.timedelta(minutes=30)
    install(_two_pieces_of_work(last_success={LIVENESS_ID: succeeded_at}))

    response = client.get(FRESHNESS_PATH)
    body = response.json()

    assert body.get("status") in {"ok", "unhealthy"}, (
        f"the response carries no top-level status of `ok` or `unhealthy`: {body!r}"
    )
    entries = _entries(body)
    assert [entry["id"] for entry in entries] == sorted(
        entry["id"] for entry in entries
    ), (
        f"the `work` array is not sorted by `id`, so two responses do not diff: {entries!r}"
    )
    assert {entry["id"] for entry in entries} == {DIGEST_ID, LIVENESS_ID}, (
        "the response does not carry exactly one entry per registered piece "
        f"of recurring work: {entries!r}"
    )
    for entry in entries:
        assert set(entry) == {"id", "last_success", "tolerance_seconds", "overdue"}, (
            f"a `work` entry is not the fixed shape design.md settles: {entry!r}"
        )
        assert isinstance(entry["overdue"], bool), (
            f"`overdue` is not a boolean, so a checker must interpret it: {entry!r}"
        )
        assert isinstance(entry["tolerance_seconds"], (int, float)), (
            f"`tolerance_seconds` is not a number: {entry!r}"
        )

    reported = _by_id(body)
    assert reported[DIGEST_ID]["last_success"] is None, (
        "work that has never succeeded is not reported with a null "
        f"last_success: {reported[DIGEST_ID]!r}"
    )
    parsed = datetime.datetime.fromisoformat(reported[LIVENESS_ID]["last_success"])
    assert parsed.utcoffset() == datetime.timedelta(0), (
        "last_success is not expressed in UTC: "
        f"{reported[LIVENESS_ID]['last_success']!r}"
    )
    assert parsed == succeeded_at, (
        "last_success is not the recorded time of the most recent "
        f"successful run: {reported[LIVENESS_ID]['last_success']!r}"
    )


def test_unhealthy_is_signalled_so_an_automated_checker_can_act_on_it(
    client: TestClient, install: Any
) -> None:
    """Scenario: Unhealthy is signalled so an automated checker can act on
    it.

    WHEN the freshness endpoint is requested and at least one piece of
    recurring work is overdue
    THEN the response SHALL indicate an unhealthy state in a way an
    automated checker can act on without parsing prose.

    SPECIFIED. tasks.md 6.12 requires the exact codes, since an uptime
    monitor is configured against them: 503, which such a monitor already
    treats as down, and `"status": "unhealthy"` in the body.
    """
    install(
        _two_pieces_of_work(
            last_success={
                DIGEST_ID: _NOW - datetime.timedelta(minutes=10),
                LIVENESS_ID: _NOW - TOLERANCE - datetime.timedelta(hours=1),
            }
        )
    )

    response = client.get(FRESHNESS_PATH)

    assert response.status_code == 503, (
        "work is overdue and the endpoint did not answer 503, so an "
        "off-the-shelf uptime monitor pointed at this URL would treat the "
        f"deployment as up: {response.status_code} {response.text}"
    )
    body = response.json()
    assert body["status"] == "unhealthy", (
        f"the body does not report an unhealthy state: {body!r}"
    )
    assert _by_id(body)[LIVENESS_ID]["overdue"] is True, (
        f"the overdue piece of work is not marked overdue: {body!r}"
    )


def test_nothing_overdue_answers_two_hundred_and_ok(
    client: TestClient, install: Any
) -> None:
    """Scenario: Unhealthy is signalled so an automated checker can act on
    it -- the healthy half, and the other exact code tasks.md 6.12 names.

    SPECIFIED. Without this, an implementation answering 503 unconditionally
    would satisfy the unhealthy scenario while making the endpoint useless.
    """
    install(
        _two_pieces_of_work(
            last_success={
                DIGEST_ID: _NOW - datetime.timedelta(minutes=10),
                LIVENESS_ID: _NOW - datetime.timedelta(minutes=10),
            }
        )
    )

    response = client.get(FRESHNESS_PATH)

    assert response.status_code == 200, (
        f"nothing is overdue and the endpoint did not answer 200: "
        f"{response.status_code} {response.text}"
    )
    body = response.json()
    assert body["status"] == "ok", f"the body does not report a healthy state: {body!r}"
    assert all(entry["overdue"] is False for entry in _entries(body)), (
        f"a piece of work is marked overdue although none is: {body!r}"
    )


def test_freshness_is_reported_while_no_worker_is_running(
    client: TestClient, install: Any
) -> None:
    """Scenario: Freshness is reported while no worker is running.

    WHEN the freshness endpoint is requested and no process running
    scheduled work is available
    THEN the system SHALL respond, reporting the resulting overdueness,
    rather than failing or hanging.

    Also covers "Overdue Work Is Reported To Slack From Inside The
    Deployment" / Scenario: Overdueness during an absent worker remains
    visible -- whose whole content is that the overdueness arising while no
    worker is available is reported *by this interface*, the in-deployment
    check being unable to observe its own process's absence.

    SPECIFIED. The precondition is the ambient condition of every test
    process in this project: no worker exists here at all, which is
    precisely the deployment this endpoint was built for. The state
    reflects it -- the worker's own liveness evidence has gone stale
    because nothing is recording runs.
    """
    install(
        _two_pieces_of_work(
            last_success={LIVENESS_ID: _NOW - TOLERANCE - datetime.timedelta(hours=6)},
            first_known={DIGEST_ID: _NOW - datetime.timedelta(days=10)},
        )
    )

    response = client.get(FRESHNESS_PATH)

    assert response.status_code == 503, (
        "no worker is running and the work it should have run is overdue, "
        f"yet the endpoint reported healthy: {response.status_code} "
        f"{response.text}"
    )
    reported = _by_id(response.json())
    assert reported[LIVENESS_ID]["overdue"] is True, (
        "the worker's own liveness evidence is stale and the endpoint does "
        f"not report it overdue, so an absent worker stays invisible: {reported!r}"
    )
    assert reported[DIGEST_ID]["overdue"] is True, (
        "work that has never succeeded and has been known for far longer "
        f"than its tolerance is not reported overdue: {reported!r}"
    )


def test_a_freshly_deployed_system_reports_healthy(
    client: TestClient, install: Any
) -> None:
    """Scenario: A freshly deployed system reports healthy.

    WHEN the freshness endpoint is requested in a deployment where the
    recorded state is readable, no work has yet run, and no work's
    tolerance has elapsed since the system first knew of it
    THEN the system SHALL report each piece of work as never having
    succeeded
    AND SHALL indicate a healthy state, since nothing is yet overdue.

    SPECIFIED. A fresh deploy that alarms is an alarm nobody can act on,
    and it is what an implementation comparing "never succeeded" against
    the epoch produces on its first poll.
    """
    just_now = _NOW - datetime.timedelta(minutes=1)
    install(
        _two_pieces_of_work(first_known={DIGEST_ID: just_now, LIVENESS_ID: just_now})
    )

    response = client.get(FRESHNESS_PATH)

    assert response.status_code == 200, (
        "a freshly deployed system in which nothing has yet run reported "
        f"unhealthy: {response.status_code} {response.text}"
    )
    body = response.json()
    assert body["status"] == "ok", f"a fresh deployment is not healthy: {body!r}"
    for entry in _entries(body):
        assert entry["last_success"] is None, (
            f"work that has never run is not reported as never having "
            f"succeeded: {entry!r}"
        )
        assert entry["overdue"] is False, (
            f"work is overdue before its tolerance has elapsed since the "
            f"system first knew of it: {entry!r}"
        )


def test_a_request_anchors_every_registered_piece_of_work(
    client: TestClient, install: Any
) -> None:
    """Scenario: A worker that never started still produces an anchor.

    WHEN the freshness interface has served a request and the process
    running scheduled work has never started
    THEN each registered piece of work SHALL have a recorded first-known
    time
    AND SHALL become overdue once its tolerance has elapsed since that
    time.

    SPECIFIED. This is the scenario design.md calls the difference between
    the change working and not: if only the worker wrote the anchor, a
    worker that never started would leave every piece of work without one,
    the endpoint could compute no overdueness, and it would report healthy
    forever -- the precise failure this capability exists to expose,
    reintroduced by the mechanism meant to close it.

    That the anchor row survives in Postgres is the durable half, covered
    in `tests/integration/shared/test_known_work_anchor.py`.
    """
    state = install(_two_pieces_of_work())

    first = client.get(FRESHNESS_PATH)

    assert first.status_code == 200, (
        f"the first request did not answer healthy: {first.status_code} {first.text}"
    )
    assert state.anchored, (
        "serving a request recorded no first-known time for anything, so a "
        "deployment whose worker never starts acquires no anchor and "
        "reports healthy indefinitely"
    )
    assert set(state.anchored[0]) == {DIGEST_ID, LIVENESS_ID}, (
        "the request did not anchor every registered piece of work: "
        f"{state.anchored[0]!r}"
    )

    # ... AND SHALL become overdue once its tolerance has elapsed since
    # that time. The anchor the request wrote is aged past the tolerance.
    for identifier in state.first_known:
        state.first_known[identifier] = _NOW - datetime.timedelta(days=10)

    later = client.get(FRESHNESS_PATH)

    assert later.status_code == 503, (
        "work anchored by an earlier request, never run since, and past its "
        f"tolerance is not reported overdue: {later.status_code} {later.text}"
    )
    assert all(entry["overdue"] is True for entry in _entries(later.json())), (
        f"not every unrun, long-anchored piece of work is overdue: {later.json()!r}"
    )


def test_the_endpoint_does_not_consult_the_process_running_scheduled_work() -> None:
    """Scenario: The endpoint does not consult the process running
    scheduled work.

    WHEN the freshness endpoint serves a request
    THEN it SHALL NOT make any request to the process running scheduled
    work.

    SPECIFIED, asserted structurally in a fresh interpreter: the HTTP
    process must not so much as import the worker entry point, and there is
    nothing else it could consult -- the worker exposes no interface, no
    port and no route. An endpoint that reached the worker would have to
    reach it through that module.

    A fresh interpreter is required because `commerce_ops.worker` is
    already imported inside this pytest process by other test files, so an
    in-process check would assert nothing. The environment is built from
    scratch so no configuration on the developer's machine satisfies an
    import-time read.

    `tests/unit/test_http_serves_without_a_worker.py` asserts the same
    structural fact for a different requirement of a different change. It
    is not modified, extended or relied upon here: this change adds the
    route module and `registrations.py` to `main.py`'s import graph, and
    this scenario is about what *this* endpoint consults.
    """
    script = (
        "import sys\n"
        "import commerce_ops.main\n"
        # Flattened the same way as `_app_routes` above: FastAPI 0.141 wraps
        # each included router, so a flat scan finds only the docs routes.
        "routes = [\n"
        "    sub\n"
        "    for entry in commerce_ops.main.app.routes\n"
        "    for sub in (\n"
        "        getattr(entry, 'original_router').routes\n"
        "        if getattr(entry, 'original_router', None) is not None\n"
        "        else [entry]\n"
        "    )\n"
        "]\n"
        "paths = sorted(getattr(r, 'path', '?') for r in routes)\n"
        f"assert {FRESHNESS_PATH!r} in paths, paths\n"
        f"print({WORKER_MODULE!r} in sys.modules)\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env={"PATH": os.environ.get("PATH", "")},
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "importing commerce_ops.main in a fresh interpreter failed, or it "
        f"serves no route at {FRESHNESS_PATH}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stdout.strip().splitlines()[-1] == "False", (
        "the process serving the freshness endpoint imports "
        f"{WORKER_MODULE}; the endpoint exists to report on that process "
        "without depending on it, and its absence is the condition it "
        "makes visible"
    )


# --------------------------------------------------------------------------
# Requirement: The Process Running Scheduled Work Is Itself Monitored Work
# --------------------------------------------------------------------------


def test_the_freshness_interface_is_unaffected_by_a_reporting_channel_outage(
    client: TestClient, install: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: The freshness interface is unaffected by a
    reporting-channel outage.

    WHEN the reporting channel is unavailable and the process running
    scheduled work is running normally
    THEN the freshness interface SHALL NOT report that process as absent.

    SPECIFIED. The state is the one a Slack outage produces given the
    other half of this requirement (asserted in `test_overdue_check.py`):
    the check completed its evaluation and recorded a successful run even
    though delivery failed, so its liveness evidence is fresh. The
    endpoint must report the worker present.

    The channel is made unavailable as well as the state being set, so an
    implementation that reached for Slack while serving this request --
    making the Slack-independent endpoint Slack-dependent, which design.md
    claims it is not -- fails here rather than passing on state alone.
    """

    async def _unavailable(message: str) -> None:
        raise RuntimeError("slack is unreachable")

    monkeypatch.setattr(
        briefing_slack_notifier, "post_monitoring_message", _unavailable
    )
    install(
        _two_pieces_of_work(
            last_success={
                LIVENESS_ID: _NOW - datetime.timedelta(minutes=5),
                DIGEST_ID: _NOW - datetime.timedelta(minutes=5),
            }
        )
    )

    response = client.get(FRESHNESS_PATH)

    assert response.status_code == 200, (
        "the reporting channel is down but the worker is running normally, "
        f"and the endpoint reported unhealthy: {response.status_code} "
        f"{response.text}"
    )
    assert _by_id(response.json())[LIVENESS_ID]["overdue"] is False, (
        "the worker's liveness evidence is fresh and the endpoint reports "
        f"the process absent anyway: {response.json()!r}"
    )
