"""`FakeLaunches`, stated directly -- and one assertion neither proof can make.

`Launch` is a plain aggregate root defining no `__eq__`, so `==` is identity and
the field-wise equality proof is inexpressible for the 58 declarations this type
takes. They are closed by the lockstep pairing instead, whose four recorded
limits apply unchanged. Four things sit outside both instruments and are stated
here:

* **`list_active` deliberately does not filter graduated launches**
  (`design.md` -- Decision 5, and the rule `tasks.md` 7.2 adds to `AGENTS.md`:
  *a shared double must not implement the filter its subject is being tested
  for*). This is the one assertion in the change that a green suite cannot
  supply, and it has its own test below with the reasoning at it.
* **`list_launches` and `all` are absent**, measured dead by execution across
  all three tiers. A double that quietly kept them would pass every migration.
* **`serving()` discards what production passes the class it patches in.**
  Decision 3's `serving` does not transfer: a `*launches` constructor handed
  `(db)` would hold a `Session` as a launch and answer it from every read.
* **The four read methods resolve their source at call time.** Whether either
  class-patched declaration actually rebinds is `tasks.md` 5.5b's to measure;
  it is the safe default either way, and this file pins the behaviour rather
  than the justification.

This is the shared harness's own behaviour, so it lives under
`tests/unit/support/` -- the deliberate exception to the tier layout, per
`AGENTS.md`.
"""

from __future__ import annotations

import datetime

import pytest

from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
)
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import FakeLaunches
from tests.support.fixtures import LAUNCH_DATE, product_id
from tests.support.playbook import CONFIRMATION_GATES, playbook

pytestmark = pytest.mark.anyio

#: No steps at all: this file is about what the double serves, not about what a
#: playbook holds, and an unheld playbook is the cheapest launch to walk.
PLAYBOOK: LaunchPlaybook = playbook(fill_unheld=False)

APPROVED_AT = datetime.datetime(2027, 3, 2, 9, 0, tzinfo=datetime.UTC)

#: Stands for the `(db)` production hands a class it constructs itself.
A_SESSION = object()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _launch(identifier: ProductId | None = None) -> Launch:
    launch, _ = Launch.start(
        product_id=identifier if identifier is not None else product_id(),
        playbook=PLAYBOOK,
        launch_date=LAUNCH_DATE,
    )
    return launch


def _graduated() -> Launch:
    """A launch standing at the final gate, walked rather than asserted into
    place -- the state `list_active` is tempted to filter."""
    launch = _launch()
    while launch.current_gate != "graduated":
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=APPROVED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(PLAYBOOK)
    assert launch.current_gate == "graduated"
    return launch


async def test_lists_every_launch_it_was_handed_as_active() -> None:
    first, second = _launch(), _launch()

    store = FakeLaunches(first, second)

    assert tuple(await store.list_active()) == (first, second)


async def test_list_all_answers_the_same_launches_as_list_active() -> None:
    """25 of the 58 declare only `list_all` and 17 only `list_active`; 7 declare
    neither. Merging them means both spellings now exist everywhere, and the
    superset is only safe while the two agree."""
    first, second = _launch(), _launch()

    store = FakeLaunches(first, second)

    assert tuple(await store.list_all()) == tuple(await store.list_active())


async def test_list_active_does_not_filter_a_graduated_launch() -> None:
    """The assertion no proof in this change can make, and the reason it is
    written before the double is.

    The real repository's `list_active` drops launches standing at `graduated`
    (`launch_repository.py:181`), and reproducing that in the double reads as
    being truer to production. It would instead delete the thing under test.
    `test_automation_pass.py::test_a_graduated_launch_is_left_alone` hands a
    graduated launch to this double **precisely** to prove the pass leaves it
    alone, and `test_gate_progression_pass.py` does the same for the
    progression pass. A filtering double keeps every assertion in both files
    green while removing the launch they are about -- they would then prove a
    property of the double.

    The requirement is specified in two capabilities, not merely tested:
    `openspec/specs/launch-step-automation/spec.md:39` and
    `openspec/specs/launch-clickup-sync/spec.md:91` both carry *A graduated
    launch is left alone*. So a filtering double would leave a specified
    requirement unverified in two capabilities at once, silently.

    Neither instrument can see this: the equality proof compares values, the
    pairing compares calls, and both are identical either way.
    """
    graduated = _graduated()
    running = _launch()

    store = FakeLaunches(graduated, running)

    listed = tuple(await store.list_active())
    assert graduated in listed, (
        "list_active dropped a graduated launch, so the double now filters what "
        "its subject is being tested for"
    )
    assert listed == (graduated, running)


async def test_resolves_a_launch_by_its_product_id() -> None:
    wanted, other = _launch(), _launch()

    store = FakeLaunches(wanted, other)

    assert await store.get_by_product_id(wanted.product_id) is wanted


async def test_answers_none_for_a_product_it_holds_no_launch_for() -> None:
    store = FakeLaunches(_launch())

    assert await store.get_by_product_id(product_id()) is None


async def test_a_saved_launch_is_the_one_read_back_for_its_product() -> None:
    identifier = product_id()
    original = _launch(identifier)
    store = FakeLaunches(original)

    replacement = _launch(identifier)
    await store.save(replacement)

    assert await store.get_by_product_id(identifier) is replacement


async def test_a_saved_launch_for_an_unheld_product_becomes_readable() -> None:
    store = FakeLaunches()
    added = _launch()

    await store.save(added)

    assert await store.get_by_product_id(added.product_id) is added
    assert tuple(await store.list_all()) == (added,)


async def test_the_two_measured_dead_spellings_are_absent() -> None:
    """`list_launches` and `all` were carried by 21 of the 26 `_FakeLaunchStore`
    as delegates to `list_all`, and recorded **zero calls** across all 2,693
    tests in all three tiers. Keeping them would pass every migration; this is
    what reports it if they come back."""
    store = FakeLaunches(_launch())

    assert not hasattr(store, "list_launches")
    assert not hasattr(store, "all")


async def test_serving_discards_what_production_passes_the_patched_class() -> None:
    """Decision 4's `serving`, which is not Decision 3's.

    The two class-patched declarations answer `type(self).launch`, a mutable
    class attribute -- the shape `tasks.md` 7.2 records as a prohibition. A
    `*launches` constructor would accept the `(db)` production hands it and
    serve a `Session` as a launch, which every read would then answer.
    """
    launch = _launch()

    store = FakeLaunches.serving(launch)(A_SESSION)

    assert tuple(await store.list_active()) == (launch,)
    assert tuple(await store.list_all()) == (launch,)
    assert await store.get_by_product_id(launch.product_id) is launch


async def test_serving_takes_a_launch_an_iterable_or_a_callable() -> None:
    first, second = _launch(), _launch()

    from_iterable = FakeLaunches.serving([first, second])(A_SESSION)
    from_callable = FakeLaunches.serving(lambda: (first, second))(A_SESSION)

    assert tuple(await from_iterable.list_active()) == (first, second)
    assert tuple(await from_callable.list_active()) == (first, second)


async def test_serving_reads_its_source_at_call_time() -> None:
    """The behaviour `tasks.md` 5.5b is to justify, pinned independently of
    whether either class-patched declaration turns out to rebind."""
    first, second = _launch(), _launch()
    served = [first]
    store = FakeLaunches.serving(lambda: served)(A_SESSION)

    assert tuple(await store.list_active()) == (first,)

    served[0] = second

    assert tuple(await store.list_active()) == (second,)


async def test_each_serving_call_produces_a_subclass_of_its_own() -> None:
    first, second = _launch(), _launch()

    first_class = FakeLaunches.serving(first)
    second_class = FakeLaunches.serving(second)

    assert first_class is not second_class
    assert issubclass(first_class, FakeLaunches)
    assert tuple(await first_class(A_SESSION).list_active()) == (first,)
    assert tuple(await second_class(A_SESSION).list_active()) == (second,)


async def test_the_reads_answer_a_tuple() -> None:
    """DERIVED, and the one assertion in this file resting on an unresolved
    question: no artifact fixes the container type, and the locals disagree --
    `test_gate_progression_pass.py` returns a `tuple`, `test_automation_pass.py`
    a `list`. Every other assertion here converts before comparing, so this is
    the single test to revisit if the migration settles on `list`.
    """
    store = FakeLaunches(_launch())

    assert isinstance(await store.list_active(), tuple)
    assert isinstance(await store.list_all(), tuple)
