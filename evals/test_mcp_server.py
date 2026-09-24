"""Track E — the MCP tool surface.

The point of the server is that the agent no longer composes a shell command, so what matters is
the contract a client sees: the right tools, honest read-only annotations, schema validation that
rejects bad arguments *before* any work happens, and results identical to the CLI's.

Driven against the warmed fixture cache via WIKIPOP_CACHE_DIR, so it runs offline.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="the MCP server is an optional transport")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "wikipedia-interest" / "server.py"
GOLDEN = Path(__file__).resolve().parent / "golden"


def _drive(coro_fn, cache_dir, cwd):
    """Run one client session against a fresh server subprocess."""
    async def main():
        params = StdioServerParameters(
            command=sys.executable, args=[str(SERVER)],
            env={**os.environ, "WIKIPOP_CACHE_DIR": str(cache_dir)},
            cwd=str(cwd),
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                return await coro_fn(session)
    return asyncio.run(main())


def _payload(result):
    return result.structured_content or json.loads(result.content[0].text)


def test_tools_are_exposed_with_honest_annotations(warm_cache, tmp_path):
    if warm_cache is None:
        pytest.skip("no recorded fixtures")

    async def go(s):
        return await s.list_tools()

    tools = {t.name: t for t in _drive(go, warm_cache, tmp_path).tools}
    assert set(tools) == {"resolve_topic", "analyze_interest", "build_report"}
    # The two read-only tools must say so: that is what lets a user grant them freely.
    assert tools["resolve_topic"].annotations.read_only_hint is True
    assert tools["analyze_interest"].annotations.read_only_hint is True
    # build_report writes a file, and must not claim otherwise.
    assert tools["build_report"].annotations.read_only_hint is False
    # The model must supply the narrative — it is a required argument, not an optional override.
    assert "findings" in (tools["build_report"].input_schema.get("required") or [])


def test_report_tool_exposes_the_same_analysis_knobs_as_analyze(warm_cache, tmp_path):
    """Both tools drive one engine, so a knob that changes the numbers must exist on both.

    `check_bots` was missing from build_report, which silently mattered: a high bot share lowers
    `confidence`, so a crawler-heavy topic could analyze as medium and then be written into the
    shared report as high — the caveat dropped out of the artifact that travels.
    """
    if warm_cache is None:
        pytest.skip("no recorded fixtures")

    async def go(s):
        return await s.list_tools()

    tools = {t.name: t for t in _drive(go, warm_cache, tmp_path).tools}
    analyze = set(tools["analyze_interest"].input_schema.get("properties") or {})
    report = set(tools["build_report"].input_schema.get("properties") or {})
    missing = analyze - report
    assert not missing, f"build_report is missing analysis knobs: {sorted(missing)}"


def test_analyze_matches_the_cli_golden(warm_cache, tmp_path):
    """Same numbers through the typed tool as through the CLI — one engine, two front doors."""
    if warm_cache is None:
        pytest.skip("no recorded fixtures")

    async def go(s):
        return await s.call_tool("analyze_interest", {
            "topic": "astronomy", "langs": ["uk", "pl"], "qid": "Q333",
            "start": "20220101", "end": "20240101",
        })

    got = _payload(_drive(go, warm_cache, tmp_path))
    expected = json.loads((GOLDEN / "analyze.json").read_text(encoding="utf-8"))
    assert got["series"] == expected["series"]


def test_malformed_argument_is_rejected_by_the_schema(warm_cache, tmp_path):
    """A shell string would have run; a typed argument cannot even reach the tool body."""
    if warm_cache is None:
        pytest.skip("no recorded fixtures")

    async def go(s):
        return await s.call_tool("analyze_interest", {
            "topic": "astronomy", "langs": ["uk"], "window": "banana"})

    result = _drive(go, warm_cache, tmp_path)
    assert result.is_error
    assert "window" in result.content[0].text


def test_report_writes_html_with_the_model_narrative(warm_cache, tmp_path):
    if warm_cache is None:
        pytest.skip("no recorded fixtures")
    out = tmp_path / "mcp_report.html"

    async def go(s):
        return await s.call_tool("build_report", {
            "topic": "astronomy", "langs": ["uk", "pl"], "qid": "Q333",
            "start": "20220101", "end": "20240101",
            "findings": "Narrative written by the model.", "out_path": str(out),
        })

    payload = _payload(_drive(go, warm_cache, tmp_path))
    assert payload["files"]["html"] == str(out)
    text = out.read_text(encoding="utf-8")
    assert "Narrative written by the model." in text
    assert "confidence" in text          # the computed caveat is appended regardless
    assert "Астрономія" in text
