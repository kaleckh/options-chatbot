from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


AD_HOC_FULL_MARKET_CLOSURES = frozenset(
    {
        # National Day of Mourning for President Jimmy Carter.
        date(2025, 1, 9),
    }
)


def observed_fixed_market_holiday(year: int, month: int, day: int) -> date:
    actual = date(year, month, day)
    if actual.weekday() == 5:
        return actual - timedelta(days=1)
    if actual.weekday() == 6:
        return actual + timedelta(days=1)
    return actual


def nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (nth - 1))


def last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    current = date(year, month, 31) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def western_easter_date(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=None)
def us_equity_market_holidays(year: int) -> frozenset[date]:
    holidays = {
        observed_fixed_market_holiday(year, 1, 1),
        nth_weekday_of_month(year, 1, 0, 3),
        nth_weekday_of_month(year, 2, 0, 3),
        western_easter_date(year) - timedelta(days=2),
        last_weekday_of_month(year, 5, 0),
        observed_fixed_market_holiday(year, 7, 4),
        nth_weekday_of_month(year, 9, 0, 1),
        nth_weekday_of_month(year, 11, 3, 4),
        observed_fixed_market_holiday(year, 12, 25),
    }
    if year >= 2022:
        holidays.add(observed_fixed_market_holiday(year, 6, 19))
    holidays.update(item for item in AD_HOC_FULL_MARKET_CLOSURES if item.year == year)
    return frozenset(holidays)


def is_us_equity_market_day(value: date) -> bool:
    if value.weekday() >= 5:
        return False
    holidays = (
        set(us_equity_market_holidays(value.year - 1))
        | set(us_equity_market_holidays(value.year))
        | set(us_equity_market_holidays(value.year + 1))
    )
    return value not in holidays


def previous_market_day(value: date) -> date:
    candidate = value - timedelta(days=1)
    while not is_us_equity_market_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def next_market_day(value: date) -> date:
    candidate = value
    while not is_us_equity_market_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def add_market_days(start: date, count: int) -> date:
    if count <= 0:
        return start
    current = start
    added = 0
    while added < count:
        current += timedelta(days=1)
        if is_us_equity_market_day(current):
            added += 1
    return current


def market_dates_between(start_exclusive: date | None, end_exclusive: date) -> list[str]:
    if start_exclusive is None:
        return []
    dates: list[str] = []
    current = start_exclusive + timedelta(days=1)
    while current < end_exclusive:
        if is_us_equity_market_day(current):
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates
