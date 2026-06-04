from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend_route_context import BackendRouteContext  # noqa: E402
from predictions_routes import create_predictions_router  # noqa: E402
from scripts.generate_route_parity import load_fastapi_routes  # noqa: E402
from tools_routes import create_tools_router  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from options_algorithm_fixtures import load_backend_main  # noqa: E402


async def _run_in_worker(fn, /, *args, **kwargs):
    return fn(*args, **kwargs)


class BackendSupportRouteFactoryTests(unittest.TestCase):
    def setUp(self):
        self.predictions = [{"id": 1, "ticker": "SPY"}]
        self.log_calls: list[dict[str, object]] = []

        def log_prediction(**kwargs):
            self.log_calls.append(dict(kwargs))
            return json.dumps({"ok": True, "kwargs": kwargs})

        self.namespace = {
            "_load_predictions": lambda: list(self.predictions),
            "log_prediction": log_prediction,
            "TOOL_DISPATCH": {
                "json_tool": lambda: json.dumps({"ok": True}),
                "plain_tool": lambda: "plain text",
            },
            "_run_in_worker": _run_in_worker,
        }
        app = FastAPI()
        ctx = BackendRouteContext(self.namespace)
        app.include_router(create_predictions_router(ctx))
        app.include_router(create_tools_router(ctx))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_predictions_router_reads_grades_and_deletes(self):
        response = self.client.get("/api/predictions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.predictions)

        grade_response = self.client.post(
            "/api/predictions/grade",
            json={"scan_date": "2026-06-04"},
        )
        self.assertEqual(grade_response.status_code, 200)
        self.assertEqual(self.log_calls[-1], {"action": "grade", "scan_date": "2026-06-04"})

        delete_response = self.client.delete("/api/predictions/12")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(self.log_calls[-1], {"action": "delete", "prediction_id": 12})

    def test_tools_router_decodes_json_and_preserves_plain_text(self):
        json_response = self.client.post("/api/tools/json_tool")
        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.json(), {"result": {"ok": True}})

        plain_response = self.client.post("/api/tools/plain_tool", json={})
        self.assertEqual(plain_response.status_code, 200)
        self.assertEqual(plain_response.json(), {"result": "plain text"})

        missing_response = self.client.post("/api/tools/missing_tool", json={})
        self.assertEqual(missing_response.status_code, 404)


class BackendSupportRouterIntegrationTests(unittest.TestCase):
    def test_backend_main_support_routers_use_late_bound_globals(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = load_backend_main(str(Path(tmp) / "chat_history.db"))
            client = TestClient(backend.app)
            self.addCleanup(client.close)

            with patch.object(backend, "_load_predictions", return_value=[{"id": "patched"}]):
                predictions = client.get("/api/predictions")
            self.assertEqual(predictions.status_code, 200)
            self.assertEqual(predictions.json(), [{"id": "patched"}])

            with patch.object(
                backend,
                "TOOL_DISPATCH",
                {"fixture_tool": lambda value="ok": json.dumps({"value": value})},
            ):
                tool_response = client.post("/api/tools/fixture_tool", json={"value": "patched"})
            self.assertEqual(tool_response.status_code, 200)
            self.assertEqual(tool_response.json(), {"result": {"value": "patched"}})

    def test_route_parity_generator_sees_extracted_support_routers(self):
        routes = {(route.method, route.path) for route in load_fastapi_routes()}

        self.assertIn(("GET", "/api/predictions"), routes)
        self.assertIn(("POST", "/api/predictions/grade"), routes)
        self.assertIn(("DELETE", "/api/predictions/{pred_id}"), routes)
        self.assertIn(("POST", "/api/tools/{tool_name}"), routes)

    def test_extracted_support_routers_do_not_import_main(self):
        for route_file in ("predictions_routes.py", "tools_routes.py"):
            source = (BACKEND_DIR / route_file).read_text(encoding="utf-8")
            self.assertNotIn("import main", source)


if __name__ == "__main__":
    unittest.main()
