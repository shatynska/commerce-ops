"""The stateful doubles the suite arranges around.

A fake here stands in for a production collaborator and **is not one**. It holds
state, answers queries and records writes; `values.py` beside it holds the
doubles that only carry fields.

**Every fake here reproduces the behaviour a measured population had.** A
parameter no measured declaration needed is not added because it might be
wanted, and a spelling the locals carried is dropped only where it has been
measured dead across both `src/` and `tests/` -- three of them, listed in
`share-the-stateful-fakes`'s design as clause (e) and nowhere extended.

**Declaration form is part of the contract, and for two of these it is the whole
substance.** `StubDate` subclasses `date` and `FakeSlackResponse` subclasses
`dict`: a `StubDate` that is not a `date` fails the `isinstance` checks inside
production date handling, and a `FakeSlackResponse` that is not a `dict` cannot
be indexed by the Slack SDK that receives it. Neither exposes an instance method
for the lockstep proof to intercept, so both migrate on their base class, `mypy`
and the contract tests under `tests/unit/support/` -- recorded there rather than
left to look like a proof that passed.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any, ClassVar

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import ProductId


class FakeSlackResponse(dict[str, Any]):
    """What a stubbed `AsyncWebClient.api_call` answers with.

    A `dict` subclass, because that is what the Slack SDK's own
    `AsyncSlackResponse` is indexed as by everything downstream of it -- the
    base class is the substance, and a fake that merely *held* a payload would
    not answer `response["view"]`.

    `data` is the SDK's own spelling for the payload, and this double carries it
    because all 13 local declarations did. **Measured, nothing in `src/` or
    `tests/` reads it** -- a fourth candidate for the treatment clause (e) gives
    `members`, `__call__` and `__iter__`. It is kept anyway: that clause names
    its three cases rather than a category, precisely so it cannot be widened
    at implementation time by whoever next finds an unread spelling.
    """

    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class FakeHandlers:
    """The step-handler registry, in the both-shapes form the suite records.

    A container answering `__contains__` and `names()`, plus `resolve` and
    `get`. `automation_pass:770` asks the membership question directly --
    `name in handlers` -- and resolves only then, so `__contains__` is a call
    production makes rather than a convention it probes for; both
    `_registered_names` sites read `names()`, which every one of the eight local
    declarations provided, so nothing this fake carries displaces a branch.

    `resolve` raises `KeyError` for a name it never held and `get` answers the
    default, matching the eight and matching production's own comment that
    "`resolve` is free to raise for a name it never held".
    """

    def __init__(self, **handlers: Any) -> None:
        self._handlers = dict(handlers)

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def resolve(self, name: str) -> Any:
        return self._handlers[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self._handlers.get(name, default)


class StubDate(date):
    """`date` with a fixed `today()`, for a page whose rendering reads it.

    A `date` subclass, because the call sites substitute the *class* --
    `monkeypatch.setattr(module, "date", _StubDate)` -- and production goes on
    constructing and comparing dates through it. A stand-in that merely held a
    day would fail the first `date(...)` call the module makes.

    **`_today` has no default, deliberately.** All 15 local declarations set it
    from a module-level `RENDER_DATE` the file owns, and every one of those is a
    per-module constant rather than a shared one -- the parent slice's rule that
    a per-module constant does not become a shared constant. So each file keeps
    a two-line subclass setting its own day, and this class is never used
    directly.

    Like `FakeSlackResponse`, it exposes no instance method: the lockstep proof
    has nothing to intercept, so this one migrates on its base class, `mypy` and
    the contract tests under `tests/unit/support/`.
    """

    _today: ClassVar[date]

    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return cls._today


class InertBackoff:
    """The automated-step backoff record, answering nothing to everything.

    Seven of the nine declarations this replaces carried all four methods and
    two carried `mark_reported` alone. The shared fake carries all four, which
    gives those two a surface they did not have -- **governed by the same-value
    invariant, and checked rather than assumed**. Production calls every one of
    the four by name at `automation_pass:404`, `:531`, `:673` and `:713`; no
    site probes for them with `getattr` or guards on `hasattr`, so nothing falls
    through and no branch moves. What changes for those two files is only that a
    path which would have raised `AttributeError` now returns `None` -- and no
    test reaches such a path, or it would be failing today.

    `read` answers `None`, which is what the seven answered and what production
    reads as "no backoff recorded for this step".
    """

    async def read(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def note(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeHandlerRegistry:
    """A step-handler registry read only for the names it registers.

    `FakeHandlers` beside it is the same subject with a `resolve`; this one is
    the population that answers the membership and naming questions alone, and
    it returns a `frozenset` where that one returns a tuple, because that is
    what its twelve local declarations returned.

    **It does not carry `__iter__`, and all twelve locals did.** Both
    `_registered_names` sites -- `activation_readiness:150` and
    `playbook_authoring:389` -- iterate the registry only when `names` is not
    callable, and every local provided `names()`; `automation_pass:770`'s
    `name in handlers` reaches `__contains__`, which all twelve declared, so
    membership never falls back to iteration either. Measured statically, and
    then by execution: making every local `__iter__` raise leaves the whole
    commit tier green. That is the clause (e) licence, and it is the strongest
    of the three -- the other two rest on a static reading alone.
    """

    def __init__(self, names: frozenset[str] = frozenset()) -> None:
        self._names = names

    def __contains__(self, name: object) -> bool:
        return name in self._names

    def names(self) -> frozenset[str]:
        return self._names


class FakeStepStore[RowT]:
    """The playbook's step set, held in memory with its version.

    Mirrors the port `playbook_authoring` declares: `load()` answers the rows
    and the version, `save()` replaces them and moves the version on.

    **It asserts on a stale write, and eighteen of the thirty-seven local
    declarations did not.** That is a deliberate strengthening rather than a
    reproduction: a fake that silently accepts `expected_version` from an
    earlier read is a fake that hides the optimistic-concurrency defect the
    real store exists to catch. The lockstep proof is what makes the
    strengthening safe to take -- a file whose test saves against a stale
    version fails loudly at the instrument commit, where the local's silence is
    compared against this assertion, and keeps its own declaration.

    **It records `saves` and eleven locals did not.** A licensed superset: no
    production reader probes the attribute, so a file that never reads it
    cannot tell.

    **Generic in its row type, and each file binds the parameter its own local
    declaration bound.** The thirty-seven locals annotated `records` three ways
    -- `_Record`, `_StepRecord` and `Any` -- and seven files then read a row
    back out through a helper declaring the concrete return type. A shared store
    fixed at `tuple[Any, ...]` makes those seven helpers return `Any` from a
    function declared otherwise, which `mypy --strict` refuses. So the settle
    line is `_FakeStepStore = FakeStepStore[_Record]` rather than a bare alias,
    read off the local's own annotation, and every annotation site in the file
    keeps the type it had.
    """

    def __init__(self, records: tuple[RowT, ...] = (), version: int = 41) -> None:
        self.records = tuple(records)
        self.version = version
        self.saves: list[tuple[tuple[RowT, ...], int]] = []

    async def load(self) -> tuple[tuple[RowT, ...], int]:
        return (self.records, self.version)

    async def save(self, records: Iterable[RowT], *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(records)
        self.saves.append((stored, expected_version))
        self.records = stored
        self.version += 1


class FakeMembersStore:
    """The membership, held in memory with its version.

    The same port shape as `FakeStepStore` -- `load()` answers the rows and the
    version, `save()` replaces them and moves the version on -- for the set
    `access.application.members` edits. It is a separate declaration rather than
    the same one because the two populations disagree on the opening version
    (13 against 41) and on the parameter's name, and a shared type bent across
    both would take a default from one of them arbitrarily.

    Unlike the step store it is **not generic**: all 38 local declarations
    annotated `rows` as `tuple[Any, ...]`, so there is no row type to bind.

    **It asserts on a stale write, and thirty of the thirty-eight did not.** As
    with the step store, a deliberate strengthening the lockstep proof makes
    safe to take: a file that saves against a version it did not read fails at
    the instrument commit rather than passing quietly forever.
    """

    def __init__(self, rows: tuple[Any, ...] = (), version: int = 13) -> None:
        self.rows = tuple(rows)
        self.version = version
        self.saves: list[tuple[tuple[Any, ...], int]] = []

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return (self.rows, self.version)

    async def save(self, rows: Any, *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        stored = tuple(rows)
        self.saves.append((stored, expected_version))
        self.rows = stored
        self.version += 1


class FakeCatalogPort:
    """The catalog's two reads, over a fixed set of products.

    `fails` makes both reads raise, which is the outage *Product identities
    cannot be read at all* is about; a product absent from `products` is one the
    catalog cannot resolve, and `get_product_by_id` answers `None` for it.

    **`fails` is a superset over eight of the sixteen locals**, and a licensed
    one: it is a constructor keyword defaulting `False`, reachable only where a
    call site sets it, and no production reader probes for the attribute --
    searched across `src/` at the commit that added it. The eight that never
    pass it cannot tell it is there.

    The two reads take `*_args, **_kwargs` after the identifier because the
    call sites pass a scope the double does not model; two declarations in the
    population go further and *sniff* their arguments for a `ProductId`, which
    is a different behaviour and keeps them out of this fake.
    """

    def __init__(self, *products: Product, fails: bool = False) -> None:
        self.products = tuple(products)
        self.fails = fails

    async def get_product_by_id(
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Product | None:
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
        for product in self.products:
            if product.id == product_id:
                return product
        return None

    async def list_products(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
        if self.fails:
            raise ConnectionError("the catalog store is unreachable")
        return self.products


class FakeLaunches:
    """The launch store, over the launches it is handed -- 58 declarations
    under two names that never appear in the same file.

    **`list_active` deliberately does not filter graduated launches, and that
    is the most load-bearing line in this class.** The real repository's
    `list_active` drops launches standing at `graduated`
    (`launch_repository.py:181`), and reproducing that here is the obvious
    "truer to production" move. It is wrong.
    `test_automation_pass.py::test_a_graduated_launch_is_left_alone` hands a
    graduated launch to this double precisely to prove *the pass* leaves it
    alone; a filtering double removes the launch before the pass ever sees it
    and **every assertion in that test still passes**. The requirement is
    specified in two capabilities -- `launch-step-automation` and
    `launch-clickup-sync` both carry *A graduated launch is left alone* -- so
    filtering here would leave both unverified while the suite stayed green.
    Neither proof instrument can see it: values and calls are identical either
    way. **A shared double must not implement the filter its subject is being
    tested for.**

    **`list_launches` and `all` are absent.** 21 of the 26 `_FakeLaunchStore`
    declarations carried them as delegates to `list_all`. Nothing in `src/`
    calls either, every `tests/` mention was their own `def`, and the licence
    was taken by execution rather than by search: mutating all 42 to raise left
    both tiers green.

    The reads answer a `tuple`, which 46 of the 60 local annotations use and
    which `FakeCatalogPort.list_products` already spells.
    """

    def __init__(self, *launches: Any) -> None:
        #: **`launches` is the stored spelling, and `stored` is derived over the
        #: same list.** Measured across `tests/`: two files *assign*
        #: `store.launches = snapshot` to restore a rolled-back state, and a
        #: read-only property cannot receive an assignment -- `AGENTS.md`'s
        #: `Member.id` precedent. Fourteen sites read `stored` and none assigns
        #: it, so that is the derived one.
        self.launches: list[Any] = list(launches)

    #: Set by `serving` on the subclass it builds; read at call time.
    _source: ClassVar[Any] = None

    @classmethod
    def serving(cls, source: Any) -> type[FakeLaunches]:
        """A subclass for the two declarations installed by patching the
        **class**, whose `__init__` therefore discards the `(db)` production
        hands it -- a `*launches` constructor would otherwise hold a `Session`
        as a launch.

        `source` is a launch, an iterable of them, or a zero-argument callable,
        and is resolved on every read rather than at subclass creation, so a
        test that rebinds it mid-file is served what it rebound.
        """
        return type(
            cls.__name__,
            (_ServingLaunches,),
            {"_source": staticmethod(source) if callable(source) else source},
        )

    def _held(self) -> tuple[Any, ...]:
        return tuple(self.launches)

    async def get_by_product_id(self, product_id: Any, *_a: Any, **_kw: Any) -> Any:
        for launch in self._held():
            if launch.product_id == product_id:
                return launch
        return None

    async def list_active(self, *_a: Any, **_kw: Any) -> tuple[Any, ...]:
        """Every launch held -- graduated ones included. See the class docstring."""
        return self._held()

    async def list_all(self, *_a: Any, **_kw: Any) -> tuple[Any, ...]:
        return self._held()

    async def save(self, launch: Any) -> None:
        for index, held in enumerate(self.launches):
            if held.product_id == launch.product_id:
                self.launches[index] = launch
                return
        self.launches.append(launch)


class _ServingLaunches(FakeLaunches):
    """What `FakeLaunches.serving` builds: production constructs it, so the
    constructor discards its arguments and the launches come from `_source`."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        super().__init__()

    def _held(self) -> tuple[Any, ...]:
        source = type(self)._source
        resolved = source() if callable(source) else source
        if resolved is None:
            return ()
        if isinstance(resolved, (list, tuple)):
            return tuple(resolved)
        return (resolved,)


class _FakePlaybooksBase:
    """What both playbook stores hold, and the one answer both give.

    The sync and async stores are **siblings over this base, not parent and
    child**: overriding a sync `get` with a coroutine is an incompatible
    override, and `mypy` -- which runs at every commit -- rejects it with
    `Return type "Coroutine[...]" ... incompatible with return type ... in
    supertype`. Discovered mechanically rather than by preference; an earlier
    draft of `share-the-aggregate-fakes` reasoned about `mypy` at the protocol
    level and missed it at the inheritance level.

    `_answer()` **increments `reads` first and raises the refusal second**,
    which is the order both counting locals use
    (`test_gate_progression_pass.py:355`, `test_advance_and_ask.py:362`): a
    refused read still counts. Reversing it answers identically on every
    non-refusing read, so only the refusing path distinguishes the two and only
    3 of the 42 declarations refuse at all.

    **`reads` is an `int` and there is no `calls`.** `FakeProductReader` above
    spells the same word as a *list* with a derived `calls`, because that is
    what its own locals spell; `calls` has a measured population of **zero**
    here. Two shared types in this module disagree on one field name
    deliberately -- `AGENTS.md`'s `clickup_user_id` precedent is that each says
    so at itself, which is what this paragraph is.

    **Neither store is callable.** Six locals carried an `async __call__` whose
    comment claimed "some callers read a playbook through a bare call": measured
    at the commit that dropped it, that is stale. Production reads a playbook
    store exclusively through `.get(...)`, `src/` contains no bare call on one,
    and wrapping all six locals' `__call__` recorded **0 invocations across all
    three tiers**. Dropped on the licence `list_launches` and `all` were.
    """

    def __init__(self, playbook: Any, *, refusal: Exception | None = None) -> None:
        self._playbook = playbook
        self.refusal = refusal
        self.reads = 0

    def _answer(self) -> Any:
        self.reads += 1
        if self.refusal is not None:
            raise self.refusal
        return self._playbook


class FakePlaybooks(_FakePlaybooksBase):
    """The playbook store, read synchronously -- 25 of the 42 declarations."""

    def get(self, version: str = "") -> Any:
        return self._answer()


class AsyncFakePlaybooks(_FakePlaybooksBase):
    """The playbook store, awaited -- 7 of the 42 declarations.

    A sibling of `FakePlaybooks`, never a subclass; see the base.
    """

    async def get(self, version: str = "") -> Any:
        return self._answer()


class FakePlaybookRepository:
    """`PlaybookRepository`, installed by patching the **class**.

    All ten declarations are `monkeypatch.setattr(module, "PlaybookRepository",
    ...)`, so production constructs the double itself with `(db)` -- it can
    never be handed a playbook as an instance, which is why `__init__` discards
    what it receives and why the playbook arrives through `serving`.

    **`serving` reads its source at call time, and that is a correctness
    condition rather than a refinement.** `test_clickup_webhook_automated_step`
    rebinds a module-level `_SERVED[0]` mid-file -- once to a playbook with an
    automated step, once to one with a human step -- to prove opposite branches.
    A `serving` that bound the value when the subclass was created would answer
    the import-time playbook to both, and **both tests would still pass**.
    Neither the equality proof nor the lockstep pairing can see that; only
    reading late prevents it.

    Each `serving` call produces its own subclass, so nothing is shared between
    call sites. A mutable class attribute would do the same job and was
    rejected: that is session-global state every test touching the class shares,
    the cross-test leak this harness exists to remove.
    """

    _source: ClassVar[Any] = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None: ...

    @classmethod
    def serving(cls, source: Any) -> type[FakePlaybookRepository]:
        """A subclass answering `source` -- a playbook, or a zero-argument
        callable read afresh on every `get`."""
        return type(
            cls.__name__,
            (cls,),
            {"_source": staticmethod(source) if callable(source) else source},
        )

    async def get(self, version: str = "") -> Any:
        source = type(self)._source
        return source() if callable(source) else source


class FakeProductReader:
    """The catalog read a launch pass makes: one product, by identifier.

    **It holds whatever object it is handed, and is deliberately not annotated
    to `values.py::CatalogProduct`** (`share-the-aggregate-fakes`, Decision 7).
    22 of the 24 declarations it replaces import that type and 2 declare their
    own frozen product; more to the point, four production sites probe the
    *served* product by attribute name -- `automation_pass:563`,
    `automation_confirmation:115`, `product_dossier:326` and `:335`. Narrowing
    the held type would move `AGENTS.md`'s same-value invariant out of the
    visible call site and into this double, where nobody reads it.

    **`reads` is the stored spelling and `calls` is derived over the same list
    object.** 6 of the locals record into `reads` and 4 into `calls`; carrying
    two lists would let a later edit populate one and not the other, so there is
    one list under two names, the arrangement `Member.identifier` and
    `FakeTask.custom_field_values` already use. `reads` is stored rather than
    `calls` because no call site *assigns* either name -- measured across
    `tests/` at the commit that added this -- and a read-only property cannot
    receive an assignment, which is `AGENTS.md`'s `Member.id` precedent.

    **Beware the neighbouring spelling.** The playbook store's `reads` is an
    `int` with no `calls` at all, because that is what its own locals spell.
    Two shared types in this module disagree on one field name, deliberately;
    `tests/unit/support/test_fake_playbooks.py` pins the other side.

    Recording where the locals recorded nothing is a superset over 14 of the 24,
    licensed by the probe search that found no production reader touching either
    name -- they are test-only recorders.
    """

    def __init__(self, product: Any) -> None:
        self._product = product
        self.reads: list[ProductId] = []

    @property
    def calls(self) -> list[ProductId]:
        """The other spelling, over the same list -- never a second one."""
        return self.reads

    async def __call__(self, product_id: ProductId) -> Any:
        self.reads.append(product_id)
        return self._product


class FakeMembers:
    """The membership, as the reader production is handed.

    **One reader shape, where the locals carried up to four.** Forty-three
    declarations spelled the read `list_members()`, thirty-two aliased it as
    `members`, and thirty-six added `async def __call__`. This fake carries
    `list_members()` alone, under clause (e), and the licence is a measurement
    rather than a preference: nothing in `src/` or `tests/` reads a reader's
    `members`, and both members probes reach their `callable(...)` branch only
    after `list_members` has missed -- which it never does, since every
    declaration provides it. Re-taken at the commit that dropped them, both
    still zero.

    `member(member_id)` is **kept**: a genuine second query that six files use,
    and no probe chooses between it and anything else. It matches on `id`, the
    spelling all fifty-two member doubles carry (`values.Member` stores `id` and
    derives `identifier`).

    The roster is `_members` -- the dominant local spelling, and private, so it
    is outside every probe. Nine locals spelled it `members_rows`; those carry a
    `state` name map while the pairing runs, and nothing after it.
    """

    def __init__(self, members: tuple[Any, ...] = ()) -> None:
        self._members = tuple(members)

    async def list_members(self) -> tuple[Any, ...]:
        return self._members

    async def member(self, member_id: str) -> Any | None:
        for known in self._members:
            if known.id == member_id:
                return known
        return None
