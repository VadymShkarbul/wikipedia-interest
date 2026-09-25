"""Synthetic Series builders shared by the eval suite.

These live here, not in `conftest.py`, for two reasons: `cases/analysis_cases.py` is imported
as a plain module and cannot request pytest fixtures, and importing `conftest` from a test is a
pytest anti-idiom that only works by accident of sys.path. One definition, imported everywhere.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from series import Series  # noqa: E402


def month_starts(n, start="2022-01-01") -> list:
    """n consecutive first-of-month dates beginning at `start`."""
    y, m = int(start[:4]), int(start[5:7])
    out = []
    for _ in range(n):
        out.append(dt.date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly(views, start="2022-01-01") -> Series:
    """Build a monthly Series(dates, views) from a list of view counts."""
    return Series(month_starts(len(views), start), [int(v) for v in views])


def ramp(n, lo, hi, start="2022-01-01") -> Series:
    """A clean linear ramp from `lo` to `hi` over n monthly points."""
    step = (hi - lo) / (n - 1) if n > 1 else 0
    return monthly([round(lo + step * i) for i in range(n)], start=start)
