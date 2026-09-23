---
name: wikipedia-interest
description: >-
  Analyze Wikipedia pageviews as a proxy for audience interest to help decide which topics to build
  and which language markets to enter. Use when a user asks whether interest in a topic is growing or
  declining, wants to compare a topic across language editions (e.g. Polish vs Czech), asks how much a
  trend can be trusted, or wants a short shareable one-page PDF report on topic/market/language demand.
  Handles topics in any language, resolves the right article per Wikipedia edition, computes growth,
  trend and confidence, and generates charts + a PDF.
license: MIT
compatibility: Requires Python 3.12+ and uv (or pip). Needs internet access to the Wikimedia APIs.
metadata:
  version: "1.0"
---

# Wikipedia interest analysis

Turn a plain-language question about audience interest into a data-grounded answer using Wikimedia
pageview statistics. The Python code does all the data work and statistics; you just pick the command,
read the JSON it prints, and explain it.

## When to use
- "Is interest in <topic> growing in <language> Wikipedia?"
- "Compare interest in <topic> across <languages>."
- "How much can we trust this growth?"
- "Give me a one-page report I can share."

Always remind the user: **pageviews measure curiosity, not willingness to pay.** They are a first
signal to validate further, not proof of a market.

## Setup (once)
From the repo root, dependencies are managed with uv. Either rely on the project env (`uv run …`) or,
to run the skill standalone anywhere, the CLI carries inline deps so `uv run` auto-installs them.

## The one command you usually need
```
uv run wikipedia-interest/scripts/wikipop.py report \
  --topic "<topic>" --langs <l1,l2,...> --last 2y --out report.pdf
```
This resolves article titles, fetches pageviews, analyzes, writes `report.pdf` + `report.png`, and
prints a JSON summary. Narrate the JSON; point the user to the PDF.

Languages are Wikipedia edition codes: `uk` (Ukrainian), `pl` (Polish), `cs` (Czech), `en` (English),
`de`, `es`, … Comma-separated, no spaces.

## Recommended workflow
1. **Resolve first** if unsure the concept exists in each language:
   ```
   uv run wikipedia-interest/scripts/wikipop.py resolve --topic "<topic>" --langs <l1,l2,...>
   ```
   Check each `found`/`method`. `method:"gap"` = the concept exists on Wikidata but that edition has no
   article (a real coverage gap — say so, don't compare it). `method:"search"` = weaker match found by
   text search (no Wikidata concept); treat with lower confidence and consider verifying the title.
   **Disambiguate ambiguous topics.** The output has a `candidates` list (Wikidata id + label +
   description). If the auto-picked concept is wrong (e.g. "mercury" → the Ford car marque, not the
   planet), re-run with `--qid Q308` to pin the right concept. Pass the same `--qid` to `analyze`/`report`.
2. **Analyze** (fast, no files) for a first read or follow-ups:
   ```
   uv run wikipedia-interest/scripts/wikipop.py analyze --topic "<topic>" --langs <...> --last 2y
   ```
3. **Report** when the user wants something shareable (adds the PDF/PNG).

## How to read the output
Per language you get `metrics`:
- `direction` (up/down/flat) + `growth_pct`: median of the last window vs the first window.
- `yoy_pct`: trailing 12 months vs prior 12 (seasonality-aware; needs ≥24 monthly points).
- `trend_slope_per_period` + `trend_r2`: slope and how well a straight line fits (R² near 1 = clean
  trend; near 0 = choppy/uncertain).
- `mean_views`, `total_views`, `latest_views`.
- `anomalies`: spike dates — usually a news/event burst, **not** organic growth.
- `confidence`: `label` (high/medium/low) + `reasons`. Lead your answer with this. Low confidence
  means low volume, short/gappy history, or spike-driven — say the signal is weak.
- `dropped`: the latest partial period the tool removed (kept out to avoid a fake drop).
- `seasonality` (≥24 months): `peak_month`/`low_month`/`strength`. Mention recurring peaks so a
  seasonal high isn't read as a trend.
- `share_per_million_mean` (only with `--normalize`): article views per **million** of that edition's
  total pageviews. Use this to compare across editions of very different sizes fairly — it can flip a
  raw-count ranking (a small edition can have a larger *share* of attention).
- `bot_share` (only with `--check-bots`): fraction of raw traffic that is non-human. High (>0.5) means
  the topic is crawler-heavy; note it as a data-quality caveat.
- Top-level `candidates`/`qid`: the resolved concept and its alternatives (for disambiguation).

## Common refinements (repeat/related queries are cheap — results are cached)
- Change window: `--last 3y`, `--last 18m`, or `--start YYYYMMDD --end YYYYMMDD`.
- Add/remove languages: edit `--langs`.
- Pin a concept: `--qid Q308` (from the `candidates` list) on `resolve`/`analyze`/`report`.
- Fair cross-edition comparison: add `--normalize` (share of attention per million).
- Flag bot-heavy topics: add `--check-bots` (one extra request per language).
- Include bots or a device split: `--agent all-agents` (default `user` excludes bots), or
  `--access mobile-web|desktop`.
- Daily detail: `--granularity daily` (better for short, recent windows).
- Provide your own narrative in the PDF: `--note "..."`.
- Inspect one article directly: `wikipop.py pageviews --lang uk --article "Астрономія" --start 20230101 --end 20250101`.

## Sanity checks before you conclude
- Did the resolved concept match the intended meaning? Check `candidates`; pin with `--qid` if not.
- Did every language resolve? Report gaps explicitly.
- Comparing editions of very different sizes? Prefer `--normalize` (share of attention).
- Is `mean_views` tiny (<~200/mo)? Trends are noisy — lower your confidence.
- Are there spikes (`anomalies`)? Don't call a one-month spike "growth".
- Compare **shape** (indexed chart / growth %), not absolute counts, across editions of different sizes.

## More detail
- `references/API.md` — the Wikimedia endpoints, parameters and gotchas.
- `references/METHODOLOGY.md` — exactly how growth/trend/confidence are computed, limitations, and how
  to grow this skill for bigger/harder research.
- `examples.md` — the canonical example questions mapped to exact commands.
