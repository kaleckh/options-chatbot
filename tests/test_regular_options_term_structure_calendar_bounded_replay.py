from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import build_regular_options_term_structure_calendar_bounded_replay as replay
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _playbook(tmp: Path, *, geometry: bool = True) -> Path:
    payload = {
        "report_id": "regular_options_preregistered_term_structure_calendar_playbook",
        "status": "preregistered_design_only",
        "concept_id": replay.CONCEPT_ID,
        "structure": replay.EXPECTED_STRUCTURE,
        "accepted_profitability": False,
        "historical_research_window": {"start_date": "2024-06-01", "end_date": "2026-05-31"},
    }
    if geometry:
        payload["candidate_geometry"] = {
            "front_back_expiry_spacing": "30_60_dte",
            "strike_delta_or_moneyness_rule": "same_strike_or_fixed_delta_proxy",
            "max_debit": 4.0,
            "max_bid_ask_width": 0.25,
            "exit_policy": "time_exit_or_front_expiry",
        }
    path = tmp / "playbook.json"
    _write_json(path, payload)
    return path


def _harness(tmp: Path, *, ready: bool = True) -> Path:
    path = tmp / "harness.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_term_structure_calendar_structure_harness",
            "status": "ready_for_bounded_read_only_term_structure_calendar_replay" if ready else "blocked_term_structure_calendar_structure_harness",
            "remaining_blockers": [] if ready else ["missing_point_in_time_term_structure_inputs", "missing_index_calendar_quote_surface"],
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
        "front_expiry": "2026-06-19",
        "back_expiry": "2026-07-17",
        "strike": 525,
        "long_back_month_ask": 6.5,
        "short_front_month_bid": 2.0,
        "long_back_month_bid": 7.2,
        "short_front_month_ask": 1.0,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
    }
    row.update(overrides)
    return row


class RegularOptionsTermStructureCalendarBoundedReplayTests(unittest.TestCase):
    def test_real_gate_blocks_when_structure_harness_not_ready(self) -> None:
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp, ready=False),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_bounded_replay")
        self.assertFalse(report["historical_replay_performed"])
        self.assertIn("missing_point_in_time_term_structure_inputs", report["replay_gate_blockers"])
        self.assertIn("missing_index_calendar_quote_surface", report["replay_gate_blockers"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])

    def test_gate_blocks_without_frozen_candidate_geometry(self) -> None:
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "quotes.db").write_bytes(b"sqlite placeholder")
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp, geometry=False),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_bounded_replay")
        self.assertIn("missing_preregistered_calendar_diagonal_geometry", report["replay_gate_blockers"])
        self.assertEqual(report["replay_rows"], [])

    def test_fixture_replay_classifies_denominator_pnl_and_strict_new_dedupe(self) -> None:
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            quotes = tmp / "quotes.db"
            quotes.write_bytes(b"sqlite placeholder")
            duplicate = _candidate()
            rows = [
                duplicate,
                dict(duplicate),
                _candidate(ticker="QQQ", strike=420, long_back_month_ask=1.0, short_front_month_bid=2.0),
                _candidate(ticker="IWM", strike=220),
                _candidate(ticker="SPY", strike=530, entry_date="2026-06-01"),
                _candidate(ticker="QQQ", strike=425, long_back_month_ask=None),
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
        self.assertEqual(counts["zero_bid_or_untradable"], 1)
        self.assertEqual(counts["rejected_geometry"], 1)
        self.assertEqual(counts["protected_holdout_blocked"], 1)
        self.assertEqual(counts["missing_leg_quote"], 1)
        self.assertEqual(report["metrics"]["net_usd_total"], 167.0)
        self.assertEqual(report["metrics"]["strict_new_exact_completed_rows"], 1)
        self.assertEqual(report["status"], "rejected_term_structure_calendar_bounded_replay")
        self.assertFalse(report["accepted_profitability"])

    def test_base_stack_identity_rejects_overlap(self) -> None:
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
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
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            bad = tmp / "bad.json"
            _write_json(bad, {"status": "implemented", "concept_id": "wrong", "accepted_profitability": True})
            report = replay.build_report(
                preregistered_playbook_path=bad,
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                clean_base_stack_path=_base_stack(tmp),
            )

        self.assertEqual(report["status"], "blocked_term_structure_calendar_bounded_replay")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["replay_gate_blockers"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="term-replay") as tmp_dir:
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
            markdown = (tmp / "docs" / "replay.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Term-Structure Calendar Bounded Replay", markdown)

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

        forbidden_calls = {
            "run_daily_ops",
            "log_scan_picks",
            "validate_pending_scan_candidates",
            "submit_order",
            "create_position",
            "auto_track",
            "import_quotes",
        }
        self.assertTrue(forbidden_calls.isdisjoint(called_names))


if __name__ == "__main__":
    unittest.main()
