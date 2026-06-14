from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import options_chatbot as oc
import wfo_optimizer as wfo


class StrategyProfileSafetyTests(unittest.TestCase):
    REQUIRED_SECTIONS = {"confidence_weights", "targets", "filters", "risk", "entry", "spread"}

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original_profiles = oc.get_strategy_profiles_snapshot()
        self.env_patch = patch.dict(os.environ, {"STRATEGY_PROFILE_DIR": self.tmp.name}, clear=False)
        self.env_patch.start()
        self.addCleanup(self._restore_profiles)
        oc.ensure_strategy_profiles_current(force=True)

    def _restore_profiles(self) -> None:
        self.env_patch.stop()
        with oc._STRATEGY_PROFILE_LOCK:
            oc._swap_strategy_profiles_unlocked(copy.deepcopy(self.original_profiles))
            oc._PROFILE_LOAD_FINGERPRINT = None
            oc._PROFILE_LOADED_SNAPSHOT = copy.deepcopy(self.original_profiles)
            oc._refresh_profile_file_aliases()

    def _assert_complete_profile_map(self, profiles: dict[str, dict]) -> None:
        self.assertEqual({"equity", "index"}, set(profiles))
        for profile_name, profile in profiles.items():
            missing = self.REQUIRED_SECTIONS - set(profile)
            self.assertFalse(missing, f"{profile_name} missing sections: {sorted(missing)}")
            for section in self.REQUIRED_SECTIONS:
                self.assertIsInstance(profile[section], dict, f"{profile_name}.{section}")

    def _write_profile_files(self, iteration: int) -> None:
        with oc._STRATEGY_PROFILE_LOCK:
            oc._refresh_profile_file_aliases()
            for profile_name, path_raw in oc.PROFILE_FILES.items():
                profile = copy.deepcopy(oc.DEFAULT_STRATEGY_PROFILES[profile_name])
                profile["risk"]["stop_loss_pct"] = 30.0 + (iteration % 10)
                profile["filters"]["vix_defense_threshold"] = 15.0 + (iteration % 5)
                path = Path(path_raw)
                tmp_path = path.with_suffix(path.suffix + f".{iteration}.tmp")
                tmp_path.write_text(json.dumps(profile), encoding="utf-8")
                os.replace(tmp_path, path)

    def test_reader_loop_sees_complete_profiles_during_background_refresh(self) -> None:
        self.assertNotIn("risk_settings", vars(oc))
        refresh_errors: list[BaseException] = []

        def refresh_loop() -> None:
            try:
                for iteration in range(60):
                    self._write_profile_files(iteration)
                    oc.ensure_strategy_profiles_current(force=True)
                    time.sleep(0.001)
            except BaseException as exc:
                refresh_errors.append(exc)

        thread = threading.Thread(target=refresh_loop, name="profile-refresh-test")
        thread.start()
        read_count = 0
        while thread.is_alive():
            profiles = oc.get_strategy_profiles_snapshot()
            self._assert_complete_profile_map(profiles)
            self._assert_complete_profile_map({"equity": oc.get_strategy_profile_snapshot("equity"), "index": oc.get_strategy_profile_snapshot("index")})
            self.assertIn("risk", oc._get_profile("AAPL"))
            read_count += 1
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertEqual([], refresh_errors)
        self.assertGreater(read_count, 0)
        self._assert_complete_profile_map(oc.get_strategy_profiles_snapshot())

    def test_wfo_profile_alias_tracks_profile_swaps(self) -> None:
        original = oc.get_strategy_profiles_snapshot()
        swapped = copy.deepcopy(original)
        swapped["equity"]["risk"]["stop_loss_pct"] = 37.0

        with oc._STRATEGY_PROFILE_LOCK:
            oc._swap_strategy_profiles_unlocked(swapped)

        self.assertIs(wfo.STRATEGY_PROFILES, oc.STRATEGY_PROFILES)
        self.assertIs(wfo.STRATEGY_PROFILE, oc.STRATEGY_PROFILE)
        self.assertEqual(wfo.STRATEGY_PROFILE["risk"]["stop_loss_pct"], 37.0)


if __name__ == "__main__":
    unittest.main()
