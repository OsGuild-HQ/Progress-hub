"""ISO weeks and calendar months, the two reporting periods."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True, order=True)
class Week:
    """An ISO week, Monday to Sunday."""

    monday: date

    def __post_init__(self) -> None:
        if self.monday.weekday() != 0:
            raise ValueError(f"{self.monday} is not a Monday")

    @classmethod
    def containing(cls, day: date) -> Week:
        return cls(monday_of(day))

    @classmethod
    def parse(cls, text: str) -> Week:
        """Parse `2026-W48`."""
        match = _WEEK_RE.match(text.strip())
        if not match:
            raise ValueError(f"expected a week like 2026-W48, got {text!r}")
        year, number = int(match[1]), int(match[2])
        try:
            return cls(date.fromisocalendar(year, number, 1))
        except ValueError as exc:
            raise ValueError(f"{text!r} is not a real ISO week") from exc

    @property
    def sunday(self) -> date:
        return self.monday + timedelta(days=6)

    @property
    def label(self) -> str:
        year, number, _ = self.monday.isocalendar()
        return f"{year}-W{number:02d}"

    @property
    def month(self) -> str:
        """The month a week belongs to is the month of its Monday."""
        return month_label(self.monday)

    def previous(self, n: int = 1) -> Week:
        return Week(self.monday - timedelta(weeks=n))

    def human(self) -> str:
        start, end = self.monday, self.sunday
        if start.month == end.month:
            return f"{start:%b} {start.day} – {end.day}, {end.year}"
        if start.year == end.year:
            return f"{start:%b} {start.day} – {end:%b} {end.day}, {end.year}"
        return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"


def month_label(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def parse_month(text: str) -> tuple[date, date]:
    """`2026-11` -> (first day, last day)."""
    match = _MONTH_RE.match(text.strip())
    if not match:
        raise ValueError(f"expected a month like 2026-11, got {text!r}")
    year, month = int(match[1]), int(match[2])
    if not 1 <= month <= 12:
        raise ValueError(f"{text!r} is not a real month")
    first = date(year, month, 1)
    nxt = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, nxt - timedelta(days=1)


def previous_month(day: date) -> str:
    return month_label(day.replace(day=1) - timedelta(days=1))


def mondays_in_month(month: str) -> list[date]:
    first, last = parse_month(month)
    day = first + timedelta(days=(7 - first.weekday()) % 7)
    out: list[date] = []
    while day <= last:
        out.append(day)
        day += timedelta(weeks=1)
    return out
