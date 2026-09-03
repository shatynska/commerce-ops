"""The stuck-step report's own fallback policy, and the form it names
identifiers in.

Derived strictly from the MODIFIED requirement *A step whose handler has
stopped making progress is reported once* in
`openspec/changes/fix-launch-thread-mentions/specs/launch-step-automation/spec.md`.

Covers:

- *A stuck step naming a confirmer tags that confirmer*
- *A stuck step naming no confirmer tags the submitter*
- *A stuck step whose confirmer cannot be resolved tags the submitter and
  names the gap*
- *A stuck step is reported to the submitter when the membership cannot be
  read*
- *A report naming a product by identifier names it by value*

## Derived from this requirement, never from the ask's

This report and the pending-result ask now degrade **differently on the
same failure**, and the requirement says why in its own words:

    **This report falls back to the submitter where the pending-result ask
    does not, and the difference is deliberate.** No authorization rule
    governs who may act on a stuck step: the report exists so that *a
    member* can supply what the handler is missing, so reaching somebody is
    the whole of its purpose, and an untagged report reaching nobody would
    defeat it.

Every assertion below is taken from that requirement. Nothing is copied
from `test_pending_result_ask_untagged_policy.py`, and the two files
deliberately assert *opposite* postconditions on the same input — which is
the point. `design.md` names this asymmetry as "the kind of thing a later
reader smooths out for consistency"; these two files are what makes
smoothing it out fail loudly.

## The discriminator this file is really about

Three states have to stay distinguishable in the channel, and two of them
tag the same member:

1. the step names no confirmer            → tags the submitter, no gap named
2. the step's confirmer cannot be reached → tags the submitter, gap named
3. the step's confirmer resolves          → tags the confirmer

States 1 and 2 differ only in the text. So
`test_a_step_naming_no_confirmer_tags_the_submitter_and_names_no_gap` is
not a redundant regression guard beside its neighbour — it is the negative
half without which the gap-naming assertion could be satisfied by a line
printed on every report.

## Level

`_report_stuck_step` directly, with `establish_thread` supplied as an
explicit argument — `automation_pass.py`'s own design, which
`test_stuck_step_report_to_thread_reply.py` in this directory already
records ("collaborators arrive as arguments… which is what lets the whole
pass be exercised without a database"). That is the smallest unit that can
observe who a report tags and what its text names.

Mention resolution's own correctness is
`tests/unit/launch/application/test_mention_resolution_namespace.py`'s
concern; "the confirmer could not be resolved" arrives here as the seam
answering `None` while the step still names one, which `design.md` states
is exactly the condition each caller derives its policy from.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: the submitter fallback and the extra
line naming an unresolved confirmer (`tasks.md` 3.8), and the anchor
fallback read as `.value` (2.4).

INVENTED, recorded in `test-manifest.md`:

- `_report_stuck_step`'s call shape, copied from
  `test_stuck_step_report_to_thread_reply.py` rather than re-derived.
- The **wording** by which the report names that the confirmer could not
  be resolved. No artifact fixes it. Correction point:
  `_NAMES_AN_UNRESOLVED_CONFIRMER`. It is not asserted blind — the
  no-confirmer test establishes that a report with nothing to report
  matches none of those markers, so the positive assertion beside it
  cannot pass vacuously on a marker that matches every report.
- The mention syntax `<@…>`.

## Expected first-run state

`test_a_stuck_step_naming_no_confirmer_tags_the_submitter_and_names_no_gap`
is expected to PASS — that rule is unchanged by this delta and is a
regression guard.

`test_a_stuck_step_report_names_the_product_identifier_by_value` is
expected to FAIL as failure state 1: `_report_stuck_step` composes
`str(launch.product_id)` today, which yields `ProductId(value='…')`.

The confirmer tests are expected to FAIL as failure state 1: today the
report renders whatever the seam returned, and nothing composes the extra
line.
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.automation_pass"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"

#: A member identifier, as a step's `confirmer` field actually holds one —
#: deliberately not Slack-shaped, so a report carrying it is visibly wrong.
CONFIRMER_MEMBER_ID: Final = "3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30"
CONFIRMER_SLACK: Final = "U01ALICE"
SUBMITTER_SLACK: Final = "U0SUBMITTER"

LAUNCH_DATE: Final = date(2027, 3, 1)
NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
SLACK_THREAD_TS: Final = "1700000000.000100"

BLOCKED_REASON: Final = "Awaiting FBA compliance certificate from vendor"

#: How the report may spell "this step's confirmer could not be resolved"
#: (INVENTED — see the module docstring). Correction point for the
#: implemented wording. Deliberately excludes any word a routine report
#: would carry anyway, so a match means the gap and nothing else.
_NAMES_AN_UNRESOLVED_CONFIRMER: Final = (
    "could not be resolved",
    "couldn't be resolved",
    "could not be reached",
    "not resolvable",
    "unresolvable confirmer",
    "unresolved confirmer",
    "cannot be resolved",
    "no longer on the membership",
    "not on the membership",
    "deactivated",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:  # pragma: no cover -- absent-target guard
        pytest.fail(f"{MODULE_PATH} does not exist ({error})")


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


@dataclass(frozen=True)
class _Step:
    identifier: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_MEMBER_ID


class _InertBackoff:
    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        return None


class _CapturingNotifier:
    """The `notifier` `_report_stuck_step` calls `.post_monitoring_message`
    through -- matching `ThreadReplyNotifier` (`launch.application.ports`),
    not `shared.application.ports`'s message-only `MonitoringNotifier`: this
    call site's real collaborator is `launch`'s own notifier, injected by
    `worker.py` (`fix-stuck-step-report-notifier`)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post_monitoring_message(
        self, *, channel: str, text: str, thread_ts: str | None = None
    ) -> None:
        self.calls.append({"channel": channel, "text": text, "thread_ts": thread_ts})

    @property
    def rendered(self) -> str:
        return json.dumps(self.calls, default=str)

    @property
    def text(self) -> str:
        return "\n".join(str(call.get("text") or "") for call in self.calls)


@dataclass
class _ThreadSeam:
    """Substitutes `establish_thread`.

    Answers whatever mention the test asked for rather than deriving one
    from the step — deriving it would re-implement `resolve_mention_target`
    here, and every test below would then pass or fail on this file's copy
    of that rule instead of on the report's own policy.
    """

    mention: str | None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[str, str | None]:
        self.calls.append(kwargs)
        return SLACK_THREAD_TS, self.mention


def _launch() -> Launch:
    return Launch(
        product_id=PRODUCT_ID,
        playbook_version="v1",
        current_gate="listable",
        launch_date=LAUNCH_DATE,
        submitter=SUBMITTER_SLACK,
    )


async def _report(
    *,
    mention: str | None,
    step: Any = None,
    product: Any = None,
    produced: str = BLOCKED_REASON,
) -> tuple[_ThreadSeam, _CapturingNotifier]:
    """INVENTED call shape — the single correction point, kept identical to
    `test_stuck_step_report_to_thread_reply.py`'s so the two files correct
    together."""
    entry = getattr(_module(), "_report_stuck_step", None)
    if not callable(entry):
        pytest.fail(
            f"{MODULE_PATH} has no `_report_stuck_step` attribute — correct "
            "this file's probe to the implemented name"
        )

    seam = _ThreadSeam(mention=mention)
    notifier = _CapturingNotifier()
    await entry(
        launch=_launch(),
        step=step if step is not None else _Step(),
        produced=produced,
        backoff=_InertBackoff(),
        notifier=notifier,
        establish_thread=seam,
        product=product,
        now=NOW,
    )
    return seam, notifier


def _names_a_gap(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _NAMES_AN_UNRESOLVED_CONFIRMER)


# ---------------------------------------------------------------------------
# Scenario: A stuck step naming a confirmer tags that confirmer
# ---------------------------------------------------------------------------


async def test_a_stuck_step_tags_the_confirmers_slack_identity_not_the_member_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stuck step naming a confirmer tags that confirmer.

    WHEN a report is delivered for a stuck step naming a confirmer the
    members carries, active and with a Slack identity
    THEN the message mentions that member by their Slack identity, and the
    membership's own identifier for them appears nowhere in it.

    SPECIFIED, both halves. The shipped test for this scenario passed a
    Slack-looking constant as `step.confirmer` and asserted it appeared,
    which is satisfied by a mention nobody receives. Here the two strings
    differ and both are asserted.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")

    _, notifier = await _report(mention=CONFIRMER_SLACK, product=_CatalogProduct())

    assert notifier.calls, "no report was delivered for the stuck step"
    # SPECIFIED: mentioned by their Slack identity.
    assert f"<@{CONFIRMER_SLACK}>" in notifier.rendered, (
        f"the report did not tag the confirmer's Slack identity: {notifier.rendered!r}"
    )
    # SPECIFIED: the membership's own identifier appears nowhere in it.
    assert CONFIRMER_MEMBER_ID not in notifier.rendered, (
        "the membership's own identifier for the confirmer reached the report; "
        f"Slack renders it as inert literal text: {notifier.rendered!r}"
    )
    # SPECIFIED, by the same scenario: a resolvable confirmer is tagged
    # *instead of* the submitter, not alongside them.
    assert f"<@{SUBMITTER_SLACK}>" not in notifier.rendered
    # And no gap is named, because there is none.
    assert not _names_a_gap(notifier.text), (
        f"a report whose confirmer resolved still named a gap: {notifier.text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A stuck step naming no confirmer tags the submitter
# ---------------------------------------------------------------------------


async def test_a_stuck_step_naming_no_confirmer_tags_the_submitter_and_names_no_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A stuck step naming no confirmer tags the submitter.

    WHEN a report is delivered for a stuck step that names no confirmer
    THEN the message tags the launch's submitter instead.

    SPECIFIED, and unchanged by this delta. Its second assertion is what
    this delta adds: this report must **not** name a gap, because there is
    no gap — the requirement's own reasoning is that "a reader can still
    tell a step that names no confirmer from one whose confirmer cannot be
    reached".

    That negative is also what makes the positive assertion in the next
    test meaningful. Without it, an implementation printing "the
    confirmer could not be resolved" on every report would satisfy the
    gap-naming scenario while destroying the distinction it exists to
    preserve.

    Expected to PASS on its first run: the submitter fallback for a step
    naming no confirmer is today's behaviour, and nothing yet composes a
    gap line to accidentally add.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")

    _, notifier = await _report(
        mention=SUBMITTER_SLACK, step=_Step(confirmer=None), product=_CatalogProduct()
    )

    assert notifier.calls, "no report was delivered for the stuck step"
    # SPECIFIED: the message tags the launch's submitter instead.
    assert f"<@{SUBMITTER_SLACK}>" in notifier.rendered, (
        f"the report did not tag the submitter: {notifier.rendered!r}"
    )
    # SPECIFIED (this delta): and says nothing about an unresolved
    # confirmer, because the step named none. This is the routine case.
    assert not _names_a_gap(notifier.text), (
        "a step naming no confirmer produced a report reading like one whose "
        f"confirmer could not be reached: {notifier.text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A stuck step whose confirmer cannot be resolved tags the
# submitter and names the gap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "why",
    [
        pytest.param("the membership does not carry them", id="unknown-confirmer"),
        pytest.param(
            "the membership carries them deactivated", id="deactivated-confirmer"
        ),
        pytest.param(
            "the membership carries no Slack identity", id="no-slack-identity"
        ),
        pytest.param(
            "the membership could not be read at all", id="unreadable-members"
        ),
    ],
)
async def test_an_unresolvable_confirmer_tags_the_submitter_and_names_the_gap(
    why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenarios: *A stuck step whose confirmer cannot be resolved tags the
    submitter and names the gap* and *A stuck step is reported to the
    submitter when the membership cannot be read*.

    THEN the report is delivered tagging the launch's submitter, its text
    names that the step's confirmer could not be resolved, and the gap is
    reported.

    SPECIFIED. The four ids name the four ways the delta says a confirmer
    fails to resolve; all four arrive at this caller identically — the step
    names a confirmer and the mention is `None` — and the requirement gives
    them one disposition. Parametrising rather than collapsing keeps the
    coverage legible against the delta's own wording.

    This is the assertion that must **not** be reached by copying the ask's
    policy. The ask carries no mention here; this report tags the
    submitter, because `Only the step's named confirmer may decide a
    pending result` governs the ask and governs nothing about a stuck step.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")

    _, notifier = await _report(mention=None, product=_CatalogProduct())

    # SPECIFIED: the report SHALL still be delivered.
    assert notifier.calls, (
        f"no report was delivered when {why}; an untagged report reaching "
        "nobody defeats the report's purpose, and no report at all is worse"
    )
    # SPECIFIED: SHALL tag the launch's submitter.
    assert f"<@{SUBMITTER_SLACK}>" in notifier.rendered, (
        f"the report did not fall back to tagging the submitter when {why}: "
        f"{notifier.rendered!r}"
    )
    # SPECIFIED: SHALL name in its text that the step's confirmer could not
    # be resolved.
    assert _names_a_gap(notifier.text), (
        f"the report tagged the submitter but did not name that the step's "
        f"confirmer could not be resolved ({why}), so a reader cannot tell it "
        f"from a step that names no confirmer at all: {notifier.text!r}"
    )
    # SPECIFIED: and the member identifier is not what got tagged instead.
    assert f"<@{CONFIRMER_MEMBER_ID}>" not in notifier.rendered


# ---------------------------------------------------------------------------
# Scenario: A report naming a product by identifier names it by value
# ---------------------------------------------------------------------------


async def test_a_stuck_step_report_names_the_product_identifier_by_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A report naming a product by identifier names it by value.

    WHEN a report is delivered for a stuck step whose product cannot be
    named any other way
    THEN the identifier appears as its own value, not as a rendering of the
    object carrying it.

    SPECIFIED, and per `shared-vocabulary`'s new requirement. `product=None`
    is what "cannot be named any other way" means here — the catalog read
    returned nothing, and the report falls back to the launch's product
    identifier.

    Not cosmetic where this report is a launch's first per-product message:
    the value it carries becomes the thread anchor's permanent heading, and
    `launch-instance`:513 forbids re-creating the anchor to correct it.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")

    _, notifier = await _report(mention=CONFIRMER_SLACK, product=None)

    assert notifier.calls, "no report was delivered for the stuck step"
    rendered = notifier.rendered
    # SPECIFIED: the identifier appears as its own value.
    assert PRODUCT_ID.value in rendered, (
        f"the report did not name the product by its identifier's value: {rendered!r}"
    )
    # SPECIFIED: not as a rendering of the object carrying it.
    assert "ProductId" not in rendered, (
        f"the report rendered the identifier's object rather than its value: "
        f"{rendered!r}"
    )
    assert "value=" not in rendered


async def test_the_report_still_names_the_step_and_what_the_handler_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement, carried over unchanged: the report names "the
    launch, the step, and **what the handler produced as its result**".

    SPECIFIED, and asserted here on the *untagged-confirmer* path
    specifically. Every other test in this file asserts an absence or a
    mention; without this, a report reduced to nothing but a submitter tag
    and a gap line would satisfy all of them.

    Expected to PASS on its first run for the step and produced text; it is
    a guard against the gap-naming change hollowing the message out.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")
    produced = f"Blocked: {BLOCKED_REASON}"

    _, notifier = await _report(
        mention=None, product=_CatalogProduct(), produced=produced
    )

    assert notifier.calls
    text = notifier.text
    assert STEP_NAME in text, f"the report did not name the step: {text!r}"
    assert BLOCKED_REASON in text, (
        f"the report did not carry what the handler produced: {text!r}"
    )


async def test_the_report_threads_the_step_through_to_mention_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: the step's confirmer "SHALL be resolved
    through the membership to that member's Slack identity".

    SPECIFIED, in the half this caller owns: it must hand the real step to
    resolution, since resolution given no step cannot reach the confirmer
    branch at all.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", "C0LAUNCHES")
    step = _Step()

    seam, _ = await _report(
        mention=CONFIRMER_SLACK, step=step, product=_CatalogProduct()
    )

    assert seam.calls and seam.calls[0].get("step") is step, (
        f"the report did not thread its own step through to resolution: {seam.calls!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED here, recorded rather than omitted
#
# - *A newly cooled-off step is reported*, *A step that stays stuck is not
#   reported again*, *A step still stuck after the cool-off expires is not
#   reported again*, *A step that gets stuck again after moving is reported
#   again*, *A pass that cannot read the backoff record delivers no
#   report*, *A report that could not be delivered is not suppressed*, and
#   *A failed report leaves the pass walking*. All unchanged in substance
#   by this delta — it revises only who is tagged and in what form
#   identifiers are named — and covered by `test_automation_pass.py`,
#   `test_automation_pass_repeat_backoff.py`,
#   `test_automated_step_backoff_live.py` and
#   `test_stuck_step_report_to_thread_reply.py`.
# - Where the gap is *reported* (as distinct from named in the message
#   text). `design.md` places the report in `resolve_mention_target`, the
#   only party that knows which of the four failure points was reached;
#   asserted in
#   `tests/unit/launch/application/test_mention_resolution_namespace.py`.
# ---------------------------------------------------------------------------
