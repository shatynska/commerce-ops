"""Tests for the `daily` monitoring use case, at the application layer.

This file is DERIVED supplementary coverage, not itself required to account
for any `#### Scenario:` block in
`openspec/changes/add-product-agent-daily-digest/specs/product-monitoring/spec.md`.
That delta spec states its requirements entirely in terms of the daily
*endpoint's* observable behavior ("when the daily endpoint is invoked ...
post a Slack message ..."), so the endpoint -- exercised in
`tests/unit/products/infrastructure/driving/test_monitoring_routes.py` -- is
the level `ai-toolkit:testing`'s Level rule assigns as authoritative for
those scenarios; message assembly and Slack delivery both happen at that
composition point, not inside this use case alone, per `design.md`'s
Decisions ("the driving route constructs the repository and passes it into
the use case", then separately "the Slack notifier from Task 4").

What this file adds beyond that: `tasks.md` 8.2 asks for use-case-level
coverage of the daily use case against a fake `ProductNameReader` port,
specifically that a reader failure "propagates rather than [is] swallowed"
-- a property that is fully observable at this smaller, faster level
without needing any HTTP/Slack machinery, and is duplicated at the route
level only insofar as the route-level test also confirms the *consequence*
of that propagation (a failing response + an attempted failure post).

## Names and shapes used here are INVENTED

No artifact fixes the daily use case's function name or its exact return
contract for "no products exist". This file assumes:

- `commerce_ops.products.application.run_daily_digest`, an async function
  taking one positional `ProductNameReader` and returning whatever
  `Sequence[str]` the reader itself returns unchanged -- including an empty
  sequence, read as the "explicit 'no products exist' result" `tasks.md`
  3.1 asks for, since an empty sequence is already unambiguous in Python
  (unlike e.g. `None`, which would conflate "no products" with "nothing was
  computed").
- `commerce_ops.products.application.ProductNameReader`, a `Protocol` with
  one async method, `list_names(self) -> Sequence[str]`. The method name is
  not itself invented: `design.md`'s Decisions says `ProductRepository`
  "satisfies it structurally" -- Python's structural `Protocol` typing
  requires the port's method to share `ProductRepository`'s own method
  name, which Task 2.1 fixes as `list_names()`.

If the real use case differs -- a different function name, a different
port shape, or a genuinely different "no products" signal (e.g. a
dataclass distinguishing the two cases) -- correcting the import or the
fake reader below is a fixture correction; the postconditions each test
checks (what came back, and that a raised failure was not swallowed) are
what trace to `tasks.md` and must survive any such correction unweakened.

At the time this pass was written, `products/application/__init__.py` is
empty, so every test here is expected to fail on an absent target
(`ModuleNotFoundError` or `ImportError`) until Tasks 2.2/3.1/3.3 land.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from commerce_ops.products.application import ProductNameReader, run_daily_digest

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio -- see tests/integration/products/conftest.py's own
    # anyio_backend fixture for the reasoning (no trio dependency installed,
    # nothing in this project's artifacts calls for trio support). Defined
    # locally rather than shared, since this directory has no conftest.py of
    # its own yet and adding one purely to host a single fixture used by one
    # file would be more machinery than the fixture itself.
    return "asyncio"


class _FakeReader:
    """A `ProductNameReader` test double: scripted names or a scripted
    failure, never both."""

    def __init__(
        self, *, names: Sequence[str] | None = None, failure: Exception | None = None
    ) -> None:
        self._names = names
        self._failure = failure
        self.calls = 0

    async def list_names(self) -> Sequence[str]:
        self.calls += 1
        if self._failure is not None:
            raise self._failure
        assert self._names is not None
        return self._names


def test_reader_satisfies_the_port_structurally() -> None:
    """DERIVED precondition check: `_FakeReader` is usable wherever
    `ProductNameReader` is expected, the same way `design.md` says
    `ProductRepository` is -- otherwise the tests below would exercise a
    double that isn't actually shaped like the port under test.
    """
    reader: ProductNameReader = _FakeReader(names=())
    assert hasattr(reader, "list_names")


async def test_returns_the_names_the_reader_reports() -> None:
    """`tasks.md` 8.2: "product names returned correctly."

    WHEN the reader reports at least one product name
    THEN the daily use case's result contains exactly those names.
    """
    reader = _FakeReader(names=("Widget A", "Widget B"))

    result = await run_daily_digest(reader)

    assert list(result) == ["Widget A", "Widget B"]
    assert reader.calls == 1


async def test_no_products_case_reports_no_names() -> None:
    """`tasks.md` 8.2: "the 'no products exist' case."

    WHEN the reader reports no products
    THEN the daily use case's result is empty (see module docstring for why
    an empty sequence is read as the explicit "no products exist" signal).
    """
    reader = _FakeReader(names=())

    result = await run_daily_digest(reader)

    assert list(result) == []


async def test_reader_failure_propagates_rather_than_being_swallowed() -> None:
    """`tasks.md` 8.2: "a reader failure propagates rather than being
    swallowed" / `tasks.md` 3.1: "lets a database-read failure propagate
    rather than swallowing it."

    WHEN the reader's `list_names()` raises
    THEN the daily use case's own call raises the same failure, rather than
    returning a value (e.g. an empty sequence) that would be
    indistinguishable from a genuine "no products exist" result.
    """
    failure = RuntimeError("simulated database-read failure")
    reader = _FakeReader(failure=failure)

    with pytest.raises(RuntimeError) as caught:
        await run_daily_digest(reader)

    # SPECIFIED (tasks.md 3.1): the failure itself propagates -- not merely
    # *some* exception, since swapping it for a different one would still
    # be "not swallowing" in the loosest sense but would discard the
    # original failure's information.
    assert caught.value is failure
