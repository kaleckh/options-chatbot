from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_historical_frozen_adapter_exit_quote_repair_demand as demand
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


class RegularOptionsHistoricalFrozenAdapterExitQuoteRepairDemandTests(unittest.TestCase):
    def test_builds_unpriced_trades_for_missing_trusted_exit_quotes_only(self) -> None:
        with WorkspaceTempDir(prefix="adapter-exit-demand") as tmp_dir:
            root = Path(tmp_dir)
            adapter_path = root / "adapter.json"
            _write_json(
                adapter_path,
                {
                    "report_id": "regular_options_historical_frozen_scanner_replay_adapter",
                    "selected_candidates": [
                        {
                            "row_id": "row-1",
                            "ticker": "SPY",
                            "entry_date": "2026-01-05",
                            "exit_date": "2026-01-20",
                            "exit_pricing_status": "missing_trusted_exit_quote",
                            "long_contract_symbol": "SPY260220C00500000",
                            "short_contract_symbol": "SPY260220C00505000",
                        },
                        {
                            "row_id": "row-2",
                            "ticker": "QQQ",
                            "entry_date": "2026-01-06",
                            "exit_pricing_status": "missing_market_day_for_policy_exit",
                            "long_contract_symbol": "QQQ260220C00400000",
                            "short_contract_symbol": "QQQ260220C00405000",
                        },
                        {
                            "row_id": "row-3",
                            "ticker": "IWM",
                            "entry_date": "2026-01-07",
                            "exact_priced": True,
                            "exit_pricing_status": "trusted_exit_priced",
                        },
                    ],
                },
            )
            report = demand.build_report(adapter_path=adapter_path, generated_at_utc="2026-06-29T00:00:00Z")

        self.assertEqual(report["status"], "exit_quote_repair_demand_ready")
        self.assertEqual(report["unpriced_repairable_trade_count"], 1)
        self.assertEqual(report["target_contract_count"], 2)
        self.assertEqual(report["target_quote_dates"], ["2026-01-20"])
        self.assertEqual(report["excluded_unpriced_exit_status_counts"], {"missing_market_day_for_policy_exit": 1})
        self.assertEqual(report["unpriced_trades"][0]["missing_quote_date"], "2026-01-20")
        self.assertEqual(report["unpriced_trades"][0]["missing_long_contract_symbol"], "SPY260220C00500000")
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])

    def test_missing_adapter_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="adapter-exit-demand-missing") as tmp_dir:
            report = demand.build_report(adapter_path=Path(tmp_dir) / "missing.json")

        self.assertEqual(report["status"], "blocked_exit_quote_repair_demand")
        self.assertIn("historical_frozen_adapter_not_loaded", report["blockers"])


if __name__ == "__main__":
    unittest.main()
