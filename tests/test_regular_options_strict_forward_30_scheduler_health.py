import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_30_scheduler_health as health


TASK_OUTPUT = rf"""
Folder: \
HostName:                             KAESDEVICE
TaskName:                             \OptionsStrictForward30Collector
Next Run Time:                        6/29/2026 7:35:00 AM
Status:                               Ready
Task To Run:                          {health.EXPECTED_TASK_TO_RUN}
Scheduled Task State:                 Enabled
Last Run Time:                        11/30/1999 12:00:00 AM
Last Result:                          0
Number of Missed Runs:                0
Start Date:                           6/29/2026
Start Time:                           7:35:00 AM
Stop Task If Runs X Hours and X Mins: 00:45:00
Repeat: Every:                        0 Hour(s), 30 Minute(s)
Repeat: Until: Duration:              6 Hour(s), 30 Minute(s)
"""

OBSERVED_OK_TASK_OUTPUT = TASK_OUTPUT.replace(
    "Last Run Time:                        11/30/1999 12:00:00 AM",
    "Last Run Time:                        6/29/2026 7:35:05 AM",
).replace("Next Run Time:                        6/29/2026 7:35:00 AM", "Next Run Time:                        6/29/2026 8:05:00 AM")

READY_BATCH = {
    "path": "scripts/run_strict_forward_30_auto_window_collector.bat",
    "exists": True,
    "status": "loaded",
    "missing_steps": [],
    "order_blockers": [],
    "prohibited_tokens_present": [],
}


def _ready_batch():
    return {key: list(value) if isinstance(value, list) else value for key, value in READY_BATCH.items()}


def _build_report_with_task(output: str, *, generated_at_utc: str = "2026-06-27T02:00:00Z"):
    with patch.object(health, "query_task", return_value=(0, output, "")):
        with patch.object(health, "_inspect_batch_file", return_value=_ready_batch()):
            return health.build_report(generated_at_utc=generated_at_utc)


def _drop_lines(output: str, prefixes: tuple[str, ...]) -> str:
    return "\n".join(
        line
        for line in output.splitlines()
        if not any(line.startswith(prefix) for prefix in prefixes)
    )


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
        report = _build_report_with_task(TASK_OUTPUT)

        self.assertEqual(report["status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["config_status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["batch_file"]["status"], "loaded")
        self.assertEqual(report["batch_file"]["missing_steps"], [])
        self.assertFalse(report["safety"]["append_allowed"])
        self.assertFalse(report["safety"]["auto_track_allowed"])
        self.assertEqual(report["runtime_status"], "scheduler_runtime_pending_first_expected_run")
        self.assertEqual(report["runtime_blockers"], [])

    def test_runtime_pending_for_configured_never_run_before_first_expected_run(self):
        fields = health.parse_schtasks_list(TASK_OUTPUT.replace("Last Result:                          0", "Last Result:                          267011"))

        with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 7, 0, 0)):
            runtime = health.build_runtime_telemetry(fields, returncode=0, generated_at_utc="2026-06-29T13:00:00Z")

        self.assertEqual(runtime["status"], "scheduler_runtime_pending_first_expected_run")
        self.assertFalse(runtime["runtime_blocking"])
        self.assertEqual(runtime["blockers"], [])
        self.assertTrue(runtime["parsed"]["last_run_time_is_never_run_sentinel"])

    def test_runtime_observed_ok_after_successful_run(self):
        fields = health.parse_schtasks_list(OBSERVED_OK_TASK_OUTPUT)

        with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 7, 50, 0)):
            runtime = health.build_runtime_telemetry(fields, returncode=0, generated_at_utc="2026-06-29T13:50:00Z")

        self.assertEqual(runtime["status"], "scheduler_runtime_observed_ok")
        self.assertFalse(runtime["runtime_blocking"])
        self.assertEqual(runtime["parsed"]["last_result_code"], 0)

    def test_runtime_failed_for_nonzero_last_result_after_observed_run(self):
        failed = OBSERVED_OK_TASK_OUTPUT.replace("Last Result:                          0", "Last Result:                          1")
        fields = health.parse_schtasks_list(failed)

        with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 7, 50, 0)):
            runtime = health.build_runtime_telemetry(fields, returncode=0, generated_at_utc="2026-06-29T13:50:00Z")

        self.assertEqual(runtime["status"], "scheduler_runtime_failed")
        self.assertTrue(runtime["runtime_blocking"])
        self.assertIn("scheduler_runtime_last_result_nonzero", runtime["blockers"])

    def test_runtime_stale_for_old_last_run_after_expected_run(self):
        stale = OBSERVED_OK_TASK_OUTPUT.replace(
            "Last Run Time:                        6/29/2026 7:35:05 AM",
            "Last Run Time:                        6/29/2026 7:35:00 AM",
        ).replace("Next Run Time:                        6/29/2026 8:05:00 AM", "Next Run Time:                        6/29/2026 8:35:00 AM")
        fields = health.parse_schtasks_list(stale)

        with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 8, 15, 0)):
            runtime = health.build_runtime_telemetry(fields, returncode=0, generated_at_utc="2026-06-29T14:15:00Z")

        self.assertEqual(runtime["status"], "scheduler_runtime_stale")
        self.assertTrue(runtime["runtime_blocking"])
        self.assertIn("scheduler_runtime_last_run_stale", runtime["blockers"])

    def test_runtime_stale_for_never_run_after_expected_run_window(self):
        fields = health.parse_schtasks_list(TASK_OUTPUT)

        with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 7, 45, 0)):
            runtime = health.build_runtime_telemetry(fields, returncode=0, generated_at_utc="2026-06-29T13:45:00Z")

        self.assertEqual(runtime["status"], "scheduler_runtime_stale")
        self.assertTrue(runtime["runtime_blocking"])
        self.assertIn("scheduler_runtime_last_run_never_after_expected_window", runtime["blockers"])

    def test_runtime_stale_for_never_run_after_next_run_rolls_forward(self):
        rolled = TASK_OUTPUT.replace("Start Date:                           6/29/2026", "Start Date:                           6/26/2026")

        with patch.object(health, "query_task", return_value=(0, rolled, "")):
            with patch.object(health, "_inspect_batch_file", return_value=_ready_batch()):
                with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 27, 10, 0, 0)):
                    report = health.build_report(generated_at_utc="2026-06-27T16:00:00Z")

        self.assertEqual(report["config_status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scheduler_runtime_stale")
        self.assertIn("scheduler_runtime_last_run_never_after_expected_window", report["runtime_blockers"])

    def test_never_run_with_missing_start_metadata_and_future_next_run_blocks(self):
        missing_start = _drop_lines(TASK_OUTPUT, ("Start Date:", "Start Time:"))

        with patch.object(health, "query_task", return_value=(0, missing_start, "")):
            with patch.object(health, "_inspect_batch_file", return_value=_ready_batch()):
                with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 27, 10, 0, 0)):
                    report = health.build_report(generated_at_utc="2026-06-27T16:00:00Z")

        self.assertEqual(report["config_status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scheduler_runtime_unobservable")
        self.assertIn("scheduler_runtime_never_run_start_metadata_missing_or_unparseable", report["runtime_blockers"])

    def test_runtime_failed_blocks_top_level_status(self):
        failed = OBSERVED_OK_TASK_OUTPUT.replace("Last Result:                          0", "Last Result:                          1")

        with patch.object(health, "query_task", return_value=(0, failed, "")):
            with patch.object(health, "_inspect_batch_file", return_value=_ready_batch()):
                with patch.object(health, "_generated_at_local_naive", return_value=datetime(2026, 6, 29, 7, 50, 0)):
                    report = health.build_report(generated_at_utc="2026-06-29T13:50:00Z")

        self.assertEqual(report["config_status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertIn("scheduler_runtime_blocking:scheduler_runtime_failed", report["blockers"])

    def test_runtime_unobservable_when_all_runtime_fields_missing(self):
        missing = _drop_lines(
            TASK_OUTPUT,
            ("Last Run Time:", "Last Result:", "Next Run Time:", "Number of Missed Runs:"),
        )
        report = _build_report_with_task(missing)

        self.assertEqual(report["config_status"], "scheduler_ready_for_next_market_window")
        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scheduler_runtime_unobservable")
        self.assertIn("scheduler_runtime_fields_missing", report["runtime_blockers"])

    def test_runtime_unobservable_when_required_runtime_field_missing(self):
        missing = _drop_lines(TASK_OUTPUT, ("Last Result:",))
        report = _build_report_with_task(missing)

        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scheduler_runtime_unobservable")
        self.assertIn("scheduler_runtime_last_result_missing", report["runtime_blockers"])

    def test_runtime_unobservable_when_runtime_field_unparseable(self):
        bad = OBSERVED_OK_TASK_OUTPUT.replace("Last Run Time:                        6/29/2026 7:35:05 AM", "Last Run Time:                        not-a-date")
        report = _build_report_with_task(bad)

        self.assertEqual(report["status"], "scheduler_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scheduler_runtime_unobservable")
        self.assertIn("scheduler_runtime_last_run_time_unparseable", report["runtime_blockers"])

    def test_markdown_uses_distinct_runtime_and_windows_state_labels(self):
        report = _build_report_with_task(TASK_OUTPUT)
        markdown = health.render_markdown(report)

        self.assertIn("Scheduler runtime telemetry status:", markdown)
        self.assertIn("Windows task state:", markdown)
        self.assertNotIn("- Runtime status:", markdown)

    def test_missing_task_fails_closed(self):
        with patch.object(health, "query_task", return_value=(1, "", "ERROR: missing")):
            with patch.object(health, "_inspect_batch_file", return_value=_ready_batch()):
                report = health.build_report(generated_at_utc="2026-06-27T02:00:00Z")

        self.assertEqual(report["status"], "scheduler_task_missing_or_unqueryable")
        self.assertIn("schtasks_query_failed", report["blockers"])

    def test_mispointed_task_blocks(self):
        bad = TASK_OUTPUT.replace("run_strict_forward_30_auto_window_collector.bat", "unsafe.bat")
        report = _build_report_with_task(bad)

        self.assertEqual(report["status"], "scheduler_config_blocked")
        self.assertEqual(report["config_status"], "scheduler_config_blocked")
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
            report = _build_report_with_task(TASK_OUTPUT)
            report["status"] = "scheduler_ready_for_next_market_window"
            report["task"] = health.parse_schtasks_list(TASK_OUTPUT)
            report["blockers"] = []

            artifacts = health.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "regular_options_strict_forward_30_scheduler_health_latest.json").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
