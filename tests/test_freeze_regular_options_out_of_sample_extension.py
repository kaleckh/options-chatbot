from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import freeze_regular_options_out_of_sample_extension as freeze


class FreezeRegularOptionsOutOfSampleExtensionTests(unittest.TestCase):
    def _write_policy_contract(self, directory: Path, *, tamper_hash: bool = False) -> Path:
        conditions = [
            {
                "field": "ticker",
                "op": "in",
                "value": ["NEM", "JNJ", "GOOGL", "AAPL", "IWM", "CVX", "SPY", "QQQ"],
            },
            {
                "field": "signal_evidence.prior_20_trading_day_return_pct",
                "op": "gte",
                "value": 10.990605,
            },
        ]
        contract = {
            "report_id": "regular_options_frozen_filtered_policy",
            "policy_id": "historical_filtered_candidate_policy_v1",
            "filter_id": "train_ranked_top_8_tickers__signal_evidence_prior_20_trading_day_return_pct_gte_10.9906",
            "conditions": conditions,
            "conditions_sha256": "bad-hash" if tamper_hash else freeze._conditions_sha256(conditions),
        }
        path = directory / "policy.json"
        path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
        return path

    def test_build_contract_freezes_phase_15_1_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = self._write_policy_contract(root)
            registry_path = root / "registry.json"
            contract = freeze.build_contract(
                policy_contract_path=policy_path,
                consumption_registry_path=registry_path,
                frozen_at_utc="2026-07-02T12:00:00Z",
            )

        self.assertEqual(contract["contract_id"], "regular_options_out_of_sample_extension_v1")
        self.assertEqual(contract["target_window"]["requested_start_month"], "2022-01")
        self.assertEqual(contract["target_window"]["requested_end_month"], "2024-05")
        self.assertEqual(contract["target_window"]["provider_received_status"], "pending_phase_15_2_import")
        self.assertTrue(contract["target_window"]["record_requested_vs_received_on_import"])
        self.assertEqual(contract["proof_set"]["symbol_count"], 13)
        self.assertEqual(
            contract["proof_set"]["symbols"],
            ["SPY", "QQQ", "IWM", "DIA", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
        )
        self.assertEqual(contract["frozen_policy"]["policy_id"], "historical_filtered_candidate_policy_v1")
        self.assertEqual(
            contract["frozen_policy"]["conditions_sha256"],
            contract["source_policy_contract"]["conditions_sha256"],
        )
        self.assertEqual(contract["gates"]["cluster_key"], "ticker:ISO-week")
        self.assertEqual(contract["gates"]["bootstrap_draws"], 10000)
        self.assertGreater(contract["gates"]["percent_cluster_pf_lb_5pct_must_be_gt"], 0.999)
        self.assertGreater(contract["gates"]["usd_cluster_pf_lb_5pct_must_be_gt"], 0.999)
        self.assertEqual(contract["gates"]["total_net_pnl_usd_must_be_gt"], 0.0)
        self.assertEqual(contract["fee_model"]["fee_per_contract_leg_usd"], 0.65)
        self.assertEqual(contract["fee_model"]["total_fees_usd_formula"], "4 * fee_per_contract_leg_usd")
        self.assertEqual(
            contract["evaluation_scope"]["registry_disposition_on_evaluation"],
            "consumed_for_evaluation",
        )
        self.assertTrue(contract["evaluation_scope"]["filter_modification_prohibited"])
        self.assertTrue(contract["evaluation_scope"]["threshold_change_prohibited"])
        self.assertTrue(contract["evaluation_scope"]["new_filter_family_prohibited"])
        self.assertTrue(contract["evaluation_scope"]["phase_15_2_import_not_started_by_this_contract"])
        self.assertEqual(contract["interpretation"]["pre_registered_expectation"], "uncertain")
        self.assertEqual(
            contract["interpretation"]["failure_verdict"],
            "park_filter_hypothesis_tracker_may_continue",
        )
        self.assertEqual(
            contract["interpretation"]["passing_verdict"],
            "historically_consistent_still_awaiting_forward_bar",
        )
        self.assertTrue(contract["interpretation"]["neither_outcome_authorizes_trading"])
        for flag in freeze.FALSE_FLAGS:
            self.assertIs(contract[flag], False)

    def test_main_requires_freeze_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = self._write_policy_contract(root)
            output_path = root / "contract.json"
            with self.assertRaises(SystemExit):
                freeze.main(
                    [
                        "--freeze-token",
                        "wrong",
                        "--policy-contract",
                        str(policy_path),
                        "--output",
                        str(output_path),
                    ]
                )
            self.assertFalse(output_path.exists())

    def test_write_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = self._write_policy_contract(root)
            output_path = root / "contract.json"
            freeze.main(
                [
                    "--freeze-token",
                    freeze.FREEZE_TOKEN,
                    "--policy-contract",
                    str(policy_path),
                    "--output",
                    str(output_path),
                ]
            )
            with self.assertRaises(SystemExit):
                freeze.main(
                    [
                        "--freeze-token",
                        freeze.FREEZE_TOKEN,
                        "--policy-contract",
                        str(policy_path),
                        "--output",
                        str(output_path),
                    ]
                )

    def test_rejects_tampered_policy_conditions_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = self._write_policy_contract(Path(tmp), tamper_hash=True)
            with self.assertRaises(SystemExit):
                freeze.build_contract(policy_contract_path=policy_path)


if __name__ == "__main__":
    unittest.main()
