from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_13_symbol_frozen_daily_candidate_decisions as decisions
from scripts import regular_options_frozen_candidate_generation_entrypoint as entrypoint


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _cohort() -> dict:
    return {
        "contract_id": "forward-cohort-preregistration",
        "status": "active",
        "cohort": {"freeze_date": "2026-06-14", "eval_date": "2026-07-28", "frozen": True},
        "lanes": [
            {
                "lane_id": "volatility_expansion_observation",
                "policy_snapshot_sha256": "vol",
                "symbols": ["SPY", "QQQ", "IWM", "DIA"],
            },
            {
                "lane_id": "bullish_pullback_observation",
                "policy_snapshot_sha256": "bull",
                "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"],
            },
        ],
    }


def _feature() -> dict:
    return {
        "report_id": "regular_options_feature_store",
        "status": "feature_store_built",
        "shared_quote_dates": ["2026-02-02", "2026-02-03"],
    }


def _daily_rows(status: str = "explicit_no_pick") -> list[dict]:
    rows: list[dict] = []
    for day in ("2026-02-02", "2026-02-03"):
        for lane in _cohort()["lanes"]:
            for symbol in lane["symbols"]:
                rows.append(
                    {
                        "date": day,
                        "lane": lane["lane_id"],
                        "underlying": symbol,
                        "status": status,
                        "proof_safe": True,
                    }
                )
    rows[0]["status"] = "selected_candidate"
    return rows


class RegularOptions13SymbolFrozenDailyCandidateDecisionsTests(unittest.TestCase):
    def test_requires_exact_universe_and_reports_no_write_truthfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())

            with self.assertRaises(ValueError):
                decisions.build_report(
                    forward_cohort_path=cohort,
                    feature_store_path=feature,
                    universe=["SPY"],
                    no_write=True,
                )

            report = decisions.build_report(forward_cohort_path=cohort, feature_store_path=feature, no_write=False)
            self.assertTrue(report["read_only"])
            self.assertFalse(report["no_write"])
            self.assertTrue(report["source_data_no_write"])
            self.assertTrue(report["report_artifact_write_requested"])

    def test_default_materializer_fails_closed_with_exact_missing_scanner_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_daily_candidate_decisions")
        self.assertEqual(report["daily_candidate_decision_row_count"], 28)
        self.assertEqual(
            report["daily_status_counts"],
            {"blocked_missing_historical_scanner_replay_adapter": 28},
        )
        self.assertIn("missing_historical_scanner_replay_adapter", report["blockers"])
        self.assertIn("missing_historical_scanner_point_in_time_inputs", report["blockers"])
        self.assertIn("candidate_generation_months_0_below_requested_1", report["blockers"])
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["scanner_policy_changed"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["scanner_replay_surface"]["adapter_available"])
        self.assertTrue(report["scanner_replay_surface"]["signature_support_available"])
        self.assertFalse(report["scanner_replay_surface"]["end_to_end_no_write_scanner_replay_available"])
        self.assertEqual(report["scanner_replay_surface"]["decision"], "end_to_end_no_write_scanner_replay_unavailable")
        self.assertIsNotNone(report["missing_inputs"][0]["missing_command"])

    def test_provided_proof_safe_daily_source_can_materialize_ready_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(source, {"daily_candidate_generation": _daily_rows(), "allowed_universe": list(decisions.ALLOWED_UNIVERSE)})
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "frozen_daily_candidate_decisions_ready")
        self.assertEqual(report["coverage"]["calendar_months_covered_count"], 1)
        self.assertEqual(report["daily_candidate_decision_row_count"], 28)
        self.assertEqual(report["selected_candidate_row_count"], 1)
        self.assertEqual(report["blockers"], [])
        self.assertTrue(report["source_integrity"]["source_exact_frozen_daily_decisions"])
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")
        self.assertFalse(report["daily_candidate_decisions"][0]["scanner_parity"])
        self.assertFalse(report["daily_candidate_decisions"][0]["production_scanner_replay"])
        self.assertEqual(report["daily_candidate_decisions"][0]["tradable_after"], "2026-02-02T15:10:00Z")

    def test_source_quote_and_decision_timestamps_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            rows = _daily_rows()
            rows[0].update(
                {
                    "known_at": "2026-02-01T21:00:00Z",
                    "tradable_after": "2026-02-02T15:13:00Z",
                    "decision_timestamp_utc": "2026-02-02T15:13:00Z",
                    "entry_quote_timestamp_utc": "2026-02-02T15:13:00Z",
                    "long_entry_quote_timestamp_utc": "2026-02-02T15:12:00Z",
                    "short_entry_quote_timestamp_utc": "2026-02-02T15:13:00Z",
                    "exit_quote_timestamp_utc": "2026-02-18T20:56:00Z",
                    "gross_pnl_pct": 10.0,
                    "pnl_pct": 10.0,
                    "net_pnl_pct": 9.0,
                    "net_pnl_pct_after_fees": 8.5,
                }
            )
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(source, {"daily_candidate_generation": rows, "allowed_universe": list(decisions.ALLOWED_UNIVERSE)})

            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
            )

        selected = report["selected_candidates"][0]
        self.assertEqual(selected["known_at"], "2026-02-01T21:00:00Z")
        self.assertEqual(selected["tradable_after"], "2026-02-02T15:13:00Z")
        self.assertEqual(selected["decision_timestamp_utc"], "2026-02-02T15:13:00Z")
        self.assertEqual(selected["entry_quote_timestamp_utc"], "2026-02-02T15:13:00Z")
        self.assertEqual(selected["exit_quote_timestamp_utc"], "2026-02-18T20:56:00Z")
        self.assertEqual(selected["gross_pnl_pct"], 10.0)
        self.assertEqual(selected["net_pnl_pct"], 8.5)
        self.assertEqual(selected["legacy_net_pnl_pct"], 9.0)

    def test_accepted_source_rows_require_explicit_proof_safe_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            rows = _daily_rows()
            rows[0]["proof_safe"] = False
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(source, {"daily_candidate_generation": rows, "allowed_universe": list(decisions.ALLOWED_UNIVERSE)})
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_daily_candidate_decisions")
        self.assertEqual(report["daily_status_counts"]["blocked_daily_candidate_decision_not_proof_safe"], 1)
        self.assertEqual(report["selected_candidate_row_count"], 0)
        blocked = [row for row in report["daily_candidate_decisions"] if row["status"] == "blocked_daily_candidate_decision_not_proof_safe"]
        self.assertEqual(len(blocked), 1)
        self.assertFalse(blocked[0]["proof_safe"])

    def test_broad_or_mismatched_source_artifact_is_rejected_before_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            rows = _daily_rows()
            rows.append(
                {
                    "date": "2026-02-02",
                    "lane": "bullish_pullback_observation",
                    "underlying": "NFLX",
                    "status": "selected_candidate",
                    "proof_safe": True,
                }
            )
            broad_universe = list(decisions.ALLOWED_UNIVERSE) + ["NFLX"]
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(source, {"daily_candidate_generation": rows, "allowed_universe": broad_universe})
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_daily_candidate_decisions")
        self.assertEqual(
            report["daily_status_counts"],
            {"blocked_source_artifact_not_exact_frozen_daily_decision_source": 28},
        )
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertIn("source_artifact_universe_not_13_symbol", report["blockers"])
        self.assertIn("outside_universe_source_rows_present", report["blockers"])
        self.assertEqual(report["source_integrity"]["outside_universe_row_count"], 1)
        self.assertFalse(report["source_integrity"]["source_exact_frozen_daily_decisions"])

    def test_exact_universe_source_with_outside_frozen_pair_is_rejected_before_accepting_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            rows = _daily_rows()
            rows.append(
                {
                    "date": "2026-02-02",
                    "lane": "volatility_expansion_observation",
                    "underlying": "AAPL",
                    "status": "selected_candidate",
                    "proof_safe": True,
                }
            )
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            _write_json(source, {"daily_candidate_generation": rows, "allowed_universe": list(decisions.ALLOWED_UNIVERSE)})
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                source_daily_decisions_path=source,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_daily_candidate_decisions")
        self.assertIn("source_artifact_frozen_pairs_not_exact", report["blockers"])
        self.assertGreater(report["source_integrity"]["outside_frozen_pair_row_count"], 0)
        self.assertEqual(report["source_integrity"]["outside_universe_row_count"], 0)
        self.assertFalse(report["source_integrity"]["source_exact_frozen_daily_decisions"])
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertTrue(report["daily_candidate_decisions"])
        self.assertFalse(any(row["proof_safe"] for row in report["daily_candidate_decisions"]))
        self.assertFalse(any(row["selected_candidate"] for row in report["daily_candidate_decisions"]))
        self.assertFalse(any(row["explicit_no_pick"] for row in report["daily_candidate_decisions"]))

    def test_entrypoint_preserves_blocked_source_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            source = root / "source.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            source_report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            _write_json(source, source_report)
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                as_of_date="2026-06-04",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["daily_status_counts"], {"blocked_missing_historical_scanner_replay_adapter": 28})
        self.assertIn("missing_historical_scanner_replay_adapter", report["blockers"])
        self.assertIn("missing_historical_scanner_point_in_time_inputs", report["blockers"])
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 0)
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")

    def test_write_outputs_creates_new_artifact_directory_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cohort = root / "cohort.json"
            feature = root / "feature.json"
            _write_json(cohort, _cohort())
            _write_json(feature, _feature())
            report = decisions.build_report(
                forward_cohort_path=cohort,
                feature_store_path=feature,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            artifacts = decisions.write_outputs(report, output_dir=root / "out", docs_report=root / "out" / "latest.md")

            self.assertFalse(report["no_write"])
            self.assertTrue(report["report_artifact_write_performed"])
            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "out" / "daily_candidate_decisions.jsonl").exists())
            self.assertTrue((root / "out" / "selected_candidates.jsonl").exists())
            self.assertTrue(artifacts["daily_candidate_decisions_jsonl"].replace("\\", "/").endswith("/out/daily_candidate_decisions.jsonl"))


if __name__ == "__main__":
    unittest.main()
