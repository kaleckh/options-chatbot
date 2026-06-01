from __future__ import annotations

from pathlib import Path

from scripts.build_regular_profitability_operating_scorecard import build_scorecard


def test_scorecard_marks_product_progress_but_keeps_proof_blocked(tmp_path: Path):
    autoresearch = tmp_path / "autoresearch.json"
    autoresearch.write_text(
        """
        {
          "experiment_batch": "batch",
          "best": {
            "variant_id": "lane_a_goal_test",
            "score": 0,
            "research_score": 166.55,
            "status": "scout_or_blocked",
            "promotion_blockers": ["lane_a_conservative_pf_below_1_30"],
            "autoresearch_metrics": {
              "promotable_clean_count": 0,
              "scout_count": 191,
              "lane_a_conservative_profit_factor": 0.92,
              "zero_bid_exit_rate_pct": 43.24
            }
          }
        }
        """,
        encoding="utf8",
    )
    guardrails = tmp_path / "guardrails.json"
    guardrails.write_text(
        """
        {
          "baseline": {
            "rows": 429,
            "priced": 383,
            "avg_pnl_pct": 5.21,
            "median_pnl_pct": -1.58,
            "negative_rate_priced_pct": 50.4
          },
          "combined_promoted_guardrails": {
            "kept": {
              "rows": 130,
              "priced": 116,
              "avg_pnl_pct": 53.08,
              "median_pnl_pct": 46.4,
              "negative_rate_priced_pct": 25.0
            },
            "blocked": {
              "rows": 299,
              "priced": 267,
              "avg_pnl_pct": -15.59,
              "median_pnl_pct": -25.08,
              "negative_rate_priced_pct": 61.4
            }
          },
          "promoted_guardrails": ["debit_gt_45_width"]
        }
        """,
        encoding="utf8",
    )
    negative = tmp_path / "negative.json"
    negative.write_text(
        """
        {
          "legacy_missed_close_targets": [
            {
              "trade_id": 26,
              "ticker": "JPM",
              "final_pnl_pct": -44.7,
              "failure_category": "missed_executable_profit_exit_before_final_loss"
            }
          ],
          "negative_trades": [
            {"failure_category": "entry_guardrail_now_blocks"}
          ]
        }
        """,
        encoding="utf8",
    )
    exit_replay = tmp_path / "exit.json"
    exit_replay.write_text(
        """
        {
          "baseline": {"avg_pnl_pct": 37.28},
          "policies": [
            {
              "policy_id": "current_policy_replay",
              "recommendation": {"status": "research_candidate"},
              "legacy_targets": [
                {
                  "trade_id": 26,
                  "ticker": "JPM",
                  "baseline_pnl_pct": -44.7,
                  "policy_pnl_pct": 3.9,
                  "delta_vs_baseline_pct": 48.6,
                  "reason": "time_exit"
                }
              ]
            }
          ]
        }
        """,
        encoding="utf8",
    )
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        """
        {
          "summary": {
            "target_count": 1,
            "diagnosis_counts": {"stale_or_non_autoclosing_review_path": 1},
            "current_action_required_count": 0,
            "historical_stale_path_count": 1,
            "recommendation": "no_broad_exit_policy_change; preserve as historical stale-policy diagnostic"
          },
          "rows": []
        }
        """,
        encoding="utf8",
    )

    scorecard = build_scorecard(
        autoresearch_path=autoresearch,
        guardrails_path=guardrails,
        negative_audit_path=negative,
        exit_replay_path=exit_replay,
        legacy_missed_close_path=legacy,
    )

    assert scorecard["status"] == "visible_product_profitability_progress_but_proof_still_blocked"
    assert scorecard["product_profitability_progress_visible"] is True
    assert scorecard["proof_grade_profitability_progress_visible"] is False
    assert scorecard["trading_desk_guardrails"]["deltas_vs_baseline"]["avg_pnl_pct"] == 47.87
    assert scorecard["trading_desk_guardrails"]["promoted_guardrails"] == ["debit_gt_45_width"]
    assert scorecard["negative_decision_audit"]["legacy_missed_close_target_count"] == 1
    assert scorecard["legacy_missed_close_audit"]["current_action_required_count"] == 0
    assert any("historical stale-policy diagnostics" in action for action in scorecard["next_actions"])
