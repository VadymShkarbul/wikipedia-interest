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
├── scripts/               # wikipop.py CLI + wiki_api / analysis / reporting
├── references/            # API.md, METHODOLOGY.md
├── examples.md
└── requirements.txt
verify/                    # dev-only cheap-model end-to-end harness (not part of the skill)
pes_task.md                # the original task brief
```

## Quick start
Dependencies are managed with **uv**:
```bash
uv sync
```
Run a report (resolves titles, fetches pageviews, analyzes, writes PDF + PNG, prints JSON):
```bash
uv run wikipedia-interest/scripts/wikipop.py report \
  --topic "astronomy" --langs uk --last 2y --out report.pdf
```
See [`wikipedia-interest/examples.md`](wikipedia-interest/examples.md) for more, including
disambiguation (`--qid`), share-of-attention (`--normalize`), and bot checks (`--check-bots`).

## Verify on a cheap model
```bash
export OPENROUTER_API_KEY=sk-or-...
export OPENROUTER_MODEL="deepseek/deepseek-v4-flash"   # or another tool-capable model
uv run verify/e2e_openrouter.py
```

## License
MIT (see the skill's `SKILL.md`).
