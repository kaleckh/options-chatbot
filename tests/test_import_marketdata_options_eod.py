import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_marketdata_options_eod import (  # noqa: E402
    _business_dates,
    _date_from_marketdata_expiration,
    _iter_marketdata_rows,
)


class ImportMarketDataOptionsEodTests(unittest.TestCase):
    def test_business_dates_skips_weekends(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 15), date(2026, 5, 18)),
            [date(2026, 5, 15), date(2026, 5, 18)],
        )

    def test_date_from_marketdata_expiration_reads_epoch_seconds(self):
        self.assertEqual(
            _date_from_marketdata_expiration(1781812800),
            date(2026, 6, 18),
        )

    def test_iter_marketdata_rows_filters_dte_and_normalizes_rows(self):
        payload = {
            "optionSymbol": ["AAPL260618C00300000", "AAPL261218P00300000"],
            "underlying": ["AAPL", "AAPL"],
            "expiration": [1781812800, 1797627600],
            "side": ["call", "put"],
            "strike": [300, 300],
            "bid": [9.05, 12.0],
            "ask": [9.4, 12.5],
            "last": [9.3, 12.25],
            "iv": [0.3195, 0.42],
            "underlyingPrice": [300.23, 300.23],
            "volume": [29801, 10],
            "openInterest": [84599, 20],
        }

        rows = _iter_marketdata_rows(
            symbol="AAPL",
            trade_date=date(2026, 5, 15),
            payload=payload,
            min_dte=5,
            max_dte=60,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contract_symbol"], "AAPL260618C00300000")
        self.assertEqual(rows[0]["option_type"], "call")
        self.assertEqual(rows[0]["strike"], "300")
        self.assertEqual(rows[0]["bid"], "9.05")
        self.assertEqual(rows[0]["ask"], "9.4")
        self.assertEqual(rows[0]["last"], "9.3")
        self.assertEqual(rows[0]["iv"], "0.3195")
        self.assertEqual(rows[0]["underlying_price"], "300.23")
        self.assertEqual(rows[0]["volume"], "29801")
        self.assertEqual(rows[0]["open_interest"], "84599")
        self.assertEqual(rows[0]["expiry"], "2026-06-18")


if __name__ == "__main__":
    unittest.main()
