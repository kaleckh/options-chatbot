"""End-to-end 2018-2021 research pipeline gated by verified quote imports.

The quote-import driver is the sole import/retry owner. This pipeline consumes
only its exact-spec, complete-verified manifest and never infers completion
from the legacy append-only progress log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_fresh_window_2018_2021_quote_imports as import_driver  # noqa: E402


LOG = ROOT / "data" / "options-validation" / "fresh_window_pipeline.log"
DEFAULT_IMPORT_MANIFEST = (
    ROOT / "data" / "options-validation" / "fresh_window_2018_2021_import_manifest.json"
)
FF = ROOT / "data" / "profitability-lab" / "regular-options-filter-family-fresh-window"
UNIVERSE = "SPY,QQQ,IWM,DIA,AAPL,GOOGL,UNH,LLY,JNJ,XOM,CVX,COP,NEM"
WINDOW = {
    "start": "2018-01-01",
    "end": "2020-06-30",
    "as_of": "2020-06-30",
    "lookback": "2017-10-01",
}
TRAIN_SPLIT_END_HINT = "family_train per data/contracts/regular-options-filter-family-fresh-window-contract-v1.json"
MISSING_FORMAL_EVALUATION_PATH_BLOCKERS = (
    "missing_f2_session_time_alignment_scoring_path",
    "missing_top3_family_member_selection_path",
    "missing_formal_one_shot_family_validation_path",
    "missing_consumption_registry_append_path",
)


def log(msg: str, *, path: Path | None = None) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    target = path or LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf8") as handle:
        handle.write(f"{stamp} {msg}\n")


def run(label: str, args: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        log(
            f"STAGE FAILED {label}: exit {result.returncode} | {tail[-1][:200] if tail else 'no output'}"
        )
        raise SystemExit(1)
    log(f"stage ok: {label}")


def artifact_status(path: Path, *, allow_blockers: bool = False) -> dict:
    payload = json.loads(path.read_text(encoding="utf8"))
    status = str(payload.get("status") or "")
    blockers = payload.get("blockers") or []
    log(f"  -> {path.parent.name}: {status} | blockers: {blockers}")
    if blockers and not allow_blockers:
        log(f"STAGE BLOCKED {path.parent.name}: {blockers}")
        raise SystemExit(1)
    return payload


def validate_import_manifest(
    payload: dict, expected_plan: dict, *, db_path: Path
) -> list[str]:
    return import_driver.revalidate_complete_manifest_database(
        payload,
        expected_plan,
        db_path=db_path,
    )


def wait_for_imports(
    *,
    manifest_path: Path = DEFAULT_IMPORT_MANIFEST,
    max_hours: float = 30.0,
    poll_seconds: float = 300.0,
    expected_plan: dict | None = None,
    db_path: Path | None = None,
    log_path: Path | None = None,
) -> dict:
    plan = expected_plan or import_driver.build_plan(
        db_path=db_path or import_driver.DEFAULT_DB
    )
    bound_db_path = Path(
        str((plan.get("database_identity") or {}).get("resolved_path") or "")
    )
    selected_db_path = (db_path or bound_db_path).resolve()
    if not str(bound_db_path) or selected_db_path != bound_db_path.resolve():
        log(
            "import manifest/database binding rejected: selected DB path does not match the exact plan",
            path=log_path,
        )
        raise SystemExit(1)
    preflight_blockers = list((plan.get("preflight") or {}).get("blockers") or [])
    if preflight_blockers:
        log(
            "fresh-window exact-plan preflight blocked before downstream work: "
            + json.dumps(plan.get("preflight") or {}, sort_keys=True),
            path=log_path,
        )
        raise SystemExit(1)
    deadline = time.time() + max_hours * 3600
    while True:
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf8"))
            except (OSError, json.JSONDecodeError) as exc:
                log(
                    f"import manifest unreadable: {type(exc).__name__}: {exc}",
                    path=log_path,
                )
                raise SystemExit(1) from exc
            if not isinstance(payload, dict):
                log("import manifest is not a JSON object", path=log_path)
                raise SystemExit(1)
            compatibility_errors = import_driver.manifest_validation_errors(
                payload, plan, require_complete=False
            )
            if compatibility_errors:
                log(
                    f"import manifest rejected as incompatible: {compatibility_errors}",
                    path=log_path,
                )
                raise SystemExit(1)
            status = str(payload.get("status") or "")
            if status == "complete_verified":
                errors = validate_import_manifest(
                    payload, plan, db_path=selected_db_path
                )
                if errors:
                    log(
                        f"import manifest/database completion rejected: {errors}",
                        path=log_path,
                    )
                    raise SystemExit(1)
                log(
                    "imports complete_verified after read-only per-chunk DB revalidation; "
                    f"spec_hash={payload.get('spec_hash')} db={selected_db_path}",
                    path=log_path,
                )
                return payload
            if status.startswith("blocked") or status == "crashed":
                log(
                    f"import manifest is terminally blocked: {status} | {payload.get('last_error')}",
                    path=log_path,
                )
                raise SystemExit(1)
        if time.time() >= deadline:
            log("TIMEOUT waiting for verified quote-import manifest", path=log_path)
            raise SystemExit(1)
        time.sleep(max(0.0, poll_seconds))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the fresh-window research pipeline after verified quote imports."
    )
    parser.add_argument("--import-manifest", type=Path, default=DEFAULT_IMPORT_MANIFEST)
    parser.add_argument("--max-wait-hours", type=float, default=30.0)
    parser.add_argument("--poll-seconds", type=float, default=300.0)
    parser.add_argument("--db-path", type=Path, default=import_driver.DEFAULT_DB)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    log("pipeline start: waiting for verified 2018-2021 quote imports")
    import_manifest = wait_for_imports(
        manifest_path=args.import_manifest,
        max_hours=float(args.max_wait_hours),
        poll_seconds=float(args.poll_seconds),
        db_path=args.db_path,
    )
    chain_standard_errors = import_driver.chain_completeness_standard_errors(
        import_manifest
    )
    if chain_standard_errors:
        log(
            "PIPELINE_BLOCKED_CHAIN_COMPLETENESS_STANDARD: downstream selection/evaluation stages were not "
            f"started; standard={import_driver.CHAIN_COMPLETENESS_STANDARD_VERSION}; "
            f"errors={chain_standard_errors}; backup_retirement_authorized=false; "
            "seal_retirement_authorized=false"
        )
        return 1

    log("stage: feature store")
    run(
        "feature-store",
        [
            "scripts/build_regular_options_feature_store.py",
            "--db-path",
            str(args.db_path.resolve()),
            "--output-dir",
            str(FF / "feature-store"),
            "--docs-report",
            str(FF / "feature-store" / "report.md"),
        ],
    )
    artifact_status(FF / "feature-store" / "latest.json", allow_blockers=True)

    log("stage: underlying daily source import")
    run(
        "underlying-daily",
        [
            "scripts/import_regular_options_underlying_daily_history.py",
            "--source-file",
            "data/import-staging/underlying_daily/point_in_time_underlying_daily_ohlcv_adjusted_ff2018_v1.csv",
            "--lookback-start-date",
            WINDOW["lookback"],
            "--target-start-date",
            WINDOW["start"],
            "--target-end-date",
            WINDOW["end"],
            "--as-of-date",
            WINDOW["as_of"],
            "--universe",
            UNIVERSE,
            "--source-family",
            "point_in_time_underlying_daily_ohlcv_adjusted_v1",
            "--approval-token",
            "APPROVE_UNDERLYING_DAILY_HISTORY_SOURCE_IMPORT",
            "--no-replay",
            "--source-rows",
            str(FF / "underlying-daily-history" / "source_rows.jsonl"),
            "--feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--output-dir",
            str(FF / "underlying-daily-source-import"),
            "--docs-report",
            str(FF / "underlying-daily-source-import" / "report.md"),
        ],
    )
    artifact_status(FF / "underlying-daily-source-import" / "latest.json")

    log("stage: VIX source + bucket")
    run(
        "vix-import",
        [
            "scripts/import_regular_options_direct_vix_source.py",
            "--source-file",
            "data/import-staging/vix/cboe_vix_daily_history.csv",
            "--lookback-start-date",
            WINDOW["lookback"],
            "--target-start-date",
            WINDOW["start"],
            "--target-end-date",
            WINDOW["end"],
            "--as-of-date",
            WINDOW["as_of"],
            "--approval-token",
            "APPROVE_DIRECT_VIX_SOURCE_IMPORT",
            "--no-replay",
            "--feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--source-rows",
            str(FF / "point-in-time-vix-bucket" / "source_rows.jsonl"),
            "--output-dir",
            str(FF / "direct-vix-source-import"),
            "--docs-report",
            str(FF / "direct-vix-source-import" / "report.md"),
        ],
    )
    run(
        "vix-bucket",
        [
            "scripts/build_regular_options_point_in_time_vix_bucket.py",
            "--source-rows",
            str(FF / "point-in-time-vix-bucket" / "source_rows.jsonl"),
            "--feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--output-dir",
            str(FF / "point-in-time-vix-bucket"),
            "--docs-report",
            str(FF / "point-in-time-vix-bucket" / "report.md"),
        ],
    )
    artifact_status(FF / "point-in-time-vix-bucket" / "latest.json")

    log("stage: earnings calendar")
    run(
        "earnings-import",
        [
            "scripts/import_regular_options_earnings_calendar.py",
            "--source-file",
            "data/import-staging/earnings/sec_item202_earnings_ff2018_v1.csv",
            "--target-start-date",
            WINDOW["start"],
            "--target-end-date",
            WINDOW["end"],
            "--approval-token",
            "APPROVE_EARNINGS_CALENDAR_SOURCE_IMPORT",
            "--no-replay",
            "--source-rows",
            str(FF / "point-in-time-earnings-calendar" / "source_rows.jsonl"),
            "--output-dir",
            str(FF / "earnings-calendar-source-import"),
            "--docs-report",
            str(FF / "earnings-calendar-source-import" / "report.md"),
        ],
    )
    run(
        "earnings-calendar",
        [
            "scripts/build_regular_options_point_in_time_earnings_calendar.py",
            "--source-rows",
            str(FF / "point-in-time-earnings-calendar" / "source_rows.jsonl"),
            "--start-date",
            WINDOW["start"],
            "--end-date",
            WINDOW["end"],
            "--output-dir",
            str(FF / "point-in-time-earnings-calendar"),
            "--docs-report",
            str(FF / "point-in-time-earnings-calendar" / "report.md"),
        ],
    )
    artifact_status(FF / "point-in-time-earnings-calendar" / "latest.json")

    log("stage: market-regime inputs")
    run(
        "market-regime",
        [
            "scripts/build_regular_options_point_in_time_market_regime_inputs.py",
            "--feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--underlying-source-rows",
            str(FF / "underlying-daily-history" / "source_rows.jsonl"),
            "--underlying-source-import-report",
            str(FF / "underlying-daily-source-import" / "latest.json"),
            "--start-date",
            WINDOW["start"],
            "--end-date",
            WINDOW["end"],
            "--as-of-date",
            WINDOW["as_of"],
            "--output-dir",
            str(FF / "point-in-time-market-regime-inputs"),
            "--docs-report",
            str(FF / "point-in-time-market-regime-inputs" / "report.md"),
        ],
    )
    artifact_status(FF / "point-in-time-market-regime-inputs" / "latest.json")

    log("stage: input-surface tracker")
    run(
        "tracker",
        [
            "scripts/build_regular_options_historical_scanner_input_surface_tracker.py",
            "--source-feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--market-regime-inputs",
            str(FF / "point-in-time-market-regime-inputs" / "latest.json"),
            "--vix-bucket",
            str(FF / "point-in-time-vix-bucket" / "latest.json"),
            "--underlying-daily-source-rows",
            str(FF / "underlying-daily-history" / "source_rows.jsonl"),
            "--alpaca-minute-source-rows",
            str(FF / "alpaca-underlying-minute-price-surface" / "source_rows.jsonl"),
            "--earnings-calendar",
            str(FF / "point-in-time-earnings-calendar" / "latest.json"),
            "--options-history-db",
            str(args.db_path.resolve()),
            "--start-date",
            WINDOW["start"],
            "--end-date",
            WINDOW["end"],
            "--as-of-date",
            WINDOW["as_of"],
            "--output-dir",
            str(FF / "historical-scanner-input-surface-tracker"),
            "--docs-report",
            str(FF / "historical-scanner-input-surface-tracker" / "report.md"),
        ],
    )
    tracker = artifact_status(
        FF / "historical-scanner-input-surface-tracker" / "latest.json",
        allow_blockers=True,
    )
    surfaces = tracker.get("surface_readiness") or {}
    entry_ok = (surfaces.get("entry_underlying_price_surface") or {}).get(
        "available"
    ) is True
    chain_ok = (surfaces.get("option_chain_selection_surface") or {}).get(
        "available"
    ) is True
    if not (entry_ok and chain_ok):
        log(
            f"STAGE BLOCKED tracker surfaces: entry={entry_ok} chain={chain_ok} - review missing provider pairs"
        )
        raise SystemExit(1)

    log(f"stage: F1 family_train diagnostic materialization ({TRAIN_SPLIT_END_HINT})")
    run(
        "gate-variant-replay",
        [
            "scripts/research_regular_options_gate_variant_replay.py",
            "--split",
            "family_train",
            "--import-manifest",
            str(args.import_manifest.resolve()),
            "--feature-store",
            str(FF / "feature-store" / "latest.json"),
            "--market-regime-inputs",
            str(FF / "point-in-time-market-regime-inputs" / "latest.json"),
            "--vix-bucket",
            str(FF / "point-in-time-vix-bucket" / "latest.json"),
            "--input-surface-tracker",
            str(FF / "historical-scanner-input-surface-tracker" / "latest.json"),
            "--earnings-calendar",
            str(FF / "point-in-time-earnings-calendar" / "latest.json"),
            "--options-db",
            str(args.db_path.resolve()),
            "--output-dir",
            str(FF / "gate-variant-replay"),
        ],
    )
    gate_report = artifact_status(
        FF / "gate-variant-replay" / "family_train_latest.json"
    )
    if (
        gate_report.get("status")
        not in {
            "diagnostic_only_incomplete_quote_surface",
            "diagnostic_only_incomplete_family_train",
        }
        or gate_report.get("diagnostic_materializer_ready") is not True
        or gate_report.get("selection_eligible") is not False
        or gate_report.get("evaluation_ready") is not False
    ):
        log(f"STAGE BLOCKED gate-variant-replay status: {gate_report.get('status')}")
        raise SystemExit(1)
    missing_paths = sorted(
        set(MISSING_FORMAL_EVALUATION_PATH_BLOCKERS)
        | {
            str(item)
            for item in (gate_report.get("validation_pending_blockers") or [])
            if str(item)
        }
    )
    log(
        "PIPELINE_BLOCKED_INCOMPLETE_CONTRACT: family_train output is diagnostic-only; "
        f"missing_paths={missing_paths}; backup_retirement_authorized=false; seal_retirement_authorized=false"
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - operational logging
        log(f"CRASHED {type(exc).__name__}: {exc}")
        raise
