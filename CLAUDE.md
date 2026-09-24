# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

An **Agent Skill** (`wikipedia-interest/`) that analyzes Wikipedia pageviews as a proxy for
audience interest — to help B2C teams decide *which topics to build* and *which language markets
to enter*. The shippable artifact is the self-contained `wikipedia-interest/` folder; everything
else in the repo supports developing and verifying it.

Core design principle — **the code does the analysis; the model just orchestrates and narrates.**
The skill must run efficiently on a small, cheap, tool-capable model (Haiku 4.5 class). When
editing, keep intelligence in Python, not in prompts: don't push statistics or data-wrangling into
`SKILL.md` for the model to do by hand.

## Layout

```
wikipedia-interest/          # THE SKILL — self-contained, portable, this is what ships
├── SKILL.md                 # metadata + agent workflow (the model's entry point)
├── INSTALL.md               # install into Claude Code / Codex
├── server.py                # MCP server: typed tools (no Bash needed); thin adapter over scripts/
├── .mcp.json                # declares that server
├── .claude-plugin/          # plugin.json — lets the skill folder bundle the server
├── scripts/
│   ├── wikipop.py           # agent-facing CLI (argparse); the stdlib-only entry point
│   ├── series.py            # Series(dates, views) — the one data structure; replaces DataFrame
│   ├── wiki_api.py          # data layer: title resolution + pageview fetch + on-disk cache (urllib)
│   ├── analysis.py          # pure stats: growth/trend/seasonality/anomalies/confidence
│   └── reporting.py         # stdlib -> self-contained HTML + inline SVG (browsers print it to PDF)
├── references/              # API.md (endpoints), METHODOLOGY.md (how stats are computed)
├── examples.md              # canonical questions -> exact commands
└── requirements.txt         # deps for pip users
verify/e2e_openrouter.py     # dev-only cheap-model E2E harness (NOT part of the skill)
pes_task.md                  # original task brief (Ukrainian)
pyproject.toml / uv.lock     # repo dev environment (uv)
```

## Running things

The skill has **no runtime dependencies at all** — `resolve`, `analyze` and the HTML report run on
the Python 3.12 standard library. uv is only for development and for the optional MCP server.

```bash
uv sync --group dev                              # dev environment (pytest, mcp)
# CLI (run from repo root during dev) — plain python3 is enough:
python3 wikipedia-interest/scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

The CLI has four commands: `resolve`, `analyze`, `report`, `pageviews`. The MCP server exposes three
tools: `resolve_topic`, `analyze_interest`, `build_report`. See
[README.md](README.md) and [wikipedia-interest/examples.md](wikipedia-interest/examples.md) for
the full command surface (`--qid`, `--normalize`, `--check-bots`, `--granularity`, etc.).

Verify changes three ways:
1. **Offline eval suite** (fast, deterministic, no network) — the primary check:
   ```bash
   uv sync --group dev
   uv run pytest evals/
   ```
   Covers analysis correctness, trust judgments, report quality, an end-to-end CLI golden
   against recorded fixtures, and the MCP tool contract driven over real stdio. See [evals/README.md](evals/README.md); refresh fixtures with
   `uv run evals/fixtures/record.py` (the only network-touching part).
2. Run the CLI directly and inspect the JSON.
3. The end-to-end cheap-model harness (live; needs an OpenRouter key):
   ```bash
   export OPENROUTER_API_KEY=sk-or-...
   uv run verify/e2e_openrouter.py
   ```

## Conventions & invariants (don't break these)

- **The CLI is a JSON API.** Every command prints exactly one JSON object to stdout. Errors are
  JSON too (`{"error": ...}`), never tracebacks — use `_fail(...)` / `_emit(...)` in `wikipop.py`.
  Anything printed to stdout that isn't the JSON object will break the agent parsing it.
- **Module boundaries:** `series.py` = the `Series(dates, views)` data type (no I/O, no imports);
  `wiki_api.py` = all network + caching (no printing/argparse); `analysis.py` = pure functions over a
  `Series` (no I/O); `reporting.py` = rendering only; `wikipop.py` = argparse +
  orchestration + JSON; `server.py` = MCP adapter only, no logic of its own. Keep new logic in the
  layer it belongs to.
- **The skill stays dependency-free.** `series`, `wiki_api`, `analysis` and `reporting` must import
  nothing outside the standard library — that is the install story, and `evals` enforce it by running
  the CLI under `python3 -I -S`. Anything heavier (parquet, STL, a chart library, a PDF renderer) does
  not belong in the skill; `server.py` and its `mcp` dependency are the one deliberate exception, and
  they are optional. The report is HTML precisely so the browser, not this repo, renders the PDF.
- **Confidence is a first-class output.** Analysis emits a `confidence` label + reasons; the whole
  point is that the tool judges trustworthiness so the model doesn't have to. Preserve this when
  changing metrics, and update `references/METHODOLOGY.md` if you change how any metric is computed.
- **The model writes the prose; the code guarantees the caveat.** `build_report` takes the model's
  `findings` narrative, but `reporting.trust_block()` appends the confidence label and leading reason
  per edition unconditionally — a report is shared detached from the conversation, so the caveat must
  travel in the file. Never make that block optional or model-supplied.
- **Partial-period trimming:** the latest incomplete period is dropped (`trim_partial_tail`) so a
  half-finished month doesn't read as a decline, and a monthly `--last` window is snapped to the 1st
  in `_period` so the *first* bucket isn't truncated either. Both ends matter — don't remove either.
- **`direction` is seasonality-safe:** it comes from `yoy_pct` whenever there are ≥24 monthly points
  and only falls back to `growth_pct` below that, with `direction_basis` saying which. `growth_pct`
  compares different calendar months, so it can invent a trend on a seasonal topic — never make it
  the headline again, and keep `_yoy_pct` monthly-only.
- **Caching:** network responses cache under `.wikipop_cache/` (gitignored). Repeat/related queries
  are meant to be cheap — don't defeat the cache.
- **Encoding:** JSON is emitted with `ensure_ascii=False`; the PDF uses DejaVu Sans for Cyrillic /
  PL / CZ diacritics. Non-Latin topics and titles must keep working.
- **Framing:** pageviews measure curiosity, not willingness to pay. Keep that caveat in user-facing
  output; don't overstate what the data proves.

## Editing the skill

- If you change CLI flags, tool schemas or behavior, update **all** of: `SKILL.md`, `examples.md`,
  `README.md`, `INSTALL.md` and the relevant `references/*.md`. `SKILL.md` is the model's contract —
  keep it accurate and concise (a small model reads it every time). The CLI and the MCP tools are two
  front doors onto one engine; changing one without the other makes the docs lie.
- Keep the skill folder self-contained and portable — no absolute paths, no repo-specific assumptions.
- Don't commit runtime artifacts (`report.html`, `.wikipop_cache/`) — already gitignored.
