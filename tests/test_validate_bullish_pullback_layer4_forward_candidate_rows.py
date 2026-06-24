from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_bullish_pullback_layer4_forward_capture_protocol as protocol
from scripts import validate_bullish_pullback_layer4_forward_candidate_rows as validator


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _valid_row(**overrides) -> dict:
    row = {
        "row_id": "bp4-20260615-aapl-1",
        "lane_id": protocol.SELECTED_LANE_ID,
        "layer_id": protocol.SELECTED_LAYER_ID,
        "variant_id": protocol.SELECTED_VARIANT_ID,
        "ticker": "AAPL",
        "selection_date": "2026-06-15",
        "denominator_status": "exact_exit_captured",
        "scanner_run_id": "scan-1",
        "scanner_policy_hash": "policy-hash",
        "long_contract_symbol": "AAPL260717C00200000",
        "short_contract_symbol": "AAPL260717C00210000",
        "long_entry_bid": 4.9,
        "long_entry_ask": 5.1,
        "short_entry_bid": 2.0,
        "short_entry_ask": 2.1,
        "long_exit_bid": 7.2,
        "long_exit_ask": 7.4,
        "short_exit_bid": 3.1,
        "short_exit_ask": 3.2,
        "entry_quote_evidence_class": "trusted_opra_nbbo",
        "exit_quote_evidence_class": "trusted_opra_nbbo",
        "policy_exit_condition": "time_exit",
        "contract_multiplier": 100,
        "fee_total_usd": 2.6,
        "net_pnl_usd": 107.4,
    }
    row.update(overrides)
    return row


class BullishPullbackLayer4ForwardCandidateValidatorTests(unittest.TestCase):
    def test_valid_future_denominator_rows_validate_without_append(self) -> None:
        rows = [
            _valid_row(),
            _valid_row(
                row_id="bp4-20260615-aapl-open",
                denominator_status="open_waiting_policy_exit",
                long_exit_bid=None,
                long_exit_ask=None,
                short_exit_bid=None,
                short_exit_ask=None,
                policy_exit_condition=None,
                net_pnl_usd=None,
            ),
            _valid_row(
                row_id="bp4-20260615-aapl-missed",
                denominator_status="missed_entry",
                long_entry_bid=None,
                long_entry_ask=None,
                short_entry_bid=None,
                short_entry_ask=None,
                policy_exit_condition=None,
                net_pnl_usd=None,
            ),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rows.jsonl"
            _write_jsonl(path, rows)
            report = validator.validate_rows(path)

        self.assertTrue(report["candidate_rows_would_be_valid_for_future_approval"])
        self.assertFalse(report["append_allowed"])
        self.assertFalse(report["cohort_append_performed"])
        self.assertEqual(report["exact_completed_candidate_count"], 1)
        self.assertEqual(report["open_waiting_policy_exit_count"], 1)
        self.assertEqual(report["missed_entry_count"], 1)

    def test_rejects_dangerous_non_proof_rows(self) -> None:
        rows = [
            _valid_row(row_id="wrong-lane", lane_id="volatility_expansion_observation"),
            _valid_row(row_id="wrong-layer", layer_id="layer_5_count_expanded"),
            _valid_row(row_id="wrong-symbol", ticker="TSLA"),
            _valid_row(row_id="pre-freeze", selection_date="2026-06-14"),
            _valid_row(row_id="missing-leg", long_contract_symbol=""),
            _valid_row(row_id="missing-entry", long_entry_bid=None),
            _valid_row(row_id="missing-exit", long_exit_bid=None),
            _valid_row(row_id="missing-policy", policy_exit_condition=""),
            _valid_row(row_id="missing-net", net_pnl_usd=None),
            _valid_row(row_id="source-mark", entry_price_source="source_mark"),
            _valid_row(row_id="zero", short_exit_bid=0.0),
            _valid_row(row_id="percent-only", net_pnl_usd=None, net_pnl_pct=0.12),
            _valid_row(row_id="duplicate"),
            _valid_row(row_id="duplicate"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rows.jsonl"
            _write_jsonl(path, rows)
            report = validator.validate_rows(path)

        self.assertFalse(report["candidate_rows_would_be_valid_for_future_approval"])
        rejects = report["reject_counts"]
        for reason in [
            "wrong_lane",
            "wrong_layer",
            "non_allowed_symbol",
            "pre_freeze_date",
            "missing_leg_identity",
            "missing_entry_quote",
            "missing_exit_quote",
            "missing_policy_exit",
            "missing_net_pnl_usd",
            "non_executable_or_source_mark_basis",
            "zero_or_untradable_claimed_as_exact_proof",
            "percent_only_pnl",
            "duplicate_row_id",
        ]:
            self.assertGreaterEqual(rejects.get(reason, 0), 1, reason)

    def test_missing_candidate_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = validator.validate_rows(Path(temp_dir) / "missing.jsonl")

        self.assertEqual(report["overall_status"], "candidate_rows_rejected_or_unavailable_no_append")
        self.assertFalse(report["candidate_source"]["exists"])
        self.assertFalse(report["candidate_rows_would_be_valid_for_future_approval"])


if __name__ == "__main__":
    unittest.main()
