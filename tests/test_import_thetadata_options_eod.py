import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_thetadata_options_eod import (  # noqa: E402
    _business_dates,
    _iter_option_eod_rows,
    _occ_contract_symbol,
    _stock_close_by_date,
)


class ImportThetaDataOptionsEodTests(unittest.TestCase):
    def test_occ_contract_symbol_uses_repo_contract_format(self):
        self.assertEqual(
            _occ_contract_symbol("fcx", date(2026, 6, 19), "c", 55000),
            "FCX260619C00055000",
        )

    def test_business_dates_skips_weekends(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 15), date(2026, 5, 18)),
            [date(2026, 5, 15), date(2026, 5, 18)],
        )

    def test_stock_close_by_date_reads_theta_stock_eod_payload(self):
        payload = {
            "header": {
                "format": [
                    "ms_of_day",
                    "ms_of_day2",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "count",
                    "bid_size",
                    "bid_exchange",
                    "bid",
                    "bid_condition",
                    "ask_size",
                    "ask_exchange",
                    "ask",
                    "ask_condition",
                    "date",
                ]
            },
            "response": [[62113929, 62060084, 62.02, 63.805, 61.38, 63.01, 15455429, 176706, 900, 7, 63, 0, 100, 7, 63.18, 0, 20260515]],
        }

        self.assertEqual(_stock_close_by_date(payload), {date(2026, 5, 15): 63.01})

    def test_iter_option_eod_rows_filters_dte_and_normalizes_rows(self):
        payload = {
            "header": {
                "format": [
                    "ms_of_day",
                    "ms_of_day2",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "count",
                    "bid_size",
                    "bid_exchange",
                    "bid",
                    "bid_condition",
                    "ask_size",
                    "ask_exchange",
                    "ask",
                    "ask_condition",
                    "date",
                ]
            },
            "response": [
                {
                    "contract": {"root": "FCX", "expiration": 20260619, "strike": 55000, "right": "C"},
                    "ticks": [[62113929, 62060084, 1.1, 1.4, 1.0, 1.25, 91, 220, 20, 7, 1.2, 0, 40, 7, 1.3, 0, 20260515]],
                },
                {
                    "contract": {"root": "FCX", "expiration": 20261218, "strike": 55000, "right": "P"},
                    "ticks": [[62113929, 62060084, 2.1, 2.4, 2.0, 2.25, 12, 44, 10, 7, 2.2, 0, 20, 7, 2.3, 0, 20260515]],
                },
            ],
        }

        rows = list(
            _iter_option_eod_rows(
                symbol="FCX",
                payload=payload,
                min_dte=5,
                max_dte=60,
                underlying_prices={date(2026, 5, 15): 63.01},
            )
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(rows[0]["option_type"], "call")
        self.assertEqual(rows[0]["strike"], "55")
        self.assertEqual(rows[0]["bid"], "1.2")
        self.assertEqual(rows[0]["ask"], "1.3")
        self.assertEqual(rows[0]["last"], "1.25")
        self.assertEqual(rows[0]["volume"], "91")
        self.assertEqual(rows[0]["underlying_price"], "63.01")
        self.assertEqual(rows[0]["expiry"], "2026-06-19")


if __name__ == "__main__":
    unittest.main()
