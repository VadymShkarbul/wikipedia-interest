# wikipedia-interest — an Agent Skill for audience-interest research

An [Agent Skill](https://agentskills.io/specification) that turns **Wikipedia pageview data** into
decisions for B2C product teams: *which topics to build next* and *which language markets to enter*.
It resolves a topic to the right article per language, judges the trend **and how far to trust it**,
and produces a shareable one-page report — designed to be driven by a small, cheap model.

Two design principles:

- **The code does the statistics; the model narrates.** Growth, year-over-year change, seasonality,
  spikes and a confidence label are computed, never estimated by the model.
- **Except the prose.** The model writes the report's findings — it does that better — but the
  computed confidence caveat is appended by the code, so a report can't be forwarded without it.

## What v2 changed

| | v1 | v2 |
|---|---|---|
| Dependencies to analyze | pandas + numpy + requests + matplotlib (**~135 MB**) | **none** (standard library) |
| Report | PDF via matplotlib | self-contained HTML + inline SVG (print to PDF) |
| Interface | shell command via Bash | typed MCP tools (Bash no longer required) |
| Findings text | 65 lines of `if/elif` | written by the model, caveats appended by code |
| Cache location | whatever directory the agent was in | next to the code |

## Layout
```
wikipedia-interest/        # the skill (self-contained, this is what you ship)
├── SKILL.md               # metadata + agent workflow (start here)
├── INSTALL.md             # install into Claude Code / Codex
├── server.py              # MCP server: typed tools, no shell access needed
├── .mcp.json              # declares that server
├── .claude-plugin/        # plugin.json — lets the skill folder bundle the server
├── scripts/               # wikipop.py CLI + series / wiki_api / analysis / reporting
├── references/            # API.md, METHODOLOGY.md
└── examples.md
evals/                     # offline deterministic eval suite (dev only)
verify/                    # cheap-model end-to-end harness (dev only)
pes_task.md                # the original task brief
```

## Prerequisites
- **Python 3.12+**
- Internet access to the Wikimedia APIs. **No API key.**
- [uv](https://docs.astral.sh/uv/) only for the optional MCP server and for development.

## Quick start

No installation needed for the core:

```bash
python3 wikipedia-interest/scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

Each command prints exactly one JSON object.

```bash
# 1. resolve — topic + languages -> the exact article per edition (flags coverage gaps)
python3 wikipedia-interest/scripts/wikipop.py resolve --topic "mercury" --langs en,uk

# 2. analyze — metrics + confidence, no files written
python3 wikipedia-interest/scripts/wikipop.py analyze --topic "astronomy" --langs uk,pl --last 2y

# 3. report — a self-contained one-page HTML; you supply the narrative (print it to PDF to share)
python3 wikipedia-interest/scripts/wikipop.py report --topic "astronomy" --langs uk,pl --last 2y \
  --out astro.html --findings "Ukrainian interest is up 11% YoY with a September school peak."

# 4. pageviews — low-level single-article series (iteration/debug)
python3 wikipedia-interest/scripts/wikipop.py pageviews --lang uk --article "Астрономія" \
  --start 20230101 --end 20250101
```

See [`wikipedia-interest/examples.md`](wikipedia-interest/examples.md) for disambiguation (`--qid`),
share-of-attention (`--normalize`) and bot checks (`--check-bots`).

## Install as a skill
```bash
cp -R wikipedia-interest ~/.claude/skills/wikipedia-interest   # Claude Code
cp -R wikipedia-interest ~/.codex/skills/wikipedia-interest    # Codex CLI
```
Full instructions, and what each optional path costs, are in
[`wikipedia-interest/INSTALL.md`](wikipedia-interest/INSTALL.md).

## Development

```bash
uv sync --group dev
uv run pytest evals/          # 58 tests, offline and deterministic
```

The eval suite covers analysis correctness against hand-checked cases, the confidence rules
individually, the report's trust guarantee, a CLI golden against recorded fixtures, and the MCP tool
contract driven over real stdio. Only `evals/fixtures/record.py` touches the network.

Cheap-model end-to-end check (live, needs an OpenRouter key):

```bash
export OPENROUTER_API_KEY=sk-or-...
uv run verify/e2e_openrouter.py
```

## License
MIT (see the skill's `SKILL.md`).
