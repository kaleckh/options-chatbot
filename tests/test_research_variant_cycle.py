import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import options_chatbot as oc
import scripts.run_research_variant_cycle as runner
import wfo_optimizer as wfo


class ResearchVariantCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.variant = self.root / "docs" / "autoresearch" / "variants" / "sample.json"
        self.variant.parent.mkdir(parents=True, exist_ok=True)
        self.variant.write_text(
            json.dumps(
                {
                    "profile_overrides": {
                        "equity": {
                            "risk": {"time_exit_pct": 33.0},
                            "early_exit": {"trailing_profit_pct": 25.0},
                        }
                    },
                    "ai_commodity_option_filter_overrides": {
                        "liquidity_spread_max_pct": 12.0,
                        "spread_liquidity_slippage_max_pct": 15.0,
                    },
                    "playbook_overrides": {
                        "ai_commodity_infra_observation": {
                            "entry_signal_id": "bullish_mean_reversion",
                            "allowed_signal_families": ["bullish_mean_reversion"],
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_variant_runner_applies_temporary_overrides_and_copies_config(self):
        original_time_exit = float(oc.STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"])
        original_liquidity_spread_max = float(oc.AI_COMMODITY_OPTION_FILTERS["liquidity_spread_max_pct"])
        original_entry_signal = wfo.REPLAY_PLAYBOOKS["ai_commodity_infra_observation"].get("entry_signal_id")

        def fake_cycle_main(argv, *, root_dir):
            self.assertEqual(float(oc.STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"]), 33.0)
            self.assertEqual(float(wfo.STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"]), 33.0)
            self.assertEqual(float(oc.STRATEGY_PROFILES["equity"]["early_exit"]["trailing_profit_pct"]), 25.0)
            self.assertEqual(float(oc.AI_COMMODITY_OPTION_FILTERS["liquidity_spread_max_pct"]), 12.0)
            self.assertEqual(
                float(oc.AI_COMMODITY_OPTION_FILTERS["spread_liquidity_slippage_max_pct"]),
                15.0,
            )
            self.assertEqual(
                wfo.REPLAY_PLAYBOOKS["ai_commodity_infra_observation"]["entry_signal_id"],
                "bullish_mean_reversion",
            )
            self.assertEqual(
                wfo.REPLAY_PLAYBOOKS["ai_commodity_infra_observation"]["allowed_signal_families"],
                ["bullish_mean_reversion"],
            )

            run_dir = root_dir / "research_runs" / "20260331_variant-test"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "manifest.json").write_text("{}", encoding="utf8")
            return 0

        with patch.object(runner.cycle, "main", side_effect=fake_cycle_main):
            code = runner.main(
                [
                    "--variant-config",
                    str(self.variant.relative_to(self.root)),
                    "--",
                    "--slug",
                    "variant-test",
                    "--proposal",
                    "docs/autoresearch/proposal.md",
                ],
                root_dir=self.root,
            )

        self.assertEqual(code, 0)
        self.assertEqual(float(oc.STRATEGY_PROFILES["equity"]["risk"]["time_exit_pct"]), original_time_exit)
        self.assertEqual(
            float(oc.AI_COMMODITY_OPTION_FILTERS["liquidity_spread_max_pct"]),
            original_liquidity_spread_max,
        )
        self.assertEqual(
            wfo.REPLAY_PLAYBOOKS["ai_commodity_infra_observation"].get("entry_signal_id"),
            original_entry_signal,
        )
        copied = self.root / "research_runs" / "20260331_variant-test" / "variant_config.json"
        self.assertTrue(copied.exists())
        payload = json.loads(copied.read_text(encoding="utf8"))
        self.assertEqual(payload["profile_overrides"]["equity"]["risk"]["time_exit_pct"], 33.0)
        manifest = json.loads((self.root / "research_runs" / "20260331_variant-test" / "manifest.json").read_text(encoding="utf8"))
        self.assertEqual(manifest["effective_override_diff"]["risk"]["time_exit_pct"], 33.0)
        self.assertEqual(manifest["ai_commodity_option_filter_overrides"]["liquidity_spread_max_pct"], 12.0)
        self.assertEqual(
            manifest["playbook_overrides"]["ai_commodity_infra_observation"]["entry_signal_id"],
            "bullish_mean_reversion",
        )

    def test_variant_runner_rejects_unknown_ai_commodity_option_filter_override(self):
        self.variant.write_text(
            json.dumps({"ai_commodity_option_filter_overrides": {"not_a_filter": 99.0}}),
            encoding="utf8",
        )

        with self.assertRaises(runner.VariantConfigError):
            runner.main(
                [
                    "--variant-config",
                    str(self.variant.relative_to(self.root)),
                    "--",
                    "--slug",
                    "bad-filter",
                ],
                root_dir=self.root,
            )

    def test_variant_runner_rejects_unknown_replay_playbook_override(self):
        self.variant.write_text(
            json.dumps({"playbook_overrides": {"not_a_playbook": {"entry_signal_id": "momentum"}}}),
            encoding="utf8",
        )

        with self.assertRaises(runner.VariantConfigError):
            runner.main(
                [
                    "--variant-config",
                    str(self.variant.relative_to(self.root)),
                    "--",
                    "--slug",
                    "bad-playbook",
                ],
                root_dir=self.root,
            )


if __name__ == "__main__":
    unittest.main()
