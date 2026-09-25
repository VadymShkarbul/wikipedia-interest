"""Track C — report / output quality.

Two things matter in the artifact the user forwards to a colleague:

  * the TRUST GUARANTEE — the model writes the narrative, so the code must append the confidence
    label and its leading reason itself. A report that travels without its caveat is the failure
    mode this whole skill exists to prevent.
  * the ARTIFACT — a real self-contained HTML one-pager that renders non-Latin titles correctly.
    It is the only output format: a browser's Print → Save as PDF makes the shareable PDF, so the
    skill ships no renderer and no dependency for it.
"""
from __future__ import annotations

import pytest

import analysis
import reporting
from helpers import monthly


def _series_entry(lang, title, views, found=True, share=None, **overrides):
    """Build one series entry shaped like wikipop._build_series output (incl. the live data).

    `overrides` patches the computed metrics, so a test can reach a branch that real 24-month
    synthetic data never lands on (growth basis, an `inf` growth, an article with no data).
    """
    if not found:
        return {"lang": lang, "title": None, "found": False, "metrics": {"available": False}}
    data = monthly(views)
    metrics = analysis.analyze_series(data, share=share)
    metrics.update(overrides)
    return {"lang": lang, "title": title, "found": True, "data": data, "metrics": metrics}


# --- the trust guarantee -----------------------------------------------------

def test_trust_block_states_confidence_for_every_edition():
    entries = [
        _series_entry("uk", "A", list(range(300, 300 + 24 * 10, 10))),
        _series_entry("pl", "B", [20] * 24),  # very low traffic -> low confidence
    ]
    lines = reporting.trust_block(entries)
    assert len(lines) == 2
    assert all("confidence" in ln for ln in lines)
    assert "low" in [ln for ln in lines if ln.startswith("pl")][0]


def test_trust_block_carries_the_leading_reason():
    """The caveat, not just the label — a bare 'low' tells the reader nothing actionable."""
    lines = reporting.trust_block([_series_entry("pl", "B", [20] * 24)])
    assert "Very low traffic" in lines[0]


def test_trust_block_quotes_the_number_the_basis_names():
    """direction_basis says which number backs the verdict; the report must not quote the other.

    Both halves are asserted. `growth_pct` compares different calendar months, so on a seasonal
    topic it invents a trend — quoting it under a yoy verdict is the specific error this prevents.
    """
    entry = _series_entry("uk", "A", list(range(300, 300 + 24 * 10, 10)))
    assert entry["metrics"]["direction_basis"] == "yoy"
    yoy_line = reporting.trust_block([entry])[0]
    assert "year-over-year" in yoy_line
    assert "over the period" not in yoy_line

    short = _series_entry("uk", "A", [100, 140, 190, 260, 350, 470],
                          direction_basis="growth", growth_pct=61.2)
    growth_line = reporting.trust_block([short])[0]
    assert "+61% over the period" in growth_line
    assert "year-over-year" not in growth_line


@pytest.mark.parametrize("growth_pct,expected", [
    ("inf", "from a near-zero baseline"),
    (None, "change unclear"),
])
def test_trust_block_describes_an_unquotable_growth_in_words(growth_pct, expected):
    """A percentage off a zero base is meaningless and `None` is not a number.

    The report must say so in words rather than print `inf%` or `None%` at a reader.
    """
    entry = _series_entry("uk", "A", [0] * 6, direction_basis="growth", growth_pct=growth_pct)
    line = reporting.trust_block([entry])[0]
    assert expected in line
    assert "inf" not in line.replace("confidence", "") and "None" not in line


def test_trust_block_distinguishes_an_empty_article_from_a_missing_one():
    """'article exists but has no pageviews here' is a different finding from 'no article'."""
    present_but_empty = {"lang": "cs", "title": "Astronomie", "found": True,
                         "metrics": {"available": False}}
    line = reporting.trust_block([present_but_empty])[0]
    assert "article exists but no pageview data in range" in line
    assert "Astronomie" in line
    assert "coverage gap" not in line


def test_trust_block_flags_coverage_gap():
    lines = reporting.trust_block([_series_entry("xx", None, [], found=False)])
    assert "coverage gap" in lines[0] and "xx" in lines[0]


def test_trust_lines_are_appended_even_when_the_model_says_nothing(tmp_path):
    out = tmp_path / "r.html"
    reporting.build_report("t", "last 2y", [_series_entry("pl", "B", [20] * 24)],
                           str(out), findings=None)
    assert "Very low traffic" in out.read_text(encoding="utf-8")


def test_model_narrative_cannot_suppress_the_caveat(tmp_path):
    """A rosy narrative must not displace the computed caveat."""
    out = tmp_path / "r.html"
    reporting.build_report("t", "last 2y", [_series_entry("pl", "B", [20] * 24)],
                           str(out), findings="Huge opportunity, ship immediately.")
    text = out.read_text(encoding="utf-8")
    assert "Huge opportunity, ship immediately." in text
    assert "Very low traffic" in text


# --- the artifact ------------------------------------------------------------

def test_build_report_writes_self_contained_html(tmp_path):
    entries = [
        _series_entry("uk", "Астрономія", list(range(300, 300 + 24 * 10, 10))),
        _series_entry("pl", "Astronomia", list(range(500, 500 + 24 * 8, 8))),
    ]
    out = tmp_path / "report.html"
    files = reporting.build_report("astronomy", "last 2y", entries, str(out))
    assert files["html"] == str(out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "<svg" in text and "<polyline" in text      # charts are really drawn
    assert "@page" in text                              # prints to one A4 page
    # self-contained: nothing fetched from the network
    assert "http://" not in text and "https://" not in text
    assert "<script" not in text


def test_html_renders_non_latin_titles_literally(tmp_path):
    """Cyrillic used to depend on matplotlib's bundled font; in HTML it must be plain text."""
    entries = [_series_entry("uk", "Астрономія", list(range(300, 300 + 24 * 10, 10)))]
    out = tmp_path / "cyr.html"
    reporting.build_report("астрономія", "last 2y", entries, str(out))
    text = out.read_text(encoding="utf-8")
    assert "Астрономія" in text
    assert "астрономія" in text


def test_html_escapes_markup_in_titles(tmp_path):
    entries = [_series_entry("xx", "<script>alert(1)</script>", list(range(300, 300 + 24 * 10, 10)))]
    out = tmp_path / "esc.html"
    reporting.build_report("t", "last 2y", entries, str(out))
    text = out.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_legend_names_every_edition(tmp_path):
    """The legend used to be laid out inside the SVG with a 6px-per-character width estimate.

    Past three editions it ran off the fixed viewBox, which SVG clips, so editions disappeared
    from the key while their lines stayed on the chart — worst in exactly the multi-edition
    comparison this skill exists for (examples.md ships a six-edition case).
    """
    titles = {"en": "English language", "pl": "Język angielski", "uk": "Англійська мова",
              "cs": "Angličtina", "de": "Englische Sprache", "es": "Idioma inglés"}
    entries = [_series_entry(lang, title, list(range(300, 300 + 24 * 10, 10)))
               for lang, title in titles.items()]
    out = tmp_path / "six.html"
    reporting.build_report("English language", "last 3y", entries, str(out))
    text = out.read_text(encoding="utf-8")

    legend = text.split('<ul class="legend">')[1].split("</ul>")[0]
    for lang, title in titles.items():
        assert f"{lang}: {title}" in legend, f"{lang} missing from the legend"
    # one swatch per edition, and the palette must not repeat inside a single chart
    assert legend.count('class="swatch"') == len(titles)
    colours = [seg.split('"')[0] for seg in legend.split("background:")[1:]]
    assert len(set(colours)) == len(titles), f"colours collide: {colours}"


def test_nothing_is_drawn_outside_the_viewbox(tmp_path):
    """Content positioned past the viewBox is silently clipped, not visibly broken.

    This is the guard the string assertions above cannot give: the old legend's text WAS present
    in the markup, just at x=844 in a 470-wide viewBox, so searching the HTML for an edition name
    found it while the reader saw nothing. Check geometry, not substrings.
    """
    import re

    titles = {"en": "English language", "pl": "Język angielski", "uk": "Англійська мова",
              "cs": "Angličtina", "de": "Englische Sprache", "es": "Idioma inglés"}
    entries = [_series_entry(lang, title, list(range(300, 300 + 24 * 10, 10)))
               for lang, title in titles.items()]
    out = tmp_path / "bounds.html"
    reporting.build_report("English language", "last 3y", entries, str(out))
    text = out.read_text(encoding="utf-8")

    for chart in text.split("<svg")[1:]:
        chart = chart.split("</svg>")[0]
        vb_w, vb_h = (float(v) for v in re.search(
            r'viewBox="0 0 ([\d.]+) ([\d.]+)"', chart).groups())
        for attr, limit in (("x", vb_w), ("x1", vb_w), ("x2", vb_w), ("cx", vb_w),
                            ("y", vb_h), ("y1", vb_h), ("y2", vb_h), ("cy", vb_h)):
            for raw in re.findall(rf'\b{attr}="(-?[\d.]+)"', chart):
                assert -1 <= float(raw) <= limit + 1, (
                    f"{attr}={raw} is outside the {vb_w}x{vb_h} viewBox and will be clipped")


def test_legend_colours_match_the_plotted_lines(tmp_path):
    """Chart and legend are rendered separately now, so their colour order must stay in step."""
    entries = [_series_entry("uk", "A", list(range(300, 300 + 24 * 10, 10))),
               _series_entry("xx", None, [], found=False),          # gap: drawn by neither
               _series_entry("pl", "B", list(range(500, 500 + 24 * 8, 8)))]
    out = tmp_path / "order.html"
    reporting.build_report("t", "last 2y", entries, str(out))
    text = out.read_text(encoding="utf-8")

    chart = text.split("<svg")[1].split("</svg>")[0]
    line_colours = [seg.split('"')[0] for seg in chart.split('stroke="')[1:] if seg.startswith("#")]
    legend = text.split('<ul class="legend">')[1].split("</ul>")[0]
    legend_colours = [seg.split('"')[0] for seg in legend.split("background:")[1:]]
    # the gap edition contributes to neither, and the two that do plot keep the same order
    assert legend_colours == reporting.PALETTE[:2]
    assert line_colours[:2] == legend_colours


def test_build_report_handles_gap_only_without_crashing(tmp_path):
    out = tmp_path / "gap.html"
    reporting.build_report("nothing", "last 2y", [_series_entry("xx", None, [], found=False)], str(out))
    text = out.read_text(encoding="utf-8")
    assert "no data" in text and "coverage gap" in text


# --- one-pageness (a proxy, deliberately) ------------------------------------

@pytest.mark.parametrize("n_editions", [2, 6])
def test_report_declares_a4_and_holds_exactly_one_page_container(tmp_path, n_editions):
    """A structural stand-in for the page-count check that left with the PDF renderer.

    v1 opened the PDF and asserted `len(PdfReader(...).pages) == 1`. The browser now makes the
    PDF, so nothing here can see the paginated result. This asserts only what the file itself
    can prove: the A4 page rule is declared and the document is a single `.page` block.

    It CANNOT prove the content fits on that page — overflow onto a second sheet would still
    pass. Proving that needs a renderer, which is exactly the dependency this branch declines to
    ship. Do not reword this test as if it guarantees one page.
    """
    entries = [_series_entry(f"l{i}", f"T{i}", list(range(300, 300 + 24 * 10, 10)))
               for i in range(n_editions)]
    out = tmp_path / "r.html"
    reporting.build_report("t", "last 2y", entries, str(out))
    text = out.read_text(encoding="utf-8")

    assert "@page { size: A4 portrait;" in text
    assert text.count('<div class="page">') == 1
