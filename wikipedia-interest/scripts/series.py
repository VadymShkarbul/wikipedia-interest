"""The one data structure the pipeline passes around: a pageview time series.

A series is at most a few hundred (date, views) pairs — 24-36 for the default monthly window.
Two parallel lists are the right size of tool for that; this replaces `DataFrame(date, views)`,
which cost 48 MB of pandas to hold a 24-row table.

Pure data. No I/O, no third-party imports.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Series:
    """Dates and their view counts, kept in ascending date order by convention.

    `views` doubles as the totals column for whole-edition aggregate series — the arithmetic is
    identical, so there is no reason for a second type.
    """

    dates: list[dt.date] = field(default_factory=list)
    views: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.dates) != len(self.views):
            raise ValueError("dates and views must have the same length")

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def empty(self) -> bool:
        return not self.dates

    def sorted_by_date(self) -> "Series":
        pairs = sorted(zip(self.dates, self.views), key=lambda p: p[0])
        return Series([d for d, _ in pairs], [v for _, v in pairs])

    def drop_last(self) -> "Series":
        return Series(self.dates[:-1], self.views[:-1])

    def as_map(self) -> dict[dt.date, int]:
        """{date: views} — used to align two series on their common periods."""
        return dict(zip(self.dates, self.views))

    def to_records(self) -> list[dict]:
        """JSON-friendly [{date, views}] for the raw-series output."""
        return [{"date": d.strftime("%Y-%m-%d"), "views": v}
                for d, v in zip(self.dates, self.views)]
