"""Pinned CLI invocations shared by the recorder and the golden test (Track D).

Everything is pinned (--qid, --start, --end) so requests are stable cache keys and the whole
CLI runs offline against the committed fixture cache. Historical Wikimedia pageviews don't change,
so the golden JSON stays valid.
"""
from __future__ import annotations

# Golden cases: (name, argv). argv omits the interpreter/script and --cache-dir (added by caller).
GOLDEN_CASES = [
    ("resolve", ["resolve", "--topic", "astronomy", "--qid", "Q333", "--langs", "uk,pl"]),
    ("analyze", ["analyze", "--topic", "astronomy", "--qid", "Q333", "--langs", "uk,pl",
                 "--start", "20220101", "--end", "20240101"]),
]

# A report case is exercised for structure only (it writes files), not byte-for-byte golden JSON.
REPORT_ARGV = ["report", "--topic", "astronomy", "--qid", "Q333", "--langs", "uk,pl",
               "--start", "20220101", "--end", "20240101"]
