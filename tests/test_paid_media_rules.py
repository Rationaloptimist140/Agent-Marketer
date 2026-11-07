from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import clients, decision_log
from scripts.paid_media_rules import AdMetrics, BudgetConfig, main, propose

REPO_ROOT = Path(__file__).resolve().parents[1]

CFG = BudgetConfig(
    currency="£",
    daily_cap=100.0,
    monthly_cap=2000.0,
    target_cpa=20.0,
    min_spend_to_judge=40.0,
    min_conversions_to_scale=3,
    pause_cpa_multiple=1.5,
    scale_cpa_multiple=0.7,
    scale_step_pct=20.0,
    min_days_running=3,
    auto_pause_enabled=False,
)


def ad(ad_id: str, *, budget: float = 20.0, spend: float = 60.0, conversions: int = 0, days: int = 5) -> AdMetrics:
    return AdMetrics(ad_id, f"Ad {ad_id}", budget, spend, 5000, 100, conversions, days)


def by_id(proposals):
    return {p.ad_id: p for p in proposals}


def test_holds_when_not_enough_data():
    p = by_id(propose([ad("a", spend=10.0)], CFG))["a"]
    assert p.action == "HOLD"
    assert not p.requires_approval


def test_pauses_zero_conversion_spender_and_requires_approval_by_default():
    p = by_id(propose([ad("a", spend=60.0, conversions=0)], CFG))["a"]
    assert p.action == "PAUSE"
    assert p.proposed_daily_budget == 0.0
    assert p.requires_approval


def test_auto_pause_only_when_enabled():
    cfg = BudgetConfig(**{**CFG.__dict__, "auto_pause_enabled": True})
    p = by_id(propose([ad("a", conversions=0)], cfg))["a"]
    assert p.action == "PAUSE"
    assert not p.requires_approval


def test_pauses_expensive_cpa():
    p = by_id(propose([ad("a", spend=100.0, conversions=2)], CFG))["a"]  # CPA 50 > 30
    assert p.action == "PAUSE"


def test_scales_winner_and_always_requires_approval():
    cfg = BudgetConfig(**{**CFG.__dict__, "auto_pause_enabled": True})
    p = by_id(propose([ad("a", spend=60.0, conversions=6)], cfg))["a"]  # CPA 10
    assert p.action == "SCALE"
    assert p.proposed_daily_budget == 24.0
    assert p.requires_approval


def test_scaling_never_exceeds_daily_cap():
    ads = [ad("a", budget=48.0, spend=60.0, conversions=6), ad("b", budget=50.0, spend=60.0, conversions=5)]
    proposals = propose(ads, CFG)
    assert sum(p.proposed_daily_budget for p in proposals) <= CFG.daily_cap
    # Best CPA (a: 10) gets the remaining £2 of headroom; b is held at the cap.
    result = by_id(proposals)
    assert result["a"].proposed_daily_budget == 50.0
    assert result["b"].action == "HOLD"
    assert "daily cap" in result["b"].reason


def test_pause_frees_headroom_for_winner():
    ads = [ad("loser", budget=50.0, spend=80.0, conversions=0), ad("winner", budget=50.0, spend=60.0, conversions=6)]
    result = by_id(propose(ads, CFG))
    assert result["loser"].action == "PAUSE"
    assert result["winner"].proposed_daily_budget == 60.0


def test_config_rejects_bad_values(tmp_path: Path):
    bad = {**CFG.__dict__, "target_cpa": 0}
    path = tmp_path / "budgets.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        BudgetConfig.load(path)


METRICS_CSV = (
    "ad_id,ad_name,daily_budget,spend,impressions,clicks,conversions,days_running\n"
    "a,Ad A,20,60,5000,100,0,5\n"
    "b,Ad B,20,10,500,10,0,1\n"
)


def test_cli_with_explicit_config_logs_to_default_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "m.csv").write_text(METRICS_CSV)
    (tmp_path / "budgets.json").write_text(json.dumps(CFG.__dict__))
    assert main(["m.csv", "--config", "budgets.json", "--log"]) == 0
    records = list(decision_log.read(tmp_path / "logs" / "decisions.jsonl"))
    assert [r["action"] for r in records] == ["PAUSE"]
    assert records[0]["client"] is None
    assert records[0]["status"] == "proposed"


def test_cli_with_client_uses_client_budgets_currency_and_isolated_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO_ROOT / "clients" / "_template", tmp_path / "clients" / "_template")
    clients.create("acme", "Acme Ltd")
    (tmp_path / "m.csv").write_text(METRICS_CSV)
    assert main(["m.csv", "--client", "acme", "--log"]) == 0
    records = list(decision_log.read(tmp_path / "clients" / "acme" / "logs" / "decisions.jsonl"))
    assert [r["client"] for r in records] == ["acme"]
    assert "£" in records[0]["reasoning"]
    assert not (tmp_path / "logs" / "decisions.jsonl").exists()


def test_cli_requires_client_or_config(tmp_path: Path):
    with pytest.raises(SystemExit):
        main([str(tmp_path / "m.csv")])


def test_budget_config_reports_missing_fields(tmp_path: Path):
    path = tmp_path / "budgets.json"
    path.write_text(json.dumps({"daily_cap": 10}))
    with pytest.raises(ValueError, match="missing budget fields"):
        BudgetConfig.load(path, currency="£")


def test_decision_log_blocks_unapproved_execution():
    with pytest.raises(ValueError):
        decision_log.Decision(pillar="paid_media", action="SCALE", target="a", reasoning="x", status="executed")
