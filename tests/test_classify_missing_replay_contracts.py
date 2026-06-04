from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import classify_missing_replay_contracts as classifier


def _write_run(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "unpriced_trades": [
                    {
                        "ticker": "WMT",
                        "missing_quote_date": "2026-03-25",
                        "missing_short_contract_symbol": "WMT260402C00140000",
                    },
                    {
                        "ticker": "WMT",
                        "missing_quote_date": "2026-03-26",
                        "missing_short_contract_symbol": "WMT260402C00139000",
                    },
                    {
                        "ticker": "PG",
                        "missing_quote_date": "2026-03-25",
                        "missing_short_contract_symbol": "PG260402C00170000",
                    },
                ]
            }
        ),
        encoding="utf8",
    )


class ClassifyMissingReplayContractsTests(unittest.TestCase):
    def test_classify_run_filters_targets_before_db_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_path = Path(temp_dir) / "run.json"
            _write_run(run_path)
            fake_connection = object()
            connect_context = mock.MagicMock()
            connect_context.__enter__.return_value = fake_connection

            with mock.patch.object(classifier.sqlite3, "connect", return_value=connect_context), mock.patch.object(
                classifier,
                "_classify_contract",
                return_value={
                    "contract_symbol": "WMT260402C00140000",
                    "missing_quote_date": "2026-03-25",
                    "classification": "provider_no_match_exact_contract_with_same_expiry_chain",
                    "exact_row_count": 0,
                    "same_expiry_chain_row_count": 15069,
                },
            ) as classify_contract:
                report = classifier.classify_run(
                    run_path,
                    db_path=Path(temp_dir) / "options.db",
                    source_labels=["thetadata_opra_nbbo_1m"],
                    tickers={"WMT"},
                    contract_symbols={"WMT260402C00140000"},
                    quote_dates={"2026-03-25"},
                )

            self.assertEqual(report["target_filters"]["tickers"], ["WMT"])
            self.assertEqual(report["target_filters"]["contract_symbols"], ["WMT260402C00140000"])
            self.assertEqual(report["target_filters"]["quote_dates"], ["2026-03-25"])
            self.assertEqual(report["classified_count"], 1)
            self.assertEqual(report["by_ticker"], {"WMT": 1})
            self.assertEqual(report["classification_counts"], {"provider_no_match_exact_contract_with_same_expiry_chain": 1})
            classify_contract.assert_called_once_with(
                fake_connection,
                contract_symbol="WMT260402C00140000",
                quote_date="2026-03-25",
                source_labels=["thetadata_opra_nbbo_1m"],
            )


if __name__ == "__main__":
    unittest.main()
