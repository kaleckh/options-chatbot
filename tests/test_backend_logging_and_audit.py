from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
TESTS_DIR = ROOT / "tests"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from logging_setup import configure_logging  # noqa: E402
from options_algorithm_fixtures import (  # noqa: E402
    build_options_algorithm_fixture_bundle,
    build_tracked_position_scan_pick,
    load_backend_main,
)


class BackendLoggingAndAuditTests(unittest.TestCase):
    def test_json_logging_formatter_emits_structured_stderr_payloads(self):
        stream = io.StringIO()
        logger = configure_logging(stream=stream, level="INFO", force=True)
        try:
            logger.info(
                "unit_request",
                extra={"structured": {"event": "unit", "method": "GET", "status": 200, "duration_ms": 1.25}},
            )
            payload = json.loads(stream.getvalue())
        finally:
            configure_logging(force=True)

        self.assertEqual(payload["message"], "unit_request")
        self.assertEqual(payload["event"], "unit")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["status"], 200)
        self.assertEqual(payload["duration_ms"], 1.25)
        self.assertEqual(payload["logger"], "options_backend")
        self.assertIn("ts", payload)

    def test_suggested_trade_create_appends_operator_mutation_ledger_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "chat_history.db")
            audit_dir = Path(tmpdir) / "operator-audit"
            backend = load_backend_main(db_path)
            backend.SUGGESTED_TRADES_REPOSITORY.init_schema()
            client = TestClient(backend.app)
            self.addCleanup(client.close)

            scan_pick = build_tracked_position_scan_pick(build_options_algorithm_fixture_bundle())
            with patch.dict(os.environ, {"OPTIONS_OPERATOR_AUDIT_DIR": str(audit_dir)}, clear=False):
                response = client.post(
                    "/api/suggested-trades",
                    headers={"x-trading-desk-mutation": "create_suggested_trade"},
                    json={
                        "creation_mode": "manual_paper",
                        "scan_pick": scan_pick,
                        "fill_price": 4.10,
                        "contracts": 1,
                    },
                )

            self.assertEqual(response.status_code, 200)
            audit_path = audit_dir / "mutations.jsonl"
            lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            trade = response.json()["trade"]
            self.assertEqual(payload["event"], "operator_mutation")
            self.assertEqual(payload["operation"], "create_suggested_trade")
            self.assertEqual(payload["store"], "sqlite_suggested_trades")
            self.assertEqual(payload["record_class"], "suggested_trade")
            self.assertEqual(payload["outcome"], "created")
            self.assertEqual(payload["mutation_intent_header"], "x-trading-desk-mutation")
            self.assertEqual(payload["mutation_intent"], "create_suggested_trade")
            self.assertEqual(payload["method"], "POST")
            self.assertEqual(payload["path"], "/api/suggested-trades")
            self.assertEqual(payload["record_ids"], [trade["id"]])
            self.assertEqual(payload["records"][0]["contract_symbol"], scan_pick["contract_symbol"])

    def test_backend_500_response_is_generic_when_internal_exception_is_logged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "chat_history.db")
            backend = load_backend_main(db_path)
            backend.SUGGESTED_TRADES_REPOSITORY.init_schema()
            client = TestClient(backend.app)
            self.addCleanup(client.close)

            with patch.object(
                backend.SUGGESTED_TRADES_REPOSITORY,
                "list_positions",
                side_effect=RuntimeError("secret backend failure"),
            ):
                response = client.get("/api/suggested-trades")

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Internal server error.")
        self.assertNotIn("secret backend failure", response.text)


if __name__ == "__main__":
    unittest.main()
