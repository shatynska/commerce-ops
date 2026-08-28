"""Driving adapter: starting a launch from Slack, on the `product_agent` app.

Implements the `launch-entry` capability. One interaction takes a new product
from nonexistent to launched: a slash command opens a modal, and submitting it
registers the product in the catalog and starts its launch, both in one
transaction.

Bolt owns request verification, acknowledgement timing and dispatch; this
module owns the listeners, the credentials, the modal's contract, and the
predicate deciding which requests need a reply credential.

Credentials are read directly from `os.environ` rather than through
`get_settings()`, exactly as `omni_agent`'s adapter does and for the same
reason: `runtime-configuration` permits a direct read "where per-request
tolerance of absence is itself required behavior", and rejecting an
unverifiable request with 401 rather than raising is exactly that. The
variable stays declared in the settings model, so the startup check still
reports it by name.

Two collaborators arrive differently, and the difference is load-bearing:

- `start_launch` is imported by name and called as a bare module global,
  keeping `clickup_sync_job.py`'s pattern.
- The catalog write arrives by *injection*. `.importlinter`'s
  `products-infrastructure-boundary` forbids this module from importing
  catalog's store, so `main.py` -- which sits outside both containers --
  supplies a registrar that runs `catalog.application.register_product`
  over a store built on the session this module opens. That shared session
  is what makes the atomicity below possible.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from typing import Any, Final, Protocol

from fastapi import APIRouter, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.catalog.application import DuplicateSkuError
from commerce_ops.launch.application import start_launch
from commerce_ops.launch.domain.launch_playbook import PlaybookNotReadyError
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.infrastructure.driven.database import transaction
from commerce_ops.shared.infrastructure.driving.slack_app import (
    SlackAppSpec,
    get_slack_app,
    register_slack_app,
)

__all__ = [
    "SLACK_APP_IDENTITY",
    "CatalogRegistrar",
    "register_catalog_product",
    "reset_handler_cache",
    "router",
    "start_launch",
    "transaction",
    "will_reply",
]

logger = logging.getLogger(__name__)

router = APIRouter()

SLACK_APP_IDENTITY: Final = "product_agent"

SLASH_COMMAND: Final = "/start-launch"
CALLBACK_ID: Final = "start_launch_modal"

# Block id and action id are the same string for every field: the submitted
# view's state is keyed `values[block_id][action_id]`, and keeping them equal
# means one name per field rather than two that must be kept in step.
SKU_FIELD: Final = "sku"
NAME_FIELD: Final = "name"
ASIN_FIELD: Final = "asin"
LAUNCH_DATE_FIELD: Final = "launch_date"
MARKETPLACE_FIELD: Final = "marketplace"

# The single marketplace offered for now. A select rather than a constant so
# that adding a second is a data change, not a redesign (design.md Decision 4).
AMAZON_US_MARKETPLACE_ID: Final = "ATVPDKIKX0DER"
AMAZON_US_LABEL: Final = "Amazon US"

# How long the ClickUp completion loop may take to project the new launch's
# work. Named in the confirmation on purpose: otherwise the first question
# after a successful start is "where are the tasks?" (design.md Decision 6).
CLICKUP_SYNC_CADENCE_DESCRIPTION: Final = "within about 10 minutes"


class CatalogRegistrar(Protocol):
    """Registers a product on the caller's own session, returning its id.

    Returns the identifier rather than the `Product` itself, so this module
    never dereferences catalog's aggregate -- it only forwards the id to
    `start_launch`.
    """

    async def __call__(
        self,
        db_session: AsyncSession,
        *,
        sku: Sku,
        marketplace_id: MarketplaceId,
        name: str,
        asin: Asin | None,
    ) -> ProductId: ...


# Injected by `main.py` after the app is built, never at import time and
# never as a listener argument. Resolved at call time, keeping
# `clickup_sync_job.read_product`'s monkeypatch-friendly pattern; a missing
# injection fails loudly at first use rather than silently at import.
register_catalog_product: CatalogRegistrar | None = None


def _signing_secret() -> str | None:
    # The variable name is a literal here and in every read below, on
    # purpose: the environment-drift check parses the source for
    # `os.environ[...]` / `.get(...)` with a *constant* argument, so passing
    # the module constant instead would make these reads invisible to it.
    return os.environ.get("PRODUCT_AGENT_SLACK_SIGNING_SECRET")


def _bot_token() -> str | None:
    """Reports absence as a falsy value, never by raising.

    The credential gate calls this inside a Bolt middleware, where a
    `KeyError` would escape to Bolt's outer handler and become a 500 -- the
    outcome the credential requirement forbids as explicitly as it forbids an
    acknowledgement.
    """
    return os.environ.get("PRODUCT_AGENT_SLACK_BOT_TOKEN")


def will_reply(body: Mapping[str, Any]) -> bool:
    """Whether handling this request will attempt a reply.

    Both request classes this module serves reply: the slash command opens a
    modal through `views.open`, and a submission reports its outcome as a
    message. Anything else is treated as replying too, so a request class
    this module does not yet handle fails closed -- the same predicate shape
    `omni_agent`'s adapter uses, and for the same reason.
    """
    return True


register_slack_app(
    SLACK_APP_IDENTITY,
    SlackAppSpec(
        signing_secret_provider=_signing_secret,
        bot_token_provider=_bot_token,
        will_reply=will_reply,
    ),
)


# --------------------------------------------------------------------------
# The modal
# --------------------------------------------------------------------------


def _plain_text_input_block(
    *, field: str, label: str, optional: bool = False
) -> dict[str, Any]:
    return {
        "type": "input",
        "block_id": field,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": {"type": "plain_text_input", "action_id": field},
    }


def build_modal_view() -> dict[str, Any]:
    """The modal's contract.

    Carries no playbook-version field, and that is a requirement rather than
    an omission: the playbook is live — every launch starts against the
    current served set and records its version only as an audit stamp — so
    asking for a version invites input nothing could act on.
    """
    return {
        "type": "modal",
        "callback_id": CALLBACK_ID,
        "title": {"type": "plain_text", "text": "Start a launch"},
        "submit": {"type": "plain_text", "text": "Start"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            _plain_text_input_block(field=SKU_FIELD, label="SKU"),
            _plain_text_input_block(field=NAME_FIELD, label="Product name"),
            _plain_text_input_block(
                field=ASIN_FIELD, label="ASIN (optional)", optional=True
            ),
            {
                "type": "input",
                "block_id": LAUNCH_DATE_FIELD,
                "optional": True,
                "label": {"type": "plain_text", "text": "Launch date (optional)"},
                "element": {
                    "type": "datepicker",
                    "action_id": LAUNCH_DATE_FIELD,
                    "placeholder": {"type": "plain_text", "text": "No date yet"},
                },
            },
            {
                "type": "input",
                "block_id": MARKETPLACE_FIELD,
                "label": {"type": "plain_text", "text": "Marketplace"},
                "element": {
                    "type": "static_select",
                    "action_id": MARKETPLACE_FIELD,
                    "initial_option": _marketplace_option(),
                    "options": [_marketplace_option()],
                },
            },
        ],
    }


def _marketplace_option() -> dict[str, Any]:
    return {
        "text": {"type": "plain_text", "text": AMAZON_US_LABEL},
        "value": AMAZON_US_MARKETPLACE_ID,
    }


# --------------------------------------------------------------------------
# Reading and validating the submitted view
# --------------------------------------------------------------------------


def _field_state(view: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    values = view.get("state", {}).get("values", {})
    block = values.get(field) or {}
    element = block.get(field) or {}
    return element if isinstance(element, Mapping) else {}


def _text_value(view: Mapping[str, Any], field: str) -> str | None:
    raw = _field_state(view, field).get("value")
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def _selected_date(view: Mapping[str, Any]) -> str | None:
    raw = _field_state(view, LAUNCH_DATE_FIELD).get("selected_date")
    return raw if isinstance(raw, str) and raw else None


def _selected_marketplace(view: Mapping[str, Any]) -> str:
    option = _field_state(view, MARKETPLACE_FIELD).get("selected_option") or {}
    value = option.get("value") if isinstance(option, Mapping) else None
    # Preselected and single-option, so an absent selection is the
    # preselection rather than a rejection.
    return value if isinstance(value, str) and value else AMAZON_US_MARKETPLACE_ID


class _Submission:
    """The field values a submission carried, already parsed."""

    def __init__(
        self,
        *,
        sku: Sku,
        name: str,
        asin: Asin | None,
        marketplace_id: MarketplaceId,
        launch_date: date | None,
    ) -> None:
        self.sku = sku
        self.name = name
        self.asin = asin
        self.marketplace_id = marketplace_id
        self.launch_date = launch_date


def _read_submission(
    view: Mapping[str, Any],
) -> tuple[_Submission | None, dict[str, str]]:
    """Parses a submitted view into field values, or into per-field errors.

    Everything checkable before acknowledgement is checked here, keyed by
    block id so Bolt can attach each message to the offending field and
    leave the modal open. A rejection only the database can establish -- a
    duplicate SKU -- is deliberately *not* checked here: it belongs to the
    transaction, and arrives after the modal has closed.
    """
    errors: dict[str, str] = {}

    raw_sku = _text_value(view, SKU_FIELD)
    raw_name = _text_value(view, NAME_FIELD)
    raw_asin = _text_value(view, ASIN_FIELD)
    raw_date = _selected_date(view)

    sku: Sku | None = None
    if raw_sku is None:
        errors[SKU_FIELD] = "A SKU is required."
    else:
        try:
            sku = Sku(raw_sku)
        except ValueError as exc:
            errors[SKU_FIELD] = str(exc)

    if raw_name is None:
        errors[NAME_FIELD] = "A product name is required."

    asin: Asin | None = None
    if raw_asin is not None:
        try:
            asin = Asin(raw_asin)
        except ValueError as exc:
            errors[ASIN_FIELD] = str(exc)

    launch_date: date | None = None
    if raw_date is not None:
        try:
            launch_date = date.fromisoformat(raw_date)
        except ValueError:
            errors[LAUNCH_DATE_FIELD] = f"{raw_date!r} is not a valid date."

    marketplace_id: MarketplaceId | None = None
    try:
        marketplace_id = MarketplaceId(_selected_marketplace(view))
    except ValueError as exc:
        errors[MARKETPLACE_FIELD] = str(exc)

    if errors or sku is None or raw_name is None or marketplace_id is None:
        return None, errors

    return (
        _Submission(
            sku=sku,
            name=raw_name,
            asin=asin,
            marketplace_id=marketplace_id,
            launch_date=launch_date,
        ),
        {},
    )


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


async def _register_and_start(submission: _Submission) -> None:
    """Registers the product and starts its launch, in one transaction.

    Both writes share one `transaction()` scope, so the catalog row and
    the launch row persist together or not at all. That provider exists
    because the repositories commit their own writes: inside it each such
    commit releases a SAVEPOINT rather than ending the transaction, so a
    rejection anywhere in the pair leaves nothing behind and the SKU stays
    free for resubmission. The launch store's own rejections behave
    correctly there too -- the not-yet-committed product row is visible to
    the launch write.
    """
    registrar = register_catalog_product
    if registrar is None:
        raise RuntimeError(
            "no catalog registrar is installed on "
            f"{__name__}.register_catalog_product; `main.py` injects it after "
            "building the application (design.md Decision 2, tasks.md 2.3)"
        )

    async with transaction() as db_session:
        # Read before the registrar runs, deliberately. A playbook that
        # cannot hold a launch refuses here, and reading it first means the
        # refusal happens before anything is written rather than being
        # rolled back after — so "nothing was saved" is true because
        # nothing was attempted, which is the stronger claim and the one a
        # reader of this function can check.
        #
        # The live served playbook: the launch records its version
        # identifier as an audit stamp, and every later read serves the
        # current set regardless of the stamp.
        playbook = await PlaybookRepository(db_session).get("live")
        product_id = await registrar(
            db_session,
            sku=submission.sku,
            marketplace_id=submission.marketplace_id,
            name=submission.name,
            asin=submission.asin,
        )
        await start_launch(
            LaunchRepository(db_session),
            playbook,
            product_id=product_id,
            launch_date=submission.launch_date,
            journal=LaunchJournalRepository(db_session),
        )


def _confirmation_text(submission: _Submission) -> str:
    when = (
        f"launching {submission.launch_date.isoformat()}"
        if submission.launch_date is not None
        else "no launch date yet"
    )
    return (
        f"Started the launch for *{submission.name}* ({submission.sku.value}) — "
        f"{when}. Its ClickUp tasks appear {CLICKUP_SYNC_CADENCE_DESCRIPTION}."
    )


def _failure_text(submission: _Submission, error: Exception) -> str:
    if isinstance(error, DuplicateSkuError):
        detail = f"the SKU {submission.sku.value} is already registered"
    elif isinstance(error, PlaybookNotReadyError):
        # Named rather than left to `str(error)`: what the submitter needs
        # is the work that would make the start succeed, and no field they
        # filled in caused this.
        detail = (
            "the playbook cannot yet hold a launch — no active blocking "
            "step holds "
            + (
                f"gates {', '.join(error.unheld_gates)}"
                if len(error.unheld_gates) > 1
                else f"gate {error.unheld_gates[0]}"
            )
        )
    else:
        detail = str(error) or error.__class__.__name__
    return (
        f"Could not start the launch for *{submission.name}* "
        f"({submission.sku.value}): {detail}. Nothing was saved."
    )


# --------------------------------------------------------------------------
# Listeners
# --------------------------------------------------------------------------


@functools.lru_cache
def _get_handler() -> AsyncSlackRequestHandler:
    """Builds the Bolt app and its FastAPI handler once, on first request.

    Lazy because the PR-validation gate imports `commerce_ops.main` and runs
    its lifespan in a fresh interpreter with the Slack secrets absent, and
    requires both to succeed.
    """
    app = get_slack_app(SLACK_APP_IDENTITY)

    @app.command(SLASH_COMMAND)
    async def open_start_launch_modal(
        ack: Callable[..., Awaitable[None]],
        body: dict[str, Any],
        client: Any,
    ) -> None:
        await ack()
        await client.views_open(trigger_id=body["trigger_id"], view=build_modal_view())

    @app.view(CALLBACK_ID)
    async def handle_start_launch_submission(
        ack: Callable[..., Awaitable[None]],
        body: dict[str, Any],
        client: Any,
    ) -> None:
        view = body.get("view") or {}
        submission, errors = _read_submission(view)

        if submission is None:
            # Before the acknowledgement, so the modal stays open with each
            # message attached to the field that earned it.
            await ack(response_action="errors", errors=errors)
            return

        # Acknowledged before any persistence is attempted: the requirement
        # is that the ack does not wait on the transaction, however long it
        # takes. Everything after this point reaches the user as a message.
        await ack()

        submitter = (body.get("user") or {}).get("id")

        try:
            await _register_and_start(submission)
        except Exception as error:
            logger.exception("starting a launch from Slack failed")
            await _post(client, submitter, _failure_text(submission, error))
            return

        await _post(client, submitter, _confirmation_text(submission))

    return AsyncSlackRequestHandler(app)


async def _post(client: Any, channel: str | None, text: str) -> None:
    """Delivers an outcome to the submitting user.

    A delivery failure is logged and swallowed on purpose: after a
    successful commit, "delivery failure is not grounds to unwind persisted
    state". Raising here would also reach Bolt's error handler long after
    the acknowledgement, changing nothing the user can see.
    """
    if not channel:
        logger.error("no submitting user on the payload; outcome undelivered: %s", text)
        return
    try:
        await client.chat_postMessage(channel=channel, text=text)
    except Exception:
        logger.exception("could not deliver the launch-entry outcome to %s", channel)


def reset_handler_cache() -> None:
    """Drops the cached Bolt handler.

    A test that changes the environment needs the next request to build a
    fresh app rather than reuse one built from an earlier one.
    """
    _get_handler.cache_clear()


@router.post("/product_agent/slack/events")
async def product_agent_slack_events(request: Request) -> Response:
    try:
        # Read per request, before the cached factory is consulted: the
        # requirement is phrased per request, and a per-construction read
        # would leave a warm process verifying against a secret the
        # environment no longer has.
        secret = os.environ["PRODUCT_AGENT_SLACK_SIGNING_SECRET"]
    except KeyError:
        secret = ""

    if not secret:
        # Absent or empty: nothing about this request can be verified either
        # way, so fail closed. Empty is handled here rather than left to
        # Bolt, whose `SignatureVerifier` raises `ValueError` for an empty
        # secret and turns into a 500 -- the outcome this capability's
        # credential requirement forbids as explicitly as an acknowledgement.
        return Response(
            status_code=401,
            media_type="application/json",
            content=json.dumps({"error": "slack signing secret is not configured"}),
        )

    return await _get_handler().handle(request)
