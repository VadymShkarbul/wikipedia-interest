#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "requests>=2.31",
#   "pandas>=2.0",
#   "numpy>=1.24",
#   "matplotlib>=3.7",
# ]
# ///
"""wikipop — analyze Wikipedia pageviews as a proxy for audience interest.

Agent-facing CLI. Every command prints ONE JSON object to stdout; errors are JSON too (never
tracebacks). Run standalone with uv:  `uv run wikipedia-interest/scripts/wikipop.py <cmd> ...`

Commands:
  resolve    topic + languages -> exact article title per language (flags coverage gaps)
  pageviews  low-level single-article time series (iteration/debug)
  analyze    topic + languages -> metrics + confidence JSON (fast; no files)
  report     analyze + write a one-page PDF (+PNG)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

import analysis as A  # noqa: E402
import wiki_api as W  # noqa: E402


def _emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fail(msg: str, **extra):
    _emit({"error": msg, **extra})
    sys.exit(1)


def _parse_langs(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _period(args) -> tuple[str, str, str]:
    """Resolve (start_YYYYMMDD, end_YYYYMMDD, label) from --last or --start/--end."""
    if args.start and args.end:
        return args.start, args.end, f"{args.start}–{args.end}"
    last = args.last or "2y"
    m = re.fullmatch(r"(\d+)\s*([ymd])", last.strip().lower())
    if not m:
        _fail(f"bad --last '{last}', use e.g. 2y, 24m, 90d")
    n, unit = int(m.group(1)), m.group(2)
    end = pd.Timestamp.today().normalize()
    offset = {"y": pd.DateOffset(years=n), "m": pd.DateOffset(months=n), "d": pd.DateOffset(days=n)}[unit]
    start = end - offset
    if start < pd.Timestamp("2015-07-01"):
        start = pd.Timestamp("2015-07-01")
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), f"last {last}"


def _build_series(topic, langs, start, end, granularity, access, agent, cache_dir,
                  qid=None, normalize=False, check_bots=False) -> tuple:
    resolved = W.resolve_titles(topic, langs, cache_dir, qid=qid)
    titles = resolved["titles"]
    series = []
    for lang in langs:
        info = titles[lang]
        entry = {
            "lang": lang, "project": W.project_for_lang(lang), "title": info["title"],
            "qid": info["qid"], "found": info["found"], "method": info["method"],
            "df": None, "dropped": None, "metrics": {"available": False},
        }
        if info["found"] and info["title"]:
            df = W.fetch_pageviews(entry["project"], info["title"], start, end,
                                   granularity, access, agent, cache_dir)
            df, dropped = W.trim_partial_tail(df, granularity)
            entry["df"] = df
            entry["dropped"] = dropped

            share = None
            if normalize and not df.empty:
                agg = W.fetch_aggregate_pageviews(entry["project"], start, end,
                                                  granularity, access, agent, cache_dir)
                share = A.share_per_million(df, agg)

            bot_share = None
            if check_bots and not df.empty:
                all_df = W.fetch_pageviews(entry["project"], info["title"], start, end,
                                           granularity, access, "all-agents", cache_dir)
                bot_share = A.bot_share(df, all_df)

            entry["metrics"] = A.analyze_series(df, granularity, share=share, bot_share=bot_share)
        series.append(entry)
    return series, resolved


def _series_json(series: list) -> list:
    """Strip DataFrames for JSON output."""
    out = []
    for s in series:
        item = {k: v for k, v in s.items() if k != "df"}
        out.append(item)
    return out


# --- commands ----------------------------------------------------------------

def cmd_resolve(args):
    resolved = W.resolve_titles(args.topic, _parse_langs(args.langs), args.cache_dir, qid=args.qid)
    _emit({"topic": args.topic, "qid": resolved["qid"], "candidates": resolved["candidates"],
           "resolved": resolved["titles"]})


def cmd_pageviews(args):
    project = args.project or (W.project_for_lang(args.lang) if args.lang else None)
    if not project:
        _fail("provide --project or --lang")
    df = W.fetch_pageviews(project, args.article, args.start, args.end,
                           args.granularity, args.access, args.agent, args.cache_dir)
    if not args.keep_partial:
        df, dropped = W.trim_partial_tail(df, args.granularity)
    else:
        dropped = None
    _emit({
        "project": project, "article": args.article,
        "granularity": args.granularity, "access": args.access, "agent": args.agent,
        "dropped_partial": dropped,
        "series": [{"date": d.strftime("%Y-%m-%d"), "views": int(v)}
                   for d, v in zip(df["date"], df["views"])],
        "metrics": A.analyze_series(df, args.granularity),
    })


def cmd_analyze(args):
    langs = _parse_langs(args.langs)
    start, end, label = _period(args)
    series, resolved = _build_series(args.topic, langs, start, end, args.granularity,
                                     args.access, args.agent, args.cache_dir,
                                     qid=args.qid, normalize=args.normalize, check_bots=args.check_bots)
    _emit({"topic": args.topic, "qid": resolved["qid"], "candidates": resolved["candidates"],
           "period": label, "start": start, "end": end,
           "granularity": args.granularity, "agent": args.agent,
           "series": _series_json(series)})


def cmd_report(args):
    import reporting as R  # imported lazily so resolve/analyze stay light
    langs = _parse_langs(args.langs)
    start, end, label = _period(args)
    series, resolved = _build_series(args.topic, langs, start, end, args.granularity,
                                     args.access, args.agent, args.cache_dir,
                                     qid=args.qid, normalize=args.normalize, check_bots=args.check_bots)
    out = args.out or "report.pdf"
    files = R.build_report(args.topic, label, series, out, note=args.note, normalized=args.normalize)
    _emit({"topic": args.topic, "qid": resolved["qid"], "candidates": resolved["candidates"],
           "period": label, "start": start, "end": end,
           "files": files, "series": _series_json(series)})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wikipop", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--cache-dir", default=W.DEFAULT_CACHE_DIR)
        sp.add_argument("--granularity", default="monthly", choices=["monthly", "daily"])
        sp.add_argument("--access", default="all-access",
                        choices=["all-access", "desktop", "mobile-app", "mobile-web"])
        sp.add_argument("--agent", default="user",
                        choices=["user", "all-agents", "spider", "automated"])

    def concept(sp):
        sp.add_argument("--qid", help="pin a Wikidata concept id (e.g. Q308) to disambiguate")
        sp.add_argument("--normalize", action="store_true",
                        help="also compute share-of-attention (views per million of edition total)")
        sp.add_argument("--check-bots", action="store_true",
                        help="fetch all-agents too and report bot_share (extra requests)")

    sr = sub.add_parser("resolve", help="topic+langs -> article titles")
    sr.add_argument("--topic", required=True)
    sr.add_argument("--langs", required=True, help="comma-separated, e.g. uk,pl,cs")
    sr.add_argument("--qid", help="pin a Wikidata concept id (e.g. Q308) to disambiguate")
    sr.add_argument("--cache-dir", default=W.DEFAULT_CACHE_DIR)
    sr.set_defaults(func=cmd_resolve)

    sp = sub.add_parser("pageviews", help="low-level single-article series")
    sp.add_argument("--project"); sp.add_argument("--lang")
    sp.add_argument("--article", required=True)
    sp.add_argument("--start", required=True); sp.add_argument("--end", required=True)
    sp.add_argument("--keep-partial", action="store_true", help="keep the trailing partial period")
    common(sp); sp.set_defaults(func=cmd_pageviews)

    sa = sub.add_parser("analyze", help="metrics + confidence JSON")
    sa.add_argument("--topic", required=True)
    sa.add_argument("--langs", required=True)
    sa.add_argument("--last", help="e.g. 2y, 24m, 90d (default 2y)")
    sa.add_argument("--start"); sa.add_argument("--end")
    common(sa); concept(sa); sa.set_defaults(func=cmd_analyze)

    srp = sub.add_parser("report", help="analyze + one-page PDF")
    srp.add_argument("--topic", required=True)
    srp.add_argument("--langs", required=True)
    srp.add_argument("--last", help="e.g. 2y, 24m, 90d (default 2y)")
    srp.add_argument("--start"); srp.add_argument("--end")
    srp.add_argument("--out", help="output PDF path (default report.pdf)")
    srp.add_argument("--note", help="override the auto findings text")
    common(srp); concept(srp); srp.set_defaults(func=cmd_report)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except W.WikiError as exc:
        _fail(str(exc))
    except Exception as exc:  # never dump a traceback at the agent
        _fail(f"unexpected: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
