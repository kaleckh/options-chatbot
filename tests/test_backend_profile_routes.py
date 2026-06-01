from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from profile_routes import create_profile_router  # noqa: E402
from scripts.generate_route_parity import load_fastapi_routes  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from options_algorithm_fixtures import load_backend_main  # noqa: E402


class ProfileRoutesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved_calls: list[dict[str, str]] = []
        self.profiles = {
            "equity": {
                "risk": {"stop_loss_pct": 90.0},
                "entry": {"min_tech_score": 55.0},
            },
            "index": {
                "risk": {"stop_loss_pct": 90.0},
                "entry": {"min_tech_score": 50.0},
            },
        }
        self.changelog_path = Path(self.tmp.name) / "brain_changelog.json"
        self.changelog_path.write_text(
            json.dumps([{"profile": "equity", "note": "profile updated"}]),
            encoding="utf-8",
        )

        def save_profile(**kwargs):
            self.saved_calls.append({key: str(value) for key, value in kwargs.items()})

        app = FastAPI()
        app.include_router(
            create_profile_router(
                strategy_profiles=self.profiles,
                save_profile=save_profile,
                changelog_files={"equity": str(self.changelog_path)},
            )
        )
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_profile_router_reads_profiles_and_risk_settings(self):
        profile = self.client.get("/api/profile?type=equity")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["entry"]["min_tech_score"], 55.0)

        profiles = self.client.get("/api/profiles")
        self.assertEqual(profiles.status_code, 200)
        self.assertIn("index", profiles.json())

        risk = self.client.get("/api/risk")
        self.assertEqual(risk.status_code, 200)
        self.assertEqual(risk.json()["equity"]["stop_loss_pct"], 90.0)

    def test_profile_router_updates_known_sections_and_records_save(self):
        response = self.client.put(
            "/api/profile",
            json={
                "type": "equity",
                "updates": {
                    "entry": {"min_tech_score": 60.0},
                    "unknown": {"ignored": True},
                },
                "note": "tighten profile",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(self.profiles["equity"]["entry"]["min_tech_score"], 60.0)
        self.assertNotIn("unknown", self.profiles["equity"])
        self.assertEqual(self.saved_calls, [{"note": "tighten profile", "profile": "equity"}])

    def test_profile_router_rejects_unknown_profile_or_bad_updates(self):
        bad_profile = self.client.get("/api/profile?type=missing")
        self.assertEqual(bad_profile.status_code, 400)

        bad_updates = self.client.put("/api/profile", json={"updates": []})
        self.assertEqual(bad_updates.status_code, 400)

    def test_profile_router_reads_changelog_as_profile_artifact(self):
        response = self.client.get("/api/changelog?profile=equity")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["note"], "profile updated")

        missing = self.client.get("/api/changelog?profile=index")
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(missing.json(), [])


class BackendProfileRouterIntegrationTests(unittest.TestCase):
    def test_backend_main_mounts_profile_router(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = load_backend_main(str(Path(tmp) / "chat_history.db"))
            client = TestClient(backend.app)
            self.addCleanup(client.close)

            profile = client.get("/api/profile?type=equity")
            self.assertEqual(profile.status_code, 200)
            self.assertIn("risk", profile.json())

            profiles = client.get("/api/profiles")
            self.assertEqual(profiles.status_code, 200)
            self.assertIn("index", profiles.json())

            risk = client.get("/api/risk")
            self.assertEqual(risk.status_code, 200)
            self.assertIn("equity", risk.json())

    def test_route_parity_generator_sees_extracted_profile_router(self):
        routes = {(route.method, route.path) for route in load_fastapi_routes()}

        self.assertIn(("GET", "/api/profile"), routes)
        self.assertIn(("PUT", "/api/profile"), routes)
        self.assertIn(("GET", "/api/profiles"), routes)
        self.assertIn(("GET", "/api/changelog"), routes)
        self.assertIn(("GET", "/api/risk"), routes)


if __name__ == "__main__":
    unittest.main()
