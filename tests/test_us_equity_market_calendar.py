from __future__ import annotations

import unittest
from datetime import date, time

from us_equity_market_calendar import (
    EARLY_CLOSE_SESSION_CLOSES_ET,
    add_market_days,
    is_us_equity_early_close,
    is_us_equity_market_day,
    market_dates_between,
    next_market_day,
    previous_market_day,
    us_equity_market_close_time_et,
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

    def test_ad_hoc_full_market_closures_are_not_trading_days(self):
        holidays_2025 = us_equity_market_holidays(2025)

        self.assertIn(date(2025, 1, 9), holidays_2025)
        self.assertFalse(is_us_equity_market_day(date(2025, 1, 9)))
        self.assertEqual(previous_market_day(date(2025, 1, 10)), date(2025, 1, 8))

    def test_2018_bush_funeral_closure_is_not_a_trading_day(self):
        holidays_2018 = us_equity_market_holidays(2018)

        self.assertIn(date(2018, 12, 5), holidays_2018)
        self.assertFalse(is_us_equity_market_day(date(2018, 12, 5)))

    def test_saturday_new_year_does_not_close_prior_friday(self):
        holidays_2021 = us_equity_market_holidays(2021)

        self.assertNotIn(date(2021, 12, 31), holidays_2021)
        self.assertTrue(is_us_equity_market_day(date(2021, 12, 31)))

    def test_market_day_navigation_skips_weekends_and_holidays(self):
        self.assertEqual(previous_market_day(date(2026, 5, 26)), date(2026, 5, 22))
        self.assertEqual(next_market_day(date(2026, 5, 23)), date(2026, 5, 26))
        self.assertEqual(add_market_days(date(2026, 5, 22), 1), date(2026, 5, 26))
        self.assertEqual(
            market_dates_between(date(2026, 5, 22), date(2026, 5, 28)),
            ["2026-05-26", "2026-05-27"],
        )

    def test_frozen_2018_2021_early_close_set_is_exact(self):
        expected = {
            date(2018, 7, 3),
            date(2018, 11, 23),
            date(2018, 12, 24),
            date(2019, 7, 3),
            date(2019, 11, 29),
            date(2019, 12, 24),
            date(2020, 11, 27),
            date(2020, 12, 24),
            date(2021, 11, 26),
        }

        self.assertEqual(set(EARLY_CLOSE_SESSION_CLOSES_ET), expected)
        for session_date in expected:
            with self.subTest(session_date=session_date):
                self.assertTrue(is_us_equity_market_day(session_date))
                self.assertTrue(is_us_equity_early_close(session_date))
                self.assertEqual(us_equity_market_close_time_et(session_date), time(13, 0))

    def test_market_close_distinguishes_normal_early_and_closed_sessions(self):
        self.assertEqual(us_equity_market_close_time_et(date(2021, 11, 24)), time(16, 0))
        self.assertEqual(us_equity_market_close_time_et(date(2021, 11, 26)), time(13, 0))
        self.assertIsNone(us_equity_market_close_time_et(date(2018, 12, 5)))
        self.assertIsNone(us_equity_market_close_time_et(date(2020, 7, 3)))
        self.assertIsNone(us_equity_market_close_time_et(date(2021, 12, 24)))
        self.assertIsNone(us_equity_market_close_time_et(date(2021, 11, 27)))


if __name__ == "__main__":
    unittest.main()
