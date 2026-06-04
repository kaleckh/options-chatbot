import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import replay_profit_service
from backend_route_context import BackendRouteContext


class ReplayProfitServiceTests(unittest.TestCase):
    def _context(self, namespace: dict[str, Any] | None = None) -> tuple[BackendRouteContext, list[tuple[Any, ...]], dict[str, Any]]:
        calls: list[tuple[Any, ...]] = []
        data = dict(namespace or {})

        def _preferred_results_cache_key(truth_lane: str | None) -> tuple[str, str]:
            return ("preferred", str(truth_lane or "default"))

        def _cached_readonly_report(key: tuple[Any, ...], builder):
            calls.append(key)
            return builder()

        data.setdefault("_preferred_results_cache_key", _preferred_results_cache_key)
        data.setdefault("_cached_readonly_report", _cached_readonly_report)
        return BackendRouteContext(data), calls, data

    def test_summary_assembles_replay_readbacks_through_context_cache(self):
        result = {"total_trades": 12, "run_at": "2026-04-01T00:00:00Z"}
        ctx, calls, _namespace = self._context(
            {
                "_cached_preferred_results_by_truth_lane": lambda truth_lane: dict(result, truth_lane=truth_lane),
                "_cached_last_results_by_truth_lane": lambda truth_lane: {"run_at": result["run_at"], "truth_lane": truth_lane},
                "build_prediction_replay_report": lambda *, result, min_trades: {
                    "kind": "report",
                    "min_trades": min_trades,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_metric_truth_report": lambda *, result, min_trades, bucket_size: {
                    "kind": "metric",
                    "min_trades": min_trades,
                    "bucket_size": bucket_size,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_options_profitability_forensics": lambda *, result, min_trades: {
                    "kind": "forensics",
                    "min_trades": min_trades,
                    "source": {"total_trades": result["total_trades"]},
                },
                "build_truth_lane_comparison": lambda *, truth_lane: {
                    "kind": "comparison",
                    "truth_lane": truth_lane,
                },
            }
        )

        summary = replay_profit_service.build_backtest_summary(ctx, "synthetic", 3, 5)

        self.assertEqual(
            set(summary),
            {"last", "report", "metricTruth", "profitabilityForensics", "comparison"},
        )
        self.assertEqual(summary["last"], {"run_at": result["run_at"], "truth_lane": "synthetic"})
        self.assertEqual(summary["report"]["kind"], "report")
        self.assertEqual(summary["metricTruth"]["bucket_size"], 5)
        self.assertEqual(summary["profitabilityForensics"]["source"]["total_trades"], 12)
        self.assertEqual(summary["comparison"], {"kind": "comparison", "truth_lane": "synthetic"})
        self.assertEqual(
            [key[0] for key in calls],
            [
                "backtest_report",
                "metric_truth_report",
                "backtest_profitability_forensics",
                "truth_lane_comparison",
            ],
        )

    def test_metric_truth_report_keeps_no_result_payload(self):
        ctx, _calls, _namespace = self._context(
            {
                "_cached_preferred_results_by_truth_lane": lambda truth_lane: None,
            }
        )

        self.assertEqual(
            replay_profit_service.build_metric_truth_report(ctx, "imported_daily", 20, 10),
            {"error": "No backtest results found"},
        )

    def test_live_policy_uses_late_bound_builder_and_cache_key(self):
        ctx, calls, namespace = self._context()

        def _policy_builder(**kwargs):
            return {"version": "first", "kwargs": kwargs}

        namespace["build_live_options_trade_policy"] = _policy_builder

        first = replay_profit_service.cached_live_trade_policy_report(
            ctx,
            1,
            2,
            3,
            1.2,
            55.0,
            "imported_daily",
        )
        namespace["build_live_options_trade_policy"] = lambda **kwargs: {"version": "second", "kwargs": kwargs}
        second = replay_profit_service.cached_live_trade_policy_report(
            ctx,
            1,
            2,
            3,
            1.2,
            55.0,
            "imported_daily",
        )

        self.assertEqual(first["version"], "first")
        self.assertEqual(second["version"], "second")
        self.assertEqual(
            calls[0],
            ("live_trade_policy", ("preferred", "imported_daily"), 1, 2, 3, 1.2, 55.0),
        )
        self.assertEqual(second["kwargs"]["truth_lane"], "imported_daily")
        self.assertEqual(second["kwargs"]["min_profit_factor"], 1.2)

    def test_exit_audit_cache_key_preserves_playbook_and_threshold_knobs(self):
        ctx, calls, namespace = self._context()
        namespace["build_playbook_exit_audit"] = lambda **kwargs: {"kwargs": kwargs}

        result = replay_profit_service.cached_playbook_exit_audit_report(
            ctx,
            "short_term",
            4,
            5,
            6,
            1.4,
            57.0,
            "synthetic",
        )

        self.assertEqual(
            calls[0],
            ("playbook_exit_audit", ("preferred", "synthetic"), "short_term", 4, 5, 6, 1.4, 57.0),
        )
        self.assertEqual(result["kwargs"]["playbook"], "short_term")
        self.assertEqual(result["kwargs"]["max_tickers"], 5)
        self.assertEqual(result["kwargs"]["min_directional_accuracy_pct"], 57.0)


if __name__ == "__main__":
    unittest.main()
