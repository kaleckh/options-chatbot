from __future__ import annotations

import unittest

from scripts import build_current_policy_historical_picks_audit as audit


def _row(position_id: int, ticker: str, playbook_id: str, pnl_pct: float | None, **overrides):
    snapshot = {
        "playbook_id": playbook_id,
        "spread_width": 10.0,
        "net_debit": 3.0,
        "ret5": 0.0,
        "quality_score": 50.0,
        "direction_score": 50.0,
        "backfill_audit_id": "all_lanes_zero_pick_current_algo_v1",
        "position_migration_id": "migration-1",
    }
    snapshot.update(overrides.pop("source_pick_snapshot", {}))
    row = {
        "id": position_id,
        "status": "closed",
        "ticker": ticker,
        "direction": "call",
        "contracts": 1,
        "entry_option_price": 1.0,
        "entry_execution_price": 1.0,
        "entry_execution_basis": "spread_bid_ask",
        "exit_execution_price": 1.2,
        "exit_execution_basis": "spread_bid_ask_exact",
        "net_pnl_pct": pnl_pct,
        "filled_at": "2026-05-20T10:10:00Z",
        "closed_at": "2026-05-21T15:45:00Z",
        "source_pick_snapshot": snapshot,
    }
    row.update(overrides)
    return row


class CurrentPolicyHistoricalPicksAuditTests(unittest.TestCase):
    def test_replay_splits_would_take_from_learned_away_rows(self):
        report = audit.build_report(
            [
                _row(1, "ORCL", "short_term", 25.0),
                _row(2, "MSFT", "short_term", -60.0, source_pick_snapshot={"net_debit": 5.0}),
                _row(3, "SPY", "bullish_pullback_observation", -30.0),
            ],
            keep_tickers={"IWM", "AAPL", "GOOGL"},
            promoted_guardrails=audit.FALLBACK_PROMOTED_GUARDRAILS,
        )

        decisions = {row["trade_id"]: row for row in report["rows"]}

        self.assertEqual(decisions[1]["current_policy_decision"], "would_take_today")
        self.assertEqual(decisions[2]["current_policy_decision"], "blocked_by_current_policy")
        self.assertIn("debit_gt_45_width", decisions[2]["guardrail_hits"])
        self.assertEqual(decisions[3]["current_policy_decision"], "blocked_by_current_policy")
        self.assertIn("bullish_pullback_not_keep_bucket", decisions[3]["guardrail_hits"])
        self.assertEqual(report["summary"]["would_take_today"]["avg_pnl_pct"], 25.0)
        self.assertEqual(report["summary"]["blocked_by_current_policy"]["negative"], 2)

    def test_replay_keeps_unpriced_rows_visible_as_unknown(self):
        report = audit.build_report(
            [
                _row(
                    4,
                    "ORCL",
                    "swing",
                    None,
                    exit_execution_price=None,
                    exit_execution_basis=None,
                )
            ],
            keep_tickers={"IWM"},
            promoted_guardrails=audit.FALLBACK_PROMOTED_GUARDRAILS,
        )

        row = report["rows"][0]

        self.assertEqual(row["current_policy_decision"], "unknown_missing_evidence")
        self.assertEqual(row["evidence_group"], "lifecycle_only")
        self.assertEqual(report["summary"]["unknown_missing_evidence"]["rows"], 1)

    def test_symbol_sleeve_status_is_advisory_not_a_hard_rewrite(self):
        symbol_sleeves = {
            ("short_term", "ORCL"): {
                "status": "watch",
                "evidence_class": "trusted_intraday_opra_nbbo_exact",
                "reason_codes": ["positive_but_thin_or_incomplete"],
            }
        }

        report = audit.build_report(
            [_row(5, "ORCL", "short_term", 15.0)],
            keep_tickers={"IWM"},
            promoted_guardrails=audit.FALLBACK_PROMOTED_GUARDRAILS,
            symbol_sleeves=symbol_sleeves,
        )

        row = report["rows"][0]

        self.assertEqual(row["current_policy_decision"], "would_take_today")
        self.assertEqual(row["symbol_sleeve_status"], "watch")
        self.assertIn("positive_but_thin_or_incomplete", row["symbol_sleeve_reason_codes"])


if __name__ == "__main__":
    unittest.main()
