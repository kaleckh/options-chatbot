from __future__ import annotations

import unittest

from scripts import generate_project_pathway_registry as registry


class ProjectPathwayRegistryTests(unittest.TestCase):
    def test_registry_has_six_unique_pathways(self) -> None:
        report = registry.build_registry()
        pathways = report["pathways"]
        ids = [row["id"] for row in pathways]

        self.assertEqual(report["report_id"], "project_pathway_registry")
        self.assertFalse(report["runtime_use"])
        self.assertEqual(len(pathways), 6)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "data_path")
        self.assertEqual(ids[-1], "operator_path")

    def test_registry_outputs_are_current(self) -> None:
        report = registry.build_registry()

        self.assertEqual(
            registry.JSON_OUTPUT_PATH.read_text(encoding="utf8"),
            registry.render_json(report),
        )
        self.assertEqual(
            registry.MD_OUTPUT_PATH.read_text(encoding="utf8"),
            registry.render_markdown(report),
        )

    def test_pathways_name_existing_owners(self) -> None:
        report = registry.build_registry()
        missing: list[str] = []
        for pathway in report["pathways"]:
            for key in ("owner_docs", "owner_scripts"):
                for relative_path in pathway[key]:
                    if not (registry.ROOT / relative_path).exists():
                        missing.append(relative_path)

        self.assertEqual(missing, [])

    def test_registry_is_navigation_only(self) -> None:
        report = registry.build_registry()

        self.assertIn("create trades", report["non_goals"])
        self.assertIn("submit broker orders", report["non_goals"])
        self.assertIn("lower proof bars", report["non_goals"])
        self.assertIn("Data first.", report["visual_model"]["short_form"])


if __name__ == "__main__":
    unittest.main()
