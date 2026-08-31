"""The `Success[T]` / `Failure[E]` result shape (`shared.domain`).

This type carries no delta-spec scenarios of its own: none of this
change's three capabilities (`subcategory-advisor`, `launch-step-automation`,
`product-catalog`) is `shared`, and no delta spec here states a scenario
about `Success`/`Failure` directly. It is introduced by `design.md`
Decision 1 as load-bearing infrastructure for `launch-step-automation`'s
ADDED requirement *A handler MAY report a typed finding alongside its
outcome*, which describes the shape in prose ("a typed finding expressed
as either a success carrying a value or a failure carrying an error,
either of which MAY carry an additional comment").

These tests are therefore DERIVED from `design.md` Decision 1's own code
sample, not from a named scenario, and are not counted in this change's
38-scenario total (see `test-manifest.md`). They exist because every other
file in this pass constructs `Success(...)`/`Failure(...)` instances to
drive `StepResolution.finding`, and the type's own contract — frozen,
`comment` optional and defaulting to `None`, `value`/`error` required — is
worth pinning once rather than assumed silently everywhere it is used.

## Level

Frozen dataclasses with no I/O; construction is the smallest unit that can
observe their shape.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 1's own code sample: the module path
`shared/domain/result.py`, the field names `value`/`comment` on `Success`
and `error`/`comment` on `Failure`, `comment` defaulting to `None` on
both, and `frozen=True`.

INVENTED: the import path used to reach them
(`commerce_ops.shared.domain.result`), following this project's own
convention of importing `shared.domain` vocabulary from its owning
submodule rather than the package root (e.g.
`from commerce_ops.shared.domain.access_scope import AccessScope` in
`tests/unit/shared/domain/test_access_scope.py`) — `tasks.md` 1.2 asks
only that the type be *exported* from `shared.domain`'s public surface,
not that it be imported from there. A test importing from the wrong path
is a fixture correction (failure state 3 in `ai-toolkit:testing`).

## Expected first-run state

`shared/domain/result.py` does not exist yet (`tasks.md` 1.1), so every
test here is expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

import dataclasses

import pytest

from commerce_ops.shared.domain.result import Failure, Success


def test_a_success_carries_its_value_and_an_optional_comment() -> None:
    """DERIVED from `design.md` Decision 1: `Success(value=..., comment=None)`."""
    success = Success(value="Home & Kitchen > Cutting Boards")

    assert success.value == "Home & Kitchen > Cutting Boards"
    # SPECIFIED (design.md's own code sample): comment defaults to None.
    assert success.comment is None


def test_a_success_may_carry_a_comment() -> None:
    success = Success(value="node", comment="demands and a rejected alternative")

    assert success.value == "node"
    assert success.comment == "demands and a rejected alternative"


def test_a_failure_carries_its_error_and_an_optional_comment() -> None:
    failure = Failure(error="no verdict could be read")

    assert failure.error == "no verdict could be read"
    assert failure.comment is None


def test_a_failure_may_carry_a_comment() -> None:
    failure = Failure(error="no verdict could be read", comment="raw text was empty")

    assert failure.error == "no verdict could be read"
    assert failure.comment == "raw text was empty"


def test_success_is_frozen() -> None:
    """DERIVED: `design.md`'s own `@dataclass(frozen=True, slots=True)`."""
    success = Success(value="node")

    assert dataclasses.is_dataclass(type(success))
    # Through a non-literal attribute name, per this project's convention
    # (`test_step_handler_contract.py`): the assertion is about
    # frozen-ness, not a spelling `mypy --strict` would reject outright.
    frozen_field = "value"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(success, frozen_field, "a different node")


def test_failure_is_frozen() -> None:
    failure = Failure(error="no verdict could be read")

    assert dataclasses.is_dataclass(type(failure))
    frozen_field = "error"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(failure, frozen_field, "a different reason")


def test_success_and_failure_are_distinguishable_by_type() -> None:
    """DERIVED: generic code reading a `finding` (`launch-step-automation`'s
    pass, in particular) has to tell a success from a failure without
    knowing what `T`/`E` mean for the handler that produced it — the whole
    point of Decision 1's "any generic code that later touches a `finding`
    ... must never need to know a field is called `sub_category`". `isinstance`
    over the two types is the mechanism that has to work for that to hold.
    """
    success: object = Success(value="node")
    failure: object = Failure(error="no verdict could be read")

    assert isinstance(success, Success)
    assert not isinstance(success, Failure)
    assert isinstance(failure, Failure)
    assert not isinstance(failure, Success)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The `Result = Success[T] | Failure[E]` alias itself. A `TypeAlias` (or
#   a bare `|`-union) carries no runtime behaviour beyond the two types
#   already tested above; there is nothing a test could observe about the
#   alias that the two constructors above do not already establish.
# ---------------------------------------------------------------------------
