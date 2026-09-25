#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests>=2.31"]
# ///
"""End-to-end verification of the wikipedia-interest skill on a cheap/fast model via OpenRouter.

Why this exists: the brief requires the skill to be usable by a small tool-capable model and says
«Перевір повний сценарій на такій моделі» — test the full scenario on such a model, naming Claude
Haiku 4.5 «або аналогічній із підтримкою інструментів» and explicitly allowing cheap or free
OpenRouter models. This drives a minimal agent loop — system prompt = SKILL.md, one `run_bash` tool
restricted to the skill's CLI — asks an example question, and then INSPECTS the report the model
produced.

What a PASS means, precisely: the model drove the CLI itself and the resulting one-pager carries a
trust line for every requested edition, a narrative the model wrote, and the A4 page rule. What it
does NOT mean: that the prose is accurate, or that the content fits on one printed page — the
browser makes the PDF, so nothing here can see the paginated result.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    # optional: any tool-capable model. The brief names Claude Haiku 4.5:
    export OPENROUTER_MODEL="anthropic/claude-haiku-4.5"
    uv run wikipedia-interest/verify/e2e_openrouter.py
    uv run wikipedia-interest/verify/e2e_openrouter.py --query "..." --expect-langs uk

This is a developer tool. It ships inside the skill folder so that all of the project's own code
lives there, but it is never loaded or run by an agent using the skill.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import requests

SKILL_DIR = Path(__file__).resolve().parent.parent  # commands run from the skill dir, as installed
SKILL_MD = SKILL_DIR / "SKILL.md"
CLI_REL = "scripts/wikipop.py"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# A tool-capable model that is cheap or free. Override with OPENROUTER_MODEL; the brief names
# anthropic/claude-haiku-4.5, which also works here.
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

DEFAULT_LANGS = "cs,uk"
DEFAULT_QUERY_TMPL = (
    "Compare interest in intermittent fasting on Czech and Ukrainian Wikipedia over the last 2 "
    "years, and produce a one-page report at {out}. Then summarize the finding in one paragraph."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "Run a shell command from the skill directory. Only the wikipop.py CLI is permitted.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "the shell command"}},
            "required": ["command"],
        },
    },
}]

# `python3 scripts/wikipop.py`, but also `python`, `./scripts/...`, or an absolute interpreter.
# Being strict here turns a harness artifact into what looks like a skill failure.
_CLI_RE = re.compile(r"^(?:[\w./\\-]*python[\d.]*\s+)?\.?/?" + re.escape(CLI_REL) + r"(\s|$)")


def run_bash(command: str, stats: dict) -> str:
    """Run ONLY the skill's CLI, with no shell.

    The command is split with shlex and executed as an argv list, so shell metacharacters are inert:
    `... analyze --topic x ; rm -rf y` is rejected rather than being half-executed. An earlier version
    validated the command and then ran the ORIGINAL string under `shell=True`, which validated nothing.
    This is still only a dev harness, but it should not model a broken pattern.
    """
    cmd = command.strip()
    # Tolerate a leading `cd <dir> &&` (models commonly prefix it) before the CLI.
    m = re.match(r"cd\s+\S+\s*&&\s*(.+)", cmd, re.S)
    remainder = m.group(1).strip() if m else cmd
    if not _CLI_RE.match(remainder):
        stats["refused"] += 1
        return (f"REFUSED: only the `{CLI_REL}` CLI is allowed (an optional `cd <dir> &&` prefix "
                f"and a python interpreter are ok). Got: {cmd[:120]}")
    try:
        argv = shlex.split(remainder)
    except ValueError as exc:
        stats["refused"] += 1
        return f"REFUSED: could not parse command ({exc})"
    if any(tok in (";", "&&", "||", "|", ">", ">>", "<", "&") for tok in argv):
        stats["refused"] += 1
        return "REFUSED: shell operators are not allowed; run a single CLI command"
    if not argv[0].lower().startswith("python"):
        argv = [sys.executable, *argv]          # `./scripts/wikipop.py` -> run it with this python
    else:
        argv = [sys.executable, *argv[1:]]      # pin the interpreter; the model's choice may not exist
    try:
        proc = subprocess.run(argv, cwd=SKILL_DIR, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 180s"
    if proc.returncode == 0:
        stats["ok_calls"] += 1
    out = (proc.stdout or "")[:6000]
    err = (proc.stderr or "")[:1500]
    return f"exit={proc.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}"


def call_model(model: str, messages: list, api_key: str) -> dict:
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "tools": TOOLS, "temperature": 0},
        timeout=120,
    )
    if resp.status_code != 200:
        raise SystemExit(f"OpenRouter error {resp.status_code}: {resp.text[:500]}")
    try:
        payload = resp.json()
    except ValueError:
        raise SystemExit(f"OpenRouter returned non-JSON: {resp.text[:500]}")
    # A 200 can still carry an error body (free-tier rate limits do exactly this).
    if "choices" not in payload:
        raise SystemExit(f"OpenRouter returned no choices: {json.dumps(payload)[:500]}")
    return payload["choices"][0]["message"]


def check_report(path: Path, expect_langs: list, stats: dict) -> list:
    """Return a list of problems; empty means the run genuinely produced a usable one-pager."""
    problems = []
    if stats["ok_calls"] == 0:
        problems.append("the model never ran the CLI successfully "
                        f"({stats['refused']} command(s) refused by the sandbox)")
    if not path.exists():
        problems.append(f"no report was written at {path}")
        return problems

    text = path.read_text(encoding="utf-8", errors="replace")
    if "(No narrative supplied" in text:
        problems.append("the report has no findings: the model called `report` without --findings")
    for lang in expect_langs:
        # Either a metrics trust line or an explicit coverage-gap line counts; both are honest.
        if not re.search(rf"<li>{re.escape(lang)}(?: \(|:)", text):
            problems.append(f"no trust line for edition '{lang}'")
    if "@page { size: A4 portrait;" not in text:
        problems.append("the A4 page rule is missing, so Print -> Save as PDF will not give one page")
    if text.count('<div class="page">') != 1:
        problems.append("expected exactly one .page container")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=None)
    ap.add_argument("--out", default=None, help="where the model is told to write the report")
    ap.add_argument("--expect-langs", default=None,
                    help=f"edition codes the report must cover (default: {DEFAULT_LANGS})")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENROUTER_API_KEY first (get a key at https://openrouter.ai/).")
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    out_report = Path(args.out).resolve() if args.out else Path.cwd() / "verify_report.html"
    query = args.query or DEFAULT_QUERY_TMPL.format(out=out_report)
    if args.expect_langs is not None:
        expect_langs = [c.strip() for c in args.expect_langs.split(",") if c.strip()]
    elif args.query:
        expect_langs = []      # a custom query: we cannot know which editions it asked for
        print("note: --query given without --expect-langs, so per-edition checks are skipped")
    else:
        expect_langs = DEFAULT_LANGS.split(",")

    if out_report.exists():
        out_report.unlink()

    system = (
        "You are a data analyst agent. You have the following skill; follow it exactly and use ONLY the "
        "run_bash tool (restricted to the skill's CLI) to do the work. When done, give a short answer.\n\n"
        "===== SKILL.md =====\n" + SKILL_MD.read_text(encoding="utf-8")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]

    stats = {"ok_calls": 0, "refused": 0}
    print(f"Model: {model}\nQuery: {query}\n" + "-" * 60)
    finished = False
    for step in range(args.max_steps):
        msg = call_model(model, messages, api_key)
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                raw = tc.get("function", {}).get("arguments") or "{}"
                try:
                    cmd = json.loads(raw).get("command", "")
                except (ValueError, TypeError):
                    # Weak models emit malformed tool arguments; tell the model rather than crash.
                    print(f"[step {step}] TOOL run_bash: <unparsable arguments> {raw[:120]}")
                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": "ERROR: arguments were not valid JSON; "
                                                "send {\"command\": \"...\"}"})
                    continue
                print(f"[step {step}] TOOL run_bash: {cmd}")
                result = run_bash(cmd, stats)
                print(result[:400])
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue
        print(f"[step {step}] FINAL:\n{msg.get('content', '')}")
        finished = True
        break

    if not finished:
        print(f"\nran out of steps after {args.max_steps} (still calling tools) — "
              f"raise --max-steps if the model was making progress")

    problems = check_report(out_report, expect_langs, stats)
    print("-" * 60)
    if problems:
        print("FAIL:")
        for p in problems:
            print(f"  - {p}")
    else:
        print(f"PASS: {out_report} covers {', '.join(expect_langs) or 'the requested editions'} "
              f"with model-written findings ({stats['ok_calls']} CLI call(s))")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
