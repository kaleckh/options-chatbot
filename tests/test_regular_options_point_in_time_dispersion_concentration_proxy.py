from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import build_regular_options_point_in_time_dispersion_concentration_proxy as proxy
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf8")


class RegularOptionsPointInTimeDispersionConcentrationProxyTests(unittest.TestCase):
    def _feature_store(self, tmp: Path, dates: list[str] | None = None, *, include_returns: bool = True) -> Path:
        dates = dates or ["2026-01-02", "2026-01-05", "2026-01-06"]
        symbols = ["SPY", "QQQ", "IWM", "AAPL", "GOOGL", "UNH", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM", "DIA"]
        path = tmp / "feature-store.json"
        _write_json(
            path,
            {
                "report_id": "regular_options_feature_store",
                "status": "feature_store_built",
                "summary": {
                    "overall_status": "feature_store_built",
                    "first_shared_quote_date_et": dates[0],
                    "latest_shared_quote_date_et": dates[-1],
                    "shared_quote_date_count": len(dates),
                },
                "shared_quote_dates": dates,
                "symbol_surface_rows": [
                    {
                        "symbol": symbol,
                        "quote_date_count": len(dates),
                        "underlying_price_row_count": len(dates) if include_returns else 0,
                    }
                    for symbol in symbols
                ],
            },
        )
        return path

    def _rows(self, dates: list[str] | None = None) -> list[dict]:
        dates = dates or ["2026-01-02", "2026-01-05", "2026-01-06"]
        returns = {
            "SPY": 0.3,
            "AAPL": 1.1,
            "GOOGL": 0.4,
            "UNH": -0.2,
            "LLY": 0.7,
            "JNJ": -0.1,
            "XOM": -0.5,
            "CVX": -0.4,
            "COP": -0.3,
            "NEM": 0.8,
        }
        rows: list[dict] = []
        for idx, day in enumerate(dates):
            prior_day = "2026-01-01" if idx == 0 else dates[idx - 1]
            for symbol, base_return in returns.items():
                rows.append(
                    {
                        "proxy_date_et": day,
                        "symbol": symbol,
                        "index_carrier": "SPY",
                        "return_pct": base_return + idx * 0.1,
                        "source_name": "fixture_underlying_returns",
                        "source_ref": f"fixture://returns/{symbol}/{prior_day}",
                        "source_timestamp_utc": f"{prior_day}T21:00:00Z",
                        "known_at_utc": f"{prior_day}T21:01:00Z",
                        "point_in_time_valid": True,
                        "source_provenance_status": "trusted_local_or_contract_declared",
                        "source_frequency": "daily_close",
                    }
                )
        return rows

    def test_clean_fixture_is_available(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = tmp / "source.jsonl"
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_jsonl(rows, self._rows(dates))
            report = proxy.build_report(
                source_rows_path=rows,
                feature_store_path=self._feature_store(tmp, dates),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "point_in_time_dispersion_concentration_proxy_available")
        self.assertEqual(report["coverage"]["covered_month_count"], 1)
        self.assertEqual(report["coverage"]["date_coverage_pct"], 100.0)
        self.assertEqual(len(report["proxy_rows"]), 3)
        self.assertFalse(report["proxy_rows"][0]["proof_eligible"])
        self.assertEqual(report["blockers"], [])

    def test_source_rows_can_provide_return_fields_without_feature_store_return_counts(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy-source-fields") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = tmp / "source.jsonl"
            dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
            _write_jsonl(rows, self._rows(dates))
            report = proxy.build_report(
                source_rows_path=rows,
                feature_store_path=self._feature_store(tmp, dates, include_returns=False),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "point_in_time_dispersion_concentration_proxy_available")
        inventory = report["source_inventory"]["feature_store"]
        self.assertTrue(inventory["proxy_source_rows_provide_return_fields"])
        self.assertTrue(inventory["return_fields_available"])
        self.assertNotIn("missing_required_return_fields", report["blockers"])

    def test_missing_source_fails_closed_without_inventing_rows(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = proxy.build_report(
                source_rows_path=tmp / "missing.jsonl",
                feature_store_path=self._feature_store(tmp, include_returns=False),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_dispersion_concentration_proxy")
        self.assertIn("missing_point_in_time_dispersion_proxy_source", report["blockers"])
        self.assertIn("missing_required_return_fields", report["blockers"])
        self.assertEqual(report["proxy_rows"], [])

    def test_wrong_universe_and_outside_symbol_fail_closed(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["symbol"] = "NFLX"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = proxy.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                universe="SPY,QQQ,IWM,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM,DIA",
                no_write=True,
            )

        reasons = [reason for row in report["rejected_source_rows"] for reason in row["reasons"]]
        self.assertIn("symbol_outside_requested_universe", reasons)
        self.assertIn("point_in_time_dispersion_proxy_row_validation_failed", report["blockers"])

    def test_insufficient_coverage_blocks(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
            source = tmp / "source.jsonl"
            _write_jsonl(source, self._rows(dates[:2]))
            report = proxy.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp, dates),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        self.assertEqual(report["status"], "blocked_point_in_time_dispersion_concentration_proxy")
        self.assertIn("insufficient_date_coverage", report["blockers"])

    def test_daily_close_same_day_known_at_is_rejected(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["source_timestamp_utc"] = "2026-01-02T21:00:00Z"
            rows[0]["known_at_utc"] = "2026-01-02T21:01:00Z"
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = proxy.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        reasons = [reason for row in report["rejected_source_rows"] for reason in row["reasons"]]
        self.assertIn("known_at_after_candidate_join_cutoff", reasons)

    def test_leakage_fields_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            rows = self._rows()
            rows[0]["net_pnl_usd"] = 100
            rows[1]["future_return"] = 2.0
            source = tmp / "source.jsonl"
            _write_jsonl(source, rows)
            report = proxy.build_report(
                source_rows_path=source,
                feature_store_path=self._feature_store(tmp),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )

        leakage_keys = [key for row in report["rejected_source_rows"] for key in row["leakage_keys"]]
        self.assertIn("net_pnl_usd", leakage_keys)
        self.assertIn("future_return", leakage_keys)

    def test_requires_no_write_mode(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            with self.assertRaises(ValueError):
                proxy.build_report(feature_store_path=self._feature_store(tmp), no_write=False)

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="dispersion-proxy") as tmp_dir:
            tmp = Path(tmp_dir)
            report = proxy.build_report(
                source_rows_path=tmp / "missing.jsonl",
                feature_store_path=self._feature_store(tmp, include_returns=False),
                start_date="2026-01-01",
                end_date="2026-01-31",
                as_of_date="2026-01-31",
                no_write=True,
            )
            artifacts = proxy.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "proxy.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "proxy.md").exists())
            self.assertIn("docs_report", artifacts)
            self.assertIn("Dispersion/Concentration Proxy", (tmp / "docs" / "proxy.md").read_text(encoding="utf8"))


if __name__ == "__main__":
    unittest.main()
