---
name: wikipedia-interest
description: >-
  Analyze Wikipedia pageviews as a proxy for audience interest to help decide which topics to build
  and which language markets to enter. Use when a user asks whether interest in a topic is growing or
  declining, wants to compare a topic across language editions (e.g. Polish vs Czech), asks how much a
  trend can be trusted, or wants a short shareable one-page report on topic/market/language demand.
  Handles topics in any language, resolves the right article per Wikipedia edition, computes growth,
  trend and confidence, and generates charts + a report.
license: MIT
compatibility: Requires Python 3.12+. Needs internet access to the Wikimedia APIs. No API key.
metadata:
  version: "2.0"
---

# Wikipedia interest analysis

Turn a plain-language question about audience interest into a data-grounded answer using Wikimedia
pageview statistics. **The code does the statistics; you orchestrate and narrate.** Never compute
growth, trend or confidence yourself — read them from the output.

## When to use
- "Is interest in <topic> growing in <language> Wikipedia?"
- "Compare interest in <topic> across <languages>."
- "How much can we trust this growth?"
- "Give me a one-page report I can share."

Always remind the user: **pageviews measure curiosity, not willingness to pay.** They are a first
signal to validate further, not proof of a market.

## How to call it

One command-line tool, four commands: `resolve`, `analyze`, `report`, `pageviews`. It needs no
installation — the whole skill runs on the Python 3.12 standard library — and prints exactly one
JSON object per run. Paths below are relative to this skill's directory; run from here, or use an
absolute path:

```
python3 scripts/wikipop.py analyze --topic "<topic>" --langs uk,pl --last 2y
```

Languages are Wikipedia edition codes: `uk`, `pl`, `cs`, `en`, `de`, `es`, … comma-separated.

## Recommended workflow

1. **Resolve first** when the topic is ambiguous or may be missing from an edition.
   → `resolve --topic "<t>" --langs uk,pl`

   Check each `found` / `method`:
   - `method:"wikidata"` — exact concept match. Good.
   - `method:"gap"` — the concept exists but that edition has **no article**. A real coverage gap:
     say so, don't compare it.
   - `method:"search"` — weaker text-search match. Lower confidence; consider verifying the title.

   **Disambiguate.** The output has `candidates` (Wikidata id + label + description). If the
   auto-pick is wrong ("mercury" → the Ford marque, not the planet), re-run pinned with `--qid Q308`.
   Pass the same `--qid` to analyze/report.

2. **Analyze** — the main step. → `analyze --topic "<t>" --langs uk,pl --last 2y`

3. **Report** only when the user wants something shareable.
   → `report --topic "<t>" --langs uk,pl --last 2y --out report.html --findings "<your narrative>"`

   **You write `--findings`** — what the numbers mean and what to do next, in the user's language.
   The code appends the confidence label and leading caveat for every edition itself, so the file
   can't be forwarded without them. Don't invent numbers; base the narrative on the analyze output.
   The result is a self-contained `.html` one-pager; tell the user where it was written, and that
   opening it and choosing Print → Save as PDF gives them a one-page PDF to send on.

## How to read the output

Per language you get `metrics`:

- `direction` (up/down/flat) + `direction_basis` — **the verdict, and which number backs it.**
  `basis:"yoy"` → quote `yoy_pct`. `basis:"growth"` → quote `growth_pct`.
  **Quote the number the basis names, not the other one.**
- `yoy_pct` — trailing 12 months vs the prior 12. Compares the same calendar months, so seasonality
  can't flip it. Needs ≥24 monthly points.
- `growth_pct` — median of the last window vs the first window. Those are usually *different calendar
  months*, so on a seasonal topic it exaggerates or invents a change (a flat topic peaking in autumn
  reads as "-34%" when the window ends in summer). Never lead with it when the basis is `yoy`.
- `confidence` — `label` (high/medium/low) + `reasons`. **Lead your answer with this** and pass the
  reasons on; they name the specific caveat. Thresholds are monthly-equivalent, so a `daily` run is
  judged on the same scale as a monthly one.
- `trend_slope_per_period`, `trend_r2` — slope, and how well a straight line fits. Low R² on a
  seasonal topic is normal, not a problem.
- `mean_views`, `total_views`, `latest_views`, `volatility_cv`.
- `anomalies` — spike dates. Usually a news/event burst, **not** organic growth.
- `dropped` — the latest partial period, removed so a half-finished month isn't read as a decline.
- `seasonality` (≥24 months) — `peak_month` / `low_month` / `strength`. Mention recurring peaks.
- `share_per_million_mean` (with `--normalize`) — views per **million** of that edition's total
  traffic. Use it to compare editions of very different sizes; it can flip a raw-count ranking.
- `bot_share` (with `--check-bots`) — fraction of raw traffic that is non-human. >0.5 is a caveat.
- Top-level `candidates` / `qid` — the resolved concept and its alternatives.

## Refinements (repeats are cheap — responses are cached)
- Window: `--last 3y` / `--last 18m`, or explicit `--start` + `--end` (`YYYYMMDD`).
- Pin a concept: `--qid Q308`.
- Fair cross-edition comparison: `--normalize`.
- Flag crawler-heavy topics: `--check-bots`.
- Recent detail: `--granularity daily` with a short window.

## Sanity checks before you conclude
- Did the resolved concept match the intended meaning? Check `candidates`; pin with `qid` if not.
- Did every language resolve? Report gaps explicitly instead of comparing nothing.
- Quoting a change? Use the number `direction_basis` names. A `growth_pct` that disagrees with
  `direction` is the seasonal artefact, not a second opinion.
- Comparing editions of very different sizes? Prefer `normalize`.
- Is `mean_views` tiny (<~200/mo)? Trends are noisy — lower your confidence.
- Spikes in `anomalies`? Don't call a one-month spike "growth".

## More detail
- `references/API.md` — the Wikimedia endpoints, parameters and gotchas.
- `references/METHODOLOGY.md` — exactly how each metric is computed, limitations, and how to grow
  this skill for bigger research.
- `examples.md` — canonical questions mapped to exact calls.
