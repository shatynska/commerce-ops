"""How the integration tier decides where its database is.

`tests/integration/conftest.py` owns that decision for the whole tier,
replacing twelve copies of it. No delta scenario covers it — the change's
spec delta is about the CI gate — so it is covered here instead, in the
tier that needs no database, because the resolver is pure logic over a
filesystem and an environment.

`verify-the-integration-tier`, task 3.4.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_CONFTEST = Path(__file__).resolve().parents[1] / "integration" / "conftest.py"


def _resolver(root: Path) -> ModuleType:
    """The integration conftest, loaded with its repository root pointed
    at `root` so the env-file rungs read a temporary directory.

    Loaded by path rather than imported: `tests/integration/` carries no
    `__init__.py`, so it is not an importable package and a plain import
    would depend on `sys.path` insertion order.
    """
    spec = importlib.util.spec_from_file_location("_tier_conftest", _CONFTEST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_tier_conftest"] = module
    spec.loader.exec_module(module)
    module._REPO_ROOT = root  # type: ignore[attr-defined]
    return module


def _write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body)


# ---------------------------------------------------------------------------
# The rungs, and their order
# ---------------------------------------------------------------------------


def test_the_environment_variable_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit instruction outranks every file."""
    module = _resolver(tmp_path)
    _write(tmp_path, ".env.test", "DATABASE_URL=postgresql://u:p@h/from-env-test\n")
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/from-env\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/from-the-variable")

    url, source = module._resolve()

    assert url.endswith("/from-the-variable")
    assert "environment variable" in source


def test_env_test_outranks_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The isolated test database is preferred over the working one."""
    module = _resolver(tmp_path)
    _write(tmp_path, ".env.test", "DATABASE_URL=postgresql://u:p@h/isolated\n")
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url, source = module._resolve()

    assert url.endswith("/isolated")
    assert source == ".env.test"


def test_env_is_the_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The rung that makes the tier run without anyone doing anything."""
    module = _resolver(tmp_path)
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url, source = module._resolve()

    assert url.endswith("/working")
    assert source == ".env"


def test_nothing_configured_resolves_to_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert _resolver(tmp_path)._resolve() is None


# ---------------------------------------------------------------------------
# Empty is absent, everywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line", ["DATABASE_URL=\n", 'DATABASE_URL=""\n', "DATABASE_URL=''\n"]
)
def test_an_empty_value_in_a_file_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    """`database.py` treats empty as unset; so does every helper this
    replaced, so a file that names the key without a value must not
    shadow the rung below it."""
    module = _resolver(tmp_path)
    _write(tmp_path, ".env.test", line)
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url, source = module._resolve()

    assert url.endswith("/working")
    assert source == ".env"


def test_an_empty_environment_variable_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _resolver(tmp_path)
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.setenv("DATABASE_URL", "")

    url, _ = module._resolve()

    assert url.endswith("/working")


# ---------------------------------------------------------------------------
# Parse forms the reader honours, and the one key it reads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("DATABASE_URL=postgresql://u:p@h/plain\n", "/plain"),
        ('DATABASE_URL="postgresql://u:p@h/double"\n', "/double"),
        ("DATABASE_URL='postgresql://u:p@h/single'\n", "/single"),
        ("export DATABASE_URL=postgresql://u:p@h/exported\n", "/exported"),
        ("  DATABASE_URL=postgresql://u:p@h/indented\n", "/indented"),
        ("DATABASE_URL=postgresql://u:p@h/commented # trailing\n", "/commented"),
    ],
)
def test_the_parse_forms_the_reader_honours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str, expected: str
) -> None:
    module = _resolver(tmp_path)
    _write(tmp_path, ".env", line)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url, _ = module._resolve()

    assert url.endswith(expected)


def test_no_other_key_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite is hermetic with respect to credentials, and stays so:
    the reader takes one key and leaves the rest of the file alone."""
    module = _resolver(tmp_path)
    _write(
        tmp_path,
        ".env",
        "OPENAI_API_KEY=sk-not-read\n"
        "OMNI_AGENT_SLACK_BOT_TOKEN=xoxb-not-read\n"
        "DATABASE_URL=postgresql://u:p@h/working\n"
        "CLICKUP_API_TOKEN=pk-not-read\n",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url, _ = module._resolve()

    assert url.endswith("/working")
    for key in ("OPENAI_API_KEY", "OMNI_AGENT_SLACK_BOT_TOKEN", "CLICKUP_API_TOKEN"):
        assert key not in module.os.environ or "not-read" not in module.os.environ[key]


def test_a_file_without_the_key_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _resolver(tmp_path)
    _write(tmp_path, ".env.test", "OPENAI_API_KEY=sk-only\n")
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert module._resolve()[1] == ".env"


# ---------------------------------------------------------------------------
# What the reader reports, and what it must not
# ---------------------------------------------------------------------------


def test_the_report_names_the_rung_and_hides_the_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _resolver(tmp_path)
    _write(
        tmp_path,
        ".env.test",
        "DATABASE_URL=postgresql+asyncpg://ops:hunter2@localhost:5432/isolated\n",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)

    header = module.pytest_report_header()

    assert ".env.test" in header
    assert "hunter2" not in header, "the report leaked the password"
    # The username is kept deliberately: it tells two databases apart.
    assert "ops" in header
    assert "localhost:5432/isolated" in header


def test_the_report_says_so_when_nothing_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state a reader most needs explained, and the one in which a
    test that needs a database and did not request the gate hard-errors
    from the application's own reader."""
    module = _resolver(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    header = module.pytest_report_header()

    assert "no database configured" in header
    assert "skip" in header
    assert "docker compose up -d postgres" in header


# ---------------------------------------------------------------------------
# What an unresolved URL means, in both directions
# ---------------------------------------------------------------------------


def _gate(module: ModuleType) -> Any:
    """The gating fixture's own function, called directly."""
    return module.database_url.__wrapped__()


def test_without_the_flag_an_absent_database_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _resolver(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv(module.REQUIRE_DATABASE, raising=False)

    # pytest's outcome exceptions derive from BaseException, not
    # Exception, so a bare `raises(Exception)` would let them escape and
    # skip this test instead of observing the skip.
    with pytest.raises(BaseException) as raised:
        _gate(module)

    assert raised.typename == "Skipped"


def test_with_the_flag_an_absent_database_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where the tier is required, a gate may not report success for
    work it never exercised."""
    module = _resolver(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(module.REQUIRE_DATABASE, "1")

    with pytest.raises(BaseException) as raised:
        _gate(module)

    assert raised.typename == "Failed"
    assert module.REQUIRE_DATABASE in str(raised.value)


def test_the_flag_changes_nothing_when_a_database_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _resolver(tmp_path)
    _write(tmp_path, ".env", "DATABASE_URL=postgresql://u:p@h/working\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(module.REQUIRE_DATABASE, "1")

    assert _gate(module).endswith("/working")
