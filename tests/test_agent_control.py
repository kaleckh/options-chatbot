import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import agent_control


class AgentControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "agent_control.db"
        self.events_path = self.root / "events.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_repo_file(self, repo_root: Path, relative_path: str, body: str) -> None:
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def _write_minimal_seed_repo(self, repo_root: Path, gateboard=None) -> None:
        for relative_path in [
            "AGENTS.md",
            "README.md",
            "docs/index.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/DECISIONS.md",
            "docs/NEXT_STEPS.md",
            "docs/agent-control-plane.md",
            "docs/agent-memory-graph.md",
            "docs/project-operator-gateboard.md",
            "package.json",
        ]:
            self._write_repo_file(repo_root, relative_path, f"# {relative_path}\n")
        self._write_repo_file(
            repo_root,
            "data/contracts/agent-memory-graph.json",
            json.dumps({"runtime_use": False, "nodes": [], "edges": []}),
        )
        self._write_repo_file(
            repo_root,
            "data/forward-tracking/project_operator_gateboard_latest.json",
            json.dumps(gateboard or self._gateboard_fixture(["open_risk_governor_blocked_or_missing"])),
        )

    def _gateboard_fixture(self, reasons):
        reason_payloads = {
            "open_risk_governor_blocked_or_missing": {
                "severity": "block_new_scanner_origin_entries",
                "evidence": {"status": "open_risk_governor_blocked"},
            },
            "no_promotion_ready_fresh_evidence": {
                "severity": "block_promotion_discussion",
                "evidence": {"promotion_ready_rows": 0},
            },
            "no_live_validation_lanes": {
                "severity": "block_live_validation",
                "evidence": {"live_validation_lanes": 0},
            },
        }
        return {
            "generated_at_utc": "2026-06-14T00:00:00Z",
            "runtime_use": False,
            "overall_status": "safe_blocked_no_live_release" if reasons else "observe_only",
            "primary_message": "Release is blocked." if reasons else "No current blockers.",
            "no_chase_manifest": {
                "status": "no_chase_active" if reasons else "no_chase_inactive",
                "live_policy_change": False,
                "prohibited_actions": [],
                "reasons": [
                    {
                        "reason": reason,
                        **reason_payloads.get(
                            reason,
                            {"severity": "block_operator_release", "evidence": {"status": "blocked"}},
                        ),
                    }
                    for reason in reasons
                ],
            },
            "pathway_statuses": [
                {
                    "id": "evidence_path",
                    "label": "Evidence Path",
                    "headline": "Fresh evidence is not promotion-ready.",
                    "details": ["promotion_ready_rows=0"],
                    "owner_docs": ["docs/fresh-executable-evidence-defect-report-2026-06-09.md"],
                    "owner_scripts": ["scripts/build_regular_options_fresh_evidence_loop.py"],
                    "state": "blocked",
                },
                {
                    "id": "promotion_path",
                    "label": "Promotion Path",
                    "headline": "No regular lane is live-validation eligible.",
                    "details": ["live_validation_lanes=0"],
                    "owner_docs": ["docs/lane-promotion-state.md"],
                    "owner_scripts": ["scripts/lane_promotion_state.py"],
                    "state": "blocked",
                },
            ]
            if reasons
            else [],
            "source_artifacts": {},
        }

    def _set_task_status(self, task_id: str, status: str) -> None:
        conn = agent_control.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, agent_control.utc_now(), task_id),
                )
                agent_control._update_task_graph_status(conn, task_id, status)
        finally:
            conn.close()

    def test_task_lifecycle_writes_graph_and_event_mirror(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Audit gateboard",
            description="Read gateboard and summarize blockers.",
            pathway="operator",
            permission_mode="read_only_workers",
            metadata={"goal": "ceo_startup"},
        )

        claimed = agent_control.claim_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="operator-reporter",
        )
        report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="operator-reporter",
            finding="Gateboard is safe_blocked_no_live_release.",
            proof_gate_status="blocked",
            recommendation="Stay observe-only.",
            verification="startup digest read",
        )
        accepted = agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            accepted_by="CEO",
            summary="Accepted read-only gateboard report.",
        )

        self.assertEqual(task["status"], "open")
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(report["report"]["proof_gate_status"], "blocked")
        self.assertEqual(accepted["status"], "accepted")
        self.assertIn(f"memory:worker_report:{task['id']}:1", accepted["writeback_node_ids"])

        graph = agent_control.query_graph(
            db_path=self.db_path,
            query="gateboard",
            tenant_id="options-chatbot",
            max_depth=2,
        )
        node_ids = {node["id"] for node in graph["graph_context"]["nodes"]}
        self.assertIn(f"task:{task['id']}", node_ids)
        self.assertTrue(any(edge["relation"] == "reports_on" for edge in graph["graph_context"]["edges"]))
        task_node = agent_control.query_graph(
            db_path=self.db_path,
            query=task["id"],
            kind="task",
            max_depth=0,
        )["graph_context"]["nodes"][0]
        self.assertEqual(task_node["metadata"]["status"], "accepted")
        report_memory = agent_control.query_graph(
            db_path=self.db_path,
            query="Gateboard safe blocked",
            metadata_filter={"source_type": "operating_memory"},
            memory_type="worker_report",
            max_depth=1,
        )
        self.assertEqual(report_memory["graph_context"]["seed_node_ids"], [f"memory:worker_report:{task['id']}:1"])
        self.assertTrue(any(edge["relation"] == "verified_by" for edge in report_memory["graph_context"]["edges"]))

        events = [
            json.loads(line)
            for line in self.events_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["task.created", "task.claimed", "task.reported", "task.accepted"],
        )

    def test_accept_task_writes_back_latest_report_only(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Review memory reports",
            pathway="operator",
        )
        first_report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="worker-a",
            finding="First stale report should stay submitted.",
        )
        second_report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="worker-b",
            finding="Second accepted report becomes durable memory.",
            verification="latest report selected",
        )

        accepted = agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            accepted_by="CEO",
            summary="Accept latest report.",
        )

        self.assertIn(
            f"memory:worker_report:{task['id']}:{second_report['id']}",
            accepted["writeback_node_ids"],
        )
        self.assertNotIn(
            f"memory:worker_report:{task['id']}:{first_report['id']}",
            accepted["writeback_node_ids"],
        )
        stale = agent_control.query_graph(
            db_path=self.db_path,
            query="First stale report",
            memory_type="worker_report",
            max_depth=0,
        )
        durable = agent_control.query_graph(
            db_path=self.db_path,
            query="Second accepted report",
            memory_type="worker_report",
            max_depth=0,
        )
        self.assertEqual(stale["graph_context"]["seed_node_ids"], [])
        self.assertEqual(
            durable["graph_context"]["seed_node_ids"],
            [f"memory:worker_report:{task['id']}:{second_report['id']}"],
        )

    def test_report_task_rejects_terminal_statuses(self):
        accepted_task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Accepted task",
            pathway="operator",
        )
        agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=accepted_task["id"],
            worker_id="worker-a",
            finding="Ready for acceptance.",
        )
        agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=accepted_task["id"],
            accepted_by="CEO",
            summary="Accepted.",
        )

        terminal_task_ids = {"accepted": accepted_task["id"]}
        for status in ["blocked", "cancelled"]:
            task = agent_control.create_task(
                db_path=self.db_path,
                events_path=self.events_path,
                title=f"{status} task",
                pathway="operator",
            )
            self._set_task_status(task["id"], status)
            terminal_task_ids[status] = task["id"]

        for status, task_id in terminal_task_ids.items():
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.report_task(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    task_id=task_id,
                    worker_id="late-worker",
                    finding="Late report should be rejected.",
                )
            tasks = agent_control.list_tasks(db_path=self.db_path, status=status)["tasks"]
            self.assertIn(task_id, {task["id"] for task in tasks})

    def test_accept_task_links_verification_and_artifacts_directly_to_task(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Link accepted report memories",
            pathway="operator",
        )
        report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="worker-a",
            finding="Accepted report has verification and artifacts.",
            verification="npm run verify:agent-control",
            artifacts_written="docs/agent-control-plane.md",
        )
        agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            accepted_by="CEO",
            summary="Accept report.",
        )

        graph = agent_control.query_graph(
            db_path=self.db_path,
            query=task["id"],
            include_inactive=True,
            max_depth=2,
        )
        triplets = graph["graph_context"]["triplets"]
        self.assertIn(
            {
                "source": f"memory:verification:{task['id']}:{report['id']}",
                "relation": "verifies",
                "target": f"task:{task['id']}",
                "metadata": {"source_type": "accepted_report_writeback"},
            },
            triplets,
        )
        self.assertIn(
            {
                "source": f"memory:artifact:{task['id']}:{report['id']}:1",
                "relation": "documents",
                "target": f"task:{task['id']}",
                "metadata": {"source_type": "accepted_report_writeback"},
            },
            triplets,
        )

    def test_operating_memory_supersession_filters_inactive_by_default(self):
        old = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Old memory lesson",
            body="obsolete operating memory fact",
            node_id="memory:lesson:old",
        )
        new = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="New memory lesson",
            body="replacement operating memory fact",
            node_id="memory:lesson:new",
            supersedes=[old["id"]],
        )

        active = agent_control.query_graph(
            db_path=self.db_path,
            query="obsolete operating memory fact",
            memory_type="lesson",
            max_depth=0,
        )
        inactive = agent_control.query_graph(
            db_path=self.db_path,
            query="obsolete operating memory fact",
            memory_type="lesson",
            include_inactive=True,
            max_depth=1,
        )

        self.assertEqual(active["graph_context"]["seed_node_ids"], [])
        self.assertEqual(inactive["graph_context"]["seed_node_ids"], [old["id"]])
        nodes = {node["id"]: node for node in inactive["graph_context"]["nodes"]}
        self.assertEqual(nodes[old["id"]]["metadata"]["memory_status"], "superseded")
        self.assertEqual(nodes[old["id"]]["metadata"]["superseded_by"], new["id"])
        self.assertTrue(any(edge["relation"] == "supersedes" for edge in inactive["graph_context"]["edges"]))

    def test_memory_audit_flags_missing_superseded_by_target(self):
        old = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Old target memory",
            body="old target body",
            node_id="memory:lesson:old-target",
        )
        new = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="New target memory",
            body="new target body",
            node_id="memory:lesson:new-target",
            supersedes=[old["id"]],
        )
        conn = agent_control.connect(self.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM graph_nodes WHERE id = ?", (new["id"],))
        finally:
            conn.close()

        audit = agent_control.memory_audit(db_path=self.db_path)

        issues = audit["supersession_inconsistencies"]
        self.assertEqual(audit["status"], "issues")
        self.assertTrue(
            any(
                issue["id"] == old["id"]
                and issue["metadata"]["audit_issue"] == "superseded_by target is missing"
                for issue in issues
            )
        )

    def test_memory_audit_flags_missing_supersedes_edge(self):
        old = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Old edge memory",
            body="old edge body",
            node_id="memory:lesson:old-edge",
        )
        new = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="New edge memory",
            body="new edge body",
            node_id="memory:lesson:new-edge",
            supersedes=[old["id"]],
        )
        conn = agent_control.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    DELETE FROM graph_edges
                    WHERE source_node_id = ? AND relation = ? AND target_node_id = ?
                    """,
                    (new["id"], "supersedes", old["id"]),
                )
        finally:
            conn.close()

        audit = agent_control.memory_audit(db_path=self.db_path)

        issues = audit["supersession_inconsistencies"]
        self.assertEqual(audit["status"], "issues")
        self.assertTrue(
            any(
                issue["id"] == old["id"]
                and issue["metadata"]["audit_issue"] == "superseded_by target is missing supersedes edge"
                for issue in issues
            )
        )

    def test_memory_supersede_rejects_non_operating_nodes(self):
        raw = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            title="Raw knowledge",
            body="This seeded-style knowledge node is not operating memory.",
            node_id="knowledge:raw",
        )
        new = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Typed lesson",
            body="Only operating memory can supersede operating memory.",
            node_id="memory:lesson:typed",
        )

        with self.assertRaises(agent_control.AgentControlError):
            agent_control.supersede_memory(
                db_path=self.db_path,
                events_path=self.events_path,
                old_node_id=raw["id"],
                new_node_id=new["id"],
                reason="Should not mark raw knowledge as operating memory.",
            )

    def test_context_pack_includes_accepted_worker_memory(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Build operating memory",
            pathway="operator",
        )
        report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="memory-worker",
            finding="Accepted worker report writes durable context.",
            verification="npm run verify:agent-control",
            blockers="Memory audit must stay green.",
            artifacts_written="docs/agent-control-plane.md; scripts/agent_control.py",
        )
        accepted = agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            accepted_by="CEO",
            summary="Accept memory worker report.",
        )

        pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="operating memory",
            pathway="operator",
            include_prompt_context=True,
        )

        self.assertIn(f"memory:worker_report:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertIn(f"memory:verification:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertIn(f"memory:blocker:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["worker_reports"]))
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["recent_verifications"]))
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["recent_artifacts"]))
        self.assertIn("# Agent Context Pack", pack["prompt_context"])
        self.assertIn("Accepted worker reports", pack["prompt_context"])

    def test_context_pack_includes_all_gateboard_blockers_for_operator_pathway(self):
        repo_root = self.root / "context-pack-repo"
        self._write_minimal_seed_repo(
            repo_root,
            gateboard=self._gateboard_fixture(["no_promotion_ready_fresh_evidence", "no_live_validation_lanes"]),
        )
        agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        operator_task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Operator memory",
            pathway="operator",
        )
        operator_report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=operator_task["id"],
            worker_id="operator-worker",
            finding="Operator pathway accepted memory.",
        )
        agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=operator_task["id"],
            accepted_by="CEO",
            summary="Accept operator memory.",
        )
        evidence_task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Evidence memory",
            pathway="evidence",
        )
        evidence_report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=evidence_task["id"],
            worker_id="evidence-worker",
            finding="Evidence pathway accepted memory.",
        )
        agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=evidence_task["id"],
            accepted_by="CEO",
            summary="Accept evidence memory.",
        )

        pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="operator context",
            pathway="operator",
            include_prompt_context=True,
        )

        blocker_ids = {node["id"] for node in pack["active_blockers"]}
        worker_report_ids = {node["id"] for node in pack["worker_reports"]}
        self.assertIn("blocker:gateboard:no_promotion_ready_fresh_evidence", blocker_ids)
        self.assertIn("blocker:gateboard:no_live_validation_lanes", blocker_ids)
        self.assertIn(f"memory:worker_report:{operator_task['id']}:{operator_report['id']}", worker_report_ids)
        self.assertNotIn(f"memory:worker_report:{evidence_task['id']}:{evidence_report['id']}", worker_report_ids)
        self.assertIn("blocker:gateboard:no_promotion_ready_fresh_evidence", pack["prompt_context"])

    def test_memory_audit_flags_expired_active_memory_and_query_hides_it(self):
        expired = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="open_question",
            title="Expired question",
            body="stale question should not seed active context",
            node_id="memory:open_question:expired",
            freshness_days=0,
        )

        audit = agent_control.memory_audit(db_path=self.db_path)
        active = agent_control.query_graph(
            db_path=self.db_path,
            query="stale question",
            memory_type="open_question",
            max_depth=0,
        )
        inactive = agent_control.query_graph(
            db_path=self.db_path,
            query="stale question",
            memory_type="open_question",
            include_inactive=True,
            max_depth=0,
        )

        self.assertEqual(audit["status"], "issues")
        self.assertEqual(audit["stale_or_expired"][0]["id"], expired["id"])
        self.assertEqual(active["graph_context"]["seed_node_ids"], [])
        self.assertEqual(inactive["graph_context"]["seed_node_ids"], [expired["id"]])

    def test_memory_eval_and_cli_pass_with_seeded_repo_and_checkpoint(self):
        repo_root = self.root / "eval-repo"
        self._write_minimal_seed_repo(repo_root)
        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Recover operating memory",
            summary="Checkpoint is available for eval.",
            next_actions=["Run memory eval."],
        )

        result = agent_control.memory_eval(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            require_checkpoint=True,
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "eval",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--repo-root",
                    str(repo_root),
                    "--require-checkpoint",
                    "--prompt-only",
                ]
            )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("# Agent Memory Eval", output)
        self.assertIn("PASS: latest checkpoint exists", output)

    def test_memory_eval_recovers_gateboard_blocker_without_open_risk_name(self):
        repo_root = self.root / "eval-non-open-risk-repo"
        self._write_minimal_seed_repo(
            repo_root,
            gateboard=self._gateboard_fixture(["no_promotion_ready_fresh_evidence"]),
        )
        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Recover non-open-risk blocker",
            summary="Checkpoint is available for eval.",
        )

        result = agent_control.memory_eval(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            require_checkpoint=True,
        )

        gateboard_check = next(check for check in result["checks"] if check["name"] == "gateboard blocker recovery")
        self.assertEqual(result["status"], "pass")
        self.assertTrue(gateboard_check["pass"])
        self.assertIn("blocker:gateboard:no_promotion_ready_fresh_evidence", gateboard_check["detail"])

    def test_memory_eval_passes_clean_gateboard_without_no_chase_blockers(self):
        repo_root = self.root / "eval-clean-gateboard-repo"
        self._write_minimal_seed_repo(repo_root, gateboard=self._gateboard_fixture([]))
        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Recover clean gateboard",
            summary="Checkpoint is available for eval.",
        )

        result = agent_control.memory_eval(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            require_checkpoint=True,
        )

        gateboard_check = next(check for check in result["checks"] if check["name"] == "gateboard blocker recovery")
        self.assertEqual(result["status"], "pass")
        self.assertTrue(gateboard_check["pass"])
        self.assertEqual(gateboard_check["detail"], "no current gateboard blockers")

    def test_context_pack_cli_prompt_only_prints_operating_memory(self):
        agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="decision",
            title="Memory CLI decision",
            body="context pack prompt-only should include this decision",
            sub_tenant_id="operator",
            node_id="memory:decision:cli",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "context",
                    "pack",
                    "--db",
                    str(self.db_path),
                    "--goal",
                    "Memory CLI decision",
                    "--pathway",
                    "operator",
                    "--prompt-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("# Agent Context Pack", output)
        self.assertIn("memory:decision:cli", output)
        self.assertNotIn('"recent_decisions"', output)

    def test_graph_memory_query_returns_linked_triplets(self):
        blocker = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="blocker",
            node_id="blocker:qqq-537",
            title="QQQ id 537 open risk",
            body="Fresh exact exit evidence is still missing.",
            sub_tenant_id="evidence",
        )
        action = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            node_id="knowledge:open-risk-plan",
            title="Open risk plan",
            body="Rerun review during a valid market-data window.",
            sub_tenant_id="evidence",
        )
        edge = agent_control.link_graph_nodes(
            db_path=self.db_path,
            events_path=self.events_path,
            source_node_id=blocker["id"],
            relation="requires",
            target_node_id=action["id"],
        )

        result = agent_control.query_graph(
            db_path=self.db_path,
            query="QQQ",
            sub_tenant_id="evidence",
            max_depth=1,
        )
        self.assertEqual(edge["relation"], "requires")
        self.assertEqual(
            result["graph_context"]["triplets"],
            [
                {
                    "source": "blocker:qqq-537",
                    "relation": "requires",
                    "target": "knowledge:open-risk-plan",
                    "metadata": {},
                }
            ],
        )

    def test_graph_query_supports_metadata_filter_multi_term_and_context(self):
        blocker = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="blocker",
            node_id="blocker:qqq-537-open-risk",
            title="QQQ id 537 open risk",
            body="Fresh exact exit evidence remains blocked.",
            sub_tenant_id="promotion",
            metadata={"source_type": "gateboard_blocker", "reason": "open_risk"},
        )
        plan = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            node_id="knowledge:market-window-review",
            title="Market window review",
            body="Review only during a valid market-data window.",
            sub_tenant_id="promotion",
            metadata={"source_type": "runbook"},
        )
        agent_control.link_graph_nodes(
            db_path=self.db_path,
            events_path=self.events_path,
            source_node_id=blocker["id"],
            relation="requires",
            target_node_id=plan["id"],
        )

        result = agent_control.query_graph(
            db_path=self.db_path,
            query="QQQ risk",
            sub_tenant_id="promotion",
            metadata_filter={"source_type": "gateboard_blocker"},
            include_prompt_context=True,
            max_depth=1,
        )

        self.assertEqual(result["graph_context"]["seed_node_ids"], ["blocker:qqq-537-open-risk"])
        self.assertIn("blocker:qqq-537-open-risk --requires--> knowledge:market-window-review", result["prompt_context"])

    def test_graph_query_prompt_only_cli_prints_context_text(self):
        agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="blocker",
            node_id="blocker:prompt-only",
            title="Prompt only blocker",
            body="Prompt only context.",
            metadata={"source_type": "gateboard_blocker"},
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "graph",
                    "query",
                    "prompt only",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--metadata",
                    "source_type=gateboard_blocker",
                    "--prompt-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("# Agent Graph Context", output)
        self.assertIn("blocker:prompt-only", output)
        self.assertNotIn('"graph_context"', output)

    def test_checkpoint_write_latest_and_prompt_context(self):
        checkpoint = agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Build repo-wide memory graph",
            scope="options-chatbot local runtime graph",
            summary="Seed and bootstrap are complete; checkpoint recovery is next.",
            success_criteria=["Future context can recover objective and next actions."],
            constraints=["No trading store mutation."],
            next_actions=["Add bootstrap checkpoint context."],
            verification=["npm run verify:agent-control"],
            files_changed=["scripts/agent_control.py"],
            commands_run=["npm run agent:control -- bootstrap --prompt-only"],
        )
        latest = agent_control.latest_checkpoint(db_path=self.db_path)

        self.assertEqual(checkpoint["id"], "checkpoint:latest")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["metadata"]["objective"], "Build repo-wide memory graph")
        self.assertEqual(latest["metadata"]["autonomy_level"], "read_only_workers")
        prompt_context = agent_control._format_checkpoint_context(latest)
        self.assertIn("# CEO Session Checkpoint", prompt_context)
        self.assertIn("Autonomy: read_only_workers", prompt_context)
        self.assertIn("Add bootstrap checkpoint context.", prompt_context)

    def test_checkpoint_cli_prompt_only_prints_checkpoint_text(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "checkpoint",
                    "write",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--objective",
                    "Recover CEO session",
                    "--next-action",
                    "Continue memory graph work.",
                    "--prompt-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("# CEO Session Checkpoint", output)
        self.assertIn("Recover CEO session", output)
        self.assertNotIn('"metadata"', output)

    def test_seed_project_memory_loads_docs_static_graph_and_gateboard(self):
        repo_root = self.root / "repo"
        for relative_path in [
            "AGENTS.md",
            "README.md",
            "docs/index.md",
            "docs/PROJECT_CONTEXT.md",
            "docs/DECISIONS.md",
            "docs/NEXT_STEPS.md",
            "docs/agent-control-plane.md",
            "docs/agent-memory-graph.md",
            "docs/project-operator-gateboard.md",
            "package.json",
        ]:
            self._write_repo_file(repo_root, relative_path, f"# {relative_path}\nQQQ open risk context.\n")
        self._write_repo_file(
            repo_root,
            "data/contracts/agent-memory-graph.json",
            json.dumps(
                {
                    "runtime_use": False,
                    "nodes": [
                        {
                            "id": "next_steps",
                            "kind": "doc",
                            "label": "Next Steps",
                            "owner_summary": "Active blockers and commands.",
                            "path": "docs/NEXT_STEPS.md",
                            "read_when": "Checking blockers.",
                        }
                    ],
                    "edges": [],
                }
            ),
        )
        self._write_repo_file(
            repo_root,
            "data/forward-tracking/project_operator_gateboard_latest.json",
            json.dumps(
                {
                    "generated_at_utc": "2026-06-14T00:00:00Z",
                    "runtime_use": False,
                    "overall_status": "safe_blocked_no_live_release",
                    "primary_message": "Release is blocked.",
                    "no_chase_manifest": {
                        "status": "no_chase_active",
                        "live_policy_change": False,
                        "prohibited_actions": ["do_not_open_live_or_auto_track_rows_from_blocked_readbacks"],
                        "reasons": [
                            {
                                "reason": "open_risk_governor_blocked_or_missing",
                                "severity": "block_new_scanner_origin_entries",
                                "evidence": {"ticker": "QQQ", "live_exact_negative_ids": [537]},
                            }
                        ],
                    },
                    "pathway_statuses": [
                        {
                            "id": "promotion_path",
                            "label": "Promotion Path",
                            "headline": "No regular lane is live-validation eligible.",
                            "details": ["open_risk_governor_status=open_risk_governor_blocked"],
                            "owner_docs": ["docs/lane-promotion-state.md"],
                            "owner_scripts": ["scripts/lane_promotion_state.py"],
                            "state": "blocked",
                        }
                    ],
                    "source_artifacts": {
                        "lane_promotion_state": {
                            "available": True,
                            "error": None,
                            "generated_at_utc": "2026-06-14T00:00:00Z",
                            "path": "data/forward-tracking/lane_promotion_state_latest.json",
                            "report_id": "regular_options_lane_promotion_state",
                            "status": "lane_promotion_state_readback",
                        }
                    },
                }
            ),
        )

        seed = agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )

        self.assertTrue(seed["gateboard_seeded"])
        self.assertEqual(seed["blockers_seeded"], 1)
        self.assertGreaterEqual(seed["documents_seeded"], 12)
        self.assertEqual(seed["static_nodes_seeded"], 1)
        self.assertGreaterEqual(seed["repo_files_seeded"], 12)
        result = agent_control.query_graph(
            db_path=self.db_path,
            query="QQQ risk",
            metadata_filter={"source_type": "gateboard_blocker"},
            include_prompt_context=True,
            max_depth=1,
        )
        self.assertEqual(result["graph_context"]["seed_node_ids"], ["blocker:gateboard:open_risk_governor_blocked_or_missing"])
        self.assertIn("entity:gateboard:pathway:promotion_path", result["prompt_context"])
        repo_result = agent_control.query_graph(
            db_path=self.db_path,
            query="agent-control-plane",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
        )
        self.assertIn("repo_file:docs/agent-control-plane.md", repo_result["graph_context"]["seed_node_ids"])

    def test_repo_index_includes_tracked_and_untracked_visible_files(self):
        if shutil.which("git") is None:
            self.skipTest("git is required for tracked/untracked repo index coverage")
        repo_root = self.root / "git-visible-repo"
        repo_root.mkdir()
        subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
        self._write_repo_file(repo_root, "tracked.md", "# Tracked\nstable repo context\n")
        subprocess.run(["git", "add", "tracked.md"], cwd=repo_root, check=True, capture_output=True, text=True)
        self._write_repo_file(repo_root, "scratch/untracked.md", "# Untracked\ncurrent workspace context\n")
        self._write_repo_file(repo_root, ".gitignore", "ignored.md\n")
        self._write_repo_file(repo_root, "ignored.md", "# Ignored\nmust not be indexed\n")

        seed = agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            include_static_memory_graph=False,
            include_gateboard=False,
            max_repo_files=20,
        )

        self.assertGreaterEqual(seed["repo_files_seeded"], 3)
        tracked = agent_control.query_graph(
            db_path=self.db_path,
            query="stable repo context",
            metadata_filter={"source_type": "repo_file_index", "git_state": "tracked"},
            max_depth=0,
        )
        untracked = agent_control.query_graph(
            db_path=self.db_path,
            query="current workspace context",
            metadata_filter={"source_type": "repo_file_index", "git_state": "untracked"},
            max_depth=0,
        )
        ignored = agent_control.query_graph(
            db_path=self.db_path,
            query="must not be indexed",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
        )

        self.assertEqual(tracked["graph_context"]["seed_node_ids"], ["repo_file:tracked.md"])
        self.assertEqual(untracked["graph_context"]["seed_node_ids"], ["repo_file:scratch/untracked.md"])
        self.assertEqual(ignored["graph_context"]["seed_node_ids"], [])

    def test_seed_project_memory_prunes_stale_current_state_nodes(self):
        repo_root = self.root / "prune-repo"
        self._write_minimal_seed_repo(repo_root)
        stale_path = repo_root / "notes/stale.md"
        self._write_repo_file(repo_root, "notes/stale.md", "# Stale\nremoved workspace context\n")

        first_seed = agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        self.assertEqual(first_seed["stale_nodes_pruned"], 0)
        stale_file = agent_control.query_graph(
            db_path=self.db_path,
            query="removed workspace context",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
        )
        stale_blocker = agent_control.query_graph(
            db_path=self.db_path,
            query="open risk",
            metadata_filter={"source_type": "gateboard_blocker"},
            max_depth=0,
        )
        self.assertEqual(stale_file["graph_context"]["seed_node_ids"], ["repo_file:notes/stale.md"])
        self.assertEqual(stale_blocker["graph_context"]["seed_node_ids"], ["blocker:gateboard:open_risk_governor_blocked_or_missing"])

        stale_path.unlink()
        self._write_repo_file(
            repo_root,
            "data/forward-tracking/project_operator_gateboard_latest.json",
            json.dumps(
                {
                    "generated_at_utc": "2026-06-14T00:00:00Z",
                    "runtime_use": False,
                    "overall_status": "observe_only",
                    "primary_message": "No current no-chase blockers in this fixture.",
                    "no_chase_manifest": {
                        "status": "no_chase_inactive",
                        "live_policy_change": False,
                        "prohibited_actions": [],
                        "reasons": [],
                    },
                    "pathway_statuses": [],
                    "source_artifacts": {},
                }
            ),
        )

        second_seed = agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        self.assertGreaterEqual(second_seed["stale_nodes_pruned"], 2)
        pruned_file = agent_control.query_graph(
            db_path=self.db_path,
            query="removed workspace context",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
        )
        pruned_blocker = agent_control.query_graph(
            db_path=self.db_path,
            query="open risk",
            metadata_filter={"source_type": "gateboard_blocker"},
            max_depth=0,
        )
        self.assertEqual(pruned_file["graph_context"]["seed_node_ids"], [])
        self.assertEqual(pruned_blocker["graph_context"]["seed_node_ids"], [])

    def test_bootstrap_project_context_seeds_and_returns_prompt_context(self):
        repo_root = self.root / "bootstrap-repo"
        self._write_minimal_seed_repo(repo_root)

        result = agent_control.bootstrap_project_context(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )

        self.assertEqual(result["context_query"]["metadata_filter"], {"source_type": "gateboard_blocker"})
        self.assertEqual(result["seed"]["blockers_seeded"], 1)
        self.assertGreaterEqual(result["seed"]["repo_files_seeded"], 12)
        self.assertEqual(result["digest"]["runtime_use"], True)
        self.assertIsNone(result["latest_checkpoint"])
        self.assertIn("blocker:gateboard:open_risk_governor_blocked_or_missing", result["context"]["prompt_context"])
        self.assertTrue(result["recommended_next_queries"])

        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Build memory graph",
            next_actions=["Continue end-to-end verification."],
        )
        with_checkpoint = agent_control.bootstrap_project_context(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            seed=False,
        )
        self.assertEqual(with_checkpoint["latest_checkpoint"]["metadata"]["objective"], "Build memory graph")
        self.assertIn("# CEO Session Checkpoint", with_checkpoint["prompt_context"])
        self.assertIn("Continue end-to-end verification.", with_checkpoint["prompt_context"])
        self.assertIn("repo-wide file discovery", with_checkpoint["prompt_context"])

    def test_cli_end_to_end_seed_checkpoint_bootstrap_prompt_only(self):
        repo_root = self.root / "cli-repo"
        self._write_minimal_seed_repo(repo_root)

        with redirect_stdout(io.StringIO()):
            seed_exit = agent_control.main(
                [
                    "seed",
                    "project",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--repo-root",
                    str(repo_root),
                    "--json",
                ]
            )
            checkpoint_exit = agent_control.main(
                [
                    "checkpoint",
                    "write",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--objective",
                    "Build memory graph",
                    "--next-action",
                    "Verify bootstrap handoff.",
                    "--prompt-only",
                ]
            )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            bootstrap_exit = agent_control.main(
                [
                    "bootstrap",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--repo-root",
                    str(repo_root),
                    "--skip-seed",
                    "--prompt-only",
                ]
            )

        self.assertEqual(seed_exit, 0)
        self.assertEqual(checkpoint_exit, 0)
        self.assertEqual(bootstrap_exit, 0)
        output = stdout.getvalue()
        self.assertIn("# CEO Session Checkpoint", output)
        self.assertIn("Build memory graph", output)
        self.assertIn("# Agent Graph Context", output)
        self.assertIn("blocker:gateboard:open_risk_governor_blocked_or_missing", output)

    def test_high_risk_modes_require_explicit_ack(self):
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.create_task(
                db_path=self.db_path,
                events_path=self.events_path,
                title="Mutate evidence",
                pathway="evidence",
                permission_mode="evidence_mutation",
            )

        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Discuss broker paper path",
            pathway="operator",
            permission_mode="broker_paper_discussion",
            ack_high_risk=True,
        )
        self.assertEqual(task["permission_mode"], "broker_paper_discussion")

    def test_digest_summarizes_tasks_graph_and_events(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Build runtime graph docs",
            pathway="operator",
        )
        agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="docs-worker",
            finding="Docs need a runtime graph section.",
            blockers="Missing first implementation slice.",
        )

        digest = agent_control.digest(db_path=self.db_path)
        self.assertEqual(digest["runtime_use"], True)
        self.assertEqual(digest["task_counts"]["reported"], 1)
        self.assertGreaterEqual(digest["graph_counts"]["task"], 1)
        self.assertGreaterEqual(digest["graph_counts"]["blocker"], 1)
        self.assertEqual(digest["recent_events"][0]["event_type"], "task.reported")


if __name__ == "__main__":
    unittest.main()
