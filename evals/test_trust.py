"""Track B — result trustworthiness.

The judgments a user actually leans on: the confidence label + reasons, spike detection, and
honest coverage-gap reporting from title resolution. Resolution is driven against crafted cache
entries (the skill's real cache layer reads them as hits) so it runs offline and deterministically.
"""
from __future__ import annotations

import datetime as dt

import pytest

import analysis
import wiki_api
from conftest import monthly as _mk_monthly
from series import Series


def _monthly(views, start="2020-01-01"):
    return _mk_monthly(views, start=start)


def _without(s, idxs):
    """Series with the given positions removed — used to punch coverage holes."""
    keep = [i for i in range(len(s)) if i not in set(idxs)]
    return Series([s.dates[i] for i in keep], [s.views[i] for i in keep])


def _daily(views, start="2024-01-01"):
    first = dt.date(int(start[:4]), int(start[5:7]), int(start[8:10]))
    return Series([first + dt.timedelta(days=i) for i in range(len(views))],
                  [int(v) for v in views])


# A noisy, trendless series: R² is ~0 and the first/last windows have the same median, so the
# only rule it can trip is the straight-line-fit one.
_NOISY_NO_TREND = [500, 620, 540, 700, 460, 660, 480, 700, 520, 640, 500, 680,
                   460, 660, 500, 540, 480, 600]


# --- confidence rules: one case per rule, asserting label + the exact reason literal --------

CONFIDENCE_CASES = [
    # (id, views, expected_label, reason_substring)
    ("very_low_traffic", [30] * 18, "low", "Very low traffic"),
    ("low_traffic", [150] * 18, "medium", "Low traffic"),
    ("very_short", [500, 400, 600, 500, 550], "low", "Very short series"),
    ("under_a_year", [500] * 10, "medium", "Under a year of data"),
    ("clean_high", list(range(300, 300 + 24 * 20, 20)), "high",
     "Sufficient volume, length, completeness and a clear trend."),
]


@pytest.mark.parametrize("cid,views,label,reason", CONFIDENCE_CASES,
                         ids=[c[0] for c in CONFIDENCE_CASES])
def test_confidence_rule(cid, views, label, reason):
    m = analysis.analyze_series(_monthly(views))
    assert m["confidence"]["label"] == label, m["confidence"]
    assert any(reason in r for r in m["confidence"]["reasons"]), m["confidence"]["reasons"]


def test_missing_periods_cap_confidence_to_medium():
    # A gap in the monthly index -> expected_points > n_points -> "missing period(s)" reason.
    df = _monthly([500] * 12)
    df = _without(df, [4, 5])  # remove two interior months
    m = analysis.analyze_series(df)
    assert m["missing_points"] >= 1
    assert m["confidence"]["label"] in ("medium", "low")
    assert any("missing period" in r for r in m["confidence"]["reasons"])


def test_anomaly_heavy_series_flagged_event_driven():
    # >15% of points are spikes -> "event-driven" reason, capped at medium.
    base = list(range(200, 200 + 20 * 15, 15))  # 20 gently rising points, MAD > 0
    for i in (3, 7, 11, 16):  # 4/20 = 20% spikes
        base[i] = 9000
    m = analysis.analyze_series(_monthly(base))
    assert m["anomaly_count"] >= 3
    assert any("event-driven" in r for r in m["confidence"]["reasons"])


def test_bot_heavy_series_flagged():
    # bot_share > 0.5 -> data-quality reason, capped at medium.
    m = analysis.analyze_series(_monthly([500] * 18), bot_share=0.8)
    assert any("non-human" in r for r in m["confidence"]["reasons"])
    assert m["confidence"]["label"] in ("medium", "low")


def test_daily_volume_is_judged_on_a_monthly_equivalent_scale():
    """A daily series must not be judged against monthly cutoffs.

    ~3.2 views/day is ~97 views/month — 'low', not 'very low / mostly noise'. Quoting a monthly
    threshold at a daily mean was both the wrong verdict and literally the wrong unit.
    """
    m = analysis.analyze_series(_daily([3, 4, 2, 5, 3, 3, 4, 2, 3, 4] * 9), granularity="daily")
    reasons = " ".join(m["confidence"]["reasons"])
    assert "views/month equivalent" in reasons
    assert "views/mo on average" not in reasons  # the monthly literal must not leak into daily
    assert not any("Very low traffic" in r for r in m["confidence"]["reasons"])


def test_daily_series_never_claims_a_year_over_year_basis():
    """12 days vs the 12 before them is not a year: a daily run must fall back to the growth window."""
    m = analysis.analyze_series(_daily([300, 320, 280, 310] * 22), granularity="daily")
    assert m["yoy_pct"] is None
    assert m["direction_basis"] == "growth"


def test_daily_absent_days_are_not_treated_as_coverage_gaps():
    """The API omits zero-traffic days; a handful of those is not a coverage problem."""
    df = _daily([5] * 90)
    few = _without(df, [10, 20, 30])                                  # 3/90 absent
    many = _without(df, range(10, 40))                                # 30/90 absent
    m_few = analysis.analyze_series(few, granularity="daily")
    m_many = analysis.analyze_series(many, granularity="daily")
    assert m_few["missing_points"] == 3
    assert not any("missing period" in r for r in m_few["confidence"]["reasons"])
    assert any("missing period" in r for r in m_many["confidence"]["reasons"])


def test_low_r2_downgrades_only_when_the_direction_rests_on_it():
    """A weak line undermines `direction` only when `direction` was read off the line.

    With <24 months the direction comes from the start-vs-end windows, so a low R² means the
    verdict is shaky -> medium. With YoY available the verdict rests on the year comparison
    instead, so a choppy series is explained, not downgraded.
    """
    short = analysis.analyze_series(_monthly(_NOISY_NO_TREND))        # 18 points -> growth basis
    assert short["direction_basis"] == "growth"
    assert short["trend_r2"] < 0.2
    assert short["confidence"]["label"] == "medium", short["confidence"]
    assert any("Weak linear trend" in r for r in short["confidence"]["reasons"])

    long = analysis.analyze_series(_monthly(_NOISY_NO_TREND[:12] * 2))  # 24 points -> yoy basis
    assert long["direction_basis"] == "yoy"
    assert long["trend_r2"] < 0.2
    assert long["confidence"]["label"] == "high", long["confidence"]
    assert any("Choppy series" in r for r in long["confidence"]["reasons"])


def test_perfectly_even_series_is_not_punished_for_a_degenerate_r2():
    """A constant series has no variance to explain; `trend_r2` is 0 by convention, not failure."""
    m = analysis.analyze_series(_monthly([500] * 18))
    assert m["trend_r2"] == 0.0 and m["volatility_cv"] == 0.0
    assert m["confidence"]["label"] == "high", m["confidence"]
    assert not any("Weak linear trend" in r for r in m["confidence"]["reasons"])


def test_short_uneven_series_is_warned_about_unmeasurable_seasonality():
    """12-23 months: the growth window straddles seasons and there is no way to check. Medium.

    This series is a flat seasonal cycle, but it starts on the autumn peak and ends in the
    spring trough, so the start-vs-end reading says "down". Under 24 months the tool can't
    prove that either way — so it says so instead of asserting a decline confidently.
    """
    views = [1600, 1500, 1300, 1000, 700, 480, 400, 480, 700, 1000, 1300, 1520,
             1600, 1500, 1300, 1000, 700, 480]
    m = analysis.analyze_series(_monthly(views, start="2022-10-01"))
    assert m["direction_basis"] == "growth" and m["direction"] == "down"
    assert m["confidence"]["label"] == "medium", m["confidence"]
    assert any("may be seasonal" in r for r in m["confidence"]["reasons"])


def test_year_aligned_growth_window_gets_no_seasonal_warning():
    """When the series length makes the first and last windows the SAME months, it's like-for-like."""
    views = [1600, 1500, 1300, 1000, 700, 480, 400, 480, 700, 1000, 1300, 1520, 1600, 1500, 1300]
    m = analysis.analyze_series(_monthly(views, start="2022-10-01"))  # 15 pts: Oct-Dec vs Oct-Dec
    assert not any("may be seasonal" in r for r in m["confidence"]["reasons"])


def test_single_spike_detected_but_not_over_flagged():
    base = list(range(300, 300 + 18 * 10, 10))  # 18 rising points
    base[9] = 20000
    m = analysis.analyze_series(_monthly(base))
    assert m["anomaly_count"] == 1
    assert m["anomalies"][0]["views"] == 20000


# --- title resolution: the coverage-gap logic (offline via crafted cache) --------------------

def _sitelinks_body(qid, present: dict):
    return {"entities": {qid: {"sitelinks": {f"{l}wiki": {"title": t} for l, t in present.items()}}}}


def _search_body(title):
    return {"query": {"search": [{"title": title}] if title else []}}


def test_resolution_wikidata_and_gap(seed_cache):
    """With a pinned QID: a language with a sitelink -> method 'wikidata'; without -> 'gap'."""
    cache_dir, write = seed_cache
    qid = "Q333"
    langs = ["uk", "xx"]
    params = {
        "action": "wbgetentities", "ids": qid, "props": "sitelinks",
        "sitefilter": "ukwiki|xxwiki", "format": "json",
    }
    write(wiki_api.WIKIDATA_API, params, 200,
          _sitelinks_body(qid, {"uk": "Астрономія"}))  # uk present, xx absent
    res = wiki_api.resolve_titles("astronomy", langs, str(cache_dir), qid=qid)

    uk = res["titles"]["uk"]
    xx = res["titles"]["xx"]
    assert uk["found"] and uk["method"] == "wikidata" and uk["title"] == "Астрономія"
    assert xx["found"] is False and xx["method"] == "gap" and xx["title"] is None


def test_resolution_search_fallback_and_none(seed_cache):
    """With no QID at all: per-language search -> 'search' when found, 'none' when not."""
    cache_dir, write = seed_cache
    # No Wikidata candidates -> chosen is None -> search path.
    for lang in ("en", "uk"):
        write(wiki_api.WIKIDATA_API, {
            "action": "wbsearchentities", "search": "zzzznotathing", "language": lang,
            "uselang": lang, "format": "json", "limit": 5, "type": "item",
        }, 200, {"search": []})
    write("https://en.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": "zzzznotathing",
        "srlimit": 1, "format": "json",
    }, 200, _search_body("Some English Article"))
    write("https://uk.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": "zzzznotathing",
        "srlimit": 1, "format": "json",
    }, 200, _search_body(None))

    res = wiki_api.resolve_titles("zzzznotathing", ["en", "uk"], str(cache_dir))
    assert res["qid"] is None
    en, uk = res["titles"]["en"], res["titles"]["uk"]
    assert en["method"] == "search" and en["found"] and en["title"] == "Some English Article"
    assert uk["method"] == "none" and uk["found"] is False and uk["title"] is None
