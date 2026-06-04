from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main as backend  # noqa: E402


class BackendBridgeAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(backend.app)

    def test_backend_api_token_is_optional_for_local_default(self):
        with patch.dict(os.environ, {"OPTIONS_BACKEND_API_TOKEN": ""}, clear=False):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)

    def test_backend_api_token_blocks_direct_api_calls_when_configured(self):
        with patch.dict(os.environ, {"OPTIONS_BACKEND_API_TOKEN": "test-token"}, clear=False):
            missing = self.client.get("/api/health")
            wrong = self.client.get(
                "/api/health",
                headers={backend.BACKEND_API_TOKEN_HEADER: "wrong-token"},
            )
            allowed = self.client.get(
                "/api/health",
                headers={backend.BACKEND_API_TOKEN_HEADER: "test-token"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
