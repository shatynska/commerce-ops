"""Recorded state that cannot be read, and the cache that must not outlive
it.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Run Freshness Is Reportable Over HTTP" / Scenarios: Recorded state that
  cannot be read is not reported as healthy; A recent healthy answer is not
  repeated once the state cannot be read; A repeated request still anchors
  work that has no first-known time

See `test-manifest.md` at the change root for the full accounting.

## The two ways recorded state becomes unreadable

tasks.md 5.8, 5.8a and 5.8b name three, failing by two different
mechanisms, and tasks.md 6.22 requires both to be covered:

- an **absent or malformed connection setting**, which `database-session`'s
  published requirement "An Absent Or Malformed Connection Setting Is
  Reported At The Point Of Use" raises *immediately* -- an implementation
  catching only connection and timeout errors returns 500 where the spec
  requires 503. Both are covered here, in this tier, because neither
  performs any I/O: the engine is never constructed.
- an **unreachable database**, including one that accepts connections and
  never answers. That reaches the network, so it is
  `tests/integration/shared/test_scheduled_runs_freshness_unreachable.py`
  under `AGENTS.md`'s tiering -- which needs no configured Postgres and is
  not skipped, since it supplies its own unreachable address.

## The cache, and why it is exempt from the anchor upsert

design.md is emphatic that the per-request anchor upsert is not an
optimisation waiting to be removed: it is the only database access a
cache-hit request still makes, and therefore the only way such a request
can discover that recorded state has become unreadable. Memoising it away
would leave a cache hit doing no I/O at all, and the endpoint would serve
its last healthy answer through the first seconds of an outage. Two of the
three scenarios here are that exemption.

## Seams, and the cache-name hazard

The route module is reached the way
`test_scheduled_runs_freshness.py` reaches it, and the same by-name
collaborator assumption applies. `CACHE_SECONDS` is substituted with
`raising=False` throughout: the assertions below hold whether or not a
cache exists, and `test_a_repeated_request_is_not_re_evaluated` covers the
cache's existence by counting reads rather than by naming anything. If the
cache is implemented under a different name, `CACHE_SECONDS` is the single
correction point -- and until it is corrected a cached answer can leak
from one test to the next, which shows up as a read count of zero rather
than as a silent pass.

At the time this pass was written neither the route nor the registry
exists, so every test here is expected to fail on an absent target.
"""

from __future__ import annotations

import dataclasses
import datetime
import sys
import time
from collections.abc import Iterable, Iterator, Mapping
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient

import commerce_ops.main as main_module
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven import database

FRESHNESS_PATH = "/health/scheduled-runs"

# How long "within a bounded time" is taken to mean in this tier. Not a
# figure any artifact fixes -- design.md says only "a short timeout" and
# "promptly". Generous by two orders of magnitude over anything an
# implementation would choose, because what this asserts is the difference
# between answering and hanging, not a latency budget.
BOUNDED_SECONDS = 15.0

SEAM_MESSAGE = (
    "the freshness route's module {module} exposes no module-level name "
    "{name!r}, so a test cannot substitute it. See "
    "test_scheduled_runs_freshness.py's docstring and test-manifest.md's "
    "unresolved project questions."
)

register_all()

_NOW = datetime.datetime.now(datetime.UTC)
# Every time in this module is an offset from this reference, so it has to
# be the same "now" the implementation reads. Pinning it to a fixed past
# date made every offset stale the moment the clock moved past it: work
# placed "10 minutes ago" was really two days ago, and scenarios written
# as within-tolerance evaluated as overdue. No collaborator substitutes a
# clock, so the reference must be the real one.
DIGEST_ID = "products.monitoring.daily"
LIVENESS_ID = "shared.scheduled-runs.overdue-check"


@dataclasses.dataclass(frozen=True)
class _Registration:
    identifier: str
    task_name: str
    schedule: str
    tolerance: datetime.timedelta


class _ReadableState:
    def __init__(self) -> None:
        self.registry = {
            DIGEST_ID: _Registration(
                DIGEST_ID, DIGEST_ID, "0 6 * * *", datetime.timedelta(hours=30)
            ),
            LIVENESS_ID: _Registration(
                LIVENESS_ID, LIVENESS_ID, "0 * * * *", datetime.timedelta(hours=4)
            ),
        }
        self.first_known: dict[str, datetime.datetime] = {}
        self.anchored: list[list[str]] = []
        self.reads = 0
        self.anchor_failure: Exception | None = None

    def registered_work(self) -> Mapping[str, _Registration]:
        return self.registry

    async def last_successful_run(self, name: str) -> datetime.datetime | None:
        self.reads += 1
        return _NOW - datetime.timedelta(minutes=5)

    async def first_known_times(self) -> Mapping[str, datetime.datetime]:
        self.reads += 1
        return dict(self.first_known)

    async def record_first_known(self, identifiers: Iterable[str]) -> None:
        if self.anchor_failure is not None:
            raise self.anchor_failure
        recorded = list(identifiers)
        self.anchored.append(recorded)
        for identifier in recorded:
            self.first_known.setdefault(identifier, _NOW)


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


def _route_module() -> ModuleType:
    matching = [
        route
        for route in _app_routes(main_module.app)
        if getattr(route, "path", None) == FRESHNESS_PATH
    ]
    assert len(matching) == 1, (
        f"expected exactly one route at {FRESHNESS_PATH} on "
        "commerce_ops.main.app; tasks.md 5.2 requires its router to be "
        "registered in main.py. Registered paths: "
        f"{sorted(getattr(route, 'path', '?') for route in _app_routes(main_module.app))}"
    )
    # `endpoint` is an APIRoute attribute, absent from the `BaseRoute`
    # type the routes list is declared as -- read reflectively rather
    # than by narrowing to a FastAPI-internal class.
    endpoint = getattr(matching[0], "endpoint", None)
    assert endpoint is not None, (
        f"the route at {FRESHNESS_PATH} carries no endpoint function"
    )
    return sys.modules[endpoint.__module__]


def _substitute(
    monkeypatch: pytest.MonkeyPatch, name: str, value: Any, *, required: bool = True
) -> None:
    module = _route_module()
    if not hasattr(module, name):
        if not required:
            return
        pytest.fail(SEAM_MESSAGE.format(module=module.__name__, name=name))
    monkeypatch.setattr(module, name, value, raising=required)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(main_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def readable(monkeypatch: pytest.MonkeyPatch) -> _ReadableState:
    """A route whose recorded state reads successfully, with a cache window
    wide enough that a second request inside the same test is a hit."""
    state = _ReadableState()
    _substitute(monkeypatch, "registered_work", state.registered_work)
    _substitute(monkeypatch, "last_successful_run", state.last_successful_run)
    _substitute(monkeypatch, "first_known_times", state.first_known_times)
    _substitute(monkeypatch, "record_first_known", state.record_first_known)
    _substitute(monkeypatch, "CACHE_SECONDS", 60, required=False)
    # Start every test from a cold cache. The window above is deliberately
    # wide enough for a second request inside one test to be a hit, which
    # also makes it wide enough for the *previous* test's entry to serve this
    # test's first request -- so each test would measure the one before it.
    # `monkeypatch` restores the attribute afterwards; this isolates module
    # state rather than changing what any test asserts.
    monkeypatch.setattr(_route_module(), "_cache", None, raising=False)
    return state


@pytest.fixture(autouse=True)
def _no_engine_left_over() -> Iterator[None]:
    """Test infrastructure, not the subject of any requirement.

    `database` caches one engine per process behind an `lru_cache`. The
    two unreadable-setting tests below assert on what happens when the
    setting is absent or malformed, which is only reached while no engine
    has already been built from a valid one.
    """
    database._get_engine_and_session_factory.cache_clear()
    yield
    database._get_engine_and_session_factory.cache_clear()


def _body(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:  # pragma: no cover - diagnostics only
        pytest.fail(
            f"the response is not JSON at all: {response.status_code} {response.text!r}"
        )


def _assert_unhealthy_and_empty(response: Any, *, elapsed: float, how: str) -> None:
    """The whole of "Recorded state that cannot be read is not reported as
    healthy", asserted the same way for each mechanism."""
    assert response.status_code == 503, (
        f"with the recorded state unreadable ({how}) the endpoint answered "
        f"{response.status_code}, not 503. A monitor cannot tell this from "
        "overdue work, which is correct -- both mean the deployment cannot "
        "demonstrate that its scheduled work is happening. Body: "
        f"{response.text!r}"
    )
    body = _body(response)
    assert body.get("status") == "unhealthy", (
        f"the body does not report an unhealthy state ({how}): {body!r}"
    )
    assert body.get("work") == [], (
        "the response reports work while the state it would have been "
        f"computed from is unreadable ({how}); the empty array is what "
        f"tells a human which of the two cases this is: {body!r}"
    )
    assert elapsed < BOUNDED_SECONDS, (
        f"the endpoint took {elapsed:.1f}s to answer with the state "
        f"unreadable ({how}); it must respond within a bounded time rather "
        "than waiting indefinitely, on the one endpoint whose whole purpose "
        "is to be polled by something that concludes nothing from a request "
        "that never returns"
    )


# --------------------------------------------------------------------------
# Requirement: Run Freshness Is Reportable Over HTTP
# --------------------------------------------------------------------------


def test_an_absent_connection_setting_is_not_reported_as_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Recorded state that cannot be read is not reported as
    healthy -- the absent-setting mechanism.

    WHEN the freshness endpoint is requested and the recorded state cannot
    be read
    THEN the system SHALL indicate an unhealthy state in a way an automated
    checker can act on without parsing prose
    AND SHALL NOT report any piece of work as being within its tolerance
    AND SHALL respond within a bounded time rather than waiting
    indefinitely on the unreadable state.

    SPECIFIED. Nothing is substituted here: the endpoint reads the real
    registry through its real accessors, and `DATABASE_URL` is absent.
    `database-session`'s "An Absent Or Malformed Connection Setting Is
    Reported At The Point Of Use" raises immediately rather than by
    expiry, so this fails by a different mechanism from an unreachable
    database -- tasks.md 5.8b's point, and an implementation catching only
    connection and timeout errors returns 500 here.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    started = time.monotonic()
    response = client.get(FRESHNESS_PATH)
    elapsed = time.monotonic() - started

    _assert_unhealthy_and_empty(response, elapsed=elapsed, how="DATABASE_URL absent")


def test_a_malformed_connection_setting_is_not_reported_as_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Recorded state that cannot be read is not reported as
    healthy -- the malformed-setting mechanism.

    SPECIFIED, from the same scenario and tasks.md 5.8b, which names
    "absent **or** malformed". A malformed value fails inside the URL
    validation rather than at the environment read, so an implementation
    that handled only the absent case would pass the test above and fail
    here.
    """
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")

    started = time.monotonic()
    response = client.get(FRESHNESS_PATH)
    elapsed = time.monotonic() - started

    _assert_unhealthy_and_empty(response, elapsed=elapsed, how="DATABASE_URL malformed")


def test_a_recent_healthy_answer_is_not_repeated_once_the_state_cannot_be_read(
    client: TestClient, readable: _ReadableState
) -> None:
    """Scenario: A recent healthy answer is not repeated once the state
    cannot be read.

    WHEN the freshness endpoint has recently reported a healthy state and
    the recorded state then becomes unreadable, including where that
    earlier answer is still recent enough that the system need not
    re-evaluate it
    THEN the system SHALL indicate an unhealthy state, rather than
    repeating the earlier healthy answer.

    SPECIFIED, and the mechanism is exactly the one design.md names: the
    second request is inside the cache window, so the anchor upsert is the
    only database access it makes -- and therefore the only way it can
    discover the outage. An implementation that memoised the upsert away,
    or that cached the response without letting the upsert's failure
    override it, serves its last healthy answer through the first seconds
    of an outage and fails here.
    """
    first = client.get(FRESHNESS_PATH)
    assert first.status_code == 200 and first.json()["status"] == "ok", (
        f"the first request did not report healthy: {first.status_code} {first.text}"
    )

    readable.anchor_failure = RuntimeError(
        "DATABASE_URL is not set (or is set but empty); the application "
        "cannot obtain a database session without it"
    )

    started = time.monotonic()
    second = client.get(FRESHNESS_PATH)
    elapsed = time.monotonic() - started

    _assert_unhealthy_and_empty(
        second, elapsed=elapsed, how="unreadable immediately after a healthy answer"
    )


def test_a_repeated_request_still_anchors_every_registered_piece_of_work(
    client: TestClient, readable: _ReadableState
) -> None:
    """Scenario: A repeated request still anchors work that has no
    first-known time.

    WHEN the freshness endpoint is requested, and requested again soon
    enough that it need not re-evaluate
    THEN the system SHALL perform the first-known recording for every
    registered piece of recurring work on the repeated request regardless,
    rather than serving a previously computed answer without having done so
    AND SHALL record a time for any registered piece of work that has none
    at that moment.

    SPECIFIED. The first clause is asserted here -- the upsert runs on the
    repeated request, for every registered piece of work. The second
    clause's *effect* -- that a work lacking an anchor at that moment gets
    one -- cannot be observed against an in-memory double that has already
    anchored everything on the first request, which is exactly the
    vacuousness tasks.md 6.24 warns about. That half is asserted in
    `tests/integration/shared/test_scheduled_runs_freshness_cache.py`,
    where the anchor row is deleted between the two requests.
    """
    client.get(FRESHNESS_PATH)
    client.get(FRESHNESS_PATH)

    assert len(readable.anchored) == 2, (
        "the anchor upsert did not run on both requests: it ran "
        f"{len(readable.anchored)} time(s). The cache short-circuits the "
        "evaluation, never the upsert -- the upsert is the only database "
        "access a cache-hit request makes"
    )
    for attempt in readable.anchored:
        assert set(attempt) == {DIGEST_ID, LIVENESS_ID}, (
            f"a request anchored only some of the registered work: {attempt!r}"
        )


def test_a_repeated_request_is_not_re_evaluated(
    client: TestClient, readable: _ReadableState
) -> None:
    """SPECIFIED by tasks.md 5.7, and the precondition the two scenarios
    above are stated under ("requested again soon enough that it need not
    re-evaluate").

    Not itself a `#### Scenario:` block. It is here because without a
    cache those two scenarios hold vacuously -- every request would
    re-evaluate, so of course the upsert runs -- and the endpoint is
    unauthenticated on an internet-facing service that, unlike `/health`,
    touches the database on every anonymous request.

    Counted rather than named: this asserts that the recorded state is not
    re-read, which holds however the cache is implemented.
    """
    client.get(FRESHNESS_PATH)
    reads_after_first = readable.reads
    assert reads_after_first > 0, (
        "the first request read no recorded state at all, which means it "
        "was served from a cache entry left behind by another test. See "
        "this file's docstring: CACHE_SECONDS is the correction point"
    )

    client.get(FRESHNESS_PATH)

    assert readable.reads == reads_after_first, (
        "a second request inside the cache window re-read the recorded "
        f"state ({reads_after_first} reads, then {readable.reads}); "
        "tasks.md 5.7 requires repeated anonymous requests to cost one "
        "evaluation rather than one each"
    )
