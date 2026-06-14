from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
BACKEND_MAIN = BACKEND_DIR / "main.py"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class BackendBridgeAuthTests(unittest.TestCase):
    def _load_backend(self, env: dict[str, str], argv: list[str] | None = None):
        module_name = f"backend_bridge_auth_{self._testMethodName}_{len(sys.modules)}"
        spec = importlib.util.spec_from_file_location(module_name, BACKEND_MAIN)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load backend module from {BACKEND_MAIN}")

        dotenv_module = types.ModuleType("dotenv")
        dotenv_module.load_dotenv = lambda *_args, **_kwargs: False
        module = importlib.util.module_from_spec(spec)
        default_env = {
            "DATABASE_URL": "",
            "OPTIONS_BACKEND_API_TOKEN": "",
            "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": "",
            "OPTIONS_ALLOW_MULTI_WORKER_BACKEND": "",
            "OPTIONS_BACKEND_WORKERS": "",
            "UVICORN_WORKERS": "",
            "WEB_CONCURRENCY": "",
        }
        default_env.update(env)
        argv_values = argv if argv is not None else ["uvicorn", "main:app"]

        had_dotenv = "dotenv" in sys.modules
        original_dotenv = sys.modules.get("dotenv")
        sys.modules["dotenv"] = dotenv_module
        try:
            with patch.dict(
                os.environ,
                default_env,
                clear=False,
            ), patch.object(sys, "argv", argv_values):
                sys.modules[module_name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(module_name, None)
                    raise
        finally:
            if had_dotenv:
                sys.modules["dotenv"] = original_dotenv
            else:
                sys.modules.pop("dotenv", None)
        self.addCleanup(lambda: sys.modules.pop(module_name, None))
        return module

    def test_backend_startup_requires_api_token_without_dev_opt_out(self):
        with self.assertRaisesRegex(RuntimeError, "OPTIONS_BACKEND_API_TOKEN is required"):
            self._load_backend(
                {
                    "OPTIONS_BACKEND_API_TOKEN": "",
                    "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": "",
                }
            )

    def test_backend_startup_allows_explicit_dev_opt_out(self):
        backend = self._load_backend(
            {
                "OPTIONS_BACKEND_API_TOKEN": "",
                "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": "1",
            }
        )
        client = TestClient(backend.app)
        self.addCleanup(client.close)

        with patch.dict(
            os.environ,
            {"OPTIONS_BACKEND_API_TOKEN": "", "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": "1"},
            clear=False,
        ):
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)

    def test_backend_startup_rejects_multi_worker_env(self):
        with self.assertRaisesRegex(RuntimeError, "must run with one worker"):
            self._load_backend(
                {
                    "OPTIONS_BACKEND_API_TOKEN": "test-token",
                    "WEB_CONCURRENCY": "2",
                }
            )

    def test_backend_startup_allows_single_worker_env(self):
        backend = self._load_backend(
            {
                "OPTIONS_BACKEND_API_TOKEN": "test-token",
                "UVICORN_WORKERS": "1",
            }
        )

        self.assertEqual(backend.app.title, "Options Chatbot Backend")

    def test_backend_startup_rejects_multi_worker_cli_flag(self):
        with self.assertRaisesRegex(RuntimeError, "must run with one worker"):
            self._load_backend(
                {"OPTIONS_BACKEND_API_TOKEN": "test-token"},
                argv=["uvicorn", "main:app", "--workers", "2"],
            )

    def test_backend_startup_allows_explicit_multi_worker_override(self):
        backend = self._load_backend(
            {
                "OPTIONS_BACKEND_API_TOKEN": "test-token",
                "OPTIONS_BACKEND_WORKERS": "2",
                "OPTIONS_ALLOW_MULTI_WORKER_BACKEND": "1",
            }
        )

        self.assertEqual(backend.app.title, "Options Chatbot Backend")

    def test_backend_api_token_blocks_direct_api_calls_when_configured(self):
        backend = self._load_backend(
            {
                "OPTIONS_BACKEND_API_TOKEN": "test-token",
                "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": "",
            }
        )
        client = TestClient(backend.app)
        self.addCleanup(client.close)

        with patch.dict(
            os.environ,
            {"OPTIONS_BACKEND_API_TOKEN": "test-token", "OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED": ""},
            clear=False,
        ):
            missing = client.get("/api/health")
            wrong = client.get(
                "/api/health",
                headers={backend.BACKEND_API_TOKEN_HEADER: "wrong-token"},
            )
            allowed = client.get(
                "/api/health",
                headers={backend.BACKEND_API_TOKEN_HEADER: "test-token"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    def test_dev_python_script_sets_backend_unauthenticated_opt_out(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        wrapper = (ROOT / "scripts" / "run_dev_python_backend.js").read_text(encoding="utf-8")

        self.assertIn("node scripts/run_dev_python_backend.js", package["scripts"]["dev"])
        self.assertIn("node scripts/run_dev_python_backend.js", package["scripts"]["dev:python"])
        self.assertIn("OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED", wrapper)
        self.assertIn('"1"', wrapper)


if __name__ == "__main__":
    unittest.main()
