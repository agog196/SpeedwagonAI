from __future__ import annotations

import re
from datetime import date


def parse_date_phrase(value: str) -> str | None:
    text = value.strip().lower().rstrip(".,!?")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if text == "today":
        return date.today().isoformat()
    if text == "tomorrow":
        return date.fromordinal(date.today().toordinal() + 1).isoformat()
    match = re.fullmatch(
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?",
        text,
    )
    if not match:
        return None
    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    month = months[match.group(1)]
    day = int(match.group(2))
    year = int(match.group(3) or date.today().year)
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    return parsed.isoformat()
