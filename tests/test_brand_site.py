from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import ad_waste_audit, brand, build_site, clients, importers
from scripts.paid_media_rules import BudgetConfig

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_brand_file_is_valid():
    b = brand.load()
    assert b.service_name and b.price.startswith("£")


def test_brand_validation(tmp_path: Path):
    raw = json.loads((REPO_ROOT / "brand.json").read_text())
    path = tmp_path / "brand.json"
    path.write_text(json.dumps({**raw, "primary_color": "navy"}))
    with pytest.raises(ValueError, match="hex colour"):
        brand.load(path)
    path.write_text(json.dumps({k: v for k, v in raw.items() if k != "price"}))
    with pytest.raises(ValueError, match="missing brand fields"):
        brand.load(path)


def test_site_renders_every_placeholder_and_escapes_values():
    b = replace(brand.load(), service_name='Leak <Check> & "Co"')
    page = build_site.render(b)
    assert "$" not in page
    assert "Leak &lt;Check&gt; &amp; &quot;Co&quot;" in page
    assert "<Check>" not in page


def test_committed_site_is_up_to_date():
    built = (REPO_ROOT / "site" / "public" / "index.html").read_text(encoding="utf-8")
    assert built == build_site.render(brand.load()), "run: python -m scripts.build_site"


def test_report_uses_brand_name_not_hard_coded_name():
    client = clients.load("demo-coffee-roasters", REPO_ROOT / "clients")
    cfg = BudgetConfig.load(client.budgets_path, currency=client.currency_symbol)
    audit = ad_waste_audit.analyse(importers.load(REPO_ROOT / "examples" / "demo-meta-export.csv"), client, cfg)
    page = ad_waste_audit.render_html(audit, client)
    b = brand.load()
    assert f"Prepared by {b.service_name} · {b.operator}" in page
    assert "Agent Marketer" not in page
