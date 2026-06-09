from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_open_risk_resolution_plan as plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _open_risk_payload() -> dict:
    return {
        "generated_at_utc": "2026-06-06T07:21:23Z",
        "scope": "regular_supervised_open_positions_read_only",
        "read_only": True,
        "summary": {
            "rows": 12,
            "priced_or_marked": 11,
            "negative": 10,
            "positive_or_flat": 1,
            "avg_pnl_pct": -44.14,
            "median_pnl_pct": -47.58,
        },
        "open_risk_governor": {
            "status": "open_risk_governor_blocked",
            "live_entry_allowed": False,
            "blockers": ["live_exact_negative_open_risk"],
            "live_exact_open_count": 1,
            "live_exact_negative_count": 1,
            "live_exact_negative_ids": [537],
            "live_exact_executable_close_ready_count": 0,
            "live_exact_review_blocked_count": 0,
            "governor_details": [
                {
                    "id": 537,
                    "ticker": "QQQ",
                    "lane": "volatility_expansion_observation",
                    "record_class": "live_exact_tracked",
                    "status": "open",
                    "action_bucket": "negative_mark_hold_or_unknown",
                    "evidence_bucket": "fresh_executable_review",
                    "recommendation": "HOLD",
                    "reason": "Position remains inside the stop, target, and exit rules.",
                    "pricing_source": "spread_bid_ask_exact",
                    "pricing_state": "priced_spread_exact",
                    "current_pnl_pct": -58.2639,
                    "mark_pnl_pct": -58.2639,
                    "exit_execution_price": 3.784,
                    "exit_execution_basis": "spread_bid_ask",
                    "price_trigger_ok": True,
                    "next_safe_action": "monitor",
                }
            ],
        },
        "actionable_positions": [
            {
                "id": 104,
                "ticker": "SBUX",
                "lane": "bullish_pullback_observation",
                "record_class": "main_zero_pick_research_backfill",
                "status": "open",
                "action_bucket": "stored_non_executable_sell",
                "evidence_bucket": "fresh_unpriced_review",
                "recommendation": "SELL",
                "reason": "Time exit reached after 16 calendar day(s), versus a 16-day limit.",
                "pricing_source": "spread_display_only",
                "pricing_state": "priced_display_only_last",
                "current_pnl_pct": None,
                "mark_pnl_pct": None,
                "price_trigger_ok": False,
                "first_warning": "Using display-only spread marks because one or both legs are missing a live executable bid/ask quote.",
                "next_safe_action": "do_not_auto_close_from_display_only_mark_rerun_explicit_review_during_fresh_executable_quote_window",
            }
        ],
    }


class RegularOptionsOpenRiskResolutionPlanTests(unittest.TestCase):
    def test_happy_path_builds_row_specific_resolution_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_risk_path = root / "open_risk.json"
            _write_json(open_risk_path, _open_risk_payload())

            report = plan.build_report(
                open_risk_path=open_risk_path,
                generated_at_utc="2026-06-07T01:00:00Z",
            )

        self.assertEqual(report["status"], plan.READY_STATUS)
        self.assertFalse(report["live_policy_change"])
        self.assertEqual(report["summary"]["source_open_risk_status"], "open_risk_governor_blocked")
        self.assertFalse(report["summary"]["live_entry_allowed"])
        self.assertEqual(report["summary"]["plan_row_count"], 2)
        self.assertEqual(report["summary"]["live_exact_plan_row_count"], 1)
        self.assertEqual(report["summary"]["display_only_sell_count"], 1)
        rows = {row["row_id"]: row for row in report["plan_rows"]}
        self.assertEqual(rows[537]["action"], "refresh_live_exact_negative_open_position_review")
        self.assertEqual(rows[537]["priority"], 0)
        self.assertIn("open_risk_governor_rerun", rows[537]["required_evidence"])
        self.assertEqual(rows[104]["action"], "refresh_display_only_sell_executable_review")
        self.assertIn("spread_bid_ask_exact_or_explicit_unpriced_review", rows[104]["required_evidence"])
        self.assertEqual(report["next_evidence_queue"][0]["action"], "execute_open_risk_resolution_review_plan")
        self.assertIn("do_not_auto_close_from_display_only_marks", report["prohibited_actions"])

    def test_missing_open_risk_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = plan.build_report(open_risk_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], plan.MISSING_STATUS)
        self.assertIn("regular_open_position_risk", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["plan_rows"], [])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_risk_path = root / "open_risk.json"
            payload = _open_risk_payload()
            payload["live_policy_change"] = True
            _write_json(open_risk_path, payload)

            report = plan.build_report(open_risk_path=open_risk_path)

        self.assertEqual(report["status"], plan.INVALID_STATUS)
        self.assertTrue(report["summary"]["live_policy_change"])
        self.assertEqual(report["plan_rows"], [])
        self.assertEqual(report["next_evidence_queue"], [])

    def test_clear_open_risk_has_no_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_risk_path = root / "open_risk.json"
            payload = _open_risk_payload()
            payload["summary"]["negative"] = 0
            payload["open_risk_governor"] = {
                "status": "open_risk_governor_pass",
                "live_entry_allowed": True,
                "blockers": [],
                "live_exact_open_count": 0,
                "live_exact_negative_count": 0,
                "live_exact_negative_ids": [],
                "live_exact_executable_close_ready_count": 0,
                "live_exact_review_blocked_count": 0,
                "governor_details": [],
            }
            payload["actionable_positions"] = []
            _write_json(open_risk_path, payload)

            report = plan.build_report(open_risk_path=open_risk_path)

        self.assertEqual(report["status"], plan.CLEAR_STATUS)
        self.assertTrue(report["summary"]["live_entry_allowed"])
        self.assertEqual(report["plan_rows"], [])
        self.assertEqual(report["next_evidence_queue"], [])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            open_risk_path = root / "open_risk.json"
            _write_json(open_risk_path, _open_risk_payload())
            report = plan.build_report(open_risk_path=open_risk_path)
            markdown = plan.render_markdown(report)
            artifacts = plan.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-open-risk-resolution-plan.md",
            )

            self.assertIn("# Regular Options Open-Risk Resolution Plan", markdown)
            self.assertIn("## Resolution Rows", markdown)
            self.assertIn("does not create trades", markdown)
            self.assertIn("refresh_display_only_sell_executable_review", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], plan.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
