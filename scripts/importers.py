"""Normalise ad-platform exports into one row shape.

Supported:
- Meta Ads Manager export (ad level, CSV): "Ad name", "Amount spent (GBP)", "Results",
  "Impressions", "Link clicks", optional "Reporting starts" / "Reporting ends".
- Google Ads report (CSV): may start with title lines ("Ad report", date range) before the
  header; "Ad" or "Ad name", "Cost", "Conversions", "Impr.", "Clicks", optional "Currency code".
- Generic CSV with: ad_id, ad_name, spend, impressions, clicks, conversions.

Numbers like "1,234.56", "£12.30", "--" and blanks are handled.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class ImportErrorWithHint(ValueError):
    pass


@dataclass(frozen=True)
class AdRow:
    ad_id: str
    ad_name: str
    campaign: str
    spend: float
    impressions: int
    clicks: int
    conversions: float

    @property
    def cpa(self) -> float | None:
        return self.spend / self.conversions if self.conversions > 0 else None

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0


@dataclass(frozen=True)
class Export:
    platform: str  # meta | google | generic
    rows: tuple[AdRow, ...]
    period_start: date | None
    period_end: date | None
    currency: str | None
    notes: tuple[str, ...]

    @property
    def days(self) -> int | None:
        if self.period_start and self.period_end:
            return (self.period_end - self.period_start).days + 1
        return None


_ALIASES = {
    "ad_name": ["ad name", "ad", "ad_name", "headline", "ad headline"],
    "ad_id": ["ad id", "ad_id"],
    "campaign": ["campaign name", "campaign"],
    "spend": ["amount spent", "cost", "spend"],
    "impressions": ["impressions", "impr.", "impr"],
    "clicks": ["link clicks", "clicks", "clicks (all)"],
    "conversions": ["results", "conversions", "purchases", "website purchases", "leads"],
    "start": ["reporting starts", "day", "start date"],
    "end": ["reporting ends", "end date"],
    "currency": ["currency code", "currency"],
}
_NUMBER_JUNK = re.compile(r"[^\d.\-]")


def _num(value: str | None) -> float:
    if value is None:
        return 0.0
    value = value.strip()
    if value in {"", "--", "-", "—"}:
        return 0.0
    cleaned = _NUMBER_JUNK.sub("", value.replace(",", ""))
    try:
        return float(cleaned) if cleaned not in {"", "-", "."} else 0.0
    except ValueError:
        return 0.0


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _match(header: list[str], key: str) -> str | None:
    lowered = {h.strip().lower(): h for h in header}
    for alias in _ALIASES[key]:
        if alias in lowered:
            return lowered[alias]
    for h_low, original in lowered.items():  # e.g. "Amount spent (GBP)"
        if any(h_low.startswith(alias + " (") for alias in _ALIASES[key]):
            return original
    return None


def _delimiter(lines: list[str]) -> str:
    sample = "\n".join(lines[:15])
    return "\t" if sample.count("\t") > sample.count(",") else ","


def _find_header(lines: list[str], delimiter: str = ",") -> int:
    for i, line in enumerate(lines[:15]):
        cells = [c.strip().lower() for c in next(csv.reader([line], delimiter=delimiter))]
        has_spend = any(c.startswith(("amount spent", "cost", "spend")) for c in cells)
        if has_spend and any(c in {"impressions", "impr.", "impr"} for c in cells):
            return i
    raise ImportErrorWithHint(
        "could not find a header row with spend and impressions columns. "
        "Export at ad level and include Amount spent/Cost, Impressions, Clicks and Results/Conversions."
    )


def parse(text: str) -> Export:
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
    delimiter = _delimiter(lines)
    start = _find_header(lines, delimiter)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    header = reader.fieldnames or []
    cols = {key: _match(header, key) for key in _ALIASES}
    if cols["ad_name"] is None or cols["spend"] is None:
        raise ImportErrorWithHint("export needs an ad name column and a spend/cost column")

    lowered = [h.lower() for h in header]
    if any(h.startswith("amount spent") for h in lowered) or "results" in lowered:
        platform = "meta"
    elif "impr." in lowered or "cost" in lowered:
        platform = "google"
    else:
        platform = "generic"

    notes: list[str] = []
    if cols["conversions"] is None:
        notes.append("No conversions/results column found: every ad is treated as having zero conversions.")
    currency = None
    if cols["spend"] and "(" in cols["spend"]:
        currency = cols["spend"].rsplit("(", 1)[1].rstrip(")").strip().upper()

    rows: list[AdRow] = []
    starts: list[date] = []
    ends: list[date] = []
    for i, r in enumerate(reader):
        name = (r.get(cols["ad_name"]) or "").strip()
        if not name or name.lower().startswith(("total", "--")):
            continue  # Google Ads adds total rows
        if cols["currency"] and r.get(cols["currency"]):
            currency = r[cols["currency"]].strip().upper()
        for key, bucket in (("start", starts), ("end", ends)):
            if cols[key] and (d := _date(r.get(cols[key]))):
                bucket.append(d)
        rows.append(
            AdRow(
                ad_id=(r.get(cols["ad_id"]) or "").strip() if cols["ad_id"] else f"row-{i + 1}",
                ad_name=name,
                campaign=(r.get(cols["campaign"]) or "").strip() if cols["campaign"] else "",
                spend=_num(r.get(cols["spend"])),
                impressions=int(_num(r.get(cols["impressions"]))) if cols["impressions"] else 0,
                clicks=int(_num(r.get(cols["clicks"]))) if cols["clicks"] else 0,
                conversions=_num(r.get(cols["conversions"])) if cols["conversions"] else 0.0,
            )
        )
    if not rows:
        raise ImportErrorWithHint("export contained no ad rows")
    return Export(
        platform=platform,
        rows=tuple(rows),
        period_start=min(starts) if starts else None,
        period_end=max(ends or starts) if (ends or starts) else None,
        currency=currency,
        notes=tuple(notes),
    )


def load(path: Path) -> Export:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):  # "Excel .csv" downloads are UTF-16, tab-separated
        return parse(raw.decode("utf-16"))
    return parse(raw.decode("utf-8-sig"))
