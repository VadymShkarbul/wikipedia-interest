# Methodology, limitations, and how to grow this skill

## What the metrics mean (computed in `scripts/analysis.py`)

All metrics are computed on **complete** periods only. The trailing partial period is dropped
(`trim_partial_tail`), and a monthly `--last` window is snapped back to the 1st of the month, because
a window starting mid-month makes the API return a truncated first bucket — which would understate
the very baseline `growth_pct` and `yoy_pct` are measured against.

- **growth_pct** — median of the last window vs the first window, as a %. The window is ~a quarter of
  the series, clamped to 1–3 points. Median (not mean) so a single spike doesn't distort it.
  **Caveat:** unless the series length happens to make the two windows the same calendar months,
  this compares one season against another. On a seasonal topic that inflates the change or invents
  one — a flat topic peaking in autumn reads ≈ −34% when the window ends in summer.
- **yoy_pct** — sum of the trailing 12 months vs the prior 12 months. Needs ≥24 monthly points.
  This cancels seasonality (same months compared), so it's the most reliable "is it growing" number.
- **direction** (up / down / flat, |change| < 10% reads as flat) and **direction_basis** — the
  headline verdict and the number behind it. `yoy` when `yoy_pct` exists (preferred: seasonality
  cannot flip it), otherwise `growth` from `growth_pct`. Report the change using the number the
  basis names; the two disagreeing is the seasonal artefact, not a second opinion.
- **trend_slope_per_period** and **trend_r2** — ordinary least-squares fit of views vs time.
  Slope is the per-month change; R² (0–1) is how well a straight line explains the series. High R²
  with a nonzero slope = a clean, believable trend; low R² = choppy, direction uncertain.
- **volatility_cv** — standard deviation / mean. High = erratic.
- **anomalies** — robust spike detection via the median absolute deviation (modified z-score > 3.5).
  Spikes are almost always a single news/event burst, not durable interest.
- **confidence** — a deliberately coarse **high / medium / low** with plain reasons. Volume and
  length thresholds are **monthly-equivalent** (a daily mean is scaled by 30.44), so the same rules
  judge `--granularity daily` and monthly runs on one scale:
  - volume (`<50/mo` → low; `<200/mo` → medium): low traffic is noise-dominated;
  - observations (`<6` points → low): not enough to fit anything;
  - calendar span (`<12 months` → medium): seasonal effects can't be separated yet — this is why a
    90-day daily run tops out at medium;
  - completeness (a missing **month** → medium; for daily, only if >10% of days are absent, since
    the API simply omits zero-traffic days);
  - anomaly share (>15% of points → medium): interest is event-driven;
  - trend R² (<0.2, on a series that actually varies): **→ medium when `direction_basis` is
    `growth`**, because the direction is then read off that weak line. When the basis is `yoy` it is
    reported as "choppy" without a downgrade — the year comparison still holds. A perfectly even
    series is exempt: its R² is 0 by convention, not by failure;
  - seasonal growth window (the first and last windows are different calendar months): if
    seasonality is measurable and `strength ≥ 0.5`, a note to quote `yoy_pct`; if the series is
    12–23 months (seasonality unmeasurable) and uneven (`cv ≥ 0.25`) → **medium**, since the size
    and even the sign of `growth_pct` may be seasonal;
  - `bot_share > 0.5` (only with `--check-bots`) → medium: raw traffic is crawler-heavy.
  It is a label, not a p-value — do not over-interpret it.

- **seasonality** (≥24 monthly points) — month-of-year means of the **detrended** series (the linear
  fit is removed first, otherwise a steady rise leaks in and a clean ramp looks seasonal); reports
  `peak_month`, `low_month`, and `strength = (max_month − min_month) / overall_mean`. Use it so a
  recurring seasonal high isn't read as a trend (e.g. astronomy on uk peaks in September, low in July).
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
- **Seasonality can't fake a trend.** The headline `direction` comes from the like-for-like year
  comparison whenever there's enough history, and `direction_basis` says so; when there isn't,
  confidence drops instead of asserting a seasonal swing as growth.
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
normalization (`--normalize`), bot-inflation diagnostic (`--check-bots`), seasonality note. In v2 the
analysis engine dropped pandas/numpy/requests for the standard library, the report became
self-contained HTML with inline SVG (no renderer dependency at all — browsers print it to PDF),
the narrative moved to
the model while the confidence caveat stayed in code, and a typed MCP tool surface replaced the need
for shell access. Still ahead, in rough order of value:

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

Each step is additive: both front doors (the CLI's JSON in/out and the MCP tool schemas) stay stable,
so the agent workflow doesn't change as capabilities grow. Note the constraint v2 introduces — the
core must keep running on the standard library alone, so step 2's parquet/sqlite store and step 3's
STL belong behind an optional extra, the way PDF output already is.
