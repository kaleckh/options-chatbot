import json
import tempfile
import unittest
from pathlib import Path

import experiment_scoreboard as scoreboard


def _fake_result(
    *,
    playbook: str,
    pricing_lane: str,
    truth_source: str = "synthetic_research",
    quote_coverage_pct: float = 100.0,
    lookback_years: int = 2,
    n_picks: int = 1,
    iv_adj: float = 1.2,
    total_trades: int = 24,
    profit_factor: float = 1.1,
    avg_pnl_pct: float = 4.0,
    win_rate_pct: float = 55.0,
    directional_accuracy_pct: float = 56.0,
    selection_source_counts: dict | None = None,
    run_at: str = "2026-03-30T14:00:00",
) -> dict:
    return {
        "run_at": run_at,
        "mode": "backtest",
        "profile": "mixed",
        "lookback_years": lookback_years,
        "iv_adj": iv_adj,
        "pricing_lane": pricing_lane,
        "playbook": playbook,
        "truth_source": truth_source,
        "quote_coverage_pct": quote_coverage_pct,
        "n_picks": n_picks,
        "total_trades": total_trades,
        "profit_factor": profit_factor,
        "avg_pnl_pct": avg_pnl_pct,
        "win_rate_pct": win_rate_pct,
        "directional_accuracy_pct": directional_accuracy_pct,
        "selection_source_counts": selection_source_counts or {"replay_calibrated": total_trades},
        "trades": [],
    }


def _stability_builder_factory(status_by_lane: dict[str, str]):
    def _builder(*, result, **_kwargs):
        lane = str(result.get("pricing_lane"))
        return {
            "overall_status": status_by_lane.get(lane, "watch"),
            "rolling_summary": {
                "pass_rate_pct": 75.0 if status_by_lane.get(lane) == "promote" else 55.0,
                "worst_profit_factor": 1.0 if status_by_lane.get(lane) != "block" else 0.7,
            },
            "recommendations": [f"{lane} status: {status_by_lane.get(lane, 'watch')}"],
        }

    return _builder


class ExperimentScoreboardTests(unittest.TestCase):
    def test_pairs_mid_and_pessimistic_variants_and_tracks_degradation(self):
        entries = [
            {"path": "mid.json", "path_label": "mid", "run_at": "2026-03-30T14:00:00", "result": _fake_result(playbook="broad", pricing_lane="mid", profit_factor=1.42, avg_pnl_pct=12.0)},
            {"path": "pess.json", "path_label": "pess", "run_at": "2026-03-30T14:05:00", "result": _fake_result(playbook="broad", pricing_lane="pessimistic", profit_factor=1.08, avg_pnl_pct=6.5)},
        ]

        report = scoreboard.build_replay_scoreboard(
            entries=entries,
            min_trades=20,
            stability_builder=_stability_builder_factory({"mid": "watch", "pessimistic": "watch"}),
        )

        self.assertEqual(report["summary"]["variants_ranked"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["anchor_lane"], "pessimistic")
        self.assertAlmostEqual(candidate["fill_degradation"]["profit_factor_drop"], 0.34, places=2)
        self.assertAlmostEqual(candidate["fill_degradation"]["avg_pnl_pct_drop"], 5.5, places=2)

    def test_bootstrap_heavy_variant_blocks_even_if_stability_is_watch(self):
        entries = [
            {"path": "mid.json", "path_label": "mid", "run_at": "2026-03-30T14:00:00", "result": _fake_result(playbook="bearish_defensive", pricing_lane="mid", selection_source_counts={"bootstrap_heuristic": 30}, total_trades=30)},
            {"path": "pess.json", "path_label": "pess", "run_at": "2026-03-30T14:05:00", "result": _fake_result(playbook="bearish_defensive", pricing_lane="pessimistic", selection_source_counts={"bootstrap_heuristic": 30}, total_trades=30)},
        ]

        report = scoreboard.build_replay_scoreboard(
            entries=entries,
            min_trades=20,
            stability_builder=_stability_builder_factory({"mid": "watch", "pessimistic": "watch"}),
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["scoreboard_status"], "block")
        self.assertTrue(any("Bootstrap share" in reason for reason in candidate["verdict_reasons"]))

    def test_ranks_promote_above_watch_above_block(self):
        entries = [
            {"path": "promote_imported.json", "path_label": "promote_imported", "run_at": "2026-03-30T14:00:00", "result": _fake_result(playbook="promote_playbook", pricing_lane="historical_imported", truth_source="historical_imported", quote_coverage_pct=92.0, profit_factor=1.2, avg_pnl_pct=7.0)},
            {"path": "promote_mid.json", "path_label": "promote_mid", "run_at": "2026-03-30T14:01:00", "result": _fake_result(playbook="promote_playbook", pricing_lane="mid", profit_factor=1.35, avg_pnl_pct=9.0)},
            {"path": "promote_pess.json", "path_label": "promote_pess", "run_at": "2026-03-30T14:05:00", "result": _fake_result(playbook="promote_playbook", pricing_lane="pessimistic", profit_factor=1.2, avg_pnl_pct=7.0)},
            {"path": "watch_mid.json", "path_label": "watch_mid", "run_at": "2026-03-30T14:10:00", "result": _fake_result(playbook="watch_playbook", pricing_lane="mid", profit_factor=1.15, avg_pnl_pct=4.0)},
            {"path": "watch_pess.json", "path_label": "watch_pess", "run_at": "2026-03-30T14:15:00", "result": _fake_result(playbook="watch_playbook", pricing_lane="pessimistic", profit_factor=1.01, avg_pnl_pct=1.5)},
            {"path": "block_mid.json", "path_label": "block_mid", "run_at": "2026-03-30T14:20:00", "result": _fake_result(playbook="block_playbook", pricing_lane="mid", total_trades=10, profit_factor=1.3, avg_pnl_pct=8.0, selection_source_counts={"bootstrap_heuristic": 10})},
            {"path": "block_pess.json", "path_label": "block_pess", "run_at": "2026-03-30T14:25:00", "result": _fake_result(playbook="block_playbook", pricing_lane="pessimistic", total_trades=10, profit_factor=0.9, avg_pnl_pct=-2.0, selection_source_counts={"bootstrap_heuristic": 10})},
        ]

        report = scoreboard.build_replay_scoreboard(
            entries=entries,
            min_trades=20,
            stability_builder=_stability_builder_factory(
                {"historical_imported": "promote", "mid": "promote", "pessimistic": "promote"}
            ),
        )

        statuses = [item["scoreboard_status"] for item in report["candidates"]]
        self.assertEqual(statuses[0], "promote")
        self.assertIn("watch", statuses)
        self.assertEqual(statuses[-1], "block")

    def test_load_cached_backtest_entries_filters_non_backtest_json_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            backtest_path = root / "variant.json"
            unrelated_path = root / "notes.json"
            backtest_path.write_text(json.dumps(_fake_result(playbook="broad", pricing_lane="mid")), encoding="utf8")
            unrelated_path.write_text(json.dumps({"hello": "world"}), encoding="utf8")

            entries = scoreboard.load_cached_backtest_entries([root])

        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["path"].endswith("variant.json"))

    def test_load_cached_backtest_entries_sorts_mixed_timezone_run_at_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            naive_path = root / "naive.json"
            aware_path = root / "aware.json"
            naive_path.write_text(
                json.dumps(_fake_result(playbook="broad", pricing_lane="mid", run_at="2026-03-30T14:00:00")),
                encoding="utf8",
            )
            aware_path.write_text(
                json.dumps(_fake_result(playbook="broad", pricing_lane="pessimistic", run_at="2026-03-30T14:01:00Z")),
                encoding="utf8",
            )

            entries = scoreboard.load_cached_backtest_entries([root])

        self.assertEqual([Path(entry["path"]).name for entry in entries], ["naive.json", "aware.json"])

    def test_load_cached_backtest_entries_sorts_invalid_run_at_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing_path = root / "missing.json"
            aware_path = root / "aware.json"
            missing_path.write_text(
                json.dumps(_fake_result(playbook="broad", pricing_lane="mid", run_at="not-a-date")),
                encoding="utf8",
            )
            aware_path.write_text(
                json.dumps(_fake_result(playbook="broad", pricing_lane="pessimistic", run_at="2026-03-30T14:01:00Z")),
                encoding="utf8",
            )

            entries = scoreboard.load_cached_backtest_entries([root])

        self.assertEqual([Path(entry["path"]).name for entry in entries], ["missing.json", "aware.json"])

    def test_discover_cached_result_paths_skips_tmp_directories_by_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tracked_path = root / "variant.json"
            tmp_variant_path = root / "tmp" / "smoke" / "variant.json"
            tracked_path.write_text(json.dumps(_fake_result(playbook="broad", pricing_lane="mid")), encoding="utf8")
            tmp_variant_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_variant_path.write_text(json.dumps(_fake_result(playbook="broad", pricing_lane="pessimistic")), encoding="utf8")

            discovered = scoreboard.discover_cached_result_paths([root])

        self.assertEqual(discovered, [tracked_path.resolve()])

    def test_discover_cached_result_paths_allows_explicit_tmp_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tmp_variant_path = root / "tmp" / "smoke" / "variant.json"
            tmp_variant_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_variant_path.write_text(json.dumps(_fake_result(playbook="broad", pricing_lane="mid")), encoding="utf8")

            discovered = scoreboard.discover_cached_result_paths([tmp_variant_path])

        self.assertEqual(discovered, [tmp_variant_path.resolve()])


if __name__ == "__main__":
    unittest.main()
