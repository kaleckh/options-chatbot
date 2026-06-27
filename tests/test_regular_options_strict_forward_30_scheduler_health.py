import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_30_scheduler_health as health


TASK_OUTPUT = r"""
Folder: \
HostName:                             KAESDEVICE
TaskName:                             \OptionsStrictForward30Collector
Next Run Time:                        6/29/2026 7:35:00 AM
Status:                               Ready
Task To Run:                          C:\Users\kalec\options-chatbot\scripts\run_strict_forward_30_auto_window_collector.bat
Scheduled Task State:                 Enabled
Stop Task If Runs X Hours and X Mins: 00:45:00
Repeat: Every:                        0 Hour(s), 30 Minute(s)
Repeat: Until: Duration:              6 Hour(s), 30 Minute(s)
"""


class RegularOptionsStrictForward30SchedulerHealthTests(unittest.TestCase):
    def test_parse_schtasks_list_handles_colon_keys(self):
        fields = health.parse_schtasks_list(
            TASK_OUTPUT + "Stop Task If Runs X Hours and X Mins: 00:45:00\n"
        )

        self.assertEqual(fields["TaskName"], r"\OptionsStrictForward30Collector")
        self.assertEqual(fields["Repeat: Every"], "0 Hour(s), 30 Minute(s)")
        self.assertEqual(fields["Repeat: Until: Duration"], "6 Hour(s), 30 Minute(s)")
        self.assertEqual(fields["Stop Task If Runs X Hours and X Mins"], "00:45:00")

    def test_ready_scheduler_passes(self):
        with patch.object(health, "query_task", return_value=(0, TASK_OUTPUT, "")):
            report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["batch_file"]["status"], "loaded")
        self.assertEqual(report["batch_file"]["missing_steps"], [])
        self.assertFalse(report["safety"]["append_allowed"])
        self.assertFalse(report["safety"]["auto_track_allowed"])

    def test_missing_task_fails_closed(self):
        with patch.object(health, "query_task", return_value=(1, "", "ERROR: missing")):
            report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_task_missing_or_unqueryable")
        self.assertIn("schtasks_query_failed", report["blockers"])

    def test_mispointed_task_blocks(self):
        bad = TASK_OUTPUT.replace("run_strict_forward_30_auto_window_collector.bat", "unsafe.bat")
        with patch.object(health, "query_task", return_value=(0, bad, "")):
            report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_config_blocked")
        self.assertIn("task_to_run_mismatch", report["blockers"])

    def test_missing_batch_step_blocks_scheduler_health(self):
        batch = {
            "path": "scripts/run_strict_forward_30_auto_window_collector.bat",
            "exists": True,
            "status": "loaded",
            "missing_steps": ["scripts\\build_regular_options_strict_forward_30_exit_evidence_plan.py --json"],
            "order_blockers": [],
            "prohibited_tokens_present": [],
        }
        with patch.object(health, "query_task", return_value=(0, TASK_OUTPUT, "")):
            with patch.object(health, "_inspect_batch_file", return_value=batch):
                report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_config_blocked")
        self.assertIn(
            "batch_missing_step:scripts\\build_regular_options_strict_forward_30_exit_evidence_plan.py --json",
            report["blockers"],
        )

    def test_batch_append_token_blocks_scheduler_health(self):
        batch = {
            "path": "scripts/run_strict_forward_30_auto_window_collector.bat",
            "exists": True,
            "status": "loaded",
            "missing_steps": [],
            "order_blockers": [],
            "prohibited_tokens_present": ["--append"],
        }
        with patch.object(health, "query_task", return_value=(0, TASK_OUTPUT, "")):
            with patch.object(health, "_inspect_batch_file", return_value=batch):
                report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_config_blocked")
        self.assertIn("batch_prohibited_token:--append", report["blockers"])

    def test_write_outputs_creates_readback_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")
            report["status"] = "scheduler_ready_for_next_market_window"
            report["task"] = health.parse_schtasks_list(TASK_OUTPUT)
            report["blockers"] = []

            artifacts = health.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "regular_options_strict_forward_30_scheduler_health_latest.json").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
