"""Assembling the daily briefing, and delivering it when there is one.

Implements the `briefing` capability's derivation, assembly, delivery and
failure requirements.

The split of responsibilities is the one `design.md` Decision 1 records:
launch publishes facts on its report, briefing decides what is worth
saying about them. Nothing here re-derives a launch rule — whether a step
is overdue, whether a gate awaits confirmation and which steps put a date
at risk are all read off the report, because only the launch context has
the playbook and the hazard rules those judgements need.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from commerce_ops.briefing.application.ports import (
    BriefingNotifier,
    CatalogProduct,
    LaunchReports,
    ProductReader,
)
from commerce_ops.briefing.domain.attention import (
    AttentionItem,
    Evidence,
    Finding,
    collapse,
)
from commerce_ops.briefing.domain.briefing import Briefing
from commerce_ops.briefing.domain.launch_causes import (
    GATE_AWAITING_CONFIRMATION,
    LAUNCH_CAUSE_ORDER,
    LAUNCH_DATE_AT_RISK,
    LAUNCH_SEVERITIES,
    OVERDUE_STEP,
)
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import Retired, SteadyState

__all__ = ["assemble_daily_briefing", "render_briefing", "run_daily_briefing"]

_logger = logging.getLogger(__name__)


def _is_active(product: CatalogProduct | None) -> bool:
    """Whether a launch is still worth briefing.

    Stage is the catalog's answer, so a launch drops out the moment
    graduation stamps its product steady-state. A product the catalog
    cannot resolve counts as active: the filter fails toward reporting,
    never toward silence — losing an item because a name lookup missed
    would be exactly the silent failure the briefing exists to prevent.
    """
    if product is None:
        return True
    return not isinstance(product.stage, SteadyState | Retired)


def _findings_for(report: Any) -> list[Finding]:
    """One launch report's raw findings, before collapse."""
    product_id: ProductId = report.product_id
    findings: list[Finding] = []

    at_risk = report.at_risk
    if at_risk is not None:
        findings.append(
            Finding(
                product_id=product_id,
                cause=LAUNCH_DATE_AT_RISK,
                severity=LAUNCH_SEVERITIES[LAUNCH_DATE_AT_RISK],
                evidence=tuple(
                    Evidence(fact=step_id) for step_id in at_risk.overdue_steps
                ),
                # The steps behind the slip are this item's evidence, so
                # they never become items of their own.
                absorbs=tuple(at_risk.overdue_steps),
            )
        )

    if report.awaiting_confirmation:
        findings.append(
            Finding(
                product_id=product_id,
                cause=GATE_AWAITING_CONFIRMATION,
                severity=LAUNCH_SEVERITIES[GATE_AWAITING_CONFIRMATION],
                evidence=(Evidence(fact=report.current_gate),),
            )
        )

    for step in report.steps:
        if not step.overdue:
            continue
        findings.append(
            Finding(
                product_id=product_id,
                cause=OVERDUE_STEP,
                severity=LAUNCH_SEVERITIES[OVERDUE_STEP],
                evidence=(
                    Evidence(
                        fact=step.step_id,
                        start=step.due_period.start if step.due_period else None,
                        end=step.due_period.end if step.due_period else None,
                    ),
                ),
                discipline=step.discipline,
            )
        )
    return findings


async def assemble_daily_briefing(
    *,
    read_launch_reports: LaunchReports,
    read_product: ProductReader,
    audience: str,
    as_of: date,
) -> Briefing:
    """The day's briefing for one audience — assembled, never stored.

    `audience` is taken as a parameter even though this slice only ever
    passes one channel: every read model is scope-aware from day one
    rather than retrofitted when `access` lands.
    """
    findings: list[Finding] = []
    for report in await read_launch_reports(as_of=as_of):
        if not _is_active(await read_product(report.product_id)):
            continue
        findings.extend(_findings_for(report))

    return Briefing(
        period=as_of,
        audience=audience,
        items=collapse(findings, LAUNCH_CAUSE_ORDER),
    )


async def _name_for(item: AttentionItem, read_product: ProductReader) -> str:
    """How an item's product is identified in the delivered message.

    A product the catalog cannot resolve is named by its raw identifier —
    the item is still reported, because a naming failure is not a reason
    to drop something the team needs to see.
    """
    product = await read_product(item.product_id)
    if product is None:
        return item.product_id.value
    return f"{product.name} ({product.sku.value})"


async def render_briefing(briefing: Briefing, *, read_product: ProductReader) -> str:
    """The briefing as one plain-text Slack message.

    Only ever called for a briefing with items: `for_delivery` refuses a
    clean one, since a clean day is no message at all.
    """
    lines = [f"Launch briefing for {briefing.period.isoformat()}"]
    for item in briefing.for_delivery():
        name = await _name_for(item, read_product)
        discipline = f" [{item.discipline.value}]" if item.discipline else ""
        evidence = ", ".join(repr(piece) for piece in item.evidence)
        lines.append(
            f"- {item.severity.value.upper()}{discipline} {name}: "
            f"{item.cause} — {evidence}"
        )
    return "\n".join(lines)


async def run_daily_briefing(
    *,
    read_launch_reports: LaunchReports,
    read_product: ProductReader,
    notifier: BriefingNotifier,
    audience: str,
    as_of: date,
) -> Briefing:
    """Assemble the briefing and deliver it if there is one to deliver.

    The two failure modes are deliberately not alike. A failure to
    *assemble* propagates: the run failed, and `scheduled-jobs`' retry
    and overdue reporting are what should see it. A failure to *deliver*
    an assembled briefing is logged and swallowed: a redelivered briefing
    would be stale, and the failure does not establish the message never
    arrived, so retrying trades a duplicate for nothing.
    """
    briefing = await assemble_daily_briefing(
        read_launch_reports=read_launch_reports,
        read_product=read_product,
        audience=audience,
        as_of=as_of,
    )

    if briefing.is_clean:
        _logger.info(
            "the launch briefing for %s is clean; nothing was posted",
            as_of.isoformat(),
        )
        return briefing

    message = await render_briefing(briefing, read_product=read_product)
    try:
        await notifier.post_monitoring_message(message)
    except Exception:
        _logger.exception(
            "failed to deliver the launch briefing for %s", as_of.isoformat()
        )
    return briefing
