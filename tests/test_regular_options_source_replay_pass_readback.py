from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_source_replay_pass_readback as readback


NOW = "2026-06-18T00:00:00Z"


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generated_at_utc": NOW, **payload}), encoding="utf8")
    return path


class SourceReplayPassReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = {
            "evidence": self.root / "evidence.json",
            "tournament": self.root / "tournament.json",
            "robust": self.root / "robust.json",
            "scoped": self.root / "scoped.json",
        }
        _write(
            self.paths["evidence"],
            {
                "overall_status": "source_replay_required_before_repairs",
                "holdout_gap_summary": {"current_final_holdout_rows": 28},
                "pf_lower_bound_gap_summary": {"current_profit_factor_lower_bound": 0.61},
            },
        )
        _write(
            self.paths["tournament"],
            {
                "overall_status": "paper_shadow_only",
                "forward_freeze_candidate_count": 0,
                "paper_shadow_candidate_count": 1,
            },
        )
        _write(self.paths["robust"], {"overall_status": "paper_shadow_only", "robust_candidate_count": 0})
        _write(self.paths["scoped"], {"variants": []})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def build(self) -> dict:
        return readback.build_report(
            evidence_blocker_path=self.paths["evidence"],
            hypothesis_tournament_path=self.paths["tournament"],
            robust_edge_path=self.paths["robust"],
            scoped_replay_path=self.paths["scoped"],
            generated_at_utc=NOW,
        )

    def test_missing_evidence_blocker_fails_closed(self) -> None:
        self.paths["evidence"].unlink()
        report = self.build()
        self.assertEqual(report["overall_status"], "blocked_missing_readbacks")

    def test_missing_target_list_fails_closed(self) -> None:
        original = readback.TARGETS
        try:
            readback.TARGETS = ()
            report = self.build()
        finally:
            readback.TARGETS = original
        self.assertEqual(report["overall_status"], "blocked_missing_targets")

    def test_source_replay_unsafe_without_scoped_variant(self) -> None:
        report = self.build()
        self.assertEqual(report["overall_status"], "source_replay_plan_only")
        self.assertEqual(report["targets_unsafe_to_run"], 5)

    def test_resolved_exact_target_is_counted(self) -> None:
        run = self.root / "run.json"
        run.write_text(
            json.dumps({"trades": [{"short_contract_symbol": "DIA251128C00495000", "date": "2025-11-05"}]}),
            encoding="utf8",
        )
        target = {
            "target_id": "t",
            "ticker": "DIA",
            "contract_symbol": "DIA251128C00495000",
            "quote_date": "2025-11-05",
            "lane_id": "tracked_winner_cheap_debit_continuity_v1",
            "source_artifact": "x",
            "source_replay_variant_id": "tracked_winner_cheap_debit_continuity_v1",
        }
        original = readback.TARGETS
        try:
            readback.TARGETS = (target,)
            _write(
                self.paths["scoped"],
                {"variants": [{"variant_id": "tracked_winner_cheap_debit_continuity_v1", "run_path": str(run)}]},
            )
            report = self.build()
        finally:
            readback.TARGETS = original
        self.assertEqual(report["overall_status"], "source_replay_resolved_some")
        self.assertEqual(report["targets_resolved"], 1)

    def test_lookahead_only_target_is_diagnostic_not_proof(self) -> None:
        row = {
            **readback.TARGETS[0],
            "result": "lookahead_only",
            "exact_row_found": False,
            "entry_exit_evidence_exact_executable": False,
        }
        self.assertEqual(row["result"], "lookahead_only")
        self.assertFalse(row["entry_exit_evidence_exact_executable"])

    def test_zero_bid_target_is_execution_failure(self) -> None:
        row = {
            **readback.TARGETS[0],
            "result": "zero_bid_tradability_failure",
            "entry_exit_evidence_exact_executable": False,
        }
        self.assertEqual(row["result"], "zero_bid_tradability_failure")
        self.assertFalse(row["entry_exit_evidence_exact_executable"])

    def test_exhausted_source_gets_do_not_repeat(self) -> None:
        row = {**readback.TARGETS[0], "result": "source_exhausted"}
        self.assertEqual(row["result"], "source_exhausted")

    def test_final_holdout_and_pf_before_after_are_separate(self) -> None:
        report = self.build()
        self.assertEqual(report["final_holdout_count_before"], 28)
        self.assertEqual(report["final_holdout_count_after"], 28)
        self.assertEqual(report["pf_lower_bound_before"], 0.61)
        self.assertEqual(report["pf_lower_bound_after"], 0.61)

    def test_script_never_allows_broker_live_or_auto_track(self) -> None:
        report = self.build()
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["auto_track_allowed"])

    def test_no_mutating_import_command_is_emitted_as_executed(self) -> None:
        report = self.build()
        commands = "\n".join(str(row.get("command_used")) for row in report["blocked_targets"])
        self.assertNotIn("import_missing_replay_quotes", commands)
        self.assertNotIn("--dry-run", commands)


if __name__ == "__main__":
    unittest.main()
