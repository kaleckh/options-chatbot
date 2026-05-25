from __future__ import annotations

import unittest
from datetime import date

from us_equity_market_calendar import (
    add_market_days,
    is_us_equity_market_day,
    market_dates_between,
    next_market_day,
    previous_market_day,
    us_equity_market_holidays,
)


class UsEquityMarketCalendarTests(unittest.TestCase):
    def test_holidays_include_2026_memorial_day_and_good_friday(self):
        holidays = us_equity_market_holidays(2026)

        self.assertIn(date(2026, 5, 25), holidays)
        self.assertIn(date(2026, 4, 3), holidays)
        self.assertFalse(is_us_equity_market_day(date(2026, 5, 25)))
        self.assertFalse(is_us_equity_market_day(date(2026, 4, 3)))
        self.assertTrue(is_us_equity_market_day(date(2026, 5, 26)))

    def test_observed_fixed_holidays_handle_weekends(self):
        holidays_2026 = us_equity_market_holidays(2026)
        holidays_2027 = us_equity_market_holidays(2027)

        self.assertIn(date(2026, 7, 3), holidays_2026)
        self.assertFalse(is_us_equity_market_day(date(2026, 7, 3)))
        self.assertIn(date(2027, 12, 24), holidays_2027)
        self.assertFalse(is_us_equity_market_day(date(2027, 12, 24)))

    def test_market_day_navigation_skips_weekends_and_holidays(self):
        self.assertEqual(previous_market_day(date(2026, 5, 26)), date(2026, 5, 22))
        self.assertEqual(next_market_day(date(2026, 5, 23)), date(2026, 5, 26))
        self.assertEqual(add_market_days(date(2026, 5, 22), 1), date(2026, 5, 26))
        self.assertEqual(
            market_dates_between(date(2026, 5, 22), date(2026, 5, 28)),
            ["2026-05-26", "2026-05-27"],
        )


if __name__ == "__main__":
    unittest.main()
