"""Track F — the Series data type.

`series.py` replaced the pandas DataFrame, so every metric in the skill is computed over these
four methods. They are small enough to look obviously correct and important enough that a silent
regression (an off-by-one in `drop_last`, a date format change in `to_records`) would corrupt
every number the skill reports without raising anything.
"""
from __future__ import annotations

import datetime as dt

import pytest

from helpers import monthly, month_starts
from series import Series


def test_mismatched_lengths_are_rejected_at_construction():
    """Parallel lists are only safe if they can never drift apart."""
    with pytest.raises(ValueError, match="same length"):
        Series([dt.date(2022, 1, 1)], [10, 20])


def test_empty_series_is_empty_and_zero_length():
    s = Series()
    assert s.empty is True and len(s) == 0
    assert s.to_records() == [] and s.as_map() == {}


def test_sorted_by_date_reorders_views_with_their_dates():
    """The views must follow their own dates, not merely be sorted alongside them."""
    dates = [dt.date(2022, 3, 1), dt.date(2022, 1, 1), dt.date(2022, 2, 1)]
    s = Series(dates, [300, 100, 200]).sorted_by_date()
    assert s.dates == [dt.date(2022, 1, 1), dt.date(2022, 2, 1), dt.date(2022, 3, 1)]
    assert s.views == [100, 200, 300]


def test_sorted_by_date_does_not_mutate_the_original():
    original = Series([dt.date(2022, 2, 1), dt.date(2022, 1, 1)], [20, 10])
    original.sorted_by_date()
    assert original.dates == [dt.date(2022, 2, 1), dt.date(2022, 1, 1)]


def test_drop_last_removes_exactly_one_point_from_the_tail():
    """This is what trim_partial_tail uses to drop a half-finished month."""
    s = monthly([10, 20, 30]).drop_last()
    assert len(s) == 2 and s.views == [10, 20]
    assert s.dates == month_starts(2)


def test_drop_last_on_a_single_point_yields_an_empty_series():
    assert monthly([10]).drop_last().empty is True


def test_to_records_emits_iso_dates_paired_with_their_views():
    """The JSON shape `pageviews` prints; the date format is part of the CLI contract."""
    assert monthly([10, 20]).to_records() == [
        {"date": "2022-01-01", "views": 10},
        {"date": "2022-02-01", "views": 20},
    ]


def test_as_map_pairs_each_date_with_its_own_views():
    assert monthly([10, 20]).as_map() == {dt.date(2022, 1, 1): 10, dt.date(2022, 2, 1): 20}
