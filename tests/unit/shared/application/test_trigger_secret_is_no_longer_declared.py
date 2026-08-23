"""`TRIGGER_SECRET` leaves the single declaration when its reader leaves.

Derived from `specs/runtime-configuration/spec.md` in the OpenSpec change
`replace-cron-with-job-runner`, MODIFIED requirement "Every Variable The
Runtime Requires Is Declared In One Place":

- Scenario: A declared variable the application does not read carries a
  recorded reason -- "or the absence of such a reason SHALL be detected
  automatically"

and from the same requirement's restated prose, which this change edits:
the illustrative example of a permitted direct read no longer cites
`internal-trigger`'s guard, since this change removes it.

See `test-manifest.md` at the change root for the full accounting, and in
particular for the four existing regression guards that transcribe
`TRIGGER_SECRET` and are recorded there as obsolete-in-part. This file
does not touch them: it adds the assertion this change specifically calls
for, which is that the variable is gone from the declaration altogether
rather than parked in the exemption table.

The three scenarios of this MODIFIED requirement are already covered,
generically, by `test_settings.py` and `test_settings_env_drift.py` --
whose drift check is itself the "detected automatically" mechanism the
second and third scenarios require. Restating them here would create a
second transcription of the variable set, which is the very thing making
those four guards need amending. What is added here is only the
change-specific instance.

Unlike most of this pass, these tests have a target that exists today and
are expected to fail on a wrong value -- `Settings` currently declares
`trigger_secret` -- rather than on an absent target.
"""

from __future__ import annotations

import commerce_ops.shared.application.settings as settings_module
from commerce_ops.shared.application.settings import (
    ENV_VAR_EXEMPTIONS,
    STARTUP_CRITICAL_ENV_VARS,
    Settings,
)

REMOVED_VARIABLE = "TRIGGER_SECRET"

# The removed capability and the removed module, whose names must not
# survive as the recorded justification for anything.
REMOVED_REFERENCES = ("trigger_guard", "internal-trigger")

# The two variables that actually rely on the direct-read permission after
# this change, per the delta's restated prose ("the variable controlling
# logging ... and ... the database connection setting").
PERMISSION_HOLDERS = ("LOG_LEVEL", "DATABASE_URL")


def test_the_removed_variable_is_not_declared() -> None:
    """Scenario: A declared variable the application does not read carries
    a recorded reason.

    SPECIFIED: with its only reader removed, the variable is not something
    "the application's runtime requires", so the single definition must
    not declare it.
    """
    fields = {name.upper() for name in Settings.model_fields}

    assert REMOVED_VARIABLE not in fields, (
        f"{REMOVED_VARIABLE} is still declared in the single definition, "
        "although nothing reads it after this change"
    )


def test_the_removed_variable_is_not_parked_in_the_exemption_table() -> None:
    """Scenario: A declared variable the application does not read carries
    a recorded reason.

    SPECIFIED, from the requirement's own reason for the table: an
    exemption names "what consumes it instead". Nothing consumes this
    variable after this change, so an exemption entry would be the
    exemption table used "as a place to hide omissions" -- which
    `settings.py` records as exactly what it must not become.
    """
    assert REMOVED_VARIABLE not in ENV_VAR_EXEMPTIONS, (
        f"{REMOVED_VARIABLE} was moved into the exemption table rather "
        f"than removed; recorded reason: {ENV_VAR_EXEMPTIONS.get(REMOVED_VARIABLE)!r}"
    )
    assert REMOVED_VARIABLE not in STARTUP_CRITICAL_ENV_VARS


def test_the_direct_read_permission_no_longer_cites_the_removed_guard() -> None:
    """DERIVED (tasks.md 4.3a), tracing to the MODIFIED requirement's
    restated prose rather than to a `#### Scenario:` block.

    The permission to read a variable directly is unchanged and still
    relied on; what changes is the example justifying it, which cited a
    capability this change removes. A stale citation points a future
    reader at a spec that no longer exists.
    """
    docstring = settings_module.__doc__ or ""

    stale = [name for name in REMOVED_REFERENCES if name in docstring]
    assert stale == [], (
        "the settings module still justifies its direct-read permission by "
        f"citing removed things: {stale}"
    )
    assert REMOVED_VARIABLE not in docstring, (
        f"the settings module still discusses {REMOVED_VARIABLE}"
    )
    missing = [name for name in PERMISSION_HOLDERS if name not in docstring]
    assert missing == [], (
        "the direct-read permission is left with no example naming what "
        f"relies on it today; expected mention of {missing}"
    )
