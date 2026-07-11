from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

from scripts import run_regular_options_vrp_credit_spread_bounded_replay as replay
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf8",
    )


def _playbook(tmp: Path, *, geometry: bool = True) -> Path:
    payload = {
        "report_id": "regular_options_preregistered_vrp_credit_spread_playbook",
        "status": "preregistered_design_only",
        "concept_id": replay.CONCEPT_ID,
        "structure": replay.EXPECTED_STRUCTURE,
        "accepted_profitability": False,
        "historical_research_window": {
            "start_date": "2024-06-01",
            "end_date": "2026-05-31",
        },
    }
    if geometry:
        payload["candidate_geometry"] = {
            "dte_min": 21,
            "dte_max": 45,
            "short_put_moneyness_or_delta": "otm_delta_proxy_20",
            "long_put_distance": "five_points_or_next_liquid_strike",
            "exit_policy": "profit_take_or_time_exit_or_expiry",
        }
    path = tmp / "playbook.json"
    _write_json(path, payload)
    return path


def _harness(tmp: Path, *, ready: bool = True) -> Path:
    path = tmp / "harness.json"
    _write_json(
        path,
        {
            "report_id": "regular_options_vrp_credit_spread_structure_harness",
            "status": "ready_for_bounded_read_only_vrp_replay"
            if ready
            else "blocked_vrp_credit_spread_structure_harness",
            "remaining_blockers": []
            if ready
            else [
                "missing_point_in_time_vix_bucket",
                "missing_index_credit_spread_quote_surface",
            ],
        },
    )
    return path


def _holdout(tmp: Path) -> Path:
    path = tmp / "holdout.json"
    _write_json(
        path,
        {
            "protected_range": {
                "start_date": "2026-06-01",
                "date_basis": "candidate_entry_date",
            }
        },
    )
    return path


def _candidate(**overrides) -> dict:
    row = {
        "ticker": "SPY",
        "entry_date": "2026-05-20",
        "short_put_bid": 2.0,
        "long_put_ask": 0.75,
        "short_put_ask": 0.9,
        "long_put_bid": 0.25,
        "short_strike": 500,
        "long_strike": 495,
        "fees_usd": 2.0,
        "slippage_usd": 1.0,
        "exercise_style": "american",
    }
    row.update(overrides)
    return row


class RegularOptionsVrpCreditSpreadBoundedReplayTests(unittest.TestCase):
    def test_real_gate_blocks_when_structure_harness_not_ready(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp, ready=False),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(
            report["status"], "blocked_vrp_credit_spread_bounded_replay_gate"
        )
        self.assertFalse(report["historical_replay_performed"])
        self.assertIn(
            "missing_point_in_time_vix_bucket", report["replay_gate_blockers"]
        )
        self.assertIn(
            "missing_index_credit_spread_quote_surface", report["replay_gate_blockers"]
        )
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["broker_order_allowed"])

    def test_gate_blocks_without_frozen_candidate_geometry(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "quotes.db").write_bytes(b"sqlite placeholder")
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp, geometry=False),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
            )

        self.assertEqual(
            report["status"], "blocked_vrp_credit_spread_bounded_replay_gate"
        )
        self.assertIn(
            "missing_preregistered_candidate_geometry", report["replay_gate_blockers"]
        )
        self.assertEqual(report["replay_rows"], [])

    def test_ready_harness_without_native_candidates_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "quotes.db").write_bytes(b"sqlite placeholder")
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
            )

        self.assertEqual(
            report["status"], "blocked_vrp_credit_spread_bounded_replay_gate"
        )
        self.assertIn(
            "missing_native_vrp_candidate_generation_engine",
            report["replay_gate_blockers"],
        )

    def test_fixture_replay_classifies_denominator_and_pnl(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            quotes = tmp / "quotes.db"
            quotes.write_bytes(b"sqlite placeholder")
            rows = [
                _candidate(),
                _candidate(ticker="QQQ", short_put_bid=0.5, long_put_ask=0.75),
                _candidate(ticker="IWM", short_put_bid=None),
                _candidate(ticker="DIA", entry_date="2026-06-01"),
            ]
            fixture = tmp / "rows.jsonl"
            _write_jsonl(fixture, rows)

            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=quotes,
                fixture_candidates_path=fixture,
            )

        self.assertTrue(report["historical_replay_performed"])
        self.assertEqual(report["metrics"]["denominator_counts"]["exact_closed"], 1)
        self.assertEqual(
            report["metrics"]["denominator_counts"]["zero_bid_untradable"], 1
        )
        self.assertEqual(
            report["metrics"]["denominator_counts"]["missing_required_quote"], 1
        )
        self.assertEqual(
            report["metrics"]["denominator_counts"]["protected_holdout_blocked"], 1
        )
        self.assertEqual(report["metrics"]["net_usd_total"], 57.0)
        self.assertEqual(report["metrics"]["exact_closed_or_settled_rows"], 1)
        self.assertEqual(report["status"], "falsified_vrp_credit_spread_replay")
        self.assertFalse(report["accepted_profitability"])

    def test_invalid_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            bad = tmp / "bad.json"
            _write_json(
                bad,
                {
                    "status": "implemented",
                    "concept_id": "wrong",
                    "accepted_profitability": True,
                },
            )
            report = replay.build_report(
                preregistered_playbook_path=bad,
                structure_harness_path=_harness(tmp),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
            )

        self.assertEqual(
            report["status"], "blocked_vrp_credit_spread_bounded_replay_gate"
        )
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("unexpected_concept_id", report["replay_gate_blockers"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="vrp-replay") as tmp_dir:
            tmp = Path(tmp_dir)
            report = replay.build_report(
                preregistered_playbook_path=_playbook(tmp),
                structure_harness_path=_harness(tmp, ready=False),
                holdout_contract_path=_holdout(tmp),
                quotes_db_path=tmp / "quotes.db",
            )
            artifacts = replay.write_outputs(
                report, output_dir=tmp / "out", docs_report=tmp / "docs" / "replay.md"
            )

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "replay.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "replay.md").read_text(encoding="utf8")
            self.assertIn("Regular Options VRP Credit Spread Bounded Replay", markdown)

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
