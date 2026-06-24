from __future__ import annotations

import unittest
from pathlib import Path

from scripts import build_regular_options_underlying_daily_source_repair_packet as packet
from workspace_tempdir import WorkspaceTempDir


HEADER_FIELDS = (
    "symbol",
    "bar_date",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "fetched_at_utc",
    "adjustment_mode",
    "corporate_action_basis",
    "vendor",
    "source_event_date",
    "known_at_utc",
    "published_at_utc",
    "source_file_hash",
    "provenance_id",
    "candidate_date",
    "input_date",
    "source_quality",
)
HEADER = ",".join(HEADER_FIELDS)


def _row(
    symbol: str,
    bar_date: str,
    *,
    close: str = "101.00",
    adjusted_close: str | None = None,
    volume: str = "1000000",
    known_at: str = "2024-06-03T21:15:00Z",
    candidate_date: str = "",
    input_date: str = "",
    source_quality: str = "trusted",
    vendor: str = "Trusted Daily Vendor",
    provenance_id: str | None = None,
) -> str:
    published_at = known_at.replace("21:15:00Z", "21:05:00Z")
    values = {
        "symbol": symbol,
        "bar_date": bar_date,
        "open": "100.00",
        "high": "102.00",
        "low": "99.00",
        "close": close,
        "adjusted_close": close if adjusted_close is None else adjusted_close,
        "volume": volume,
        "fetched_at_utc": "2024-06-03T21:20:00Z",
        "adjustment_mode": "split_and_dividend_adjusted",
        "corporate_action_basis": "vendor_adjusted_total_return_basis",
        "vendor": vendor,
        "source_event_date": bar_date,
        "known_at_utc": known_at,
        "published_at_utc": published_at,
        "source_file_hash": "fixture_file_hash",
        "provenance_id": provenance_id or f"trusted:{symbol}:{bar_date}",
        "candidate_date": candidate_date,
        "input_date": input_date,
        "source_quality": source_quality,
    }
    return ",".join(values[field] for field in HEADER_FIELDS)


class RegularOptionsUnderlyingDailySourceRepairPacketTests(unittest.TestCase):
    def test_parser_accepts_good_rows_and_known_at_policy_rejects_same_day_candidate(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "underlying.csv"
            path.write_text(
                "\n".join(
                    [
                        HEADER,
                        _row("SPY", "2024-05-31", known_at="2024-05-31T21:15:00Z"),
                        _row("QQQ", "2024-06-03"),
                    ]
                )
                + "\n",
                encoding="utf8",
            )
            rows = packet.parse_future_source_csv(path)

        self.assertEqual(len(rows), 2)
        prior = next(row for row in rows if row["symbol"] == "SPY")
        same_day = next(row for row in rows if row["symbol"] == "QQQ")
        self.assertTrue(
            packet.row_usable_for_candidate(
                prior,
                candidate_date="2024-06-03",
                candidate_decision_utc="2024-06-03T13:35:00Z",
            )
        )
        self.assertFalse(
            packet.row_usable_for_candidate(
                same_day,
                candidate_date="2024-06-03",
                candidate_decision_utc="2024-06-03T13:35:00Z",
            )
        )
        self.assertFalse(
            packet.row_usable_for_candidate(
                prior,
                candidate_date="2024-06-03",
                candidate_decision_utc=prior["published_at_utc"],
            )
        )

    def test_missing_required_header_fails(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "bad.csv"
            path.write_text("symbol,bar_date\nSPY,2024-05-31\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_future_source_csv(path)

    def test_leakage_headers_are_rejected(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-source-packet") as tmp_dir:
            path = Path(tmp_dir) / "leak.csv"
            path.write_text(f"{HEADER},pnl,winner\n{_row('SPY', '2024-05-31')},10,true\n", encoding="utf8")

            with self.assertRaises(ValueError):
                packet.parse_future_source_csv(path)

    def test_validation_rejects_manual_synthetic_missing_price_same_day_and_conflicting_duplicates(self) -> None:
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    HEADER,
                    _row("SPY", "2024-05-31"),
                    _row("SPY", "2024-05-31", close="102.00"),
                    _row("AAPL", "2024-05-31", close="0"),
                    _row("QQQ", "2024-06-03", candidate_date="2024-06-03"),
                    _row("DIA", "2024-06-03", input_date="2024-06-03"),
                    _row("IWM", "2024-05-31", source_quality="manual_synthetic_source_mark_only"),
                    _row("CVX", "2024-05-31", vendor="manual vendor export"),
                    _row("COP", "2024-05-31", provenance_id="synthetic:cop:2024-05-31"),
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(rows)

        reasons = validation["reject_counts"]
        self.assertEqual(validation["duplicate_conflicting_group_count"], 1)
        self.assertGreaterEqual(reasons["duplicate_conflicting_rows"], 1)
        self.assertEqual(reasons["missing_or_invalid_close"], 1)
        self.assertEqual(reasons["future_or_same_day_bar_for_candidate"], 2)
        self.assertEqual(reasons["stale_manual_synthetic_or_source_mark_only_row"], 3)

    def test_validation_rejects_zero_volume_and_requires_adjustment_value_or_policy(self) -> None:
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    HEADER,
                    _row("SPY", "2024-05-31", volume="0"),
                    _row("QQQ", "2024-05-31", adjusted_close=""),
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(rows, target_universe=("SPY", "QQQ"), target_start_date="2024-06-03", target_end_date="2024-06-03", requested_dates=["2024-06-03"])

        self.assertEqual(validation["reject_counts"]["missing_or_invalid_volume"], 1)
        self.assertEqual(validation["reject_counts"]["missing_adjusted_close_or_adjustment_policy"], 1)

    def test_validation_accepts_adjustment_policy_when_adjusted_close_empty(self) -> None:
        header = HEADER + ",adjustment_policy"
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    header,
                    _row("SPY", "2024-05-31", adjusted_close="", known_at="2024-05-31T21:15:00Z") + ",split_adjusted_vendor_policy_v1",
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(rows, target_universe=("SPY",), target_start_date="2024-06-03", target_end_date="2024-06-03", requested_dates=["2024-06-03"])

        self.assertFalse(validation["reject_counts"])
        self.assertTrue(validation["coverage_ready"])

    def test_validation_enforces_per_symbol_requested_date_coverage(self) -> None:
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    HEADER,
                    _row("SPY", "2024-05-31", known_at="2024-05-31T21:15:00Z"),
                    _row("SPY", "2024-06-03", known_at="2024-06-03T21:15:00Z"),
                    _row("QQQ", "2024-05-31", known_at="2024-06-03T21:15:00Z"),
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(
            rows,
            target_universe=("SPY", "QQQ"),
            target_start_date="2024-06-03",
            target_end_date="2024-06-04",
            requested_dates=["2024-06-03", "2024-06-04"],
        )

        self.assertFalse(validation["coverage_ready"])
        self.assertEqual(validation["per_symbol_date_coverage"]["SPY"]["coverage_pct"], 100.0)
        self.assertEqual(validation["per_symbol_date_coverage"]["QQQ"]["coverage_pct"], 50.0)
        self.assertEqual(validation["min_date_coverage_pct"], 50.0)

    def test_exact_duplicate_rows_are_deduped_without_rejecting(self) -> None:
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    HEADER,
                    _row("SPY", "2024-05-31", known_at="2024-05-31T21:15:00Z"),
                    _row("SPY", "2024-05-31", known_at="2024-05-31T21:15:00Z"),
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(
            rows,
            target_universe=("SPY",),
            target_start_date="2024-06-03",
            target_end_date="2024-06-03",
            requested_dates=["2024-06-03"],
        )

        self.assertEqual(validation["reject_count"], 0)
        self.assertEqual(validation["duplicate_exact_group_count"], 1)
        self.assertEqual(validation["deduped_exact_duplicate_row_count"], 1)
        self.assertEqual(validation["valid_row_count"], 1)
        self.assertTrue(validation["coverage_ready"])

    def test_non_monotonic_known_at_rejects(self) -> None:
        rows = packet.parse_future_source_csv_from_text(
            "\n".join(
                [
                    HEADER,
                    _row("SPY", "2024-05-31", known_at="2024-06-03T21:15:00Z"),
                    _row("SPY", "2024-06-03", known_at="2024-06-01T21:15:00Z"),
                ]
            )
            + "\n"
        )
        validation = packet.validate_future_source_rows(rows)

        self.assertEqual(validation["non_monotonic_known_at_count"], 1)
        self.assertEqual(validation["reject_counts"]["non_monotonic_known_at"], 1)

    def test_build_report_is_read_only_and_names_future_materialization_path(self) -> None:
        with WorkspaceTempDir(prefix="underlying-daily-source-packet") as tmp_dir:
            tmp = Path(tmp_dir)
            report = packet.build_report(output_dir=tmp / "out", docs_report=tmp / "doc.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "doc.md").exists())

        self.assertEqual(
            report["status"],
            "underlying_daily_source_repair_packet_ready_for_future_source_import_decision",
        )
        self.assertEqual(report["source_family"], "point_in_time_underlying_daily_ohlcv_adjusted_v1")
        self.assertEqual(report["target_universe"], list(packet.TARGET_UNIVERSE))
        self.assertEqual(report["current_baseline"]["strict_forward_proof"], "0/30")
        self.assertEqual(report["current_baseline"]["frozen_scanner_blocked_rows"], 6916)
        self.assertEqual(report["current_baseline"]["frozen_scanner_underlying_blocker_rows"], 6916)
        self.assertFalse(report["source_materialized"])
        self.assertFalse(report["future_import_command_executed"])
        self.assertTrue(report["future_import_command_currently_implemented"])
        self.assertFalse(report["source_rows_written"])
        self.assertFalse(report["evidence_stores_mutated"])
        self.assertFalse(report["protected_holdout_consumed"])
        self.assertFalse(report["accepted_profitability"])
        future = report["future_approval"]
        self.assertIn("APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT", future["future_materialization_command_template"])
        self.assertIn(
            "data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_v1.csv",
            future["future_materialization_command_template"],
        )
        self.assertIn("known_at_utc", report["future_source_schema"]["required_fields"][10])
        self.assertTrue(report["known_at_policy"]["do_not_infer_known_at_from_bar_date"])
        self.assertFalse(report["local_market_data_db_assessment"]["sufficient_for_point_in_time_scanner_decisions"])
        self.assertIn("historical frozen scanner replay adapter", report["downstream_unlocks_after_future_approval_and_valid_source"])
        self.assertIn(
            "historical_frozen_scanner_replay_adapter",
            report["downstream_commands_after_future_source_materialization"],
        )


if __name__ == "__main__":
    unittest.main()
