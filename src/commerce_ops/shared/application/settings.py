"""The single declaration of what this application's runtime requires.

Implements the `runtime-configuration` capability
(`openspec/changes/revise-foundation-for-launch-mvp/specs/runtime-configuration/spec.md`).

What this declares, and what it does not:

- It declares every environment variable the *runtime* requires, whether
  this application's own source reads it or a dependency reads it on its
  behalf. `OPENAI_API_KEY` appears in no `os.environ` call anywhere in
  `src/`; it is read inside `langchain_openai.ChatOpenAI`. It is required
  all the same, and omitting it would make this an incomplete inventory.
- It does *not* declare a variable the deployment consumes but the
  application process never receives. `POSTGRES_PASSWORD` is read by
  `docker-compose.yml`'s own substitution and by the `postgres` service;
  this process cannot check what it never gets.
- It does *not* replace every direct `os.environ` read. A module may read a
  variable directly where routing it through the declaration would defeat
  required behavior -- `runtime-configuration`'s own wording, generalised
  from a narrower criterion when the trigger guard that motivated it was
  removed. `DATABASE_URL` is read directly for that reason: its reader must
  fail on its own absence, not on an unrelated variable's. `LOG_LEVEL` is
  read directly for the same reason of kind, though a different reason in
  substance: `configure_logging()` runs at
  `main.py`'s module import, where `get_settings()` would raise under this
  capability's own empty-environment guarantee below. It is declared here
  regardless, so the drift test still sees it and the startup report still
  names it.

`ENV_VAR_EXEMPTIONS` is what keeps the two facts above from rotting: the
drift test asserts that every variable the source reads is declared here,
and that every variable declared here is either read by the source or
carries an entry below naming what consumes it instead.

Forbidden names
---------------

Two environment variables must **never** be set in this application's
runtime, and are deliberately not declared below:

- ``SLACK_BOT_TOKEN``
- ``SLACK_SIGNING_SECRET``

These are the generic names Slack Bolt falls back to when the corresponding
constructor argument is omitted. This application constructs its Bolt apps
with a custom ``authorize`` callable and no token, so that no ``auth.test``
call is ever made; an ambient ``SLACK_BOT_TOKEN`` silently defeats that,
because Bolt adopts it, installs single-team authorization and ignores the
``authorize``. No argument value prevents the fallback, so
``shared/infrastructure/driving/slack_app.py`` refuses to build when the
name is present, and warns when ``SLACK_SIGNING_SECRET`` is.

They are absent from the model on purpose: declaring a variable here states
that the runtime *requires* it, which is the opposite of what is true. The
guard tests for their presence rather than reading their values, so the
drift check below is unaffected -- it detects value reads, and a name whose
absence is asserted is not a value this application consumes.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from typing import Annotated, Final

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The scheme SQLAlchemy's async engine is configured with (see
# `shared/infrastructure/driven/database.py`, the single process-wide
# session provider). A URL carrying any other scheme fails later with an
# error naming neither the variable nor the cause, so it is rejected here
# instead.
_REQUIRED_DATABASE_SCHEME: Final = "postgresql+asyncpg"


def must_be_an_async_postgres_url(value: str) -> str:
    """Public: also reused by `shared/infrastructure/driven/database.py` so
    the required scheme has one definition. Not moved there -- this module
    needs it for `DatabaseUrl`'s `AfterValidator`, and importing it back
    would be `shared.application` importing `shared.infrastructure`, which
    `.importlinter`'s `module-layers` contract forbids.
    """
    scheme, separator, _ = value.partition("://")
    if not separator or scheme != _REQUIRED_DATABASE_SCHEME:
        raise ValueError(
            f"must use the {_REQUIRED_DATABASE_SCHEME} scheme, "
            f"which this application connects with; got {scheme or value!r}"
        )
    return value


DatabaseUrl = Annotated[str, AfterValidator(must_be_an_async_postgres_url)]

# A required variable that is present but empty is a fault, not a value --
# a rendered-but-empty `.env` line is exactly the failure mode this exists
# to catch, and it is indistinguishable from absence in effect.
NonEmpty = Annotated[str, Field(min_length=1)]


class Settings(BaseSettings):
    """Every environment variable this application's runtime requires.

    A field with no default is required; a field defaulting to `None` is
    optional, and a caller reading it sees `None` when it is absent.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # The rendered `.env` this project deploys carries `IMAGE_TAG` and
        # `POSTGRES_PASSWORD`, neither of which is a field here. The strict
        # default would report both as faults for anyone holding a copy of
        # it, so keys this model does not declare are ignored.
        extra="ignore",
    )

    # Startup-critical, and required. The container's next step is
    # `alembic upgrade head`, which cannot run without this, so the process
    # genuinely cannot start; see `STARTUP_CRITICAL_ENV_VARS` below.
    database_url: DatabaseUrl

    # Required: each is scoped to one capability, so a fault in it degrades
    # that capability rather than the application.
    openai_api_key: NonEmpty
    omni_agent_slack_signing_secret: NonEmpty
    omni_agent_slack_bot_token: NonEmpty
    product_agent_slack_bot_token: NonEmpty
    product_agent_monitoring_channel_id: NonEmpty
    # Required as of `start-launch-from-slack`, its first consumer: the
    # `product_agent` app now receives inbound Slack traffic, so a
    # deployment without this is misconfigured rather than merely
    # feature-less. Required but *not* startup-critical, matching the other
    # Slack credentials -- absent, it is reported by name at startup, the
    # process still serves, and the launch-entry surface rejects every
    # request until it arrives (fail-closed degradation).
    product_agent_slack_signing_secret: NonEmpty

    # Optional: registered `production` secrets that no caller reaches yet.
    # `CLICKUP_API_TOKEN` in particular must stay optional --
    # `clickup-task-client`'s "Authentication is configured independently of
    # any one caller" has a scenario "Credential absent until first use", so
    # treating its absence as a fault would contradict a specification
    # already recorded in `openspec/specs/`.
    # Added by move-principals-to-roster (tasks 3.4): the Slack identity
    # the startup seed makes the first admin. Optional because it confers
    # nothing once the roster holds an admin of its own -- only a roster
    # that is readable, admin-less and unseeded needs it, and that is the
    # one case where its absence refuses startup.
    bootstrap_admin_identity: NonEmpty | None = None
    clickup_api_token: NonEmpty | None = None

    # Optional for the same reason `CLICKUP_API_TOKEN` is: each degrades
    # the launch completion loop rather than the application. Absent, the
    # webhook rejects every delivery and the reconciliation pass fails its
    # own run visibly -- both stated by `launch-clickup-sync` -- while the
    # rest of the system runs unchanged. Treating either as a startup fault
    # would make a capability's configuration a condition of booting.
    clickup_launch_folder_id: NonEmpty | None = None
    clickup_webhook_secret: NonEmpty | None = None

    # Optional, and deliberately typed `str | None` rather than `NonEmpty |
    # None` -- the same departure `LOG_LEVEL` makes below, for a related
    # reason. `record-gate-and-discipline-as-fields` gives absent and
    # present-but-empty *different* meanings: absent is how a deployment
    # declines the capability and is answered with silence, while an empty
    # value is what a mis-rendered secret produces for a deployment that
    # meant to opt in, and is reported as a configuration gap by the pass.
    # `NonEmpty` would collapse the distinction by refusing the empty value
    # here, so the fault would surface as a settings error instead of the
    # gap the check is written to report. Nothing validates or parses the
    # identifier either: a malformed non-empty value must arrive at the
    # pass and be reported as a field the folder does not include, not
    # raise before the pass ever runs.
    clickup_gate_field_id: str | None = None
    clickup_discipline_field_id: str | None = None

    # Optional: the public URL the admin surface is reachable at, consumed
    # by `access`'s admin-link adapter to compose magic links (and, by its
    # scheme, to decide the session cookie's Secure flag). Absent, the
    # `/playbook-admin` command refuses every caller rather than minting a
    # link no browser could follow — fail-closed degradation of that one
    # surface, like the other capability-scoped optionals above.
    admin_base_url: NonEmpty | None = None

    # Optional, and deliberately typed `str | None` rather than `NonEmpty |
    # None`: `application-logging`'s spec defines an empty value as "not
    # configured", and `NonEmpty` would make `preflight` report `LOG_LEVEL`
    # as faulting while logging behaved exactly as specified -- two accounts
    # of one value (that change's design.md, "Empty deserves a straight
    # answer").
    log_level: str | None = None


# The startup-critical marking sits *on top of* required -- it is not a
# third peer status. A fault in one of these fails the configuration check;
# a fault in any other declared variable is reported and startup continues.
STARTUP_CRITICAL_ENV_VARS: Final[frozenset[str]] = frozenset({"DATABASE_URL"})


# Declared variables that this application's own source does not read, each
# with the consumer that reads it instead. An entry with no reason fails the
# drift test: without that, this table becomes a place to hide omissions
# rather than a record of them.
ENV_VAR_EXEMPTIONS: Final[Mapping[str, str]] = {
    "OPENAI_API_KEY": (
        "read by langchain_openai.ChatOpenAI, constructed in "
        "omni_agent/application/graph.py"
    ),
}


@functools.lru_cache
def get_settings() -> Settings:
    """Builds and validates the declaration, once.

    Cached rather than eager, and never called at import time: the
    PR-validation gate imports `commerce_ops.main` and runs its lifespan
    with the production secrets absent, and must succeed. Reading
    configuration is therefore deferred to whoever actually needs it -- in
    practice `commerce_ops.preflight`, at container start.
    """
    # mypy reads the generated `__init__` and wants every field without a
    # default passed as a keyword argument. That is the wrong model for a
    # `BaseSettings`, whose whole purpose is to populate those fields from
    # the environment -- passing them here would defeat it. Narrowed to
    # `call-arg` so any other typing fault on this line still surfaces.
    return Settings()  # type: ignore[call-arg]
