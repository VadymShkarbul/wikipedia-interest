# Worked examples

Canonical questions mapped to the exact command. Paths are relative to this skill's directory.
Nothing here needs an installed package — the whole CLI runs on the standard library.

## 1. Compare "intermittent fasting" — Polish vs Czech, last 2 years

```
python3 scripts/wikipop.py analyze --topic "intermittent fasting" --langs pl,cs --last 2y
```

What to expect: Polish is a **coverage gap** (no article for the concept — cannot compare), Czech has
data. Say so explicitly rather than comparing nothing. Add `uk` for a real comparison.

## 2. Is astronomy growing on Ukrainian Wikipedia — and can we trust it?

```
python3 scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

Read `direction` with `direction_basis` (it says whether to quote `yoy_pct` or `growth_pct`), and
especially `confidence`. Astronomy is a school-calendar topic: expect a September peak, and expect
the reasons to tell you to quote the year-over-year number rather than start-vs-end. The two numbers
tell very different stories on the same series — measured 2026-09, `growth_pct` was **-81.9%** while
`yoy_pct` was **-59.6%**, because a window ending in the June low is compared against a September
peak. The basis says `yoy`, so **-59.6%** is the honest headline. (The figures move as the window
rolls forward; the gap between them is the durable point.)

## 3. Language-learning app: compare "English language" across editions, recommend next audiences

```
python3 scripts/wikipop.py analyze --topic "English language" \
  --langs en,pl,uk,cs,de,es --last 3y --normalize
```

Compare shape, not size. `--normalize` adds `share_per_million_mean` so a small edition with a big
*share* of attention isn't hidden by en's raw counts (uk ≈137/M vs en ≈46/M). Then write the
recommendation yourself and pass it to the report.

## 4. Disambiguate an ambiguous topic (Mercury)

```
python3 scripts/wikipop.py resolve --topic "mercury" --langs en,uk
```

Read `candidates`: the top auto-pick is the Ford car marque (Q613883); the planet is Q308, the
element Q925. Pin the one you mean:

```
python3 scripts/wikipop.py analyze --topic "mercury" --qid Q308 --langs en,uk --last 2y
```

## 5. A shareable one-pager

```
python3 scripts/wikipop.py report --topic "astronomy" --langs uk,pl --last 2y \
  --out astro.html \
  --findings "<your narrative: what the numbers mean for the decision, and what to validate next>"
```

**You write `--findings`.** The confidence label and leading caveat for each edition are appended by
the code, so the file can't be shared without them. The output is one self-contained HTML file; open
it and Print → Save as PDF for a one-page PDF to send on.

## Handy variations
- Quantify crawler traffic: `--check-bots`.
- Zoom into a recent surge: `--granularity daily --last 90d`.
- One raw article series: `python3 scripts/wikipop.py pageviews --lang uk --article "Астрономія" --start 20230101 --end 20250101`
