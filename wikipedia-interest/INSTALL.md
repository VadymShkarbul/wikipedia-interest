# Installing `wikipedia-interest`

This folder **is** the skill. Copy it into an agent's skills directory and restart.

## Prerequisites
- **Python 3.12+**
- Internet access to the Wikimedia APIs. **No API key.**
- **uv** ([install](https://docs.astral.sh/uv/)) — only if you want the MCP server or PDF output.
  The CLI's `resolve` and `analyze` run on the standard library alone.

## What each path costs

| Path | Extra packages | Needs a Bash grant? |
|---|---|---|
| CLI — `resolve`, `analyze`, `report` (HTML) | **none** | yes |
| MCP server — typed tools | `mcp` (~27 MB) | **no** |
| `report --format pdf` | `matplotlib` (~61 MB with fontTools/PIL) | yes |

## Claude Code

```bash
mkdir -p ~/.claude/skills
cp -R wikipedia-interest ~/.claude/skills/wikipedia-interest
```

Project-scoped instead, from that repo's root:

```bash
mkdir -p .claude/skills
cp -R /path/to/wikipedia-interest .claude/skills/wikipedia-interest
```

Restart Claude Code. The skill activates when a request matches its description, or invoke it with
`/wikipedia-interest`.

Because the folder carries `.claude-plugin/plugin.json`, it also loads as a plugin
(`wikipedia-interest@skills-dir`), which is what lets it register the bundled MCP server declared in
`.mcp.json`. `uv run` plus the PEP 723 header in `server.py` installs the `mcp` package on first use
— there is no separate install step. Approve the server when prompted, then allow the individual
tools you want:

```
mcp__wikipedia-interest__resolve_topic      (read-only)
mcp__wikipedia-interest__analyze_interest   (read-only)
mcp__wikipedia-interest__build_report       (writes one .html file)
```

Granting these is much narrower than granting `Bash(uv run *)`, which can execute anything.

## Codex CLI

```bash
mkdir -p ~/.codex/skills
cp -R wikipedia-interest ~/.codex/skills/wikipedia-interest
```

Restart Codex; invoke with `$wikipedia-interest`. The plugin wrapper is Claude Code-specific, so
Codex uses the CLI — which needs no dependencies. To use the typed tools there instead, register
`server.py` as an stdio MCP server in Codex's own config.

## Verify

From inside the installed skill directory:

```bash
python3 scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

You should get one JSON object with `metrics` and `confidence`. See `examples.md` for more.

## Where files go
- **Cache:** `scripts/.wikipop_cache/` next to the code, not your working directory. Override with
  `--cache-dir` or `WIKIPOP_CACHE_DIR`. Safe to delete; it only makes repeat queries slower.
- **Reports:** where you point `--out` / `out_path` (default `report.html` in the working directory).
