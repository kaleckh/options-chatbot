import unittest
from pathlib import Path

from scripts import generate_agent_memory_graph as memory_graph


ROOT = Path(__file__).resolve().parents[1]


class AgentMemoryGraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = memory_graph.build_graph()
        self.nodes = {node["id"]: node for node in self.graph["nodes"]}

    def test_generated_artifacts_are_current(self):
        self.assertEqual(
            memory_graph.JSON_OUTPUT_PATH.read_text(encoding="utf-8"),
            memory_graph.render_json(self.graph),
        )
        self.assertEqual(
            memory_graph.MD_OUTPUT_PATH.read_text(encoding="utf-8"),
            memory_graph.render_markdown(self.graph),
        )

    def test_graph_is_non_runtime_and_paths_exist(self):
        self.assertFalse(self.graph["runtime_use"])
        self.assertEqual(self.graph["artifact"], "agent_memory_graph")
        self.assertEqual(len(self.nodes), len(self.graph["nodes"]))

        for node in self.graph["nodes"]:
            self.assertTrue(
                (ROOT / node["path"]).exists(),
                f"{node['id']} points at a missing path: {node['path']}",
            )

    def test_required_nodes_edges_and_playbooks_exist(self):
        for node_id in [
            "architecture_best_practices",
            "living_docs_hygiene",
            "living_docs_hygiene_checker",
            "memory_graph_doc",
            "memory_graph_json",
            "route_parity_doc",
            "route_mutation_inventory_json",
            "backend_route_ownership_map_doc",
            "backend_route_ownership_map_json",
            "backend_route_ownership_map_generator",
            "storage_ownership_map_doc",
            "storage_ownership_map_json",
            "storage_ownership_map_generator",
            "proof_doc",
            "proof_invariant_cases",
            "proof_invariant_doc",
            "proof_invariant_generator",
            "scanner_doc",
            "replay_profit_doc",
            "regular_options_operating_scorecard_doc",
            "regular_options_operating_scorecard_generator",
            "regular_options_profit_capture_queue_doc",
            "regular_options_profit_capture_queue_generator",
            "regular_options_paper_shortlist_doc",
            "regular_options_paper_shortlist_generator",
            "regular_options_fresh_evidence_loop_doc",
            "regular_options_fresh_evidence_loop_generator",
            "current_policy_circuit_breaker_doc",
            "current_policy_circuit_breaker_generator",
            "regular_options_operator_workflow_doc",
            "regular_options_repair_attempts_doc",
            "regular_options_repair_attempts_generator",
            "regular_options_repair_burndown_doc",
            "regular_options_repair_burndown_generator",
            "repository_doc",
            "fintable",
            "ai_commodity_runner",
            "remediation_loop_map_doc",
            "remediation_loop_map_json",
            "remediation_loop_map_generator",
            "generated_artifact_manifest",
            "generated_artifact_governance_doc",
            "generated_artifact_governance_json",
            "generated_artifact_governance_generator",
            "final_remediation_closure_pack_doc",
            "final_remediation_closure_pack_json",
            "final_remediation_closure_pack_generator",
        ]:
            self.assertIn(node_id, self.nodes)

        edge_keys = {(edge["from"], edge["type"], edge["to"]) for edge in self.graph["edges"]}
        for edge_key in [
            ("memory_graph_generator", "generates", "memory_graph_json"),
            ("memory_graph_generator", "generates", "memory_graph_doc"),
            ("remediation_loop_map_generator", "generates", "remediation_loop_map_json"),
            ("remediation_loop_map_generator", "generates", "remediation_loop_map_doc"),
            ("memory_graph_doc", "does_not_replace", "remediation_loop_map_doc"),
            ("generated_artifact_governance_generator", "generates", "generated_artifact_governance_json"),
            ("generated_artifact_governance_generator", "generates", "generated_artifact_governance_doc"),
            ("living_docs_hygiene_checker", "consumes", "generated_artifact_manifest"),
            ("memory_graph_doc", "does_not_replace", "generated_artifact_governance_doc"),
            ("final_remediation_closure_pack_generator", "generates", "final_remediation_closure_pack_json"),
            ("final_remediation_closure_pack_generator", "generates", "final_remediation_closure_pack_doc"),
            ("final_remediation_closure_pack_json", "checks", "remediation_loop_map_json"),
            ("final_remediation_closure_pack_json", "checks", "generated_artifact_governance_json"),
            ("final_remediation_closure_pack_json", "checks", "memory_graph_json"),
            ("memory_graph_doc", "does_not_replace", "final_remediation_closure_pack_doc"),
            ("living_docs_hygiene_checker", "checks", "living_docs_hygiene"),
            ("living_docs_hygiene_checker", "checks", "docs_index"),
            ("route_parity_generator", "generates", "route_parity_doc"),
            ("route_parity_generator", "generates", "route_mutation_inventory_json"),
            ("backend_route_ownership_map_generator", "generates", "backend_route_ownership_map_json"),
            ("backend_route_ownership_map_generator", "generates", "backend_route_ownership_map_doc"),
            ("memory_graph_doc", "does_not_replace", "backend_route_ownership_map_doc"),
            ("storage_ownership_map_generator", "generates", "storage_ownership_map_json"),
            ("storage_ownership_map_generator", "generates", "storage_ownership_map_doc"),
            ("memory_graph_doc", "does_not_replace", "storage_ownership_map_doc"),
            ("schema_bridge_generator", "generates", "schema_bridge_json"),
            ("proof_generator", "generates", "proof_generated_ts"),
            ("proof_invariant_generator", "generates", "proof_invariant_doc"),
            ("memory_graph_doc", "does_not_replace", "route_parity_doc"),
            ("regular_options_operating_scorecard_generator", "generates", "regular_options_operating_scorecard_doc"),
            ("regular_options_operating_scorecard_generator", "consumes", "regular_options_profit_capture_queue_doc"),
            ("regular_options_operating_scorecard_generator", "consumes", "regular_options_paper_shortlist_doc"),
            ("regular_options_operating_scorecard_generator", "consumes", "regular_options_fresh_evidence_loop_doc"),
            ("regular_options_operating_scorecard_generator", "consumes", "current_policy_circuit_breaker_doc"),
            ("regular_options_operating_scorecard_generator", "consumes", "regular_options_repair_burndown_doc"),
            ("regular_options_profit_capture_queue_generator", "generates", "regular_options_profit_capture_queue_doc"),
            ("regular_options_paper_shortlist_generator", "generates", "regular_options_paper_shortlist_doc"),
            ("regular_options_fresh_evidence_loop_generator", "generates", "regular_options_fresh_evidence_loop_doc"),
            ("current_policy_circuit_breaker_generator", "generates", "current_policy_circuit_breaker_doc"),
            ("regular_options_repair_attempts_generator", "generates", "regular_options_repair_attempts_doc"),
            ("regular_options_repair_burndown_generator", "generates", "regular_options_repair_burndown_doc"),
            ("regular_options_repair_burndown_generator", "consumes", "regular_options_profit_capture_queue_doc"),
            ("regular_options_repair_burndown_generator", "consumes", "regular_options_repair_attempts_doc"),
        ]:
            self.assertIn(edge_key, edge_keys)

        playbooks = {playbook["id"]: playbook for playbook in self.graph["playbooks"]}
        for playbook_id in [
            "start_here",
            "routes_auth",
            "proof_evidence",
            "scanner_creation",
            "replay_profit",
            "profitability_paper_gates",
            "db_repositories",
            "frontend_trading_desk",
            "generated_artifacts",
            "ai_commodity",
            "final_closure",
        ]:
            self.assertIn(playbook_id, playbooks)
            self.assertGreaterEqual(len(playbooks[playbook_id]["nodes"]), 3)
        self.assertIn("regular_options_operating_scorecard_doc", playbooks["profitability_paper_gates"]["nodes"])
        self.assertIn("regular_options_repair_burndown_doc", playbooks["profitability_paper_gates"]["nodes"])

    def test_living_docs_link_the_memory_graph(self):
        for path in [
            ROOT / "docs" / "index.md",
            ROOT / "docs" / "living-docs-hygiene.md",
            ROOT / "docs" / "architecture-best-practices.md",
            ROOT / "docs" / "architecture-overview.md",
        ]:
            self.assertIn("docs/agent-memory-graph.md", path.read_text(encoding="utf-8"))

        self.assertIn(
            "docs/remediation-loop-map.md",
            (ROOT / "docs" / "agent-memory-graph.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "docs/final-remediation-closure-pack.md",
            (ROOT / "docs" / "agent-memory-graph.md").read_text(encoding="utf-8"),
        )

    def test_non_goals_defer_future_inventory_and_governance_points(self):
        serialized = "\n".join(self.graph["non_goals"])
        for phrase in [
            "generated route inventory",
            "route mutation inventory",
            "storage ownership maps",
            "generated artifact governance",
            "remediation loop handoff ledger",
            "final remediation closure pack",
            "runtime behavior",
        ]:
            self.assertIn(phrase, serialized)


if __name__ == "__main__":
    unittest.main()
