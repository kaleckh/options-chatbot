import json
import unittest
from pathlib import Path

from scripts import generate_final_remediation_closure_pack as closure_pack


ROOT = Path(__file__).resolve().parents[1]


class FinalRemediationClosurePackTests(unittest.TestCase):
    def setUp(self):
        self.closure = closure_pack.build_closure_pack()

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.closure["artifact"], "final_remediation_closure_pack")
        self.assertEqual(self.closure["closure_status"], "closed")
        self.assertFalse(self.closure["runtime_use"])
        self.assertEqual(self.closure["generated_by"], "scripts/generate_final_remediation_closure_pack.py")
        self.assertEqual(self.closure["validation"]["errors"], [])
        self.assertEqual(
            closure_pack.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            closure_pack.render_json(self.closure),
        )
        self.assertEqual(
            closure_pack.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            closure_pack.render_markdown(self.closure),
        )

    def test_loop_is_fully_closed(self):
        loop = self.closure["loop_closure"]
        self.assertEqual(loop["total_points"], 44)
        self.assertEqual(loop["completed_points"], 44)
        self.assertEqual(loop["planned_points"], 0)
        self.assertEqual(loop["in_progress_points"], 0)
        self.assertEqual(loop["completed_through_point"], 44)
        self.assertIsNone(loop["next_point"])
        self.assertEqual(loop["point_44_title"], "Final Goal Closure Verification Pack")
        self.assertFalse(loop["point_44_behavior_changed"])
        self.assertIn("docs/final-remediation-closure-pack.md", loop["point_44_owner_docs"])
        self.assertIn("scripts/generate_final_remediation_closure_pack.py", loop["point_44_owner_artifacts"])
        self.assertIn("data/contracts/final-remediation-closure-pack.json", loop["point_44_owner_artifacts"])
        self.assertIn("tests.test_final_remediation_closure_pack", loop["point_44_tests_or_checks"])
        self.assertEqual(loop["missing_owner_paths"], [])
        self.assertEqual(loop["missing_evidence"], [])

    def test_generated_artifact_governance_includes_closure_pack(self):
        generated = self.closure["generated_artifact_closure"]
        self.assertIn("docs/final-remediation-closure-pack.md", generated["closure_artifacts_governed"])
        self.assertIn("data/contracts/final-remediation-closure-pack.json", generated["closure_artifacts_governed"])
        self.assertEqual(generated["missing_closure_artifacts"], [])
        self.assertEqual(generated["runtime_generated_artifacts"], ["src/lib/generated/proofEvidenceContract.ts"])
        self.assertEqual(generated["uncovered_artifacts"], [])
        self.assertEqual(generated["hand_editable_artifacts"], [])

        governance = json.loads((ROOT / "data" / "contracts" / "generated-artifact-governance.json").read_text(encoding="utf-8"))
        governed_paths = {artifact["path"] for artifact in governance["governed_artifacts"]}
        self.assertIn("docs/final-remediation-closure-pack.md", governed_paths)
        self.assertIn("data/contracts/final-remediation-closure-pack.json", governed_paths)

    def test_guard_artifacts_and_scope_boundaries_are_clean(self):
        for artifact in self.closure["guard_artifact_closure"]:
            with self.subTest(path=artifact["path"]):
                self.assertFalse(artifact["runtime_use"])
                self.assertEqual(artifact["validation_error_count"], 0)

        scope = self.closure["active_scope_closure"]
        self.assertEqual(scope["mismatches"], [])
        self.assertEqual(scope["actual_status"]["regular_supervised_options_browser"], "active_browser_product")
        self.assertEqual(scope["actual_status"]["ai_commodity_proof_lane"], "separate_non_browser_proof_lane")
        self.assertEqual(scope["actual_status"]["day_trading"], "paused_out_of_scope")
        self.assertEqual(scope["actual_status"]["crypto_options_sidecar"], "paused_out_of_scope")
        self.assertEqual(scope["actual_status"]["polymarket_sidecar"], "paused_out_of_scope")

    def test_discoverability_and_package_wiring(self):
        discovery = self.closure["discoverability_closure"]
        self.assertEqual(discovery["missing_discovery_docs"], [])
        for node_id in [
            "final_remediation_closure_pack_doc",
            "final_remediation_closure_pack_json",
            "final_remediation_closure_pack_generator",
        ]:
            self.assertIn(node_id, discovery["memory_graph_nodes"])

        package = self.closure["package_closure"]
        self.assertTrue(package["owner_command_present"])
        self.assertTrue(package["verify_docs_covers_generator"])

        for relative_path in [
            "docs/index.md",
            "docs/living-docs-hygiene.md",
            "docs/architecture-overview.md",
            "docs/architecture-best-practices.md",
            "docs/remediation-loop-map.md",
            "docs/agent-memory-graph.md",
            "docs/generated-artifact-governance.md",
        ]:
            with self.subTest(path=relative_path):
                self.assertIn(
                    "docs/final-remediation-closure-pack.md",
                    (ROOT / relative_path).read_text(encoding="utf-8"),
                )

    def test_non_goals_keep_closure_non_runtime_and_non_product_claim(self):
        serialized = "\n".join(self.closure["non_goals"] + self.closure["risk_boundaries"])
        for phrase in [
            "route behavior",
            "auth semantics",
            "DB schema",
            "frontend behavior",
            "production profitability",
            "AI commodity proof completion",
            "paused sidecar lanes",
            "network freshness checks",
        ]:
            self.assertIn(phrase, serialized)


if __name__ == "__main__":
    unittest.main()
