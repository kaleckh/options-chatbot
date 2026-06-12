from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import build_monthly_all_lanes_profitability_audit as monthly_audit
from scripts import build_regime_stratified_replay_report as regime


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _write_market_db(path: Path, *, include_vix: bool = True, flat_spy: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE daily_history (
                symbol TEXT,
                bar_date TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL,
                fetched_at TEXT,
                source TEXT,
                adjustment_mode TEXT
            );
            """
        )
        rows = []
        for index, day in enumerate(_business_days(date(2025, 1, 1), 150)):
            spy_close = 100.0 if flat_spy else 100.0 + index
            rows.append(("SPY", day.isoformat(), spy_close, "fixture"))
            if include_vix:
                vix_close = 10.0 + (index * 0.25)
                rows.append(("^VIX", day.isoformat(), vix_close, "fixture"))
        conn.executemany(
            """
            INSERT INTO daily_history(
                symbol, bar_date, open, high, low, close, adj_close, volume, fetched_at, source, adjustment_mode
            )
            VALUES (?, ?, NULL, NULL, NULL, ?, NULL, NULL, '2026-06-12T00:00:00Z', ?, 'raw')
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _source_rows(*, all_winners: bool = False) -> dict:
    rows = []
    for index, day in enumerate(_business_days(date(2025, 3, 17), 60)):
        if all_winners:
            pnl = 10.0
        elif index >= 40:
            pnl = -8.0 if index % 5 else 2.0
        else:
            pnl = 6.0 if index % 3 else -2.0
        rows.append(
            {
                "scan_date": day.isoformat(),
                "playbook": "fixture_lane",
                "ticker": "SPY",
                "mark": {
                    "priced": True,
                    "quote_evidence_class": "trusted_intraday_opra_nbbo",
                    "net_pnl_pct": pnl,
                    "net_pnl_usd": pnl * 10.0,
                },
            }
        )
    return {"generated_at_utc": "2026-06-12T00:00:00Z", "rows": rows}


def _selected_trade_source_rows() -> dict:
    rows = []
    for lane_id, pnl in (("lane_a", 4.0), ("lane_b", -6.0)):
        for day in _business_days(date(2025, 4, 1), 20):
            rows.append(
                {
                    "entry_date": day.isoformat(),
                    "lane_family": "fixture_family",
                    "lane_id": lane_id,
                    "ticker": "SPY",
                    "priced": True,
                    "exact_priced": True,
                    "proof_grade": "trusted_intraday_opra_nbbo",
                    "pnl_pct": pnl,
                }
            )
    return {"generated_at_utc": "2026-06-12T00:00:00Z", "selected_trades": rows}


class RegimeStratifiedReplayReportTests(unittest.TestCase):
    def test_build_report_fails_regime_robustness_for_negative_sized_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            market = root / "market_data.db"
            _write_json(source, _source_rows())
            _write_market_db(market)

            report = regime.build_report(
                source_path=source,
                market_data_db_path=market,
                generated_at_utc="2026-06-12T12:00:00Z",
            )

        self.assertEqual(report["status"], "regime_stratified_replay_readback")
        self.assertEqual(report["summary"]["eligible_replay_row_count"], 60)
        self.assertEqual(report["summary"]["market_context_status"], "complete")
        self.assertFalse(report["summary"]["regime_robust"])
        failing = report["robustness"]["failing_buckets"]
        self.assertTrue(
            any(
                bucket["dimension"] == "vix_tercile"
                and bucket["bucket"] == "high"
                and bucket["robustness_reason"] == "profit_factor_below_1_0"
                for bucket in failing
            )
        )

    def test_missing_vix_context_blocks_robustness_without_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            market = root / "market_data.db"
            _write_json(source, _source_rows())
            _write_market_db(market, include_vix=False)

            report = regime.build_report(source_path=source, market_data_db_path=market)

        self.assertEqual(report["summary"]["overall_status"], "blocked_missing_market_context")
        self.assertEqual(report["summary"]["vix_context_available_count"], 0)
        self.assertEqual(report["summary"]["vix_missing_count"], 60)
        self.assertFalse(report["summary"]["regime_robust"])
        actions = {item["action"] for item in report["next_evidence_queue"]}
        self.assertIn("refresh_vix_daily_history_for_regime_report", actions)

    def test_no_loss_sample_keeps_profit_factor_null_and_does_not_pass_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            market = root / "market_data.db"
            _write_json(source, _source_rows(all_winners=True))
            _write_market_db(market)

            report = regime.build_report(source_path=source, market_data_db_path=market)

        self.assertFalse(report["summary"]["regime_robust"])
        failing = report["robustness"]["failing_buckets"]
        self.assertTrue(any(bucket["profit_factor"] is None for bucket in failing))
        self.assertTrue(
            any(bucket["robustness_reason"] == "profit_factor_unavailable_no_loss_sample" for bucket in failing)
        )

    def test_selected_trades_are_stratified_by_lane_id_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            market = root / "market_data.db"
            _write_json(source, _selected_trade_source_rows())
            _write_market_db(market)

            report = regime.build_report(source_path=source, market_data_db_path=market)

        self.assertEqual(report["summary"]["eligible_replay_row_count"], 40)
        self.assertEqual(report["summary"]["branch_count"], 2)
        self.assertEqual(set(report["branch_bucket_tables"]), {"lane_a", "lane_b"})
        self.assertTrue(all(row["lane"] in {"lane_a", "lane_b"} for row in report["annotated_rows"]))
        lane_b_month = [
            bucket
            for bucket in report["branch_bucket_tables"]["lane_b"]["entry_month"]
            if bucket["bucket"] == "2025-04"
        ]
        self.assertEqual(lane_b_month[0]["n_trades"], 20)
        self.assertEqual(lane_b_month[0]["robustness_reason"], "profit_factor_below_1_0")
        self.assertTrue(any(bucket.get("branch") == "lane_b" for bucket in report["robustness"]["failing_buckets"]))

    def test_write_outputs_creates_latest_and_docs_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            market = root / "market_data.db"
            _write_json(source, _source_rows())
            _write_market_db(market)
            report = regime.build_report(source_path=source, market_data_db_path=market)

            artifacts = regime.write_outputs(
                report,
                output_dir=root / "out",
                docs_report=root / "docs" / "regime-stratified-replay-report.md",
            )

            for artifact_path in artifacts.values():
                self.assertTrue(Path(artifact_path).exists(), artifact_path)
            latest = json.loads(Path(artifacts["latest_json"]).read_text(encoding="utf8"))
            self.assertEqual(latest["report_id"], regime.REPORT_ID)
            self.assertIn("Regime-Stratified Replay Report", Path(artifacts["docs_report"]).read_text(encoding="utf8"))

    def test_monthly_audit_regime_helper_surfaces_advisory_readback(self) -> None:
        readback = monthly_audit._regime_stratified_replay_report(
            {
                "status": "regime_stratified_replay_readback",
                "summary": {
                    "overall_status": "blocked_missing_market_context",
                    "regime_robust": False,
                    "eligible_replay_row_count": 60,
                    "vix_missing_count": 60,
                    "spy50_missing_count": 0,
                    "market_context_status": "missing_or_incomplete",
                    "evaluable_bucket_count": 3,
                    "failing_bucket_count": 0,
                    "branch_count": 2,
                    "branch_bucket_count": 12,
                    "minimum_bucket_n_for_robustness": 15,
                },
                "next_evidence_queue": [{"action": "refresh_vix_daily_history_for_regime_report"}],
            }
        )

        self.assertEqual(readback["implementation_status"], "built_context_blocked")
        self.assertFalse(readback["regime_robust"])
        self.assertEqual(readback["metrics"]["vix_missing_count"], 60)
        self.assertEqual(readback["metrics"]["branch_count"], 2)
        self.assertEqual(readback["metrics"]["branch_bucket_count"], 12)
        self.assertEqual(readback["next_evidence_queue"][0]["action"], "refresh_vix_daily_history_for_regime_report")


if __name__ == "__main__":
    unittest.main()
