from __future__ import annotations

import unittest
from pathlib import Path

import supervised_scan as ss
from scripts import generate_ai_commodity_isolation as isolation


ROOT = Path(__file__).resolve().parents[1]


class AICommodityIsolationTests(unittest.TestCase):
    def setUp(self):
        self.contract = isolation.build_contract()

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.contract["artifact"], "ai_commodity_isolation")
        self.assertEqual(self.contract["version"], 1)
        self.assertIs(self.contract["runtime_use"], False)
        self.assertEqual(self.contract["validation"]["errors"], [])
        self.assertEqual(
            isolation.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            isolation.render_json(self.contract),
        )
        self.assertEqual(
            isolation.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            isolation.render_markdown(self.contract),
        )

    def test_scanner_boundary_matches_runtime_metadata(self):
        runtime = self.contract["scanner_boundary"]["runtime"]

        self.assertEqual(runtime["playbook_id"], isolation.PLAYBOOK_ID)
        self.assertEqual(runtime["proof_scope"], ss.COMMODITY_PROOF_SCOPE)
        self.assertEqual(runtime["proof_scope"], isolation.PROOF_SCOPE)
        self.assertEqual(runtime["position_tracking_mode"], ss.POSITION_TRACKING_DISABLED)
        self.assertIs(runtime["auto_track_allowed"], False)
        self.assertIs(runtime["fresh_live_validation_enabled"], False)
        self.assertEqual(runtime["creation_blocker_when_visible"], "position_tracking_mode:disabled")
        self.assertFalse(ss.scan_playbook_allows_auto_track(isolation.PLAYBOOK_ID))

    def test_browser_api_tool_and_route_surfaces_are_not_mounted(self):
        browser = self.contract["browser_api_boundary"]

        self.assertFalse(browser["dedicated_browser_routes_allowed"])
        self.assertEqual(browser["route_inventory_findings"], [])
        self.assertEqual(browser["active_browser_import_findings"], [])
        self.assertEqual(browser["navigation_route_lifecycle_findings"], [])
        self.assertEqual(browser["tool_dispatch_findings"], [])

    def test_storage_and_legacy_boundaries_remain_separate(self):
        storage = self.contract["storage_boundary"]
        legacy = self.contract["legacy_lane_boundary"]

        self.assertEqual(storage["store_id"], "ai_commodity_artifacts")
        self.assertEqual(storage["scope"], "separate_lane")
        self.assertEqual(storage["storage_role"], "separate_lane")
        self.assertEqual(storage["persistence"], "file_artifact")
        self.assertEqual(storage["route_contract_ids"], [])
        self.assertEqual(storage["route_references"], {"active_browser": [], "backend_only": []})

        self.assertEqual(legacy["status"], "separate_non_browser_proof_lane")
        self.assertEqual(legacy["route_ui_status"], "not_mounted_browser_product")
        self.assertEqual(legacy["detail_owner"], "docs/ai-commodity-isolation.md")

    def test_latest_progress_readback_preserves_proof_source_honesty(self):
        latest = self.contract["latest_progress_readback"]
        proof_source = latest["proof_source_isolation"]

        self.assertTrue(latest["available"])
        self.assertEqual(latest["proof_source_label"], isolation.PROOF_SOURCE_LABEL)
        self.assertEqual(
            proof_source["exact_profitability_proof_source_labels"],
            [isolation.PROOF_SOURCE_LABEL],
        )
        self.assertEqual(proof_source["blockers"], [])
        if latest["verification_status"] != "verified_profitable":
            self.assertIsNot(latest["verified"], True)

    def test_living_docs_link_isolation_owner(self):
        for path in (
            "docs/index.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/architecture-overview.md",
            "docs/architecture-audit.md",
            "docs/scanner-creation-safety-contract.md",
        ):
            with self.subTest(path=path):
                self.assertIn(
                    "ai-commodity-isolation.md",
                    (ROOT / path).read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
