"""Driving adapter: the launch-tracking pages (`launch-admin`).

Server-rendered HTML end to end, the shape `playbook_admin` established
and `roster_admin` followed, so the admin surfaces read the same way and
none of them needs JavaScript to work.

**Read-only, by requirement rather than by omission.** Nothing here
records an outcome, approves a gate, decides an automated result or moves
a launch date; those keep the Slack paths that already serve them. The
guarantee is what makes this surface safe to open on a live launch.

Two things this module deliberately does not do, both of them the
arrangement `launch-instance`'s governing principle exists to protect:

- It never reads the playbook. Every fact it renders about a step — the
  name, the gate, the discipline, whether it blocks, its due period and
  whether it is overdue — travels on the launch report, and so does the
  gate sequence itself.
- It never derives a judgement the launch context already made. The
  overdue mark is read, never recomputed: whether a step is overdue
  depends on the terminal outcomes its hazard permits, so a page
  computing it from a due period and an outcome would mark a
  `prohibited-tactic` step overdue for ever.

Between the use cases and the templates sits a small set of frozen
dataclasses — one per rendered thing. Shaping is separable from markup on
purpose (`add-launch-tracking-pages`' design.md, Decision 2): the
surface this one is modelled on grew to 1400 lines because the two were
not, and its nearest thing to a view model returns `dict[str, Any]`,
which mypy cannot check a template against.

`launches`, `playbooks`, `roster`, `catalog` and `admin_sessions` are
injected by `main.py` after the app is built, the pattern both existing
admin surfaces use; absent injection refuses every request, which is the
failing-closed direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from commerce_ops.access.application import (
    list_people,
    resolve_scope,
    verify_admin_session,
)
from commerce_ops.catalog.application import (
    get_product_by_id as _read_product,
)
from commerce_ops.catalog.application import (
    list_products as _read_products,
)
from commerce_ops.launch.application import read_launch, read_launches
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driving.admin_assets import TEMPLATES_DIR

__all__ = [
    "PAGE_PATH",
    "admin_sessions",
    "catalog",
    "launches",
    "playbooks",
    "read_journal",
    "roster",
    "router",
]

PAGE_PATH: Final = "/admin/launches"

SESSION_COOKIE: Final = "admin_session"

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


class _RequestScopedLaunches:
    """The production `LaunchStore` read: each operation on its own
    session, the shape `playbook_admin`'s step store already uses.

    Read-only by construction — the page has no `save`, because it has
    nothing to save. A write reaching this object would be a type error
    rather than a silent success.
    """

    async def get_by_product_id(self, product_id: ProductId) -> Any:
        async with session() as db:
            return await LaunchRepository(db).get_by_product_id(product_id)

    async def list_all(self) -> Any:
        async with session() as db:
            return await LaunchRepository(db).list_all()


launches: Any = _RequestScopedLaunches()

# `playbooks` is the one collaborator with no request-scoped shim, and the
# reason is the port's own shape: `Playbooks.get` is synchronous while a
# Postgres read is not, so the playbook is loaded once per request and
# handed over wrapped -- the arrangement `ServedPlaybooks` exists for, and
# what keeps "read per pass, never cached at import" true here too. Left
# `None` so production loads it; a test installs its own and that install
# is what `_playbook_port` honours.
playbooks: Any = None

# Injected by `main.py` after the app is built, the pattern both other
# admin surfaces use. `roster` and `admin_sessions` come from the access
# module, whose infrastructure this one may not import; `catalog` is here
# for the same reason and not for want of a shim -- the
# `products-infrastructure-boundary` contract permits this module
# `catalog.application` and forbids it `catalog.infrastructure`, so only
# the composition root can build the store the reads run against.
roster: Any = None
catalog: Any = None
# The journal *read*, injected by `main.py` after the app is built: a
# callable taking the product and the caller's scope and answering that
# launch's entries. Absent injection the page renders the empty-journal
# statement, which is also what a launch predating the journal shows for
# ever -- and what the read itself answers for a scope that does not
# permit the product, deliberately indistinguishable from both.
read_journal: Any = None
admin_sessions: Any = None


def today() -> date:
    """The day the page renders on.

    Its own function so that "evaluated as of the date the page is
    rendered" has one place to be true, rather than a `date.today()` at
    each read site that a later edit could leave behind.
    """
    return datetime.now(UTC).date()


async def _require_admin(request: Request) -> str:
    """The one guard every route here rides. Refusal is the app's own
    404 — identical to an unregistered route, whatever actually failed."""
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


# ---------------------------------------------------------------------------
# The read model: one frozen dataclass per rendered thing.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LaunchRow:
    """One launch as the list renders it."""

    product_id: str
    label: str
    resolved: bool
    current_gate: str
    launch_date: date | None
    at_risk: bool
    awaiting_confirmation: bool
    in_play: bool
    retired: bool
    detail_path: str
    # The most recently recorded completion, and when it was recorded.
    # Defaulted so that a row can still be constructed without one -- a
    # launch on which nothing has been completed yet is the ordinary case
    # at the first gate, not a degenerate one.
    last_completed: str | None = None
    last_completed_at: datetime | None = None
    # The product's SKU, split out from `label` (which now holds only the
    # product's name) so the list can render the two as separate columns
    # rather than one combined string. `None` for the same reason `label`
    # falls back to the raw identifier -- a product the catalog cannot
    # resolve has no SKU to show either.
    sku: str | None = None

    @property
    def band(self) -> int:
        """Which attention band the row sits in — at-risk first, then
        awaiting-confirmation, then the rest. A launch matching both
        appears once, in the first, which is what makes this a band index
        rather than two flags the template has to reconcile."""
        if self.at_risk:
            return 0
        if self.awaiting_confirmation:
            return 1
        return 2


@dataclass(frozen=True, slots=True)
class StepLine:
    """One step as the detail page renders it."""

    step_id: str
    name: str
    discipline: str
    blocking: bool
    overdue: bool
    outcome: str | None
    recorded_by: str | None
    recorded_at: datetime | None
    source: str | None
    evidence: str | None
    due_from: date | None
    due_to: date | None

    @property
    def recorded(self) -> bool:
        """Whether anything has been recorded at all. Distinct from an
        outcome of "not started": nothing recorded carries no provenance,
        and something recorded as not-started names who said so."""
        return self.outcome is not None


@dataclass(frozen=True, slots=True)
class GateGroup:
    """One gate and the steps that belong to it, in the authored order the
    report hands them over in."""

    identifier: str
    current: bool
    steps: tuple[StepLine, ...]


@dataclass(frozen=True, slots=True)
class JournalLine:
    """One journal entry as the detail page renders it.

    `who` is the entry's `actor`, resolved against the roster to a
    display name where it names a known person (by roster identifier or
    by ClickUp user id — `_actor_names`), and left as the raw value
    otherwise.

    `subject` is the page's own narrowing of `JournalEntry.subject` to
    what its column is named for: a gate or a step (`_gate_or_step`).
    `metric-attested`'s subject is a metric condition, neither a gate
    nor a step, so it carries `None` here -- that condition text renders
    as part of `detail` instead.

    `detail` is this page's own composed phrase, built from
    `JournalEntry`'s per-kind raw fields (`outcome`, `decision`,
    `gate_id`, ...) — the page tried a column per fact and then two
    columns (`detail`/`note`) and settled on one short readable phrase,
    the same shape the page's original composed `what` sentence had,
    minus the subject clause for every kind except `metric-attested`
    (`subject` already has its own column for the others, so repeating
    it here would duplicate that column). Composition the page performs,
    the same way it already composes `who`, not a fact `journal.py`
    stores or exposes as its own field (`_journal_detail`)."""

    when: Any
    label: str
    category: str
    subject: str | None
    source: str | None
    who: str | None
    detail: str | None


@dataclass(frozen=True, slots=True)
class LaunchDetail:
    """One launch as the detail page renders it."""

    product_id: str
    label: str
    resolved: bool
    current_gate: str
    launch_date: date | None
    gates: tuple[GateGroup, ...]
    served_any: bool


@dataclass(frozen=True, slots=True)
class JournalPage:
    """One launch's journal, as its own page renders it."""

    product_id: str
    label: str
    entries: tuple[JournalLine, ...]
    available: bool


# ---------------------------------------------------------------------------
# Shaping — separable from rendering, and tested without a template.
# ---------------------------------------------------------------------------


def _label_for(product: Any, product_id: str) -> tuple[str, bool]:
    """A product's human label, and whether the catalog resolved it.

    Name only, not the SKU-prefixed form this used to combine — the
    detail and journal pages render this as the page's own title now
    (`add-admin-breadcrumb-navigation`'s breadcrumb-current segment), and
    a title carrying a code beside the name is the same duplication the
    list's own `sku`/`label` split moved away from.

    A launch whose product does not resolve is still rendered, named by
    its raw identifier. Losing a launch to a failed lookup is the silent
    failure a tracking surface exists to prevent, and during a wholesale
    catalog outage it would lose every one of them.
    """
    if product is None:
        return product_id, False
    name = getattr(product, "name", None)
    return str(name or product_id), True


def _row_identity(product: Any, product_id: str) -> tuple[str | None, str, bool]:
    """A launch row's own SKU and name, split apart -- unlike `_label_for`
    above, which the detail and journal pages still use for their single
    combined label. A launch whose product does not resolve shows no SKU
    and is named by its raw identifier, the same fallback `_label_for`
    uses, for the same reason.
    """
    if product is None:
        return None, product_id, False
    sku = getattr(getattr(product, "sku", None), "value", None)
    name = getattr(product, "name", None)
    return (str(sku) if sku else None), str(name or product_id), True


def _last_completed(report: Any) -> tuple[str | None, datetime | None]:
    """The step whose completion was recorded most recently, and when.

    "Last" is by RECORDING time, not by the playbook's order: the question
    the column answers is what most recently happened on this launch. The
    two disagree when a completion is backfilled -- a step finished weeks
    ago but recorded today leads, though later steps are already done --
    and that is the reading chosen, because a list read for "where does
    this stand" is read for recent activity.

    Only `Satisfied` counts. The other outcomes are recorded with the same
    provenance, so taking the latest recording of any outcome would let a
    step recorded as blocked read as the launch's latest completion.

    Ties are broken by the report's own order, which `launch-playbook`
    obliges to be the authored one, so two completions recorded in the
    same instant do not order themselves by chance.
    """
    best_name: str | None = None
    best_when: datetime | None = None
    for entry in getattr(report, "steps", ()):
        progress = getattr(entry, "progress", None)
        if progress is None:
            continue
        recorded = progress.outcome
        name = (
            recorded.__name__ if isinstance(recorded, type) else type(recorded).__name__
        )
        if name != "Satisfied":
            continue
        when = getattr(getattr(progress, "provenance", None), "when", None)
        if when is None:
            continue
        if best_when is None or when >= best_when:
            best_name, best_when = entry.name, when
    return best_name, best_when


def _stage_of(product: Any) -> str:
    stage = getattr(product, "stage", None)
    return type(stage).__name__.lower() if stage is not None else ""


def _rows_for(
    reports: tuple[Any, ...], products: dict[str, Any]
) -> tuple[LaunchRow, ...]:
    rows: list[LaunchRow] = []
    for report in reports:
        product_id = str(report.product_id.value)
        product = products.get(product_id)
        sku, label, resolved = _row_identity(product, product_id)
        stage = _stage_of(product)
        retired = stage.startswith("retired")
        last_name, last_when = _last_completed(report)
        # An unresolved product is treated as in play: the filter fails
        # toward showing, never toward silence, which is `briefing`'s rule
        # for the same judgement on the same data.
        in_play = not resolved or not (stage.startswith("steadystate") or retired)
        rows.append(
            LaunchRow(
                product_id=product_id,
                label=label,
                resolved=resolved,
                current_gate=report.current_gate,
                launch_date=report.launch_date,
                at_risk=report.at_risk is not None,
                awaiting_confirmation=report.awaiting_confirmation,
                in_play=in_play,
                retired=retired,
                detail_path=f"{PAGE_PATH}/{product_id}",
                last_completed=last_name,
                last_completed_at=last_when,
                sku=sku,
            )
        )
    return tuple(rows)


def _sort_key(row: LaunchRow) -> tuple[int, int, str, str]:
    """Band, then launch date ascending with undated last, then product
    identifier. Total by construction — at most one launch record exists
    per product — so ordering never depends on how the enumeration
    happened to arrive."""
    undated = 1 if row.launch_date is None else 0
    stamp = row.launch_date.isoformat() if row.launch_date else ""
    return (row.band, undated, stamp, row.product_id)


def _finished_key(row: LaunchRow) -> tuple[int, str, str]:
    """Most recent first, undated last, ties by product identifier. The
    reverse direction from the bands, deliberately: what is finished is
    read newest-first."""
    undated = 1 if row.launch_date is None else 0
    stamp = row.launch_date.isoformat() if row.launch_date else ""
    inverted = "".join(chr(0x10FFFD - ord(c)) for c in stamp)
    return (undated, inverted, row.product_id)


def _steps_for(report: Any) -> tuple[StepLine, ...]:
    lines: list[StepLine] = []
    for entry in report.steps:
        progress = entry.progress
        outcome = None
        recorded_by = recorded_at = source = evidence = None
        if progress is not None:
            recorded = progress.outcome
            outcome = (
                recorded.__name__
                if isinstance(recorded, type)
                else type(recorded).__name__
            )
            provenance = progress.provenance
            recorded_by = provenance.who
            recorded_at = provenance.when
            source = provenance.source
            evidence = provenance.evidence
        period = entry.due_period
        lines.append(
            StepLine(
                step_id=entry.step_id,
                name=entry.name,
                discipline=entry.discipline.value,
                blocking=entry.blocking,
                overdue=entry.overdue,
                outcome=outcome,
                recorded_by=recorded_by,
                recorded_at=recorded_at,
                source=source,
                evidence=evidence,
                due_from=getattr(period, "start", None) if period else None,
                due_to=getattr(period, "end", None) if period else None,
            )
        )
    return tuple(lines)


def _gates_for(report: Any) -> tuple[GateGroup, ...]:
    """Steps grouped under their gate, in the gate sequence's order, each
    gate's steps left in the order the report handed them over — which is
    the served playbook's authored order, and which `launch-playbook`
    obliges every consumer that lists a gate's steps to follow."""
    lines = _steps_for(report)
    return tuple(
        GateGroup(
            identifier=gate,
            current=gate == report.current_gate,
            steps=tuple(line for line in lines if _gate_of(report, line) == gate),
        )
        for gate in report.gate_sequence
    )


def _gate_of(report: Any, line: StepLine) -> str:
    for entry in report.steps:
        if entry.step_id == line.step_id:
            return str(entry.gate)
    return ""


async def _actor_names(roster: Any) -> dict[str, str]:
    """Every identifier a journal entry's `actor` might carry, mapped to
    the person's display name: a Slack-sourced entry's `actor` is a
    roster identifier (`Person.identifier`), a ClickUp-sourced one is
    that person's `clickup_user_id` (`clickup_webhook`'s `_status_change`,
    `raw-out-the-journal-columns`). Both map into one dict, since the two
    identifier spaces do not collide in practice.

    Empty where the roster is unavailable or unreadable, the same
    fail-quiet fallback `_label_for` uses for an unresolved product: an
    actor then renders by its raw value rather than the page failing.
    """
    if roster is None:
        return {}
    try:
        people = await list_people(roster=roster)
    except Exception:  # noqa: BLE001 — an unreadable roster still renders raw ids
        return {}
    names: dict[str, str] = {}
    for person in people:
        names[person.identifier] = person.display_name
        if person.clickup_user_id:
            names[person.clickup_user_id] = person.display_name
    return names


def _who(actor: str | None, actor_names: dict[str, str]) -> str | None:
    if actor is None:
        return None
    return actor_names.get(actor, actor)


def _gate_or_step(entry: Any) -> str | None:
    """`subject` where it names a gate or a step -- every kind except
    `metric-attested`, whose subject is the metric condition being
    attested, not a gate or a step. That condition text is folded into
    `_journal_detail` instead, so this column stays true to its name.

    `gate_id` is unique to `metric-attested` among this entry's fields,
    so its presence is what distinguishes the one kind this column
    excludes."""
    if entry.gate_id is not None:
        return None
    subject = entry.subject
    return None if subject is None else str(subject)


def _journal_detail(entry: Any) -> str | None:
    """A short, readable phrase describing what this entry recorded,
    composed from its per-kind facts.

    The page's third attempt at rendering these facts: a column per
    fact, then two columns (a primary fact plus an explanatory one), and
    now one composed phrase -- the same shape the page's original
    composed `what` sentence had, minus the subject clause, since
    `subject` already has its own column (the gate/step column,
    `_gate_or_step`) and repeating it here would duplicate that column.
    The one exception is `metric-attested`, whose subject is not a gate
    or a step and so has no column of its own -- its condition text is
    composed in here instead.

    Dispatches on which raw field is populated rather than on `kind`,
    since each field belongs to exactly one or two kinds already — the
    order matters only where two kinds share a field (`decision` and
    `posture`: an approving `gate-approval-recorded` carries both, and
    `decision` takes the lead clause, folding posture in alongside it,
    so a graduating approval's posture still has somewhere to go)."""
    if entry.playbook_version is not None:
        return f"started against playbook version {entry.playbook_version}"
    if entry.outcome is not None:
        recorded = f"recorded {entry.outcome}"
        extra = entry.reason or entry.evidence
        return f"{recorded} — {extra}" if extra else recorded
    if entry.decision is not None:
        decided = f"{entry.decision} decision recorded"
        return f"{decided}, posture '{entry.posture}'" if entry.posture else decided
    if entry.gate_id is not None:
        attested = (
            f"the condition '{entry.subject}' attested on the {entry.gate_id} gate"
        )
        return f"{attested} — {entry.evidence}" if entry.evidence else attested
    if entry.standing_at is not None:
        return f"opened; the launch now stands at {entry.standing_at}"
    if entry.previous_date is not None or entry.new_date is not None:
        if entry.previous_date is None:
            return f"set to {entry.new_date}"
        return f"moved from {entry.previous_date} to {entry.new_date}"
    if entry.unsatisfied:
        named = ", ".join(str(item) for item in entry.unsatisfied)
        return f"refused, waiting on: {named}"
    if entry.posture is not None:
        return f"graduated, steady-state posture '{entry.posture}'"
    return None


def _journal_lines(
    entries: Any, actor_names: dict[str, str]
) -> tuple[JournalLine, ...]:
    """The journal as the page renders it, in the order the read gave it.

    R5 requires the journal to render newest first, and puts that on the
    render rather than on the read: the page sorts by the moment each
    entry names instead of trusting the order it was handed. The store's
    read already answers that way, so this is normally a no-op -- but the
    obligation is the page's, and a page that only looks right because
    its collaborator happened to be ordered is not meeting it.

    Composes `who`, `subject` (`_gate_or_step`) and `detail`; every other
    field is carried across unchanged, which is what R5 requires each
    entry to name.
    """
    lines = [
        JournalLine(
            when=entry.when,
            label=entry.label,
            category=entry.category,
            subject=_gate_or_step(entry),
            source=entry.source,
            who=_who(entry.actor, actor_names),
            detail=_journal_detail(entry),
        )
        for entry in entries or ()
    ]
    lines.sort(key=lambda line: line.when, reverse=True)
    return tuple(lines)


def _detail_for(report: Any, product: Any) -> LaunchDetail:
    product_id = str(report.product_id.value)
    label, resolved = _label_for(product, product_id)
    gates = _gates_for(report)
    return LaunchDetail(
        product_id=product_id,
        label=label,
        resolved=resolved,
        current_gate=report.current_gate,
        launch_date=report.launch_date,
        gates=gates,
        served_any=any(group.steps for group in gates),
    )


def _journal_page_for(
    report: Any, product: Any, journal: tuple[JournalLine, ...]
) -> JournalPage:
    product_id = str(report.product_id.value)
    label, _resolved = _label_for(product, product_id)
    return JournalPage(
        product_id=product_id,
        label=label,
        entries=journal,
        # Whether the store answered, not whether it answered anything. An
        # empty journal is a fact about the launch; an absent store is a
        # fact about the deployment, and the page must not present the
        # second as the first.
        available=read_journal is not None,
    )


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------


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


async def _playbook_port() -> Any:
    """The `Playbooks` port for one request: whatever is installed, else
    the served playbook loaded now and wrapped."""
    if playbooks is not None:
        return playbooks
    async with session() as db:
        return ServedPlaybooks(await PlaybookRepository(db).get("live"))


async def _scope_for(principal: str) -> Any:
    return await resolve_scope(roster, identity=principal)


async def _journal_for(product_id: ProductId, scope: Any) -> tuple[JournalLine, ...]:
    """The launch's journal, or nothing where the read is not wired.

    `read_journal` is the read itself, bound to its store by the
    composition root — not the store. The page asks for one launch's
    entries under a scope and does not know what answers, the same shape
    `list_products` and `get_product_by_id` take here.

    **A failure is not swallowed.** The empty-journal statement this page
    renders is a claim about the launch — that nothing is recorded — and
    a read that raised has established no such thing. Turning an
    unreadable journal into that sentence would put a false statement on
    the page and hide the fault behind it, which is the substitution
    `launch-step-automation` refuses elsewhere for the same reason.
    """
    if read_journal is None:
        return ()
    entries = await read_journal(product_id=product_id, scope=scope)
    return _journal_lines(entries, await _actor_names(roster))


async def _products_by_id(scope: Any) -> tuple[dict[str, Any], bool]:
    """Every product the scope permits, keyed by identifier — one read for
    the page rather than one per row.

    A read that fails entirely yields nothing and says so, and the page
    then renders every row by its raw identifier. Failing the page instead
    would answer "where do we stand" with an error at exactly the moment
    someone is asking.
    """
    try:
        products = await list_products(scope)
    except Exception:  # noqa: BLE001 — any failure of this read renders raw ids
        return {}, False
    return {str(product.id.value): product for product in products}, True


def _href(params: dict[str, str]) -> str:
    """The list's own path under a set of query parameters."""
    query = urlencode(params)
    return f"{PAGE_PATH}?{query}" if query else PAGE_PATH


@router.get(PAGE_PATH)
async def launch_list(request: Request) -> HTMLResponse:
    principal = await _require_admin(request)
    scope = await _scope_for(principal)
    as_of = today()
    reports = await read_launches(
        launches, await _playbook_port(), as_of=as_of, scope=scope
    )
    products, _ = await _products_by_id(scope)
    rows = _rows_for(reports, products)

    gate = (request.query_params.get("gate") or "").strip()
    attention = (request.query_params.get("attention") or "").strip()
    reveal = (request.query_params.get("finished") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    narrowed = bool(gate or attention)

    in_play = [row for row in rows if row.in_play]
    finished = [row for row in rows if not row.in_play]

    def _narrow(subject: list[LaunchRow]) -> list[LaunchRow]:
        kept = subject
        if gate:
            kept = [row for row in kept if row.current_gate == gate]
        if attention:
            kept = [row for row in kept if row.at_risk or row.awaiting_confirmation]
        return kept

    shown = sorted(_narrow(in_play), key=_sort_key)
    revealed = sorted(_narrow(finished), key=_finished_key) if reveal else []

    # The reveal is a link, not a checkbox: an unchecked box contributes
    # nothing when its form is submitted, so it could not be engaged in
    # one action -- which is what this control has to be.
    carried = {k: v for k, v in (("gate", gate), ("attention", attention)) if v}
    reveal_href = _href({**carried, "finished": "1"})
    hide_href = _href(carried)

    template = _TEMPLATES.get_template("launches.html")
    return HTMLResponse(
        template.render(
            page_path=PAGE_PATH,
            reveal_href=reveal_href,
            hide_href=hide_href,
            rows=shown,
            revealed=revealed,
            reveal=reveal,
            narrowed=narrowed,
            gate=gate,
            attention=attention,
            gates=sorted({row.current_gate for row in rows}),
            any_enumerated=bool(rows),
            any_in_play=bool(in_play),
            any_finished=bool(finished),
        )
    )


def _journal_path(product_id: str) -> str:
    return f"{PAGE_PATH}/{product_id}/journal"


def _detail_path(product_id: str) -> str:
    return f"{PAGE_PATH}/{product_id}"


async def _resolve_launch(identifier: ProductId, scope: Any) -> tuple[Any, Any]:
    """The launch position and its product, resolved the one way both the
    detail route and the journal route resolve a launch by — so the two
    refuse identically by construction rather than by agreeing twice.

    Refusal turns on the launch position, never on whether the catalog
    can name the product: the list renders an unresolvable launch and
    offers the detail page in one action, so refusing here would put a
    dead end behind a row the surface deliberately keeps visible.
    """
    report = await read_launch(
        launches,
        await _playbook_port(),
        product_id=identifier,
        as_of=today(),
        scope=scope,
    )
    if report is None:
        raise HTTPException(status_code=404)

    try:
        product = await get_product_by_id(identifier, scope)
    except Exception:  # noqa: BLE001 — an unnameable product still renders
        product = None
    return report, product


def _identifier_or_404(product_id: str) -> ProductId:
    try:
        return ProductId(product_id)
    except ValueError as exc:
        # An identifier naming nothing the system knows, refused in the
        # shape every other refusal here takes.
        raise HTTPException(status_code=404) from exc


@router.get(PAGE_PATH + "/{product_id}")
async def launch_detail(request: Request, product_id: str) -> HTMLResponse:
    principal = await _require_admin(request)
    scope = await _scope_for(principal)
    identifier = _identifier_or_404(product_id)
    report, product = await _resolve_launch(identifier, scope)

    detail = _detail_for(report, product)
    template = _TEMPLATES.get_template("launch.html")
    return HTMLResponse(
        template.render(
            page_path=PAGE_PATH,
            launch=detail,
            breadcrumb=[("Launches", PAGE_PATH), (detail.label, None)],
            descendants=[("Journal", _journal_path(detail.product_id))],
        )
    )


@router.get(PAGE_PATH + "/{product_id}/journal")
async def launch_journal(request: Request, product_id: str) -> HTMLResponse:
    principal = await _require_admin(request)
    scope = await _scope_for(principal)
    identifier = _identifier_or_404(product_id)
    report, product = await _resolve_launch(identifier, scope)

    journal = await _journal_for(identifier, scope)
    page = _journal_page_for(report, product, journal)

    template = _TEMPLATES.get_template("journal.html")
    return HTMLResponse(
        template.render(
            page_path=PAGE_PATH,
            journal=page,
            breadcrumb=[
                ("Launches", PAGE_PATH),
                (page.label, _detail_path(page.product_id)),
                ("Journal", None),
            ],
        )
    )
