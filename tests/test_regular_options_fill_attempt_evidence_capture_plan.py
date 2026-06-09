from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_fill_attempt_evidence_capture_plan as plan


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _candidate_row(*, lane: str = "swing", ticker: str = "QQQ") -> dict:
    return {
        "action_priority": 7,
        "blocking_reasons": [
            "entry_status:fill_attempt_missing",
            "no_fill_attempt_logged",
            "lane_not_profitable_enough_for_live_validation",
        ],
        "candidate_key": f"2026-06-05|{lane}|{ticker}|call|2026-06-26|{ticker}260626C00730000|{ticker}260626C00750000|730.0|750.0",
        "candidate_status": "diagnostic_only_lane_profitability_gate",
        "contract_symbol": f"{ticker}260626C00730000",
        "direction": "call",
        "entry_evidence_status": "fill_attempt_missing",
        "evidence_bridge_status": "non_executable_entry_blocked",
        "expiry": "2026-06-26",
        "fill_attempt_status": "missing",
        "lane_id": lane,
        "ledger_key": f"fresh:2026-06-05|{lane}|{ticker}|call|2026-06-26",
        "live_policy_change": False,
        "next_evidence_action": "capture_missing_fill_attempt_evidence",
        "playbook_id": lane,
        "row_type": "candidate",
        "scan_date": "2026-06-05",
        "short_contract_symbol": f"{ticker}260626C00750000",
        "source_report": "fresh_evidence_loop",
        "symbol": ticker,
        "ticker": ticker,
        "validation_outcome": "diagnostic_only",
    }


def _candidate_ledger() -> dict:
    return {
        "report_id": "regular_options_candidate_outcome_ledger",
        "status": "candidate_outcome_ledger_readback",
        "generated_at_utc": "2026-06-07T01:00:00Z",
        "read_only": True,
        "summary": {
            "operating_status": "ledger_live_entry_blocked_collect_evidence",
            "action_counts": {"capture_missing_fill_attempt_evidence": 2},
        },
        "ledger_rows": [_candidate_row(lane="swing", ticker="QQQ"), _candidate_row(lane="short_term", ticker="SPY")],
        "next_evidence_queue": [
            {
                "action_priority": 7,
                "next_evidence_action": "capture_missing_fill_attempt_evidence",
                "count": 2,
            }
        ],
    }


def _matching_fill_attempt(*, lane: str = "swing", ticker: str = "QQQ") -> dict:
    return {
        "logged_at": "2026-06-05T14:00:00Z",
        "scan_date": "2026-06-05",
        "event_type": "candidate_shown",
        "fill_status": "not_filled_auto_track_skipped",
        "fill_outcome": "no_fill",
        "playbook_id": lane,
        "ticker": ticker,
        "direction": "call",
        "selected_spread": {
            "expiry": "2026-06-26",
            "long_contract_symbol": f"{ticker}260626C00730000",
            "short_contract_symbol": f"{ticker}260626C00750000",
        },
    }


class RegularOptionsFillAttemptEvidenceCapturePlanTests(unittest.TestCase):
    def test_happy_path_builds_row_specific_capture_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            fills = root / "fills.jsonl"
            _write_json(ledger, _candidate_ledger())
            _write_jsonl(fills, [])

            report = plan.build_report(
                candidate_ledger_path=ledger,
                fill_attempts_path=fills,
                generated_at_utc="2026-06-07T02:00:00Z",
            )

        self.assertEqual(report["status"], plan.READY_STATUS)
        self.assertFalse(report["live_policy_change"])
        self.assertEqual(report["summary"]["plan_row_count"], 2)
        self.assertEqual(report["summary"]["missing_fill_attempt_evidence_count"], 2)
        self.assertEqual(report["summary"]["market_window_required_count"], 2)
        self.assertEqual(report["summary"]["lane_counts"]["swing"], 1)
        self.assertEqual(report["summary"]["ticker_counts"]["QQQ"], 1)
        self.assertEqual(report["next_evidence_queue"][0]["action"], plan.PLAN_ACTION)
        self.assertIn("do_not_backfill_broker_fills_from_fill_attempt_evidence_capture_plan", report["prohibited_actions"])
        self.assertTrue(all(row["market_window_required"] for row in report["plan_rows"]))

    def test_matching_fill_attempt_marks_ledger_stale_and_clears_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            fills = root / "fills.jsonl"
            payload = _candidate_ledger()
            payload["ledger_rows"] = [_candidate_row(lane="swing", ticker="QQQ")]
            _write_json(ledger, payload)
            _write_jsonl(fills, [_matching_fill_attempt(lane="swing", ticker="QQQ")])

            report = plan.build_report(candidate_ledger_path=ledger, fill_attempts_path=fills)

        self.assertEqual(report["status"], plan.CLEAR_STATUS)
        self.assertEqual(report["summary"]["missing_fill_attempt_evidence_count"], 0)
        self.assertEqual(report["summary"]["ledger_stale_fill_attempt_logged_count"], 1)
        self.assertEqual(report["next_evidence_queue"], [])
        self.assertEqual(report["plan_rows"][0]["action"], "rerun_candidate_outcome_ledger_after_fill_attempt_log")

    def test_missing_required_inputs_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = plan.build_report(
                candidate_ledger_path=root / "missing-ledger.json",
                fill_attempts_path=root / "missing-fills.jsonl",
            )

        self.assertEqual(report["status"], plan.MISSING_STATUS)
        self.assertIn("regular_options_candidate_outcome_ledger", report["summary"]["missing_required_inputs"])
        self.assertIn("fill_attempts", report["summary"]["missing_required_inputs"])
        self.assertEqual(report["plan_rows"], [])

    def test_live_policy_change_invalidates_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            fills = root / "fills.jsonl"
            payload = _candidate_ledger()
            payload["live_policy_change"] = True
            _write_json(ledger, payload)
            _write_jsonl(fills, [])

            report = plan.build_report(candidate_ledger_path=ledger, fill_attempts_path=fills)

        self.assertEqual(report["status"], plan.INVALID_STATUS)
        self.assertTrue(report["summary"]["live_policy_change"])
        self.assertEqual(report["plan_rows"], [])
        self.assertEqual(report["next_evidence_queue"], [])

    def test_markdown_and_write_outputs_render_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "ledger.json"
            fills = root / "fills.jsonl"
            _write_json(ledger, _candidate_ledger())
            _write_jsonl(fills, [])
            report = plan.build_report(candidate_ledger_path=ledger, fill_attempts_path=fills)
            markdown = plan.render_markdown(report)
            artifacts = plan.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-fill-attempt-evidence-capture-plan.md",
            )

            self.assertIn("# Regular Options Fill-Attempt Evidence Capture Plan", markdown)
            self.assertIn("## Capture Rows", markdown)
            self.assertIn("does not create trades", markdown)
            self.assertIn("capture_durable_fill_attempt_on_fresh_selection", markdown)
            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], plan.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
