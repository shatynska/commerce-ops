"""Drift tests: the declaration must not diverge from what the source reads.

Derived strictly from the `runtime-configuration` delta spec at
`openspec/changes/revise-foundation-for-launch-mvp/specs/runtime-configuration/spec.md`,
requirement "Every Variable The Runtime Requires Is Declared In One Place",
scenarios two and three. Both scenarios say the condition "SHALL be detected
automatically, rather than depending on a reader noticing it" -- so the tests
in this file *are* the mechanism the scenarios require, not merely coverage
of one.

The two directions are deliberately NOT symmetric (design.md, "A drift test
with a reasoned exemption table"; tasks.md section 6):

- source-reads-must-be-declared admits no exemption at all;
- declared-must-be-read consults the exemption table;
- and a third test requires every exemption entry to carry a reason, so the
  table cannot become a place to hide omissions.

`commerce_ops.shared.application.settings` does not exist yet (tasks 4.1,
6.1), so this module is expected to fail collection with
`ModuleNotFoundError` until it lands. See `test-manifest.md` at the change
root, including the interface names this file assumes.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from commerce_ops.shared.application.settings import ENV_VAR_EXEMPTIONS, Settings

# --------------------------------------------------------------------------
# Scan scope, transcribed from tasks.md 6.5.
# --------------------------------------------------------------------------

SCANNED_TREES = ("src/commerce_ops", "alembic")

# "Exclude the settings module and the preflight entry point themselves"
# (tasks 6.5) -- the declaration naming its own variables, and the preflight
# reporting on them, are not application reads.
EXCLUDED_FILES = (
    "src/commerce_ops/shared/application/settings.py",
    "src/commerce_ops/preflight.py",
)

# tasks.md 6.6's confirmed inventory of what the tree reads today. Used only
# by the scanner's own self-check below -- the drift assertions themselves
# never mention a variable by name, or they would stop detecting drift.
KNOWN_READS_AT_TIME_OF_WRITING = frozenset(
    {
        "PRODUCT_AGENT_SLACK_BOT_TOKEN",
        "PRODUCT_AGENT_MONITORING_CHANNEL_ID",
        "DATABASE_URL",
        "OMNI_AGENT_SLACK_SIGNING_SECRET",
        "OMNI_AGENT_SLACK_BOT_TOKEN",
        "TRIGGER_SECRET",
        "CLICKUP_API_TOKEN",
    }
)

# tasks.md 6.1's seeded exemption table.
SEEDED_EXEMPTIONS = frozenset({"OPENAI_API_KEY", "PRODUCT_AGENT_SLACK_SIGNING_SECRET"})


# --------------------------------------------------------------------------
# The scanner. Covers the idiom family tasks.md 6.5 names: `os.environ[...]`,
# `os.environ.get(...)` and `os.getenv(...)`. Parsed rather than regexed so a
# name inside a string or comment is not mistaken for a read.
# --------------------------------------------------------------------------


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    pytest.fail("could not locate the repository root from this test's path")


def _is_os_environ(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "environ" and (
            isinstance(node.value, ast.Name) and node.value.id == "os"
        )
    return isinstance(node, ast.Name) and node.id == "environ"


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_env_read_call(func: ast.expr) -> bool:
    """`os.environ.get(...)`, `os.getenv(...)`, or a bare `getenv(...)`."""
    if isinstance(func, ast.Attribute):
        if func.attr == "get":
            return _is_os_environ(func.value)
        if func.attr == "getenv":
            return isinstance(func.value, ast.Name) and func.value.id == "os"
        return False
    return isinstance(func, ast.Name) and func.id == "getenv"


class _EnvReadCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()

    def _record_first_arg(self, call: ast.Call) -> None:
        if call.args:
            name = _constant_str(call.args[0])
            if name is not None:
                self.names.add(name)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if _is_os_environ(node.value):
            name = _constant_str(node.slice)
            if name is not None:
                self.names.add(name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_env_read_call(node.func):
            self._record_first_arg(node)
        self.generic_visit(node)


def _scanned_source_files() -> list[Path]:
    root = _repository_root()
    excluded = {(root / relative).resolve() for relative in EXCLUDED_FILES}
    files: list[Path] = []
    for tree in SCANNED_TREES:
        directory = root / tree
        assert directory.is_dir(), f"scan scope {tree!r} is not a directory"
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if path.resolve() in excluded:
                continue
            files.append(path)
    return files


def _environment_names_read_by_source() -> set[str]:
    names: set[str] = set()
    for path in _scanned_source_files():
        collector = _EnvReadCollector()
        collector.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        names |= collector.names
    return names


def _env_name(field_name: str, field: Any) -> str:
    alias = (
        field.validation_alias if field.validation_alias is not None else field.alias
    )
    if alias is None:
        return field_name.upper()
    if isinstance(alias, str):
        return alias.upper()
    pytest.fail(
        f"field {field_name!r} declares a non-string validation alias ({alias!r}); "
        "see test-manifest.md"
    )


def _declared_env_names() -> set[str]:
    return {_env_name(name, field) for name, field in Settings.model_fields.items()}


def _sorted(names: Iterable[str]) -> list[str]:
    return sorted(names)


# --------------------------------------------------------------------------
# Self-checks on the scanner itself.
#
# Without these, the two drift assertions below are satisfiable by a scanner
# that finds nothing: `set() <= declared` passes, and every declared variable
# would then look unread. A scanner returning an empty set is exactly the
# false pass the whole mechanism exists to prevent, so it is asserted
# against directly.
# --------------------------------------------------------------------------


def test_scanner_finds_the_reads_known_to_exist_in_the_tree() -> None:
    """DERIVED from tasks.md 6.6's confirmed inventory, not from a scenario.

    This guards the scanner, not the declaration: it fails if the scanner
    stops recognising an idiom that is in use, which would silently disarm
    the two drift assertions below.
    """
    found = _environment_names_read_by_source()

    missing = KNOWN_READS_AT_TIME_OF_WRITING - found
    assert not missing, (
        "the environment-read scanner no longer finds reads tasks.md 6.6 "
        f"confirmed are present in the scanned tree: {_sorted(missing)}. "
        "Either the read moved/changed idiom (update the scanner) or it was "
        "genuinely removed (update KNOWN_READS_AT_TIME_OF_WRITING)."
    )


def test_scan_scope_covers_both_trees_and_excludes_the_declaration_itself() -> None:
    """DERIVED from tasks.md 6.5, not from a scenario.

    `alembic/` is in scope because it runs inside the same container and
    `alembic/env.py` reads `DATABASE_URL`; the settings module and preflight
    are out of scope because naming a variable there is a declaration, not an
    application read.
    """
    scanned = {path.resolve() for path in _scanned_source_files()}
    root = _repository_root()

    assert any(
        path.is_relative_to(root / "src" / "commerce_ops") for path in scanned
    ), "the scan covers no file under src/commerce_ops/"
    assert any(path.is_relative_to(root / "alembic") for path in scanned), (
        "the scan covers no file under alembic/, so alembic/env.py's "
        "DATABASE_URL read would go unseen"
    )
    for relative in EXCLUDED_FILES:
        assert (root / relative).resolve() not in scanned, (
            f"{relative} must be excluded from the scan (tasks 6.5)"
        )


# --------------------------------------------------------------------------
# Requirement: Every Variable The Runtime Requires Is Declared In One Place
# --------------------------------------------------------------------------


def test_every_variable_the_source_reads_is_declared() -> None:
    """Scenario: A variable read by the application but not declared is detected.

    WHEN the application's own source reads an environment variable that the
    single definition does not declare
    THEN that omission SHALL be detected automatically, rather than depending
    on a reader noticing it.

    No exemption is possible in this direction (design.md: "a direct
    `os.environ` read that the model does not know about is exactly the drift
    being prevented"). `ENV_VAR_EXEMPTIONS` is deliberately not consulted
    here.
    """
    read = _environment_names_read_by_source()
    declared = _declared_env_names()

    undeclared = read - declared
    # Specified.
    assert not undeclared, (
        "the application source reads environment variables the settings "
        f"declaration does not declare: {_sorted(undeclared)}. Declare them "
        "in commerce_ops.shared.application.settings -- this direction admits "
        "no exemption."
    )


def test_every_declared_variable_is_read_or_carries_an_exemption() -> None:
    """Scenario: A declared variable the application does not read carries a
    recorded reason.

    WHEN the single definition declares a variable that the application's own
    source does not read
    THEN that variable SHALL carry a recorded reason naming what consumes it
    instead, or the absence of such a reason SHALL be detected automatically.

    This is the direction the exemption table exists for: `OPENAI_API_KEY` is
    read by `langchain_openai`, and `PRODUCT_AGENT_SLACK_SIGNING_SECRET` has
    no consumer yet.
    """
    read = _environment_names_read_by_source()
    declared = _declared_env_names()

    unaccounted = declared - read - set(ENV_VAR_EXEMPTIONS)
    # Specified.
    assert not unaccounted, (
        "the settings declaration declares variables the application source "
        f"does not read, with no recorded exemption: {_sorted(unaccounted)}. "
        "Either a read is missing, or add an ENV_VAR_EXEMPTIONS entry whose "
        "reason names what consumes the variable instead."
    )


def test_every_exemption_carries_a_non_empty_reason() -> None:
    """Same scenario, second half: "... or the absence of such a reason SHALL
    be detected automatically" (tasks 6.4).

    LIMIT, recorded rather than glossed: "naming what consumes it" is not
    mechanically checkable, so this asserts only that a reason is present and
    non-blank. Whether the reason actually names a consumer stays a review
    obligation -- which is the point of keeping each entry a reviewable line
    (design.md).
    """
    assert ENV_VAR_EXEMPTIONS, (
        "the exemption table is empty; tasks 6.1 seeds it with "
        f"{_sorted(SEEDED_EXEMPTIONS)}"
    )

    for name, reason in ENV_VAR_EXEMPTIONS.items():
        # Specified.
        assert isinstance(reason, str) and reason.strip(), (
            f"exemption entry {name!r} carries no reason; an unreasoned "
            "exemption is a place to hide an omission (design.md)"
        )


def test_exemptions_only_cover_declared_variables() -> None:
    """DERIVED, not a scenario.

    An exemption for a variable the declaration does not declare exempts
    nothing, and would quietly outlive the declaration it was written for.
    """
    stale = set(ENV_VAR_EXEMPTIONS) - _declared_env_names()

    assert not stale, (
        f"the exemption table names variables that are not declared: {_sorted(stale)}"
    )


def test_exemption_table_is_seeded_as_the_change_specifies() -> None:
    """DERIVED from tasks.md 6.1 and 6.6, not from a scenario.

    tasks 6.6: "the two declared-but-unread are exactly the seeded
    exemptions". Asserted as a subset rather than equality so that a later
    change adding a genuinely-exempt variable does not have to edit this
    test -- the seeded pair must survive, an addition need not be forbidden.
    """
    missing = SEEDED_EXEMPTIONS - set(ENV_VAR_EXEMPTIONS)

    assert not missing, (
        f"the exemption table is missing seeded entries: {_sorted(missing)}"
    )
