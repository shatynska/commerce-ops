"""A guarded tier tolerates no skipped test.

`tests/unit` and `tests/agents` run at commit time and in CI. A skipped
test there is invisible: the run reports success, the count moves by one,
and nothing says a requirement stopped being checked. Forty-four tests
were removed from this gate that way -- by two autouse fixtures matching
on *filename*, over five commits in one afternoon, each adding names to a
list, under a reason (`"Unit test requires database"`) that was false for
every one of them. `restore-the-skipped-unit-tests` restored them; this
guard is what stops it happening again.

The rule is deliberately absolute: **no skip at all**, rather than a rule
about blanket skips or about reason strings. Two narrower rules were
considered and rejected in that change's `design.md` Decision 3 -- "every
test in the file was skipped" is fragile under `-k` selection, and
inspecting reasons for a filename match is unenforceable. Zero tolerance
cannot be satisfied by widening a list, which is exactly how the defect
grew, and there is no list here to widen.

**`tests/integration` is guarded too, but only where the run says the tier
is required.** `COMMERCE_OPS_REQUIRE_DATABASE` already means exactly that
sentence: `tests/integration/conftest.py` turns its own no-database skip
into a failure when it is set, and CI sets it. So the marker is the line
between two populations, and it is a line this project had already drawn:

- **Marker set** -- the validation gate, and anything else declaring the
  tier required. No skip is tolerated, for any reason. The gate's own
  variable cannot see most of them: it fires only when *no* URL resolves,
  so a database that is present, reachable and merely named wrong left
  five tests skipping on every CI run while the job reported a pass. That
  is what this half exists to catch.
- **Marker unset** -- a developer's machine. The tier skips as it always
  has, and a skip fails nothing. The population with no database
  configured is the one least able to act on a failure, which is the
  trade-off `2026-08-25-verify-the-integration-tier`'s `design.md` argued
  and this change does not reverse.

Read once, at import, and never per report: a session is judged by one
rule, so a test that mutates the environment mid-run cannot change what
the session it is running in is held to. Decided by **truthiness** rather
than presence, matching how `tests/integration/conftest.py` reads the same
variable -- two readings of one variable is the class of silent
disagreement this guard exists to end.

## Two report kinds, because there are two shapes of whole-file skip

Each is invisible to the other's hook (measured, pytest 9.1.1):

- `pytestmark = pytest.mark.skip`, and any `pytest.skip()` raised in a
  test body or in a fixture during **setup**, collect the items and skip
  each -- one `TestReport` per test.
- `pytest.skip(..., allow_module_level=True)`, and a module-level
  `importorskip`, abort the module during **collection** -- no
  `TestReport` at all, only a `CollectReport`.

A guard reading `TestReport`s alone is blind to the second while pytest's
own summary still counts it as skipped, so a single line at the top of a
file could take it out of the gate silently. Both are read.

Note that `pytest_collection_modifyitems` sees neither: the historical
defect skipped during fixture setup, long after collection. A guard
written there would pass vacuously.

## Why this file is at `tests/`, not `tests/unit/`

A conftest is loaded only for the paths actually collected, so a hook
under `tests/unit/` would not be registered by `uv run pytest
tests/agents` -- leaving that tier unguarded and silent. Placed here it
is loaded for any invocation under `tests/`, and the *path filter* below,
not this file's location, is what decides which tiers a given run guards.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import pytest

#: Set where the integration tier is required and may not be skipped -- CI
#: sets it, `pre-push` deliberately does not. The same variable
#: `tests/integration/conftest.py` reads to turn its no-database skip into
#: a failure; read the same way here, by truthiness, so an empty value
#: cannot mean "unset" to one and "set" to the other.
REQUIRE_DATABASE: Final = "COMMERCE_OPS_REQUIRE_DATABASE"

# Tiers that run on every commit. A skip beneath one of these always fails
# the run.
_COMMIT_TIME_TIERS: Final = ("unit", "agents")

# Tier directories, relative to this file. A skip anywhere beneath one of
# these fails the run; anywhere else is left alone. Evaluated once, at
# import, so both report hooks below judge the whole session by the rule it
# began under -- see the module docstring.
_GUARDED_TIERS: Final[tuple[str, ...]] = (
    (*_COMMIT_TIME_TIERS, "integration")
    if os.environ.get(REQUIRE_DATABASE)
    else _COMMIT_TIME_TIERS
)

_TESTS_ROOT = Path(__file__).resolve().parent

# Accumulated across the session, then reported once at the end. Module
# state rather than a fixture: the guard must observe runs it is not a
# participant in, including sessions where no test requests anything.
_skips: list[tuple[str, str]] = []


def _is_guarded(path_text: str) -> bool:
    """Whether a report's path lies under a tier that tolerates no skip.

    Resolved against this file's own location rather than the rootdir or
    the invocation's cwd, so a hand-run from inside a tier directory is
    judged the same as a full-tier run.
    """
    if not path_text:
        return False
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    for tier in _GUARDED_TIERS:
        tier_root = _TESTS_ROOT / tier
        if candidate == tier_root or tier_root in candidate.parents:
            return True
    return False


def _reason(report: object) -> str:
    """The skip's stated reason, however pytest happens to carry it.

    `longrepr` is a `(path, lineno, message)` triple for a skipped test
    and a string or representation object for a skipped collection, so
    neither shape is assumed.
    """
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2])
    if longrepr is not None:
        return str(longrepr)
    return "no reason given"


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """A test that was skipped -- in its body, or by a fixture at setup.

    `report.skipped` is also true for an `xfail`ed test, which is a
    different thing entirely and must not be banned here: pytest marks
    those with a `wasxfail` attribute, so they are excluded explicitly.
    """
    if not report.skipped:
        return
    if hasattr(report, "wasxfail"):
        return
    if not _is_guarded(str(getattr(report, "fspath", "") or "")):
        return
    _skips.append((report.nodeid, _reason(report)))


def pytest_collectreport(report: pytest.CollectReport) -> None:
    """A whole module skipped during collection.

    `pytest.skip(..., allow_module_level=True)` and a module-level
    `importorskip` never produce a `TestReport`, so this is the only hook
    that sees them.
    """
    if not report.skipped:
        return
    if not _is_guarded(str(getattr(report, "fspath", "") or report.nodeid or "")):
        return
    _skips.append((report.nodeid, _reason(report)))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the session, naming every skip and its reason.

    Named, because a run that fails without saying which test skipped or
    why leaves the next reader to rediscover it -- and a *false* reason
    attached to a skip is what this guard exists to prevent recurring.

    Fails by setting `session.exitstatus`, never by raising: an exception
    escaping this hook produces a raw `pluggy` traceback and reports
    neither the test nor the reason, which is the whole point of the
    guard.
    """
    if not _skips:
        return

    tiers = ", ".join(f"tests/{tier}" for tier in _GUARDED_TIERS)
    headline = (
        f"{len(_skips)} skipped test(s) in {tiers}, which tolerate none in this run:"
    )
    lines = ["", "=" * 72, headline, ""]
    for nodeid, reason in _skips:
        lines.append(f"  SKIPPED  {nodeid}")
        lines.append(f"           reason: {reason}")
    lines += [
        "",
        "A skip in a guarded tier removes a check without failing anything,",
        "which is why it fails the run instead. If a test genuinely cannot",
        "run, delete it and record why -- do not skip it, and do not route",
        "it through xfail, which this guard exempts for expectations that",
        "are named rather than checks that are withdrawn.",
    ]
    if "integration" in _GUARDED_TIERS:
        lines += [
            "",
            f"tests/integration is guarded here because {REQUIRE_DATABASE} is",
            "set, which says the tier is required in this run. Unset it and a",
            "skip there reports and fails nothing -- but do that only on a",
            "machine, never in a gate.",
        ]
    lines += [
        "See tests/conftest.py for why this rule admits no exceptions.",
        "=" * 72,
        "",
    ]
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line("\n".join(lines))
    else:
        print("\n".join(lines))

    session.exitstatus = 1


def pytest_unconfigure(config: pytest.Config) -> None:
    """Leave no state behind for a second session in the same process."""
    _skips.clear()
