"""Analysis engine: turn a pageview time series into decision-ready metrics + a trust judgment.

Pure functions over a DataFrame(date, views). No I/O. The point of this module is that the
*code* computes growth, trend strength, seasonality-aware change, anomalies, and a coarse
confidence label — so a small model never has to do statistics itself.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

FLAT_THRESHOLD_PCT = 10.0  # |growth| below this reads as "flat"
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def share_per_million(df: pd.DataFrame, agg: pd.DataFrame) -> "float | None":
    """Mean share-of-attention: article views per million of the edition's total pageviews.

    Aligns on matching periods so editions of very different sizes compare fairly.
    """
    if df is None or df.empty or agg is None or agg.empty:
        return None
    merged = df.merge(agg, on="date", how="inner")
    merged = merged[merged["total_views"] > 0]
    if merged.empty:
        return None
    ratio = merged["views"] / merged["total_views"] * 1_000_000.0
    return _round(float(ratio.mean()), 2)


def bot_share(user_df: pd.DataFrame, all_df: pd.DataFrame) -> "float | None":
    """Fraction of traffic that is non-human (1 - user/all-agents), over matching periods.

    A high value means the topic's raw traffic is bot/crawler-heavy; the default `user` numbers
    already exclude bots, so this is a data-quality diagnostic.
    """
    if user_df is None or user_df.empty or all_df is None or all_df.empty:
        return None
    merged = user_df.merge(all_df, on="date", how="inner", suffixes=("_user", "_all"))
    all_total = float(merged["views_all"].sum())
    if all_total <= 0:
        return None
    return _round(1.0 - float(merged["views_user"].sum()) / all_total, 2)


def _seasonality(df: pd.DataFrame) -> "dict | None":
    """Month-of-year pattern for series with >=24 monthly points. None otherwise."""
    if len(df) < 24:
        return None
    by_month = df.groupby(df["date"].dt.month)["views"].mean()
    overall = float(df["views"].mean())
    if overall <= 0 or by_month.empty:
        return None
    peak_m, low_m = int(by_month.idxmax()), int(by_month.idxmin())
    strength = (float(by_month.max()) - float(by_month.min())) / overall
    return {"peak_month": _MONTHS[peak_m - 1], "low_month": _MONTHS[low_m - 1],
            "strength": _round(strength, 2)}


def _round(x, n=1):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def _window(n: int) -> int:
    """Comparison window for first-vs-last means: ~a quarter of the series, clamped to [1, 3]."""
    return max(1, min(3, n // 3)) if n >= 3 else 1


def _growth_pct(df: pd.DataFrame) -> tuple:
    # Median of the window (not mean) so a single event spike doesn't distort the comparison.
    n = len(df)
    w = _window(n)
    first = df["views"].iloc[:w].median()
    last = df["views"].iloc[-w:].median()
    if first <= 0:
        pct = None if last <= 0 else float("inf")
    else:
        pct = (last - first) / first * 100.0
    return pct, first, last, w


def _trend(df: pd.DataFrame) -> tuple:
    """Linear fit views ~ time. Returns (slope_per_period, r2). R² = how well a line explains it."""
    n = len(df)
    if n < 2:
        return None, None
    x = np.arange(n, dtype=float)
    y = df["views"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return slope, r2


def _yoy_pct(df: pd.DataFrame) -> "float | None":
    """Trailing-12-months vs the prior 12 months (seasonality-aware). None if <24 monthly points."""
    if len(df) < 24:
        return None
    last12 = df["views"].iloc[-12:].sum()
    prev12 = df["views"].iloc[-24:-12].sum()
    if prev12 <= 0:
        return None
    return (last12 - prev12) / prev12 * 100.0


def _anomalies(df: pd.DataFrame) -> list:
    """Robust spike detection via MAD. Points >~3.5 modified z-scores above the median.

    Spikes usually mean a news/event burst, not organic interest — reported so callers don't
    mistake them for a trend.
    """
    y = df["views"].to_numpy(dtype=float)
    if len(y) < 4:
        return []
    med = float(np.median(y))
    mad = float(np.median(np.abs(y - med)))
    if mad == 0:
        return []
    mz = 0.6745 * (y - med) / mad
    out = []
    for i, score in enumerate(mz):
        if score > 3.5:
            out.append({
                "date": df["date"].iloc[i].strftime("%Y-%m-%d"),
                "views": int(y[i]),
                "x_median": _round(y[i] / med if med else None, 1),
            })
    return out


def _expected_points(df: pd.DataFrame, granularity: str) -> int:
    if df.empty:
        return 0
    start, end = df["date"].iloc[0], df["date"].iloc[-1]
    if granularity == "monthly":
        return (end.year - start.year) * 12 + (end.month - start.month) + 1
    return (end - start).days + 1


def _confidence(metrics: dict) -> dict:
    """Coarse high/medium/low label with plain-language reasons. Deliberately not a fake score."""
    reasons = []
    score = 2  # 2 high, 1 medium, 0 low

    mean = metrics["mean_views"]
    n = metrics["n_points"]
    missing = metrics["missing_points"]
    r2 = metrics["trend_r2"]
    anom = metrics["anomaly_count"]

    if mean is not None and mean < 50:
        score = min(score, 0)
        reasons.append("Very low traffic (<50 views/mo on average): the signal is mostly noise.")
    elif mean is not None and mean < 200:
        score = min(score, 1)
        reasons.append("Low traffic (<200 views/mo on average): treat trend size cautiously.")

    if n < 6:
        score = min(score, 0)
        reasons.append(f"Very short series ({n} points): not enough history to judge a trend.")
    elif n < 12:
        score = min(score, 1)
        reasons.append("Under a year of data: seasonal effects can't be separated yet.")

    if missing > 0:
        score = min(score, 1)
        reasons.append(f"{missing} missing period(s): coverage has gaps.")

    if n > 0 and anom / n > 0.15:
        score = min(score, 1)
        reasons.append("Frequent spikes: interest looks event-driven, not steadily organic.")

    if r2 is not None and r2 < 0.2:
        reasons.append("Weak linear trend (low R²): the direction is uncertain / choppy.")

    bs = metrics.get("bot_share")
    if bs is not None and bs > 0.5:
        score = min(score, 1)
        reasons.append(f"{bs:.0%} of raw traffic is non-human (bots/crawlers): interpret demand with care.")

    if not reasons:
        reasons.append("Sufficient volume, length, completeness and a clear trend.")

    return {"label": {2: "high", 1: "medium", 0: "low"}[score], "reasons": reasons}


def analyze_series(df: pd.DataFrame, granularity: str = "monthly",
                   share: "float | None" = None, bot_share: "float | None" = None) -> dict:
    """Compute all metrics for one series. Returns a JSON-serializable dict.

    Optional `share` (views per million of edition total) and `bot_share` are folded in when the
    caller has fetched the extra data (--normalize / --check-bots).

    Empty input -> {"available": False} so callers report "no data" instead of crashing.
    """
    if df is None or df.empty:
        return {"available": False}

    n = len(df)
    mean = float(df["views"].mean())
    std = float(df["views"].std(ddof=0))
    pct, first_med, last_med, w = _growth_pct(df)
    slope, r2 = _trend(df)
    yoy = _yoy_pct(df)
    anomalies = _anomalies(df)
    expected = _expected_points(df, granularity)
    missing = max(0, expected - n)

    if pct is None:
        direction = "n/a"
    elif pct == float("inf"):
        direction = "up"
    elif pct > FLAT_THRESHOLD_PCT:
        direction = "up"
    elif pct < -FLAT_THRESHOLD_PCT:
        direction = "down"
    else:
        direction = "flat"

    metrics = {
        "available": True,
        "n_points": n,
        "date_start": df["date"].iloc[0].strftime("%Y-%m-%d"),
        "date_end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
        "total_views": int(df["views"].sum()),
        "mean_views": _round(mean, 1),
        "latest_views": int(df["views"].iloc[-1]),
        "growth_pct": _round(pct, 1) if pct not in (None, float("inf")) else (None if pct is None else "inf"),
        "growth_window": w,
        "growth_first_median": _round(first_med, 1),
        "growth_last_median": _round(last_med, 1),
        "direction": direction,
        "trend_slope_per_period": _round(slope, 2),
        "trend_r2": _round(r2, 3),
        "yoy_pct": _round(yoy, 1),
        "volatility_cv": _round(std / mean, 2) if mean > 0 else None,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "expected_points": expected,
        "missing_points": missing,
        "seasonality": _seasonality(df) if granularity == "monthly" else None,
        "share_per_million_mean": share,
        "bot_share": bot_share,
    }
    metrics["confidence"] = _confidence(metrics)
    return metrics
