# evals — results evaluation for the `wikipedia-interest` skill

Dev-only, **offline, deterministic** evaluation of what the skill actually reasons about. Not part
of the shipped skill (like `verify/`). The skill's design bet is *the code does the analysis so a
small model doesn't have to* — so these evals assert the code's outputs directly, on the skill's own
modules. No math is re-implemented here.

The task brief asks that the skill help the agent **evaluate results and verify conclusions**. Each
track below maps to that: correctness of the numbers, honesty of the trust judgments, and quality of
the shareable output.

## Run

```bash
uv sync --group dev          # once: installs pytest + pypdf
uv run pytest evals/         # ~2s, no network
```

Everything runs without network. Track D (CLI golden) uses recorded fixtures and **skips** cleanly
if none are present.

## Tracks

| File | Track | What it proves |
|------|-------|----------------|
| `test_analysis.py` | A — analysis correctness | `analyze_series` computes the right growth / trend / seasonality / anomaly / volatility values across a declarative table of synthetic series (`cases/analysis_cases.py`), incl. the `inf` / `None` / all-zero edge cases; plus `share_per_million` and `bot_share`. Two cases pin the seasonality trap from both sides: a flat seasonal cycle must not read as a decline, and a clean ramp must not read as seasonal. |
| `test_trust.py` | B — trustworthiness | The `confidence` label + exact reason literal for every rule (low volume, short history, missing periods, spike-heavy, bot-heavy, clean); that daily series are judged on a monthly-equivalent scale and never claim a year-over-year basis; that a weak R² downgrades only when `direction` actually rests on it; spike detection; and `resolve_titles` returning the right `method` — `wikidata` / `gap` / `search` / `none` — so real coverage gaps are flagged, not silently compared. |
| `test_report.py` | C — report / output quality | `build_findings` draws the right conclusions (recommends the strongest *rising, higher-volume* edition, deprioritizes when none rise, flags gaps, reports size-adjusted attention share, honors an analyst `--note`); and `build_report` writes a genuine **single-page** PDF + PNG (page count checked with `pypdf`). |
| `test_cli_golden.py` | D — end-to-end, offline | Runs the real `wikipop.py` CLI as a subprocess against the warmed fixture cache and diffs the JSON against committed goldens; asserts the JSON **error contract** (bad input → `{"error": ...}` + exit 1, never a traceback) and that a monthly `--last` window is snapped to whole months (a mid-month start returns a truncated first bucket). |

## How determinism is achieved

- **Synthetic series** (Tracks A & C) are built in-process — pure functions, nothing to record.
- **Crafted cache entries** (Track B resolution) are written with the skill's own `_cache_key`, so
  `resolve_titles` reads them as real cache hits — exercising the actual code path offline.
- **Recorded fixtures** (Track D) live in `fixtures/cache/` (real Wikimedia responses, committed).
  The `warm_cache` fixture copies them to a temp dir and refreshes mtimes so they never TTL-expire.
  All commands are pinned (`--qid`, `--start`, `--end`), and historical pageviews are stable, so the
  goldens stay valid.

## Refreshing fixtures / goldens

Only when you deliberately re-baseline (changed the pinned window, or a metric definition):

```bash
uv run evals/fixtures/record.py     # the ONLY network-touching part; re-records cache + goldens
```

Pinned cases live in `cli_cases.py` (shared by the recorder and the test).

## Relationship to `verify/`

`verify/e2e_openrouter.py` is the complementary **live, agent-behavior** smoke test: it checks a
small tool-capable model can drive the skill end-to-end. It needs an OpenRouter key and network and
is non-deterministic by nature. These evals are its deterministic, offline counterpart.

## Not covered (future)

- LLM-judge scoring of the narrated prose, and multi-query cheap-model agent evals (would extend
  `verify/`).
