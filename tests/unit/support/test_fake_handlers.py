"""`FakeHandlers`' contract, stated directly.

The lockstep proof compares this fake against each local it replaces, on the
calls those files execute. What it cannot reach is a path no test exercises --
`resolve` on an unregistered name, in particular, which production's own comment
at `automation_pass:770` says is free to raise. That is what this module is for.
"""

from __future__ import annotations

import pytest

from tests.support.fakes import FakeHandlers


def test_an_empty_registry_registers_nothing() -> None:
    handlers = FakeHandlers()

    assert handlers.names() == ()
    assert "price.buy_box_check" not in handlers


def test_names_answers_the_registered_names_in_registration_order() -> None:
    """Order matters: `_registered_names` builds a `frozenset` from it, but the
    suite's own assertions read the tuple, and the eight locals all returned
    `tuple(self._handlers)` -- insertion order."""
    handlers = FakeHandlers(second=object(), first=object())

    assert handlers.names() == ("second", "first")


def test_membership_is_answered_directly_rather_than_by_resolving() -> None:
    """`automation_pass:770` asks `name in handlers` before it resolves."""
    handlers = FakeHandlers(known=object())

    assert "known" in handlers
    assert "unknown" not in handlers


def test_resolve_answers_the_registered_handler() -> None:
    handler = object()

    assert FakeHandlers(known=handler).resolve("known") is handler


def test_resolve_raises_for_a_name_it_never_held() -> None:
    """The behaviour production relies on being safe: it guards with `in`."""
    with pytest.raises(KeyError):
        FakeHandlers().resolve("unknown")


def test_get_answers_the_default_for_a_name_it_never_held() -> None:
    fallback = object()

    assert FakeHandlers().get("unknown") is None
    assert FakeHandlers().get("unknown", fallback) is fallback
