"""Build the public landing page from site/index.template.html and brand.json.

Usage:
    python -m scripts.build_site            # writes site/public/index.html

Host site/public/ anywhere static (Cloudflare Pages, Netlify). Rebuild after editing brand.json.
"""

from __future__ import annotations

import html
import sys
from dataclasses import asdict
from pathlib import Path
from string import Template

from scripts import brand

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "site" / "index.template.html"
OUTPUT = ROOT / "site" / "public" / "index.html"


def render(b: brand.Brand, template: Path = TEMPLATE) -> str:
    values = {k: html.escape(v, quote=True) for k, v in asdict(b).items()}
    return Template(template.read_text(encoding="utf-8")).substitute(values)


def main(argv: list[str] | None = None) -> int:
    try:
        page = render(brand.load())
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"built {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
