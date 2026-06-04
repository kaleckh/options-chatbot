import unittest
from pathlib import Path

from scripts import check_living_docs_hygiene as hygiene
from scripts import generate_generated_artifact_governance as governance
from scripts.generated_artifact_manifest import GENERATED_ARTIFACTS


ROOT = Path(__file__).resolve().parents[1]


class GeneratedArtifactGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.governance = governance.build_governance()
        self.artifacts = {
            artifact["path"]: artifact
            for artifact in self.governance["governed_artifacts"]
        }

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.governance["artifact"], "generated_artifact_governance")
        self.assertFalse(self.governance["runtime_use"])
        self.assertEqual(self.governance["generated_by"], "scripts/generate_generated_artifact_governance.py")
        self.assertEqual(self.governance["validation"]["errors"], [])
        self.assertEqual(
            governance.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            governance.render_json(self.governance),
        )
        self.assertEqual(
            governance.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            governance.render_markdown(self.governance),
        )

    def test_manifest_is_shared_with_living_docs_hygiene(self):
        manifest_paths = {artifact.path for artifact in GENERATED_ARTIFACTS}
        hygiene_paths = {artifact.path for artifact in hygiene.GENERATED_ARTIFACTS}
        self.assertEqual(set(self.artifacts), manifest_paths)
        self.assertEqual(hygiene_paths, manifest_paths)

    def test_artifacts_have_commands_generators_and_stale_boundaries(self):
        for manifest_entry in GENERATED_ARTIFACTS:
            with self.subTest(path=manifest_entry.path):
                artifact = self.artifacts[manifest_entry.path]
                self.assertTrue((ROOT / artifact["path"]).exists())
                self.assertTrue((ROOT / artifact["generator"]).exists())
                self.assertIn("Do not hand-edit", artifact["stale_action"])
                self.assertFalse(artifact["hand_edit_allowed"])
                self.assertTrue(artifact["verify_docs_covered"])
                self.assertTrue(artifact["source_inputs"])
                self.assertTrue(artifact["owner_docs"])

    def test_runtime_generated_exception_is_explicit_and_unique(self):
        runtime_artifacts = [
            artifact
            for artifact in self.artifacts.values()
            if artifact["runtime_use"]
        ]
        self.assertEqual([artifact["path"] for artifact in runtime_artifacts], ["src/lib/generated/proofEvidenceContract.ts"])
        proof_ts = runtime_artifacts[0]
        self.assertEqual(proof_ts["runtime_posture"], "generated_frontend_runtime_policy")
        self.assertEqual(proof_ts["trust_role"], "generated_runtime_bridge")
        self.assertIn("data/contracts/proof-evidence-contract.json", proof_ts["source_inputs"])

    def test_no_ungoverned_generated_markers_in_narrow_roots(self):
        marker_paths = governance._narrow_generated_marker_paths()
        self.assertLessEqual(marker_paths, set(self.artifacts))
        self.assertIn("docs/generated-artifact-governance.md", marker_paths)
        self.assertIn("data/contracts/generated-artifact-governance.json", marker_paths)
        self.assertIn("docs/final-remediation-closure-pack.md", marker_paths)
        self.assertIn("data/contracts/final-remediation-closure-pack.json", marker_paths)

    def test_closure_pack_artifacts_are_governed(self):
        for path in [
            "docs/final-remediation-closure-pack.md",
            "data/contracts/final-remediation-closure-pack.json",
        ]:
            with self.subTest(path=path):
                artifact = self.artifacts[path]
                self.assertEqual(artifact["generator"], "scripts/generate_final_remediation_closure_pack.py")
                self.assertEqual(artifact["owner_command"], "docs:final-remediation-closure-pack")
                self.assertFalse(artifact["runtime_use"])
                self.assertEqual(artifact["runtime_posture"], "non_runtime_metadata")
                self.assertIn("docs/final-remediation-closure-pack.md", artifact["owner_docs"])

    def test_docs_memory_graph_and_remediation_loop_discover_governance(self):
        for relative_path in [
            "docs/index.md",
            "docs/living-docs-hygiene.md",
            "docs/architecture-overview.md",
            "docs/architecture-best-practices.md",
            "docs/agent-memory-graph.md",
            "docs/remediation-loop-map.md",
        ]:
            with self.subTest(path=relative_path):
                self.assertIn(
                    "docs/generated-artifact-governance.md",
                    (ROOT / relative_path).read_text(encoding="utf-8"),
                )

        remediation = (ROOT / "data" / "contracts" / "remediation-loop-map.json").read_text(encoding="utf-8")
        self.assertIn('"completed_through_point": 44', remediation)
        self.assertIn('"next_point": null', remediation)


if __name__ == "__main__":
    unittest.main()
