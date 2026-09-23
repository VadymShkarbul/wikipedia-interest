#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests>=2.31"]
# ///
"""End-to-end verification of the wikipedia-interest skill on a cheap/fast model via OpenRouter.

Why this exists: the task requires the skill to be usable by a small tool-capable model (Haiku 4.5
class). This drives a minimal agent loop — system prompt = SKILL.md, one `run_bash` tool restricted to
the skill's CLI — asks an example question, and checks the model produces a valid one-page PDF.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    # optional: pick a model (default is a cheap Anthropic Haiku; a free model also works)
    export OPENROUTER_MODEL="anthropic/claude-3.5-haiku"
    uv run verify/e2e_openrouter.py
    uv run verify/e2e_openrouter.py --query "Is interest in astronomy growing on Ukrainian Wikipedia?"

This is a developer tool. It is NOT part of the shipped skill.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
SKILL_MD = REPO / "wikipedia-interest" / "SKILL.md"
CLI_PREFIX = "uv run wikipedia-interest/scripts/wikipop.py"
OUT_PDF = REPO / "verify_report.pdf"
API_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_QUERY = (
    "Compare interest in intermittent fasting on Czech and Ukrainian Wikipedia over the last 2 years, "
    f"and produce a one-page PDF at {OUT_PDF}. Then summarize the finding in one paragraph."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "Run a shell command from the repo root. Only the wikipop.py CLI is permitted.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "the shell command"}},
            "required": ["command"],
        },
    },
}]


def run_bash(command: str) -> str:
    cmd = command.strip()
    # Tolerate a leading `cd <repo> &&` (models commonly prefix it) before the CLI.
    m = re.match(r"cd\s+\S+\s*&&\s*(.+)", cmd, re.S)
    remainder = m.group(1).strip() if m else cmd
    if not remainder.startswith(CLI_PREFIX):
        return f"REFUSED: only the `{CLI_PREFIX}` CLI is allowed (an optional `cd <repo> &&` prefix is ok). Got: {cmd[:120]}"
    try:
        proc = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after 180s"
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
    return resp.json()["choices"][0]["message"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=DEFAULT_QUERY)
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENROUTER_API_KEY first (get a key at https://openrouter.ai/).")
    model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-haiku")

    if OUT_PDF.exists():
        OUT_PDF.unlink()

    system = (
        "You are a data analyst agent. You have the following skill; follow it exactly and use ONLY the "
        "run_bash tool (restricted to the skill's CLI) to do the work. When done, give a short answer.\n\n"
        "===== SKILL.md =====\n" + SKILL_MD.read_text(encoding="utf-8")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": args.query},
    ]

    print(f"Model: {model}\nQuery: {args.query}\n" + "-" * 60)
    for step in range(args.max_steps):
        msg = call_model(model, messages, api_key)
        messages.append(msg)
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                cmd = json.loads(tc["function"]["arguments"]).get("command", "")
                print(f"[step {step}] TOOL run_bash: {cmd}")
                result = run_bash(cmd)
                print(result[:400])
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue
        print(f"[step {step}] FINAL:\n{msg.get('content', '')}")
        break

    ok = OUT_PDF.exists() and OUT_PDF.stat().st_size > 1000
    print("-" * 60)
    print(f"PASS: PDF created at {OUT_PDF}" if ok else "FAIL: no valid PDF produced")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
