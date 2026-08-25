"""How the integration tier reaches its database — the one place that
decides it.

Twelve files used to carry the same `_database_url()` helper, each
skipping when `DATABASE_URL` was unset. The rule lived in twelve copies
and was owned by none, and it produced a false green: `pre-push` runs
this tier, set no variable, and reported `3 passed, 64 skipped` as a
pass. See `openspec/changes/verify-the-integration-tier/`.

Two fixtures, because there are two jobs and one test must not be gated:

- `_publish_database_url` (autouse) puts a resolved URL into the process
  environment. Four files drive the real application, whose session
  provider reads `os.environ["DATABASE_URL"]` directly rather than
  taking it from a fixture, so without this the file rungs below would
  make them fail instead of run.
- `database_url` gates. Requesting it is how a test says it needs a
  configured database — so `test_scheduled_runs_freshness_unreachable.py`,
  which supplies its own unreachable address and documents that it never
  skips, requests neither and is untouched.

Reporting goes through `pytest_report_header`, not `print`: a session
fixture's stdout is captured and surfaces only beside a failing test,
which is exactly the wrong place on the run that matters most — a bare
machine, where everything skips and nothing fails.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

import pytest

#: Set by CI. Where it is set, no database is a failure rather than a
#: skip, so a validation job cannot report success for a tier it never
#: ran. Deliberately not set by the `pre-push` hook — see the change's
#: `design.md`, "A required-tier flag turns a skip into a failure — in
#: CI only".
REQUIRE_DATABASE: Final = "COMMERCE_OPS_REQUIRE_DATABASE"

_KEY: Final = "DATABASE_URL"
_REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: Searched in order. An explicit environment variable wins; `.env.test`
#: is a standing choice to keep the tier out of the database the
#: developer works in; `.env` is what every working machine already has.
_ENV_FILES: Final = (".env.test", ".env")

_START_HINT: Final = (
    "Start it with `docker compose up -d postgres` and apply "
    "`alembic upgrade head` (schema and seed) before running this tier."
)


def _from_env_file(path: Path) -> str | None:
    """The `DATABASE_URL` line of an env file, and nothing else.

    Only this key is read. The same files carry the OpenAI key, both
    Slack tokens and the ClickUp token, and the suite is hermetic with
    respect to credentials — every test that needs one sets its own. A
    whole-file load would let a test that forgot to set one inherit an
    ambient value and pass, which is the same defect this module exists
    to remove, one layer down.
    """
    if not path.is_file():
        return None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        if not separator or name.strip() != _KEY:
            continue
        value = value.strip()
        if value[:1] in {"'", '"'} and value[-1:] == value[:1] and len(value) > 1:
            return value[1:-1] or None
        # An unquoted value ends at an inline comment; a quoted one does
        # not, which is why this runs only on the unquoted branch.
        return value.split(" #")[0].strip() or None
    return None


def _resolve() -> tuple[str, str] | None:
    """`(url, where it came from)`, or `None` when nothing is configured.

    Empty is absent throughout, matching `database.py`'s own reading and
    all twelve helpers this replaces.
    """
    from_environment = os.environ.get(_KEY)
    if from_environment:
        return from_environment, f"the {_KEY} environment variable"
    for name in _ENV_FILES:
        found = _from_env_file(_REPO_ROOT / name)
        if found:
            return found, name
    return None


def _redacted(url: str) -> str:
    """The URL with its password removed. Everything else is kept — the
    username included, since it tells two databases apart and the point
    of a stated rule is that nothing is left to decide at the keyboard."""
    scheme, separator, rest = url.partition("://")
    if not separator or "@" not in rest:
        return url
    credentials, _, location = rest.rpartition("@")
    user, has_password, _ = credentials.partition(":")
    if not has_password:
        return url
    return f"{scheme}://{user}:***@{location}"


def pytest_report_header() -> str:
    """Printed above the run, uncaptured and unconditionally.

    Both states are reported. The resolved one names the rung, so a
    stale `.env.test` pointing at a reachable but unmigrated database is
    diagnosable — the case with no connection error to hang a diagnosis
    on. The unresolved one says the tier will skip, because that is
    where a test needing a database that did not request `database_url`
    hard-errors from the application's own reader, and nothing else
    would explain it.
    """
    resolved = _resolve()
    if resolved is None:
        return (
            f"integration tier: no database configured — no {_KEY}, "
            f"no {' or '.join(_ENV_FILES)}. Tests needing one will skip. "
            f"{_START_HINT}"
        )
    url, source = resolved
    return f"integration tier: database from {source} — {_redacted(url)}"


@pytest.fixture(scope="session", autouse=True)
def _publish_database_url() -> object:
    """Publish a resolved URL into the environment for the whole session.

    Session-scoped `MonkeyPatch` rather than a bare assignment, so it
    unwinds afterwards and a per-test `setenv` still overrides it —
    which `test_scheduled_runs_freshness_unreachable.py` relies on.

    Publishes nothing when nothing resolves, and never raises: gating is
    the other fixture's job, and this one runs for every test including
    the ones that must not be gated.
    """
    patch = pytest.MonkeyPatch()
    resolved = _resolve()
    if resolved is not None:
        patch.setenv(_KEY, resolved[0])
    yield patch
    patch.undo()


@pytest.fixture(scope="session")
def database_url() -> str:
    """The tier's database, for a test that needs one configured.

    Requesting this fixture is how a test opts into being gated. Where
    nothing resolves it skips — or fails, if `COMMERCE_OPS_REQUIRE_DATABASE`
    says the tier is required here, so that a gate cannot report success
    for work it never exercised.
    """
    resolved = _resolve()
    if resolved is not None:
        return resolved[0]
    unconfigured = (
        f"No database is configured for the integration tier: {_KEY} is "
        f"unset (or empty) and neither {' nor '.join(_ENV_FILES)} carries "
        f"it. {_START_HINT}"
    )
    if os.environ.get(REQUIRE_DATABASE):
        pytest.fail(
            f"{unconfigured} {REQUIRE_DATABASE} is set, so this "
            "tier is required here and may not be skipped."
        )
    pytest.skip(unconfigured)
