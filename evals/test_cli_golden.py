"""Track D — end-to-end CLI golden, offline.

Drives the real wikipop.py CLI as a subprocess against the warmed fixture cache (no network) and
asserts the emitted JSON matches the committed golden. Also pins the JSON error contract the agent
depends on: bad input -> {"error": ...} + exit 1, never a traceback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "wikipedia-interest"
CLI = SKILL / "scripts" / "wikipop.py"
GOLDEN = Path(__file__).resolve().parent / "golden"

from cli_cases import GOLDEN_CASES, REPORT_ARGV  # noqa: E402


def _run(argv, cache_dir, cwd=None):
    return subprocess.run(
        [sys.executable, str(CLI), *argv, "--cache-dir", str(cache_dir)],
        cwd=str(cwd or SKILL), capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("name,argv", GOLDEN_CASES, ids=[c[0] for c in GOLDEN_CASES])
def test_cli_matches_golden(name, argv, warm_cache):
    if warm_cache is None:
        pytest.skip("no recorded fixtures; run `uv run evals/fixtures/record.py`")
    proc = _run(argv, warm_cache)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    expected = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert got == expected


def test_cli_report_writes_pdf_offline(warm_cache, tmp_path):
    if warm_cache is None:
        pytest.skip("no recorded fixtures; run `uv run evals/fixtures/record.py`")
    out_pdf = tmp_path / "report.pdf"
    proc = _run([*REPORT_ARGV, "--out", str(out_pdf)], warm_cache)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["files"]["pdf"] == str(out_pdf)
    assert out_pdf.exists() and out_pdf.stat().st_size > 5000
    assert Path(payload["files"]["png"]).exists()


# --- window construction (no network: pure argument handling) --------------------------------

def _period(last, granularity):
    import argparse

    import wikipop
    return wikipop._period(argparse.Namespace(start=None, end=None, last=last,
                                              granularity=granularity))


def test_monthly_last_window_snaps_to_whole_months():
    """A mid-month start makes the API return a TRUNCATED first monthly bucket.

    That silently understates the baseline `growth_pct` and `yoy_pct` are measured against, so a
    monthly `--last` window must begin on the 1st.
    """
    import datetime as dt
    today = dt.date.today()
    start, _, _ = _period("2y", "monthly")
    assert start[-2:] == "01", start
    # Two years back, snapped to the 1st: with the day forced to 1 there is no clamping to
    # reason about, so this oracle is independent of the implementation's date arithmetic.
    assert start == dt.date(today.year - 2, today.month, 1).strftime("%Y%m%d")


def test_daily_last_window_is_not_snapped():
    """Daily buckets aren't truncated by a mid-month start, so the window stays exact."""
    import datetime as dt
    start, _, _ = _period("90d", "daily")
    assert start == (dt.date.today() - dt.timedelta(days=90)).strftime("%Y%m%d")


def test_cli_error_contract_is_json_not_traceback(tmp_path):
    # Required args present but neither --lang nor --project -> the CLI's own JSON error path.
    proc = _run(
        ["pageviews", "--article", "Астрономія", "--start", "20220101", "--end", "20240101"],
        tmp_path,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)  # must be parseable JSON, not a traceback
    assert "error" in payload
    assert "Traceback" not in proc.stdout


def test_cli_empty_topic_is_json_error(tmp_path):
    proc = _run(["resolve", "--topic", "  ", "--langs", "uk"], tmp_path)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert "error" in payload
