#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "mcp>=2,<3",
# ]
# ///
"""MCP server for the wikipedia-interest skill: typed tools instead of shell commands.

Why this exists. Driving the skill through Bash means the user has to grant Bash, and a grant
broad enough to run `uv run scripts/wikipop.py ...` is broad enough to run anything. These tools
take schema-validated arguments, so the agent cannot compose a command at all — permissions are
per-tool (`mcp__wikipedia-interest__analyze_interest`), and `resolve_topic`/`analyze_interest` are
annotated read-only.

It is a thin adapter: every line of analysis lives in scripts/ and is shared with the CLI, which
remains the zero-dependency way to use this skill.
"""
from __future__ import annotations

import os
import sys
from typing import Annotated, Literal, Optional

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

import analysis as A  # noqa: E402
import reporting as R  # noqa: E402
import wiki_api as W  # noqa: E402
import wikipop  # noqa: E402

server = MCPServer(
    name="wikipedia-interest",
    version="2.0",
    instructions=(
        "Wikipedia pageviews as a proxy for audience interest. Call resolve_topic first when a "
        "topic may be ambiguous or missing from an edition, analyze_interest for the numbers, and "
        "build_report only when the user wants something shareable. Pageviews measure curiosity, "
        "not willingness to pay — say so. Always lead with `confidence`, and quote the number "
        "`direction_basis` names (yoy or growth), never the other one."
    ),
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITES_FILE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

Langs = Annotated[list[str], Field(
    description="Wikipedia edition codes, e.g. ['uk','pl','cs']. Not language names.",
    min_length=1, max_length=12)]
Window = Annotated[str, Field(
    description="Relative window: 2y, 18m, 90d. Ignored when start/end are given.",
    pattern=r"^\d+\s*[ymdYMD]$")]
Qid = Annotated[Optional[str], Field(
    default=None, description="Pin a Wikidata concept, e.g. Q308, from a resolve_topic candidate.",
    pattern=r"^Q\d+$")]
Ymd = Annotated[Optional[str], Field(default=None, description="YYYYMMDD", pattern=r"^\d{8}$")]


def _window(window: str, start: Optional[str], end: Optional[str], granularity: str):
    try:
        return wikipop.resolve_window(window, start, end, granularity)
    except ValueError as exc:
        raise ValueError(str(exc)) from None


@server.tool(
    description="Map a topic to the exact article title in each Wikipedia edition. Use before "
                "analyzing when a topic is ambiguous, or to tell a real coverage gap from a bad "
                "match. Returns per-language {title, found, method} plus Wikidata `candidates` to "
                "disambiguate with `qid`. method='gap' means the concept exists but that edition "
                "has no article — report it, do not compare it.",
    annotations=READ_ONLY,
)
def resolve_topic(topic: str, langs: Langs, qid: Qid = None) -> dict:
    resolved = W.resolve_titles(topic, langs, qid=qid)
    return {"topic": topic, "qid": resolved["qid"],
            "candidates": resolved["candidates"], "resolved": resolved["titles"]}


@server.tool(
    description="Fetch pageviews and compute growth, year-over-year change, trend, seasonality, "
                "spikes and a confidence judgment for each edition. This is the main tool. Lead "
                "your answer with `confidence.label` and its `reasons`, and quote whichever of "
                "yoy_pct / growth_pct that `direction_basis` names.",
    annotations=READ_ONLY,
)
def analyze_interest(
    topic: str,
    langs: Langs,
    window: Window = "2y",
    start: Ymd = None,
    end: Ymd = None,
    granularity: Literal["monthly", "daily"] = "monthly",
    normalize: Annotated[bool, Field(description=(
        "Also fetch each edition's total pageviews and report views per million, so a small "
        "edition with a big share of attention is not hidden by a large one."))] = False,
    check_bots: Annotated[bool, Field(description=(
        "Also fetch all-agents traffic and report the non-human share."))] = False,
    qid: Qid = None,
) -> dict:
    s, e, label = _window(window, start, end, granularity)
    series, resolved = wikipop._build_series(
        topic, langs, s, e, granularity, "all-access", "user", W.DEFAULT_CACHE_DIR,
        qid=qid, normalize=normalize, check_bots=check_bots)
    return {"topic": topic, "qid": resolved["qid"], "candidates": resolved["candidates"],
            "period": label, "start": s, "end": e, "granularity": granularity,
            "series": wikipop._series_json(series)}


@server.tool(
    description="Write a shareable one-page HTML report (charts + metrics table + your findings). "
                "YOU write the `findings` narrative — the tool appends the computed confidence "
                "label and leading caveat for every edition automatically, so the file cannot be "
                "forwarded without them. Call analyze_interest first and base the narrative on it.",
    annotations=WRITES_FILE,
)
def build_report(
    topic: str,
    langs: Langs,
    findings: Annotated[str, Field(description=(
        "Your narrative for the Findings section, in the user's language: what the numbers mean "
        "and what to do next. Caveats are added by the tool; do not invent numbers."))],
    window: Window = "2y",
    start: Ymd = None,
    end: Ymd = None,
    granularity: Literal["monthly", "daily"] = "monthly",
    normalize: bool = False,
    out_path: Annotated[Optional[str], Field(
        default=None,
        description="Where to write the .html file. Defaults to report.html in the working "
                    "directory. The absolute path is returned — tell the user where it is.")] = None,
    qid: Qid = None,
) -> dict:
    s, e, label = _window(window, start, end, granularity)
    series, resolved = wikipop._build_series(
        topic, langs, s, e, granularity, "all-access", "user", W.DEFAULT_CACHE_DIR,
        qid=qid, normalize=normalize, check_bots=False)
    out = os.path.abspath(out_path or "report.html")
    files = R.build_report(topic, label, series, out, findings=findings, normalized=normalize)
    return {"topic": topic, "period": label, "files": {"html": files["html"]},
            "series": wikipop._series_json(series)}


if __name__ == "__main__":
    server.run(transport="stdio")
