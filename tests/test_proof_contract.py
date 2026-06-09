from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import proof_contract as contract  # noqa: E402


class ProofContractTests(unittest.TestCase):
    def _live_proof_row(self, **overrides):
        source = {
            "selection_source": contract.REQUIRED_LIVE_SELECTION_SOURCE,
            "options_data_source": "alpaca_opra",
            "quote_time_et": "2026-04-06T10:00:00-04:00",
            "quote_freshness_status": "fresh",
            "entry_execution_price": 4.5,
            "entry_execution_basis": "ask",
            "source_scan_lineage_verified": True,
        }
        source.update(overrides.pop("source_pick_snapshot", {}))
        row = {
            "status": "closed",
            "proof_eligible": True,
            "proof_class": contract.LIVE_SCAN_EXACT_PROOF_CLASS,
            "contract_symbol": "SPY260619C00600000",
            "entry_execution_price": 4.5,
            "entry_execution_basis": "ask",
            "exit_execution_price": 5.5,
            "exit_execution_basis": "spread_bid_ask_exact",
            "net_pnl_pct": 22.2,
            "source_scan_session_id": 55,
            "source_scan_event_key": "short_term:rank_1",
            "source_scan_run_id": "api_scan_20260406T100000Z",
            "source_scan_recorded_at_utc": "2026-04-06T14:00:00Z",
            "source_pick_snapshot": source,
        }
        row.update(overrides)
        return row

    def test_contract_exposes_canonical_proof_classes(self):
        self.assertEqual(contract.LIVE_SCAN_EXACT_PROOF_CLASS, "live_scan_exact_contract")
        self.assertEqual(contract.MANUAL_BROKER_EXACT_PROOF_CLASS, "manual_broker_exact_contract")
        self.assertEqual(contract.INELIGIBLE_PROOF_CLASS, "ineligible")
        self.assertIn("alpaca_opra", contract.TRUSTED_OPTIONS_SOURCE_LABELS)
        self.assertIn("source_scan_event_key", contract.REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS)
        self.assertEqual(
            contract.PROOF_EVIDENCE_CONTRACT["frontendGroups"]["displayPrecedence"],
            [
                "lifecycle_only",
                "historical_paper",
                "research_backfill",
                "proof_ineligible",
                "manual_exact",
                "live_exact",
                "legacy_unclassified",
            ],
        )

    def test_research_backfill_markers_block_production_proof(self):
        row = self._live_proof_row(
            source_pick_snapshot={
                "selection_source": contract.REQUIRED_LIVE_SELECTION_SOURCE,
                "options_data_source": "alpaca_opra",
                "quote_time_et": "2026-04-06T10:00:00-04:00",
                "quote_freshness_status": "fresh",
                "entry_execution_price": 4.5,
                "entry_execution_basis": "ask",
                "source_scan_lineage_verified": True,
                "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
                "pricing_evidence_class": "research_backfill",
            },
        )

        self.assertTrue(contract.row_has_research_backfill_marker(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_top_level_research_identity_marker_blocks_production_proof(self):
        row = self._live_proof_row(backfill_audit_id="audit-1")

        self.assertTrue(contract.row_has_research_backfill_marker(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

        research_only_row = self._live_proof_row(research_only=True)
        self.assertTrue(contract.row_has_research_backfill_marker(research_only_row))
        self.assertFalse(contract.row_counts_as_production_proof(research_only_row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(research_only_row))

    def test_proof_grade_exact_closed_requires_contract_and_live_proof(self):
        row = self._live_proof_row()

        self.assertTrue(contract.row_counts_as_production_proof(row))
        self.assertTrue(contract.row_counts_as_proof_grade_exact_closed(row))
        row.pop("contract_symbol")
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_stale_live_proof_flag_without_lineage_or_entry_is_not_proof(self):
        row = {
            "status": "closed",
            "proof_eligible": True,
            "proof_class": contract.LIVE_SCAN_EXACT_PROOF_CLASS,
            "contract_symbol": "SPY260619C00600000",
            "source_pick_snapshot": {"options_data_source": "alpaca_opra"},
            "exit_execution_price": 5.5,
            "exit_execution_basis": "spread_bid_ask_exact",
            "net_pnl_pct": 22.2,
        }

        self.assertFalse(contract.row_has_verified_live_scan_lineage(row))
        self.assertFalse(contract.row_has_executable_entry(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_non_opra_source_blocks_stored_row_proof(self):
        row = self._live_proof_row(source_pick_snapshot={"options_data_source": "non_opra_vendor"})

        self.assertFalse(contract.row_has_trusted_opra_source(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_stale_quote_freshness_blocks_stored_row_proof(self):
        row = self._live_proof_row(source_pick_snapshot={"quote_freshness_status": "stale"})

        self.assertFalse(contract.row_has_executable_entry(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_missing_quote_freshness_blocks_stored_row_proof(self):
        row = self._live_proof_row(source_pick_snapshot={"quote_freshness_status": None})

        self.assertFalse(contract.row_has_executable_entry(row))
        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_closed_truth_grade_requires_trusted_exit_and_calculable_pnl(self):
        lifecycle_exit = self._live_proof_row(
            exit_execution_price=None,
            exit_execution_basis="lifecycle_elapsed",
        )
        missing_pnl = self._live_proof_row(net_pnl_pct=None, gross_pnl_pct=None)
        missing_pnl.pop("exit_option_price", None)

        self.assertFalse(contract.row_has_trusted_executable_exit(lifecycle_exit))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(lifecycle_exit))
        self.assertTrue(contract.row_has_trusted_executable_exit(missing_pnl))
        self.assertTrue(contract.row_has_calculable_realized_pnl(missing_pnl))
        missing_pnl["entry_execution_price"] = None
        missing_pnl["entry_option_price"] = None
        missing_pnl["source_pick_snapshot"]["entry_execution_price"] = None
        self.assertFalse(contract.row_has_calculable_realized_pnl(missing_pnl))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(missing_pnl))

    def test_closed_at_requires_closed_exit_even_when_status_is_missing(self):
        row = self._live_proof_row(status=None, closed_at="2026-04-06T20:00:00Z")
        row["exit_execution_price"] = None
        row["exit_option_price"] = None
        row["exit_execution_basis"] = None

        self.assertFalse(contract.row_counts_as_production_proof(row))
        self.assertFalse(contract.row_counts_as_proof_grade_exact_closed(row))

    def test_scan_pick_research_marker_uses_shared_tokens(self):
        self.assertTrue(
            contract.scan_pick_has_research_backfill_marker(
                {"selection_source": "historical_chain_native_exact_contract"}
            )
        )
        self.assertTrue(contract.scan_pick_has_research_backfill_marker({"research_only": True}))
        for field, value in {
            "pricing_evidence_class": "historical_replay",
            "profitability_evidence_class": "historical_selection",
            "source_separation": "historical_chain_native",
        }.items():
            self.assertTrue(contract.scan_pick_has_research_backfill_marker({field: value}))
        self.assertFalse(
            contract.scan_pick_has_research_backfill_marker(
                {"selection_source": "live_chain_exact_contract"}
            )
        )
        self.assertFalse(
            contract.scan_pick_has_research_backfill_marker(
                {
                    "selection_source": "live_chain_exact_contract",
                    "pricing_evidence_class": "proof_live_opra_exact_contract",
                    "profitability_evidence_class": "research_profitability_calibration",
                    "source_separation": "pricing_proof_profitability_research",
                    "promotion_class": "research_bootstrap",
                }
            )
        )

    def test_row_evidence_classifier_keeps_live_research_calibration_live_exact(self):
        row = self._live_proof_row(
            source_pick_snapshot={
                "pricing_evidence_class": "proof_live_opra_exact_contract",
                "profitability_evidence_class": "research_profitability_calibration",
                "source_separation": "pricing_proof_profitability_research",
                "promotion_class": "research_bootstrap",
                "source_label": "alpaca_opra",
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
            }
        )

        self.assertFalse(contract.row_has_research_backfill_marker(row))
        summary = contract.classify_row_evidence(row)
        quote = contract.classify_quote_evidence(row)
        self.assertEqual(summary["proof_contract_version"], contract.PROOF_EVIDENCE_CONTRACT_VERSION)
        self.assertEqual(summary["evidence_group"], "live_exact")
        self.assertTrue(summary["production_proof"])
        self.assertTrue(summary["truth_grade_closed"])
        self.assertEqual(quote["quote_evidence_class"], "trusted_intraday_opra_nbbo")
        self.assertTrue(quote["production_proof_source_eligible"])

    def test_quote_evidence_classifier_separates_daily_and_synthetic_sources(self):
        trusted_daily = self._live_proof_row(
            source_pick_snapshot={
                "source_label": "alpaca_opra_daily_snapshot",
                "snapshot_kind": "daily_eod",
                "data_trust": "trusted",
            }
        )
        research_daily = self._live_proof_row(
            source_pick_snapshot={
                "source_label": "onclickmedia_research_grade_eod_bidask",
                "snapshot_kind": "daily_eod",
                "data_trust": "research",
            }
        )
        synthetic = self._live_proof_row(
            source_pick_snapshot={
                "truth_source": "synthetic_research",
                "data_trust": "synthetic",
            }
        )

        self.assertEqual(contract.classify_quote_evidence(trusted_daily)["quote_evidence_class"], "trusted_daily_eod")
        self.assertFalse(contract.classify_quote_evidence(trusted_daily)["production_proof_source_eligible"])
        self.assertEqual(contract.classify_quote_evidence(research_daily)["quote_evidence_class"], "research_eod")
        self.assertEqual(contract.classify_quote_evidence(synthetic)["quote_evidence_class"], "synthetic_research")


if __name__ == "__main__":
    unittest.main()
