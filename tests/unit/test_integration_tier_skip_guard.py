"""The gate tolerates no skipped integration test; a developer's run does.

Covers the four scenarios `restore-the-skipped-integration-tests` adds to
`deploy-pipeline`'s *Pull Request Validation Gate* requirement — the half of
that requirement that reaches `tests/integration`:

- *A test the gate's database does not satisfy fails rather than skipping*
- *A test skipped for an unmet precondition fails rather than passing*
- *An expected failure is not treated as a skip*
- *A developer's run is not held to the gate's rule*

The subject is the guard in `tests/conftest.py`. Today that guard covers
`tests/unit` and `tests/agents` unconditionally and excludes
`tests/integration` unconditionally; the change makes the integration half
conditional on `COMMERCE_OPS_REQUIRE_DATABASE`, the marker `ci.yml` already
sets and a developer's machine does not. See `tasks.md` §2 and `design.md`
Decision 1.

## Why a separate file from `test_commit_time_tier_skip_guard.py`

That file is the spec-derived test for the same guard's commit-time half,
written by `restore-the-skipped-unit-tests`. This pass may add tests and
never subtract or amend one, so the new cases land here rather than being
folded into it. `tasks.md` 5.3 assigned the one edit that file needed — its
`test_the_integration_tier_may_still_skip`, whose docstring called the
integration exclusion unconditional — to whoever implemented §2, and that
edit was made in the same commit that added this file: it is now
`test_the_integration_tier_may_still_skip_without_the_marker`, and it
holds the unarmed half while
`test_a_developers_run_is_not_failed_by_a_skipped_integration_test` below
holds it here. The two files assert opposite outcomes for the same tier
because they differ in one environment variable, which is the whole
behaviour. Neither inherits the marker: `_run` in each builds its child
environment as `{"PATH": ...}`, so a job-level marker cannot reach them.

## Expected first-run state (measured, see `test-manifest.md`)

`tests/conftest.py`'s `_GUARDED_TIERS` is `("unit", "agents")` and is not
conditioned on anything, so on the unmodified tree:

- the three cases requiring the guard to *fire* on an integration skip
  under the marker FAIL — and fail in the strongest of the four states the
  `testing` standard names: the guard exists, the session runs, and it
  produces the wrong answer (exit 0). They discriminate.
- the developer-machine cases, the expected-failure case, the commit-time
  controls and the marker-latching cases PASS — several of them vacuously,
  because today the integration tier is excluded whatever the marker says.
  They are here as the controls that stop the three above being satisfied
  by a guard that simply fails harder, and they become non-vacuous the
  moment §2 lands.

Do not modify `tests/conftest.py` to make anything here pass; writing it is
`tasks.md` 2.1's job.

## Mechanism, inherited rather than invented

Each case builds a synthetic three-tier tree in `tmp_path`, copies the real
`tests/conftest.py` into it verbatim, and runs a fresh `pytest` over it in a
child process whose environment is constructed from scratch. That is
`test_commit_time_tier_skip_guard.py`'s pattern and its reasoning applies
unchanged (`pytester` is unavailable without editing the file under test;
`runpytest_inprocess` would register the guard's hooks against this
session). The helpers are duplicated rather than imported so that the two
files can be edited independently — importing one test module from another
would also make `tasks.md` 5.3's rewrite of that file able to break this
one.

The environment being built from scratch is what makes these cases cheap:
`COMMERCE_OPS_REQUIRE_DATABASE` is one dict entry, present or absent, and
nothing in the outer shell can reach the child to contradict it.

## The synthetic tree deliberately omits `addopts = "-rs"`

The real `pyproject.toml` carries `-rs`, which prints every skip and its
reason. Inheriting it would make every "names the test and its reason"
assertion here pass vacuously, since pytest itself would have printed what
the guard is required to print. Under pytest's default reporting a skipped
test contributes an `s` and no name, so a nodeid or a reason in the output
can only have come from the guard. The one case that *wants* `-rs` —
`test_a_developers_run_still_reports_the_skipped_test_and_its_reason` —
passes it explicitly on the command line and says why.

## This file must never skip

It lives under `tests/unit`, so a `pytest.skip` here would trip the very
guard it exercises. Nothing here is conditional.

## Specified, derived, deliberately untested

SPECIFIED by the delta's four added scenarios:

- an integration test that declines the gate's database fails the gate,
  named, with its reason (scenario *A test the gate's database does not
  satisfy...*);
- an integration test skipped for a precondition unrelated to the database
  fails the gate, named, with its reason (scenario *A test skipped for an
  unmet precondition...*);
- an `xfail`ed integration test does not fail the gate and is reported as
  an expected failure rather than as a skip (scenario *An expected failure
  is not treated as a skip*);
- a skip outside the gate is reported and does not fail the run (scenario
  *A developer's run is not held to the gate's rule*).

SPECIFIED by the requirement's own prose rather than by a scenario:

- that the commit-time tiers stay guarded with the marker absent. The
  requirement scopes the exemption to *the integration tier*
  ("the integration tier SHALL skip as it does today"), and `proposal.md`
  — Capabilities states the consequence outright: "a skip in the
  commit-time tiers fails a developer's run today and continues to." This
  is also the control that stops the developer-machine scenario being
  satisfied by an implementation that disarms the whole guard.
- that the commit-time tiers stay guarded with the marker set. "The
  widened rule reads on **every** tier the gate runs, `tests/unit` and
  `tests/agents` included" (`proposal.md` — Capabilities).
- that a whole integration module skipped at *collection* fails the gate.
  `tasks.md` 2.1: "Reuse `_is_guarded`, both report hooks and
  `pytest_unconfigure` unchanged". The requirement's "any test skipped in
  that tier ... whatever the skip's stated reason" does not distinguish the
  two report kinds, and `tests/conftest.py`'s own docstring records that a
  guard reading only `TestReport`s is blind to this shape.

SPECIFIED by `tasks.md` 2.2 rather than by a scenario:

- that the session is judged by the marker as the session began, so a test
  mutating the environment mid-run changes neither the rule the session is
  held to nor its disarming.

DERIVED — that a clean integration run under the marker exits zero
(`test_a_clean_integration_run_under_the_marker_is_left_alone`). No
scenario states it, because a guard that fails every marked session reads
as absurd. But all three firing cases above are satisfied by exactly that
guard, so this is the control that tells them apart.

DELIBERATELY UNTESTED — `COMMERCE_OPS_REQUIRE_DATABASE` set to the empty
string. `tasks.md` 2.1 says "set in the environment", which reads as
presence; `tests/integration/conftest.py:220` decides the same question by
`os.environ.get(...)` truthiness, which reads as non-empty. The two
readings disagree and nothing in the change settles it, so no assertion
here depends on the answer: every case below either sets the marker to
`"1"` or omits the key entirely. Raised in `test-manifest.md` as an
unresolved project question.

DELIBERATELY UNTESTED — the reachability carve-out ("not a database a test
deliberately points at in order to observe how the system behaves when one
is unreachable"). It states that such a test SHALL run and is subject to
the skip rule like any other, which is the rule these cases already assert;
it adds no distinguishable behaviour to the guard, whose only input is a
skipped report and its path.

DELIBERATELY UNTESTED — that `ci.yml`'s database is named `commerce_ops_test`
(`tasks.md` §1) and that the tier's last skip is gone (§3). Both are
verified by running the real integration tier (`tasks.md` 7.3, 7.5), not by
a unit-tier assertion about a workflow file's text.

Not asserted anywhere: the guard's wording, its exit code beyond being
non-zero, or where it writes. A guard is free to phrase its report however
it likes — the requirement constrains that it names the test and the
reason, not how.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

# `tests/conftest.py` -- this file is `tests/unit/test_....py`.
GUARD_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"

# The real `pyproject.toml`, for the one case whose subject is this
# project's own reporting configuration rather than the guard.
PROJECT_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# The marker `ci.yml` sets on the validation job, and which a developer's
# machine does not set. `design.md` Decision 1: it already means "this is a
# context where the tier is required and may not be skipped", which is
# exactly the sentence the guard needs, so no second variable is introduced.
GATE_MARKER = "COMMERCE_OPS_REQUIRE_DATABASE"

COMMIT_TIME_TIERS = ("unit", "agents")
INTEGRATION_TIER = "integration"

# Deliberately without `-rs`; see the module docstring.
SYNTHETIC_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
"""

A_PASSING_TEST = """\
def test_that_passes() -> None:
    assert True
"""

# The two reasons the tier actually produces today, transcribed so the
# cases below are about the real shapes rather than invented ones.
#
# `tests/integration/launch/test_playbook_readiness_live.py:137` -- the
# database is present, reachable and prepared, and the test declines it.
DECLINED_DATABASE_REASON = (
    "this module rewrites the stored step set and restores it, so it runs "
    "only against an isolated test database. Resolved database was "
    "'commerce_ops'."
)
# `tests/integration/launch/test_registered_handlers_activate_nothing.py:345`
# -- nothing to do with the database at all.
UNMET_PRECONDITION_REASON = (
    "no seeded automated step names a handler this deployment registers, "
    "so there is nothing here to discriminate on"
)


def _skipping_test(function: str, reason: str) -> str:
    return f'''\
import pytest


def {function}() -> None:
    pytest.skip("{reason}")
'''


def _module_level_skip(reason: str) -> str:
    """A whole file taken out during collection.

    `pytest.skip(..., allow_module_level=True)` produces no `TestReport` at
    all -- only a `CollectReport` -- so a guard reading reports alone is
    blind to it while pytest's summary still counts it as skipped.
    """
    return f'''\
import pytest

pytest.skip("{reason}", allow_module_level=True)


def test_never_collected() -> None:
    raise AssertionError("unreachable")
'''


def _fixture_skipping_conftest(reason: str) -> str:
    """The tier's real shape: an autouse fixture that inspects the resolved
    database name and declines, during setup rather than at collection --
    `test_playbook_readiness_live.py:126`."""
    return f'''\
import pytest


@pytest.fixture(autouse=True)
def _requires_an_isolated_database() -> None:
    pytest.skip("{reason}")
'''


def _marker_mutating_test(function: str, value: str | None) -> str:
    """A test that sets or unsets the gate's marker mid-session.

    `tasks.md` 2.2: the guard reads the marker once, where the tier set is
    decided, so one session is judged by one rule whatever a test later
    does to the environment.
    """
    mutation = (
        f'os.environ["{GATE_MARKER}"] = "{value}"'
        if value is not None
        else f'os.environ.pop("{GATE_MARKER}", None)'
    )
    return f"""\
import os


def {function}() -> None:
    {mutation}
"""


@dataclass(frozen=True)
class GuardRun:
    """One synthetic pytest session, as this process observed it."""

    exit_code: int
    output: str
    invocation: str

    @property
    def fired(self) -> bool:
        return self.exit_code != 0

    def context(self) -> str:
        return (
            f"invocation: {self.invocation}\n"
            f"exit code: {self.exit_code}\n"
            f"output:\n{self.output}"
        )


def _guard_source() -> str:
    """The guard as it stands in this repository.

    Read rather than imported: `tests/conftest.py` is a conftest, and
    importing it into this session would register its hooks against the
    session running this file.
    """
    assert GUARD_CONFTEST.is_file(), (
        f"{GUARD_CONFTEST} does not exist, so there is no guard to exercise "
        "and every test in this file is failing on an absent target rather "
        "than on anything it asserts. The file is expected to be present -- "
        "`restore-the-skipped-unit-tests` added it on 2026-09-01 and this "
        "change extends it. Do not create it here."
    )
    return GUARD_CONFTEST.read_text(encoding="utf-8")


def _tree(root: Path, files: dict[str, str]) -> Path:
    """A synthetic three-tier `tests/` tree with the real guard installed.

    All three tier directories exist whether or not `files` puts anything
    in them, so the guard's path filter always has the same shape to
    resolve against.

    Basenames must be unique across the whole tree. The synthetic tree
    carries no `__init__.py`, so two files sharing a basename in different
    tiers collide on import and pytest aborts collection with exit 2 --
    which a case expecting the guard to fire reads as success. Caught
    while writing this file, so it is asserted rather than left as a
    convention: the failure it produces is a broken test wearing the
    costume of a passing one.
    """
    basenames = [Path(relative).name for relative in files]
    duplicates = sorted({name for name in basenames if basenames.count(name) > 1})
    assert not duplicates, (
        f"the synthetic tree reuses the basename(s) {duplicates} across "
        "tiers. With no `__init__.py` anywhere, pytest fails to import the "
        "second and aborts collection (exit 2) before any test runs -- so "
        "the session's non-zero status says nothing about the guard. Give "
        "each file a name unique to the tree."
    )
    (root / "pyproject.toml").write_text(SYNTHETIC_PYPROJECT, encoding="utf-8")
    tests = root / "tests"
    for tier in (*COMMIT_TIME_TIERS, INTEGRATION_TIER):
        (tests / tier).mkdir(parents=True, exist_ok=True)
    (tests / "conftest.py").write_text(_guard_source(), encoding="utf-8")
    for relative, body in files.items():
        path = tests / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _run(
    root: Path,
    *targets: str,
    marker: str | None = None,
    cwd: Path | None = None,
) -> GuardRun:
    """Run a fresh pytest over the synthetic tree.

    The environment is built from scratch rather than inherited, so neither
    a `PYTEST_ADDOPTS` nor a real `COMMERCE_OPS_REQUIRE_DATABASE` in the
    outer shell can reach the child and change what it does. `marker=None`
    means the key is absent entirely -- the developer's machine -- rather
    than present and empty, a state the module docstring records as
    deliberately untested.
    """
    working = cwd if cwd is not None else root
    environment = {"PATH": os.environ.get("PATH", "")}
    if marker is not None:
        environment[GATE_MARKER] = marker
    command = [sys.executable, "-m", "pytest", *targets, "-p", "no:cacheprovider"]
    result = subprocess.run(
        command,
        env=environment,
        cwd=str(working),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    marker_text = (
        f"{GATE_MARKER}={marker!r}" if marker is not None else f"no {GATE_MARKER}"
    )
    return GuardRun(
        exit_code=result.returncode,
        output=result.stdout + result.stderr,
        invocation=f"{' '.join(['pytest', *targets])} ({marker_text}, cwd={working})",
    )


def _assert_failed_cleanly(run: GuardRun) -> None:
    """The guard fails a session by setting `session.exitstatus`, never by
    raising inside a hook.

    A session that dies in the hook reports neither which test skipped nor
    why, which is the whole point of the guard. Both shapes an escaping
    exception can take are checked: against pytest 9.1.1 the observed shape
    is a raw `pluggy` traceback naming the hook, with no `INTERNALERROR`
    banner -- measured by `test_commit_time_tier_skip_guard.py`, whose
    finding this reuses rather than re-derives.
    """
    escaped = "Traceback (most recent call last)" in run.output and (
        "pytest_sessionfinish" in run.output
        or "pytest_runtest_logreport" in run.output
        or "pytest_collectreport" in run.output
    )
    assert "INTERNALERROR" not in run.output and not escaped, (
        "an exception escaped the guard's hook instead of it failing the "
        "session cleanly. `tests/conftest.py` documents the rule it must "
        "keep: fail by setting `session.exitstatus`, never by raising -- a "
        "session that dies in the hook names neither the test nor the "
        f"reason.\n{run.context()}"
    )


def _assert_fired(run: GuardRun, *expected: str) -> None:
    """The guard failed the session and named what it objected to."""
    _assert_failed_cleanly(run)
    assert run.fired, (
        "the session exited zero despite a skipped test in a tier that, in "
        "this session, tolerates none. This is the defect the change "
        "exists to close: the validation gate ran 132 of 137 integration "
        "tests and reported a pass, because a skip removes a check without "
        f"failing anything.\n{run.context()}"
    )
    for fragment in expected:
        assert fragment in run.output, (
            f"the guard failed the session but never named {fragment!r}. "
            "The requirement: the gate SHALL name each skipped test and its "
            "reason, so that the failure identifies what stopped being "
            "checked rather than only that something did. (The synthetic "
            "tree omits `-rs` deliberately, so nothing but the guard prints "
            f"this.)\n{run.context()}"
        )


def _assert_silent(run: GuardRun, why: str) -> None:
    """The guard left the session alone."""
    _assert_failed_cleanly(run)
    assert not run.fired, f"{why}\n{run.context()}"


# ---------------------------------------------------------------------------
# Under the gate's marker, an integration skip fails the session
# ---------------------------------------------------------------------------


def test_an_integration_test_declining_the_gates_database_fails_the_gate(
    tmp_path: Path,
) -> None:
    """Scenario: *A test the gate's database does not satisfy fails rather
    than skipping.*

    SPECIFIED. The database is present, reachable and prepared, and the
    test declines it anyway -- `_requires_an_isolated_database` refuses a
    name not ending `_test`, which is what removed five tests from the gate
    with `pytest` exiting 0 throughout.

    Modelled as an autouse fixture skipping during *setup*, which is the
    real shape and the one `pytest_collection_modifyitems` cannot see. The
    commit-time tiers carry passing tests here, so a firing guard cannot be
    accounted for by anything but the integration skip.
    """
    root = _tree(
        tmp_path,
        {
            "integration/conftest.py": _fixture_skipping_conftest(
                DECLINED_DATABASE_REASON
            ),
            "integration/test_needs_isolation.py": A_PASSING_TEST,
            "unit/test_healthy.py": A_PASSING_TEST,
            "agents/test_healthy_too.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker="1")

    _assert_fired(
        run,
        "test_needs_isolation.py::test_that_passes",
        "isolated test database",
    )


def test_an_integration_test_skipped_for_an_unmet_precondition_fails_the_gate(
    tmp_path: Path,
) -> None:
    """Scenario: *A test skipped for an unmet precondition fails rather
    than passing.*

    SPECIFIED, and the case that establishes the widening. The old
    requirement reached only an absent or unreachable database; this skip
    has nothing to do with the database at all -- it is a test finding
    nothing to discriminate on. A guard that fired only on
    database-flavoured reasons would pass the case above and fail here,
    which is why the two are separate tests over the same mechanism rather
    than one parametrisation.
    """
    root = _tree(
        tmp_path,
        {
            "integration/test_precondition.py": _skipping_test(
                "test_precondition", UNMET_PRECONDITION_REASON
            ),
            "integration/test_healthy_integration.py": A_PASSING_TEST,
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker="1")

    _assert_fired(
        run,
        "test_precondition.py::test_precondition",
        "nothing here to discriminate on",
    )


def test_a_whole_integration_module_skipped_at_collection_fails_the_gate(
    tmp_path: Path,
) -> None:
    """`tasks.md` 2.1 -- "both report hooks", applied to the new tier.

    SPECIFIED by the requirement's "any test skipped in that tier, whatever
    the skip's stated reason", which does not distinguish how pytest
    happens to report the skip. A module-level skip produces a
    `CollectReport` and no `TestReport`, so a guard that reuses only
    `pytest_runtest_logreport` for the integration tier passes both cases
    above and lets a single line at the top of a file take a whole module
    out of the gate silently -- exactly the shape `tests/conftest.py`'s own
    docstring says the second hook exists for.
    """
    root = _tree(
        tmp_path,
        {
            "integration/test_whole_module.py": _module_level_skip(
                DECLINED_DATABASE_REASON
            ),
            "integration/test_healthy_integration.py": A_PASSING_TEST,
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker="1")

    _assert_fired(run, "test_whole_module.py", "isolated test database")


# ---------------------------------------------------------------------------
# An expected failure is not a skip
# ---------------------------------------------------------------------------


def test_an_expected_failure_in_the_integration_tier_is_not_treated_as_a_skip(
    tmp_path: Path,
) -> None:
    """Scenario: *An expected failure is not treated as a skip.*

    SPECIFIED, both halves. `TestReport.skipped` is true for an `xfail`ed
    test as well as a skipped one, so a guard that does not distinguish
    them bans a marker nobody proposed banning -- under the marker, where
    the integration tier is newly guarded, that is a live risk rather than
    a theoretical one. `design.md` Decision 6 puts the exclusion in the
    requirement rather than leaving it to the implementation.

    The second THEN -- reported *as an expected failure rather than as a
    skip* -- is asserted two ways: pytest's own summary must say `xfailed`,
    and the test's nodeid must be absent from the output. The synthetic
    tree omits `-rs`, so pytest names nothing itself; a nodeid appearing
    could only be the guard listing it among the skips.
    """
    expected_failure = """\
import pytest


@pytest.mark.xfail(reason="the tier is expected to fail this one")
def test_expected_failure() -> None:
    raise AssertionError("as expected")
"""
    root = _tree(
        tmp_path,
        {
            "integration/test_expected_failure.py": expected_failure,
            "integration/test_healthy_integration.py": A_PASSING_TEST,
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker="1")

    _assert_silent(
        run,
        "the guard failed a session under the gate's marker over an "
        "`xfail`ed integration test. An expected failure is a named, "
        "visible expectation carried in the run's own report, not a check "
        "withdrawn without notice, and the requirement excludes it "
        "explicitly.",
    )
    assert "xfailed" in run.output, (
        "the session did not report the test as an expected failure. The "
        "requirement's second THEN: it SHALL be reported as an expected "
        f"failure rather than as a skip.\n{run.context()}"
    )
    assert "test_expected_failure.py::test_expected_failure" not in run.output, (
        "the expected failure was named in the session's output, which "
        "under this tree can only be the guard listing it among the skips. "
        "It must be reported as an expected failure, not as a skip."
        f"\n{run.context()}"
    )


# ---------------------------------------------------------------------------
# Outside the gate, a developer's run is left alone
# ---------------------------------------------------------------------------


def test_a_developers_run_is_not_failed_by_a_skipped_integration_test(
    tmp_path: Path,
) -> None:
    """Scenario: *A developer's run is not held to the gate's rule*, second
    THEN.

    SPECIFIED. With the marker absent the integration tier skips as it does
    today and the run must not fail. `design.md` Decision 1: guarding the
    tier unconditionally would fail a contributor with no local Postgres
    for a condition they cannot act on, and "the population that has
    configured no database is the one least able to act on a failure".

    Both integration skip shapes are present, so an implementation that
    conditions only one of the two hooks on the marker fails here.

    Passes vacuously on the unmodified tree, where the tier is excluded
    whatever the marker says; it becomes discriminating the moment §2 lands.
    """
    root = _tree(
        tmp_path,
        {
            "integration/test_no_database.py": _skipping_test(
                "test_no_database", "No database is configured for the tier"
            ),
            "integration/test_whole_module.py": _module_level_skip(
                DECLINED_DATABASE_REASON
            ),
            "unit/test_healthy.py": A_PASSING_TEST,
            "agents/test_healthy_too.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker=None)

    _assert_silent(
        run,
        "the guard failed a run on a machine where the gate's marker is "
        "not set. This obligation belongs to the gate and does not extend "
        "to a run outside it: outside the gate the integration tier SHALL "
        "skip as it does today, and a skip there SHALL NOT fail the run.",
    )


def test_a_developers_run_still_reports_the_skipped_test_and_its_reason(
    tmp_path: Path,
) -> None:
    """Scenario: *A developer's run is not held to the gate's rule*, first
    THEN -- "the run SHALL report the skip and its reason".

    SPECIFIED. Exempting the run from failure is not licence to hide what
    did not run: the reader on a developer's machine is the one who can act
    on the reason, and the skip messages in this tier carry the setup
    instructions. That reporting is pytest's `-rs`, which the real
    `pyproject.toml` sets and this synthetic tree deliberately does not, so
    the flag is passed explicitly here and
    `test_the_projects_own_configuration_reports_skips` holds the other
    half -- that the real suite runs with it.

    `-rs` names the skip by *file and line* -- `SKIPPED [1]
    tests/integration/test_no_database.py:5: <reason>` -- not by nodeid,
    measured against pytest 9.1.1 rather than assumed. The first draft of
    this case asserted a nodeid and failed on its own mistake, which is the
    third of the four failure states the `testing` standard names and
    establishes nothing about the guard. The assertion is on the file and
    the reason, which is what the requirement asks be reported.
    """
    reason = "No database is configured for the integration tier"
    root = _tree(
        tmp_path,
        {
            "integration/test_no_database.py": _skipping_test(
                "test_no_database", reason
            ),
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", "-rs", marker=None)

    _assert_silent(
        run,
        "the guard failed a developer's run over a skipped integration "
        "test. See the paired case above; this one differs only in asking "
        "pytest to report the skip.",
    )
    assert "test_no_database.py" in run.output and reason in run.output, (
        "the run did not name the skipped test and its reason. The "
        "requirement: outside the gate the run SHALL report the skip and "
        "its reason -- the skip is exempt from failing the run, not from "
        f"being visible in it.\n{run.context()}"
    )


def test_the_projects_own_configuration_reports_skips() -> None:
    """Scenario: *A developer's run is not held to the gate's rule*, first
    THEN -- the real subject.

    SPECIFIED. The case above establishes that pytest reports a skip and
    its reason when asked; this establishes that this project asks. `-rs`
    is what makes "the run SHALL report the skip and its reason" true of an
    actual `uv run pytest tests/integration`, and `pyproject.toml`'s own
    comment records why it is set: the default `-r fE` hides skip reasons,
    "which is how a run reporting '64 skipped' was once read as a passing
    integration tier".

    Asserted on the file's text rather than through a pytest API because
    the subject is the recorded configuration, not this session's resolved
    options -- which any `-p`/`-o` on the invocation could have overridden.
    """
    configuration = tomllib.loads(PROJECT_PYPROJECT.read_text(encoding="utf-8"))
    addopts = (
        configuration.get("tool", {})
        .get("pytest", {})
        .get("ini_options", {})
        .get("addopts", "")
    )

    # Read the parsed `addopts` value, never the file's text. `-rs` also
    # appears in the comment above the setting, so a substring search over
    # the whole file passes even when the setting itself is deleted -- a
    # tautology, and one this file of all files should not carry.
    assert "-rs" in addopts, (
        f"{PROJECT_PYPROJECT}'s pytest `addopts` is {addopts!r}, which no "
        "longer carries `-rs`. Without it pytest's default `-r fE` prints a skip "
        "count and no reason, and a developer's run -- which the "
        "requirement exempts from failing on a skip -- stops reporting "
        "what did not run at all. The exemption is from failing, not from "
        "reporting."
    )


# ---------------------------------------------------------------------------
# The commit-time tiers are unaffected in either direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "marker",
    ["1", None],
    ids=["under the gate's marker", "on a developer's machine"],
)
def test_the_commit_time_tiers_stay_guarded_whatever_the_marker_says(
    tmp_path: Path, marker: str | None
) -> None:
    """SPECIFIED by the requirement's prose, and the control the
    developer-machine scenario needs.

    The exemption is scoped to the *integration tier* -- "the integration
    tier SHALL skip as it does today". `proposal.md` -- Capabilities states
    both halves outright: the widened rule reads on every tier the gate
    runs, `tests/unit` and `tests/agents` included, and "a skip in the
    commit-time tiers fails a developer's run today and continues to."

    Without this, the developer-machine scenario is satisfied by an
    implementation that makes the *whole* guard conditional on the marker
    -- which would silently return `tests/unit` and `tests/agents` to the
    state that lost forty-four tests in one afternoon, while every other
    case in this file still passed.

    One skip in each guarded tier, so a condition applied to only one of
    them is caught.
    """
    unit_reason = "a deliberately skipped unit test"
    agents_reason = "a deliberately skipped agent-graph test"
    root = _tree(
        tmp_path,
        {
            "unit/test_matched.py": _skipping_test("test_matched", unit_reason),
            "agents/test_elsewhere.py": _skipping_test("test_elsewhere", agents_reason),
            "integration/test_healthy_integration.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker=marker)

    _assert_fired(
        run,
        "test_matched.py::test_matched",
        unit_reason,
        "test_elsewhere.py::test_elsewhere",
        agents_reason,
    )


def test_a_clean_integration_run_under_the_marker_is_left_alone(
    tmp_path: Path,
) -> None:
    """DERIVED, and the control the three firing cases rest on.

    No scenario states it: a guard that fails every session in which the
    marker is set reads as absurd. But each firing case above is satisfied
    by exactly that guard, so without this they establish nothing -- they
    would all pass against a hook that set a non-zero exit status whenever
    `COMMERCE_OPS_REQUIRE_DATABASE` was present.
    """
    root = _tree(
        tmp_path,
        {
            "unit/test_healthy.py": A_PASSING_TEST,
            "agents/test_healthy_too.py": A_PASSING_TEST,
            "integration/test_healthy_as_well.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker="1")

    _assert_silent(
        run,
        "the guard failed a session under the gate's marker in which "
        "nothing was skipped at all. Every firing case in this file would "
        "also pass against a guard that failed whenever the marker was "
        "set, so this is what tells the two apart.",
    )


# ---------------------------------------------------------------------------
# One session, one rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("marker", "mutation", "expect_fired"),
    [
        ("1", None, True),
        (None, "1", False),
    ],
    ids=["marker unset mid-session", "marker set mid-session"],
)
def test_the_session_is_judged_by_the_marker_as_the_session_began(
    tmp_path: Path, marker: str | None, mutation: str | None, expect_fired: bool
) -> None:
    """`tasks.md` 2.2 -- read the flag once, where the tier set is decided,
    rather than per report.

    SPECIFIED by that task rather than by a scenario. Both directions
    matter and they fail differently: a guard re-reading the environment
    per report can be *disarmed* mid-session by a test that pops the key
    (the first case, which is the one with teeth -- it would hand a future
    author a one-line way out of the gate), and can be *armed* mid-session
    against a developer who was never subject to it (the second).

    The mutating test is placed so that it runs before the skipping one:
    within `tests/integration` pytest collects files in name order, and
    `test_a_...` precedes `test_b_...`.
    """
    root = _tree(
        tmp_path,
        {
            "integration/test_a_mutates_the_marker.py": _marker_mutating_test(
                "test_a_mutates_the_marker", mutation
            ),
            "integration/test_b_skips.py": _skipping_test(
                "test_b_skips", UNMET_PRECONDITION_REASON
            ),
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests", marker=marker)

    if expect_fired:
        _assert_fired(
            run,
            "test_b_skips.py::test_b_skips",
            "nothing here to discriminate on",
        )
    else:
        _assert_silent(
            run,
            "a test that set the gate's marker mid-session changed what "
            "the session was held to. `tasks.md` 2.2: the marker is read "
            "once, where the tier set is decided -- one session is judged "
            "by one rule.",
        )
