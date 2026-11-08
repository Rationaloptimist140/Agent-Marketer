"""Single source of truth for the public-facing brand.

Change the name, price, links or colours in brand.json and every surface follows:
the landing page (scripts/build_site.py), audit reports and delivery emails.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path

BRAND_PATH = Path(__file__).resolve().parents[1] / "brand.json"
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Brand:
    service_name: str
    tagline: str
    operator: str
    contact_email: str
    price: str
    min_monthly_spend: str
    turnaround: str
    booking_url: str
    sample_report_url: str
    walkthrough_url: str
    primary_color: str
    accent_color: str


def load(path: Path = BRAND_PATH) -> Brand:
    raw = json.loads(path.read_text(encoding="utf-8"))
    missing = [f.name for f in fields(Brand) if f.name not in raw]
    if missing:
        raise ValueError(f"{path}: missing brand fields {missing}")
    brand = Brand(**{f.name: str(raw[f.name]) for f in fields(Brand)})
    for key in ("primary_color", "accent_color"):
        if not HEX_RE.match(getattr(brand, key)):
            raise ValueError(f"{path}: {key} must be a hex colour like #1b2b44")
    if not brand.service_name.strip():
        raise ValueError(f"{path}: service_name must not be empty")
    return brand
