from __future__ import annotations

import unittest
from datetime import date

from historical_options_store import HistoricalQuote
from scripts import migrate_main_lane_backfills_to_positions as migration


class _FakeStore:
    def __init__(self):
        self.quotes = {
            "SPY260619C00500000": HistoricalQuote(
                as_of_utc="2026-06-20T19:45:00Z",
                quote_date_et="2026-06-20",
                quote_minute_et=1545,
                underlying="SPY",
                contract_symbol="SPY260619C00500000",
                expiry="2026-06-19",
                option_type="call",
                strike=500.0,
                price=5.0,
                price_basis="mid",
                underlying_price=505.0,
                bid=4.8,
                ask=5.2,
                last=None,
                iv=None,
                volume=None,
                open_interest=None,
                snapshot_kind="intraday",
            ),
            "SPY260619C00520000": HistoricalQuote(
                as_of_utc="2026-06-20T19:45:00Z",
                quote_date_et="2026-06-20",
                quote_minute_et=1545,
                underlying="SPY",
                contract_symbol="SPY260619C00520000",
                expiry="2026-06-19",
                option_type="call",
                strike=520.0,
                price=2.0,
                price_basis="mid",
                underlying_price=505.0,
                bid=1.8,
                ask=2.2,
                last=None,
                iv=None,
                volume=None,
                open_interest=None,
                snapshot_kind="intraday",
            ),
        }

    def get_closing_quote(self, *, contract_symbol, **_kwargs):
        return self.quotes.get(contract_symbol)


class MigrateMainLaneBackfillsToPositionsTests(unittest.TestCase):
    def test_spread_exit_snapshot_accepts_contract_symbol_aliases(self):
        result = migration._spread_exit_snapshot(
            {
                "contractSymbol": "SPY260619C00500000",
                "shortContractSymbol": "SPY260619C00520000",
            },
            close_date=date(2026, 6, 20),
            store=_FakeStore(),
            source_labels=["thetadata_opra_nbbo_1m"],
            requested_pricing_lane="bid_ask",
            trusted_only=True,
        )

        self.assertTrue(result["priced"])
        self.assertEqual(result["long_quote"]["contract_symbol"], "SPY260619C00500000")
        self.assertEqual(result["short_quote"]["contract_symbol"], "SPY260619C00520000")


if __name__ == "__main__":
    unittest.main()
