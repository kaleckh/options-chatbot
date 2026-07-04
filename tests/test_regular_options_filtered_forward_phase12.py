from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_filtered_forward_evidence_bar_evaluation as evaluator
from scripts import build_regular_options_filtered_forward_paper_shadow_tracker as tracker
from scripts import capture_regular_options_filtered_forward_exit_evidence as capture


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + ("\n" if rows else ""), encoding="utf8")


def _conditions() -> list[dict]:
    return [
        {"field": "ticker", "op": "in", "value": ["AAPL"]},
        {"field": "signal_evidence.prior_20_trading_day_return_pct", "op": "gte", "value": 10.0},
    ]


def _policy_contract(path: Path) -> dict:
    conditions = _conditions()
    payload = {
        "report_id": "regular_options_frozen_filtered_policy",
        "schema_version": 1,
        "policy_id": "historical_filtered_candidate_policy_v1",
        "filter_id": "fixture_filter",
        "conditions": conditions,
        "conditions_sha256": tracker._conditions_sha256(conditions),
        "tracking_start_at_utc": "2026-06-01T00:00:00Z",
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }
    _write_json(path, payload)
    return payload


def _bar_contract(policy_path: Path, *, min_rows: int = 1, max_fixture_rows: int = 0) -> dict:
    return {
        "report_id": "regular_options_filtered_forward_evidence_bar",
        "schema_version": 1,
        "bar_id": "regular_options_filtered_forward_evidence_bar_v1",
        "policy_id": "historical_filtered_candidate_policy_v1",
        "source_policy_contract": {
            "path": str(policy_path),
            "sha256": evaluator._file_hash(policy_path),
            "conditions_sha256": tracker._conditions_sha256(_conditions()),
        },
        "requirements": {
            "min_completed_forward_paper_shadow_rows": min_rows,
            "min_ticker_week_clusters": 1,
            "min_calendar_months_with_rows": 1,
            "min_percent_cluster_pf_lb_5pct": 1.0,
            "min_usd_cluster_pf_lb_5pct": 1.0,
            "min_total_net_pnl_usd_exclusive": 0.0,
            "max_fixture_rows": max_fixture_rows,
            "bootstrap_draws": 25,
            "evaluation_may_not_occur_before_min_completed_rows": True,
        },
    }


def _audit() -> dict:
    return {
        "report_id": "regular_options_historical_filtered_simulated_forward_audit",
        "status": "blocked_historical_filtered_simulated_forward_audit",
        "filter_source": {"conditions": _conditions(), "filter_id": "fixture_filter"},
        "metrics": {"simulated_forward_audit": {"bootstrap_cluster": {"pf_lb_5pct": 1.1}}},
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
    }


def _scan_row() -> dict:
    return {
        "scan_run_id": "scan-aapl-1",
        "scan_date": "2026-06-01",
        "logged_at": "2026-06-01T15:00:00Z",
        "ticker": "AAPL",
        "playbook_id": "bullish_pullback_observation",
        "strategy_type": "vertical_spread",
        "direction": "call",
        "expiry": "2026-06-05",
        "dte": 4,
        "contract_symbol": "AAPL260605C00200000",
        "short_contract_symbol": "AAPL260605C00210000",
        "long_strike": 200,
        "short_strike": 210,
        "quote_source": "alpaca_opra",
        "quote_timestamp_utc": "2026-06-01T15:00:00Z",
        "spread_liquidity": {"long_bid": 4.0, "long_ask": 4.2, "short_bid": 1.0, "short_ask": 1.1},
        "net_debit": 3.2,
        "signal_evidence": {"prior_20_trading_day_return_pct": 12.5},
    }


def _options_db(path: Path, *, long_bid: float = 6.2, short_ask: float = 1.0) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE import_batches (id INTEGER PRIMARY KEY, source_label TEXT NOT NULL, data_trust TEXT NOT NULL)")
        conn.execute(
            """
            CREATE TABLE option_quote_snapshots (
                bid REAL,
                ask REAL,
                as_of_utc TEXT,
                quote_minute_et INTEGER,
                source_batch_id INTEGER,
                contract_symbol TEXT,
                quote_date_et TEXT,
                snapshot_kind TEXT
            )
            """
        )
        conn.execute("INSERT INTO import_batches (id, source_label, data_trust) VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')")
        rows = [
            ("AAPL260605C00200000", long_bid, long_bid + 0.1),
            ("AAPL260605C00210000", short_ask - 0.1, short_ask),
        ]
        for contract, bid, ask in rows:
            conn.execute(
                """
                INSERT INTO option_quote_snapshots
                    (bid, ask, as_of_utc, quote_minute_et, source_batch_id, contract_symbol, quote_date_et, snapshot_kind)
                VALUES (?, ?, '2026-06-04T19:55:00Z', ?, 1, ?, '2026-06-04', 'intraday')
                """,
                (bid, ask, 15 * 60 + 55, contract),
            )
        conn.commit()
    finally:
        conn.close()


class RegularOptionsFilteredForwardPhase12Tests(unittest.TestCase):
    def test_end_to_end_fixture_walk_entry_exit_completion_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            audit_path = root / "audit.json"
            bar_path = root / "bar.json"
            scan_path = root / "scan.jsonl"
            daily_path = root / "daily.jsonl"
            matched_log = root / "matched_rows.jsonl"
            db_path = root / "options_history.db"
            _policy_contract(policy_path)
            _write_json(audit_path, _audit())
            _write_json(bar_path, _bar_contract(policy_path, min_rows=1))
            _write_jsonl(scan_path, [_scan_row()])
            _write_jsonl(daily_path, [])
            _options_db(db_path)

            tracked = tracker.build_report(
                policy_contract_path=policy_path,
                filtered_audit_path=audit_path,
                forward_evidence_bar_contract_path=bar_path,
                source_scan_picks_path=scan_path,
                underlying_daily_source_rows_path=daily_path,
                matched_rows_log_path=matched_log,
                append_matched_rows=True,
                generated_at_utc="2026-06-01T15:05:00Z",
            )
            captured = capture.build_report(
                matched_rows_log_path=matched_log,
                exit_evidence_path=root / "missing-live-evidence.jsonl",
                options_history_db_path=db_path,
                no_write=False,
                generated_at_utc="2026-06-05T22:00:00Z",
            )
            evaluated = evaluator.build_report(
                matched_rows_log_path=matched_log,
                policy_contract_path=policy_path,
                forward_evidence_bar_contract_path=bar_path,
                generated_at_utc="2026-06-05T22:05:00Z",
            )

        self.assertEqual(tracked["forward_tracking"]["entry_rows_appended_count"], 1)
        self.assertEqual(captured["status"], "exit_completion_appended")
        self.assertEqual(captured["completion_rows_appended"], 1)
        self.assertEqual(evaluated["forward_evidence_bar"]["completed_forward_rows"], 1)
        self.assertTrue(evaluated["forward_evidence_bar"]["evaluation_permitted"])
        self.assertIn(evaluated["status"], {"bar_met_pending_operator_review", "bar_not_met"})
        self.assertFalse(evaluated["broker_order_allowed"])
        self.assertFalse(captured["options_history_db_mutated"])

    def test_exit_capture_rejects_untrusted_live_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matched_log = root / "matched_rows.jsonl"
            entry, reasons = tracker._matched_entry_log_row(
                _scan_row(),
                tracking_start_date="2026-06-01",
                tracking_start_at_utc="2026-06-01T00:00:00Z",
            )
            self.assertEqual(reasons, [])
            _write_jsonl(matched_log, [entry])
            evidence = root / "exit_evidence.jsonl"
            _write_jsonl(
                evidence,
                [
                    {
                        "candidate_id": entry["candidate_id"],
                        "exit_quote_source": "midpoint_model",
                        "exit_quote_timestamp_utc": "2026-06-04T19:55:00Z",
                        "long_exit_bid": 6.2,
                        "short_exit_ask": 1.0,
                    }
                ],
            )

            report = capture.build_report(
                matched_rows_log_path=matched_log,
                exit_evidence_path=evidence,
                options_history_db_path=root / "missing.db",
                no_write=True,
                generated_at_utc="2026-06-05T22:00:00Z",
            )

        self.assertEqual(report["status"], "exit_completion_rows_rejected")
        self.assertEqual(report["reject_counts"]["untrusted_exit_quote_source"], 1)
        self.assertEqual(report["completion_rows_appended"], 0)

    def test_evaluator_refuses_before_minimum_and_flags_fixture_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            bar_path = root / "bar.json"
            matched_log = root / "matched_rows.jsonl"
            _policy_contract(policy_path)
            _write_json(bar_path, _bar_contract(policy_path, min_rows=30))
            rows = []
            for index in range(29):
                rows.append(
                    {
                        "candidate_id": f"c{index}",
                        "candidate_identity_schema": tracker.MATCHED_ROW_IDENTITY_SCHEMA,
                        "scan_date": "2026-06-01",
                        "ticker": "AAPL",
                        "tracking_state": "forward_paper_shadow_completed",
                        "realized_pnl_status": "completed_exact_exit",
                        "net_pnl_pct": 10.0,
                        "net_pnl_usd": 100.0,
                    }
                )
            _write_jsonl(matched_log, rows)

            before_min = evaluator.build_report(
                matched_rows_log_path=matched_log,
                policy_contract_path=policy_path,
                forward_evidence_bar_contract_path=bar_path,
            )
            rows.append({**rows[-1], "candidate_id": "c29", "is_fixture": True})
            _write_jsonl(matched_log, rows)
            fixture = evaluator.build_report(
                matched_rows_log_path=matched_log,
                policy_contract_path=policy_path,
                forward_evidence_bar_contract_path=bar_path,
            )

        self.assertEqual(before_min["status"], "evaluation_not_permitted_yet")
        self.assertFalse(before_min["forward_evidence_bar"]["evaluation_permitted"])
        self.assertTrue(fixture["forward_evidence_bar"]["evaluation_permitted"])
        self.assertEqual(fixture["forward_evidence_bar"]["fixture_row_count"], 1)
        self.assertFalse(fixture["forward_evidence_bar"]["checks"]["fixture_rows"])

    def test_evaluator_rejects_duplicate_daily_signal_matched_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy_path = root / "policy.json"
            bar_path = root / "bar.json"
            matched_log = root / "matched_rows.jsonl"
            _policy_contract(policy_path)
            _write_json(bar_path, _bar_contract(policy_path, min_rows=1))
            entry, reasons = tracker._matched_entry_log_row(
                _scan_row(),
                tracking_start_date="2026-06-01",
                tracking_start_at_utc="2026-06-01T00:00:00Z",
            )
            self.assertEqual(reasons, [])
            duplicate = {**entry, "candidate_id": "doctored-duplicate", "source_scan_run_id": "later-session"}
            _write_jsonl(matched_log, [entry, duplicate])

            report = evaluator.build_report(
                matched_rows_log_path=matched_log,
                policy_contract_path=policy_path,
                forward_evidence_bar_contract_path=bar_path,
            )

        self.assertEqual(report["status"], "blocked_forward_evidence_bar_evaluation")
        self.assertIn("duplicate_ticker_date_direction_matched_rows", report["blockers"])
        self.assertEqual(report["duplicate_daily_signal_identity_count"], 1)


if __name__ == "__main__":
    unittest.main()
