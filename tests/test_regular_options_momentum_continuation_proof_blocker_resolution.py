from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from scripts import build_regular_options_momentum_continuation_proof_blocker_resolution as resolution
from workspace_tempdir import WorkspaceTempDir


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _trade(**overrides: object) -> dict:
    row = {
        "ticker": "QQQ",
        "date": "2025-08-14",
        "exit_date": "2025-09-11",
        "strategy_type": "vertical_spread",
        "type": "call",
        "contract_symbol": "QQQ250912C00581000",
        "short_contract_symbol": "QQQ250912C00600000",
        "net_debit": 8.40,
        "entry_spread_ask_bid_debit": 8.40,
        "net_pnl_usd": 203.40,
        "truth_source": "historical_imported",
        "execution_realism": "quote_backed_intraday_replay",
        "spy_ret5": 1.2,
        "qqq_ret5": 1.6,
        "vix_bucket": "low_mid",
        "breadth_confirmation": "confirmed",
        "long_entry_quote_basis": "ask_bid",
        "short_entry_quote_basis": "ask_bid",
    }
    row.update(overrides)
    return row


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        create table import_batches (
            id integer primary key,
            source_label text not null,
            dataset_kind text not null,
            data_trust text not null,
            input_path text not null,
            file_hash text not null,
            imported_at_utc text not null,
            total_rows integer not null,
            imported_rows integer not null,
            duplicate_rows integer not null,
            rejected_rows integer not null,
            warnings_json text not null
        )
        """
    )
    conn.execute(
        """
        create table option_quote_snapshots (
            id integer primary key,
            as_of_utc text not null,
            quote_date_et text not null,
            quote_minute_et integer not null,
            snapshot_kind text not null,
            underlying text not null,
            contract_symbol text not null,
            expiry text not null,
            option_type text not null,
            strike real not null,
            bid real,
            ask real,
            last real,
            iv real,
            underlying_price real,
            volume integer,
            open_interest integer,
            source_batch_id integer not null
        )
        """
    )
    conn.execute(
        "insert into import_batches values (1, 'thetadata_opra_nbbo_1m', 'intraday_csv', 'trusted', 'fixture', 'hash', '2026-06-23T00:00:00Z', 4, 4, 0, 0, '[]')"
    )
    rows = [
        ("2025-08-14", 625, "QQQ250912C00581000", 10.0, 10.1, 581.0),
        ("2025-08-14", 625, "QQQ250912C00600000", 1.8, 1.9, 600.0),
        ("2025-09-11", 959, "QQQ250912C00581000", 13.0, 13.2, 581.0),
        ("2025-09-11", 959, "QQQ250912C00600000", 2.0, 2.1, 600.0),
    ]
    for quote_date, minute, contract, bid, ask, strike in rows:
        conn.execute(
            """
            insert into option_quote_snapshots (
                as_of_utc, quote_date_et, quote_minute_et, snapshot_kind, underlying,
                contract_symbol, expiry, option_type, strike, bid, ask, last, iv,
                underlying_price, volume, open_interest, source_batch_id
            )
            values (?, ?, ?, 'intraday', 'QQQ', ?, '2025-09-12', 'call', ?, ?, ?, null, null, null, 0, 0, 1)
            """,
            (f"{quote_date}T16:00:00Z", quote_date, minute, contract, strike, bid, ask),
        )
    conn.commit()
    conn.close()


def _vix_bucket(path: Path, *, ready: bool = True, dates: list[str] | None = None) -> None:
    rows = []
    for entry_date in dates or ["2025-08-14"]:
        rows.append(
            {
                "bucket_date_et": entry_date,
                "vix_value": 14.2,
                "vix_bucket": "low",
                "low_mid_eligible": True,
                "source_name": "fixture_vix",
                "source_ref": f"fixture://vix/{entry_date}",
                "source_timestamp_utc": "2025-08-13T21:15:00Z",
                "known_at_utc": "2025-08-13T21:16:00Z",
                "point_in_time_valid": True,
                "source_provenance_status": "trusted_local_or_contract_declared",
                "source_frequency": "daily_close",
                "proof_eligible": False,
            }
        )
    _write_json(
        path,
        {
            "report_id": "regular_options_point_in_time_vix_bucket",
            "status": "point_in_time_vix_bucket_ready" if ready else "blocked_point_in_time_vix_bucket_validation",
            "point_in_time_vix_low_mid_bucket_available": ready,
            "blockers": [] if ready else ["point_in_time_vix_row_validation_failed"],
            "bucket_rows": rows,
        },
    )


def _market_regime_inputs(
    path: Path,
    *,
    ready: bool = True,
    dates: list[str] | None = None,
    spy: bool = True,
    qqq: bool = True,
    breadth: bool = True,
    historical_reconstruction: bool = False,
) -> None:
    rows = []
    for entry_date in dates or ["2025-08-14"]:
        rows.append(
            {
                "input_date_et": entry_date,
                "point_in_time_valid": not historical_reconstruction,
                "source_time_status": "historical_prior_bar_reconstruction" if historical_reconstruction else "source_known_before_input_date",
                "historical_prior_bar_reconstruction": historical_reconstruction,
                "spy_momentum_confirmed": spy,
                "qqq_momentum_confirmed": qqq,
                "breadth_confirmed": breadth,
                "breadth_ratio": 0.77 if breadth else 0.31,
                "available_symbol_count": 13,
                "above_prior_50_sma_symbol_count": 10 if breadth else 4,
                "blockers": ["market_regime_source_time_not_point_in_time"] if historical_reconstruction else [],
                "proof_eligible": False,
            }
        )
    source_time_mode = (
        "historical_prior_bar_reconstruction"
        if historical_reconstruction
        else "point_in_time_verified_daily_history"
    )
    _write_json(
        path,
        {
            "report_id": "regular_options_point_in_time_market_regime_inputs",
            "status": "point_in_time_market_regime_inputs_ready" if ready and not historical_reconstruction else "blocked_point_in_time_market_regime_inputs",
            "blockers": [] if ready and not historical_reconstruction else ["market_regime_source_time_not_point_in_time"],
            "point_in_time_market_regime_inputs_available": ready and not historical_reconstruction,
            "source_time_policy": {
                "source_time_mode": source_time_mode,
                "historical_reconstruction_can_clear_point_in_time_blockers": False,
            },
            "coverage": {
                "requested_month_count": 1,
                "covered_month_count": 1 if ready and not historical_reconstruction else 0,
                "requested_date_count": len(rows),
                "covered_date_count": len(rows) if ready and not historical_reconstruction else 0,
                "date_coverage_pct": 100.0 if ready and not historical_reconstruction else 0.0,
            },
            "input_rows": rows,
        },
    )


class MomentumContinuationProofBlockerResolutionTests(unittest.TestCase):
    def _fixture_paths(self, tmp: Path, trades: list[dict]) -> dict[str, Path]:
        run = tmp / "runs" / "momentum_run.json"
        _write_json(
            run,
            {
                "playbook": "fixture_momentum",
                "truth_source": "historical_imported",
                "execution_realism": "quote_backed_intraday_replay",
                "imported_data_scope": "trusted",
                "entry_quote_time_et": "10:10 ET + 15m",
                "trades": trades,
                "unpriced_trades": [],
            },
        )
        all_planned = tmp / "all_planned.json"
        _write_json(all_planned, {"variants": [{"variant_id": "fixture_momentum", "run_path": str(run)}]})
        source_replay = tmp / "source_replay.json"
        _write_json(
            source_replay,
            {
                "concept_id": resolution.CONCEPT_ID,
                "research_only_replay_harness_implemented": True,
                "accepted_profitability": False,
                "denominator": {"row_count": len(trades)},
                "proof_qualified": {"row_count": 0},
                "diagnostic_only_existing_marks": {"metrics": {"row_count": len(trades), "profit_factor": 0.75}},
            },
        )
        prereg = tmp / "prereg.json"
        _write_json(prereg, {"status": "preregistered_design_only", "concept_id": resolution.CONCEPT_ID})
        vix_bucket = tmp / "vix_bucket.json"
        _vix_bucket(vix_bucket)
        market_regime = tmp / "missing_market_regime.json"
        db = tmp / "options_history.db"
        _make_db(db)
        return {
            "source_replay_path": source_replay,
            "preregistered_playbook_path": prereg,
            "point_in_time_vix_bucket_path": vix_bucket,
            "point_in_time_market_regime_inputs_path": market_regime,
            "all_planned_path": all_planned,
            "options_db_path": db,
            "runs_dir": tmp / "runs",
        }

    def test_resolves_strict_row_when_all_inputs_and_quotes_exist(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            paths = self._fixture_paths(Path(tmp_dir), [_trade()])
            report = resolution.build_report(generated_at_utc="2026-06-23T00:00:00Z", **paths)

        self.assertEqual(report["proof_qualified_rows_after_resolution"], 1)
        self.assertEqual(report["resolution_counts"]["side_aware_quotes_resolved"], 1)
        self.assertEqual(report["strict_research_metrics"]["net_pnl_usd"], 257.4)
        self.assertFalse(report["accepted_profitability"])
        self.assertFalse(report["historical_rows_are_forward_proof"])

    def test_missing_point_in_time_inputs_fail_closed_despite_quotes(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            trade = _trade(vix_bucket=None, breadth_confirmation=None)
            paths = self._fixture_paths(Path(tmp_dir), [trade])
            report = resolution.build_report(**paths)

        self.assertEqual(report["status"], "momentum_continuation_blocked_missing_local_proof_inputs")
        self.assertEqual(report["proof_qualified_rows_after_resolution"], 0)
        self.assertEqual(report["resolution_counts"]["side_aware_quotes_resolved"], 1)
        self.assertEqual(report["resolution_counts"]["point_in_time_vix_bucket_resolved"], 1)
        self.assertEqual(report["source_artifacts"]["point_in_time_market_regime_inputs"]["path"], str(Path(paths["point_in_time_market_regime_inputs_path"]).as_posix()).replace("\\", "/"))
        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertNotIn("missing_point_in_time_vix_bucket", blockers)
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)

    def test_blocked_vix_artifact_preserves_missing_vix_blocker(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            trade = _trade(vix_bucket=None, breadth_confirmation=None)
            paths = self._fixture_paths(Path(tmp_dir), [trade])
            _vix_bucket(paths["point_in_time_vix_bucket_path"], ready=False)
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertEqual(report["resolution_counts"]["point_in_time_vix_bucket_resolved"], 0)
        self.assertEqual(blockers["missing_point_in_time_vix_bucket"], 1)
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)

    def test_missing_vix_date_preserves_missing_vix_blocker(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            trade = _trade(vix_bucket=None, breadth_confirmation=None)
            paths = self._fixture_paths(Path(tmp_dir), [trade])
            _vix_bucket(paths["point_in_time_vix_bucket_path"], dates=["2025-08-13"])
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertEqual(report["resolution_counts"]["point_in_time_vix_bucket_resolved"], 0)
        self.assertEqual(blockers["missing_point_in_time_vix_bucket"], 1)
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)

    def test_ready_market_regime_artifact_clears_true_confirmation_blockers(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                ticker="AAPL",
                vix_bucket=None,
                breadth_confirmation=None,
                spy_ret5=None,
                qqq_ret5=None,
                qqq_ret20=None,
            )
            paths = self._fixture_paths(tmp, [trade])
            market = tmp / "market_regime.json"
            _market_regime_inputs(market)
            paths["point_in_time_market_regime_inputs_path"] = market
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertNotIn("missing_point_in_time_breadth_confirmation", blockers)
        self.assertNotIn("missing_point_in_time_spy_momentum_confirmation", blockers)
        self.assertNotIn("missing_point_in_time_qqq_momentum_confirmation", blockers)
        self.assertEqual(report["resolution_counts"]["point_in_time_breadth_confirmation_resolved"], 1)
        self.assertEqual(report["resolution_counts"]["point_in_time_spy_momentum_confirmation_resolved"], 1)
        self.assertEqual(report["resolution_counts"]["point_in_time_qqq_momentum_confirmation_resolved"], 1)

    def test_false_market_regime_confirmations_become_rejections_not_missing_passes(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                ticker="AAPL",
                vix_bucket=None,
                breadth_confirmation=None,
                spy_ret5=None,
                qqq_ret5=None,
                qqq_ret20=None,
            )
            paths = self._fixture_paths(tmp, [trade])
            market = tmp / "market_regime.json"
            _market_regime_inputs(market, spy=False, qqq=False, breadth=False)
            paths["point_in_time_market_regime_inputs_path"] = market
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertNotIn("missing_point_in_time_breadth_confirmation", blockers)
        self.assertNotIn("missing_point_in_time_spy_momentum_confirmation", blockers)
        self.assertNotIn("missing_point_in_time_qqq_momentum_confirmation", blockers)
        self.assertEqual(blockers["rejected_no_breadth_confirmation"], 1)
        self.assertEqual(blockers["rejected_no_spy_momentum_confirmation"], 1)
        self.assertEqual(blockers["rejected_no_qqq_momentum_confirmation"], 1)
        self.assertEqual(report["proof_qualified_rows_after_resolution"], 0)

    def test_blocked_market_regime_artifact_preserves_missing_confirmation_blockers(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                ticker="AAPL",
                vix_bucket=None,
                breadth_confirmation=None,
                spy_ret5=None,
                qqq_ret5=None,
                qqq_ret20=None,
            )
            paths = self._fixture_paths(tmp, [trade])
            market = tmp / "market_regime_blocked.json"
            _market_regime_inputs(market, ready=False)
            paths["point_in_time_market_regime_inputs_path"] = market
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertEqual(report["point_in_time_market_regime_input_resolution"]["artifact_ready_for_stale_blocker_clear"], False)
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_spy_momentum_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_qqq_momentum_confirmation"], 1)

    def test_missing_market_regime_date_preserves_missing_confirmation_blockers(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                ticker="AAPL",
                vix_bucket=None,
                breadth_confirmation=None,
                spy_ret5=None,
                qqq_ret5=None,
                qqq_ret20=None,
            )
            paths = self._fixture_paths(tmp, [trade])
            market = tmp / "market_regime_wrong_date.json"
            _market_regime_inputs(market, dates=["2025-08-13"])
            paths["point_in_time_market_regime_inputs_path"] = market
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertEqual(report["point_in_time_market_regime_input_resolution"]["valid_input_date_count"], 1)
        self.assertEqual(report["point_in_time_market_regime_input_resolution"]["resolved_row_count"], 0)
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_spy_momentum_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_qqq_momentum_confirmation"], 1)

    def test_historical_market_regime_reconstruction_cannot_clear_point_in_time_blockers(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            trade = _trade(
                ticker="AAPL",
                vix_bucket=None,
                breadth_confirmation=None,
                spy_ret5=None,
                qqq_ret5=None,
                qqq_ret20=None,
            )
            paths = self._fixture_paths(tmp, [trade])
            market = tmp / "market_regime_historical.json"
            _market_regime_inputs(market, historical_reconstruction=True)
            paths["point_in_time_market_regime_inputs_path"] = market
            report = resolution.build_report(**paths)

        blockers = report["resolution_counts"]["blocker_counts"]
        self.assertEqual(
            report["point_in_time_market_regime_input_resolution"]["source_time_policy"]["source_time_mode"],
            "historical_prior_bar_reconstruction",
        )
        self.assertEqual(
            report["point_in_time_market_regime_input_resolution"]["historical_reconstruction_can_clear_point_in_time_blockers"],
            False,
        )
        self.assertEqual(blockers["missing_point_in_time_breadth_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_spy_momentum_confirmation"], 1)
        self.assertEqual(blockers["missing_point_in_time_qqq_momentum_confirmation"], 1)

    def test_missing_db_blocks_quote_resolution_without_mutation(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            paths = self._fixture_paths(Path(tmp_dir), [_trade()])
            paths["options_db_path"].unlink()
            report = resolution.build_report(**paths)

        self.assertEqual(report["resolution_counts"]["side_aware_quotes_resolved"], 0)
        self.assertIn("entry_missing_leg_quote", report["blockers"])
        self.assertFalse(report["quotes_imported"])
        self.assertFalse(report["evidence_stores_mutated"])

    def test_write_outputs_writes_latest_and_docs(self) -> None:
        with WorkspaceTempDir(prefix="momentum-resolution") as tmp_dir:
            tmp = Path(tmp_dir)
            paths = self._fixture_paths(tmp, [_trade()])
            report = resolution.build_report(**paths)
            artifacts = resolution.write_outputs(report, output_dir=tmp / "out", docs_report=tmp / "docs" / "report.md")

            self.assertTrue((tmp / "out" / "latest.json").exists())
            self.assertTrue((tmp / "out" / "latest.md").exists())
            self.assertTrue((tmp / "docs" / "report.md").exists())
            self.assertIn("docs_report", artifacts)


if __name__ == "__main__":
    unittest.main()
