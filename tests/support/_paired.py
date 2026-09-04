"""The lockstep proof, in force only between a name's two commits.

**Temporary. The last settle commit deletes this module**
(`share-the-stateful-fakes`, task 12.1). A proof that outlives its migration is
a permanent dependency on a temporary arrangement.

It drives a local double and its shared replacement *in lockstep*: the twin is
built from the same call, and every executed method runs on both, comparing the
return value, the raised exception and the instance state afterwards. Where the
parent slice's `_instrument.py` compared two objects' fields, this compares two
behaviours -- which is the check `share-the-unit-test-harness`'s Decision 7(b2)
recorded as caught by nothing, because `FakeStepStore() == FakeStepStore()` is
identity and no equality proof is expressible for a fake.

**A divergence is raised, not logged, and it is not an `Exception`.** Production
wraps collaborator calls in `except Exception` in several places, and any of
those would swallow a divergence and leave the commit green -- restoring exactly
the failure mode raising was chosen to prevent. `pytest.fail` raises `Failed`,
which derives from `BaseException`, so nothing in the code under test absorbs
it.

The two *non-fatal* observations go out as warnings rather than prints, because
pytest discards a passing test's output and a note nobody reads is not a record.
"""

from __future__ import annotations

import atexit
import inspect
import json
import os
import warnings
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeVar

import pytest

_T = TypeVar("_T")

#: Where the local instance holds its twin. Excluded from every state
#: comparison: the decorator stores it on the local before the first
#: comparison runs, so leaving it in would report the proof's own bookkeeping
#: as an attribute the shared fake models less of.
_TWIN = "_paired_twin"

#: Every decorated class, and how much the pairing actually did for it:
#: constructions, where the initial state was compared, and method calls, where
#: a return value, an exception and the state after were. A declaration that
#: migrated with both at zero is proved by nothing, and one with calls at zero
#: is proved only at construction -- task 12.3 names either rather than letting
#: a green commit read as evidence it is not.
PAIRED_BUILDS: Counter[str] = Counter()
PAIRED_CALLS: Counter[str] = Counter()

#: `(class name, method name)` pairs that clause (e) licenses the shared fake to
#: drop. Matched as pairs and never by bare name: `_Catalog.__call__` must be
#: rejected where `_FakeMembers.__call__` is excused, and a name-only whitelist
#: cannot tell them apart.
LICENSED_DROPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("_FakeMembers", "members"),
        ("_FakeMembers", "__call__"),
        ("_FakeHandlerRegistry", "__iter__"),
    }
)


def _observable(obj: Any, names: Mapping[str, str]) -> dict[str, Any]:
    """The instance attribute mapping, with the local's spellings renamed.

    `names` maps a *local* attribute to the shared fake's spelling for the same
    value. It is a name map and never a callable: a projection applied to both
    sides could normalise two different values into agreement, which is the one
    way a state comparison can be made to pass by writing it.
    """
    return {
        names.get(key, key): value for key, value in vars(obj).items() if key != _TWIN
    }


def _compare_state(
    where: str, local: Any, shared: Any, names: Mapping[str, str]
) -> None:
    mine, theirs = _observable(local, names), _observable(shared, names)
    missing = sorted(set(mine) - set(theirs))
    if missing:
        pytest.fail(
            f"{where}: the shared fake models less than {type(local).__name__} -- "
            f"it has no {missing!r}.\n  local : {mine!r}\n  shared: {theirs!r}"
        )
    differing = {
        key: (mine[key], theirs[key])
        for key in sorted(mine)
        if mine[key] != theirs[key]
    }
    if differing:
        pytest.fail(
            f"{where}: state disagrees on {differing!r}\n"
            f"  local : {mine!r}\n  shared: {theirs!r}"
        )
    added = sorted(set(theirs) - set(mine))
    if added:
        warnings.warn(
            f"{where}: the shared fake adds {added!r} over {type(local).__name__}. "
            "A licensed superset -- check it against the same-value invariant.",
            stacklevel=2,
        )


def _compare_outcome(
    where: str,
    mine: Any,
    my_error: BaseException | None,
    theirs: Any,
    their_error: BaseException | None,
) -> None:
    if (my_error is None) != (their_error is None):
        raised, quiet = ("local", "shared") if my_error else ("shared", "local")
        pytest.fail(
            f"{where}: the {raised} fake raised where the {quiet} one returned -- "
            f"{(my_error or their_error)!r}"
        )
    if my_error is not None and their_error is not None:
        if type(my_error) is not type(their_error) or str(my_error) != str(their_error):
            pytest.fail(f"{where}: {my_error!r} against {their_error!r}")
        return
    if mine != theirs:
        pytest.fail(f"{where}: returned {mine!r} against {theirs!r}")


def _declares(shared: type, name: str) -> bool:
    """Whether the shared fake itself defines `name`, metaclass lookups aside.

    `hasattr(SomeClass, "__call__")` is **always true** -- a class is callable,
    so the lookup finds `type.__call__` and reports a `__call__` the fake does
    not have. The same reading would excuse `_Catalog.__call__`, which is
    exactly the declaration clause (e) must reject. `object` is excluded for the
    matching reason: it supplies `__eq__` and `__repr__` that a fake declaring
    neither does not really answer.
    """
    return any(name in vars(klass) for klass in shared.__mro__ if klass is not object)


def _callables(local: type) -> dict[str, Any]:
    """Every class-body binding to a callable, aliases included.

    `members = list_members` is an alias, not a `def`; a `FunctionDef`-only
    reading would never see it, and clause (e)'s licence for the largest dropped
    spelling would check nothing.
    """
    return {
        name: value
        for name, value in vars(local).items()
        if name != "__init__"
        and callable(value)
        and not isinstance(value, (classmethod, staticmethod, property))
    }


def paired(
    shared: type,
    *,
    build: Callable[..., Any] | None = None,
    build_from: Callable[[Any], Any] | None = None,
    state: Mapping[str, str] | None = None,
) -> Callable[[type[_T]], type[_T]]:
    """Drive a local double and its shared replacement in lockstep.

    **`build` and `build_from` are not equally strong, and the difference is
    the whole reason both exist.**

    `build` receives the local's *call arguments* and constructs the twin from
    them independently. Everything is then compared: that the two constructors
    agree, and that every executed method does.

    `build_from` receives the *constructed local* and seeds the twin from its
    state. It is weaker: construction is no longer independently checked, only
    the methods are. It exists for the population where the stronger form
    reports nothing but false positives -- a double that **builds its own
    contents** rather than being handed them. `FakeMembers` is that population:
    thirty-three of its forty-three declarations hard-code a roster inside the
    class, so an independently built twin holds different `Member` objects, and
    `values.Member` is a plain class whose `==` is identity by design. Every
    comparison would differ, on every call, for a difference that is an artefact
    of running two objects. Seeded from the local instead, the twin holds *the
    same* members, and what the pairing then establishes is what risk 3 is
    actually about: that `list_members()` returns the same tuple in the same
    order and `member()` resolves the same way.

    What `build_from` gives up is stated rather than glossed: for those
    declarations the shared fake's *constructor* is proved by the adapter
    reproducing the roster literally, and by nothing else.
    """

    if build is not None and build_from is not None:
        raise TypeError("paired() takes build or build_from, never both")

    names = dict(state or {})

    def decorate(local: type[_T]) -> type[_T]:
        label = f"{local.__module__}.{local.__name__}"
        PAIRED_BUILDS[label] += 0
        PAIRED_CALLS[label] += 0

        wrapped = _callables(local)
        for name in sorted(wrapped):
            if _declares(shared, name):
                continue
            if (local.__name__, name) in LICENSED_DROPS:
                warnings.warn(
                    f"{label}.{name}: silent pairing -- the shared fake drops this "
                    "spelling under clause (e), so no call is compared here.",
                    stacklevel=2,
                )
                continue
            raise TypeError(
                f"{label}.{name}: the shared fake has no such attribute, and the "
                "pair is not one clause (e) licenses. This declaration is a keep: "
                "drop its @paired line before committing."
            )

        original_init = local.__init__

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            PAIRED_BUILDS[label] += 1
            if build_from is not None:
                twin = build_from(self)
            elif build is not None:
                twin = build(*args, **kwargs)
            else:
                twin = shared(*args, **kwargs)
            object.__setattr__(self, _TWIN, twin)
            if build_from is None:
                _compare_state(f"{label}(...) initial state", self, twin, names)

        local.__init__ = __init__  # type: ignore[method-assign]

        for name, attribute in wrapped.items():
            if not _declares(shared, name):
                continue
            setattr(local, name, _wrap(label, name, attribute, names))
        return local

    return decorate


def _wrap(label: str, name: str, attribute: Any, names: Mapping[str, str]) -> Any:
    where = f"{label}.{name}()"

    if inspect.iscoroutinefunction(attribute):

        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            PAIRED_CALLS[label] += 1
            twin = getattr(self, _TWIN)
            mine: Any = None
            my_error: BaseException | None = None
            try:
                mine = await attribute(self, *args, **kwargs)
            except Exception as failure:  # noqa: BLE001 -- compared, then re-raised
                my_error = failure
            theirs: Any = None
            their_error: BaseException | None = None
            try:
                theirs = await getattr(twin, name)(*args, **kwargs)
            except Exception as failure:  # noqa: BLE001 -- compared, never raised on
                their_error = failure
            _compare_outcome(where, mine, my_error, theirs, their_error)
            _compare_state(where, self, twin, names)
            if my_error is not None:
                raise my_error
            return mine

        return async_wrapper

    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        PAIRED_CALLS[label] += 1
        twin = getattr(self, _TWIN)
        mine: Any = None
        my_error: BaseException | None = None
        try:
            mine = attribute(self, *args, **kwargs)
        except Exception as failure:  # noqa: BLE001 -- compared, then re-raised
            my_error = failure
        theirs: Any = None
        their_error: BaseException | None = None
        try:
            theirs = getattr(twin, name)(*args, **kwargs)
        except Exception as failure:  # noqa: BLE001 -- compared, never raised on
            their_error = failure
        _compare_outcome(where, mine, my_error, theirs, their_error)
        _compare_state(where, self, twin, names)
        if my_error is not None:
            raise my_error
        return mine

    return wrapper


@atexit.register
def _report() -> None:
    """Write the per-class paired-call counts where a task asked for them."""
    destination = os.environ.get("PAIRED_REPORT")
    if destination:
        Path(destination).write_text(
            json.dumps(
                {
                    label: {
                        "builds": PAIRED_BUILDS[label],
                        "calls": PAIRED_CALLS[label],
                    }
                    for label in sorted(PAIRED_CALLS)
                },
                indent=1,
            )
        )
