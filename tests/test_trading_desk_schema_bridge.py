import json
import unittest

from scripts import generate_trading_desk_schema_bridge as schema_bridge


class TradingDeskSchemaBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = schema_bridge.build_schema_bridge()
        self.routes = {
            route["route_id"]: route
            for route in self.bridge["route_contracts"]
        }

    def test_generated_artifacts_are_current(self):
        self.assertEqual(
            schema_bridge.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            schema_bridge.render_json(self.bridge),
        )
        self.assertEqual(
            schema_bridge.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            schema_bridge.render_markdown(self.bridge),
        )

    def test_bridge_covers_only_trading_desk_contract_slice(self):
        self.assertEqual(
            set(self.routes),
            {
                "tracked_positions_read",
                "tracked_positions_create",
                "tracked_positions_review",
                "tracked_positions_close",
                "suggested_trades_read",
                "suggested_trades_create",
                "suggested_trades_review",
                "suggested_trades_close",
            },
        )
        for route in self.routes.values():
            self.assertEqual(route["family"], "trading_desk")
            self.assertFalse(route["runtime_use"])
            self.assertNotIn("/api/scan", route["route"])
            self.assertNotIn("/api/backtest", route["route"])
            self.assertNotIn("/api/tools", route["route"])

    def test_mutation_routes_have_pydantic_refs_and_read_routes_stay_typescript_only(self):
        mutation_routes = [
            route
            for route in self.routes.values()
            if route["method"] != "GET"
        ]
        self.assertEqual(len(mutation_routes), 6)
        for route in mutation_routes:
            self.assertEqual(route["schema_status"], "pydantic_adapter_schema")
            self.assertRegex(route["pydantic"]["request_schema_ref"], r"^#/\$defs/")
            self.assertRegex(route["pydantic"]["response_envelope_schema_ref"], r"^#/\$defs/")

        for route_id in ("tracked_positions_read", "suggested_trades_read"):
            self.assertEqual(self.routes[route_id]["schema_status"], "typescript_contract_only")
            self.assertIsNone(self.routes[route_id]["pydantic"])

    def test_request_adapter_schemas_remain_intentionally_loose(self):
        defs = self.bridge["json_schema"]["$defs"]
        create_schema = defs["CreateTradingDeskRecordBody"]
        review_schema = defs["ReviewTradingDeskRecordsBody"]
        close_schema = defs["CloseTradingDeskRecordBody"]

        for schema in (create_schema, review_schema, close_schema):
            self.assertTrue(schema["additionalProperties"])

        self.assertNotIn("type", create_schema["properties"]["fill_price"])
        self.assertNotIn("type", create_schema["properties"]["contracts"])
        self.assertNotIn("type", review_schema["properties"]["position_ids"])
        self.assertNotIn("type", close_schema["properties"]["exit_price"])

    def test_tracked_and_suggested_response_envelopes_stay_split(self):
        defs = self.bridge["json_schema"]["$defs"]
        self.assertIn("position_event_persistence", defs["TrackedPositionEnvelope"]["properties"])
        self.assertIn("position_event_persistence", defs["TrackedPositionsEnvelope"]["properties"])
        self.assertNotIn("position_event_persistence", defs["SuggestedTradeEnvelope"]["properties"])
        self.assertNotIn("position_event_persistence", defs["SuggestedTradesEnvelope"]["properties"])

    def test_bridge_declares_runtime_and_scope_non_goals(self):
        serialized = json.dumps(self.bridge, sort_keys=True)
        self.assertFalse(self.bridge["runtime_use"])
        self.assertIn("No OpenAPI generation", serialized)
        self.assertIn("No runtime JSON Schema", serialized)
        self.assertIn("No generated TypeScript replacement", serialized)
        self.assertNotIn("proof_class", serialized)
        self.assertNotIn("source_scan_session_id", serialized)


if __name__ == "__main__":
    unittest.main()
