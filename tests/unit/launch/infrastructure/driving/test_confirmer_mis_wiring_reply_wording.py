"""A mis-wired decision blames neither roster membership nor confirmer status.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-step-automation/spec.md`

Covers the one clause the ADDED requirement *Only the step's named
confirmer may decide a pending result* adds to its wiring-fault paragraph
beyond what the REMOVED requirement it replaces already said:

> "an unreadable collaborator SHALL NOT be resolved into 'this identity is
> not the confirmer' ... and SHALL NOT leave a decider with any reason to
> believe their roster entry **or their standing as confirmer** is at
> fault."

The REMOVED requirement's equivalent paragraph said only "SHALL NOT be
resolved into 'the roster does not know that Slack identity' ... any
reason to believe their roster entry ... is at fault" — it had no
confirmer to misattribute to, because there was no confirmer. This file
adds the one assertion the widened wording makes possible: that a
mis-wired reply says nothing that reads as a statement about the
decider's *confirmer* standing, not only nothing about their roster
membership.

The rest of scenario *A mis-wiring is never reported as an unknown
identity* — that the decider is not told the roster does not know their
identity, and that the mis-wiring is logged at `error` level or above
with its exception — is unchanged in substance from the REMOVED
requirement's version and stays covered by
`tests/unit/launch/infrastructure/driving/
test_automated_decision_wiring.py::
test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators`,
whose fixtures, session seams and entry-point probing this file reuses
verbatim rather than reinventing.

**Level.** The confirmation adapter's entry point, substituting only its
session/persistence seams — the identical placement and technique
`test_automated_decision_wiring.py` uses and explains at length.

## Expected first-run state

Nothing in the adapter today distinguishes "not on the roster" from "not
the confirmer" in its reply wording (there being no confirmer yet), and
the wiring fault is not caught at all before this change lands, so this
test fails the same way `test_automated_decision_wiring.py`'s wiring
tests do on their first run: the fault escapes rather than producing a
reply to inspect.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.infrastructure.driving import automation_confirmation
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId("11111111-1111-1111-1111-111111111111")
STEP_ID: Final = "listing.sub-category"

ALICE_SLACK: Final = "U01ALICE"
DECIDED_AT: Final = datetime(2027, 1, 6, 10, 0, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)

#: Wording that would blame the decider's roster membership — kept
#: identical to the sibling wiring file's list.
_BLAMES_ROSTER_MEMBERSHIP: Final = (
    "does not know",
    "doesn't know",
    "not on the roster",
    "unknown identity",
    "unrecognised",
    "unrecognized",
    "no such person",
    "not known",
)

#: NEW for this delta: wording that would blame the decider's *confirmer*
#: standing specifically, distinct from roster membership.
_BLAMES_CONFIRMER_STANDING: Final = (
    "not the confirmer",
    "not a confirmer",
    "isn't the confirmer",
    "is not this step's confirmer",
    "not named as confirmer",
    "not the named confirmer",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


_SESSION_SEAM_NAMES: Final = ("session", "transaction")
_PERSISTENCE_SUFFIXES: Final = ("Repository", "Repositories", "Store", "Roster")


class _AnswersNothing:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def __getattr__(self, name: str) -> Any:
        async def _answer(*args: Any, **kwargs: Any) -> None:
            return None

        return _answer


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    substituted = [
        name for name in _SESSION_SEAM_NAMES if hasattr(automation_confirmation, name)
    ]
    for name in substituted:
        monkeypatch.setattr(automation_confirmation, name, _fake_session)
    assert substituted, (
        "the confirmation adapter exposes no session seam under any of "
        f"{_SESSION_SEAM_NAMES}; correct `_SESSION_SEAM_NAMES` to the "
        "implemented one, or these tests will reach a real database"
    )
    for name, value in list(vars(automation_confirmation).items()):
        if isinstance(value, type) and name.endswith(_PERSISTENCE_SUFFIXES):
            monkeypatch.setattr(automation_confirmation, name, _AnswersNothing)


class _CapturingRespond:
    def __init__(self) -> None:
        self.replies: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.replies.append({"args": args, "kwargs": kwargs})

    @property
    def rendered(self) -> str:
        return json.dumps(self.replies, default=str)


class _CountingAck:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1


def _button_body(*, accept: bool) -> dict[str, Any]:
    value = json.dumps({"product_id": str(PRODUCT_ID), "step_id": STEP_ID})
    action = {
        "action_id": "accept_automated_result" if accept else "reject_automated_result",
        "type": "button",
        "value": value,
    }
    return {
        "type": "block_actions",
        "user": {"id": ALICE_SLACK},
        "channel": {"id": "C0MONITORING"},
        "actions": [action],
        "response_url": "https://slack.example/respond",
    }


@dataclass
class _Answer:
    returned: Any
    respond: _CapturingRespond
    escaped: BaseException | None

    @property
    def text(self) -> str:
        parts = [self.respond.rendered]
        if self.returned is not None:
            parts.append(str(self.returned))
        return "\n".join(parts)

    @property
    def answered(self) -> bool:
        if self.respond.replies:
            return True
        return isinstance(self.returned, str) and bool(self.returned.strip())


_ENTRY_NAMES: Final = (
    "_handle_decision",
    "handle_decision",
    "_decide",
    "handle_decision_action",
)


async def _drive_decision(*, accept: bool = True) -> _Answer:
    entry = None
    for name in _ENTRY_NAMES:
        found = getattr(automation_confirmation, name, None)
        if callable(found):
            entry = found
            break
    if entry is None:
        pytest.fail(
            "the confirmation adapter exposes no decision entry point under "
            f"any of {_ENTRY_NAMES} — correct `_ENTRY_NAMES` to the "
            "implemented name"
        )

    respond = _CapturingRespond()
    body = _button_body(accept=accept)
    pool: dict[str, Any] = {
        "ack": _CountingAck(),
        "body": body,
        "payload": body["actions"][0],
        "action": body["actions"][0],
        "respond": respond,
        "say": respond,
        "client": None,
        "context": {},
        "logger": logging.getLogger("commerce_ops.launch.automation_confirmation"),
        "accept": accept,
        "product_id": PRODUCT_ID,
        "step_id": STEP_ID,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }

    accepted = set(inspect.signature(entry).parameters)
    supplied = {key: value for key, value in pool.items() if key in accepted}
    assert supplied, (
        "none of this file's supplied arguments matched the decision entry "
        f"point's signature ({sorted(accepted)}); correct `_drive_decision`"
    )

    try:
        returned = entry(**supplied)
        if inspect.isawaitable(returned):
            returned = await returned
    except Exception as error:  # noqa: BLE001 -- an escaping fault is exactly
        # the outcome the scenario forbids, so it is observed, not raised
        return _Answer(returned=None, respond=respond, escaped=error)
    return _Answer(returned=returned, respond=respond, escaped=None)


def _blames(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


async def test_a_mis_wiring_blames_neither_roster_membership_nor_confirmer_standing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: A mis-wiring is never reported as an unknown identity —
    the widened clause this delta adds.

    WHEN a decision is judged against a roster collaborator that cannot
    answer who the roster carries
    THEN the decider is not told that their identity is not the
    confirmer, and the mis-wiring is reported where operators see faults.

    SPECIFIED: the reply must carry no clause reading as a statement about
    the decider's *confirmer* standing, in addition to carrying none about
    their roster membership — a decider whose deployment is mis-wired
    must not be told, in either vocabulary, that the fault is about them.
    """
    monkeypatch.setattr(automation_confirmation, "read_people", None)

    with caplog.at_level(logging.DEBUG):
        answer = await _drive_decision()

    assert answer.answered, (
        "there is no reply to inspect — the decider got nothing back, so "
        "the assertions below would pass for the wrong reason"
    )

    # SPECIFIED (unchanged half, regression guard): not blamed for roster
    # membership.
    assert not _blames(answer.text, _BLAMES_ROSTER_MEMBERSHIP), (
        "a mis-wired deployment told the decider something about their "
        f"roster membership: {answer.text!r}"
    )
    # SPECIFIED (the widened clause): not blamed for confirmer standing
    # either.
    assert not _blames(answer.text, _BLAMES_CONFIRMER_STANDING), (
        "a mis-wired deployment told the decider something about their "
        f"standing as confirmer: {answer.text!r}"
    )
    assert ALICE_SLACK not in answer.text, (
        f"the reply names the decider's Slack identity: {answer.text!r}"
    )

    # SPECIFIED: the mis-wiring is reported where operators see faults.
    faults = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert faults, (
        "the mis-wiring was answered to the decider but never reported at "
        "`error` level or above"
    )
    assert any(record.exc_info is not None for record in faults), (
        "the fault was logged without its exception"
    )
