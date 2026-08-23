"""The monitoring-notifier port `shared` exposes, and what satisfies it.

Derived from the OpenSpec change `report-overdue-scheduled-runs`:
tasks.md 2.1, 2.2 and 2.3, and design.md's "The overdue check reports
through a `Protocol` port, injected by `worker.py`".

**No `#### Scenario:` block of the delta spec maps to this file.** It is a
DERIVED precondition check, recorded as such in `test-manifest.md`: the
requirement "Overdue Work Is Reported To Slack From Inside The Deployment"
is about a message arriving, not about the mechanism that carries it. The
mechanism is nonetheless load-bearing and machine-enforced --
`.importlinter`'s `shared-boundary` contract forbids
`commerce_ops.shared` from importing `commerce_ops.launch` at all, so if
the structural satisfaction below does not hold there is no legal way for
the check in `shared` to reach the only adapter that posts to the
monitoring channel.

It mirrors `tests/unit/shared/infrastructure/driven/test_clickup_client.py`'s
`test_clickup_client_module_satisfies_the_writer_port_structurally`, which
tasks.md 2.3 names as the pattern. As design.md insists: the port is
satisfied by the **module**, not by the bare `post_monitoring_message`
function -- a `Protocol` declaring a method is not satisfied by a function
of that name, and the two must not be mixed up at the wiring site.

Nothing here is invented: tasks.md 2.1 fixes the Protocol's name, its home
in `shared/application/ports.py`, and its member's signature
(`post_monitoring_message(message: str) -> None`, async); tasks.md 2.2
fixes the export from `shared/application/__init__.py`'s `__all__`.

`MonitoringNotifier` does not exist at the time this pass was written, so
every test here is expected to fail on an absent target (`ImportError`)
until tasks 2.1 and 2.2 land.
"""

from __future__ import annotations

import inspect

import commerce_ops.catalog.infrastructure.driven.slack_notifier as products_slack_notifier
import commerce_ops.shared.application as shared_application
from commerce_ops.shared.application import MonitoringNotifier


def test_the_products_notifier_module_satisfies_the_port_structurally() -> None:
    """DERIVED, from tasks.md 2.3.

    The assignment is the assertion mypy checks; the `hasattr` below is
    what makes the test discriminate at runtime as well, since a `Protocol`
    that is not `runtime_checkable` costs nothing at runtime and an
    assignment alone would pass whatever the module contained.
    """
    notifier: MonitoringNotifier = products_slack_notifier

    assert hasattr(notifier, "post_monitoring_message"), (
        "products' slack_notifier module does not expose "
        "post_monitoring_message, so nothing satisfies MonitoringNotifier "
        "and the overdue check in `shared` has no legal route to the "
        "monitoring channel"
    )


def test_the_port_member_is_awaitable() -> None:
    """DERIVED, from tasks.md 2.1 ("as an async method").

    A synchronous notifier would be accepted by a `Protocol` whose member
    is declared `async` only under a type check, and the check's `await`
    would then raise at runtime inside whatever handles a delivery failure
    -- where it would be indistinguishable from Slack being down.
    """
    assert inspect.iscoroutinefunction(
        products_slack_notifier.post_monitoring_message
    ), (
        "post_monitoring_message is not a coroutine function; the port "
        "declares it async and the overdue check awaits it"
    )


def test_the_port_is_exported_from_the_modules_public_surface() -> None:
    """SPECIFIED by tasks.md 2.2, and by the module-boundary contract
    `AGENTS.md` records: a module's `application/__init__.py`
    (`__all__`-exported) is its only public surface.

    A `Protocol` reachable only by importing `shared.application.ports`
    directly is not exposed to other modules at all under that contract.
    """
    assert "MonitoringNotifier" in shared_application.__all__, (
        "MonitoringNotifier is not in shared.application.__all__, so it is "
        "not part of `shared`'s public surface; worker.py wires the "
        "notifier through it"
    )
