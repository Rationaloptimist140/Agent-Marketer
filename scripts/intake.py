"""One command from a client's booking-form submission to a ready-to-send audit.

Creates (or reuses) the client folder, sets their target from the booking form,
copies their export into clients/<slug>/data/, runs the Ad Waste Audit and drafts
the delivery email (or the refund email if the guarantee applies).

Usage:
    python -m scripts.intake "Acme Plumbing Ltd" ~/Downloads/acme.csv --max-cpa 25 \
        --email jo@acme.co.uk --contact "Jo Smith" --monthly-spend 3000 --founding
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from scripts import ad_waste_audit, brand, clients, importers
from scripts.paid_media_rules import BudgetConfig


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-(ltd|limited|llp|plc)$", "", slug)
    return slug[:50].strip("-") or "client"


def _update_json(path: Path, changes: dict) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        node = raw
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_client(
    name: str,
    max_cpa: float,
    *,
    email: str = "",
    contact: str = "",
    website: str = "",
    monthly_spend: float | None = None,
    founding: bool = False,
    clients_dir: Path = clients.CLIENTS_DIR,
) -> clients.Client:
    if max_cpa <= 0:
        raise ValueError("--max-cpa must be greater than 0")
    slug = slugify(name)
    root = clients_dir / slug
    if not (root / "client.json").exists():
        clients.create(slug, name, clients_dir)
    _update_json(
        root / "client.json",
        {
            "name": name,
            "website": website,
            "contact.name": contact,
            "contact.email": email,
            "engagement.relationship": "client",
            "engagement.offer": "ad-waste-audit",
            "engagement.status": "active",
            "engagement.founding": founding,
        },
    )
    budgets = {
        "target_cpa": round(max_cpa, 2),
        # Judge an ad once it has spent twice the target with nothing to show, but never on pennies.
        "min_spend_to_judge": round(max(2 * max_cpa, 20.0), 2),
    }
    if monthly_spend:
        budgets["daily_cap"] = round(monthly_spend / 30, 2)
        budgets["monthly_cap"] = round(monthly_spend, 2)
    _update_json(root / "budgets.json", budgets)
    return clients.load(slug, clients_dir)


def delivery_email(audit: ad_waste_audit.Audit, client: clients.Client, b: brand.Brand) -> str:
    sym = audit.currency_symbol
    first = client.contact_name.split()[0] if client.contact_name else "there"
    money = ad_waste_audit._money
    if audit.addressable_waste < ad_waste_audit.GUARANTEE_THRESHOLD:
        return (
            f"Subject: Your {b.service_name} report, and your refund\n\n"
            f"Hi {first},\n\n"
            f"Your report for {client.name} is attached. The good news: we found {money(sym, audit.addressable_waste)} of "
            f"avoidable spend, which means your account is in good shape.\n\n"
            f"Because that's below our {b.price} guarantee, we've refunded your payment in full. "
            "It should reach your card within 5–10 working days.\n\n"
            "The report still lists the ads worth watching and where you could test more budget.\n\n"
            f"Best,\n{b.operator}\n"
        )
    walkthrough = f"\nWant to go through it together? Book 15 minutes here: {b.walkthrough_url}\n" if b.walkthrough_url else ""
    top = audit.actions[0] if audit.actions else ""
    monthly = (
        f" That's roughly {money(sym, audit.monthly_waste_estimate)} a month at your current pace."
        if audit.monthly_waste_estimate
        else ""
    )
    return (
        f"Subject: Your {b.service_name} report: {money(sym, audit.addressable_waste)} of avoidable spend found\n\n"
        f"Hi {first},\n\n"
        f"Your {b.service_name} report for {client.name} is attached.\n\n"
        f"In short: {money(sym, audit.addressable_waste)} of the {money(sym, audit.total_spend)} you spent "
        f"({audit.waste_share:.0%}) went to ads with no conversions or a cost per conversion well above your "
        f"{money(sym, audit.target_cpa)} target.{monthly}\n\n"
        f"The first thing to do: {top}\n\n"
        "Nothing changes in your account unless you decide. The last page has an approval checklist "
        "if you'd like us to help with the changes.\n"
        f"{walkthrough}\n"
        f"Best,\n{b.operator}\n"
    )


def run(export_path: Path, client: clients.Client, days: int | None = None) -> tuple[ad_waste_audit.Audit, Path, Path]:
    client.data_dir.mkdir(parents=True, exist_ok=True)
    stored = client.data_dir / export_path.name
    if export_path.resolve() != stored.resolve():
        shutil.copy2(export_path, stored)
    cfg = BudgetConfig.load(client.budgets_path, currency=client.currency_symbol)
    audit = ad_waste_audit.analyse(importers.load(stored), client, cfg, days=days)
    html_path, _ = ad_waste_audit.write(audit, client, client.reports_dir)
    email_path = client.reports_dir / f"email-{audit.generated_at}.txt"
    email_path.write_text(delivery_email(audit, client, brand.load()), encoding="utf-8")
    return audit, html_path, email_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a booking-form submission into a ready-to-send audit")
    parser.add_argument("name", help="business name, as entered in the booking form")
    parser.add_argument("export", type=Path, help="the CSV they uploaded")
    parser.add_argument("--max-cpa", type=float, required=True, help="most they'd happily pay for one sale or lead")
    parser.add_argument("--email", default="")
    parser.add_argument("--contact", default="", help="contact person's name")
    parser.add_argument("--website", default="")
    parser.add_argument("--monthly-spend", type=float, help="their stated monthly ad spend")
    parser.add_argument("--days", type=int, help="reporting period, if the export has no dates")
    parser.add_argument("--founding", action="store_true", help="founding client (free 30-day re-audit)")
    args = parser.parse_args(argv)

    if not args.export.exists():
        print(f"error: file not found: {args.export}", file=sys.stderr)
        return 1
    try:
        client = prepare_client(
            args.name,
            args.max_cpa,
            email=args.email,
            contact=args.contact,
            website=args.website,
            monthly_spend=args.monthly_spend,
            founding=args.founding,
        )
        audit, html_path, email_path = run(args.export, client, days=args.days)
    except (clients.ClientError, importers.ImportErrorWithHint, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sym = audit.currency_symbol
    refund = audit.addressable_waste < ad_waste_audit.GUARANTEE_THRESHOLD
    print(f"client:  {client.slug}")
    money = ad_waste_audit._money
    print(f"result:  {money(sym, audit.addressable_waste)} avoidable of {money(sym, audit.total_spend)}")
    print(f"report:  {html_path}   (open, check, then Ctrl+P → Save as PDF)")
    print(f"email:   {email_path}")
    if refund:
        print("ACTION:  below the guarantee threshold, so refund the payment in Stripe before sending.")
    if args.founding:
        print("ACTION:  founding client, so set a reminder for the 30-day re-audit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
