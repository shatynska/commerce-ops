"""Shared construction of a Slack Bolt `AsyncApp`, one per Slack app.

Implements the construction decisions of the `migrate-slack-to-bolt` change
(`openspec/changes/migrate-slack-to-bolt/design.md`). Lives in
`shared.infrastructure.driving`, not a business module, for the same reason
`trigger_guard.py` does: it carries no business logic and calls into no
module. Each module registers its own Slack app and owns its own
credentials.

Four decisions here are load-bearing and were each verified against
`slack-bolt` 1.30.0 rather than taken from its documentation. They are
recorded as Verified Findings 1, 7, 8 and 9 in the change's design.md; the
short forms are inline below, beside the code they constrain.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from slack_bolt.app.async_app import AsyncApp
from slack_bolt.authorization import AuthorizeResult
from slack_bolt.error import BoltUnhandledRequestError
from slack_bolt.response import BoltResponse

logger = logging.getLogger(__name__)

# Bolt reads these itself when the corresponding argument is omitted:
# `token = token or os.environ.get("SLACK_BOT_TOKEN")` (async_app.py:219),
# and the same shape for the signing secret. An ambient SLACK_BOT_TOKEN makes
# `self._token` truthy, which installs AsyncSingleTeamAuthorization and
# silently ignores our `authorize` -- restoring the `auth.test` call this
# whole construction exists to avoid. No argument value prevents the
# fallback, so it is a precondition rather than a parameter.
_FORBIDDEN_BOT_TOKEN_VAR: Final = "SLACK_BOT_TOKEN"
_FORBIDDEN_SIGNING_SECRET_VAR: Final = "SLACK_SIGNING_SECRET"

# Slack request types that Bolt answers without running authorization
# (`_is_no_auth_required` = url_verification or ssl_check). A challenge must
# stay answerable when the bot token is absent, so the credential gate lets
# it through. `ssl_check` needs no branch here: AsyncSslCheck is installed at
# position 1, ahead of this middleware at position 3, and detects it as
# `body["ssl_check"] == "1"` rather than by type.
_NO_REPLY_REQUEST_TYPE: Final = "url_verification"

TokenProvider = Callable[[], str | None]
WillReply = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class SlackAppSpec:
    """Everything needed to build one module's Bolt app.

    Providers rather than values: nothing here reads the environment until a
    request arrives, so importing this module -- and the app object it
    serves -- requires no Slack credential to be set.
    """

    signing_secret_provider: TokenProvider
    bot_token_provider: TokenProvider
    will_reply: WillReply


_REGISTRY: Final[dict[str, SlackAppSpec]] = {}


def register_slack_app(identity: str, spec: SlackAppSpec) -> None:
    """Registers one module's Slack app under a stable identity.

    The identity is the cache key: not the signing secret, which rotates, and
    not the provider objects, whose identity changes if a caller passes a
    fresh closure -- either would mean a new `AsyncApp` and a new
    `AsyncWebClient` per request.
    """
    _REGISTRY[identity] = spec


def _guard_forbidden_environment() -> None:
    """Refuses to build under an ambient generic Slack variable.

    Membership tests, never value reads, and that is required rather than
    stylistic: these names must never be declared in the settings model, and
    the environment-drift check's source-reads-must-be-declared direction
    admits no exemption. Asserting a name's absence is not consuming a value.

    Presence is the rule, not truthiness. An empty SLACK_BOT_TOKEN cannot
    defeat the guarantee, but reading its value to find that out is exactly
    the drift conflict above -- and a name set empty today may be set
    properly tomorrow without the deployment changing again.
    """
    if _FORBIDDEN_BOT_TOKEN_VAR in os.environ:
        raise RuntimeError(
            f"{_FORBIDDEN_BOT_TOKEN_VAR} is set in this runtime. Bolt falls "
            "back to it when no token argument is given, which installs "
            "single-team authorization and makes an auth.test call on the "
            "first request. Remove it; this application uses per-module "
            "variables instead."
        )

    if _FORBIDDEN_SIGNING_SECRET_VAR in os.environ:
        # Diagnostic only, deliberately not fatal: this application always
        # passes a signing secret explicitly, so Bolt's fallback is
        # unreachable. Failing hard would break every Slack request --
        # including the url_verification challenge Slack itself issues --
        # in exchange for protection against nothing.
        logger.warning(
            "%s is set in this runtime. It is unused here, but it is a name "
            "Bolt would fall back to; prefer removing it.",
            _FORBIDDEN_SIGNING_SECRET_VAR,
        )


def _build_authorize(
    bot_token_provider: TokenProvider,
) -> Callable[..., Awaitable[AuthorizeResult]]:
    """Supplies the bot token by declaration instead of by round-trip.

    Constructing with a `token` would make Bolt install
    AsyncSingleTeamAuthorization, whose middleware calls `auth.test` on the
    first request -- `if self._token:` wins over `elif self._async_authorize`
    (async_app.py:423/430). Passing `authorize` and no token is the only
    construction that avoids the call.

    No token-absence branch here, and no raise. A request the credential gate
    let through -- a challenge, an unhandled event type, a bot-authored
    mention -- reaches this callable with the token still absent, and must
    not fail: it never uses the injected client. Returning None would produce
    a 200 and raising would produce a 500, and the credential requirement
    forbids both.
    """

    async def authorize(**_kwargs: Any) -> AuthorizeResult:
        return AuthorizeResult(
            enterprise_id=None,
            team_id=None,
            bot_token=bot_token_provider() or "",
            bot_id=None,
            bot_user_id=None,
        )

    return authorize


def _build_credential_gate(
    bot_token_provider: TokenProvider, will_reply: WillReply
) -> Callable[..., Awaitable[Any]]:
    """Rejects a request that needs a reply credential it does not have.

    Installed as `before_authorize`, which Bolt places after request
    verification and immediately before authorization. That position is
    forced: returning None from `authorize` yields 200 and raising yields
    500, so neither can produce the 401 the requirement specifies.

    Scoped by the module's own predicate rather than by a list of exempt
    cases. Three successive drafts enumerated exemptions and each was one
    case short, because "requests that will reply" is not a list that can be
    finished from outside the module.
    """

    async def gate(req: Any, resp: Any, next: Callable[[], Awaitable[Any]]) -> Any:
        body = req.body if isinstance(req.body, Mapping) else {}

        # A challenge is answered by AsyncUrlVerification at position 6,
        # *after* authorization, so this middleware sees it first and must
        # let it past itself.
        if body.get("type") == _NO_REPLY_REQUEST_TYPE:
            return await next()

        try:
            needs_credential = will_reply(body)
        except Exception:
            logger.exception(
                "the will_reply predicate raised; treating the request as one "
                "that needs a reply credential"
            )
            needs_credential = True

        if needs_credential and not bot_token_provider():
            return BoltResponse(
                status=401, body={"error": "slack credential unavailable"}
            )

        return await next()

    return gate


def _register_unhandled_request_acknowledgement(app: AsyncApp) -> None:
    """Acknowledges an event no listener matched, instead of Bolt's 404.

    Slack treats a non-2xx as a delivery failure and retries, so the default
    turns "a newly subscribed event type has no handler yet" into a retry
    storm. Bolt's own unhandled-request path is used rather than a catch-all
    listener: it runs only after listener matching has already failed, so it
    cannot shadow a real listener by construction rather than by test.
    """

    @app.error
    async def handle_error(error: Exception) -> BoltResponse | None:
        if isinstance(error, BoltUnhandledRequestError):
            return BoltResponse(status=200, body="")

        # Every listener error reaches this handler, and registering it
        # displaces Bolt's default, whose contribution is the log. Status is
        # not the lever on the events path -- the acknowledgement is already
        # decided by the time the error arrives -- so log and return nothing,
        # leaving the response as Bolt left it. Returning 200 here would
        # convert a genuine failure into an apparent success on the
        # slash-command and interactivity paths this helper serves next.
        logger.exception("slack listener failed", exc_info=error)
        return None


@functools.lru_cache
def get_slack_app(identity: str) -> AsyncApp:
    """Builds one module's Bolt app, once, on first use.

    Cached rather than eager, and never called at import time: the
    PR-validation gate imports `commerce_ops.main` and runs its lifespan with
    the Slack secrets absent, and must succeed. `lru_cache` also supplies the
    `cache_clear()` seam a test needs to observe a changed environment rather
    than an app built from an earlier one.
    """
    spec = _REGISTRY[identity]

    _guard_forbidden_environment()

    app = AsyncApp(
        # Explicit, so Bolt's SLACK_SIGNING_SECRET fallback is unreachable.
        # An empty value is not an error here: Bolt does not raise for one,
        # and its own request verification then answers 401 natively.
        signing_secret=spec.signing_secret_provider() or "",
        authorize=_build_authorize(spec.bot_token_provider),
        before_authorize=_build_credential_gate(
            spec.bot_token_provider, spec.will_reply
        ),
        raise_error_for_unhandled_request=True,
        # `process_before_response` is left at its False default: Bolt then
        # acknowledges before running the listener, which is what keeps the
        # acknowledgement independent of how long generation takes.
        #
        # `token_verification_enabled` is NOT passed: AsyncApp has no such
        # parameter -- it exists only on the synchronous App. Believing
        # otherwise is what made this a separate change.
    )
    _register_unhandled_request_acknowledgement(app)
    return app
