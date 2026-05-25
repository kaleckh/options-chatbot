from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.summarize_profitability_research import build_research_summary
from workspace_tempdir import WorkspaceTempDir


class SummarizeProfitabilityResearchTests(unittest.TestCase):
    def test_build_research_summary_reads_lab_and_exit_artifacts(self):
        tmp = WorkspaceTempDir(prefix="profit-summary")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        lab_run = root / "runs" / "profit_lab_test"
        lab_run.mkdir(parents=True)
        (lab_run / "report.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-24T00:00:00Z",
                    "variants": [
                        {
                            "id": "bullish_index_calls_score70",
                            "status": "evaluated",
                            "verdict": {"status": "block", "promotion_allowed": False},
                            "summary": {
                                "source": {"pricing_lane": "pessimistic", "lookback_years": 2, "n_picks": 3},
                                "overall": {"trades": 43, "profit_factor": 0.57, "avg_pnl_pct": -11.39},
                            },
                        }
                    ],
                }
            ),
            encoding="utf8",
        )
        exit_dir = root / "exit-sweeps"
        exit_dir.mkdir()
        (exit_dir / "exit_sweep_test.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "variant": "bullish_index_calls_score70",
                            "pricing_lane": "pessimistic",
                            "lookback_years": 2,
                            "n_picks": 3,
                            "spread_stop_loss_pct": 90,
                            "spread_time_exit_pct": 55,
                            "summary": {"trade_count": 43, "profit_factor": 0.57, "gate_passed": False},
                        }
                    ]
                }
            ),
            encoding="utf8",
        )
        audit_dir = root / "losing-window-audits"
        audit_dir.mkdir()
        (audit_dir / "losing_window_audit_test.json").write_text(
            json.dumps(
                {
                    "source_run": "run.json",
                    "playbook": "bullish_index_calls_score70",
                    "pricing_lane": "pessimistic",
                    "lookback_years": 2,
                    "n_picks": 3,
                    "exact_trade_metrics": {"trades": 43, "profit_factor": 0.57, "avg_pnl_pct": -11.39},
                    "losing_trade_count": 20,
                    "worst_groups": [{"dimension": "ticker", "key": "QQQ", "avg_pnl_pct": -15.0}],
                    "candidate_filters": [{"dimension": "debit", "key": "debit<50%", "profit_factor": 1.9}],
                }
            ),
            encoding="utf8",
        )
        hypothesis_dir = root / "hypothesis-sweeps"
        hypothesis_dir.mkdir()
        (hypothesis_dir / "hypothesis_sweep_test.json").write_text(
            json.dumps(
                {
                    "source_run": "run.json",
                    "playbook": "bullish_index_calls_score70",
                    "pricing_lane": "pessimistic",
                    "lookback_years": 2,
                    "n_picks": 3,
                    "baseline": {"trades": 43, "profit_factor": 0.57},
                    "hypothesis_count": 10,
                    "results": [{"id": "max_debit_lt_50", "verdict": "candidate_for_replay"}],
                }
            ),
            encoding="utf8",
        )
        exact_dir = root / "exact-coverage-audits"
        exact_dir.mkdir()
        (exact_dir / "exact_coverage_audit_test.json").write_text(
            json.dumps(
                {
                    "source_run": "run.json",
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "overall": {"total": 65, "exact": 11, "nearest": 54, "exact_pct": 16.9},
                    "by_ticker": [{"key": "SPY", "exact_pct": 20.0}],
                    "next_data_need": "Collect more exact rows.",
                }
            ),
            encoding="utf8",
        )
        checklist_dir = root / "promotion-checklists"
        checklist_dir.mkdir()
        (checklist_dir / "promotion_checklist_test.json").write_text(
            json.dumps(
                {
                    "source_run": "run.json",
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "promotion_allowed": False,
                    "requirements": [{"id": "exact_historical_trade_count", "current": 11}],
                    "next_actions": ["Collect more exact rows."],
                }
            ),
            encoding="utf8",
        )
        canary_dir = root / "canary-status"
        canary_dir.mkdir()
        (canary_dir / "canary_status_test.json").write_text(
            json.dumps(
                {
                    "source_run": "run.json",
                    "canary_id": "quality90_debit55_canary",
                    "cohort_role": "proof_control_yardstick",
                    "readiness": "research_positive_needs_exact_proof",
                    "promotion_allowed": False,
                    "research_signal": {"profit_factor": 2.4},
                    "proof_signal": {"trade_count": 11, "profit_factor": 0.97},
                    "exact_coverage": {"exact_pct": 16.9},
                    "interpretation": {"current_claim": "Research-positive, not promotable."},
                }
            ),
            encoding="utf8",
        )
        forward_dir = root / "forward-evidence"
        forward_dir.mkdir()
        (forward_dir / "forward_evidence_test.json").write_text(
            json.dumps(
                {
                    "cohort_id": "quality90_debit55_canary",
                    "readiness": "no_forward_evidence_yet",
                    "promotion_allowed": False,
                    "progress": {"closed_forward_trade_count": 0, "closed_forward_needed": 20},
                    "target": {"closed_forward_trade_count": 20},
                }
            ),
            encoding="utf8",
        )
        sample_plan_dir = root / "exact-sample-plans"
        sample_plan_dir.mkdir()
        (sample_plan_dir / "exact_sample_plan_test.json").write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_quality90_debit55",
                    "targets": {"exact_historical_trade_count": 40},
                    "current": {"exact_historical_trade_count": 11},
                    "gaps": {"exact_historical_trades_needed": 29},
                    "collection_order": [{"id": "collect_forward_canary_outcomes"}],
                }
            ),
            encoding="utf8",
        )
        tracked_winner_dir = root / "tracked-winner-profiles"
        tracked_winner_dir.mkdir()
        (tracked_winner_dir / "tracked_winner_profile_test.json").write_text(
            json.dumps(
                {
                    "overall": {"count": 20, "profit_factor": 16.3},
                    "winners": {"count": 17, "avg_pnl_pct": 36.99},
                    "winner_count_by_ticker": {"SPY": 5},
                    "candidate_lane": {"id": "tracked_winner_observation", "status": "candidate"},
                    "limitations": ["Open tracked P&L is marked-to-market."],
                }
            ),
            encoding="utf8",
        )
        readiness_dir = root / "paid-data-readiness"
        readiness_dir.mkdir()
        (readiness_dir / "paid_data_readiness_test.json").write_text(
            json.dumps(
                {
                    "status": "not_ready",
                    "blocker": "missing_required_underlyings",
                    "snapshot_kind": "daily_eod",
                    "required_underlyings": ["SPY", "QQQ", "GOOGL"],
                    "missing_required_underlyings": ["GOOGL"],
                    "thin_required_underlyings": [],
                    "low_executable_required_underlyings": [],
                    "shared_required_quote_dates": {"count": 490},
                    "next_actions": ["Import trusted option history for missing required symbols: GOOGL."],
                }
            ),
            encoding="utf8",
        )

        summary = build_research_summary(
            lab_runs=root / "runs",
            exit_sweeps=exit_dir,
            losing_audits=audit_dir,
            hypothesis_sweeps=hypothesis_dir,
            exact_coverage_audits=exact_dir,
            promotion_checklists=checklist_dir,
            canary_status=canary_dir,
            forward_evidence=forward_dir,
            exact_sample_plans=sample_plan_dir,
            tracked_winner_profiles=tracked_winner_dir,
            paid_data_readiness=readiness_dir,
        )

        self.assertEqual(summary["variant_run_count"], 1)
        self.assertEqual(summary["exit_sweep_count"], 1)
        self.assertEqual(summary["losing_audit_count"], 1)
        self.assertEqual(summary["hypothesis_sweep_count"], 1)
        self.assertEqual(summary["exact_coverage_audit_count"], 1)
        self.assertEqual(summary["promotion_checklist_count"], 1)
        self.assertEqual(summary["canary_status_count"], 1)
        self.assertEqual(summary["forward_evidence_count"], 1)
        self.assertEqual(summary["exact_sample_plan_count"], 1)
        self.assertEqual(summary["tracked_winner_profile_count"], 1)
        self.assertEqual(summary["paid_data_readiness_count"], 1)
        self.assertEqual(summary["variant_runs"][0]["variant"], "bullish_index_calls_score70")
        self.assertEqual(summary["exit_sweeps"][0]["spread_stop_loss_pct"], 90)
        self.assertEqual(summary["losing_window_audits"][0]["top_worst_groups"][0]["key"], "QQQ")
        self.assertEqual(summary["losing_window_audits"][0]["top_candidate_filters"][0]["key"], "debit<50%")
        self.assertEqual(summary["hypothesis_sweeps"][0]["top_results"][0]["id"], "max_debit_lt_50")
        self.assertEqual(summary["exact_coverage_audits"][0]["overall"]["exact"], 11)
        self.assertEqual(summary["promotion_checklists"][0]["requirements"][0]["current"], 11)
        self.assertEqual(summary["canary_statuses"][0]["readiness"], "research_positive_needs_exact_proof")
        self.assertEqual(summary["forward_evidence"][0]["progress"]["closed_forward_needed"], 20)
        self.assertEqual(summary["exact_sample_plans"][0]["gaps"]["exact_historical_trades_needed"], 29)
        self.assertEqual(summary["tracked_winner_profiles"][0]["candidate_lane"]["status"], "candidate")
        self.assertEqual(summary["paid_data_readiness"][0]["missing_required_underlyings"], ["GOOGL"])


if __name__ == "__main__":
    unittest.main()
