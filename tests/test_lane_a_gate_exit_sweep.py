import json
import unittest
from pathlib import Path

from scripts.lane_a_gate_exit_sweep import (
    LANE_A_GATE_SUITE,
    LANE_A_PLAYBOOK,
    lane_a_pre_registered_plan,
    run_lane_a_gate_sweep,
)
from workspace_tempdir import WorkspaceTempDir


class LaneAGateExitSweepTests(unittest.TestCase):
    def test_plan_pre_registers_pullback_gate_and_exit_sweeps(self):
        plan = lane_a_pre_registered_plan()

        self.assertEqual(plan["playbook"], LANE_A_PLAYBOOK)
        self.assertEqual(plan["gate_suite"], LANE_A_GATE_SUITE)
        self.assertEqual(len(plan["gate_hypotheses"]), 10)
        self.assertEqual(len(plan["exit_configs"]), 5)
        self.assertEqual(plan["authoritative_profitability_basis"], "exact_contract_only")

    def test_gate_sweep_uses_lane_a_suite(self):
        tmp = WorkspaceTempDir(prefix="lane-a-gate")
        self.addCleanup(tmp.cleanup)
        run_path = Path(tmp.name) / "lane_a_run.json"
        trades = []
        for idx in range(5):
            trades.append(
                {
                    "date": "2026-05-01",
                    "ticker": "SPY",
                    "entry_contract_resolution": "exact_target_contract",
                    "pnl_pct": -1.0 if idx == 0 else 10.0,
                    "net_debit": 4.0,
                    "spread_width": 10.0,
                    "signal_ret5": -1.5,
                    "signal_ret20": 5.0,
                    "direction_score": 80.0,
                    "quality_score": 70.0,
                }
            )
        run_path.write_text(
            json.dumps({"playbook": LANE_A_PLAYBOOK, "trades": trades}),
            encoding="utf8",
        )

        sweep = run_lane_a_gate_sweep(run_path=run_path, min_trades=1, min_profit_factor=1.05)

        self.assertEqual(sweep["hypothesis_suite"], LANE_A_GATE_SUITE)
        self.assertEqual(sweep["hypothesis_count"], 10)
        ret20 = next(item for item in sweep["results"] if item["id"] == "lane_a_ret20_ge_4")
        self.assertEqual(ret20["verdict"], "candidate_for_replay")


if __name__ == "__main__":
    unittest.main()
