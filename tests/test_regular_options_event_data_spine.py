from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_event_data_spine as spine


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsEventDataSpineTests(unittest.TestCase):
    def test_build_report_tracks_event_annotation_gap_without_proof_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fill_attempts.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "logged_at": "2026-06-05T14:43:50Z",
                        "scan_date": "2026-06-05",
                        "playbook_id": "volatility_expansion_observation",
                        "ticker": "QQQ",
                        "direction": "call",
                        "strategy_type": "vertical_spread",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_status": "auto_tracked",
                        "fill_outcome": "paper_fill_recorded",
                        "filled_price": 9.04,
                        "selected_spread": {
                            "ticker": "QQQ",
                            "strategy_type": "vertical_spread",
                            "expiry": "2026-06-18",
                        },
                    },
                    {
                        "event_type": "candidate_shown",
                        "logged_at": "2026-06-05T15:00:00Z",
                        "scan_date": "2026-06-05",
                        "playbook_id": "earnings_watch_observation",
                        "ticker": "NVDA",
                        "direction": "call",
                        "strategy_type": "vertical_spread",
                        "pricing_evidence_class": "proof_live_opra_exact_contract",
                        "fill_outcome": "paper_fill_recorded",
                        "filled_price": 4.25,
                        "earnings_date": "2026-06-10",
                        "post_event_vol_crush_pct": -18.4,
                        "selected_spread": {
                            "ticker": "NVDA",
                            "strategy_type": "vertical_spread",
                            "expiry": "2026-06-18",
                        },
                        "exit_result": {
                            "net_pnl_pct": 12.0,
                            "exit_execution_basis": "opra_bid_ask",
                            "quote_source": "alpaca_opra",
                        },
                    },
                    {"event_type": "historical_backfill_candidate_shown", "earnings_date": "2026-06-11"},
                ],
            )

            report = spine.build_report(fill_attempts_path=fills, generated_at_utc="2026-06-06T00:00:00Z")

        self.assertEqual(report["status"], "event_data_spine_built_collecting")
        self.assertFalse(report["summary"]["live_policy_change"])
        self.assertEqual(report["summary"]["candidate_shown_count"], 2)
        self.assertEqual(report["summary"]["event_annotation_count"], 1)
        self.assertEqual(report["summary"]["missing_event_annotation_count"], 1)
        self.assertEqual(report["summary"]["proof_live_exact_entry_count"], 2)
        self.assertEqual(report["summary"]["paper_fill_recorded_count"], 2)
        self.assertEqual(report["summary"]["true_event_replay_pnl_count"], 1)
        self.assertEqual(report["summary"]["post_event_vol_crush_replay_pnl_count"], 1)
        self.assertIn("event_calendar_annotations_missing", report["summary"]["blockers"])
        self.assertNotIn("event_data_spine_missing", report["summary"]["blockers"])
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertIn("collect_event_calendar_annotations", actions)
        rows = {(row["ticker"], row["playbook_id"]): row for row in report["event_spine_rows"]}
        self.assertEqual(rows[("QQQ", "volatility_expansion_observation")]["missing_event_annotation_count"], 1)
        self.assertEqual(rows[("NVDA", "earnings_watch_observation")]["post_event_vol_crush_replay_pnl_count"], 1)

    def test_missing_fill_attempts_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = spine.build_report(fill_attempts_path=Path(tmp) / "missing.jsonl")

        self.assertEqual(report["status"], "blocked_missing_inputs")
        self.assertIn("fill_attempts", report["summary"]["missing_required_inputs"])

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fills = root / "fill_attempts.jsonl"
            _write_jsonl(
                fills,
                [
                    {
                        "event_type": "candidate_shown",
                        "ticker": "QQQ",
                        "playbook_id": "volatility_expansion_observation",
                    }
                ],
            )
            report = spine.build_report(fill_attempts_path=fills, generated_at_utc="2026-06-06T00:00:00Z")
            artifacts = spine.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regular-options-event-data-spine.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], spine.REPORT_ID)


if __name__ == "__main__":
    unittest.main()
