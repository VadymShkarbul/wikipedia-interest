"""Track C — report / output quality.

reporting.build_findings is a pure text function: the best offline proxy for the quality of the
narrated answer. We assert it draws the right conclusions (recommendation, gaps, caveats). Then a
structural check on build_report: a real single-page PDF + PNG (replacing the old '>1KB exists').
"""
from __future__ import annotations

import pytest
from pypdf import PdfReader

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


def test_findings_recommends_strongest_rising_higher_volume():
    rising_big = _series_entry("pl", "X", list(range(500, 500 + 24 * 40, 40)))    # rising, high volume
    rising_small = _series_entry("cs", "Y", list(range(50, 50 + 24 * 4, 4)))      # rising, low volume
    text = reporting.build_findings("topic", [rising_big, rising_small], note=None)
    assert "Recommendation:" in text
    assert "pl" in text.split("Recommendation:")[1].split("\n")[0]  # pl named as the pick


def test_findings_says_deprioritize_when_none_rising():
    flat = _series_entry("uk", "A", [500] * 24)
    declining = _series_entry("pl", "B", list(range(1000, 1000 - 24 * 30, -30)))
    text = reporting.build_findings("topic", [flat, declining], note=None)
    assert "no edition shows clear rising interest" in text


def test_findings_flags_coverage_gap():
    ok = _series_entry("uk", "A", list(range(300, 300 + 24 * 10, 10)))
    gap = _series_entry("xx", None, [], found=False)
    text = reporting.build_findings("topic", [ok, gap], note=None)
    assert "coverage gap" in text
    assert "xx" in text


def test_findings_reports_attention_share_when_normalized():
    a = _series_entry("en", "A", list(range(1000, 1000 + 24 * 5, 5)), share=40.0)
    b = _series_entry("uk", "B", list(range(200, 200 + 24 * 5, 5)), share=137.0)  # smaller edition, bigger share
    text = reporting.build_findings("topic", [a, b], note=None)
    assert "Attention share" in text
    assert "uk" in text.split("Attention share")[1].split("\n")[0]  # uk wins the size-adjusted share


def test_findings_note_overrides_generated_text():
    ok = _series_entry("uk", "A", [500] * 24)
    text = reporting.build_findings("topic", [ok], note="Custom analyst narrative.")
    assert text == "Custom analyst narrative."


def test_findings_empty_when_no_usable_data():
    gap = _series_entry("xx", None, [], found=False)
    text = reporting.build_findings("topic", [gap], note=None)
    assert "coverage gap" in text  # the gap line still appears; never a crash


def test_build_report_writes_single_page_pdf_and_png(tmp_path):
    entries = [
        _series_entry("uk", "Астрономія", list(range(300, 300 + 24 * 10, 10))),
        _series_entry("pl", "Astronomia", list(range(500, 500 + 24 * 8, 8))),
    ]
    out_pdf = tmp_path / "report.pdf"
    files = reporting.build_report("astronomy", "last 2y", entries, str(out_pdf))

    pdf_path = files["pdf"]
    png_path = files["png"]
    assert out_pdf.exists() and out_pdf.stat().st_size > 5000
    assert png_path.endswith(".png")
    from pathlib import Path
    assert Path(png_path).exists() and Path(png_path).stat().st_size > 5000

    reader = PdfReader(str(out_pdf))
    assert len(reader.pages) == 1  # the deliverable is genuinely one page


def test_build_report_handles_gap_only_without_crashing(tmp_path):
    entries = [_series_entry("xx", None, [], found=False)]
    out_pdf = tmp_path / "gap.pdf"
    files = reporting.build_report("nothing", "last 2y", entries, str(out_pdf))
    assert out_pdf.exists()
    reader = PdfReader(files["pdf"])
    assert len(reader.pages) == 1
