"""Text-level guards over the `Dockerfile`'s `HEALTHCHECK` timing.

Derived from the delta spec of the OpenSpec change
`let-the-start-chain-finish`:

- `specs/deploy-pipeline/spec.md`, ADDED "The Container's Health Probe
  Allows Its Start Chain to Finish"

## What these tests are, and what they are not

**These are text-level guards over a file. They establish only that the
declared numbers are present in the `Dockerfile` -- nothing more.** A
container that actually survives a slow start chain, is actually reported
healthy once the server answers, actually fails the deploy when a step of
the chain dies, or is actually granted the window again after a restart,
is behaviour none of them observes, and none of them can: **no pytest
tier in this repository has a built Docker image.** The unit and agents
tiers run at commit time with no Docker at all; the integration tier runs
at `pre-push` against Postgres, and design.md -- "Guard the value with a
text-level test, and say what it does not prove" records why building an
image inside it was rejected.

**What makes the requirement's scenarios true is Docker's own health
monitor and the deploy itself** (`docker compose pull && up -d --wait`
on the host), plus the start-to-healthy figure the deploy reports on
every run, which tasks.md 4.4 reads after the merge. Not this module.

So each assertion below reads as "the number someone decided on is still
in the file", which is worth having as a regression guard -- a future
edit cannot quietly buy start-up tolerance out of the steady-state
liveness signal without turning one of these red -- and is worth nothing
as proof of the requirement. Read it that way. See `test-manifest.md` at
the change root for the full scenario-by-scenario accounting, including
the four scenarios no test here covers and why.

## Level

Reading the `Dockerfile` as text is the smallest unit that can observe
"the declared start period is at least 60 seconds" and "the declared
interval and retry count are still 10s and 3". Everything larger --
building the image, starting a container, timing a probe -- is where the
behaviour lives, and is out of reach here.

`tests/unit/test_dockerfile_runtime_sync.py` is this module's precedent:
same way of locating the repository root, same `_instructions` handling
of comments and backslash continuations, same explicitness about what a
text-level guard does not establish. Those helpers are duplicated rather
than imported, which is the convention those two neighbouring modules
already follow between themselves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# The Go duration units Docker accepts in a `HEALTHCHECK` flag. Spelled
# out so that `1m` and `60s` are read as the same window: the delta
# states the floor in seconds, not as a literal string to match.
_DURATION_UNITS = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}

_DURATION_TERM = re.compile(r"(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|ms|s|m|h)")

# The floor the delta's Sizing paragraph states, and the two steady-state
# values its Scope paragraph fixes.
_MINIMUM_START_PERIOD_SECONDS = 60.0
_REQUIRED_INTERVAL_SECONDS = 10.0
_REQUIRED_RETRIES = 3


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _instructions(text: str) -> list[tuple[str, str]]:
    """The `Dockerfile`'s instructions as `(KEYWORD, argument)` pairs.

    Comment lines are dropped and backslash continuations are joined, so
    an instruction split across lines -- which `HEALTHCHECK` is today --
    is one entry rather than two fragments.
    """
    statements: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        buffer += stripped
        statements.append(buffer)
        buffer = ""
    if buffer:
        statements.append(buffer)

    parsed: list[tuple[str, str]] = []
    for statement in statements:
        keyword, _, argument = statement.partition(" ")
        parsed.append((keyword.upper(), argument.strip()))
    return parsed


def _healthcheck_options(argument: str) -> dict[str, str]:
    """The `--flag=value` options one `HEALTHCHECK` declares.

    Only the tokens before the probe command are read, so a flag-looking
    fragment inside the command itself cannot be mistaken for a probe
    option. Dockerfile instruction flags are `--name=value`; a bare
    `--name` is recorded with an empty value rather than dropped, so a
    malformed flag surfaces as a failed assertion instead of as a
    missing key.
    """
    options: dict[str, str] = {}
    for token in argument.split():
        if not token.startswith("--"):
            break
        name, _, value = token[2:].partition("=")
        options[name.lower()] = value
    return options


def _duration_seconds(text: str) -> float | None:
    """A Go duration string in seconds, or `None` if it is not one.

    `None` rather than an exception so a caller can fail with the raw
    text in the message: an unparseable duration is a defect in this
    test's reading of the file, and it should say so rather than looking
    like a violated requirement.
    """
    remainder = text.strip()
    if not remainder:
        return None
    sign = 1.0
    if remainder[0] in "+-":
        sign = -1.0 if remainder[0] == "-" else 1.0
        remainder = remainder[1:]
    if remainder == "0":
        return 0.0

    total = 0.0
    position = 0
    for match in _DURATION_TERM.finditer(remainder):
        if match.start() != position:
            return None
        total += float(match.group(1)) * _DURATION_UNITS[match.group(2)]
        position = match.end()
    if position == 0 or position != len(remainder):
        return None
    return sign * total


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return (_repository_root() / "Dockerfile").read_text(encoding="utf-8")


@pytest.fixture()
def health_probe_options(dockerfile_text: str) -> dict[str, str]:
    """The options of the `HEALTHCHECK` the built image would actually use.

    DERIVED, from Docker's documented semantics rather than from any
    scenario: where an image declares more than one `HEALTHCHECK`, the
    last one wins. Taking the last is therefore what "the image's health
    probe is inspected" means when there are several; today there is one,
    and the two readings coincide.
    """
    healthchecks = [
        argument
        for keyword, argument in _instructions(dockerfile_text)
        if keyword == "HEALTHCHECK"
    ]
    assert healthchecks, (
        "the Dockerfile declares no HEALTHCHECK at all, so there is no "
        "start-up grace window and no steady-state liveness signal; "
        "`docker compose up -d --wait` blocks the deploy on `app` being "
        "healthy, and these tests would otherwise pass vacuously by the "
        "probe having been deleted"
    )

    effective = healthchecks[-1]
    assert effective.strip().upper() != "NONE", (
        "the image's HEALTHCHECK is disabled (`HEALTHCHECK NONE`), which "
        "satisfies no part of this requirement: a disabled probe never "
        "reports the container unhealthy, so the deploy stops failing on a "
        "genuinely broken container as well as on a slow-starting one"
    )
    return _healthcheck_options(effective)


# --------------------------------------------------------------------------
# deploy-pipeline: The Container's Health Probe Allows Its Start Chain to
# Finish
# --------------------------------------------------------------------------


def test_the_start_period_is_at_least_sixty_seconds(
    health_probe_options: dict[str, str],
) -> None:
    """Scenario: The declared window meets its floor.

    A TEXT-LEVEL GUARD. It establishes that a number at least this large
    is written in the `Dockerfile`. Whether a container with a chain
    slower than the probe's failure budget actually reaches healthy --
    the requirement's point -- is verified by the deploy, never here.

    SPECIFIED: "its start-up grace window SHALL be at least 60 seconds",
    and the Sizing paragraph's "SHALL NOT be less than 60 seconds".

    SPECIFIED, as the absent-flag case: a `HEALTHCHECK` with no
    `--start-period` declares a window of zero, which is below the floor.
    That is asserted as a violation of the requirement rather than as a
    broken test, because it is exactly the state the delta forbids.

    DERIVED: reading the value as a duration rather than matching the
    literal string `60s`. The delta states a floor in seconds, so `1m`
    and `90s` satisfy it as fully as `60s` does, and pinning one spelling
    would fail a harmless edit.

    Deliberately not asserted: that the value is exactly 60 seconds.
    Sizing makes 60s a floor, not a target -- the window is required to
    grow when the deploy's start-to-healthy figure rises (tasks.md 4.4),
    so a test demanding exactly 60 would fail the very edit the delta
    obliges.

    Deliberately not asserted: `--timeout`, `--start-interval`, and the
    probe command. The delta fixes none of them. design.md records
    leaving `--start-interval` unset as a decision about a Docker version
    floor this repository does not establish -- a test either way would
    assert a preference no scenario states.
    """
    declared = health_probe_options.get("start-period")
    assert declared is not None, (
        "the image's HEALTHCHECK declares no --start-period, so its "
        "start-up grace window is Docker's default of 0s: every failing "
        "probe counts from the first, and a container is reported "
        "unhealthy after 3 of them however far through the start chain it "
        f"is; flags declared: {sorted(health_probe_options)}"
    )

    seconds = _duration_seconds(declared)
    assert seconds is not None, (
        f"--start-period={declared!r} is not a duration this test can read, "
        "so it cannot say whether the window meets its floor; this is a "
        "defect in the test's parsing, not evidence about the requirement"
    )

    assert seconds >= _MINIMUM_START_PERIOD_SECONDS, (
        f"the image's start-up grace window is --start-period={declared} "
        f"({seconds:g}s), below the {_MINIMUM_START_PERIOD_SECONDS:g}s floor "
        "the spec states. The start chain deploy-pipeline mandates -- the "
        "configuration check, the migrations, both seeding steps and the "
        "handler-registration report -- runs inside this window, and a "
        "window too small for it reports a working deployment dead"
    )


def test_the_steady_state_liveness_signal_is_unchanged(
    health_probe_options: dict[str, str],
) -> None:
    """Scenario: Start-up tolerance is not taken from the steady-state signal.

    A TEXT-LEVEL GUARD, and a narrower one than it looks. It establishes
    that the two declared numbers are the ones the delta fixes. The
    scenario's second clause -- that the window "SHALL NOT have been
    obtained by widening either of them" -- is a statement about how the
    window came about, which no reading of the file's current text can
    observe. What this test can do, and does, is make the outcome that
    clause forbids impossible to reach quietly: a future edit buying
    start-up tolerance out of the interval or the retry count turns this
    red.

    SPECIFIED: "its interval SHALL be 10 seconds and its consecutive-
    failure count SHALL be 3", restated by the requirement's Scope
    paragraph as "those SHALL remain a 10-second interval and 3
    consecutive failures". Both are asserted as equalities, not as
    bounds, because the delta fixes them rather than bounding them --
    design.md's rejected `--retries=9` is the widening this forbids, and
    a narrowing (`--retries=1`) is equally a change to the steady-state
    signal that the delta does not authorise.

    SPECIFIED, as the absent-flag case: a `HEALTHCHECK` declaring neither
    flag inherits Docker's defaults, which happen to be 30s and 3. The
    interval default is not the required 10s, so an absent `--interval`
    is a violation; an absent `--retries` is asserted rather than
    accepted-by-default because the delta requires the count to be
    stated at this probe, not left to an engine default that a future
    Docker release could move.
    """
    declared_interval = health_probe_options.get("interval")
    assert declared_interval is not None, (
        "the image's HEALTHCHECK declares no --interval, so it falls back "
        "to Docker's 30s default rather than the 10 seconds the spec fixes; "
        f"flags declared: {sorted(health_probe_options)}"
    )

    interval_seconds = _duration_seconds(declared_interval)
    assert interval_seconds is not None, (
        f"--interval={declared_interval!r} is not a duration this test can "
        "read, so it cannot say whether the steady-state signal is intact; "
        "this is a defect in the test's parsing, not evidence about the "
        "requirement"
    )

    assert interval_seconds == _REQUIRED_INTERVAL_SECONDS, (
        f"the probe's interval is --interval={declared_interval} "
        f"({interval_seconds:g}s), not the "
        f"{_REQUIRED_INTERVAL_SECONDS:g}s the spec fixes. The interval "
        "governs how quickly a container that has stopped answering without "
        "exiting is reported unhealthy; start-up tolerance belongs in "
        "--start-period, which expires, not here, which never does"
    )

    declared_retries = health_probe_options.get("retries")
    assert declared_retries is not None, (
        "the image's HEALTHCHECK declares no --retries, so its consecutive-"
        "failure count is left to Docker's default instead of being stated "
        "at the probe as the spec requires; flags declared: "
        f"{sorted(health_probe_options)}"
    )

    assert declared_retries.isdigit(), (
        f"--retries={declared_retries!r} is not a whole number, so this test "
        "cannot read the consecutive-failure count; this is a defect in the "
        "test's parsing, not evidence about the requirement"
    )

    assert int(declared_retries) == _REQUIRED_RETRIES, (
        f"the probe's consecutive-failure count is --retries="
        f"{declared_retries}, not the {_REQUIRED_RETRIES} the spec fixes. "
        "Raising it would buy start-up tolerance out of the steady-state "
        "liveness signal -- the trade design.md rejects, because it "
        "proportionally lengthens how long a container that dies in "
        "production keeps receiving traffic, permanently and in every state"
    )
