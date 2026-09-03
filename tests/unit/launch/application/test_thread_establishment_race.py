"""Thread establishment and mention resolution -- `tasks.md` 8.1 and 8.2.

Derived strictly from the ADDED requirement in `launch-instance`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

Covers:
- Scenario: The first per-product Slack message establishes the thread reference
- Scenario: A concurrent race to establish the thread produces exactly one anchor
- Scenario: Establishing an already-set thread reference changes nothing

Plus, directly against `resolve_mention_target` (`tasks.md` 8.2, `design.md`
— "Mention resolution is one small, shared function: `step`-or-`None` in, a
Slack identity out"): a step naming a confirmer resolves to that confirmer;
a step naming none, and the no-step case, resolve to the launch's
submitter.

## Level

Application tier, against `ensure_launch_thread`
(`launch/application/thread_establishment.py`) directly. It already takes
its store, its lock and its channel as injected callables -- exactly what
lets this be exercised with fakes and no database, per the ports-and-
adapters split `design.md` draws between this operation (which owns none
of those collaborators) and the driving adapters that supply real ones.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Concurrent attempts to establish one launch's thread post exactly one anchor
- Both messages in a race see the same resulting thread reference
- A serial message that comes after the thread exists reuses that reference

INVENTED, recorded in `test-manifest.md`:
- `hold_lock`'s contract is read off `launch_thread_lock.py`'s docstring
  (block until acquired, held until the caller's own transaction ends) and
  faked with a real `asyncio.Lock` per product, released when the fake
  session used to call `ensure_launch_thread` exits -- not with
  `pg_advisory_xact_lock` itself, which the race scenario does not require
  observing directly.

## Correction under `inject-the-thread-anchor-poster`

That change made the anchor's poster an injected port and moved the
anchor's product facts out of the caller and into one read taken at
establishment time. Two consequences here, kept apart on purpose:

- **A harness update.** `_call` passed the six positional arguments the
  operation used to take, so all three scenario tests below broke on the
  new signature even where their assertions were untouched. The helper was
  updated; `test_concurrent_race_produces_one_anchor` and
  `test_serial_establishment_is_idempotent` assert exactly what they
  asserted before.
- **One assertion rewritten.** `test_first_message_establishes_thread`
  passed the three product strings and then asserted they appeared in the
  anchor -- a postcondition satisfied precisely by composing from whatever
  the caller held, which is the defect that change removes. It now asserts
  the anchor names the product the *reader* resolved, which is the same
  scenario grounded in the thing that is now authoritative.

## Correction from the first-run scaffold

The scaffold probed for the operation on `commerce_ops.launch.application`'s
public surface (`__all__`) under several invented names. The real
implementation is `thread_establishment.ensure_launch_thread`, reached
directly by every driving adapter as a same-module import -- not
re-exported through `application/__init__.py`, and under no obligation to
be: the module-layers contract governs cross-module boundaries, and
`thread_establishment.py` and its callers all live in `launch`. This is the
fixture correction that scaffold's own docstring invited; the postconditions
below are what it fixed, unweakened.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final, Self

import pytest

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.application.thread_establishment import (
    ensure_launch_thread,
    resolve_mention_target,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.fixtures import PRODUCT_NAME, product_id

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
PRODUCT_SKU: Final = "BCB-2027-01"
PRODUCT_MARKETPLACE: Final = "ATVPDKIKX0DER"
LAUNCH_DATE: Final = date(2027, 3, 1)
CHANNEL_ID: Final = "C0LAUNCHES"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _launch() -> Launch:
    return Launch(
        product_id=PRODUCT_ID,
        playbook_version="v1",
        current_gate="commit",
        launch_date=LAUNCH_DATE,
        submitter="U0SUBMITTER",
    )


@dataclass
class _FakeLaunchStore:
    """The one launch this file's races are fought over."""

    launch: Launch
    saves: list[str | None] = field(default_factory=list)

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        assert product_id == self.launch.product_id
        return self.launch

    async def save(self, launch: Launch) -> None:
        self.launch = launch
        self.saves.append(launch.slack_thread_id)

    async def list_all(self) -> tuple[Launch, ...]:
        return (self.launch,)


class _FakeSession:
    """Stands in for the real `AsyncSession` `ensure_launch_thread` never
    inspects -- only forwards to `hold_lock`. Doubles as the point at which
    a held advisory lock releases, mirroring `pg_advisory_xact_lock`
    releasing when the caller's transaction ends."""

    def __init__(self) -> None:
        self._on_release: list[Any] = []

    def on_release(self, release: Any) -> None:
        self._on_release.append(release)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        for release in self._on_release:
            release()


class _FakeAdvisoryLock:
    """One real `asyncio.Lock` per product: blocks a second caller until
    the first releases, the same shape `hold_launch_thread_establishment_lock`
    gives `pg_advisory_xact_lock` -- block to acquire, held for the
    transaction's life."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self.acquire_order: list[str] = []

    def _lock_for(self, product_id: ProductId) -> asyncio.Lock:
        return self._locks.setdefault(product_id.value, asyncio.Lock())

    async def hold(self, db_session: _FakeSession, product_id: ProductId) -> None:
        lock = self._lock_for(product_id)
        await lock.acquire()
        self.acquire_order.append(product_id.value)
        db_session.on_release(lock.release)


class _CapturingPoster:
    """Substitutes the injected anchor poster: `(channel, text) -> ts`.

    This used to substitute `thread_establishment._get_slack_client()`'s
    return value, because the operation built its own `AsyncWebClient` from
    a credential and there was no other reachable seam.
    `inject-the-thread-anchor-poster` made the poster a port like the lock
    and the channel already were, so the class-level patching and the
    `lru_cache` reset it needed are both gone. The recorded shape is
    unchanged, so every assertion below reads exactly as it did.
    """

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self._next_ts = 0

    async def __call__(self, channel: str, text: str) -> str:
        self._next_ts += 1
        ts = f"1700000000.{self._next_ts:06d}"
        self.posts.append({"channel": channel, "text": text, "ts": ts})
        return ts


@pytest.fixture()
def poster() -> _CapturingPoster:
    return _CapturingPoster()


#: What the launch's product resolves to. The operation reads the anchor's
#: facts from this now, rather than taking them from its caller -- the whole
#: point of the change -- so the constants below are what the *reader*
#: answers, not what a delivery path happened to be holding.
PRODUCT: Final = Product.register(
    sku=Sku(PRODUCT_SKU),
    marketplace_id=MarketplaceId(PRODUCT_MARKETPLACE),
    name=PRODUCT_NAME,
    registered_at=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
)


async def _call(
    store: _FakeLaunchStore, lock: _FakeAdvisoryLock, poster: _CapturingPoster
) -> str:
    async with _FakeSession() as db_session:
        return await ensure_launch_thread(
            store,
            PRODUCT_ID,
            hold_lock=lambda: lock.hold(db_session, PRODUCT_ID),
            channel=lambda: CHANNEL_ID,
            post_anchor=poster,
            read_product=_resolves_to_the_product,
        )


async def _resolves_to_the_product() -> Any:
    return PRODUCT


async def test_first_message_establishes_thread(poster: _CapturingPoster) -> None:
    """Scenario: The first per-product Slack message establishes the thread.

    WHEN the first message about a launch that has no thread reference is
    delivered
    THEN an anchor message is posted and its identifying reference is
    persisted on the launch record.
    """
    store = _FakeLaunchStore(launch=_launch())
    lock = _FakeAdvisoryLock()

    thread_ts = await _call(store, lock, poster)

    assert len(poster.posts) == 1, (
        f"expected exactly one anchor message, observed: {poster.posts}"
    )
    anchor = poster.posts[0]
    assert anchor["channel"] == CHANNEL_ID
    # The resolved product's facts, not the caller's: `_call` supplies none,
    # and these read off `PRODUCT`, which is what the reader answered.
    assert PRODUCT.name in anchor["text"]
    assert PRODUCT.sku.value in anchor["text"]
    assert PRODUCT.marketplace_id.value in anchor["text"]
    assert thread_ts == anchor["ts"]
    assert store.launch.slack_thread_id == thread_ts, (
        "the returned reference was not persisted on the launch record"
    )


async def test_concurrent_race_produces_one_anchor(poster: _CapturingPoster) -> None:
    """Scenario: A concurrent race to establish the thread produces exactly
    one anchor.

    WHEN two per-product Slack messages are triggered for the same launch
    at the same time, and neither has yet observed a thread reference
    THEN exactly one anchor message is posted, and both messages are
    ultimately delivered against the same, single thread reference.
    """
    store = _FakeLaunchStore(launch=_launch())
    lock = _FakeAdvisoryLock()

    first_ts, second_ts = await asyncio.gather(
        _call(store, lock, poster),
        _call(store, lock, poster),
    )

    assert len(poster.posts) == 1, (
        f"a concurrent race produced more than one anchor message: {poster.posts}"
    )
    assert first_ts == second_ts == poster.posts[0]["ts"], (
        "the two racing callers did not settle on the same thread reference"
    )
    assert store.launch.slack_thread_id == first_ts


async def test_serial_establishment_is_idempotent(poster: _CapturingPoster) -> None:
    """Scenario: Establishing an already-set thread reference changes
    nothing.

    WHEN a per-product Slack message is delivered for a launch that already
    has a thread reference
    THEN no new anchor message is posted, and the existing thread reference
    is reused.
    """
    launch = _launch()
    launch.slack_thread_id = "1700000000.000001"
    store = _FakeLaunchStore(launch=launch)
    lock = _FakeAdvisoryLock()

    thread_ts = await _call(store, lock, poster)

    assert not poster.posts, (
        f"a new anchor was posted for a launch that already had a thread: "
        f"{poster.posts}"
    )
    assert thread_ts == "1700000000.000001"
    assert not store.saves, "an already-set thread reference was re-saved"


# ---------------------------------------------------------------------------
# `resolve_mention_target` -- `tasks.md` 8.2
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StepWithConfirmer:
    """Duck-typed against `resolve_mention_target`'s own reads: the confirmer
    it names, and the identifier a report names it by."""

    confirmer: str | None
    identifier: str = "listing.sub-category"


async def test_a_named_confirmer_is_never_handed_back_as_the_mention() -> None:
    """Corrected by `fix-launch-thread-mentions`. This test used to read:

        step = _StepWithConfirmer(confirmer="U0CONFIRMER")
        assert mention == "U0CONFIRMER"

    which is satisfied by returning `step.confirmer` unchanged -- and that is
    precisely what the implementation did. A step's confirmer holds the
    membership's *own generated identifier*, not a Slack identity, so the shipped
    behaviour rendered `<@3f7c1a92-…>`, which Slack leaves as inert literal
    text. Naming the constant `U0CONFIRMER` is what disguised it: a
    Slack-shaped value in a field that never holds one.

    The full matrix -- resolvable, unknown, deactivated, no Slack identity,
    and the three unreadable-members cases -- lives in
    `tests/unit/launch/application/test_mention_resolution_namespace.py`,
    where the member identifier and the Slack identity are deliberately
    different strings. What remains here is the one property this file is
    placed to guard: no arrangement hands the identifier back.
    """
    member_identifier = "3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30"
    step = _StepWithConfirmer(confirmer=member_identifier)
    launch = _launch()  # submitter="U0SUBMITTER" -- must not win here either

    mention = await resolve_mention_target(launch, step=step)  # type: ignore[arg-type]

    assert mention != member_identifier, (
        "the confirmer was handed back unchanged; that is a member identifier, "
        "which Slack renders as inert literal text and notifies nobody"
    )
    # With no members supplied there is nothing to translate it, so nothing
    # resolves -- and specifically not the submitter, which would make a data
    # gap read exactly like a step naming no confirmer.
    assert mention is None


async def test_a_step_naming_no_confirmer_falls_back_to_the_submitter() -> None:
    step = _StepWithConfirmer(confirmer=None)
    launch = _launch()

    mention = await resolve_mention_target(launch, step=step)  # type: ignore[arg-type]

    assert mention == launch.submitter


async def test_no_step_at_all_falls_back_to_the_submitter() -> None:
    """A gate ask (`gate_confirmation.py`) always calls with no step at
    all, not a step it invented -- this is that case, not a degenerate
    form of the one above."""
    launch = _launch()

    mention = await resolve_mention_target(launch, step=None)

    assert mention == launch.submitter
