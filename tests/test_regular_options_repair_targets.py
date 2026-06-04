from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import regular_options_repair_targets as targets


def _write_run(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "unpriced_trades": [
                    {
                        "ticker": "wmt",
                        "date": "2026-02-25",
                        "missing_quote_date": "2026-03-25",
                        "missing_short_contract_symbol": "wmt260402c00140000",
                    },
                    {
                        "ticker": "WMT",
                        "date": "2026-02-26",
                        "missing_quote_date": "2026-03-26",
                        "short_contract_symbol": "WMT260402C00139000",
                    },
                    {
                        "ticker": "PG",
                        "date": "2026-02-25",
                        "missing_quote_date": "2026-03-25",
                        "missing_short_contract_symbol": "PG260402C00170000",
                    },
                ]
            }
        ),
        encoding="utf8",
    )


class RegularOptionsRepairTargetsTests(unittest.TestCase):
    def test_filters_normalize_repeated_comma_values(self) -> None:
        self.assertEqual(
            targets.target_filters(
                tickers=["wmt, pg", "WMT"],
                contract_symbols=["wmt260402c00140000"],
                quote_dates=["2026-03-25,2026-03-26"],
            ),
            {
                "tickers": ["PG", "WMT"],
                "contract_symbols": ["WMT260402C00140000"],
                "quote_dates": ["2026-03-25", "2026-03-26"],
            },
        )

    def test_missing_items_dedupe_and_optional_fallback_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_path = Path(temp_dir) / "run.json"
            _write_run(run_path)

            missing_only = targets.missing_items_from_run_paths([run_path], tickers={"WMT"})
            with_fallback = targets.missing_items_from_run_paths(
                [run_path],
                tickers={"WMT"},
                include_fallback_contracts=True,
            )

        self.assertEqual([item["contract_symbol"] for item in missing_only], ["WMT260402C00140000"])
        self.assertEqual(
            [item["contract_symbol"] for item in with_fallback],
            ["WMT260402C00140000", "WMT260402C00139000"],
        )
        self.assertEqual(with_fallback[0]["quote_date"].isoformat(), "2026-03-25")
        self.assertEqual(with_fallback[0]["source_occurrences"][0]["source_field"], "missing_short_contract_symbol")

    def test_expand_items_tracks_original_missing_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_path = Path(temp_dir) / "run.json"
            _write_run(run_path)
            items = targets.missing_items_from_run_paths(
                [run_path],
                tickers={"WMT"},
                contract_symbols={"WMT260402C00140000"},
            )

        expanded = targets.expand_items(items, lookahead_calendar_days=1)
        self.assertEqual([item["quote_date"].isoformat() for item in expanded], ["2026-03-25", "2026-03-26"])
        self.assertEqual(expanded[1]["original_missing_quote_date"].isoformat(), "2026-03-25")
        self.assertEqual(targets.original_target_key(expanded[1]), ("2026-03-25", "WMT260402C00140000"))


if __name__ == "__main__":
    unittest.main()
