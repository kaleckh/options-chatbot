import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.audit_missed_guardrail_trades as audit_mod
from scripts.audit_missed_guardrail_trades import build_audit, render_markdown


class MissedGuardrailTradeAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp.name) / "forward_tracking_authoritative.db"
        self._init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE forward_sessions (
                    id INTEGER PRIMARY KEY,
                    recorded_at_utc TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    playbook TEXT,
                    scan_picks_count INTEGER NOT NULL DEFAULT 0,
                    reviewed_positions_count INTEGER NOT NULL DEFAULT 0,
                    notes_json TEXT NOT NULL DEFAULT '{}',
                    run_id TEXT,
                    run_mode TEXT,
                    evidence_class TEXT,
                    eligibility_status TEXT
                );
                CREATE TABLE forward_events (
                    id INTEGER PRIMARY KEY,
                    session_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def _insert_session(self, session_id: int, *, raw: int, blocked: int, candidate_details: bool = False):
        scan_snapshot = {
            "picks": [],
            "policy_applied": True,
            "playbook": {
                "id": "short_term",
                "max_concurrent_positions": 3,
                "max_portfolio_cost_risk_pct": 25.0,
            },
            "scan_funnel": {
                "raw_candidates": raw,
                "returned_picks": 0,
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": blocked},
                "policy_counts": {"approved": 0, "watch": raw, "blocked": 0},
            },
            "exposure_snapshot": {
                "open_positions": 44,
                "open_cost_risk_usd": 29_000.0,
                "ticker_counts": {"SPY": 4},
            },
            "candidate_count": raw,
            "returned_count": 0,
            "guardrail_decision_counts": {"clear": 0, "caution": 0, "blocked": blocked},
        }
        if candidate_details:
            scan_snapshot["candidate_audit_picks"] = [
                {
                    "ticker": "SPY",
                    "contract_symbol": "SPY260515C00560000",
                    "guardrail_decision": "blocked",
                }
            ]
        tracked_snapshot = [
            {
                "id": 1,
                "status": "open",
                "ticker": "SPY",
                "direction": "call",
                "last_recommendation": "SELL",
            },
            {
                "id": 2,
                "status": "open",
                "ticker": "QQQ",
                "direction": "call",
                "last_recommendation": "HOLD",
            },
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO forward_sessions (
                    id,
                    recorded_at_utc,
                    source_label,
                    playbook,
                    scan_picks_count,
                    notes_json,
                    run_id,
                    run_mode,
                    evidence_class,
                    eligibility_status
                ) VALUES (?, ?, 'scheduled_scan', 'short_term', 0, '{}', ?, 'scheduled_scan', 'live_production', 'ineligible')
                """,
                (
                    session_id,
                    f"2026-04-{23 + session_id:02d}T17:00:00Z",
                    f"scheduled_scan:2026-04-{23 + session_id:02d}:test",
                ),
            )
            conn.execute(
                "INSERT INTO forward_events (session_id, event_type, payload_json) VALUES (?, 'scan_snapshot', ?)",
                (session_id, json.dumps(scan_snapshot)),
            )
            conn.execute(
                "INSERT INTO forward_events (session_id, event_type, payload_json) VALUES (?, 'tracked_positions_snapshot', ?)",
                (session_id, json.dumps(tracked_snapshot)),
            )

    def test_build_audit_counts_missed_guardrail_candidates_only_when_candidates_exist(self):
        self._insert_session(1, raw=3, blocked=3)
        self._insert_session(2, raw=0, blocked=0)

        with patch(
            "scripts.audit_missed_guardrail_trades._historical_options_coverage",
            return_value={
                "available": True,
                "covers_requested_window": False,
                "underlyings_cover_live_universe": False,
            },
        ):
            audit = build_audit(
                db_path=self.db_path,
                date_from=date(2026, 4, 24),
                date_to=date(2026, 4, 25),
            )

        self.assertEqual(audit["summary"]["sessions"], 2)
        self.assertEqual(audit["summary"]["raw_candidates"], 3)
        self.assertEqual(audit["summary"]["missed_candidate_appearances"], 3)
        self.assertEqual(audit["summary"]["sessions_with_missed_candidates"], 1)
        self.assertEqual(audit["summary"]["sessions_global_cap_sufficient_to_block"], 1)
        self.assertEqual(
            audit["summary"]["candidate_identity_recovery"],
            "not_available_counts_only",
        )
        self.assertEqual(
            audit["summary"]["likely_guardrail_cause_counts"]["max_concurrent_positions"],
            1,
        )
        markdown = render_markdown(audit)
        self.assertIn("Missed candidate appearances", markdown)
        self.assertIn("not_available_counts_only", markdown)

    def test_build_audit_marks_candidate_audit_picks_recoverable(self):
        self._insert_session(1, raw=1, blocked=1, candidate_details=True)

        with patch(
            "scripts.audit_missed_guardrail_trades._historical_options_coverage",
            return_value={
                "available": True,
                "covers_requested_window": False,
                "underlyings_cover_live_universe": False,
            },
        ):
            audit = build_audit(
                db_path=self.db_path,
                date_from=date(2026, 4, 24),
                date_to=date(2026, 4, 24),
            )

        self.assertEqual(audit["summary"]["sessions_with_candidate_details"], 1)
        self.assertEqual(audit["summary"]["candidate_identity_recovery"], "available")
        self.assertEqual(audit["sessions"][0]["recoverability"], "candidate_details_persisted")

    def test_historical_coverage_uses_trusted_data_and_requested_window(self):
        root = Path(self.tmp.name) / "repo"
        options_dir = root / "data" / "options-validation"
        options_dir.mkdir(parents=True)
        options_db = options_dir / "options_history.db"
        with sqlite3.connect(options_db) as conn:
            conn.executescript(
                """
                CREATE TABLE import_batches (
                    id INTEGER PRIMARY KEY,
                    source_label TEXT,
                    data_trust TEXT
                );
                CREATE TABLE option_quote_snapshots (
                    id INTEGER PRIMARY KEY,
                    source_batch_id INTEGER,
                    snapshot_kind TEXT,
                    underlying TEXT,
                    quote_date_et TEXT
                );
                INSERT INTO import_batches (id, source_label, data_trust) VALUES
                    (1, 'untrusted_old', 'research'),
                    (2, 'trusted_recent', 'trusted');
                """
            )
            live_needed = ["SPY", "QQQ", "IWM", "DIA", "XLK", "GOOGL", "NVDA", "AMZN", "JPM"]
            for idx, symbol in enumerate(live_needed, start=1):
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots
                        (source_batch_id, snapshot_kind, underlying, quote_date_et)
                    VALUES (2, 'daily_eod', ?, '2026-05-10')
                    """,
                    (symbol,),
                )
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots
                        (source_batch_id, snapshot_kind, underlying, quote_date_et)
                    VALUES (2, 'daily_eod', ?, '2026-05-11')
                    """,
                    (symbol,),
                )
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots
                        (source_batch_id, snapshot_kind, underlying, quote_date_et)
                    VALUES (1, 'daily_eod', ?, '2026-04-01')
                    """,
                    (f"OLD{idx}",),
                )

        with patch.object(audit_mod, "ROOT", root):
            coverage = audit_mod._historical_options_coverage(
                date_from=date(2026, 5, 10),
                date_to=date(2026, 5, 11),
            )
            stale_window = audit_mod._historical_options_coverage(
                date_from=date(2026, 5, 10),
                date_to=date(2026, 5, 12),
            )

        self.assertTrue(coverage["covers_requested_window"])
        self.assertTrue(coverage["underlyings_cover_live_universe"])
        self.assertEqual(coverage["first_quote_date"], "2026-05-10")
        self.assertEqual(coverage["latest_quote_date"], "2026-05-11")
        self.assertNotIn("OLD1", coverage["available_underlyings"])
        self.assertFalse(stale_window["covers_requested_window"])

    def test_historical_coverage_requires_each_live_underlying_to_cover_window(self):
        root = Path(self.tmp.name) / "repo_split_coverage"
        options_dir = root / "data" / "options-validation"
        options_dir.mkdir(parents=True)
        options_db = options_dir / "options_history.db"
        live_needed = ["SPY", "QQQ", "IWM", "DIA", "XLK", "GOOGL", "NVDA", "AMZN", "JPM"]
        with sqlite3.connect(options_db) as conn:
            conn.executescript(
                """
                CREATE TABLE import_batches (
                    id INTEGER PRIMARY KEY,
                    source_label TEXT,
                    data_trust TEXT
                );
                CREATE TABLE option_quote_snapshots (
                    id INTEGER PRIMARY KEY,
                    source_batch_id INTEGER,
                    snapshot_kind TEXT,
                    underlying TEXT,
                    quote_date_et TEXT
                );
                INSERT INTO import_batches (id, source_label, data_trust)
                VALUES (1, 'trusted_split', 'trusted');
                """
            )
            for index, symbol in enumerate(live_needed):
                quote_date = "2026-01-01" if index % 2 == 0 else "2026-01-31"
                conn.execute(
                    """
                    INSERT INTO option_quote_snapshots
                        (source_batch_id, snapshot_kind, underlying, quote_date_et)
                    VALUES (1, 'daily_eod', ?, ?)
                    """,
                    (symbol, quote_date),
                )

        with patch.object(audit_mod, "ROOT", root):
            coverage = audit_mod._historical_options_coverage(
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
            )

        self.assertTrue(coverage["underlyings_cover_live_universe"])
        self.assertFalse(coverage["covers_requested_window"])
        self.assertFalse(coverage["live_universe_coverage_by_underlying"]["QQQ"]["covers_requested_window"])


if __name__ == "__main__":
    unittest.main()
