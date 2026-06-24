from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_dispersion_proxy_hybrid_replay_readiness as readiness
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


class RegularOptionsDispersionProxyHybridReplayReadinessTests(unittest.TestCase):
    def _valid_preregistration(self, tmp: Path) -> Path:
        path = tmp / "latest.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_preregistered_dispersion_proxy_hybrid_playbook",
                "status": "preregistered_design_only",
                "concept_id": readiness.CONCEPT_ID,
                "structure": readiness.EXPECTED_STRUCTURE,
                "accepted_profitability": False,
                "historical_replay_performed": False,
                "lane_implementation_performed": False,
                "undefined_or_uncapped_pair_risk_allowed": False,
                "concept": {"undefined_or_uncapped_pair_risk_allowed": False},
            },
        )
        return path

    def _feature_store(self, tmp: Path) -> Path:
        path = tmp / "feature.json"
        _write_json(
            path,
            {
                "source_label": "thetadata_opra_nbbo_1m",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "join_contract": "feature.tradable_after_time <= candidate_entry_time",
                "symbols": ["SPY", "QQQ", "AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
            },
        )
        return path

    def _source_quality(self, tmp: Path) -> Path:
        path = tmp / "source-quality.json"
        _write_json(
            path,
            {
                "rules": [
                    {
                        "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                        "reason": "zero_bid_tradability_floor_failure",
                        "prohibited_actions": ["do_not_lower_90pct_executable_quote_floor"],
                    }
                ]
            },
        )
        return path

    def _blocked_vix(self, tmp: Path) -> Path:
        path = tmp / "vix.json"
        _write_json(
            path,
            {
                "status": "blocked_point_in_time_vix_source_missing",
                "point_in_time_vix_low_mid_bucket_available": False,
                "blockers": ["point_in_time_vix_source_missing"],
            },
        )
        return path

    def _ready_vix(self, tmp: Path) -> Path:
        path = tmp / "vix-ready.json"
        _write_json(path, {"status": "ready", "point_in_time_vix_low_mid_bucket_available": True})
        return path

    def _blocked_dispersion_proxy(self, tmp: Path) -> Path:
        path = tmp / "dispersion-proxy.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                "status": "blocked_point_in_time_dispersion_concentration_proxy",
                "blockers": ["missing_point_in_time_dispersion_proxy_source"],
                "coverage": {"covered_month_count": 0, "date_coverage_pct": 0.0},
            },
        )
        return path

    def _ready_dispersion_proxy(self, tmp: Path) -> Path:
        path = tmp / "dispersion-proxy-ready.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_point_in_time_dispersion_concentration_proxy",
                "status": "point_in_time_dispersion_concentration_proxy_available",
                "blockers": [],
                "coverage": {"covered_month_count": 1, "date_coverage_pct": 100.0},
            },
        )
        return path

    def _holdout(self, tmp: Path) -> Path:
        path = tmp / "holdout.json"
        _write_json(path, {"contract_id": "forward_holdout_contract", "status": "active"})
        return path

    def test_report_is_read_only_and_blocks_missing_dispersion_and_vix(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            evidence = tmp / "evidence.py"
            _write_text(evidence, "dispersion design mentions pair_entry_cashflow but no exact known-at source")
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                source_quality_policy_path=self._source_quality(tmp),
                point_in_time_dispersion_concentration_proxy_path=self._blocked_dispersion_proxy(tmp),
                point_in_time_vix_bucket_path=self._blocked_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[evidence],
                generated_at_utc="2026-06-23T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_dispersion_proxy_hybrid_replay_readiness")
        for key, expected in readiness.READ_ONLY_FLAGS.items():
            self.assertIs(report[key], expected)
        self.assertFalse(report["accepted_profitability"])
        self.assertIn("missing_dispersion_or_concentration_proxy_inputs", report["blockers"])
        self.assertIn("point_in_time_vix_bucket_blocked", report["blockers"])

    def test_invalid_or_uncapped_preregistration_fails_closed(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            invalid = tmp / "bad.json"
            _write_json(
                invalid,
                {
                    "status": "preregistered_design_only",
                    "concept_id": readiness.CONCEPT_ID,
                    "structure": readiness.EXPECTED_STRUCTURE,
                    "accepted_profitability": False,
                    "historical_replay_performed": False,
                    "lane_implementation_performed": False,
                    "undefined_or_uncapped_pair_risk_allowed": True,
                },
            )
            report = readiness.build_report(
                preregistered_playbook_path=invalid,
                feature_store_path=self._feature_store(tmp),
                source_quality_policy_path=self._source_quality(tmp),
                point_in_time_dispersion_concentration_proxy_path=self._ready_dispersion_proxy(tmp),
                point_in_time_vix_bucket_path=self._ready_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[],
            )

        self.assertEqual(report["status"], "blocked_invalid_dispersion_proxy_hybrid_preregistration")
        self.assertFalse(report["preregistration_validation"]["valid"])
        self.assertIn("undefined_or_uncapped_pair_risk_not_false", report["preregistration_validation"]["reasons"])
        self.assertEqual(report["critical_prerequisites"], [])

    def test_exact_evidence_can_reach_ready_status(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            exact = tmp / "exact.py"
            _write_text(
                exact,
                """
point_in_time_dispersion_proxy = True
point_in_time_concentration_proxy = True
pair_entry_cashflow = credit_side_entry - debit_side_entry
debit_side_entry = 1
debit_side_exit_value = 1
credit_side_entry = 1
credit_side_exit_debit = 1
pair_net_pnl_usd = 1
pair_max_loss_usd = 100
required_collateral_usd = 100
denominator = ["rejected_dispersion_proxy_missing", "rejected_pair_universe_mismatch", "rejected_undefined_or_uncapped_risk", "missing_leg_quote", "zero_bid_or_untradable", "exact_entry_captured", "assignment_or_expiration_blocked", "exact_exit_captured", "missing_exit"]
assignment and expiration classifier
strict-new dedupe against 157-row clean base stack
proof_eligible = False
production proof is forbidden
""",
            )
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                source_quality_policy_path=self._source_quality(tmp),
                point_in_time_dispersion_concentration_proxy_path=self._ready_dispersion_proxy(tmp),
                point_in_time_vix_bucket_path=self._ready_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[exact],
            )

        self.assertEqual(report["status"], "dispersion_proxy_hybrid_replay_readiness_ready")
        self.assertEqual(report["blockers"], [])
        self.assertIsNone(report["smallest_next_blocker_clearing_slice"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-readiness") as tmp_dir:
            tmp = Path(tmp_dir)
            evidence = tmp / "evidence.py"
            _write_text(evidence, "dispersion")
            report = readiness.build_report(
                preregistered_playbook_path=self._valid_preregistration(tmp),
                feature_store_path=self._feature_store(tmp),
                source_quality_policy_path=self._source_quality(tmp),
                point_in_time_dispersion_concentration_proxy_path=self._blocked_dispersion_proxy(tmp),
                point_in_time_vix_bucket_path=self._blocked_vix(tmp),
                forward_holdout_contract_path=self._holdout(tmp),
                evidence_paths=[evidence],
            )
            artifacts = readiness.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "readiness.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "readiness.md").exists())
            self.assertIn("docs_report", artifacts)
            markdown = (tmp / "docs" / "readiness.md").read_text(encoding="utf8")
            self.assertIn("Regular Options Dispersion-Proxy Hybrid Replay Readiness", markdown)
            self.assertIn("Critical Prerequisites", markdown)


if __name__ == "__main__":
    unittest.main()
