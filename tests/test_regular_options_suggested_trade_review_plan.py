from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_suggested_trade_review_plan as plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _suggested_close_risk_payload() -> dict:
    return {
        "generated_at_utc": "2026-06-07T01:00:00Z",
        "scope": "suggested_trades_close_risk_read_only",
        "read_only": True,
        "summary": {
            "rows": 1,
            "priced_or_marked": 0,
            "negative": 0,
            "positive_or_flat": 0,
            "avg_pnl_pct": None,
            "median_pnl_pct": None,
        },
        "evidence_counts": {"missing_review": 1},
        "action_counts": {"no_stored_review": 1},
        "close_risk_trade_ids": [],
        "stale_or_missing_review_trade_ids": [138],
        "attention_trade_ids": [138],
        "attention_trades": [
            {
                "id": 138,
                "ticker": "AAA",
                "lane": "legacy_unlabeled",
                "record_class": "suggested_trade",
                "status": "open",
                "action_bucket": "no_stored_review",
                "evidence_bucket": "missing_review",
                "last_reviewed_at": None,
                "recommendation": None,
                "pricing_source": None,
                "pricing_state": None,
                "current_pnl_pct": None,
                "mark_pnl_pct": None,
                "stop_loss_pct": 50.0,
                "profit_target_pct": 100.0,
                "price_trigger_ok": False,
                "next_safe_action": "refresh_explicit_suggested_trade_review_before_using_close_or_pnl_state",
            }
        ],
    }


class RegularOptionsSuggestedTradeReviewPlanTests(unittest.TestCase):
    def test_happy_path_builds_row_specific_review_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "suggested.json"
            _write_json(source, _suggested_close_risk_payload())

            report = plan.build_report(
                suggested_close_risk_path=source,
                generated_at_utc="2026-06-07T02:00:00Z",
            )

        self.assertEqual(report["status"], plan.READY_STATUS)
        self.assertFalse(report["live_policy_change"])
        self.assertEqual(report["summary"]["open_suggested_trade_rows"], 1)
        self.assertEqual(report["summary"]["attention_trade_count"], 1)
        self.assertEqual(report["summary"]["missing_review_count"], 1)
        self.assertEqual(report["summary"]["plan_row_count"], 1)
        self.assertEqual(report["summary"]["market_window_required_count"], 1)
        row = report["plan_rows"][0]
        self.assertEqual(row["suggested_trade_id"], 138)
        self.assertEqual(row["action"], "refresh_missing_suggested_trade_review")
        self.assertEqual(row["resolution_status"], "market_window_required_missing_suggested_trade_review")
        self.assertIn("stored_review_snapshot", row["required_evidence"])
        self.assertEqual(report["next_evidence_queue"][0]["action"], plan.PLAN_ACTION)
        self.assertIn("do_not_mutate_suggested_trade_database_from_suggested_trade_review_plan", report["prohibited_actions"])

    def test_stored_executable_sell_gets_close_decision_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "suggested.json"
            payload = _suggested_close_risk_payload()
            payload["evidence_counts"] = {"fresh_executable_review": 1}
            payload["action_counts"] = {"stored_executable_sell": 1}
            payload["close_risk_trade_ids"] = [138]
            payload["attention_trades"][0]["action_bucket"] = "stored_executable_sell"
            payload["attention_trades"][0]["evidence_bucket"] = "fresh_executable_review"
            payload["attention_trades"][0]["recommendation"] = "SELL"
            payload["attention_trades"][0]["current_pnl_pct"] = 72.5
            _write_json(source, payload)

            report = plan.build_report(suggested_close_risk_path=source)

        self.assertEqual(report["summary"]["executable_close_ready_count"], 1)
        self.assertEqual(report["plan_rows"][0]["priority"], 0)
        self.assertEqual(report["plan_rows"][0]["action"], "review_executable_suggested_trade_close_decision")
        self.assertIn("paper_idea_close_decision_after_executable_review", report["plan_rows"][0]["required_evidence"])

    def test_missing_required_input_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = plan.build_report(suggested_close_risk_path=Path(tmp) / "missing.json")

        self.assertEqual(report["status"], plan.MISSING_STATUS)
        self.assertIn("suggested_trade_close_risk", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["plan_rows"], [])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "suggested.json"
            payload = _suggested_close_risk_payload()
            payload["live_policy_change"] = True
            _write_json(source, payload)

            report = plan.build_report(suggested_close_risk_path=source)

        self.assertEqual(report["status"], plan.INVALID_STATUS)
        self.assertTrue(report["summary"]["live_policy_change"])
        self.assertEqual(report["plan_rows"], [])
        self.assertEqual(report["next_evidence_queue"], [])

    def test_clear_suggested_trade_review_has_no_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "suggested.json"
            payload = _suggested_close_risk_payload()
            payload["evidence_counts"] = {"fresh_unpriced_review": 1}
            payload["action_counts"] = {"hold_or_positive": 1}
            payload["stale_or_missing_review_trade_ids"] = []
            payload["attention_trade_ids"] = []
            payload["attention_trades"] = []
            _write_json(source, payload)

            report = plan.build_report(suggested_close_risk_path=source)

        self.assertEqual(report["status"], plan.CLEAR_STATUS)
        self.assertEqual(report["summary"]["plan_row_count"], 0)
        self.assertEqual(report["plan_rows"], [])
        self.assertEqual(report["next_evidence_queue"], [])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "suggested.json"
            _write_json(source, _suggested_close_risk_payload())
            report = plan.build_report(suggested_close_risk_path=source)
            markdown = plan.render_markdown(report)
            artifacts = plan.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-suggested-trade-review-plan.md",
            )

            self.assertIn("# Regular Options Suggested-Trade Review Plan", markdown)
            self.assertIn("## Review Rows", markdown)
            self.assertIn("does not create trades", markdown)
            self.assertIn("refresh_missing_suggested_trade_review", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], plan.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
