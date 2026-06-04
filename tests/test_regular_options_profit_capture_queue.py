from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_profit_capture_queue as capture_queue


def _sleeve_row(
    symbol: str,
    lane_id: str,
    *,
    status: str,
    exact: int,
    candidates: int,
    unresolved: int,
    coverage: float,
    profit_factor: float,
    avg_pnl: float,
    median_pnl: float = 0.0,
    reason_codes: list[str] | None = None,
    source_artifacts: list[str] | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "lane_id": lane_id,
        "lane_family": lane_id,
        "status": status,
        "evidence_class": capture_queue.TRUSTED_EXACT,
        "sample_status": "adequate",
        "reason_codes": reason_codes or [],
        "status_reason": "; ".join(reason_codes or []),
        "next_step": "fixture next step",
        "source_artifacts": source_artifacts or [],
        "metrics": {
            "exact_trusted_priced_trades": exact,
            "candidates": candidates,
            "unresolved_rows": unresolved,
            "quote_coverage": coverage,
            "profit_factor": profit_factor,
            "avg_pnl": avg_pnl,
            "median_pnl": median_pnl,
            "win_rate": 70.0,
        },
    }


class RegularOptionsProfitCaptureQueueTests(unittest.TestCase):
    def test_tier_a_requires_clean_exact_and_watch_rows_get_repair_priority(self):
        clean = _sleeve_row(
            "NEM",
            "bullish_pullback_observation",
            status="keep",
            exact=16,
            candidates=16,
            unresolved=0,
            coverage=100.0,
            profit_factor=13.37,
            avg_pnl=84.03,
        )
        watch = _sleeve_row(
            "GOOGL",
            "tracked_winner_primary",
            status="watch",
            exact=34,
            candidates=41,
            unresolved=7,
            coverage=82.93,
            profit_factor=7.14,
            avg_pnl=54.01,
            reason_codes=["quote_coverage_below_97_5", "unresolved_rows_remain"],
        )
        thin = _sleeve_row(
            "CVX",
            "bullish_pullback_observation",
            status="keep",
            exact=8,
            candidates=8,
            unresolved=0,
            coverage=100.0,
            profit_factor=10.0,
            avg_pnl=58.0,
            reason_codes=["sample_status:thin"],
        )

        self.assertEqual(capture_queue.classify_capture_tier(clean), capture_queue.TIER_A)
        self.assertEqual(capture_queue.classify_capture_tier(watch), capture_queue.TIER_B)
        self.assertEqual(capture_queue.evidence_repair_priority(watch, capture_queue.TIER_B), "high")
        self.assertEqual(capture_queue.classify_capture_tier(thin), capture_queue.TIER_B)
        self.assertEqual(
            capture_queue.selection_gate_for_tier(capture_queue.TIER_A)["selection_readiness"],
            capture_queue.READINESS_PAPER_REVIEW,
        )
        self.assertEqual(
            capture_queue.selection_gate_for_tier(capture_queue.TIER_B)["selection_readiness"],
            capture_queue.READINESS_WATCH_REPAIR,
        )

    def test_build_report_surfaces_clean_watch_fresh_blocked_and_quarantine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sleeves = root / "sleeves.json"
            current_policy = root / "current-policy.json"
            starvation = root / "starvation.json"
            googl_replay = root / "googl-replay.json"
            googl_replay.write_text(
                json.dumps(
                    {
                        "unpriced_trades": [
                            {
                                "ticker": "GOOGL",
                                "date": "2025-12-03",
                                "missing_quote_date": "2025-12-29",
                                "unpriced_reason": "missing_exit_quote_for_leg",
                                "missing_short_contract_symbol": "GOOGL260102C00350000",
                                "long_contract_symbol": "GOOGL260102C00320000",
                                "short_contract_symbol": "GOOGL260102C00350000",
                                "long_entry_expiry": "2026-01-02",
                                "short_entry_expiry": "2026-01-02",
                                "long_entry_strike": 320.0,
                                "short_entry_strike": 350.0,
                                "selected_spread": {
                                    "debit_pct_of_width": 29.16,
                                    "bid_ask_pct": 3.67,
                                    "fill_degradation_vs_mid_pct": 2.2,
                                    "long_delta": 0.493,
                                    "short_delta": 0.2214,
                                },
                            }
                        ]
                    }
                ),
                encoding="utf8",
            )
            sleeves.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-02T00:00:00Z",
                        "lane_symbol_rows": [
                            _sleeve_row(
                                "NEM",
                                "bullish_pullback_observation",
                                status="keep",
                                exact=16,
                                candidates=16,
                                unresolved=0,
                                coverage=100.0,
                                profit_factor=13.37,
                                avg_pnl=84.03,
                                median_pnl=80.0,
                            ),
                            _sleeve_row(
                                "GOOGL",
                                "tracked_winner_primary",
                                status="watch",
                                exact=34,
                                candidates=41,
                                unresolved=7,
                                coverage=82.93,
                                profit_factor=7.14,
                                avg_pnl=54.01,
                                median_pnl=45.0,
                                reason_codes=["quote_coverage_below_97_5", "unresolved_rows_remain"],
                                source_artifacts=[str(googl_replay)],
                            ),
                            _sleeve_row(
                                "SPY",
                                "swing",
                                status="keep",
                                exact=14,
                                candidates=14,
                                unresolved=0,
                                coverage=100.0,
                                profit_factor=2.0,
                                avg_pnl=44.48,
                                median_pnl=46.44,
                            ),
                            _sleeve_row(
                                "QQQ",
                                "swing",
                                status="keep",
                                exact=10,
                                candidates=10,
                                unresolved=0,
                                coverage=100.0,
                                profit_factor=2.4,
                                avg_pnl=48.46,
                                median_pnl=52.24,
                            ),
                            _sleeve_row(
                                "TSLA",
                                "high_beta_momentum",
                                status="rejected",
                                exact=10,
                                candidates=10,
                                unresolved=0,
                                coverage=100.0,
                                profit_factor=0.45,
                                avg_pnl=-32.0,
                                median_pnl=-40.0,
                                reason_codes=["adequate_negative_exact_intraday_evidence"],
                            ),
                        ],
                    }
                ),
                encoding="utf8",
            )
            current_policy.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-02T00:01:00Z",
                        "rows": [
                            {
                                "ticker": "NEM",
                                "lane": "bullish_pullback_observation",
                                "current_policy_decision": "would_take_today",
                                "pnl_pct": 80.0,
                                "guardrail_hits": [],
                            },
                            {
                                "ticker": "NEM",
                                "lane": "bullish_pullback_observation",
                                "current_policy_decision": "would_take_today",
                                "pnl_pct": -12.0,
                                "guardrail_hits": [],
                            },
                        ],
                    }
                ),
                encoding="utf8",
            )
            starvation.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-06-02T00:02:00Z",
                        "overall": {"status": "guardrail_starvation_detected"},
                        "playbooks": [
                            {
                                "playbook_id": "swing",
                                "label": "Swing",
                                "returned_picks": [
                                    {
                                        "ticker": "SPY",
                                        "guardrail_decision": "clear",
                                        "guardrail_reasons": [],
                                        "direction": "call",
                                        "expiry": "2026-06-26",
                                        "candidate_execution_label": "executable_opra_paper_candidate",
                                        "debit_pct_of_width": 37.9,
                                        "quality_score": 97.9,
                                    }
                                ],
                            },
                            {
                                "playbook_id": "speculative",
                                "label": "Speculative",
                                "returned_picks": [
                                    {
                                        "ticker": "QQQ",
                                        "guardrail_decision": "blocked",
                                        "guardrail_reasons": ["quality below minimum"],
                                        "direction": "call",
                                        "expiry": "2026-06-08",
                                        "candidate_execution_label": "executable_opra_paper_candidate",
                                        "debit_pct_of_width": 49.9,
                                        "quality_score": 63.6,
                                    }
                                ],
                            },
                        ],
                    }
                ),
                encoding="utf8",
            )

            report = capture_queue.build_report(
                symbol_sleeves_path=sleeves,
                current_policy_path=current_policy,
                guardrail_starvation_path=starvation,
            )

        self.assertEqual(report["status"], "research_paper_capture_queue")
        self.assertFalse(report["live_policy_change"])
        self.assertGreaterEqual(report["summary"]["tier_counts"][capture_queue.TIER_A], 3)
        self.assertEqual(report["summary"]["evidence_repair_priority_counts"]["high"], 1)
        self.assertEqual(report["summary"]["fresh_scan_guardrail_decision_counts"]["clear"], 1)
        self.assertEqual(report["summary"]["fresh_scan_guardrail_decision_counts"]["blocked"], 1)
        readiness_counts = report["summary"]["selection_readiness_counts"]
        self.assertGreaterEqual(readiness_counts[capture_queue.READINESS_PAPER_REVIEW], 3)
        self.assertEqual(readiness_counts[capture_queue.READINESS_WATCH_REPAIR], 1)
        self.assertEqual(readiness_counts[capture_queue.READINESS_FRESH_SIGNATURE], 1)
        self.assertEqual(readiness_counts[capture_queue.READINESS_BLOCKED], 1)
        self.assertEqual(readiness_counts[capture_queue.READINESS_DO_NOT_CHASE], 1)
        self.assertEqual(len(report["blocked_but_interesting"]), 1)
        self.assertEqual(report["blocked_but_interesting"][0]["symbol"], "QQQ")
        self.assertEqual(report["evidence_repair_queue"][0]["symbol"], "GOOGL")
        self.assertEqual(report["evidence_repair_queue"][0]["selection_readiness"], capture_queue.READINESS_WATCH_REPAIR)
        repair_summary = report["evidence_repair_queue"][0]["repair_target_summary"]
        self.assertEqual(repair_summary["detail_status"], "available")
        self.assertEqual(repair_summary["missing_leg_counts"], {"short": 1})
        self.assertEqual(repair_summary["missing_quote_dates"], ["2025-12-29"])
        self.assertIn("GOOGL260102C00350000", repair_summary["contracts"])
        promotion_gap = report["evidence_repair_queue"][0]["tier_a_promotion_gap"]
        self.assertFalse(promotion_gap["eligible_now"])
        self.assertIn("zero_unresolved_rows", {gate["gate"] for gate in promotion_gap["blocking_gates"]})
        self.assertEqual(report["quarantine_queue"][0]["symbol"], "TSLA")
        nem = next(row for row in report["capture_queue"] if row["symbol"] == "NEM")
        self.assertEqual(nem["selection_readiness"], capture_queue.READINESS_PAPER_REVIEW)
        self.assertEqual(nem["current_policy_overlay"]["negative_count"], 1)
        self.assertEqual(nem["current_policy_overlay"]["decision_counts"]["would_take_today"], 2)


if __name__ == "__main__":
    unittest.main()
