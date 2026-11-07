from __future__ import annotations

from pathlib import Path

from scripts.seo_opportunities import Row, find, load


def row(query: str, page: str = "/a", *, impressions: int = 1000, clicks: int = 0, position: float = 30.0) -> Row:
    return Row(query, page, clicks, impressions, clicks / impressions if impressions else 0.0, position)


def test_deep_ranking_with_impressions_becomes_new_guide():
    [opp] = find([row("how to hide photos on android", impressions=16000, position=50)])
    assert opp.action == "NEW_GUIDE"
    assert opp.potential_extra_clicks == 800  # 16000 * 5% expected at position 5


def test_page_one_two_query_becomes_improvement():
    [opp] = find([row("courier route planner uk", impressions=2000, clicks=10, position=12)])
    assert opp.action == "IMPROVE_PAGE"


def test_filters_low_volume_top_ranked_and_hopeless():
    rows = [
        row("tiny", impressions=50),
        row("already winning", impressions=5000, clicks=1000, position=2),
        row("too deep", impressions=5000, position=80),
    ]
    assert find(rows) == []


def test_ranks_by_potential_and_flags_cannibalisation():
    rows = [
        row("small", impressions=500, position=30),
        row("big", "/a", impressions=6000, position=25),
        row("big", "/b", impressions=4000, position=40),
    ]
    first, second = find(rows)
    assert first.query == "big"
    assert first.impressions == 10000
    assert first.best_page == "/a"
    assert first.cannibalised
    assert second.query == "small"


def test_loads_search_console_export_with_percent_ctr(tmp_path: Path):
    path = tmp_path / "gsc.csv"
    path.write_text("Query,Page,Clicks,Impressions,CTR,Position\nfoo,/x,3,1200,0.25%,18.4\n")
    [r] = load(path)
    assert r.query == "foo"
    assert r.ctr == 0.0025
    assert r.position == 18.4
