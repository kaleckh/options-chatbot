from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_phase2_drop_decomposition as decomposition


NOW = "2026-07-04T12:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_throughput(
    path: Path,
    *,
    aggregate_drops: int = 4,
    symbol_reasons: int = 4,
    generated_at_utc: str = NOW,
) -> None:
    _write_json(
        path,
        {
            "report_id": "regular_options_forward_candidate_throughput_audit",
            "status": "blocked_no_same_day_phase2_natural_selections",
            "generated_at_utc": generated_at_utc,
            "target_selection_date": "2026-07-02",
            "scheduled_phase2_drop_count_total": aggregate_drops,
            "scheduled_phase2_scan_drop_reason_count_total": symbol_reasons,
        },
    )


def _write_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT,
                playbook TEXT,
                scan_picks_count INTEGER,
                eligibility_status TEXT,
                eligibility_blockers TEXT,
                notes_json TEXT,
                run_id TEXT,
                source_label TEXT
            )
            """
        )
        rows = [
            (
                1,
                "2026-07-02T14:10:00Z",
                "bullish_pullback_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps(
                    {
                        "scan_funnel": {"raw_candidates": 4, "returned_picks": 0, "drop_counts": {"option_liquidity": 2}},
                        "symbol_diagnostics": {
                            "scan_drop_reasons": {
                                "JPM": {
                                    "drop_key": "option_liquidity",
                                    "details": {
                                        "reason": "illiquid_quote",
                                        "liquidity": {"worst_leg_bid_ask_spread_pct": 3.0},
                                        "liquidity_filters": {"liquidity_spread_max_pct": 1.0},
                                    },
                                },
                                "SPY": {
                                    "drop_key": "option_liquidity",
                                    "details": {
                                        "candidate_execution_label": "rejected_liquidity",
                                        "liquidity": {"worst_leg_bid_ask_spread_pct": 2.5},
                                        "liquidity_filters": {"liquidity_spread_max_pct": 1.0},
                                    },
                                },
                            }
                        },
                    }
                ),
                "scheduled_scan:2026-07-02:test:bp",
                "scheduled_scan",
            ),
            (
                2,
                "2026-07-02T15:20:00Z",
                "volatility_expansion_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps(
                    {
                        "scan_funnel": {"raw_candidates": 2, "returned_picks": 0, "drop_counts": {"momentum": 2}},
                        "symbol_diagnostics": {
                            "scan_drop_reasons": {
                                "QQQ": {"drop_key": "momentum", "details": {"reason": "below_momentum"}},
                                "IWM": {"drop_key": "momentum", "details": {"reason": "below_momentum"}},
                            }
                        },
                    }
                ),
                "scheduled_scan:2026-07-02:test:vol",
                "scheduled_scan",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO forward_sessions (
                id, recorded_at_utc, playbook, scan_picks_count, eligibility_status,
                eligibility_blockers, notes_json, run_id, source_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _write_zero_fallback_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT,
                playbook TEXT,
                scan_picks_count INTEGER,
                eligibility_status TEXT,
                eligibility_blockers TEXT,
                notes_json TEXT,
                run_id TEXT,
                source_label TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO forward_sessions (
                id, recorded_at_utc, playbook, scan_picks_count, eligibility_status,
                eligibility_blockers, notes_json, run_id, source_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled_scan')
            """,
            (
                1,
                "2026-07-02T14:10:00Z",
                "bullish_pullback_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps(
                    {
                        "candidate_count": 99,
                        "returned_count": 7,
                        "scan_funnel": {"raw_candidates": 0, "returned_picks": 0, "drop_counts": {"momentum": 1}},
                        "symbol_diagnostics": {
                            "scan_drop_reasons": {
                                "QQQ": {"drop_key": "momentum", "details": {"reason": "below_momentum"}}
                            }
                        },
                    }
                ),
                "scheduled_scan:2026-07-02:test:bp",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_stage_counts_only_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE forward_sessions (
                id INTEGER PRIMARY KEY,
                recorded_at_utc TEXT,
                playbook TEXT,
                scan_picks_count INTEGER,
                eligibility_status TEXT,
                eligibility_blockers TEXT,
                notes_json TEXT,
                run_id TEXT,
                source_label TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO forward_sessions (
                id, recorded_at_utc, playbook, scan_picks_count, eligibility_status,
                eligibility_blockers, notes_json, run_id, source_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled_scan')
            """,
            (
                1,
                "2026-07-02T14:10:00Z",
                "bullish_pullback_observation",
                0,
                "ineligible",
                json.dumps(["no_scan_picks"]),
                json.dumps({"scan_funnel": {"raw_candidates": 2, "returned_picks": 0, "drop_counts": {"momentum": 2}}}),
                "scheduled_scan:2026-07-02:test:bp",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fixture(root: Path) -> dict[str, Path]:
    paths = {
        "ledger": root / "forward_tracking_authoritative.db",
        "throughput": root / "throughput" / "latest.json",
    }
    _write_ledger(paths["ledger"])
    _write_throughput(paths["throughput"])
    return paths


class RegularOptionsPhase2DropDecompositionTests(unittest.TestCase):
    def test_decomposes_symbol_reasons_and_reconciles_to_throughput_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _fixture(Path(tmp))
            report = decomposition.build_report(
                ledger_db_path=paths["ledger"],
                throughput_latest_path=paths["throughput"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "phase2_drop_decomposition_ready")
        self.assertEqual(report["target_selection_date"], "2026-07-02")
        self.assertTrue(report["reconciliation"]["aggregate_drop_count_matches_throughput_latest"])
        self.assertTrue(report["reconciliation"]["symbol_drop_reason_count_matches_throughput_latest"])
        self.assertEqual(report["scheduled_phase2_throughput"]["raw_candidates"], 6)
        self.assertEqual(report["scheduled_phase2_throughput"]["returned_picks"], 0)
        self.assertEqual(report["scheduled_phase2_throughput"]["recorded_drop_denominator"], 4)
        self.assertEqual(report["scheduled_phase2_throughput"]["returned_pick_rate_over_recorded_drops"], 0.0)
        self.assertEqual(report["aggregate_drop_counts"], {"momentum": 2, "option_liquidity": 2})
        decomp = report["symbol_reason_decomposition"]
        self.assertEqual(decomp["drop_key_counts"], {"momentum": 2, "option_liquidity": 2})
        self.assertEqual(decomp["reason_counts"]["illiquid_quote"], 1)
        self.assertEqual(decomp["reason_counts"]["rejected_liquidity"], 1)
        self.assertEqual(decomp["reason_counts"]["below_momentum"], 2)
        self.assertEqual(decomp["symbol_counts"]["JPM"], 1)
        self.assertEqual(decomp["gate_category_counts"]["liquidity_or_history"], 2)
        self.assertEqual(decomp["gate_category_counts"]["signal_or_regime_threshold"], 2)
        self.assertEqual(report["liquidity_or_history_decomposition"]["row_count"], 2)
        self.assertEqual(report["liquidity_or_history_decomposition"]["pct_of_symbol_drop_reasons"], 0.5)
        self.assertEqual(decomp["monthly_breakdown"][0]["month"], "2026-07")
        combined = decomp["symbol_month_drop_key_breakdown"]
        self.assertIn(
            {
                "month": "2026-07",
                "symbol": "JPM",
                "drop_key": "option_liquidity",
                "reason": "illiquid_quote",
                "playbook": "bullish_pullback_observation",
                "gate_category": "liquidity_or_history",
                "count": 1,
            },
            combined,
        )
        self.assertEqual(len(decomp["drop_rows"]), 4)
        survival = report["production_gate_survival"]
        self.assertEqual(survival["overall"]["recorded_drop_denominator"], 4)
        self.assertEqual(survival["overall"]["returned_pick_rate_over_recorded_drops"], 0.0)
        self.assertEqual(len(survival["by_playbook"]), 2)
        self.assertEqual(survival["by_month"][0]["month"], "2026-07")
        self.assertEqual(survival["by_month"][0]["aggregate_drops"], 4)
        self.assertEqual(survival["drop_share_by_drop_key"][0]["drop_key"], "momentum")
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["forward_rows_are_profitability_proof"])
        self.assertFalse(report["promotion_ready"])
        self.assertFalse(report["live_validation_enabled"])
        self.assertFalse(report["auto_track_enabled"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["scanner_policy_changed"])
        self.assertFalse(report["proof_bars_changed"])
        self.assertFalse(report["cohort_append_performed"])

    def test_zero_scan_funnel_counts_do_not_fall_back_to_legacy_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "forward_tracking_authoritative.db"
            throughput = root / "throughput" / "latest.json"
            _write_zero_fallback_ledger(ledger)
            _write_throughput(throughput, aggregate_drops=1, symbol_reasons=1)
            report = decomposition.build_report(
                ledger_db_path=ledger,
                throughput_latest_path=throughput,
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "phase2_drop_decomposition_ready")
        self.assertEqual(report["scheduled_phase2_throughput"]["raw_candidates"], 0)
        self.assertEqual(report["scheduled_phase2_throughput"]["returned_picks"], 0)
        self.assertEqual(report["scheduled_phase2_throughput"]["recorded_drop_denominator"], 1)
        self.assertEqual(report["scheduled_phase2_throughput"]["returned_pick_rate_over_recorded_drops"], 0.0)

    def test_reconciliation_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            _write_throughput(paths["throughput"], aggregate_drops=99, symbol_reasons=4)
            report = decomposition.build_report(
                ledger_db_path=paths["ledger"],
                throughput_latest_path=paths["throughput"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("aggregate_drop_count_mismatch_with_throughput_latest", report["blockers"])

    def test_stale_throughput_latest_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            _write_throughput(paths["throughput"], generated_at_utc="2026-06-20T00:00:00Z")
            report = decomposition.build_report(
                ledger_db_path=paths["ledger"],
                throughput_latest_path=paths["throughput"],
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("throughput_latest_stale_generated_at_utc", report["blockers"])

    def test_stage_counts_without_symbol_reasons_waits_for_reason_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "forward_tracking_authoritative.db"
            throughput = root / "throughput" / "latest.json"
            _write_stage_counts_only_ledger(ledger)
            _write_throughput(throughput, aggregate_drops=2, symbol_reasons=0)
            report = decomposition.build_report(
                ledger_db_path=ledger,
                throughput_latest_path=throughput,
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "phase2_drop_decomposition_waiting_for_symbol_drop_reasons")
        self.assertEqual(report["reconciliation"]["aggregate_drop_count_total"], 2)
        self.assertEqual(report["reconciliation"]["symbol_drop_reason_count_total"], 0)
        self.assertEqual(report["symbol_reason_decomposition"]["drop_rows"], [])

    def test_missing_ledger_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            throughput = root / "throughput" / "latest.json"
            _write_throughput(throughput)
            report = decomposition.build_report(
                ledger_db_path=root / "missing.db",
                throughput_latest_path=throughput,
                generated_at_utc=NOW,
            )

        self.assertEqual(report["status"], "blocked_missing_or_stale_inputs")
        self.assertIn("scheduled_scan_session_source_unavailable", report["blockers"])

    def test_write_outputs_creates_read_only_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            report = decomposition.build_report(
                ledger_db_path=paths["ledger"],
                throughput_latest_path=paths["throughput"],
                generated_at_utc=NOW,
            )
            artifacts = decomposition.write_outputs(report, output_dir=root / "out", docs_report=root / "docs" / "drops.md")
            doc = (root / "docs" / "drops.md").read_text(encoding="utf8")

        self.assertIn("latest_json", artifacts)
        self.assertIn("Phase 2 Drop Decomposition", doc)
        self.assertIn("Top Drop Keys", doc)
        self.assertIn("does not change scanner policy", doc)


if __name__ == "__main__":
    unittest.main()
