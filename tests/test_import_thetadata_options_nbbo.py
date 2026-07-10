import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    _business_dates,
    _normalize_theta_quote_row,
    _occ_contract_symbol,
    _parse_theta_expiration,
    build_thetadata_nbbo_import,
)
from scripts import import_thetadata_options_nbbo as importer  # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.closed = False

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(self.payload)

    def close(self):
        self.closed = True


class _FailingSession:
    def get(self, url, params, timeout):
        raise RuntimeError("provider unavailable")


class ImportThetaDataOptionsNbboTests(unittest.TestCase):
    def test_occ_contract_symbol_uses_repo_contract_format(self):
        self.assertEqual(
            _occ_contract_symbol("fcx", date(2026, 6, 19), "call", 55.0),
            "FCX260619C00055000",
        )

    def test_business_dates_skips_weekends(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 15), date(2026, 5, 18)),
            [date(2026, 5, 15), date(2026, 5, 18)],
        )

    def test_business_dates_skips_exchange_holidays(self):
        self.assertEqual(
            _business_dates(date(2026, 5, 22), date(2026, 5, 26)),
            [date(2026, 5, 22), date(2026, 5, 26)],
        )

    def test_business_dates_skips_ad_hoc_full_market_closures(self):
        self.assertEqual(
            _business_dates(date(2025, 1, 8), date(2025, 1, 10)),
            [date(2025, 1, 8), date(2025, 1, 10)],
        )

    def test_parse_theta_expiration_accepts_iso_or_theta_format(self):
        self.assertEqual(_parse_theta_expiration("20260618"), "20260618")
        self.assertEqual(_parse_theta_expiration("2026-06-18"), "20260618")
        self.assertIsNone(_parse_theta_expiration(None))

    def test_normalize_theta_quote_row_preserves_bid_ask_and_timestamp(self):
        row = _normalize_theta_quote_row(
            {
                "symbol": "FCX",
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 1.2,
                "ask": 1.35,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(row["option_type"], "call")
        self.assertEqual(row["strike"], "55")
        self.assertEqual(row["bid"], "1.2")
        self.assertEqual(row["ask"], "1.35")
        self.assertEqual(row["as_of_utc"], "2026-05-15T19:55:00Z")

    def test_normalize_theta_quote_row_rejects_non_executable_quotes(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "put",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 1.4,
                "ask": 1.1,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNone(row)

    def test_normalize_theta_quote_row_accepts_zero_bid_positive_ask_quote(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 0.0,
                "ask": 0.05,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(row["bid"], "0")
        self.assertEqual(row["ask"], "0.05")

    def test_normalize_theta_quote_row_rejects_zero_ask_quote(self):
        row = _normalize_theta_quote_row(
            {
                "expiration": "2026-06-19",
                "strike": 55.0,
                "right": "call",
                "timestamp": "2026-05-15T15:55:00.000",
                "bid": 0.0,
                "ask": 0.0,
            },
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )

        self.assertIsNone(row)

    def test_normalize_requires_real_provider_timestamp_on_requested_trade_date(self):
        base = {
            "expiration": "2026-06-19",
            "strike": 55.0,
            "right": "call",
            "bid": 1.0,
            "ask": 1.1,
        }

        self.assertIsNone(
            _normalize_theta_quote_row(
                base, underlying="FCX", trade_date=date(2026, 5, 15)
            )
        )
        self.assertIsNone(
            _normalize_theta_quote_row(
                {**base, "timestamp": "2026-05-16T15:55:00-04:00"},
                underlying="FCX",
                trade_date=date(2026, 5, 15),
            )
        )

    def test_fractional_provider_timestamp_is_preserved_and_cannot_truncate_into_exact_window(
        self,
    ):
        raw = {
            "expiration": "2026-06-19",
            "strike": 55.0,
            "right": "call",
            "timestamp": "2026-05-15T15:55:00.999999-04:00",
            "bid": 1.0,
            "ask": 1.1,
        }
        normalized = _normalize_theta_quote_row(
            raw,
            underlying="FCX",
            trade_date=date(2026, 5, 15),
        )
        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["as_of_utc"], "2026-05-15T19:55:00.999999Z")

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            right="call",
            start_time="15:55:00",
            end_time="15:55:00",
            session=_FakeSession([raw]),
        )

        self.assertFalse(payload["request_surface_complete"])
        self.assertEqual(payload["successful_request_count"], 0)
        self.assertEqual(
            payload["skipped_rows"], {"provider_timestamp_outside_requested_window": 1}
        )

    def test_normalize_rejects_invalid_right_and_contract_right_mismatch(self):
        base = {
            "expiration": "2026-06-19",
            "strike": 55.0,
            "timestamp": "2026-05-15T15:55:00-04:00",
            "bid": 1.0,
            "ask": 1.1,
        }

        self.assertIsNone(
            _normalize_theta_quote_row(
                {**base, "right": "unknown"},
                underlying="FCX",
                trade_date=date(2026, 5, 15),
            )
        )
        self.assertIsNone(
            _normalize_theta_quote_row(
                {**base, "right": "put", "contract_symbol": "FCX260619C00055000"},
                underlying="FCX",
                trade_date=date(2026, 5, 15),
            )
        )

    def test_build_thetadata_nbbo_import_fetches_and_filters_rows(self):
        session = _FakeSession(
            [
                {
                    "symbol": "FCX",
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "call",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 1.2,
                    "ask": 1.35,
                },
                {
                    "symbol": "FCX",
                    "expiration": "2026-12-18",
                    "strike": 55.0,
                    "right": "put",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 2.2,
                    "ask": 2.35,
                },
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            session=session,
        )

        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["generated_rows"], 1)
        self.assertEqual(payload["rows_by_symbol"], {"FCX": 1})
        self.assertEqual(payload["skipped_rows"], {"outside_dte_window": 1})
        self.assertEqual(payload["rows"][0]["contract_symbol"], "FCX260619C00055000")
        self.assertEqual(session.calls[0]["params"]["expiration"], "*")
        self.assertEqual(session.calls[0]["params"]["interval"], "1m")
        self.assertEqual(session.calls[0]["params"]["start_time"], "15:55:00")

    def test_build_thetadata_nbbo_import_uses_exact_expiration_when_provided(self):
        session = _FakeSession(
            [
                {
                    "symbol": "FCX",
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "call",
                    "timestamp": "2026-05-15T15:55:00.000",
                    "bid": 1.2,
                    "ask": 1.35,
                }
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            expiration="20260619",
            session=session,
        )

        self.assertEqual(payload["expiration"], "20260619")
        self.assertEqual(session.calls[0]["params"]["expiration"], "20260619")
        self.assertEqual(payload["generated_rows"], 1)

    def test_build_reports_provider_failure_as_incomplete_request_surface(self):
        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            session=_FailingSession(),
        )

        self.assertEqual(payload["status"], "blocked_request_surface_incomplete")
        self.assertFalse(payload["request_surface_complete"])
        self.assertEqual(payload["expected_request_count"], 1)
        self.assertEqual(payload["request_count"], 0)
        self.assertEqual(payload["failed_request_count"], 1)
        self.assertEqual(payload["request_errors"][0]["symbol"], "FCX")
        self.assertEqual(payload["request_errors"][0]["date"], "2026-05-15")

    def test_complete_request_has_structured_call_put_dte_and_timestamp_lineage(self):
        session = _FakeSession(
            [
                {
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": right,
                    "timestamp": "2026-05-15T15:55:00-04:00",
                    "bid": 1.0,
                    "ask": 1.1,
                }
                for right in ("call", "put")
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            min_dte=5,
            max_dte=60,
            session=session,
        )

        self.assertEqual(payload["status"], "request_surface_complete")
        self.assertEqual(payload["successful_request_count"], 1)
        self.assertEqual(payload["rows_by_right"], {"call": 1, "put": 1})
        request = payload["request_results"][0]
        self.assertEqual(request["request_id"], "FCX:2026-05-15")
        self.assertTrue(request["provider_request_succeeded"])
        self.assertEqual(request["requested_right"], "both")
        self.assertEqual((request["call_row_count"], request["put_row_count"]), (1, 1))
        self.assertEqual(request["normalized_row_count"], 2)
        self.assertEqual(
            (request["observed_min_dte"], request["observed_max_dte"]), (35, 35)
        )
        self.assertEqual(
            request["first_provider_timestamp_utc"], "2026-05-15T19:55:00Z"
        )
        self.assertEqual(payload["chain_completeness"]["status"], "not_established")
        self.assertEqual(
            payload["chain_completeness"]["standard_version"],
            importer.CHAIN_COMPLETENESS_STANDARD_VERSION,
        )
        self.assertFalse(
            payload["chain_completeness"]["selection_or_evaluation_authorized"]
        )

    def test_http_200_wrong_minute_or_requested_right_does_not_count_as_complete(self):
        wrong_minute = _FakeSession(
            [
                {
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": right,
                    "timestamp": "2026-05-15T15:54:00-04:00",
                    "bid": 1.0,
                    "ask": 1.1,
                }
                for right in ("call", "put")
            ]
        )
        wrong_right = _FakeSession(
            [
                {
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "put",
                    "timestamp": "2026-05-15T15:55:00-04:00",
                    "bid": 1.0,
                    "ask": 1.1,
                }
            ]
        )

        for session, requested_right in ((wrong_minute, "both"), (wrong_right, "call")):
            with self.subTest(requested_right=requested_right):
                payload = build_thetadata_nbbo_import(
                    symbols=["FCX"],
                    dates=[date(2026, 5, 15)],
                    right=requested_right,
                    session=session,
                )
                self.assertFalse(payload["request_surface_complete"])
                self.assertEqual(payload["successful_request_count"], 0)
                self.assertGreater(
                    payload["request_results"][0]["lineage_rejection_count"], 0
                )

    def test_valid_single_right_request_remains_complete(self):
        session = _FakeSession(
            [
                {
                    "expiration": "2026-06-19",
                    "strike": 55.0,
                    "right": "call",
                    "timestamp": "2026-05-15T15:55:00-04:00",
                    "bid": 1.0,
                    "ask": 1.1,
                }
            ]
        )

        payload = build_thetadata_nbbo_import(
            symbols=["FCX"],
            dates=[date(2026, 5, 15)],
            right="call",
            session=session,
        )

        self.assertTrue(payload["request_surface_complete"])
        self.assertEqual(payload["successful_request_count"], 1)
        self.assertEqual(payload["request_results"][0]["missing_requested_rights"], [])

    def test_frozen_1555_preflight_blocks_all_known_early_closes_without_http(self):
        early_closes = [
            date(2018, 7, 3),
            date(2018, 11, 23),
            date(2018, 12, 24),
            date(2019, 7, 3),
            date(2019, 11, 29),
            date(2019, 12, 24),
            date(2020, 11, 27),
            date(2020, 12, 24),
            date(2021, 11, 26),
        ]
        session = _FakeSession([])

        payload = build_thetadata_nbbo_import(
            symbols=["SPY"],
            dates=early_closes,
            start_time="15:55:00",
            end_time="15:55:00",
            session=session,
        )

        self.assertEqual(
            payload["status"], "blocked_preflight_unsupported_market_session_time"
        )
        self.assertEqual(payload["request_count"], 0)
        self.assertEqual(len(payload["unsupported_market_sessions"]), 9)
        self.assertEqual(
            {item["date"] for item in payload["unsupported_market_sessions"]},
            {item.isoformat() for item in early_closes},
        )
        self.assertEqual(session.calls, [])

    def test_unknown_market_close_metadata_blocks_without_http(self):
        session = _FakeSession([])
        with patch.object(
            importer, "us_equity_market_close_time_et", return_value=None
        ):
            payload = build_thetadata_nbbo_import(
                symbols=["SPY"],
                dates=[date(2021, 12, 30)],
                start_time="10:10:00",
                end_time="10:10:00",
                session=session,
            )

        self.assertEqual(
            payload["status"], "blocked_preflight_unsupported_market_session_time"
        )
        self.assertFalse(payload["request_surface_complete"])
        self.assertEqual(
            payload["unsupported_market_sessions"][0]["reason"],
            "market_close_time_metadata_missing",
        )
        self.assertIn(
            "authoritative market close-time metadata is missing", payload["errors"][0]
        )
        self.assertEqual(session.calls, [])

    def test_cli_unknown_close_metadata_never_constructs_http_or_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "must-not-exist.csv"
            stdout = io.StringIO()
            with (
                patch.object(
                    importer, "us_equity_market_close_time_et", return_value=None
                ),
                patch.object(importer.requests, "Session") as session_constructor,
                patch.object(importer, "_write_csv") as write_csv,
                patch.object(
                    importer, "import_historical_option_snapshots"
                ) as import_rows,
                redirect_stdout(stdout),
            ):
                exit_code = importer.main(
                    [
                        "--date-from",
                        "2021-12-30",
                        "--date-to",
                        "2021-12-30",
                        "--symbols",
                        "SPY",
                        "--csv-output",
                        str(csv_path),
                        "--json",
                    ]
                )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            output["unsupported_market_sessions"][0]["reason"],
            "market_close_time_metadata_missing",
        )
        session_constructor.assert_not_called()
        write_csv.assert_not_called()
        import_rows.assert_not_called()
        self.assertFalse(csv_path.exists())

    def test_cli_early_close_preflight_is_nonzero_without_require_complete_and_never_writes(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "must-not-exist.csv"
            stdout = io.StringIO()
            with (
                patch.object(importer, "_write_csv") as write_csv,
                patch.object(
                    importer, "import_historical_option_snapshots"
                ) as import_rows,
                redirect_stdout(stdout),
            ):
                exit_code = importer.main(
                    [
                        "--date-from",
                        "2021-11-24",
                        "--date-to",
                        "2021-11-26",
                        "--symbols",
                        "SPY",
                        "--csv-output",
                        str(csv_path),
                        "--json",
                    ]
                )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            output["status"], "blocked_preflight_unsupported_market_session_time"
        )
        self.assertTrue(output["write_blocked_by_incomplete_surface"])
        self.assertIsNone(output["csv_path"])
        self.assertFalse(csv_path.exists())
        write_csv.assert_not_called()
        import_rows.assert_not_called()

    def test_cli_binds_each_request_to_csv_hash_and_import_batch(self):
        request_result = {
            "request_id": "FCX:2026-05-15",
            "symbol": "FCX",
            "date": "2026-05-15",
            "status": "request_complete",
            "provider_request_succeeded": True,
            "requested_right": "both",
            "min_dte": 5,
            "max_dte": 60,
            "start_time": "15:55:00",
            "end_time": "15:55:00",
            "provider_response_row_count": 2,
            "normalized_row_count": 2,
            "call_row_count": 1,
            "put_row_count": 1,
            "lineage_rejection_count": 0,
            "observed_min_dte": 35,
            "observed_max_dte": 35,
            "first_provider_timestamp_utc": "2026-05-15T19:55:00Z",
            "last_provider_timestamp_utc": "2026-05-15T19:55:00Z",
        }
        complete_build = {
            "status": "request_surface_complete",
            "source": importer.DEFAULT_SOURCE_LABEL,
            "request_surface_complete": True,
            "expected_request_count": 1,
            "request_count": 1,
            "successful_request_count": 1,
            "failed_request_count": 0,
            "empty_request_count": 0,
            "generated_rows": 1,
            "rows_by_symbol": {"FCX": 1},
            "rows_by_date": {"2026-05-15": 1},
            "rows_by_right": {"call": 1, "put": 1},
            "skipped_rows": {},
            "errors": [],
            "request_errors": [],
            "empty_requests": [],
            "request_results": [request_result],
            "unsupported_market_sessions": [],
            "chain_completeness": importer._unproved_chain_completeness(
                limitation="not exhaustive"
            ),
            "rows": [
                {
                    "as_of_utc": "2026-05-15T19:55:00Z",
                    "underlying": "FCX",
                    "contract_symbol": "FCX260619C00055000",
                    "expiry": "2026-06-19",
                    "option_type": "call",
                    "strike": "55",
                    "bid": "1",
                    "ask": "1.1",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as raw_temp_dir:
            temp_dir = Path(raw_temp_dir)
            csv_path = temp_dir / "quotes.csv"
            db_path = temp_dir / "quotes.sqlite3"
            stdout = io.StringIO()

            def fake_import(path, source, **_kwargs):
                return {
                    "db_path": str(db_path),
                    "batch_id": 17,
                    "file_hash": importer._file_sha256(Path(path)),
                    "source_label": source,
                    "data_trust": "trusted",
                    "dataset_kind": "intraday_csv",
                    "input_path": str(Path(path)),
                    "total_rows": 1,
                    "imported_rows": 1,
                    "duplicate_rows": 0,
                    "rejected_rows": 0,
                }

            with (
                patch.object(
                    importer, "build_thetadata_nbbo_import", return_value=complete_build
                ),
                patch.object(
                    importer,
                    "import_historical_option_snapshots",
                    side_effect=fake_import,
                ),
                redirect_stdout(stdout),
            ):
                exit_code = importer.main(
                    [
                        "--date-from",
                        "2026-05-15",
                        "--date-to",
                        "2026-05-15",
                        "--symbols",
                        "FCX",
                        "--csv-output",
                        str(csv_path),
                        "--db-path",
                        str(db_path),
                        "--snapshot-kind",
                        "intraday",
                        "--require-complete",
                        "--json",
                    ]
                )

            output = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertTrue(output["database_import_complete"])
        lineage = output["request_results"][0]["artifact_lineage"]
        self.assertEqual(lineage["csv_sha256"], output["csv_artifact"]["sha256"])
        self.assertEqual(lineage["import_batch_id"], 17)
        self.assertEqual(lineage["import_file_hash"], output["csv_artifact"]["sha256"])
        self.assertEqual(Path(lineage["import_db_path"]), db_path)
        self.assertTrue(lineage["database_import_complete"])

    def test_require_complete_blocks_csv_and_database_writes(self):
        incomplete_build = {
            "status": "blocked_request_surface_incomplete",
            "source": importer.DEFAULT_SOURCE_LABEL,
            "request_surface_complete": False,
            "expected_request_count": 1,
            "request_count": 0,
            "successful_request_count": 0,
            "failed_request_count": 1,
            "empty_request_count": 0,
            "generated_rows": 1,
            "rows_by_symbol": {"FCX": 1},
            "rows_by_date": {"2026-05-15": 1},
            "skipped_rows": {},
            "errors": ["provider unavailable"],
            "request_errors": [{"symbol": "FCX", "date": "2026-05-15"}],
            "empty_requests": [],
            "rows": [{"contract_symbol": "FCX260619C00055000"}],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "should-not-exist.csv"
            stdout = io.StringIO()
            with (
                patch.object(
                    importer,
                    "build_thetadata_nbbo_import",
                    return_value=incomplete_build,
                ),
                patch.object(importer, "_write_csv") as write_csv,
                patch.object(
                    importer, "import_historical_option_snapshots"
                ) as import_rows,
                redirect_stdout(stdout),
            ):
                exit_code = importer.main(
                    [
                        "--date-from",
                        "2026-05-15",
                        "--date-to",
                        "2026-05-15",
                        "--symbols",
                        "FCX",
                        "--csv-output",
                        str(csv_path),
                        "--require-complete",
                        "--json",
                    ]
                )

        output = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertTrue(output["write_blocked_by_incomplete_surface"])
        self.assertIsNone(output["csv_path"])
        self.assertFalse(csv_path.exists())
        write_csv.assert_not_called()
        import_rows.assert_not_called()


if __name__ == "__main__":
    unittest.main()
