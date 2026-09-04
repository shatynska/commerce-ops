"""`playbook()`'s `fillers_first` parameter, stated directly.

`share-the-playbook-builders` adds exactly one parameter to the shared
builder, for the 8 local `_playbook` declarations that build
`steps=(*fillers, *steps)` rather than `steps=(*steps, *fillers)`. That
group cannot be reached from any existing parameter, and the reason is a
fact about the subject rather than about the builder:
`LaunchPlaybook.__post_init__` sorts `gates` and does **not** sort `steps`
(`launch_playbook.py:830-844`), so step order is part of `==` and cannot
be normalised away.

Two things follow, and both are asserted below rather than left implied.
The parameter *reorders* and never rebuilds -- the two orders hold the same
step set -- and the order is *observable at all*, which is what the design
decision rests on. Were the aggregate ever to start sorting its steps, the
order test here fails and says so, instead of the 8 migrated files quietly
agreeing with the 74 that did not need the parameter.

This is the shared harness's own behaviour, so it lives under
`tests/unit/support/` -- the deliberate exception to the tier layout, per
`AGENTS.md`.
"""

from __future__ import annotations

from collections.abc import Callable

from commerce_ops.launch.domain.launch_playbook import StepDefinition
from tests.support.playbook import SPECIFIED_GATE_ORDER, playbook
from tests.support.steps import hold

#: A blocking step of the test's own, holding one gate so that the other
#: seven are the ones filled. Its identifier is distinct from `hold()`'s so
#: that a filler can never be mistaken for it in an ordering assertion.
SUBJECT = hold("listable", identifier="subject.listable")


def _marker(gate: str) -> StepDefinition:
    """A filler distinguishable from the builder's default one."""
    return hold(gate, identifier=f"marker.{gate}")


def _fillers(
    filler: Callable[[str], StepDefinition] = hold,
) -> tuple[StepDefinition, ...]:
    """What `playbook()` fills the seven gates `SUBJECT` leaves unheld with."""
    return tuple(filler(gate) for gate in SPECIFIED_GATE_ORDER if gate != SUBJECT.gate)


def test_the_fillers_follow_the_steps_by_default() -> None:
    """Today's order, pinned before the parameter can move it.

    The 74 declarations that do not need `fillers_first` are proved against
    this order, and 13 files already migrated onto the builder assert on the
    tuple it produces.
    """
    built = playbook(SUBJECT)

    assert built.steps == (SUBJECT, *_fillers())


def test_fillers_first_puts_the_fillers_ahead_of_the_steps() -> None:
    built = playbook(SUBJECT, fillers_first=True)

    assert built.steps == (*_fillers(), SUBJECT)


def test_fillers_first_reorders_the_same_steps_rather_than_building_others() -> None:
    """The 8 declarations it takes are ORDER-ONLY: same steps, different
    order. A parameter that changed *which* steps were built would satisfy
    the two order assertions above and still be the wrong function."""
    default = playbook(SUBJECT)
    reordered = playbook(SUBJECT, fillers_first=True)

    assert set(reordered.steps) == set(default.steps)
    assert reordered.steps != default.steps


def test_fillers_first_is_inert_where_no_gate_is_filled() -> None:
    """`fill_unheld=False` builds no filler, so there is nothing to put
    first and the parameter must not perturb the steps it was handed."""
    reordered = playbook(SUBJECT, fill_unheld=False, fillers_first=True)

    assert reordered.steps == (SUBJECT,)
    assert reordered.steps == playbook(SUBJECT, fill_unheld=False).steps


def test_fillers_first_orders_a_supplied_filler_the_same_way() -> None:
    """Every migrated call passes its own filler (`design.md` -- Decision 7),
    so the parameter is never exercised against the built-in `hold` in
    practice. It orders whatever `filler` produced."""
    built = playbook(SUBJECT, fillers_first=True, filler=_marker)

    assert built.steps == (*_fillers(_marker), SUBJECT)


def test_supplied_step_order_is_read_back_rather_than_sorted() -> None:
    """What makes the parameter necessary at all.

    The two steps are supplied in an order that both plausible sorts --
    by identifier and by gate position -- would reverse. If
    `LaunchPlaybook.__post_init__` ever started sorting `steps` as it
    already sorts `gates`, this fails, and `fillers_first` would have
    become a parameter that cannot be observed.
    """
    later, earlier = hold("live"), hold("commit")

    built = playbook(later, earlier, fill_unheld=False)

    assert built.steps == (later, earlier)
