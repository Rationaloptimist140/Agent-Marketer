"""Deterministic rules engine for the Autonomous Paid Media Agent (pillar 1).

It reads ad-level metrics and a budget config, and *proposes* actions. It never
calls an ads API itself. Anything that increases spend always requires approval;
pauses can be auto-allowed only when the config explicitly enables it.

Usage:
    python -m scripts.paid_media_rules metrics.csv --client acme-plumbing [--log]
    python -m scripts.paid_media_rules metrics.csv --config path/to/budgets.json

metrics.csv columns: ad_id, ad_name, daily_budget, spend, impressions, clicks, conversions, days_running
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts import clients, decision_log


@dataclass(frozen=True)
class BudgetConfig:
    currency: str
    daily_cap: float
    monthly_cap: float
    target_cpa: float
    min_spend_to_judge: float
    min_conversions_to_scale: int
    pause_cpa_multiple: float
    scale_cpa_multiple: float
    scale_step_pct: float
    min_days_running: int
    auto_pause_enabled: bool

    @classmethod
    def load(cls, path: Path, currency: str | None = None) -> BudgetConfig:
        """Load thresholds. A client's currency symbol overrides any value in the file."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        if currency is not None:
            raw["currency"] = currency
        missing = [k for k in cls.__dataclass_fields__ if k not in raw]
        if missing:
            raise ValueError(f"{path}: missing budget fields {missing}")
        cfg = cls(**{k: raw[k] for k in cls.__dataclass_fields__})
        if cfg.daily_cap <= 0 or cfg.target_cpa <= 0:
            raise ValueError("daily_cap and target_cpa must be positive")
        if not 0 < cfg.scale_step_pct <= 50:
            raise ValueError("scale_step_pct must be between 0 and 50")
        return cfg


@dataclass(frozen=True)
class AdMetrics:
    ad_id: str
    ad_name: str
    daily_budget: float
    spend: float
    impressions: int
    clicks: int
    conversions: int
    days_running: int

    @property
    def cpa(self) -> float | None:
        return self.spend / self.conversions if self.conversions else None

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0


@dataclass(frozen=True)
class Proposal:
    ad_id: str
    ad_name: str
    action: str  # PAUSE | SCALE | HOLD
    reason: str
    current_daily_budget: float
    proposed_daily_budget: float
    requires_approval: bool


def load_metrics(path: Path) -> list[AdMetrics]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            AdMetrics(
                ad_id=row["ad_id"],
                ad_name=row["ad_name"],
                daily_budget=float(row["daily_budget"]),
                spend=float(row["spend"]),
                impressions=int(row["impressions"]),
                clicks=int(row["clicks"]),
                conversions=int(row["conversions"]),
                days_running=int(row["days_running"]),
            )
            for row in csv.DictReader(fh)
        ]


def _judge(ad: AdMetrics, cfg: BudgetConfig) -> tuple[str, str]:
    if ad.spend < cfg.min_spend_to_judge or ad.days_running < cfg.min_days_running:
        return "HOLD", (
            f"not enough data: spent {cfg.currency}{ad.spend:.2f} over {ad.days_running}d "
            f"(need {cfg.currency}{cfg.min_spend_to_judge:.2f} and {cfg.min_days_running}d)"
        )
    if ad.conversions == 0:
        return "PAUSE", f"spent {cfg.currency}{ad.spend:.2f} with zero conversions"
    cpa = ad.cpa
    assert cpa is not None
    if cpa > cfg.target_cpa * cfg.pause_cpa_multiple:
        return "PAUSE", (
            f"CPA {cfg.currency}{cpa:.2f} is above {cfg.pause_cpa_multiple}x target ({cfg.currency}{cfg.target_cpa:.2f})"
        )
    if cpa <= cfg.target_cpa * cfg.scale_cpa_multiple and ad.conversions >= cfg.min_conversions_to_scale:
        return "SCALE", (
            f"CPA {cfg.currency}{cpa:.2f} is at or below {cfg.scale_cpa_multiple}x target with {ad.conversions} conversions"
        )
    return "HOLD", f"CPA {cfg.currency}{cpa:.2f} is within the normal range of target"


def propose(ads: list[AdMetrics], cfg: BudgetConfig) -> list[Proposal]:
    """Return one proposal per ad. Total proposed daily budget never exceeds daily_cap."""
    judged = [(ad, *_judge(ad, cfg)) for ad in ads]
    # Budgets that stay in place: everything except pauses.
    committed = sum(ad.daily_budget for ad, action, _ in judged if action != "PAUSE")
    headroom = max(cfg.daily_cap - committed, 0.0)

    proposals: list[Proposal] = []
    # Best CPA scales first so limited headroom goes to the strongest ad.
    for ad, action, reason in sorted(judged, key=lambda j: (j[0].cpa is None, j[0].cpa or 0.0)):
        new_budget = ad.daily_budget
        if action == "PAUSE":
            new_budget = 0.0
        elif action == "SCALE":
            increase = min(ad.daily_budget * cfg.scale_step_pct / 100, headroom)
            if increase <= 0:
                action, reason = "HOLD", f"{reason}; but the daily cap of {cfg.currency}{cfg.daily_cap:.2f} is reached"
            else:
                headroom -= increase
                new_budget = round(ad.daily_budget + increase, 2)
        requires_approval = not (action == "PAUSE" and cfg.auto_pause_enabled) and action != "HOLD"
        proposals.append(
            Proposal(
                ad_id=ad.ad_id,
                ad_name=ad.ad_name,
                action=action,
                reason=reason,
                current_daily_budget=ad.daily_budget,
                proposed_daily_budget=new_budget,
                requires_approval=requires_approval,
            )
        )
    return proposals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("metrics", type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--client", help="client slug under clients/ (uses its budgets.json and decision log)")
    target.add_argument("--config", type=Path, help="explicit budgets.json, for ad-hoc runs outside a client")
    parser.add_argument("--log", action="store_true", help="append proposals to the decision log")
    args = parser.parse_args(argv)

    if args.client:
        client = clients.load(args.client)
        cfg = BudgetConfig.load(client.budgets_path, currency=client.currency_symbol)
        client_slug, log_path = client.slug, client.log_path
    else:
        cfg = BudgetConfig.load(args.config)
        client_slug, log_path = None, decision_log.DEFAULT_LOG_PATH

    proposals = propose(load_metrics(args.metrics), cfg)
    for p in proposals:
        print(json.dumps(asdict(p), ensure_ascii=False))
        if args.log and p.action != "HOLD":
            decision_log.append(
                decision_log.Decision(
                    pillar="paid_media",
                    action=p.action,
                    target=p.ad_id,
                    reasoning=p.reason,
                    client=client_slug,
                    inputs={"current_daily_budget": p.current_daily_budget, "proposed_daily_budget": p.proposed_daily_budget},
                    requires_approval=p.requires_approval,
                ),
                path=log_path,
            )
    total = sum(p.proposed_daily_budget for p in proposals)
    print(f"# proposed total daily budget {cfg.currency}{total:.2f} / cap {cfg.currency}{cfg.daily_cap:.2f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
