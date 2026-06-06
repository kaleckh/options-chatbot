import copy
import gc
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

from options_execution import commission_total_usd


TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
BACKEND_DIR = ROOT / "python-backend"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import positions_service as psvc
from positions_repository import UnavailableTrackedPositionsRepository
from options_algorithm_fixtures import (
    FrozenDateTime,
    build_fresh_lane_gate_report,
    build_fresh_lane_promotion_report,
    build_fresh_open_risk_report,
    build_options_algorithm_fixture_bundle,
    build_scanner_origin_forward_event,
    build_scanner_origin_proof_scan_pick,
    build_tracked_position_scan_pick,
    load_backend_main,
)


class SuggestedTradesApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._backend_tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls._backend_tmp.name, "chat_history.db")
        cls.db_path = db_path
        cls.backend = load_backend_main(db_path)
        cls.backend.SUGGESTED_TRADES_REPOSITORY.init_schema()
        cls.client = TestClient(cls.backend.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.backend.SUGGESTED_TRADES_REPOSITORY = None
        gc.collect()
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
        self.stack.enter_context(patch.object(
            self.backend,
            "POSITIONS_REPOSITORY",
            UnavailableTrackedPositionsRepository("DATABASE_URL is not configured for tracked positions."),
        ))
        self.assertEqual(self.backend.DB_PATH, self.db_path)
        self.assertEqual(self.backend.SUGGESTED_TRADES_REPOSITORY.db_path, self.db_path)

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
        create_payload = create_response.json()
        self.assertNotIn("position_event_persistence", create_payload)
        trade = create_payload["trade"]
        self.assertEqual(trade["ticker"], scan_pick["ticker"])
        self.assertEqual(trade["contract_symbol"], scan_pick["contract_symbol"])
        self.assertEqual(trade["entry_option_price"], 4.1)
        self.assertEqual(trade["entry_execution_price"], 4.1)
        self.assertEqual(trade["entry_fee_total_usd"], commission_total_usd(contracts=1))
        self.assertEqual(trade["contracts"], 1)
        self.assertEqual(trade["status"], "open")

        list_open_response = self.client.get("/api/suggested-trades", params={"status": "open"})
        self.assertEqual(list_open_response.status_code, 200)
        self.assertGreaterEqual(float(list_open_response.headers["x-python-backend-duration-ms"]), 0.0)
        open_payload = list_open_response.json()
        self.assertEqual(len(open_payload["trades"]), 1)
        self.assertEqual(open_payload["trades"][0]["status"], "open")

        paged_open_response = self.client.get("/api/suggested-trades", params={"status": "open", "limit": 1})
        self.assertEqual(paged_open_response.status_code, 200)
        paged_open_payload = paged_open_response.json()
        self.assertEqual(len(paged_open_payload["trades"]), 1)
        self.assertEqual(paged_open_payload["page"], {"limit": 1, "offset": 0, "returned": 1})

        invalid_window_response = self.client.get("/api/suggested-trades", params={"status": "open", "offset": 1})
        self.assertEqual(invalid_window_response.status_code, 400)
        self.assertEqual(invalid_window_response.json()["detail"], "offset requires limit.")

        grouped_open_response = self.client.get("/api/suggested-trades", params={"status": "all", "grouped": 1})
        self.assertEqual(grouped_open_response.status_code, 200)
        grouped_open_payload = grouped_open_response.json()
        self.assertEqual(len(grouped_open_payload["open"]), 1)
        self.assertEqual(grouped_open_payload["closed"], [])

        positions_response = self.client.get("/api/positions", params={"status": "open"})
        self.assertEqual(positions_response.status_code, 200)
        self.assertIn("error", positions_response.json())
        self.assertIn("DATABASE_URL", positions_response.json()["error"])

        review_response = self.client.post("/api/suggested-trades/review", json={})
        self.assertEqual(review_response.status_code, 200)
        review_payload = review_response.json()
        self.assertNotIn("position_event_persistence", review_payload)
        reviewed = review_payload["trades"][0]
        self.assertTrue(
            {
                "id",
                "last_option_price",
                "last_pnl_pct",
                "last_recommendation",
                "last_recommendation_reason",
                "net_pnl_usd",
                "fee_total_usd",
                "latest_review",
            }.issubset(reviewed.keys())
        )
        self.assertIn(reviewed["last_recommendation"], {"HOLD", "SELL"})
        if reviewed["latest_review"]:
            self.assertIn("net_pnl_usd", reviewed["latest_review"])
            self.assertIn("fee_total_usd", reviewed["latest_review"])

        close_response = self.client.post(
            f"/api/suggested-trades/{reviewed['id']}/close",
            json={"exit_price": 5.15, "notes": "Paper exit"},
        )
        self.assertEqual(close_response.status_code, 200)
        close_payload = close_response.json()
        self.assertNotIn("position_event_persistence", close_payload)
        closed_trade = close_payload["trade"]
        self.assertEqual(closed_trade["status"], "closed")
        self.assertEqual(closed_trade["exit_option_price"], 5.15)
        self.assertEqual(closed_trade["exit_execution_price"], 5.15)
        self.assertEqual(closed_trade["exit_execution_basis"], "manual_close")
        self.assertEqual(closed_trade["exit_reason"], "manual_hypothetical_close")
        self.assertEqual(closed_trade["last_option_price"], 5.15)
        self.assertEqual(closed_trade["last_recommendation"], "SELL")
        self.assertEqual(closed_trade["latest_review"]["recommendation"], "SELL")
        self.assertEqual(closed_trade["latest_review"]["current_option_price"], 5.15)
        self.assertEqual(closed_trade["latest_review"]["current_pnl_pct"], closed_trade["gross_pnl_pct"])
        self.assertEqual(closed_trade["gross_pnl_usd"], 105.0)
        self.assertEqual(closed_trade["fee_total_usd"], commission_total_usd(contracts=1, sides=2))
        self.assertEqual(closed_trade["net_pnl_usd"], 103.7)

        list_closed_response = self.client.get("/api/suggested-trades", params={"status": "closed"})
        self.assertEqual(list_closed_response.status_code, 200)
        closed_payload = list_closed_response.json()
        self.assertEqual(len(closed_payload["trades"]), 1)
        self.assertEqual(closed_payload["trades"][0]["status"], "closed")

        grouped_closed_response = self.client.get("/api/suggested-trades", params={"status": "all", "grouped": 1})
        self.assertEqual(grouped_closed_response.status_code, 200)
        grouped_closed_payload = grouped_closed_response.json()
        self.assertEqual(grouped_closed_payload["open"], [])
        self.assertEqual(len(grouped_closed_payload["closed"]), 1)

        second_close_response = self.client.post(
            f"/api/suggested-trades/{reviewed['id']}/close",
            json={"exit_price": 6.0, "notes": "Should not overwrite"},
        )
        self.assertEqual(second_close_response.status_code, 400)

        unchanged_response = self.client.get("/api/suggested-trades", params={"status": "closed"})
        unchanged_trade = unchanged_response.json()["trades"][0]
        self.assertEqual(unchanged_trade["exit_option_price"], 5.15)
        self.assertEqual(unchanged_trade["last_option_price"], 5.15)

    def test_review_rejects_bool_position_ids(self):
        response = self.client.post("/api/suggested-trades/review", json={"position_ids": [True]})

        self.assertEqual(response.status_code, 400)
        self.assertIn("position_ids must be a list of positive integers", response.json()["detail"])

    def test_create_scanner_origin_suggested_trade_rejects_caps_off_source_scan(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick.update(
            {
                "guardrail_decision": "clear",
                "portfolio_caps_enforced": False,
                "creation_blockers": ["portfolio_caps_not_enforced"],
                "source_scan_session_id": 123,
                "source_scan_event_key": "rank_1",
                "source_scan_run_id": "scan:test",
                "source_scan_recorded_at_utc": "2026-04-14T15:00:00Z",
            }
        )

        with patch.object(self.backend, "_verify_source_scan_lineage", return_value=True):
            response = self.client.post(
                "/api/suggested-trades",
                json={
                    "creation_mode": "scanner",
                    "scan_pick": scan_pick,
                    "fill_price": 4.10,
                    "contracts": 1,
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("portfolio_caps_not_enforced", str(response.json()["detail"]))

    def test_create_scanner_origin_suggested_trade_rejects_ineligible_current_rerun(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick.update(
            {
                "guardrail_decision": "clear",
                "portfolio_caps_enforced": True,
                "creation_eligible": True,
                "creation_blockers": [],
                "candidate_execution_label": "executable_opra_paper_candidate",
                "source_scan_session_id": 123,
                "source_scan_event_key": "rank_1",
                "source_scan_run_id": "scan:test",
                "source_scan_recorded_at_utc": "2026-04-14T15:00:00Z",
            }
        )

        with (
            patch.object(self.backend, "_verify_source_scan_lineage", return_value=True),
            patch.object(
                self.backend,
                "apply_playbook_guardrails",
                return_value={
                    "ranked_picks": [
                        {
                            **scan_pick,
                            "guardrail_decision": "clear",
                            "portfolio_caps_enforced": True,
                            "creation_eligible": False,
                            "creation_blockers": ["candidate_execution_label:fallback_delayed"],
                            "candidate_execution_label": "fallback_delayed",
                        }
                    ]
                },
            ),
        ):
            response = self.client.post(
                "/api/suggested-trades",
                json={
                    "creation_mode": "scanner",
                    "scan_pick": scan_pick,
                    "fill_price": 4.10,
                    "contracts": 1,
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("candidate_execution_label:fallback_delayed", str(response.json()["detail"]))

    def test_create_scanner_origin_suggested_trade_accepts_matching_archived_lineage(self):
        scan_pick = build_scanner_origin_proof_scan_pick(self.bundle)
        archived_event = build_scanner_origin_forward_event(scan_pick)
        playbook_id = scan_pick.get("playbook_id") or "short_term"

        with (
            patch.object(self.backend, "list_forward_scan_pick_events", return_value=[archived_event]),
            patch.object(
                self.backend,
                "apply_playbook_guardrails",
                return_value={"ranked_picks": [dict(scan_pick)]},
            ),
            patch(
                "scripts.lane_profitability_gate.load_lane_gate_report",
                return_value=build_fresh_lane_gate_report(playbook_id),
            ),
            patch(
                "scripts.lane_promotion_state.load_lane_promotion_report",
                return_value=build_fresh_lane_promotion_report(playbook_id),
            ),
            patch(
                "scripts.regular_open_risk_governor.load_regular_open_risk_report",
                return_value=build_fresh_open_risk_report(),
            ),
        ):
            response = self.client.post(
                "/api/suggested-trades",
                json={
                    "creation_mode": "scanner",
                    "scan_pick": scan_pick,
                    "fill_price": scan_pick["entry_execution_price"],
                    "contracts": 1,
                },
            )

        self.assertEqual(response.status_code, 200)
        trade = response.json()["trade"]
        self.assertEqual(trade["ticker"], scan_pick["ticker"])
        self.assertEqual(trade["contract_symbol"], scan_pick["contract_symbol"])
        self.assertTrue(trade["source_pick_snapshot"]["source_scan_lineage_verified"])
        self.assertEqual(
            trade["source_pick_snapshot"]["source_scan_event_key"],
            scan_pick["source_scan_event_key"],
        )

    def test_create_scanner_origin_suggested_trade_rejects_paper_probation_lane(self):
        scan_pick = build_scanner_origin_proof_scan_pick(self.bundle)
        archived_event = build_scanner_origin_forward_event(scan_pick)
        playbook_id = scan_pick.get("playbook_id") or "short_term"

        with (
            patch.object(self.backend, "list_forward_scan_pick_events", return_value=[archived_event]),
            patch.object(
                self.backend,
                "apply_playbook_guardrails",
                return_value={"ranked_picks": [dict(scan_pick)]},
            ),
            patch(
                "scripts.lane_profitability_gate.load_lane_gate_report",
                return_value=build_fresh_lane_gate_report(playbook_id),
            ),
            patch(
                "scripts.lane_promotion_state.load_lane_promotion_report",
                return_value=build_fresh_lane_promotion_report(playbook_id, promotion_state="paper_probation"),
            ),
            patch(
                "scripts.regular_open_risk_governor.load_regular_open_risk_report",
                return_value=build_fresh_open_risk_report(),
            ),
        ):
            response = self.client.post(
                "/api/suggested-trades",
                json={
                    "creation_mode": "scanner",
                    "scan_pick": scan_pick,
                    "fill_price": scan_pick["entry_execution_price"],
                    "contracts": 1,
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("lane_promotion_state", str(response.json()["detail"]))

    def test_create_scanner_origin_suggested_trade_rejects_mutated_archived_lineage_fields(self):
        baseline_pick = build_scanner_origin_proof_scan_pick(self.bundle)
        archived_event = build_scanner_origin_forward_event(baseline_pick)

        mutations = {
            "source_scan_run_id": lambda pick: pick.update({"source_scan_run_id": "api_scan_tampered"}),
            "contract_symbol": lambda pick: pick.update({"contract_symbol": "AAA260408C99999999"}),
            "entry_execution_price": lambda pick: pick.update({"entry_execution_price": 4.75}),
            "options_data_source": lambda pick: pick.update({"options_data_source": "delayed_vendor"}),
            "creation_eligible": lambda pick: pick.update({"creation_eligible": False}),
        }

        with patch.object(self.backend, "list_forward_scan_pick_events", return_value=[archived_event]):
            self.assertTrue(self.backend._verify_source_scan_lineage(baseline_pick))

        for field, mutate in mutations.items():
            with self.subTest(field=field):
                scan_pick = copy.deepcopy(baseline_pick)
                mutate(scan_pick)
                before_count = len(self.backend.SUGGESTED_TRADES_REPOSITORY.list_positions("open"))

                with (
                    patch.object(self.backend, "list_forward_scan_pick_events", return_value=[archived_event]),
                    patch.object(
                        self.backend,
                        "apply_playbook_guardrails",
                        return_value={"ranked_picks": [dict(scan_pick)]},
                    ),
                ):
                    response = self.client.post(
                        "/api/suggested-trades",
                        json={
                            "creation_mode": "scanner",
                            "scan_pick": scan_pick,
                            "fill_price": scan_pick["entry_execution_price"],
                            "contracts": 1,
                        },
                    )

                self.assertEqual(response.status_code, 409)
                self.assertIn("source_scan_lineage_unverified", str(response.json()["detail"]))
                after_count = len(self.backend.SUGGESTED_TRADES_REPOSITORY.list_positions("open"))
                self.assertEqual(after_count, before_count)

    def test_create_and_close_reject_json_booleans_as_numbers(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)

        bool_fill = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": True,
                "contracts": 1,
            },
        )
        self.assertEqual(bool_fill.status_code, 400)
        self.assertIn("fill_price", bool_fill.text)

        bool_contracts = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.10,
                "contracts": True,
            },
        )
        self.assertEqual(bool_contracts.status_code, 400)
        self.assertIn("contracts", bool_contracts.text)

        create_response = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.10,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        trade_id = create_response.json()["trade"]["id"]

        bool_exit = self.client.post(f"/api/suggested-trades/{trade_id}/close", json={"exit_price": True})
        self.assertEqual(bool_exit.status_code, 400)
        self.assertIn("exit_price", bool_exit.text)

    def test_create_rejects_bool_scan_pick_numeric_fields(self):
        for field in ("strike", "stop_loss_pct", "profit_target_pct", "time_exit_day"):
            with self.subTest(field=field):
                scan_pick = build_tracked_position_scan_pick(self.bundle)
                scan_pick[field] = True
                response = self.client.post(
                    "/api/suggested-trades",
                    json={
                        "scan_pick": scan_pick,
                        "fill_price": 4.10,
                        "contracts": 1,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.text)

    def test_create_rejects_non_object_scan_pick_and_invalid_text_fields(self):
        for scan_pick in ([1], True, "not-an-object"):
            with self.subTest(scan_pick=scan_pick):
                response = self.client.post(
                    "/api/suggested-trades",
                    json={"scan_pick": scan_pick, "fill_price": 4.10, "contracts": 1},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("scan_pick", response.text)

        scan_pick = build_tracked_position_scan_pick(self.bundle)
        scan_pick.update(
            {
                "selection_source": "live_chain_exact_contract",
                "contract_selection_source": "live_chain_exact_contract",
                "quote_time_et": "2026-04-06T10:00:00-04:00",
                "bid": 4.0,
                "ask": 4.1,
                "entry_execution_price": 4.1,
                "entry_execution_basis": "ask",
                "contract_symbol": True,
                "options_data_source": "alpaca_opra",
            }
        )
        bool_contract = self.client.post(
            "/api/suggested-trades",
            json={"scan_pick": scan_pick, "fill_price": 4.10, "contracts": 1},
        )
        self.assertEqual(bool_contract.status_code, 400)
        self.assertIn("contract_symbol", bool_contract.text)

        bad_notes = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": build_tracked_position_scan_pick(self.bundle),
                "fill_price": 4.10,
                "contracts": 1,
                "notes": {"not": "text"},
            },
        )
        self.assertEqual(bad_notes.status_code, 400)
        self.assertIn("notes", bad_notes.text)

    def test_create_and_close_reject_malformed_timestamps(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_bad_time = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.10,
                "contracts": 1,
                "filled_at": True,
            },
        )
        self.assertEqual(create_bad_time.status_code, 400)
        self.assertIn("filled_at", create_bad_time.text)

        create_response = self.client.post(
            "/api/suggested-trades",
            json={
                "scan_pick": scan_pick,
                "fill_price": 4.10,
                "contracts": 1,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        trade_id = create_response.json()["trade"]["id"]

        close_bad_time = self.client.post(
            f"/api/suggested-trades/{trade_id}/close",
            json={"exit_price": 1.0, "closed_at": True},
        )
        self.assertEqual(close_bad_time.status_code, 400)
        self.assertIn("closed_at", close_bad_time.text)

    def test_close_allows_zero_exit_but_rejects_negative_exit(self):
        scan_pick = build_tracked_position_scan_pick(self.bundle)
        create_negative = self.client.post(
            "/api/suggested-trades",
            json={"scan_pick": scan_pick, "fill_price": 4.10, "contracts": 1},
        )
        self.assertEqual(create_negative.status_code, 200)
        negative_trade_id = create_negative.json()["trade"]["id"]
        negative_response = self.client.post(
            f"/api/suggested-trades/{negative_trade_id}/close",
            json={"exit_price": -0.01},
        )
        self.assertEqual(negative_response.status_code, 400)
        self.assertIn("exit_price", negative_response.text)

        create_zero = self.client.post(
            "/api/suggested-trades",
            json={"scan_pick": scan_pick, "fill_price": 4.10, "contracts": 1},
        )
        self.assertEqual(create_zero.status_code, 200)
        zero_trade_id = create_zero.json()["trade"]["id"]
        zero_response = self.client.post(
            f"/api/suggested-trades/{zero_trade_id}/close",
            json={"exit_price": 0},
        )
        self.assertEqual(zero_response.status_code, 200)
        self.assertEqual(zero_response.json()["trade"]["exit_option_price"], 0.0)


if __name__ == "__main__":
    unittest.main()
