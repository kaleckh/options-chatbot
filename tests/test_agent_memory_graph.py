import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts import agent_control
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
            "agent_control_plane_doc",
            "agent_control_cli",
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
            ("agent_control_plane_doc", "owns", "agent_control_cli"),
            ("agent_control_cli", "implements", "agent_control_plane_doc"),
            ("memory_graph_doc", "does_not_replace", "agent_control_plane_doc"),
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
            "ceo_runtime_memory",
            "ai_commodity",
            "final_closure",
        ]:
            self.assertIn(playbook_id, playbooks)
            self.assertGreaterEqual(len(playbooks[playbook_id]["nodes"]), 3)
        self.assertIn("regular_options_operating_scorecard_doc", playbooks["profitability_paper_gates"]["nodes"])
        self.assertIn("regular_options_repair_burndown_doc", playbooks["profitability_paper_gates"]["nodes"])
        self.assertIn("agent_control_plane_doc", playbooks["ceo_runtime_memory"]["nodes"])
        self.assertIn("agent_control_cli", playbooks["ceo_runtime_memory"]["nodes"])

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


class AgentControlRetrievalTierTests(unittest.TestCase):
    def _seed_fixture_nodes(self, db_path: Path) -> None:
        with closing(agent_control.connect(db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="memory:strict-forward-blocker",
                kind="memory",
                title="Strict forward blocker memory",
                body="Strict forward 30 is blocked by candidate starvation.",
                metadata={
                    "source_type": "operating_memory",
                    "memory_type": "blocker",
                    "memory_status": "active",
                    "authority_scope": agent_control.OPERATING_AUTHORITY_SCOPE,
                    "capability_label": "coordination_only",
                },
            )
            agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:strict-forward-doc",
                kind="knowledge",
                title="Strict forward living doc",
                body="Strict forward 30 operator queue context.",
                metadata={"source_type": "living_doc"},
            )
            agent_control.upsert_graph_node(
                conn,
                node_id="repo_file:scripts/agent_control.py",
                kind="knowledge",
                title="scripts/agent_control.py",
                body="Strict forward 30 code filename agent_control.py implementation.",
                metadata={"source_type": "repo_file_index"},
            )
            agent_control.upsert_graph_edge(
                conn,
                source_node_id="knowledge:strict-forward-doc",
                relation="indexes_file",
                target_node_id="repo_file:scripts/agent_control.py",
            )

    def test_tier_ordering_keeps_repo_index_last_when_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_control.db"
            self._seed_fixture_nodes(db_path)

            result = agent_control.query_graph(
                db_path=db_path,
                query="strict forward 30",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                include_repo_index=True,
                max_depth=0,
                limit=3,
            )

            explanations = result["retrieval"]["seed_explanations"]
            source_types = [explanation["source_type"] for explanation in explanations]
            tiers = [explanation["retrieval_tier"] for explanation in explanations]
            self.assertIn("repo_file_index", source_types)
            self.assertEqual(tiers, sorted(tiers))
            self.assertEqual(source_types[-1], "repo_file_index")

    def test_tier_three_is_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_control.db"
            self._seed_fixture_nodes(db_path)

            result = agent_control.query_graph(
                db_path=db_path,
                query="agent_control.py",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                max_depth=0,
                limit=5,
            )

            source_types = [
                explanation["source_type"]
                for explanation in result["retrieval"]["seed_explanations"]
            ]
            self.assertNotIn("repo_file_index", source_types)
            self.assertNotIn("repo_file:scripts/agent_control.py", result["graph_context"]["seed_node_ids"])

    def test_tier_three_is_excluded_from_graph_expansion_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_control.db"
            self._seed_fixture_nodes(db_path)

            result = agent_control.query_graph(
                db_path=db_path,
                query="strict forward living",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                max_depth=1,
                limit=5,
            )

            source_types = [
                node["metadata"].get("source_type")
                for node in result["graph_context"]["nodes"]
            ]
            self.assertIn("living_doc", source_types)
            self.assertNotIn("repo_file_index", source_types)

    def test_graph_query_can_opt_into_repo_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_control.db"
            self._seed_fixture_nodes(db_path)

            result = agent_control.query_graph(
                db_path=db_path,
                query="agent_control.py",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                include_repo_index=True,
                max_depth=0,
                limit=5,
            )

            self.assertIn("repo_file:scripts/agent_control.py", result["graph_context"]["seed_node_ids"])

    def test_context_pack_excludes_repo_index_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "agent_control.db"
            self._seed_fixture_nodes(db_path)

            result = agent_control.build_context_pack(
                db_path=db_path,
                goal="agent_control.py",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                include_prompt_context=True,
            )

            self.assertEqual(result["relevant_repo_files"], [])
            self.assertNotIn("source=repo_file", result["prompt_context"])

    def test_golden_query_harness_uses_real_query_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "agent_control.db"
            fixture_path = tmp_path / "golden.json"
            self._seed_fixture_nodes(db_path)
            fixture_path.write_text(
                json.dumps(
                    {
                        "queries": [
                            {
                                "query": "strict forward 30",
                                "expect_source_types": ["operating_memory", "living_doc"],
                                "expect_no_source_types": ["repo_file_index"],
                            },
                            {
                                "query": "agent_control.py",
                                "include_repo_index": True,
                                "expect_source_types": ["repo_file_index"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = agent_control.memory_golden_query_eval(
                db_path=db_path,
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                fixture_path=fixture_path,
            )

            self.assertEqual(result["status"], "pass")

    def test_checked_golden_queries_include_living_history_source(self):
        payload = json.loads((ROOT / "data" / "contracts" / "memory-golden-queries.json").read_text(encoding="utf-8"))
        by_name = {case["name"]: case for case in payload["queries"]}
        self.assertIn(
            agent_control.LIVING_HISTORY_SOURCE_TYPE,
            by_name["filtered tracker context"]["expect_source_types"],
        )


class AgentControlLivingHistoryIngestTests(unittest.TestCase):
    def _write_history_repo(self, repo_root: Path) -> None:
        (repo_root / "docs").mkdir(parents=True, exist_ok=True)
        (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
        (repo_root / "docs" / "regular-options-filtered-forward-paper-shadow-tracker.md").write_text(
            "# Tracker\n",
            encoding="utf-8",
        )
        (repo_root / "scripts" / "build_regular_options_filtered_forward_paper_shadow_tracker.py").write_text(
            "print('tracker')\n",
            encoding="utf-8",
        )
        (repo_root / "docs" / "WORKLOG.md").write_text(
            "\n".join(
                [
                    "# Worklog",
                    "",
                    "## 2026-07-02",
                    "",
                    "- Added filtered forward paper shadow tracker coverage in "
                    "`docs/regular-options-filtered-forward-paper-shadow-tracker.md` and "
                    "`scripts/build_regular_options_filtered_forward_paper_shadow_tracker.py`. "
                    "This is orchestration memory only and does not authorize trading.",
                    "- Recorded a second safe verification entry.",
                ]
            ),
            encoding="utf-8",
        )
        (repo_root / "docs" / "DECISIONS.md").write_text(
            "\n".join(
                [
                    "# Decisions",
                    "",
                    "## 2026-07-02: Filtered Forward Evidence Needs A Bar",
                    "",
                    "The filtered forward tracker must wait for completed rows before evaluation.",
                    "",
                    "Durable decision: keep the tracker reporting-only and reference "
                    "`docs/regular-options-filtered-forward-paper-shadow-tracker.md`.",
                    "",
                    "## 2026-07-01: Empty Heading",
                ]
            ),
            encoding="utf-8",
        )

    def test_ingest_living_history_is_idempotent_and_retrievable(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            db_path = Path(tmp) / "agent_control.db"
            self._write_history_repo(repo_root)

            first = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id=agent_control.DEFAULT_TENANT_ID,
            )
            second = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id=agent_control.DEFAULT_TENANT_ID,
            )
            with closing(agent_control.connect(db_path)) as conn:
                repo_refs_before_seed = conn.execute(
                    "SELECT count(*) FROM graph_nodes WHERE id LIKE 'repo-ref:%'"
                ).fetchone()[0]
                living_edges_before_seed = conn.execute(
                    """
                    SELECT count(*)
                    FROM graph_edges
                    WHERE json_extract(metadata_json, '$.source_type') = ?
                    """,
                    (agent_control.LIVING_HISTORY_SOURCE_TYPE,),
                ).fetchone()[0]
            agent_control.seed_project_memory(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                include_static_memory_graph=False,
                include_gateboard=False,
                include_repo_files=True,
                max_repo_files=20,
            )
            with closing(agent_control.connect(db_path)) as conn:
                repo_refs_after_seed = conn.execute(
                    "SELECT count(*) FROM graph_nodes WHERE id LIKE 'repo-ref:%'"
                ).fetchone()[0]
                living_edges_after_seed = conn.execute(
                    """
                    SELECT count(*)
                    FROM graph_edges
                    WHERE json_extract(metadata_json, '$.source_type') = ?
                    """,
                    (agent_control.LIVING_HISTORY_SOURCE_TYPE,),
                ).fetchone()[0]
            self.assertGreaterEqual(repo_refs_before_seed, 2)
            self.assertEqual(repo_refs_after_seed, repo_refs_before_seed)
            self.assertEqual(living_edges_after_seed, living_edges_before_seed)

            original_history_count = first["nodes_created"]
            (repo_root / "docs" / "WORKLOG.md").write_text(
                "\n".join(
                    [
                        "# Worklog",
                        "",
                        "## 2026-07-02",
                        "",
                        "- Added filtered forward paper shadow tracker coverage with an edited note in "
                        "`docs/regular-options-filtered-forward-paper-shadow-tracker.md`. "
                        "This is orchestration memory only and does not authorize trading.",
                    ]
                ),
                encoding="utf-8",
            )
            changed = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id=agent_control.DEFAULT_TENANT_ID,
            )

            with closing(agent_control.connect(db_path)) as conn:
                source_rows = conn.execute(
                    """
                    SELECT kind, metadata_json
                    FROM graph_nodes
                    WHERE tenant_id = ?
                    """,
                    (agent_control.DEFAULT_TENANT_ID,),
                ).fetchall()
                history_rows = [
                    (row["kind"], json.loads(row["metadata_json"] or "{}"))
                    for row in source_rows
                    if json.loads(row["metadata_json"] or "{}").get("source_type")
                    == agent_control.LIVING_HISTORY_SOURCE_TYPE
                ]
                edge_count = conn.execute(
                    "SELECT count(*) FROM graph_edges WHERE relation = 'references'"
                ).fetchone()[0]

            self.assertEqual(first["status"], "pass_with_warnings")
            self.assertGreaterEqual(first["nodes_created"], 3)
            self.assertGreaterEqual(first["edges_created"], 2)
            self.assertIn("malformed_decision_without_body:2026-07-01: Empty Heading", first["warnings"])
            self.assertEqual(second["nodes_created"], 0)
            self.assertEqual(second["nodes_updated"], 0)
            self.assertGreaterEqual(second["nodes_skipped"], first["nodes_created"])
            self.assertGreaterEqual(changed["nodes_pruned"], 1)
            self.assertGreaterEqual(edge_count, 2)
            self.assertLessEqual(len(history_rows), original_history_count)
            self.assertTrue(any(kind == "episode" for kind, _metadata in history_rows))
            self.assertTrue(any(kind == "decision" for kind, _metadata in history_rows))
            for _kind, metadata in history_rows:
                self.assertEqual(metadata["authority_scope"], agent_control.OPERATING_AUTHORITY_SCOPE)
                self.assertEqual(metadata["capability_label"], "coordination_only")
                self.assertEqual(metadata["parser_version"], agent_control.LIVING_HISTORY_INGEST_VERSION)

            query = agent_control.query_graph(
                db_path=db_path,
                query="filtered forward paper shadow tracker",
                tenant_id=agent_control.DEFAULT_TENANT_ID,
                max_depth=0,
                limit=5,
            )
            source_types = [
                explanation["source_type"]
                for explanation in query["retrieval"]["seed_explanations"]
            ]
            self.assertIn(agent_control.LIVING_HISTORY_SOURCE_TYPE, source_types)

    def test_ingest_living_history_uses_tenant_scoped_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            db_path = Path(tmp) / "agent_control.db"
            self._write_history_repo(repo_root)

            first = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id="tenant-a",
            )
            second = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id="tenant-b",
            )
            repeat = agent_control.ingest_living_history(
                db_path=db_path,
                repo_root=repo_root,
                tenant_id="tenant-b",
            )

            with closing(agent_control.connect(db_path)) as conn:
                counts = {
                    row["tenant_id"]: row["count"]
                    for row in conn.execute(
                        """
                        SELECT tenant_id, count(*) AS count
                        FROM graph_nodes
                        WHERE json_extract(metadata_json, '$.source_type') = ?
                        GROUP BY tenant_id
                        """,
                        (agent_control.LIVING_HISTORY_SOURCE_TYPE,),
                    ).fetchall()
                }

            self.assertGreater(first["nodes_created"], 0)
            self.assertGreater(second["nodes_created"], 0)
            self.assertEqual(repeat["nodes_created"], 0)
            self.assertEqual(repeat["nodes_updated"], 0)
            self.assertIn("tenant-a", counts)
            self.assertIn("tenant-b", counts)

            tenant_a_query = agent_control.query_graph(
                db_path=db_path,
                query="filtered forward paper shadow tracker",
                tenant_id="tenant-a",
                max_depth=0,
                limit=5,
            )
            tenant_b_query = agent_control.query_graph(
                db_path=db_path,
                query="filtered forward paper shadow tracker",
                tenant_id="tenant-b",
                max_depth=0,
                limit=5,
            )
            self.assertTrue(tenant_a_query["retrieval"]["seed_explanations"])
            self.assertTrue(tenant_b_query["retrieval"]["seed_explanations"])


if __name__ == "__main__":
    unittest.main()
