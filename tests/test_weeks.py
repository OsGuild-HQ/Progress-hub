from datetime import date

import pytest

from progress_bot.weeks import Week, mondays_in_month, parse_month, previous_month


def test_week_parse_and_label() -> None:
    week = Week.parse("2026-W48")
    assert week.monday == date(2026, 11, 23)
    assert week.sunday == date(2026, 11, 29)
    assert week.label == "2026-W48"
    assert week.month == "2026-11"
    assert week.previous().label == "2026-W47"


def test_week_containing_and_year_boundary() -> None:
    assert Week.containing(date(2026, 11, 26)).monday == date(2026, 11, 23)
    week = Week.parse("2026-W53")
    assert week.monday == date(2026, 12, 28)
    assert week.human() == "Dec 28, 2026 – Jan 3, 2027"


@pytest.mark.parametrize("text", ["2026-48", "2026-W60", "W48"])
def test_week_parse_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        Week.parse(text)


def test_week_must_be_monday() -> None:
    with pytest.raises(ValueError):
        Week(date(2026, 11, 24))


def test_months() -> None:
    assert parse_month("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert previous_month(date(2026, 1, 15)) == "2025-12"
    assert mondays_in_month("2026-11") == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
        date(2026, 11, 30),
    ]
    with pytest.raises(ValueError):
        parse_month("2026-13")
