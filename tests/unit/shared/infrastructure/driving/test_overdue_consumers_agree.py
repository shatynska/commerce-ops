"""The check and the freshness endpoint reach the same verdict.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Each Piece Of Recurring Work Declares Its Schedule And Tolerance In One
  Place" / Scenario: Every consumer reads the same declaration

See `test-manifest.md` at the change root for the full accounting.

## Why the registry here is the real one

tasks.md 6.15 is explicit: the two consumers must be compared "reading the
registry populated by `registrations.py` -- not an ad-hoc registry built in
the test". That is the whole content of the scenario. Two consumers given
the same fake tolerances would agree by construction; what the requirement
forbids is two consumers holding different opinions about the *declared*
tolerance, and only the real declaration can establish that.

So the registry is left alone here. What is substituted is the recorded
state both consumers read -- the last-success times and the anchors -- so
that the same facts reach both, and the verdicts can be compared at all.
The state is built from the real registrations' own tolerances rather than
from transcribed figures, so this file pins none of design.md's Open
Questions figures.

The seam names are the same ones
`test_overdue_check.py` and `test_scheduled_runs_freshness.py` record as
this pass's largest invented surface; see either file's docstring and
test-manifest.md.
"""

from __future__ import annotations

import datetime
import inspect
import sys
import time
from collections.abc import Iterable, Iterator, Mapping
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from procrastinate import job_context, jobs

import commerce_ops.main as main_module
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app
from commerce_ops.shared.infrastructure.driven.recurring_work import registered_work

pytestmark = pytest.mark.anyio

FRESHNESS_PATH = "/health/scheduled-runs"
OVERDUE_CHECK_PACKAGE = "commerce_ops.shared.infrastructure.driving"

SEAM_MESSAGE = (
    "{module} exposes no module-level name {name!r}, so a test cannot "
    "substitute it. See test_overdue_check.py's SEAM CONTRACT docstring "
    "and test-manifest.md's unresolved project questions."
)

register_all()

_NOW = datetime.datetime.now(datetime.UTC)
# Every time in this module is an offset from this reference, so it has to
# be the same "now" the implementation reads. Pinning it to a fixed past
# date made every offset stale the moment the clock moved past it: work
# placed "10 minutes ago" was really two days ago, and scenarios written
# as within-tolerance evaluated as overdue. No collaborator substitutes a
# clock, so the reference must be the real one.


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# Reaching both consumers
# --------------------------------------------------------------------------


def _registrations() -> list[Any]:
    declared = registered_work()
    if hasattr(declared, "values"):
        return list(declared.values())
    return list(declared)


def _names(entry: Any) -> set[str]:
    return {
        str(getattr(entry, attribute))
        for attribute in ("identifier", "id", "task_name", "name")
        if getattr(entry, attribute, None) is not None
    }


def _tolerance(entry: Any) -> datetime.timedelta:
    value = getattr(entry, "tolerance", None)
    if isinstance(value, datetime.timedelta):
        return value
    seconds = getattr(entry, "tolerance_seconds", value)
    assert isinstance(seconds, (int, float)), (
        f"no readable tolerance on registration {entry!r}"
    )
    return datetime.timedelta(seconds=float(seconds))


def _check_periodic() -> Any:
    matching = [
        entry
        for entry in runner_app.periodic_registry.periodic_tasks.values()
        if entry.task.func.__module__.startswith(OVERDUE_CHECK_PACKAGE)
    ]
    assert len(matching) == 1, (
        f"expected exactly one scheduled job under {OVERDUE_CHECK_PACKAGE!r} "
        "(tasks.md 4.1)"
    )
    return matching[0]


def _check_module() -> ModuleType:
    return sys.modules[_check_periodic().task.func.__module__]


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
        f"expected exactly one route at {FRESHNESS_PATH} on commerce_ops.main.app"
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
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, name: str, value: Any
) -> None:
    if not hasattr(module, name):
        pytest.fail(SEAM_MESSAGE.format(module=module.__name__, name=name))
    monkeypatch.setattr(module, name, value)


async def _run_check() -> None:
    entry = _check_periodic()
    task = entry.task
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=runner_app,
                job=jobs.Job(
                    id=1,
                    queue=task.queue,
                    lock=task.lock,
                    queueing_lock=task.queueing_lock,
                    task_name=task.name,
                    task_kwargs={},
                    attempts=0,
                ),
                start_timestamp=time.time(),
                abort_reason=lambda: None,
            )
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in inspect.signature(task.func).parameters:
        kwargs["timestamp"] = int(_NOW.timestamp())
    await task.func(*args, **kwargs)


# --------------------------------------------------------------------------
# The shared recorded state
# --------------------------------------------------------------------------


class _SharedState:
    def __init__(self, last_success: Mapping[str, datetime.datetime]) -> None:
        self.last_success = dict(last_success)
        self.first_known: dict[str, datetime.datetime] = {}

    async def last_successful_run(self, name: str) -> datetime.datetime | None:
        return self.last_success.get(name)

    async def first_known_times(self) -> Mapping[str, datetime.datetime]:
        return dict(self.first_known)

    async def record_first_known(self, identifiers: Iterable[str]) -> None:
        for identifier in identifiers:
            self.first_known.setdefault(identifier, _NOW)

    async def suppressed_identifiers(self) -> set[str]:
        return set()

    async def record_report_delivered(self, identifier: str) -> None:
        return None

    async def clear_report_suppression(self, identifier: str) -> None:
        return None


class _RecordingNotifier:
    def __init__(self) -> None:
        self.posted: list[str] = []

    async def post_monitoring_message(self, message: str) -> None:
        self.posted.append(message)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(main_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


async def test_both_consumers_reach_the_same_verdict_from_the_same_declaration(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Every consumer reads the same declaration.

    WHEN the reporting check and the freshness interface each determine
    whether a given piece of work is overdue
    THEN both SHALL reach the same verdict, having read the same declared
    tolerance.

    SPECIFIED. The recorded state is arranged so the answer is not uniform
    -- the work with the longest declared tolerance is placed well past it,
    everything else a minute ago -- because two consumers that both said
    "nothing is overdue" would agree without either having read a tolerance
    at all. The failure this prevents is silent: a check and an endpoint
    disagreeing about what is overdue produces an alarm nobody can
    reconcile with the dashboard.
    """
    registrations = _registrations()
    assert len(registrations) >= 2, (
        "fewer than two pieces of recurring work are registered, so a "
        "mixed verdict cannot be arranged; the daily digest and the "
        "overdue check's own liveness are both registered (tasks.md 1.2, 4.7)"
    )

    stale = max(registrations, key=lambda entry: _tolerance(entry).total_seconds())
    stale_names = _names(stale)
    last_success: dict[str, datetime.datetime] = {}
    for entry in registrations:
        moment = (
            _NOW - _tolerance(entry) * 2
            if _names(entry) == stale_names
            else _NOW - datetime.timedelta(minutes=1)
        )
        for name in _names(entry):
            last_success[name] = moment

    state = _SharedState(last_success)
    notifier = _RecordingNotifier()

    check_module = _check_module()
    for name in (
        "last_successful_run",
        "first_known_times",
        "suppressed_identifiers",
        "record_report_delivered",
        "clear_report_suppression",
    ):
        _substitute(monkeypatch, check_module, name, getattr(state, name))
    _substitute(monkeypatch, check_module, "notifier", notifier)
    monkeypatch.setattr(
        check_module, "record_first_known", state.record_first_known, raising=False
    )

    route_module = _route_module()
    for name in ("last_successful_run", "first_known_times", "record_first_known"):
        _substitute(monkeypatch, route_module, name, getattr(state, name))
    monkeypatch.setattr(route_module, "CACHE_SECONDS", 0, raising=False)

    await _run_check()
    response = client.get(FRESHNESS_PATH)

    endpoint_overdue = {
        entry["id"] for entry in response.json()["work"] if entry["overdue"]
    }
    check_overdue = {
        name
        for entry in registrations
        for name in _names(entry)
        if any(name in message for message in notifier.posted)
    }

    assert endpoint_overdue, (
        "the freshness endpoint reported nothing overdue although the work "
        "with the longest declared tolerance was placed at twice that "
        f"tolerance: {response.json()!r}"
    )
    assert check_overdue, (
        f"the check reported nothing overdue under the same state: {notifier.posted!r}"
    )

    # Compared as the underlying registrations rather than as raw strings,
    # since the two consumers may name a piece of work differently -- what
    # the scenario fixes is the verdict, not the vocabulary.
    endpoint_verdict = {
        frozenset(_names(entry))
        for entry in registrations
        if _names(entry) & endpoint_overdue
    }
    check_verdict = {
        frozenset(_names(entry))
        for entry in registrations
        if _names(entry) & check_overdue
    }

    assert endpoint_verdict == check_verdict, (
        "the reporting check and the freshness endpoint disagree about "
        "which work is overdue, reading the same recorded state and the "
        "same declared tolerances.\n"
        f"endpoint: {sorted(sorted(names) for names in endpoint_verdict)}\n"
        f"check:    {sorted(sorted(names) for names in check_verdict)}"
    )
    assert endpoint_verdict == {frozenset(stale_names)}, (
        "the consumers agree, but not on the work whose declared tolerance "
        f"had actually elapsed ({sorted(stale_names)}): "
        f"{sorted(sorted(names) for names in endpoint_verdict)}"
    )
