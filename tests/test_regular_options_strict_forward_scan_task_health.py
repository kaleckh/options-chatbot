import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_regular_options_strict_forward_scan_task_health as health


SCAN_OUTPUT = r"""
Folder: \
HostName:                             KAESDEVICE
TaskName:                             \OptionsScanPicks
Next Run Time:                        6/29/2026 11:00:00 AM
Status:                               Ready
Last Result:                          0
Task To Run:                          C:\Users\kalec\options-chatbot\scripts\run_scan_picks.bat
Scheduled Task State:                 Enabled
Start Time:                           11:00:00 AM
Days:                                 MON, TUE, WED, THU, FRI
"""

SAFETY_OUTPUT = r"""
Folder: \
HostName:                             KAESDEVICE
TaskName:                             \OptionsScanPicksSafetyNet
Next Run Time:                        6/29/2026 11:30:00 AM
Status:                               Ready
Last Result:                          0
Task To Run:                          C:\Users\kalec\options-chatbot\scripts\run_scan_picks_safety_net.bat
Scheduled Task State:                 Enabled
Start Time:                           11:30:00 AM
Days:                                 MON, TUE, WED, THU, FRI
"""


def _query(task_name: str) -> tuple[int, str, str]:
    if task_name == r"\OptionsScanPicks":
        return 0, SCAN_OUTPUT, ""
    if task_name == r"\OptionsScanPicksSafetyNet":
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
            report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")

        self.assertEqual(report["status"], "scan_tasks_ready_for_next_market_window")
        self.assertEqual(report["blockers"], [])
        self.assertFalse(report["safety"]["append_allowed"])
        self.assertFalse(report["safety"]["auto_track_allowed"])

    def test_missing_forced_sweep_batch_step_blocks(self):
        with (
            patch.object(health, "query_task", side_effect=_query),
            patch.object(
                health,
                "_inspect_batch_file",
                return_value=_batch_report(missing_steps=["scripts\\run_forward_cohort_scan_sweep.py --force"]),
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
            patch.object(health, "_inspect_batch_file", return_value=_batch_report(prohibited_tokens_present=["--append"])),
        ):
            report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")

        self.assertEqual(report["status"], "scan_task_config_blocked")
        self.assertIn(r"\OptionsScanPicksSafetyNet:batch_prohibited_token:--append", report["blockers"])

    def test_mispointed_task_blocks(self):
        bad_output = SCAN_OUTPUT.replace("run_scan_picks.bat", "unsafe.bat")

        def query(task_name: str) -> tuple[int, str, str]:
            if task_name == r"\OptionsScanPicks":
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
                patch.object(health, "_inspect_batch_file", return_value=_batch_report()),
            ):
                report = health.build_report(generated_at_utc="2026-06-27T05:35:00Z")
            artifacts = health.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            doc = (root / "doc.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Strict Forward Scan Task Health", doc)
        self.assertIn("scan_tasks_ready_for_next_market_window", doc)


if __name__ == "__main__":
    unittest.main()
