"""Client registry: every engagement lives in clients/<slug>/.

Layout per client:
    clients/<slug>/client.json    who they are, offer, branding (committed)
    clients/<slug>/budgets.json   spend thresholds for the rules engines (committed)
    clients/<slug>/data/          raw exports from the client (git-ignored, delete after delivery)
    clients/<slug>/reports/       generated deliverables (git-ignored)
    clients/<slug>/logs/          decision log for this client only (git-ignored)

Usage:
    python -m scripts.clients list
    python -m scripts.clients validate
    python -m scripts.clients new acme-plumbing --name "Acme Plumbing"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CLIENTS_DIR = Path("clients")
TEMPLATE = "_template"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€", "AUD": "A$", "CAD": "C$"}
STAGES = {"pre-traction", "private-beta", "growing", "scaling"}
RELATIONSHIPS = {"own-product", "pilot", "client", "demo"}
OFFERS = {"internal", "ad-waste-audit", "seo-opportunity-report", "weekly-report"}
STATUSES = {"prospect", "active", "paused", "completed"}


class ClientError(ValueError):
    pass


@dataclass(frozen=True)
class Client:
    slug: str
    name: str
    website: str
    industry: str
    country: str
    currency: str
    stage: str
    audience: str
    core_promise: str
    proof_points: tuple[str, ...]
    competitors: tuple[str, ...]
    compliance_notes: tuple[str, ...]
    contact_name: str
    contact_email: str
    primary_color: str
    logo: str | None
    relationship: str
    offer: str
    status: str
    root: Path

    @property
    def currency_symbol(self) -> str:
        return CURRENCY_SYMBOLS[self.currency]

    @property
    def budgets_path(self) -> Path:
        return self.root / "budgets.json"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def log_path(self) -> Path:
        return self.root / "logs" / "decisions.jsonl"


def _require(raw: dict[str, Any], key: str, where: str) -> Any:
    if key not in raw:
        raise ClientError(f"{where}: missing required field {key!r}")
    return raw[key]


def _str_list(value: Any, where: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ClientError(f"{where}: {key!r} must be a list of strings")
    return tuple(value)


def parse(raw: dict[str, Any], root: Path) -> Client:
    where = str(root / "client.json")
    slug = _require(raw, "slug", where)
    if slug != root.name:
        raise ClientError(f"{where}: slug {slug!r} must match folder name {root.name!r}")
    if not SLUG_RE.match(slug):
        raise ClientError(f"{where}: slug {slug!r} must be lowercase letters, digits and hyphens")
    name = str(_require(raw, "name", where)).strip()
    if not name:
        raise ClientError(f"{where}: name must not be empty")

    currency = _require(raw, "currency", where)
    if currency not in CURRENCY_SYMBOLS:
        raise ClientError(f"{where}: currency {currency!r} must be one of {sorted(CURRENCY_SYMBOLS)}")
    stage = _require(raw, "stage", where)
    if stage not in STAGES:
        raise ClientError(f"{where}: stage {stage!r} must be one of {sorted(STAGES)}")

    branding = raw.get("branding", {})
    color = branding.get("primary_color", "#1f3a5f")
    if not HEX_RE.match(color):
        raise ClientError(f"{where}: branding.primary_color {color!r} must be a hex colour like #1f3a5f")

    engagement = _require(raw, "engagement", where)
    relationship = engagement.get("relationship")
    offer = engagement.get("offer")
    status = engagement.get("status")
    if relationship not in RELATIONSHIPS:
        raise ClientError(f"{where}: engagement.relationship must be one of {sorted(RELATIONSHIPS)}")
    if offer not in OFFERS:
        raise ClientError(f"{where}: engagement.offer must be one of {sorted(OFFERS)}")
    if status not in STATUSES:
        raise ClientError(f"{where}: engagement.status must be one of {sorted(STATUSES)}")

    contact = raw.get("contact", {})
    return Client(
        slug=slug,
        name=name,
        website=raw.get("website", ""),
        industry=raw.get("industry", ""),
        country=raw.get("country", "GB"),
        currency=currency,
        stage=stage,
        audience=raw.get("audience", ""),
        core_promise=raw.get("core_promise", ""),
        proof_points=_str_list(raw.get("proof_points", []), where, "proof_points"),
        competitors=_str_list(raw.get("competitors", []), where, "competitors"),
        compliance_notes=_str_list(raw.get("compliance_notes", []), where, "compliance_notes"),
        contact_name=contact.get("name", ""),
        contact_email=contact.get("email", ""),
        primary_color=color,
        logo=branding.get("logo"),
        relationship=relationship,
        offer=offer,
        status=status,
        root=root,
    )


def load(slug: str, clients_dir: Path = CLIENTS_DIR) -> Client:
    root = clients_dir / slug
    path = root / "client.json"
    if not path.exists():
        known = ", ".join(c.slug for c in list_clients(clients_dir)) or "none"
        raise ClientError(f"unknown client {slug!r} (known: {known}). Create one with: python -m scripts.clients new {slug}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClientError(f"{path}: invalid JSON ({exc})") from exc
    return parse(raw, root)


def list_clients(clients_dir: Path = CLIENTS_DIR) -> list[Client]:
    if not clients_dir.exists():
        return []
    return [
        load(d.name, clients_dir)
        for d in sorted(clients_dir.iterdir())
        if d.is_dir() and not d.name.startswith("_") and (d / "client.json").exists()
    ]


def create(slug: str, name: str, clients_dir: Path = CLIENTS_DIR) -> Client:
    if not SLUG_RE.match(slug):
        raise ClientError(f"slug {slug!r} must be lowercase letters, digits and hyphens")
    target = clients_dir / slug
    if target.exists():
        raise ClientError(f"client {slug!r} already exists")
    shutil.copytree(clients_dir / TEMPLATE, target, ignore=shutil.ignore_patterns("README.md"))
    path = target / "client.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["slug"], raw["name"] = slug, name
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return load(slug, clients_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Agent Marketer clients")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("validate")
    new = sub.add_parser("new")
    new.add_argument("slug")
    new.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    from scripts.paid_media_rules import BudgetConfig  # local import avoids a cycle

    try:
        if args.cmd == "new":
            client = create(args.slug, args.name)
            print(f"created {client.root}/ — fill in client.json and budgets.json before running any audit")
        elif args.cmd == "list":
            for c in list_clients():
                print(f"{c.slug:<28} {c.name:<28} {c.relationship:<12} {c.offer:<24} {c.status}")
        else:
            clients = list_clients()
            for c in clients:
                BudgetConfig.load(c.budgets_path, currency=c.currency_symbol)
            print(f"ok: {len(clients)} clients valid")
    except (ClientError, ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
