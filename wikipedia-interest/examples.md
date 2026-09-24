# Worked examples

Run from this skill's directory (the folder holding `SKILL.md`). Each command prints a JSON summary;
`report` also writes a PDF + PNG. `uv run` auto-installs the CLI's dependencies on first use.

## 1. Compare growth of "intermittent fasting" — Polish vs Czech, last 2 years
```
uv run scripts/wikipop.py report \
  --topic "intermittent fasting" --langs pl,cs --last 2y --out fasting.pdf
```
What to expect: Polish is a **coverage gap** (no article for the concept — cannot compare), Czech has
data. Say so explicitly rather than comparing nothing. Add `uk` to have a real comparison:
```
uv run scripts/wikipop.py report --topic "intermittent fasting" --langs cs,uk --last 2y --out fasting.pdf
```

## 2. Is interest in astronomy growing on Ukrainian Wikipedia — and can we trust it?
```
uv run scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```
Read `direction` together with `direction_basis` (it says whether to quote `yoy_pct` or `growth_pct`),
and especially `confidence`. Lead with the confidence label and its reasons; mention any `anomalies`.
Astronomy is a school-calendar topic — expect a September peak, and expect the `confidence` reasons to
tell you to quote the year-over-year number rather than the start-vs-end one. If you want a shareable
version, swap `analyze` → `report --out astro.pdf`.

## 3. Language-learning app: compare interest in "English language" across editions, recommend next audiences
```
uv run scripts/wikipop.py report \
  --topic "English language" --langs en,pl,uk,cs,de,es --last 3y --normalize --out english.pdf
```
Compare the indexed chart (shape, not size). `--normalize` adds a `share/M` column so a small edition
with a big *share* of attention isn't hidden by en's huge raw counts (uk ≈137/M vs en ≈46/M). The auto
Findings block ranks candidates to research next. Override the narrative with `--note "..."` if needed.

## 4. Disambiguate an ambiguous topic (e.g. Mercury)
```
uv run scripts/wikipop.py resolve --topic "mercury" --langs en,uk
```
Read `candidates`: the top auto-pick is the Ford car marque (Q613883); the planet is Q308, the element
Q925. Pin the one you mean and analyze:
```
uv run scripts/wikipop.py report --topic "mercury" --qid Q308 --langs en,uk --last 2y --out mercury.pdf
```

## Handy variations
- Check resolution before committing: `wikipop.py resolve --topic "meditation" --langs uk,pl,cs`
- Quantify bot/crawler traffic: add `--check-bots` to see `bot_share` and a confidence adjustment.
- Fair cross-edition comparison: add `--normalize` for share of attention (views per million).
- Zoom into a recent surge: `--granularity daily --last 90d`.
- One raw article series: `wikipop.py pageviews --lang uk --article "Астрономія" --start 20230101 --end 20250101`
