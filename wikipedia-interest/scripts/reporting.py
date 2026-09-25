"""Reporting: render a shareable one-pager as self-contained HTML with inline SVG charts.

Standard library only — nothing to install, no fonts to ship. SVG/HTML text is Unicode natively, so
Cyrillic and PL/CZ article titles render without any font handling. `@page { size: A4 }` keeps
"one page" meaningful: any browser's Print → Save as PDF produces the shareable PDF, which is why
this skill no longer carries a PDF renderer of its own.

Division of labour: the *model* writes the narrative (`findings`), because that is the one part of
this skill a language model does better than an if/elif ladder. The *code* appends the confidence
label and its leading reason for every edition, so a caveat can never be lost when the file is
shared on its own, detached from the conversation that produced it.
"""
from __future__ import annotations

import datetime as dt
import html
import math
from typing import Optional

LIMITATIONS = (
    "Assumptions & limitations: Wikipedia pageviews are a proxy for public curiosity, not for "
    "market size or willingness to pay. Editions differ in audience size and internet habits, so "
    "compare trends (shape), not absolute counts. Bot traffic is excluded (agent=user). Spikes are "
    "often single news/events, not durable interest. Data begins 2015-07; the latest partial period "
    "is dropped. Always validate a promising signal with other evidence before investing."
)

# Colour-blind-safe qualitative palette; index by series position.
PALETTE = ["#2b6cb0", "#c05621", "#2f855a", "#6b46c1", "#b83280", "#00707f"]


# --- the trust guarantee -----------------------------------------------------

def trust_block(series_list: list) -> list[str]:
    """One mechanical line per edition: direction, volume, confidence and its leading reason.

    Never model-authored. This is the caveat that must survive the report being forwarded.
    """
    lines = []
    for s in series_list:
        m = s.get("metrics", {})
        if not s.get("found"):
            lines.append(f"{s['lang']}: no article for this concept (coverage gap) — not comparable.")
            continue
        if not m.get("available"):
            lines.append(f"{s['lang']} ({s.get('title') or '?'}): article exists but no pageview data in range.")
            continue
        conf = m["confidence"]
        basis = m.get("direction_basis")
        if basis == "yoy" and m.get("yoy_pct") is not None:
            num = f"{m['yoy_pct']:+.0f}% year-over-year"
        else:
            g = m.get("growth_pct")
            num = ("from a near-zero baseline" if g == "inf"
                   else "change unclear" if g is None else f"{g:+.0f}% over the period")
        reason = f" {conf['reasons'][0]}" if conf["reasons"] else ""
        lines.append(
            f"{s['lang']} ({s.get('title')}): {m['direction']} ({num}); "
            f"~{m['mean_views']:.0f} views/mo; confidence {conf['label']}.{reason}"
        )
    return lines


# --- SVG charting ------------------------------------------------------------

def _nice_step(vmax: float, target: int = 4) -> float:
    """A round axis step (1/2/2.5/5 x 10^k) giving roughly `target` gridlines below vmax."""
    if vmax <= 0:
        return 1.0
    raw = vmax / target
    mag = 10.0 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if mult * mag >= raw:
            return mult * mag
    return 10 * mag


def _fmt_count(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M".replace(".0M", "M")
    if v >= 1_000:
        return f"{v / 1_000:.1f}k".replace(".0k", "k")
    return f"{v:.0f}"


def _drawn(series_list: list) -> list:
    """The series that actually have data, each paired with its palette colour.

    One function so the chart and the legend can never disagree about which colour belongs to
    which edition — they are rendered separately, but both index off this list.
    """
    out = []
    for s in series_list:
        d = s.get("data")
        if d is None or d.empty:
            continue
        out.append((s, d, PALETTE[len(out) % len(PALETTE)]))
    return out


def _legend_html(series_list: list, indexed: bool) -> str:
    """The chart legend, as HTML rather than SVG.

    It used to be laid out inside the SVG by estimating text width at 6px per character. That
    estimate cannot be right: a static generator has no way to measure rendered text (SVG's
    getComputedTextLength needs a DOM), and the error compounds per entry — with four or more
    editions the legend ran past the fixed viewBox, which SVG clips, so editions silently vanished
    from the key while their lines stayed on the chart. Handing the job to the browser removes the
    estimate: it measures and wraps text itself, in any script and at any width.
    """
    items = []
    for s, _, colour in _drawn(series_list):
        label = s["lang"] if indexed else f"{s['lang']}: {s.get('title') or ''}"
        items.append(f'<li><span class="swatch" style="background:{colour}"></span>'
                     f'{html.escape(label)}</li>')
    return f'<ul class="legend">{"".join(items)}</ul>' if items else ""


def _line_chart(series_list: list, title: str, indexed: bool,
                width: int = 470, height: int = 235) -> str:
    """One inline SVG line chart. `indexed` rebases every series to 100 at its first point.

    The legend is rendered separately by _legend_html; see there for why.
    """
    left, right, top, bottom = 52, 12, 26, 34
    pw, ph = width - left - right, height - top - bottom

    drawn = _drawn(series_list)
    if not drawn:
        return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}: no data">'
                f'<text x="{width/2}" y="{height/2}" text-anchor="middle" class="nodata">no data</text></svg>')

    # Value series, after optional rebasing.
    plots = []
    for s, d, colour in drawn:
        vals = [float(v) for v in d.views]
        if indexed:
            base = next((v for v in vals if v > 0), 1.0)
            vals = [v / base * 100.0 for v in vals]
        plots.append((s, d.dates, vals, colour))

    x_min = min(d[0].toordinal() for _, d, _, _ in plots)
    x_max = max(d[-1].toordinal() for _, d, _, _ in plots)
    y_max = max(max(v) for _, _, v, _ in plots)
    step = _nice_step(y_max)
    y_top = math.ceil(y_max / step) * step if y_max > 0 else step

    def px(o: int) -> float:
        return left + (0 if x_max == x_min else (o - x_min) / (x_max - x_min) * pw)

    def py(v: float) -> float:
        return top + ph - (v / y_top * ph if y_top else 0)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">']
    out.append(f'<text x="{left}" y="16" class="ctitle">{html.escape(title)}</text>')

    # horizontal gridlines + y labels
    n_lines = int(round(y_top / step))
    for k in range(n_lines + 1):
        v = k * step
        y = py(v)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + pw}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{left - 6}" y="{y + 3:.1f}" class="tick" text-anchor="end">{_fmt_count(v)}</text>')

    # x labels: up to 6 evenly spaced dates from the longest series
    ref_dates = max((d for _, d, _, _ in plots), key=len)
    n_lab = min(6, len(ref_dates))
    idxs = [round(i * (len(ref_dates) - 1) / max(1, n_lab - 1)) for i in range(n_lab)]
    for i in sorted(set(idxs)):
        d = ref_dates[i]
        x = px(d.toordinal())
        out.append(f'<text x="{x:.1f}" y="{top + ph + 16}" class="tick" text-anchor="middle" '
                   f'transform="rotate(-30 {x:.1f} {top + ph + 16})">{d.strftime("%Y-%m")}</text>')

    if indexed:
        y100 = py(100.0)
        out.append(f'<line x1="{left}" y1="{y100:.1f}" x2="{left + pw}" y2="{y100:.1f}" class="ref"/>')

    # the lines, plus spike markers
    for s, dates, vals, colour in plots:
        pts = " ".join(f"{px(d.toordinal()):.1f},{py(v):.1f}" for d, v in zip(dates, vals))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="1.6"/>')
        spikes = sorted(s.get("metrics", {}).get("anomalies", []),
                        key=lambda a: a["views"], reverse=True)[:3]
        by_date = {d.isoformat(): v for d, v in zip(dates, vals)}
        for an in spikes:
            if an["date"] in by_date:
                x = px(dt.date.fromisoformat(an["date"]).toordinal())
                y = py(by_date[an["date"]])
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="none" stroke="{colour}"/>')
                out.append(f'<text x="{x:.1f}" y="{y - 6:.1f}" class="spike" fill="{colour}" '
                           f'text-anchor="middle">spike</text>')

    # axes
    out.append(f'<line x1="{left}" y1="{top + ph}" x2="{left + pw}" y2="{top + ph}" class="axis"/>')
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + ph}" class="axis"/>')

    out.append("</svg>")
    return "".join(out)


# --- table -------------------------------------------------------------------

def _table_html(series_list: list, normalized: bool) -> str:
    heads = ["lang", "article", "views/mo", "growth", "YoY", "trend", "confidence"]
    if normalized:
        heads.insert(3, "share/M")
    rows = []
    for s in series_list:
        m = s.get("metrics", {})
        if not s.get("found"):
            cells = [s["lang"], "(no article)"] + ["–"] * (len(heads) - 3) + ["gap"]
        elif not m.get("available"):
            cells = [s["lang"], s.get("title") or ""] + ["–"] * (len(heads) - 3) + ["no data"]
        else:
            g = m["growth_pct"]
            cells = [
                s["lang"], s.get("title") or "",
                f"{m['mean_views']:,.0f}",
                "n/a" if g in (None, "inf") else f"{g:+.0f}%",
                "n/a" if m["yoy_pct"] is None else f"{m['yoy_pct']:+.0f}%",
                m["direction"],
                m["confidence"]["label"],
            ]
            if normalized:
                sm = m.get("share_per_million_mean")
                cells.insert(3, "n/a" if sm is None else f"{sm:.1f}")
        cls = ""
        if cells[-1] in ("gap", "no data", "low"):
            cls = ' class="weak"'
        rows.append("<tr>" + "".join(f"<td{cls if i == len(cells) - 1 else ''}>{html.escape(str(c))}</td>"
                                     for i, c in enumerate(cells)) + "</tr>")
    head = "".join(f"<th>{html.escape(h)}</th>" for h in heads)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


# --- page --------------------------------------------------------------------

_CSS = """
:root { --ink:#1a202c; --muted:#4a5568; --rule:#e2e8f0; --head:#2b6cb0; --bg:#ffffff; }
* { box-sizing: border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
       font:13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
.page { max-width: 820px; margin: 0 auto; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:var(--muted); font-size:12px; margin-bottom:16px; }
.charts { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.charts > div { flex:1 1 360px; min-width:0; }
svg { width:100%; height:auto; }
.ctitle { font-size:10px; font-weight:600; fill:var(--ink); }
.tick { font-size:8px; fill:var(--muted); }
ul.legend { display:flex; flex-wrap:wrap; gap:3px 12px; list-style:none;
            margin:2px 0 0; padding:0; font-size:10px; color:var(--muted); }
ul.legend li { display:flex; align-items:center; gap:5px; min-width:0; }
ul.legend .swatch { width:12px; height:2px; flex:none; border-radius:1px; }
.spike { font-size:7px; }
.nodata { font-size:11px; fill:var(--muted); }
.grid { stroke:var(--rule); stroke-width:1; }
.axis { stroke:#a0aec0; stroke-width:1; }
.ref  { stroke:#a0aec0; stroke-width:1; stroke-dasharray:4 3; }
table { width:100%; border-collapse:collapse; font-size:11.5px; margin-bottom:14px; }
th { background:var(--head); color:#fff; text-align:left; padding:5px 7px; font-weight:600; }
td { padding:5px 7px; border-bottom:1px solid var(--rule); }
td.weak { color:#9b2c2c; }
h2 { font-size:13px; margin:14px 0 6px; }
.findings { white-space:pre-wrap; }
ul.trust { margin:6px 0 0; padding-left:18px; color:var(--muted); font-size:11.5px; }
footer { margin-top:16px; padding-top:10px; border-top:1px solid var(--rule);
         color:var(--muted); font-size:10px; }
@media print { body { padding:0; } .page { max-width:none; } }
@page { size: A4 portrait; margin: 14mm; }
"""


def build_report(topic: str, period_label: str, series_list: list, out_path: str,
                 findings: Optional[str] = None, normalized: bool = False) -> dict:
    """Render the one-pager to a single self-contained HTML file. Returns {"html": path}.

    `findings` is the model's narrative. Whatever it says (or omits), `trust_block` is appended
    verbatim, so the confidence label and its leading reason always travel with the numbers.
    """
    langs = ", ".join(s["lang"] for s in series_list)
    narrative = (findings or "").strip()
    body = [
        '<div class="page">',
        f"<h1>Wikipedia interest: {html.escape(topic)}</h1>",
        f'<div class="sub">Editions: {html.escape(langs)} &nbsp;|&nbsp; Period: {html.escape(period_label)}'
        f" &nbsp;|&nbsp; Generated: {dt.date.today().isoformat()}</div>",
        '<div class="charts">',
        f"<div>{_line_chart(series_list, 'Pageviews (raw)', indexed=False)}"
        f"{_legend_html(series_list, indexed=False)}</div>",
        f"<div>{_line_chart(series_list, 'Indexed to 100 at start (compare shape, not size)', indexed=True)}"
        f"{_legend_html(series_list, indexed=True)}</div>",
        "</div>",
        _table_html(series_list, normalized),
        "<h2>Findings</h2>",
    ]
    if narrative:
        body.append(f'<div class="findings">{html.escape(narrative)}</div>')
    else:
        body.append('<div class="findings">(No narrative supplied — the figures and the '
                    "confidence notes below stand on their own.)</div>")
    body.append("<ul class=\"trust\">")
    body.extend(f"<li>{html.escape(line)}</li>" for line in trust_block(series_list))
    body.append("</ul>")
    body.append(f"<footer>{html.escape(LIMITATIONS)}</footer>")
    body.append("</div>")

    doc = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>Wikipedia interest: {html.escape(topic)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n" + "\n".join(body) + "\n</body>\n</html>\n"
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return {"html": out_path}
