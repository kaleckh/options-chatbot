from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_profitability_hypothesis_sweep import (
    HYPOTHESIS_SUITES,
    build_hypothesis_sweep,
    build_sweep_fingerprint,
    find_duplicate_sweep,
)
from workspace_tempdir import WorkspaceTempDir


class RunProfitabilityHypothesisSweepTests(unittest.TestCase):
    def _write_fixture_run(self, root: Path) -> Path:
        run_path = root / "run.json"
        trades = []
        for idx in range(10):
            trades.append(
                {
                    "date": f"2025-01-{idx + 1:02d}",
                    "ticker": "SPY",
                    "entry_contract_resolution": "exact_target_contract",
                    "net_pnl_pct": 10,
                    "net_debit": 4,
                    "spread_width": 10,
                    "tech_score": 90,
                    "direction_score": 91,
                    "spy_ret5": 1.2,
                }
            )
        for idx in range(10):
            trades.append(
                {
                    "date": f"2025-02-{idx + 1:02d}",
                    "ticker": "QQQ",
                    "entry_contract_resolution": "exact_target_contract",
                    "net_pnl_pct": -10,
                    "net_debit": 7,
                    "spread_width": 10,
                    "tech_score": 96,
                    "direction_score": 82,
                    "spy_ret5": 0.5,
                }
            )
        run_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_score70",
                    "pricing_lane": "pessimistic",
                    "lookback_years": 2,
                    "n_picks": 3,
                    "trades": trades,
                }
            ),
            encoding="utf8",
        )
        return run_path

    def test_build_hypothesis_sweep_ranks_debit_filter(self):
        tmp = WorkspaceTempDir(prefix="hypothesis-sweep")
        self.addCleanup(tmp.cleanup)
        run_path = self._write_fixture_run(Path(tmp.name))

        sweep = build_hypothesis_sweep(run_path, min_trades=10, min_profit_factor=1.2)

        self.assertEqual(sweep["lens"], "exact")
        self.assertEqual(sweep["fingerprint"], build_sweep_fingerprint(run_path, min_trades=10, min_profit_factor=1.2))
        self.assertEqual(sweep["hypothesis_count"], 10)
        max_debit = next(item for item in sweep["results"] if item["id"] == "max_debit_lt_50")
        self.assertEqual(max_debit["verdict"], "candidate_for_replay")
        self.assertEqual(max_debit["metrics"]["trades"], 10)
        self.assertGreater(max_debit["metrics"]["avg_pnl_pct"], 0)

    def test_all_priced_lens_includes_nearest_contract_research_rows(self):
        tmp = WorkspaceTempDir(prefix="hypothesis-lens")
        self.addCleanup(tmp.cleanup)
        run_path = self._write_fixture_run(Path(tmp.name))
        payload = json.loads(run_path.read_text(encoding="utf8"))
        payload["trades"].append(
            {
                "date": "2025-03-01",
                "ticker": "SPY",
                "entry_contract_resolution": "nearest_listed_contract",
                "net_pnl_pct": 25,
                "net_debit": 4,
                "spread_width": 10,
                "tech_score": 90,
                "direction_score": 91,
                "spy_ret5": 1.2,
            }
        )
        run_path.write_text(json.dumps(payload), encoding="utf8")

        exact = build_hypothesis_sweep(run_path, min_trades=1, min_profit_factor=1.2, lens="exact")
        all_priced = build_hypothesis_sweep(run_path, min_trades=1, min_profit_factor=1.2, lens="all-priced")

        self.assertEqual(exact["baseline"]["trades"], 20)
        self.assertEqual(all_priced["baseline"]["trades"], 21)
        self.assertNotEqual(exact["fingerprint"], all_priced["fingerprint"])

    def test_batch2_is_a_distinct_ten_hypothesis_suite(self):
        batch1_ids = {item["id"] for item in HYPOTHESIS_SUITES["batch1"]}
        batch2_ids = {item["id"] for item in HYPOTHESIS_SUITES["batch2"]}

        self.assertEqual(len(batch2_ids), 10)
        self.assertFalse(batch1_ids & batch2_ids)

    def test_lane_a_pullback_suite_is_pre_registered(self):
        lane_a_ids = {item["id"] for item in HYPOTHESIS_SUITES["lane_a_pullback_gates"]}

        self.assertEqual(len(lane_a_ids), 10)
        self.assertIn("lane_a_ret5_minus2p5_to_minus0p5", lane_a_ids)
        self.assertIn("lane_a_ret20_ge_4", lane_a_ids)
        self.assertIn("lane_a_max_debit_lt_55", lane_a_ids)

    def test_build_hypothesis_sweep_records_suite_name(self):
        tmp = WorkspaceTempDir(prefix="hypothesis-suite")
        self.addCleanup(tmp.cleanup)
        run_path = self._write_fixture_run(Path(tmp.name))

        sweep = build_hypothesis_sweep(
            run_path,
            min_trades=10,
            min_profit_factor=1.2,
            hypotheses=HYPOTHESIS_SUITES["batch2"],
            hypothesis_suite="batch2",
        )

        self.assertEqual(sweep["hypothesis_suite"], "batch2")
        self.assertEqual(sweep["hypothesis_count"], 10)

    def test_find_duplicate_sweep_matches_existing_fingerprint(self):
        tmp = WorkspaceTempDir(prefix="hypothesis-dupe")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        run_path = self._write_fixture_run(root)
        output_dir = root / "sweeps"
        output_dir.mkdir()
        fingerprint = build_sweep_fingerprint(run_path, min_trades=10, min_profit_factor=1.2)
        existing = output_dir / "hypothesis_sweep_existing.json"
        existing.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf8")

        self.assertEqual(find_duplicate_sweep(output_dir, fingerprint), existing)
        other = build_sweep_fingerprint(run_path, min_trades=20, min_profit_factor=1.2)
        self.assertIsNone(find_duplicate_sweep(output_dir, other))


if __name__ == "__main__":
    unittest.main()
