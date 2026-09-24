"""Track C — report / output quality.

Two things matter in the artifact the user forwards to a colleague:

  * the TRUST GUARANTEE — the model writes the narrative, so the code must append the confidence
    label and its leading reason itself. A report that travels without its caveat is the failure
    mode this whole skill exists to prevent.
  * the ARTIFACT — a real self-contained HTML one-pager that renders non-Latin titles correctly.

The optional matplotlib PDF renderer is checked separately, and skipped when it isn't installed.
"""
from __future__ import annotations

import pytest

import analysis
import reporting
from conftest import monthly


def _series_entry(lang, title, views, found=True, share=None):
    """Build one series entry shaped like wikipop._build_series output (incl. the live data)."""
    if not found:
        return {"lang": lang, "title": None, "found": False, "metrics": {"available": False}}
    data = monthly(views)
    metrics = analysis.analyze_series(data, share=share)
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
    """direction_basis says which number backs the verdict; the report must not quote the other."""
    entry = _series_entry("uk", "A", list(range(300, 300 + 24 * 10, 10)))
    assert entry["metrics"]["direction_basis"] == "yoy"
    assert "year-over-year" in reporting.trust_block([entry])[0]


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


def test_build_report_handles_gap_only_without_crashing(tmp_path):
    out = tmp_path / "gap.html"
    reporting.build_report("nothing", "last 2y", [_series_entry("xx", None, [], found=False)], str(out))
    text = out.read_text(encoding="utf-8")
    assert "no data" in text and "coverage gap" in text


# --- the optional PDF renderer ----------------------------------------------

def test_pdf_renderer_still_produces_one_page(tmp_path):
    pytest.importorskip("matplotlib", reason="PDF output is an optional extra")
    from pypdf import PdfReader
    import report_pdf

    entries = [_series_entry("uk", "Астрономія", list(range(300, 300 + 24 * 10, 10)))]
    out = tmp_path / "report.pdf"
    files = report_pdf.build_report("astronomy", "last 2y", entries, str(out),
                                    findings="Model-written narrative.")
    assert out.exists() and out.stat().st_size > 5000
    assert PdfReader(str(out)).pages.__len__() == 1
    from pathlib import Path
    assert Path(files["png"]).exists()
