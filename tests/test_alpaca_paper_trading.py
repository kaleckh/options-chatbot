from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import alpaca_paper_trading as apt  # noqa: E402


ENV_NAMES = [
    "OPTIONS_ALPACA_PAPER_TRADING_ENABLED",
    "ALPACA_PAPER_TRADING_ENABLED",
    "APCA_API_KEY_ID",
    "ALPACA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "ALPACA_API_SECRET_KEY",
    "ALPACA_TRADING_ENDPOINT",
    "APCA_API_BASE_URL",
    "ALPACA_PAPER_TRADING_ALLOW_CUSTOM_BASE_URL",
    "ALPACA_PAPER_ORDER_LEDGER_PATH",
]


def base_payload(**overrides):
    payload = {
        "ticker": "MSFT",
        "direction": "call",
        "expiry": "2026-06-19",
        "strike": 500,
        "short_strike": 510,
        "contract_symbol": "MSFT260619C00500000",
        "contracts": 1,
        "entry_option_price": 4.1,
        "entry_execution_price": 4.1,
        "entry_execution_basis": "live_scan_exact_contract_quote",
        "proof_eligible": True,
        "proof_class": "live_scan_exact_contract",
        "source_scan_run_id": "scan-run-1",
        "source_scan_event_key": "event-1",
        "source_pick_snapshot": {
            "source_scan_run_id": "scan-run-1",
            "source_scan_event_key": "event-1",
            "strategy_type": "vertical_spread",
            "contract_symbol": "MSFT260619C00500000",
            "short_contract_symbol": "MSFT260619C00510000",
        },
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class AlpacaPaperTradingTests(unittest.TestCase):
    def test_build_vertical_spread_order_payload_is_one_contract_mleg(self):
        order = apt.build_alpaca_order_payload(base_payload())

        self.assertEqual(order["order_class"], "mleg")
        self.assertEqual(order["qty"], "1")
        self.assertEqual(order["type"], "limit")
        self.assertEqual(order["limit_price"], "4.1")
        self.assertEqual(order["time_in_force"], "day")
        self.assertNotIn("notional", order)
        self.assertNotIn("extended_hours", order)
        self.assertEqual(order["legs"][0]["symbol"], "MSFT260619C00500000")
        self.assertEqual(order["legs"][0]["side"], "buy")
        self.assertEqual(order["legs"][0]["position_intent"], "buy_to_open")
        self.assertEqual(order["legs"][1]["symbol"], "MSFT260619C00510000")
        self.assertEqual(order["legs"][1]["side"], "sell")
        self.assertEqual(order["legs"][1]["position_intent"], "sell_to_open")

    def test_rejects_non_proof_payload(self):
        with self.assertRaises(apt.AlpacaPaperTradingError):
            apt.build_alpaca_order_payload(base_payload(proof_eligible=False))

    def test_submit_fails_closed_when_disabled(self):
        calls = []

        def fake_post(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeResponse(200, {"id": "ord-1", "status": "accepted"})

        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.jsonl"
            with patch.dict(os.environ, {name: "" for name in ENV_NAMES}, clear=False):
                with self.assertRaises(apt.AlpacaPaperTradingError) as ctx:
                    apt.submit_alpaca_paper_order(base_payload(), post=fake_post, ledger_path=ledger)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(calls, [])

    def test_submit_requires_credentials(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.jsonl"
            with patch.dict(
                os.environ,
                {
                    **{name: "" for name in ENV_NAMES},
                    "OPTIONS_ALPACA_PAPER_TRADING_ENABLED": "1",
                },
                clear=False,
            ):
                with self.assertRaises(apt.AlpacaPaperTradingError) as ctx:
                    apt.submit_alpaca_paper_order(base_payload(), ledger_path=ledger)

        self.assertEqual(ctx.exception.status_code, 400)

    def test_submit_records_submit_and_fill_events_and_applies_fill(self):
        calls = []

        def fake_post(url, *, headers, json, timeout):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse(
                200,
                {
                    "id": "ord-1",
                    "status": "filled",
                    "client_order_id": json["client_order_id"],
                    "order_class": "mleg",
                    "type": "limit",
                    "qty": "1",
                    "limit_price": "4.1",
                    "filled_qty": "1",
                    "filled_avg_price": "4.05",
                    "submitted_at": "2026-06-05T14:00:00Z",
                    "filled_at": "2026-06-05T14:01:00Z",
                },
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            ledger = Path(tmp_dir) / "ledger.jsonl"
            with patch.dict(
                os.environ,
                {
                    **{name: "" for name in ENV_NAMES},
                    "OPTIONS_ALPACA_PAPER_TRADING_ENABLED": "1",
                    "APCA_API_KEY_ID": "key",
                    "APCA_API_SECRET_KEY": "secret",
                    "ALPACA_TRADING_ENDPOINT": "https://paper-api.alpaca.markets/v2",
                },
                clear=False,
            ):
                result = apt.submit_alpaca_paper_order(base_payload(), post=fake_post, ledger_path=ledger)
                applied = apt.apply_alpaca_order_result_to_position_payload(base_payload(), result)

            events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(calls[0]["url"], "https://paper-api.alpaca.markets/v2/orders")
        self.assertEqual(calls[0]["headers"]["APCA-API-KEY-ID"], "key")
        self.assertEqual([event["event_type"] for event in events], ["submitted", "filled"])
        self.assertEqual(applied["entry_execution_price"], 4.05)
        self.assertEqual(applied["entry_execution_basis"], "alpaca_paper_fill")
        self.assertEqual(applied["filled_at"], "2026-06-05T14:01:00Z")
        order = applied["source_pick_snapshot"]["alpaca_paper_order"]
        self.assertEqual(order["provider"], "alpaca")
        self.assertEqual(order["environment"], "paper")
        self.assertEqual(order["order_id"], "ord-1")
        self.assertEqual(order["event_ledger_path"], str(ledger))


if __name__ == "__main__":
    unittest.main()
