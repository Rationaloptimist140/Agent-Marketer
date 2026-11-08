"""Ad Waste Audit: turn a Meta or Google Ads export into a client-ready report.

Deterministic: every figure comes from the export and the client's budgets.json.
Nothing touches an ad account. Output is a self-contained HTML report (print to
PDF from any browser) plus a JSON summary for the decision log and follow-ups.

Usage:
    python -m scripts.ad_waste_audit clients/acme/data/meta.csv --client acme [--days 30] [--log]
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from string import Template

from scripts import brand, clients, decision_log, importers
from scripts.paid_media_rules import BudgetConfig

LOW_CTR = 0.007  # below 0.7% click-through on an ad that has had real delivery
LOW_CTR_MIN_IMPRESSIONS = 2000
REALLOCATION_EFFICIENCY = 0.5  # assume moved budget converts at half the winners' current rate
GUARANTEE_THRESHOLD = 99.0  # refund if avoidable spend found is below the audit price

VERDICTS = {
    "WASTE": ("Pause", "Spent with no conversions"),
    "EXPENSIVE": ("Pause or fix", "Cost per conversion far above target"),
    "WINNER": ("Scale (with approval)", "Converting well below target cost"),
    "OK": ("Keep", "Within the normal range"),
    "TOO_EARLY": ("Wait", "Not enough spend to judge yet"),
}


@dataclass(frozen=True)
class AdVerdict:
    ad_id: str
    ad_name: str
    campaign: str
    spend: float
    conversions: float
    cpa: float | None
    ctr: float
    verdict: str
    action: str
    reason: str
    wasted: float
    low_ctr: bool


@dataclass(frozen=True)
class Audit:
    client_slug: str
    client_name: str
    currency_symbol: str
    platform: str
    period_start: str | None
    period_end: str | None
    days: int | None
    target_cpa: float
    daily_cap: float
    min_spend_to_judge: float
    pause_cpa_multiple: float
    total_spend: float
    total_conversions: float
    blended_cpa: float | None
    zero_conversion_spend: float
    overspend_vs_target: float
    addressable_waste: float
    waste_share: float
    monthly_waste_estimate: float | None
    extra_conversions_estimate: float | None
    ads: tuple[AdVerdict, ...]
    actions: tuple[str, ...]
    notes: tuple[str, ...]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%d"))


def _money(sym: str, value: float) -> str:
    return f"{sym}{value:,.0f}" if abs(value) >= 100 else f"{sym}{value:,.2f}"


def analyse(export: importers.Export, client: clients.Client, cfg: BudgetConfig, days: int | None = None) -> Audit:
    sym = client.currency_symbol
    notes = list(export.notes)
    if export.currency and export.currency != client.currency:
        notes.append(
            f"Export currency is {export.currency} but the client is set up in {client.currency}; figures are shown as exported."
        )
    days = days or export.days

    verdicts: list[AdVerdict] = []
    for row in export.rows:
        cpa = row.cpa
        wasted = 0.0
        if row.spend < cfg.min_spend_to_judge:
            verdict = "TOO_EARLY"
            reason = f"Spent {_money(sym, row.spend)}; needs {_money(sym, cfg.min_spend_to_judge)} before judging"
        elif row.conversions <= 0:
            verdict, wasted = "WASTE", row.spend
            reason = f"{_money(sym, row.spend)} spent with no conversions"
        elif cpa is not None and cpa > cfg.target_cpa * cfg.pause_cpa_multiple:
            verdict = "EXPENSIVE"
            wasted = max(row.spend - row.conversions * cfg.target_cpa, 0.0)
            reason = f"{_money(sym, cpa)} per conversion vs {_money(sym, cfg.target_cpa)} target"
        elif (
            cpa is not None and cpa <= cfg.target_cpa * cfg.scale_cpa_multiple and row.conversions >= cfg.min_conversions_to_scale
        ):
            verdict = "WINNER"
            reason = f"{_money(sym, cpa)} per conversion, {row.conversions:g} conversions"
        else:
            verdict = "OK"
            reason = f"{_money(sym, cpa)} per conversion" if cpa else "Within range"
        low_ctr = row.impressions >= LOW_CTR_MIN_IMPRESSIONS and row.ctr < LOW_CTR and verdict in {"OK", "TOO_EARLY"}
        verdicts.append(
            AdVerdict(
                ad_id=row.ad_id,
                ad_name=row.ad_name,
                campaign=row.campaign,
                spend=row.spend,
                conversions=row.conversions,
                cpa=cpa,
                ctr=row.ctr,
                verdict=verdict,
                action=VERDICTS[verdict][0],
                reason=reason,
                wasted=round(wasted, 2),
                low_ctr=low_ctr,
            )
        )
    verdicts.sort(key=lambda v: (-v.wasted, -v.spend))

    total_spend = sum(v.spend for v in verdicts)
    total_conv = sum(v.conversions for v in verdicts)
    zero_conv = sum(v.wasted for v in verdicts if v.verdict == "WASTE")
    overspend = sum(v.wasted for v in verdicts if v.verdict == "EXPENSIVE")
    addressable = zero_conv + overspend
    winners = [v for v in verdicts if v.verdict == "WINNER"]

    extra = None
    if winners and addressable > 0:
        winner_cpa = sum(w.spend for w in winners) / sum(w.conversions for w in winners)
        extra = round(addressable / winner_cpa * REALLOCATION_EFFICIENCY, 1)
    monthly = round(addressable / days * 30, 2) if days else None
    if days is None:
        notes.append("Reporting period unknown: pass --days to estimate monthly waste.")

    actions: list[str] = []
    to_pause = [v for v in verdicts if v.verdict in {"WASTE", "EXPENSIVE"}]
    if to_pause:
        names = ", ".join(f"“{v.ad_name}”" for v in to_pause[:3])
        more = f" and {len(to_pause) - 3} more" if len(to_pause) > 3 else ""
        actions.append(f"Pause {names}{more}: together they account for {_money(sym, addressable)} of avoidable spend.")
    if winners:
        ranked = sorted(winners, key=lambda w: w.cpa or 0)[:2]
        names = " and ".join(f"“{w.ad_name}” ({_money(sym, w.cpa or 0)} per conversion)" for w in ranked)
        lead = "Move freed budget to" if addressable > 0 else "If you want more volume, test a budget increase on"
        actions.append(
            f"{lead} {names}, in steps of no more than {cfg.scale_step_pct:g}% "
            f"and within the agreed daily cap of {_money(sym, cfg.daily_cap)}."
        )
        top = max(winners, key=lambda w: w.conversions)
        actions.append(
            f"Brief two new variations on the hook and offer of “{top.ad_name}” to find the next winner before it fatigues."
        )
    refresh = [v for v in verdicts if v.low_ctr]
    if refresh:
        actions.append(
            f"Refresh creative on {len(refresh)} ad(s) you are keeping whose click-through is below {LOW_CTR:.1%}: "
            "people are scrolling past them."
        )
    if not actions:
        actions.append(
            "No clear waste at current thresholds. Keep spend steady and re-run once every ad has passed the minimum spend."
        )

    return Audit(
        client_slug=client.slug,
        client_name=client.name,
        currency_symbol=sym,
        platform=export.platform,
        period_start=export.period_start.isoformat() if export.period_start else None,
        period_end=export.period_end.isoformat() if export.period_end else None,
        days=days,
        target_cpa=cfg.target_cpa,
        daily_cap=cfg.daily_cap,
        min_spend_to_judge=cfg.min_spend_to_judge,
        pause_cpa_multiple=cfg.pause_cpa_multiple,
        total_spend=round(total_spend, 2),
        total_conversions=round(total_conv, 2),
        blended_cpa=round(total_spend / total_conv, 2) if total_conv else None,
        zero_conversion_spend=round(zero_conv, 2),
        overspend_vs_target=round(overspend, 2),
        addressable_waste=round(addressable, 2),
        waste_share=round(addressable / total_spend, 4) if total_spend else 0.0,
        monthly_waste_estimate=monthly,
        extra_conversions_estimate=extra,
        ads=tuple(verdicts),
        actions=tuple(actions),
        notes=tuple(notes),
    )


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "ad_waste_audit.html"


def _guarantee_line(audit: Audit) -> str:
    threshold = f"{audit.currency_symbol}{GUARANTEE_THRESHOLD:,.0f}"
    if audit.addressable_waste >= GUARANTEE_THRESHOLD:
        text = f"Guarantee check: avoidable spend found is above the {threshold} threshold, so the audit has paid for itself."
        css = "ok"
    else:
        text = f"Guarantee check: avoidable spend found is below {threshold}. Your audit fee will be refunded in full."
        css = "refund"
    return f"<p class='guarantee {css}'>{html.escape(text)}</p>"


def render_html(audit: Audit, client: clients.Client) -> str:
    e = html.escape
    sym = audit.currency_symbol

    def money(v: float | None) -> str:
        return "–" if v is None else e(_money(sym, v))

    period = (
        f"{audit.period_start} to {audit.period_end}"
        if audit.period_start and audit.period_end
        else (f"Last {audit.days} days" if audit.days else "Period not stated")
    )
    platform = {"meta": "Meta Ads", "google": "Google Ads"}.get(audit.platform, "Ads")
    monthly = (
        f"<div><span>Estimated per month</span><strong>{money(audit.monthly_waste_estimate)}</strong></div>"
        if audit.monthly_waste_estimate is not None
        else ""
    )
    extra = (
        "<div><span>Extra conversions if reinvested (estimate)</span>"
        f"<strong>≈{audit.extra_conversions_estimate:g}</strong></div>"
        if audit.extra_conversions_estimate
        else ""
    )
    rows = "\n".join(
        f"<tr><td><strong>{e(a.ad_name)}</strong>"
        + (f"<br><span class='small'>{e(a.campaign)}</span>" if a.campaign else "")
        + ("<br><span class='flag'>Low click-through: creative refresh</span>" if a.low_ctr else "")
        + f"</td><td class='num'>{money(a.spend)}</td><td class='num'>{a.conversions:g}</td>"
        f"<td class='num'>{money(a.cpa)}</td><td class='num'>{a.ctr:.2%}</td>"
        f"<td><span class='badge {a.verdict}'>{e(a.action)}</span><br><span class='small'>{e(a.reason)}</span></td>"
        f"<td class='num'>{money(a.wasted) if a.wasted else '–'}</td></tr>"
        for a in audit.ads
    )
    actions = "\n".join(f"<li>{e(x)}</li>" for x in audit.actions)
    pause = [a for a in audit.ads if a.verdict in {"WASTE", "EXPENSIVE"}]
    scale = [a for a in audit.ads if a.verdict == "WINNER"]
    checklist = "".join(f"<label><input type='checkbox'> Pause “{e(a.ad_name)}”</label>" for a in pause) + "".join(
        f"<label><input type='checkbox'> Increase daily budget on “{e(a.ad_name)}” by ______ "
        f"(total stays within the agreed {money(audit.daily_cap)}/day cap)</label>"
        for a in scale
    )
    notes = "".join(f"<li>{e(n)}</li>" for n in audit.notes)
    b = brand.load()
    values = {
        "service_name": e(b.service_name),
        "operator": e(b.operator),
        "client_name": e(audit.client_name),
        "brand_color": client.primary_color,
        "platform": e(platform),
        "period": e(period),
        "generated_at": e(audit.generated_at),
        "addressable_waste": money(audit.addressable_waste),
        "waste_share": f"{audit.waste_share:.0%}",
        "total_spend": money(audit.total_spend),
        "side": monthly + extra,
        "total_conversions": f"{audit.total_conversions:g}",
        "blended_cpa": money(audit.blended_cpa),
        "target_cpa": money(audit.target_cpa),
        "actions": actions,
        "rows": rows,
        "checklist": checklist or "<p class='small'>No changes recommended at this time.</p>",
        "min_spend": money(audit.min_spend_to_judge),
        "pause_multiple": f"{audit.pause_cpa_multiple:g}",
        "notes": notes,
        "guarantee": _guarantee_line(audit) if client.offer == "ad-waste-audit" else "",
        "demo_banner": (
            "<p class='demo'>Demonstration report built from fictional data. Not a real client result.</p>"
            if client.relationship == "demo"
            else ""
        ),
    }
    return Template(TEMPLATE_PATH.read_text(encoding="utf-8")).substitute(values)


def write(audit: Audit, client: clients.Client, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"ad-waste-audit-{audit.generated_at}"
    html_path = out_dir / f"{stem}.html"
    json_path = out_dir / f"{stem}.json"
    html_path.write_text(render_html(audit, client), encoding="utf-8")
    json_path.write_text(json.dumps(asdict(audit), indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return html_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path)
    parser.add_argument("--client", required=True)
    parser.add_argument("--days", type=int, help="reporting period length, if the export doesn't include dates")
    parser.add_argument("--out", type=Path, help="output folder (default: clients/<slug>/reports/)")
    parser.add_argument("--log", action="store_true", help="record recommended pauses in the client's decision log")
    args = parser.parse_args(argv)

    try:
        client = clients.load(args.client)
        cfg = BudgetConfig.load(client.budgets_path, currency=client.currency_symbol)
        export = importers.load(args.export)
    except (clients.ClientError, importers.ImportErrorWithHint, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    audit = analyse(export, client, cfg, days=args.days)
    html_path, json_path = write(audit, client, args.out or client.reports_dir)
    if args.log:
        for a in audit.ads:
            if a.verdict in {"WASTE", "EXPENSIVE"}:
                decision_log.append(
                    decision_log.Decision(
                        pillar="ad_waste_audit",
                        action="PAUSE",
                        target=a.ad_id,
                        reasoning=a.reason,
                        client=client.slug,
                        inputs={"spend": a.spend, "conversions": a.conversions, "avoidable": a.wasted},
                    ),
                    path=client.log_path,
                )
    sym = audit.currency_symbol
    print(f"{_money(sym, audit.addressable_waste)} avoidable of {_money(sym, audit.total_spend)}")
    print(f"report: {html_path}\nsummary: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
