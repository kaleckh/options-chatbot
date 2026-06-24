from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_13_symbol_candidate_generation_surface_audit as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _months() -> list[str]:
    return audit._month_range(audit._parse_date("2024-06-01"), audit._parse_date("2026-05-31"))  # type: ignore[arg-type]


def _feature_store() -> dict:
    return {
        "status": "feature_store_built",
        "inputs": {
            "source_label": "thetadata_opra_nbbo_1m",
            "snapshot_kind": "intraday",
            "data_trust": "trusted",
            "symbols": list(audit.ALLOWED_UNIVERSE),
        },
        "summary": {
            "shared_quote_date_count": 505,
            "first_shared_quote_date_et": "2024-05-22",
            "latest_shared_quote_date_et": "2026-06-04",
        },
        "feature_contract": {
            "point_in_time_join_rule": "candidate joins must require feature.tradable_after_time <= candidate_entry_time",
            "trusted_source_filter": {
                "option_quote_snapshots.snapshot_kind": "intraday",
                "import_batches.source_label": "thetadata_opra_nbbo_1m",
                "import_batches.data_trust": "trusted",
            },
        },
        "shared_quote_dates": ["2024-06-03", "2026-05-29"],
        "symbol_surface_rows": [
            {
                "symbol": symbol,
                "source_label": "thetadata_opra_nbbo_1m",
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_date_count": 505,
                "read_only": True,
            }
            for symbol in audit.ALLOWED_UNIVERSE
        ],
    }


def _policy() -> dict:
    return {
        "policy_id": "regular_options_source_quality_scope_policy",
        "status": "active",
        "rules": [
            {
                "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                "status": "active",
                "action": "exclude_matching_trades_from_historical_candidate_scope",
                "symbols": ["CVX"],
                "minimum_executable_quote_pct": 90.0,
                "observed_executable_quote_pct": 88.66,
            }
        ],
    }


def _holdout(start: str = "2026-06-05") -> dict:
    return {
        "contract_id": "forward-holdout-contract",
        "status": "active",
        "protected_range": {"start_date": start, "date_basis": "candidate_entry_date"},
    }


def _selected_depth(months: list[str] | None = None) -> dict:
    months = months or []
    return {
        "status": "point_in_time_selected_trade_depth_ready_for_audit",
        "calendar_coverage": {
            "covered_months": months,
            "zero_selection_months": [],
            "zero_selection_months_explicit": False,
        },
        "blockers": [],
    }


def _candidate(
    *,
    covered_months: list[str] | None = None,
    zero_months: list[str] | None = None,
    selected_trades: list[dict] | None = None,
    universe: list[str] | None = None,
    runner_support: dict | None = None,
    commands: list[str] | None = None,
) -> dict:
    covered_months = covered_months or []
    zero_months = zero_months or []
    return {
        "status": "point_in_time_candidate_generation_ready_for_audit",
        "allowed_universe": universe if universe is not None else list(audit.ALLOWED_UNIVERSE),
        "calendar_coverage": {
            "covered_months": covered_months,
            "zero_selection_months": zero_months,
            "zero_selection_months_explicit": bool(zero_months),
        },
        "selected_trades": selected_trades or [],
        "source_quality_exclusions": [
            {
                "rule_id": "cvx_zero_bid_tradability_candidate_scope_v1",
                "ticker": "CVX",
                "entry_date": "2026-01-13",
                "reason": "zero_bid_tradability_floor_failure",
            }
        ],
        "source_artifact_inventory": [
            {
                "playbook": "bounded_13_symbol_test",
                "replay_calendar": {"underlyings": universe if universe is not None else list(audit.ALLOWED_UNIVERSE)},
                "runner_entrypoints": commands or [],
            }
        ],
        "runner_support": runner_support
        if runner_support is not None
        else {
            "read_only": True,
            "no_write": True,
            "as_of_date": True,
            "pre_holdout_as_of": True,
            "universe_filter": True,
            "candidate_commands": [
                "python scripts/run_13.py --no-write --as-of-date 2026-06-04 --symbols SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA"
            ],
        },
    }


def _no_write_report(*, valid: bool = True) -> dict:
    manifest = {
        "read_only_no_write_runner_available": True,
        "read_only": True,
        "research_only": True,
        "no_write": True,
        "mutating": False,
        "as_of_date": "2026-06-04",
        "as_of_gated": True,
        "pre_holdout_as_of": True,
        "universe_filter": True,
        "frozen_universe_exact_13_symbols": True,
        "candidate_commands": [
            "uv run --locked python scripts/run_regular_options_13_symbol_no_write_candidate_generation.py --start-date 2024-06-01 --end-date 2026-05-31 --as-of-date 2026-06-04 --universe SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA --no-write --json"
        ],
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "production_scanner_changed": False,
        "strategy_logic_changed": False,
        "stops_changed": False,
        "sizing_changed": False,
        "proof_bars_changed": False,
    }
    if not valid:
        manifest["no_write"] = False
    return {
        "report_id": "regular_options_13_symbol_candidate_generation_no_write",
        "status": "candidate_generation_no_write_runner_ready_with_blockers",
        "support_manifest": manifest,
    }


class RegularOptions13SymbolCandidateGenerationSurfaceAuditTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        candidate: dict,
        selected_depth: dict | None = None,
        holdout: dict | None = None,
        no_write: dict | None = None,
    ) -> dict[str, Path]:
        paths = {
            "feature": root / "feature.json",
            "candidate": root / "candidate.json",
            "no_write": root / "no_write.json",
            "selected": root / "selected.json",
            "policy": root / "policy.json",
            "holdout": root / "holdout.json",
        }
        _write_json(paths["feature"], _feature_store())
        _write_json(paths["candidate"], candidate)
        if no_write is not None:
            _write_json(paths["no_write"], no_write)
        _write_json(paths["selected"], selected_depth or _selected_depth())
        _write_json(paths["policy"], _policy())
        _write_json(paths["holdout"], holdout or _holdout())
        return paths

    def _build(
        self,
        paths: dict[str, Path],
        *,
        window_start: str = "2024-06-01",
        window_end: str = "2026-05-31",
        use_no_write: bool = False,
    ) -> dict:
        return audit.build_report(
            feature_store_report_path=paths["feature"],
            selected_trade_depth_path=paths["selected"],
            candidate_generation_path=paths["candidate"],
            no_write_candidate_generation_path=paths["no_write"] if use_no_write else None,
            source_quality_policy_path=paths["policy"],
            holdout_contract_path=paths["holdout"],
            window_start=window_start,
            window_end=window_end,
            as_of_date="2026-06-04",
            generated_at_utc="2026-06-23T00:00:00Z",
        )

    def test_quote_depth_alone_does_not_count_a_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(Path(tmp), candidate=_candidate(covered_months=[]))
            report = self._build(paths, window_start="2024-06-01", window_end="2024-06-30")

        self.assertEqual(report["status"], "blocked_13_symbol_candidate_generation_surface_audit")
        self.assertIn("quote_depth_only_months_cannot_count", report["blockers"])
        self.assertIn("cannot_count_zero_selection_month", report["month_diagnostics"][0]["statuses"])
        self.assertFalse(report["month_diagnostics"][0]["month_counted_for_bounded_13_symbol_replay"])

    def test_explicit_candidate_generation_diagnostics_can_count_zero_selection_month(self) -> None:
        months = _months()
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(covered_months=months, zero_months=months),
                selected_depth=_selected_depth(months),
            )
            report = self._build(paths)

        self.assertEqual(report["status"], "ready_for_bounded_13_symbol_no_write_replay")
        self.assertEqual(report["blockers"], [])
        self.assertTrue(all(row["explicit_zero_selection_month"] for row in report["month_diagnostics"]))
        self.assertTrue(all(row["month_counted_for_bounded_13_symbol_replay"] for row in report["month_diagnostics"]))

    def test_protected_holdout_overlap_blocks_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(covered_months=["2026-06"], zero_months=["2026-06"]),
                selected_depth=_selected_depth(["2026-06"]),
                holdout=_holdout("2026-06-05"),
            )
            report = self._build(paths, window_start="2026-06-01", window_end="2026-06-30")

        self.assertEqual(report["status"], "blocked_13_symbol_candidate_generation_surface_audit")
        self.assertIn("protected_holdout_overlap", report["blockers"])
        self.assertIn("protected_holdout_overlap", report["month_diagnostics"][0]["statuses"])

    def test_cvx_scope_remains_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(covered_months=["2026-01"], zero_months=["2026-01"]),
                selected_depth=_selected_depth(["2026-01"]),
            )
            report = self._build(paths, window_start="2026-01-01", window_end="2026-01-31")

        self.assertTrue(report["cvx_scope"]["cvx_scope_enforced"])
        self.assertEqual(report["cvx_scope"]["rule_id"], "cvx_zero_bid_tradability_candidate_scope_v1")
        self.assertIn("cvx_scope_blocked", report["month_diagnostics"][0]["statuses"])

    def test_non_13_symbol_rows_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(
                    covered_months=["2026-03"],
                    selected_trades=[{"entry_date": "2026-03-19", "ticker": "NFLX"}],
                    universe=list(audit.ALLOWED_UNIVERSE) + ["NFLX"],
                ),
                selected_depth=_selected_depth(["2026-03"]),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31")

        self.assertEqual(report["status"], "blocked_13_symbol_candidate_generation_surface_audit")
        self.assertIn("non_13_symbol_selected_rows_present", report["blockers"])
        self.assertIn("source_artifact_universe_not_13_symbol", report["blockers"])

    def test_mutating_runner_commands_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(
                    covered_months=["2026-03"],
                    zero_months=["2026-03"],
                    runner_support={
                        "read_only": True,
                        "no_write": False,
                        "as_of_date": True,
                        "pre_holdout_as_of": True,
                        "universe_filter": True,
                        "candidate_commands": ["python scripts/run_13.py --import-quotes --as-of-date 2026-06-04 --symbols SPY"],
                    },
                ),
                selected_depth=_selected_depth(["2026-03"]),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31")

        self.assertEqual(report["status"], "blocked_13_symbol_candidate_generation_surface_audit")
        self.assertIn("missing_no_write_runner_support", report["blockers"])
        self.assertIn("mutating_runner_command_rejected", report["blockers"])
        self.assertEqual(report["candidate_commands"], [])

    def test_valid_no_write_runner_artifact_clears_missing_runner_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(
                    covered_months=["2026-03"],
                    zero_months=["2026-03"],
                    runner_support={
                        "read_only": True,
                        "no_write": False,
                        "as_of_date": True,
                        "pre_holdout_as_of": True,
                        "universe_filter": True,
                        "candidate_commands": ["python scripts/run_13.py --import-quotes --as-of-date 2026-06-04 --symbols SPY"],
                    },
                ),
                selected_depth=_selected_depth(["2026-03"]),
                no_write=_no_write_report(),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31", use_no_write=True)

        self.assertNotIn("missing_no_write_runner_support", report["blockers"])
        self.assertNotIn("mutating_runner_command_rejected", report["blockers"])
        self.assertEqual(report["runner_support"]["status"], "read_only_no_write_runner_available")
        self.assertTrue(report["candidate_commands"])

    def test_invalid_no_write_runner_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(covered_months=["2026-03"], zero_months=["2026-03"]),
                selected_depth=_selected_depth(["2026-03"]),
                no_write=_no_write_report(valid=False),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31", use_no_write=True)

        self.assertEqual(report["status"], "blocked_13_symbol_candidate_generation_surface_audit")
        self.assertIn("invalid_no_write_runner_support", report["blockers"])
        self.assertIn("no_write_not_true", report["runner_support"]["validation_reason_codes"])

    def test_no_profitability_or_promotion_flags_become_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._write_fixture(
                Path(tmp),
                candidate=_candidate(covered_months=["2026-03"], zero_months=["2026-03"]),
                selected_depth=_selected_depth(["2026-03"]),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31")

        for key, expected in audit.READ_ONLY_FLAGS.items():
            self.assertEqual(report[key], expected)

    def test_write_outputs_creates_docs_and_latest_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._write_fixture(
                root,
                candidate=_candidate(covered_months=["2026-03"], zero_months=["2026-03"]),
                selected_depth=_selected_depth(["2026-03"]),
            )
            report = self._build(paths, window_start="2026-03-01", window_end="2026-03-31")
            artifacts = audit.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue(Path(artifacts["latest_json"]).exists())
            self.assertTrue(Path(artifacts["latest_markdown"]).exists())
            self.assertTrue(Path(artifacts["docs_report"]).exists())


if __name__ == "__main__":
    unittest.main()
