from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from options_profit_state import (
    ensure_options_profit_state,
    list_candidate_manifests,
    load_incumbents_state,
    load_live_profile_state,
    load_profit_status,
)
from workspace_tempdir import WorkspaceTempDir


class OptionsProfitStateMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = WorkspaceTempDir(prefix="options-profit-state")
        self.addCleanup(self._tmp.cleanup)
        self.state_dir = Path(self._tmp.name) / "options_profit"
        self.manifest_path = Path(self._tmp.name) / "truth-first-champions.json"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(
            self.manifest_path,
            {
                "manifest_version": 1,
                "symbols": ["SPY", "QQQ"],
                "cohorts": [
                    {"id": "baseline_broad_control", "role": "control", "overrides": {}},
                    {"id": "broad_ev7", "role": "candidate", "overrides": {"filters": {"min_calibrated_expectancy_pct": 7.0}}},
                ],
            },
        )
        self.env = patch.dict(
            os.environ,
            {
                "OPTIONS_PROFIT_STATE_DIR": str(self.state_dir),
                "OPTIONS_PROFIT_CANDIDATE_MANIFEST": str(self.manifest_path),
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf8")

    def test_legacy_symbol_scoped_state_migrates_to_v2_side_state(self):
        self._write_json(
            self.state_dir / "live_profile.json",
            {
                "generated_at": "2026-04-01T00:00:00Z",
                "symbols": {
                    "SPY": {
                        "symbol": "SPY",
                        "candidate_id": "SPY__broad_ev7",
                        "cohort_id": "broad_ev7",
                        "base_profile": "index",
                        "overrides": {"entry": {"min_tech_score": 88.0}},
                        "source": "legacy_test",
                        "mode": "incumbent",
                        "status": "incumbent",
                    }
                },
            },
        )
        self._write_json(
            self.state_dir / "incumbents.json",
            {
                "generated_at": "2026-04-01T00:00:00Z",
                "symbols": {
                    "SPY": {
                        "symbol": "SPY",
                        "active": {
                            "symbol": "SPY",
                            "candidate_id": "SPY__broad_ev7",
                            "cohort_id": "broad_ev7",
                            "base_profile": "index",
                            "overrides": {"entry": {"min_tech_score": 88.0}},
                            "source": "legacy_test",
                            "mode": "incumbent",
                            "status": "incumbent",
                        },
                        "previous": None,
                        "canary": {
                            "symbol": "SPY",
                            "candidate_id": "SPY__broad_ev7",
                            "required_outcomes": 10,
                        },
                        "objective": {"objective_score": 1.25},
                    }
                },
                "current_canary": {"symbol": "SPY", "candidate_id": "SPY__broad_ev7"},
            },
        )
        self._write_json(
            self.state_dir / "status.json",
            {
                "generated_at": "2026-04-01T00:00:00Z",
                "active_incumbents": {
                    "SPY": {
                        "symbol": "SPY",
                        "candidate_id": "SPY__broad_ev7",
                        "cohort_id": "broad_ev7",
                        "base_profile": "index",
                        "overrides": {"entry": {"min_tech_score": 88.0}},
                        "source": "legacy_test",
                        "mode": "incumbent",
                        "status": "incumbent",
                    }
                },
                "current_canary": {"symbol": "SPY", "candidate_id": "SPY__broad_ev7"},
                "candidate_rankings": [
                    {
                        "candidate_id": "SPY__call__broad_ev7",
                        "symbol": "SPY",
                        "direction": "call",
                        "eligible": True,
                        "blockers": [],
                    }
                ],
                "last_decision": {"action": "no_op"},
                "blockers": [],
            },
        )

        ensure_options_profit_state()

        live_profile = load_live_profile_state(refresh=True)
        incumbents = load_incumbents_state()
        status = load_profit_status()

        self.assertEqual(live_profile["version"], 2)
        self.assertEqual(live_profile["symbols"]["SPY"]["call"]["candidate_id"], "SPY__call__broad_ev7")
        self.assertEqual(live_profile["symbols"]["SPY"]["put"]["candidate_id"], "SPY__put__broad_ev7")
        self.assertEqual(live_profile["symbols"]["SPY"]["call"]["overrides"]["entry"]["min_tech_score"], 88.0)
        self.assertEqual(live_profile["symbols"]["SPY"]["put"]["overrides"]["entry"]["min_tech_score"], 88.0)

        self.assertEqual(incumbents["version"], 2)
        self.assertEqual(incumbents["symbols"]["SPY"]["call"]["active"]["candidate_id"], "SPY__call__broad_ev7")
        self.assertEqual(incumbents["symbols"]["SPY"]["put"]["active"]["candidate_id"], "SPY__put__broad_ev7")
        self.assertIsNone(incumbents["symbols"]["SPY"]["call"]["canary"])
        self.assertIsNone(incumbents["symbols"]["SPY"]["put"]["canary"])
        self.assertIsNone(incumbents["symbols"]["SPY"]["call"]["objective"])
        self.assertIsNone(incumbents["symbols"]["SPY"]["put"]["objective"])

        self.assertEqual(status["version"], 2)
        self.assertEqual(status["active_incumbents"]["SPY"]["call"]["candidate_id"], "SPY__call__broad_ev7")
        self.assertEqual(status["active_incumbents"]["SPY"]["put"]["candidate_id"], "SPY__put__broad_ev7")
        self.assertIsNone(status["current_canary"]["SPY"]["call"])
        self.assertIsNone(status["current_canary"]["SPY"]["put"])
        self.assertEqual(status["candidate_rankings"][0]["direction"], "call")

        first_live = json.loads((self.state_dir / "live_profile.json").read_text(encoding="utf8"))
        first_incumbents = json.loads((self.state_dir / "incumbents.json").read_text(encoding="utf8"))
        first_status = json.loads((self.state_dir / "status.json").read_text(encoding="utf8"))

        ensure_options_profit_state()

        self.assertEqual(first_live, json.loads((self.state_dir / "live_profile.json").read_text(encoding="utf8")))
        self.assertEqual(first_incumbents, json.loads((self.state_dir / "incumbents.json").read_text(encoding="utf8")))
        self.assertEqual(first_status, json.loads((self.state_dir / "status.json").read_text(encoding="utf8")))

    def test_manifest_seeding_creates_side_specific_candidates_and_keeps_legacy_files_readable(self):
        legacy_candidate_path = self.state_dir / "candidates" / "SPY__legacy_candidate.json"
        self._write_json(
            legacy_candidate_path,
            {
                "candidate_id": "SPY__legacy_candidate",
                "symbol": "SPY",
                "base_profile": "index",
                "overrides": {"entry": {"min_tech_score": 77.0}},
                "status": "candidate",
            },
        )

        ensure_options_profit_state()
        candidate_ids = {str(item.get("candidate_id") or "") for item in list_candidate_manifests()}

        self.assertIn("SPY__legacy_candidate", candidate_ids)
        self.assertIn("SPY__call__baseline_broad_control", candidate_ids)
        self.assertIn("SPY__put__baseline_broad_control", candidate_ids)
        self.assertIn("QQQ__call__broad_ev7", candidate_ids)
        self.assertIn("QQQ__put__broad_ev7", candidate_ids)

    def test_manifest_directions_seed_only_requested_sides_for_challengers(self):
        self._write_json(
            self.manifest_path,
            {
                "manifest_version": 1,
                "symbols": ["SPY", "QQQ"],
                "cohorts": [
                    {"id": "baseline_broad_control", "role": "control", "overrides": {}},
                    {
                        "id": "broad_tech72",
                        "role": "candidate",
                        "overrides": {"entry": {"min_tech_score": 72.0}},
                        "directions": ["call"],
                    },
                ],
            },
        )

        ensure_options_profit_state()
        candidate_ids = {str(item.get("candidate_id") or "") for item in list_candidate_manifests()}

        self.assertIn("SPY__call__broad_tech72", candidate_ids)
        self.assertIn("QQQ__call__broad_tech72", candidate_ids)
        self.assertNotIn("SPY__put__broad_tech72", candidate_ids)
        self.assertNotIn("QQQ__put__broad_tech72", candidate_ids)


if __name__ == "__main__":
    unittest.main()
