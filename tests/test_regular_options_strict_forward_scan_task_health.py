import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_scan_task_health as health


SCAN_TASK = r"\OptionsScanPicks"
SAFETY_TASK = r"\OptionsScanPicksSafetyNet"


def _task_output(
    task_name: str,
    *,
    next_run: str = "6/30/2026 11:00:00 AM",
    status: str = "Ready",
    last_run: str | None = "6/29/2026 11:00:00 AM",
    last_result: str | None = "0",
    missed_runs: str | None = "0",
    scheduled_state: str = "Enabled",
    start_date: str | None = "6/29/2026",
    start_time: str | None = None,
    task_to_run: str | None = None,
) -> str:
    expected = health.EXPECTED_TASKS[task_name]
    resolved_start_time = start_time or str(expected["start_time"])
    resolved_task_to_run = task_to_run or str(expected["batch_file"])
    lines = [
        "Folder: \\",
        "HostName:                             KAESDEVICE",
        f"TaskName:                             {task_name}",
        f"Next Run Time:                        {next_run}",
        f"Status:                               {status}",
    ]
    if last_run is not None:
        lines.append(f"Last Run Time:                        {last_run}")
    if last_result is not None:
        lines.append(f"Last Result:                          {last_result}")
    if missed_runs is not None:
        lines.append(f"Number of Missed Runs:                {missed_runs}")
    lines.extend(
        [
            f"Task To Run:                          {resolved_task_to_run}",
            f"Scheduled Task State:                 {scheduled_state}",
        ]
    )
    if start_date is not None:
        lines.append(f"Start Date:                           {start_date}")
    lines.extend(
        [
            f"Start Time:                           {resolved_start_time}",
            "Days:                                 MON, TUE, WED, THU, FRI",
        ]
    )
    return "\n".join(lines) + "\n"


SCAN_OUTPUT = _task_output(SCAN_TASK)
SAFETY_OUTPUT = _task_output(
    SAFETY_TASK, next_run="6/30/2026 11:30:00 AM", last_run="6/29/2026 11:30:00 AM"
)


def _query(task_name: str) -> tuple[int, str, str]:
    if task_name == SCAN_TASK:
        return 0, SCAN_OUTPUT, ""
    if task_name == SAFETY_TASK:
        return 0, SAFETY_OUTPUT, ""
    return 1, "", "missing"


def _batch_report(**overrides):
    payload = {
        "path": "scripts/run_scan_picks.bat",
        "exists": True,
        "status": "loaded",
        "missing_steps": [],
        "order_blockers": [],
        "prohibited_tokens_present": [],
    }
    payload.update(overrides)
    return payload


class RegularOptionsStrictForwardScanTaskHealthTests(unittest.TestCase):
    def test_ready_scan_tasks_pass(self):
        with (
            patch.object(health, "query_task", side_effect=_query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T18:00:00Z")

        self.assertEqual(report["status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(report["config_status"], "scan_tasks_config_ready")
        self.assertEqual(report["runtime_status"], "scan_task_runtime_observed_ok")
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["runtime_blockers"], [])
        self.assertFalse(report["safety"]["append_allowed"])
        self.assertFalse(report["safety"]["auto_track_allowed"])

    def test_never_run_before_first_expected_run_is_pending_not_blocked(self):
        scan_output = _task_output(
            SCAN_TASK,
            next_run="6/29/2026 11:00:00 AM",
            last_run="N/A",
        )
        safety_output = _task_output(
            SAFETY_TASK,
            next_run="6/29/2026 11:30:00 AM",
            last_run="N/A",
        )

        def query(task_name: str) -> tuple[int, str, str]:
            return (
                (0, scan_output, "")
                if task_name == SCAN_TASK
                else (0, safety_output, "")
            )

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T00:00:00Z")

        self.assertEqual(report["status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(
            report["runtime_status"], "scan_task_runtime_pending_first_expected_run"
        )
        self.assertEqual(report["runtime_blockers"], [])
        self.assertEqual(
            report["task_reports"][SCAN_TASK]["runtime_status"],
            "scan_task_runtime_pending_first_expected_run",
        )

    def test_observed_runtime_ok_is_reported_per_task(self):
        with (
            patch.object(health, "query_task", side_effect=_query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T18:00:00Z")

        self.assertEqual(report["runtime_status"], "scan_task_runtime_observed_ok")
        self.assertEqual(
            report["task_reports"][SCAN_TASK]["runtime_status"],
            "scan_task_runtime_observed_ok",
        )
        self.assertEqual(
            report["task_reports"][SAFETY_TASK]["runtime_status"],
            "scan_task_runtime_observed_ok",
        )

    def test_rolled_forward_missed_daily_feeder_blocks_after_expected_start(self):
        scan_output = _task_output(
            SCAN_TASK,
            next_run="7/1/2026 11:00:00 AM",
            last_run="6/29/2026 11:00:00 AM",
            start_date="6/29/2026",
        )
        safety_output = _task_output(
            SAFETY_TASK,
            next_run="7/1/2026 11:30:00 AM",
            last_run="6/30/2026 11:30:00 AM",
            start_date="6/29/2026",
        )

        def query(task_name: str) -> tuple[int, str, str]:
            return (
                (0, scan_output, "")
                if task_name == SCAN_TASK
                else (0, safety_output, "")
            )

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
            patch.object(
                health,
                "_generated_at_local_naive",
                return_value=health.datetime(2026, 6, 30, 11, 40),
            ),
        ):
            report = health.build_report(generated_at_utc="2026-06-30T17:40:00Z")

        self.assertEqual(report["status"], "scan_task_runtime_blocked")
        self.assertEqual(report["runtime_status"], "scan_task_runtime_blocked")
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_last_run_not_on_expected_scan_date",
            report["runtime_blockers"],
        )
        self.assertEqual(
            report["task_reports"][SAFETY_TASK]["runtime_status"],
            "scan_task_runtime_observed_ok",
        )

    def test_previous_success_before_daily_start_is_not_blocking(self):
        scan_output = _task_output(
            SCAN_TASK,
            next_run="6/30/2026 11:00:00 AM",
            last_run="6/29/2026 11:00:00 AM",
            start_date="6/29/2026",
        )

        def query(task_name: str) -> tuple[int, str, str]:
            return (0, scan_output, "") if task_name == SCAN_TASK else _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
            patch.object(
                health,
                "_generated_at_local_naive",
                return_value=health.datetime(2026, 6, 30, 10, 40),
            ),
        ):
            report = health.build_report(generated_at_utc="2026-06-30T16:40:00Z")

        self.assertEqual(report["status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(
            report["task_reports"][SCAN_TASK]["runtime_status"],
            "scan_task_runtime_observed_ok",
        )

    def test_failed_last_result_blocks_runtime_and_aggregate(self):
        bad_scan_output = _task_output(SCAN_TASK, last_result="1")

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == SCAN_TASK:
                return 0, bad_scan_output, ""
            return _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T18:00:00Z")

        self.assertEqual(report["config_status"], "scan_tasks_config_ready")
        self.assertEqual(report["runtime_status"], "scan_task_runtime_blocked")
        self.assertEqual(report["status"], "scan_task_runtime_blocked")
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_last_result_nonzero",
            report["runtime_blockers"],
        )
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_blocking:scan_task_runtime_failed",
            report["blockers"],
        )

    def test_currently_running_result_is_in_progress_not_failed(self):
        current_scan_output = _task_output(
            SCAN_TASK,
            next_run="7/13/2026 11:00:00 AM",
            last_run="7/10/2026 11:00:00 AM",
            start_date="4/22/2026",
        )
        running_safety_output = _task_output(
            SAFETY_TASK,
            next_run="7/13/2026 11:30:00 AM",
            status="Running",
            last_run="7/10/2026 11:30:00 AM",
            last_result=str(health.SCHEDULER_TASK_RUNNING_RESULT),
            missed_runs="0",
            start_date="5/5/2026",
        )

        def query(task_name: str) -> tuple[int, str, str]:
            return (
                (0, running_safety_output, "")
                if task_name == SAFETY_TASK
                else (0, current_scan_output, "")
            )

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-07-10T17:38:22Z")

        self.assertEqual(report["status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(report["runtime_status"], "scan_task_runtime_in_progress")
        self.assertEqual(report["runtime_blockers"], [])
        self.assertEqual(
            report["task_reports"][SAFETY_TASK]["runtime_status"],
            "scan_task_runtime_in_progress",
        )

    def test_stale_never_run_after_expected_run_blocks(self):
        stale_output = _task_output(
            SCAN_TASK,
            next_run="6/30/2026 11:00:00 AM",
            last_run="N/A",
            start_date="6/29/2026",
        )

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == SCAN_TASK:
                return 0, stale_output, ""
            return _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-30T00:00:00Z")

        self.assertEqual(report["status"], "scan_task_runtime_blocked")
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_last_run_never_after_expected_window",
            report["runtime_blockers"],
        )

    def test_missing_runtime_metadata_blocks(self):
        missing_runtime_output = _task_output(SCAN_TASK, last_run=None)

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == SCAN_TASK:
                return 0, missing_runtime_output, ""
            return _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T18:00:00Z")

        self.assertEqual(report["status"], "scan_task_runtime_blocked")
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_last_run_time_missing",
            report["runtime_blockers"],
        )

    def test_never_run_with_missing_start_metadata_blocks(self):
        missing_start_output = _task_output(SCAN_TASK, last_run="N/A", start_date=None)

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == SCAN_TASK:
                return 0, missing_start_output, ""
            return _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-29T00:00:00Z")

        self.assertEqual(report["status"], "scan_task_runtime_blocked")
        self.assertIn(
            f"{SCAN_TASK}:scan_task_runtime_never_run_start_metadata_missing_or_unparseable",
            report["runtime_blockers"],
        )

    def test_missing_forced_sweep_batch_step_blocks(self):
        with (
            patch.object(health, "query_task", side_effect=_query),
            patch.object(
                health,
                "_inspect_batch_file",
                return_value=_batch_report(
                    missing_steps=["scripts\\run_forward_cohort_scan_sweep.py --force"]
                ),
            ),
        ):
            report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")

        self.assertEqual(report["status"], "scan_task_config_blocked")
        self.assertIn(
            r"\OptionsScanPicks:batch_missing_step:scripts\run_forward_cohort_scan_sweep.py --force",
            report["blockers"],
        )

    def test_append_token_blocks(self):
        with (
            patch.object(health, "query_task", side_effect=_query),
            patch.object(
                health,
                "_inspect_batch_file",
                return_value=_batch_report(prohibited_tokens_present=["--append"]),
            ),
        ):
            report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")

        self.assertEqual(report["status"], "scan_task_config_blocked")
        self.assertIn(
            r"\OptionsScanPicksSafetyNet:batch_prohibited_token:--append",
            report["blockers"],
        )

    def test_batch_inspection_detects_append_script_token_and_autotrack_true_variants(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scan.bat"
            path.write_text(
                "\n".join(
                    [
                        *health.EXPECTED_BATCH_STEPS,
                        "set OPTIONS_SCAN_AUTO_TRACK=true",
                        "set OPTIONS_SCAN_AUTO_TRACK=True",
                        "set OPTIONS_SCAN_AUTO_TRACK=TRUE",
                        "set OPTIONS_SCAN_AUTO_TRACK=1",
                        "uv run --locked python scripts\\Append_Volatility_Expansion_Forward_Paper_Shadow_Rows.py",
                        "APPROVE_PHASE2_FORWARD_COHORT_APPEND",
                    ]
                ),
                encoding="utf8",
            )

            report = health._inspect_batch_file(path)

        self.assertEqual(report["status"], "loaded")
        self.assertEqual(report["missing_steps"], [])
        self.assertIn(
            "APPROVE_PHASE2_FORWARD_COHORT_APPEND", report["prohibited_tokens_present"]
        )
        self.assertIn(
            "append_volatility_expansion_forward_paper_shadow_rows.py",
            report["prohibited_tokens_present"],
        )
        self.assertIn("OPTIONS_SCAN_AUTO_TRACK=1", report["prohibited_tokens_present"])
        self.assertIn(
            "OPTIONS_SCAN_AUTO_TRACK=true", report["prohibited_tokens_present"]
        )
        self.assertIn(
            "OPTIONS_SCAN_AUTO_TRACK=True", report["prohibited_tokens_present"]
        )
        self.assertIn(
            "OPTIONS_SCAN_AUTO_TRACK=TRUE", report["prohibited_tokens_present"]
        )

    def test_mispointed_task_blocks(self):
        bad_output = SCAN_OUTPUT.replace("run_scan_picks.bat", "unsafe.bat")

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == SCAN_TASK:
                return 0, bad_output, ""
            return _query(task_name)

        with (
            patch.object(health, "query_task", side_effect=query),
            patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
        ):
            report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")

        self.assertEqual(report["status"], "scan_task_config_blocked")
        self.assertIn(r"\OptionsScanPicks:task_to_run_mismatch", report["blockers"])

    def test_write_outputs_creates_docs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(health, "query_task", side_effect=_query),
                patch.object(
                    health, "_inspect_batch_file", return_value=_batch_report()
                ),
            ):
                report = health.build_report(generated_at_utc="2026-06-29T18:00:00Z")
            artifacts = health.write_outputs(
                report, output_dir=root / "out", docs_report=root / "doc.md"
            )
            doc = (root / "doc.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Strict Forward Scan Task Health", doc)
        self.assertIn("scan_tasks_ready_for_next_market_window", doc)


if __name__ == "__main__":
    unittest.main()
