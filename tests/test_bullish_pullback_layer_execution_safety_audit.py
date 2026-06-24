from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer_execution_safety_audit as audit


NOW = "2026-06-21T18:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")


def _layer_stack(generated_at: str = "2026-06-01T00:00:00Z") -> dict:
    return {
        "generated_at": generated_at,
        "paper_shadow_only": True,
        "ordered_layers": [
            {
                "layer_id": "layer_4_clean_exact",
                "variant_id": audit.PRIMARY_VARIANT_ID,
                "source_result_path": "source-run.json",
                "metrics": {
                    "candidate_trade_count": 129,
                    "exact_trade_count": 129,
                    "profit_factor": 2.20,
                    "quote_coverage_pct": 100.0,
                    "stress_5pct_per_side_profit_factor": 1.67,
                    "unpriced_trade_count": 0,
                },
            }
        ],
    }


def _selector(generated_at: str = NOW, source_path: str = "source-run.json") -> dict:
    return {
        "generated_at_utc": generated_at,
        "overall_status": "layer_shadow_selection_ready",
        "primary_harness_layer": {
            "layer_id": "layer_4_clean_exact",
            "variant_id": audit.PRIMARY_VARIANT_ID,
            "source_result_path": source_path,
        },
        "harness_requirements": {
            "selected_layer_id": "layer_4_clean_exact",
            "selected_variant_id": audit.PRIMARY_VARIANT_ID,
            "source_result_path": source_path,
        },
    }


def _base_row() -> dict:
    return {
        "ticker": "NEM",
        "date": "2025-08-15",
        "exit_date": "2025-09-15",
        "target_expiry": "2025-09-19",
        "strategy_type": "vertical_spread",
        "contract_symbol": "NEM250919C00070000",
        "short_contract_symbol": "NEM250919C00075000",
        "entry_px": 1.45,
        "exit_px": 4.05,
        "exit_reason": "time_exit",
        "exit_fill_basis": "imported_spread_mark",
        "entry_contract_resolution": "exact_listed_spread_contract",
        "contract_selection_source": "chain_native_listed_spread",
    }


def _ready_row() -> dict:
    row = _base_row()
    row.update(
        {
            "long_entry_bid": 1.40,
            "long_entry_ask": 1.50,
            "short_entry_bid": 0.04,
            "short_entry_ask": 0.05,
            "long_exit_bid": 4.20,
            "long_exit_ask": 4.30,
            "short_exit_bid": 0.20,
            "short_exit_ask": 0.25,
        }
    )
    return row


def _source_run(rows: list[dict], run_at: str = "2026-06-01T00:00:00Z") -> dict:
    return {
        "run_at": run_at,
        "result_path": "source-run.json",
        "candidate_trade_count": 129,
        "exact_contract_match_count": 129,
        "profit_factor": 2.20,
        "quote_coverage_pct": 100.0,
        "trades": rows,
    }


def _write_sources(root: Path, *, rows: list[dict] | None = None, selector_payload: dict | None = None) -> dict[str, Path]:
    layer_stack_path = root / "layer-stack.json"
    selector_path = root / "selector.json"
    source_run_path = root / "source-run.json"
    _write_json(layer_stack_path, _layer_stack())
    _write_json(selector_path, selector_payload or _selector(source_path="source-run.json"))
    _write_json(source_run_path, _source_run(rows or [_ready_row() for _ in range(129)]))
    return {
        "layer_stack_path": layer_stack_path,
        "layer_shadow_selection_path": selector_path,
        "selected_source_run_path": source_run_path,
    }


def _write_quote_db(path: Path, *, match_source_prices: bool = True, zero_exit_bid: bool = False) -> Path:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
            source_label TEXT NOT NULL,
            dataset_kind TEXT NOT NULL DEFAULT 'intraday_csv',
            data_trust TEXT NOT NULL DEFAULT 'trusted',
            input_path TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL,
            total_rows INTEGER NOT NULL,
            imported_rows INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            rejected_rows INTEGER NOT NULL,
            warnings_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE option_quote_snapshots (
            id INTEGER PRIMARY KEY,
            as_of_utc TEXT NOT NULL,
            quote_date_et TEXT NOT NULL,
            quote_minute_et INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL DEFAULT 'intraday',
            underlying TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            expiry TEXT NOT NULL,
            option_type TEXT NOT NULL,
            strike REAL NOT NULL,
            bid REAL,
            ask REAL,
            last REAL,
            iv REAL,
            underlying_price REAL,
            volume INTEGER,
            open_interest INTEGER,
            source_batch_id INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX idx_option_quotes_contract_date ON option_quote_snapshots(contract_symbol, snapshot_kind, quote_date_et, quote_minute_et)"
    )
    conn.execute(
        """
        INSERT INTO import_batches (
            id, source_label, dataset_kind, data_trust, input_path, file_hash, imported_at_utc,
            total_rows, imported_rows, duplicate_rows, rejected_rows, warnings_json
        )
        VALUES (1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture.csv', 'hash', ?, 4, 4, 0, 0, '[]')
        """,
        (NOW,),
    )
    entry_long_ask = 1.50 if match_source_prices else 1.80
    exit_long_bid = 4.20 if match_source_prices else 4.60
    if zero_exit_bid:
        exit_long_bid = 0.0
    rows = [
        ("2025-08-15T14:10:00Z", "2025-08-15", audit.DEFAULT_ENTRY_MINUTE_ET, "NEM250919C00070000", 70.0, 1.40, entry_long_ask),
        ("2025-08-15T14:10:00Z", "2025-08-15", audit.DEFAULT_ENTRY_MINUTE_ET, "NEM250919C00075000", 75.0, 0.05, 0.06),
        ("2025-09-15T19:55:00Z", "2025-09-15", audit.DEFAULT_EXIT_MINUTE_ET, "NEM250919C00070000", 70.0, exit_long_bid, 4.30),
        ("2025-09-15T19:55:00Z", "2025-09-15", audit.DEFAULT_EXIT_MINUTE_ET, "NEM250919C00075000", 75.0, 0.10, 0.15),
    ]
    conn.executemany(
        """
        INSERT INTO option_quote_snapshots (
            as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying, contract_symbol,
            expiry, option_type, strike, bid, ask, source_batch_id
        )
        VALUES (?, ?, ?, 'intraday', 'NEM', ?, '2025-09-19', 'call', ?, ?, ?, 1)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return path


class BullishPullbackLayerExecutionSafetyAuditTests(unittest.TestCase):
    def test_ready_when_all_rows_have_leg_level_bid_ask_and_policy_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            report = audit.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "ready_for_future_market_window_paper_shadow_preflight")
        self.assertTrue(report["preflight_ready"])
        self.assertEqual(report["selected_layer"]["layer_id"], "layer_4_clean_exact")
        self.assertEqual(report["selected_layer"]["metrics"]["exact_trade_count"], 129)
        counts = report["row_counts"]
        self.assertEqual(counts["total_selected_rows"], 129)
        self.assertEqual(counts["rows_with_leg_level_entry_bid_ask"], 129)
        self.assertEqual(counts["rows_with_leg_level_exit_bid_ask"], 129)
        self.assertEqual(counts["rows_with_side_aware_entry_price"], 129)
        self.assertEqual(counts["rows_with_side_aware_exit_price"], 129)
        self.assertEqual(counts["rows_with_assignment_expiration_classification"], 129)
        self.assertEqual(counts["fatal_blocker_count"], 0)
        self.assertFalse(report["live_entry_allowed"])
        self.assertFalse(report["broker_order_allowed"])
        self.assertFalse(report["mutated_evidence_databases"])

    def test_source_mark_shape_blocks_when_existing_quote_lookup_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rows = [_base_row() for _ in range(129)]
            paths = _write_sources(Path(temp_dir), rows=rows)
            report = audit.build_report(generated_at_utc=NOW, options_history_db_path=Path(temp_dir) / "missing.db", **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertFalse(report["preflight_ready"])
        self.assertIn("existing_quote_lookup_unavailable", report["blockers"])
        self.assertIn("existing_trusted_leg_entry_quotes_missing", report["blockers"])
        self.assertIn("existing_trusted_leg_exit_quotes_missing", report["blockers"])
        counts = report["row_counts"]
        self.assertEqual(counts["total_selected_rows"], 129)
        self.assertEqual(counts["rows_with_parsed_leg_identity"], 129)
        self.assertEqual(counts["rows_with_source_run_leg_level_entry_bid_ask"], 0)
        self.assertEqual(counts["rows_with_source_run_leg_level_exit_bid_ask"], 0)
        self.assertEqual(counts["rows_with_existing_trusted_entry_leg_bid_ask"], 0)
        self.assertEqual(counts["rows_with_existing_trusted_exit_leg_bid_ask"], 0)
        self.assertEqual(counts["rows_with_leg_level_entry_bid_ask"], 0)
        self.assertEqual(counts["rows_with_leg_level_exit_bid_ask"], 0)
        self.assertEqual(counts["rows_with_assignment_expiration_classification"], 129)
        self.assertEqual(counts["crossed_or_missing_quote_rows"], 129)
        self.assertEqual(counts["fatal_blocker_count"], 129)

    def test_existing_trusted_quotes_can_resolve_source_mark_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = [_base_row() for _ in range(129)]
            paths = _write_sources(root, rows=rows)
            db_path = _write_quote_db(root / "quotes.db")
            report = audit.build_report(generated_at_utc=NOW, options_history_db_path=db_path, **paths)

        self.assertEqual(report["overall_status"], "ready_for_future_market_window_paper_shadow_preflight")
        counts = report["row_counts"]
        self.assertEqual(counts["rows_with_source_run_leg_level_entry_bid_ask"], 0)
        self.assertEqual(counts["rows_with_existing_trusted_entry_leg_bid_ask"], 129)
        self.assertEqual(counts["rows_with_existing_trusted_exit_leg_bid_ask"], 129)
        self.assertEqual(counts["rows_with_side_aware_entry_price_matching_source_run"], 129)
        self.assertEqual(counts["rows_with_side_aware_exit_price_matching_source_run"], 129)
        self.assertEqual(counts["rows_with_side_aware_price_mismatch"], 0)
        self.assertFalse(report["imported_quotes"])
        self.assertFalse(report["mutated_evidence_databases"])

    def test_existing_trusted_quote_mismatch_blocks_ready_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = [_base_row() for _ in range(129)]
            paths = _write_sources(root, rows=rows)
            db_path = _write_quote_db(root / "quotes.db", match_source_prices=False)
            report = audit.build_report(generated_at_utc=NOW, options_history_db_path=db_path, **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertIn("existing_trusted_side_aware_price_mismatch_with_source_run", report["blockers"])
        self.assertEqual(report["row_counts"]["rows_with_side_aware_price_mismatch"], 129)

    def test_missing_leg_identity_blocks_before_resolution_can_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bad = _base_row()
            bad["contract_symbol"] = "NOT_OCC"
            paths = _write_sources(root, rows=[bad for _ in range(129)])
            db_path = _write_quote_db(root / "quotes.db")
            report = audit.build_report(generated_at_utc=NOW, options_history_db_path=db_path, **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertIn("source_run_missing_leg_identity", report["blockers"])
        self.assertEqual(report["row_counts"]["rows_with_parsed_leg_identity"], 0)

    def test_selector_primary_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            selector_payload = _selector(source_path="source-run.json")
            selector_payload["primary_harness_layer"]["layer_id"] = "layer_5_count_expanded"
            paths = _write_sources(Path(temp_dir), selector_payload=selector_payload)
            report = audit.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertIn("selector_primary_layer_drift", report["blockers"])

    def test_stale_layer_stack_fails_closed_when_age_limit_is_tight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            report = audit.build_report(generated_at_utc=NOW, max_source_age_hours=24, **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertTrue(any("stale" in reason for reason in report["blockers"]))

    def test_missing_source_run_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = _write_sources(Path(temp_dir))
            paths["selected_source_run_path"].unlink()
            report = audit.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], "blocked_execution_safety_preflight")
        self.assertIn("selected_layer_source_run:missing_readback", report["blockers"])


if __name__ == "__main__":
    unittest.main()
