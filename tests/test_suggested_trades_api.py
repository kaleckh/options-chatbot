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


class SuggestedTradesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._backend_tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._backend_tmp.name, "chat_history.db")
        cls.backend = load_backend_main(db_path)
        cls.backend.SUGGESTED_TRADES_REPOSITORY.init_schema()
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

        with self.backend._db() as conn:
            conn.execute("DELETE FROM suggested_trade_reviews WHERE 1=1")
            conn.execute("DELETE FROM suggested_trades WHERE 1=1")

    def _cleanup(self):
        self.stack.close()

    def test_suggested_trades_workflow_create_list_review_and_close(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)

        create_response = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.10,
                "contracts": 1,
                "notes": "Paper-track this setup",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        trade = create_response.json()["trade"]
        self.assertEqual(trade["ticker"], scan_pick["ticker"])
        self.assertEqual(trade["entry_option_price"], 4.1)
        self.assertEqual(trade["contracts"], 1)
        self.assertEqual(trade["status"], "open")

        list_open_response = self.client.get("/api/suggested-trades", params={"status": "open"})
        self.assertEqual(list_open_response.status_code, 200)
        open_payload = list_open_response.json()
        self.assertEqual(len(open_payload["trades"]), 1)
        self.assertEqual(open_payload["trades"][0]["status"], "open")

        positions_response = self.client.get("/api/positions", params={"status": "open"})
        self.assertEqual(positions_response.status_code, 200)
        self.assertIn("error", positions_response.json())
        self.assertIn("DATABASE_URL", positions_response.json()["error"])

        review_response = self.client.post("/api/suggested-trades/review", json={})
        self.assertEqual(review_response.status_code, 200)
        reviewed = review_response.json()["trades"][0]
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

        close_response = self.client.post(
            f"/api/suggested-trades/{reviewed['id']}/close",
            json={"exit_price": 5.15, "notes": "Paper exit"},
        )
        self.assertEqual(close_response.status_code, 200)
        closed_trade = close_response.json()["trade"]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_option_price"], 5.15)
        self.assertEqual(closed_trade["exit_reason"], "manual_hypothetical_close")

        list_closed_response = self.client.get("/api/suggested-trades", params={"status": "closed"})
        self.assertEqual(list_closed_response.status_code, 200)
        closed_payload = list_closed_response.json()
        self.assertEqual(len(closed_payload["trades"]), 1)
        self.assertEqual(closed_payload["trades"][0]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
