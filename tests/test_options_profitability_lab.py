from __future__ import annotations

import json
import unittest
from pathlib import Path

from options_profitability_lab import (
    render_profitability_lab_markdown,
    run_profitability_lab_cycle,
    run_profitability_lab_loop,
)
from scripts.options_profitability_lab import _validate_run_safety
from scripts.options_profitability_lab import build_lab_run_fingerprint, find_duplicate_lab_run
from workspace_tempdir import WorkspaceTempDir


def _fake_replay(**kwargs):
    return {
        "mode": "backtest",
        "run_at": "2026-04-23T12:00:00Z",
        "trades": [{"ticker": "SPY", "pnl_pct": 5.0}],
        "kwargs": kwargs,
    }


def _fake_matrix(*, result, min_trades, min_profit_factor, min_directional_accuracy_pct):
    playbook = result.get("kwargs", {}).get("playbook") or "broad"
    passes = playbook in {"broad", "short_term", "bullish_momentum"}
    return {
        "source": {"mode": "backtest", "run_at": "2026-04-23T12:00:00Z"},
        "source_run_at": "2026-04-23T12:00:00Z",
        "lookback_years": result.get("kwargs", {}).get("lookback_years", 1),
        "pricing_lane": result.get("kwargs", {}).get("pricing_lane", "pessimistic"),
        "overall": {
            "trades": 24,
            "profit_factor": 1.2 if passes else 0.8,
            "avg_pnl_pct": 3.5 if passes else -1.5,
            "directional_accuracy_pct": 55.0 if passes else 45.0,
        },
        "authoritative_profitability_lens": "exact_contract_only",
        "authoritative_profitability_metrics": {
            "trades": 24,
            "profit_factor": 1.2 if passes else 0.8,
            "avg_pnl_pct": 3.5 if passes else -1.5,
            "directional_accuracy_pct": 55.0 if passes else 45.0,
        },
        "authoritative_profitability_gate": {"passed": passes},
        "experiments": [
            {
                "label": f"{playbook} score floor",
                "category": "score_floors",
                "trades": 24,
                "profit_factor": 1.2 if passes else 0.8,
                "avg_pnl_pct": 3.5 if passes else -1.5,
                "directional_accuracy_pct": 55.0 if passes else 45.0,
                "passes_quality_bar": passes,
            }
        ],
        "passing_experiments": [] if not passes else [
            {
                "label": f"{playbook} score floor",
                "category": "score_floors",
                "trades": 24,
                "profit_factor": 1.2,
                "avg_pnl_pct": 3.5,
                "directional_accuracy_pct": 55.0,
            }
        ],
        "recommendations": ["Keep as candidate."],
    }


def _healthy_gate():
    return {
        "state": "healthy",
        "blockers": [],
        "checks": {
            "tracked_positions": {
                "closed_position_count": 5,
                "net_profit_factor": 1.25,
                "avg_net_pnl_pct": 4.0,
            }
        },
    }


class OptionsProfitabilityLabTests(unittest.TestCase):
    def test_cli_safety_blocks_default_multi_variant_fresh_backtest(self):
        with self.assertRaises(SystemExit):
            _validate_run_safety(
                run_backtests=True,
                variants=None,
                cycles=1,
                allow_heavy=False,
            )

    def test_cli_safety_allows_single_fresh_backtest_cycle(self):
        self.assertIsNone(
            _validate_run_safety(
                run_backtests=True,
                variants=["incumbent_broad"],
                cycles=1,
                allow_heavy=False,
            )
        )

    def test_bullish_index_calls_variant_targets_index_bullish_playbook(self):
        calls = []

        def capture_replay(**kwargs):
            calls.append(kwargs)
            return _fake_replay(**kwargs)

        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["bullish_index_calls"],
            backtest_func=capture_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(calls[0]["playbook"], "bullish_index_calls")
        self.assertEqual(calls[0]["allowed_directions"], ["call"])
        self.assertEqual(report["variants"][0]["label"], "Bullish Index Calls")

    def test_score70_bullish_index_calls_variant_targets_strict_playbook(self):
        calls = []

        def capture_replay(**kwargs):
            calls.append(kwargs)
            return _fake_replay(**kwargs)

        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["bullish_index_calls_score70"],
            backtest_func=capture_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(calls[0]["playbook"], "bullish_index_calls_score70")
        self.assertEqual(calls[0]["allowed_directions"], ["call"])
        self.assertEqual(report["variants"][0]["label"], "Bullish Index Calls Score 70+")

    def test_score70_bullish_qqq_calls_variant_targets_qqq_playbook(self):
        calls = []

        def capture_replay(**kwargs):
            calls.append(kwargs)
            return _fake_replay(**kwargs)

        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["bullish_qqq_calls_score70"],
            backtest_func=capture_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(calls[0]["playbook"], "bullish_qqq_calls_score70")
        self.assertEqual(calls[0]["allowed_directions"], ["call"])
        self.assertEqual(report["variants"][0]["label"], "Bullish QQQ Calls Score 70+")

    def test_quality90_debit55_variant_targets_debit_capped_playbook(self):
        calls = []

        def capture_replay(**kwargs):
            calls.append(kwargs)
            return _fake_replay(**kwargs)

        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["bullish_index_calls_quality90_debit55"],
            backtest_func=capture_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(calls[0]["playbook"], "bullish_index_calls_quality90_debit55")
        self.assertEqual(calls[0]["allowed_directions"], ["call"])
        self.assertEqual(report["variants"][0]["label"], "Bullish Index Calls Quality 90+ Debit <55%")

    def test_cli_safety_blocks_repeated_fresh_backtest_cycles(self):
        with self.assertRaises(SystemExit):
            _validate_run_safety(
                run_backtests=True,
                variants=["incumbent_broad"],
                cycles=2,
                allow_heavy=False,
            )

    def test_cycle_evaluates_challengers_as_candidates(self):
        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["incumbent_broad", "bearish_defensive"],
            backtest_func=_fake_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(len(report["variants"]), 2)
        incumbent = report["variants"][0]
        bearish = report["variants"][1]
        self.assertEqual(incumbent["status"], "evaluated")
        self.assertEqual(incumbent["verdict"]["status"], "forward_watch_candidate")
        self.assertFalse(incumbent["verdict"]["promotion_allowed"])
        self.assertEqual(bearish["verdict"]["status"], "block")

    def test_cycle_refreshes_measurement_gate_after_fresh_backtest(self):
        events = []

        def replay_after_marker(**kwargs):
            events.append("backtest")
            return _fake_replay(**kwargs)

        def gate_after_marker():
            events.append("gate")
            return _healthy_gate()

        report = run_profitability_lab_cycle(
            run_backtests=True,
            variant_ids=["incumbent_broad"],
            backtest_func=replay_after_marker,
            matrix_func=_fake_matrix,
            measurement_gate_func=gate_after_marker,
        )

        self.assertEqual(events, ["backtest", "gate"])
        self.assertEqual(report["measurement_gate"]["state"], "healthy")
        self.assertEqual(report["variants"][0]["verdict"]["status"], "forward_watch_candidate")

    def test_cached_mode_skips_challengers_to_avoid_false_comparison(self):
        report = run_profitability_lab_cycle(
            run_backtests=False,
            variant_ids=["incumbent_broad", "short_term_calls"],
            load_result_func=lambda truth_lane: _fake_replay(truth_lane=truth_lane),
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        self.assertEqual(report["variants"][0]["status"], "evaluated")
        self.assertEqual(report["variants"][1]["status"], "skipped")
        self.assertEqual(report["variants"][1]["verdict"]["status"], "not_evaluated")

    def test_loop_writes_json_and_markdown_artifacts(self):
        tmp = WorkspaceTempDir(prefix="profitability-lab")
        self.addCleanup(tmp.cleanup)

        result = run_profitability_lab_loop(
            cycles=1,
            output_root=Path(tmp.name),
            run_backtests=True,
            variant_ids=["incumbent_broad"],
            backtest_func=_fake_replay,
            matrix_func=_fake_matrix,
            measurement_gate_func=_healthy_gate,
        )

        artifact = result["artifacts"][0]
        self.assertTrue(Path(artifact["json"]).exists())
        self.assertTrue(Path(artifact["markdown"]).exists())
        self.assertTrue(Path(result["history_jsonl"]).exists())
        self.assertTrue(Path(result["active_run"]).exists())
        payload = json.loads(Path(artifact["json"]).read_text(encoding="utf8"))
        self.assertEqual(payload["cycle_index"], 1)
        self.assertEqual(payload["status"], "watch")
        markdown = render_profitability_lab_markdown(payload)
        self.assertIn("Options Profitability Lab", markdown)
        self.assertIn("Incumbent Broad", markdown)
        self.assertIn("Research PF", markdown)
        self.assertIn("Proof PF", markdown)
        self.assertIn("nearest-listed historical pricing", markdown)

    def test_lab_run_duplicate_fingerprint_finds_existing_report(self):
        tmp = WorkspaceTempDir(prefix="profitability-lab-dupe")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fingerprint = build_lab_run_fingerprint(
            truth_lane="historical_imported_daily",
            pricing_lane="pessimistic",
            lookback_years=3,
            n_picks=3,
            iv_adj=1.2,
            min_trades=20,
            min_profit_factor=1.2,
            min_directional_accuracy=50.0,
            run_backtests=True,
            variants=["bullish_index_calls_quality90_debit55"],
        )
        run_dir = root / "runs" / "profit_lab_test"
        run_dir.mkdir(parents=True)
        report_path = run_dir / "report.json"
        report_path.write_text(json.dumps({"run_fingerprint": fingerprint}), encoding="utf8")

        self.assertEqual(find_duplicate_lab_run(root, fingerprint), report_path)


if __name__ == "__main__":
    unittest.main()
