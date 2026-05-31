from __future__ import annotations

from datetime import date
import unittest

from scripts.run_side_aware_zero_bid_replay import RawQuote, parse_occ, replay_trade


class FakeQuoteProvider:
    def __init__(self, quotes):
        self.quotes = quotes

    def quote(self, *, contract_symbol, quote_date, start_minute, end_minute, prefer_latest):
        return self.quotes.get((contract_symbol, quote_date.isoformat(), start_minute, end_minute))


def _quote(contract, quote_date, minute, bid, ask):
    return RawQuote(
        contract_symbol=contract,
        quote_date_et=quote_date,
        quote_minute_et=minute,
        bid=bid,
        ask=ask,
        source="test",
    )


class SideAwareZeroBidReplayTests(unittest.TestCase):
    def test_parse_occ_contract_parts(self):
        parts = parse_occ("WMT250926C00109000")

        self.assertEqual(parts.root, "WMT")
        self.assertEqual(parts.expiry, date(2025, 9, 26))
        self.assertEqual(parts.option_type, "call")
        self.assertEqual(parts.strike, 109.0)

    def test_conservative_mode_prices_zero_bid_short_buyback_as_loss(self):
        long_contract = "AAA260106C00100000"
        short_contract = "AAA260106C00110000"
        provider = FakeQuoteProvider(
            {
                (long_contract, "2026-01-02", 610, 625): _quote(long_contract, "2026-01-02", 610, 4.0, 5.0),
                (short_contract, "2026-01-02", 610, 625): _quote(short_contract, "2026-01-02", 610, 2.0, 2.5),
                (long_contract, "2026-01-05", 955, 955): _quote(long_contract, "2026-01-05", 955, 1.0, 2.0),
                (short_contract, "2026-01-05", 955, 955): _quote(short_contract, "2026-01-05", 955, 0.0, 1.2),
            }
        )

        result = replay_trade(
            {
                "ticker": "AAA",
                "date": "2026-01-02",
                "long_contract_symbol": long_contract,
                "short_contract_symbol": short_contract,
                "missing_quote_date": "2026-01-05",
            },
            quote_provider=provider,
            mode="conservative",
            stop_loss_pct=200.0,
            profit_target_pct=150.0,
            time_exit_pct=1.0,
            trailing_profit_pct=40.0,
            trailing_giveback_pct=50.0,
        )

        self.assertTrue(result["priced"])
        self.assertTrue(result["used_zero_bid_exit_quote"])
        self.assertEqual(result["entry_px"], 3.0)
        self.assertEqual(result["exit_px"], 0.0)
        self.assertEqual(result["net_pnl_pct"], -100.87)

    def test_midpoint_mode_can_price_same_zero_bid_quote_less_conservatively(self):
        long_contract = "AAA260106C00100000"
        short_contract = "AAA260106C00110000"
        provider = FakeQuoteProvider(
            {
                (long_contract, "2026-01-02", 610, 625): _quote(long_contract, "2026-01-02", 610, 4.0, 5.0),
                (short_contract, "2026-01-02", 610, 625): _quote(short_contract, "2026-01-02", 610, 2.0, 2.5),
                (long_contract, "2026-01-05", 955, 955): _quote(long_contract, "2026-01-05", 955, 1.0, 2.0),
                (short_contract, "2026-01-05", 955, 955): _quote(short_contract, "2026-01-05", 955, 0.0, 1.2),
            }
        )

        result = replay_trade(
            {
                "ticker": "AAA",
                "date": "2026-01-02",
                "long_contract_symbol": long_contract,
                "short_contract_symbol": short_contract,
                "missing_quote_date": "2026-01-05",
            },
            quote_provider=provider,
            mode="midpoint_zero_bid",
            stop_loss_pct=200.0,
            profit_target_pct=150.0,
            time_exit_pct=1.0,
            trailing_profit_pct=40.0,
            trailing_giveback_pct=50.0,
        )

        self.assertTrue(result["priced"])
        self.assertTrue(result["used_zero_bid_exit_quote"])
        self.assertEqual(result["entry_px"], 2.25)
        self.assertEqual(result["exit_px"], 0.9)
        self.assertEqual(result["net_pnl_pct"], -61.16)


if __name__ == "__main__":
    unittest.main()
