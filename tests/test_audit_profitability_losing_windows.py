from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.audit_profitability_losing_windows import build_losing_window_audit
from workspace_tempdir import WorkspaceTempDir


class AuditProfitabilityLosingWindowsTests(unittest.TestCase):
    def test_cli_help_runs_from_repo_root(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "audit_profitability_losing_windows.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Audit where a profitability replay loses money", result.stdout)

    def test_build_losing_window_audit_groups_exact_trade_losses(self):
        tmp = WorkspaceTempDir(prefix="loss-window-audit")
        self.addCleanup(tmp.cleanup)
        run_path = Path(tmp.name) / "run.json"
        run_path.write_text(
            json.dumps(
                {
                    "playbook": "bullish_index_calls_score70",
                    "pricing_lane": "pessimistic",
                    "lookback_years": 2,
                    "n_picks": 3,
                    "trades": [
                        {
                            "date": "2024-03-25",
                            "ticker": "QQQ",
                            "entry_contract_resolution": "exact_target_contract",
                            "exit_reason": "stop",
                            "net_pnl_pct": -90,
                            "quality_score": 75,
                            "direction_score": 88,
                            "tech_score": 96,
                            "dte": 25,
                            "net_debit": 9,
                            "spread_width": 20,
                            "spy_ret5": 2.1,
                        },
                        {
                            "date": "2024-03-26",
                            "ticker": "QQQ",
                            "entry_contract_resolution": "exact_target_contract",
                            "exit_reason": "time_exit",
                            "net_pnl_pct": -10,
                            "quality_score": 78,
                            "direction_score": 80,
                            "tech_score": 90,
                            "dte": 24,
                            "net_debit": 8,
                            "spread_width": 20,
                            "spy_ret5": 1.1,
                        },
                        {
                            "date": "2024-03-27",
                            "ticker": "SPY",
                            "entry_contract_resolution": "nearest_listed_contract",
                            "exit_reason": "time_exit",
                            "net_pnl_pct": -50,
                        },
                        {
                            "date": "2024-04-01",
                            "ticker": "SPY",
                            "entry_contract_resolution": "exact_target_contract",
                            "exit_reason": "time_exit",
                            "net_pnl_pct": 20,
                            "quality_score": 82,
                            "direction_score": 91,
                            "tech_score": 94,
                            "dte": 25,
                            "net_debit": 7,
                            "spread_width": 20,
                            "spy_ret5": 0.5,
                        },
                    ],
                }
            ),
            encoding="utf8",
        )

        audit = build_losing_window_audit(run_path, min_group_trades=1)

        self.assertEqual(audit["exact_trade_metrics"]["trades"], 3)
        self.assertEqual(audit["losing_trade_count"], 2)
        self.assertEqual(audit["worst_trades"][0]["ticker"], "QQQ")
        ticker_groups = [row for row in audit["worst_groups"] if row["dimension"] == "ticker"]
        self.assertTrue(any(row["key"] == "QQQ" and row["avg_pnl_pct"] == -50 for row in ticker_groups))
        debit_filters = [row for row in audit["candidate_filters"] if row["key"] == "debit<50%"]
        self.assertEqual(debit_filters[0]["trades"], 3)

    def test_archived_exact_basis_uses_primary_judge_rows_only(self):
        tmp = WorkspaceTempDir(prefix="loss-window-audit-archived")
        self.addCleanup(tmp.cleanup)
        run_path = Path(tmp.name) / "run.json"
        run_path.write_text(
            json.dumps(
                {
                    "authoritative_profitability_basis": "archived_exact_contract_only",
                    "primary_judge_trade_class": "exact_archived_contract",
                    "trades": [
                        {
                            "date": "2024-03-25",
                            "ticker": "QQQ",
                            "entry_contract_resolution": "exact_archived_contract",
                            "exit_reason": "stop",
                            "net_pnl_pct": -20,
                            "net_debit": 5,
                            "spread_width": 20,
                        },
                        {
                            "date": "2024-03-26",
                            "ticker": "SPY",
                            "entry_contract_resolution": "exact_target_contract",
                            "exit_reason": "target",
                            "net_pnl_pct": 80,
                            "net_debit": 5,
                            "spread_width": 20,
                        },
                        {
                            "date": "2024-03-27",
                            "ticker": "IWM",
                            "entry_contract_resolution": "nearest_listed_contract",
                            "exit_reason": "target",
                            "net_pnl_pct": 100,
                        },
                    ],
                }
            ),
            encoding="utf8",
        )

        audit = build_losing_window_audit(run_path, min_group_trades=1)

        self.assertEqual(audit["exact_trade_metrics"]["trades"], 1)
        self.assertEqual(audit["losing_trade_count"], 1)
        self.assertEqual(audit["worst_trades"][0]["ticker"], "QQQ")


if __name__ == "__main__":
    unittest.main()
