import json
import unittest
from pathlib import Path

from scripts import generate_backend_route_ownership_map as backend_map


ROOT = Path(__file__).resolve().parents[1]


class BackendRouteOwnershipMapTests(unittest.TestCase):
    def setUp(self):
        self.map = backend_map.build_backend_route_ownership_map()
        self.routes = {
            (route["method"], route["path"]): route
            for route in self.map["routes"]
        }

    def test_generated_artifacts_are_current_and_non_runtime(self):
        self.assertEqual(self.map["artifact"], "backend_route_ownership_map")
        self.assertFalse(self.map["runtime_use"])
        self.assertEqual(self.map["generated_by"], "scripts/generate_backend_route_ownership_map.py")
        self.assertEqual(self.map["validation"]["errors"], [])
        self.assertEqual(
            backend_map.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            backend_map.render_json(self.map),
        )
        self.assertEqual(
            backend_map.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            backend_map.render_markdown(self.map),
        )

    def test_static_route_discovery_matches_map_and_route_inventory(self):
        discovered_keys = {
            (route["method"], route["path"])
            for route in backend_map.discover_fastapi_routes()
        }
        self.assertEqual(set(self.routes), discovered_keys)

        mounted, backend_only, excluded_next_only = backend_map._inventory_maps(backend_map._load_route_inventory())
        self.assertEqual(set(self.routes), set(mounted) | set(backend_only))
        self.assertEqual(
            {(route["method"], route["browser_path"]) for route in excluded_next_only},
            {("GET", "/api/operator/session"), ("POST", "/api/operator/session")},
        )

    def test_representative_route_ownership_is_pinned(self):
        scan = self.routes[("POST", "/api/scan")]
        self.assertEqual(scan["adapter_owner_module"], "python-backend/main.py")
        self.assertEqual(scan["adapter_kind"], "main_inline_route_adapter")
        self.assertEqual(scan["route_family"], "scanner")
        self.assertIn("supervised_scan.py", scan["domain_owners"])

        tools = self.routes[("POST", "/api/tools/{tool_name}")]
        self.assertEqual(tools["adapter_owner_module"], "python-backend/tools_routes.py")
        self.assertEqual(tools["adapter_kind"], "extracted_router")
        self.assertEqual(tools["dependency_style"], "BackendRouteContext")

        profile = self.routes[("GET", "/api/profile")]
        self.assertEqual(profile["adapter_owner_module"], "python-backend/profile_routes.py")
        self.assertEqual(profile["dependency_style"], "explicit_dependency_injection")

        proof_summary = self.routes[("GET", "/api/proof-summary")]
        self.assertIn("python-backend/proof_summary_service.py", proof_summary["delegate_modules"])

        replay_summary = self.routes[("GET", "/api/backtest/summary")]
        self.assertIn("python-backend/replay_profit_service.py", replay_summary["delegate_modules"])

        delete_prediction = self.routes[("DELETE", "/api/predictions/{pred_id}")]
        self.assertEqual(delete_prediction["surface"], "backend_only")
        self.assertEqual(delete_prediction["adapter_owner_module"], "python-backend/predictions_routes.py")

    def test_modules_and_owner_paths_are_existing_and_bounded(self):
        modules = {module["path"]: module for module in self.map["modules"]}
        self.assertEqual(modules["python-backend/proof_summary_service.py"]["route_count"], 0)
        self.assertEqual(modules["python-backend/replay_profit_service.py"]["route_count"], 0)
        self.assertFalse(modules["python-backend/predictions_routes.py"]["imports_main"])
        self.assertFalse(modules["python-backend/tools_routes.py"]["imports_main"])

        for module in self.map["modules"]:
            self.assertTrue((ROOT / module["path"]).exists(), module["path"])
            for owner_doc in module["owner_docs"]:
                self.assertTrue((ROOT / owner_doc).exists(), owner_doc)

        for route in self.map["routes"]:
            with self.subTest(route=f"{route['method']} {route['path']}"):
                self.assertNotEqual(route["route_family"], "unclassified")
                self.assertNotEqual(route["surface"], "unknown")
                for owner_doc in route["owner_docs"]:
                    self.assertTrue((ROOT / owner_doc).exists(), owner_doc)

    def test_docs_and_remediation_loop_discover_backend_map(self):
        for relative_path in [
            "docs/index.md",
            "docs/living-docs-hygiene.md",
            "docs/api-and-storage.md",
            "docs/architecture-overview.md",
            "docs/architecture-best-practices.md",
            "docs/agent-memory-graph.md",
            "docs/remediation-loop-map.md",
        ]:
            with self.subTest(path=relative_path):
                self.assertIn(
                    "docs/backend-route-ownership-map.md",
                    (ROOT / relative_path).read_text(encoding="utf-8"),
                )

        remediation = json.loads((ROOT / "data" / "contracts" / "remediation-loop-map.json").read_text(encoding="utf-8"))
        point_42 = remediation["points"][41]
        self.assertEqual(point_42["point"], 42)
        self.assertEqual(point_42["status"], "completed")


if __name__ == "__main__":
    unittest.main()
