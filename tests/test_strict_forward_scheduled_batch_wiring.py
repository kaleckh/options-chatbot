import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StrictForwardScheduledBatchWiringTests(unittest.TestCase):
    def _read(self, name: str) -> str:
        return (ROOT / "scripts" / name).read_text(encoding="utf8")

    def test_scheduled_scan_batches_run_collector_after_forward_sweep(self):
        for name in ("run_scan_picks.bat", "run_scan_picks_safety_net.bat"):
            with self.subTest(name=name):
                text = self._read(name)
                sweep_index = text.index("scripts\\run_forward_cohort_scan_sweep.py")
                collector_index = text.index("scripts\\run_regular_options_strict_forward_30_auto_window_collector.py")
                scheduler_index = text.index("scripts\\build_regular_options_strict_forward_30_scheduler_health.py")
                scan_task_health_index = text.index("scripts\\build_regular_options_strict_forward_scan_task_health.py")
                review_index = text.index("scripts\\build_regular_options_strict_forward_30_candidate_review_packet.py")
                exit_evidence_plan_index = text.index("scripts\\build_regular_options_strict_forward_30_exit_evidence_plan.py")
                exit_stager_index = text.index("scripts\\build_regular_options_strict_forward_30_exit_completion_stager.py")
                lifecycle_index = text.index("scripts\\build_regular_options_strict_forward_30_lifecycle_audit.py")
                monitor_index = text.index("scripts\\build_regular_options_strict_forward_30_completion_monitor.py")

                self.assertLess(sweep_index, collector_index)
                self.assertLess(collector_index, scheduler_index)
                self.assertLess(scheduler_index, scan_task_health_index)
                self.assertLess(scan_task_health_index, review_index)
                self.assertLess(review_index, exit_evidence_plan_index)
                self.assertLess(exit_evidence_plan_index, exit_stager_index)
                self.assertLess(exit_stager_index, lifecycle_index)
                self.assertLess(lifecycle_index, monitor_index)
                self.assertIn("scripts\\run_forward_cohort_scan_sweep.py --force", text)
                self.assertIn("--skip-scan-sweep --json", text)
                self.assertIn("strict_forward_30_auto_window_collector_log.txt", text)
                self.assertIn("strict_forward_30_scheduler_health_log.txt", text)
                self.assertIn("strict_forward_scan_task_health_log.txt", text)
                self.assertIn("strict_forward_30_candidate_review_log.txt", text)
                self.assertIn("strict_forward_30_exit_evidence_plan_log.txt", text)
                self.assertIn("strict_forward_30_exit_completion_stager_log.txt", text)
                self.assertIn("strict_forward_30_lifecycle_audit_log.txt", text)
                self.assertIn("strict_forward_30_completion_monitor_log.txt", text)

    def test_standalone_auto_window_batch_preserves_no_autotrack_gates(self):
        text = self._read("run_strict_forward_30_auto_window_collector.bat")
        collector_index = text.index("scripts\\run_regular_options_strict_forward_30_auto_window_collector.py")
        scheduler_index = text.index("scripts\\build_regular_options_strict_forward_30_scheduler_health.py")
        scan_task_health_index = text.index("scripts\\build_regular_options_strict_forward_scan_task_health.py")
        review_index = text.index("scripts\\build_regular_options_strict_forward_30_candidate_review_packet.py")
        exit_evidence_plan_index = text.index("scripts\\build_regular_options_strict_forward_30_exit_evidence_plan.py")
        exit_stager_index = text.index("scripts\\build_regular_options_strict_forward_30_exit_completion_stager.py")
        lifecycle_index = text.index("scripts\\build_regular_options_strict_forward_30_lifecycle_audit.py")
        monitor_index = text.index("scripts\\build_regular_options_strict_forward_30_completion_monitor.py")

        self.assertIn("set OPTIONS_SCAN_AUTO_TRACK=0", text)
        self.assertIn("set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1", text)
        self.assertIn("set OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1", text)
        self.assertIn(
            "scripts\\run_regular_options_strict_forward_30_auto_window_collector.py --max-attempts 3 --sleep-seconds 300 --json",
            text,
        )
        self.assertLess(collector_index, scheduler_index)
        self.assertLess(scheduler_index, scan_task_health_index)
        self.assertLess(scan_task_health_index, review_index)
        self.assertLess(review_index, exit_evidence_plan_index)
        self.assertLess(exit_evidence_plan_index, exit_stager_index)
        self.assertLess(exit_stager_index, lifecycle_index)
        self.assertLess(lifecycle_index, monitor_index)
        self.assertIn("strict_forward_30_auto_window_collector_log.txt", text)
        self.assertIn("strict_forward_30_scheduler_health_log.txt", text)
        self.assertIn("strict_forward_scan_task_health_log.txt", text)
        self.assertIn("strict_forward_30_candidate_review_log.txt", text)
        self.assertIn("strict_forward_30_exit_evidence_plan_log.txt", text)
        self.assertIn("strict_forward_30_exit_completion_stager_log.txt", text)
        self.assertIn("strict_forward_30_lifecycle_audit_log.txt", text)
        self.assertIn("strict_forward_30_completion_monitor_log.txt", text)
        self.assertNotIn("--append", text)


if __name__ == "__main__":
    unittest.main()
