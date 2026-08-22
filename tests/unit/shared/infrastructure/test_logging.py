"""In-process tests for `commerce_ops.shared.infrastructure.logging`.

Derived strictly from the `application-logging` capability's delta spec:
`openspec/changes/configure-application-logging/specs/application-logging/spec.md`.

`src/commerce_ops/shared/infrastructure/logging.py` does not exist yet
(tasks.md 1.1), so every test in this file is expected to fail on collection
or on an absent target (`ModuleNotFoundError` / `AttributeError`) until it
lands. That failure establishes only that the target is absent -- see
`test-manifest.md` at the change root.

WHY THE RESET FIXTURE RUNS FIRST (design.md, Risks/Trade-offs; tasks.md
5.1). Several unit modules elsewhere in this suite import `commerce_ops.main`
at module/collection time, which -- once implemented -- runs
`configure_logging()` once before any test body in this *session* executes.
Combined with the idempotency guard (tasks.md 1.4), a test in this file that
called `configure_logging()` without first detaching that handler would
silently assert against the collection-time configuration instead of its
own. `_reset_logging_configuration` below is `autouse`, uses the module's
documented reset seam (tasks.md 1.7, `_reset()`) to detach the sentinel
handler, and restores the two logger levels itself, exactly as tasks.md 5.1
specifies -- the seam deliberately does not touch levels, because "restore"
has no single correct target for it to pick.

HOW A TEST OBSERVES "reached the process's standard error stream". Every
test that needs to observe emitted output requests pytest's own `capsys`
fixture and reads `capsys.readouterr().err` -- not a bespoke
`monkeypatch.setattr(sys, "stderr", io.StringIO())` fixture, which was tried
first and does not work here: pytest's default capture manager reinstalls
its own `sys.stderr` proxy when a test's *call* phase begins, which silently
discards a patch applied during a fixture's *setup* phase (confirmed
empirically -- `sys.stderr`'s object identity differs between the two
phases under default capture). `logging.StreamHandler()` (task 1.5) binds to
whatever `sys.stderr` *is* at construction time, which is fine here because
`configure_logging()` is always called from inside the test body itself
(the call phase), where `sys.stderr` is already pytest's own capture-managed
object -- exactly what `capsys.readouterr()` reads from. `readouterr()`
drains what it returns, so a test that needs the value more than once
captures it into a variable rather than calling `readouterr()` again.

CONSTRUCTING "DEPENDENCY" LOGGERS (design.md, "The installed dependencies
were then checked, rather than left to assertion"; tasks.md 5's own
preamble). No test in this file asserts against an installed third-party
package's real logger (`sqlalchemy`, `slack_bolt`, `httpx`, ...) -- doing so
is either vacuously true (a library that already sets its own `WARNING`
level) or breaks on an unrelated dependency bump with no behavioural
meaning, per design.md's own account of checking those loggers directly.
Every "unconfigured dependency" and "self-configuring library" in this file
is a fresh `logging.getLogger(<unique, fictitious name>)` constructed inside
the test, never a real package's logger name.
"""

from __future__ import annotations

import io
import logging
import uuid
from collections.abc import Iterator

import pytest

from commerce_ops.shared.infrastructure import logging as logging_config

# --------------------------------------------------------------------------
# Reset fixture -- required first. See module docstring.
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_logging_configuration() -> Iterator[None]:
    root = logging.getLogger()
    app_logger = logging.getLogger("commerce_ops")
    root_level, app_level = root.level, app_logger.level

    logging_config._reset()

    yield

    logging_config._reset()
    root.setLevel(root_level)
    app_logger.setLevel(app_level)


def _unique_dependency_logger() -> logging.Logger:
    """A fresh, fictitious logger name -- never a real installed package's.

    Unique per call so leftover state from one test (a level or handler set
    on it) can never leak into another test's assertions; an unused, unique
    `NOTSET`/no-handler logger left in `logging.Logger.manager` afterward is
    harmless.
    """
    return logging.getLogger(f"fixture_dependency_{uuid.uuid4().hex}")


def _app_logger() -> logging.Logger:
    return logging.getLogger(f"commerce_ops.fixture_probe_{uuid.uuid4().hex}")


def _looks_like_a_timestamp(text: str) -> bool:
    """Loosely matches an `HH:MM:SS`-shaped component anywhere in `text`.

    DERIVED, deliberately loose: neither the delta spec nor design.md pins
    an exact strftime format for "the time of emission" -- only that it must
    be present -- so this avoids asserting a specific formatter string that
    would make the test brittle to an implementation detail nothing here
    requires.
    """
    import re

    return re.search(r"\d{1,2}:\d{2}:\d{2}", text) is not None


# --------------------------------------------------------------------------
# Requirement: The Application Emits Its Own Log Records
# --------------------------------------------------------------------------


def test_a_record_at_the_configured_threshold_is_emitted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: A record at the configured threshold is emitted.

    WHEN the application's logging is configured, and the application emits
    a record at the configured threshold
    THEN that record SHALL reach the process's standard error stream.
    """
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().warning(marker)

    # Specified.
    assert marker in capsys.readouterr().err


def test_an_application_record_below_the_configured_threshold_is_suppressed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: An application record below the configured threshold is
    suppressed.

    WHEN the application's logging is configured at a given threshold, and
    the application emits a record below it
    THEN that record SHALL NOT reach the process's standard error stream.
    """
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().info(marker)

    # Specified.
    assert marker not in capsys.readouterr().err


def test_an_informational_record_is_emitted_under_the_default_threshold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: An informational record is emitted under the default
    threshold; also covers Scenario: The threshold is not configured (both
    under different requirements, same precondition and mechanism -- tasks.md
    5.3 groups them the same way).

    WHEN the application's logging is configured with no threshold
    specified, and the application emits a record at informational level
    THEN that record SHALL reach the process's standard error stream.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().info(marker)

    # Specified.
    assert marker in capsys.readouterr().err


# --------------------------------------------------------------------------
# Requirement: The Threshold Is Configurable And Defaults To Informational
# --------------------------------------------------------------------------


def test_the_threshold_is_configured_explicitly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: The threshold is configured explicitly.

    WHEN the threshold is configured to a recognized severity level
    THEN application records at or above that level SHALL be emitted, and
    application records below it SHALL NOT.

    All three parts of the THEN clause are exercised directly: at, above,
    and below the configured `WARNING` threshold.
    """
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logging_config.configure_logging()

    at_marker = f"at-{uuid.uuid4().hex}"
    above_marker = f"above-{uuid.uuid4().hex}"
    below_marker = f"below-{uuid.uuid4().hex}"
    logger = _app_logger()
    logger.warning(at_marker)
    logger.error(above_marker)
    logger.info(below_marker)

    output = capsys.readouterr().err
    # Specified: at or above the threshold is emitted.
    assert at_marker in output
    assert above_marker in output
    # Specified: below the threshold is not.
    assert below_marker not in output


def test_the_threshold_is_configured_as_an_empty_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: The threshold is configured as an empty value.

    WHEN the threshold is present in the environment but empty
    THEN it SHALL be treated as not configured, the threshold SHALL be
    informational level, and no unrecognized-value report SHALL be made.
    """
    monkeypatch.setenv("LOG_LEVEL", "")
    logging_config.configure_logging()

    # Specified: no unrecognized-value report is made. Checked before any
    # other emission so the buffer contains only what `configure_logging()`
    # itself produced. `readouterr()` drains what it returns, so it is
    # captured once and reused rather than called twice.
    report = capsys.readouterr().err
    assert report == "", (
        f"an empty LOG_LEVEL must produce no unrecognized-value report; got: {report!r}"
    )

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().info(marker)

    # Specified: treated as not configured -> default (informational).
    assert marker in capsys.readouterr().err


def test_a_level_name_in_lower_case_is_recognized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: A level name in lower case is recognized.

    WHEN the threshold is configured to a recognized severity level written
    in lower case
    THEN it SHALL be applied as that level, and no unrecognized-value report
    SHALL be made.
    """
    monkeypatch.setenv("LOG_LEVEL", "debug")
    logging_config.configure_logging()

    # Specified: no unrecognized-value report. Captured once and reused --
    # `readouterr()` drains what it returns.
    report = capsys.readouterr().err
    assert report == "", (
        f"a lower-case LOG_LEVEL must produce no report; got: {report!r}"
    )

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().debug(marker)

    # Specified: applied as DEBUG, not the INFO default.
    assert marker in capsys.readouterr().err


def test_the_zero_level_is_treated_as_unrecognized(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: The zero level is treated as unrecognized.

    WHEN the threshold is configured to a value naming the zero level
    THEN logging SHALL be configured at the default threshold
    AND the value SHALL be reported as unrecognized.
    """
    monkeypatch.setenv("LOG_LEVEL", "NOTSET")
    logging_config.configure_logging()

    report = capsys.readouterr().err
    # Specified: the value is reported as unrecognized.
    assert report != "", "LOG_LEVEL=NOTSET must produce an unrecognized-value report"
    assert "NOTSET" in report, (
        f"the report does not name the rejected value 'NOTSET': {report!r}"
    )

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().info(marker)

    # Specified: configured at the default (informational) threshold.
    assert marker in capsys.readouterr().err


@pytest.mark.parametrize(
    "raw_value",
    [
        "NOT_A_LEVEL",
        # DERIVED deviation from tasks.md 5.12's literal example "20": a
        # short numeric string risks colliding with a substring of whatever
        # timestamp format the implementation happens to render (e.g. an
        # hour, minute, or day component), which would make the "the report
        # names the rejected value" assertion below pass by coincidence
        # rather than by the behaviour it's meant to check. "9999" cannot
        # collide with a 4-digit year (2026), an HH/MM/SS component (<= 59),
        # or a 3-digit millisecond field. The requirement itself does not
        # pin the literal value "20" -- only that a numeric value is
        # unrecognized -- so this substitution changes no scenario coverage.
        "9999",
    ],
)
def test_the_configured_threshold_is_not_a_recognized_level(
    raw_value: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: The configured threshold is not a recognized level.

    WHEN the threshold is configured to a non-empty value that does not name
    a recognized severity level, including a numeric value
    THEN logging SHALL be configured at the default threshold
    AND the unrecognized value SHALL be reported
    AND the application SHALL NOT fail to start on account of it.
    """
    monkeypatch.setenv("LOG_LEVEL", raw_value)

    # Specified: does not raise / fail to start.
    logging_config.configure_logging()

    report = capsys.readouterr().err
    # Specified: reported.
    assert report != "", f"LOG_LEVEL={raw_value!r} must produce a report"
    assert raw_value in report, (
        f"the report does not name the rejected value {raw_value!r}: {report!r}"
    )

    marker = f"probe-{uuid.uuid4().hex}"
    _app_logger().info(marker)

    # Specified: configured at the default (informational) threshold.
    assert marker in capsys.readouterr().err


# --------------------------------------------------------------------------
# Requirement: Dependency Records Are Formatted But Not Governed By The
# Application's Threshold
# --------------------------------------------------------------------------


def test_an_unconfigured_dependencys_informational_record_is_suppressed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: An unconfigured dependency's informational record is
    suppressed.

    WHEN logging is configured at any threshold and a library whose logger
    carries no handler and sets no level of its own emits a record at
    informational level
    THEN that record SHALL NOT reach the process's standard error stream.

    "any threshold" is exercised with the application's own threshold set
    well below informational (`DEBUG`), so a failure here cannot be
    attributed to the application's own threshold happening to be at or
    above informational.
    """
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _unique_dependency_logger().info(marker)

    # Specified.
    assert marker not in capsys.readouterr().err


def test_an_unconfigured_dependencys_warning_is_emitted_and_formatted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: An unconfigured dependency's warning is emitted and
    formatted.

    WHEN a library whose logger carries no handler and sets no level of its
    own emits a record at warning level or above
    THEN that record SHALL reach the process's standard error stream,
    formatted the same way as the application's own records.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()

    dependency_logger = _unique_dependency_logger()
    marker = f"probe-{uuid.uuid4().hex}"
    dependency_logger.warning(marker)

    output = capsys.readouterr().err
    # Specified: reached the stream.
    assert marker in output
    # Specified: formatted the same way as an application record -- i.e.
    # carries the same components "Every Emitted Record Carries Time,
    # Level, And Origin" requires: a time-like component, the level name,
    # and the emitting logger's own name.
    assert _looks_like_a_timestamp(output)
    assert "WARNING" in output
    assert dependency_logger.name in output


def test_a_library_that_configures_its_own_logger_still_emits_its_own_records(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: A library that configures its own logger still emits its
    own records.

    WHEN a library sets its own logger's level to informational, attaches
    its own handler, and emits an informational record
    THEN that record SHALL be emitted by the library's own handler
    AND it SHALL additionally reach this capability's handler if that
    logger propagates, so such a record appears twice rather than being
    suppressed.

    Root's threshold (`WARNING`) does not gate this: per design.md's
    "Set root's level to WARNING" decision, only the *originating* logger's
    own effective level gates record creation, and this logger's own level
    is `INFO`, set on itself.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()

    dependency_logger = _unique_dependency_logger()
    dependency_logger.setLevel(logging.INFO)
    own_buffer = io.StringIO()
    dependency_logger.addHandler(logging.StreamHandler(own_buffer))
    # `propagate` is left at its default (True) deliberately -- the
    # scenario's own "if that logger propagates" clause is exercised, not
    # bypassed.

    marker = f"probe-{uuid.uuid4().hex}"
    dependency_logger.info(marker)

    # Specified: emitted by the library's own handler.
    assert marker in own_buffer.getvalue()
    # Specified: additionally reaches this capability's handler.
    assert marker in capsys.readouterr().err


def test_lowering_the_applications_threshold_does_not_turn_on_dependency_logging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: Lowering the application's threshold does not turn on
    dependency logging.

    WHEN the configured threshold is set below warning level
    THEN the records of a library whose logger carries no handler and sets
    no level of its own SHALL still NOT be emitted below warning level.
    """
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _unique_dependency_logger().info(marker)

    # Specified.
    assert marker not in capsys.readouterr().err


def test_raising_the_applications_threshold_does_not_silence_dependency_warnings(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: Raising the application's threshold does not silence
    dependency warnings.

    WHEN the configured threshold is set above warning level
    THEN the records of a library whose logger carries no handler and sets
    no level of its own SHALL still be emitted at warning level and above.
    """
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    logging_config.configure_logging()

    marker = f"probe-{uuid.uuid4().hex}"
    _unique_dependency_logger().warning(marker)

    # Specified.
    assert marker in capsys.readouterr().err


# --------------------------------------------------------------------------
# Requirement: Every Emitted Record Carries Time, Level, And Origin
# --------------------------------------------------------------------------


def test_a_record_emitted_through_the_configured_logging_identifies_when_how_severe_and_from_where(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: A record emitted through the configured logging identifies
    when, how severe, and from where.

    WHEN a record is emitted through the logging this capability configures
    THEN the emitted output SHALL carry the time of emission, the record's
    level, and the emitting logger's name alongside the message.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()

    logger = _app_logger()
    marker = f"probe-{uuid.uuid4().hex}"
    logger.info(marker)

    output = capsys.readouterr().err
    # Specified: message.
    assert marker in output
    # Specified: time of emission.
    assert _looks_like_a_timestamp(output)
    # Specified: the record's level.
    assert "INFO" in output
    # Specified: the emitting logger's name.
    assert logger.name in output


def test_an_exceptions_traceback_is_preserved(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: An exception's traceback is preserved.

    WHEN a record that includes exception information is emitted through
    the logging this capability configures
    THEN the emitted output SHALL carry that exception's traceback.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()

    logger = _app_logger()
    marker = f"probe-{uuid.uuid4().hex}"
    try:
        raise ValueError(marker)
    except ValueError:
        logger.exception("something went wrong")

    output = capsys.readouterr().err
    # Specified: the traceback is present.
    assert "Traceback (most recent call last):" in output
    assert "ValueError" in output
    assert marker in output


# --------------------------------------------------------------------------
# Requirement: Logging Is Configured From Every Entrypoint
# (the "non-HTTP entrypoint" and "fresh interpreter" scenarios of this
# requirement are covered in test_logging_process_boundary.py; see its
# module docstring for why they need a fresh interpreter.)
# --------------------------------------------------------------------------


def test_configuring_logging_more_than_once_does_not_duplicate_records(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario: Configuring logging more than once does not duplicate
    records.

    WHEN logging is configured more than once in a single process
    THEN a subsequently emitted record SHALL be emitted once, not once per
    configuration.
    """
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logging_config.configure_logging()
    logging_config.configure_logging()

    logger = _app_logger()
    marker = f"probe-{uuid.uuid4().hex}"
    logger.info(marker)

    # Specified. Captured once and reused -- `readouterr()` drains what it
    # returns.
    output = capsys.readouterr().err
    assert output.count(marker) == 1, (
        "configuring logging twice must not duplicate a subsequently "
        f"emitted record; captured stderr:\n{output!r}"
    )
