"""Reporting: render a one-page PDF (+ PNG) from analyzed series. matplotlib only, no system libs.

Layout (A4 portrait): title -> raw line chart + indexed-to-100 chart -> per-language metrics table
-> auto findings -> fixed assumptions/limitations footer. DejaVu Sans (matplotlib default) renders
Cyrillic and PL/CZ diacritics.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.gridspec import GridSpec


def _format_time_axis(ax):
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for lbl in ax.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha("right")

LIMITATIONS = (
    "Assumptions & limitations: Wikipedia pageviews are a proxy for public curiosity, not for "
    "market size or willingness to pay. Editions differ in audience size and internet habits, so "
    "compare trends (shape), not absolute counts. Bot traffic is excluded (agent=user). Spikes are "
    "often single news/events, not durable interest. Data begins 2015-07; the latest partial period "
    "is dropped. Always validate a promising signal with other evidence before investing."
)


def _direction_phrase(m: dict) -> str:
    d = m.get("direction")
    g = m.get("growth_pct")
    gtxt = "n/a" if g in (None, "inf") else f"{g:+.0f}%"
    if d == "up":
        return f"rising ({gtxt} over the period)"
    if d == "down":
        return f"declining ({gtxt} over the period)"
    if d == "flat":
        return f"broadly flat ({gtxt})"
    return "unclear"


def build_findings(topic: str, series_list: list, note: Optional[str]) -> str:
    if note:
        return note
    lines = []
    found = [s for s in series_list if s.get("metrics", {}).get("available")]
    gaps = [s for s in series_list if not s.get("found")]
    empty = [s for s in series_list if s.get("found") and not s.get("metrics", {}).get("available")]

    for s in found:
        m = s["metrics"]
        conf = m["confidence"]
        share = m.get("share_per_million_mean")
        share_txt = f"; {share:.1f} views/M of edition traffic" if share is not None else ""
        lines.append(
            f"- {s['lang']} ({s['title']}): interest is {_direction_phrase(m)}; "
            f"YoY {('n/a' if m['yoy_pct'] is None else f'{m['yoy_pct']:+.0f}%')}; "
            f"~{m['mean_views']:.0f} views/mo{share_txt}; confidence {conf['label']}."
        )
    if found:
        rising = [s for s in found if s["metrics"]["direction"] == "up"]
        if len(found) > 1:
            if rising:
                best = max(rising, key=lambda s: s["metrics"].get("mean_views") or 0)
                lines.append(
                    f"- Recommendation: strongest rising, higher-volume signal is {best['lang']} "
                    f"({best['title']}) — a reasonable audience to research next."
                )
            else:
                lines.append("- Recommendation: no edition shows clear rising interest; deprioritize or pick another topic.")
        # When normalized, also point out where the topic wins the largest share of attention.
        with_share = [s for s in found if s["metrics"].get("share_per_million_mean") is not None]
        if len(with_share) > 1:
            top = max(with_share, key=lambda s: s["metrics"]["share_per_million_mean"])
            lines.append(
                f"- Attention share (size-adjusted) is highest in {top['lang']} "
                f"({top['metrics']['share_per_million_mean']:.1f} views per million) — this can flip a "
                f"raw-count ranking dominated by large editions."
            )
    for s in gaps:
        lines.append(f"- {s['lang']}: no matching article for this concept (coverage gap) — cannot compare.")
    for s in empty:
        lines.append(f"- {s['lang']} ({s['title']}): article exists but has no pageview data in range.")
    return "\n".join(lines) if lines else "- No usable data for the requested topic/languages."


def _plot_raw(ax, series_list):
    plotted = False
    for s in series_list:
        df = s.get("df")
        if df is None or df.empty:
            continue
        (line,) = ax.plot(df["date"], df["views"], marker="o", ms=2.5, lw=1.4, label=f"{s['lang']}: {s['title']}")
        top_anoms = sorted(s.get("metrics", {}).get("anomalies", []), key=lambda a: a["views"], reverse=True)[:3]
        for an in top_anoms:
            ax.annotate("spike", xy=(dt.datetime.strptime(an["date"], "%Y-%m-%d"), an["views"]),
                        fontsize=6, color=line.get_color(), ha="center", va="bottom")
        plotted = True
    ax.set_title("Monthly pageviews (raw)", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.3)
    _format_time_axis(ax)
    if plotted:
        ax.legend(fontsize=6, loc="best")
    else:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)


def _plot_indexed(ax, series_list):
    plotted = False
    for s in series_list:
        df = s.get("df")
        if df is None or df.empty:
            continue
        base = df["views"].iloc[0]
        if base <= 0:
            base = df["views"][df["views"] > 0].iloc[0] if (df["views"] > 0).any() else 1
        ax.plot(df["date"], df["views"] / base * 100.0, lw=1.4, label=s["lang"])
        plotted = True
    ax.axhline(100, color="gray", lw=0.8, ls="--", alpha=0.6)
    ax.set_title("Indexed to 100 at start (compare shape, not size)", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(True, alpha=0.3)
    _format_time_axis(ax)
    if plotted:
        ax.legend(fontsize=6, loc="best")
    else:
        ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)


def _table(ax, series_list, normalized=False):
    ax.axis("off")
    headers = ["lang", "article", "views/mo", "growth", "YoY", "trend", "confidence"]
    if normalized:
        headers.insert(3, "share/M")
    ncols = len(headers)
    rows = []
    for s in series_list:
        m = s.get("metrics", {})
        if not s.get("found"):
            row = [s["lang"], "(no article)"] + ["-"] * (ncols - 3) + ["gap"]
        elif not m.get("available"):
            row = [s["lang"], (s.get("title") or "")[:22]] + ["-"] * (ncols - 3) + ["no data"]
        else:
            g = m["growth_pct"]
            row = [
                s["lang"], (s.get("title") or "")[:22],
                f"{m['mean_views']:.0f}",
                "n/a" if g in (None, "inf") else f"{g:+.0f}%",
                "n/a" if m["yoy_pct"] is None else f"{m['yoy_pct']:+.0f}%",
                m["direction"],
                m["confidence"]["label"],
            ]
            if normalized:
                sm = m.get("share_per_million_mean")
                row.insert(3, "n/a" if sm is None else f"{sm:.1f}")
        rows.append(row)
    tbl = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1, 1.4)
    for j in range(len(headers)):
        tbl[0, j].set_facecolor("#2b6cb0")
        tbl[0, j].set_text_props(color="white", fontweight="bold")


def build_report(topic: str, period_label: str, series_list: list, out_pdf: str,
                 note: Optional[str] = None, normalized: bool = False) -> dict:
    """Render the one-pager. Returns {"pdf": path, "png": path}."""
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
    gs = GridSpec(5, 2, figure=fig, height_ratios=[0.6, 3.2, 1.7, 2.2, 1.4],
                  hspace=0.55, wspace=0.2, left=0.08, right=0.95, top=0.95, bottom=0.05)

    # title band
    axt = fig.add_subplot(gs[0, :]); axt.axis("off")
    axt.text(0, 0.7, f"Wikipedia interest: {topic}", fontsize=16, fontweight="bold")
    langs = ", ".join(s["lang"] for s in series_list)
    axt.text(0, 0.15, f"Editions: {langs}   |   Period: {period_label}   |   "
                      f"Generated: {dt.date.today().isoformat()}", fontsize=8, color="#444")

    _plot_raw(fig.add_subplot(gs[1, 0]), series_list)
    _plot_indexed(fig.add_subplot(gs[1, 1]), series_list)
    _table(fig.add_subplot(gs[2, :]), series_list, normalized=normalized)

    # findings
    axf = fig.add_subplot(gs[3, :]); axf.axis("off")
    axf.text(0, 1.0, "Findings", fontsize=11, fontweight="bold", va="top")
    axf.text(0, 0.85, build_findings(topic, series_list, note), fontsize=8, va="top", wrap=True)

    # footer / limitations
    axl = fig.add_subplot(gs[4, :]); axl.axis("off")
    axl.text(0, 1.0, LIMITATIONS, fontsize=7, color="#333", va="top", wrap=True)

    png = out_pdf.rsplit(".", 1)[0] + ".png"
    with PdfPages(out_pdf) as pdf:
        pdf.savefig(fig)
    fig.savefig(png, dpi=130)
    plt.close(fig)
    return {"pdf": out_pdf, "png": png}
