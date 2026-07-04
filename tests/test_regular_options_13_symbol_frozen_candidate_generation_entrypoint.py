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
                rows.append({"date": day, "lane": lane["lane_id"], "underlying": symbol, "status": status})
    rows[0]["status"] = "selected_candidate"
    return rows


class RegularOptions13SymbolFrozenCandidateGenerationEntrypointTests(unittest.TestCase):
    def test_requires_no_write_and_exact_requested_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, {"allowed_universe": list(entrypoint.ALLOWED_UNIVERSE), "daily_candidate_generation": []})
            _write_json(feature, _feature())
            _write_json(cohort, _cohort())

            with self.assertRaises(ValueError):
                entrypoint.build_report(source_candidate_generation_path=source, feature_store_path=feature, forward_cohort_path=cohort, universe=["SPY"], no_write=True)
            with self.assertRaises(ValueError):
                entrypoint.build_report(source_candidate_generation_path=source, feature_store_path=feature, forward_cohort_path=cohort, no_write=False)

    def test_exact_daily_source_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, {"allowed_universe": list(entrypoint.ALLOWED_UNIVERSE), "daily_candidate_generation": _daily_rows()})
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

        self.assertEqual(report["status"], "frozen_13_symbol_candidate_generation_entrypoint_ready")
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

    def test_broad_or_missing_daily_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, {"allowed_universe": list(entrypoint.ALLOWED_UNIVERSE) + ["NFLX"], "daily_candidate_generation": []})
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
                    "net_pnl_pct": 11.9,
                    "proof_grade": "trusted_intraday_opra_nbbo",
                    "fill_basis": "imported_spread_mark",
                }
            )
            _write_json(
                source,
                {
                    "allowed_universe": list(entrypoint.ALLOWED_UNIVERSE),
                    "daily_candidate_generation": rows,
                    "blockers": ["missing_point_in_time_earnings_calendar_source"],
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
        self.assertIn("missing_point_in_time_earnings_calendar_source", report["blockers"])
        self.assertEqual(report["coverage"]["candidate_generation_months_covered_count"], 1)
        self.assertEqual(report["selected_candidate_row_count"], 1)
        selected = report["selected_trades"][0]
        self.assertEqual(selected["status"], "selected_candidate")
        self.assertEqual(selected["blockers"], [])
        self.assertTrue(selected["exact_priced"])
        self.assertEqual(selected["pnl_pct"], 12.5)
        self.assertEqual(selected["proof_grade"], "trusted_intraday_opra_nbbo")

    def test_write_outputs_creates_jsonl_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            feature = root / "feature.json"
            cohort = root / "cohort.json"
            _write_json(source, {"allowed_universe": list(entrypoint.ALLOWED_UNIVERSE), "daily_candidate_generation": _daily_rows()})
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

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "daily_candidate_generation.jsonl").exists())
            self.assertTrue((root / "out" / "selected_candidates.jsonl").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["daily_candidate_generation_jsonl"].replace("\\", "/").endswith("/out/daily_candidate_generation.jsonl"))


if __name__ == "__main__":
    unittest.main()
