from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_lane_lab import (  # noqa: E402
    evaluate_ai_commodity_data_readiness,
    evaluate_current_paper_book,
    evaluate_data_readiness,
    evaluate_historical_debit_controls,
    lane_definitions,
    run_lane_lab,
)
from workspace_tempdir import WorkspaceTempDir  # noqa: E402


def _metric(payload: dict, *keys: str):
    for key in keys:
        if key in payload:
            return payload[key]
    raise AssertionError(f"missing expected metric key in {sorted(payload)}")


class LaneLabTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="lane-lab")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_lane_definitions_start_with_expected_lane_ids(self):
        self.assertTrue(callable(run_lane_lab))

        lane_ids = [lane["id"] for lane in lane_definitions()]

        self.assertEqual(
            lane_ids[:5],
            [
                "fill_discipline",
                "liquidity_first_spread",
                "high_debit_control",
                "gld_macro_breakout",
                "relative_strength_pullback",
            ],
        )
        self.assertIn("ai_commodity_infra_observation", lane_ids)

    def test_current_paper_metrics_from_tracked_positions_db(self):
        db_path = self.tmp / "tracked_positions.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE tracked_positions (
                    id TEXT PRIMARY KEY,
                    ticker TEXT,
                    status TEXT,
                    last_pnl_pct REAL,
                    source_pick_snapshot TEXT
                )
                """
            )
            rows = [
                ("spy-win", "SPY", "open", 12.5, {"net_debit": 2.0, "spread_width": 5.0}),
                ("qqq-loss", "QQQ", "open", -4.0, {"net_debit": 1.5, "spread_width": 5.0}),
                ("iwm-closed", "IWM", "closed", 30.0, {"net_debit": 1.0, "spread_width": 5.0}),
            ]
            conn.executemany(
                "INSERT INTO tracked_positions VALUES (?, ?, ?, ?, ?)",
                [(id_, ticker, status, pnl, json.dumps(snapshot)) for id_, ticker, status, pnl, snapshot in rows],
            )

        metrics = evaluate_current_paper_book(db_path)

        self.assertEqual(_metric(metrics, "open_position_count", "position_count"), 2)
        self.assertEqual(_metric(metrics, "winner_count", "winning_position_count"), 1)
        self.assertEqual(_metric(metrics, "loser_count", "losing_position_count"), 1)
        self.assertAlmostEqual(_metric(metrics, "paper_pnl_pct_points", "total_pnl_pct_points"), 8.5)

    def test_historical_debit_control_compares_high_debit_to_cheap_debit(self):
        run_path = self.tmp / "historical_run.json"
        run_path.write_text(
            json.dumps(
                {
                    "trades": [
                        {"id": "cheap-win", "net_debit": 2.0, "spread_width": 5.0, "pnl_pct": 40.0},
                        {"id": "cheap-loss", "net_debit": 2.4, "spread_width": 5.0, "pnl_pct": -10.0},
                        {"id": "high-loss", "net_debit": 3.5, "spread_width": 5.0, "pnl_pct": -30.0},
                        {"id": "high-flat", "net_debit": 3.1, "spread_width": 5.0, "pnl_pct": 0.0},
                    ]
                }
            ),
            encoding="utf8",
        )

        control = evaluate_historical_debit_controls(run_path)

        cheap = _metric(control, "cheap_debit", "cheap_debit_control")
        high = _metric(control, "high_debit", "high_debit_control")
        self.assertEqual(_metric(cheap, "trade_count", "count"), 2)
        self.assertEqual(_metric(high, "trade_count", "count"), 2)
        self.assertGreater(
            _metric(cheap, "avg_pnl_pct", "average_pnl_pct"),
            _metric(high, "avg_pnl_pct", "average_pnl_pct"),
        )
        self.assertEqual(control.get("preferred_control"), "cheap_debit")

    def test_data_readiness_blocks_missing_gld_tlt_iwm(self):
        readiness_path = self.tmp / "readiness.json"
        readiness_path.write_text(
            json.dumps(
                {
                    "status": "ready_for_exact_replay",
                    "available_underlyings": ["SPY", "QQQ"],
                    "required_underlying_health": {
                        "SPY": {"quote_date_count": 20},
                        "QQQ": {"quote_date_count": 20},
                    },
                }
            ),
            encoding="utf8",
        )

        readiness = evaluate_data_readiness(["GLD", "TLT", "IWM"], readiness_path)

        self.assertEqual(readiness["status"], "blocked")
        self.assertEqual(readiness["blocker"], "missing_required_symbols")
        self.assertEqual(readiness["missing_required_symbols"], ["GLD", "IWM", "TLT"])

    def test_ai_commodity_readiness_requires_full_scan_universe(self):
        readiness_path = self.tmp / "readiness.json"
        readiness_path.write_text(
            json.dumps(
                {
                    "status": "ready_for_exact_replay",
                    "available_underlyings": ["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG"],
                    "shared_required_quote_dates": {"count": 120},
                }
            ),
            encoding="utf8",
        )

        readiness = evaluate_ai_commodity_data_readiness(
            core_symbols=["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG"],
            expansion_symbols=["ALB", "URA"],
            readiness_path=readiness_path,
        )

        self.assertEqual(readiness["status"], "blocked")
        self.assertEqual(readiness["proof"]["status"], "blocked")
        self.assertEqual(readiness["missing_required_symbols"], ["ALB", "URA"])
        self.assertIn("missing_required_underlyings", readiness["blockers"])

    def test_ai_commodity_readiness_promotes_full_scan_universe(self):
        symbols = ["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG", "ALB", "URA"]
        readiness_path = self.tmp / "readiness.json"
        readiness_path.write_text(
            json.dumps(
                {
                    "status": "ready_for_exact_replay",
                    "available_underlyings": symbols,
                    "shared_required_quote_dates": {"count": 120},
                }
            ),
            encoding="utf8",
        )

        readiness = evaluate_ai_commodity_data_readiness(
            core_symbols=symbols[:9],
            expansion_symbols=symbols[9:],
            readiness_path=readiness_path,
        )

        self.assertEqual(readiness["status"], "full_scan_ready")
        self.assertEqual(readiness["proof_symbols"], sorted(symbols))
        self.assertEqual(readiness["blockers"], [])

    def test_ai_commodity_readiness_accepts_in_memory_no_write_readiness(self):
        symbols = ["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG", "ALB", "URA"]

        readiness = evaluate_ai_commodity_data_readiness(
            core_symbols=symbols[:9],
            expansion_symbols=symbols[9:],
            readiness_path=self.tmp / "missing-readiness.json",
            readiness_payload={
                "status": "ready_for_exact_replay",
                "available_underlyings": symbols,
                "shared_required_quote_dates": {"count": 120},
            },
        )

        self.assertEqual(readiness["status"], "full_scan_ready")
        self.assertEqual(readiness["proof"]["source"], "in_memory_paid_data_readiness")
        self.assertEqual(readiness["blockers"], [])

    def test_ai_commodity_readiness_blocks_thin_shared_calendar(self):
        readiness_path = self.tmp / "readiness.json"
        readiness_path.write_text(
            json.dumps(
                {
                    "status": "ready_for_exact_replay",
                    "available_underlyings": ["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG"],
                    "shared_required_quote_dates": {"count": 1},
                }
            ),
            encoding="utf8",
        )

        readiness = evaluate_ai_commodity_data_readiness(
            core_symbols=["FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG"],
            expansion_symbols=[],
            readiness_path=readiness_path,
        )

        self.assertEqual(readiness["status"], "blocked")
        self.assertIn("insufficient_shared_quote_dates", readiness["blockers"])


if __name__ == "__main__":
    unittest.main()
