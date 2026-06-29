import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest import mock

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

    def _write_profit_learning_artifact(self, repo_root: Path, artifact_name: str, payload: dict) -> None:
        relative_path = agent_control.PROFIT_LEARNING_ARTIFACTS[artifact_name]
        self._write_repo_file(repo_root, relative_path, json.dumps(payload))

    def _write_profit_learning_repo(self, repo_root: Path) -> None:
        self._write_profit_learning_artifact(
            repo_root,
            "gateboard",
            {
                "generated_at_utc": "2026-06-28T20:00:00Z",
                "overall_status": "safe_blocked_no_live_release",
                "no_chase_manifest": {
                    "reasons": [
                        {
                            "reason": "thin_fresh_forward_denominator",
                            "status": "ready_for_research_only",
                            "evidence": ["exact_forward_rows:0", "fresh_scan_match_count:2"],
                        }
                    ]
                },
                "broker_order_allowed": True,
                "scanner_policy_changed": True,
            },
        )
        self._write_profit_learning_artifact(
            repo_root,
            "forward_candidate_throughput",
            {
                "generated_at_utc": "2026-06-28T20:01:00Z",
                "status": "blocked_no_same_day_phase2_natural_selections",
                "zero_candidate_diagnostics": {
                    "target_selection_date": "2026-06-28",
                    "status": "no_phase2_candidates",
                    "returned_picks": 0,
                    "candidate_rows_staged": 0,
                },
                "scheduled_phase2_drop_counts": {"strict_forward_reject": 4, "market_window_not_open": 2},
                "broker_order_allowed": True,
            },
        )
        self._write_profit_learning_artifact(
            repo_root,
            "profit_capture_queue",
            {
                "generated_at_utc": "2026-06-28T20:02:00Z",
                "status": "promotion_ready",
                "summary": {
                    "queue_rows": 97,
                    "quarantine_queue_count": 173,
                    "high_priority_evidence_repair_count": 16,
                    "fresh_scan_match_count": 2,
                },
                "reason_codes": [
                    "positive_exact_intraday_symbol_lane",
                    "fresh_executable_tier_a_match_required",
                ],
                "live_entry_allowed": True,
                "evidence_stores_mutated": True,
            },
        )

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

    def test_agent_run_ledger_appends_redacts_and_validates_hash_chain(self):
        started = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-test-ledger",
            event_type="started",
            title="Test ledger sk-titleSecret123",
            summary="Start run with Authorization: Basic abcdef.",
            payload={"goal": "test", "api_token": "secret-token", "nested": {"password": "secret"}},
        )
        tool = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-test-ledger",
            event_type="tool_call",
            summary="Ran a read-only command.",
            payload={"command": "npm run memory:bootstrap", "authorization": "Bearer abc"},
        )
        completed = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-test-ledger",
            event_type="completed",
            summary="Run completed.",
            payload={"artifact": "docs/agent-control-plane.md"},
        )

        self.assertEqual(started["payload"]["api_token"], agent_control.AGENT_RUN_REDACTED)
        self.assertEqual(started["payload"]["nested"]["password"], agent_control.AGENT_RUN_REDACTED)
        self.assertNotIn("sk-titleSecret123", started["title"])
        self.assertNotIn("abcdef", started["summary"])
        self.assertEqual(tool["payload"]["authorization"], agent_control.AGENT_RUN_REDACTED)
        self.assertEqual(tool["prev_event_hash"], started["event_hash"])
        self.assertEqual(completed["prev_event_hash"], tool["event_hash"])
        with closing(agent_control.connect(self.db_path)) as conn:
            audit = agent_control.validate_agent_run_ledger(conn)
        self.assertEqual(audit["status"], "pass")

        runs = agent_control.list_agent_runs(db_path=self.db_path)
        self.assertEqual(runs["runs"][0]["run_id"], "RUN-test-ledger")
        self.assertEqual(runs["runs"][0]["status"], "succeeded")
        self.assertEqual(runs["runs"][0]["tool_call_count"], 1)

    def test_agent_run_ledger_handles_noisy_runs_and_tenant_scoped_run_ids(self):
        for index in range(35):
            agent_control.record_agent_run_event(
                db_path=self.db_path,
                events_path=self.events_path,
                run_id="RUN-noisy",
                event_type="tool_call" if index else "started",
                summary=f"noisy event {index}",
            )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-quiet",
            event_type="started",
            summary="quiet run",
        )
        tenant_a = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-shared",
            event_type="started",
            tenant_id="tenant-a",
            summary="tenant a",
        )
        tenant_b = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-shared",
            event_type="started",
            tenant_id="tenant-b",
            summary="tenant b",
        )

        runs = agent_control.list_agent_runs(db_path=self.db_path, limit=2)
        self.assertEqual({run["run_id"] for run in runs["runs"]}, {"RUN-noisy", "RUN-quiet"})
        self.assertNotEqual(tenant_a["event_hash"], tenant_b["event_hash"])
        with closing(agent_control.connect(self.db_path)) as conn:
            self.assertEqual(agent_control.validate_agent_run_ledger(conn, tenant_id="tenant-a")["status"], "pass")
            self.assertEqual(agent_control.validate_agent_run_ledger(conn, tenant_id="tenant-b")["status"], "pass")

    def test_agent_run_ledger_status_filter_finds_older_matching_runs(self):
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-old-failed",
            event_type="failed",
            summary="older failed run",
        )
        for index in range(201):
            agent_control.record_agent_run_event(
                db_path=self.db_path,
                events_path=self.events_path,
                run_id=f"RUN-noise-{index:03d}",
                event_type="started",
                summary="newer noise",
            )

        runs = agent_control.list_agent_runs(db_path=self.db_path, status="failed", limit=20)
        self.assertEqual([run["run_id"] for run in runs["runs"]], ["RUN-old-failed"])

    def test_agent_run_ledger_audit_reports_malformed_payload_json(self):
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-corrupt",
            event_type="started",
            summary="will corrupt payload",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE agent_run_events SET payload_json = ? WHERE id = ?",
                    ("{broken-json", event["id"]),
                )
            audit = agent_control.validate_agent_run_ledger(conn)

        self.assertEqual(audit["status"], "issues")
        self.assertTrue(any("payload_json" in issue["issue"] for issue in audit["issues"]))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                ["memory", "run-ledger", "--db", str(self.db_path), "--prompt-only"]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("Audit: issues", stdout.getvalue())

    def test_agent_run_ledger_cli_prompt_only(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "run",
                    "event",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--run-id",
                    "RUN-cli-ledger",
                    "--event-type",
                    "blocked",
                    "--title",
                    "CLI ledger",
                    "--summary",
                    "Blocked waiting for user input.",
                    "--payload",
                    json.dumps({"blocker_code": "user_input_required"}),
                    "--prompt-only",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("RUN-cli-ledger", stdout.getvalue())

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                ["memory", "run-ledger", "--db", str(self.db_path), "--prompt-only"]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("# Agent Run Ledger", stdout.getvalue())
        self.assertIn("Audit: pass", stdout.getvalue())
        self.assertIn("user_input_required", stdout.getvalue())

    def test_daily_operator_brief_surfaces_attention_and_pending_approvals(self):
        repo_root = self.root / "daily-brief-repo"
        self._write_minimal_seed_repo(repo_root)
        agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-brief-blocked",
            event_type="started",
            title="Brief blocked",
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-brief-blocked",
            event_type="approval_requested",
            summary="Need operator decision before guarded append.",
            payload={"approval_scope": "guarded_append"},
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-brief-blocked",
            event_type="blocked",
            summary="Blocked waiting for operator.",
            payload={"blocker_code": "user_input_required"},
        )

        brief = agent_control.daily_operator_brief(db_path=self.db_path, runs_dir=self.root / "dream-runs")
        rendered = agent_control._format_daily_operator_brief(brief)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "daily-brief",
                    "--db",
                    str(self.db_path),
                    "--runs-dir",
                    str(self.root / "dream-runs"),
                    "--prompt-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(brief["status"], "needs_attention")
        self.assertEqual(brief["attention_runs"][0]["run_id"], "RUN-brief-blocked")
        self.assertEqual(brief["pending_approvals"][0]["run_id"], "RUN-brief-blocked")
        self.assertTrue(brief["pending_approvals"][0]["non_authoritative"])
        self.assertIn("ledger note only; not authorization", rendered)
        self.assertIn("# Daily Operator Brief", stdout.getvalue())
        self.assertIn("RUN-brief-blocked", stdout.getvalue())

    def test_daily_operator_brief_keeps_later_approval_request_pending(self):
        repo_root = self.root / "daily-brief-later-approval-repo"
        self._write_minimal_seed_repo(repo_root)
        agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        for event_type, summary in [
            ("started", "started"),
            ("approval_requested", "First request."),
            ("approval_recorded", "First request recorded."),
            ("approval_requested", "Second request still pending."),
        ]:
            agent_control.record_agent_run_event(
                db_path=self.db_path,
                events_path=self.events_path,
                run_id="RUN-later-approval",
                event_type=event_type,
                summary=summary,
            )

        brief = agent_control.daily_operator_brief(db_path=self.db_path, runs_dir=self.root / "dream-runs")

        self.assertEqual([approval["run_id"] for approval in brief["pending_approvals"]], ["RUN-later-approval"])
        self.assertIn("Second request still pending.", brief["pending_approvals"][0]["summary"])

    def test_agent_eval_harness_runs_temp_self_tests_and_cli(self):
        repo_root = self.root / "agent-eval-repo"
        self._write_minimal_seed_repo(repo_root)
        result = agent_control.agent_eval_harness(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "agent-eval",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--repo-root",
                    str(repo_root),
                    "--prompt-only",
                ]
            )

        self.assertEqual(result["status"], "pass")
        self.assertTrue(all(check["pass"] for check in result["checks"]))
        self.assertEqual(exit_code, 0)
        self.assertIn("# Agent Eval Harness", stdout.getvalue())
        self.assertIn("daily brief surfaces blocked run", stdout.getvalue())

    def test_agent_eval_harness_fails_on_tampered_live_ledger(self):
        repo_root = self.root / "agent-eval-fail-repo"
        self._write_minimal_seed_repo(repo_root)
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-tampered-live",
            event_type="started",
            summary="tamper target",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE agent_run_events SET payload_json = ? WHERE id = ?",
                    (json.dumps({"tampered": True}), event["id"]),
                )

        result = agent_control.agent_eval_harness(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )

        self.assertEqual(result["status"], "fail")
        failed = [check for check in result["checks"] if not check["pass"]]
        self.assertTrue(any(check["name"] == "live agent run ledger audit passes" for check in failed))

    def test_blocker_autopsy_groups_repeated_blockers_and_cli(self):
        for run_id in ["RUN-blocker-a", "RUN-blocker-b"]:
            agent_control.record_agent_run_event(
                db_path=self.db_path,
                events_path=self.events_path,
                run_id=run_id,
                event_type="blocked",
                summary="Waiting for explicit operator input.",
                payload={"blocker_code": "user_input_required"},
            )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-blocker-c",
            event_type="failed",
            summary="Different failure.",
            payload={"blocker_code": "provider_unavailable"},
        )

        report = agent_control.blocker_autopsy_report(db_path=self.db_path)
        rendered = agent_control._format_blocker_autopsy_report(report)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                ["memory", "blocker-autopsy", "--db", str(self.db_path), "--prompt-only"]
            )

        self.assertEqual(report["status"], "repeated_blockers")
        self.assertEqual(report["repeated_blockers"][0]["code"], "user_input_required")
        self.assertEqual(report["repeated_blockers"][0]["count"], 2)
        provider = next(item for item in report["latest_blockers"] if item["code"] == "provider_unavailable")
        self.assertEqual(provider["taxonomy"], "uncategorized")
        self.assertIn("safe next step", rendered)
        self.assertIn(agent_control.MEMORY_NON_AUTHORIZATION_BANNER, rendered)
        self.assertEqual(exit_code, 0)
        self.assertIn("user_input_required", stdout.getvalue())

    def test_local_inbox_lists_pending_items_and_hides_resolved_approvals(self):
        for event_type, summary in [
            ("started", "started"),
            ("approval_requested", "Resolved approval."),
            ("approval_recorded", "Resolved approval recorded."),
        ]:
            agent_control.record_agent_run_event(
                db_path=self.db_path,
                events_path=self.events_path,
                run_id="RUN-resolved-approval",
                event_type=event_type,
                summary=summary,
            )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-pending-approval",
            event_type="approval_requested",
            summary="Operator input needed.",
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-inbox-blocked",
            event_type="blocked",
            summary="Blocked on provider.",
            payload={"blocker_code": "external_dependency"},
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-inbox-failed",
            event_type="failed",
            summary="Failed local command.",
            payload={"blocker_code": "tool_failure"},
        )
        running = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-inbox-stale",
            event_type="started",
            summary="Long running task.",
        )
        stale_time = (agent_control.datetime.now(agent_control.timezone.utc) - agent_control.timedelta(hours=8)).isoformat()
        with closing(agent_control.connect(self.db_path)) as conn:
            with conn:
                conn.execute(
                    "UPDATE agent_run_events SET created_at = ? WHERE id = ?",
                    (stale_time, running["id"]),
                )

        report = agent_control.local_inbox_report(db_path=self.db_path)
        rendered = agent_control._format_local_inbox_report(report)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                ["memory", "inbox", "--db", str(self.db_path), "--prompt-only"]
            )
        run_ids = {item["run_id"] for item in report["items"]}

        self.assertEqual(report["status"], "pending")
        self.assertIn("RUN-pending-approval", run_ids)
        self.assertIn("RUN-inbox-blocked", run_ids)
        self.assertIn("RUN-inbox-failed", run_ids)
        self.assertIn("RUN-inbox-stale", run_ids)
        self.assertNotIn("RUN-resolved-approval", run_ids)
        kinds = {item["run_id"]: item["kind"] for item in report["items"]}
        self.assertEqual(kinds["RUN-inbox-failed"], "failed")
        self.assertEqual(kinds["RUN-inbox-stale"], "stale_running")
        self.assertIn("ledger note only; not authorization", rendered)
        self.assertEqual(exit_code, 0)
        self.assertIn("# Local Agent Inbox", stdout.getvalue())

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

    def test_claim_task_rejects_stale_status_update(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Claim stale task",
            pathway="operator",
        )
        original_task_row = agent_control._task_row
        stale_once = {"done": False}

        def stale_task_row(conn, task_id):
            row = original_task_row(conn, task_id)
            if task_id == task["id"] and not stale_once["done"]:
                stale_once["done"] = True
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    ("accepted", agent_control.utc_now(), task_id),
                )
            return row

        with mock.patch.object(agent_control, "_task_row", side_effect=stale_task_row):
            with self.assertRaisesRegex(agent_control.AgentControlError, "status changed concurrently"):
                agent_control.claim_task(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    task_id=task["id"],
                    worker_id="late-worker",
                )

        with closing(agent_control.connect(self.db_path)) as conn:
            self.assertEqual(agent_control._task_row(conn, task["id"])["status"], "open")

    def test_report_task_rejects_stale_terminal_status_update(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Report stale task",
            pathway="operator",
        )
        original_task_row = agent_control._task_row
        stale_once = {"done": False}

        def stale_task_row(conn, task_id):
            row = original_task_row(conn, task_id)
            if task_id == task["id"] and not stale_once["done"]:
                stale_once["done"] = True
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    ("accepted", agent_control.utc_now(), task_id),
                )
            return row

        with mock.patch.object(agent_control, "_task_row", side_effect=stale_task_row):
            with self.assertRaisesRegex(agent_control.AgentControlError, "status changed concurrently"):
                agent_control.report_task(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    task_id=task["id"],
                    worker_id="late-worker",
                    finding="Late report should be rejected.",
                )

        with closing(agent_control.connect(self.db_path)) as conn:
            self.assertEqual(agent_control._task_row(conn, task["id"])["status"], "open")

    def test_accept_task_rejects_stale_status_update(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Accept stale task",
            pathway="operator",
        )
        agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="worker-a",
            finding="Ready for acceptance.",
        )
        original_task_row = agent_control._task_row
        stale_once = {"done": False}

        def stale_task_row(conn, task_id):
            row = original_task_row(conn, task_id)
            if task_id == task["id"] and not stale_once["done"]:
                stale_once["done"] = True
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    ("cancelled", agent_control.utc_now(), task_id),
                )
            return row

        with mock.patch.object(agent_control, "_task_row", side_effect=stale_task_row):
            with self.assertRaisesRegex(agent_control.AgentControlError, "status changed concurrently"):
                agent_control.accept_task(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    task_id=task["id"],
                    accepted_by="CEO",
                    summary="Accepted stale report.",
                )

        with closing(agent_control.connect(self.db_path)) as conn:
            self.assertEqual(agent_control._task_row(conn, task["id"])["status"], "reported")

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

    def test_graph_remember_cannot_forge_operating_memory(self):
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                kind="memory",
                title="Forged operating memory",
                body="This should not enter context packs as reviewed memory.",
                metadata={"source_type": "operating_memory", "memory_type": "decision"},
            )

    def test_memory_remember_defaults_to_inferred_confidence(self):
        memory = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Manual note",
            body="Manual memory should not default to accepted confidence.",
            node_id="memory:lesson:manual-note",
        )

        self.assertEqual(memory["metadata"]["confidence"], "inferred")

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

    def test_memory_audit_and_repair_authority_metadata_for_legacy_rows(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO graph_nodes(
                    id, kind, tenant_id, sub_tenant_id, title, body, metadata_json,
                    source_ref, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "memory:lesson:legacy-authority",
                    "memory",
                    agent_control.DEFAULT_TENANT_ID,
                    None,
                    "Legacy memory",
                    "Legacy operating memory without authority metadata.",
                    agent_control.canonical_json(
                        {
                            "source_type": "operating_memory",
                            "memory_type": "lesson",
                            "memory_status": "active",
                            "confidence": "accepted",
                        }
                    ),
                    "legacy:test",
                    agent_control.utc_now(),
                    agent_control.utc_now(),
                ),
            )

        audit = agent_control.memory_audit(db_path=self.db_path)

        self.assertEqual(audit["status"], "issues")
        self.assertTrue(
            any(issue["id"] == "memory:lesson:legacy-authority" for issue in audit["authority_inconsistencies"])
        )

        repair = agent_control.repair_operating_memory_authority_metadata(db_path=self.db_path)
        repaired_audit = agent_control.memory_audit(db_path=self.db_path)

        self.assertEqual(repair["status"], "repaired")
        self.assertEqual(repair["repaired_count"], 1)
        self.assertEqual(repaired_audit["authority_inconsistencies"], [])

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
            files_read="docs/agent-control-plane.md",
            commands_run="npm run verify:agent-control",
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
            manifest_dir=self.root / "context-packs",
        )

        self.assertIn(f"memory:worker_report:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertIn(f"memory:verification:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertIn(f"memory:blocker:{task['id']}:{report['id']}", accepted["writeback_node_ids"])
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["worker_reports"]))
        decision_graph = agent_control.query_graph(
            db_path=self.db_path,
            query=accepted["decision_node_id"],
            max_depth=0,
            include_inactive=True,
        )
        decision_node = next(
            node for node in decision_graph["graph_context"]["nodes"] if node["id"] == accepted["decision_node_id"]
        )
        self.assertEqual(decision_node["metadata"]["authority_scope"], "orchestration_only")
        self.assertTrue(decision_node["metadata"]["does_not_authorize_trading_or_evidence_mutation"])
        worker_memory = next(node for node in pack["worker_reports"] if node["id"] in accepted["writeback_node_ids"])
        self.assertEqual(worker_memory["metadata"]["authority_scope"], "orchestration_only")
        self.assertTrue(worker_memory["metadata"]["does_not_authorize_trading_or_evidence_mutation"])
        self.assertEqual(worker_memory["metadata"]["files_artifacts_read"], "docs/agent-control-plane.md")
        self.assertEqual(worker_memory["metadata"]["commands_run"], "npm run verify:agent-control")
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["recent_verifications"]))
        self.assertTrue(any(node["id"] in accepted["writeback_node_ids"] for node in pack["recent_artifacts"]))
        self.assertIn("# Agent Context Pack", pack["prompt_context"])
        self.assertIn("Accepted worker reports", pack["prompt_context"])
        self.assertIn("commands: npm run verify:agent-control", pack["prompt_context"])

    def test_writeback_alias_accepts_report_into_operating_memory(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Alias writeback",
            pathway="operator",
        )
        report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="memory-worker",
            finding="Writeback alias should accept this report.",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "writeback",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    task["id"],
                    "--summary",
                    "Accepted through writeback alias.",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "accepted")
        self.assertIn(f"memory:worker_report:{task['id']}:{report['id']}", payload["writeback_node_ids"])

    def test_writeback_alias_requires_worker_report(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="No report writeback",
            pathway="operator",
        )

        exit_code = agent_control.main(
            [
                "writeback",
                "--db",
                str(self.db_path),
                "--events",
                str(self.events_path),
                task["id"],
                "--summary",
                "Should fail because no report exists.",
                "--json",
            ]
        )
        listed = agent_control.list_tasks(db_path=self.db_path)

        self.assertEqual(exit_code, 2)
        self.assertEqual(next(row for row in listed["tasks"] if row["id"] == task["id"])["status"], "open")

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
            manifest_dir=self.root / "context-packs",
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
                    "--manifest-dir",
                    str(self.root / "context-packs"),
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
        self.assertGreaterEqual(seed["repo_files_seeded"], 11)
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

    def test_repo_index_refuses_secret_and_generated_paths(self):
        repo_root = self.root / "safety-repo"
        self._write_minimal_seed_repo(repo_root)
        self._write_repo_file(repo_root, ".env", "SECRET=value\n")
        self._write_repo_file(repo_root, "keys/private.pem", "private key\n")
        self._write_repo_file(repo_root, "data/forward-tracking/report.md", "# Generated evidence\n")
        self._write_repo_file(repo_root, "data/contracts/allowed.json", json.dumps({"runtime_use": False}))

        seed = agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            include_static_memory_graph=False,
            include_gateboard=False,
            max_repo_files=50,
        )

        self.assertGreater(seed["repo_files_seeded"], 0)
        blocked_queries = [
            "SECRET",
            "private key",
            "Generated evidence",
        ]
        for query in blocked_queries:
            result = agent_control.query_graph(
                db_path=self.db_path,
                query=query,
                metadata_filter={"source_type": "repo_file_index"},
                max_depth=0,
            )
            self.assertEqual(result["graph_context"]["seed_node_ids"], [])
        allowed = agent_control.query_graph(
            db_path=self.db_path,
            query="allowed",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
        )
        self.assertEqual(allowed["graph_context"]["seed_node_ids"], ["repo_file:data/contracts/allowed.json"])

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
        self.assertEqual(result["context_query"]["query"], "gateboard")
        self.assertEqual(result["seed"]["blockers_seeded"], 1)
        self.assertGreaterEqual(result["seed"]["repo_files_seeded"], 11)
        self.assertEqual(result["digest"]["runtime_use"], True)
        self.assertIsNone(result["latest_checkpoint"])
        self.assertIn(
            "blocker:gateboard:open_risk_governor_blocked_or_missing",
            result["context"]["graph_context"]["seed_node_ids"],
        )
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
                    "--manifest-dir",
                    str(self.root / "context-packs"),
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

    def test_bootstrap_cli_writes_context_manifest_and_dashboard_passes_startup(self):
        repo_root = self.root / "bootstrap-cli-manifest-repo"
        self._write_minimal_seed_repo(repo_root)
        runs_dir = self.root / "dream-runs"
        agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            dreams_dir=self.root / "dreams",
            runs_dir=runs_dir,
            generate_from_sessions=False,
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
                    "--no-repo-files",
                    "--manifest-dir",
                    str(self.root / "context-packs"),
                    "--prompt-only",
                ]
            )

        dashboard = agent_control.operator_dashboard(db_path=self.db_path, runs_dir=runs_dir)
        self.assertEqual(bootstrap_exit, 0)
        self.assertIn("# Context Manifest", stdout.getvalue())
        startup_check = next(check for check in dashboard["checks"] if check["name"] == "startup/context manifest")
        self.assertTrue(startup_check["pass"])

    def test_agent_facing_memory_commands_are_discoverable(self):
        help_text = agent_control.build_parser().format_help()
        for expected in [
            "Common agent commands",
            "npm run memory:bootstrap",
            "npm run memory:context",
            "npm run memory:audit",
            "npm run memory:repair-authority",
            "npm run memory:dream-run",
            "npm run memory:dream-audit",
            "npm run memory:operator-dashboard",
            "npm run memory:research-priorities",
            "npm run memory:profit-learning-sync",
            "npm run memory:profit-learning-audit",
            "npm run memory:review-dreams",
            "npm run memory:dreams",
            "npm run memory:eval",
            "npm run verify:memory",
            "writeback <task-id>",
        ]:
            self.assertIn(expected, help_text)

        package = json.loads((agent_control.ROOT / "package.json").read_text(encoding="utf-8"))
        for script_name in [
            "memory:bootstrap",
            "memory:context",
            "memory:audit",
            "memory:repair-authority",
            "memory:dream-run",
            "memory:dream-audit",
            "memory:operator-dashboard",
            "memory:research-priorities",
            "memory:profit-learning-sync",
            "memory:profit-learning-audit",
            "memory:schedule-dreams",
            "memory:review-dreams",
            "memory:dreams",
            "memory:eval",
            "memory:writeback",
            "verify:memory",
        ]:
            self.assertIn(script_name, package["scripts"])
        self.assertEqual(
            package["scripts"]["memory:profit-learning-sync"],
            (
                "uv run --locked python scripts/agent_control.py memory profit-learning-sync "
                "--write-memory --approval-token APPROVE_PROFIT_LEARNING_MEMORY_SYNC --prompt-only"
            ),
        )
        self.assertEqual(
            package["scripts"]["memory:profit-learning-audit"],
            "uv run --locked python scripts/agent_control.py memory profit-learning-audit --prompt-only",
        )

    def test_memory_policy_rejects_authority_wording_and_retrieval_explains_hits(self):
        for title, body, metadata in [
            ("Bad authority", "Approve live trading from memory.", {}),
            ("Broker order authority", "Broker orders are enabled by memory.", {}),
            ("Submit order authority", "Submit orders is approved by memory.", {}),
            ("Place order authority", "Place orders from memory.", {}),
            ("Camel flags", "Looks harmless.", {"appendAllowed": True, "promotionReady": True}),
            ("Live validation camel flag", "Looks harmless.", {"liveValidationEligible": True}),
            ("Truthy string flags", "Looks harmless.", {"append_allowed": "true", "promotionReady": "yes"}),
            ("Nested flags", "Looks harmless.", {"nested": {"appendAllowed": True, "liveValidationEligible": "1"}}),
            ("Nested authority labels", "Looks harmless.", {"nested": {"authority_scope": "promotion_authority"}}),
            ("Case authority labels", "Looks harmless.", {"authority_scope": "Promotion_Authority"}),
            ("Whitespace authority labels", "Looks harmless.", {"capability_label": " promotion_authority "}),
            ("List truthy flags", "Looks harmless.", {"items": [{"brokerOrderAllowed": "enabled"}]}),
            ("Numeric truthy flags", "Looks harmless.", {"items": [{"brokerOrderAllowed": 1}]}),
            ("Append readiness text", "Append readiness is approved by memory.", {}),
            ("Cohort append text", "Cohort append is approved by memory.", {}),
            ("Candidate append text", "Candidate append is ready and cleared by memory.", {}),
            ("Guarded append text", "Guarded append is allowed by memory.", {}),
            ("Mixed unsafe after negation", "Memory must not authorize trading but broker orders are approved by memory.", {}),
            ("Unsafe after negation and", "Memory must not authorize trading and broker orders are approved by memory.", {}),
            ("Unsafe after negation comma", "Memory must not authorize trading, broker orders are approved by memory.", {}),
        ]:
            with self.subTest(title=title):
                with self.assertRaises(agent_control.AgentControlError):
                    agent_control.remember_operating_memory(
                        db_path=self.db_path,
                        events_path=self.events_path,
                        memory_type="lesson",
                        title=title,
                        body=body,
                        metadata=metadata,
                    )

        for body in [
            "Memory cannot authorize live trading.",
            "Memory can't authorize broker orders.",
            "Memory never approve proof-bar changes.",
        ]:
            with self.subTest(body=body):
                agent_control.remember_operating_memory(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    memory_type="constraint",
                    title=f"Safe prohibition {len(body)}",
                    body=body,
                    node_id=f"memory:constraint:safe-prohibition:{len(body)}",
                    metadata={"safe_false": False, "safe_zero": 0, "safe_string_false": "false"},
                )

        with self.assertRaises(agent_control.AgentControlError):
            agent_control.remember_operating_memory(
                db_path=self.db_path,
                events_path=self.events_path,
                memory_type="constraint",
                title="Unsafe mixed cannot",
                body="Memory cannot authorize live trading, but broker orders are approved by memory.",
                node_id="memory:constraint:unsafe-mixed-cannot",
            )

        safe = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Retrieval v2 smoke lesson",
            body="Retrieval documents should explain source quality and authority scope.",
            metadata={"retrieval_keywords": ["retrieval-v2", "authority-scope"]},
            node_id="memory:lesson:retrieval-v2-smoke",
        )
        prohibition = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="constraint",
            title="Dreams cannot authorize options actions",
            body="Dream memories must not authorize trading, broker paths, evidence mutation, or promotion.",
            node_id="memory:constraint:safe-negated-authority",
        )

        self.assertEqual(safe["metadata"]["authority_scope"], "orchestration_only")
        self.assertEqual(prohibition["metadata"]["authority_scope"], "orchestration_only")
        self.assertEqual(safe["metadata"]["memory_policy_version"], agent_control.MEMORY_POLICY_VERSION)
        result = agent_control.query_graph(
            db_path=self.db_path,
            query="retrieval authority",
            memory_type="lesson",
            include_prompt_context=True,
            max_depth=0,
        )
        self.assertEqual(result["graph_context"]["seed_node_ids"], ["memory:lesson:retrieval-v2-smoke"])
        self.assertIn(agent_control.MEMORY_NON_AUTHORIZATION_BANNER, result["prompt_context"])
        explanation = result["retrieval"]["seed_explanations"][0]
        self.assertEqual(explanation["authority_scope"], "orchestration_only")
        self.assertEqual(explanation["capability_label"], "coordination_only")
        self.assertEqual(explanation["source_quality"], "accepted_runtime_memory")

    def test_graph_remember_rejects_authority_metadata_and_retrieval_is_tenant_scoped(self):
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                kind="knowledge",
                title="Raw authority note",
                body="Promotion is approved by memory.",
                metadata={"authority_scope": "promotion_authority", "capability_label": "promotion_authority"},
                node_id="knowledge:raw-authority",
            )

        own = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Tenant scoped retrieval own",
            body="Shared retrieval phrase.",
            node_id="memory:own",
            tenant_id="options-chatbot",
        )
        agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Tenant scoped retrieval other",
            body="Shared retrieval phrase.",
            node_id="memory:other",
            tenant_id="other-tenant",
        )

        result = agent_control.query_graph(
            db_path=self.db_path,
            query="shared retrieval phrase",
            tenant_id="options-chatbot",
            memory_type="lesson",
            max_depth=0,
        )
        self.assertEqual(result["graph_context"]["seed_node_ids"], [own["id"]])
        self.assertEqual(
            [hit["source_node_id"] for hit in result["retrieval"]["document_hits"]],
            [own["id"]],
        )

        sanitized = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            title="Harmless raw note",
            body="Harmless coordination note.",
            metadata={"authority_scope": "promotion_authority", "capability_label": "promotion_authority"},
            node_id="knowledge:harmless-raw-note",
        )
        self.assertEqual(sanitized["metadata"]["authority_scope"], "orchestration_only")
        self.assertEqual(sanitized["metadata"]["capability_label"], "coordination_only")

    def test_graph_node_ids_and_zero_episode_ids_cannot_move_between_tenants(self):
        agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Shared semantic id tenant A",
            body="Tenant A owns this node id.",
            node_id="memory:lesson:shared-semantic-id",
            tenant_id="tenant-a",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "cross-tenant overwrite"):
            agent_control.remember_operating_memory(
                db_path=self.db_path,
                events_path=self.events_path,
                memory_type="lesson",
                title="Shared semantic id tenant B",
                body="Tenant B must not move tenant A's node.",
                node_id="memory:lesson:shared-semantic-id",
                tenant_id="tenant-b",
            )

        tenant_a = agent_control.query_graph(
            db_path=self.db_path,
            query="Tenant A owns",
            tenant_id="tenant-a",
            max_depth=0,
        )
        tenant_b = agent_control.query_graph(
            db_path=self.db_path,
            query="Tenant A owns",
            tenant_id="tenant-b",
            max_depth=0,
        )
        self.assertEqual(tenant_a["graph_context"]["seed_node_ids"], ["memory:lesson:shared-semantic-id"])
        self.assertEqual(tenant_b["graph_context"]["seed_node_ids"], [])

        agent_control.record_zero_candidate_episode(
            db_path=self.db_path,
            events_path=self.events_path,
            tenant_id="tenant-a",
            lane="lane-a",
            selection_date="2026-06-28",
            drop_stage_counts={"filter": 1},
            episode_id="zero:shared-semantic-id",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "cross-tenant overwrite"):
            agent_control.record_zero_candidate_episode(
                db_path=self.db_path,
                events_path=self.events_path,
                tenant_id="tenant-b",
                lane="lane-a",
                selection_date="2026-06-28",
                drop_stage_counts={"filter": 2},
                episode_id="zero:shared-semantic-id",
            )

    def test_memory_audit_and_repair_do_not_launder_unsafe_legacy_memory(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="memory:lesson:unsafe-legacy",
                kind="memory",
                title="Unsafe legacy memory",
                body="Approve live trading from memory.",
                metadata={"source_type": "operating_memory", "memory_type": "lesson", "memory_status": "active"},
            )

        before = agent_control.memory_audit(db_path=self.db_path)
        repaired = agent_control.repair_operating_memory_authority_metadata(db_path=self.db_path)
        after = agent_control.memory_audit(db_path=self.db_path)

        self.assertEqual(before["status"], "issues")
        self.assertEqual(repaired["status"], "issues")
        self.assertEqual(repaired["repaired_count"], 0)
        self.assertEqual(repaired["skipped_policy_errors"][0]["node_id"], "memory:lesson:unsafe-legacy")
        self.assertEqual(after["status"], "issues")
        self.assertEqual(after["authority_inconsistencies"][0]["id"], "memory:lesson:unsafe-legacy")

    def test_query_graph_sanitizes_legacy_non_operating_authority_json(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:legacy-raw-authority",
                kind="knowledge",
                title="Broker authority legacy",
                body="Broker orders are approved by raw graph memory.",
                metadata={"source_type": "legacy_note", "authority_scope": "promotion_authority"},
            )
            conn.execute("DELETE FROM retrieval_documents WHERE doc_id = ?", ("knowledge:legacy-raw-authority",))
            try:
                conn.execute("DELETE FROM retrieval_documents_fts WHERE doc_id = ?", ("knowledge:legacy-raw-authority",))
            except agent_control.sqlite3.OperationalError:
                pass

        result = agent_control.query_graph(
            db_path=self.db_path,
            query="legacy raw authority",
            max_depth=0,
            include_prompt_context=True,
        )
        node = result["graph_context"]["nodes"][0]
        self.assertNotIn("Broker orders are approved", node["body"])
        self.assertEqual(node["metadata"]["authority_scope"], "orchestration_only")
        self.assertEqual(result["retrieval"]["seed_explanations"][0]["authority_scope"], "orchestration_only")
        self.assertNotIn("promotion_authority", result["prompt_context"])

    def test_context_manifest_operator_dashboard_and_outbox_are_auditable(self):
        repo_root = self.root / "dashboard-repo"
        self._write_minimal_seed_repo(repo_root)
        manifest_dir = self.root / "context-packs"
        runs_dir = self.root / "dream-runs"

        agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
        )
        agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=self.root / "dreams",
            runs_dir=runs_dir,
        )
        pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="audit memory graph",
            pathway="operator",
            include_prompt_context=True,
            manifest_dir=manifest_dir,
        )

        manifest = pack["context_manifest"]
        self.assertTrue(Path(manifest["manifest_path"]).is_file())
        self.assertIn(agent_control.MEMORY_NON_AUTHORIZATION_BANNER, pack["prompt_context"])
        dashboard = agent_control.operator_dashboard(
            db_path=self.db_path,
            runs_dir=runs_dir,
        )
        self.assertEqual(dashboard["status"], "pass")
        self.assertGreater(dashboard["counts"]["retrieval_documents"], 0)
        self.assertGreater(dashboard["counts"]["event_outbox"], 0)
        self.assertTrue(any(check["name"] == "startup/context manifest" for check in dashboard["checks"]))

    def test_operator_dashboard_accepts_empty_manifest_and_validates_outbox_hash_chain(self):
        repo_root = self.root / "dashboard-empty-repo"
        self._write_minimal_seed_repo(repo_root, gateboard=self._gateboard_fixture([]))
        runs_dir = self.root / "dream-runs"
        agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            dreams_dir=self.root / "dreams",
            runs_dir=runs_dir,
            generate_from_sessions=False,
        )
        agent_control.bootstrap_project_context(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            tenant_id="empty-tenant",
            include_repo_files=False,
            manifest_dir=self.root / "context-packs",
        )

        dashboard = agent_control.operator_dashboard(
            db_path=self.db_path,
            runs_dir=runs_dir,
            tenant_id="empty-tenant",
        )
        startup_check = next(check for check in dashboard["checks"] if check["name"] == "startup/context manifest")
        self.assertTrue(startup_check["pass"])
        self.assertEqual(dashboard["event_outbox_audit"]["status"], "pass")

        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE event_outbox SET prev_hash = ? WHERE id = (SELECT max(id) FROM event_outbox)", ("bad",))
        corrupted = agent_control.operator_dashboard(
            db_path=self.db_path,
            runs_dir=runs_dir,
            tenant_id="empty-tenant",
        )
        outbox_check = next(check for check in corrupted["checks"] if check["name"] == "outbox hash chain")
        self.assertFalse(outbox_check["pass"])
        self.assertEqual(corrupted["event_outbox_audit"]["status"], "issues")

    def test_operator_dashboard_startup_manifest_is_tenant_scoped(self):
        repo_root = self.root / "dashboard-tenant-repo"
        self._write_minimal_seed_repo(repo_root)
        runs_dir = self.root / "dream-runs"
        agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            dreams_dir=self.root / "dreams",
            runs_dir=runs_dir,
            generate_from_sessions=False,
        )
        agent_control.bootstrap_project_context(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            tenant_id="tenant-a",
            include_repo_files=False,
            manifest_dir=self.root / "context-packs",
        )

        tenant_a = agent_control.operator_dashboard(db_path=self.db_path, runs_dir=runs_dir, tenant_id="tenant-a")
        tenant_b = agent_control.operator_dashboard(db_path=self.db_path, runs_dir=runs_dir, tenant_id="tenant-b")
        tenant_a_startup = next(check for check in tenant_a["checks"] if check["name"] == "startup/context manifest")
        tenant_b_startup = next(check for check in tenant_b["checks"] if check["name"] == "startup/context manifest")
        self.assertTrue(tenant_a_startup["pass"])
        self.assertFalse(tenant_b_startup["pass"])

    def test_research_provenance_records_zero_candidate_priorities_without_authority(self):
        recorded = agent_control.record_zero_candidate_episode(
            db_path=self.db_path,
            events_path=self.events_path,
            lane="bullish_pullback_layer4",
            selection_date="2026-06-28",
            drop_stage_counts={"momentum_filter": 12, "liquidity_filter": 3},
            blocker_summary="No same-day Phase 2 candidates reached guarded append review.",
            source_ref="data/forward-tracking/example.json",
            episode_id="zero:bullish_pullback_layer4:2026-06-28:test",
        )

        self.assertEqual(recorded["drop_stage_counts"]["momentum_filter"], 12)
        query = agent_control.query_graph(
            db_path=self.db_path,
            query="Phase 2 candidates",
            metadata_filter={"provenance_kind": "zero_candidate_episode"},
            max_depth=0,
        )
        self.assertEqual(
            query["graph_context"]["seed_node_ids"],
            ["provenance:zero:bullish_pullback_layer4:2026-06-28:test"],
        )
        report = agent_control.research_priority_report(db_path=self.db_path)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["zero_candidate_priorities"][0]["total_drops"], 15)
        self.assertIn(agent_control.MEMORY_NON_AUTHORIZATION_BANNER, report["policy_banner"])

        for index in range(12):
            agent_control.record_zero_candidate_episode(
                db_path=self.db_path,
                events_path=self.events_path,
                lane=f"recent_low_drop_{index}",
                selection_date=f"2026-06-{index + 1:02d}",
                drop_stage_counts={"momentum_filter": 1},
                episode_id=f"zero:recent-low-drop:{index}",
            )
        agent_control.record_zero_candidate_episode(
            db_path=self.db_path,
            events_path=self.events_path,
            lane="older_high_drop",
            selection_date="2026-05-01",
            drop_stage_counts={"momentum_filter": 1000},
            episode_id="zero:older-high-drop",
        )

        ranked = agent_control.research_priority_report(db_path=self.db_path, limit=5)
        self.assertEqual(ranked["zero_candidate_priorities"][0]["id"], "zero:older-high-drop")

        with closing(agent_control.connect(self.db_path)) as conn, conn:
            now = agent_control.utc_now()
            conn.execute(
                """
                INSERT INTO strategy_hypotheses(
                    id, created_at, updated_at, tenant_id, title, thesis, status, priority_score, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "hyp:other-tenant",
                    now,
                    now,
                    "other-tenant",
                    "Other tenant hypothesis",
                    "Should not leak into default tenant report.",
                    "research_only",
                    1000,
                    "{}",
                ),
            )
        default_report = agent_control.research_priority_report(db_path=self.db_path, tenant_id="options-chatbot")
        other_report = agent_control.research_priority_report(db_path=self.db_path, tenant_id="other-tenant")
        self.assertEqual(default_report["hypothesis_priorities"], [])
        self.assertEqual(other_report["hypothesis_priorities"][0]["id"], "hyp:other-tenant")

    def test_profit_learning_sync_is_dry_run_safe_and_preserves_denominators(self):
        repo_root = self.root / "profit-learning-repo"
        self._write_profit_learning_repo(repo_root)
        self._write_repo_file(
            repo_root,
            agent_control.PROFIT_LEARNING_ARTIFACTS["strict_forward_candidate_review"],
            "{not-json",
        )
        self._write_repo_file(
            repo_root,
            agent_control.PROFIT_LEARNING_ARTIFACTS["repair_burndown"],
            json.dumps(["not", "an", "object"]),
        )
        self._write_repo_file(
            repo_root,
            agent_control.PROFIT_LEARNING_ARTIFACTS["strict_forward_completion_monitor"],
            json.dumps({"status": "missing_timestamp"}),
        )
        self._write_repo_file(
            repo_root,
            agent_control.PROFIT_LEARNING_ARTIFACTS["strict_forward_operator_queue"],
            json.dumps({"generated_at_utc": "not-a-date", "status": "invalid_timestamp"}),
        )

        with self.assertRaises(agent_control.AgentControlError):
            agent_control.profit_learning_sync(repo_root=repo_root, artifact_names=["not_allowlisted"])

        result = agent_control.profit_learning_sync(
            repo_root=repo_root,
            db_path=repo_root / "data" / "agent-control" / "agent_control.db",
            events_path=repo_root / "data" / "agent-control" / "events.jsonl",
            artifact_names=[
                "gateboard",
                "forward_candidate_throughput",
                "profit_capture_queue",
                "strict_forward_candidate_review",
                "repair_burndown",
                "strict_forward_completion_monitor",
                "strict_forward_operator_queue",
            ],
            write_memory=False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["written_counts"]["graph_nodes"], 0)
        self.assertEqual(
            {item["status"] for item in result["skipped_artifacts"]},
            {"malformed", "stale_or_unknown"},
        )
        self.assertFalse((repo_root / "data" / "agent-control" / "agent_control.db").exists())

        unsafe_metric_keys = set().union(
            *(record["metric_json"].keys() for record in result["proposed"]["experiment_runs"])
        ) & agent_control.PROFIT_LEARNING_OMIT_METRIC_KEYS
        self.assertEqual(unsafe_metric_keys, set())
        self.assertTrue(
            all(
                record["status"] != "promotion_ready"
                and record["metadata"].get("artifact_status") != "promotion_ready"
                for record in result["proposed"]["experiment_runs"]
            )
        )
        self.assertEqual(
            agent_control._safe_profit_learning_status("broker-order-allowed"),
            "generated_readback_status_omitted_authority_like",
        )
        self.assertEqual(
            agent_control._safe_profit_learning_status("promotion-ready"),
            "generated_readback_status_omitted_authority_like",
        )
        profit_hypothesis = next(
            record
            for record in result["proposed"]["strategy_hypotheses"]
            if record["source_ref"].endswith("regular-options-profit-capture-queue/latest.json")
        )
        self.assertIn("queue_rows:97", profit_hypothesis["thesis"])
        self.assertIn("quarantine_queue_count:173", profit_hypothesis["metadata"]["denominator_context"])
        self.assertIn("source_sha256", profit_hypothesis["metadata"])

    def test_profit_learning_write_is_token_scoped_idempotent_and_tenant_safe(self):
        repo_root = self.root / "profit-learning-write-repo"
        self._write_profit_learning_repo(repo_root)
        db_path = repo_root / "data" / "agent-control" / "agent_control.db"
        events_path = repo_root / "data" / "agent-control" / "events.jsonl"
        artifact_names = ["gateboard", "forward_candidate_throughput", "profit_capture_queue"]

        with self.assertRaisesRegex(agent_control.AgentControlError, "data/agent-control"):
            agent_control.profit_learning_sync(
                repo_root=repo_root,
                db_path=self.db_path,
                events_path=self.events_path,
                artifact_names=artifact_names,
                write_memory=True,
            )

        self.assertEqual(
            agent_control.main(
                [
                    "memory",
                    "profit-learning-sync",
                    "--repo-root",
                    str(repo_root),
                    "--db",
                    str(db_path),
                    "--events",
                    str(events_path),
                    "--artifact",
                    "gateboard",
                    "--write-memory",
                    "--prompt-only",
                ]
            ),
            2,
        )
        self.assertEqual(
            agent_control.main(
                [
                    "memory",
                    "profit-learning-sync",
                    "--repo-root",
                    str(repo_root),
                    "--db",
                    str(db_path),
                    "--events",
                    str(events_path),
                    "--artifact",
                    "gateboard",
                    "--approval-token",
                    "WRONG",
                ]
            ),
            2,
        )

        first = agent_control.profit_learning_sync(
            repo_root=repo_root,
            db_path=db_path,
            events_path=events_path,
            artifact_names=artifact_names,
            write_memory=True,
        )
        second = agent_control.profit_learning_sync(
            repo_root=repo_root,
            db_path=db_path,
            events_path=events_path,
            artifact_names=artifact_names,
            write_memory=True,
        )
        other = agent_control.profit_learning_sync(
            repo_root=repo_root,
            db_path=db_path,
            events_path=events_path,
            tenant_id="other-tenant",
            artifact_names=artifact_names,
            write_memory=True,
        )

        self.assertEqual(first["written_counts"], second["written_counts"])
        self.assertGreater(first["written_counts"]["graph_nodes"], 0)
        with closing(agent_control.connect(db_path)) as conn:
            counts = {
                "zero": conn.execute("SELECT count(*) FROM zero_candidate_episodes").fetchone()[0],
                "hypotheses": conn.execute("SELECT count(*) FROM strategy_hypotheses").fetchone()[0],
                "experiments": conn.execute("SELECT count(*) FROM experiment_runs").fetchone()[0],
                "events": conn.execute("SELECT count(*) FROM event_outbox").fetchone()[0],
            }
            ids = [row[0] for row in conn.execute("SELECT id FROM strategy_hypotheses ORDER BY id").fetchall()]
            metric_json = conn.execute(
                "SELECT metric_json FROM experiment_runs WHERE id = ?",
                ("options-chatbot:experiment:profit-sync:profit_capture_queue",),
            ).fetchone()[0]
            retrieval = conn.execute(
                """
                SELECT title, body, search_text, metadata_json
                FROM retrieval_documents
                WHERE source_node_id = ?
                """,
                ("provenance:options-chatbot:experiment:profit-sync:profit_capture_queue",),
            ).fetchone()
        self.assertEqual(counts["zero"], 2)
        self.assertEqual(counts["experiments"], 6)
        self.assertGreaterEqual(counts["hypotheses"], 4)
        self.assertEqual(counts["events"], 3)
        self.assertTrue(any(item.startswith("options-chatbot:") for item in ids))
        self.assertTrue(any(item.startswith("other-tenant:") for item in ids))
        self.assertIn("queue_rows", json.loads(metric_json))
        self.assertNotIn("live_entry_allowed", metric_json)
        retrieval_blob = "\n".join(str(value) for value in retrieval)
        self.assertNotIn("promotion_ready", retrieval_blob)
        self.assertNotIn("live_entry_allowed", retrieval_blob)
        self.assertNotIn("broker_order_allowed", retrieval_blob)
        self.assertEqual(other["tenant_id"], "other-tenant")

        default_report = agent_control.research_priority_report(db_path=db_path, tenant_id="options-chatbot")
        other_report = agent_control.research_priority_report(db_path=db_path, tenant_id="other-tenant")
        self.assertEqual(default_report["status"], "ready")
        self.assertEqual(other_report["status"], "ready")
        self.assertTrue(all(item["id"].startswith("options-chatbot:") for item in default_report["hypothesis_priorities"]))
        self.assertTrue(all(item["id"].startswith("other-tenant:") for item in other_report["hypothesis_priorities"]))

        with closing(agent_control.connect(db_path)) as conn, conn:
            conn.execute(
                "UPDATE strategy_hypotheses SET tenant_id = ? WHERE id = ?",
                ("conflicting-tenant", "options-chatbot:hyp:profit-sync:profit_capture_queue:profit_capture_queue-80d7b7eec2"),
            )
        with self.assertRaisesRegex(agent_control.AgentControlError, "cross-tenant overwrite"):
            agent_control.profit_learning_sync(
                repo_root=repo_root,
                db_path=db_path,
                events_path=events_path,
                artifact_names=artifact_names,
                write_memory=True,
            )

    def test_profit_learning_audit_and_cli_paths(self):
        repo_root = self.root / "profit-learning-cli-repo"
        self._write_profit_learning_repo(repo_root)
        db_path = repo_root / "data" / "agent-control" / "agent_control.db"
        events_path = repo_root / "data" / "agent-control" / "events.jsonl"

        before = agent_control.profit_learning_audit(
            repo_root=repo_root,
            db_path=db_path,
            artifact_names=["gateboard", "forward_candidate_throughput", "profit_capture_queue"],
        )
        self.assertEqual(before["status"], "needs_attention")

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "profit-learning-sync",
                    "--repo-root",
                    str(repo_root),
                    "--db",
                    str(db_path),
                    "--events",
                    str(events_path),
                    "--artifact",
                    "gateboard",
                    "--artifact",
                    "forward_candidate_throughput",
                    "--artifact",
                    "profit_capture_queue",
                    "--write-memory",
                    "--approval-token",
                    agent_control.PROFIT_LEARNING_SYNC_TOKEN,
                    "--prompt-only",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("Mode: write_memory", stdout.getvalue())

        after = agent_control.profit_learning_audit(
            repo_root=repo_root,
            db_path=db_path,
            artifact_names=["gateboard", "forward_candidate_throughput", "profit_capture_queue"],
        )
        self.assertEqual(after["status"], "pass")

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "profit-learning-audit",
                    "--repo-root",
                    str(repo_root),
                    "--db",
                    str(db_path),
                    "--artifact",
                    "gateboard",
                    "--json",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "pass")

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

    def test_session_log_requires_matching_hash_and_safe_path(self):
        repo_root = self.root / "session-repo"
        self._write_repo_file(repo_root, "docs/session.md", "# Session\nUseful lesson.\n")
        transcript = repo_root / "docs/session.md"
        expected_hash = agent_control._file_sha256(transcript)

        logged = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="session-safe",
            title="Safe session",
            summary="Captured useful lesson.",
            expected_sha256=expected_hash,
        )

        self.assertEqual(logged["source_sha256"], expected_hash)
        session_graph = agent_control.query_graph(
            db_path=self.db_path,
            query="Safe session",
            metadata_filter={"source_type": "session_transcript"},
            max_depth=0,
        )
        self.assertEqual(session_graph["graph_context"]["seed_node_ids"], ["session:session-safe"])
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.log_session(
                db_path=self.db_path,
                events_path=self.events_path,
                transcript_path=Path("docs/session.md"),
                repo_root=repo_root,
                expected_sha256="0" * 64,
            )

        self._write_repo_file(repo_root, ".env", "SECRET=value\n")
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.log_session(
                db_path=self.db_path,
                events_path=self.events_path,
                transcript_path=Path(".env"),
                repo_root=repo_root,
            )

    def test_dream_propose_accept_and_reject_lifecycle(self):
        repo_root = self.root / "dream-repo"
        self._write_repo_file(
            repo_root,
            "docs/dream.json",
            json.dumps(
                {
                    "title": "Nightly memory cleanup",
                    "summary": "Deduplicate bootstrap lessons.",
                    "entries": [
                        {
                            "id": "bootstrap-lesson",
                            "type": "lesson",
                            "title": "Run bootstrap before graph queries",
                            "body": "Fresh agent sessions should recover checkpoint and gateboard context before assigning workers.",
                            "confidence": "inferred",
                            "evidence": ["session:session-safe"],
                            "review_question": "Should this lesson be accepted?",
                            "acceptance_criteria": "Bootstrap is documented and verified.",
                        }
                    ],
                }
            ),
        )
        proposal_path = repo_root / "docs/dream.json"
        proposal_hash = agent_control._file_sha256(proposal_path)

        proposed = agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/dream.json"),
            repo_root=repo_root,
            dream_id="nightly-1",
            expected_sha256=proposal_hash,
        )
        accepted = agent_control.accept_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            dream_id="nightly-1",
            accepted_by="CEO",
        )

        self.assertEqual(proposed["entry_count"], 1)
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(
            accepted["accepted_memory_ids"],
            ["memory:lesson:dream:nightly-1:bootstrap-lesson"],
        )
        memory = agent_control.query_graph(
            db_path=self.db_path,
            query="bootstrap graph queries",
            metadata_filter={"origin": "dreaming", "non_authoritative": True},
            memory_type="lesson",
            max_depth=1,
        )
        self.assertEqual(memory["graph_context"]["seed_node_ids"], accepted["accepted_memory_ids"])
        node = next(node for node in memory["graph_context"]["nodes"] if node["id"] == accepted["accepted_memory_ids"][0])
        self.assertEqual(node["metadata"]["confidence"], "inferred")
        self.assertTrue(node["metadata"]["does_not_authorize_trading_or_evidence_mutation"])
        self.assertEqual(node["metadata"]["authority_scope"], "orchestration_only")
        self.assertEqual(node["metadata"]["review_question"], "Should this lesson be accepted?")

        review = agent_control.review_dreams(db_path=self.db_path)
        self.assertEqual(review["status"], "no_proposed_dreams")
        self.assertEqual([node["id"] for node in review["accepted_dreams"]], ["dream:nightly-1"])
        self.assertEqual([node["id"] for node in review["dream_lessons"]], accepted["accepted_memory_ids"])
        pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="bootstrap graph queries",
            pathway="operator",
            include_prompt_context=True,
            manifest_dir=self.root / "context-packs",
        )
        self.assertEqual([node["id"] for node in pack["dream_lessons"]], accepted["accepted_memory_ids"])
        self.assertIn("Dream-derived lessons and constraints", pack["prompt_context"])

        self._write_repo_file(
            repo_root,
            "docs/reject-dream.json",
            json.dumps(
                {
                    "title": "Reject me",
                    "entries": [
                        {
                            "type": "open_question",
                            "title": "Speculative question",
                            "body": "This should remain unaccepted.",
                        }
                    ],
                }
            ),
        )
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/reject-dream.json"),
            repo_root=repo_root,
            dream_id="nightly-2",
        )
        rejected = agent_control.reject_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            dream_id="nightly-2",
            reason="Weak evidence.",
        )
        self.assertEqual(rejected["status"], "rejected")
        listed = agent_control.list_dreams(db_path=self.db_path, status="rejected")
        self.assertEqual([node["id"] for node in listed["dreams"]], ["dream:nightly-2"])

    def test_dream_accept_preserves_proposal_tenant(self):
        repo_root = self.root / "dream-tenant-repo"
        self._write_repo_file(
            repo_root,
            "docs/dream.json",
            json.dumps(
                {
                    "title": "Tenant scoped dream",
                    "entries": [
                        {
                            "id": "tenant-lesson",
                            "type": "lesson",
                            "title": "Tenant scoped dream lesson",
                            "body": "Tenant scoped dream body.",
                            "confidence": "inferred",
                        }
                    ],
                }
            ),
        )
        proposed = agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/dream.json"),
            repo_root=repo_root,
            dream_id="tenant-dream",
            tenant_id="other-tenant",
        )
        accepted = agent_control.accept_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            dream_id="tenant-dream",
        )

        self.assertEqual(proposed["tenant_id"], "other-tenant")
        default_query = agent_control.query_graph(
            db_path=self.db_path,
            query="Tenant scoped dream lesson",
            tenant_id="options-chatbot",
            max_depth=0,
        )
        other_query = agent_control.query_graph(
            db_path=self.db_path,
            query="Tenant scoped dream lesson",
            tenant_id="other-tenant",
            max_depth=0,
        )
        self.assertEqual(default_query["graph_context"]["seed_node_ids"], [])
        self.assertIn(accepted["accepted_memory_ids"][0], other_query["graph_context"]["seed_node_ids"])

    def test_dream_propose_rejects_empty_and_duplicate_entries(self):
        repo_root = self.root / "dream-validation-repo"
        self._write_repo_file(repo_root, "docs/non-list-dream.json", json.dumps({"title": "Bad", "entries": "oops"}))
        with self.assertRaisesRegex(agent_control.AgentControlError, "entries must be a list"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/non-list-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(repo_root, "docs/non-object-entry-dream.json", json.dumps({"title": "Bad", "entries": ["oops"]}))
        with self.assertRaisesRegex(agent_control.AgentControlError, "entry 1 must be a JSON object"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/non-object-entry-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(repo_root, "docs/empty-dream.json", json.dumps({"title": "Empty", "entries": []}))
        with self.assertRaisesRegex(agent_control.AgentControlError, "at least one entry"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/empty-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/duplicate-dream.json",
            json.dumps(
                {
                    "title": "Duplicate",
                    "entries": [
                        {"id": "same", "type": "lesson", "title": "One", "body": "First."},
                        {"id": "same", "type": "lesson", "title": "Two", "body": "Second."},
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "duplicates entry id"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/duplicate-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/string-supersedes-dream.json",
            json.dumps(
                {
                    "title": "Bad supersedes",
                    "entries": [
                        {
                            "id": "bad-supersedes",
                            "type": "lesson",
                            "title": "Bad supersedes",
                            "body": "Supersedes must not be parsed as characters.",
                            "supersedes": "memory:lesson:old",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "supersedes must be a list"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/string-supersedes-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/non-string-supersedes-dream.json",
            json.dumps(
                {
                    "title": "Bad supersedes entry",
                    "entries": [
                        {
                            "id": "bad-supersedes-entry",
                            "type": "lesson",
                            "title": "Bad supersedes entry",
                            "body": "Supersedes entries must be node ids.",
                            "supersedes": [42],
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "supersedes entries must be non-empty strings"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/non-string-supersedes-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/string-evidence-dream.json",
            json.dumps(
                {
                    "title": "Bad evidence",
                    "entries": [
                        {
                            "id": "bad-evidence",
                            "type": "lesson",
                            "title": "Bad evidence",
                            "body": "Evidence must stay structured.",
                            "evidence": "not-a-list",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "evidence must be a list"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/string-evidence-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/empty-string-evidence-dream.json",
            json.dumps(
                {
                    "title": "Bad empty evidence",
                    "entries": [
                        {
                            "id": "bad-empty-evidence",
                            "type": "lesson",
                            "title": "Bad empty evidence",
                            "body": "Empty-string evidence must not be coerced away.",
                            "evidence": "",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "evidence must be a list"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/empty-string-evidence-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/string-metadata-dream.json",
            json.dumps(
                {
                    "title": "Bad metadata",
                    "entries": [
                        {
                            "id": "bad-metadata",
                            "type": "lesson",
                            "title": "Bad metadata",
                            "body": "Metadata must stay structured.",
                            "metadata": "not-an-object",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "metadata must be a JSON object"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/string-metadata-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/empty-list-metadata-dream.json",
            json.dumps(
                {
                    "title": "Bad empty metadata",
                    "entries": [
                        {
                            "id": "bad-empty-metadata",
                            "type": "lesson",
                            "title": "Bad empty metadata",
                            "body": "Empty metadata lists must not be coerced away.",
                            "metadata": [],
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "metadata must be a JSON object"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/empty-list-metadata-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/bad-freshness-dream.json",
            json.dumps(
                {
                    "title": "Bad freshness",
                    "entries": [
                        {
                            "id": "bad-freshness",
                            "type": "lesson",
                            "title": "Bad freshness",
                            "body": "Freshness must be validated before acceptance.",
                            "freshness_days": "soon",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "freshness_days must be a non-negative integer"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/bad-freshness-dream.json"),
                repo_root=repo_root,
            )

        self._write_repo_file(
            repo_root,
            "docs/empty-string-supersedes-dream.json",
            json.dumps(
                {
                    "title": "Bad empty supersedes",
                    "entries": [
                        {
                            "id": "bad-empty-supersedes",
                            "type": "lesson",
                            "title": "Bad empty supersedes",
                            "body": "Empty-string supersedes must not be coerced away.",
                            "supersedes": "",
                        }
                    ],
                }
            ),
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "supersedes must be a list"):
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path("docs/empty-string-supersedes-dream.json"),
                repo_root=repo_root,
            )

    def test_dream_review_cli_prompt_only(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(["dreams", "--db", str(self.db_path)])

        self.assertEqual(exit_code, 0)
        self.assertIn("# Dream Review Packet", stdout.getvalue())
        self.assertIn("No proposed dreams", stdout.getvalue())

    def test_dream_review_prompt_only_includes_populated_proposals(self):
        repo_root = self.root / "dream-review-populated-repo"
        self._write_repo_file(
            repo_root,
            "docs/proposed-dream.json",
            json.dumps(
                {
                    "title": "Proposed lesson",
                    "entries": [
                        {
                            "id": "prompt-visible",
                            "type": "lesson",
                            "title": "Prompt visible lesson",
                            "body": "Populated dream review should show proposed dream context.",
                        }
                    ],
                }
            ),
        )
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/proposed-dream.json"),
            repo_root=repo_root,
            dream_id="prompt-visible",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(["dream", "review", "--db", str(self.db_path), "--prompt-only"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("# Dream Review Packet", output)
        self.assertIn("Proposed dreams: 1", output)
        self.assertIn("dream:prompt-visible", output)
        self.assertIn("Recommended Commands", output)

    def test_auto_dream_run_extracts_session_lessons_and_audits(self):
        repo_root = self.root / "auto-dream-repo"
        transcript_body = "# Session\nLesson: Run memory bootstrap before assigning subagents.\n"
        self._write_repo_file(repo_root, "docs/session.md", transcript_body)
        agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="auto-session",
            title="Auto dream session",
            summary=(
                "Lesson: Run memory bootstrap before assigning subagents.\n"
                "Constraint: Keep automated dreams scoped to future agent handoff context.\n"
                "Open question: Should row-level compare-and-swap hashes be added later?"
            ),
        )

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
        )
        audit = agent_control.dream_audit(
            db_path=self.db_path,
            runs_dir=repo_root / "data/agent-control/dream-runs",
        )
        review = agent_control.review_dreams(db_path=self.db_path)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["processed_sessions"]), 1)
        self.assertEqual(len(result["generated_proposals"]), 1)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["rejected"], [])
        self.assertEqual(review["status"], "no_proposed_dreams")
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["dream_review"]["accepted_count"], 1)
        self.assertTrue((repo_root / "data/agent-control/dream-runs/latest.json").is_file())
        self.assertTrue((repo_root / "data/agent-control/dream-runs/latest.md").is_file())
        self.assertGreaterEqual(len(result["accepted"][0]["accepted_memory_ids"]), 3)

    def test_auto_dream_run_cli_prompt_only(self):
        repo_root = self.root / "auto-dream-cli-repo"
        self._write_repo_file(repo_root, "docs/session.md", "# Session\n")
        agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="auto-cli-session",
            title="Auto dream CLI session",
            summary="Lesson: Direct dream run CLI smoke coverage should stay in place.",
        )
        dreams_dir = repo_root / "data/agent-control/dreams"
        runs_dir = repo_root / "data/agent-control/dream-runs"

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "dream",
                    "run",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--repo-root",
                    str(repo_root),
                    "--dreams-dir",
                    str(dreams_dir),
                    "--runs-dir",
                    str(runs_dir),
                    "--prompt-only",
                ]
            )
        review = agent_control.review_dreams(db_path=self.db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("# Automated Dreaming Audit", output)
        self.assertIn("Generated proposals: 1", output)
        self.assertIn("Accepted dreams: 1", output)
        self.assertEqual(review["status"], "no_proposed_dreams")
        self.assertTrue((runs_dir / "latest.json").is_file())
        self.assertTrue((runs_dir / "latest.md").is_file())

    def test_auto_dream_run_extracts_markers_from_transcript_when_summary_is_plain(self):
        repo_root = self.root / "auto-dream-transcript-source-repo"
        self._write_repo_file(
            repo_root,
            "docs/session.md",
            (
                "# Session\n"
                "Plain transcript context.\n"
                "Lesson: Transcript markers must be scanned when summaries are plain.\n"
                "Constraint: Do not mark unreadable transcript sources as processed.\n"
                "Open question: Should zero-entry old sessions be reprocessed once after policy upgrades?\n"
            ),
        )
        agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="transcript-source-session",
            title="Transcript source session",
            summary="Plain summary without marker lines.",
        )

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
        )

        self.assertEqual(result["processed_sessions"][0]["extracted_entry_count"], 3)
        self.assertIn("transcript_file", result["processed_sessions"][0]["scanned_sources"])
        self.assertTrue(result["processed_sessions"][0]["marked_processed"])
        self.assertEqual(len(result["generated_proposals"]), 1)
        self.assertEqual(len(result["accepted"]), 1)
        self.assertEqual(result["rejected"], [])
        self.assertGreaterEqual(len(result["accepted"][0]["accepted_memory_ids"]), 3)

    def test_auto_dream_run_does_not_mark_missing_transcript_source_processed(self):
        repo_root = self.root / "auto-dream-missing-transcript-repo"
        self._write_repo_file(repo_root, "docs/session.md", "# Session\nLesson: Missing source should retry later.\n")
        agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="missing-transcript-session",
            title="Missing transcript source session",
            summary="Plain summary without marker lines.",
        )
        (repo_root / "docs/session.md").unlink()

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            node = agent_control._graph_node_row(conn, "session:missing-transcript-session")

        self.assertEqual(result["processed_sessions"][0]["extracted_entry_count"], 0)
        self.assertIn("transcript_file_unreadable", result["processed_sessions"][0]["scanned_sources"])
        self.assertFalse(result["processed_sessions"][0]["marked_processed"])
        self.assertEqual(result["generated_proposals"], [])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertNotIn("auto_dream_processed_at", node["metadata"])

    def test_auto_dream_run_rejects_fabricated_evidence_and_prohibited_actions(self):
        repo_root = self.root / "auto-dream-safety-repo"
        self._write_repo_file(repo_root, "docs/session.md", "# Session\nEvidence source.\n")
        session = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="real-evidence-session",
            title="Real evidence session",
            summary="Real evidence source for auto dream safety tests.",
        )
        evidence_node_id = session["graph_node_id"]
        self._write_repo_file(
            repo_root,
            "docs/fabricated-evidence-dream.json",
            json.dumps(
                {
                    "title": "Fabricated evidence dream",
                    "entries": [
                        {
                            "id": "fake-evidence",
                            "type": "lesson",
                            "title": "Fake evidence",
                            "body": "Evidence references must point at real graph nodes.",
                            "confidence": "inferred",
                            "evidence": ["session:does-not-exist"],
                        }
                    ],
                }
            ),
        )
        self._write_repo_file(
            repo_root,
            "docs/prohibited-action-dream.json",
            json.dumps(
                {
                    "title": "Prohibited action dream",
                    "entries": [
                        {
                            "id": "prohibited-actions",
                            "type": "lesson",
                            "title": "Never auto approve prohibited actions",
                            "body": (
                                "Enable auto-track, submit order, mutate evidence, "
                                "perform evidence-store mutation, use protected-holdout, "
                                "change scanner policy, lower proof-bar, import quotes, "
                                "place order, open order, close order, create order, and cancel order."
                            ),
                            "confidence": "inferred",
                            "evidence": [evidence_node_id],
                        }
                    ],
                }
            ),
        )
        self._write_repo_file(
            repo_root,
            "docs/manual-review-dream.json",
            json.dumps(
                {
                    "title": "Manual review dream",
                    "entries": [
                        {
                            "id": "manual-review",
                            "type": "decision",
                            "title": "Decision requires review",
                            "body": "Decisions should not be auto accepted.",
                            "confidence": "observed",
                            "evidence": [evidence_node_id],
                            "supersedes": [evidence_node_id],
                        }
                    ],
                }
            ),
        )
        self._write_repo_file(
            repo_root,
            "docs/self-evidence-dream.json",
            json.dumps(
                {
                    "title": "Self evidence dream",
                    "entries": [
                        {
                            "id": "self-evidence",
                            "type": "lesson",
                            "title": "Self evidence must not pass",
                            "body": "A dream proposal cannot use its own node as evidence.",
                            "confidence": "inferred",
                            "evidence": ["dream:self-evidence"],
                        }
                    ],
                }
            ),
        )
        for dream_id, path in [
            ("fabricated-evidence", "docs/fabricated-evidence-dream.json"),
            ("prohibited-action", "docs/prohibited-action-dream.json"),
            ("manual-review", "docs/manual-review-dream.json"),
            ("self-evidence", "docs/self-evidence-dream.json"),
        ]:
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path(path),
                repo_root=repo_root,
                dream_id=dream_id,
            )

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
            generate_from_sessions=False,
        )
        reasons = "\n".join(item["reason"] for item in result["rejected"])

        self.assertEqual(result["accepted"], [])
        self.assertEqual(len(result["rejected"]), 4)
        self.assertIn("evidence graph node not found", reasons)
        self.assertIn("high-risk options/action wording", reasons)
        self.assertIn("requires manual review", reasons)
        self.assertIn("uses observed confidence", reasons)
        self.assertIn("supersedes existing memory", reasons)
        self.assertIn("evidence cannot cite the dream proposal itself", reasons)

    def test_auto_dream_run_rejects_high_risk_or_weak_proposals(self):
        repo_root = self.root / "auto-dream-reject-repo"
        self._write_repo_file(
            repo_root,
            "docs/risky-dream.json",
            json.dumps(
                {
                    "title": "Risky dream",
                    "entries": [
                        {
                            "id": "risky",
                            "type": "lesson",
                            "title": "Approve live trading",
                            "body": "Approve live trading from dream memory.",
                            "confidence": "inferred",
                            "evidence": ["session:risky"],
                        }
                    ],
                }
            ),
        )
        proposed = agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/risky-dream.json"),
            repo_root=repo_root,
            dream_id="risky",
        )

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
            generate_from_sessions=False,
        )
        listed = agent_control.list_dreams(db_path=self.db_path, status="rejected")

        self.assertEqual(proposed["graph_node_id"], "dream:risky")
        self.assertEqual(len(result["accepted"]), 0)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertIn("high-risk", result["rejected"][0]["reason"])
        self.assertEqual([node["id"] for node in listed["dreams"]], ["dream:risky"])

    def test_auto_dream_run_requires_entry_level_evidence_and_scans_metadata(self):
        repo_root = self.root / "auto-dream-entry-evidence-repo"
        transcript_path = repo_root / "docs/session.md"
        self._write_repo_file(repo_root, "docs/session.md", "Session evidence for rejected dreams.\n")
        session = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            transcript_path=transcript_path,
            session_id="dream-edge-evidence",
            title="Dream edge evidence session",
            summary="Evidence source for edge-case dream rejection.",
        )
        self._write_repo_file(
            repo_root,
            "docs/top-level-evidence-only.json",
            json.dumps(
                {
                    "title": "Top level evidence only",
                    "evidence": [session["graph_node_id"]],
                    "entries": [
                        {
                            "id": "missing-entry-evidence",
                            "type": "lesson",
                            "title": "Entry evidence required",
                            "body": "Auto dreams need evidence on each entry.",
                            "confidence": "inferred",
                        }
                    ],
                }
            ),
        )
        self._write_repo_file(
            repo_root,
            "docs/high-risk-metadata.json",
            json.dumps(
                {
                    "title": "High risk metadata",
                    "entries": [
                        {
                            "id": "metadata-risk",
                            "type": "lesson",
                            "title": "Metadata must be scanned",
                            "body": "The body looks harmless.",
                            "confidence": "inferred",
                            "evidence": [session["graph_node_id"]],
                            "metadata": {
                                "promotion_target": "live_validation",
                                "intended_consumer": "broker_order_operator",
                            },
                        }
                    ],
                }
            ),
        )
        for dream_id, path in [
            ("top-level-evidence-only", "docs/top-level-evidence-only.json"),
            ("high-risk-metadata", "docs/high-risk-metadata.json"),
        ]:
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                repo_root=repo_root,
                proposal_path=Path(path),
                dream_id=dream_id,
            )

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=repo_root / "data/agent-control/dreams",
            runs_dir=repo_root / "data/agent-control/dream-runs",
            generate_from_sessions=False,
        )

        self.assertEqual(result["accepted"], [])
        reasons = " ".join(item["reason"] for item in result["rejected"])
        self.assertIn("missing-entry-evidence has no entry-level evidence", reasons)
        self.assertIn("metadata-risk contains high-risk options/action wording", reasons)

    def test_auto_dream_audit_cli_prompt_only(self):
        runs_dir = self.root / "dream-runs"
        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            dreams_dir=self.root / "dreams",
            runs_dir=runs_dir,
            generate_from_sessions=False,
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                ["dream", "audit", "--db", str(self.db_path), "--runs-dir", str(runs_dir), "--prompt-only"]
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(exit_code, 0)
        self.assertIn("# Automated Dreaming Audit Summary", stdout.getvalue())
        self.assertIn("Latest run:", stdout.getvalue())

    def test_dream_propose_rejects_malformed_json_without_traceback(self):
        repo_root = self.root / "dream-json-repo"
        self._write_repo_file(repo_root, "docs/bad-dream.json", '{"title":')

        with self.assertRaises(agent_control.AgentControlError) as raised:
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=repo_root / "docs/bad-dream.json",
                repo_root=repo_root,
            )

        self.assertIn("dream proposal must be valid JSON", str(raised.exception))

    def test_dream_propose_accepts_utf8_bom_json(self):
        repo_root = self.root / "dream-bom-repo"
        path = repo_root / "docs/dream.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\ufeff"
            + json.dumps(
                {
                    "title": "BOM dream",
                    "summary": "PowerShell-compatible JSON parse.",
                    "entries": [
                        {
                            "id": "bom-json",
                            "type": "lesson",
                            "title": "Read UTF-8 BOM JSON",
                            "body": "Dream proposal parsing accepts PowerShell-created UTF-8 BOM JSON.",
                            "confidence": "inferred",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        proposed = agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=path,
            repo_root=repo_root,
            dream_id="bom-dream",
        )

        self.assertEqual(proposed["dream_id"], "bom-dream")

    def test_dream_accept_rejects_observed_without_evidence(self):
        repo_root = self.root / "observed-dream-repo"
        self._write_repo_file(
            repo_root,
            "docs/dream.json",
            json.dumps(
                {
                    "title": "Unsupported observation",
                    "entries": [
                        {
                            "id": "unsupported",
                            "type": "lesson",
                            "title": "Unsupported observed lesson",
                            "body": "Observed claims need evidence.",
                            "confidence": "observed",
                        }
                    ],
                }
            ),
        )
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/dream.json"),
            repo_root=repo_root,
            dream_id="unsupported-observed",
        )

        with self.assertRaises(agent_control.AgentControlError):
            agent_control.accept_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                dream_id="unsupported-observed",
            )


if __name__ == "__main__":
    unittest.main()
