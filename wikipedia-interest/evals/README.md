# evals — results evaluation for the `wikipedia-interest` skill

Dev-only, **offline, deterministic** evaluation of what the skill actually reasons about. It lives
inside the skill folder (as does `verify/`) because the brief requires all of the project's own code
to be in the skill directory — but an agent using the skill never loads it. The skill's design bet is *the code does the analysis so a
small model doesn't have to* — so these evals assert the code's outputs directly, on the skill's own
modules. No math is re-implemented here.

The task brief asks that the skill help the agent **evaluate results and verify conclusions**. Each
track below maps to that: correctness of the numbers, honesty of the trust judgments, and quality of
the shareable output.

## Run

```bash
uv sync --group dev          # once: installs pytest
uv run pytest                # ~0.5s, no network
```

Everything runs without network. Track D (CLI golden) uses recorded fixtures and **skips** cleanly
if none are present — so a green run in a checkout without `fixtures/cache/` is *not* full coverage:
five tests, including the dependency-free invariant, simply did not run. Check the skip count.

## Tracks

| File | Track | What it proves |
|------|-------|----------------|
| `test_analysis.py` | A — analysis correctness | `analyze_series` computes the right growth / trend / seasonality / anomaly / volatility values across a declarative table of synthetic series (`cases/analysis_cases.py`), incl. the `inf` / `None` / all-zero edge cases; plus `share_per_million` and `bot_share`. Two cases pin the seasonality trap from both sides: a flat seasonal cycle must not read as a decline, and a clean ramp must not read as seasonal. |
| `test_trust.py` | B — trustworthiness | The `confidence` label + exact reason literal for every rule (low volume, short history, missing periods, spike-heavy, bot-heavy, clean); that daily series are judged on a monthly-equivalent scale and never claim a year-over-year basis; that a weak R² downgrades only when `direction` actually rests on it; spike detection; and `resolve_titles` returning the right `method` — `wikidata` / `gap` / `search` / `none` — so real coverage gaps are flagged, not silently compared. |
| `test_report.py` | C — report / output quality | The **trust guarantee**: `trust_block` states a confidence label and its leading caveat for every edition, quotes the number `direction_basis` names, and cannot be suppressed by a rosy model-written narrative. Plus the artifact itself — self-contained HTML (inline SVG, no network refs, no scripts), non-Latin titles rendered literally, markup in titles escaped. |
| `test_series.py` | F — the `Series` type | The four methods every metric is computed over: `sorted_by_date` moves views *with* their dates and leaves the original alone, `drop_last` removes exactly one point (what `trim_partial_tail` relies on), `to_records` emits the ISO date shape the `pageviews` command promises, and mismatched list lengths are rejected at construction rather than corrupting arithmetic later. |
| `test_cache.py` | G — cache & retry policy | The paths every other track skips by pre-seeding a cache: the **write** actually happens (this is what makes "repeat queries are cheap" true), a stale entry is refetched, a corrupt entry self-heals instead of poisoning later runs, a 404 is cached as an answer rather than raised, transient 5xx/transport failures are retried, and three failures raise `WikiError` — which is what the CLI converts into its JSON error contract. Network is replaced by monkeypatching `wiki_api._request`; `time.sleep` is stubbed so the real 9s backoff doesn't dominate the suite. |
| `test_cli_golden.py` | D — end-to-end, offline | Runs the real `wikipop.py` CLI as a subprocess against the warmed fixture cache and diffs the JSON against committed goldens; asserts the JSON **error contract** (bad input → `{"error": ...}` + exit 1, never a traceback) and that a monthly `--last` window is snapped to whole months (a mid-month start returns a truncated first bucket). Also pins the **dependency-free invariant**: the CLI is run under `python3 -I -S`, with site-packages disabled so pandas/numpy/requests/matplotlib are all unimportable, and must still reproduce the golden byte-for-byte. |

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

## Not covered

- **That the one-pager is genuinely one page.** v1 opened the PDF and asserted
  `len(PdfReader(...).pages) == 1`. The browser now renders the PDF, so nothing offline can see the
  paginated result. `test_report_declares_a4_and_holds_exactly_one_page_container` is a deliberate
  *proxy*: it checks the A4 rule is declared and the document is a single `.page` block, and it
  would still pass if the content overflowed onto a second sheet. Verified by eye instead.
- **Wikidata candidate disambiguation** (the en + target-language merge that fixes "mercury" → the
  planet, not the Ford marque). Both goldens pin `--qid`, so `candidates` is `[]` in each.
- `--normalize` / `--check-bots` end to end; both goldens carry `null` for those metrics.
- LLM-judge scoring of the narrated prose, and multi-query cheap-model agent evals (would extend
  `verify/`).
