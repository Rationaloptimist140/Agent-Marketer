"""Search-demand opportunity finder for the Programmatic SEO Engine (pillar 2).

Finds queries where the site is already shown but rarely clicked, e.g.
16,000 impressions at position ~50, and ranks them by the clicks a better page
could plausibly win. The daily loop then writes ONE high-quality page for the
top opportunity rather than bulk content.

Usage:
    python -m scripts.seo_opportunities gsc_export.csv [--top 10] [--min-impressions 200]

gsc_export.csv columns (Google Search Console > Performance > Export, query+page):
    query, page, clicks, impressions, ctr, position
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

# Conservative organic CTR by position, used only to rank opportunities.
_CTR_CURVE = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03, 8: 0.025, 9: 0.02, 10: 0.018}
TARGET_POSITION = 5


def expected_ctr(position: float) -> float:
    pos = max(1, round(position))
    return _CTR_CURVE.get(pos, 0.01 if pos <= 20 else 0.003)


@dataclass(frozen=True)
class Row:
    query: str
    page: str
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass(frozen=True)
class Opportunity:
    query: str
    best_page: str
    impressions: int
    clicks: int
    position: float
    potential_extra_clicks: int
    action: str  # NEW_GUIDE | IMPROVE_PAGE
    cannibalised: bool
    note: str


def _parse_ctr(value: str) -> float:
    value = value.strip()
    return float(value.rstrip("%")) / 100 if value.endswith("%") else float(value or 0)


def load(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for r in reader:
            norm = {k.strip().lower(): v for k, v in r.items()}
            rows.append(
                Row(
                    query=norm["query"].strip(),
                    page=norm["page"].strip(),
                    clicks=int(float(norm["clicks"])),
                    impressions=int(float(norm["impressions"])),
                    ctr=_parse_ctr(norm["ctr"]),
                    position=float(norm["position"]),
                )
            )
        return rows


def find(rows: list[Row], min_impressions: int = 200, max_position: float = 60.0) -> list[Opportunity]:
    by_query: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_query[r.query.lower()].append(r)

    opportunities: list[Opportunity] = []
    for query_rows in by_query.values():
        impressions = sum(r.impressions for r in query_rows)
        clicks = sum(r.clicks for r in query_rows)
        best = min(query_rows, key=lambda r: r.position)
        if impressions < min_impressions or best.position > max_position or best.position <= 3:
            continue
        current_ctr = clicks / impressions if impressions else 0.0
        potential = int(impressions * max(expected_ctr(TARGET_POSITION) - current_ctr, 0))
        if potential <= 0:
            continue
        action = "IMPROVE_PAGE" if best.position <= 20 else "NEW_GUIDE"
        cannibalised = len({r.page for r in query_rows}) > 1
        note = (
            "page ranks on page 1-2: sharpen title/meta and answer the query higher up"
            if action == "IMPROVE_PAGE"
            else "no page truly targets this query: write one dedicated, high-quality guide"
        )
        if cannibalised:
            note += "; several pages compete for this query, consolidate or differentiate them"
        opportunities.append(
            Opportunity(
                query=best.query,
                best_page=best.page,
                impressions=impressions,
                clicks=clicks,
                position=round(best.position, 1),
                potential_extra_clicks=potential,
                action=action,
                cannibalised=cannibalised,
                note=note,
            )
        )
    return sorted(opportunities, key=lambda o: o.potential_extra_clicks, reverse=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-impressions", type=int, default=200)
    args = parser.parse_args(argv)
    for opp in find(load(args.export), min_impressions=args.min_impressions)[: args.top]:
        print(json.dumps(asdict(opp), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
