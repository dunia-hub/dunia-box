import re
from datetime import date, timedelta

WEEKDAYS = {
    "jumatatu": 0, "jumanne": 1, "jumatano": 2, "alhamisi": 3,
    "ijumaa": 4, "jumamosi": 5, "jumapili": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

MONTHS = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2,
    "machi": 3, "march": 3, "mar": 3,
    "aprili": 4, "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "julai": 7, "july": 7, "jul": 7,
    "agosti": 8, "august": 8, "aug": 8,
    "septemba": 9, "september": 9, "sept": 9, "sep": 9,
    "oktoba": 10, "october": 10, "oct": 10,
    "novemba": 11, "november": 11, "nov": 11,
    "desemba": 12, "december": 12, "dec": 12,
}

NUMBER_WORDS = {
    "moja": 1, "mbili": 2, "tatu": 3, "nne": 4, "tano": 5,
    "sita": 6, "saba": 7, "nane": 8, "tisa": 9, "kumi": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_spoken_date(text: str, today: date) -> date | None:
    t = text.lower()

    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    if "kesho kutwa" in t or "day after tomorrow" in t:
        return today + timedelta(days=2)
    if re.search(r"\b(kesho|tomorrow)\b", t):
        return today + timedelta(days=1)
    if re.search(r"\b(leo|today)\b", t):
        return today
    if "wiki ijayo" in t or "next week" in t:
        return today + timedelta(days=7)

    m = re.search(r"\bbaada ya siku\s+(\w+)\b", t) or re.search(r"\bin\s+(\w+)\s+days?\b", t)
    if m:
        n = _number(m.group(1))
        if n is not None:
            return today + timedelta(days=n)

    for name, idx in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", t):
            delta = (idx - today.weekday()) % 7 or 7  # never today
            return today + timedelta(days=delta)

    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        day = int(m.group(1))
        month = next((num for name, num in MONTHS.items() if re.search(rf"\b{name}\b", t)), None)
        if month:
            year = today.year if (month, day) >= (today.month, today.day) else today.year + 1
            return _safe_date(year, month, day)
        if day > today.day:
            return _safe_date(today.year, today.month, day)
        nxt_month = today.month % 12 + 1
        nxt_year = today.year + (1 if today.month == 12 else 0)
        return _safe_date(nxt_year, nxt_month, day)

    return None
