# Worked examples

Each example gives the MCP tool call and the equivalent CLI command. CLI paths are relative to this
skill's directory. `resolve` and `analyze` need no installed packages.

## 1. Compare "intermittent fasting" — Polish vs Czech, last 2 years

```
analyze_interest(topic="intermittent fasting", langs=["pl","cs"], window="2y")
```
```
python3 scripts/wikipop.py analyze --topic "intermittent fasting" --langs pl,cs --last 2y
```

What to expect: Polish is a **coverage gap** (no article for the concept — cannot compare), Czech has
data. Say so explicitly rather than comparing nothing. Add `uk` for a real comparison.

## 2. Is astronomy growing on Ukrainian Wikipedia — and can we trust it?

```
analyze_interest(topic="astronomy", langs=["uk"], window="2y")
```
```
python3 scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```

Read `direction` with `direction_basis` (it says whether to quote `yoy_pct` or `growth_pct`), and
especially `confidence`. Astronomy is a school-calendar topic: expect a September peak, and expect
the reasons to tell you to quote the year-over-year number rather than start-vs-end. On real data
`growth_pct` is about **+59%** while `yoy_pct` is **+11%** — same series, very different story. The
basis says `yoy`, so **+11%** is the honest headline.

## 3. Language-learning app: compare "English language" across editions, recommend next audiences

```
analyze_interest(topic="English language", langs=["en","pl","uk","cs","de","es"],
                 window="3y", normalize=True)
```
```
python3 scripts/wikipop.py analyze --topic "English language" \
  --langs en,pl,uk,cs,de,es --last 3y --normalize
```

Compare shape, not size. `normalize` adds `share_per_million_mean` so a small edition with a big
*share* of attention isn't hidden by en's raw counts (uk ≈137/M vs en ≈46/M). Then write the
recommendation yourself and pass it to the report.

## 4. Disambiguate an ambiguous topic (Mercury)

```
resolve_topic(topic="mercury", langs=["en","uk"])
```
```
python3 scripts/wikipop.py resolve --topic "mercury" --langs en,uk
```

Read `candidates`: the top auto-pick is the Ford car marque (Q613883); the planet is Q308, the
element Q925. Pin the one you mean:

```
analyze_interest(topic="mercury", qid="Q308", langs=["en","uk"], window="2y")
```

## 5. A shareable one-pager

```
build_report(topic="astronomy", langs=["uk","pl"], window="2y",
             findings="Ukrainian interest is up 11% year-over-year with a September school peak. "
                      "Polish volume is higher but flat. Validate uk with a landing-page test "
                      "before committing course production.")
```
```
python3 scripts/wikipop.py report --topic "astronomy" --langs uk,pl --last 2y \
  --out astro.html --findings "..."
```

**You write `findings`.** The confidence label and leading caveat for each edition are appended by
the tool, so the file can't be shared without them. Add `--format pdf` (needs matplotlib) for a PDF.

## Handy variations
- Quantify crawler traffic: `check_bots=True` / `--check-bots`.
- Zoom into a recent surge: `granularity="daily", window="90d"`.
- One raw article series: `python3 scripts/wikipop.py pageviews --lang uk --article "Астрономія" --start 20230101 --end 20250101`
