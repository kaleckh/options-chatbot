import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import options_chatbot as oc
import wfo_optimizer as wfo


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
        self.bundle = build_options_algorithm_fixture_bundle()
        self.stack = ExitStack()
        self.addCleanup(self._cleanup)

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

    def _cleanup(self):
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

        grouped_open_response = self.client.get("/api/positions", params={"status": "all", "grouped": 1})
        self.assertEqual(grouped_open_response.status_code, 200)
        grouped_open_payload = grouped_open_response.json()
        self.assertEqual(len(grouped_open_payload["open"]), 1)
        self.assertEqual(grouped_open_payload["closed"], [])

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

    def test_close_rejects_non_positive_exit_price(self):
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

        response = self.client.post(f"/api/positions/{position_id}/close", json={"exit_price": 0})
        self.assertEqual(response.status_code, 400)
        self.assertIn("exit_price", response.text)

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
