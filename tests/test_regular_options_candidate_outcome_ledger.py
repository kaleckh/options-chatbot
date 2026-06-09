from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_candidate_outcome_ledger as ledger


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf8")


def _fresh_candidate(ticker: str, *, key: str, **overrides) -> dict:
    row = {
        "candidate_key": key,
        "scan_date": "2026-06-05",
        "playbook_id": "swing",
        "ticker": ticker,
        "direction": "call",
        "expiry": "2026-06-26",
        "contract_symbol": f"{ticker}260626C00100000",
        "short_contract_symbol": f"{ticker}260626C00110000",
        "candidate_status": "live_validation_attempted",
        "validation_outcome": "created",
        "validation_outcome_reason": "fresh_validation_created_or_confirmed_auto_track_position",
        "entry_evidence_status": "fresh_executable_exact_entry",
        "entry_evidence_reasons": [],
        "fill_attempt_status": "logged",
        "position_link_status": "tracked_position_linked",
        "auto_track_position_id": 42,
        "realized_pnl_status": "missing_realized_pnl",
        "evidence_bridge_status": "exact_exit_pnl_required",
        "evidence_bridge_blockers": ["missing_exact_exit_pnl"],
        "required_next_evidence": ["fresh_executable_exact_opra_nbbo_exit"],
        "promotion_gate_context": "no_lane_promotion_state_payload",
        "promotion_discussion_ready": False,
        "live_policy_change": False,
        "evidence_bridge": {
            "status": "exact_exit_pnl_required",
            "blockers": ["missing_exact_exit_pnl"],
            "required_next_evidence": ["fresh_executable_exact_opra_nbbo_exit"],
            "prohibited_actions": ["do_not_count_midpoint_stale_eod_or_manual_evidence"],
        },
    }
    row.update(overrides)
    return row


class RegularOptionsCandidateOutcomeLedgerTests(unittest.TestCase):
    def test_ledger_unifies_candidate_outcomes_and_operator_blockers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fresh_path = root / "fresh.json"
            shortlist_path = root / "shortlist.json"
            queue_path = root / "queue.json"
            open_risk_path = root / "open-risk.json"
            suggested_path = root / "suggested.json"

            _write_json(
                fresh_path,
                {
                    "generated_at_utc": "2026-06-06T00:00:00Z",
                    "summary": {
                        "candidate_count": 3,
                        "promotion_discussion_ready_count": 1,
                        "exact_realized_pnl_count": 1,
                        "missing_realized_pnl_count": 1,
                        "paper_probation_bridge_count": 1,
                        "exact_exit_bridge_count": 1,
                        "live_policy_change": False,
                    },
                    "candidates": [
                        _fresh_candidate("QQQ", key="fresh-exit"),
                        _fresh_candidate(
                            "SPY",
                            key="paper-entry",
                            auto_track_position_id=None,
                            validation_outcome="paper_only",
                            validation_outcome_reason="lane_routed_to_paper_validation_only",
                            entry_evidence_status="fill_attempt_missing",
                            entry_evidence_reasons=["no_fill_attempt_logged"],
                            fill_attempt_status="missing",
                            position_link_status="no_tracked_or_suggested_link",
                            realized_pnl_status="no_position_link",
                            evidence_bridge_status="paper_probation_exact_entry_required",
                            evidence_bridge_blockers=["entry_status:fill_attempt_missing"],
                            required_next_evidence=["fresh_executable_exact_opra_nbbo_entry"],
                            evidence_bridge={
                                "status": "paper_probation_exact_entry_required",
                                "blockers": ["entry_status:fill_attempt_missing"],
                                "required_next_evidence": ["fresh_executable_exact_opra_nbbo_entry"],
                            },
                        ),
                        _fresh_candidate(
                            "IWM",
                            key="ready",
                            auto_track_position_id=77,
                            realized_pnl_status="exact_realized_pnl_available",
                            evidence_bridge_status="promotion_review_ready",
                            promotion_discussion_ready=True,
                            evidence_bridge={"status": "promotion_review_ready", "blockers": []},
                        ),
                    ],
                },
            )
            _write_json(
                shortlist_path,
                {
                    "generated_at_utc": "2026-06-06T00:01:00Z",
                    "summary": {
                        "eligible_count": 1,
                        "invariant_violation_count": 0,
                        "release_gate_status": "paper_shortlist_candidates_ready",
                        "live_policy_change": False,
                    },
                    "eligible_paper_review_candidates": [
                        {"playbook_id": "swing", "symbol": "SPY", "expiry": "2026-06-26"}
                    ],
                    "fresh_scan_non_eligible_preview": [
                        {
                            "playbook_id": "tracked_winner_primary",
                            "symbol": "SPY",
                            "match_type": "lane_signature",
                            "guardrail_decision": "blocked",
                            "blockers": ["guardrail_not_clear", "no_tier_a_lane_match"],
                            "fresh_executable_quote_window": True,
                        }
                    ],
                },
            )
            _write_json(
                queue_path,
                {
                    "generated_at_utc": "2026-06-06T00:02:00Z",
                    "summary": {
                        "queue_rows": 2,
                        "selection_readiness_counts": {"paper_review_candidate": 1},
                        "live_policy_change": False,
                    },
                    "capture_queue": [
                        {
                            "lane_id": "nem_tier_a",
                            "symbol": "NEM",
                            "capture_tier": "tier_a_clean_exact_capture",
                            "selection_readiness": "paper_review_candidate",
                            "selection_reason": "Clean exact evidence awaits a fresh bridge.",
                            "paper_shortlist_bridge": {"status": "requires_fresh_executable_tier_a_match"},
                        },
                        {
                            "lane_id": "qqq_repair",
                            "symbol": "QQQ",
                            "capture_tier": "tier_b_profitable_watch_repair",
                            "selection_readiness": "watch_repair_only",
                            "evidence_repair_priority": "high",
                            "repair_actionability": "needs_status_or_forward_validation_after_repair",
                        },
                    ],
                },
            )
            _write_json(
                open_risk_path,
                {
                    "generated_at_utc": "2026-06-06T00:03:00Z",
                    "open_risk_governor": {
                        "status": "open_risk_governor_blocked",
                        "live_entry_allowed": False,
                        "live_policy_change": False,
                        "blockers": ["live_exact_negative_open_risk"],
                        "governor_details": [
                            {
                                "id": 537,
                                "ticker": "QQQ",
                                "lane": "volatility_expansion_observation",
                                "record_class": "live_exact_tracked",
                                "next_safe_action": "monitor",
                            }
                        ],
                    },
                },
            )
            _write_json(
                suggested_path,
                {
                    "generated_at_utc": "2026-06-06T00:04:00Z",
                    "attention_trade_ids": [138],
                    "attention_trades": [
                        {
                            "id": 138,
                            "ticker": "AAA",
                            "lane": "legacy_unlabeled",
                            "record_class": "suggested_trade",
                            "next_safe_action": "refresh_explicit_suggested_trade_review_before_using_close_or_pnl_state",
                        }
                    ],
                },
            )

            report = ledger.build_report(
                fresh_evidence_loop_path=fresh_path,
                paper_shortlist_path=shortlist_path,
                profit_capture_queue_path=queue_path,
                open_risk_path=open_risk_path,
                suggested_close_risk_path=suggested_path,
                generated_at_utc="2026-06-06T00:05:00Z",
            )

        summary = report["summary"]
        actions = summary["action_counts"]
        self.assertEqual(summary["operating_status"], "ledger_live_entry_blocked_collect_evidence")
        self.assertEqual(summary["ledger_row_count"], 9)
        self.assertFalse(summary["live_policy_change"])
        self.assertEqual(actions["resolve_open_risk_governor"], 1)
        self.assertEqual(actions["collect_exact_exit_evidence"], 1)
        self.assertEqual(actions["capture_paper_only_exact_entry"], 1)
        self.assertEqual(actions["promotion_review_candidate"], 1)
        self.assertEqual(actions["create_or_link_paper_review_row"], 1)
        self.assertEqual(actions["wait_for_fresh_executable_tier_a_bridge"], 1)
        self.assertEqual(actions["repair_historical_evidence"], 1)
        self.assertEqual(actions["respect_guardrail_or_lane_mismatch"], 1)
        self.assertEqual(actions["refresh_suggested_trade_review"], 1)
        self.assertEqual(report["ledger_rows"][0]["next_evidence_action"], "resolve_open_risk_governor")
        self.assertEqual(report["next_evidence_queue"][0]["next_evidence_action"], "resolve_open_risk_governor")

    def test_missing_required_fresh_evidence_loop_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = ledger.build_report(
                fresh_evidence_loop_path=root / "missing-fresh.json",
                paper_shortlist_path=root / "missing-shortlist.json",
                profit_capture_queue_path=root / "missing-queue.json",
                open_risk_path=root / "missing-open-risk.json",
                suggested_close_risk_path=root / "missing-suggested.json",
                generated_at_utc="2026-06-06T00:00:00Z",
            )

        self.assertEqual(report["summary"]["operating_status"], "ledger_blocked_missing_inputs")
        self.assertEqual(report["summary"]["ledger_row_count"], 0)
        self.assertEqual(report["inputs"]["fresh_evidence_loop"]["status"], "missing")
        self.assertTrue(report["inputs"]["fresh_evidence_loop"]["required"])
        self.assertEqual(report["summary"]["input_status_counts"], {"missing": 5})

    def test_markdown_and_outputs_render_read_only_boundary(self):
        report = {
            "report_id": ledger.REPORT_ID,
            "status": "candidate_outcome_ledger_readback",
            "generated_at_utc": "2026-06-06T00:00:00Z",
            "summary": {
                "operating_status": "ledger_collect_exact_evidence",
                "ledger_row_count": 1,
                "fresh_candidate_count": 1,
                "paper_shortlist_eligible_count": 0,
                "profit_capture_paper_review_candidate_count": 0,
                "promotion_discussion_ready_count": 0,
                "exact_realized_pnl_count": 0,
                "missing_realized_pnl_count": 1,
                "paper_probation_bridge_count": 0,
                "exact_exit_bridge_count": 1,
                "open_risk_live_entry_allowed": True,
                "suggested_attention_count": 0,
                "action_counts": {"collect_exact_exit_evidence": 1},
                "live_policy_change": False,
            },
            "source_summaries": {
                "fresh_evidence_loop": {
                    "validation_outcome_counts": {"created": 1},
                    "evidence_bridge_status_counts": {"exact_exit_pnl_required": 1},
                },
                "paper_shortlist": {"release_gate_status": "no_paper_shortlist_candidates"},
                "profit_capture_queue": {"selection_readiness_counts": {}},
                "open_risk_governor": {"status": "open_risk_governor_pass"},
            },
            "next_evidence_queue": [
                {
                    "action_priority": 2,
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "count": 1,
                    "operator_next_step": "Collect exact exit evidence.",
                }
            ],
            "ledger_rows": [
                {
                    "action_priority": 2,
                    "next_evidence_action": "collect_exact_exit_evidence",
                    "source_report": "fresh_evidence_loop",
                    "lane_id": "swing",
                    "ticker": "QQQ",
                    "action_reason": "linked_position_has_missing_realized_pnl",
                }
            ],
        }

        markdown = ledger.render_markdown(report)
        self.assertIn("# Regular Options Candidate Outcome Ledger", markdown)
        self.assertIn("`collect_exact_exit_evidence`", markdown)
        self.assertIn("does not create trades", markdown)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifacts = ledger.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["artifacts"]["docs_report"], str(root / "doc.md"))
            self.assertTrue((root / "doc.md").exists())


if __name__ == "__main__":
    unittest.main()
