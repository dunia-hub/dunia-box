from datetime import date

import pytest

from app.dates import parse_spoken_date

FRIDAY = date(2026, 11, 20)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Ijumaa", date(2026, 11, 27)),
        ("ilipwe Ijumaa", date(2026, 11, 27)),
        ("Jumatatu", date(2026, 11, 23)),
        ("next Monday", date(2026, 11, 23)),
        ("kesho", date(2026, 11, 21)),
        ("kesho kutwa", date(2026, 11, 22)),
        ("wiki ijayo", date(2026, 11, 27)),
        ("baada ya siku 14", date(2026, 12, 4)),
        ("baada ya siku tano", date(2026, 11, 25)),
        ("in 10 days", date(2026, 11, 30)),
        ("tarehe 30", date(2026, 11, 30)),
        ("tarehe 5", date(2026, 12, 5)),
        ("5 Desemba", date(2026, 12, 5)),
        ("December 1st", date(2026, 12, 1)),
        ("2026-12-15", date(2026, 12, 15)),
        ("tarehe 10 Januari", date(2027, 1, 10)),
    ],
)
def test_parses_spoken_dates(text, expected):
    assert parse_spoken_date(text, FRIDAY) == expected


@pytest.mark.parametrize("text", ["sijui", "Wanjiku Traders", "", "tarehe 31 Novemba"])
def test_returns_none_when_no_date(text):
    assert parse_spoken_date(text, FRIDAY) is None
