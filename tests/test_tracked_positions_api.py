import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import options_chatbot as oc
import market_data_service as mds
import wfo_optimizer as wfo

from options_execution import commission_total_usd


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
BACKEND_DIR = ROOT / "python-backend"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import positions_service as psvc
from options_algorithm_fixtures import (
    FrozenDateTime,
    build_options_algorithm_fixture_bundle,
    build_tracked_position_scan_pick,
    load_backend_main,
)
from positions_repository import MemoryTrackedPositionsRepository, UnavailableTrackedPositionsRepository


class _CompactClosedPositionsOnlyRepository:
    is_available = True

    def __init__(self):
        self.compact_called = False
        self.status = None
        self.limit = None
        self.offset = None

    def list_positions(self, *args, **kwargs):
        raise AssertionError("compact closed reads should not use the full position list")

    def list_compact_positions(self, status="open", *, limit=None, offset=0):
        self.compact_called = True
        self.status = status
        self.limit = limit
        self.offset = offset
        return [
            {
                "id": 999,
                "status": "closed",
                "ticker": "MSFT",
                "direction": "call",
                "contract_symbol": "MSFT260117C00400000",
                "strike": 400.0,
                "expiry": "2026-01-17",
                "asset_class": "equity",
                "contracts": 1,
                "entry_option_price": 5.0,
                "entry_execution_price": 5.0,
                "entry_execution_basis": "ask",
                "entry_fee_total_usd": 0.65,
                "entry_underlying_price": 401.0,
                "filled_at": "2026-01-02T15:00:00Z",
                "stop_loss_pct": 90,
                "profit_target_pct": 100,
                "time_exit_day": 14,
                "peak_pnl_pct": None,
                "last_option_price": 6.5,
                "last_pnl_pct": 30.0,
                "last_recommendation": "SELL",
                "last_recommendation_reason": "target",
                "last_reviewed_at": "2026-01-03T15:00:00Z",
                "source_pick_snapshot": {
                    "playbook_id": "short_term",
                    "playbook_label": "Short Term",
                    "scan_date": "2026-01-02",
                    "debit_pct_of_width": 50.0,
                    "net_debit": 5.0,
                    "spread_width": 10.0,
                    "ret5": 0.4,
                    "selection_source": "historical_chain_native_exact_contract",
                    "promotion_class": "research_backfill_exact_contract",
                    "backfill_audit_id": "audit-v1",
                    "position_migration_id": "migration-v1",
                    "research_only": True,
                    "contract_symbol": "detail-only-source-contract",
                },
                "notes": "x" * 180,
                "closed_at": "2026-01-03T15:00:00Z",
                "exit_option_price": 6.5,
                "exit_execution_price": 6.5,
                "exit_execution_basis": "spread_bid_ask_exact",
                "exit_reason": "target",
                "gross_pnl_pct": 30.0,
                "net_pnl_pct": 29.2,
                "gross_pnl_usd": 150.0,
                "net_pnl_usd": 148.7,
                "fee_total_usd": 1.3,
                "source_scan_session_id": None,
                "source_scan_event_key": "detail-only-event",
                "source_scan_run_id": "detail-only-run",
                "source_scan_recorded_at_utc": "2026-01-02T15:00:00Z",
                "proof_eligible": False,
                "proof_ineligibility_reason": "research_backfill",
                "proof_class": "ineligible",
                "proof_class_reason": "research_backfill",
                "created_at": "2026-01-02T15:00:00Z",
                "updated_at": "2026-01-03T15:00:00Z",
                "latest_review": {"id": 1, "recommendation": "SELL"},
            }
        ]


class TrackedPositionsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._backend_tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._backend_tmp.name, "chat_history.db")
        cls.backend = load_backend_main(db_path)
        cls.client = TestClient(cls.backend.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls._backend_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.market_data_db_path = os.path.join(self._tmp.name, "market_data.db")
        self.bundle = build_options_algorithm_fixture_bundle()
        self.stack = ExitStack()
        self.addCleanup(self._cleanup)

        self.stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "MARKET_DATA_DB_PATH": self.market_data_db_path,
                    "OPTIONS_MARKET_DATA_PROVIDER": "yahoo",
                    "OPTIONS_RUN_MODE": "test",
                },
                clear=False,
            )
        )
        self.stack.enter_context(patch.object(oc, "DEFAULT_WATCHLIST", self.bundle.watchlist))
        self.stack.enter_context(patch.object(wfo, "DEFAULT_WATCHLIST", self.bundle.watchlist))
        self.stack.enter_context(patch.object(oc.yf, "Ticker", side_effect=self.bundle.make_ticker))
        self.stack.enter_context(patch.object(wfo.yf, "Ticker", side_effect=self.bundle.make_ticker))
        self.stack.enter_context(patch.object(psvc.yf, "Ticker", side_effect=self.bundle.make_ticker))
        self.stack.enter_context(patch.object(oc, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(wfo, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(psvc, "datetime", FrozenDateTime))
        self.stack.enter_context(patch.object(oc, "_market_is_open", return_value=False))
        self.stack.enter_context(patch.object(self.backend, "POSITIONS_REPOSITORY", MemoryTrackedPositionsRepository()))
        mds._MEMORY_CACHE.clear()
        mds._SCHEMA_READY.clear()

    def _cleanup(self):
        mds._MEMORY_CACHE.clear()
        self.stack.close()

    def test_positions_workflow_create_list_review_and_close(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 2,
                "notes": "Taken from scanner",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position = create_response.json()["position"]
        self.assertEqual(position["ticker"], scan_pick["ticker"])
        self.assertEqual(position["contracts"], 2)
        self.assertEqual(position["entry_option_price"], 4.5)
        self.assertEqual(position["contract_symbol"], scan_pick["contract_symbol"])
        self.assertEqual(position["source_pick_snapshot"]["ticker"], scan_pick["ticker"])

        list_open_response = self.client.get("/api/positions", params={"status": "open"})
        self.assertEqual(list_open_response.status_code, 200)
        open_payload = list_open_response.json()
        self.assertEqual(len(open_payload["positions"]), 1)
        self.assertEqual(open_payload["positions"][0]["status"], "open")

        paged_open_response = self.client.get("/api/positions", params={"status": "open", "limit": 1})
        self.assertEqual(paged_open_response.status_code, 200)
        paged_open_payload = paged_open_response.json()
        self.assertEqual(len(paged_open_payload["positions"]), 1)
        self.assertEqual(paged_open_payload["page"], {"limit": 1, "offset": 0, "returned": 1})

        invalid_window_response = self.client.get("/api/positions", params={"status": "open", "offset": 1})
        self.assertEqual(invalid_window_response.status_code, 400)
        self.assertEqual(invalid_window_response.json()["detail"], "offset requires limit.")

        grouped_open_response = self.client.get("/api/positions", params={"status": "all", "grouped": 1})
        self.assertEqual(grouped_open_response.status_code, 200)
        grouped_open_payload = grouped_open_response.json()
        self.assertEqual(len(grouped_open_payload["open"]), 1)
        self.assertEqual(grouped_open_payload["closed"], [])
        self.assertEqual(grouped_open_payload["summary"]["open"]["tracked"]["count"], 1)
        self.assertIn("proof", grouped_open_payload["summary"]["open"])

        review_response = self.client.post("/api/positions/review", json={})
        self.assertEqual(review_response.status_code, 200)
        reviewed = review_response.json()["positions"][0]
        self.assertTrue(
            {
                "id",
                "last_option_price",
                "last_pnl_pct",
                "last_recommendation",
                "last_recommendation_reason",
                "latest_review",
            }.issubset(reviewed.keys())
        )
        self.assertIn(reviewed["last_recommendation"], {"HOLD", "SELL"})
        self.assertTrue(
            {
                "reviewed_at",
                "pricing_source",
                "recommendation",
                "reason",
                "warnings",
                "metrics_snapshot",
            }.issubset(reviewed["latest_review"].keys())
        )

        close_response = self.client.post(
            f"/api/positions/{reviewed['id']}/close",
            json={"exit_price": 2.45, "notes": "User sold the position"},
        )
        self.assertEqual(close_response.status_code, 200)
        closed_position = close_response.json()["position"]
        self.assertEqual(closed_position["status"], "closed")
        self.assertEqual(closed_position["exit_option_price"], 2.45)
        self.assertEqual(closed_position["last_recommendation"], "SELL")
        self.assertEqual(closed_position["latest_review"]["recommendation"], "SELL")
        self.assertEqual(closed_position["latest_review"]["current_option_price"], 2.45)
        self.assertEqual(closed_position["latest_review"]["current_pnl_pct"], closed_position["gross_pnl_pct"])

        list_closed_response = self.client.get("/api/positions", params={"status": "closed"})
        self.assertEqual(list_closed_response.status_code, 200)
        closed_payload = list_closed_response.json()
        self.assertEqual(len(closed_payload["positions"]), 1)
        self.assertEqual(closed_payload["positions"][0]["status"], "closed")

        grouped_closed_response = self.client.get("/api/positions", params={"status": "all", "grouped": 1})
        self.assertEqual(grouped_closed_response.status_code, 200)
        grouped_closed_payload = grouped_closed_response.json()
        self.assertEqual(grouped_closed_payload["open"], [])
        self.assertEqual(len(grouped_closed_payload["closed"]), 1)
        self.assertEqual(grouped_closed_payload["summary"]["closed"]["tracked"]["count"], 1)
        self.assertEqual(grouped_closed_payload["summary"]["closed"]["tracked"]["priced_count"], 1)
        self.assertIn("proof", grouped_closed_payload["summary"]["closed"])

    def test_compact_closed_positions_use_narrow_repository_path(self):
        repository = _CompactClosedPositionsOnlyRepository()
        with patch.object(self.backend, "POSITIONS_REPOSITORY", repository):
            response = self.client.get(
                "/api/positions",
                params={"status": "closed", "limit": 100, "offset": 0, "compact": 1},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        position = payload["positions"][0]
        self.assertTrue(repository.compact_called)
        self.assertEqual(repository.status, "closed")
        self.assertEqual(repository.limit, 100)
        self.assertEqual(repository.offset, 0)
        self.assertEqual(payload["page"], {"limit": 100, "offset": 0, "returned": 1})
        self.assertEqual(position["source_pick_snapshot"]["debit_pct_of_width"], 50.0)
        self.assertEqual(position["compact_evidence"]["migrated_paper"], True)
        self.assertEqual(position["compact_evidence"]["research_backfill"], True)
        self.assertLessEqual(len(position["notes"]), 96)
        self.assertNotIn("latest_review", position)
        self.assertNotIn("contract_symbol", position["source_pick_snapshot"])
        self.assertNotIn("backfill_audit_id", position["source_pick_snapshot"])

    def test_review_rejects_invalid_position_ids(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )

        response = self.client.post("/api/positions/review", json={"position_ids": ["abc", 1]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("position_ids", response.text)

    def test_close_rejects_negative_exit_price_and_allows_zero(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        position_id = create_response.json()["position"]["id"]

        response = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": -0.01})
        self.assertEqual(response.status_code, 400)
        self.assertIn("exit_price", response.text)

        zero_response = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": 0})
        self.assertEqual(zero_response.status_code, 200)
        self.assertEqual(zero_response.json()["position"]["exit_option_price"], 0.0)

    def test_create_and_close_reject_json_booleans_as_numbers(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)

        bool_fill = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": True,
                "contracts": 1,
            },
        )
        self.assertEqual(bool_fill.status_code, 400)
        self.assertIn("fill_price", bool_fill.text)

        bool_contracts = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": True,
            },
        )
        self.assertEqual(bool_contracts.status_code, 400)
        self.assertIn("contracts", bool_contracts.text)

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position_id = create_response.json()["position"]["id"]

        bool_exit = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": True})
        self.assertEqual(bool_exit.status_code, 400)
        self.assertIn("exit_price", bool_exit.text)

    def test_create_rejects_bool_scan_pick_numeric_fields(self):
        for field in ("strike", "stop_loss_pct", "profit_target_pct", "time_exit_day"):
            with self.subTest(field=field):
                scan_pick = build_tracked_position_scan_pick(self.bundle)
                scan_pick[field] = True
                response = self.client.post(
                    "/api/positions",
                    json={
                        "scan_pick": scan_pick,
                        "fill_price": 4.50,
                        "contracts": 1,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.text)

    def test_create_rejects_non_object_scan_pick_and_invalid_text_fields(self):
        for scan_pick in ([1], True, "not-an-object"):
            with self.subTest(scan_pick=scan_pick):
                response = self.client.post(
                    "/api/positions",
                    json={"scan_pick": scan_pick, "fill_price": 4.50, "contracts": 1},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("scan_pick", response.text)

        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick.update(
            {
                "selection_source": "live_chain_exact_contract",
                "contract_selection_source": "live_chain_exact_contract",
                "quote_time_et": "2026-04-06T10:00:00-04:00",
                "bid": 4.4,
                "ask": 4.6,
                "entry_execution_price": 4.5,
                "entry_execution_basis": "ask",
                "contract_symbol": True,
                "options_data_source": "alpaca_opra",
            }
        )
        bool_contract = self.client.post(
            "/api/positions",
            json={"scan_pick": scan_pick, "fill_price": 4.50, "contracts": 1},
        )
        self.assertEqual(bool_contract.status_code, 400)
        self.assertIn("contract_symbol", bool_contract.text)

        bad_notes = self.client.post(
            "/api/positions",
            json={
                "scan_pick": build_tracked_position_scan_pick(self.bundle),
                "fill_price": 4.50,
                "contracts": 1,
                "notes": {"not": "text"},
            },
        )
        self.assertEqual(bad_notes.status_code, 400)
        self.assertIn("notes", bad_notes.text)

    def test_create_and_close_reject_malformed_timestamps(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_bad_time = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
                "filled_at": True,
            },
        )
        self.assertEqual(create_bad_time.status_code, 400)
        self.assertIn("filled_at", create_bad_time.text)

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position_id = create_response.json()["position"]["id"]

        close_bad_time = self.client.post(
            f"/api/positions/{position_id}/close",
            json={"exit_price": 1.0, "closed_at": True},
        )
        self.assertEqual(close_bad_time.status_code, 400)
        self.assertIn("closed_at", close_bad_time.text)

    def test_close_rejects_already_closed_position(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        position_id = create_response.json()["position"]["id"]

        first_close = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": 2.45})
        self.assertEqual(first_close.status_code, 200)

        second_close = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": 2.25})
        self.assertEqual(second_close.status_code, 409)
        self.assertIn("already closed", second_close.text)

    def test_manual_close_charges_both_spread_exit_legs(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        chain = self.bundle.tickers["AAA"].option_chain(scan_pick["expiry"]).calls
        short_contract = chain[chain["strike"] > scan_pick["strike"]].iloc[0]
        scan_pick.update(
            {
                "strategy_type": "vertical_spread",
                "short_strike": float(short_contract["strike"]),
                "short_contract_symbol": str(short_contract["contractSymbol"]),
            }
        )
        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position = create_response.json()["position"]
        self.assertEqual(position["entry_fee_total_usd"], commission_total_usd(contracts=1, sides=2))

        close_response = self.client.post(
            f"/api/positions/{position['id']}/close",
            json={"exit_price": 2.45},
        )

        self.assertEqual(close_response.status_code, 200)
        closed = close_response.json()["position"]
        self.assertEqual(closed["fee_total_usd"], commission_total_usd(contracts=1, sides=4))

    def test_create_position_allows_second_open_same_ticker_when_contract_differs(self):
        first_pick = build_tracked_position_scan_pick(self.bundle)
        first_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": first_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(first_response.status_code, 200)

        second_pick = build_tracked_position_scan_pick(self.bundle)
        chain = self.bundle.tickers["AAA"].option_chain(second_pick["expiry"]).calls
        alt_contract = chain[chain["contractSymbol"] != second_pick["contract_symbol"]].iloc[0]
        second_pick.update(
            {
                "strike": float(alt_contract["strike"]),
                "contract_symbol": str(alt_contract["contractSymbol"]),
                "selection_source": "live_chain_exact_contract",
                "contract_selection_source": "live_chain_exact_contract",
                "promotion_class": "promotable_exact_contract",
                "quote_time_et": "2026-04-06T10:00:00-04:00",
                "bid": float(alt_contract["bid"]),
                "ask": float(alt_contract["ask"]),
                "mid": round((float(alt_contract["bid"]) + float(alt_contract["ask"])) / 2, 2),
                "entry_execution_price": float(alt_contract["ask"]),
                "entry_execution_basis": "ask",
            }
        )

        second_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": second_pick,
                "fill_price": float(alt_contract["ask"]),
                "contracts": 1,
            },
        )

        self.assertEqual(second_response.status_code, 200)
        second_position = second_response.json()["position"]
        self.assertEqual(second_position["ticker"], "AAA")
        self.assertEqual(second_position["contract_symbol"], str(alt_contract["contractSymbol"]))

        list_open_response = self.client.get("/api/positions", params={"status": "open"})
        self.assertEqual(list_open_response.status_code, 200)
        self.assertEqual(len(list_open_response.json()["positions"]), 2)

    def test_create_position_stores_scan_provenance(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["source_scan_session_id"] = 55
        scan_pick["source_scan_event_key"] = "baseline_broad_control:rank_1"
        scan_pick["source_scan_run_id"] = "api_scan_20260406T100000Z"
        scan_pick["source_scan_recorded_at_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["backfill_audit_id"] = "main_lane_zero_pick_current_algo_v1"
        scan_pick["candidate_execution_label"] = "historical_selection"
        scan_pick["position_migration_id"] = "migration-55"
        scan_pick["pricing_evidence_class"] = "trusted_intraday"
        scan_pick["production_filter_action"] = "research_backfill"
        scan_pick["profitability_evidence_class"] = "research_backfill"
        scan_pick["research_only"] = True
        scan_pick["source_separation"] = "historical_replay"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["quote_time_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["mid"] = 4.5
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"
        scan_pick["entry_underlying_price"] = scan_pick["stock_price"]
        scan_pick["underlying_price_at_selection"] = scan_pick["stock_price"]
        scan_pick["current_spot"] = scan_pick["stock_price"]
        scan_pick["legs"] = [
            {
                "role": "long",
                "contract_symbol": scan_pick["contract_symbol"],
                "strike": scan_pick["strike"],
                "bid": 4.4,
                "ask": 4.6,
                "mid": 4.5,
            }
        ]

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position = create_response.json()["position"]
        self.assertEqual(position["source_scan_session_id"], 55)
        self.assertEqual(position["source_scan_event_key"], "baseline_broad_control:rank_1")
        self.assertEqual(position["source_scan_run_id"], "api_scan_20260406T100000Z")
        self.assertFalse(position["proof_eligible"])
        self.assertIn("source_scan_lineage_unverified", position["proof_ineligibility_reason"])
        self.assertEqual(position["proof_class"], "ineligible")
        self.assertIsNotNone(position["proof_class_reason"])
        self.assertEqual(position["source_pick_snapshot"]["quote_time_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(position["source_pick_snapshot"]["bid"], 4.4)
        self.assertEqual(position["source_pick_snapshot"]["ask"], 4.6)
        self.assertEqual(position["source_pick_snapshot"]["mid"], 4.5)
        self.assertEqual(position["source_pick_snapshot"]["entry_execution_price"], 4.5)
        self.assertEqual(position["source_pick_snapshot"]["entry_execution_basis"], "ask")
        self.assertFalse(position["source_pick_snapshot"]["source_scan_lineage_verified"])
        self.assertEqual(position["source_pick_snapshot"]["entry_underlying_price"], scan_pick["stock_price"])
        self.assertEqual(position["source_pick_snapshot"]["underlying_price_at_selection"], scan_pick["stock_price"])
        self.assertEqual(position["source_pick_snapshot"]["current_spot"], scan_pick["stock_price"])
        self.assertEqual(position["source_pick_snapshot"]["legs"], scan_pick["legs"])
        self.assertEqual(position["source_pick_snapshot"]["quote_time_utc"], "2026-04-06T14:00:00Z")
        self.assertIn("entry_quote_snapshot", position["source_pick_snapshot"])
        self.assertEqual(position["source_pick_snapshot"]["entry_quote_snapshot"]["captured_at_utc"], "2026-04-06T14:00:00Z")

        list_roundtrip_response = self.client.get("/api/positions", params={"status": "open"})
        self.assertEqual(list_roundtrip_response.status_code, 200)
        listed_position = list_roundtrip_response.json()["positions"][0]
        self.assertEqual(listed_position["source_pick_snapshot"]["quote_time_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(listed_position["source_pick_snapshot"]["entry_execution_price"], 4.5)
        self.assertEqual(listed_position["source_pick_snapshot"]["legs"], scan_pick["legs"])
        self.assertEqual(listed_position["source_pick_snapshot"]["entry_quote_snapshot"]["captured_at_utc"], "2026-04-06T14:00:00Z")

        compact_response = self.client.get("/api/positions", params={"status": "open", "compact": 1})
        self.assertEqual(compact_response.status_code, 200)
        compact_position = compact_response.json()["positions"][0]
        compact_snapshot = compact_position["source_pick_snapshot"]
        self.assertEqual(compact_snapshot["quote_time_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(compact_snapshot["entry_execution_price"], 4.5)
        self.assertEqual(compact_snapshot["entry_quote_snapshot"]["captured_at_utc"], "2026-04-06T14:00:00Z")
        self.assertNotIn("entry_execution_price", compact_snapshot["entry_quote_snapshot"])
        self.assertNotIn("quote_basis", compact_snapshot["entry_quote_snapshot"])
        self.assertNotIn("legs", compact_snapshot)
        self.assertNotIn("backfill_audit_id", compact_snapshot)
        self.assertNotIn("candidate_execution_label", compact_snapshot)
        self.assertNotIn("position_migration_id", compact_snapshot)
        self.assertNotIn("pricing_evidence_class", compact_snapshot)
        self.assertNotIn("profitability_evidence_class", compact_snapshot)
        self.assertNotIn("production_filter_action", compact_snapshot)
        self.assertNotIn("source_separation", compact_snapshot)
        self.assertEqual(compact_position["compact_evidence"], {"migrated_paper": True, "research_backfill": True})
        self.assertNotIn("share_review_age_minutes", compact_position)
        self.assertNotIn("share_reviewed_at", compact_position)

    def test_compact_closed_positions_omit_detail_only_fields(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["source_scan_event_key"] = "baseline_broad_control:rank_1"
        scan_pick["source_scan_run_id"] = "api_scan_20260406T100000Z"
        scan_pick["source_scan_recorded_at_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["quote_time_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"
        scan_pick["debit_pct_of_width"] = 45.0
        scan_pick["net_debit"] = 4.5
        scan_pick["spread_width"] = 10.0
        scan_pick["ret5"] = -3.25
        scan_pick["spread_liquidity"] = {
            "spread_entry_debit": 4.5,
            "spread_mid_debit": 4.0,
            "long_bid": 4.8,
            "long_ask": 5.2,
            "short_bid": 1.0,
            "short_ask": 1.4,
        }

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position_id = create_response.json()["position"]["id"]

        close_response = self.client.post(
            f"/api/positions/{position_id}/close",
            json={"exit_price": 2.45, "notes": "Closed from compact payload test. " + ("x" * 140)},
        )
        self.assertEqual(close_response.status_code, 200)
        closed_position = close_response.json()["position"]

        compact_response = self.client.get(
            "/api/positions",
            params={"status": "closed", "limit": 100, "offset": 0, "compact": 1},
        )
        self.assertEqual(compact_response.status_code, 200)
        compact_position = compact_response.json()["positions"][0]
        compact_snapshot = compact_position["source_pick_snapshot"]

        self.assertEqual(compact_position["status"], "closed")
        self.assertEqual(compact_position["exit_execution_price"], closed_position["exit_execution_price"])
        self.assertEqual(compact_position["net_pnl_pct"], closed_position["net_pnl_pct"])
        self.assertEqual(compact_position["source_pick_snapshot"]["quote_time_et"], "2026-04-06T10:00:00-04:00")
        self.assertEqual(compact_snapshot["debit_pct_of_width"], 45.0)
        self.assertEqual(compact_snapshot["spread_width"], 10.0)
        self.assertEqual(compact_snapshot["ret5"], -3.25)
        self.assertAlmostEqual(compact_snapshot["fill_degradation_vs_mid_pct"], 12.5)
        self.assertAlmostEqual(compact_snapshot["worst_leg_bid_ask_spread_pct"], 33.3333333333)
        self.assertLessEqual(len(compact_position["notes"]), 96)
        self.assertNotIn("latest_review", compact_position)
        self.assertNotIn("entry_quote_snapshot", compact_snapshot)
        self.assertNotIn("entry_execution_price", compact_snapshot)
        self.assertNotIn("contract_symbol", compact_snapshot)
        self.assertNotIn("selection_source", compact_snapshot)
        self.assertNotIn("promotion_class", compact_snapshot)
        self.assertNotIn("spread_liquidity", compact_snapshot)
        self.assertNotIn("created_at", compact_position)
        self.assertNotIn("updated_at", compact_position)
        self.assertNotIn("source_scan_event_key", compact_position)
        self.assertNotIn("source_scan_run_id", compact_position)
        self.assertNotIn("source_scan_recorded_at_utc", compact_position)
        self.assertNotIn("share_safe_reason", compact_position)
        self.assertNotIn("share_safe_exact_live", compact_position)
        self.assertNotIn("exact_contract_symbol", compact_position)

    def test_exact_looking_position_without_scan_provenance_is_not_live_scan_proof(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["quote_time_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"

        payload = psvc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.5,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            require_resolved_contract=True,
            preserve_fill_price=True,
        )

        self.assertFalse(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "ineligible")
        self.assertIn("source_scan_session_id", payload["proof_ineligibility_reason"])
        self.assertIn("source_scan_event_key", payload["proof_ineligibility_reason"])
        self.assertIn("source_scan_run_id", payload["proof_ineligibility_reason"])
        self.assertIn("source_scan_recorded_at_utc", payload["proof_ineligibility_reason"])
        self.assertIn("source_scan_lineage_unverified", payload["proof_ineligibility_reason"])

    def test_verified_scan_lineage_is_required_for_live_scan_proof(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["source_scan_session_id"] = 55
        scan_pick["source_scan_event_key"] = "baseline_broad_control:rank_1"
        scan_pick["source_scan_run_id"] = "api_scan_20260406T100000Z"
        scan_pick["source_scan_recorded_at_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["quote_time_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"

        payload = psvc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.5,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
            require_resolved_contract=True,
            preserve_fill_price=True,
            source_scan_lineage_verified=True,
        )

        self.assertTrue(payload["proof_eligible"])
        self.assertIsNone(payload["proof_ineligibility_reason"])
        self.assertEqual(payload["proof_class"], "live_scan_exact_contract")
        self.assertTrue(payload["source_pick_snapshot"]["source_scan_lineage_verified"])

    def test_research_backfill_marker_blocks_live_proof_even_with_exact_contract(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["quote_time_utc"] = "2026-04-06T14:00:00Z"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"
        scan_pick["backfill_audit_id"] = "main_lane_zero_pick_current_algo_v1"
        scan_pick["pricing_evidence_class"] = "research_backfill"

        payload = psvc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.50,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
        )

        self.assertFalse(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "ineligible")
        self.assertIn("research_backfill_not_live_proof", payload["proof_ineligibility_reason"])
        self.assertEqual(payload["source_pick_snapshot"]["proof_class"], "ineligible")
        self.assertIn("research_backfill_not_live_proof", payload["source_pick_snapshot"]["proof_class_reason"])

    def test_research_backfill_marker_takes_precedence_over_manual_exact(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"
        scan_pick["backfill_audit_id"] = "all_lanes_zero_pick_current_algo_v1"
        scan_pick["pricing_evidence_class"] = "research_backfill"

        payload = psvc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.75,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
        )

        self.assertFalse(payload["proof_eligible"])
        self.assertEqual(payload["proof_class"], "ineligible")
        self.assertIn("research_backfill_not_live_proof", payload["proof_ineligibility_reason"])
        self.assertNotEqual(payload["proof_class"], "manual_broker_exact_contract")

    def test_grouped_summary_excludes_stale_research_backfill_proof_flags(self):
        row = {
            "id": 99,
            "status": "closed",
            "proof_eligible": True,
            "proof_class": "live_scan_exact_contract",
            "net_pnl_pct": 25.0,
            "source_pick_snapshot": {
                "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
                "pricing_evidence_class": "research_backfill",
            },
        }

        grouped = self.backend._group_rows_by_status([row])

        self.assertEqual(grouped["summary"]["closed"]["tracked"]["count"], 1)
        self.assertEqual(grouped["summary"]["closed"]["proof"]["count"], 0)

    def test_create_position_without_provenance_marks_not_proof_eligible(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        # Exact contract is present, but scan/proof provenance is not.

        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        position = create_response.json()["position"]
        self.assertFalse(position["proof_eligible"])
        self.assertIsNotNone(position["proof_ineligibility_reason"])
        self.assertEqual(position["proof_class"], "manual_broker_exact_contract")
        self.assertIn("selection_source_not_exact", position["proof_ineligibility_reason"])

    def test_exact_contract_manual_fill_gets_separate_proof_class(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["selection_source"] = "live_chain_exact_contract"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00-04:00"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        scan_pick["entry_execution_basis"] = "ask"

        payload = psvc.build_position_payload(
            scan_pick=scan_pick,
            fill_price=4.75,
            contracts=1,
            filled_at="2026-04-06T10:00:00-04:00",
        )

        self.assertFalse(payload["proof_eligible"])
        self.assertIn("entry_execution_price_mismatch", payload["proof_ineligibility_reason"])
        self.assertIn("manual_fill_not_scan_execution", payload["proof_ineligibility_reason"])
        self.assertEqual(payload["proof_class"], "manual_broker_exact_contract")
        self.assertIn("manual/broker fill", payload["proof_class_reason"])

    def test_proof_lane_validation_blocks_missing_contract_symbol(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick.pop("contract_symbol", None)
        with self.assertRaises(ValueError) as ctx:
            psvc.build_position_payload(
                scan_pick=scan_pick,
                fill_price=4.50,
                contracts=1,
                require_proof_eligible=True,
            )
        self.assertIn("selection_source_not_exact", str(ctx.exception))

    def test_proof_lane_validation_blocks_non_exact_selection_source(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick["selection_source"] = "nearest_strike"
        scan_pick["promotion_class"] = "promotable_exact_contract"
        scan_pick["quote_time_et"] = "2026-04-06T10:00:00"
        scan_pick["bid"] = 4.4
        scan_pick["ask"] = 4.6
        scan_pick["entry_execution_price"] = 4.5
        with self.assertRaises(ValueError) as ctx:
            psvc.build_position_payload(
                scan_pick=scan_pick,
                fill_price=4.50,
                contracts=1,
                require_proof_eligible=True,
            )
        self.assertIn("selection_source", str(ctx.exception))

    def test_close_prefill_returns_review_exit_data(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_response = self.client.post(
            "/api/positions",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.50,
                "contracts": 1,
            },
        )
        position_id = create_response.json()["position"]["id"]

        self.client.post("/api/positions/review", json={})

        prefill_response = self.client.get(f"/api/positions/{position_id}/close-prefill")
        self.assertEqual(prefill_response.status_code, 200)
        prefill = prefill_response.json()
        self.assertEqual(prefill["position_id"], position_id)
        self.assertIn("exit_execution_price", prefill)
        self.assertIn("pricing_state", prefill)

    def test_positions_endpoints_return_clear_error_when_storage_missing(self):
        unavailable = UnavailableTrackedPositionsRepository("DATABASE_URL is not configured for tracked positions.")
        with patch.object(self.backend, "POSITIONS_REPOSITORY", unavailable):
            list_response = self.client.get("/api/positions", params={"status": "open"})
            self.assertEqual(list_response.status_code, 200)
            self.assertIn("error", list_response.json())

            create_response = self.client.post(
                "/api/positions",
                json={
                    "scan_pick": build_tracked_position_scan_pick(self.bundle),
                    "fill_price": 3.0,
                    "contracts": 1,
                },
            )
            self.assertEqual(create_response.status_code, 200)
            self.assertIn("error", create_response.json())


if __name__ == "__main__":
    unittest.main()
