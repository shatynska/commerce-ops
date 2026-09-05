"""`FakePlaybookRepository.serving()`, stated directly.

All ten `_FakePlaybookRepository` declarations are installed as
`monkeypatch.setattr(module, "PlaybookRepository", _FakePlaybookRepository)`, so
**production constructs the double itself, with `(db)`**. That is why this one
takes a class-producing constructor rather than being handed a playbook, and
why its `_conforms` assignment takes the class-object form.

Two things the equality proof cannot see are pinned here:

* **`serving()` reads its source at call time, not at subclass creation.**
  `design.md` -- Decision 3 records this as the correctness condition rather
  than a refinement: `test_clickup_webhook_automated_step.py` rebinds
  `_SERVED[0]` at line 359 and again at 398 to prove opposite branches, and a
  `serving()` that froze the value at subclass creation would serve the
  import-time playbook to both -- **and both tests would still pass**. The
  failure is invisible to every instrument this change carries except this one.
* **Each `serving()` call produces its own subclass.** The rejected alternative
  was a mutable class attribute the test sets, which is session-global state
  shared across every test touching the class. Two subclasses that quietly
  shared one source would answer identically at any single call site.

This is the shared harness's own behaviour, so it lives under
`tests/unit/support/` -- the deliberate exception to the tier layout, per
`AGENTS.md`.
"""

from __future__ import annotations

import pytest

from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from tests.support.fakes import FakePlaybookRepository
from tests.support.playbook import playbook
from tests.support.steps import hold

pytestmark = pytest.mark.anyio

FIRST = playbook(hold("listable", identifier="first.listable"))
SECOND = playbook(hold("listable", identifier="second.listable"))

#: Stands for the `(db)` production hands the class it constructs. Deliberately
#: not a `Session`: what matters is that *something* arrives and is discarded.
A_SESSION = object()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_serving_a_playbook_answers_it_from_the_built_repository() -> None:
    """The four declarations that build a `LaunchPlaybook` inline become
    `serving(playbook(...))`, and production still constructs the class."""
    repository = FakePlaybookRepository.serving(FIRST)(A_SESSION)

    assert await repository.get("") is FIRST


async def test_the_constructor_discards_what_production_passes_it() -> None:
    """Production calls the patched class with `(db)`. Nothing it passes may
    reach what the double serves."""
    repository = FakePlaybookRepository.serving(FIRST)(A_SESSION, echo=True)

    assert await repository.get("") is FIRST


async def test_serving_a_zero_argument_callable_invokes_it_per_call() -> None:
    """The five declarations that `return _playbook()` become
    `serving(_playbook)` -- the file's own builder, unfrozen."""
    built: list[LaunchPlaybook] = []

    def build() -> LaunchPlaybook:
        built.append(FIRST)
        return FIRST

    repository = FakePlaybookRepository.serving(build)(A_SESSION)

    assert await repository.get("") is FIRST
    assert await repository.get("") is FIRST
    assert len(built) == 2


async def test_the_source_is_read_at_call_time_not_at_subclass_creation() -> None:
    """`tasks.md` 4.3's required test, and Decision 3's correctness condition.

    This is the `_SERVED[0]` shape: a module-level list rebound *inside* a test,
    after the subclass exists and after production has constructed it. A
    `serving()` that bound the value when the subclass was created would answer
    `FIRST` twice here, and in the file it is written for both branches would
    still pass while proving nothing.
    """
    served = [FIRST]
    repository = FakePlaybookRepository.serving(lambda: served[0])(A_SESSION)

    assert await repository.get("") is FIRST

    served[0] = SECOND

    assert await repository.get("") is SECOND


async def test_each_serving_call_produces_a_subclass_of_its_own() -> None:
    """The rejected mutable-class-attribute form would make these two share one
    source, and the second `serving()` would silently retune the first."""
    first_class = FakePlaybookRepository.serving(FIRST)
    second_class = FakePlaybookRepository.serving(SECOND)

    assert first_class is not second_class
    assert await first_class(A_SESSION).get("") is FIRST
    assert await second_class(A_SESSION).get("") is SECOND


def test_serving_returns_a_class_rather_than_an_instance() -> None:
    """It is patched in as a class; an instance would be constructed by
    production and raise rather than serve."""
    served = FakePlaybookRepository.serving(FIRST)

    assert isinstance(served, type)
    assert issubclass(served, FakePlaybookRepository)


async def test_get_takes_the_version_production_passes_positionally() -> None:
    """All ten locals declare `get(self, version: str)` -- required, not
    defaulted, because production always passes one."""
    repository = FakePlaybookRepository.serving(FIRST)(A_SESSION)

    assert await repository.get("2027.1") is FIRST
