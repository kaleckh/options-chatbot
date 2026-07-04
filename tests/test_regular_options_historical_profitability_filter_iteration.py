from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_historical_profitability_filter_iteration as iteration


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


def _row(
    month: str,
    ticker: str,
    pnl: float,
    *,
    prior: float = 5.0,
    lane: str = "bullish_pullback_observation",
    day: int = 3,
    direction: str = "call",
) -> dict:
    return {
        "entry_date": f"{month}-{day:02d}",
        "candidate_generation_date": f"{month}-{day:02d}",
        "month": month,
        "ticker": ticker,
        "symbol": ticker,
        "lane_id": lane,
        "lane": lane,
        "direction": direction,
        "long_contract_symbol": f"{ticker}-{month}-{day:02d}-{direction}-L",
        "dte": 32,
        "debit_pct_of_width": 40.0,
        "spread_width": 5.0,
        "exact_priced": True,
        "proof_grade": "trusted_intraday_opra_nbbo",
        "fill_basis": "imported_spread_mark",
        "pnl_pct": pnl,
        "net_pnl_pct": pnl,
        "net_pnl_usd": pnl * 10.0,
        "signal_evidence": {
            "prior_20_trading_day_return_pct": prior,
            "above_prior_50_sma": True,
        },
    }


class RegularOptionsHistoricalProfitabilityFilterIterationTests(unittest.TestCase):
    def _profitable_cluster_rows(self, month: str, *, cluster_count: int, prefix: str) -> list[dict]:
        rows = []
        for i in range(cluster_count):
            ticker = f"{prefix}{i:03d}"
            day = (i % 20) + 1
            rows.append(_row(month, ticker, 10.0, prior=8.0, day=day, direction="call"))
            rows.append(_row(month, ticker, -1.0, prior=-1.0, day=day, direction="put"))
        return rows

    def test_blocks_when_no_train_selected_filter_passes_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            rows = []
            for month in ("2026-01", "2026-02"):
                rows.extend([_row(month, "AAPL", -20.0, prior=1.0), _row(month, "MSFT", 10.0, prior=2.0)])
            _write_jsonl(selected, rows)
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": ["audit_bootstrap_pf_lb_not_above_1"]})

            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=root / "registry.json",
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_historical_profitability_filter_iteration")
        self.assertIn("no_preregistered_train_selected_filter_passes_train_and_audit", report["blockers"])
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["scanner_policy_changed"])

    def test_accepts_train_selected_filter_only_when_train_and_audit_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            rows = []
            rows.extend(self._profitable_cluster_rows("2026-01", cluster_count=60, prefix="TRN"))
            rows.extend(self._profitable_cluster_rows("2026-02", cluster_count=20, prefix="AUD"))
            _write_jsonl(selected, rows)
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": ["audit_bootstrap_pf_lb_not_above_1"]})

            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=root / "registry.json",
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "historical_profitability_filter_iteration_candidate_found")
        self.assertTrue(report["selection_permitted"])
        self.assertGreaterEqual(report["accepted_filter_count"], 1)
        self.assertTrue(any(row["accepted_by_historical_iteration_gate"] for row in report["accepted_filters"]))
        self.assertEqual(report["source_summary"]["duplicate_rows_removed"], 0)
        self.assertIn("bootstrap_iid", report["baseline"]["train"])
        self.assertIn("bootstrap_cluster", report["baseline"]["train"])
        self.assertGreater(report["baseline"]["train"]["bootstrap_cluster"]["pf_lb_5pct"], 1.0)
        self.assertFalse(report["accepted_profitability"])
        self.assertIn("do_not_change_scanner_policy_from_historical_filter_iteration", report["prohibited_actions"])

    def test_consumed_audit_window_blocks_selection_but_keeps_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            registry = root / "registry.json"
            rows = []
            rows.extend(self._profitable_cluster_rows("2026-01", cluster_count=60, prefix="TRN"))
            rows.extend(self._profitable_cluster_rows("2026-02", cluster_count=20, prefix="AUD"))
            _write_jsonl(selected, rows)
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": []})
            _write_json(
                registry,
                {
                    "report_id": "regular_options_audit_window_consumption_registry",
                    "schema_version": 1,
                    "entries": [
                        {
                            "window_months": ["2026-02"],
                            "consumed_by": "regular_options_historical_profitability_filter_iteration",
                            "candidate_filter_count": 162,
                            "accepted_filter_id": "old_filter",
                        }
                    ],
                },
            )

            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=registry,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["status"], "blocked_audit_window_already_consumed_for_selection")
        self.assertFalse(report["selection_permitted"])
        self.assertEqual(report["accepted_filter_count"], 0)
        self.assertIn("audit_window_already_consumed_for_selection", report["blockers"])
        self.assertGreaterEqual(report["selection_permitted_accepted_filter_count"], 1)

    def test_record_consumption_appends_only_when_selection_permitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            registry = root / "registry.json"
            rows = []
            rows.extend(self._profitable_cluster_rows("2026-01", cluster_count=60, prefix="TRN"))
            rows.extend(self._profitable_cluster_rows("2026-02", cluster_count=20, prefix="AUD"))
            _write_jsonl(selected, rows)
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": []})
            _write_json(registry, {"report_id": "regular_options_audit_window_consumption_registry", "schema_version": 1, "entries": []})
            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=registry,
                train_months=1,
                audit_months=1,
                bootstrap_draws=100,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

            recorded = iteration.record_consumption_if_needed(report, registry)
            updated = json.loads(registry.read_text(encoding="utf8"))

        self.assertTrue(recorded)
        self.assertEqual(len(updated["entries"]), 1)
        self.assertEqual(updated["entries"][0]["window_months"], ["2026-02"])

    def test_dedupes_same_date_ticker_direction_before_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            duplicate = _row("2026-01", "AAPL", 5.0, prior=5.0, day=3, direction="call")
            rows = [
                duplicate,
                {**duplicate, "lane_id": "zzz_duplicate_lane", "long_contract_symbol": "ZZZ"},
                _row("2026-02", "MSFT", 6.0, prior=5.0, day=4, direction="call"),
            ]
            _write_jsonl(selected, rows)
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": []})

            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=root / "registry.json",
                train_months=1,
                audit_months=1,
                bootstrap_draws=20,
                generated_at_utc="2026-06-30T00:00:00Z",
            )

        self.assertEqual(report["source_summary"]["accepted_exact_candidate_rows_before_dedupe"], 3)
        self.assertEqual(report["source_summary"]["deduped_row_count"], 2)
        self.assertEqual(report["source_summary"]["duplicate_rows_removed"], 1)

    def test_write_outputs_creates_latest_and_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / "selected.jsonl"
            audit = root / "audit.json"
            _write_jsonl(selected, [_row("2026-01", "AAPL", 5.0), _row("2026-02", "AAPL", 6.0)])
            _write_json(audit, {"status": "blocked_historical_simulated_forward_audit", "blockers": []})
            report = iteration.build_report(
                selected_candidates_path=selected,
                audit_report_path=audit,
                consumption_registry_path=root / "registry.json",
                train_months=1,
                audit_months=1,
                bootstrap_draws=20,
                generated_at_utc="2026-06-30T00:00:00Z",
            )
            artifacts = iteration.write_outputs(report, output_dir=root / "out", docs_report=root / "doc.md")

            self.assertTrue((root / "out" / "latest.json").exists())
            self.assertTrue((root / "out" / "latest.md").exists())
            self.assertTrue((root / "doc.md").exists())
            self.assertTrue(artifacts["latest_json"].replace("\\", "/").endswith("/out/latest.json"))


if __name__ == "__main__":
    unittest.main()
