#!/usr/bin/env python3
"""Arabic weekday and Hijri date strings for the Noctalia widgets."""
from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from hijridate import Gregorian
except ImportError:  # older installations
    try:
        from hijri_converter import Gregorian  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency error path
        raise ImportError(
            "The Python package 'hijridate' is required. "
            "Install it with: python3 -m pip install --user hijridate"
        ) from exc


# Elongated weekdays with tatweel (ـ), matching the existing GNOME widget.
ARABIC_WEEKDAYS: dict[int, str] = {
    0: "الإثـــــنـــــيـــــن",
    1: "الـــــثـــــلاثـــــاء",
    2: "الأربـــــعـــــاء",
    3: "الـــــخـــــمـــــيـــــس",
    4: "الـــــجـــــمـــــعـــــة",
    5: "الـــــســـــبـــــت",
    6: "الأحــــــــــد",
}

# Elongated Hijri months with tatweel (ـ).
HIJRI_MONTHS: dict[int, str] = {
    1: "مــــحـــــرّم",
    2: "صـــــفـــــر",
    3: "ربـــــــيـــــع الأولــــــــــ",
    4: "ربـــــــيـــــع الآخـــــــر",
    5: "جــــمــــادى الأولــــى",
    6: "جــــمــــادى الآخــــرة",
    7: "رجــــــــــب",
    8: "شــــعــــبــــان",
    9: "رمـــــضـــــان",
    10: "شـــــــــــوال",
    11: "ذو الــــقــــعــــدة",
    12: "ذو الــــحــــجــــة",
}

EASTERN_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_eastern_arabic(value: Any) -> str:
    return str(value).translate(EASTERN_DIGITS)


def get_current_strings(
    now: datetime | None = None,
    *,
    eastern_numerals: bool = True,
) -> dict[str, Any]:
    """Return weekday and Hijri strings for ``now`` (local time by default)."""
    now = now or datetime.now()
    hijri = Gregorian(now.year, now.month, now.day).to_hijri()
    day = to_eastern_arabic(hijri.day) if eastern_numerals else str(hijri.day)
    weekday = ARABIC_WEEKDAYS[now.weekday()]
    month = HIJRI_MONTHS[hijri.month]
    return {
        "weekday": weekday,
        "date": f"{day} {month}",
        "date_iso": now.date().isoformat(),
        "gregorian_year": now.year,
        "gregorian_month": now.month,
        "gregorian_day": now.day,
        "hijri_year": hijri.year,
        "hijri_month": hijri.month,
        "hijri_day": hijri.day,
        "weekday_index": now.weekday(),
    }
