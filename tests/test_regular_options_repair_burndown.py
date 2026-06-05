from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_repair_burndown as burndown
from scripts.regular_options_repair_targets import repair_attempt_key


def _repair_row(
    symbol: str,
    lane_id: str,
    *,
    priority: str = "high",
    source_artifact: str = "data/options-validation/runs/source.json",
    contract_symbol: str = "GOOGL260102C00350000",
    missing_quote_date: str = "2025-12-29",
    attempts: list[dict] | None = None,
    detail_status: str = "available",
) -> dict:
    targets = []
    if detail_status == "available":
        targets.append(
            {
                "source_artifact": source_artifact,
                "ticker": symbol,
                "entry_date": "2025-12-03",
                "missing_quote_date": missing_quote_date,
                "contracts": [contract_symbol],
                "missing_leg_role": "short",
                "unpriced_reason": "missing_exit_quote_for_leg",
                "selected_spread": {"debit_pct_of_width": 29.16},
                "latest_repair_attempts": attempts or [],
            }
        )
    return {
        "capture_tier": "tier_b_profitable_watch_repair",
        "selection_readiness": "watch_repair_only",
        "symbol": symbol,
        "lane_id": lane_id,
        "lane_family": lane_id,
        "evidence_repair_priority": priority,
        "repair_actionability": {
            "status": "needs_status_or_forward_validation_after_repair",
            "target_count": len(targets),
            "attempt_count": len(attempts or []),
        },
        "tier_a_promotion_gap": {
            "blocking_gates": [
                {"gate": "zero_unresolved_rows", "current": 1, "target": 0},
                {"gate": "quote_coverage", "current": 90.0, "target": 97.5},
            ]
        },
        "rank_score": 500.0,
        "metrics": {
            "exact_trusted_priced_trades": 9,
            "unresolved_rows": 1,
            "quote_coverage": 90.0,
            "profit_factor": 4.9,
            "avg_pnl": 51.6,
            "median_pnl": 4.36,
        },
        "repair_target_summary": {
            "detail_status": detail_status,
            "targets": targets,
            "source_artifacts": [source_artifact],
        },
    }


def _attempt(
    *,
    source_artifact: str,
    symbol: str,
    contract_symbol: str,
    missing_quote_date: str,
    outcome: str,
    proof_repair_status: str,
    exact_rows: int = 0,
    lookahead_rows: int = 0,
    exhausted: bool = False,
) -> dict:
    return {
        "repair_attempt_key": repair_attempt_key(
            source_artifact=source_artifact,
            ticker=symbol,
            contract_symbol=contract_symbol,
            missing_quote_date=missing_quote_date,
        ),
        "summary_path": "data/options-validation/thetadata-nbbo/summary.json",
        "summary_generated_at_utc": "2026-06-04T11:00:00Z",
        "outcome": outcome,
        "proof_repair_status": proof_repair_status,
        "exact_missing_date_status": "rows_found" if exact_rows else "no_rows_found",
        "exact_date_row_count": exact_rows,
        "lookahead_row_count": lookahead_rows,
        "total_row_count": exact_rows + lookahead_rows,
        "available_quote_dates": [missing_quote_date] if exact_rows else ["2025-12-30"] if lookahead_rows else [],
        "first_available_after_missing_date": "2025-12-30" if lookahead_rows else None,
        "current_source_exhausted_for_exact_date": exhausted,
    }


class RegularOptionsRepairBurndownTests(unittest.TestCase):
    def test_burndown_separates_active_replay_diagnostic_and_exhausted_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profit_queue = root / "profit-queue.json"
            repair_attempts = root / "repair-attempts.json"
            source = "data/options-validation/runs/source.json"
            imported = _attempt(
                source_artifact=source,
                symbol="NEM",
                contract_symbol="NEM251107C00093000",
                missing_quote_date="2025-10-27",
                outcome="imported_pending_replay",
                proof_repair_status="exact_date_imported_pending_replay",
                exact_rows=12,
            )
            lookahead = _attempt(
                source_artifact=source,
                symbol="WMT",
                contract_symbol="WMT260402C00140000",
                missing_quote_date="2026-03-25",
                outcome="lookahead_only_rows_found",
                proof_repair_status="lookahead_only_not_exact_proof",
                lookahead_rows=3,
                exhausted=True,
            )
            exhausted = _attempt(
                source_artifact=source,
                symbol="UNH",
                contract_symbol="UNH251205C00390000",
                missing_quote_date="2025-11-20",
                outcome="exact_date_no_match",
                proof_repair_status="current_source_exhausted",
                exhausted=True,
            )
            plan_only = _attempt(
                source_artifact=source,
                symbol="AAPL",
                contract_symbol="AAPL251226C00290000",
                missing_quote_date="2026-01-13",
                outcome="planned_not_requested",
                proof_repair_status="planned_not_requested",
            )
            profit_queue.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "summary": {"high_priority_evidence_repair_count": 5},
                        "evidence_repair_queue": [
                            _repair_row("GOOGL", "tracked_winner_primary"),
                            _repair_row(
                                "NEM",
                                "bullish_pullback_observation",
                                contract_symbol="NEM251107C00093000",
                                missing_quote_date="2025-10-27",
                                attempts=[imported],
                            ),
                            _repair_row(
                                "WMT",
                                "relative_strength_pullback",
                                contract_symbol="WMT260402C00140000",
                                missing_quote_date="2026-03-25",
                            ),
                            _repair_row(
                                "UNH",
                                "sleeve_next_index_refill_v1",
                                contract_symbol="UNH251205C00390000",
                                missing_quote_date="2025-11-20",
                            ),
                            _repair_row(
                                "AAPL",
                                "bullish_pullback_observation",
                                contract_symbol="AAPL251226C00290000",
                                missing_quote_date="2026-01-13",
                            ),
                        ],
                    }
                ),
                encoding="utf8",
            )
            repair_attempts.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:01:00Z",
                        "summary": {"latest_attempt_count": 3, "input_summary_count": 3},
                        "latest_attempts": [lookahead, exhausted, plan_only],
                    }
                ),
                encoding="utf8",
            )

            report = burndown.build_report(
                profit_capture_queue_path=profit_queue,
                repair_attempts_path=repair_attempts,
            )

        summary = report["summary"]
        self.assertEqual(summary["active_exact_repair_target_count"], 2)
        self.assertEqual(summary["source_replay_required_target_count"], 1)
        self.assertEqual(summary["diagnostic_lookahead_only_target_count"], 1)
        self.assertEqual(summary["exhausted_current_source_target_count"], 1)
        self.assertEqual(
            {row["symbol"]: row["burndown_status"] for row in report["active_exact_repair_targets"]},
            {
                "GOOGL": burndown.STATUS_ACTIVE_UNATTEMPTED,
                "AAPL": burndown.STATUS_ACTIVE_PLAN_ONLY,
            },
        )
        self.assertEqual(report["source_replay_required_targets"][0]["symbol"], "NEM")
        self.assertIn("rerun the source replay", report["source_replay_required_targets"][0]["next_action"].lower())
        self.assertEqual(report["diagnostic_lookahead_only_targets"][0]["symbol"], "WMT")
        self.assertEqual(report["exhausted_current_source_targets"][0]["symbol"], "UNH")
        self.assertIn("--plan-only --json", report["active_exact_repair_targets"][0]["commands"]["plan_only"])

    def test_missing_repair_target_details_are_not_active_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profit_queue = root / "profit-queue.json"
            repair_attempts = root / "repair-attempts.json"
            profit_queue.write_text(
                json.dumps(
                    {
                        "evidence_repair_queue": [
                            _repair_row("LLY", "bullish_pullback_observation", detail_status="source_artifacts_missing")
                        ]
                    }
                ),
                encoding="utf8",
            )
            repair_attempts.write_text(json.dumps({"latest_attempts": [], "summary": {}}), encoding="utf8")

            report = burndown.build_report(
                profit_capture_queue_path=profit_queue,
                repair_attempts_path=repair_attempts,
            )

        self.assertEqual(report["summary"]["active_exact_repair_target_count"], 0)
        self.assertEqual(report["summary"]["target_details_missing_count"], 1)
        self.assertEqual(
            report["target_details_missing_rows"][0]["burndown_status"],
            burndown.STATUS_TARGET_DETAILS_MISSING,
        )

    def test_missing_repair_attempt_memory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profit_queue = root / "profit-queue.json"
            missing_repair_attempts = root / "missing-repair-attempts.json"
            profit_queue.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "summary": {"high_priority_evidence_repair_count": 1},
                        "evidence_repair_queue": [_repair_row("GOOGL", "tracked_winner_primary")],
                    }
                ),
                encoding="utf8",
            )

            report = burndown.build_report(
                profit_capture_queue_path=profit_queue,
                repair_attempts_path=missing_repair_attempts,
            )

        summary = report["summary"]
        self.assertEqual(report["status"], "repair_burndown_memory_unavailable")
        self.assertEqual(summary["target_count"], 1)
        self.assertEqual(summary["active_exact_repair_target_count"], 0)
        self.assertEqual(summary["repair_attempt_memory_unavailable_count"], 1)
        self.assertEqual(report["active_exact_repair_targets"], [])
        unavailable = report["repair_attempt_memory_unavailable_rows"][0]
        self.assertEqual(unavailable["burndown_status"], burndown.STATUS_MEMORY_UNAVAILABLE)
        self.assertEqual(unavailable["commands"], {})
        self.assertIn("Rebuild the repair-attempt readback", summary["next_operator_step"])

    def test_unreadable_repair_attempt_memory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profit_queue = root / "profit-queue.json"
            unreadable_repair_attempts = root / "repair-attempts.json"
            profit_queue.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "summary": {"high_priority_evidence_repair_count": 1},
                        "evidence_repair_queue": [_repair_row("GOOGL", "tracked_winner_primary")],
                    }
                ),
                encoding="utf8",
            )
            unreadable_repair_attempts.write_text("{not json", encoding="utf8")

            report = burndown.build_report(
                profit_capture_queue_path=profit_queue,
                repair_attempts_path=unreadable_repair_attempts,
            )

        summary = report["summary"]
        repair_attempt_input = report["inputs"][1]
        self.assertEqual(report["status"], "repair_burndown_memory_unavailable")
        self.assertEqual(summary["active_exact_repair_target_count"], 0)
        self.assertEqual(summary["repair_attempt_memory_unavailable_count"], 1)
        self.assertEqual(report["repair_attempt_memory_unavailable_rows"][0]["commands"], {})
        self.assertTrue(repair_attempt_input["status"].startswith("unreadable:"))

    def test_duplicate_target_rows_are_collapsed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profit_queue = root / "profit-queue.json"
            repair_attempts = root / "repair-attempts.json"
            duplicate = _repair_row("DIA", "tracked_winner_cheap_debit_continuity_v1")
            profit_queue.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-04T12:00:00Z",
                        "evidence_repair_queue": [duplicate, duplicate],
                    }
                ),
                encoding="utf8",
            )
            repair_attempts.write_text(json.dumps({"latest_attempts": [], "summary": {}}), encoding="utf8")

            report = burndown.build_report(
                profit_capture_queue_path=profit_queue,
                repair_attempts_path=repair_attempts,
            )

        self.assertEqual(report["summary"]["target_count"], 1)
        self.assertEqual(report["summary"]["active_exact_repair_target_count"], 1)


if __name__ == "__main__":
    unittest.main()
