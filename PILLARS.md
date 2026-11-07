# The 11 Pillars — specs and build status

Each pillar is described by **Goal → Inputs → Output → MVP → Success metric → Guardrails**.
Status: `scaffolded` = code exists in this repo · `spec` = designed, not yet built.

| # | Pillar | Status | Stage it unlocks |
|---|--------|--------|------------------|
| 1 | Autonomous Paid Media Agent | scaffolded (`scripts/paid_media_rules.py`) | With ad budget |
| 2 | Programmatic SEO Engine | scaffolded (`scripts/seo_opportunities.py`) | Pre-traction |
| 3 | AI Creative Factory | spec | With ad budget |
| 4 | Competitor Ad Intelligence | spec | With ad budget |
| 5 | AI Visibility & Citation Engine | spec | Pre-traction |
| 6 | Voice-of-Customer Intelligence | spec | Pre-traction (start here) |
| 7 | Dynamic Message-Match Landing Pages | spec | With ad budget |
| 8 | Precision Conversion Tracking | spec | Before any paid spend |
| 9 | Behavioural Lifecycle Marketing | spec | With active users |
| 10 | True Incrementality Measurement | spec | With meaningful spend |
| 11 | Automated Reporting & Decision Systems | spec | Always on |

---

## 1. Autonomous Paid Media Agent
- **Goal:** move budget toward what works and stop waste quickly, within hard limits.
- **Inputs:** daily ad-level metrics (spend, impressions, clicks, conversions) from Meta / Google Ads; the client's `clients/<slug>/budgets.json`.
- **Output:** a ranked list of proposed actions (PAUSE / SCALE / HOLD / REFRESH_CREATIVE), each with a reason, logged to the decision log. Approved actions are applied via the ads API or browser.
- **MVP:** deterministic rules engine (built) → a weekly human-approved run → optionally auto-pause only.
- **Success metric:** blended cost per acquisition (CPA) against target; share of spend on ads that meet target.
- **Guardrails:** caps are enforced in code; anything that increases spend needs approval; nothing is judged before it reaches a minimum spend.

## 2. Programmatic SEO Engine
- **Goal:** capture search demand the incumbents ignore, one useful page at a time.
- **Inputs:** a Google Search Console performance export (query, page, clicks, impressions, CTR, position); later a structured dataset for templated pages (e.g. UK towns × courier routes for QuantaRoute).
- **Output:** a daily ranked opportunity list ("new guide" vs "improve existing page") → one drafted page → internal links from pages that already get traffic.
- **MVP:** opportunity finder (built) → a daily scheduled run that drafts one page for approval.
- **Success metric:** clicks from targeted queries 28 days after publishing; visitor-to-signup rate.
- **Guardrails:** a quality gate for every page (unique data, answers the query, no keyword stuffing); never bulk-publish.

## 3. AI Creative Factory
- **Goal:** test many hooks cheaply so winners are found by data, not taste.
- **Inputs:** VoC phrases (pillar 6), competitor patterns (4), brand kit.
- **Output:** a creative matrix (hook × angle × format × voice) with asset files and manifest; uses the existing *Make channel-native creative* and *creative-experiments* skills.
- **MVP:** 3 angles × 3 hooks of static ads + 1 short video for one product.
- **Success metric:** thumb-stop rate, CTR, then CPA per concept.
- **Guardrails:** AI people are never presented as real customers; follow platform AI-disclosure rules; claims must be substantiated.

## 4. Competitor Ad Intelligence
- **Goal:** learn what already works in the market before spending.
- **Inputs:** Meta Ad Library / Google Ads Transparency Center for named competitors.
- **Output:** a table of long-running ads (running 30+ days) with extracted pattern: hook, angle, offer, format, proof type; then *original* concepts for our product built on those patterns.
- **MVP:** a manual-trigger browser scan for 5 competitors per product.
- **Guardrails:** extract patterns only; never copy copy, assets, trademarks or brand look.

## 5. AI Visibility & Citation Engine
- **Goal:** be the answer AI assistants cite for our category questions.
- **Inputs:** a list of buyer questions (from VoC), current answers in ChatGPT / Perplexity / Google AI Overviews.
- **Output:** a monthly citation audit (who is cited, for which question) plus fixes: clear "what is X / X vs Y / pricing" pages, schema.org markup, `llms.txt`, factual listings on relevant directories.
- **MVP:** a 20-question audit for one product, then 3 page fixes.
- **Guardrails:** no fake reviews or astroturfing; only factual, verifiable claims.

## 6. Voice-of-Customer Intelligence
- **Goal:** write in the buyer's words, not ours.
- **Inputs:** public reviews of competitors (App Store, Play Store, G2, Trustpilot), Reddit/forum threads, our own support tickets and calls.
- **Output:** a phrase bank grouped by pain / desired outcome / objection / trigger moment, with frequency counts and source links.
- **MVP:** 200 reviews across 3 competitors for one product → one-page messaging brief.
- **Guardrails:** respect site terms; quote sparingly; never present a review as our own testimonial.

## 7. Dynamic Message-Match Landing Pages
- **Goal:** the page should finish the sentence the ad started.
- **Inputs:** UTM parameters / ad ID / search query; a variant map (headline, sub-headline, proof, CTA).
- **Output:** one landing page that swaps content by parameter, with a safe default.
- **MVP:** 3 variants keyed on `utm_content` for one product.
- **Success metric:** conversion rate by variant against the default.
- **Guardrails:** every variant stays truthful and consistent with the ad's claim.

## 8. Precision Conversion Tracking
- **Goal:** trustworthy numbers before spending money on ads.
- **Inputs:** the product's signup / purchase events.
- **Output:** an event dictionary, consent-gated browser tags, server-side events (Meta CAPI, GA4 Measurement Protocol, Google enhanced conversions) with event-ID deduplication, and a weekly tracking-health check.
- **MVP:** signup + purchase events for one product, verified end to end.
- **Guardrails:** UK GDPR / PECR consent first; hash personal data; no sensitive data.

## 9. Behavioural Lifecycle Marketing
- **Goal:** turn signups into active, paying users.
- **Inputs:** product events (signed up, activated, went quiet, hit limit).
- **Output:** 3–5 triggered flows (onboarding, activation nudge, win-back, upgrade), each with a 10–20% holdout.
- **MVP:** one onboarding flow with a holdout, on the cheapest suitable tool.
- **Guardrails:** opt-in only, easy unsubscribe, frequency caps.

## 10. True Incrementality Measurement
- **Goal:** know what marketing actually caused.
- **Inputs:** spend and outcome data by region and week.
- **Output:** geo-holdout test designs, a power check (can this budget detect the effect?), and later a lightweight MMM.
- **MVP:** a power calculator that tells the owner whether a test is worth running at current spend.
- **Guardrails:** be explicit about uncertainty; never report an underpowered result as a win.

## 11. Automated Reporting & Decision Systems
- **Goal:** one weekly page that says what happened and what to do next.
- **Inputs:** outputs of every active pillar plus the decision log.
- **Output:** a weekly report: results vs last week, spend vs cap, what the agent did and why, and the one recommended next test.
- **MVP:** a weekly scheduled run that reads the decision log and available metrics.
- **Guardrails:** never invent numbers; mark missing data as missing.
