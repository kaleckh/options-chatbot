from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from trading_desk_api_models import (  # noqa: E402
    CloseTradingDeskRecordBody,
    CreateTradingDeskRecordBody,
    SuggestedTradeEnvelope,
    SuggestedTradesEnvelope,
    TrackedPositionEnvelope,
    TrackedPositionsEnvelope,
    parse_close_trading_desk_record_body,
    parse_create_trading_desk_record_body,
    parse_review_trading_desk_records_body,
    trading_desk_api_model_manifest,
)


class TradingDeskApiModelTests(unittest.TestCase):
    def test_model_manifest_covers_trading_desk_mutation_routes(self):
        manifest = trading_desk_api_model_manifest()
        route_ids = [entry["route_id"] for entry in manifest]

        self.assertEqual(len(route_ids), len(set(route_ids)))
        self.assertEqual(
            set(route_ids),
            {
                "tracked_positions_create",
                "tracked_positions_review",
                "tracked_positions_close",
                "suggested_trades_create",
                "suggested_trades_review",
                "suggested_trades_close",
            },
        )
        for entry in manifest:
            with self.subTest(route_id=entry["route_id"]):
                self.assertEqual(entry["method"], "POST")
                self.assertTrue(entry["request_model"])
                self.assertTrue(entry["response_envelope_model"])
                self.assertIn(entry["record_class"], {"tracked_position", "suggested_trade"})

    def test_create_body_preserves_raw_values_and_extra_fields(self):
        body = parse_create_trading_desk_record_body(
            {
                "scan_pick": {"ticker": "AAA"},
                "fill_price": True,
                "contracts": "2",
                "creation_mode": "manual_paper",
                "extra_debug": {"keep": True},
            }
        )

        self.assertIs(body["fill_price"], True)
        self.assertEqual(body["contracts"], "2")
        self.assertEqual(body["extra_debug"], {"keep": True})
        self.assertEqual(body["scan_pick"], {"ticker": "AAA"})

    def test_suggested_create_missing_contracts_stays_absent_for_route_default(self):
        body = parse_create_trading_desk_record_body(
            {
                "scan_pick": {"ticker": "AAA"},
                "fill_price": 4.1,
            }
        )

        self.assertNotIn("contracts", body)

    def test_create_body_rejects_non_object_scan_pick_as_value_error(self):
        with self.assertRaises(ValueError) as context:
            parse_create_trading_desk_record_body(
                {
                    "scan_pick": [1],
                    "fill_price": 4.1,
                    "contracts": 1,
                }
            )

        self.assertIn("scan_pick", str(context.exception))

    def test_review_body_preserves_invalid_position_ids_for_existing_parser(self):
        body = parse_review_trading_desk_records_body({"position_ids": [True, "abc", 3]})

        self.assertEqual(body["position_ids"], [True, "abc", 3])
        self.assertEqual(parse_review_trading_desk_records_body(None), {})

    def test_close_body_preserves_zero_exit_and_missing_exit(self):
        zero_exit = parse_close_trading_desk_record_body({"exit_price": 0, "notes": "worthless"})
        missing_exit = parse_close_trading_desk_record_body({"notes": "missing"})

        self.assertEqual(zero_exit["exit_price"], 0)
        self.assertNotIn("exit_price", missing_exit)

    def test_envelope_models_preserve_tracked_suggested_top_level_differences(self):
        TrackedPositionEnvelope(
            position={"id": 1},
            position_event_persistence={"status": "recorded"},
        )
        TrackedPositionsEnvelope(
            positions=[{"id": 1}],
            position_event_persistence={"status": "recorded"},
        )
        SuggestedTradeEnvelope(trade={"id": 1})
        SuggestedTradesEnvelope(trades=[{"id": 1}])

        with self.assertRaises(ValidationError):
            SuggestedTradeEnvelope(
                trade={"id": 1},
                position_event_persistence={"status": "recorded"},
            )
        with self.assertRaises(ValidationError):
            SuggestedTradesEnvelope(
                trades=[{"id": 1}],
                position_event_persistence={"status": "recorded"},
            )

    def test_docs_name_model_owner_and_deferred_boundaries(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "architecture": (ROOT / "docs" / "architecture-overview.md").read_text(encoding="utf-8"),
            "project": (ROOT / "docs" / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
            "models": (ROOT / "docs" / "trading-desk-api-models.md").read_text(encoding="utf-8"),
        }
        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("trading-desk-api-models.md", text)
                self.assertIn("trading_desk_api_models.py", text)

        model_doc = docs["models"]
        self.assertIn("do not use `response_model=`", model_doc)
        self.assertIn("automatic FastAPI `422` responses", model_doc)
        self.assertIn("Suggested-trade envelopes intentionally do not include `position_event_persistence`", model_doc)


if __name__ == "__main__":
    unittest.main()
