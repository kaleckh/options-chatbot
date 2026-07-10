import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
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

    def _claim_for_report(self, task_id: str, worker_id: str) -> None:
        agent_control.claim_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task_id,
            worker_id=worker_id,
        )

    def test_connect_skips_schema_ddl_when_schema_version_is_current(self):
        first = agent_control.connect(self.db_path)
        first.close()

        with mock.patch.object(agent_control, "init_schema", wraps=agent_control.init_schema) as init_schema:
            second = agent_control.connect(self.db_path)
            try:
                timeout = second.execute("PRAGMA busy_timeout").fetchone()[0]
            finally:
                second.close()

        self.assertEqual(timeout, 30000)
        init_schema.assert_not_called()

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

    def test_agent_run_ledger_is_append_only_without_maintenance_connection(self):
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-append-only",
            event_type="started",
            summary="append-only target",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            migration = conn.execute(
                "SELECT version FROM schema_migrations WHERE version = ?",
                (agent_control.CONTROL_SCHEMA_VERSION,),
            ).fetchone()
            self.assertIsNotNone(migration)
            with self.assertRaises(sqlite3.DatabaseError):
                with conn:
                    conn.execute(
                        "UPDATE agent_run_events SET summary = ? WHERE id = ?",
                        ("mutated", event["id"]),
                    )
            with self.assertRaises(sqlite3.DatabaseError):
                with conn:
                    conn.execute("DELETE FROM agent_run_events WHERE id = ?", (event["id"],))

        with closing(agent_control.connect(self.db_path, maintenance=True)) as conn:
            with conn:
                conn.execute(
                    "UPDATE agent_run_events SET summary = ? WHERE id = ?",
                    ("maintenance mutation for audit drill", event["id"]),
                )
            mutated = conn.execute("SELECT summary FROM agent_run_events WHERE id = ?", (event["id"],)).fetchone()
            with self.assertRaises(sqlite3.DatabaseError):
                with conn:
                    conn.execute("DELETE FROM agent_run_events WHERE id = ?", (event["id"],))
        self.assertEqual(mutated["summary"], "maintenance mutation for audit drill")

    def test_agent_run_ledger_anchor_records_and_detects_tampering(self):
        anchors_path = self.root / "anchors.jsonl"
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-anchor",
            event_type="started",
            summary="anchor target",
        )

        report = agent_control.agent_run_anchor_report(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=anchors_path,
            write_anchor=True,
        )
        self.assertEqual(report["status"], "pass")
        self.assertTrue(anchors_path.exists())
        self.assertEqual(report["anchor_validation"]["freshness"], "current")

        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-anchor-new-row",
            event_type="started",
            summary="new row after anchor",
        )
        stale = agent_control.agent_run_anchor_report(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=anchors_path,
        )
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["anchor_validation"]["issues"], [])

        with closing(agent_control.connect(self.db_path, maintenance=True)) as conn:
            with conn:
                conn.execute(
                    "UPDATE agent_run_events SET summary = ? WHERE id = ?",
                    ("tampered anchored row", event["id"]),
                )
        tampered = agent_control.agent_run_anchor_report(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=anchors_path,
        )
        self.assertEqual(tampered["status"], "issues")
        self.assertTrue(any("mismatch" in issue["issue"] for issue in tampered["anchor_validation"]["issues"]))

    def test_agent_run_ledger_anchor_keeps_zero_row_history_valid_after_events(self):
        anchors_path = self.root / "anchors.jsonl"
        empty_anchor = agent_control.agent_run_anchor_report(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=anchors_path,
            write_anchor=True,
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-after-empty-anchor",
            event_type="started",
            summary="event after empty anchor",
        )
        current_anchor = agent_control.agent_run_anchor_report(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=anchors_path,
            write_anchor=True,
            anchor_type="maintenance",
        )

        self.assertEqual(empty_anchor["status"], "pass")
        self.assertEqual(current_anchor["status"], "pass")
        self.assertEqual(current_anchor["anchor_validation"]["issues"], [])

    def test_agent_run_ledger_anchor_cli_writes_prompt_report(self):
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-anchor-cli",
            event_type="started",
            summary="anchor cli",
        )

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "anchor-ledger",
                    "--db",
                    str(self.db_path),
                    "--events",
                    str(self.events_path),
                    "--anchors",
                    str(self.root / "anchors.jsonl"),
                    "--write-anchor",
                    "--prompt-only",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("# Agent Run Ledger Anchor", stdout.getvalue())
        self.assertIn("Status: pass", stdout.getvalue())

    def test_memory_backup_and_restore_check_validate_bundle(self):
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-backup",
            event_type="started",
            summary="backup target",
        )
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "anchors.jsonl",
            sessions_path=self.root / "sessions.jsonl",
            backup_root=self.root / "backups",
        )
        check = agent_control.restore_check_memory_backup(backup_dir=Path(backup["backup_dir"]))
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "restore-check",
                    backup["backup_dir"],
                    "--prompt-only",
                ]
            )

        self.assertEqual(backup["status"], "pass")
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["issues"], [])
        self.assertEqual(exit_code, 0)
        self.assertIn("# Memory Restore Check", stdout.getvalue())
        self.assertIn("Status: pass", stdout.getvalue())

    def test_memory_maintenance_logs_run_and_keeps_doctor_passing(self):
        repo_root = self.root / "maintenance-repo"
        gateboard_relative_path = "data/forward-tracking/project_operator_gateboard_latest.json"
        artifact_relative_path = "data/forward-tracking/gateboard_source_artifact_fixture.json"
        unavailable_artifact_path = "data/forward-tracking/intentionally_unavailable_fixture.json"
        gateboard = self._gateboard_fixture(["open_risk_governor_blocked_or_missing"])
        gateboard["source_artifacts"] = {
            "fixture": {
                "available": True,
                "path": artifact_relative_path,
                "report_id": "fixture_readback",
                "status": "pass",
                "generated_at_utc": "2026-07-10T00:00:00Z",
                "error": None,
            },
            "unavailable_fixture": {
                "available": False,
                "path": unavailable_artifact_path,
                "report_id": None,
                "status": None,
                "generated_at_utc": None,
                "error": "missing",
            },
        }
        self._write_minimal_seed_repo(repo_root, gateboard=gateboard)
        self._write_repo_file(repo_root, artifact_relative_path, '{"status":"first"}\n')
        db_path = self.root / "maintenance.db"
        events_path = self.root / "maintenance-events.jsonl"
        anchors_path = self.root / "maintenance-anchors.jsonl"
        sessions_path = self.root / "maintenance-sessions.jsonl"
        backup_root = self.root / "maintenance-backups"
        runs_dir = self.root / "maintenance-dream-runs"
        agent_control.run_dream_cycle(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            dreams_dir=self.root / "maintenance-dreams",
            runs_dir=runs_dir,
        )
        agent_control.bootstrap_project_context(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            manifest_dir=self.root / "maintenance-context-packs",
        )
        bootstrap_refresh = agent_control.refresh_retrieval_freshness(
            db_path=db_path,
            repo_root=repo_root,
        )
        bootstrap_audit = agent_control.memory_audit(db_path=db_path)

        result = agent_control.memory_maintenance(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
        )
        ledger = agent_control.agent_run_ledger_report(db_path=db_path, limit=10)
        maintenance_run = next(run for run in ledger["runs"] if run["run_id"] == result["run_id"])
        doctor = agent_control.memory_doctor(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "maintenance",
                    "--db",
                    str(db_path),
                    "--events",
                    str(events_path),
                    "--anchors",
                    str(anchors_path),
                    "--sessions",
                    str(sessions_path),
                    "--backup-root",
                    str(backup_root),
                    "--runs-dir",
                    str(runs_dir),
                    "--repo-root",
                    str(repo_root),
                    "--prompt-only",
                ]
            )
        with closing(agent_control.connect(db_path)) as conn:
            artifact_node = agent_control._graph_node_row(conn, "evidence_artifact:gateboard:fixture")
            unavailable_node = agent_control._graph_node_row(
                conn,
                "evidence_artifact:gateboard:unavailable_fixture",
            )
        expected_artifact_hash = agent_control._file_sha256(repo_root / artifact_relative_path)
        expected_gateboard_hash = agent_control._file_sha256(repo_root / gateboard_relative_path)

        self.assertEqual(bootstrap_refresh["status"], "pass")
        self.assertEqual(bootstrap_audit["status"], "pass")
        self.assertEqual(result["status"], "pass")
        self.assertTrue(Path(result["backup"]["backup_dir"]).is_dir())
        self.assertEqual(result["doctor"]["status"], "pass")
        self.assertEqual(maintenance_run["status"], "succeeded")
        self.assertEqual(maintenance_run["event_count"], 2)
        self.assertEqual(doctor["status"], "pass")
        self.assertEqual(exit_code, 0)
        self.assertIn("# Memory Maintenance", stdout.getvalue())
        self.assertIn("Status: pass", stdout.getvalue())
        self.assertEqual(artifact_node["metadata"]["source_path"], gateboard_relative_path)
        self.assertEqual(artifact_node["source_ref"], gateboard_relative_path)
        self.assertEqual(artifact_node["metadata"]["source_content_sha256"], expected_gateboard_hash)
        self.assertEqual(artifact_node["metadata"]["artifact_snapshot_path"], artifact_relative_path)
        self.assertEqual(artifact_node["metadata"]["artifact_snapshot_sha256"], expected_artifact_hash)
        self.assertEqual(artifact_node["metadata"]["artifact_snapshot_hash_mode"], "sha256_bytes")
        self.assertEqual(artifact_node["metadata"]["freshness_provenance_mode"], "gateboard_snapshot_sha256")
        self.assertEqual(
            artifact_node["metadata"]["source_content_sha256"],
            artifact_node["metadata"]["gateboard_source_content_sha256"],
        )
        self.assertEqual(unavailable_node["metadata"]["path"], unavailable_artifact_path)
        self.assertEqual(unavailable_node["metadata"]["source_path"], gateboard_relative_path)
        self.assertEqual(unavailable_node["source_ref"], gateboard_relative_path)
        self.assertEqual(
            unavailable_node["metadata"]["freshness_provenance_mode"],
            "gateboard_snapshot_sha256",
        )
        self.assertIsNone(unavailable_node["metadata"]["artifact_snapshot_sha256"])

        self._write_repo_file(repo_root, artifact_relative_path, '{"status":"changed"}\n')
        artifact_changed_refresh = agent_control.refresh_retrieval_freshness(
            db_path=db_path,
            repo_root=repo_root,
        )
        artifact_changed_audit = agent_control.memory_audit(db_path=db_path)
        self.assertEqual(artifact_changed_refresh["status"], "pass")
        self.assertEqual(artifact_changed_audit["status"], "pass")

        gateboard["primary_message"] = "Gateboard snapshot changed after seeding."
        self._write_repo_file(repo_root, gateboard_relative_path, json.dumps(gateboard))
        gateboard_changed_refresh = agent_control.refresh_retrieval_freshness(
            db_path=db_path,
            repo_root=repo_root,
        )
        gateboard_changed_audit = agent_control.memory_audit(db_path=db_path)
        gateboard_changed_required_ids = {
            item["id"] for item in gateboard_changed_audit["required_freshness_issues"]
        }
        self.assertEqual(gateboard_changed_refresh["status"], "issues")
        self.assertGreaterEqual(gateboard_changed_refresh["stale"], 1)
        self.assertEqual(gateboard_changed_audit["status"], "issues")
        self.assertIn("evidence_artifact:gateboard:fixture", gateboard_changed_required_ids)
        self.assertIn("evidence_artifact:gateboard:unavailable_fixture", gateboard_changed_required_ids)

        missing_required_path = "data/forward-tracking/declared_available_but_missing_fixture.json"
        gateboard["source_artifacts"]["missing_required"] = {
            "available": True,
            "path": missing_required_path,
            "report_id": "missing_required_fixture",
            "status": "pass",
            "generated_at_utc": "2026-07-10T00:00:00Z",
            "error": None,
        }
        self._write_repo_file(repo_root, gateboard_relative_path, json.dumps(gateboard))
        with self.assertRaisesRegex(
            agent_control.AgentControlError,
            "declared available gateboard source artifact is missing or unsafe",
        ):
            agent_control.seed_project_memory(
                db_path=db_path,
                events_path=events_path,
                repo_root=repo_root,
                include_repo_files=False,
            )

    def test_memory_auto_maintenance_runs_once_then_skips_when_current(self):
        repo_root = self.root / "auto-maintenance-repo"
        self._write_minimal_seed_repo(repo_root)
        db_path = self.root / "auto-maintenance.db"
        events_path = self.root / "auto-maintenance-events.jsonl"
        anchors_path = self.root / "auto-maintenance-anchors.jsonl"
        sessions_path = self.root / "auto-maintenance-sessions.jsonl"
        backup_root = self.root / "auto-maintenance-backups"
        runs_dir = self.root / "auto-maintenance-dream-runs"
        agent_control.run_dream_cycle(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            dreams_dir=self.root / "auto-maintenance-dreams",
            runs_dir=runs_dir,
        )
        agent_control.bootstrap_project_context(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            manifest_dir=self.root / "auto-maintenance-context-packs",
        )

        first = agent_control.memory_auto_maintenance(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
        )
        second = agent_control.memory_auto_maintenance(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
        )
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = agent_control.main(
                [
                    "memory",
                    "auto-maintenance",
                    "--db",
                    str(db_path),
                    "--events",
                    str(events_path),
                    "--anchors",
                    str(anchors_path),
                    "--sessions",
                    str(sessions_path),
                    "--backup-root",
                    str(backup_root),
                    "--runs-dir",
                    str(runs_dir),
                    "--repo-root",
                    str(repo_root),
                    "--prompt-only",
                ]
            )

        self.assertEqual(first["status"], "pass")
        self.assertEqual(first["action"], "ran")
        self.assertTrue(first["reasons"])
        self.assertEqual(second["status"], "pass")
        self.assertEqual(second["action"], "skipped")
        self.assertEqual(second["reasons"], [])
        self.assertEqual(exit_code, 0)
        self.assertIn("# Memory Auto-Maintenance", stdout.getvalue())
        self.assertIn("Action: skipped", stdout.getvalue())

    def test_memory_restore_check_detects_corrupt_backup_file(self):
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-backup-corrupt",
            event_type="started",
            summary="backup corruption target",
        )
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "anchors.jsonl",
            backup_root=self.root / "backups",
        )
        backup_events = Path(backup["backup_dir"]) / backup["files"]["events"]["member"]
        backup_events.write_text(backup_events.read_text(encoding="utf-8") + "\n{\"corrupt\": true}\n", encoding="utf-8")

        check = agent_control.restore_check_memory_backup(backup_dir=Path(backup["backup_dir"]))

        self.assertEqual(check["status"], "fail")
        self.assertIn("events sha256 mismatch", check["issues"])

    def test_memory_restore_check_detects_semantic_sidecar_corruption_after_manifest_refresh(self):
        sessions_path = self.root / "sessions.jsonl"
        sessions_path.write_text(
            agent_control.canonical_json(
                {
                    "session_id": "S-test",
                    "logged_at": "2026-06-29T00:00:00Z",
                    "path": "docs/session.md",
                    "source_sha256": "abc",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-sidecar-corrupt",
            event_type="started",
            summary="sidecar target",
        )
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "anchors.jsonl",
            sessions_path=sessions_path,
            backup_root=self.root / "backups",
        )
        backup_dir = Path(backup["backup_dir"])
        for label, extra in [
            ("events", {"corrupt": "events"}),
            ("anchors", {"anchor_hash": "fake"}),
            ("sessions", {"corrupt": "sessions"}),
        ]:
            path = backup_dir / backup["files"][label]["member"]
            path.write_text(path.read_text(encoding="utf-8") + agent_control.canonical_json(extra) + "\n", encoding="utf-8")
        manifest_path = backup_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for label in ("events", "anchors", "sessions"):
            member_path = backup_dir / manifest["files"][label]["member"]
            manifest["files"][label]["sha256"] = agent_control._file_sha256(member_path)
        manifest_without_hash = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        manifest["manifest_sha256"] = agent_control._text_sha256(agent_control.canonical_json(manifest_without_hash))
        manifest_path.write_text(agent_control.canonical_json(manifest), encoding="utf-8")

        check = agent_control.restore_check_memory_backup(backup_dir=backup_dir)

        self.assertEqual(check["status"], "fail")
        self.assertIn("events.jsonl sha256 does not match latest ledger anchor", check["issues"])
        self.assertIn("anchors.jsonl does not match database anchor history", check["issues"])
        self.assertTrue(any("sessions.jsonl" in issue for issue in check["issues"]))

    def test_control_file_lock_blocks_second_holder(self):
        lock_path = self.root / "agent_control.lock"
        with agent_control._control_file_lock(lock_path, timeout_seconds=0.1, poll_seconds=0.01):
            with agent_control._control_file_lock(lock_path, timeout_seconds=0.01, poll_seconds=0.01):
                self.assertTrue(lock_path.exists())
        with agent_control._control_file_lock(lock_path, timeout_seconds=0.1, poll_seconds=0.01):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())

    def test_control_file_lock_does_not_probe_windows_pids_with_os_kill(self):
        if agent_control.sys.platform != "win32":
            self.skipTest("Windows-specific os.kill liveness regression")
        lock_path = self.root / "agent_control.lock"
        lock_path.write_text(f"{os.getpid()} {agent_control.utc_now()}\n", encoding="utf-8")
        try:
            with mock.patch.object(agent_control.os, "kill", side_effect=AssertionError("os.kill must not probe pids")):
                with self.assertRaises(agent_control.AgentControlError):
                    with agent_control._control_file_lock(lock_path, timeout_seconds=0.01, poll_seconds=0.01):
                        pass
        finally:
            if lock_path.exists():
                lock_path.unlink()

    def test_agent_run_secret_redaction_catches_common_token_shapes(self):
        private_key = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-secret-redaction",
            event_type="started",
            title="Token ghp_abcdefghijklmnopqrstuvwxyz123456",
            summary=f"Anthropic sk-ant-secret12345 and key {private_key}",
            payload={
                "message": "OpenAI sk-proj-secret12345 and GitHub ghs_abcdefghijklmnopqrstuvwxyz123456",
                "nested": {"not_secret": "visible"},
            },
        )

        serialized = json.dumps(event)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", serialized)
        self.assertNotIn("ghs_abcdefghijklmnopqrstuvwxyz123456", serialized)
        self.assertNotIn("sk-ant-secret12345", serialized)
        self.assertNotIn("sk-proj-secret12345", serialized)
        self.assertNotIn("BEGIN PRIVATE KEY", serialized)
        self.assertIn(agent_control.AGENT_RUN_REDACTED, serialized)

    def test_agent_run_ledger_audit_reports_malformed_payload_json(self):
        event = agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-corrupt",
            event_type="started",
            summary="will corrupt payload",
        )
        with closing(agent_control.connect(self.db_path, maintenance=True)) as conn:
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
        with closing(agent_control.connect(self.db_path, maintenance=True)) as conn:
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
        with closing(agent_control.connect(self.db_path, maintenance=True)) as conn:
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
        self._claim_for_report(task["id"], "worker-a")
        first_report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="worker-a",
            finding="First stale report should stay submitted.",
        )
        self._claim_for_report(task["id"], "worker-b")
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
        self._claim_for_report(accepted_task["id"], "worker-a")
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
        self._claim_for_report(task["id"], "late-worker")
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
            self.assertEqual(agent_control._task_row(conn, task["id"])["status"], "claimed")

    def test_accept_task_rejects_stale_status_update(self):
        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Accept stale task",
            pathway="operator",
        )
        self._claim_for_report(task["id"], "worker-a")
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
        self._claim_for_report(task["id"], "worker-a")
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
        expected_links = {
            (
                f"memory:verification:{task['id']}:{report['id']}",
                "verifies",
                f"task:{task['id']}",
            ),
            (
                f"memory:artifact:{task['id']}:{report['id']}:1",
                "documents",
                f"task:{task['id']}",
            ),
        }
        actual_links = {(item["source"], item["relation"], item["target"]) for item in triplets}
        self.assertTrue(expected_links.issubset(actual_links))
        for item in triplets:
            self.assertTrue(item["metadata"]["does_not_authorize_trading_or_evidence_mutation"])

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
        self._claim_for_report(task["id"], "memory-worker")
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
        self._claim_for_report(task["id"], "memory-worker")
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
        self._claim_for_report(operator_task["id"], "operator-worker")
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
        self._claim_for_report(evidence_task["id"], "evidence-worker")
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
        self.assertEqual(len(result["graph_context"]["triplets"]), 1)
        triplet = result["graph_context"]["triplets"][0]
        self.assertEqual(
            {key: triplet[key] for key in ("source", "relation", "target")},
            {
                "source": "blocker:qqq-537",
                "relation": "requires",
                "target": "knowledge:open-risk-plan",
            },
        )
        self.assertTrue(triplet["metadata"]["does_not_authorize_trading_or_evidence_mutation"])

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
        self._write_repo_file(
            repo_root,
            "data/forward-tracking/lane_promotion_state_latest.json",
            '{"report_id":"regular_options_lane_promotion_state","status":"lane_promotion_state_readback"}\n',
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
            include_repo_index=True,
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
            include_repo_index=True,
        )
        untracked = agent_control.query_graph(
            db_path=self.db_path,
            query="current workspace context",
            metadata_filter={"source_type": "repo_file_index", "git_state": "untracked"},
            max_depth=0,
            include_repo_index=True,
        )
        ignored = agent_control.query_graph(
            db_path=self.db_path,
            query="must not be indexed",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
            include_repo_index=True,
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
                include_repo_index=True,
            )
            self.assertEqual(result["graph_context"]["seed_node_ids"], [])
        allowed = agent_control.query_graph(
            db_path=self.db_path,
            query="allowed",
            metadata_filter={"source_type": "repo_file_index"},
            max_depth=0,
            include_repo_index=True,
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
            include_repo_index=True,
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
            include_repo_index=True,
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
            "npm run memory:anchor-ledger",
            "npm run memory:backup",
            "npm run memory:doctor",
            "npm run memory:maintenance",
            "npm run memory:auto-maintenance",
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
            "memory:anchor-ledger",
            "memory:backup",
            "memory:restore-check",
            "memory:doctor",
            "memory:maintenance",
            "memory:auto-maintenance",
            "memory:research-priorities",
            "memory:profit-learning-sync",
            "memory:profit-learning-audit",
            "memory:schedule-dreams",
            "memory:schedule-maintenance",
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

        with self.assertRaises(agent_control.AgentControlError):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                kind="knowledge",
                title="Harmless raw note",
                body="Harmless coordination note.",
                metadata={"authority_scope": "promotion_authority", "capability_label": "promotion_authority"},
                node_id="knowledge:harmless-raw-note",
            )

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
        self._claim_for_report(task["id"], "docs-worker")
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

    def test_phase10_prunes_dead_schema_tables_and_keeps_blocker_nodes(self):
        legacy_db_path = self.root / "legacy-agent-control.db"
        dead_tables = {
            "messages",
            "feature_snapshots",
            "drift_reports",
            "dataset_versions",
            "provenance_edges",
            "blockers",
        }
        with closing(sqlite3.connect(legacy_db_path)) as conn, conn:
            conn.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT, description TEXT)")
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
                ("agent_control_schema_v2", agent_control.utc_now(), "legacy fixture"),
            )
            for table in dead_tables:
                conn.execute(f"CREATE TABLE {table}(id TEXT)")
        with closing(agent_control.connect(legacy_db_path)) as conn:
            tables_after_migration = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            migration = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (agent_control.CONTROL_SCHEMA_VERSION,),
            ).fetchone()
        self.assertFalse(dead_tables & tables_after_migration)
        self.assertIsNotNone(migration)

        task = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Report graph blocker",
            pathway="operator",
        )
        self._claim_for_report(task["id"], "reviewer")
        agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task["id"],
            worker_id="reviewer",
            finding="Found a blocker.",
            blockers="Need a blocker graph node.",
        )

        with closing(agent_control.connect(self.db_path)) as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            blocker_nodes = conn.execute(
                "SELECT count(*) FROM graph_nodes WHERE kind = 'blocker'"
            ).fetchone()[0]

        self.assertFalse(dead_tables & tables)
        self.assertGreaterEqual(blocker_nodes, 1)

    def test_phase10_retrieval_freshness_marks_and_demotes_stale_docs(self):
        repo_root = self.root / "freshness-repo"
        current_path = repo_root / "docs" / "current.md"
        stale_path = repo_root / "docs" / "stale.md"
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_body = "shared freshness topic current source"
        stale_body = "shared freshness topic stale source"
        current_path.write_text(current_body, encoding="utf-8")
        stale_path.write_text(stale_body, encoding="utf-8")

        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:freshness:stale",
                kind="knowledge",
                title="A stale freshness doc",
                body=stale_body,
                metadata={
                    "source_type": "living_doc",
                    "path": "docs/stale.md",
                    "content_sha256": agent_control._text_sha256(stale_body),
                },
                source_ref="docs/stale.md",
            )
            agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:freshness:current",
                kind="knowledge",
                title="Z current freshness doc",
                body=current_body,
                metadata={
                    "source_type": "living_doc",
                    "path": "docs/current.md",
                    "content_sha256": agent_control._text_sha256(current_body),
                },
                source_ref="docs/current.md",
            )
        stale_path.write_text("shared freshness topic changed source", encoding="utf-8")

        refreshed = agent_control.refresh_retrieval_freshness(db_path=self.db_path, repo_root=repo_root)
        query = agent_control.query_graph(
            db_path=self.db_path,
            query="shared freshness topic",
            max_depth=0,
            limit=2,
        )
        explanations = query["retrieval"]["seed_explanations"]

        self.assertEqual(refreshed["stale"], 1)
        self.assertEqual(explanations[0]["source_node_id"], "knowledge:freshness:current")
        self.assertEqual(explanations[0]["freshness_status"], "current")
        self.assertEqual(explanations[1]["source_node_id"], "knowledge:freshness:stale")
        self.assertEqual(explanations[1]["freshness_status"], "stale")

    def test_phase10_rejects_mismatched_metadata_tenant(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.upsert_graph_node(
                    conn,
                    node_id="memory:wrong-tenant",
                    kind="memory",
                    title="Wrong tenant",
                    body="Should be rejected.",
                    tenant_id=agent_control.DEFAULT_TENANT_ID,
                    metadata={"source_type": "operating_memory", "tenant_id": "other-project"},
                )

    def test_phase10_archives_cross_project_fashion_memory(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="memory:fashion-test",
                kind="memory",
                title="Fashion shopping bot planning loop",
                body="Cross-project planning.",
                metadata=agent_control._with_memory_policy_metadata(
                    {
                        "source_type": "operating_memory",
                        "memory_type": "objective",
                        "memory_status": "active",
                    },
                    source_type="operating_memory",
                    source_quality="operating_memory",
                ),
            )
            agent_control.upsert_graph_node(
                conn,
                node_id="episode:fashion-doc-mention",
                kind="episode",
                title="Phase 10 documents Fashion cleanup",
                body="This living-history entry mentions Fashion bot cleanup but is not cross-project memory.",
                metadata=agent_control._with_memory_policy_metadata(
                    {
                        "source_type": agent_control.LIVING_HISTORY_SOURCE_TYPE,
                        "memory_status": "archived",
                        "archive_reason": "cross_project_tenant_cleanup",
                        "content_sha256": "fixture",
                    },
                    source_type=agent_control.LIVING_HISTORY_SOURCE_TYPE,
                    source_quality="living_history",
                ),
            )

        archived = agent_control.archive_cross_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM graph_nodes WHERE id = ?",
                ("memory:fashion-test",),
            ).fetchone()
            mention = conn.execute(
                "SELECT metadata_json FROM graph_nodes WHERE id = ?",
                ("episode:fashion-doc-mention",),
            ).fetchone()
        metadata = json.loads(row["metadata_json"])
        mention_metadata = json.loads(mention["metadata_json"])
        self.assertEqual(archived["archived_count"], 1)
        self.assertEqual(archived["repaired_count"], 1)
        self.assertEqual(metadata["memory_status"], "archived")
        self.assertEqual(metadata["archive_reason"], "cross_project_tenant_cleanup")
        self.assertNotEqual(mention_metadata.get("memory_status"), "archived")
        self.assertNotIn("archive_reason", mention_metadata)

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


    def test_schema_current_rejects_premature_v4_marker_and_repairs_shape(self):
        partial_db = self.root / "premature-v4.db"
        with closing(sqlite3.connect(partial_db)) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT, description TEXT);
                CREATE TABLE graph_nodes(
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, tenant_id TEXT NOT NULL,
                    sub_tenant_id TEXT, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}', source_ref TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE tasks(
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', pathway TEXT NOT NULL,
                    status TEXT NOT NULL, permission_mode TEXT NOT NULL, owner TEXT,
                    priority INTEGER NOT NULL DEFAULT 50, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE task_claims(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL, status TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE task_reports(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    reported_at TEXT NOT NULL, report_json TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE evidence_artifacts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, graph_node_id TEXT, path TEXT NOT NULL,
                    evidence_class TEXT NOT NULL, created_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE decisions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, graph_node_id TEXT,
                    summary TEXT NOT NULL, created_at TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE worker_runs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, graph_node_id TEXT, worker_id TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
                (agent_control.CONTROL_SCHEMA_VERSION, agent_control.utc_now(), "premature marker"),
            )
            now = agent_control.utc_now()
            conn.execute(
                """
                INSERT INTO tasks(
                    id, created_at, updated_at, title, description, pathway, status,
                    permission_mode, owner, priority, metadata_json
                ) VALUES (?, ?, ?, ?, '', 'operator', 'reported', 'code_docs', 'worker', 50, '{}')
                """,
                ("T-migrate", now, now, "Migrated task"),
            )
            for node_id, tenant_id, metadata in (
                ("task:T-migrate", "tenant-migrated", {"task_id": "T-migrate", "source_type": "task"}),
                ("report:T-migrate:1", agent_control.DEFAULT_TENANT_ID, {"task_id": "T-migrate", "source_type": "task_report"}),
            ):
                conn.execute(
                    """
                    INSERT INTO graph_nodes(
                        id, kind, tenant_id, sub_tenant_id, title, body, metadata_json,
                        source_ref, created_at, updated_at
                    ) VALUES (?, 'episode', ?, 'operator', ?, '', ?, ?, ?, ?)
                    """,
                    (node_id, tenant_id, node_id, json.dumps(metadata), node_id, now, now),
                )

        with closing(agent_control.connect(partial_db)) as conn:
            for table_name in (
                "tasks",
                "task_claims",
                "task_reports",
                "evidence_artifacts",
                "decisions",
                "worker_runs",
            ):
                columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
                self.assertIn("tenant_id", columns)
            self.assertTrue(agent_control._schema_is_current(conn))
            migrated_task = conn.execute("SELECT tenant_id FROM tasks WHERE id = 'T-migrate'").fetchone()
            migrated_report = conn.execute(
                "SELECT tenant_id FROM graph_nodes WHERE id = 'report:T-migrate:1'"
            ).fetchone()
            self.assertEqual(migrated_task["tenant_id"], "tenant-migrated")
            self.assertEqual(migrated_report["tenant_id"], "tenant-migrated")

    def test_backup_v2_and_legacy_relocation_validate_only_supplied_bundle(self):
        agent_control.record_agent_run_event(
            db_path=self.db_path,
            events_path=self.events_path,
            run_id="RUN-relocation",
            event_type="started",
        )
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "anchors.jsonl",
            backup_root=self.root / "backups",
        )
        original = Path(backup["backup_dir"])
        manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], agent_control.BACKUP_MANIFEST_VERSION)
        self.assertTrue(all(not Path(info["member"]).is_absolute() for info in manifest["files"].values()))

        relocated = self.root / "relocated-v2"
        shutil.copytree(original, relocated)
        relocated_db = relocated / "agent_control.db"
        relocated_db.write_bytes(relocated_db.read_bytes() + b"corrupt-copy")
        self.assertEqual(agent_control.restore_check_memory_backup(backup_dir=relocated)["status"], "fail")

        legacy_manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8"))
        legacy_manifest.pop("manifest_version", None)
        for info in legacy_manifest["files"].values():
            info["path"] = str((original / info.pop("member")).resolve())
        unsigned = {key: value for key, value in legacy_manifest.items() if key != "manifest_sha256"}
        legacy_manifest["manifest_sha256"] = agent_control._text_sha256(agent_control.canonical_json(unsigned))
        (original / "manifest.json").write_text(agent_control.canonical_json(legacy_manifest), encoding="utf-8")
        self.assertEqual(agent_control.restore_check_memory_backup(backup_dir=original)["status"], "pass")
        relocated_legacy = self.root / "relocated-legacy"
        shutil.copytree(original, relocated_legacy)
        legacy_copy_db = relocated_legacy / "agent_control.db"
        legacy_copy_db.write_bytes(legacy_copy_db.read_bytes() + b"corrupt-copy")
        self.assertEqual(agent_control.restore_check_memory_backup(backup_dir=relocated_legacy)["status"], "fail")

    def test_checkpoint_eval_accepts_code_docs_but_rejects_trading_modes(self):
        for index, mode in enumerate(sorted(agent_control.PERMISSION_MODES)):
            tenant_id = f"tenant-mode-{index}"
            agent_control.write_checkpoint(
                db_path=self.db_path,
                events_path=self.events_path,
                objective=f"Mode {mode}",
                autonomy_level=mode,
                tenant_id=tenant_id,
            )
            result = agent_control.memory_eval(
                db_path=self.db_path,
                events_path=self.events_path,
                tenant_id=tenant_id,
                seed=False,
            )
            autonomy = next(check for check in result["checks"] if check["name"] == "checkpoint autonomy fails closed")
            self.assertEqual(autonomy["pass"], mode in agent_control.TRADING_FAIL_CLOSED_PERMISSION_MODES)

    def test_task_tenant_isolation_claim_ownership_and_lifecycle_closure(self):
        task_a = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Tenant A task",
            tenant_id="tenant-a",
        )
        task_b = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Tenant B task",
            tenant_id="tenant-b",
        )
        self.assertEqual([row["id"] for row in agent_control.list_tasks(db_path=self.db_path, tenant_id="tenant-a")["tasks"]], [task_a["id"]])
        self.assertEqual([row["id"] for row in agent_control.list_tasks(db_path=self.db_path, tenant_id="tenant-b")["tasks"]], [task_b["id"]])
        with self.assertRaisesRegex(agent_control.AgentControlError, "cannot be accepted from status open"):
            agent_control.accept_task(
                db_path=self.db_path,
                events_path=self.events_path,
                task_id=task_b["id"],
                accepted_by="CEO",
                summary="must not skip review",
            )
        agent_control.claim_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task_b["id"],
            worker_id="tenant-b-worker",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "cannot be accepted from status claimed"):
            agent_control.accept_task(
                db_path=self.db_path,
                events_path=self.events_path,
                task_id=task_b["id"],
                accepted_by="CEO",
                summary="must not skip report",
            )
        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Tenant A objective",
            tenant_id="tenant-a",
        )
        agent_control.write_checkpoint(
            db_path=self.db_path,
            events_path=self.events_path,
            objective="Tenant B objective",
            tenant_id="tenant-b",
        )
        pack_a = agent_control.build_context_pack(db_path=self.db_path, tenant_id="tenant-a")
        pack_b = agent_control.build_context_pack(db_path=self.db_path, tenant_id="tenant-b")
        self.assertEqual(pack_a["latest_checkpoint"]["metadata"]["objective"], "Tenant A objective")
        self.assertEqual(pack_b["latest_checkpoint"]["metadata"]["objective"], "Tenant B objective")
        self.assertNotEqual(pack_a["latest_checkpoint"]["id"], pack_b["latest_checkpoint"]["id"])
        self.assertEqual(agent_control.memory_audit(db_path=self.db_path, tenant_id="tenant-a")["status"], "pass")
        self.assertEqual(agent_control.memory_audit(db_path=self.db_path, tenant_id="tenant-b")["status"], "pass")

        agent_control.claim_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task_a["id"],
            worker_id="tenant-a-worker",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "active claim owner"):
            agent_control.report_task(
                db_path=self.db_path,
                events_path=self.events_path,
                task_id=task_a["id"],
                worker_id="other-label",
                finding="must fail",
            )
        report = agent_control.report_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task_a["id"],
            worker_id="tenant-a-worker",
            finding="tenant A report",
            proof_gate_status="observe_only",
        )
        accepted = agent_control.accept_task(
            db_path=self.db_path,
            events_path=self.events_path,
            task_id=task_a["id"],
            accepted_by="CEO",
            summary="accept tenant A",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            claim = conn.execute("SELECT tenant_id, status FROM task_claims WHERE task_id = ?", (task_a["id"],)).fetchone()
            run = conn.execute(
                "SELECT tenant_id, status, finished_at FROM worker_runs WHERE task_id = ?",
                (task_a["id"],),
            ).fetchone()
            report_row = conn.execute("SELECT tenant_id FROM task_reports WHERE id = ?", (report["id"],)).fetchone()
            decision_row = conn.execute("SELECT tenant_id FROM decisions WHERE task_id = ?", (task_a["id"],)).fetchone()
            tenant_nodes = conn.execute(
                "SELECT tenant_id FROM graph_nodes WHERE id IN (?, ?, ?)",
                (f"task:{task_a['id']}", report["graph_node_id"], accepted["decision_node_id"]),
            ).fetchall()
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.upsert_graph_edge(
                    conn,
                    source_node_id=f"task:{task_a['id']}",
                    relation="crosses",
                    target_node_id=f"task:{task_b['id']}",
                )
        self.assertEqual(claim["status"], "reported")
        self.assertEqual(run["status"], "reported")
        self.assertIsNotNone(run["finished_at"])
        self.assertEqual({claim["tenant_id"], run["tenant_id"], report_row["tenant_id"], decision_row["tenant_id"]}, {"tenant-a"})
        self.assertEqual({row["tenant_id"] for row in tenant_nodes}, {"tenant-a"})

    def test_retrieval_mutations_reindex_audit_parity_and_fresh_only(self):
        memory = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Parity lesson",
            body="first parity body",
            node_id="memory:lesson:parity",
        )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control._update_graph_node_metadata(
                conn,
                memory["id"],
                {"review_state": "updated"},
                body="second parity body",
            )
            doc = conn.execute(
                "SELECT body, metadata_json FROM retrieval_documents WHERE source_node_id = ?",
                (memory["id"],),
            ).fetchone()
        self.assertEqual(doc["body"], "second parity body")
        self.assertEqual(json.loads(doc["metadata_json"])["review_state"], "updated")
        self.assertEqual(agent_control.memory_audit(db_path=self.db_path)["retrieval_parity_issues"], [])

        raw = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            title="Fresh only quartz token",
            body="quartz-fresh-only-token",
            node_id="knowledge:fresh-only",
        )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE retrieval_documents SET freshness_status = 'missing' WHERE source_node_id = ?", (raw["id"],))
            conn.execute("DROP TABLE IF EXISTS retrieval_documents_fts")
        self.assertEqual(
            agent_control.query_graph(db_path=self.db_path, query="quartz-fresh-only-token", fresh_only=True, max_depth=0)["graph_context"]["seed_node_ids"],
            [],
        )
        self.assertIn(
            raw["id"],
            agent_control.query_graph(db_path=self.db_path, query="quartz-fresh-only-token", max_depth=0)["graph_context"]["seed_node_ids"],
        )

    def test_required_freshness_is_fatal_but_repo_mirror_gap_is_nonfatal(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            living = agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:living-required",
                kind="knowledge",
                title="Required living doc",
                body="required body",
                metadata={"source_type": "living_doc"},
            )
            conn.execute("UPDATE retrieval_documents SET freshness_status = 'missing' WHERE source_node_id = ?", (living["id"],))
        audit = agent_control.memory_audit(db_path=self.db_path)
        self.assertEqual(audit["status"], "issues")
        self.assertTrue(audit["required_freshness_issues"])
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE retrieval_documents SET freshness_status = 'current' WHERE source_node_id = ?", (living["id"],))
            repo = agent_control.upsert_graph_node(
                conn,
                node_id="repo_file:nonfatal-gap",
                kind="knowledge",
                title="repo gap",
                body="repo mirror gap",
                metadata={"source_type": "repo_file_index", "path": "missing/repo-gap.md"},
            )
            conn.execute("UPDATE retrieval_documents SET freshness_status = 'missing' WHERE source_node_id = ?", (repo["id"],))
        audit = agent_control.memory_audit(db_path=self.db_path)
        self.assertEqual(audit["status"], "pass")
        self.assertTrue(audit["tier3_repo_mirror_gaps_nonfatal"])

        repo_root = self.root / "gateboard-freshness-repo"
        gateboard_path = "data/forward-tracking/project_operator_gateboard_latest.json"
        self._write_repo_file(repo_root, gateboard_path, '{"status":"first"}\n')
        original_body = (repo_root / gateboard_path).read_text(encoding="utf-8")
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            gateboard_node = agent_control.upsert_graph_node(
                conn,
                node_id="blocker:gateboard:freshness-regression",
                kind="blocker",
                title="Gateboard freshness regression",
                body="gateboard subset",
                metadata={
                    "source_type": "gateboard_blocker",
                    "path": gateboard_path,
                    "source_content_sha256": agent_control._text_sha256(original_body),
                },
                source_ref=gateboard_path,
            )
        agent_control.refresh_retrieval_freshness(
            db_path=self.db_path,
            repo_root=repo_root,
        )
        self._write_repo_file(repo_root, gateboard_path, '{"status":"changed"}\n')
        refreshed = agent_control.refresh_retrieval_freshness(
            db_path=self.db_path,
            repo_root=repo_root,
        )
        self.assertGreaterEqual(refreshed["stale"], 1)
        required_ids = {
            node["id"] for node in agent_control.memory_audit(db_path=self.db_path)["required_freshness_issues"]
        }
        self.assertIn(gateboard_node["id"], required_ids)

    def test_session_id_is_idempotent_by_hash_and_rejects_changed_duplicate(self):
        repo_root = self.root / "immutable-session-repo"
        self._write_repo_file(repo_root, "docs/session.md", "Immutable session body.\n")
        sessions_path = self.root / "immutable-sessions.jsonl"
        first = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=sessions_path,
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="immutable",
        )
        second = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=sessions_path,
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="immutable",
        )
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(sessions_path.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(first["source_sha256"], second["source_sha256"])
        self._write_repo_file(repo_root, "docs/session.md", "Changed session body.\n")
        with self.assertRaisesRegex(agent_control.AgentControlError, "immutable"):
            agent_control.log_session(
                db_path=self.db_path,
                events_path=self.events_path,
                sessions_path=sessions_path,
                transcript_path=Path("docs/session.md"),
                repo_root=repo_root,
                session_id="immutable",
            )

    def test_dream_accept_rehashes_source_and_validates_observed_evidence(self):
        repo_root = self.root / "observed-evidence-repo"
        self._write_repo_file(repo_root, "docs/session.md", "Observed evidence.\n")
        evidence = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "observed-sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="observed-evidence",
        )
        proposal_payload = {
            "entries": [
                {
                    "id": "observed",
                    "type": "lesson",
                    "title": "Observed evidence lesson",
                    "body": "Observed evidence must resolve to an allowed node.",
                    "confidence": "observed",
                    "evidence": [evidence["graph_node_id"]],
                }
            ]
        }
        self._write_repo_file(repo_root, "docs/dream.json", json.dumps(proposal_payload))
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/dream.json"),
            repo_root=repo_root,
            dream_id="observed-valid",
        )
        accepted = agent_control.accept_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            dream_id="observed-valid",
        )
        self.assertEqual(accepted["status"], "accepted")

        task_evidence = agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Disallowed observed evidence kind",
        )
        for dream_id, evidence_ref, expected_error in (
            ("observed-missing", "episode:missing", "not found"),
            ("observed-kind", f"task:{task_evidence['id']}", "kind is not allowed"),
        ):
            invalid_payload = json.loads(json.dumps(proposal_payload))
            invalid_payload["entries"][0]["evidence"] = [evidence_ref]
            relative_path = f"docs/{dream_id}.json"
            self._write_repo_file(repo_root, relative_path, json.dumps(invalid_payload))
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path(relative_path),
                repo_root=repo_root,
                dream_id=dream_id,
            )
            with self.assertRaisesRegex(agent_control.AgentControlError, expected_error):
                agent_control.accept_dream(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    dream_id=dream_id,
                )

        other_evidence = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "other-tenant-sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="other-tenant-evidence",
            tenant_id="other-tenant",
        )
        cross_payload = json.loads(json.dumps(proposal_payload))
        cross_payload["entries"][0]["evidence"] = [other_evidence["graph_node_id"]]
        self._write_repo_file(repo_root, "docs/observed-cross-tenant.json", json.dumps(cross_payload))
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/observed-cross-tenant.json"),
            repo_root=repo_root,
            dream_id="observed-cross-tenant",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "another tenant"):
            agent_control.accept_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                dream_id="observed-cross-tenant",
            )

        self._write_repo_file(repo_root, "docs/changed-dream.json", json.dumps(proposal_payload))
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/changed-dream.json"),
            repo_root=repo_root,
            dream_id="changed-source",
        )
        self._write_repo_file(repo_root, "docs/changed-dream.json", json.dumps({**proposal_payload, "summary": "changed"}))
        with self.assertRaisesRegex(agent_control.AgentControlError, "source changed"):
            agent_control.accept_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                dream_id="changed-source",
            )

    def test_auto_dream_hash_mismatch_stays_unprocessed_for_retry(self):
        repo_root = self.root / "auto-dream-hash-retry"
        self._write_repo_file(repo_root, "docs/session.md", "Lesson: original source lesson\n")
        session = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "auto-dream-hash-sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="hash-retry",
        )
        self._write_repo_file(repo_root, "docs/session.md", "Lesson: changed after capture\n")

        result = agent_control.run_dream_cycle(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            dreams_dir=self.root / "auto-dream-hash-dreams",
            runs_dir=self.root / "auto-dream-hash-runs",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            node = agent_control._graph_node_row(conn, session["graph_node_id"])

        self.assertEqual(result["generated_proposals"], [])
        self.assertEqual(result["accepted"], [])
        self.assertFalse(result["processed_sessions"][0]["marked_processed"])
        self.assertIn("transcript_hash_mismatch", result["processed_sessions"][0]["scanned_sources"])
        self.assertIn("hash changed", result["skipped"][0]["reason"])
        self.assertNotIn("auto_dream_processed_at", node["metadata"])

    def test_graph_create_only_content_path_proof_and_recursive_quarantine(self):
        raw = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            kind="knowledge",
            title="Create only",
            node_id="knowledge:create-only",
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "already exists"):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                kind="knowledge",
                title="Replace",
                node_id=raw["id"],
            )
        operating = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Protected operating",
            node_id="memory:lesson:protected",
        )
        with self.assertRaises(agent_control.AgentControlError):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                kind="knowledge",
                title="Replace operating",
                node_id=operating["id"],
                upsert=True,
            )
        for text in ("Buy 10 SPY calls now", "Send an order for 10 SPY calls", "api_key=sk-abcdefghijklmnopqrstuvwxyz123456"):
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.remember_operating_memory(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    memory_type="lesson",
                    title="Unsafe memory",
                    body=text,
                )
        safe = agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Safe documentation",
            body="Document how options order routing is reviewed; token=<redacted>.",
        )
        self.assertTrue(safe["id"])

        repo_root = self.root / "unsafe-path-repo"
        for relative_path in (
            ".npmrc",
            ".netrc",
            ".aws/config",
            ".ssh/config",
            "browser-profiles/Profile 1/Cookies",
            "config.yml",
        ):
            self._write_repo_file(repo_root, relative_path, "placeholder\n")
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.log_session(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    transcript_path=Path(relative_path),
                    repo_root=repo_root,
                )

        with closing(agent_control.connect(self.db_path)) as conn, conn:
            legacy = agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:legacy-action-flag",
                kind="knowledge",
                title="Legacy flag",
                metadata={"source_type": "legacy", "nested": {"brokerOrderAllowed": True}},
            )
            retrieval_metadata = conn.execute(
                "SELECT metadata_json FROM retrieval_documents WHERE source_node_id = ?",
                (legacy["id"],),
            ).fetchone()["metadata_json"]
        self.assertNotIn("brokerOrderAllowed", retrieval_metadata)
        self.assertTrue(agent_control.memory_audit(db_path=self.db_path)["quarantined_metadata"])

        task = agent_control.create_task(db_path=self.db_path, events_path=self.events_path, title="Proof enum")
        self._claim_for_report(task["id"], "proof-worker")
        with self.assertRaisesRegex(agent_control.AgentControlError, "proof_gate_status"):
            agent_control.report_task(
                db_path=self.db_path,
                events_path=self.events_path,
                task_id=task["id"],
                worker_id="proof-worker",
                finding="invalid proof label",
                proof_gate_status="live_authorized",
            )

    def test_event_mirror_detects_payload_tamper_repairs_with_archive_and_temp_db_isolated(self):
        agent_control.create_task(
            db_path=self.db_path,
            events_path=self.events_path,
            title="Mirror tamper",
        )
        rows = [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines()]
        rows[0]["payload"]["task_id"] = "tampered"
        rows[0]["unexpected_authority"] = True
        self.events_path.write_text("".join(agent_control.canonical_json(row) + "\n" for row in rows), encoding="utf-8")
        with closing(agent_control.connect(self.db_path)) as conn:
            mirror = agent_control.validate_event_mirror(conn, events_path=self.events_path)
        self.assertEqual(mirror["status"], "issues")
        self.assertTrue(any("fields differ" in issue["issue"] for issue in mirror["issues"]))
        doctor = agent_control.memory_doctor(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "mirror-doctor-anchors.jsonl",
            sessions_path=self.root / "mirror-doctor-sessions.jsonl",
            backup_root=self.root / "mirror-doctor-backups",
            runs_dir=self.root / "mirror-doctor-runs",
            repo_root=self.root,
        )
        mirror_check = next(check for check in doctor["checks"] if check["name"] == "events.jsonl mirror")
        self.assertFalse(mirror_check["pass"])
        dry_run = agent_control.repair_event_mirror(
            db_path=self.db_path,
            events_path=self.events_path,
        )
        self.assertEqual(dry_run["status"], "would_repair")
        repaired = agent_control.repair_event_mirror(
            db_path=self.db_path,
            events_path=self.events_path,
            apply=True,
        )
        self.assertTrue(Path(repaired["archive_path"]).is_file())
        self.assertEqual(repaired["after"]["status"], "pass")

        isolated_db = self.root / "isolated" / "temp.db"
        with mock.patch.object(agent_control, "_append_jsonl") as append_jsonl:
            agent_control.create_task(db_path=isolated_db, title="Isolated event path")
        written_path = Path(append_jsonl.call_args.args[0])
        self.assertEqual(written_path, isolated_db.parent / "events.jsonl")
        self.assertNotEqual(written_path.resolve(), agent_control.DEFAULT_EVENTS_PATH.resolve())

    def test_restore_v2_requires_declared_members_exact_tenant_and_session_parity(self):
        repo_root = self.root / "strict-backup-repo"
        self._write_repo_file(repo_root, "docs/session.md", "Strict backup session.\n")
        sessions_path = self.root / "strict-sessions.jsonl"
        agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=sessions_path,
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="strict-backup-session",
        )
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "strict-anchors.jsonl",
            sessions_path=sessions_path,
            backup_root=self.root / "strict-backups",
        )
        original = Path(backup["backup_dir"])
        self.assertEqual(agent_control.restore_check_memory_backup(backup_dir=original)["status"], "pass")

        def resign(bundle: Path, mutate) -> None:
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            mutate(manifest)
            unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
            manifest["manifest_sha256"] = agent_control._text_sha256(agent_control.canonical_json(unsigned))
            manifest_path.write_text(agent_control.canonical_json(manifest), encoding="utf-8")

        omitted = self.root / "strict-omitted"
        shutil.copytree(original, omitted)
        resign(omitted, lambda manifest: manifest["files"].pop("events"))
        omitted_check = agent_control.restore_check_memory_backup(backup_dir=omitted)
        self.assertEqual(omitted_check["status"], "fail")
        self.assertTrue(any("events backup member is not declared" in issue for issue in omitted_check["issues"]))

        wrong_tenant = self.root / "strict-wrong-tenant"
        shutil.copytree(original, wrong_tenant)
        resign(wrong_tenant, lambda manifest: manifest.__setitem__("tenant_id", "other-tenant"))
        tenant_check = agent_control.restore_check_memory_backup(backup_dir=wrong_tenant)
        self.assertEqual(tenant_check["status"], "fail")
        self.assertTrue(any("tenant_id must exactly match" in issue for issue in tenant_check["issues"]))

        divergent_session = self.root / "strict-session-divergence"
        shutil.copytree(original, divergent_session)
        session_member = divergent_session / "sessions.jsonl"
        session_member.write_text("", encoding="utf-8")

        def update_session_hash(manifest):
            manifest["files"]["sessions"]["sha256"] = agent_control._file_sha256(session_member)

        resign(divergent_session, update_session_hash)
        session_check = agent_control.restore_check_memory_backup(backup_dir=divergent_session)
        self.assertEqual(session_check["status"], "fail")
        self.assertTrue(any("session ids do not match" in issue for issue in session_check["issues"]))

    def test_outbox_hash_binds_sql_columns_and_mirror_rejects_order_and_legacy_rows(self):
        agent_control.create_task(db_path=self.db_path, events_path=self.events_path, title="Outbox event one")
        agent_control.create_task(db_path=self.db_path, events_path=self.events_path, title="Outbox event two")
        with closing(agent_control.connect(self.db_path)) as conn:
            original = conn.execute(
                "SELECT id, tenant_id, created_at, hash_version FROM event_outbox WHERE id = 1"
            ).fetchone()
            self.assertEqual(original["hash_version"], agent_control.EVENT_OUTBOX_HASH_VERSION_V2)
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute("UPDATE event_outbox SET created_at = ? WHERE id = 1", ("2099-01-01T00:00:00Z",))
            tampered_time = agent_control.validate_event_outbox(conn)
            conn.execute("UPDATE event_outbox SET created_at = ? WHERE id = 1", (original["created_at"],))
            conn.execute("UPDATE event_outbox SET tenant_id = ? WHERE id = 1", ("other-tenant",))
            tampered_tenant = agent_control.validate_event_outbox(conn)
            conn.execute("UPDATE event_outbox SET tenant_id = ? WHERE id = 1", (original["tenant_id"],))
        self.assertEqual(tampered_time["status"], "issues")
        self.assertTrue(any("SQL created_at" in issue["issue"] for issue in tampered_time["issues"]))
        self.assertEqual(tampered_tenant["status"], "issues")
        self.assertTrue(any("tenant_id" in issue["issue"] for issue in tampered_tenant["issues"]))

        rows = [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines()]
        self.events_path.write_text(
            "".join(agent_control.canonical_json(row) + "\n" for row in reversed(rows)),
            encoding="utf-8",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            reversed_audit = agent_control.validate_event_mirror(conn, events_path=self.events_path)
        self.assertTrue(any("canonical DB outbox order" in issue["issue"] for issue in reversed_audit["issues"]))
        self.events_path.write_text(
            "".join(agent_control.canonical_json(row) + "\n" for row in rows)
            + agent_control.canonical_json({"event_type": "legacy.arbitrary", "payload": {}})
            + "\n",
            encoding="utf-8",
        )
        with closing(agent_control.connect(self.db_path)) as conn:
            legacy_audit = agent_control.validate_event_mirror(conn, events_path=self.events_path)
        self.assertEqual(legacy_audit["status"], "issues")
        self.assertEqual(legacy_audit["quarantined_legacy_row_count"], 1)

    def test_restore_audits_declared_legacy_v1_outbox_without_new_hash_columns(self):
        agent_control.create_task(db_path=self.db_path, events_path=self.events_path, title="Legacy v1 event")
        backup = agent_control.create_memory_backup(
            db_path=self.db_path,
            events_path=self.events_path,
            anchors_path=self.root / "legacy-v1-anchors.jsonl",
            sessions_path=self.root / "legacy-v1-sessions.jsonl",
            backup_root=self.root / "legacy-v1-backups",
            write_anchor=False,
        )
        bundle = Path(backup["backup_dir"])
        backup_db = bundle / "agent_control.db"
        with closing(sqlite3.connect(backup_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM event_outbox ORDER BY id LIMIT 1").fetchone()
            wrapper = json.loads(row["payload_json"])
            legacy_wrapper = {
                "event_log_id": wrapper["event_log_id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "payload": wrapper["payload"],
            }
            legacy_hash = agent_control._text_sha256(
                f"{row['prev_hash']}\n{agent_control.canonical_json(legacy_wrapper)}"
            )
            with conn:
                conn.executescript(
                    """
                    ALTER TABLE event_outbox RENAME TO event_outbox_v2;
                    CREATE TABLE event_outbox (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        prev_hash TEXT NOT NULL DEFAULT '',
                        event_hash TEXT NOT NULL,
                        delivered_at TEXT
                    );
                    """
                )
                conn.execute(
                    """
                    INSERT INTO event_outbox(
                        id, created_at, event_type, payload_json, prev_hash, event_hash, delivered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["created_at"],
                        row["event_type"],
                        agent_control.canonical_json(legacy_wrapper),
                        row["prev_hash"],
                        legacy_hash,
                        row["delivered_at"],
                    ),
                )
                conn.execute("DROP TABLE event_outbox_v2")
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
                    ("agent_control_schema_v4", agent_control.utc_now(), "legacy backup compatibility fixture"),
                )
        legacy_mirror = {
            "event_type": row["event_type"],
            "created_at": row["created_at"],
            "payload": wrapper["payload"],
            "outbox_event_id": row["id"],
            "outbox_hash": legacy_hash,
        }
        (bundle / "events.jsonl").write_text(
            agent_control.canonical_json(legacy_mirror) + "\n",
            encoding="utf-8",
        )
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = "agent_control_schema_v4"
        manifest["files"]["db"]["sha256"] = agent_control._file_sha256(backup_db)
        manifest["files"]["events"]["sha256"] = agent_control._file_sha256(bundle / "events.jsonl")
        unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        manifest["manifest_sha256"] = agent_control._text_sha256(agent_control.canonical_json(unsigned))
        manifest_path.write_text(agent_control.canonical_json(manifest), encoding="utf-8")

        check = agent_control.restore_check_memory_backup(backup_dir=bundle)
        self.assertEqual(check["event_outbox"]["status"], "pass", check["event_outbox"]["issues"])
        self.assertEqual(check["event_mirror"]["status"], "pass", check["event_mirror"]["issues"])
        self.assertEqual(
            check["event_outbox"]["hash_version_counts"],
            {agent_control.EVENT_OUTBOX_HASH_VERSION_V1: 1},
        )

    def test_event_writes_repair_and_snapshot_backup_are_serialized(self):
        agent_control.create_task(db_path=self.db_path, events_path=self.events_path, title="Concurrency seed")
        anchors_path = self.root / "concurrency-anchors.jsonl"
        with ThreadPoolExecutor(max_workers=3) as pool:
            writer = pool.submit(
                agent_control.create_task,
                db_path=self.db_path,
                events_path=self.events_path,
                title="Concurrent writer",
            )
            repair = pool.submit(
                agent_control.repair_event_mirror,
                db_path=self.db_path,
                events_path=self.events_path,
                apply=True,
            )
            backup = pool.submit(
                agent_control.create_memory_backup,
                db_path=self.db_path,
                events_path=self.events_path,
                anchors_path=anchors_path,
                backup_root=self.root / "concurrency-backups",
            )
            writer.result(timeout=30)
            repaired = repair.result(timeout=30)
            backed_up = backup.result(timeout=30)
        self.assertEqual(repaired["after"]["status"], "pass")
        with closing(agent_control.connect(self.db_path)) as conn:
            self.assertEqual(agent_control.validate_event_outbox(conn)["status"], "pass")
            self.assertEqual(agent_control.validate_event_mirror(conn, events_path=self.events_path)["status"], "pass")
        self.assertEqual(
            agent_control.restore_check_memory_backup(backup_dir=Path(backed_up["backup_dir"]))["status"],
            "pass",
        )

    def test_session_append_failure_is_durable_and_idempotent_retry_repairs_sidecar(self):
        repo_root = self.root / "session-recovery-repo"
        self._write_repo_file(repo_root, "docs/session.md", "Recover session sidecar.\n")
        sessions_path = self.root / "recover-sessions.jsonl"
        real_append = agent_control._append_jsonl
        failed = False

        def flaky_append(path, event):
            nonlocal failed
            if Path(path).resolve() == sessions_path.resolve() and not failed:
                failed = True
                raise OSError("simulated session append failure")
            return real_append(path, event)

        with mock.patch.object(agent_control, "_append_jsonl", side_effect=flaky_append):
            with self.assertRaisesRegex(agent_control.AgentControlError, "remains retryable"):
                agent_control.log_session(
                    db_path=self.db_path,
                    events_path=self.events_path,
                    sessions_path=sessions_path,
                    transcript_path=Path("docs/session.md"),
                    repo_root=repo_root,
                    session_id="retryable-session",
                )
        with closing(agent_control.connect(self.db_path)) as conn:
            pending = conn.execute(
                "SELECT delivered_at FROM session_sidecar_outbox WHERE session_id = 'retryable-session'"
            ).fetchone()
            self.assertIsNone(pending["delivered_at"])
            self.assertIsNotNone(conn.execute("SELECT 1 FROM graph_nodes WHERE id = 'session:retryable-session'").fetchone())

        recovered = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=sessions_path,
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="retryable-session",
        )
        self.assertTrue(recovered["idempotent"])
        self.assertEqual(len(sessions_path.read_text(encoding="utf-8").splitlines()), 1)
        with closing(agent_control.connect(self.db_path)) as conn:
            delivered = conn.execute(
                "SELECT delivered_at FROM session_sidecar_outbox WHERE session_id = 'retryable-session'"
            ).fetchone()
            session_events = conn.execute(
                "SELECT count(*) FROM event_outbox WHERE event_type = 'session.logged'"
            ).fetchone()[0]
        self.assertIsNotNone(delivered["delivered_at"])
        self.assertEqual(session_events, 1)

    def test_dream_observed_evidence_requires_reviewed_integrity_and_accept_reparses_source(self):
        repo_root = self.root / "dream-integrity-repo"
        raw_sha = "a" * 64
        forged_session = agent_control.remember_graph_node(
            db_path=self.db_path,
            events_path=self.events_path,
            node_id="episode:forged-session-evidence",
            kind="episode",
            title="Forged session evidence",
            source_ref="docs/fake-session.md",
            metadata={
                "source_type": "session_transcript",
                "session_id": "forged-session-evidence",
                "path": "docs/fake-session.md",
                "source_sha256": raw_sha,
                "bytes": 128,
                "logged_at": "2026-07-09T00:00:00Z",
            },
        )
        with self.assertRaisesRegex(agent_control.AgentControlError, "reserved trusted evidence attestation"):
            agent_control.remember_graph_node(
                db_path=self.db_path,
                events_path=self.events_path,
                node_id="episode:forged-attested-session",
                kind="episode",
                title="Forged attested session",
                metadata={
                    "source_type": "session_transcript",
                    "session_id": "forged-attested-session",
                    "path": "docs/fake-session.md",
                    "source_sha256": raw_sha,
                    agent_control.TRUSTED_EVIDENCE_ATTESTATION_KEY: {
                        "version": agent_control.TRUSTED_EVIDENCE_ATTESTATION_VERSION,
                        "writer": "log_session",
                        "record_type": "session_sidecar_outbox",
                        "record_id": "forged-attested-session",
                    },
                },
            )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            raw_evidence = agent_control.upsert_graph_node(
                conn,
                node_id="evidence:raw-unreviewed",
                kind="evidence_artifact",
                title="Raw unreviewed evidence",
                metadata={"source_type": "raw_graph_note", "source_sha256": raw_sha},
            )
            raw_decision = agent_control.upsert_graph_node(
                conn,
                node_id="decision:raw-unreviewed",
                kind="decision",
                title="Raw decision",
                metadata={"source_type": "raw_graph_note", "source_sha256": raw_sha},
            )
        for dream_id, evidence_id, expected in (
            ("forged-session-dream", forged_session["id"], "not reviewed"),
            ("raw-evidence-dream", raw_evidence["id"], "not reviewed"),
            ("raw-decision-dream", raw_decision["id"], "kind is not allowed"),
        ):
            relative = f"docs/{dream_id}.json"
            self._write_repo_file(
                repo_root,
                relative,
                json.dumps(
                    {
                        "entries": [
                            {
                                "id": "observed",
                                "type": "lesson",
                                "title": "Observed raw evidence",
                                "body": "Raw graph context is not reviewed evidence.",
                                "confidence": "observed",
                                "evidence": [evidence_id],
                            }
                        ]
                    }
                ),
            )
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path(relative),
                repo_root=repo_root,
                dream_id=dream_id,
            )
            with self.assertRaisesRegex(agent_control.AgentControlError, expected):
                agent_control.accept_dream(db_path=self.db_path, events_path=self.events_path, dream_id=dream_id)

        self._write_repo_file(repo_root, "docs/session.md", "Reviewed session evidence.\n")
        session = agent_control.log_session(
            db_path=self.db_path,
            events_path=self.events_path,
            sessions_path=self.root / "dream-integrity-sessions.jsonl",
            transcript_path=Path("docs/session.md"),
            repo_root=repo_root,
            session_id="dream-integrity-session",
        )
        source_payload = {
            "entries": [
                {
                    "id": "source-entry",
                    "type": "lesson",
                    "title": "Verified source entry",
                    "body": "Acceptance reparses the source.",
                    "confidence": "observed",
                    "evidence": [session["graph_node_id"]],
                }
            ]
        }
        self._write_repo_file(repo_root, "docs/reparse.json", json.dumps(source_payload))
        agent_control.propose_dream(
            db_path=self.db_path,
            events_path=self.events_path,
            proposal_path=Path("docs/reparse.json"),
            repo_root=repo_root,
            dream_id="reparse-source",
        )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            row = conn.execute("SELECT metadata_json FROM graph_nodes WHERE id = 'dream:reparse-source'").fetchone()
            metadata = json.loads(row["metadata_json"])
            metadata["entries"][0]["body"] = "tampered stored entry"
            conn.execute(
                "UPDATE graph_nodes SET metadata_json = ? WHERE id = 'dream:reparse-source'",
                (agent_control.canonical_json(metadata),),
            )
        with self.assertRaisesRegex(agent_control.AgentControlError, "stored entries differ"):
            agent_control.accept_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                dream_id="reparse-source",
            )

    def test_query_and_audit_force_nonauthorization_and_quarantine_raw_edge_metadata(self):
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            raw = agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:legacy-authority-node",
                kind="knowledge",
                title="Legacy authority node",
                metadata={
                    "source_type": "legacy",
                    "authority_scope": "broker_action",
                    "does_not_authorize_trading_or_evidence_mutation": False,
                    "nested": {"brokerOrderAllowed": True},
                },
            )
            target = agent_control.upsert_graph_node(
                conn,
                node_id="knowledge:legacy-authority-target",
                kind="knowledge",
                title="Legacy authority target",
            )
            edge = agent_control.upsert_graph_edge(
                conn,
                source_node_id=raw["id"],
                relation="references",
                target_node_id=target["id"],
            )
            conn.execute(
                "UPDATE graph_edges SET metadata_json = ? WHERE id = ?",
                (json.dumps({"brokerOrderAllowed": True, "authority_scope": "broker_action"}), edge["id"]),
            )
            with self.assertRaises(agent_control.AgentControlError):
                agent_control.upsert_graph_edge(
                    conn,
                    source_node_id=raw["id"],
                    relation="unsafe",
                    target_node_id=target["id"],
                    metadata={"promotionReady": True},
                )
        result = agent_control.query_graph(
            db_path=self.db_path,
            query="legacy-authority-node",
            max_depth=1,
        )
        returned = next(node for node in result["graph_context"]["nodes"] if node["id"] == raw["id"])
        self.assertTrue(returned["metadata"]["does_not_authorize_trading_or_evidence_mutation"])
        self.assertNotIn("brokerOrderAllowed", json.dumps(returned["metadata"]))
        returned_edge = next(item for item in result["graph_context"]["edges"] if item["id"] == edge["id"])
        self.assertTrue(returned_edge["metadata"]["does_not_authorize_trading_or_evidence_mutation"])
        self.assertNotIn("brokerOrderAllowed", json.dumps(returned_edge["metadata"]))
        audit = agent_control.memory_audit(db_path=self.db_path)
        self.assertTrue(audit["quarantined_metadata"])
        self.assertTrue(audit["quarantined_edge_metadata"])
        self.assertNotIn('"brokerOrderAllowed": true', json.dumps(audit))

    def test_context_pack_filters_accepted_dream_lessons_by_pathway(self):
        repo_root = self.root / "dream-pathway-repo"
        for pathway in ("evidence", "profitability"):
            relative = f"docs/{pathway}-lesson.json"
            self._write_repo_file(
                repo_root,
                relative,
                json.dumps(
                    {
                        "entries": [
                            {
                                "id": f"{pathway}-lesson",
                                "type": "lesson",
                                "title": f"{pathway} dream lesson",
                                "body": f"Lesson scoped to {pathway}.",
                                "metadata": {"pathway": pathway},
                            }
                        ]
                    }
                ),
            )
            agent_control.propose_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                proposal_path=Path(relative),
                repo_root=repo_root,
                dream_id=f"{pathway}-pathway",
            )
            agent_control.accept_dream(
                db_path=self.db_path,
                events_path=self.events_path,
                dream_id=f"{pathway}-pathway",
            )
        evidence_pack = agent_control.build_context_pack(
            db_path=self.db_path,
            pathway="evidence",
        )
        profitability_pack = agent_control.build_context_pack(
            db_path=self.db_path,
            pathway="profitability",
        )
        self.assertEqual(
            [node["metadata"]["pathway"] for node in evidence_pack["dream_lessons"]],
            ["evidence"],
        )
        self.assertEqual(
            [node["metadata"]["pathway"] for node in profitability_pack["dream_lessons"]],
            ["profitability"],
        )

    def test_freshness_contains_paths_guards_protected_files_and_tracks_deleted_required_sources(self):
        repo_root = self.root / "freshness-containment-repo"
        repo_root.mkdir(parents=True)
        (self.root / "outside-secret.txt").write_text("outside secret marker", encoding="utf-8")
        self._write_repo_file(repo_root, ".env", "SECRET=outside\n")
        self._write_repo_file(repo_root, "docs/delete-me.md", "required source\n")
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            for node_id, source_path in (
                ("knowledge:outside-required", "../outside-secret.txt"),
                ("knowledge:protected-required", ".env"),
                ("knowledge:deleted-required", "docs/delete-me.md"),
            ):
                agent_control.upsert_graph_node(
                    conn,
                    node_id=node_id,
                    kind="knowledge",
                    title=node_id,
                    body="required source",
                    metadata={"source_type": "living_doc", "path": source_path},
                    source_ref=source_path,
                )
            conn.execute("DELETE FROM graph_nodes WHERE id = 'knowledge:deleted-required'")
        refreshed = agent_control.refresh_retrieval_freshness(
            db_path=self.db_path,
            repo_root=repo_root,
        )
        self.assertGreaterEqual(refreshed["missing"], 2)
        self.assertEqual(refreshed["status"], "issues")
        self.assertIn("living_doc", refreshed["missing_required_source_types"])
        self.assertTrue(
            any(item["node_id"] == "knowledge:deleted-required" for item in refreshed["missing_required_sources"])
        )
        audit = agent_control.memory_audit(db_path=self.db_path)
        self.assertEqual(audit["status"], "issues")
        self.assertTrue(any(item["id"] == "knowledge:deleted-required" for item in audit["required_freshness_issues"]))

    def test_versioned_history_expectations_retire_without_weakening_canonical_freshness(self):
        repo_root = self.root / "canonical-freshness-repo"
        self._write_repo_file(
            repo_root,
            "docs/WORKLOG.md",
            "# Worklog\n\n## 2026-07-01\n\n- Version one worklog entry.\n",
        )
        self._write_repo_file(
            repo_root,
            "docs/DECISIONS.md",
            "# Decisions\n\n## 2026-07-01: Version One\n\nDurable decision: version one.\n",
        )
        first = agent_control.ingest_living_history(db_path=self.db_path, repo_root=repo_root)
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            first_ids = {
                str(row["id"])
                for row in conn.execute(
                    """
                    SELECT id FROM graph_nodes
                    WHERE json_extract(metadata_json, '$.source_type') = ?
                    """,
                    (agent_control.LIVING_HISTORY_SOURCE_TYPE,),
                ).fetchall()
            }
            now = agent_control.utc_now()
            conn.executemany(
                """
                INSERT INTO retrieval_source_expectations(
                    tenant_id, node_id, source_type, source_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        agent_control.DEFAULT_TENANT_ID,
                        node_id,
                        agent_control.LIVING_HISTORY_SOURCE_TYPE,
                        "docs/DECISIONS.md" if node_id.startswith("decision:") else "docs/WORKLOG.md",
                        now,
                        now,
                    )
                    for node_id in first_ids
                ],
            )

        self._write_repo_file(
            repo_root,
            "docs/WORKLOG.md",
            "# Worklog\n\n## 2026-07-02\n\n- Version two worklog entry.\n",
        )
        self._write_repo_file(
            repo_root,
            "docs/DECISIONS.md",
            "# Decisions\n\n## 2026-07-02: Version Two\n\nDurable decision: version two.\n",
        )
        second = agent_control.ingest_living_history(db_path=self.db_path, repo_root=repo_root)
        refreshed_history = agent_control.refresh_retrieval_freshness(
            db_path=self.db_path,
            repo_root=repo_root,
        )
        history_audit = agent_control.memory_audit(db_path=self.db_path)
        with closing(agent_control.connect(self.db_path)) as conn:
            remaining_old_ids = conn.execute(
                "SELECT id FROM graph_nodes WHERE id IN ({})".format(
                    ", ".join("?" for _ in first_ids)
                ),
                tuple(sorted(first_ids)),
            ).fetchall()
            history_expectation_ids = {
                str(row["node_id"])
                for row in conn.execute(
                    "SELECT node_id FROM retrieval_source_expectations WHERE source_type = ?",
                    (agent_control.LIVING_HISTORY_SOURCE_TYPE,),
                ).fetchall()
            }
            ghost_expectation_count = conn.execute(
                "SELECT count(*) FROM retrieval_source_expectations WHERE node_id IN ({})".format(
                    ", ".join("?" for _ in first_ids)
                ),
                tuple(sorted(first_ids)),
            ).fetchone()[0]

        expected_history_expectations = {
            f"{agent_control.LIVING_HISTORY_EXPECTATION_PREFIX}docs/worklog.md",
            f"{agent_control.LIVING_HISTORY_EXPECTATION_PREFIX}docs/decisions.md",
        }

        self.assertEqual(first["nodes_created"], 2)
        self.assertEqual(second["nodes_created"], 2)
        self.assertEqual(second["nodes_pruned"], 2)
        self.assertEqual(remaining_old_ids, [])
        self.assertEqual(history_expectation_ids, expected_history_expectations)
        self.assertEqual(ghost_expectation_count, 0)
        self.assertEqual(refreshed_history["status"], "pass")
        self.assertEqual(history_audit["status"], "pass")

        worklog_expectation = f"{agent_control.LIVING_HISTORY_EXPECTATION_PREFIX}docs/worklog.md"
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute(
                "DELETE FROM retrieval_source_expectations WHERE tenant_id = ? AND node_id = ?",
                (agent_control.DEFAULT_TENANT_ID, worklog_expectation),
            )
            conn.execute(
                """
                DELETE FROM graph_nodes
                WHERE tenant_id = ?
                  AND json_extract(metadata_json, '$.source_type') = ?
                  AND lower(json_extract(metadata_json, '$.source_path')) = 'docs/worklog.md'
                """,
                (agent_control.DEFAULT_TENANT_ID, agent_control.LIVING_HISTORY_SOURCE_TYPE),
            )
        one_class_audit = agent_control.memory_audit(db_path=self.db_path)
        one_class_issue_ids = {item["id"] for item in one_class_audit["required_freshness_issues"]}
        self.assertEqual(one_class_audit["status"], "issues")
        self.assertIn(worklog_expectation, one_class_issue_ids)

        agent_control.ingest_living_history(db_path=self.db_path, repo_root=repo_root)
        self.assertEqual(
            agent_control.refresh_retrieval_freshness(db_path=self.db_path, repo_root=repo_root)["status"],
            "pass",
        )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute(
                "DELETE FROM retrieval_source_expectations WHERE tenant_id = ? AND source_type = ?",
                (agent_control.DEFAULT_TENANT_ID, agent_control.LIVING_HISTORY_SOURCE_TYPE),
            )
            conn.execute(
                """
                DELETE FROM graph_nodes
                WHERE tenant_id = ? AND json_extract(metadata_json, '$.source_type') = ?
                """,
                (agent_control.DEFAULT_TENANT_ID, agent_control.LIVING_HISTORY_SOURCE_TYPE),
            )
        no_class_audit = agent_control.memory_audit(db_path=self.db_path)
        no_class_issue_ids = {item["id"] for item in no_class_audit["required_freshness_issues"]}
        self.assertEqual(no_class_audit["status"], "issues")
        self.assertTrue(expected_history_expectations.issubset(no_class_issue_ids))

        agent_control.ingest_living_history(db_path=self.db_path, repo_root=repo_root)
        self.assertEqual(
            agent_control.refresh_retrieval_freshness(db_path=self.db_path, repo_root=repo_root)["status"],
            "pass",
        )
        self.assertEqual(agent_control.memory_audit(db_path=self.db_path)["status"], "pass")

        self._write_minimal_seed_repo(repo_root)
        agent_control.seed_project_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            repo_root=repo_root,
            include_repo_files=False,
        )

        deleted_id = "knowledge:package.json"
        reclassified_id = "knowledge:docs/agent-control-plane.md"
        missing_id = "knowledge:readme.md"
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            conn.execute("DELETE FROM retrieval_source_expectations WHERE node_id = ?", (deleted_id,))
            conn.execute("DELETE FROM graph_nodes WHERE id = ?", (deleted_id,))

            reclassified = agent_control._graph_node_row(conn, reclassified_id)
            reclassified_metadata = dict(reclassified["metadata"])
            reclassified_metadata["source_type"] = "repo_file_index"
            agent_control.upsert_graph_node(
                conn,
                node_id=reclassified_id,
                kind=reclassified["kind"],
                title=reclassified["title"],
                body=reclassified["body"],
                tenant_id=reclassified["tenant_id"],
                sub_tenant_id=reclassified["sub_tenant_id"],
                metadata=reclassified_metadata,
                source_ref=reclassified["source_ref"],
            )
            conn.execute("DELETE FROM retrieval_source_expectations WHERE node_id = ?", (reclassified_id,))
            conn.execute("DELETE FROM retrieval_source_expectations WHERE node_id = ?", (missing_id,))

        (repo_root / "README.md").unlink()
        refreshed = agent_control.refresh_retrieval_freshness(
            db_path=self.db_path,
            repo_root=repo_root,
        )
        refreshed_ids = {item["node_id"] for item in refreshed["missing_required_sources"]}
        self.assertEqual(refreshed["status"], "issues")
        self.assertTrue({deleted_id, reclassified_id, missing_id}.issubset(refreshed_ids))
        self.assertIn("package_manifest", refreshed["missing_required_source_types"])
        self.assertIn("control_plane_doc", refreshed["missing_required_source_types"])
        self.assertIn("startup_doc", refreshed["missing_required_source_types"])

        report = agent_control.retrieval_freshness_report(db_path=self.db_path)
        report_ids = {item["node_id"] for item in report["missing_required_sources"]}
        self.assertEqual(report["status"], "issues")
        self.assertTrue({deleted_id, reclassified_id, missing_id}.issubset(report_ids))

        audit = agent_control.memory_audit(db_path=self.db_path)
        audit_ids = {item["id"] for item in audit["required_freshness_issues"]}
        self.assertEqual(audit["status"], "issues")
        self.assertTrue({deleted_id, reclassified_id, missing_id}.issubset(audit_ids))

    def test_concurrent_process_init_serializes_partial_schema_migration(self):
        db_path = self.root / "concurrent-init.db"
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute(
                "CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT, description TEXT)"
            )
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
                (agent_control.CONTROL_SCHEMA_VERSION, agent_control.utc_now(), "premature concurrent marker"),
            )
        gate_path = self.root / "concurrent-init.start"
        ready_paths = [self.root / f"concurrent-init.ready-{index}" for index in range(8)]
        processes = []
        for ready_path in ready_paths:
            code = f"""
import time
from pathlib import Path
from scripts import agent_control as a

gate = Path({str(gate_path)!r})
Path({str(ready_path)!r}).write_text("ready", encoding="utf-8")
deadline = time.monotonic() + 15
while not gate.exists():
    if time.monotonic() >= deadline:
        raise RuntimeError("concurrent connect gate timed out")
    time.sleep(0.005)
for _ in range(3):
    connection = a.connect(Path({str(db_path)!r}))
    try:
        assert a._schema_is_current(connection)
    finally:
        connection.close()
"""
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", code],
                    cwd=agent_control.ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        ready_deadline = time.monotonic() + 15
        while not all(path.exists() for path in ready_paths) and time.monotonic() < ready_deadline:
            time.sleep(0.01)
        all_ready = all(path.exists() for path in ready_paths)
        gate_path.write_text("start", encoding="utf-8")
        self.assertTrue(all_ready, "concurrent connect subprocesses did not reach the start gate")
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")
        with closing(agent_control.connect(db_path)) as conn:
            self.assertTrue(agent_control._schema_is_current(conn))
            marker_count = conn.execute(
                "SELECT count(*) FROM schema_migrations WHERE version = ?",
                (agent_control.CONTROL_SCHEMA_VERSION,),
            ).fetchone()[0]
        self.assertEqual(marker_count, 1)

    def test_memory_audit_cli_nonzero_and_context_repo_index_is_opt_in(self):
        agent_control.remember_operating_memory(
            db_path=self.db_path,
            events_path=self.events_path,
            memory_type="lesson",
            title="Expired CLI audit",
            body="expired audit body",
            freshness_days=0,
        )
        self.assertEqual(
            agent_control.main(["memory", "audit", "--db", str(self.db_path), "--prompt-only"]),
            1,
        )
        with closing(agent_control.connect(self.db_path)) as conn, conn:
            agent_control.upsert_graph_node(
                conn,
                node_id="repo_file:quartz-context-hit",
                kind="knowledge",
                title="quartz context goal file",
                body="quartz-context-goal-token",
                metadata={"source_type": "repo_file_index", "path": "docs/quartz.md"},
            )
        default_pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="quartz-context-goal-token",
        )
        opted_pack = agent_control.build_context_pack(
            db_path=self.db_path,
            goal="quartz-context-goal-token",
            include_repo_index=True,
        )
        self.assertEqual(default_pack["relevant_repo_files"], [])
        self.assertEqual([node["id"] for node in opted_pack["relevant_repo_files"]], ["repo_file:quartz-context-hit"])

    def test_lock_checks_live_pid_before_age_and_preserves_replacement_owner(self):
        lock_path = self.root / "aged-live.lock"
        lock_path.write_text(f"{os.getpid()} {agent_control.utc_now()} live-owner\n", encoding="utf-8")
        old = os.path.getmtime(lock_path) - 3600
        os.utime(lock_path, (old, old))
        with self.assertRaises(agent_control.AgentControlError):
            with agent_control._control_file_lock(
                lock_path,
                timeout_seconds=0.01,
                poll_seconds=0.001,
                stale_seconds=1,
            ):
                pass
        self.assertTrue(lock_path.exists())
        lock_path.unlink()

        replacement_path = self.root / "replacement.lock"
        with agent_control._control_file_lock(replacement_path):
            replacement_path.write_text(f"{os.getpid()} {agent_control.utc_now()} replacement-owner\n", encoding="utf-8")
        self.assertTrue(replacement_path.exists())
        replacement_path.unlink()

        denied_path = self.root / "denied.lock"
        denied_path.write_text("invalid lock", encoding="utf-8")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(agent_control.AgentControlError, "cannot be inspected"):
                with agent_control._control_file_lock(
                    denied_path,
                    timeout_seconds=0,
                    poll_seconds=0.001,
                    stale_seconds=0,
                ):
                    pass


if __name__ == "__main__":
    unittest.main()
