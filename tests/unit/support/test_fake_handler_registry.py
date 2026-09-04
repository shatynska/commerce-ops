"""`FakeHandlerRegistry`'s contract, stated directly.

Its one interesting property is a *missing* method: the twelve locals all
carried `__iter__` and this double does not, under clause (e). What the pairing
cannot show is that nothing reaches the dropped spelling -- a pairing over a
name the shared fake lacks is silent by construction -- so the licence rests on
task 7.1's measurement instead, and these tests state what remains.
"""

from __future__ import annotations

import pytest

from tests.support.fakes import FakeHandlerRegistry


def test_an_empty_registry_registers_nothing() -> None:
    registry = FakeHandlerRegistry()

    assert registry.names() == frozenset()
    assert "price.buy_box_check" not in registry


def test_names_answers_the_registered_set() -> None:
    """A `frozenset`, not a tuple: `_registered_names` only iterates it, and
    this is what all twelve local declarations returned."""
    registry = FakeHandlerRegistry(frozenset({"price.buy_box_check", "listing.copy"}))

    assert registry.names() == frozenset({"price.buy_box_check", "listing.copy"})


def test_membership_is_answered_directly() -> None:
    """`automation_pass:770` asks `name in handlers`; without `__contains__`
    that would fall back to `__iter__`, which this double deliberately lacks."""
    registry = FakeHandlerRegistry(frozenset({"price.buy_box_check"}))

    assert "price.buy_box_check" in registry
    assert "listing.copy" not in registry


def test_does_not_iterate() -> None:
    """The dropped spelling, asserted as dropped.

    `_registered_names` reaches its iteration branch only when `names` is not
    callable, and it always is here. Task 7.1 establishes the same thing by
    execution across the whole tier; this states it for the double itself, so
    a future edit that quietly restores `__iter__` has to argue with a test.
    """
    with pytest.raises(TypeError):
        list(FakeHandlerRegistry(frozenset({"price.buy_box_check"})))  # type: ignore[call-overload]
