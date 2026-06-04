from __future__ import annotations

import unittest
from pathlib import Path

from scripts import generate_legacy_lane_boundaries as boundaries


ROOT = Path(__file__).resolve().parents[1]


class LegacyLaneBoundariesTests(unittest.TestCase):
    def setUp(self):
        self.contract = boundaries.build_contract()
        self.lanes = {lane["lane_id"]: lane for lane in self.contract["lanes"]}

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.contract["artifact"], "legacy_lane_boundaries")
        self.assertEqual(self.contract["version"], 1)
        self.assertIs(self.contract["runtime_use"], False)
        self.assertEqual(self.contract["validation"]["errors"], [])
        self.assertEqual(
            boundaries.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            boundaries.render_json(self.contract),
        )
        self.assertEqual(
            boundaries.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            boundaries.render_markdown(self.contract),
        )

    def test_required_lane_statuses_and_reopen_rules_are_explicit(self):
        expected_statuses = {
            "regular_supervised_options_browser": "active_browser_product",
            "legacy_prediction_analytics": "active_browser_legacy_analytics",
            "ai_commodity_proof_lane": "separate_non_browser_proof_lane",
            "day_trading": "paused_out_of_scope",
            "crypto_options_sidecar": "paused_out_of_scope",
            "polymarket_sidecar": "paused_out_of_scope",
        }
        self.assertEqual(
            {lane_id: self.lanes[lane_id]["status"] for lane_id in expected_statuses},
            expected_statuses,
        )

        for lane_id in ("day_trading", "crypto_options_sidecar", "polymarket_sidecar"):
            with self.subTest(lane=lane_id):
                serialized = "\n".join(
                    [
                        *self.lanes[lane_id]["allowed_work"],
                        *self.lanes[lane_id]["forbidden_work"],
                        *self.lanes[lane_id]["hard_rules"],
                    ]
                )
                self.assertIn("explicit", serialized.lower())
                self.assertIn("user", serialized.lower())

        self.assertEqual(
            self.lanes["ai_commodity_proof_lane"]["detail_owner"],
            "docs/ai-commodity-isolation.md",
        )

    def test_referenced_paths_and_docs_exist(self):
        for lane in self.contract["lanes"]:
            for path in lane["path_roots"]:
                with self.subTest(lane=lane["lane_id"], path=path):
                    self.assertTrue((ROOT / path).exists(), path)
            for path in lane["owner_docs"]:
                with self.subTest(lane=lane["lane_id"], doc=path):
                    self.assertTrue((ROOT / path).exists(), path)

    def test_paused_lanes_are_not_mounted_browser_surfaces(self):
        self.assertEqual(boundaries._day_trading_route_handlers(), [])
        self.assertEqual(boundaries._active_browser_import_findings(), [])
        self.assertEqual(boundaries._route_inventory_findings(), [])

        navigation_source = (ROOT / "src" / "lib" / "navigation" / "tabs.ts").read_text(
            encoding="utf-8"
        )
        route_contract_source = (
            ROOT / "src" / "lib" / "route-lifecycle" / "routeContracts.ts"
        ).read_text(encoding="utf-8")
        for token in ("day-trading", "polymarket", "crypto"):
            with self.subTest(token=token):
                self.assertNotIn(token, navigation_source.lower())
                self.assertNotIn(token, route_contract_source.lower())

    def test_living_docs_link_boundary_owner(self):
        for path in (
            "docs/index.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-overview.md",
            "docs/architecture-audit.md",
        ):
            with self.subTest(path=path):
                self.assertIn(
                    "legacy-lane-boundaries.md",
                    (ROOT / path).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
