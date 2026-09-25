# Installing `wikipedia-interest`

This folder **is** the skill. Copy it into an agent's skills directory and restart.

## Prerequisites
- **Python 3.12+** — and nothing else.
- Internet access to the Wikimedia APIs. **No API key.**

There are no packages to install. `resolve`, `analyze`, `report` and `pageviews` all run on the
Python standard library, so the whole install is one `cp -R`.

The folder also carries `evals/` and `verify/` — the project's test suite and its cheap-model
harness. They are here because the task brief requires all of the project's own code to live in the
skill directory. They are **developer tooling**: nothing loads or runs them when an agent uses the
skill, and they add no runtime dependency. Delete them if you want a leaner copy.

The report is a self-contained HTML one-pager. To share it as a PDF, open it and choose
Print → Save as PDF — every browser does this, and it honours the `@page { size: A4 }` rule, so the
skill ships no PDF renderer and no dependency for one.

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

The skill drives its CLI through Bash, so the agent needs permission to run it. A narrow grant is
enough — it never needs a blanket one:

```
Bash(python3 scripts/wikipop.py:*)
```

## Codex CLI

```bash
mkdir -p ~/.codex/skills
cp -R wikipedia-interest ~/.codex/skills/wikipedia-interest
```

Restart Codex; invoke with `$wikipedia-interest`. Same CLI, same zero dependencies.

## Verify

From inside the installed skill directory:

```bash
python3 scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

You should get one JSON object with `metrics` and `confidence`. See `examples.md` for more.

## Where files go
- **Cache:** `scripts/.wikipop_cache/` next to the code, not your working directory. Override with
  `--cache-dir` or `WIKIPOP_CACHE_DIR`. Safe to delete; it only makes repeat queries slower.
- **Reports:** where you point `--out` (default `report.html` in the working directory).
