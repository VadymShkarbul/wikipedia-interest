"""Track A — analysis correctness.

Runs the declarative golden table in cases/analysis_cases.py through the skill's real
analysis.analyze_series, plus focused checks for the normalize/bot helpers. No network.
"""
from __future__ import annotations

import pytest

import analysis
from cases.analysis_cases import CASES, _monthly


def _resolve(metrics: dict, path: str):
    """Resolve a dotted path like 'confidence.label' or 'anomalies.0.date' into metrics."""
    cur = metrics
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_analysis_golden(case):
    metrics = analysis.analyze_series(case["df"], granularity="monthly")
    for field, expected in case["expect"].items():
        # special suffix: assert a substring appears among confidence.reasons
        if field.endswith(".contains"):
            base = field[: -len(".contains")]
            reasons = _resolve(metrics, base)
            assert any(expected in r for r in reasons), (
                f"[{case['id']}] no reason contains {expected!r}; got {reasons}"
            )
            continue
        actual = _resolve(metrics, field)
        if callable(expected):
            assert expected(actual), f"[{case['id']}] {field}={actual!r} failed predicate"
        else:
            assert actual == expected, f"[{case['id']}] {field}={actual!r}, expected {expected!r}"


def test_empty_series_reports_unavailable():
    import pandas as pd

    empty = pd.DataFrame(columns=["date", "views"])
    assert analysis.analyze_series(empty) == {"available": False}


def test_share_per_million_aligns_on_dates():
    df = _monthly([100, 200, 300])
    agg = _monthly([1_000_000, 1_000_000, 1_000_000]).rename(columns={"views": "total_views"})
    # (100+200+300)/1e6 * 1e6 averaged = mean(100,200,300) = 200.0
    assert analysis.share_per_million(df, agg) == pytest.approx(200.0)


def test_share_per_million_none_on_empty():
    import pandas as pd

    empty = pd.DataFrame(columns=["date", "total_views"])
    assert analysis.share_per_million(_monthly([100]), empty) is None


def test_bot_share_fraction_non_human():
    user = _monthly([50, 50])
    allx = _monthly([100, 100])  # user is half of all-agents -> 0.5 bot share
    assert analysis.bot_share(user, allx) == pytest.approx(0.5)


def test_bot_share_none_when_all_zero():
    assert analysis.bot_share(_monthly([0, 0]), _monthly([0, 0])) is None
