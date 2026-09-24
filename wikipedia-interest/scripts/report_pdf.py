"""Optional PDF renderer: a one-page A4 PDF (+ PNG) from analyzed series, via matplotlib.

This is the ONLY part of the skill that needs a third-party package, and it is imported lazily —
`report --format html` (the default) never touches it. Install with the `pdf` extra.

Layout (A4 portrait): title -> raw line chart + indexed-to-100 chart -> per-language metrics table
-> findings -> fixed assumptions/limitations footer. DejaVu Sans (matplotlib default) renders
Cyrillic and PL/CZ diacritics.

The narrative in `findings` is written by the model; `trust_block()` from reporting.py is appended
mechanically so a caveat cannot be lost when the file travels on its own.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from reporting import LIMITATIONS, findings_text

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

def _plot_raw(ax, series_list):
    plotted = False
    for s in series_list:
        data = s.get("data")
        if data is None or data.empty:
            continue
        (line,) = ax.plot(data.dates, data.views, marker="o", ms=2.5, lw=1.4, label=f"{s['lang']}: {s['title']}")
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
        data = s.get("data")
        if data is None or data.empty:
            continue
        base = data.views[0]
        if base <= 0:
            positive = [v for v in data.views if v > 0]
            base = positive[0] if positive else 1
        ax.plot(data.dates, [v / base * 100.0 for v in data.views], lw=1.4, label=s["lang"])
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
                 findings: Optional[str] = None, normalized: bool = False) -> dict:
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
    axf.text(0, 0.85, findings_text(series_list, findings), fontsize=8, va="top", wrap=True)

    # footer / limitations
    axl = fig.add_subplot(gs[4, :]); axl.axis("off")
    axl.text(0, 1.0, LIMITATIONS, fontsize=7, color="#333", va="top", wrap=True)

    png = out_pdf.rsplit(".", 1)[0] + ".png"
    with PdfPages(out_pdf) as pdf:
        pdf.savefig(fig)
    fig.savefig(png, dpi=130)
    plt.close(fig)
    return {"pdf": out_pdf, "png": png}
