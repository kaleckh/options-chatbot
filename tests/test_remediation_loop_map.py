import json
import unittest
from pathlib import Path

from scripts import generate_remediation_loop_map as loop_map


ROOT = Path(__file__).resolve().parents[1]


class RemediationLoopMapTests(unittest.TestCase):
    def setUp(self):
        self.contract = loop_map.build_contract()
        self.points = self.contract["points"]

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.contract["artifact"], "remediation_loop_map")
        self.assertFalse(self.contract["runtime_use"])
        self.assertEqual(self.contract["generated_by"], "scripts/generate_remediation_loop_map.py")
        self.assertEqual(
            loop_map.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            loop_map.render_json(self.contract),
        )
        self.assertEqual(
            loop_map.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            loop_map.render_markdown(self.contract),
        )

        payload = json.loads(loop_map.JSON_OUTPUT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["validation"]["errors"], [])

    def test_points_are_unique_consecutive_and_have_expected_status_split(self):
        numbers = [point["point"] for point in self.points]
        self.assertEqual(numbers, list(range(1, 45)))

        status_by_point = {point["point"]: point["status"] for point in self.points}
        for point_number in range(1, 45):
            self.assertEqual(status_by_point[point_number], "completed")

        self.assertIsNone(self.contract["current_state"]["next_point"])
        self.assertEqual(self.contract["current_state"]["planned_points"], [])
        self.assertEqual(self.contract["validation"]["status_split"]["completed"], 44)
        self.assertEqual(self.contract["validation"]["status_split"]["planned"], 0)
        self.assertEqual(self.contract["validation"]["status_split"]["in_progress"], 0)

    def test_completed_points_have_evidence_and_existing_owner_paths(self):
        worklog = (ROOT / "docs" / "WORKLOG.md").read_text(encoding="utf-8")

        for point in self.points[:44]:
            with self.subTest(point=point["point"]):
                self.assertTrue(point["owner_docs"])
                self.assertTrue(point["owner_artifacts"])
                self.assertTrue(point["tests_or_checks"])
                self.assertTrue(any(anchor in worklog for anchor in point["worklog_evidence"]))
                for relative_path in [*point["owner_docs"], *point["owner_artifacts"]]:
                    self.assertTrue((ROOT / relative_path).exists(), relative_path)

    def test_point_41_is_a_handoff_ledger_not_a_runtime_owner(self):
        point_41 = self.points[40]
        self.assertEqual(point_41["point"], 41)
        self.assertEqual(point_41["title"], "Generated Remediation Loop Map / LLM Handoff Ledger")
        self.assertFalse(point_41["behavior_changed"])
        self.assertIn("scripts/generate_remediation_loop_map.py", point_41["owner_artifacts"])
        self.assertIn("data/contracts/remediation-loop-map.json", point_41["owner_artifacts"])
        for forbidden_owner in [
            "route handler behavior",
            "auth semantics",
            "proof predicates",
            "scanner policy",
            "database schema or persistence behavior",
            "frontend runtime behavior",
        ]:
            self.assertIn(forbidden_owner, point_41["does_not_own"])

    def test_point_42_is_backend_map_not_runtime_route_behavior(self):
        point_42 = self.points[41]
        self.assertEqual(point_42["point"], 42)
        self.assertEqual(point_42["title"], "Backend Route Ownership Map")
        self.assertFalse(point_42["behavior_changed"])
        self.assertIn("scripts/generate_backend_route_ownership_map.py", point_42["owner_artifacts"])
        self.assertIn("data/contracts/backend-route-ownership-map.json", point_42["owner_artifacts"])
        self.assertIn("docs/backend-route-ownership-map.md", point_42["owner_docs"])
        for forbidden_owner in [
            "FastAPI route handler behavior",
            "decorators or route paths",
            "auth behavior",
            "request or response payloads",
            "database schema or repositories",
            "frontend behavior",
        ]:
            self.assertIn(forbidden_owner, point_42["does_not_own"])

    def test_point_43_is_generated_artifact_governance_not_runtime_policy(self):
        point_43 = self.points[42]
        self.assertEqual(point_43["point"], 43)
        self.assertEqual(point_43["title"], "Generated Artifact Governance And Stale-Artifact Trust Boundaries")
        self.assertFalse(point_43["behavior_changed"])
        self.assertIn("scripts/generated_artifact_manifest.py", point_43["owner_artifacts"])
        self.assertIn("scripts/generate_generated_artifact_governance.py", point_43["owner_artifacts"])
        self.assertIn("data/contracts/generated-artifact-governance.json", point_43["owner_artifacts"])
        self.assertIn("docs/generated-artifact-governance.md", point_43["owner_docs"])
        for forbidden_owner in [
            "route behavior",
            "auth semantics",
            "request or response payloads",
            "proof/scanner/replay semantics",
            "database schema",
            "volatile research or market-data report governance",
        ]:
            self.assertIn(forbidden_owner, point_43["does_not_own"])

    def test_point_44_is_final_closure_not_runtime_behavior(self):
        point_44 = self.points[43]
        self.assertEqual(point_44["point"], 44)
        self.assertEqual(point_44["title"], "Final Goal Closure Verification Pack")
        self.assertEqual(point_44["status"], "completed")
        self.assertFalse(point_44["behavior_changed"])
        self.assertIn("docs/final-remediation-closure-pack.md", point_44["owner_docs"])
        self.assertIn("scripts/generate_final_remediation_closure_pack.py", point_44["owner_artifacts"])
        self.assertIn("data/contracts/final-remediation-closure-pack.json", point_44["owner_artifacts"])
        self.assertIn("tests.test_final_remediation_closure_pack", point_44["tests_or_checks"])
        for forbidden_owner in [
            "route behavior",
            "auth semantics",
            "request or response payloads",
            "proof/scanner/replay semantics",
            "database schema",
            "frontend behavior",
            "product profitability or broker execution readiness",
            "AI commodity proof completion",
            "paused sidecar lane reopening",
        ]:
            self.assertIn(forbidden_owner, point_44["does_not_own"])

    def test_living_docs_and_memory_graph_discover_the_map(self):
        self.assertEqual(loop_map._validate_discovery_links(), [])
        graph_text = (ROOT / "docs" / "agent-memory-graph.md").read_text(encoding="utf-8")
        self.assertIn("docs/remediation-loop-map.md", graph_text)


if __name__ == "__main__":
    unittest.main()
