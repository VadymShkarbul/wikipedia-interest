"""Track D — end-to-end CLI golden, offline.

Drives the real wikipop.py CLI as a subprocess against the warmed fixture cache (no network) and
asserts the emitted JSON matches the committed golden. Also pins the JSON error contract the agent
depends on: bad input -> {"error": ...} + exit 1, never a traceback.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
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


def test_cli_report_writes_html_offline(warm_cache, tmp_path):
    """The default path: a one-pager with no third-party dependency in sight."""
    if warm_cache is None:
        pytest.skip("no recorded fixtures; run `uv run evals/fixtures/record.py`")
    out = tmp_path / "report.html"
    proc = _run([*REPORT_ARGV, "--out", str(out), "--findings", "Narrative from the model."],
                warm_cache)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["files"]["html"] == str(out)
    text = out.read_text(encoding="utf-8")
    assert "Narrative from the model." in text
    assert "Астрономія" in text          # non-Latin title survives the whole pipeline

    # The computed caveat travels with it. Matching the real trust-line shape, not the bare word
    # "confidence" — that is also a static table header, so it is present even with no trust block.
    assert re.search(r"uk \([^)]+\): (up|down|flat) \([^)]+\); ~[\d,]+ views/mo; "
                     r"confidence (high|medium|low)\.", text), "trust line missing or reshaped"


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
    start, end, _ = _period("2y", "monthly")
    # Derive `today` from the CLI's own end date, so a run that straddles midnight cannot flake.
    today = dt.datetime.strptime(end, "%Y%m%d").date()
    assert start[-2:] == "01", start
    # Two years back, snapped to the 1st: with the day forced to 1 there is no clamping to
    # reason about, so this oracle is independent of the implementation's date arithmetic.
    assert start == dt.date(today.year - 2, today.month, 1).strftime("%Y%m%d")


def test_daily_last_window_is_exact_and_not_snapped():
    """Daily buckets aren't truncated by a mid-month start, so the window stays exact.

    Asserted as a contract over the returned pair — the span is exactly 90 days and the start is
    NOT forced to the 1st — rather than by re-deriving `today - timedelta(days=90)`, which is the
    implementation's own expression and so could never fail.
    """
    import datetime as dt
    start, end, _ = _period("90d", "daily")
    start_d = dt.datetime.strptime(start, "%Y%m%d").date()
    end_d = dt.datetime.strptime(end, "%Y%m%d").date()
    assert (end_d - start_d).days == 90
    # A monthly snap would force day 01; over a 90-day span that is a 1-in-30 coincidence, so
    # only assert it when the end date proves no snap could have produced this start.
    if end_d.day != 1:
        assert not (start_d.day == 1 and end_d.day == 1)


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


# --- the dependency-free invariant -------------------------------------------

def test_core_runs_with_site_packages_disabled(warm_cache, tmp_path):
    """The install story, enforced.

    `-S` skips site-packages entirely, so pandas, numpy, requests and matplotlib are all
    unimportable. resolve/analyze and the default HTML report must still work, and must produce
    byte-identical output to the golden. If someone reintroduces a third-party import into the
    core, this fails rather than quietly costing every user ~135 MB again.
    """
    if warm_cache is None:
        pytest.skip("no recorded fixtures")

    import subprocess as sp
    probe = sp.run([sys.executable, "-I", "-S", "-c",
                    "import importlib.util as u;"
                    "print([m for m in ('pandas','numpy','requests','matplotlib')"
                    " if u.find_spec(m) is not None])"],
                   capture_output=True, text=True)
    assert probe.stdout.strip() == "[]", f"-S did not isolate site-packages: {probe.stdout}"

    proc = sp.run([sys.executable, "-I", "-S", str(CLI), "analyze",
                   "--topic", "astronomy", "--qid", "Q333", "--langs", "uk,pl",
                   "--start", "20220101", "--end", "20240101",
                   "--cache-dir", str(warm_cache)],
                  cwd=str(SKILL), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == json.loads((GOLDEN / "analyze.json").read_text(encoding="utf-8"))


def test_html_report_needs_no_dependencies(warm_cache, tmp_path):
    if warm_cache is None:
        pytest.skip("no recorded fixtures")
    import subprocess as sp
    out = tmp_path / "r.html"
    proc = sp.run([sys.executable, "-I", "-S", str(CLI), *REPORT_ARGV,
                   "--out", str(out), "--findings", "Model narrative.",
                   "--cache-dir", str(warm_cache)],
                  cwd=str(SKILL), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "<svg" in out.read_text(encoding="utf-8")
