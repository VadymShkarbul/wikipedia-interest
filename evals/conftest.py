"""Shared fixtures for the wikipedia-interest evaluation suite.

The evals are deterministic and offline. They import the skill's own modules directly
(`analysis`, `wiki_api`, `reporting`) and assert on their real outputs — no math is
re-implemented here. Network is replaced by two fixture mechanisms:

  * synthetic pandas Series/DataFrames built in-process (Tracks A & C), and
  * a warmed on-disk cache the skill's own cache layer reads from (Tracks B & D).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "wikipedia-interest" / "scripts"
FIXTURE_CACHE = Path(__file__).resolve().parent / "fixtures" / "cache"

# Make the skill's modules importable exactly as the CLI does (scripts/ on sys.path).
sys.path.insert(0, str(SCRIPTS))

import analysis  # noqa: E402
import wiki_api  # noqa: E402


# --- synthetic series builders ----------------------------------------------

def monthly(views, start="2022-01-01") -> pd.DataFrame:
    """Build a monthly DataFrame(date, views) from a list of view counts."""
    dates = pd.date_range(start=start, periods=len(views), freq="MS")
    return pd.DataFrame({"date": dates, "views": [int(v) for v in views]})


def ramp(n, lo, hi, start="2022-01-01") -> pd.DataFrame:
    """A clean linear ramp from `lo` to `hi` over n monthly points."""
    step = (hi - lo) / (n - 1) if n > 1 else 0
    return monthly([round(lo + step * i) for i in range(n)], start=start)


@pytest.fixture
def mk_monthly():
    return monthly


@pytest.fixture
def mk_ramp():
    return ramp


# --- cache helpers (offline network replacement) ----------------------------

def write_cache_entry(cache_dir: Path, url: str, params, status: int, body) -> Path:
    """Seed a cache entry using the skill's OWN key function, so wiki_api reads it as a hit.

    This lets a test craft an exact Wikidata / search / pageviews response without a network
    call, and drive the real resolution and fetch code paths against it.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = wiki_api._cache_key(url, params)
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps({"status": status, "body": body}), encoding="utf-8")
    return path


@pytest.fixture
def seed_cache(tmp_path):
    """Return (cache_dir, writer). The writer seeds one entry; cache_dir is a fresh temp dir."""
    cache_dir = tmp_path / "cache"

    def _writer(url, params, status, body):
        return write_cache_entry(cache_dir, url, params, status, body)

    return cache_dir, _writer


@pytest.fixture
def warm_cache(tmp_path):
    """Copy the committed fixture cache to a temp dir and refresh mtimes so it never TTL-expires.

    Returns None (skips the test) when no recorded fixtures are present, so the offline unit
    evals still run in a clean checkout that hasn't recorded fixtures yet.
    """
    if not FIXTURE_CACHE.exists() or not any(FIXTURE_CACHE.glob("*.json")):
        return None
    dest = tmp_path / "warm_cache"
    shutil.copytree(FIXTURE_CACHE, dest)
    now = time.time()
    for f in dest.glob("*.json"):
        os.utime(f, (now, now))
    return dest
