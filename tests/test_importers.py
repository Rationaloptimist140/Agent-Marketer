from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import importers

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_meta_export_detects_platform_currency_period_and_values():
    export = importers.load(REPO_ROOT / "examples" / "demo-meta-export.csv")
    assert export.platform == "meta"
    assert export.currency == "GBP"
    assert export.period_start == date(2026, 10, 1)
    assert export.days == 30
    assert len(export.rows) == 10
    first = export.rows[0]
    assert first.ad_name == "Subscription - Never run out of beans"
    assert first.campaign == "Prospecting - Broad"
    assert first.spend == 452.18
    assert first.conversions == 41
    assert first.clicks == 1012


GOOGLE_EXPORT = """Ad report
"October 1, 2026 - October 31, 2026"
Ad status,Ad,Campaign,Ad group,Currency code,Impr.,Clicks,Cost,Conversions
Enabled,Emergency plumber 24/7,Search - Brand,Emergency,GBP,"12,400",610,"1,204.50",38.00
Enabled,Boiler repair same day,Search - Generic,Boilers,GBP,"8,020",233,640.10,--
Total: Account,,,,,"20,420",843,"1,844.60",38.00
"""


def test_google_export_skips_title_lines_totals_and_parses_formatted_numbers():
    export = importers.parse(GOOGLE_EXPORT)
    assert export.platform == "google"
    assert export.currency == "GBP"
    assert [r.ad_name for r in export.rows] == ["Emergency plumber 24/7", "Boiler repair same day"]
    assert export.rows[0].spend == 1204.50
    assert export.rows[0].impressions == 12400
    assert export.rows[1].conversions == 0.0
    assert export.days is None


def test_generic_export_and_missing_conversions_note():
    export = importers.parse("ad_name,spend,impressions,clicks\nA,10,100,5\n")
    assert export.platform == "generic"
    assert export.rows[0].conversions == 0
    assert any("No conversions" in n for n in export.notes)


def test_bom_and_currency_symbols_are_handled():
    export = importers.parse(
        "\ufeffAd name,Amount spent (EUR),Impressions,Results\nA,€1.234,50,2000,3\n".replace("€1.234,50", '"€1,234.50"')
    )
    assert export.currency == "EUR"
    assert export.rows[0].spend == 1234.50


def test_unusable_file_gives_a_helpful_error():
    with pytest.raises(importers.ImportErrorWithHint, match="Export at ad level"):
        importers.parse("name,value\na,1\n")


def test_google_excel_csv_utf16_tab_separated(tmp_path: Path):
    path = tmp_path / "google_excel.csv"
    path.write_bytes(
        GOOGLE_EXPORT.replace(",", "\t")
        .replace('"12\t400"', "12400")
        .replace('"1\t204.50"', "1204.50")
        .replace('"20\t420"', "20420")
        .replace('"1\t844.60"', "1844.60")
        .replace('"October 1\t 2026 - October 31\t 2026"', "Oct 2026")
        .encode("utf-16")
    )
    export = importers.load(path)
    assert [r.ad_name for r in export.rows] == ["Emergency plumber 24/7", "Boiler repair same day"]
    assert export.rows[0].spend == 1204.50
    assert export.rows[0].impressions == 12400
