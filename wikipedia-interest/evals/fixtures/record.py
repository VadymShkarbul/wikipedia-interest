#!/usr/bin/env python3
"""Refresh the recorded fixtures for the offline CLI golden test (Track D).

Runs the pinned CLI cases (see evals/cli_cases.py) against the LIVE Wikimedia API into the
committed fixture cache, then regenerates the golden JSON from that freshly warmed cache.

This is the ONLY part of the eval suite that touches the network, and you run it by hand only
when you deliberately want to re-baseline (e.g. after changing the pinned window or metrics).

Usage (from repo root):
    uv run evals/fixtures/record.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
CLI = SKILL / "scripts" / "wikipop.py"
CACHE = Path(__file__).resolve().parent / "cache"
GOLDEN = SKILL / "evals" / "golden"

sys.path.insert(0, str(SKILL / "evals"))
from cli_cases import GOLDEN_CASES  # noqa: E402


def run(argv):
    proc = subprocess.run(
        [sys.executable, str(CLI), *argv, "--cache-dir", str(CACHE)],
        cwd=str(SKILL), capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise SystemExit(f"command failed ({argv}):\n{proc.stderr}\n{proc.stdout}")
    return json.loads(proc.stdout)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name, argv in GOLDEN_CASES:
        out = run(argv)
        (GOLDEN / f"{name}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"recorded golden: {name}.json")
    print(f"fixture cache entries: {len(list(CACHE.glob('*.json')))}")


if __name__ == "__main__":
    main()
