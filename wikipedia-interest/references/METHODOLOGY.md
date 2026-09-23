# Methodology, limitations, and how to grow this skill

## What the metrics mean (computed in `scripts/analysis.py`)

All metrics are computed on the fetched monthly series **after** the trailing partial period is dropped.

- **growth_pct** — median of the last window vs the first window, as a %. The window is ~a quarter of
  the series, clamped to 1–3 points. Median (not mean) so a single spike doesn't distort it.
  `direction` = up / down / flat (|growth| < 10% reads as flat).
- **yoy_pct** — sum of the trailing 12 months vs the prior 12 months. Needs ≥24 monthly points.
  This cancels seasonality (same months compared), so it's the most reliable "is it growing" number.
- **trend_slope_per_period** and **trend_r2** — ordinary least-squares fit of views vs time.
  Slope is the per-month change; R² (0–1) is how well a straight line explains the series. High R²
  with a nonzero slope = a clean, believable trend; low R² = choppy, direction uncertain.
- **volatility_cv** — standard deviation / mean. High = erratic.
- **anomalies** — robust spike detection via the median absolute deviation (modified z-score > 3.5).
  Spikes are almost always a single news/event burst, not durable interest.
- **confidence** — a deliberately coarse **high / medium / low** with plain reasons, from:
  - absolute volume (`<50/mo` → low; `<200/mo` → medium): low traffic is noise-dominated;
  - series length (`<6` points → low; `<12` → medium): too little history to trust a trend;
  - completeness (missing months → medium);
  - anomaly share (>15% of points → medium): interest is event-driven;
  - trend R² (<0.2) is noted as a weak/uncertain direction;
  - `bot_share > 0.5` (only with `--check-bots`) → medium: raw traffic is crawler-heavy.
  It is a label, not a p-value — do not over-interpret it.

- **seasonality** (≥24 monthly points) — month-of-year means; reports `peak_month`, `low_month`, and
  `strength = (max_month_mean − min_month_mean) / overall_mean`. Use it so a recurring seasonal high
  isn't read as a trend (e.g. astronomy on uk peaks in September, low in July).
- **share_per_million_mean** (only with `--normalize`) — mean of `article_views / edition_total × 1e6`
  over matching periods, using the aggregate endpoint. Compares editions of very different sizes fairly:
  a small edition can hold a *larger share* of attention than a huge one (e.g. "English language" is
  ~46 views/M on en.wikipedia but ~137 on uk.wikipedia).
- **bot_share** (only with `--check-bots`) — `1 − user_total / all-agents_total` over matching periods.
  A data-quality diagnostic (the main numbers already use `agent=user`), not a change to the trend.

## How the skill helps you verify conclusions
- **Coverage is explicit.** Missing articles are `found:false` (`gap`), never silently substituted.
- **Partial period removed.** The latest incomplete month is dropped and reported in `dropped`.
- **Spikes are surfaced.** So a one-off event isn't mistaken for a trend.
- **Fair comparison.** The indexed-to-100 chart and growth % compare *shape*, not raw counts; with
  `--normalize`, share-of-attention (views per million) corrects for edition size directly.
- **Repeatability.** Responses are cached by request parameters, so refining a query (different period,
  languages, agent) is fast and cheap.

## Limitations (state these in reports)
- Pageviews are a proxy for **curiosity**, not market size, intent, or willingness to pay.
- Wikipedia's audience skews toward the connected, information-seeking public; it under-represents some
  demographics and over-represents others.
- Editions differ in size and internet habits — compare trends, not absolute counts.
- One article ≠ a whole topic. A concept may be spread across several articles, or an article may cover
  more than the topic. Check the resolved title.
- Redirects, article splits/merges, and renames can create artificial steps in a series.
- `agent=user` filters known bots but is imperfect; `--check-bots` quantifies the residual.
- Share-of-attention normalization assumes the aggregate total is a fair denominator; a viral edition-
  wide event can move the denominator too.
- History starts 2015-07; long-run baselines before that are unavailable.

## Growing the skill (iterative roadmap)
Delivered so far: multi-language resolution + candidate disambiguation (`--qid`), share-of-attention
normalization (`--normalize`), bot-inflation diagnostic (`--check-bots`), seasonality note. Still ahead,
in rough order of value:

1. **Topic discovery.** Use the `top` endpoint + Wikidata categories to *suggest* rising topics, not
   just analyze given ones. Add a `discover` command.
2. **Larger volumes & speed.** For many topics/languages, switch from per-request JSON to the Wikimedia
   pageview **dumps** / AQS bulk, loaded into a local **sqlite or parquet** store; batch and parallelize
   fetches; add a longer/warmed cache.
3. **Better statistics.** Seasonal decomposition (STL), change-point detection (was there a real
   inflection?), and simple forecasting with uncertainty bands. Significance tests on YoY.
4. **Portfolios.** Score and rank many topics × languages into a single opportunity matrix for the
   report, with a weighted "promise" score the user can tune.
5. **Corroboration.** Cross-check a signal with other free sources (Google Trends, app-store data) so a
   recommendation rests on more than pageviews.
6. **Report polish.** Themable templates, per-language small multiples, and an executive summary block.

Each step is additive: the CLI contract (JSON in/out, subcommands) stays stable so the agent workflow
doesn't change as capabilities grow.
