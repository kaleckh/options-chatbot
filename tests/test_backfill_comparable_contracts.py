import unittest
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import backfill_comparable_contracts as backfill
from scripts.backfill_comparable_contracts import _needs_backfill


class BackfillComparableContractsTests(unittest.TestCase):
    def test_needs_backfill_for_open_dict_row_with_null_contract_symbol(self):
        self.assertTrue(
            _needs_backfill(
                {"status": "open", "contract_symbol": None},
                {},
            )
        )

    def test_migrate_suggested_trades_populates_row_contract_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE suggested_trades (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    contracts INTEGER,
                    contract_symbol TEXT,
                    strike REAL,
                    expiry TEXT,
                    entry_option_price REAL,
                    entry_underlying_price REAL,
                    source_pick_snapshot TEXT,
                    filled_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO suggested_trades (
                    id, status, contracts, contract_symbol, strike, expiry,
                    entry_option_price, entry_underlying_price, source_pick_snapshot, filled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "open",
                    1,
                    None,
                    495.0,
                    "2026-06-19",
                    4.5,
                    500.0,
                    json.dumps({"ticker": "SPY", "approximation_only": True}),
                    "2026-05-21T14:30:00Z",
                ),
            )
            conn.commit()
            conn.close()

            resolved = {
                "ticker": "SPY",
                "contract_symbol": "SPY260619C00500000",
                "strike": 500.0,
                "expiry": "2026-06-19",
                "entry_underlying_price": 501.0,
            }
            with patch.object(backfill, "SUGGESTED_DB_PATH", db_path), \
                 patch.object(backfill, "resolve_comparable_contract_pick", return_value=(resolved, 5.0, {"ok": True})):
                result = backfill.migrate_suggested_trades()

            self.assertEqual(result["updated_ids"], [1])
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT contract_symbol, strike, entry_option_price, source_pick_snapshot FROM suggested_trades WHERE id = 1"
            ).fetchone()
            conn.close()
            self.assertEqual(row[0], "SPY260619C00500000")
            self.assertEqual(row[1], 500.0)
            self.assertEqual(row[2], 5.0)
            self.assertEqual(json.loads(row[3])["contract_symbol"], "SPY260619C00500000")

    def test_migrate_suggested_trades_repairs_missing_column_from_exact_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE suggested_trades (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    contracts INTEGER,
                    contract_symbol TEXT,
                    strike REAL,
                    expiry TEXT,
                    entry_option_price REAL,
                    entry_underlying_price REAL,
                    source_pick_snapshot TEXT,
                    filled_at TEXT,
                    updated_at TEXT
                )
                """
            )
            snapshot = {
                "ticker": "SPY",
                "contract_symbol": "SPY260619C00500000",
                "strike": 500.0,
                "expiry": "2026-06-19",
                "entry_underlying_price": 501.0,
            }
            conn.execute(
                """
                INSERT INTO suggested_trades (
                    id, status, contracts, contract_symbol, strike, expiry,
                    entry_option_price, entry_underlying_price, source_pick_snapshot, filled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "open",
                    1,
                    None,
                    500.0,
                    "2026-06-19",
                    5.0,
                    501.0,
                    json.dumps(snapshot),
                    "2026-05-21T14:30:00Z",
                ),
            )
            conn.commit()
            conn.close()

            with patch.object(backfill, "SUGGESTED_DB_PATH", db_path), \
                 patch.object(backfill, "resolve_comparable_contract_pick", side_effect=AssertionError("resolver not needed")):
                result = backfill.migrate_suggested_trades()

            self.assertEqual(result["updated_ids"], [1])
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT contract_symbol, entry_option_price FROM suggested_trades WHERE id = 1").fetchone()
            conn.close()
            self.assertEqual(row[0], "SPY260619C00500000")
            self.assertEqual(row[1], 5.0)

    def test_migrate_suggested_trades_accepts_contract_symbol_alias_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE suggested_trades (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    contracts INTEGER,
                    contract_symbol TEXT,
                    strike REAL,
                    expiry TEXT,
                    entry_option_price REAL,
                    entry_underlying_price REAL,
                    source_pick_snapshot TEXT,
                    filled_at TEXT,
                    updated_at TEXT
                )
                """
            )
            snapshot = {
                "ticker": "SPY",
                "contractSymbol": "SPY260619C00500000",
                "strike": 500.0,
                "expiry": "2026-06-19",
                "entry_underlying_price": 501.0,
            }
            conn.execute(
                """
                INSERT INTO suggested_trades (
                    id, status, contracts, contract_symbol, strike, expiry,
                    entry_option_price, entry_underlying_price, source_pick_snapshot, filled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "open",
                    1,
                    None,
                    500.0,
                    "2026-06-19",
                    5.0,
                    501.0,
                    json.dumps(snapshot),
                    "2026-05-21T14:30:00Z",
                ),
            )
            conn.commit()
            conn.close()

            with patch.object(backfill, "SUGGESTED_DB_PATH", db_path), \
                 patch.object(backfill, "resolve_comparable_contract_pick", side_effect=AssertionError("resolver not needed")):
                result = backfill.migrate_suggested_trades()

            self.assertEqual(result["updated_ids"], [1])
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT contract_symbol, source_pick_snapshot FROM suggested_trades WHERE id = 1").fetchone()
            conn.close()
            self.assertEqual(row[0], "SPY260619C00500000")
            self.assertEqual(json.loads(row[1])["contract_symbol"], "SPY260619C00500000")

    def test_migrate_tracked_positions_accepts_spread_contract_aliases_in_snapshot(self):
        class FakeRepository:
            def __init__(self):
                self.updated: list[tuple[int, dict]] = []
                self.rows = [
                    {
                        "id": 1,
                        "status": "open",
                        "contracts": 1,
                        "contract_symbol": None,
                        "strike": 500.0,
                        "expiry": "2026-06-19",
                        "entry_option_price": 5.0,
                        "entry_underlying_price": 501.0,
                        "filled_at": "2026-05-21T14:30:00Z",
                        "source_pick_snapshot": {
                            "ticker": "SPY",
                            "contractSymbol": "SPY260619C00500000",
                            "shortContractSymbol": "SPY260619C00520000",
                            "strike": 500.0,
                            "short_strike": 520.0,
                            "expiry": "2026-06-19",
                            "entry_underlying_price": 501.0,
                        },
                    }
                ]

            def list_positions(self, _status):
                return self.rows

            def update_position(self, position_id, updates):
                self.updated.append((position_id, updates))
                return updates

        repo = FakeRepository()

        with patch.object(backfill, "resolve_comparable_contract_pick", side_effect=AssertionError("resolver not needed")):
            result = backfill.migrate_tracked_positions(repo)

        self.assertEqual(result["updated_ids"], [1])
        self.assertEqual(repo.updated[0][1]["contract_symbol"], "SPY260619C00500000")
        self.assertEqual(repo.updated[0][1]["source_pick_snapshot"]["short_contract_symbol"], "SPY260619C00520000")

    def test_migrate_tracked_positions_repairs_missing_column_from_exact_snapshot(self):
        class FakeRepository:
            def __init__(self):
                self.updated: list[tuple[int, dict]] = []
                self.rows = [
                    {
                        "id": 1,
                        "status": "open",
                        "contracts": 1,
                        "contract_symbol": None,
                        "strike": 500.0,
                        "expiry": "2026-06-19",
                        "entry_option_price": 5.0,
                        "entry_underlying_price": 501.0,
                        "filled_at": "2026-05-21T14:30:00Z",
                        "source_pick_snapshot": {
                            "ticker": "SPY",
                            "contract_symbol": "SPY260619C00500000",
                            "strike": 500.0,
                            "expiry": "2026-06-19",
                            "entry_underlying_price": 501.0,
                        },
                    }
                ]

            def list_positions(self, _status):
                return self.rows

            def update_position(self, position_id, updates):
                self.updated.append((position_id, updates))
                return updates

        repo = FakeRepository()

        with patch.object(backfill, "resolve_comparable_contract_pick", side_effect=AssertionError("resolver not needed")):
            result = backfill.migrate_tracked_positions(repo)

        self.assertEqual(result["updated_ids"], [1])
        self.assertEqual(repo.updated[0][0], 1)
        self.assertEqual(repo.updated[0][1]["contract_symbol"], "SPY260619C00500000")
        self.assertEqual(repo.updated[0][1]["entry_option_price"], 5.0)
        self.assertEqual(repo.updated[0][1]["proof_ineligibility_reason"], "comparable_exact_contract")

    def test_migrate_tracked_positions_resolves_missing_short_leg_for_spreads(self):
        class FakeRepository:
            def __init__(self):
                self.updated: list[tuple[int, dict]] = []
                self.rows = [
                    {
                        "id": 1,
                        "status": "open",
                        "contracts": 1,
                        "contract_symbol": "SPY260619C00500000",
                        "strike": 500.0,
                        "expiry": "2026-06-19",
                        "entry_option_price": 5.0,
                        "entry_underlying_price": 501.0,
                        "filled_at": "2026-05-21T14:30:00Z",
                        "source_pick_snapshot": {
                            "ticker": "SPY",
                            "contract_symbol": "SPY260619C00500000",
                            "strike": 500.0,
                            "short_strike": 520.0,
                            "expiry": "2026-06-19",
                            "entry_underlying_price": 501.0,
                        },
                    }
                ]

            def list_positions(self, _status):
                return self.rows

            def update_position(self, position_id, updates):
                self.updated.append((position_id, updates))
                return updates

        resolved = dict(FakeRepository().rows[0]["source_pick_snapshot"])
        resolved["short_contract_symbol"] = "SPY260619C00520000"
        repo = FakeRepository()

        with patch.object(backfill, "resolve_comparable_contract_pick", return_value=(resolved, 5.25, {"ok": True})) as resolver:
            result = backfill.migrate_tracked_positions(repo)

        self.assertEqual(result["updated_ids"], [1])
        resolver.assert_called_once()
        self.assertEqual(repo.updated[0][1]["source_pick_snapshot"]["short_contract_symbol"], "SPY260619C00520000")
        self.assertEqual(repo.updated[0][1]["entry_option_price"], 5.25)

    def test_migrate_suggested_trades_resolves_missing_short_leg_for_spreads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "chat_history.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE suggested_trades (
                    id INTEGER PRIMARY KEY,
                    status TEXT,
                    contracts INTEGER,
                    contract_symbol TEXT,
                    strike REAL,
                    expiry TEXT,
                    entry_option_price REAL,
                    entry_underlying_price REAL,
                    source_pick_snapshot TEXT,
                    filled_at TEXT,
                    updated_at TEXT
                )
                """
            )
            snapshot = {
                "ticker": "SPY",
                "contract_symbol": "SPY260619C00500000",
                "strike": 500.0,
                "short_strike": 520.0,
                "expiry": "2026-06-19",
                "entry_underlying_price": 501.0,
            }
            conn.execute(
                """
                INSERT INTO suggested_trades (
                    id, status, contracts, contract_symbol, strike, expiry,
                    entry_option_price, entry_underlying_price, source_pick_snapshot, filled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "open",
                    1,
                    "SPY260619C00500000",
                    500.0,
                    "2026-06-19",
                    5.0,
                    501.0,
                    json.dumps(snapshot),
                    "2026-05-21T14:30:00Z",
                ),
            )
            conn.commit()
            conn.close()

            resolved = dict(snapshot)
            resolved["short_contract_symbol"] = "SPY260619C00520000"
            with patch.object(backfill, "SUGGESTED_DB_PATH", db_path), \
                 patch.object(backfill, "resolve_comparable_contract_pick", return_value=(resolved, 5.25, {"ok": True})) as resolver:
                result = backfill.migrate_suggested_trades()

            self.assertEqual(result["updated_ids"], [1])
            resolver.assert_called_once()
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT entry_option_price, source_pick_snapshot FROM suggested_trades WHERE id = 1").fetchone()
            conn.close()
            self.assertEqual(row[0], 5.25)
            self.assertEqual(json.loads(row[1])["short_contract_symbol"], "SPY260619C00520000")


if __name__ == "__main__":
    unittest.main()
