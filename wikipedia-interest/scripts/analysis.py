"""Analysis engine: turn a pageview time series into decision-ready metrics + a trust judgment.

Pure functions over a `Series` (dates + views). No I/O, no third-party imports. The point of this
module is that the *code* computes growth, trend strength, seasonality-aware change, anomalies,
and a coarse confidence label — so a small model never has to do statistics itself.
"""
from __future__ import annotations

import math
from statistics import fmean, median, pstdev

from series import Series

FLAT_THRESHOLD_PCT = 10.0  # |change| below this reads as "flat"
SEASONAL_NOTE_STRENGTH = 0.5  # month-of-year swing (share of mean traffic) worth warning about
SEASONAL_RISK_MIN_CV = 0.25  # volatility proxy, used when a series is too short to measure season
DAYS_PER_MONTH = 30.44  # for putting daily series on the same scale as monthly ones
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _ols(y: list[float]) -> tuple[float, float]:
    """Least-squares line fit of `y` against 0..n-1. Returns (slope, intercept).

    Closed-form normal equations — exact for a degree-1 fit, and the series here is at most a
    few hundred points, so there is nothing for a matrix solver to add.
    """
    n = len(y)
    x_bar = (n - 1) / 2.0
    y_bar = fmean(y)
    s_xx = sum((i - x_bar) ** 2 for i in range(n))
    s_xy = sum((i - x_bar) * (v - y_bar) for i, v in enumerate(y))
    slope = s_xy / s_xx if s_xx > 0 else 0.0
    return slope, y_bar - slope * x_bar


def share_per_million(s: Series, agg: Series) -> "float | None":
    """Mean share-of-attention: article views per million of the edition's total pageviews.

    Aligns on matching periods so editions of very different sizes compare fairly.
    """
    if s is None or s.empty or agg is None or agg.empty:
        return None
    totals = agg.as_map()
    ratios = [v / totals[d] * 1_000_000.0
              for d, v in zip(s.dates, s.views)
              if d in totals and totals[d] > 0]
    if not ratios:
        return None
    return _round(fmean(ratios), 2)


def bot_share(user_s: Series, all_s: Series) -> "float | None":
    """Fraction of traffic that is non-human (1 - user/all-agents), over matching periods.

    A high value means the topic's raw traffic is bot/crawler-heavy; the default `user` numbers
    already exclude bots, so this is a data-quality diagnostic.
    """
    if user_s is None or user_s.empty or all_s is None or all_s.empty:
        return None
    all_map = all_s.as_map()
    pairs = [(v, all_map[d]) for d, v in zip(user_s.dates, user_s.views) if d in all_map]
    all_total = float(sum(a for _, a in pairs))
    if all_total <= 0:
        return None
    return _round(1.0 - sum(u for u, _ in pairs) / all_total, 2)


def _seasonality(s: Series) -> "dict | None":
    """Month-of-year pattern for series with >=24 monthly points. None otherwise.

    The linear trend is removed before grouping by month: otherwise a steadily rising or falling
    series leaks its trend into the month-of-year means and a clean ramp reads as "seasonal"
    (its last months are simply bigger than its first ones). `strength` is the peak-to-low swing
    of the detrended pattern, as a share of overall mean traffic.
    """
    if len(s) < 24:
        return None
    y = [float(v) for v in s.views]
    overall = fmean(y)
    if overall <= 0:
        return None
    slope, intercept = _ols(y)
    by_month: dict[int, list[float]] = {}
    for i, (d, v) in enumerate(zip(s.dates, y)):
        by_month.setdefault(d.month, []).append(v - (slope * i + intercept))
    if not by_month:
        return None
    means = {m: fmean(vals) for m, vals in by_month.items()}
    # Ascending month order with strict comparisons reproduces first-wins tie-breaking.
    peak_m = low_m = min(means)
    for m in sorted(means):
        if means[m] > means[peak_m]:
            peak_m = m
        if means[m] < means[low_m]:
            low_m = m
    strength = (means[peak_m] - means[low_m]) / overall
    return {"peak_month": _MONTHS[peak_m - 1], "low_month": _MONTHS[low_m - 1],
            "strength": _round(strength, 2)}


def _round(x, n=1):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def _window(n: int) -> int:
    """Comparison window for first-vs-last means: ~a quarter of the series, clamped to [1, 3]."""
    return max(1, min(3, n // 3)) if n >= 3 else 1


def _growth_pct(s: Series) -> tuple:
    # Median of the window (not mean) so a single event spike doesn't distort the comparison.
    n = len(s)
    w = _window(n)
    first = median(s.views[:w])
    last = median(s.views[-w:])
    if first <= 0:
        pct = None if last <= 0 else float("inf")
    else:
        pct = (last - first) / first * 100.0
    return pct, first, last, w


def _windows_share_months(s: Series, w: int) -> bool:
    """Do the first and last growth windows cover any of the same calendar months?

    If they don't, `growth_pct` is comparing one season against another (e.g. autumn vs summer)
    and a seasonal swing shows up as "growth" or "decline".
    """
    first = {d.month for d in s.dates[:w]}
    last = {d.month for d in s.dates[-w:]}
    return bool(first & last)


def _classify(pct) -> str:
    """up / down / flat / n/a from a percentage change."""
    if pct is None:
        return "n/a"
    if pct == float("inf") or pct > FLAT_THRESHOLD_PCT:
        return "up"
    if pct < -FLAT_THRESHOLD_PCT:
        return "down"
    return "flat"


def _trend(s: Series) -> tuple:
    """Linear fit views ~ time. Returns (slope_per_period, r2). R² = how well a line explains it."""
    n = len(s)
    if n < 2:
        return None, None
    y = [float(v) for v in s.views]
    slope, intercept = _ols(y)
    y_bar = fmean(y)
    ss_res = sum((v - (slope * i + intercept)) ** 2 for i, v in enumerate(y))
    ss_tot = sum((v - y_bar) ** 2 for v in y)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2


def _yoy_pct(s: Series, granularity: str = "monthly") -> "float | None":
    """Trailing-12-months vs the prior 12 months (seasonality-aware). None if <24 monthly points.

    Monthly only: on a daily series the same arithmetic would compare 12 *days* against the 12
    before them, which is not a year-over-year comparison and must never back `direction`.
    """
    if granularity != "monthly" or len(s) < 24:
        return None
    last12 = sum(s.views[-12:])
    prev12 = sum(s.views[-24:-12])
    if prev12 <= 0:
        return None
    return (last12 - prev12) / prev12 * 100.0


def _anomalies(s: Series) -> list:
    """Robust spike detection via MAD. Points >~3.5 modified z-scores above the median.

    Spikes usually mean a news/event burst, not organic interest — reported so callers don't
    mistake them for a trend.
    """
    y = [float(v) for v in s.views]
    if len(y) < 4:
        return []
    med = median(y)
    mad = median([abs(v - med) for v in y])
    if mad == 0:
        return []
    out = []
    for i, v in enumerate(y):
        if 0.6745 * (v - med) / mad > 3.5:
            out.append({
                "date": s.dates[i].strftime("%Y-%m-%d"),
                "views": int(v),
                "x_median": _round(v / med if med else None, 1),
            })
    return out


def _expected_points(s: Series, granularity: str) -> int:
    if s.empty:
        return 0
    start, end = s.dates[0], s.dates[-1]
    if granularity == "monthly":
        return (end.year - start.year) * 12 + (end.month - start.month) + 1
    return (end - start).days + 1


def _confidence(metrics: dict, granularity: str = "monthly",
                seasonal_window_risk: bool = False) -> dict:
    """Coarse high/medium/low label with plain-language reasons. Deliberately not a fake score.

    Volume and length thresholds are expressed in **monthly-equivalent** terms, so a daily series
    is judged on the same scale as a monthly one (a daily mean of 3 views is ~96 views/month, not
    "<50 views/mo"). `seasonal_window_risk` says the growth windows straddle different seasons.
    """
    reasons = []
    score = 2  # 2 high, 1 medium, 0 low
    daily = granularity == "daily"

    mean = metrics["mean_views"]
    n = metrics["n_points"]
    missing = metrics["missing_points"]
    expected = metrics["expected_points"]
    r2 = metrics["trend_r2"]
    cv = metrics["volatility_cv"]
    anom = metrics["anomaly_count"]
    basis = metrics["direction_basis"]
    seas = metrics.get("seasonality")

    # Volume, on a monthly-equivalent scale.
    per_month = None if mean is None else (mean * DAYS_PER_MONTH if daily else mean)
    if per_month is not None and per_month < 50:
        score = min(score, 0)
        reasons.append(
            f"Very low traffic (~{per_month:.0f} views/month equivalent): the signal is mostly noise."
            if daily else
            "Very low traffic (<50 views/mo on average): the signal is mostly noise.")
    elif per_month is not None and per_month < 200:
        score = min(score, 1)
        reasons.append(
            f"Low traffic (~{per_month:.0f} views/month equivalent): treat trend size cautiously."
            if daily else
            "Low traffic (<200 views/mo on average): treat trend size cautiously.")

    # Length: observations (enough points to fit anything?) and calendar span (a full year?).
    span_months = expected / DAYS_PER_MONTH if daily else expected
    if n < 6:
        score = min(score, 0)
        reasons.append(f"Very short series ({n} points): not enough history to judge a trend.")
    elif span_months < 12:
        score = min(score, 1)
        reasons.append("Under a year of data: seasonal effects can't be separated yet.")

    # Completeness. A missing month is a real coverage hole; an absent *day* is usually just a
    # genuine zero-traffic day (the API omits those), so daily series need a material share.
    if missing > 0 and (not daily or (expected > 0 and missing / expected > 0.10)):
        score = min(score, 1)
        reasons.append(f"{missing} missing period(s): coverage has gaps.")

    if n > 0 and anom / n > 0.15:
        score = min(score, 1)
        reasons.append("Frequent spikes: interest looks event-driven, not steadily organic.")

    # Straight-line fit. Only meaningful on a series that actually varies — a perfectly even
    # series has no variance to explain and `trend_r2` is 0 there by convention, not by failure.
    if r2 is not None and r2 < 0.2 and cv is not None and cv > 0.05:
        if basis == "yoy":
            reasons.append("Choppy series (low R²): no straight-line trend, but `direction` comes "
                           "from the year-over-year comparison, which still holds.")
        else:
            score = min(score, 1)
            reasons.append("Weak linear trend (low R²): the direction is uncertain / choppy.")

    # Seasonality vs the growth window: the first and last windows are different calendar months,
    # so a recurring seasonal swing can masquerade as growth or decline.
    if seasonal_window_risk:
        if basis == "yoy":
            # Seasonality is measured here, so judge on it directly.
            if seas and (seas.get("strength") or 0) >= SEASONAL_NOTE_STRENGTH:
                reasons.append(
                    f"Seasonal pattern (peaks {seas['peak_month']}, lows {seas['low_month']}): "
                    "`growth_pct` compares different calendar months, so quote `yoy_pct` as the change.")
        elif n >= 12 and cv is not None and cv >= SEASONAL_RISK_MIN_CV:
            # Under 24 months seasonality can't be measured; an uneven series is the warning sign.
            score = min(score, 1)
            reasons.append(
                "`growth_pct` compares different calendar months and there is under 24 months of "
                "history to measure seasonality: the size, and possibly the sign, may be seasonal.")

    bs = metrics.get("bot_share")
    if bs is not None and bs > 0.5:
        score = min(score, 1)
        reasons.append(f"{bs:.0%} of raw traffic is non-human (bots/crawlers): interpret demand with care.")

    if not reasons:
        reasons.append("Sufficient volume, length, completeness and a clear trend.")

    return {"label": {2: "high", 1: "medium", 0: "low"}[score], "reasons": reasons}


def analyze_series(s: Series, granularity: str = "monthly",
                   share: "float | None" = None, bot_share: "float | None" = None) -> dict:
    """Compute all metrics for one series. Returns a JSON-serializable dict.

    Optional `share` (views per million of edition total) and `bot_share` are folded in when the
    caller has fetched the extra data (--normalize / --check-bots).

    Empty input -> {"available": False} so callers report "no data" instead of crashing.
    """
    if s is None or s.empty:
        return {"available": False}

    n = len(s)
    y = [float(v) for v in s.views]
    mean = fmean(y)
    std = pstdev(y)
    pct, first_med, last_med, w = _growth_pct(s)
    slope, r2 = _trend(s)
    yoy = _yoy_pct(s, granularity)
    anomalies = _anomalies(s)
    expected = _expected_points(s, granularity)
    missing = max(0, expected - n)
    cv = std / mean if mean > 0 else None

    # `direction` prefers the year-over-year comparison, which compares the same calendar months
    # and so cannot be flipped by seasonality. `growth_pct` (start window vs end window) is only
    # the fallback, for series too short for YoY. `direction_basis` says which number backs it.
    if yoy is not None:
        direction, direction_basis = _classify(yoy), "yoy"
    else:
        direction = _classify(pct)
        direction_basis = "growth" if direction != "n/a" else "n/a"

    # Does `growth_pct` compare one season against another? Only a monthly-granularity question;
    # how much that matters is judged in _confidence (measured seasonality when we have 24 months,
    # volatility as a proxy when we don't).
    seasonal_window_risk = granularity == "monthly" and not _windows_share_months(s, w)

    metrics = {
        "available": True,
        "n_points": n,
        "date_start": s.dates[0].strftime("%Y-%m-%d"),
        "date_end": s.dates[-1].strftime("%Y-%m-%d"),
        "total_views": int(sum(s.views)),
        "mean_views": _round(mean, 1),
        "latest_views": int(s.views[-1]),
        "growth_pct": _round(pct, 1) if pct not in (None, float("inf")) else (None if pct is None else "inf"),
        "growth_window": w,
        "growth_first_median": _round(first_med, 1),
        "growth_last_median": _round(last_med, 1),
        "direction": direction,
        "direction_basis": direction_basis,
        "trend_slope_per_period": _round(slope, 2),
        "trend_r2": _round(r2, 3),
        "yoy_pct": _round(yoy, 1),
        "volatility_cv": _round(cv, 2),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "expected_points": expected,
        "missing_points": missing,
        "seasonality": _seasonality(s) if granularity == "monthly" else None,
        "share_per_million_mean": share,
        "bot_share": bot_share,
    }
    metrics["confidence"] = _confidence(metrics, granularity, seasonal_window_risk)
    return metrics
