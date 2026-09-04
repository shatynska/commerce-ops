"""`InertBackoff`'s contract, stated directly.

The lockstep proof compares this fake against each local it replaces on the
calls those files execute -- which for the two carrying `mark_reported` alone is
that one method. The three the shared fake adds to those two are never called on
the local, so they are invisible to the pairing; that is the "surface the shared
fake adds" blind spot, and these tests plus the completeness search of task 6.3
are what stand in its place.
"""

from __future__ import annotations

import datetime

import pytest

from tests.support.fakes import InertBackoff

pytestmark = pytest.mark.anyio

WHEN = datetime.datetime(2027, 4, 1, 9, 0, tzinfo=datetime.UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_reads_no_backoff_for_any_step() -> None:
    """`None` is what production reads as "nothing recorded for this step"."""
    assert await InertBackoff().read("product-1", "step.one") is None


async def test_noting_an_outcome_records_nothing_to_read_back() -> None:
    backoff = InertBackoff()

    await backoff.note("product-1", "step.one", "failed", WHEN)

    assert await backoff.read("product-1", "step.one") is None


async def test_marking_reported_records_nothing_to_read_back() -> None:
    backoff = InertBackoff()

    await backoff.mark_reported("product-1", "step.one", WHEN)

    assert await backoff.read("product-1", "step.one") is None


async def test_rollback_is_inert_and_takes_no_arguments() -> None:
    """`automation_pass:713` awaits it bare, after a contained failure."""
    backoff = InertBackoff()

    await backoff.rollback()

    assert await backoff.read("product-1", "step.one") is None
