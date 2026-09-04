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

from datetime import date
from typing import Any, ClassVar


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
