"""The anchor is composed from one authoritative read, or not posted at all.

Derived strictly from the MODIFIED requirement in `launch-instance`:
`openspec/changes/inject-the-thread-anchor-poster/specs/launch-instance/spec.md`
— *A launch record establishes and persists its Slack thread once*.

Covers, from that delta:

- Scenario: The first per-product Slack message establishes the thread reference
- Scenario: The anchor names the product the system resolved, not what the
  caller held
- Scenario: A product that cannot be read refuses establishment
- Scenario: A product that resolves to nothing refuses establishment
- Scenario: A refused establishment leaves the next delivery free to establish
- Scenario: A concurrent race to establish the thread produces exactly one anchor
- Scenario: Establishing an already-set thread reference changes nothing
- Scenario: A launch with a thread never reads its product

The two remaining scenarios of the requirement — *The submitter is recorded
at launch start* and *The thread reference starts absent* — are domain-entity
facts the delta does not change, and are covered in
`tests/unit/launch/domain/test_launch_submitter_and_thread.py`. They are not
duplicated here; `test-manifest.md` records where each of the ten lands.

## Why this file is new rather than an edit

`test_thread_establishment_race.py` covers three of these scenarios today,
against the *superseded* rule: it hands `ensure_launch_thread` the product's
name, SKU and marketplace as three loose strings and asserts the anchor names
what the caller passed. The delta says the opposite — the anchor names the
product *as the system resolves it at establishment time*, and a caller's
facts are not what it is composed from. Per `ai-toolkit:testing`, a test that
pins superseded behaviour is reported as superseded, never rewritten, so that
file is left exactly as it is and its entries are listed in
`test-manifest.md`'s obsolete list for human confirmation.

## Level

Application tier, calling `ensure_launch_thread` directly over in-memory
fakes. Every outcome the delta states — an anchor posted or not posted, a
thread reference persisted or not persisted, a product read or not read, and
two concurrent callers settling on one reference — is observable at a plain
function call, which is the smallest unit that can observe it
(`ai-toolkit:testing`, *Choosing the level*). No database, no Slack.

Deliberately **not** covered here, recorded with the reason rather than
omitted:

- That the surrounding `transaction()` rolls back on a refusal, and that
  establishment holds exactly one pooled connection. Neither is stated by the
  delta; both are `tasks.md` 3.6 / 8.6 verification obligations on the
  implementation, and both need a real database.
- The anchor's **wording**, and that it names the launch date. The delta
  states outright that *"What the anchor names is unchanged and is stated by
  `launch-entry`"* and that this clause "governs only where those values come
  from". `launch-entry`'s own scenarios cover what it names.

## What is fixed, and what is DERIVED

Fixed by the delta:

- The anchor is composed from the launch's product as the system resolves it
  at establishment time, read once for that purpose.
- Unreadable, absent, and no-reader-configured are one case, and all three
  refuse: no anchor, no persisted reference, and the delivery fails.
- A refusal does not poison the launch — a later delivery, with a resolvable
  product, establishes normally.
- A launch that already carries a reference reuses it and does not resolve its
  product for the anchor.
- One anchor per launch, including under a concurrent race.

DERIVED — every one of these is an invention of this file, recorded in
`test-manifest.md` as an unresolved project question with its correction
point, because no artifact this file may read fixes it:

- The **names and shapes of the four ports**. `tasks.md` 2.2/3.1 name
  `post_anchor: (channel, text) -> ts` and a nullary `read_product`, and
  `tasks.md` 2.3 removes `db_session` and narrows `hold_lock` to nullary, but
  `tasks.md` is the implementation's plan, not the specification. Correction
  points: `_POSTER_PARAM_NAMES`, `_READER_PARAM_NAMES`, `_LOCK_PARAM_NAMES`,
  `_CHANNEL_PARAM_NAMES`, and `_call_shape`. The probe reflects over the real
  signature and fails naming it, rather than silently passing an argument the
  function ignores.
- That refusal is signalled by **raising**, and that the exception names the
  product identifier. The delta says the delivery "fails and is reported";
  raising is the mechanism `tasks.md` 3.4 chooses. Correction point:
  `_REFUSAL`.
- That the resolved product exposes `name`, `sku.value` and
  `marketplace_id.value`. Not invented so much as taken from the real
  `catalog.domain.product.Product`, which is what the composition roots'
  readers answer — deliberately, so a double cannot satisfy a check the real
  store would not (`tasks.md` 3.5).
- That the poster is handed the channel the `channel` port resolves. The
  delta does not mention the channel; `design.md` keeps the two ports
  separate so the "the anchor is a top-level message" rule stays in the layer
  that states it.

## Expected first-run state

Every test in this file is expected to FAIL before the change is
implemented, and most of them as `ai-toolkit:testing`'s failure state 2
(absent target): `ensure_launch_thread` today takes a session, a store, a
product identifier and three loose product strings, and posts through a
module-level Slack client, so `_call_shape` fails its bind and reports the
signature it actually found. That establishes absence and nothing more —
none of the assertions below will have executed.

Baseline, taken before any of this was written: `uv run pytest` on this tree
— 2064 passed, 135 skipped, 0 failed; `uv run pytest tests/unit/launch` —
1294 passed, 0 skipped, 0 failed.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Final, Self

import pytest

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.application import thread_establishment
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

pytestmark = pytest.mark.anyio

#: The operation under test, held as `Any` on purpose.
#:
#: Its signature is what this change alters, so a statically-typed call would
#: make `mypy` — not the test run — the thing that reports the shape, and it
#: would report it identically for "not implemented yet" and "implemented
#: wrongly". `_call_shape` below binds against the real signature at runtime
#: and fails naming it, which distinguishes the two. `ai-toolkit:testing`'s
#: failure states are readable only if the failure comes from the test.
_ensure_launch_thread: Final[Any] = thread_establishment.ensure_launch_thread


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixture vocabulary
# ---------------------------------------------------------------------------

#: A real `Product`, not a double. `tasks.md` 3.5 forbids `getattr`
#: tolerances on the resolved product precisely so a double modelling less
#: than the real aggregate cannot satisfy a check the real store would fail;
#: the cheapest way to hold that line from the test side is to hand the port
#: what the composition roots' readers actually answer.
PRODUCT: Final = Product.register(
    sku=Sku("BCB-2027-01"),
    marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
    name="Bamboo Cutting Board",
    registered_at=datetime(2026, 8, 23, 9, 0, tzinfo=UTC),
)
PRODUCT_ID: Final[ProductId] = PRODUCT.id

LAUNCH_DATE: Final = date(2027, 3, 1)
SUBMITTER: Final = "U0SUBMITTER"
CHANNEL_ID: Final = "C0LAUNCHES"
EXISTING_THREAD_TS: Final = "1700000000.000001"

#: DERIVED. The delta says a refused delivery "fails and is reported";
#: `tasks.md` 3.4 chooses a plain `RuntimeError` naming the product, over a
#: new exception type no caller would catch. Single correction point.
_REFUSAL: Final = RuntimeError


def _launch(*, slack_thread_id: str | None = None) -> Launch:
    return Launch(
        product_id=PRODUCT_ID,
        playbook_version="v1",
        current_gate="commit",
        launch_date=LAUNCH_DATE,
        submitter=SUBMITTER,
        slack_thread_id=slack_thread_id,
    )


# KEPT LOCAL by `share-the-aggregate-fakes` (task 5.7). A `@dataclass` where
# the shared store is a plain class -- a declaration-form mismatch is a keep
# under `AGENTS.md` -- and it carries an internal assertion and a `saves`
# recorder the shared store has not.
@dataclass
class _FakeLaunchStore:
    """The one launch every scenario in this file is about."""

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


# ---------------------------------------------------------------------------
# The ports, and the signature probe that binds them
# ---------------------------------------------------------------------------

_POSTER_PARAM_NAMES: Final = ("post_anchor", "post", "poster", "post_message")
_READER_PARAM_NAMES: Final = ("read_product", "product_reader", "read_catalog_product")
_LOCK_PARAM_NAMES: Final = ("hold_lock", "lock")
_CHANNEL_PARAM_NAMES: Final = ("channel", "channel_id")

#: Parameters the delta's second clause forbids: the operation must not be
#: able to be handed product facts by whichever delivery path got there
#: first. `db_session` is here for a different reason (`tasks.md` 2.3, the
#: application layer naming SQLAlchemy) and is not asserted on by the
#: scenario tests — only by the structural test below, which says which of
#: the two grounds each name is on.
_CALLER_SUPPLIED_PRODUCT_FACTS: Final = (
    "product_name",
    "product_sku",
    "product_marketplace",
)


def _parameter(candidates: tuple[str, ...]) -> str:
    """The real parameter name for one of this operation's ports."""
    parameters = inspect.signature(_ensure_launch_thread).parameters
    for candidate in candidates:
        if candidate in parameters:
            return candidate
    pytest.fail(
        f"`ensure_launch_thread` takes no parameter named any of {candidates}; "
        f"its signature is {inspect.signature(_ensure_launch_thread)}. If the "
        "port landed under another name, add it to this file's candidate "
        "tuple — do not weaken the assertions below."
    )


class _RecordingPoster:
    """The anchor poster port: `(channel, text) -> ts`.

    Tolerant about *how* it is called — positionally or by keyword — because
    the calling convention is not something the delta fixes; strict about
    what it records, which is what the assertions read.
    """

    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []
        self._posted = 0

    @property
    def timestamps(self) -> list[str]:
        return [f"1700000000.{index + 1:06d}" for index in range(self._posted)]

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        channel = kwargs.get("channel", args[0] if args else None)
        text = kwargs.get(
            "text",
            kwargs.get("message", args[1] if len(args) > 1 else None),
        )
        assert isinstance(channel, str), (
            f"the anchor poster was handed a non-string channel: {channel!r}"
        )
        assert isinstance(text, str), (
            f"the anchor poster was handed a non-string body: {text!r}"
        )
        self._posted += 1
        self.posts.append((channel, text))
        return f"1700000000.{self._posted:06d}"


class _PosterThatMustNotBeCalled:
    def __init__(self) -> None:
        self.posts: list[tuple[str, str]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> str:
        self.posts.append((str(args), str(kwargs)))
        raise AssertionError(
            "an anchor was posted where the delta requires none: "
            f"args={args!r} kwargs={kwargs!r}"
        )


class _ProductReaderMustNotBeConsulted(Exception):
    """Raised by the reader in the scenario that forbids reading at all.

    A reader that *fails when called* is what that scenario asks for — not a
    call counter checked afterwards, which a refusal path could reach before
    the assertion ran.
    """


@dataclass
class _RecordingReader:
    """The product-resolution port. Nullary: the adapter binds the session."""

    product: Any
    reads: int = 0

    async def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.reads += 1
        return self.product


@dataclass
class _FailingReader:
    """A catalog read that raises — the "unreadable" half of one case."""

    reads: int = 0

    async def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        self.reads += 1
        raise ConnectionError("the catalog is unreachable")


class _ForbiddenReader:
    async def __call__(self, *_args: Any, **_kwargs: Any) -> Any:
        raise _ProductReaderMustNotBeConsulted(
            "the product was resolved for a launch that already carries a "
            "thread reference"
        )


class _Transaction:
    """Stands in for the establishing adapter's own transaction.

    `hold_launch_thread_establishment_lock` blocks until the advisory lock is
    acquired and holds it until the caller's transaction ends. This models
    that: `hold` is the nullary port `ensure_launch_thread` awaits, and the
    lock releases on `__aexit__`, not on return.
    """

    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock
        self._held = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._held:
            self._lock.release()
            self._held = False

    async def hold(self, *_args: Any, **_kwargs: Any) -> None:
        await self._lock.acquire()
        self._held = True


class _AdvisoryLocks:
    """One real `asyncio.Lock` per product, as `pg_advisory_xact_lock` is."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def transaction(self, product_id: ProductId) -> _Transaction:
        return _Transaction(self._locks.setdefault(product_id.value, asyncio.Lock()))


def _call_shape(**ports: Any) -> dict[str, Any]:
    """Bind this file's ports onto the real signature, or fail naming it."""
    kwargs = {
        _parameter(_LOCK_PARAM_NAMES): ports["hold_lock"],
        _parameter(_CHANNEL_PARAM_NAMES): ports["channel"],
        _parameter(_POSTER_PARAM_NAMES): ports["post_anchor"],
        _parameter(_READER_PARAM_NAMES): ports["read_product"],
    }
    try:
        inspect.signature(_ensure_launch_thread).bind(
            ports["store"], PRODUCT_ID, **kwargs
        )
    except TypeError as error:
        pytest.fail(
            "`ensure_launch_thread` cannot be called as "
            "`(launch_store, product_id, *, <four ports>)`, which is the shape "
            "the delta's second and third clauses require — the operation "
            "resolves the product itself and posts through an injected "
            f"poster. Bind failed with: {error}. Its signature is "
            f"{inspect.signature(_ensure_launch_thread)}."
        )
    return kwargs


async def _establish(
    store: _FakeLaunchStore,
    locks: _AdvisoryLocks,
    *,
    post_anchor: Any,
    read_product: Any,
    channel: Any = None,
) -> str:
    async with locks.transaction(PRODUCT_ID) as transaction:
        kwargs = _call_shape(
            store=store,
            hold_lock=transaction.hold,
            channel=channel if channel is not None else (lambda: CHANNEL_ID),
            post_anchor=post_anchor,
            read_product=read_product,
        )
        thread_ts = await _ensure_launch_thread(store, PRODUCT_ID, **kwargs)
    assert isinstance(thread_ts, str), (
        f"the operation answered something other than a thread reference: {thread_ts!r}"
    )
    return thread_ts


# ---------------------------------------------------------------------------
# Scenario: The anchor names the product the system resolved, not what the
# caller held — the structural half
# ---------------------------------------------------------------------------


def test_the_operation_accepts_no_product_facts_from_its_caller() -> None:
    """SPECIFIED (delta, clause 2): the anchor "SHALL NOT be composed from
    product facts supplied by whichever delivery path happens to be
    establishing the thread".

    The behavioural half is the test below it. This half is what makes the
    guarantee unconditional: a parameter that can carry a caller's product
    name is a parameter some future call site will fill, and the delta's
    reason — that a path supplying less than another would make the launch's
    permanent header depend on which message arrived first — bites on the
    *possibility*, not only on today's four call sites.

    `db_session` is asserted on the neighbouring ground that `tasks.md` 2.3
    states (the application layer must stop naming SQLAlchemy); it is noted
    in `test-manifest.md` as DERIVED, not read out of the delta.
    """
    parameters = inspect.signature(_ensure_launch_thread).parameters

    supplied = [name for name in _CALLER_SUPPLIED_PRODUCT_FACTS if name in parameters]
    assert not supplied, (
        f"`ensure_launch_thread` still accepts {supplied} from its caller; the "
        "delta requires the anchor to be composed from the product the system "
        "resolves at establishment time, not from what a delivery path held"
    )

    assert "db_session" not in parameters, (
        "`ensure_launch_thread` still takes a session (DERIVED from "
        "`tasks.md` 2.3, not from the delta): the lock is a port and can "
        "close over the adapter's own session"
    )


# ---------------------------------------------------------------------------
# Scenario: The first per-product Slack message establishes the thread
# reference
# ---------------------------------------------------------------------------


async def test_the_first_message_establishes_the_thread_reference() -> None:
    """SPECIFIED.

    WHEN the first message about a launch that has no thread reference is
    delivered
    THEN an anchor message is posted and its identifying reference is
    persisted on the launch record.
    """
    store = _FakeLaunchStore(launch=_launch())
    poster = _RecordingPoster()
    reader = _RecordingReader(product=PRODUCT)

    thread_ts = await _establish(
        store, _AdvisoryLocks(), post_anchor=poster, read_product=reader
    )

    assert len(poster.posts) == 1, (
        f"expected exactly one anchor message, observed: {poster.posts}"
    )
    assert thread_ts == poster.timestamps[0], (
        "the reference returned is not the one the anchor was posted under"
    )
    assert store.launch.slack_thread_id == thread_ts, (
        "the returned reference was not persisted on the launch record"
    )


# ---------------------------------------------------------------------------
# Scenario: The anchor names the product the system resolved, not what the
# caller held — the behavioural half
# ---------------------------------------------------------------------------


async def test_the_anchor_names_the_product_the_system_resolved() -> None:
    """SPECIFIED.

    WHEN a delivery path that holds no product facts, or partial ones,
    establishes a launch's thread
    THEN the anchor names the product, SKU and marketplace as resolved from
    the launch's product at establishment time.

    The caller here holds nothing at all — which, after the structural test
    above, is the only kind of caller there is. What makes the assertion
    discriminating is that the three values appear in the anchor *and* come
    from the port: nothing else in this call knows them, and the launch
    record carries none of them.
    """
    store = _FakeLaunchStore(launch=_launch())
    poster = _RecordingPoster()
    reader = _RecordingReader(product=PRODUCT)

    await _establish(store, _AdvisoryLocks(), post_anchor=poster, read_product=reader)

    assert reader.reads == 1, (
        "the delta requires the launch's product to be read once, at "
        f"establishment time, for the anchor's purpose; it was read "
        f"{reader.reads} times"
    )
    channel, anchor = poster.posts[0]
    assert PRODUCT.name in anchor, (
        f"the anchor does not name the resolved product: {anchor!r}"
    )
    assert PRODUCT.sku.value in anchor, (
        f"the anchor does not name the resolved product's SKU: {anchor!r}"
    )
    assert PRODUCT.marketplace_id.value in anchor, (
        f"the anchor does not name the resolved product's marketplace: {anchor!r}"
    )
    # DERIVED: the anchor is a top-level message in the channel the `channel`
    # port resolves. `design.md` keeps poster and channel as two ports for
    # exactly this reason; the delta itself does not mention the channel.
    assert channel == CHANNEL_ID


# ---------------------------------------------------------------------------
# Scenario: A product that cannot be read refuses establishment
# ---------------------------------------------------------------------------


async def test_a_product_read_that_fails_refuses_establishment() -> None:
    """SPECIFIED.

    WHEN a per-product message would establish a launch's thread and the
    launch's product cannot be read
    THEN no anchor is posted, no thread reference is persisted, and the
    delivery fails and is reported.
    """
    store = _FakeLaunchStore(launch=_launch())
    poster = _PosterThatMustNotBeCalled()
    reader = _FailingReader()

    with pytest.raises(_REFUSAL) as refusal:
        await _establish(
            store, _AdvisoryLocks(), post_anchor=poster, read_product=reader
        )

    assert reader.reads == 1, "the product read was not even attempted"
    assert not poster.posts, (
        f"an anchor was posted despite an unreadable product: {poster.posts}"
    )
    assert store.launch.slack_thread_id is None, (
        "a thread reference was persisted for a launch whose anchor could not "
        "be composed; the delta requires the launch to be left with none"
    )
    assert not store.saves, "the launch record was saved on a refused establishment"
    # DERIVED (`tasks.md` 3.4): the refusal names the product it could not
    # resolve, so an operator reading the report can tell which launch is
    # waiting.
    assert PRODUCT_ID.value in str(refusal.value), (
        f"the refusal does not name the product: {refusal.value!r}"
    )


async def test_an_unconfigured_product_reader_refuses_establishment() -> None:
    """SPECIFIED. The delta puts three cases together in as many words: "A
    product that is unreadable, absent, or whose reader is not configured are
    one case and SHALL be treated alike: the system cannot say what the
    product is."

    This is the third of them, and it is the one with an operational edge: a
    composition root that forgot to wire the reader would, under any
    degrading policy, post blank anchors forever. Under this one it posts
    none.

    It is deliberately the *opposite* disposition from an absent members
    reader, which still delivers the message untagged
    (`tests/unit/launch/application/test_mention_resolution_namespace.py`).
    The two globals live four lines apart in `launch_thread_delivery`, so the
    pair is named here rather than left to be inferred.
    """
    store = _FakeLaunchStore(launch=_launch())
    poster = _PosterThatMustNotBeCalled()

    with pytest.raises(_REFUSAL):
        await _establish(store, _AdvisoryLocks(), post_anchor=poster, read_product=None)

    assert not poster.posts, (
        f"an anchor was posted with no product reader configured: {poster.posts}"
    )
    assert store.launch.slack_thread_id is None
    assert not store.saves


# ---------------------------------------------------------------------------
# Scenario: A product that resolves to nothing refuses establishment
# ---------------------------------------------------------------------------


async def test_a_product_that_resolves_to_nothing_refuses_establishment() -> None:
    """SPECIFIED.

    WHEN a per-product message would establish a launch's thread and the
    launch's product resolves to nothing
    THEN no anchor is posted, no thread reference is persisted, and the
    delivery fails and is reported.

    Distinct from the raising case above and asserted separately, because
    answering `None` is the shape that a degrading implementation swallows
    without any error to notice.
    """
    store = _FakeLaunchStore(launch=_launch())
    poster = _PosterThatMustNotBeCalled()
    reader = _RecordingReader(product=None)

    with pytest.raises(_REFUSAL):
        await _establish(
            store, _AdvisoryLocks(), post_anchor=poster, read_product=reader
        )

    assert reader.reads == 1
    assert not poster.posts, (
        f"an anchor was posted for a product that resolved to nothing: {poster.posts}"
    )
    assert store.launch.slack_thread_id is None
    assert not store.saves


# ---------------------------------------------------------------------------
# Scenario: A refused establishment leaves the next delivery free to
# establish
# ---------------------------------------------------------------------------


async def test_a_refused_establishment_leaves_the_next_delivery_free() -> None:
    """SPECIFIED.

    WHEN establishment was refused because the product could not be resolved,
    and a later message for the same launch is delivered while the product
    can be resolved
    THEN that message establishes the thread and posts a complete anchor.

    This is what bounds the refusal policy's cost: the delay is recoverable,
    where a blank anchor would not be. A refusal that left any mark on the
    launch — a sentinel reference, a "tried once" flag — would fail here.
    """
    store = _FakeLaunchStore(launch=_launch())
    locks = _AdvisoryLocks()
    poster = _RecordingPoster()

    with pytest.raises(_REFUSAL):
        await _establish(
            store, locks, post_anchor=poster, read_product=_FailingReader()
        )

    reader = _RecordingReader(product=PRODUCT)
    thread_ts = await _establish(store, locks, post_anchor=poster, read_product=reader)

    assert len(poster.posts) == 1, (
        f"the recovering delivery did not post exactly one anchor: {poster.posts}"
    )
    _, anchor = poster.posts[0]
    assert PRODUCT.name in anchor
    assert PRODUCT.sku.value in anchor
    assert PRODUCT.marketplace_id.value in anchor
    assert store.launch.slack_thread_id == thread_ts


# ---------------------------------------------------------------------------
# Scenario: A concurrent race to establish the thread produces exactly one
# anchor
# ---------------------------------------------------------------------------


async def test_a_concurrent_race_produces_exactly_one_anchor() -> None:
    """SPECIFIED.

    WHEN two per-product Slack messages are triggered for the same launch at
    the same time, and neither has yet observed a thread reference
    THEN exactly one anchor message is posted, and both messages are
    ultimately delivered against the same, single thread reference.

    Unchanged by this delta in what it requires, and re-asserted here under
    the new call shape rather than left to the superseded file. The reader
    count is the delta's own addition to it: the losing caller returns before
    the read, so the product is resolved once per launch, not once per racing
    message.
    """
    store = _FakeLaunchStore(launch=_launch())
    locks = _AdvisoryLocks()
    poster = _RecordingPoster()
    reader = _RecordingReader(product=PRODUCT)

    first_ts, second_ts = await asyncio.gather(
        _establish(store, locks, post_anchor=poster, read_product=reader),
        _establish(store, locks, post_anchor=poster, read_product=reader),
    )

    assert len(poster.posts) == 1, (
        f"a concurrent race produced more than one anchor: {poster.posts}"
    )
    assert first_ts == second_ts == poster.timestamps[0], (
        "the two racing callers did not settle on the same thread reference"
    )
    assert store.launch.slack_thread_id == first_ts
    assert reader.reads == 1, (
        "the launch's product was resolved for the anchor more than once; the "
        "delta requires it read once, at establishment time, and the caller "
        f"that loses the race must return before reading it ({reader.reads} "
        "reads)"
    )


# ---------------------------------------------------------------------------
# Scenario: Establishing an already-set thread reference changes nothing
# ---------------------------------------------------------------------------


async def test_an_already_set_thread_reference_is_reused() -> None:
    """SPECIFIED.

    WHEN a per-product Slack message is delivered for a launch that already
    has a thread reference
    THEN no new anchor message is posted, and the existing thread reference
    is reused.
    """
    store = _FakeLaunchStore(launch=_launch(slack_thread_id=EXISTING_THREAD_TS))
    poster = _PosterThatMustNotBeCalled()
    reader = _RecordingReader(product=PRODUCT)

    thread_ts = await _establish(
        store, _AdvisoryLocks(), post_anchor=poster, read_product=reader
    )

    assert not poster.posts, (
        f"a second anchor was posted for a launch that already had a thread: "
        f"{poster.posts}"
    )
    assert thread_ts == EXISTING_THREAD_TS
    assert not store.saves, "an already-set thread reference was re-saved"


# ---------------------------------------------------------------------------
# Scenario: A launch with a thread never reads its product
# ---------------------------------------------------------------------------


async def test_a_launch_with_a_thread_never_reads_its_product() -> None:
    """SPECIFIED.

    WHEN a per-product Slack message is delivered for a launch that already
    has a thread reference and whose product cannot be read
    THEN the existing thread reference is reused, no product is resolved for
    the anchor, and the message is delivered.

    This is the scenario that bounds the whole change's risk surface: every
    launch already carrying a thread — which is every launch after its first
    message — is unaffected by whatever the catalog is doing. It is asserted
    with a reader that *fails if consulted* rather than with a call count,
    so an implementation that reads before the early return cannot reach a
    later assertion at all.
    """
    store = _FakeLaunchStore(launch=_launch(slack_thread_id=EXISTING_THREAD_TS))
    poster = _PosterThatMustNotBeCalled()

    thread_ts = await _establish(
        store, _AdvisoryLocks(), post_anchor=poster, read_product=_ForbiddenReader()
    )

    assert thread_ts == EXISTING_THREAD_TS, (
        "the existing thread reference was not reused"
    )
    assert not poster.posts
    assert not store.saves


async def test_a_launch_with_a_thread_is_unaffected_by_an_absent_reader() -> None:
    """SPECIFIED, same scenario, its second reading: "a launch with a thread
    is unaffected by whether the product can be resolved" covers the
    unconfigured reader too, not only the failing one.

    Asserted separately from the test above because the two failures reach
    the early return by different routes: one would raise inside the read,
    the other would raise instead of reading. An implementation that checked
    `read_product is None` *before* the early return would pass the test
    above and fail this one.
    """
    store = _FakeLaunchStore(launch=_launch(slack_thread_id=EXISTING_THREAD_TS))
    poster = _PosterThatMustNotBeCalled()

    thread_ts = await _establish(
        store, _AdvisoryLocks(), post_anchor=poster, read_product=None
    )

    assert thread_ts == EXISTING_THREAD_TS
    assert not poster.posts
    assert not store.saves


def test_the_fixture_product_is_the_real_aggregate() -> None:
    """A guard on this file's own fixture, not on the change.

    `tasks.md` 3.5 forbids `getattr` tolerances on the resolved product,
    reasoning that a double modelling less than the real aggregate would let
    a test pass a check the real store fails. That reasoning only holds while
    this file keeps handing the port a real `Product`; if someone later
    replaces it with a dataclass double to make a test easier, this says so.
    """
    assert isinstance(PRODUCT, Product)
    assert uuid.UUID(PRODUCT_ID.value), "the fixture product carries no real identifier"
