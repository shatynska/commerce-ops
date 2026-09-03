"""Delivering a briefing: silent when clean, and what a delivered message
says.

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/briefing/spec.md

Covers three ADDED requirements and five of their scenarios:

- *A clean briefing is not sent* -- both scenarios
- *Items identify products by name and SKU, and never drop an item over
  naming* -- both scenarios
- *Delivery failure is decoupled from the run* -- its one scenario

## Why the application tier

`tasks.md` 4.4 puts all three decisions in `run_daily_briefing`: whether
to post at all, what the message says, and what happens when the post
fails. That use case is the smallest unit that can observe any of them
(`ai-toolkit:testing`'s level rule) -- the scheduled job wraps it but
makes none of these decisions. The job-level facts that the job *does*
decide -- schedule, retries, and the assemble-failure message -- are in
`tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`.

## Reading "the run SHALL be recorded as succeeded"

Read here as *`run_daily_briefing` returns normally*, the same reading the
retired daily digest's job tests recorded for the same words: a raised
exception is the only way this call reports a failed run to the job that
awaits it, and it is what would also cause a retry. A test asserting the
runner's own recording of that outcome belongs to the integration tier
(`tests/integration/shared/test_scheduled_run_history.py`), not here.

## The interface under test does not exist yet, and its shape is INVENTED

`commerce_ops.briefing` is created by this change, so every test here is
expected to fail on an absent target (`ModuleNotFoundError`) until tasks
4.1-4.5 land. Per `ai-toolkit:testing`, that failure establishes only
absence.

Fixed by the artifacts: `run_daily_briefing(...)` assembling, posting only
when not clean, and logging rather than raising on a delivery failure
(`tasks.md` 4.4); the notifier port having the `MonitoringNotifier` shape,
i.e. an async `post_monitoring_message(message)` (`tasks.md` 4.1, and
`shared/application/ports.py` as it stands).

INVENTED, recorded in `test-manifest.md`: `run_daily_briefing`'s keyword
names (`_run` below is the single correction point), and `None` as the
product reader's "cannot resolve" answer. Correcting either is a fixture
correction; what must survive unweakened is what each test asserts about
what was posted and what was not.

DELIBERATELY UNTESTED: the message's layout, ordering across products, and
any wording beyond the facts the requirements name (product name, SKU or
raw identifier, severity, evidence). `design.md`'s Non-Goals put
formatting outside this change and its Open Questions leave Block Kit
open, so asserting a phrasing would impose a contract nobody agreed to --
the same reading the retired digest's tests applied to their own message.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.briefing.application import run_daily_briefing
from commerce_ops.launch.application import read_launches
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Launching
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"

LAUNCH_DATE: Final = date(2027, 4, 15)  # -30 days => 2027-03-16
HEALTHY_LAUNCH_DATE: Final = date(2027, 8, 1)  # -30 days => 2027-07-02
AS_OF: Final = date(2027, 4, 1)
OVERDUE_STEP_DUE: Final = date(2027, 3, 16)

AUDIENCE: Final = "monitoring-channel"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Launch-side builders (the shapes `test_launch_dates.py` records)
# ---------------------------------------------------------------------------


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "live",
        "discipline": Discipline("listing"),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires, and anchored a year after launch so a filler is
    never the overdue step a briefing item is about."""
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        timing_anchor=OffsetAnchor(days=365),
    )


def _satisfy_fillers(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Record `Satisfied` for the current gate's holding fillers, so the
    conditions in play are only the ones a test authored deliberately."""
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking and step.identifier.startswith("hold."):
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=Provenance(
                    source="automated",
                    who="hold-filler",
                    when=APPROVED_AT,
                    evidence="filler obligations satisfied by the walk",
                ),
            )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _launch(
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = LAUNCH_DATE,
    at_gate: str = "listable",
) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    while launch.current_gate != at_gate:
        _satisfy_fillers(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver=APPROVER,
                    when=APPROVED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    _satisfy_fillers(launch, playbook)
    return launch


class _FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    async def all(self) -> tuple[Launch, ...]:
        return await self.list_all()

    async def list_launches(self) -> tuple[Launch, ...]:
        return await self.list_all()


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# Briefing-side test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku
    stage: Any


class _FakeCatalog:
    def __init__(self, products: dict[ProductId, _CatalogProduct]) -> None:
        self._products = products

    async def __call__(self, product_id: ProductId) -> _CatalogProduct | None:
        return self._products.get(product_id)


class _ScriptedLaunchReports:
    """Scripted reports, or a scripted read failure -- never both."""

    def __init__(
        self,
        reports: tuple[Any, ...] = (),
        *,
        failure: Exception | None = None,
    ) -> None:
        self._reports = reports
        self._failure = failure

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        if self._failure is not None:
            raise self._failure
        return self._reports


class _RecordingNotifier:
    """The `MonitoringNotifier`-shaped port, recording each posted message.

    Exposes the port member *and* `__call__`, so that whichever of the two
    the implementation wires up, the message still lands in `posted`. That
    is fixture-level accommodation of a call shape no artifact fixes; the
    assertions are all made on `posted`.
    """

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.posted: list[str] = []
        self._failure = failure

    async def post_monitoring_message(self, message: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.posted.append(message)

    async def __call__(self, message: str) -> None:
        await self.post_monitoring_message(message)


def _active(name: str, sku: str) -> _CatalogProduct:
    return _CatalogProduct(name=name, sku=Sku(sku), stage=Launching(phase=1))


async def _reports_for(playbook: LaunchPlaybook, *launches: Launch) -> tuple[Any, ...]:
    return tuple(
        await read_launches(
            _FakeLaunchStore(*launches),
            _FakePlaybooks(playbook),
            as_of=AS_OF,
            scope=AccessScope.unrestricted(),
        )
    )


async def _run(
    reports: tuple[Any, ...],
    products: dict[ProductId, _CatalogProduct],
    notifier: _RecordingNotifier,
    *,
    read_failure: Exception | None = None,
) -> Any:
    """The one place to correct if `run_daily_briefing`'s call shape
    differs from what `tasks.md` 4.1/4.4 imply."""
    return await run_daily_briefing(
        read_launch_reports=_ScriptedLaunchReports(reports, failure=read_failure),
        read_product=_FakeCatalog(products),
        notifier=notifier,
        audience=AUDIENCE,
        as_of=AS_OF,
    )


def _at_risk_launch(product_id: ProductId) -> tuple[LaunchPlaybook, Launch]:
    """A launch that yields exactly one (critical) attention item: one
    overdue blocking step, standing at an automatic gate so no
    confirmation is awaited."""
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    return playbook, _launch(playbook, product_id=product_id)


# ---------------------------------------------------------------------------
# Requirement: A clean briefing is not sent
# ---------------------------------------------------------------------------


async def test_a_clean_day_posts_nothing() -> None:
    """Scenario: A clean day posts nothing.

    WHEN the daily briefing is assembled and no attention item exists
    THEN no Slack message SHALL be posted
    AND the run SHALL be recorded as succeeded.

    The launch is healthy on the evaluation date -- an automatic current
    gate and a step not yet due -- so the briefing is clean for the reason
    the requirement is about, rather than because nothing was enumerated.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook,
        _launch(playbook, product_id=product_id, launch_date=HEALTHY_LAUNCH_DATE),
    )
    notifier = _RecordingNotifier()

    # SPECIFIED: the run is recorded as succeeded -- the call returns
    # rather than raising (see the module docstring's reading).
    await _run(reports, {product_id: _active("Widget A", "WIDGET-001")}, notifier)

    # SPECIFIED: no Slack message is posted.
    assert notifier.posted == [], (
        "a clean briefing was delivered, so silent-when-clean does not hold: "
        f"{notifier.posted}"
    )


async def test_a_clean_day_posts_nothing_even_with_no_launches_at_all() -> None:
    """Scenario: A clean day posts nothing -- the empty case.

    DERIVED boundary of the same scenario: an enumeration reporting no
    launches is also a day with no attention item, and is the state the
    system is in before any launch exists. Recorded separately because an
    implementation that posted an "all clear" only in this case would still
    pass the test above.
    """
    notifier = _RecordingNotifier()

    await _run((), {}, notifier)

    assert notifier.posted == []


async def test_a_briefing_with_items_is_delivered() -> None:
    """Scenario: A briefing with items is delivered.

    WHEN the daily briefing is assembled and at least one attention item
    exists
    THEN the system SHALL post one Slack message reporting every item, its
    severity, and its evidence.

    Two products, so "one message reporting *every* item" discriminates
    against an implementation posting one message per item, and against one
    that reports only the first.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    first, second = _new_product_id(), _new_product_id()
    reports = await _reports_for(
        playbook,
        _launch(playbook, product_id=first),
        _launch(playbook, product_id=second),
    )
    notifier = _RecordingNotifier()

    await _run(
        reports,
        {
            first: _active("Widget A", "WIDGET-001"),
            second: _active("Widget B", "WIDGET-002"),
        },
        notifier,
    )

    # SPECIFIED: one Slack message.
    assert len(notifier.posted) == 1, (
        f"expected exactly one message for the whole briefing, got "
        f"{len(notifier.posted)}"
    )
    message = notifier.posted[0]
    # SPECIFIED: reporting every item -- both products' items are in it.
    assert "Widget A" in message
    assert "Widget B" in message
    # SPECIFIED: its severity. DERIVED: read as the severity's own value
    # appearing in the text, case-insensitively, since no artifact fixes
    # how a severity is rendered.
    assert "critical" in message.lower(), (
        f"the message does not report the items' severity; got: {message}"
    )
    # SPECIFIED: its evidence.
    assert "listing.title-conforms" in message, (
        f"the message does not report the items' evidence; got: {message}"
    )


# ---------------------------------------------------------------------------
# Requirement: Items identify products by name and SKU, and never drop an
# item over naming
# ---------------------------------------------------------------------------


async def test_a_resolvable_product_is_named() -> None:
    """Scenario: A resolvable product is named.

    WHEN a briefing item concerns a product the catalog resolves
    THEN the delivered item SHALL show that product's name and SKU.
    """
    product_id = _new_product_id()
    playbook, launch = _at_risk_launch(product_id)
    reports = await _reports_for(playbook, launch)
    notifier = _RecordingNotifier()

    await _run(reports, {product_id: _active("Widget A", "WIDGET-001")}, notifier)

    (message,) = notifier.posted
    # SPECIFIED: the product's name and SKU, both.
    assert "Widget A" in message
    assert "WIDGET-001" in message, (
        f"the delivered item does not show the product's SKU; got: {message}"
    )


async def test_an_unresolvable_product_does_not_lose_its_item() -> None:
    """Scenario: An unresolvable product does not lose its item.

    WHEN a briefing item concerns a product the catalog cannot resolve
    THEN the item SHALL be delivered identifying the product by its raw
    identifier.
    """
    product_id = _new_product_id()
    playbook, launch = _at_risk_launch(product_id)
    reports = await _reports_for(playbook, launch)
    notifier = _RecordingNotifier()

    await _run(reports, {}, notifier)

    # SPECIFIED: the item is still delivered -- a message went out at all.
    assert len(notifier.posted) == 1, (
        "an item was dropped because its product could not be named; the "
        "briefing must fail toward reporting"
    )
    message = notifier.posted[0]
    # SPECIFIED: identified by its raw product identifier.
    #
    # Corrected during apply: this read `str(product_id)`, which is
    # `ProductId`'s dataclass repr (`ProductId(value='...')`) because the
    # value object defines no `__str__`. The requirement says "its raw
    # product identifier", and a Slack line reading `ProductId(value=...)`
    # leaks a Python type name to the ops team rather than naming the
    # product. Asserting the identifier appears *and* that the type name
    # does not is strictly more discriminating than the original, which
    # would have passed only for the leaking rendering.
    assert product_id.value in message, (
        "the delivered item does not identify the unresolvable product by "
        f"its raw identifier; got: {message}"
    )
    assert "ProductId(" not in message, (
        f"the delivered message leaks a Python type name; got: {message}"
    )
    # SPECIFIED (same requirement, carried over): the item itself is intact
    # -- its evidence survives the naming failure.
    assert "listing.title-conforms" in message


async def test_one_unresolvable_product_does_not_take_the_others_with_it() -> None:
    """Requirement statement: "never drop an item over naming".

    DERIVED boundary: a resolvable and an unresolvable product in the same
    briefing. Recorded separately because an implementation that abandoned
    the whole message on a naming failure would still pass the
    single-product scenario above, whose expectation is only that *that*
    item survives.
    """
    resolvable, unresolvable = _new_product_id(), _new_product_id()
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    reports = await _reports_for(
        playbook,
        _launch(playbook, product_id=resolvable),
        _launch(playbook, product_id=unresolvable),
    )
    notifier = _RecordingNotifier()

    await _run(reports, {resolvable: _active("Widget A", "WIDGET-001")}, notifier)

    (message,) = notifier.posted
    assert "Widget A" in message
    # Corrected during apply for the same reason as the scenario above:
    # the raw identifier, not `ProductId`'s dataclass repr.
    assert unresolvable.value in message
    assert "ProductId(" not in message


# ---------------------------------------------------------------------------
# Requirement: Delivery failure is decoupled from the run
# ---------------------------------------------------------------------------


async def test_a_failed_slack_post_does_not_fail_the_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failed Slack post does not fail the run.

    WHEN an assembled briefing's Slack post fails
    THEN the system SHALL log the failure
    AND the run SHALL be recorded as succeeded
    AND the run SHALL NOT be retried.

    SPECIFIED: recorded as succeeded, and not retried -- both read as the
    call returning normally, which is what leaves the job with no failure
    to report and therefore nothing for the retry strategy to act on. A
    raised exception here would contradict both clauses at once.
    DERIVED: "logged" is read as at least one record at WARNING or above,
    since no artifact pins a logger name or a message.
    """
    product_id = _new_product_id()
    playbook, launch = _at_risk_launch(product_id)
    reports = await _reports_for(playbook, launch)
    notifier = _RecordingNotifier(failure=RuntimeError("simulated Slack API failure"))

    with caplog.at_level(logging.WARNING):
        # SPECIFIED: the delivery failure does not propagate.
        await _run(reports, {product_id: _active("Widget A", "WIDGET-001")}, notifier)

    # SPECIFIED: the failure is logged rather than silently swallowed.
    assert any(record.levelno >= logging.WARNING for record in caplog.records), (
        "the Slack delivery failure was neither raised nor logged at "
        f"WARNING or above; captured: {[r.getMessage() for r in caplog.records]}"
    )


async def test_a_read_failure_is_not_swallowed_like_a_delivery_failure() -> None:
    """Requirement: *A failure to assemble is surfaced, not treated like a
    delivery failure* -- the use-case half of its "the run SHALL be
    recorded as failed" clause.

    SPECIFIED by that requirement's contrast with the one above, and by
    `tasks.md` 4.4 ("lets a read failure propagate while only logging a
    delivery failure"). The scenarios themselves are asserted at the job
    level, where retries and the failure message live
    (`test_daily_briefing_job.py`); what is asserted here is the one fact
    that must hold for those to be reachable at all -- that a read failure
    leaves the call raising rather than returning quietly.

    Deliberately not narrowed to the scripted exception type: an
    implementation wrapping the read failure in its own type still records
    the run as failed, and narrowing would assert a type no artifact
    states.
    """
    notifier = _RecordingNotifier()

    with pytest.raises(Exception):  # noqa: B017 -- see the docstring
        await _run(
            (),
            {},
            notifier,
            read_failure=RuntimeError("simulated launch-read failure"),
        )

    # SPECIFIED by "so one outage produces one message": the use case does
    # not itself post on an assembly failure -- that decision belongs to
    # the job, which alone knows whether retries are exhausted.
    assert notifier.posted == []
