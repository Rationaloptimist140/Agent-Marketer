from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import decision_log
from scripts.paid_media_rules import AdMetrics, BudgetConfig, main, propose

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


def test_cli_logs_non_hold_proposals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    metrics = tmp_path / "m.csv"
    metrics.write_text(
        "ad_id,ad_name,daily_budget,spend,impressions,clicks,conversions,days_running\n"
        "a,Ad A,20,60,5000,100,0,5\n"
        "b,Ad B,20,10,500,10,0,1\n"
    )
    cfg_path = tmp_path / "budgets.json"
    cfg_path.write_text(json.dumps(CFG.__dict__))
    assert main([str(metrics), str(cfg_path), "--log", "--brand", "QuantaRoute"]) == 0
    records = list(decision_log.read(tmp_path / "logs" / "decisions.jsonl"))
    assert [r["action"] for r in records] == ["PAUSE"]
    assert records[0]["brand"] == "QuantaRoute"
    assert records[0]["status"] == "proposed"


def test_decision_log_blocks_unapproved_execution():
    with pytest.raises(ValueError):
        decision_log.Decision(pillar="paid_media", action="SCALE", target="a", reasoning="x", status="executed")
