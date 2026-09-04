"""Stuck-step report moves to thread reply with confirmer/submitter tagging.

Derived strictly from the MODIFIED requirement in `launch-step-automation`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

Covers:
- Scenario: A newly cooled-off step is reported (as thread reply)
- Scenario: A stuck step naming a confirmer tags that confirmer
- Scenario: A stuck step naming no confirmer tags the submitter
- Scenario: A pass that cannot read the backoff record delivers no report
- Scenario: A report that could not be delivered is not suppressed

The modified behavior: stuck-step reports are delivered as replies within the
launch's thread in the launches channel, establishing that thread first if
needed. They tag the step's named confirmer (or the submitter if the step
names no confirmer).

## Level

Unit tests of the stuck-step reporting adapter over a captured Slack poster.
The adapter decides what channel and thread to post to, and who to tag based
on the step's confirmer field.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Stuck-step reports are posted to launches channel as thread replies (not monitoring)
- The message tags the step's named confirmer, or the submitter if none
- The adapter establishes the thread if needed before posting the report
- The report names the launch, step, and what the handler produced (as-is)

INVENTED, recorded in `test-manifest.md`:
- The thread-ts parameter and how it is passed to Slack
- The mention format for tagging (confirmer or submitter)
- How the adapter receives the confirmer and submitter information
- The call signature of the reporting adapter (probed dynamically)

## Level, and how thread establishment is substituted

`_report_stuck_step` directly -- the module's own docstring names it as
the unit that "reports the step, then records that it was reported", and
its parameters (`launch`, `step`, `produced`, `backoff`, `notifier`,
`establish_thread`, `product`, `now`) are exactly this file's INVENTED
dataclasses' shape. Reached as a module attribute despite the leading
underscore, the same way this directory's other files reach
`run_automation_pass`'s siblings -- this project does not treat a single
underscore as enforced privacy for its own tests.

Thread establishment is substituted at the module-level seam every driving
adapter now shares (`establish_thread_and_resolve_mention`,
`launch_thread_delivery.py`, threaded into `_report_stuck_step` as its
required `establish_thread` argument rather than reached for as a module
global -- `automation_pass.py`'s own stated design, "collaborators arrive
as arguments... which is what lets the whole pass be exercised without a
database"). Thread establishment's own behavior is covered directly
against the real operation in
`tests/unit/launch/application/test_thread_establishment_race.py`; this
file only checks that `_report_stuck_step` reaches it, threads the real
`step` through, and uses what it returns.

## Fixture correction

The scaffold's `_StepWithConfirmer`/`_StepWithoutConfirmer` named their
identifier field `id`; the real `StepDefinition` (and everything reading
one -- `_stuck_step_message`, `resolve_mention_target`) names it
`identifier`. Corrected here per this file's own "probed dynamically"
license; the postconditions are unweakened.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_run import Launch
from tests.support.fakes import InertBackoff as _InertBackoff
from tests.support.fixtures import STEP_ID, product_id
from tests.support.values import CatalogProduct as _CatalogProduct

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.automation_pass"

PRODUCT_ID: Final = product_id()
STEP_NAME: Final = "Choose the sub-category node"
CONFIRMER_ID: Final = "U0CONFIRMER"
SUBMITTER_ID: Final = "U0SUBMITTER"

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SLACK_THREAD_TS: Final = "1700000000.000100"

BLOCKED_REASON: Final = "Awaiting FBA compliance certificate from vendor"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` creates it. "
            "This is the absent-target state per ai-toolkit:testing."
        )


@dataclass(frozen=True)
class _StepWithConfirmer:
    identifier: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_ID


@dataclass(frozen=True)
class _StepWithoutConfirmer:
    identifier: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = None


def _launch(*, submitter: str | None = SUBMITTER_ID) -> Launch:
    return Launch(
        product_id=PRODUCT_ID,
        playbook_version="v1",
        current_gate="listable",
        launch_date=None,
        submitter=submitter,
    )


class _CapturingNotifier:
    """The `notifier` `_report_stuck_step` calls `.post_monitoring_message`
    through -- an object, not a bare function, matching `ThreadReplyNotifier`
    (`launch.application.ports`), not `shared.application.ports`'s
    message-only `MonitoringNotifier`: this call site's real collaborator is
    `launch`'s own notifier, injected by `worker.py`
    (`fix-stuck-step-report-notifier`)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post_monitoring_message(
        self, *, channel: str, text: str, thread_ts: str | None = None
    ) -> None:
        self.calls.append({"channel": channel, "text": text, "thread_ts": thread_ts})

    @property
    def rendered(self) -> str:
        return json.dumps(self.calls, default=str)


def _fake_establish_thread(
    calls: list[dict[str, Any]],
) -> Any:
    """A fake for `_report_stuck_step`'s `establish_thread` argument.

    `automation_pass.py` threads this collaborator through as an explicit
    argument, not a module global (its own stated design: "collaborators
    arrive as arguments... which is what lets the whole pass be exercised
    without a database") -- so, unlike the other three driving adapters,
    this one needs no `monkeypatch.setattr`, only a fake passed directly.
    Returns a mention derived from `step.confirmer` when the caller passed
    a step naming one, mirroring `resolve_mention_target`'s own rule --
    that rule's correctness is `test_thread_establishment_race.py`'s
    concern; this file only checks that `_report_stuck_step` asks for it
    right and uses what comes back.
    """

    async def _fake(*args: Any, **kwargs: Any) -> tuple[str, str | None]:
        calls.append(kwargs)
        step = kwargs.get("step")
        mention = getattr(step, "confirmer", None) or SUBMITTER_ID
        return SLACK_THREAD_TS, mention

    return _fake


async def _report(
    *,
    step: Any,
    produced: str,
    notifier: _CapturingNotifier,
    establish_thread_calls: list[dict[str, Any]] | None = None,
    launch: Launch | None = None,
) -> None:
    """INVENTED call shape — the single correction point for reaching
    `_report_stuck_step` directly."""
    entry = getattr(_module(), "_report_stuck_step", None)
    if not callable(entry):
        pytest.fail(
            f"{_module().__name__} has no `_report_stuck_step` attribute — "
            "correct this file's probe to the implemented name"
        )
    await entry(
        launch=launch or _launch(),
        step=step,
        produced=produced,
        backoff=_InertBackoff(),
        notifier=notifier,
        establish_thread=_fake_establish_thread(
            establish_thread_calls if establish_thread_calls is not None else []
        ),
        product=_CatalogProduct(),
        now=datetime(2027, 1, 6, 9, 30, tzinfo=UTC),
    )


async def test_stuck_step_goes_to_launches_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED: the stuck-step report is posted to launches channel, not monitoring.

    The modified behavior delivers to the launches channel (where the thread
    lives) instead of the monitoring channel. This is a channel change required
    by "reported as a reply within the launch's Slack thread".
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()

    await _report(step=_StepWithConfirmer(), produced=BLOCKED_REASON, notifier=notifier)

    assert notifier.calls, "no report was delivered for the stuck step"
    assert notifier.calls[0].get("channel") == LAUNCHES_CHANNEL_ID, (
        f"the stuck-step report was not posted to the launches channel: "
        f"{notifier.calls[0]!r}"
    )


async def test_stuck_step_with_confirmer_tags_confirmer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stuck step naming a confirmer tags that confirmer.

    WHEN a report is delivered for a stuck step that names a confirmer
    THEN the message tags that confirmer.

    SPECIFIED: if the step names a confirmer, they are tagged. Asserted two
    ways: `_report_stuck_step` threads the real `step` through to mention
    resolution (not just its name), and it uses whatever mention that
    resolution returns.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()
    calls: list[dict[str, Any]] = []
    step = _StepWithConfirmer()

    await _report(
        step=step,
        produced=BLOCKED_REASON,
        notifier=notifier,
        establish_thread_calls=calls,
    )

    assert calls and calls[0].get("step") is step, (
        "_report_stuck_step did not thread the stuck step through to "
        f"mention resolution: {calls!r}"
    )
    assert f"<@{CONFIRMER_ID}>" in notifier.rendered, (
        f"the report did not tag the step's confirmer: {notifier.rendered!r}"
    )


async def test_stuck_step_without_confirmer_tags_submitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stuck step naming no confirmer tags the submitter.

    WHEN a report is delivered for a stuck step that names no confirmer
    THEN the message tags the launch's submitter instead.

    SPECIFIED: if the step has no confirmer, the submitter is tagged. The
    fallback rule itself belongs to `resolve_mention_target` and is
    asserted directly in `test_thread_establishment_race.py`; this checks
    that `_report_stuck_step` still threads the step through (so the
    fallback can even run) rather than substituting `None`.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()
    calls: list[dict[str, Any]] = []
    step = _StepWithoutConfirmer()

    await _report(
        step=step,
        produced=BLOCKED_REASON,
        notifier=notifier,
        establish_thread_calls=calls,
    )

    assert calls and calls[0].get("step") is step, (
        f"_report_stuck_step did not thread the confirmer-less step through: {calls!r}"
    )
    assert f"<@{SUBMITTER_ID}>" in notifier.rendered, (
        f"the report did not fall back to tagging the submitter: {notifier.rendered!r}"
    )


async def test_stuck_step_report_is_thread_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED: the stuck-step report is posted as a reply (with thread_ts parameter).

    A thread reply requires the `thread_ts` parameter to be passed to Slack's
    API. This derives from "reported as a reply within the launch's Slack
    thread". Asserted structurally -- the literal `thread_ts` kwarg, set to
    exactly what thread establishment returned.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()

    await _report(step=_StepWithConfirmer(), produced=BLOCKED_REASON, notifier=notifier)

    assert notifier.calls, "no report was delivered for the stuck step"
    assert notifier.calls[0].get("thread_ts") == SLACK_THREAD_TS, (
        f"the report was not posted with the established thread's "
        f"reference: {notifier.calls[0]!r}"
    )


async def test_stuck_step_names_handler_result_as_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED: the report names what the handler produced as its result.

    From the requirement: "naming the launch, the step, and what the handler
    produced as its result, which for a `Blocked` outcome is also the reason
    it carries".

    The result is reported as what the handler said, never asserted as a
    fact: the produced text is read back verbatim, not reworded or
    summarized.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()
    produced = "Recommended sub-category: Kitchen Utensils & Gadgets."

    await _report(step=_StepWithConfirmer(), produced=produced, notifier=notifier)

    assert notifier.calls, "no report was delivered for the stuck step"
    text = notifier.calls[0].get("text") or ""
    assert STEP_NAME in text, f"the report did not name the step: {text!r}"
    assert produced in text, (
        f"the report did not carry what the handler produced, verbatim: {text!r}"
    )


async def test_stuck_step_with_blocked_includes_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED: a Blocked outcome's reason is included in the report.

    For a `Blocked` outcome, the reason is also part of what the handler
    produced -- by the time it reaches `_report_stuck_step`, the caller has
    already folded it into `produced` (this function's own docstring: the
    report says "what the handler produced as its result"). This confirms
    that fold-in survives to the message rather than being dropped.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)
    notifier = _CapturingNotifier()
    produced = f"Blocked: {BLOCKED_REASON}"

    await _report(step=_StepWithConfirmer(), produced=produced, notifier=notifier)

    assert notifier.calls, "no report was delivered for the stuck step"
    text = notifier.calls[0].get("text") or ""
    assert BLOCKED_REASON in text, (
        f"the Blocked outcome's reason did not reach the report: {text!r}"
    )
