from __future__ import annotations

import copy
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, contextmanager
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repository_migrations import (  # noqa: E402
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
)
from repository_parity import (  # noqa: E402
    COMMON_LATEST_REVIEW_FIELDS,
    COMMON_LIFECYCLES,
    COMMON_POSITION_ROW_FIELDS,
    COMMON_POSITION_TABLE_COLUMNS,
    COMMON_REVIEW_TABLE_COLUMNS,
    SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS,
    TRACKED_ONLY_REPOSITORY_METHODS,
    TRACKED_ONLY_RESPONSE_FIELDS,
    boundaries_by_category,
    record_parity_manifest,
    route_parity_manifest,
)
from positions_repository import MemoryTrackedPositionsRepository  # noqa: E402
from suggested_trades_repository import SQLiteSuggestedTradesRepository  # noqa: E402


class TradingDeskRecordParityTests(unittest.TestCase):
    def _runtime_parity_payload(self) -> dict:
        source_snapshot = {
            "ticker": "AAA",
            "direction": "call",
            "contract_symbol": "AAA260619C00100000",
            "source_scan_session_id": 55,
            "source_scan_event_key": "short_term:rank_1",
            "source_scan_run_id": "api_scan_20260604T140000Z",
            "source_scan_recorded_at_utc": "2026-06-04T14:00:00Z",
            "proof_eligible": True,
            "proof_ineligibility_reason": None,
            "proof_class": "live_scan_exact_contract",
            "proof_class_reason": "all_live_scan_proof_gates_passed",
            "source_scan_lineage_verified": True,
        }
        return {
            "status": "open",
            "ticker": "AAA",
            "direction": "call",
            "contract_symbol": "AAA260619C00100000",
            "strike": 100.0,
            "expiry": date(2026, 6, 19),
            "asset_class": "equity",
            "contracts": 2,
            "entry_option_price": 4.5,
            "entry_execution_price": 4.5,
            "entry_execution_basis": "ask",
            "entry_fee_total_usd": 1.3,
            "entry_underlying_price": 101.25,
            "filled_at": datetime(2026, 6, 4, 14, 0, 0),
            "stop_loss_pct": 50.0,
            "profit_target_pct": 100.0,
            "time_exit_day": 4,
            "peak_pnl_pct": None,
            "last_option_price": None,
            "last_pnl_pct": None,
            "last_recommendation": None,
            "last_recommendation_reason": None,
            "last_reviewed_at": None,
            "source_pick_snapshot": source_snapshot,
            "notes": "parity fixture",
            "closed_at": None,
            "exit_option_price": None,
            "exit_execution_price": None,
            "exit_execution_basis": None,
            "exit_reason": None,
            "gross_pnl_pct": None,
            "net_pnl_pct": None,
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "fee_total_usd": 1.3,
            "source_scan_session_id": 55,
            "source_scan_event_key": "short_term:rank_1",
            "source_scan_run_id": "api_scan_20260604T140000Z",
            "source_scan_recorded_at_utc": "2026-06-04T14:00:00Z",
            "proof_eligible": True,
            "proof_ineligibility_reason": None,
            "proof_class": "live_scan_exact_contract",
            "proof_class_reason": "all_live_scan_proof_gates_passed",
        }

    def _runtime_review_payload(self) -> dict:
        return {
            "reviewed_at": datetime(2026, 6, 5, 14, 0, 0),
            "pricing_source": "mid",
            "current_option_price": 5.25,
            "current_pnl_pct": 16.67,
            "gross_pnl_pct": 16.67,
            "net_pnl_pct": 15.81,
            "gross_pnl_usd": 150.0,
            "net_pnl_usd": 147.4,
            "entry_execution_price": 4.5,
            "exit_execution_price": 5.25,
            "entry_execution_basis": "ask",
            "exit_execution_basis": "bid",
            "fee_total_usd": 2.6,
            "recommendation": "HOLD",
            "reason": "Parity review.",
            "warnings": ["parity-warning"],
            "metrics_snapshot": {
                "price_trigger_ok": True,
                "pricing_state": "priced_exact",
            },
            "peak_pnl_pct": 16.67,
        }

    @contextmanager
    def _create_runtime_parity_rows(self):
        payload = self._runtime_parity_payload()
        tracked_repo = MemoryTrackedPositionsRepository()
        self.assertTrue(tracked_repo.init_schema())

        with tempfile.TemporaryDirectory() as tmpdir:
            suggested_repo = SQLiteSuggestedTradesRepository(os.path.join(tmpdir, "suggested.db"))
            self.assertTrue(suggested_repo.init_schema())
            tracked_row = tracked_repo.create_position(copy.deepcopy(payload))
            suggested_row = suggested_repo.create_position(copy.deepcopy(payload))
            yield tracked_repo, suggested_repo, tracked_row, suggested_row

    def assertCommonPositionRowShape(self, row: dict) -> None:
        self.assertEqual(set(COMMON_POSITION_ROW_FIELDS), set(row) & set(COMMON_POSITION_ROW_FIELDS))

    def assertCommonLatestReviewShape(self, review: dict) -> None:
        self.assertEqual(set(COMMON_LATEST_REVIEW_FIELDS), set(review))

    def test_record_parity_manifest_names_shared_and_separate_boundaries(self):
        manifest = record_parity_manifest()
        ids = [entry["parity_id"] for entry in manifest]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(boundaries_by_category("shared_workflow"))
        self.assertTrue(boundaries_by_category("shared_row_shape"))
        self.assertTrue(boundaries_by_category("shared_review_shape"))
        self.assertTrue(boundaries_by_category("intentional_difference"))
        self.assertTrue(boundaries_by_category("tracked_only"))
        self.assertTrue(boundaries_by_category("suggested_trade_boundary"))
        self.assertIn("tracked_only_proof_fields", ids)
        self.assertIn("tracked_only_lifecycle_event_persistence", ids)
        self.assertIn("suggested_trade_paper_boundary", ids)

    def test_route_parity_manifest_keeps_lifecycle_parallel_and_store_ids_split(self):
        manifest = route_parity_manifest()

        self.assertEqual(tuple(entry["lifecycle"] for entry in manifest), COMMON_LIFECYCLES)
        for entry in manifest:
            with self.subTest(lifecycle=entry["lifecycle"]):
                self.assertEqual(entry["tracked_store_id"], POSTGRES_TRACKED_POSITIONS_STORE_ID)
                self.assertEqual(entry["suggested_store_id"], SQLITE_SUGGESTED_TRADES_STORE_ID)
                self.assertEqual(entry["tracked_record_class"], "tracked_position")
                self.assertEqual(entry["suggested_record_class"], "suggested_trade")
                self.assertTrue(entry["shared_contract"])
                self.assertTrue(entry["intentional_difference"])

        response_keys = {entry["lifecycle"]: entry for entry in manifest}
        self.assertEqual(response_keys["read"]["tracked_response_key"], "positions")
        self.assertEqual(response_keys["read"]["suggested_response_key"], "trades")
        self.assertEqual(response_keys["create"]["tracked_response_key"], "position")
        self.assertEqual(response_keys["create"]["suggested_response_key"], "trade")
        self.assertEqual(response_keys["review"]["tracked_response_key"], "positions")
        self.assertEqual(response_keys["review"]["suggested_response_key"], "trades")
        self.assertEqual(response_keys["close"]["tracked_response_key"], "position")
        self.assertEqual(response_keys["close"]["suggested_response_key"], "trade")

    def test_common_and_forbidden_field_manifests_are_explicit(self):
        self.assertIn("latest_review", COMMON_POSITION_ROW_FIELDS)
        self.assertIn("metrics_snapshot", COMMON_LATEST_REVIEW_FIELDS)
        self.assertIn("entry_fee_total_usd", COMMON_POSITION_TABLE_COLUMNS)
        self.assertIn("source_pick_snapshot", COMMON_POSITION_TABLE_COLUMNS)
        self.assertIn("metrics_snapshot", COMMON_REVIEW_TABLE_COLUMNS)

        self.assertIn("proof_eligible", SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS)
        self.assertIn("source_scan_session_id", SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS)
        self.assertIn("position_event_persistence", TRACKED_ONLY_RESPONSE_FIELDS)
        self.assertIn("profit_status_snapshot", TRACKED_ONLY_REPOSITORY_METHODS)
        self.assertIn("get_realized_pnl_since", TRACKED_ONLY_REPOSITORY_METHODS)

        self.assertTrue(
            set(SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS).isdisjoint(COMMON_POSITION_TABLE_COLUMNS)
        )

    def test_sqlite_suggested_schema_has_common_columns_without_tracked_only_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "suggested.db")
            repo = SQLiteSuggestedTradesRepository(db_path)
            self.assertTrue(repo.init_schema())

            with closing(sqlite3.connect(db_path)) as conn:
                trade_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(suggested_trades)").fetchall()
                }
                review_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(suggested_trade_reviews)").fetchall()
                }

        for column in COMMON_POSITION_TABLE_COLUMNS:
            with self.subTest(column=column):
                self.assertIn(column, trade_columns)
        for column in SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS:
            with self.subTest(forbidden=column):
                self.assertNotIn(column, trade_columns)
        for column in COMMON_REVIEW_TABLE_COLUMNS:
            with self.subTest(review_column=column):
                self.assertIn(column, review_columns)

    def test_executable_open_rows_share_common_display_fields_but_keep_tracked_only_fields_split(self):
        with self._create_runtime_parity_rows() as (
            _tracked_repo,
            _suggested_repo,
            tracked_row,
            suggested_row,
        ):
            self.assertCommonPositionRowShape(tracked_row)
            self.assertCommonPositionRowShape(suggested_row)

            shared_values = (
                "status",
                "ticker",
                "direction",
                "contract_symbol",
                "strike",
                "asset_class",
                "contracts",
                "entry_option_price",
                "entry_execution_price",
                "entry_execution_basis",
                "entry_fee_total_usd",
                "entry_underlying_price",
                "stop_loss_pct",
                "profit_target_pct",
                "time_exit_day",
                "notes",
                "fee_total_usd",
            )
            for field in shared_values:
                with self.subTest(field=field):
                    self.assertEqual(tracked_row[field], suggested_row[field])

            self.assertEqual(str(tracked_row["expiry"])[:10], "2026-06-19")
            self.assertEqual(str(suggested_row["expiry"])[:10], "2026-06-19")
            self.assertTrue(str(tracked_row["filled_at"]).startswith("2026-06-04T14:00:00"))
            self.assertTrue(str(suggested_row["filled_at"]).startswith("2026-06-04T14:00:00"))

            for field in SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS:
                with self.subTest(tracked_only=field):
                    self.assertIn(field, tracked_row)
                    self.assertNotIn(field, suggested_row)
                    self.assertIn(field, suggested_row["source_pick_snapshot"])

            self.assertEqual(
                suggested_row["source_pick_snapshot"]["source_scan_run_id"],
                tracked_row["source_scan_run_id"],
            )
            self.assertTrue(tracked_row["proof_eligible"])
            self.assertTrue(suggested_row["source_pick_snapshot"]["proof_eligible"])
            self.assertIsNone(tracked_row["latest_review"])
            self.assertIsNone(suggested_row["latest_review"])

    def test_executable_review_and_close_rows_share_common_shapes_without_merging_meaning(self):
        with self._create_runtime_parity_rows() as (
            tracked_repo,
            suggested_repo,
            tracked_row,
            suggested_row,
        ):
            review_payload = self._runtime_review_payload()
            tracked_reviewed = tracked_repo.save_review(
                tracked_row["id"],
                copy.deepcopy(review_payload),
            )
            suggested_reviewed = suggested_repo.save_review(
                suggested_row["id"],
                copy.deepcopy(review_payload),
            )

            self.assertCommonPositionRowShape(tracked_reviewed)
            self.assertCommonPositionRowShape(suggested_reviewed)
            self.assertCommonLatestReviewShape(tracked_reviewed["latest_review"])
            self.assertCommonLatestReviewShape(suggested_reviewed["latest_review"])

            for field in (
                "pricing_source",
                "current_option_price",
                "gross_pnl_pct",
                "net_pnl_pct",
                "fee_total_usd",
                "recommendation",
                "reason",
                "warnings",
                "metrics_snapshot",
            ):
                with self.subTest(review_field=field):
                    self.assertEqual(
                        tracked_reviewed["latest_review"][field],
                        suggested_reviewed["latest_review"][field],
                    )

            close_time = datetime(2026, 6, 6, 14, 0, 0)
            tracked_closed = tracked_repo.close_position(
                tracked_row["id"],
                5.75,
                close_time,
                "manual_hypothetical_close",
                notes="closed parity",
                exit_execution_basis="manual_close",
            )
            suggested_closed = suggested_repo.close_position(
                suggested_row["id"],
                5.75,
                close_time,
                "manual_hypothetical_close",
                notes="closed parity",
                exit_execution_basis="manual_close",
            )
            self.assertIsNotNone(tracked_closed)
            self.assertIsNotNone(suggested_closed)

            self.assertCommonPositionRowShape(tracked_closed)
            self.assertCommonPositionRowShape(suggested_closed)
            self.assertCommonLatestReviewShape(tracked_closed["latest_review"])
            self.assertCommonLatestReviewShape(suggested_closed["latest_review"])
            self.assertEqual(tracked_closed["status"], "closed")
            self.assertEqual(suggested_closed["status"], "closed")

            for field in (
                "exit_option_price",
                "exit_execution_price",
                "exit_execution_basis",
                "exit_reason",
                "gross_pnl_pct",
                "net_pnl_pct",
                "gross_pnl_usd",
                "net_pnl_usd",
                "fee_total_usd",
            ):
                with self.subTest(close_field=field):
                    self.assertEqual(tracked_closed[field], suggested_closed[field])

            self.assertEqual(tracked_closed["latest_review"]["recommendation"], "SELL")
            self.assertEqual(suggested_closed["latest_review"]["recommendation"], "SELL")
            self.assertEqual(
                tracked_closed["latest_review"]["metrics_snapshot"]["pricing_state"],
                "closed",
            )
            self.assertEqual(
                suggested_closed["latest_review"]["metrics_snapshot"]["pricing_state"],
                "closed",
            )

            for field in SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS:
                with self.subTest(forbidden_after_close=field):
                    self.assertIn(field, tracked_closed)
                    self.assertNotIn(field, suggested_closed)
                    self.assertIn(field, suggested_closed["source_pick_snapshot"])

    def test_docs_name_parity_owner_and_do_not_merge_boundaries(self):
        docs = {
            "index": (ROOT / "docs" / "index.md").read_text(encoding="utf-8"),
            "api": (ROOT / "docs" / "api-and-storage.md").read_text(encoding="utf-8"),
            "repository": (ROOT / "docs" / "repository-contract.md").read_text(encoding="utf-8"),
            "architecture": (ROOT / "docs" / "architecture-overview.md").read_text(encoding="utf-8"),
            "project": (ROOT / "docs" / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"),
            "parity": (ROOT / "docs" / "trading-desk-record-parity.md").read_text(encoding="utf-8"),
        }
        for name, text in docs.items():
            with self.subTest(name=name):
                self.assertIn("trading-desk-record-parity.md", text)
                self.assertIn("repository_parity.py", text)

        parity_doc = docs["parity"]
        self.assertIn("SuggestedTrade = TrackedPosition", parity_doc)
        self.assertIn("Suggested trades are local paper/hypothetical ideas", parity_doc)
        self.assertIn("Do not merge suggested trades into tracked positions", parity_doc)
        self.assertIn("Do not add `position_event_persistence` to suggested-trade mutation responses", parity_doc)
        self.assertIn("Do not count suggested trades in production proof", parity_doc)
        self.assertIn("Executable Row-Shape Test Map", parity_doc)
        self.assertIn(
            "test_executable_review_and_close_rows_share_common_shapes_without_merging_meaning",
            parity_doc,
        )

    def test_frontend_store_contract_still_names_distinct_record_classes(self):
        store_source = (ROOT / "src" / "lib" / "trading-desk" / "storeOwnership.ts").read_text(
            encoding="utf-8"
        )
        type_source = (ROOT / "src" / "lib" / "types.ts").read_text(encoding="utf-8")

        self.assertIn('"postgres_tracked_positions"', store_source)
        self.assertIn('"sqlite_suggested_trades"', store_source)
        self.assertIn('"tracked_position"', store_source)
        self.assertIn('"suggested_trade"', store_source)
        self.assertIn("export type SuggestedTrade = TrackedPosition;", type_source)


if __name__ == "__main__":
    unittest.main()
