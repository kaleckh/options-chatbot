from __future__ import annotations

import unittest
from pathlib import Path

from scripts import generate_storage_ownership_map as storage_map


ROOT = Path(__file__).resolve().parents[1]


class StorageOwnershipMapTests(unittest.TestCase):
    def setUp(self):
        self.storage_map = storage_map.build_storage_ownership_map()
        self.stores = {store["store_id"]: store for store in self.storage_map["stores"]}

    def test_generated_artifacts_are_current(self):
        self.assertEqual(
            storage_map.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            storage_map.render_json(self.storage_map),
        )
        self.assertEqual(
            storage_map.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            storage_map.render_markdown(self.storage_map),
        )

    def test_map_is_non_runtime_and_sources_exist(self):
        self.assertEqual(self.storage_map["artifact"], "storage_ownership_map")
        self.assertFalse(self.storage_map["runtime_use"])
        self.assertFalse(self.storage_map["validation"]["errors"])
        self.assertEqual(len(self.stores), len(self.storage_map["stores"]))

        for source in self.storage_map["sources"]:
            self.assertTrue((ROOT / source).exists(), source)

        serialized_non_goals = "\n".join(self.storage_map["non_goals"])
        for phrase in [
            "No DB reads",
            "No route handler",
            "No proof",
            "No tracked-position SQLite fallback",
            "Does not replace",
        ]:
            self.assertIn(phrase, serialized_non_goals)

    def test_every_route_and_repository_manifest_store_is_mapped(self):
        route_inventory = storage_map._load_json(storage_map.ROUTE_INVENTORY_PATH)
        route_stores = {
            store_id
            for route in route_inventory["mounted_browser_routes"]
            for store_id in route["stores"]
        }
        route_stores.update(
            route["store"]
            for route in route_inventory["backend_only_routes"]
            if route.get("store")
        )

        manifest_store_ids = {
            entry["store_id"]
            for entry in storage_map.migration_manifest()
        }
        manifest_store_ids.update(
            entry["store_id"]
            for entry in storage_map.constraint_manifest()
        )
        manifest_store_ids.update(
            entry["store_id"]
            for entry in storage_map.index_manifest()
        )
        manifest_store_ids.update(
            entry["store_id"]
            for entry in storage_map.local_database_manifest()
        )

        self.assertTrue(route_stores)
        self.assertTrue(manifest_store_ids)
        self.assertTrue(route_stores.issubset(self.stores))
        self.assertTrue(manifest_store_ids.issubset(self.stores))

    def test_tracked_and_suggested_store_boundaries_are_visible(self):
        tracked = self.stores["postgres_tracked_positions"]
        suggested = self.stores["sqlite_suggested_trades"]
        legacy = self.stores["sqlite_tracked_positions_test_legacy"]

        self.assertEqual(tracked["storage_role"], "active_repository")
        self.assertEqual(tracked["persistence"], "postgres")
        self.assertEqual(tracked["location"], "DATABASE_URL")
        self.assertEqual(len(tracked["route_references"]["active_browser"]), 4)
        self.assertTrue(tracked["repository_migrations"])
        self.assertIn("db_enforced", tracked["repository_constraints_by_enforcement"])
        self.assertIn("db_existing", tracked["repository_indexes_by_status"])
        self.assertIn("Do not silently fall back to SQLite.", tracked["hard_rules"])

        self.assertEqual(suggested["storage_role"], "active_repository")
        self.assertEqual(suggested["persistence"], "sqlite")
        self.assertEqual(suggested["location"], "chat_history.db")
        self.assertEqual(len(suggested["route_references"]["active_browser"]), 4)
        self.assertEqual(suggested["local_database_roles"][0]["mutability"], "active_mutable")
        self.assertIn("suggested_trade", suggested["record_classes"])

        self.assertEqual(legacy["storage_role"], "test_legacy_repository")
        self.assertEqual(legacy["scope"], "test_legacy")
        self.assertFalse(legacy["route_references"]["active_browser"])
        self.assertIn("Do not route browser tracked-position traffic to this store.", legacy["hard_rules"])

    def test_route_artifact_and_virtual_stores_do_not_look_like_databases(self):
        backend_domain = self.stores["backend/domain"]
        tools = self.stores["backend_tool_dispatch"]
        market_data = self.stores["market_data_cache"]

        self.assertEqual(backend_domain["persistence"], "virtual")
        self.assertEqual(backend_domain["storage_role"], "backend_domain")
        self.assertTrue(backend_domain["route_references"]["backend_only"])

        self.assertEqual(tools["persistence"], "virtual")
        self.assertEqual(tools["storage_role"], "backend_dispatch")
        self.assertEqual(len(tools["route_references"]["active_browser"]), 1)

        self.assertEqual(market_data["storage_role"], "support_cache")
        self.assertEqual(market_data["local_database_roles"][0]["mutability"], "outside_repository_scope")
        self.assertIn("Outside Trading Desk repository", market_data["hard_rules"][0])

    def test_living_docs_and_memory_graph_link_storage_map(self):
        for path in [
            ROOT / "docs" / "index.md",
            ROOT / "docs" / "api-and-storage.md",
            ROOT / "docs" / "architecture-overview.md",
            ROOT / "docs" / "agent-memory-graph.md",
        ]:
            self.assertIn("storage-ownership-map", path.read_text(encoding="utf-8"))

    def test_generated_map_has_no_placeholders(self):
        serialized = storage_map.render_json(self.storage_map)
        self.assertNotIn("TODO", serialized)
        self.assertNotIn("TBD", serialized)


if __name__ == "__main__":
    unittest.main()
