# Wikimedia API reference (as used by this skill)

No API key is required, but the Wikimedia policy requires a descriptive `User-Agent` (this skill sets
one; override with the `WIKI_UA` env var). Be polite: the skill caches responses and retries with
backoff.

## 1. Pageviews (per article)

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
    {project}/{access}/{agent}/{article}/{granularity}/{start}/{end}
```

| Param        | Values                                                        | Notes |
|--------------|--------------------------------------------------------------|-------|
| `project`    | `uk.wikipedia`, `pl.wikipedia`, `cs.wikipedia`, `en.wikipedia`, … | edition host |
| `access`     | `all-access` \| `desktop` \| `mobile-app` \| `mobile-web`      | default `all-access` |
| `agent`      | `user` \| `all-agents` \| `spider` \| `automated`             | skill default `user` (excludes bots) |
| `article`    | page title, spaces → `_`, URL-encoded                         | case/diacritics sensitive |
| `granularity`| `daily` \| `monthly`                                          | skill default `monthly` |
| `start`,`end`| `YYYYMMDD00` (10 digits)                                      | skill accepts `YYYYMMDD`, appends `00` |

Response:
```json
{"items":[{"project":"uk.wikipedia","article":"Астрономія","granularity":"monthly",
           "timestamp":"2024010100","access":"all-access","agent":"user","views":3700}, ...]}
```

Gotchas:
- **Data starts 2015-07-01.** Earlier ranges return nothing.
- **The latest month/day is partial** and, if kept, badly skews growth. The skill drops it
  (`trim_partial_tail`) and reports what it dropped in `dropped`.
- **404** = no such article or no data in range → the skill returns an empty series (not an error).
- Titles differ per edition; always resolve first (below).

## 2. Aggregate pageviews (edition total)

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate/
    {project}/{access}/{agent}/{granularity}/{start}/{end}
```
Same params as per-article, minus `article`. Returns the whole edition's total views per period (e.g.
uk.wikipedia ≈ 80–94M/month). The skill divides an article's views by this to get a **share of
attention** (`--normalize`), so editions of very different sizes compare fairly. Cached per project/range.

## 3. Title resolution

Article titles differ across editions, so a topic must be mapped to the right title per language.

### Preferred: Wikidata (one concept → per-language titles)
```
GET https://www.wikidata.org/w/api.php?action=wbsearchentities&search=<topic>&language=<lang>&format=json&limit=5
GET https://www.wikidata.org/w/api.php?action=wbgetentities&ids=<QID>&props=sitelinks&sitefilter=ukwiki|plwiki|…&format=json
```
The skill searches in English **and** the first target language, then merges candidates (multi-language
search finds concepts named in the topic's own language, e.g. "інтервальне голодування" → Q1666254).
It returns the top **candidates** (id/label/description) so an ambiguous word can be disambiguated:
"mercury" ranks the Ford car marque (Q613883) above the planet (Q308) and element (Q925) — the caller
picks with `--qid`.

Sitelink key = `<lang>wiki` (e.g. `ukwiki`), and its `title` is the exact article name. If a language
has no sitelink, that edition genuinely lacks an article for the concept — a **coverage gap** (the skill
marks `found:false, method:"gap"`). We do **not** fuzzy-search in that case, because search returns
loosely-related articles (e.g. "oxidative stress" for "intermittent fasting" in Polish) and would
silently analyze the wrong topic.

### Fallback: per-language search (only when no Wikidata concept exists)
```
GET https://<lang>.wikipedia.org/w/api.php?action=query&list=search&srsearch=<topic>&srlimit=1&format=json
```
Returns the top matching title (`method:"search"`, lower confidence).

## 4. Discovery (not used yet, noted for growth)
Most-viewed articles per edition:
```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/{access}/{year}/{month}/all-days
```
Useful for suggesting topics rather than analyzing a given one.
