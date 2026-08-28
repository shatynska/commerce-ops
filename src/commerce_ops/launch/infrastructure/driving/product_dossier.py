"""Driving adapter: the product surfaces (`product-dossier`).

Two server-rendered pages, the shape `playbook_admin` established and
`roster_admin` and `launch_admin` followed: an index of every product the
caller may see, and, for one product, its identity as the catalog holds it
together with the record of what automated steps produced about it.

**Addressed by product, not by launch.** A launch is a temporary state
over a continuously observed product; a page that appeared when a launch
began and vanished when it ended would make a permanent record
conditional on a temporary one. So the dossier turns on the product, and
renders for one that never launched and for one that has graduated alike.

**Read-only, by requirement rather than by omission.** Accepting and
rejecting a pending result keep the Slack path `launch-step-automation`
specifies. Its once-only settlement, its roster checks and its refusals
are all written against a decision arriving there; offering a second door
would put those guarantees behind something nothing has specified.

Two things the record does that are easy to get wrong:

- A `voided` result is labelled **withdrawn**, never rejected, and shows
  no decider — because none is recorded. Voiding refuses a decision
  rather than making one, and presenting it as a rejection attributes to
  the person who tried to decide a judgement they never made.
- The record is labelled as the results retained **for a decision**, not
  as everything produced. Only a terminal proposal on a confirmable step
  reaches the store; a page implying otherwise would be wrong invisibly,
  and totally so for a product whose automated steps need no confirmation.

The decider is rendered as recorded and never re-resolved against the
roster, which is why this module has no roster seam at all.

`catalog`, `results`, `roster` and `admin_sessions` are injected by
`main.py` after the app is built, the pattern every admin surface uses;
absent injection refuses every request, which is the failing-closed
direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import resolve_scope, verify_admin_session
from commerce_ops.catalog.application import (
    get_product_by_id as _read_product,
)
from commerce_ops.catalog.application import (
    list_products as _read_products,
)
from commerce_ops.launch.application import (
    read_retained_results as _read_retained,
)
from commerce_ops.launch.domain.launch_playbook import StepStatus
from commerce_ops.launch.infrastructure.driven.automated_results import (
    AutomatedResultRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    Retired,
    SteadyState,
)
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driving.admin_assets import TEMPLATES_DIR

__all__ = [
    "PAGE_PATH",
    "admin_sessions",
    "catalog",
    "results",
    "roster",
    "router",
    "steps",
]

PAGE_PATH: Final = "/admin/products"

SESSION_COOKIE: Final = "admin_session"

#: The stored state of a retained result, as the page marks it. Four
#: values, because the store admits four; `voided` becomes *withdrawn*
#: deliberately — the marker names what the page says, and the store's
#: vocabulary is not the page's.
_STATE_MARKERS: Final = {
    "pending": "result-pending",
    "accepted": "result-accepted",
    "rejected": "result-rejected",
    "voided": "result-withdrawn",
}

_STATE_LABELS: Final = {
    "result-pending": "Awaiting a decision",
    "result-accepted": "Accepted",
    "result-rejected": "Rejected",
    "result-withdrawn": "Withdrawn",
}

# Own templates first, then the shared ones: the admin header is one
# partial every surface includes, so no module owns a copy of it.
_TEMPLATES: Final = Environment(
    loader=ChoiceLoader(
        [
            FileSystemLoader(Path(__file__).parent / "templates"),
            FileSystemLoader(TEMPLATES_DIR),
        ]
    ),
    autoescape=select_autoescape(default=True, default_for_string=True),
)

router = APIRouter()


class _RequestScopedResults:
    """The production retained-result read: one session per operation,
    the shape every other admin surface's store uses.

    Read-only by construction — this page has nothing to write, so a
    write reaching this object would be a type error rather than a silent
    success.
    """

    async def for_product(self, product_id: ProductId) -> Any:
        async with session() as db:
            return await AutomatedResultRepository(db).for_product(product_id)


class _RequestScopedSteps:
    """The served step set, read once per request. Only `load` — names
    are all this page wants from the playbook."""

    async def load(self) -> Any:
        async with session() as db:
            return await PlaybookRepository(db).load()


results: Any = _RequestScopedResults()
steps: Any = _RequestScopedSteps()

# Injected by `main.py` after the app is built. `roster` and
# `admin_sessions` come from the access module, whose infrastructure this
# one may not import; `catalog` is here for the same reason — the
# `products-infrastructure-boundary` contract permits this module
# `catalog.application` and forbids it `catalog.infrastructure`, so only
# the composition root can build the store the reads run against.
roster: Any = None
catalog: Any = None
admin_sessions: Any = None


async def list_products(scope: Any) -> Any:
    """The catalog's product list, with the store already bound.

    A thin seam rather than a direct call so this module reads in its own
    terms — the page asks the catalog for products under a scope, and
    which store answers is composition's business, not the page's.
    """
    return await _read_products(catalog, scope=scope)


async def get_product_by_id(product_id: ProductId, scope: Any) -> Any:
    """One product, with the store already bound. See `list_products`."""
    return await _read_product(catalog, product_id, scope=scope)


async def read_retained_results(product_id: ProductId, scope: Any) -> Any:
    """What was retained for this product, with the store already bound.

    The use case applies the scope; passing it here is what makes that
    true of *this* caller rather than only of the use case.
    """
    return await _read_retained(results, product_id=product_id, scope=scope)


async def _require_admin(request: Request) -> str:
    """The one guard every route here rides. Refusal is the app's own 404
    — identical to an unregistered route, whatever actually failed."""
    session_id = request.cookies.get(SESSION_COOKIE)
    principal: str | None = None
    if session_id:
        principal = await verify_admin_session(
            roster,
            admin_sessions,
            session_id=session_id,
            now=datetime.now(UTC),
        )
    if principal is None:
        raise HTTPException(status_code=404)
    return principal


async def _scope_for(principal: str) -> Any:
    return await resolve_scope(roster, identity=principal)


# ---------------------------------------------------------------------------
# The read model: one frozen dataclass per rendered thing, so shaping is
# testable without a template and mypy can check what the template reads.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProductRow:
    """One product as the index renders it."""

    product_id: str
    sku: str
    name: str
    stage: str
    retired: bool
    dossier_path: str

    @property
    def group(self) -> int:
        """Which group the row sits in. Retired products are set apart
        and follow the rest, so this outranks the SKU sort — a single
        ascending sort across the whole page and the set-apart rule
        cannot both hold once a retired SKU sorts first."""
        return 1 if self.retired else 0


@dataclass(frozen=True, slots=True)
class Identity:
    """The product as the catalog holds it."""

    product_id: str
    sku: str
    name: str
    marketplace: str
    asin: str | None
    stage: str
    stage_entered_at: datetime | None
    stage_confirmed_by: str | None


@dataclass(frozen=True, slots=True)
class RecordEntry:
    """One retained result as the record renders it."""

    step_id: str
    step_name: str
    named: bool
    handler: str
    proposed_outcome: str
    result_text: str
    produced_at: datetime
    marker: str
    label: str
    decided_by: str | None
    decided_at: datetime | None


@dataclass(frozen=True, slots=True)
class Dossier:
    """One product's page."""

    identity: Identity
    entries: tuple[RecordEntry, ...]


def _stage_label(stage: Any) -> str:
    """How a lifecycle stage names itself on a page.

    Spelled out rather than taken from `repr`, so the wording is this
    module's and does not change when a domain class is renamed.
    """
    match stage:
        case Development():
            return "Development"
        case Launching(phase=phase):
            return f"Launching phase {phase}"
        case SteadyState(posture=posture):
            return f"Steady state — {getattr(posture, 'value', posture)}"
        case Retired():
            return "Retired"
        case _:
            return str(stage)


def _is_retired(stage: Any) -> bool:
    return isinstance(stage, Retired)


def _row_for(product: Any) -> ProductRow:
    identifier = str(product.id.value)
    return ProductRow(
        product_id=identifier,
        sku=str(getattr(product.sku, "value", product.sku)),
        name=product.name,
        stage=_stage_label(product.stage),
        retired=_is_retired(product.stage),
        dossier_path=f"{PAGE_PATH}/{identifier}",
    )


def _identity_for(product: Any) -> Identity:
    asin = getattr(product, "asin", None)
    return Identity(
        product_id=str(product.id.value),
        sku=str(getattr(product.sku, "value", product.sku)),
        name=product.name,
        marketplace=str(
            getattr(product.marketplace_id, "value", product.marketplace_id)
        ),
        asin=None if asin is None else str(getattr(asin, "value", asin)),
        stage=_stage_label(product.stage),
        stage_entered_at=getattr(product, "stage_entered_at", None),
        stage_confirmed_by=getattr(product, "stage_confirmed_by", None),
    )


async def _step_names() -> dict[str, str]:
    """The served step set's names, keyed by identifier.

    One read for the page rather than one per entry. A playbook that
    cannot be read at all yields nothing and every entry then renders by
    its step identifier — the record is this page's reason to exist, and
    an improvement on it that can fail the page is a worse page.
    """
    try:
        loaded = await steps.load()
    except Exception:  # noqa: BLE001 — an unreadable playbook names nothing
        return {}
    records = loaded[0] if isinstance(loaded, tuple) else loaded
    names: dict[str, str] = {}
    for record in records or ():
        definition = getattr(record, "definition", record)
        identifier = getattr(definition, "identifier", None)
        name = getattr(definition, "name", None)
        # Only `active` steps are *served*, so only they can name an entry.
        # A retired step is still authored and still loads, but a result
        # produced for one is exactly the case the fallback exists for --
        # naming it here would hide that the playbook no longer serves it.
        if identifier and name and _is_served(definition):
            names[str(identifier)] = str(name)
    return names


def _is_served(definition: Any) -> bool:
    status = getattr(definition, "status", None)
    return getattr(status, "value", status) == StepStatus.ACTIVE.value


def _entry_for(result: Any, names: dict[str, str]) -> RecordEntry:
    step_id = str(result.step_id)
    name = names.get(step_id)
    marker = _STATE_MARKERS.get(str(result.state), "result-pending")
    return RecordEntry(
        step_id=step_id,
        step_name=name or step_id,
        named=name is not None,
        handler=str(result.handler),
        proposed_outcome=str(result.proposed_outcome),
        result_text=str(result.result_text),
        produced_at=result.produced_at,
        marker=marker,
        label=_STATE_LABELS[marker],
        decided_by=result.decided_by,
        decided_at=result.decided_at,
    )


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------


@router.get(PAGE_PATH)
async def product_index(request: Request) -> HTMLResponse:
    """Every product the caller's scope permits, one row each."""
    principal = await _require_admin(request)
    scope = await _scope_for(principal)

    products = await list_products(scope)
    rows = sorted(
        (_row_for(product) for product in products or ()),
        key=lambda row: (row.group, row.sku),
    )

    template = _TEMPLATES.get_template("products.html")
    return HTMLResponse(template.render(page_path=PAGE_PATH, rows=rows))


@router.get(PAGE_PATH + "/{product_id}")
async def product_dossier(request: Request, product_id: str) -> HTMLResponse:
    """One product: what the catalog holds, and what was produced for it."""
    principal = await _require_admin(request)
    scope = await _scope_for(principal)

    try:
        identifier = ProductId(product_id)
    except ValueError as exc:
        # An identifier naming nothing the system knows -- a SKU included,
        # since this address accepts one canonical form. Refused in the
        # shape every other refusal here takes.
        raise HTTPException(status_code=404) from exc

    product = await get_product_by_id(identifier, scope)
    # `get_product_by_id` already collapses "no such product" and "outside
    # the caller's scope" into one absence, so nothing here distinguishes
    # them and nothing may: telling them apart would confirm the existence
    # of a product the caller may not see.
    if product is None:
        raise HTTPException(status_code=404)

    # Turns on the product, never on whether a launch exists: a product
    # that never launched renders, and only its record is empty.
    retained = await read_retained_results(identifier, scope)
    names = await _step_names()
    entries = tuple(_entry_for(result, names) for result in retained or ())

    template = _TEMPLATES.get_template("product.html")
    return HTMLResponse(
        template.render(
            page_path=PAGE_PATH,
            dossier=Dossier(identity=_identity_for(product), entries=entries),
        )
    )
