"""`worker` translates launch's refusal into the briefing's own condition.

Derived strictly from the delta specs of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/briefing/spec.md`

Covers, from the ADDED requirement *A launch source that cannot supply
reports is reported, not treated as a clean day*, its statement rather than
one of its scenarios:

> Whatever satisfies that source is responsible for translating its own
> module's condition into this one; the briefing SHALL treat the carried
> identifiers as opaque. Today the only such condition is a launch playbook
> that cannot hold a launch, and the identifiers are the gates that hold no
> active blocking step.

`worker.py` is what satisfies the `LaunchReports` port (`design.md`, "the
seam is the one this codebase already uses for every other launch fact the
briefing needs"), so it is what owes the translation.

## Why this is a test and not a review item

`tasks.md` 5.13 states it plainly: this translation is the only thing
standing between a `launch.domain` exception and the `briefing`
requirement. Untested, a failure here reaches `daily_briefing`'s generic
handler and produces a failed run plus the assembly-failure message —
which three scenarios of the `briefing` delta forbid — with nothing in the
suite going red. The briefing-side tests
(`tests/unit/briefing/infrastructure/driving/test_unavailable_launch_source.py`)
raise the briefing-owned condition directly and so cannot detect it.

## Level

`worker`'s reader function, in-process. It is a plain async function over a
substituted playbook read; nothing below it can observe a translation, and
nothing above it distinguishes a translation that happened from one the
briefing invented.

`worker.py` sits outside every `.importlinter` container, which is what
lets it — and this test — name both `launch` and `briefing`.

## What is fixed, and what is INVENTED

Fixed: that `worker` translates `PlaybookNotReadyError` from its
launch-reports reader into the briefing-owned condition, carrying the
unheld gate identifiers (`tasks.md` 4.5); that the reader is
`_read_launch_reports`, assigned to `daily_briefing_job.read_launch_reports`
(`design.md`, `worker.py:129`).

INVENTED, each with a correction point below:

- `PlaybookNotReadyError`'s constructor keywords — `_build_not_ready()`.
- The briefing-owned condition's name — `_condition_type()`, which probes
  the briefing's public surface and fails loudly rather than defaulting.
- The reader's own name and call shape — `_reader()` probes
  `_READER_NAMES` on the worker module.

## Expected first-run state

Neither `PlaybookNotReadyError` nor the briefing-owned condition exists, so
every test here fails on an absent target — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest

import commerce_ops.briefing.application as briefing_application
import commerce_ops.worker as worker_module
from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

UNHELD_GATES: Final = ("ignition", "graduated")

_READER_NAMES: Final = (
    "_read_launch_reports",
    "read_launch_reports",
    "_launch_reports",
)

_CONDITION_NAMES: Final = (
    "LaunchReportsUnavailableError",
    "ReportsUnavailableError",
    "SourceUnavailableError",
    "LaunchSourceUnavailableError",
    "ReportSourceUnavailable",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=0),
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "handler": "fixture.holding_check",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _unready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=tuple(
            _hold(
                gate,
                status=StepStatus.DRAFT if gate in UNHELD_GATES else StepStatus.ACTIVE,
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
    )


# ---------------------------------------------------------------------------
# The two conditions — the single correction points
# ---------------------------------------------------------------------------


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": UNHELD_GATES}),
        ((), {"playbook": playbook, "unheld_gates": UNHELD_GATES}),
        ((UNHELD_GATES, playbook), {}),
        ((playbook, UNHELD_GATES), {}),
    )
    for args, kwargs in attempts:
        try:
            return error(*args, **kwargs)  # type: ignore[no-any-return]
        except TypeError:
            continue
    pytest.fail(
        "could not construct PlaybookNotReadyError under any probed "
        "signature; correct `_build_not_ready` to the implemented one"
    )


def _condition_type() -> type[Exception]:
    for name in _CONDITION_NAMES:
        found = getattr(briefing_application, name, None)
        if isinstance(found, type) and issubclass(found, BaseException):
            return found  # type: ignore[return-value]
    pytest.fail(
        "commerce_ops.briefing.application exports no condition meaning "
        f"'the launch source cannot supply reports' under any of "
        f"{_CONDITION_NAMES} (`tasks.md` 4.4)"
    )


# ---------------------------------------------------------------------------
# Reaching the reader
# ---------------------------------------------------------------------------


def _reader() -> Any:
    for name in _READER_NAMES:
        found = getattr(worker_module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"commerce_ops.worker exposes no launch-reports reader under any of "
        f"{_READER_NAMES} (`design.md`: `_read_launch_reports`, assigned to "
        "`daily_briefing_job.read_launch_reports`)"
    )


async def _call_reader(reader: Any) -> Any:
    """Invoke the reader with whatever its signature asks for.

    Every parameter is optional as far as this test is concerned: the
    refusal is raised by the substituted playbook read before any of them
    matters.
    """
    parameters = inspect.signature(reader).parameters
    kwargs: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if name in {"as_of", "when", "today"}:
            import datetime

            kwargs[name] = datetime.date(2027, 3, 2)
        elif name == "scope":
            from commerce_ops.shared.domain.access_scope import AccessScope

            kwargs[name] = AccessScope.unrestricted()
        else:
            kwargs[name] = None
    return await reader(**kwargs)


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_module, "session", _fake_session, raising=False)
    monkeypatch.setattr(worker_module, "transaction", _fake_session, raising=False)


def install_refusing_playbook_read(
    monkeypatch: pytest.MonkeyPatch, playbook: LaunchPlaybook
) -> None:
    class _Repository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str = "") -> LaunchPlaybook:
            raise _build_not_ready(playbook)

    monkeypatch.setattr(worker_module, "PlaybookRepository", _Repository)


# ---------------------------------------------------------------------------
# The translation
# ---------------------------------------------------------------------------


async def test_the_reader_raises_the_briefing_owned_condition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "Whatever satisfies that source is
    responsible for translating its own module's condition into this one."

    The condition the briefing sees must be the briefing's own, so that
    `daily_briefing_job`'s handler — written against a briefing type —
    recognises it. A `PlaybookNotReadyError` escaping here reaches the
    generic assembly-failure branch instead, and three scenarios of this
    delta forbid the outcome that produces.
    """
    install_refusing_playbook_read(monkeypatch, _unready_playbook())
    condition = _condition_type()

    with pytest.raises(condition):
        await _call_reader(_reader())


async def test_the_translated_condition_carries_the_unheld_gate_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "and SHALL carry with it the identifiers
    describing why ... the identifiers are the gates that hold no active
    blocking step".

    Asserted separately from the type above so that a translation losing
    the identifiers fails distinguishably: the briefing posts a message
    naming them, and a condition carrying none would produce a message
    that says nothing actionable while every type assertion still passed.

    The identifiers are asserted as *present*, not as a particular
    container — the briefing treats them as opaque strings, so how they are
    carried is not something this requirement fixes.
    """
    install_refusing_playbook_read(monkeypatch, _unready_playbook())
    condition = _condition_type()

    with pytest.raises(condition) as caught:
        await _call_reader(_reader())

    carried = str(caught.value) + repr(vars(caught.value))
    for gate in UNHELD_GATES:
        assert gate in carried, (
            f"the translated condition does not carry the unheld gate "
            f"{gate!r}, so the briefing cannot name what is missing: "
            f"{carried!r}"
        )


async def test_the_launch_domain_exception_does_not_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 4.5 / `design.md`: the translation exists so that
    `briefing` never meets a `launch.domain` type.

    Stated as its own test because `PlaybookNotReadyError` could in
    principle be made a subclass of the briefing condition — which would
    satisfy the first test above while leaving the briefing catching a
    `launch.domain` exception, exactly the coupling `design.md` refuses.
    """
    install_refusing_playbook_read(monkeypatch, _unready_playbook())
    not_ready = getattr(playbook_module, "PlaybookNotReadyError", None)
    assert not_ready is not None
    condition = _condition_type()

    with pytest.raises(condition) as caught:
        await _call_reader(_reader())

    assert not isinstance(caught.value, not_ready), (
        "the condition the briefing receives is a `launch.domain` "
        "exception, so `briefing` would be catching a launch type"
    )
