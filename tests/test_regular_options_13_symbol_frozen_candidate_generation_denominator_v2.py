from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_13_symbol_frozen_candidate_generation_denominator_v2 as denom


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _feature_store() -> dict:
    return {
        "report_id": "regular_options_feature_store",
        "status": "feature_store_built",
        "shared_quote_dates": ["2026-02-02", "2026-02-03", "2026-03-02"],
        "summary": {"shared_quote_date_count": 3},
    }


def _runner() -> dict:
    return {
        "report_id": "regular_options_13_symbol_candidate_generation_no_write",
        "status": "candidate_generation_no_write_runner_ready",
        "support_manifest": {
            "read_only_no_write_runner_available": True,
            "read_only": True,
            "research_only": True,
            "no_write": True,
            "as_of_gated": True,
            "pre_holdout_as_of": True,
            "universe_filter": True,
            "frozen_universe_exact_13_symbols": True,
            "candidate_commands": ["fixture --no-write --as-of-date 2026-06-04"],
            "mutating": False,
            "quotes_imported": False,
            "evidence_stores_mutated": False,
            "protected_holdout_consumed": False,
            "production_scanner_changed": False,
            "strategy_logic_changed": False,
            "stops_changed": False,
            "sizing_changed": False,
            "proof_bars_changed": False,
        },
    }


def _source_surface(*, ready: bool = False, selected_rows: list[dict] | None = None) -> dict:
    selected_rows = selected_rows or []
    month_diag = []
    for month in ["2026-02", "2026-03"]:
        if ready:
            month_diag.append(
                {
                    "month": month,
                    "candidate_generation_proven": True,
                    "explicit_no_pick_proof": not selected_rows,
                    "blockers": [],
                }
            )
        else:
            month_diag.append(
                {
                    "month": month,
                    "candidate_generation_proven": False,
                    "explicit_no_pick_proof": False,
                    "blockers": [
                        "missing_daily_candidate_generation_diagnostics",
                        "missing_frozen_13_symbol_candidate_generation_engine",
                    ],
                }
            )
    return {
        "report_id": "regular_options_13_symbol_frozen_candidate_generation_source_surface",
        "status": (
            "ready_13_symbol_frozen_candidate_generation_source_surface"
            if ready
            else "blocked_13_symbol_frozen_candidate_generation_source_surface"
        ),
        "calendar_coverage": {
            "calendar_months_covered": ["2026-02", "2026-03"] if ready else [],
            "calendar_months_covered_count": 2 if ready else 0,
        },
        "selected_trade_summary": {"selected_rows_in_window": len(selected_rows)},
        "selected_trades": selected_rows,
        "month_diagnostics": month_diag,
        "blockers": [] if ready else ["missing_frozen_13_symbol_candidate_generation_engine"],
    }


def _surface_audit() -> dict:
    return {
        "report_id": "regular_options_13_symbol_candidate_generation_surface_audit",
        "status": "blocked_13_symbol_candidate_generation_surface_audit",
        "quote_history_vs_candidate_generation": {"quote_surface_months_available_count": 24},
        "runner_support": {"status": "read_only_no_write_runner_available"},
    }


def _base_ledger() -> dict:
    return {
        "report_id": "regular_options_base_clean_stack_identity_ledger",
        "status": "base_clean_stack_identity_ledger_ready",
        "identity_hashes": ["SPY|old"],
        "ledger_entries": [],
    }


def _policy() -> dict:
    return {
        "status": "active",
        "rules": [
            {
                "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                "status": "active",
                "symbols": ["CVX"],
            }
        ],
    }


def _contract(report_id: str) -> dict:
    return {"report_id": report_id, "status": "active"}


class RegularOptions13SymbolFrozenCandidateGenerationDenominatorV2Tests(unittest.TestCase):
    def _write_inputs(self, root: Path, *, source_ready: bool = False, selected_rows: list[dict] | None = None) -> dict[str, Path]:
        paths = {
            "feature": root / "feature.json",
            "runner": root / "runner.json",
            "source": root / "source.json",
            "audit": root / "audit.json",
            "base": root / "base.json",
            "policy": root / "policy.json",
            "holdout": root / "holdout.json",
            "cohort": root / "cohort.json",
        }
        _write_json(paths["feature"], _feature_store())
        _write_json(paths["runner"], _runner())
        _write_json(paths["source"], _source_surface(ready=source_ready, selected_rows=selected_rows))
        _write_json(paths["audit"], _surface_audit())
        _write_json(paths["base"], _base_ledger())
        _write_json(paths["policy"], _policy())
        _write_json(paths["holdout"], _contract("forward-holdout-contract"))
        _write_json(paths["cohort"], _contract("forward-cohort-preregistration"))
        return paths

    def _build(self, paths: dict[str, Path], **kwargs: object) -> dict:
        return denom.build_report(
            feature_store_path=paths["feature"],
            no_write_runner_path=paths["runner"],
            source_surface_path=paths["source"],
            surface_audit_path=paths["audit"],
            base_ledger_path=paths["base"],
            source_quality_policy_path=paths["policy"],
            holdout_contract_path=paths["holdout"],
            cohort_preregistration_path=paths["cohort"],
            window_start="2026-02-01",
            window_end="2026-03-31",
            generated_at_utc="2026-06-23T00:00:00Z",
            **kwargs,
        )

    def test_requires_exact_frozen_universe_and_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_inputs(Path(tmp))
            with self.assertRaises(ValueError):
                self._build(paths, universe=["SPY", "QQQ"])
            with self.assertRaises(ValueError):
                self._build(paths, no_write=False)

    def test_current_blocked_surface_emits_daily_blockers_and_safety_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_inputs(Path(tmp), source_ready=False)
            report = self._build(paths)

        self.assertEqual(report["status"], "blocked_13_symbol_frozen_candidate_generation_denominator_v2")
        self.assertIn("missing_frozen_13_symbol_candidate_generation_engine", report["blockers"])
        self.assertIn("blocked_daily_candidate_generation_coverage", report["blockers"])
        self.assertEqual(report["candidate_generation_denominator"]["blocked_days"], 3)
        self.assertEqual(report["candidate_generation_denominator"]["latest_four_month_candidate_rows_after_dedupe"], 0)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])
        self.assertFalse(report["broker_order_allowed"])

    def test_ready_fixture_counts_strict_new_daily_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = [
                {"entry_date": "2026-02-02", "ticker": "SPY", "opportunity_identity_hash": "SPY|old"},
                {"entry_date": "2026-02-03", "ticker": "QQQ", "opportunity_identity_hash": "QQQ|new"},
            ]
            paths = self._write_inputs(Path(tmp), source_ready=True, selected_rows=rows)
            report = self._build(paths)

        self.assertIn("blocked_latest_four_month_rows_below_30", report["blockers"])
        self.assertEqual(report["candidate_generation_denominator"]["selected_candidate_rows"], 2)
        self.assertEqual(report["candidate_generation_denominator"]["overlap_rows_against_base_157"], 1)
        self.assertEqual(report["candidate_generation_denominator"]["strict_new_candidate_rows_after_opportunity_dedupe"], 1)

    def test_write_outputs_creates_latest_docs_and_daily_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._write_inputs(root, source_ready=False)
            report = self._build(paths)
            artifacts = denom.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "out" / "daily_status.jsonl").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["daily_status_jsonl"].replace("\\", "/").endswith("/out/daily_status.jsonl"))


if __name__ == "__main__":
    unittest.main()
