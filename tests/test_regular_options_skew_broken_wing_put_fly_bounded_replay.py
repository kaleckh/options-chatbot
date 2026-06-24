from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_skew_broken_wing_put_fly_bounded_replay as replay
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _playbook(tmp: Path, *, valid: bool = True) -> Path:
    payload = {
        "report_id": "regular_options_preregistered_skew_broken_wing_playbook",
        "status": "preregistered_design_only" if valid else "implemented",
        "concept_id": replay.CONCEPT_ID if valid else "wrong",
        "structure": replay.EXPECTED_STRUCTURE if valid else "wrong",
        "accepted_profitability": False,
    }
    path = tmp / "playbook.json"
    _write_json(path, payload)
    return path


def _harness(tmp: Path, *, ready: bool = True) -> Path:
    path = tmp / "harness.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_skew_broken_wing_structure_harness",
            "status": "ready_for_skew_broken_wing_bounded_read_only_replay" if ready else "blocked_skew_broken_wing_structure_harness",
            "remaining_blockers": [] if ready else ["missing_point_in_time_downside_skew_inputs", "missing_index_broken_wing_quote_surface"],
        },
    )
    return path


def _holdout(tmp: Path) -> Path:
    path = tmp / "holdout.json"
    _write_json(path, {"protected_range": {"start_date": "2026-06-01", "date_basis": "candidate_entry_date"}})
    return path


def _base_stack(tmp: Path, rows: list[dict] | None = None) -> Path:
    path = tmp / "base.json"
    _write_json(path, {"rows": rows or []})
    return path


def _candidate(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "entry_date": "2026-05-20",
        "expiration": "2026-06-19",
        "upper_strike": 525,
        "middle_strike": 515,
        "lower_strike": 500,
        "upper_long_put_ask": 13.0,
        "middle_short_put_bid": 7.0,
        "lower_long_put_ask": 2.5,
        "upper_long_put_bid": 15.0,
        "middle_short_put_ask": 6.0,
        "lower_long_put_bid": 2.0,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
        "quote_basis": "trusted_opra_nbbo_bid_ask",
    }
    row.update(overrides)
    return row


class RegularOptionsSkewBrokenWingBoundedReplayTests(unittest.TestCase):
    def test_real_gate_blocks_when_structure_harness_not_ready(self) -> None:
        with WorkspaceTempDir(prefix="skew-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp, ready=False),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_skew_broken_wing_bounded_replay")
        self.assertFalse(report["historical_replay_performed"])
        self.assertIn("missing_point_in_time_downside_skew_inputs", report["replay_gate_blockers"])
        self.assertIn("missing_index_broken_wing_quote_surface", report["replay_gate_blockers"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])

    def test_fixture_replay_classifies_denominator_pnl_and_dedupe(self) -> None:
        with WorkspaceTempDir(prefix="skew-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            quotes = tmp / "quotes.db"
            quotes.write_bytes(b"sqlite placeholder")
            duplicate = _candidate()
            rows = [
                duplicate,
                dict(duplicate),
                _candidate(ticker="QQQ", upper_long_put_ask=None),
                _candidate(ticker="IWM", middle_short_put_bid=0.0),
                _candidate(ticker="DIA", entry_date="2026-06-01"),
                _candidate(ticker="SPY", upper_strike=515, middle_strike=525),
            ]
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, rows)

            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=quotes,
                clean_base_stack_path=_base_stack(tmp),
                fixture_candidates_path=fixture,
            )

        self.assertTrue(report["historical_replay_performed"])
        counts = report["metrics"]["denominator_counts"]
        self.assertEqual(counts["exact_exit_captured"], 1)
        self.assertEqual(counts["duplicate_strict_new_identity"], 1)
        self.assertEqual(counts["missing_leg_quote"], 1)
        self.assertEqual(counts["zero_bid_or_untradable"], 1)
        self.assertEqual(counts["protected_holdout_blocked"], 1)
        self.assertEqual(counts["rejected_width_or_liquidity"], 1)
        self.assertEqual(report["metrics"]["net_usd_total"], 347.0)
        self.assertEqual(report["status"], "rejected_skew_broken_wing_bounded_replay")

    def test_base_stack_identity_rejects_overlap(self) -> None:
        with WorkspaceTempDir(prefix="skew-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            quotes = tmp / "quotes.db"
            quotes.write_bytes(b"sqlite placeholder")
            row = _candidate()
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, [row])
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=quotes,
                clean_base_stack_path=_base_stack(tmp, [row]),
                fixture_candidates_path=fixture,
            )

        self.assertEqual(report["metrics"]["denominator_counts"]["duplicate_strict_new_identity"], 1)
        self.assertEqual(report["metrics"]["exact_completed_rows"], 0)

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="skew-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp, valid=False),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
            )

        self.assertEqual(report["status"], "blocked_skew_broken_wing_bounded_replay")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["replay_gate_blockers"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="skew-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp, ready=False),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
            )
            artifacts = replay.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "replay.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "replay.md").exists())
            self.assertIn("docs_report", artifacts)

    def test_runner_does_not_call_scanner_or_trading_paths(self) -> None:
        source = Path(replay.__file__).read_text(encoding="utf8")
        tree = ast.parse(source)
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called_names.add(node.func.attr)
        forbidden_calls = {"run_daily_ops", "log_scan_picks", "validate_pending_scan_candidates", "submit_order", "create_position", "auto_track", "import_quotes"}
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
