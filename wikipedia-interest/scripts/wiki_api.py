"""Wikimedia data access: article-title resolution + pageview retrieval, with an on-disk cache.

Pure data layer used by the CLI (wikipop.py) and the MCP server. No printing, no argument parsing.
All network access goes through one retrying helper with the policy-required User-Agent, on the
standard library only — the four GETs this module makes do not justify a dependency.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from series import Series

# --- constants ---------------------------------------------------------------

PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "{project}/{access}/{agent}/{article}/{granularity}/{start}/{end}"
)
AGGREGATE_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/"
    "{project}/{access}/{agent}/{granularity}/{start}/{end}"
)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
DATA_START = "20150701"  # Wikimedia pageview history begins here
# Cache next to this module, not in the caller's cwd: the agent's working directory is not ours
# to litter, and it varies between clients. Override with --cache-dir, the cache_dir argument, or
# WIKIPOP_CACHE_DIR (the MCP server takes no CLI flags, so it needs the env route).
DEFAULT_CACHE_DIR = os.environ.get(
    "WIKIPOP_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wikipop_cache"),
)
# A descriptive UA is required by the Wikimedia API policy. Override via env if desired.
USER_AGENT = os.environ.get(
    "WIKI_UA",
    "wikipedia-interest-skill/1.0 (https://agentskills.io; agent data-analysis skill)",
)
TIMEOUT = 30


class WikiError(Exception):
    """Raised for well-understood failures (bad input, no data). CLI turns these into JSON."""


# --- HTTP + cache ------------------------------------------------------------

def _cache_key(url: str, params: Optional[dict]) -> str:
    raw = url + "?" + urllib.parse.urlencode(sorted((params or {}).items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _request(url: str, params: Optional[dict]) -> tuple[int, Optional[dict]]:
    """One GET. Returns (status, parsed_json_or_None); 4xx/5xx come back rather than raising.

    Transport-level failures (DNS, timeout, reset) propagate so the caller can retry them.
    """
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(
        full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 404 etc. are answers, not failures
        status, raw = exc.code, exc.read()
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        body = None
    return status, body


def _get_json(
    url: str,
    params: Optional[dict] = None,
    cache_dir: str = DEFAULT_CACHE_DIR,
    ttl_seconds: int = 7 * 24 * 3600,
    ok_statuses: tuple = (200,),
) -> tuple[int, Optional[dict]]:
    """GET JSON with a simple file cache. Returns (status_code, parsed_json_or_None).

    Historical pageviews are stable, so a week-long TTL keeps repeat/related queries cheap.
    Non-OK statuses (e.g. 404 = article/data absent) are returned, not raised, and also cached.
    """
    os.makedirs(cache_dir, exist_ok=True)
    key = _cache_key(url, params)
    path = os.path.join(cache_dir, key + ".json")

    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_seconds:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cached = json.load(fh)
            return cached["status"], cached["body"]
        except (OSError, ValueError, KeyError):
            pass  # corrupt cache entry -> refetch

    last_exc = None
    for attempt in range(3):
        try:
            status, body = _request(url, params)
            if status in ok_statuses or status == 404:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"status": status, "body": body}, fh)
                return status, body
            # transient (429/5xx) -> back off and retry
            last_exc = WikiError(f"HTTP {status} for {url}")
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
        time.sleep(1.5 * (attempt + 1))
    raise WikiError(f"Request failed after retries: {last_exc}")


# --- title resolution --------------------------------------------------------

def _wikidata_candidates(topic: str, langs: list[str], cache_dir: str, limit: int = 5) -> list[dict]:
    """Return ranked concept candidates [{id, label, description}] for a topic.

    Searches in English AND in the first target language, then merges by id preserving rank. This
    fixes two problems: (1) English-only search misses concepts named in another language, and
    (2) top-1 silently picks the wrong concept for ambiguous words (e.g. "mercury" -> a car marque
    before the planet). Callers can show these candidates and let the user pin one via `qid`.
    """
    search_langs = ["en"]
    if langs and langs[0] != "en":
        search_langs.append(langs[0])

    ordered: list[dict] = []
    seen: set[str] = set()
    for lang in search_langs:
        params = {
            "action": "wbsearchentities",
            "search": topic,
            "language": lang,
            "uselang": lang,
            "format": "json",
            "limit": limit,
            "type": "item",
        }
        status, body = _get_json(WIKIDATA_API, params, cache_dir, ttl_seconds=30 * 24 * 3600)
        if status == 200 and body:
            for hit in body.get("search", []):
                if hit["id"] in seen:
                    continue
                seen.add(hit["id"])
                ordered.append({
                    "id": hit["id"],
                    "label": hit.get("label", ""),
                    "description": hit.get("description", ""),
                })
    return ordered[:limit]


def _wikidata_sitelinks(qid: str, langs: list[str], cache_dir: str) -> dict[str, str]:
    """Return {lang: title} for the requested language editions that have an article."""
    sitefilter = "|".join(f"{lang}wiki" for lang in langs)
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": sitefilter,
        "format": "json",
    }
    status, body = _get_json(WIKIDATA_API, params, cache_dir, ttl_seconds=30 * 24 * 3600)
    out: dict[str, str] = {}
    if status == 200 and body:
        sitelinks = body.get("entities", {}).get(qid, {}).get("sitelinks", {})
        for lang in langs:
            entry = sitelinks.get(f"{lang}wiki")
            if entry and entry.get("title"):
                out[lang] = entry["title"]
    return out


def _search_title(lang: str, topic: str, cache_dir: str) -> Optional[str]:
    """Per-language MediaWiki search fallback: return the top matching article title."""
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": topic,
        "srlimit": 1,
        "format": "json",
    }
    status, body = _get_json(url, params, cache_dir, ttl_seconds=7 * 24 * 3600)
    if status == 200 and body:
        hits = body.get("query", {}).get("search", [])
        if hits:
            return hits[0]["title"]
    return None


def resolve_titles(topic: str, langs: list[str], cache_dir: str = DEFAULT_CACHE_DIR,
                   qid: Optional[str] = None) -> dict:
    """Map a topic to the exact article title in each language edition.

    Strategy:
      1. Identify a Wikidata concept (QID) for the topic. If the caller passes `qid`, use it
         directly (pin the concept) and skip search. Otherwise pick the top candidate — but also
         return the full `candidates` list so an ambiguous topic (e.g. "mercury": car vs planet vs
         element) can be disambiguated by re-running pinned with `qid`.
      2. With a QID, its sitelinks are authoritative: a language present -> exact title
         (method="wikidata"); a language absent -> genuine coverage gap (found=False,
         method="gap"). We deliberately do NOT fuzzy-search here — that returns loosely-related
         articles and would silently compare the wrong topic.
      3. Only if NO concept QID exists at all do we use per-language search as a best-effort
         fallback (method="search", inherently lower confidence).

    Returns {"qid", "candidates", "titles": {lang: {title, qid, found, method}}}.
    """
    if not topic or not topic.strip():
        raise WikiError("topic is empty")
    langs = [l.strip() for l in langs if l.strip()]
    if not langs:
        raise WikiError("no languages given")

    if qid:
        candidates = []
        chosen = qid
    else:
        candidates = _wikidata_candidates(topic, langs, cache_dir)
        chosen = candidates[0]["id"] if candidates else None

    titles: dict[str, dict] = {}
    if chosen:
        sitelinks = _wikidata_sitelinks(chosen, langs, cache_dir)
        for lang in langs:
            title = sitelinks.get(lang)
            titles[lang] = {
                "title": title,
                "qid": chosen,
                "found": title is not None,
                "method": "wikidata" if title else "gap",
            }
    else:
        for lang in langs:
            title = _search_title(lang, topic, cache_dir)
            titles[lang] = {
                "title": title,
                "qid": None,
                "found": title is not None,
                "method": "search" if title else "none",
            }
    return {"qid": chosen, "candidates": candidates, "titles": titles}


# --- pageview retrieval ------------------------------------------------------

def project_for_lang(lang: str) -> str:
    """`uk` -> `uk.wikipedia`. Accepts a full project string unchanged."""
    return lang if "." in lang else f"{lang}.wikipedia"


def _series_from_items(body: Optional[dict]) -> Series:
    """Wikimedia `items` payload -> Series, sorted by date."""
    if not body or "items" not in body:
        return Series()
    dates, views = [], []
    for it in body["items"]:
        dates.append(dt.datetime.strptime(it["timestamp"][:8], "%Y%m%d").date())
        views.append(int(it["views"]))
    return Series(dates, views).sorted_by_date()


def fetch_pageviews(
    project: str,
    article: str,
    start: str,
    end: str,
    granularity: str = "monthly",
    access: str = "all-access",
    agent: str = "user",
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> Series:
    """Fetch a pageview time series. Returns Series(dates: date, views: int).

    `start`/`end` are YYYYMMDD. Missing article or empty range -> empty Series (not an error),
    so callers can report "no coverage" rather than crash.
    """
    if not article:
        raise WikiError("article title is empty")
    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = PAGEVIEWS_URL.format(
        project=project,
        access=access,
        agent=agent,
        article=encoded,
        granularity=granularity,
        start=f"{start}00",
        end=f"{end}00",
    )
    status, body = _get_json(url, None, cache_dir)
    if status == 404:
        return Series()
    return _series_from_items(body)


def fetch_aggregate_pageviews(
    project: str,
    start: str,
    end: str,
    granularity: str = "monthly",
    access: str = "all-access",
    agent: str = "user",
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> Series:
    """Fetch the WHOLE edition's total pageviews per period. Returns Series(dates, views=totals).

    Used to normalize an article's views into a share-of-attention, so editions of very different
    sizes compare fairly. Cached per project/range and shared across topics -> cheap.
    """
    url = AGGREGATE_URL.format(
        project=project, access=access, agent=agent,
        granularity=granularity, start=f"{start}00", end=f"{end}00",
    )
    status, body = _get_json(url, None, cache_dir)
    if status == 404:
        return Series()
    return _series_from_items(body)


def trim_partial_tail(s: Series, granularity: str = "monthly") -> tuple:
    """Drop a trailing incomplete period. Wikimedia's latest month/day is usually partial and,
    if kept, badly skews growth and the 'latest' figure.

    Conservative rule (returns the dropped row info for transparency):
      * monthly: drop the last row if its month is the current calendar month, OR if it is
        far below recent levels (< 25% of the median of the preceding up-to-6 months) — the
        signature of a partial month.
      * daily: same idea against the preceding up-to-14 days.
    """
    if s is None or len(s) < 3:
        return s, None

    from statistics import median

    last_date = s.dates[-1]
    last_val = float(s.views[-1])
    lookback = 6 if granularity == "monthly" else 14
    prior = s.views[-(lookback + 1):-1]
    prior_med = float(median(prior)) if prior else 0.0

    today = dt.date.today()
    same_period = (
        (last_date.year == today.year and last_date.month == today.month)
        if granularity == "monthly"
        else last_date == today
    )
    far_below = prior_med > 0 and last_val < 0.25 * prior_med

    if same_period or far_below:
        dropped = {
            "date": last_date.strftime("%Y-%m-%d"),
            "views": int(last_val),
            "reason": "current-period" if same_period else "far-below-recent-levels",
        }
        return s.drop_last(), dropped
    return s, None
