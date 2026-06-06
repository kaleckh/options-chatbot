from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import audit_missed_regular_picks_outcomes as audit


def _init_options_db(path: Path, rows: list[tuple[str, str, str, float, float]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE import_batches (
                id INTEGER PRIMARY KEY,
                source_label TEXT NOT NULL,
                data_trust TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE option_quote_snapshots (
                id INTEGER PRIMARY KEY,
                as_of_utc TEXT NOT NULL,
                quote_date_et TEXT NOT NULL,
                quote_minute_et INTEGER NOT NULL,
                snapshot_kind TEXT NOT NULL,
                underlying TEXT NOT NULL,
                contract_symbol TEXT NOT NULL,
                expiry TEXT NOT NULL,
                option_type TEXT NOT NULL,
                strike REAL NOT NULL,
                bid REAL,
                ask REAL,
                last REAL,
                iv REAL,
                underlying_price REAL,
                volume INTEGER,
                open_interest INTEGER,
                source_batch_id INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO import_batches (id, source_label, data_trust) VALUES (1, 'thetadata_opra_nbbo_1m', 'trusted')"
        )
        for idx, (underlying, contract, expiry, bid, ask) in enumerate(rows, start=1):
            conn.execute(
                """
                INSERT INTO option_quote_snapshots (
                    id, as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                    contract_symbol, expiry, option_type, strike, bid, ask, source_batch_id
                ) VALUES (?, '2026-06-04T14:10:00Z', '2026-06-04', 610, 'intraday', ?, ?, ?, 'call', ?, ?, ?, 1)
                """,
                (idx, underlying, contract, expiry, float(idx), bid, ask),
            )
        conn.commit()
    finally:
        conn.close()


def _pick(playbook: str, ticker: str, long_contract: str, short_contract: str, debit: float) -> dict:
    return {
        "scan_date": "2026-06-01",
        "playbook": playbook,
        "lane_label": playbook,
        "ticker": ticker,
        "direction": "call",
        "contract_symbol": long_contract,
        "short_contract_symbol": short_contract,
        "expiry": "2026-06-12",
        "strike": 100.0,
        "short_strike": 110.0,
        "dte": 11,
        "net_debit": debit,
    }


def test_outcome_audit_builds_lane_gates_from_untracked_conservative_marks() -> None:
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "options_history.db"
        _init_options_db(
            db_path,
            [
                ("AAA", "AAA260612C00100000", "2026-06-12", 2.2, 2.3),
                ("AAA", "AAA260612C00110000", "2026-06-12", 0.1, 0.2),
                ("BBB", "BBB260612C00100000", "2026-06-12", 2.1, 2.2),
                ("BBB", "BBB260612C00110000", "2026-06-12", 0.1, 0.2),
                ("CCC", "CCC260612C00100000", "2026-06-12", 0.1, 0.2),
                ("CCC", "CCC260612C00110000", "2026-06-12", 0.5, 0.6),
                ("DDD", "DDD260612C00100000", "2026-06-12", 0.1, 0.2),
                ("DDD", "DDD260612C00110000", "2026-06-12", 0.5, 0.6),
                ("EEE", "EEE260612C00100000", "2026-06-12", 0.1, 0.2),
                ("EEE", "EEE260612C00110000", "2026-06-12", 0.5, 0.6),
                ("FFF", "FFF260612C00100000", "2026-06-12", 1.5, 1.6),
                ("FFF", "FFF260612C00110000", "2026-06-12", 0.4, 0.5),
            ],
        )
        rows = [
            _pick("profitable_lane", "AAA", "AAA260612C00100000", "AAA260612C00110000", 1.0),
            _pick("profitable_lane", "BBB", "BBB260612C00100000", "BBB260612C00110000", 1.0),
            _pick("profitable_lane", "CCC", "CCC260612C00100000", "CCC260612C00110000", 1.0),
            _pick("bad_lane", "DDD", "DDD260612C00100000", "DDD260612C00110000", 1.0),
            _pick("bad_lane", "EEE", "EEE260612C00100000", "EEE260612C00110000", 1.0),
            _pick("tracked_lane", "FFF", "FFF260612C00100000", "FFF260612C00110000", 1.0),
        ]
        positions = [
            {
                "id": 99,
                "status": "closed",
                "ticker": "FFF",
                "contract_symbol": "FFF260612C00100000",
                "source_pick_snapshot": {
                    "scan_date": "2026-06-01",
                    "playbook_id": "tracked_lane",
                    "ticker": "FFF",
                    "short_contract_symbol": "FFF260612C00110000",
                },
                "net_pnl_pct": 12.5,
            }
        ]

        report = audit.build_report(
            input_rows=rows,
            positions=positions,
            options_db=db_path,
            source_labels=["thetadata_opra_nbbo_1m"],
            trusted_only=True,
            fee_total_usd=2.60,
            min_priced_rows=2,
            min_profit_factor=1.10,
            min_avg_net_pnl_pct=0.0,
            min_cluster_rows=2,
            input_info={"source": "unit"},
            position_store={"status": "unit"},
        )

    assert report["summary"]["raw_row_count"] == 6
    assert report["summary"]["tracked_row_count"] == 1
    assert report["summary"]["untracked_row_count"] == 5
    assert report["lane_gates"]["profitable_lane"]["auto_track_allowed"] is True
    assert report["lane_gates"]["bad_lane"]["auto_track_allowed"] is False
    assert "profit_factor_below_lane_gate" in report["lane_gates"]["bad_lane"]["blockers"]


class MissedRegularPicksOutcomeAuditTests(unittest.TestCase):
    def test_outcome_audit_builds_lane_gates_from_untracked_conservative_marks(self) -> None:
        test_outcome_audit_builds_lane_gates_from_untracked_conservative_marks()
