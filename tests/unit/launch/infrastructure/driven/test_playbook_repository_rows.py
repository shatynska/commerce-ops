"""Malformed stored playbook rows surface as errors, never as silence.

Re-homed coverage for the launch-playbook scenario *A malformed step is
reported alongside a coherence violation*, whose only test rode the
retired YAML-loader file boundary (`move-playbook-steps-to-postgres`
test manifest, scenario 17 / O-1). Post-change the raw-data boundaries
are the seed migration and the Postgres adapter's row parsing, and
"what a write cannot persist, a load cannot see" means malformed rows
cannot arrive through the write path — so what remains observable at
the unit tier is the adapter's parsing of a row shape the domain does
not recognize: it must refuse, naming what it cannot read, rather than
serving a silently wrong anchor. The aggregation half of the scenario
(every fault in one error) lives on in the write path
(`test_playbook_authoring.py::test_a_rejected_write_reports_all_faults_and_persists_nothing`)
and in `LaunchPlaybook` construction itself.
"""

from __future__ import annotations

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Cadence,
    OffsetAnchor,
    OpenEndedAnchor,
    RecurringAnchor,
    WindowAnchor,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    _anchor_from_json,
    _anchor_to_json,
)


def test_every_anchor_kind_round_trips() -> None:
    """The four anchor kinds survive the JSON row shape unchanged."""
    for anchor in (
        OffsetAnchor(days=-7),
        WindowAnchor(start=28, end=55),
        OpenEndedAnchor(start=1),
        RecurringAnchor(cadence=Cadence.WEEKLY),
    ):
        assert _anchor_from_json(_anchor_to_json(anchor)) == anchor


def test_an_unknown_anchor_kind_is_refused_by_name() -> None:
    """A stored row whose anchor kind the domain does not define is
    refused, naming the unreadable kind — never parsed as something else."""
    with pytest.raises(ValueError) as caught:
        _anchor_from_json({"kind": "fortnightly", "days": 3})

    assert "fortnightly" in str(caught.value)
