# agent-marketer

Autonomous marketing systems for Crewlet's products: guardrailed agents, rules engines and scheduled loops across 11 pillars, from paid media and SEO to tracking, lifecycle and incrementality.

**The principle:** deterministic rules decide, LLMs draft and enrich, humans approve anything that spends money or goes public, and every automated decision is logged.

## What's here

| Path | What it is |
|---|---|
| `AGENT_PROMPT.md` | System prompt for the Agent Marketer (identity, 11 pillars, sequencing, guardrails) |
| `PILLARS.md` | Spec and build status for each pillar |
| `scripts/decision_log.py` | Append-only JSONL log of every proposed/approved/executed action |
| `scripts/paid_media_rules.py` | Pillar 1: proposes PAUSE / SCALE / HOLD per ad, with hard daily caps enforced in code |
| `scripts/seo_opportunities.py` | Pillar 2: ranks "shown but not clicked" Search Console queries into NEW_GUIDE / IMPROVE_PAGE |
| `config/*.example.json` | Budget limits and brand definitions; copy to `budgets.json` / `brands.json` (git-ignored) |
| `tests/` | 15 tests covering caps, approval rules, logging and opportunity ranking |

## Quick start

```bash
pip install -e ".[dev]"
pytest -q

# Paid media: propose actions from an ad-level metrics export
cp config/budgets.example.json config/budgets.json
python -m scripts.paid_media_rules metrics.csv config/budgets.json --brand QuantaRoute --log

# SEO: rank opportunities from a Search Console export (Performance > Queries + Pages > Export)
python -m scripts.seo_opportunities gsc_export.csv --top 10
```

Windows PowerShell: the same commands work; use `python -m pip install -e ".[dev]"` if `pip` is not on PATH.

## Safety rules built into the code

- Total proposed daily budget can never exceed `daily_cap`; the best-CPA ads get headroom first.
- Anything that raises spend is always `requires_approval: true`.
- Pauses are auto-allowed only if `auto_pause_enabled` is set to `true`; it is off by default.
- Nothing is judged before it reaches `min_spend_to_judge` and `min_days_running`.
- The decision log refuses to record an action as `executed` if it needed approval and has no approver.

## Roadmap

See `PILLARS.md`. Suggested order for a pre-traction product: Voice-of-Customer → tracking → daily SEO loop → AI visibility audit → weekly report. Paid media comes once tracking is verified and a budget is approved.
