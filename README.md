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
python -m scripts.paid_media_rules clients/acme-plumbing/data/meta.csv --client acme-plumbing --log
```

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
