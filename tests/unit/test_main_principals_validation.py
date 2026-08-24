"""The HTTP composition root validates the principals directory at startup.

Derived from `access-scope`'s requirement *A principals directory is loaded
from a repo-owned definition and validated*, specifically the clause its
sixth scenario states:

    WHEN the process starts against a malformed principals directory
    THEN startup fails with the load error naming the offending entry, and
    no scope resolution ever observes the malformed directory

The second clause is asserted structurally in
`tests/unit/access/application/test_resolve_scope.py` (a malformed file
hands back no directory to resolve against). This file covers the first --
that *startup* fails -- which the change's test-writing pass recorded as
deliberately untested because no artifact then fixed where the eager
validation is invoked.

## Where it is invoked, and why not `preflight.py`

`commerce_ops.main`, the process that will serve scope resolution once Omni
is rewired over the modules' public surfaces. Not `preflight.py`, though a
deploy-time check would otherwise belong there: `runtime-configuration`
requires the configuration check to "read only the process environment" with
its outcome depending "only on the declared variables' presence and
parseability", and a repo-owned file's faults failing that check would
contradict both. Loading the file at `main.py`'s composition root needs no
configuration, so `runtime-configuration`'s "importing and starting the
application do not require configuration to be present" still holds -- which
`tests/unit/test_startup_without_configuration.py` independently guards.

## Why a fresh interpreter

`commerce_ops.main` is imported at module scope by several test files in
this tier, so an in-process import would be a cache hit asserting nothing,
and a failed `importlib.reload` would leave a half-executed module behind
for every test that runs after it. The subprocess form is the one
`test_startup_without_configuration.py` already uses for exactly this
reason.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from commerce_ops.access.application import PrincipalsDirectory

DUPLICATED_IDENTITY = "U01DUPLICATE"

# Patches the loader on the already-imported module object *before*
# `commerce_ops.main` is imported, so that main's own
# `from ... import load_shipped_principals` binds the raising stand-in. The
# shipped file is valid by design (and is asserted so in
# `test_principals_loader.py`), so a malformed one cannot be produced by
# editing package data from a test.
_MALFORMED_DIRECTORY_SCRIPT = f"""
from commerce_ops.access.domain.principals import InvalidPrincipalsError
from commerce_ops.access.infrastructure.driven import principals_loader


def _raise_as_a_malformed_file_would():
    raise InvalidPrincipalsError(
        ["principal '{DUPLICATED_IDENTITY}' is declared more than once"]
    )


principals_loader.load_shipped_principals = _raise_as_a_malformed_file_would

import commerce_ops.main  # noqa: E402,F401
"""


def test_a_malformed_principals_directory_prevents_http_startup(
    tmp_path: Path,
) -> None:
    """Scenario: A malformed directory prevents serving rather than failing
    resolutions -- the startup half.

    WHEN the process starts against a malformed principals directory
    THEN startup fails with the load error naming the offending entry.

    Run from `tmp_path` with a bare environment, matching
    `test_startup_without_configuration.py`: the failure under test must be
    the directory's, not a missing variable's.
    """
    result = subprocess.run(
        [sys.executable, "-c", _MALFORMED_DIRECTORY_SCRIPT],
        env={"PATH": os.environ.get("PATH", "")},
        cwd=str(tmp_path),
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # SPECIFIED: startup fails.
    assert result.returncode != 0, (
        "importing commerce_ops.main against a malformed principals "
        "directory succeeded; a malformed directory must stop the process "
        "from starting to serve rather than surface on an asker's "
        f"resolution.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # SPECIFIED: the failure names the offending entry.
    assert DUPLICATED_IDENTITY in result.stderr, (
        "startup failed without naming the offending entry, leaving nothing "
        f"to correct the file by.\nstderr:\n{result.stderr}"
    )


def test_the_http_root_holds_the_validated_directory() -> None:
    """DERIVED, the positive half of the same wiring: the load actually
    happens at the composition root and its result is held.

    Without this, `main.py` could validate and discard, leaving the next
    change's resolver wiring to load the file a second time -- and a second
    load is a second place for an unvalidated directory to enter.
    """
    from commerce_ops.main import principals

    assert isinstance(principals, PrincipalsDirectory)
