from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import ad_waste_audit, clients, decision_log, importers
from scripts.paid_media_rules import BudgetConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_CSV = REPO_ROOT / "examples" / "demo-meta-export.csv"


@pytest.fixture
def demo():
    client = clients.load("demo-coffee-roasters", REPO_ROOT / "clients")
    cfg = BudgetConfig.load(client.budgets_path, currency=client.currency_symbol)
    return client, cfg, importers.load(DEMO_CSV)


def test_demo_audit_figures_match_hand_calculation(demo):
    client, cfg, export = demo
    audit = ad_waste_audit.analyse(export, client, cfg)
    # Zero-conversion ads: 418.75 + 262.40
    assert audit.zero_conversion_spend == pytest.approx(681.15)
    # Over 1.5x target (£27): brand story 296.60 - 2*18, cart 163.30 - 6*18
    assert audit.overspend_vs_target == pytest.approx(260.60 + 55.30)
    assert audit.addressable_waste == pytest.approx(997.05)
    assert audit.total_spend == pytest.approx(2644.98)
    assert audit.days == 30
    assert audit.monthly_waste_estimate == pytest.approx(997.05)
    verdicts = {a.ad_name: a.verdict for a in audit.ads}
    assert verdicts["Free grinder giveaway"] == "WASTE"
    assert verdicts["Brand story - our roastery"] == "EXPENSIVE"
    assert verdicts["Subscription - Never run out of beans"] == "WINNER"
    assert verdicts["Carousel - 6 origins"] == "OK"
    assert verdicts["Gift subscriptions (new)"] == "TOO_EARLY"
    assert audit.ads[0].ad_name == "Free grinder giveaway"  # ranked by avoidable spend


def test_actions_reference_caps_and_never_promise_results(demo):
    client, cfg, export = demo
    audit = ad_waste_audit.analyse(export, client, cfg)
    text = " ".join(audit.actions)
    assert "daily cap of £120" in text
    assert "20%" in text
    assert "guarantee" not in text.lower()


def test_no_waste_produces_a_calm_recommendation(demo):
    client, cfg, _ = demo
    export = importers.parse("ad_name,spend,impressions,clicks,conversions\nGood,100,5000,100,8\n")
    audit = ad_waste_audit.analyse(export, client, cfg, days=7)
    assert audit.addressable_waste == 0
    assert audit.extra_conversions_estimate is None
    assert not any("freed budget" in a for a in audit.actions)
    assert "test a budget increase" in audit.actions[0]

    flat = importers.parse("ad_name,spend,impressions,clicks,conversions\nFine,100,5000,100,5\n")  # CPA 20: OK
    assert "No clear waste" in ad_waste_audit.analyse(flat, client, cfg, days=7).actions[0]


def test_currency_mismatch_and_unknown_period_are_disclosed(demo):
    client, cfg, _ = demo
    export = importers.parse("Ad name,Amount spent (USD),Impressions,Results\nA,50,1000,0\n")
    audit = ad_waste_audit.analyse(export, client, cfg)
    assert any("USD" in n for n in audit.notes)
    assert any("--days" in n for n in audit.notes)
    assert audit.monthly_waste_estimate is None


def test_html_escapes_ad_names_and_shows_demo_banner(demo):
    client, cfg, _ = demo
    export = importers.parse('ad_name,spend,impressions,clicks,conversions\n"<script>alert(1)</script>",80,3000,10,0\n')
    page = ad_waste_audit.render_html(ad_waste_audit.analyse(export, client, cfg, days=30), client)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "fictional data" in page
    assert "$" not in page.replace("$(", "")  # no unfilled template placeholders


def test_real_clients_get_no_demo_banner(demo, tmp_path: Path):
    _, cfg, export = demo
    shutil.copytree(REPO_ROOT / "clients" / "_template", tmp_path / "clients" / "_template")
    real = clients.create("acme", "Acme", tmp_path / "clients")
    page = ad_waste_audit.render_html(ad_waste_audit.analyse(export, real, cfg), real)
    assert "fictional data" not in page
    assert "Acme" in page


def test_cli_writes_report_into_client_reports_and_logs_pauses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO_ROOT / "clients" / "demo-coffee-roasters", tmp_path / "clients" / "demo-coffee-roasters")
    assert ad_waste_audit.main([str(DEMO_CSV), "--client", "demo-coffee-roasters", "--log"]) == 0
    reports = tmp_path / "clients" / "demo-coffee-roasters" / "reports"
    html_files = list(reports.glob("ad-waste-audit-*.html"))
    json_files = list(reports.glob("ad-waste-audit-*.json"))
    assert len(html_files) == 1 and len(json_files) == 1
    summary = json.loads(json_files[0].read_text())
    assert summary["client_slug"] == "demo-coffee-roasters"
    logged = list(decision_log.read(tmp_path / "clients" / "demo-coffee-roasters" / "logs" / "decisions.jsonl"))
    assert len(logged) == 4
    assert all(r["action"] == "PAUSE" and r["status"] == "proposed" and r["requires_approval"] for r in logged)


def test_cli_reports_bad_input_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO_ROOT / "clients" / "demo-coffee-roasters", tmp_path / "clients" / "demo-coffee-roasters")
    bad = tmp_path / "bad.csv"
    bad.write_text("x,y\n1,2\n")
    assert ad_waste_audit.main([str(bad), "--client", "demo-coffee-roasters"]) == 1
    assert "error:" in capsys.readouterr().err


def test_guarantee_line_reflects_threshold(demo):
    client, cfg, export = demo
    page = ad_waste_audit.render_html(ad_waste_audit.analyse(export, client, cfg), client)
    assert "paid for itself" in page
    small = importers.parse("ad_name,spend,impressions,clicks,conversions\nA,50,3000,30,0\nB,400,9000,200,30\n")
    page = ad_waste_audit.render_html(ad_waste_audit.analyse(small, client, cfg, days=30), client)
    assert "refunded in full" in page
