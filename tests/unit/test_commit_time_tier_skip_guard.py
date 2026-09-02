"""The commit-time tier tolerates no skipped test.

Covers the guard that `restore-the-skipped-unit-tests` adds in a new
`tests/conftest.py` — a `pytest_sessionfinish` hook that fails the session
when any test under `tests/unit` or `tests/agents` was skipped, naming each
one and its reason.

## Why this file exists when the change has no delta specs

`restore-the-skipped-unit-tests` sets `skip_specs: true`: it edits `tests/`
only and changes no capability, so there are no delta scenarios to derive
from, and the forty-four restored tests are already-existing tests that
this pass neither writes nor touches. `design.md`'s Risks section records
one qualification to that — section 4's guard *is* new behaviour — and
`tasks.md` 4.5/4.6/4.7 verify it only by a manual procedure: temporarily
add a skip, observe, revert. A manual procedure is not run again by
anybody. This file is the automated form of 4.5 and 4.7.

Every assertion below therefore traces to `tasks.md` section 4 and
`design.md` Decision 3 rather than to a delta scenario. See
`test-manifest.md` at the change root for the full accounting.

## Expected to fail on the unmodified tree

`tests/conftest.py` does not exist yet — section 4 is unimplemented. Every
test here fails on its absence, with the message `_guard_source` raises.
That is the weakest of the four failure states the `testing` standard
names: it establishes that the target is absent and nothing about whether
these assertions discriminate. They become readable only once the guard
exists. Do not create `tests/conftest.py` to make this file execute; that
is the change's own task 4.1.

Measured on the tree as this pass found it (`uv run pytest tests/unit
tests/agents`): **1979 passed, 44 skipped**, matching `design.md`'s
baseline exactly.

That these assertions *do* discriminate was established separately, by
running this file against seven reference guards outside the repository —
one correct, six deliberately broken. The correct one passes all ten
cases; a collection-based guard is caught by seven, a guard that fails
unconditionally by all ten, an `xfail`-blind one by exactly the `xfail`
case, an unfiltered one by exactly the integration case, and one that
reports without naming by seven. Those reference guards are not part of
this repository and no part of this file depends on how any of them was
written.

## Why a subprocess and a synthetic tree, and not `pytester`

The guard's whole subject is what a *pytest session* does, so it can only
be observed by running one. Three mechanisms were considered.

`pytester` is the obvious candidate and is rejected on availability, not
on taste. Its fixture is not registered by default — measured here, `uv run
pytest --fixtures` lists no `pytester` — so using it means declaring
`pytest_plugins = "pytester"` in a conftest. The only conftest that could
carry it for this file is `tests/conftest.py` itself, which is the very
file under test and which a test-writing pass may not author. It would
also register the plugin for the entire suite, which is a repository-wide
configuration decision belonging to its own change rather than a side
effect of one test file. `runpytest_inprocess` carries a second problem:
it runs the guard's hooks inside the *outer* session's plugin manager,
where the guard under test could observe the outer session's reports.

Running the real `tests/` tree is rejected as well: it costs the whole
tier per invocation and could not exhibit a skip without adding one.

So each case below builds a synthetic three-tier tree in `tmp_path`,
copies the real `tests/conftest.py` into it verbatim, and runs a fresh
`pytest` against it — the subprocess pattern
`tests/unit/test_handler_registration_is_cheap.py` and
`tests/unit/test_registrations_across_processes.py` already establish for
process-global effects, and the by-path loading of a conftest that
`tests/unit/test_integration_tier_database_resolution.py` establishes for
test infrastructure. Measured at roughly 0.4s per invocation, eleven
invocations, against a tier the change already accepts growing by 13s.

The copy is verbatim and the synthetic tree reproduces the real
`tests/unit`, `tests/agents`, `tests/integration` layout under a rootdir
fixed by a `pyproject.toml`, so a guard that resolves its tiers relative
to its own location, or from a nodeid, or against the rootdir, all behave
identically. Only a guard hard-coding an absolute path to this checkout
would differ — and that guard would be broken in every other checkout too.

## The synthetic tree deliberately omits `addopts = "-rs"`

The real `pyproject.toml` carries `-rs`, which prints every skip and its
reason in the terminal summary. Inheriting it here would make the "names
each one and its reason" assertions pass vacuously — pytest itself would
have printed what the guard is supposed to print. The synthetic tree runs
under pytest's default reporting, where a skipped test contributes only an
`s` and no name, so a nodeid or a reason appearing in the output can only
have come from the guard.

## This file must never skip

It lives under `tests/unit`, so a `pytest.skip` here would trip the guard
it is testing. An absent target is asserted, never skipped.

## Specified, derived, deliberately untested

SPECIFIED by `tasks.md` section 4 and `design.md` Decision 3:

- that a skipped test under `tests/unit` or `tests/agents` fails the
  session (4.1), including one skipped by an autouse fixture during setup
  rather than at collection (4.2);
- that each skipped test and its reason is named (4.1);
- that the guard fails the session cleanly rather than letting an
  exception escape the hook (4.2a — see the correction below);
- that `tests/integration` may still skip **where the run does not declare
  the tier required** (4.3, 4.7). That clause was unqualified until
  `restore-the-skipped-integration-tests` armed the guard over that tier
  under `COMMERCE_OPS_REQUIRE_DATABASE`; the armed half is covered by
  `tests/unit/test_integration_tier_skip_guard.py`, a sibling of this file
  rather than an addition to it, because the tests for it were derived
  before this file could be edited;
- that an `xfail` is not treated as a skip (4.4);
- that `uv run pytest tests/agents` on its own is guarded, which is the
  single property the `tests/conftest.py` placement exists to buy over
  `tests/unit/conftest.py` (4.1, Decision 3);
- that a hand-run of one file, one nodeid, or `.` from inside a tier
  directory is guarded (Decision 3, "it reaches the single-file hand-run
  too").

A CORRECTION to 4.2a, measured rather than assumed. That task says an
exception raised inside `pytest_sessionfinish` "surfaces as
`INTERNALERROR`". Against pytest 9.1.1 it does not: it produces a raw
`Traceback` on stderr through `pluggy`, with no `INTERNALERROR` banner
anywhere, and exit code 1. An assertion keyed on the literal string would
therefore have passed against exactly the mistake 4.2a warns about — it
did, before this was checked. `_assert_failed_cleanly` looks for either
shape. The task's *advice* is unaffected and correct; only its stated
symptom is wrong, and it is raised as a finding against the artifacts.

DERIVED: that a run containing no skip at all still exits zero
(`test_a_run_with_no_skips_leaves_the_session_alone`). No task states it,
because it reads as too obvious to state — but without it every other
assertion here is satisfied by a guard that fails every session
unconditionally, so it is the control the rest depend on.

Also DERIVED: that a `skipif` marker counts as a skip. `tasks.md` names
`pytest.skip` and an autouse fixture; `skipif` is a third spelling that
produces the same setup-time skipped report (measured), and the two
conditional skips `tasks.md` 4.6 inventories are of that kind.

DELIBERATELY UNTESTED — `pytest.skip(..., allow_module_level=True)`. This
skips a whole file at import, which is exactly the outcome `design.md`
states the guard exists to prevent ("A blanket skip cannot silently take a
file out of the commit-time tier again"). Measured against pytest 9.1.1,
it produces **no `TestReport` at all** — only a `CollectReport` — so a
guard built as `tasks.md` 4.2 instructs, reading `TestReport`s, cannot see
it. Asserting that the guard catches it would contradict a stated task and
impose a requirement nobody agreed to; asserting that it does not would
freeze the gap into the suite. It is neither, and is raised as a finding
against the change's artifacts instead. See `test-manifest.md`.

DELIBERATELY UNTESTED — `tasks.md` 4.6's `git`-absent case. It asks what
two *real, existing* tests do when `git` leaves `PATH`, which is a question
about those tests and the machine, not about the guard's logic; the
guard's half of it — a skip under `tests/unit` failing the session — is
`test_a_skip_in_the_unit_tier_fails_the_session` below. Left to 4.6's
procedure.

DELIBERATELY UNTESTED — `tasks.md` 4.2a's "no work at import time". It is
a property of how the guard is written rather than of what a session does,
so no black-box run can observe it.

Not asserted anywhere: the guard's exact wording, its exit code beyond
being non-zero, or where it writes. A guard is free to phrase its report
however it likes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# `tests/conftest.py` -- this file is `tests/unit/test_....py`.
GUARD_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"

# The two tiers the guard covers, and the one it must leave alone.
GUARDED_TIERS = ("unit", "agents")
UNGUARDED_TIER = "integration"

# Deliberately without `-rs`; see the module docstring.
SYNTHETIC_PYPROJECT = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
"""

A_PASSING_TEST = """\
def test_that_passes() -> None:
    assert True
"""


def _skipping_test(function: str, reason: str) -> str:
    return f'''\
import pytest


def {function}() -> None:
    pytest.skip("{reason}")
'''


def _fixture_skipping_conftest(reason: str) -> str:
    """The defect this change repairs, in miniature: an autouse fixture
    skipping by filename, during setup rather than at collection."""
    return f'''\
import pytest


@pytest.fixture(autouse=True)
def skip_by_filename(request: pytest.FixtureRequest) -> None:
    if "matched" in request.node.fspath.strpath:
        pytest.skip("{reason}")
'''


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
    session that is running this file.
    """
    assert GUARD_CONFTEST.is_file(), (
        f"{GUARD_CONFTEST} does not exist, so there is no guard to exercise "
        "and every test in this file is failing on an absent target rather "
        "than on anything it asserts. That is the expected state until "
        "`restore-the-skipped-unit-tests` task 4.1 adds the file. Do not "
        "create it to make this file execute -- writing it is that task's "
        "job, not this one's."
    )
    return GUARD_CONFTEST.read_text(encoding="utf-8")


def _tree(root: Path, files: dict[str, str]) -> Path:
    """A synthetic three-tier `tests/` tree with the real guard installed.

    All three tier directories are created whether or not `files` puts
    anything in them, so the guard's path filter always has the same shape
    to resolve against.
    """
    (root / "pyproject.toml").write_text(SYNTHETIC_PYPROJECT, encoding="utf-8")
    tests = root / "tests"
    for tier in (*GUARDED_TIERS, UNGUARDED_TIER):
        (tests / tier).mkdir(parents=True, exist_ok=True)
    (tests / "conftest.py").write_text(_guard_source(), encoding="utf-8")
    for relative, body in files.items():
        path = tests / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _run(root: Path, *targets: str, cwd: Path | None = None) -> GuardRun:
    """Run a fresh pytest over the synthetic tree.

    The environment is built from scratch rather than inherited so that a
    `PYTEST_ADDOPTS` in the outer shell cannot reach the child and change
    what it reports -- the same reasoning
    `test_handler_registration_is_cheap.py` gives for its own probes.
    """
    working = cwd if cwd is not None else root
    command = [sys.executable, "-m", "pytest", *targets, "-p", "no:cacheprovider"]
    result = subprocess.run(
        command,
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(working),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return GuardRun(
        exit_code=result.returncode,
        output=result.stdout + result.stderr,
        invocation=f"{' '.join(['pytest', *targets])} (cwd={working})",
    )


def _assert_failed_cleanly(run: GuardRun) -> None:
    """tasks.md 4.2a: fail by setting `session.exitstatus`, never by
    raising inside `pytest_sessionfinish`.

    Both shapes an escaping exception can take are checked. 4.2a predicts
    `INTERNALERROR`; against pytest 9.1.1 the observed shape is instead a
    raw `pluggy` traceback naming the hook, with no banner. Checking only
    the predicted string would let the very mistake the task warns about
    through -- measured, not supposed.
    """
    escaped = "Traceback (most recent call last)" in run.output and (
        "pytest_sessionfinish" in run.output or "pytest_runtest_logreport" in run.output
    )
    assert "INTERNALERROR" not in run.output and not escaped, (
        "an exception escaped the guard's hook instead of it failing the "
        "session cleanly. tasks.md 4.2a: fail by setting "
        "`session.exitstatus`, never by raising inside "
        "`pytest_sessionfinish` -- a session that dies in the hook reports "
        "neither which test skipped nor why, which is the whole point of "
        f"the guard.\n{run.context()}"
    )


def _assert_fired(run: GuardRun, *expected: str) -> None:
    """The guard failed the session and named what it objected to."""
    _assert_failed_cleanly(run)
    assert run.fired, (
        "the session exited zero despite a skipped test in a tier that "
        "tolerates none. A skip in `tests/unit` or `tests/agents` must fail "
        "the run: this is the mechanism that stops a whole file being taken "
        "out of the commit-time gate by name, which is how forty-four tests "
        "stopped running across five commits in one afternoon with the "
        f"suite reporting success throughout.\n{run.context()}"
    )
    for fragment in expected:
        assert fragment in run.output, (
            f"the guard failed the session but never named {fragment!r}. "
            "tasks.md 4.1 requires it to name each skipped test and its "
            "reason: a run that fails without saying which test skipped, or "
            "why, leaves the next reader to rediscover it -- and the false "
            "reason attached to the original forty-four is the reason this "
            "change exists. (The synthetic tree omits `-rs` deliberately, so "
            "nothing but the guard prints this.)"
            f"\n{run.context()}"
        )


def _assert_silent(run: GuardRun, why: str) -> None:
    """The guard left the session alone."""
    _assert_failed_cleanly(run)
    assert not run.fired, f"{why}\n{run.context()}"


# ---------------------------------------------------------------------------
# The guard fires where the tier tolerates no skip
# ---------------------------------------------------------------------------


def test_a_skip_in_the_unit_tier_fails_the_session(tmp_path: Path) -> None:
    """tasks.md 4.1 and 4.5, the `tests/unit` half.

    SPECIFIED. The plain case: a `pytest.skip` in a test body under
    `tests/unit`, which 4.5 verifies by hand and this verifies on every run.
    """
    reason = "a deliberately skipped unit test"
    root = _tree(
        tmp_path,
        {
            "unit/test_matched.py": _skipping_test("test_matched", reason),
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_fired(run, "test_matched.py::test_matched", reason)


def test_a_skip_raised_by_an_autouse_fixture_fails_the_session(
    tmp_path: Path,
) -> None:
    """tasks.md 4.2 — the guard must read reports, not collection.

    SPECIFIED, and the single most discriminating case in this file. The
    skip that took forty-four tests out of the tier was raised by an
    autouse fixture matching on filename, which happens during *setup*:
    `pytest_collection_modifyitems` never sees it. A guard written there
    passes vacuously — worse than no guard, because it reads as protection.
    Every other test here would be satisfied by that vacuous guard as long
    as it also fired on a body-level skip; this one would not.
    """
    reason = "Unit test requires database; should be integration tier"
    root = _tree(
        tmp_path,
        {
            "unit/conftest.py": _fixture_skipping_conftest(reason),
            "unit/test_matched.py": A_PASSING_TEST,
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_fired(run, "test_matched.py::test_that_passes", reason)


@pytest.mark.parametrize(
    ("target", "from_inside_the_tier"),
    [("tests/agents", False), (".", True)],
    ids=["pytest tests/agents", "cd tests/agents && pytest ."],
)
def test_a_skip_in_the_agents_tier_fails_when_that_tier_runs_alone(
    tmp_path: Path, target: str, from_inside_the_tier: bool
) -> None:
    """tasks.md 4.1 and 4.5, the `tests/agents` half — and the one property
    the guard's placement exists to buy.

    SPECIFIED. `design.md` Decision 3: a conftest is loaded only for the
    paths collected, so a hook in `tests/unit/conftest.py` is never
    registered by `uv run pytest tests/agents` and that tier runs unguarded
    and silently. Run as part of the pair, this case cannot show the
    difference — which is why 4.5 requires the agents tier be run on its own
    and why it is run on its own here.

    The second parametrisation is Decision 3's claim that `cd tests/agents
    && uv run pytest .` is covered too, since rootdir resolution does not
    depend on the working directory.
    """
    reason = "a deliberately skipped agent-graph test"
    root = _tree(
        tmp_path,
        {
            "agents/test_matched.py": _skipping_test("test_matched", reason),
            "agents/test_healthy.py": A_PASSING_TEST,
            # Present and clean, so nothing in the unit tier can account
            # for the failure this case expects.
            "unit/test_healthy_unit.py": A_PASSING_TEST,
        },
    )
    cwd = root / "tests" / "agents" if from_inside_the_tier else None

    run = _run(root, target, cwd=cwd)

    _assert_fired(run, "test_matched.py::test_matched", reason)


def test_every_skipped_test_is_named(tmp_path: Path) -> None:
    """tasks.md 4.1 — "naming each one and its reason", in the plural.

    SPECIFIED for `pytest.skip`; the `skipif` spelling is DERIVED (it
    produces the same setup-time skipped report, measured, and the two
    conditional skips 4.6 inventories are of that kind). Three skipped
    tests across both guarded tiers and two spellings: a guard that reports
    only the first, or only the tier it happened to see first, fails here
    and passes every case above.
    """
    body_reason = "skipped in the body"
    marker_reason = "skipped by a skipif marker"
    agents_reason = "skipped in the agents tier"
    marker_test = f'''\
import pytest


@pytest.mark.skipif(True, reason="{marker_reason}")
def test_marker() -> None:
    assert True
'''
    root = _tree(
        tmp_path,
        {
            "unit/test_body.py": _skipping_test("test_body", body_reason),
            "unit/test_marker.py": marker_test,
            "agents/test_elsewhere.py": _skipping_test("test_elsewhere", agents_reason),
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_fired(
        run,
        "test_body.py::test_body",
        body_reason,
        "test_marker.py::test_marker",
        marker_reason,
        "test_elsewhere.py::test_elsewhere",
        agents_reason,
    )


@pytest.mark.parametrize(
    "target",
    ["tests/unit/test_matched.py", "tests/unit/test_matched.py::test_matched"],
    ids=["one file", "one nodeid"],
)
def test_the_guard_reaches_a_hand_run(tmp_path: Path, target: str) -> None:
    """`design.md` Decision 3 — "it reaches the single-file hand-run too,
    which is the case a developer meets first".

    SPECIFIED. `confcutdir` defaults to the rootdir, so pytest walks the
    ancestor chain down to each argument's directory and loads
    `tests/conftest.py` for a file path and a bare nodeid alike. The
    synthetic tree fixes its rootdir with a `pyproject.toml` exactly as the
    real one does, because that is the property this rests on.
    """
    reason = "a deliberately skipped unit test"
    root = _tree(
        tmp_path,
        {"unit/test_matched.py": _skipping_test("test_matched", reason)},
    )

    run = _run(root, target)

    _assert_fired(run, "test_matched.py::test_matched", reason)


# ---------------------------------------------------------------------------
# The guard stays silent everywhere else
# ---------------------------------------------------------------------------


def test_the_integration_tier_may_still_skip_without_the_marker(
    tmp_path: Path,
) -> None:
    """tasks.md 4.3 and 4.7 — the false positive must be absent.

    SPECIFIED. `tests/integration` skips legitimately when no database
    resolves, and failing those would break a tier this change does not
    touch. 4.7 notes that on a machine where a database *does* resolve the
    real check is vacuous and asks that the case be forced; the synthetic
    tree forces it — the skip is unconditional and always present.

    The guarded tiers hold passing tests here, so this establishes that the
    guard discriminates by path rather than that it never fires at all.

    **Renamed by `restore-the-skipped-integration-tests`, and the rename is
    the point.** This test used to be called
    `test_the_integration_tier_may_still_skip` and its docstring called that
    exclusion unconditional. It is not: the guard now covers
    `tests/integration` when `COMMERCE_OPS_REQUIRE_DATABASE` is set. What
    kept this test passing across that change was not the property it names
    but `_run`'s environment — built from scratch as `{"PATH": ...}`, so the
    marker never reaches the child whatever the outer shell holds. A test
    that keeps passing for a reason other than the one it states is worse
    than one that fails, which is why the name now carries the condition.
    The armed half is `tests/unit/test_integration_tier_skip_guard.py`.
    """
    root = _tree(
        tmp_path,
        {
            "integration/test_needs_a_database.py": _skipping_test(
                "test_needs_a_database", "no database configured"
            ),
            "unit/test_healthy.py": A_PASSING_TEST,
            "agents/test_healthy_too.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_silent(
        run,
        "the guard failed a session whose only skip was in "
        "`tests/integration`, where a skip is specified behaviour: "
        "`AGENTS.md` says tests needing a database skip and say why. The "
        "path filter, not the conftest's location, is what must exclude "
        "that tier (tasks.md 4.3).",
    )


def test_an_expected_failure_is_not_treated_as_a_skip(tmp_path: Path) -> None:
    """tasks.md 4.4 — `xfail` is not a skip for this purpose.

    SPECIFIED. `TestReport.skipped` is true for an `xfail`ed test as well as
    a skipped one — confirmed against pytest 9.1.1 — so a hook that does not
    distinguish them bans a marker nobody proposed banning. No `xfail`
    exists under `tests/` today, but three file docstrings record "2
    xfailed" from 2026-08-28, so it is a shape this repository has used.
    """
    expected_failure = """\
import pytest


@pytest.mark.xfail(reason="expected to fail")
def test_expected_failure() -> None:
    assert False
"""
    root = _tree(
        tmp_path,
        {
            "unit/test_expected_failure.py": expected_failure,
            "unit/test_healthy.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_silent(
        run,
        "the guard failed a session over an `xfail`ed test. `xfail` reports "
        "as skipped and is not a skip for this purpose (tasks.md 4.4): "
        "distinguish it, by `wasxfail` or equivalent, rather than banning a "
        "marker nobody proposed banning.",
    )


def test_a_run_with_no_skips_leaves_the_session_alone(tmp_path: Path) -> None:
    """DERIVED, and the control the whole file rests on.

    No task states it, because a guard that fails every session reads as
    absurd. But every firing case above is satisfied by exactly that guard,
    so without this one they establish nothing: they would all pass against
    a hook that set a non-zero exit status unconditionally.
    """
    root = _tree(
        tmp_path,
        {
            "unit/test_healthy.py": A_PASSING_TEST,
            "agents/test_healthy_too.py": A_PASSING_TEST,
            "integration/test_healthy_as_well.py": A_PASSING_TEST,
        },
    )

    run = _run(root, "tests")

    _assert_silent(
        run,
        "the guard failed a session in which nothing was skipped at all. "
        "Every firing case in this file would also pass against a guard "
        "that failed unconditionally, so this is what tells the two apart.",
    )
