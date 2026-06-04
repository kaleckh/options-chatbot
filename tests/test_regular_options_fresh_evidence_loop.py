from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_regular_options_fresh_evidence_loop as evidence_loop


def _candidate(
    ticker: str,
    *,
    status: str = "live_validation_attempted",
    playbook_id: str = "swing",
    expiry: str = "2026-06-26",
    long_contract: str | None = None,
    short_contract: str | None = None,
) -> dict:
    long_contract = long_contract or f"{ticker}260626C00100000"
    short_contract = short_contract or f"{ticker}260626C00110000"
    return {
        "audit_generated_at_utc": "2026-06-02T06:39:32Z",
        "candidate_key": f"2026-06-02|{playbook_id}|{ticker}|call|{expiry}|{long_contract}|{short_contract}|100.0|110.0",
        "candidate_status": status,
        "validation_exit_code": 0,
        "validation_recorded_at_utc": "2026-06-02T15:00:00Z",
        "tracking_approved_lane": True,
        "position_tracking_mode": "auto_track",
        "playbook_id": playbook_id,
        "ticker": ticker,
        "direction": "call",
        "expiry": expiry,
        "contract_symbol": long_contract,
        "short_contract_symbol": short_contract,
        "long_strike": 100.0,
        "short_strike": 110.0,
    }


def _fill(
    ticker: str,
    *,
    position_id: int | None,
    label: str = "executable_opra_paper_candidate",
    basis: str = "spread_ask_bid",
    quote_freshness: str = "fresh",
    fill_status: str = "auto_tracked",
    fill_outcome: str = "paper_fill_recorded",
    fill_reason: str = "auto_track_position_created",
    auto_track_outcome: str | None = "created",
    long_contract: str | None = None,
    short_contract: str | None = None,
) -> dict:
    long_contract = long_contract or f"{ticker}260626C00100000"
    short_contract = short_contract or f"{ticker}260626C00110000"
    row = {
        "event_type": "candidate_shown",
        "status": "shown",
        "scan_date": "2026-06-02",
        "playbook_id": "swing",
        "ticker": ticker,
        "direction": "call",
        "expiry": "2026-06-26",
        "candidate_execution_label": label,
        "attempted_limit_basis": basis,
        "quote_freshness_status": quote_freshness,
        "options_data_source": "OPRA",
        "pricing_evidence_class": "proof_live_opra_exact_contract",
        "selection_source": "live_chain_exact_contract",
        "filled": position_id is not None and fill_status == "auto_tracked",
        "fill_status": fill_status,
        "fill_outcome": fill_outcome,
        "fill_outcome_reason": fill_reason,
        "auto_track_outcome": auto_track_outcome,
        "selected_spread": {
            "long_contract_symbol": long_contract,
            "short_contract_symbol": short_contract,
            "long_strike": 100.0,
            "short_strike": 110.0,
            "entry_execution_basis": basis,
            "quote_freshness_status": quote_freshness,
        },
    }
    if position_id is not None:
        row["auto_track_position_id"] = position_id
    return row


def _stop_row(position_id: int, pnl: float, *, basis: str = "historical_spread_bid_ask") -> dict:
    return {
        "position_id": position_id,
        "baseline_pnl_pct": pnl,
        "baseline_close_date": "2026-06-20",
        "last_priced_point": {
            "exit_execution_basis": basis,
            "net_pnl_pct": pnl,
        },
    }


class RegularOptionsFreshEvidenceLoopTests(unittest.TestCase):
    def test_fresh_evidence_loop_reconciles_validation_fill_links_and_realized_pnl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fills = root / "fills.jsonl"
            stop_grid = root / "stop-grid.json"
            candidates = [
                _candidate("SPY"),
                _candidate("QQQ"),
                _candidate("IWM"),
                _candidate("DIA"),
                _candidate("XLF"),
            ]
            queue.write_text("\n".join(json.dumps(row) for row in candidates) + "\n", encoding="utf8")
            fill_rows = [
                _fill("SPY", position_id=11),
                _fill("QQQ", position_id=12, auto_track_outcome="duplicate_open"),
                _fill(
                    "DIA",
                    position_id=None,
                    label="non_executable_opra_candidate",
                    basis="midpoint",
                    fill_status="not_filled_auto_track_skipped",
                    fill_outcome="no_fill",
                    fill_reason="auto_track_skipped_or_missing_fill_price",
                    auto_track_outcome=None,
                ),
                _fill(
                    "XLF",
                    position_id=None,
                    label="stale_snapshot_candidate",
                    quote_freshness="stale",
                    fill_status="not_filled_auto_track_skipped",
                    fill_outcome="no_fill",
                    fill_reason="auto_track_skipped_or_missing_fill_price",
                    auto_track_outcome=None,
                ),
            ]
            fills.write_text("\n".join(json.dumps(row) for row in fill_rows) + "\n", encoding="utf8")
            stop_grid.write_text(
                json.dumps({"report_id": "fixture_stop_grid", "rows": [_stop_row(11, 42.5)]}),
                encoding="utf8",
            )

            report = evidence_loop.build_report(
                queue_file=queue,
                fill_attempt_file=fills,
                stop_grid_path=stop_grid,
            )

        by_ticker = {row["ticker"]: row for row in report["candidates"]}
        self.assertTrue(by_ticker["SPY"]["promotion_discussion_ready"])
        self.assertEqual(by_ticker["SPY"]["realized_pnl_status"], "exact_realized_pnl_available")
        self.assertEqual(by_ticker["QQQ"]["realized_pnl_status"], "missing_realized_pnl")
        self.assertEqual(by_ticker["QQQ"]["validation_outcome"], "duplicate")
        self.assertEqual(by_ticker["IWM"]["validation_outcome"], "no_longer_matched")
        self.assertEqual(by_ticker["DIA"]["validation_outcome"], "proof_ineligible")
        self.assertEqual(by_ticker["DIA"]["entry_evidence_status"], "non_executable")
        self.assertEqual(by_ticker["XLF"]["entry_evidence_status"], "stale")
        self.assertEqual(report["summary"]["exact_realized_pnl_count"], 1)
        self.assertEqual(report["summary"]["missing_realized_pnl_count"], 1)
        self.assertEqual(report["summary"]["no_longer_matched_count"], 1)
        self.assertEqual(report["summary"]["proof_ineligible_count"], 2)
        self.assertEqual(report["summary"]["stale_count"], 1)
        self.assertEqual(report["summary"]["non_executable_count"], 1)
        self.assertEqual(report["summary"]["promotion_discussion_ready_count"], 1)

    def test_realized_pnl_requires_exact_exit_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fills = root / "fills.jsonl"
            stop_grid = root / "stop-grid.json"
            queue.write_text(json.dumps(_candidate("SPY")) + "\n", encoding="utf8")
            fills.write_text(json.dumps(_fill("SPY", position_id=11)) + "\n", encoding="utf8")
            stop_grid.write_text(
                json.dumps({"rows": [_stop_row(11, 12.5, basis="daily_eod_close")]}),
                encoding="utf8",
            )

            report = evidence_loop.build_report(
                queue_file=queue,
                fill_attempt_file=fills,
                stop_grid_path=stop_grid,
            )

        row = report["candidates"][0]
        self.assertEqual(row["realized_pnl_status"], "missing_exact_exit_evidence")
        self.assertFalse(row["promotion_discussion_ready"])

    def test_contaminated_exit_basis_tokens_do_not_count_as_exact_pnl(self):
        contaminated = [
            "expired_auto_close",
            "lifecycle_spread_bid_ask",
            "spread_bid_ask_midpoint",
            "spread_bid_ask_unpriced",
        ]
        for basis in contaminated:
            with self.subTest(basis=basis):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    queue = root / "pending.jsonl"
                    fills = root / "fills.jsonl"
                    stop_grid = root / "stop-grid.json"
                    queue.write_text(json.dumps(_candidate("SPY")) + "\n", encoding="utf8")
                    fills.write_text(json.dumps(_fill("SPY", position_id=11)) + "\n", encoding="utf8")
                    stop_grid.write_text(
                        json.dumps({"rows": [_stop_row(11, 12.5, basis=basis)]}),
                        encoding="utf8",
                    )

                    report = evidence_loop.build_report(
                        queue_file=queue,
                        fill_attempt_file=fills,
                        stop_grid_path=stop_grid,
                    )

                row = report["candidates"][0]
                self.assertEqual(row["realized_pnl_status"], "missing_exact_exit_evidence")
                self.assertFalse(row["promotion_discussion_ready"])

    def test_zero_realized_pnl_can_still_clear_exact_exit_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fills = root / "fills.jsonl"
            stop_grid = root / "stop-grid.json"
            queue.write_text(json.dumps(_candidate("SPY")) + "\n", encoding="utf8")
            fills.write_text(json.dumps(_fill("SPY", position_id=11)) + "\n", encoding="utf8")
            stop_grid.write_text(json.dumps({"rows": [_stop_row(11, 0.0)]}), encoding="utf8")

            report = evidence_loop.build_report(
                queue_file=queue,
                fill_attempt_file=fills,
                stop_grid_path=stop_grid,
            )

        row = report["candidates"][0]
        self.assertEqual(row["realized_pnl_status"], "exact_realized_pnl_available")
        self.assertEqual(row["realized_pnl"]["baseline_pnl_pct"], 0.0)
        self.assertTrue(row["promotion_discussion_ready"])

    def test_entry_vocabulary_rejects_plain_mid_and_space_separated_non_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue = root / "pending.jsonl"
            fills = root / "fills.jsonl"
            stop_grid = root / "stop-grid.json"
            candidates = [_candidate("SPY"), _candidate("QQQ")]
            queue.write_text("\n".join(json.dumps(row) for row in candidates) + "\n", encoding="utf8")
            fills.write_text(
                "\n".join(
                    [
                        json.dumps(_fill("SPY", position_id=None, basis="mid")),
                        json.dumps(_fill("QQQ", position_id=None, label="non executable opra candidate")),
                    ]
                )
                + "\n",
                encoding="utf8",
            )
            stop_grid.write_text(json.dumps({"rows": []}), encoding="utf8")

            report = evidence_loop.build_report(
                queue_file=queue,
                fill_attempt_file=fills,
                stop_grid_path=stop_grid,
            )

        by_ticker = {row["ticker"]: row for row in report["candidates"]}
        self.assertEqual(by_ticker["SPY"]["entry_evidence_status"], "non_executable")
        self.assertIn("midpoint_entry_evidence", by_ticker["SPY"]["entry_evidence_reasons"])
        self.assertEqual(by_ticker["QQQ"]["entry_evidence_status"], "non_executable")
        self.assertIn("non_executable_entry_evidence", by_ticker["QQQ"]["entry_evidence_reasons"])

    def test_markdown_renders_core_readback_counts(self):
        report = {
            "status": "fresh_evidence_loop_readback",
            "summary": {
                "candidate_count": 2,
                "validation_outcome_counts": {"no_longer_matched": 1, "proof_ineligible": 1},
                "entry_evidence_status_counts": {"stale": 1, "non_executable": 1},
                "realized_pnl_status_counts": {"no_position_link": 2},
                "no_longer_matched_count": 1,
                "proof_ineligible_count": 1,
                "linked_position_count": 0,
                "exact_realized_pnl_count": 0,
                "missing_realized_pnl_count": 0,
                "stale_count": 1,
                "non_executable_count": 1,
                "promotion_discussion_ready_count": 0,
                "live_policy_change": False,
            },
            "candidates": [],
        }

        markdown = evidence_loop.render_markdown(report)

        self.assertIn("# Regular Options Fresh Evidence Loop", markdown)
        self.assertIn("No-longer-matched: `1`", markdown)
        self.assertIn("Non-executable entry evidence: `1`", markdown)


if __name__ == "__main__":
    unittest.main()
