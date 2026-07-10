from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
            {"lane_id": "volatility_expansion_observation", "policy_snapshot_sha256": "vol", "symbols": ["SPY", "QQQ", "IWM", "DIA"]},
            {"lane_id": "bullish_pullback_observation", "policy_snapshot_sha256": "bull", "symbols": ["IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"]},
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
                        "proof_safe": False,
                        "research_materializer_safe": True,
                        "read_only": True,
                        "no_write": True,
                        "known_at": f"{day}T14:00:00Z",
                        "tradable_after": f"{day}T15:10:00Z",
                        "decision_timestamp_utc": f"{day}T15:10:00Z",
                        "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
                        "scanner_parity": False,
                        "production_scanner_replay": False,
                    }
                )
    rows[0]["status"] = "selected_candidate"
    rows[0]["entry_quote_timestamp_utc"] = "2026-02-02T15:10:00Z"
    return rows


def _trusted_source(*, rows: list[dict] | None = None, blockers: list[str] | None = None) -> dict:
    proof_blockers = ["production_policy_parity_not_established"]
    return {
        "report_id": entrypoint.TRUSTED_DAILY_SOURCE_REPORT_ID,
        "schema_version": 1,
        "status": "blocked_frozen_daily_candidate_decisions",
        "read_only": True,
        "research_only": True,
        "source_data_no_write": True,
        "research_materializer_status": "research_materializer_ready",
        "research_materializer_ready": True,
        "research_materializer_blockers": [],
        "candidate_materialization_basis": "deterministic_local_pit_candidate_materializer_v1",
        "scanner_parity": False,
        "production_scanner_replay": False,
        "production_parity_mismatches": [{"mismatch_id": "fixture_non_parity"}],
        "historical_selection_conditioning": {"classification": "fixture_current_definition_backfill"},
        "proof_or_nomination_blockers": proof_blockers,
        "allowed_universe": list(entrypoint.ALLOWED_UNIVERSE),
        "frozen_universe": list(entrypoint.ALLOWED_UNIVERSE),
        "requested_window": {
            "window_start": "2026-02-01",
            "window_end": "2026-02-28",
            "as_of_date": entrypoint.DEFAULT_AS_OF_DATE,
        },
        "daily_candidate_generation": _daily_rows() if rows is None else rows,
        "blockers": proof_blockers if blockers is None else blockers,
    }


class RegularOptions13SymbolFrozenCandidateGenerationEntrypointTests(unittest.TestCase):
    def test_requires_exact_requested_universe_and_reports_write_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, _trusted_source(rows=[]))
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())

            with self.assertRaises(ValueError):
                entrypoint.build_report(source_candidate_generation_path=source, feature_store_path=feature, forward_cohort_path=cohort, universe=["SPY"], no_write=True)
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                no_write=False,
            )
            self.assertFalse(report["no_write"])
            self.assertTrue(report["source_data_no_write"])
            self.assertTrue(report["report_artifact_write_requested"])

    def test_explicit_trusted_daily_source_is_research_ready_while_proof_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, _trusted_source())
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_13_symbol_candidate_generation_entrypoint")
        self.assertTrue(report["research_materializer_ready"])
        self.assertIn("production_policy_parity_not_established", report["proof_or_nomination_blockers"])
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 1)
        self.assertEqual(report["daily_candidate_generation_row_count"], 28)
        self.assertEqual(report["selected_candidate_row_count"], 1)
        self.assertEqual(report["outside_universe_row_count"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["scanner_parity"])
        self.assertFalse(report["production_scanner_replay"])
        self.assertEqual(report["candidate_materialization_basis"], "deterministic_local_pit_candidate_materializer_v1")
        self.assertFalse(report["daily_candidate_generation"][0]["scanner_parity"])
        self.assertFalse(report["daily_candidate_generation"][0]["production_scanner_replay"])
        self.assertTrue(report["daily_candidate_generation"][0]["research_materializer_safe"])
        self.assertFalse(report["daily_candidate_generation"][0]["proof_safe"])

    def test_naked_exact_universe_source_is_diagnostic_only_and_never_gets_synthetic_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(
                source,
                {
                    "allowed_universe": list(entrypoint.ALLOWED_UNIVERSE),
                    "daily_candidate_generation": [
                        {
                            "date": row["date"],
                            "lane": row["lane"],
                            "underlying": row["underlying"],
                            "status": row["status"],
                        }
                        for row in _daily_rows()
                    ],
                },
            )
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_13_symbol_candidate_generation_entrypoint")
        self.assertFalse(report["research_materializer_ready"])
        self.assertEqual(report["selected_candidate_row_count"], 0)
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 0)
        first = report["daily_candidate_generation"][0]
        self.assertFalse(first["research_materializer_safe"])
        self.assertFalse(first["proof_safe"])
        self.assertIsNone(first["known_at"])
        self.assertIsNone(first["tradable_after"])
        self.assertIsNone(first["decision_timestamp_utc"])
        self.assertIn("source_daily_report_identity_untrusted", first["blockers"])
        self.assertIn("source_daily_row_research_materializer_safe_not_explicit_true", first["blockers"])

    def test_broad_or_missing_daily_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            broad_source = _trusted_source(rows=[])
            broad_source["allowed_universe"] = list(entrypoint.ALLOWED_UNIVERSE) + ["NFLX"]
            broad_source["frozen_universe"] = list(entrypoint.ALLOWED_UNIVERSE) + ["NFLX"]
            _write_json(source, broad_source)
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_13_symbol_candidate_generation_entrypoint")
        self.assertIn("source_artifact_universe_not_13_symbol", report["blockers"])
        self.assertIn("missing_daily_candidate_generation_diagnostics", report["blockers"])
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 0)
        self.assertEqual(report["selected_candidate_row_count"], 0)

    def test_source_level_blockers_do_not_taint_accepted_daily_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            rows = _daily_rows()
            rows[0].update(
                {
                    "exact_priced": True,
                    "pnl_pct": 12.5,
                    "gross_pnl_pct": 12.5,
                    "net_pnl_pct": 11.9,
                    "net_pnl_pct_after_fees": 11.5,
                    "proof_grade": "trusted_intraday_opra_nbbo",
                    "fill_basis": "imported_spread_mark",
                    "known_at": "2026-02-01T21:00:00Z",
                    "tradable_after": "2026-02-02T15:12:00Z",
                    "decision_timestamp_utc": "2026-02-02T15:12:00Z",
                    "entry_quote_timestamp_utc": "2026-02-02T15:12:00Z",
                    "exit_quote_timestamp_utc": "2026-02-18T20:56:00Z",
                }
            )
            _write_json(source, _trusted_source(rows=rows, blockers=["missing_point_in_time_earnings_calendar_source"]))
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_frozen_13_symbol_candidate_generation_entrypoint")
        self.assertIn("missing_point_in_time_earnings_calendar_source", report["blockers"])
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 1)
        self.assertEqual(report["selected_candidate_row_count"], 1)
        selected = report["selected_trades"][0]
        self.assertEqual(selected["status"], "selected_candidate")
        self.assertEqual(selected["blockers"], [])
        self.assertTrue(selected["exact_priced"])
        self.assertEqual(selected["pnl_pct"], 12.5)
        self.assertEqual(selected["gross_pnl_pct"], 12.5)
        self.assertEqual(selected["net_pnl_pct"], 11.5)
        self.assertEqual(selected["legacy_net_pnl_pct"], 11.9)
        self.assertEqual(selected["proof_grade"], "trusted_intraday_opra_nbbo")
        self.assertEqual(selected["known_at"], "2026-02-01T21:00:00Z")
        self.assertEqual(selected["tradable_after"], "2026-02-02T15:12:00Z")
        self.assertEqual(selected["decision_timestamp_utc"], "2026-02-02T15:12:00Z")
        self.assertEqual(selected["entry_quote_timestamp_utc"], "2026-02-02T15:12:00Z")
        self.assertEqual(selected["exit_quote_timestamp_utc"], "2026-02-18T20:56:00Z")

    def test_write_outputs_creates_jsonl_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, _trusted_source())
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())
            report = entrypoint.build_report(
                source_candidate_generation_path=source,
                feature_store_path=feature,
                forward_cohort_path=cohort,
                window_start="2026-02-01",
                window_end="2026-02-28",
                generated_at_utc="2026-06-24T00:00:00Z",
            )
            artifacts = entrypoint.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertFalse(report["no_write"])
            self.assertTrue(report["report_artifact_write_performed"])
            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "daily_candidate_generation.jsonl").exists())
            self.assertTrue((root / "out" / "selected_candidates.jsonl").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["daily_candidate_generation_jsonl"].replace("\\", "/").endswith("/out/daily_candidate_generation.jsonl"))


if __name__ == "__main__":
    unittest.main()
