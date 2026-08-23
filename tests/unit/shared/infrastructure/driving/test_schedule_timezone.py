"""A schedule's due moments do not follow the host's timezone.

Covers the `scheduled-jobs` capability's requirement *Recurring Work Runs
On Its Declared Schedule*, scenario *The schedule's timezone does not
depend on the host*.

Preserved verbatim in substance from
`tests/unit/catalog/infrastructure/driving/test_daily_digest_job.py`,
which was retired with the daily product-name digest
(`introduce-launch-briefing`). That file carried this assertion even
though it derives from `scheduled-jobs` rather than from the retired
`product-monitoring` requirements, so deleting it with the digest would
have dropped a standing obligation silently. It lives here now, beside
the other `scheduled-jobs` tests, where its subject actually is.

It asserts the property of whichever daily schedule is registered — the
daily briefing today — rather than of any one job, which is why it did not
need rewriting when the digest gave up its slot.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from typing import Final

RUNNER_MODULE: Final = "commerce_ops.shared.infrastructure.driven.job_runner"
RUNNER_APP_ATTRIBUTE: Final = "app"
WORKER_MODULE: Final = "commerce_ops.worker"


def test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone() -> None:
    """Scenario: The schedule's timezone does not depend on the host.

    WHEN a schedule is evaluated on a host whose default timezone differs
    from the configured one
    THEN it SHALL be evaluated in the configured timezone.

    Run in subprocesses because the host's default timezone is read once,
    from the process environment: `TZ` cannot be changed meaningfully
    inside an already-running interpreter's imported modules.

    SPECIFIED: the hosts' due moments are identical, i.e. the schedule did
    not follow the host. DELIBERATELY UNTESTED here: *which* timezone was
    configured — the daily job's own test asserts its 06:00-UTC slot, and
    that is the same fact asserted once.
    """
    script = (
        "import datetime, json, sys, time\n"
        "time.tzset()\n"
        f"import {WORKER_MODULE}\n"
        f"from {RUNNER_MODULE} import {RUNNER_APP_ATTRIBUTE} as runner_app\n"
        "entries = list(runner_app.periodic_registry.periodic_tasks.values())\n"
        "daily = [e for e in entries if 'daily' in e.task.name.lower()][0]\n"
        "at = datetime.datetime(2026, 3, 10, 12, 0,\n"
        "    tzinfo=datetime.timezone.utc).timestamp()\n"
        "ticks = []\n"
        "for _ in range(3):\n"
        "    at = daily.croniter.get_next(ret_type=float, start_time=at)\n"
        "    ticks.append(at)\n"
        "print(json.dumps(ticks))\n"
    )

    outputs = {}
    for timezone_name in ("UTC", "Asia/Kolkata", "America/New_York"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "TZ": timezone_name},
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"evaluating the daily schedule under TZ={timezone_name} failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        outputs[timezone_name] = result.stdout.strip().splitlines()[-1]

    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "the daily schedule's due moments differ by the host's default "
        f"timezone, so the schedule follows the host: {outputs}"
    )

    # The subprocesses agreed; confirm they actually evaluated something,
    # rather than agreeing on an empty result.
    ticks = json.loads(distinct.pop())
    assert len(ticks) == 3
    assert all(
        datetime.datetime.fromtimestamp(tick, datetime.UTC).hour == 6 for tick in ticks
    ), f"the daily schedule's due moments are not at 06:00 UTC: {ticks}"
