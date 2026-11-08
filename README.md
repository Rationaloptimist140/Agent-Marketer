# Agent Marketer

A done-for-you AI marketing service, run by Crewlet. Clients send their data; Agent Marketer turns it into clear reports and safe, approved actions, starting with the **Ad Waste Audit**.

**The principle:** deterministic rules decide, LLMs draft and enrich, humans approve anything that spends money or goes public, and every automated decision is logged per client.

## What's here

| Path | What it is |
|---|---|
| `AGENT_PROMPT.md` | System prompt: identity, the service, client separation, 11 pillars, guardrails |
| `PILLARS.md` | Spec and build status for each pillar |
| `clients/` | One folder per engagement (`client.json` + `budgets.json`). `_template/` is the starting point |
| `scripts/clients.py` | Create, list and validate clients |
| `scripts/ad_waste_audit.py` | **Lead offer:** turns a Meta or Google Ads export into a branded, client-ready Ad Waste Audit (HTML + JSON) |
| `scripts/importers.py` | Reads Meta Ads Manager, Google Ads and generic CSV exports into one shape |
| `templates/ad_waste_audit.html` | Report design; edit freely without touching code |
| `scripts/intake.py` | One command from a booking-form submission to a ready-to-send report and drafted email |
| `brand.json` | Public name, price, links and colours: change here, everything follows |
| `site/` | Landing page template; `python -m scripts.build_site` writes `site/public/index.html` |
| `DELIVERY.md` | Client journey, one-time setup (Stripe, Tally, hosting), copy to paste, per-client checklist |
| `examples/` | Fictional demo export and the demo report it produces, for sales conversations |
| `scripts/paid_media_rules.py` | Pillar 1: proposes PAUSE / SCALE / HOLD per ad, with hard daily caps enforced in code |
| `scripts/seo_opportunities.py` | Pillar 2: ranks "shown but not clicked" Search Console queries into NEW_GUIDE / IMPROVE_PAGE |
| `scripts/decision_log.py` | Append-only JSONL log of every proposed, approved and executed action |
| `tests/` | Caps, approvals, client validation and isolation, logging, opportunity ranking |

## Onboarding a client

```bash
pip install -e ".[dev]"

python -m scripts.clients new acme-plumbing --name "Acme Plumbing"
# edit clients/acme-plumbing/client.json and budgets.json
python -m scripts.clients validate

# put their export in clients/acme-plumbing/data/ (git-ignored), then:
python -m scripts.ad_waste_audit clients/acme-plumbing/data/meta.csv --client acme-plumbing --log
# → clients/acme-plumbing/reports/ad-waste-audit-YYYY-MM-DD.html (open it, print to PDF, send)
```

## Ad Waste Audit

- **Input:** an ad-level export from Meta Ads Manager (Amount spent, Impressions, Link clicks, Results, Reporting starts/ends) or Google Ads (Cost, Impr., Clicks, Conversions). Formatted numbers, title lines and total rows are handled. Pass `--days` if the export has no dates.
- **Verdicts:** Pause (spend with zero conversions), Pause or fix (cost per conversion above `pause_cpa_multiple` × target), Scale with approval (well below target with enough conversions), Keep, Wait (below minimum spend).
- **Headline figure:** avoidable spend = zero-conversion spend + spend above what expensive ads' conversions were worth at target. Monthly projection and reinvestment uplift are labelled as estimates.
- **Approval checklist:** the client ticks what they want actioned. Nothing touches their ad account.
- **Demo:** `python -m scripts.ad_waste_audit examples/demo-meta-export.csv --client demo-coffee-roasters` (fictional client; reports show a "fictional data" banner).

Windows PowerShell: the same commands work; use `python -m pip install -e ".[dev]"` if `pip` is not on PATH.

## Client data stays out of git

`clients/*/data/`, `clients/*/reports/` and `clients/*/logs/` are git-ignored. Only each client's configuration is committed. Delete raw exports after delivery.

## Safety rules built into the code

- Total proposed daily budget can never exceed `daily_cap`; the best-CPA ads get headroom first.
- Anything that raises spend is always `requires_approval: true`.
- Pauses are auto-allowed only if `auto_pause_enabled` is set to `true`; it is off by default.
- Nothing is judged before it reaches `min_spend_to_judge` and `min_days_running`.
- The decision log refuses to record an action as `executed` if it needed approval and has no approver.
- Each client's decisions are written to that client's own log.

## Contributing

`main` is protected by convention: every change arrives as a PR from a feature branch and must pass CI (ruff + pytest).
