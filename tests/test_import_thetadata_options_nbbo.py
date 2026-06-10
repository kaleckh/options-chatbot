import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    _business_dates,
    _normalize_theta_quote_row,
    _occ_contract_symbol,
    _parse_theta_expiration,
    build_thetadata_nbbo_import,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.closed = False

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(self.payload)

    def close(self):
        self.closed = True


class ImportThetaDataOptionsNbboTests(unittest.TestCase):
    def test_occ_contract_symbol_uses_repo_contract_format(self):
        self.assertEqual(
            _occ_contract_symbol("fcx", date(2026, 6, 19), "call", 55.0),
            "FCX260619C00055000",
        )

    def test_business_dates_skips_weekends(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 15), date(2026, 5, 18)),
            [date(2026, 5, 15), date(2026, 5, 18)],
        )

    def test_business_dates_skips_exchange_holidays(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 22), date(2026, 5, 26)),
            [date(2026, 5, 22), date(2026, 5, 26)],
        )

    def test_business_dates_skips_ad_hoc_full_market_closures(self):
        self.assertEqual(
            _business_dates(date(2025, 1, 8), date(2025, 1, 10)),
            [date(2025, 1, 8), date(2025, 1, 10)],
        )

    def test_parse_theta_expiration_accepts_iso_or_theta_format(self):
        self.assertEqual(_parse_theta_expiration("20260618"), "20260618")
        self.assertEqual(_parse_theta_expiration("2026-06-18"), "20260618")
        self.assertIsNone(_parse_theta_expiration(None))

    def test_normalize_theta_quote_row_preserves_bid_ask_and_timestamp(self):
        row = _normalize_theta_quote_row(
            {
                "symbol": "FCX",
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 1.2,
                "ask": 1.35,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(row["option_type"], "call")
        self.assertEqual(row["strike"], "55")
        self.assertEqual(row["bid"], "1.2")
        self.assertEqual(row["ask"], "1.35")
        self.assertEqual(row["as_of_utc"], "2026-05-15T19:55:00Z")

    def test_normalize_theta_quote_row_rejects_non_executable_quotes(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "put",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 1.4,
                "ask": 1.1,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNone(row)

    def test_normalize_theta_quote_row_accepts_zero_bid_positive_ask_quote(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 0.0,
                "ask": 0.05,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(row["bid"], "0")
        self.assertEqual(row["ask"], "0.05")

    def test_normalize_theta_quote_row_rejects_zero_ask_quote(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 0.0,
                "ask": 0.0,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNone(row)

    def test_build_thetadata_nbbo_import_fetches_and_filters_rows(self):
        session = _FakeSession(
            [
                {
                    "symbol": "FCX",
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "call",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 1.2,
                    "ask": 1.35,
                },
                {
                    "symbol": "FCX",
                    "expiration": "2026-12-18",
                    "strike": 55.0,
                    "right": "put",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 2.2,
                    "ask": 2.35,
                },
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            session=session,
        )

        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["generated_rows"], 1)
        self.assertEqual(payload["rows_by_symbol"], {"FCX": 1})
        self.assertEqual(payload["skipped_rows"], {"outside_dte_window": 1})
        self.assertEqual(payload["rows"][0]["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(session.calls[0]["params"]["expiration"], "*")
        self.assertEqual(session.calls[0]["params"]["interval"], "1m")
        self.assertEqual(session.calls[0]["params"]["start_time"], "15:55:00")

    def test_build_thetadata_nbbo_import_uses_exact_expiration_when_provided(self):
        session = _FakeSession(
            [
                {
                    "symbol": "FCX",
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "call",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 1.2,
                    "ask": 1.35,
                }
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            expiration="20260619",
            session=session,
        )

        self.assertEqual(payload["expiration"], "20260619")
        self.assertEqual(session.calls[0]["params"]["expiration"], "20260619")
        self.assertEqual(payload["generated_rows"], 1)


if __name__ == "__main__":
    unittest.main()
