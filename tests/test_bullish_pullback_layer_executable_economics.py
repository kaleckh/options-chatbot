from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer_executable_economics as econ
from scripts import build_bullish_pullback_layer_execution_safety_audit as audit


NOW = "2026-06-21T20:30:00Z"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf8")
    return path


def _source_row(index: int, *, source_net: float = -50.0) -> dict:
    return {
        "ticker": "NEM",
        "date": f"2025-08-{15 + index:02d}",
        "exit_date": f"2025-09-{15 + index:02d}",
        "contract_symbol": f"NEM250919C0007{index:04d}",
        "short_contract_symbol": f"NEM250919C0008{index:04d}",
        "entry_px": 1.0,
        "exit_px": 0.5,
        "net_pnl_usd": source_net,
        "fee_total_usd": 2.6,
    }


def _identity(row: dict) -> str:
    return "|".join([row["ticker"], row["date"], row["contract_symbol"], row["short_contract_symbol"]])


def _audit_row(source: dict, *, entry: float = 1.0, exit_price: float = 2.0, zero: bool = False, missing: bool = False) -> dict:
    side_exit = None if missing else exit_price
    fatal = []
    if missing:
        fatal.extend(["missing_leg_level_exit_bid_ask", "missing_side_aware_exit_price"])
    if zero:
        fatal.append("zero_bid_or_untradable_leg_quote")
    fatal.append("side_aware_price_mismatch_with_source_run")
    return {
        "candidate_identity": _identity(source),
        "ticker": source["ticker"],
        "entry_date": source["date"],
        "exit_date": source["exit_date"],
        "entry_quote_provenance": {
            "side_aware_entry_price": entry,
            "source_entry_price": source["entry_px"],
        },
        "exit_quote_provenance": {
            "side_aware_exit_price": side_exit,
            "source_exit_price": source["exit_px"],
        },
        "side_aware_price_mismatch_with_source_run": True,
        "zero_bid_or_untradable": zero,
        "crossed_or_missing_quote": missing,
        "fatal_blockers": fatal,
    }


def _audit_payload(rows: list[dict]) -> dict:
    return {
        "report_id": "bullish_pullback_layer_execution_safety_audit",
        "generated_at_utc": NOW,
        "overall_status": "blocked_execution_safety_preflight",
        "selected_layer": {
            "layer_id": audit.PRIMARY_LAYER_ID,
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
        },
        "row_counts": {
            "rows_with_parsed_leg_identity": len(rows),
            "rows_with_existing_trusted_entry_leg_bid_ask": len(rows),
            "rows_with_existing_trusted_exit_leg_bid_ask": sum(1 for row in rows if not row.get("crossed_or_missing_quote")),
            "rows_with_side_aware_entry_price": len(rows),
            "rows_with_side_aware_exit_price": sum(
                1 for row in rows if row.get("exit_quote_provenance", {}).get("side_aware_exit_price") is not None
            ),
            "zero_bid_or_untradable_rows": sum(1 for row in rows if row.get("zero_bid_or_untradable")),
            "crossed_or_missing_quote_rows": sum(1 for row in rows if row.get("crossed_or_missing_quote")),
            "rows_with_side_aware_price_mismatch": len(rows),
        },
        "audit_rows": rows,
    }


def _write_fixture(root: Path, *, audit_rows: list[dict], source_rows: list[dict]) -> dict[str, Path]:
    return {
        "execution_safety_audit_path": _write_json(root / "audit.json", _audit_payload(audit_rows)),
        "selected_source_run_path": _write_json(root / "source-run.json", {"run_at": NOW, "trades": source_rows}),
    }


class BullishPullbackLayerExecutableEconomicsTests(unittest.TestCase):
    def test_computes_side_aware_usd_pnl_instead_of_source_marks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_rows = [_source_row(i, source_net=-500.0) for i in range(129)]
            audit_rows = [_audit_row(row, entry=1.0, exit_price=2.0) for row in source_rows]
            paths = _write_fixture(root, audit_rows=audit_rows, source_rows=source_rows)
            report = econ.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], econ.STATUS_PROFITABLE_BUT_BLOCKED)
        metrics = report["denominator_views"]["tradable_executable_only"]
        self.assertEqual(metrics["row_count"], 129)
        self.assertGreater(metrics["net_usd_total"], 0)
        self.assertLess(report["denominator_views"]["source_mark_comparison"]["source_mark_metrics"]["net_usd_total"], 0)
        self.assertIn("source_mark_mismatch_rows", report["blockers"])
        self.assertFalse(report["imported_quotes"])
        self.assertFalse(report["mutated_evidence_databases"])

    def test_missing_required_quotes_keep_full_denominator_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_rows = [_source_row(i) for i in range(129)]
            audit_rows = [_audit_row(row, entry=1.0, exit_price=2.0) for row in source_rows]
            audit_rows[0] = _audit_row(source_rows[0], missing=True)
            paths = _write_fixture(root, audit_rows=audit_rows, source_rows=source_rows)
            report = econ.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], econ.STATUS_PROFITABLE_BUT_BLOCKED)
        self.assertIn("missing_required_quotes", report["blockers"])
        self.assertEqual(report["row_counts"]["missing_required_quote_rows"], 1)
        self.assertEqual(report["denominator_views"]["full_selected_fail_closed"]["selected_rows"], 129)

    def test_zero_untradable_rows_are_not_used_as_executable_pf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_rows = [_source_row(i) for i in range(129)]
            audit_rows = [_audit_row(row, entry=1.0, exit_price=2.0) for row in source_rows]
            audit_rows[0] = _audit_row(source_rows[0], entry=1.0, exit_price=2.0, zero=True)
            paths = _write_fixture(root, audit_rows=audit_rows, source_rows=source_rows)
            report = econ.build_report(generated_at_utc=NOW, **paths)

        self.assertIn("zero_or_untradable_rows", report["blockers"])
        self.assertEqual(report["row_counts"]["zero_or_untradable_rows"], 1)
        self.assertEqual(report["row_counts"]["tradable_executable_rows"], 128)

    def test_negative_side_aware_pf_rejects_current_harness_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_rows = [_source_row(i, source_net=500.0) for i in range(129)]
            audit_rows = [_audit_row(row, entry=2.0, exit_price=1.0) for row in source_rows]
            paths = _write_fixture(root, audit_rows=audit_rows, source_rows=source_rows)
            report = econ.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], econ.STATUS_NEGATIVE_OR_FLAT)
        self.assertEqual(report["harness_decision"], "rejected_for_current_harness_selection")
        self.assertFalse(report["promotion_ready"])

    def test_selected_layer_drift_fails_source_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_rows = [_source_row(i) for i in range(129)]
            audit_rows = [_audit_row(row) for row in source_rows]
            paths = _write_fixture(root, audit_rows=audit_rows, source_rows=source_rows)
            payload = json.loads(paths["execution_safety_audit_path"].read_text())
            payload["selected_layer"]["layer_id"] = "layer_5_count_expanded"
            paths["execution_safety_audit_path"].write_text(json.dumps(payload), encoding="utf8")
            report = econ.build_report(generated_at_utc=NOW, **paths)

        self.assertEqual(report["overall_status"], econ.STATUS_SOURCE_SHAPE_MISSING)
        self.assertIn("selected_layer_drift", report["blockers"])


if __name__ == "__main__":
    unittest.main()
