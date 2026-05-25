from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from crypto_options import execution


def _signal():
    return SimpleNamespace(
        symbol="ETHUSDT",
        direction="call",
        direction_score=72.0,
        tech_score=81.0,
        signal_strength=0.74,
        regime="trend",
        htf_trend="up",
        price=3200.0,
        rsi=58.0,
        rationale="fixture",
    )


def _spread():
    return SimpleNamespace(
        long_leg=SimpleNamespace(instrument="ETH-TEST-LONG", ask=0.12),
        short_leg=SimpleNamespace(instrument="ETH-TEST-SHORT", bid=0.04),
        net_debit_base=0.08,
        net_debit_usd=80.0,
        spread_width=200.0,
        risk_reward=2.5,
        expiry="2026-06-26",
        dte=7,
    )


class _Client:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def place_order(self, instrument, side, amount, price=None, order_type="limit"):
        self.calls.append((instrument, side, amount, price, order_type))
        if self.fail:
            raise RuntimeError("order rejected")
        return {"order_id": f"{instrument}-{side}"}


class CryptoOptionsExecutionTests(unittest.TestCase):
    def test_live_orders_use_amount_and_price_before_recording_position(self):
        client = _Client()
        saved_positions = []
        with patch.dict(os.environ, {"CRYPTO_OPTIONS_ORDER_AMOUNT": "2"}, clear=False), \
             patch.object(execution, "_load_positions", return_value=[]), \
             patch.object(execution, "_save_positions", side_effect=lambda positions: saved_positions.extend(positions)), \
             patch.object(execution, "_log_pick"), \
             patch.object(execution, "scan_crypto_signals", return_value=[_signal()]), \
             patch.object(execution, "find_best_spread", return_value=_spread()):
            result = execution.run_scan_cycle(client=client, paper_trade=False, max_positions=1)

        self.assertEqual(
            client.calls,
            [
                ("ETH-TEST-LONG", "buy", 2.0, 0.12, "limit"),
                ("ETH-TEST-SHORT", "sell", 2.0, 0.04, "limit"),
            ],
        )
        self.assertEqual(result["open_positions"], 1)
        self.assertEqual(len(saved_positions), 1)
        self.assertEqual(saved_positions[0]["status"], "open")

    def test_failed_live_order_does_not_record_open_position(self):
        client = _Client(fail=True)
        saved_batches = []
        with patch.object(execution, "_load_positions", return_value=[]), \
             patch.object(execution, "_save_positions", side_effect=lambda positions: saved_batches.append(list(positions))), \
             patch.object(execution, "_log_pick") as log_pick, \
             patch.object(execution, "scan_crypto_signals", return_value=[_signal()]), \
             patch.object(execution, "find_best_spread", return_value=_spread()):
            result = execution.run_scan_cycle(client=client, paper_trade=False, max_positions=1)

        self.assertEqual(result["open_positions"], 0)
        self.assertEqual(saved_batches, [[]])
        logged = log_pick.call_args.args[0]
        self.assertEqual(logged["order_status"], "failed")
        self.assertIn("order rejected", logged["order_error"])


if __name__ == "__main__":
    unittest.main()
