"""Text-level guards over the `Dockerfile`'s runtime-sync properties.

Derived from the delta spec of the OpenSpec change
`start-containers-without-a-package-index`:

- `specs/deploy-pipeline/spec.md`, ADDED "A Container Starts From Its
  Image Alone"

## What these tests are, and what they are not

**These are text-level guards over a file. They establish only that the
text is present in the `Dockerfile` -- nothing more.** A container that
actually starts with no route to a package index is a behaviour none of
them observes, and none of them can: no pytest tier here has a built
Docker image.

**The behavioural check lives in the build job** of
`.github/workflows/deploy.yml` (tasks.md 3.1/3.3): it starts a container
from the freshly built image with `docker run --network none` and fails
the deploy if the application does not import. That check, not this
module, is what makes the requirement's scenarios true. design.md records
why the integration tier was rejected for it -- that tier's trigger is
`pre-push`, where no built image exists.

So each assertion below reads as "the line someone decided on is still in
the file", which is worth having as a regression guard and is worth
nothing as proof of the requirement. Read it that way. See
`test-manifest.md` at the change root for the full scenario-by-scenario
accounting, including the three scenarios no test here covers.

## Level

Reading the `Dockerfile` as text is the smallest unit that can observe
"the `Dockerfile` sets `UV_NO_SYNC`" and "the `HEALTHCHECK` does not go
through `uv run`". Everything larger -- building the image, starting a
container -- is where the behaviour lives, and is out of reach here.

The neighbouring `tests/unit/test_compose_worker_service.py` reads
`docker-compose.yml` from the repository root the same way; this module
follows it, including how it locates the root.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

# Values a shell-style boolean would read as "off". Setting `UV_NO_SYNC`
# to one of these declares the variable while leaving the runtime syncing,
# which is the fault the change exists to fix.
_FALSEY = frozenset({"", "0", "false", "no", "off"})

_UV_RUN = re.compile(r"\buv\s+run\b")
_UV_SYNC = re.compile(r"\buv\s+sync\b")


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


def _env_pairs(argument: str) -> dict[str, str]:
    """The variables one `ENV` instruction declares.

    Both spellings Docker accepts are handled: `ENV K=V [K=V ...]` and the
    legacy `ENV K V`. Neither is asserted on -- which one the
    implementation uses is not this test's business.
    """
    try:
        tokens = shlex.split(argument)
    except ValueError:
        tokens = argument.split()

    if tokens and not any("=" in token for token in tokens):
        return {tokens[0]: " ".join(tokens[1:])}

    pairs: dict[str, str] = {}
    for token in tokens:
        name, sep, value = token.partition("=")
        if sep:
            pairs[name] = value
    return pairs


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return (_repository_root() / "Dockerfile").read_text(encoding="utf-8")


@pytest.fixture()
def instructions(dockerfile_text: str) -> list[tuple[str, str]]:
    return _instructions(dockerfile_text)


@pytest.fixture()
def image_environment(instructions: list[tuple[str, str]]) -> dict[str, str]:
    environment: dict[str, str] = {}
    for keyword, argument in instructions:
        if keyword == "ENV":
            environment.update(_env_pairs(argument))
    return environment


# --------------------------------------------------------------------------
# deploy-pipeline: A Container Starts From Its Image Alone
# --------------------------------------------------------------------------


def test_the_image_sets_uv_no_sync(image_environment: dict[str, str]) -> None:
    """Scenario: A container starts with no route to a package index.

    A TEXT-LEVEL GUARD. It establishes that the `Dockerfile` declares this
    variable and nothing else: whether a container actually starts without
    reaching an index is verified by the build job's
    `docker run --network none` step (tasks.md 3.1), not here.

    SPECIFIED: that a container "SHALL NOT contact a package index,
    resolve dependencies, or install packages as part of starting", and
    that dev-group dependencies "SHALL NOT be installed into a container
    at any point". `UV_NO_SYNC` is the mechanism design.md chose for that
    -- one image-level variable rather than flags at each `uv run` call
    site, because the fourth call site is typed by an operator into
    `docker compose exec` and has no text in this repository to edit.

    DERIVED: excluding the falsey spellings. No scenario states a value;
    `UV_NO_SYNC=0` would satisfy "the variable is declared" while leaving
    the runtime syncing, which is the fault itself. The exact truthy
    spelling is deliberately not asserted -- `1` and `true` are equally
    fine, and pinning one would fail a harmless edit.

    Deliberately not asserted: the `ENV`'s position relative to
    `HEALTHCHECK`. Image environment is image configuration, so a
    healthcheck reads it whichever side it is declared on (design.md
    verified this against a probe image). A test asserting that order
    would fail on a harmless reorder and teach the next reader a false
    model -- tasks.md 5.1 names this exclusion explicitly.
    """
    assert "UV_NO_SYNC" in image_environment, (
        "the Dockerfile declares no UV_NO_SYNC, so every `uv run` in a "
        "container -- the CMD chain, the healthcheck, compose's worker "
        "command, and an operator's `docker compose exec ... uv run ...` "
        "-- re-syncs the environment at start and downloads the dev group "
        f"from PyPI; ENV declares: {sorted(image_environment)}"
    )

    value = image_environment["UV_NO_SYNC"]
    assert value.strip().lower() not in _FALSEY, (
        f"UV_NO_SYNC is declared as {value!r}, which turns the setting off; "
        "the runtime would still sync at every container start"
    )


def test_uv_no_sync_is_declared_after_the_build_time_sync(
    instructions: list[tuple[str, str]],
) -> None:
    """DERIVED (tasks.md 1.1; design.md, "Set `UV_NO_SYNC=1` in the image,
    not flags at each call site").

    A TEXT-LEVEL GUARD, like its neighbours: it establishes the order of
    two lines in a file, not any property of a running container.

    No `#### Scenario:` states this. What does state it is the recorded
    decision that a variable meant for the runtime must not be in scope
    while the image is being built -- and unlike the `ENV`/`HEALTHCHECK`
    ordering this module deliberately leaves alone, this one has real
    Docker semantics behind it: an `ENV` applies to every `RUN` beneath
    it, so declaring it above `RUN uv sync --frozen --no-dev` would put it
    in scope for the build step that produces the environment.

    Recorded as derived because it constrains where the implementation
    puts a line. If the placement is later reconsidered, this test is the
    thing to change -- deliberately, and with the reason -- not something
    to work around.
    """
    build_sync = [
        index
        for index, (keyword, argument) in enumerate(instructions)
        if keyword == "RUN" and _UV_SYNC.search(argument)
    ]
    assert build_sync, (
        "no `RUN uv sync ...` remains in the Dockerfile; tasks.md 1.2 keeps "
        "the build-time sync exactly as it is, so its absence is a bigger "
        "finding than this test's subject"
    )

    declares_no_sync = [
        index
        for index, (keyword, argument) in enumerate(instructions)
        if keyword == "ENV" and "UV_NO_SYNC" in _env_pairs(argument)
    ]
    assert declares_no_sync, (
        "no ENV instruction declares UV_NO_SYNC (see "
        "test_the_image_sets_uv_no_sync, which is the assertion that "
        "matters here)"
    )

    assert min(declares_no_sync) > max(build_sync), (
        "UV_NO_SYNC is declared before the build-time `uv sync`, so a "
        "variable meant for the runtime is in scope while the image is "
        f"being built; ENV at instruction {min(declares_no_sync)}, "
        f"`RUN uv sync` at {max(build_sync)}"
    )


def test_the_healthcheck_does_not_launch_through_uv_run(
    instructions: list[tuple[str, str]],
) -> None:
    """Scenario: A container starts with no route to a package index --
    the healthcheck's share of it.

    A TEXT-LEVEL GUARD. It establishes that the word `uv run` is absent
    from one instruction in a file. Whether the probe actually executes,
    and whether it reports unhealthy when the app is not serving, is
    verified against a running container by hand (tasks.md 4.5) and on the
    host after deploy (tasks.md 6.4) -- never here.

    DERIVED (tasks.md 2.2/5.2; design.md, "The healthcheck calls the
    interpreter directly"). No scenario requires this: `UV_NO_SYNC` alone
    satisfies the requirement, and design.md says so outright. The
    healthcheck rewrite is a cost-and-blast-radius decision -- the probe
    runs every 10 seconds for the life of every `app` container, and each
    layer between it and the HTTP request is another way for it to report
    the wrong thing. This test guards that specific regression, which the
    pipeline's behavioural check would not isolate: a container starting
    offline says nothing about which launcher its probe uses.

    Deliberately not asserted: that the command names
    `/app/.venv/bin/python`. That path is confirmed against the built
    image (tasks.md 2.1) because getting it wrong makes every `app`
    container permanently unhealthy -- a text test transcribing it would
    assert the guess rather than check it, and would contradict 2.1 if the
    real path differed.
    """
    healthchecks = [
        argument for keyword, argument in instructions if keyword == "HEALTHCHECK"
    ]

    assert healthchecks, (
        "the Dockerfile declares no HEALTHCHECK at all; `docker compose up "
        "-d --wait` blocks the deploy on `app` being healthy, and this test "
        "would otherwise pass by the probe having been deleted"
    )

    for argument in healthchecks:
        assert argument.strip().upper() != "NONE", (
            "the HEALTHCHECK is disabled in the image rather than rewritten"
        )
        assert not _UV_RUN.search(argument), (
            "the HEALTHCHECK still launches through `uv run`, so the probe "
            "starts uv every 10 seconds for the life of every app "
            f"container: {argument}"
        )
