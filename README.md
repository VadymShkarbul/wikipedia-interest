# wikipedia-interest — an Agent Skill for audience-interest research

An [Agent Skill](https://agentskills.io/specification) that turns **Wikipedia pageview data** into
decisions for B2C product teams: *which topics to build next* and *which language markets to enter*. It
resolves a topic to the right article per language, analyzes trend and trustworthiness, and produces a
shareable **one-page PDF** — designed to be driven efficiently by a small, cheap model.

The design principle: **the code does the analysis; the model just orchestrates and narrates.**

## Layout
```
wikipedia-interest/        # the skill (self-contained, this is what you ship)
├── SKILL.md               # metadata + agent workflow (start here)
├── INSTALL.md             # how to install into Claude Code / Codex
├── scripts/               # wikipop.py CLI + wiki_api / analysis / reporting
├── references/            # API.md, METHODOLOGY.md
├── examples.md
└── requirements.txt
verify/                    # dev-only cheap-model end-to-end harness (not part of the skill)
pes_task.md                # the original task brief
```

## Prerequisites
- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — the package/exec runner used here. Install it with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  (or `brew install uv`; on Windows `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`).
  Prefer plain pip? The CLI's deps are listed in [`wikipedia-interest/requirements.txt`](wikipedia-interest/requirements.txt).
- **Internet access** to the Wikimedia APIs.

uv installs Python for you if it is missing, and `scripts/wikipop.py` carries PEP 723 inline
dependencies, so `uv run` auto-installs them on first use — no manual venv needed.

## Quick start
Clone, then sync the project environment with **uv**:
```bash
git clone <this-repo-url> && cd wikipedia-interest
uv sync
```
The CLI has four commands; each prints one JSON object to stdout (run from the repo root):
```bash
# 1. resolve — topic + languages -> the exact article title per Wikipedia edition (flags gaps)
uv run wikipedia-interest/scripts/wikipop.py resolve --topic "astronomy" --langs uk,pl,cs

# 2. analyze — fast metrics + confidence, no files written
uv run wikipedia-interest/scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y

# 3. report — analyze + write a shareable one-page PDF (+PNG)
uv run wikipedia-interest/scripts/wikipop.py report \
  --topic "astronomy" --langs uk --last 2y --out report.pdf

# 4. pageviews — low-level single-article time series (iteration/debug)
uv run wikipedia-interest/scripts/wikipop.py pageviews \
  --lang uk --article "Астрономія" --start 20230101 --end 20250101
```
See [`wikipedia-interest/examples.md`](wikipedia-interest/examples.md) for more, including
disambiguation (`--qid`), share-of-attention (`--normalize`), and bot checks (`--check-bots`).

## Install as an Agent Skill (Claude Code / Codex)
The `wikipedia-interest/` folder is a self-contained, portable skill. Drop it into an agent's skills
directory and restart:
```bash
# Claude Code (personal, all projects)
cp -R wikipedia-interest ~/.claude/skills/wikipedia-interest

# Codex CLI (personal)
cp -R wikipedia-interest ~/.codex/skills/wikipedia-interest
```
Full instructions (project-scoped installs, prerequisites, how to verify) are in
[`wikipedia-interest/INSTALL.md`](wikipedia-interest/INSTALL.md).

## Verify on a cheap model
```bash
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_MODEL="deepseek/deepseek-v4-flash"   # or another tool-capable model
uv run verify/e2e_openrouter.py
```

## License
MIT (see the skill's `SKILL.md`).
