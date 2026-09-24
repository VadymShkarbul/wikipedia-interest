"""Declarative golden cases for analysis.analyze_series (Track A: analysis correctness).

Each case is a synthetic monthly series with a small, hand-checked set of expectations.
An expectation value is either a literal (asserted with ==) or a callable value->bool
(for ranges / approximate floats). Adding a case is one dict entry.

Fields not listed for a case are intentionally not asserted — each case pins only what it
is designed to prove, so the table stays robust to unrelated implementation detail.
"""
from __future__ import annotations

import pandas as pd


def _monthly(views, start="2022-01-01") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(views), freq="MS")
    return pd.DataFrame({"date": dates, "views": [int(v) for v in views]})


def _ramp(n, lo, hi, start="2022-01-01") -> pd.DataFrame:
    step = (hi - lo) / (n - 1) if n > 1 else 0
    return _monthly([round(lo + step * i) for i in range(n)], start=start)


# --- series builders for the trickier cases ---------------------------------

def _seasonal():
    """24 months: July is the recurring peak, January the recurring low."""
    views = []
    for i in range(24):
        month = (i % 12) + 1
        base = 300
        if month == 7:
            base = 520
        elif month == 1:
            base = 200
        views.append(base)
    return _monthly(views)


def _seasonal_flat():
    """24 months of a strong seasonal cycle with ZERO underlying trend.

    The trap: the growth window compares the autumn start against the summer end, so a
    start-vs-end reading says "declining" for a series that is exactly flat year over year.
    """
    import math
    views = []
    for i in range(24):
        month = ((8 + i) % 12) + 1  # start in September
        views.append(int(1000 + 600 * math.cos(2 * math.pi * ((month - 10) / 12))))
    return _monthly(views, start="2022-09-01")


def _ramp_with_spike():
    """A gentle ramp (so MAD > 0) with one obvious spike at Oct 2022 (index 9)."""
    df = _ramp(19, 200, 500)
    df.loc[9, "views"] = 6000
    return df


CASES = [
    {
        "id": "rising_clean",
        "df": _ramp(24, 100, 1000),
        "expect": {
            "available": True,
            "n_points": 24,
            "direction": "up",
            "growth_pct": lambda v: isinstance(v, (int, float)) and v > 200,
            "trend_r2": lambda v: v is not None and v > 0.98,
            "yoy_pct": lambda v: v is not None and v > 0,
            "anomaly_count": 0,
            "missing_points": 0,
            "confidence.label": "high",
        },
    },
    {
        "id": "declining_clean",
        "df": _ramp(24, 1000, 100),
        "expect": {
            "direction": "down",
            "growth_pct": lambda v: isinstance(v, (int, float)) and v < -50,
            "trend_r2": lambda v: v is not None and v > 0.98,
            "yoy_pct": lambda v: v is not None and v < 0,
            "confidence.label": "high",
        },
    },
    {
        "id": "flat",
        "df": _monthly([500] * 18),
        "expect": {
            "direction": "flat",
            "growth_pct": 0.0,
            "trend_slope_per_period": 0.0,
            "trend_r2": 0.0,
            "volatility_cv": 0.0,
            "confidence.label": "high",
        },
    },
    {
        "id": "spike_detected",
        "df": _ramp_with_spike(),
        "expect": {
            "available": True,
            "anomaly_count": 1,
            "anomalies.0.date": "2022-10-01",
        },
    },
    {
        "id": "inf_growth_from_zero_base",
        "df": _monthly([0, 0, 0, 100, 150, 200, 250, 300, 350, 400, 450, 500]),
        "expect": {
            "growth_pct": "inf",
            "direction": "up",
        },
    },
    {
        "id": "all_zero",
        "df": _monthly([0] * 12),
        "expect": {
            "growth_pct": None,
            "direction": "n/a",
            "volatility_cv": None,
            "confidence.label": "low",
        },
    },
    {
        "id": "low_volume",
        "df": _monthly([20, 30, 25, 35, 40, 30, 45, 20, 30, 35, 40, 25]),
        "expect": {
            "confidence.label": "low",
            "confidence.reasons.contains": "Very low traffic",
        },
    },
    {
        "id": "short_series",
        "df": _monthly([100, 200, 150, 300, 250]),
        "expect": {
            "n_points": 5,
            "yoy_pct": None,
            "seasonality": None,
            "confidence.label": "low",
            "confidence.reasons.contains": "Very short series",
        },
    },
    {
        "id": "medium_length",
        "df": _monthly([300, 320, 310, 305, 330, 315, 325, 300, 340, 310]),
        "expect": {
            "n_points": 10,
            "yoy_pct": None,
            "confidence.label": "medium",
            "confidence.reasons.contains": "Under a year of data",
        },
    },
    {
        # Regression: a purely seasonal, zero-trend series must not read as a decline.
        # `growth_pct` still reports the (season-driven) window comparison; `direction` must
        # come from the seasonality-safe YoY number instead.
        "id": "seasonal_flat_is_not_declining",
        "df": _seasonal_flat(),
        "expect": {
            "direction": "flat",
            "direction_basis": "yoy",
            "yoy_pct": 0.0,
            "growth_pct": lambda v: isinstance(v, (int, float)) and v < -20,  # the trap it avoids
            "seasonality.strength": lambda v: v is not None and v >= 0.5,
            "confidence.reasons.contains": "Seasonal pattern",
        },
    },
    {
        # Regression: a clean ramp is a trend, not a season — detrended seasonality keeps the
        # "quote yoy instead" note off a series where month-of-year variation is just the trend.
        "id": "clean_ramp_is_not_seasonal",
        "df": _ramp(24, 300, 760),
        "expect": {
            "direction": "up",
            "direction_basis": "yoy",
            "seasonality.strength": lambda v: v is not None and v < 0.2,
            "confidence.label": "high",
            "confidence.reasons.contains": "Sufficient volume, length, completeness",
        },
    },
    {
        "id": "seasonal_peak_july",
        "df": _seasonal(),
        "expect": {
            "seasonality.peak_month": "Jul",
            "seasonality.low_month": "Jan",
            "seasonality.strength": lambda v: v is not None and v > 0,
            "yoy_pct": lambda v: v is not None,
        },
    },
]
