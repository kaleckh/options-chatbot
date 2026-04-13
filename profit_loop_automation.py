from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pyarrow.parquet as pq

from local_env import load_local_env


ROOT_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, ROOT_DIR / "python-backend"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


def _load_local_env(root_dir: Path = ROOT_DIR) -> list[str]:
    return load_local_env(root_dir)


_ENV_FILES_LOADED = _load_local_env(ROOT_DIR)

from forward_options_ledger import summarize_forward_holdout
from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore
from options_profit_gate import DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS, evaluate_claim_readiness, evaluate_measurement_gate
from profit_loop_shared_state import (
    _infer_loop_execution_status,
    append_run_ledger,
    begin_active_run,
    claim_issue,
    clear_active_run,
    complete_active_run,
    defer_issue,
    ensure_profit_loop_state,
    heartbeat_active_run,
    load_profit_loop_state,
    list_run_ledger_events,
    proof_bundle_dir as shared_proof_bundle_dir,
    prioritized_open_issues,
    reconcile_source_open_issues,
    resolve_issue,
    save_profit_loop_state,
    set_latest_snapshot,
    shared_state_dir,
    upsert_open_issue,
    utc_now_iso,
    validation_prerequisite_blockers,
    auto_resolve_seeded_issues,
)
from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    OPTIONS_VALIDATION_DAILY_LATEST_FILE,
    _is_imported_truth_source,
    run_historical_backtest,
)


DAILY_TRUTH_AUTO_REFRESH_ENV = "OPTIONS_DAILY_TRUTH_AUTO_REFRESH"
DAILY_TRUTH_IMPORT_MANIFEST_ENV = "OPTIONS_DAILY_TRUTH_IMPORT_MANIFEST"
LEGACY_DAILY_TRUTH_IMPORT_MANIFEST_ENV = "HISTORICAL_OPTIONS_IMPORT_MANIFEST"
DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST = ROOT_DIR / "data" / "options-validation" / "daily_truth_import_manifest.json"
DEFAULT_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS = 2
DEFAULT_DAILY_TRUTH_REFRESH_N_PICKS = 1
DEFAULT_DAILY_TRUTH_REFRESH_IV_ADJ = 1.2
DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE = "pessimistic"
DEFAULT_DAILY_TRUTH_REFRESH_PLAYBOOK = "broad"
DEFAULT_DAILY_TRUTH_IMPORT_TIMEOUT_SECONDS = 600
DEFAULT_DAILY_TRUTH_ARTIFACT_TIMEOUT_SECONDS = 1800
DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS = 60
BOOTSTRAP_DOMINANCE_THRESHOLD_PCT = 80.0
BOOTSTRAP_RECOVERY_EXTENDED_LOOKBACK_YEARS = 3

HEALTH_TEST_MODULES = [
    "tests.test_market_data_service",
    "tests.test_historical_options_store",
    "tests.test_options_api_e2e",
]
VALIDATION_TEST_MODULES = [
    "tests.test_options_api_e2e",
    "tests.test_market_data_service",
    "tests.test_metric_truth_audit",
    "tests.test_expectancy_calibration",
    "tests.test_wfo_optimizer_calibration",
    "tests.test_autoresearch_cycle",
]
VALIDATION_REPLAY_CASES = [
    {"lookback_years": 1, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "mid"},
    {"lookback_years": 1, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "pessimistic"},
    {"lookback_years": 2, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "mid"},
    {"lookback_years": 2, "n_picks": 1, "iv_adj": 1.2, "pricing_lane": "pessimistic"},
]
VALIDATION_PRIORITY_NEXT_ACTION = {
    "truth-lane-live-policy-mismatch": "Trace live scan policy loading and align live policy truth provenance with the scan truth lane before trusting unattended validation.",
    "forward-holdout-no-raw-candidates": "Trace candidate starvation through run_supervised_scan and live scan filters to explain why both raw and policy-gated holdout runs emitted zero candidates.",
    "replay-matrix-collapsed-results": "Trace run_historical_backtest inputs and replay selection surfaces to explain why the required replay matrix collapsed to identical cells.",
}
VALIDATION_TEST_PLAN_BY_BLOCKER = {
    "truth_lane_mismatch": ["tests.test_options_api_e2e", "tests.test_expectancy_calibration", "tests.test_wfo_optimizer_calibration"],
    "truth_provenance": ["tests.test_options_api_e2e", "tests.test_expectancy_calibration", "tests.test_wfo_optimizer_calibration"],
    "calibration": ["tests.test_expectancy_calibration", "tests.test_wfo_optimizer_calibration"],
    "scan_starvation": ["tests.test_options_api_e2e"],
    "fail_open": ["tests.test_options_api_e2e"],
    "replay_matrix_suspicious": ["tests.test_metric_truth_audit", "tests.test_wfo_optimizer_calibration"],
    "replay_report_integrity": ["tests.test_metric_truth_audit", "tests.test_wfo_optimizer_calibration"],
    "market_data": ["tests.test_market_data_service", "tests.test_historical_options_store"],
    "storage": ["tests.test_market_data_service", "tests.test_historical_options_store"],
    "test_gap": ["tests.test_autoresearch_cycle"],
}


class ProfitLoopAutomationError(RuntimeError):
    """Raised when a profit-loop automation step cannot finish safely."""


class CommandTimeoutError(ProfitLoopAutomationError):
    """Raised when a subprocess exceeds its bounded runtime."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _command_text(command: list[str]) -> str:
    rendered: list[str] = []
    for item in command:
        rendered.append("python" if str(item) == sys.executable else str(item))
    return " ".join(rendered)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    with contextlib.suppress(Exception):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            process.kill()
    with contextlib.suppress(Exception):
        process.kill()


def _run_command(
    command: list[str],
    *,
    cwd: Path = ROOT_DIR,
    timeout_seconds: int | None = None,
    heartbeat_every_seconds: int | None = None,
    heartbeat: Any = None,
) -> dict[str, Any]:
    if timeout_seconds is None and heartbeat_every_seconds is None and heartbeat is None:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "command": _command_text(command),
            "returncode": int(completed.returncode),
            "passed": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "duration_seconds": None,
        }

    started_at = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    heartbeat_interval = max(int(heartbeat_every_seconds or DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS), 1)
    while True:
        elapsed = time.monotonic() - started_at
        if timeout_seconds is not None and elapsed >= float(timeout_seconds):
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
            raise CommandTimeoutError(
                f"Command timed out after {int(timeout_seconds)}s: {_command_text(command)}\n{stderr or stdout}"
            )
        wait_timeout = float(heartbeat_interval)
        if timeout_seconds is not None:
            wait_timeout = min(wait_timeout, max(float(timeout_seconds) - elapsed, 0.1))
        try:
            stdout, stderr = process.communicate(timeout=wait_timeout)
            duration_seconds = round(time.monotonic() - started_at, 3)
            return {
                "command": _command_text(command),
                "returncode": int(process.returncode or 0),
                "passed": int(process.returncode or 0) == 0,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "duration_seconds": duration_seconds,
            }
        except subprocess.TimeoutExpired:
            if callable(heartbeat):
                heartbeat(
                    {
                        "command": _command_text(command),
                        "pid": process.pid,
                        "elapsed_seconds": int(time.monotonic() - started_at),
                        "timeout_seconds": timeout_seconds,
                    }
                )
            continue


def _run_command_with_retry(
    command: list[str],
    *,
    cwd: Path = ROOT_DIR,
    timeout_seconds: int | None = None,
    heartbeat_every_seconds: int | None = None,
    heartbeat: Any = None,
    max_retries: int = 1,
    timeout_escalation: float = 1.5,
) -> dict[str, Any]:
    """Run a command with retry on timeout. Escalates timeout by multiplier on retry."""
    current_timeout = timeout_seconds
    last_error: Exception | None = None
    for attempt in range(1 + max_retries):
        try:
            result = _run_command(
                command,
                cwd=cwd,
                timeout_seconds=int(current_timeout) if current_timeout is not None else None,
                heartbeat_every_seconds=heartbeat_every_seconds,
                heartbeat=heartbeat,
            )
            if attempt > 0:
                result["retried"] = True
                result["retry_attempt"] = attempt
            return result
        except CommandTimeoutError as exc:
            last_error = exc
            if current_timeout is not None:
                current_timeout = int(current_timeout * timeout_escalation)
    # All retries exhausted
    raise last_error  # type: ignore[misc]


def _run_json_command(
    command: list[str],
    *,
    cwd: Path = ROOT_DIR,
    timeout_seconds: int | None = None,
    heartbeat_every_seconds: int | None = None,
    heartbeat: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _run_command(
        command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        heartbeat_every_seconds=heartbeat_every_seconds,
        heartbeat=heartbeat,
    )
    if not record["passed"]:
        raise ProfitLoopAutomationError(
            f"Command failed: {record['command']}\n{record['stderr'] or record['stdout']}"
        )
    try:
        payload = json.loads(record["stdout"])
    except json.JSONDecodeError as exc:
        raise ProfitLoopAutomationError(
            f"Command did not emit valid JSON: {record['command']}"
        ) from exc
    return payload, record


def _run_unittest_modules(modules: list[str], *, cwd: Path = ROOT_DIR) -> dict[str, Any]:
    return _run_command([sys.executable, "-m", "unittest", *modules, "-v"], cwd=cwd)


def _extract_unittest_count(output: str) -> int | None:
    match = re.search(r"Ran\s+(\d+)\s+tests?", str(output or ""))
    return int(match.group(1)) if match else None


def _extract_unittest_module_status(output: str) -> dict[str, bool]:
    statuses: dict[str, bool] = {}
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("test_") or " ... " not in line:
            continue
        module_name = line.split(" ", 1)[0]
        statuses[module_name] = line.endswith("ok")
    return statuses


def _git_head(repo_root: Path = ROOT_DIR) -> str:
    record = _run_command(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if record["passed"]:
        return str(record["stdout"]).strip()
    return "unknown"


def _env_hash(*, repo_root: Path = ROOT_DIR) -> str:
    payload = {
        "python": sys.executable,
        "version": sys.version,
        "env_files_loaded": list(_ENV_FILES_LOADED),
        "cwd": str(repo_root.resolve()),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf8")).hexdigest()


def _write_json_artifact(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return path


def _read_json_artifact(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def _base_proof_fingerprint(
    *,
    commit_sha: str,
    env_hash: str,
    truth_lane: str = IMPORTED_DAILY_TRUTH_SOURCE,
    playbook: str = "broad",
) -> str:
    encoded = json.dumps(
        {
            "commit_sha": commit_sha,
            "env_hash": env_hash,
            "truth_lane": truth_lane,
            "playbook": playbook,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf8")).hexdigest()


def _validation_fingerprint(
    *,
    commit_sha: str,
    env_hash: str,
    truth_lane: str,
    playbook: str,
    blocker_class: str,
    pricing_spec: str,
    modules: list[str],
) -> str:
    encoded = json.dumps(
        {
            "commit_sha": commit_sha,
            "env_hash": env_hash,
            "truth_lane": truth_lane,
            "playbook": playbook,
            "blocker_class": blocker_class,
            "pricing_spec": pricing_spec,
            "modules": list(modules),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf8")).hexdigest()


def _proof_context(*, repo_root: Path = ROOT_DIR) -> dict[str, Any]:
    commit_sha = _git_head(repo_root)
    env_hash = _env_hash(repo_root=repo_root)
    return {
        "commit_sha": commit_sha,
        "env_hash": env_hash,
        "base_fingerprint": _base_proof_fingerprint(commit_sha=commit_sha, env_hash=env_hash),
        "env_files_loaded": list(_ENV_FILES_LOADED),
    }


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _repo_relative_text(path: str | Path, *, repo_root: Path = ROOT_DIR) -> str:
    value = Path(path).expanduser()
    try:
        return str(value.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(value.resolve())


def _resolve_daily_truth_import_manifest(repo_root: Path = ROOT_DIR) -> tuple[str | None, str | None]:
    for env_name in (DAILY_TRUTH_IMPORT_MANIFEST_ENV, LEGACY_DAILY_TRUTH_IMPORT_MANIFEST_ENV):
        raw = str(os.getenv(env_name) or "").strip()
        if not raw:
            continue
        if raw.startswith(("http://", "https://")):
            return raw, env_name
        return str((repo_root / raw).resolve()) if not Path(raw).is_absolute() else str(Path(raw).resolve()), env_name
    if DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST.exists():
        return str(DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST.resolve()), "default_manifest"
    return None, None


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return None


def _parse_date(raw: Any) -> date | None:
    parsed = _parse_iso_datetime(raw)
    return parsed.date() if parsed is not None else None


def _business_days_stale(truth_horizon: date | None, current_date: date | None) -> int | None:
    if truth_horizon is None or current_date is None:
        return None
    if truth_horizon >= current_date:
        return 0
    day = truth_horizon
    business_days = 0
    while day < current_date:
        day += timedelta(days=1)
        if day.weekday() < 5:
            business_days += 1
    return business_days


def _load_manifest_entries(manifest_path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf8"))
    if isinstance(payload, list):
        entries = payload
    else:
        entries = payload.get("imports")
    if not isinstance(entries, list):
        raise ProfitLoopAutomationError(f"Daily truth manifest is invalid: {manifest_path}")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        normalized.append(dict(entry))
    if not normalized:
        raise ProfitLoopAutomationError(f"Daily truth manifest is empty: {manifest_path}")
    return normalized


def _resolve_manifest_entry_path(value: Any, *, repo_root: Path = ROOT_DIR) -> Path | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _normalize_source_horizon_date(value: Any) -> date | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parquet_source_horizon(path: Path, *, date_column: str = "date") -> date | None:
    try:
        parquet = pq.ParquetFile(path)
    except Exception:
        return None
    names = list(parquet.schema_arrow.names)
    if date_column not in names:
        return None
    column_index = names.index(date_column)
    latest: date | None = None
    try:
        for row_group_index in range(parquet.metadata.num_row_groups):
            stats = parquet.metadata.row_group(row_group_index).column(column_index).statistics
            candidate = _normalize_source_horizon_date(getattr(stats, "max", None))
            if candidate is None:
                latest = None
                break
            if latest is None or candidate > latest:
                latest = candidate
        if latest is not None:
            return latest
    except Exception:
        latest = None
    try:
        table = pq.read_table(path, columns=[date_column], use_threads=False)
    except Exception:
        return None
    values = [
        _normalize_source_horizon_date(item)
        for item in table.column(date_column).to_pylist()
    ]
    values = [item for item in values if item is not None]
    return max(values) if values else None


def _manifest_requested_inputs(entries: list[dict[str, Any]], *, repo_root: Path = ROOT_DIR) -> list[str]:
    requested: list[str] = []
    for entry in entries:
        for key in ("input", "underlying_input"):
            candidate = _resolve_manifest_entry_path(entry.get(key), repo_root=repo_root)
            if candidate is not None:
                requested.append(str(candidate))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in requested:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _daily_truth_source_freshness(
    entries: list[dict[str, Any]],
    *,
    repo_root: Path = ROOT_DIR,
    db_path: str | None = None,
    allowed_staleness_business_days: int = 3,
) -> dict[str, Any]:
    requested_inputs = _manifest_requested_inputs(entries, repo_root=repo_root)
    latest_input_mtime: datetime | None = None
    latest_source_horizon: date | None = None
    for raw_path in requested_inputs:
        candidate = Path(raw_path)
        if not candidate.exists():
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
        if latest_input_mtime is None or modified > latest_input_mtime:
            latest_input_mtime = modified
        if candidate.suffix.lower() == ".parquet":
            source_horizon = _parquet_source_horizon(candidate)
            if source_horizon is not None and (latest_source_horizon is None or source_horizon > latest_source_horizon):
                latest_source_horizon = source_horizon
    store_summary = _current_daily_truth_store(db_path)
    trusted_truth_horizon = _parse_date(store_summary.get("latest_quote_at_utc"))
    today = _utc_now().date()
    truth_staleness = _business_days_stale(trusted_truth_horizon, today)
    latest_source_date = latest_input_mtime.date() if latest_input_mtime is not None else None
    source_staleness = _business_days_stale(latest_source_date, today)
    source_horizon_staleness = _business_days_stale(latest_source_horizon, today)
    effective_source_staleness = source_horizon_staleness if latest_source_horizon is not None else source_staleness
    return {
        "requested_manifest_inputs": requested_inputs,
        "daily_truth_source_latest_mtime_utc": (
            latest_input_mtime.isoformat().replace("+00:00", "Z")
            if latest_input_mtime is not None
            else None
        ),
        "daily_truth_source_horizon": latest_source_horizon.isoformat() if latest_source_horizon else None,
        "daily_truth_source_stale": (
            effective_source_staleness is not None
            and effective_source_staleness > int(allowed_staleness_business_days)
        ),
        "source_horizon_staleness_business_days": source_horizon_staleness,
        "trusted_truth_horizon": trusted_truth_horizon.isoformat() if trusted_truth_horizon else None,
        "truth_staleness_business_days": truth_staleness,
        "allowed_truth_staleness_business_days": int(allowed_staleness_business_days),
    }


def _current_daily_truth_store(db_path: str | None = None) -> dict[str, Any]:
    store = HistoricalOptionsStore(db_path)
    return store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)


def _daily_truth_entries_needing_import(
    entries: list[dict[str, Any]],
    *,
    repo_root: Path = ROOT_DIR,
    db_path: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = _current_daily_truth_store(db_path)
    known_sources = {str(item).strip() for item in list(summary.get("source_labels") or []) if str(item).strip()}
    latest_imported_at = _parse_iso_datetime(summary.get("latest_imported_at_utc"))
    needed: list[dict[str, Any]] = []
    for entry in entries:
        source_label = str(entry.get("source") or "").strip()
        input_path = _resolve_manifest_entry_path(entry.get("input"), repo_root=repo_root)
        underlying_path = _resolve_manifest_entry_path(entry.get("underlying_input"), repo_root=repo_root)
        latest_input_mtime: datetime | None = None
        for candidate in (input_path, underlying_path):
            if candidate is None or not candidate.exists():
                continue
            modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
            if latest_input_mtime is None or modified > latest_input_mtime:
                latest_input_mtime = modified
        source_known = bool(source_label and source_label in known_sources)
        if not source_known:
            needed.append(dict(entry))
            continue
        if latest_imported_at is not None and latest_input_mtime is not None and latest_input_mtime > latest_imported_at:
            needed.append(dict(entry))
    return needed, summary


def _daily_truth_refresh_failure_issue(
    *,
    source_automation: str,
    refresh: dict[str, Any],
) -> dict[str, Any]:
    refresh_stage = str(refresh.get("stage") or "").strip().lower()
    evidence = [
        f"status={refresh.get('status')}",
        f"stage={refresh.get('stage')}",
        f"manifest_source={refresh.get('manifest_source')}",
        f"manifest_path={refresh.get('manifest_path')}",
        f"error={refresh.get('error')}",
    ]
    import_summary = dict(refresh.get("import_summary") or {})
    if import_summary:
        evidence.extend(
            [
                f"import_total_rows={import_summary.get('total_imported_rows')}",
                f"import_duplicate_rows={import_summary.get('total_duplicate_rows')}",
            ]
        )
    return _issue_payload(
        issue_id=(
            "daily-truth-refresh-freshness-stale"
            if refresh_stage == "trusted_truth_freshness"
            else "daily-truth-refresh-failed"
        ),
        source_automation=source_automation,
        severity="high",
        blocker_class="truth_data_refresh",
        summary=(
            "Imported-daily truth refresh could not advance the trusted truth horizon, so the profit loop cannot trust the current measurement window."
            if refresh_stage == "trusted_truth_freshness"
            else "Imported-daily truth refresh failed, so the profit loop cannot trust the current truth horizon."
        ),
        evidence=evidence,
        suggested_fix_targets=[
            "profit_loop_automation.py",
            "scripts/import_historical_options_snapshots.py",
            _repo_relative_text(refresh.get("manifest_path") or DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST),
        ],
    )


def _run_daily_truth_artifact_refresh(
    *,
    lookback_years: int,
    n_picks: int,
    iv_adj: float,
    pricing_lane: str,
    playbook: str,
    repo_root: Path = ROOT_DIR,
    heartbeat: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    command = [
        sys.executable,
        "profit_loop_automation.py",
        "daily-truth-refresh-artifact",
        "--lookback-years",
        str(int(lookback_years)),
        "--n-picks",
        str(int(n_picks)),
        "--iv-adj",
        str(float(iv_adj)),
        "--pricing-lane",
        str(pricing_lane),
        "--playbook",
        str(playbook),
        "--json",
    ]
    return _run_json_command(
        command,
        cwd=repo_root,
        timeout_seconds=DEFAULT_DAILY_TRUTH_ARTIFACT_TIMEOUT_SECONDS,
        heartbeat_every_seconds=DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS,
        heartbeat=heartbeat,
    )


def _refresh_daily_truth(
    *,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    auto_refresh = _env_flag(DAILY_TRUTH_AUTO_REFRESH_ENV, default=False)
    manifest_path, manifest_source = _resolve_daily_truth_import_manifest(repo_root)
    refresh_config = {
        "lookback_years": _env_int("OPTIONS_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS", DEFAULT_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS),
        "n_picks": _env_int("OPTIONS_DAILY_TRUTH_REFRESH_N_PICKS", DEFAULT_DAILY_TRUTH_REFRESH_N_PICKS),
        "iv_adj": _env_float("OPTIONS_DAILY_TRUTH_REFRESH_IV_ADJ", DEFAULT_DAILY_TRUTH_REFRESH_IV_ADJ),
        "pricing_lane": str(os.getenv("OPTIONS_DAILY_TRUTH_REFRESH_PRICING_LANE") or DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE).strip() or DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE,
        "playbook": str(os.getenv("OPTIONS_DAILY_TRUTH_REFRESH_PLAYBOOK") or DEFAULT_DAILY_TRUTH_REFRESH_PLAYBOOK).strip() or DEFAULT_DAILY_TRUTH_REFRESH_PLAYBOOK,
    }
    base_result = {
        "auto_refresh": auto_refresh,
        "manifest_path": manifest_path,
        "manifest_source": manifest_source,
        "env_files_loaded": list(_ENV_FILES_LOADED),
        "refresh_config": refresh_config,
        "stage_timeouts": {
            "import": DEFAULT_DAILY_TRUTH_IMPORT_TIMEOUT_SECONDS,
            "artifact_refresh": DEFAULT_DAILY_TRUTH_ARTIFACT_TIMEOUT_SECONDS,
            "heartbeat_seconds": DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS,
        },
    }
    if dry_run:
        return {
            **base_result,
            "status": "dry_run",
            "commands": [],
        }
    if not auto_refresh:
        return {
            **base_result,
            "status": "disabled",
            "commands": [],
        }
    if not manifest_path:
        return {
            **base_result,
            "status": "skipped_no_manifest",
            "commands": [],
        }

    historical_db_path = str(os.getenv("HISTORICAL_OPTIONS_DB_PATH") or "").strip() or None
    if not str(manifest_path).startswith(("http://", "https://")) and not Path(manifest_path).exists():
        return {
            **base_result,
            "status": "failed",
            "stage": "preflight",
            "error": f"Configured imported-daily truth manifest does not exist: {manifest_path}",
            "commands": [],
        }

    try:
        manifest_entries = _load_manifest_entries(manifest_path)
    except Exception as exc:
        return {
            **base_result,
            "status": "failed",
            "stage": "preflight",
            "error": f"Unable to load imported-daily truth manifest: {exc}",
            "commands": [],
        }
    import_entries, pre_import_summary = _daily_truth_entries_needing_import(
        manifest_entries,
        repo_root=repo_root,
        db_path=historical_db_path,
    )
    base_result["pre_import_store_summary"] = pre_import_summary
    pre_refresh_freshness = _daily_truth_source_freshness(
        manifest_entries,
        repo_root=repo_root,
        db_path=historical_db_path,
        allowed_staleness_business_days=DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS,
    )

    if not import_entries and pre_refresh_freshness["requested_manifest_inputs"]:
        trusted_truth_horizon = _parse_date(pre_refresh_freshness.get("trusted_truth_horizon"))
        source_truth_horizon = _parse_date(pre_refresh_freshness.get("daily_truth_source_horizon"))
        source_truth_capped = bool(
            trusted_truth_horizon is not None
            and source_truth_horizon is not None
            and trusted_truth_horizon >= source_truth_horizon
        )
        source_truth_stale = bool(pre_refresh_freshness.get("daily_truth_source_stale"))
        if source_truth_capped:
            return {
                **base_result,
                "status": "artifact_refreshed",
                "import_required_entry_count": 0,
                "imported_entry_sources": [],
                "import_summary": {
                    "mode": "manifest",
                    "db_path": historical_db_path,
                    "total_imported_rows": 0,
                    "total_duplicate_rows": 0,
                    "total_rejected_rows": 0,
                    "trusted_snapshot_summaries": {
                        DAILY_SNAPSHOT_KIND: pre_import_summary,
                    },
                },
                "artifact_refresh": {
                    "skipped": True,
                    "reason": "source_truth_stale_preflight",
                },
                "source_freshness": {
                    **pre_refresh_freshness,
                    "source_truth_capped": True,
                },
                "commands": [],
            }

    commands: list[str] = []
    import_payload: dict[str, Any] = {
        "mode": "manifest",
        "db_path": historical_db_path,
        "entries": [],
        "total_imported_rows": 0,
        "total_duplicate_rows": 0,
        "total_rejected_rows": 0,
        "trusted_snapshot_summaries": {
            DAILY_SNAPSHOT_KIND: pre_import_summary,
        },
    }
    if import_entries:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf8") as handle:
            json.dump({"imports": import_entries}, handle, indent=2)
            temp_manifest_path = handle.name
        try:
            import_command = [
                sys.executable,
                "scripts/import_historical_options_snapshots.py",
                "--manifest",
                temp_manifest_path,
                "--json",
            ]
            if historical_db_path:
                import_command.extend(["--db-path", historical_db_path])
            try:
                import_payload, import_record = _run_json_command(
                    import_command,
                    cwd=repo_root,
                    timeout_seconds=DEFAULT_DAILY_TRUTH_IMPORT_TIMEOUT_SECONDS,
                    heartbeat_every_seconds=DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS,
                )
            except Exception as exc:
                return {
                    **base_result,
                    "status": "failed",
                    "stage": "import",
                    "error": str(exc),
                    "commands": [_command_text(import_command)],
                }
            commands.append(import_record.get("command"))
        finally:
            with contextlib.suppress(Exception):
                Path(temp_manifest_path).unlink()
    else:
        import_payload = {
            **import_payload,
            "trusted_snapshot_summaries": {
                DAILY_SNAPSHOT_KIND: pre_import_summary,
            },
        }

    artifact_command = (
        f"python profit_loop_automation.py daily-truth-refresh-artifact --truth-lane {IMPORTED_DAILY_TRUTH_SOURCE}"
        f" --pricing-lane {refresh_config['pricing_lane']}"
        f" --lookback-years {refresh_config['lookback_years']}"
        f" --n-picks {refresh_config['n_picks']}"
        f" --iv-adj {refresh_config['iv_adj']}"
        f" --playbook {refresh_config['playbook']}"
    )
    try:
        artifact_result, artifact_record = _run_daily_truth_artifact_refresh(
            lookback_years=int(refresh_config["lookback_years"]),
            n_picks=int(refresh_config["n_picks"]),
            iv_adj=float(refresh_config["iv_adj"]),
            pricing_lane=str(refresh_config["pricing_lane"]),
            playbook=str(refresh_config["playbook"]),
            repo_root=repo_root,
        )
        if artifact_result.get("error"):
            raise ProfitLoopAutomationError(str(artifact_result.get("error")))
        commands.append(artifact_record.get("command"))
    except Exception as exc:
        return {
            **base_result,
            "status": "failed",
            "stage": "artifact_refresh",
            "error": str(exc),
            "import_summary": {
                "total_imported_rows": import_payload.get("total_imported_rows"),
                "total_duplicate_rows": import_payload.get("total_duplicate_rows"),
                "trusted_snapshot_summaries": import_payload.get("trusted_snapshot_summaries"),
            },
            "commands": commands + [artifact_command],
        }

    freshness_summary = _daily_truth_source_freshness(
        manifest_entries,
        repo_root=repo_root,
        db_path=historical_db_path,
        allowed_staleness_business_days=DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS,
    )
    if freshness_summary["requested_manifest_inputs"] and (
        freshness_summary["trusted_truth_horizon"] is None
        or (
            freshness_summary["truth_staleness_business_days"] is not None
            and int(freshness_summary["truth_staleness_business_days"])
            > int(DEFAULT_MAX_TRUSTED_TRUTH_STALENESS_BUSINESS_DAYS)
        )
    ):
        trusted_truth_horizon = _parse_date(freshness_summary.get("trusted_truth_horizon"))
        source_truth_horizon = _parse_date(freshness_summary.get("daily_truth_source_horizon"))
        source_truth_capped = bool(
            trusted_truth_horizon is not None
            and source_truth_horizon is not None
            and trusted_truth_horizon >= source_truth_horizon
        )
        source_truth_stale = bool(freshness_summary.get("daily_truth_source_stale"))
        if source_truth_capped:
            return {
                **base_result,
                "status": "refreshed" if import_entries else "artifact_refreshed",
                "commands": commands + [artifact_command],
                "import_required_entry_count": len(import_entries),
                "imported_entry_sources": [str(item.get("source") or "").strip() for item in import_entries],
                "import_summary": {
                    "mode": import_payload.get("mode"),
                    "db_path": import_payload.get("db_path"),
                    "total_imported_rows": import_payload.get("total_imported_rows"),
                    "total_duplicate_rows": import_payload.get("total_duplicate_rows"),
                    "total_rejected_rows": import_payload.get("total_rejected_rows"),
                    "trusted_snapshot_summaries": import_payload.get("trusted_snapshot_summaries"),
                },
                "artifact_refresh": {
                    "result_path": artifact_result.get("result_path"),
                    "truth_source": artifact_result.get("truth_source"),
                    "total_trades": artifact_result.get("total_trades"),
                    "profit_factor": artifact_result.get("profit_factor"),
                    "quote_coverage_pct": artifact_result.get("quote_coverage_pct"),
                    "calendar_source": ((artifact_result.get("calendar_summary") or {}).get("source")),
                },
                "source_freshness": {
                    **freshness_summary,
                    "source_truth_capped": True,
                },
            }
        return {
            **base_result,
            "status": "failed",
            "stage": "trusted_truth_freshness",
            "error": (
                "Imported-daily artifact refresh completed, but the trusted truth horizon is still stale after refresh."
                if not source_truth_capped
                else "Imported-daily artifact refresh completed, but the trusted truth horizon is capped by stale source inputs."
            ),
            "import_required_entry_count": len(import_entries),
            "imported_entry_sources": [str(item.get("source") or "").strip() for item in import_entries],
            "import_summary": {
                "mode": import_payload.get("mode"),
                "db_path": import_payload.get("db_path"),
                "total_imported_rows": import_payload.get("total_imported_rows"),
                "total_duplicate_rows": import_payload.get("total_duplicate_rows"),
                "total_rejected_rows": import_payload.get("total_rejected_rows"),
                "trusted_snapshot_summaries": import_payload.get("trusted_snapshot_summaries"),
            },
            "artifact_refresh": {
                "result_path": artifact_result.get("result_path"),
                "truth_source": artifact_result.get("truth_source"),
                "total_trades": artifact_result.get("total_trades"),
                "profit_factor": artifact_result.get("profit_factor"),
                "quote_coverage_pct": artifact_result.get("quote_coverage_pct"),
                "calendar_source": ((artifact_result.get("calendar_summary") or {}).get("source")),
            },
            "source_freshness": {
                **freshness_summary,
                "source_truth_capped": source_truth_capped,
            },
            "commands": commands + [artifact_command],
        }

    return {
        **base_result,
        "status": "refreshed" if import_entries else "artifact_refreshed",
        "commands": commands + [artifact_command],
        "import_required_entry_count": len(import_entries),
        "imported_entry_sources": [str(item.get("source") or "").strip() for item in import_entries],
        "import_summary": {
            "mode": import_payload.get("mode"),
            "db_path": import_payload.get("db_path"),
            "total_imported_rows": import_payload.get("total_imported_rows"),
            "total_duplicate_rows": import_payload.get("total_duplicate_rows"),
            "total_rejected_rows": import_payload.get("total_rejected_rows"),
            "trusted_snapshot_summaries": import_payload.get("trusted_snapshot_summaries"),
        },
        "artifact_refresh": {
            "result_path": artifact_result.get("result_path"),
            "truth_source": artifact_result.get("truth_source"),
            "total_trades": artifact_result.get("total_trades"),
            "profit_factor": artifact_result.get("profit_factor"),
            "quote_coverage_pct": artifact_result.get("quote_coverage_pct"),
            "calendar_source": ((artifact_result.get("calendar_summary") or {}).get("source")),
        },
        "source_freshness": freshness_summary,
    }


def _run_daily_truth_refresh_subprocess(
    *,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    heartbeat: Any = None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "profit_loop_automation.py",
        "daily-truth-refresh",
        "--json",
    ]
    if dry_run:
        command.append("--dry-run")
    try:
        payload, _ = _run_json_command(
            command,
            cwd=repo_root,
            timeout_seconds=DEFAULT_DAILY_TRUTH_IMPORT_TIMEOUT_SECONDS + DEFAULT_DAILY_TRUTH_ARTIFACT_TIMEOUT_SECONDS + 120,
            heartbeat_every_seconds=DEFAULT_SUBPROCESS_HEARTBEAT_SECONDS,
            heartbeat=heartbeat,
        )
        return payload
    except CommandTimeoutError as exc:
        return {
            "status": "failed",
            "stage": "subprocess_timeout",
            "error": str(exc),
            "commands": [_command_text(command)],
            "timed_out": True,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "stage": "subprocess",
            "error": str(exc),
            "commands": [_command_text(command)],
            "timed_out": False,
        }


def _require_daily_truth_refresh(
    *,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    refresh_result: dict[str, Any] | None = None,
    heartbeat: Any = None,
) -> dict[str, Any]:
    result = dict(
        refresh_result
        or _run_daily_truth_refresh_subprocess(repo_root=repo_root, dry_run=dry_run, heartbeat=heartbeat)
    )
    status = str(result.get("status") or "").strip().lower()
    if status in {"refreshed", "artifact_refreshed", "dry_run"}:
        return result
    if status != "failed":
        result["status"] = "failed"
        result["stage"] = str(result.get("stage") or "preflight")
        result["error"] = str(
            result.get("error")
            or {
                "disabled": f"{DAILY_TRUTH_AUTO_REFRESH_ENV} disabled the mandatory imported-daily refresh step.",
                "skipped_no_manifest": "No imported-daily truth manifest was configured for the mandatory refresh step.",
            }.get(status)
            or "The mandatory imported-daily refresh did not complete successfully."
        )
    return result


def _issue_payload(
    *,
    issue_id: str,
    source_automation: str,
    severity: str,
    blocker_class: str,
    summary: str,
    evidence: list[str],
    suggested_fix_targets: list[str],
) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "source_automation": source_automation,
        "severity": severity,
        "blocker_class": blocker_class,
        "summary": summary,
        "evidence": evidence,
        "suggested_fix_targets": suggested_fix_targets,
        "status": "open",
    }


def _make_active_run_heartbeat(
    state: dict[str, Any],
    *,
    run_id: str,
    phase: str,
    state_dir: str | Path | None = None,
) -> Any:
    def _heartbeat(_: dict[str, Any]) -> None:
        now_iso = utc_now_iso()
        heartbeat_active_run(state, run_id=run_id, phase=phase, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)

    return _heartbeat


def _normalized_scan_funnel(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    normalized_drop_counts = {
        "min_history": 0,
        "history_or_liquidity": 0,
        "signal_index": 0,
        "momentum": 0,
        "tech_score": 0,
        "direction_score": 0,
        "earnings": 0,
        "option_liquidity": 0,
        "iv_crush_penalty": 0,
        "ev_floor": 0,
        "guardrails": 0,
        "exceptions": 0,
    }
    for key in list(normalized_drop_counts):
        normalized_drop_counts[key] = int(((payload.get("drop_counts") or {}).get(key)) or 0)
    return {
        "raw_candidates": int(payload.get("raw_candidates") or 0),
        "post_policy_visible": int(payload.get("post_policy_visible") or 0),
        "post_guardrails_visible": int(payload.get("post_guardrails_visible") or 0),
        "returned_picks": int(payload.get("returned_picks") or 0),
        "policy_filtered_out": int(payload.get("policy_filtered_out") or 0),
        "guardrail_filtered_out": int(payload.get("guardrail_filtered_out") or 0),
        "final_trimmed": int(payload.get("final_trimmed") or 0),
        "policy_counts": dict(payload.get("policy_counts") or {}),
        "guardrail_counts": dict(payload.get("guardrail_counts") or {}),
        "policy_applied": bool(payload.get("policy_applied")),
        "policy_fail_closed": bool(payload.get("policy_fail_closed")),
        "include_blocked_policy_picks": bool(payload.get("include_blocked_policy_picks")),
        "include_blocked_guardrail_picks": bool(payload.get("include_blocked_guardrail_picks")),
        "drop_counts": normalized_drop_counts,
        "symbol_diagnostics": dict(payload.get("symbol_diagnostics") or {}),
    }


def _scan_funnel_stage(funnel: dict[str, Any] | None) -> str:
    normalized = _normalized_scan_funnel(funnel)
    if int(normalized.get("raw_candidates") or 0) <= 0:
        return "raw_candidates_zero"
    if int(normalized.get("post_policy_visible") or 0) <= 0:
        return "policy_filtered_all"
    if int(normalized.get("post_guardrails_visible") or 0) <= 0:
        return "guardrails_filtered_all"
    if int(normalized.get("returned_picks") or 0) <= 0:
        return "returned_picks_zero"
    return "candidates_visible"


def _candidate_flow_breakdown(
    funnel: dict[str, Any] | None,
    *,
    refresh_status: str | None = None,
) -> dict[str, Any]:
    normalized = _normalized_scan_funnel(funnel)
    drop_counts = dict(normalized.get("drop_counts") or {})
    environment_or_data_failure = 1 if str(refresh_status or "").strip().lower() == "failed" else 0
    classification = "recorded"
    primary_starving_gate = None
    if drop_counts:
        primary_starving_gate = max(drop_counts.items(), key=lambda item: int(item[1] or 0))[0]
        if int(drop_counts.get(primary_starving_gate) or 0) <= 0:
            primary_starving_gate = None
    symbol_diagnostics = dict(normalized.get("symbol_diagnostics") or {})
    has_symbol_diagnostics = bool(symbol_diagnostics)
    if environment_or_data_failure:
        classification = "environment_or_data_failure"
        primary_starving_gate = primary_starving_gate or "environment_or_data_failure"
    elif int(normalized.get("raw_candidates") or 0) <= 0:
        if int(drop_counts.get("exceptions") or 0) > 0:
            classification = "environment_or_data_failure"
        elif any(
            int(drop_counts.get(key) or 0) > 0
            for key in ("min_history", "history_or_liquidity", "signal_index", "earnings", "option_liquidity")
        ):
            classification = "filtered_by_history_or_liquidity"
        elif not any(int(v or 0) > 0 for v in drop_counts.values()) and not has_symbol_diagnostics:
            classification = "scanner_starvation_unresolved"
        else:
            classification = "no_candidates_from_scan"
    elif int(normalized.get("post_policy_visible") or 0) <= 0:
        classification = "filtered_by_policy"
    elif int(normalized.get("post_guardrails_visible") or 0) <= 0:
        classification = "filtered_by_guardrails"
    return {
        "classification": classification,
        "no_candidates_from_scan": 1 if int(normalized.get("raw_candidates") or 0) <= 0 else 0,
        "filtered_by_history_or_liquidity": sum(
            int(drop_counts.get(key) or 0)
            for key in ("min_history", "history_or_liquidity", "signal_index", "earnings", "option_liquidity")
        ),
        "filtered_by_policy": int(normalized.get("policy_filtered_out") or 0),
        "filtered_by_guardrails": max(
            int(normalized.get("guardrail_filtered_out") or 0),
            int(drop_counts.get("guardrails") or 0),
        ),
        "environment_or_data_failure": max(environment_or_data_failure, int(drop_counts.get("exceptions") or 0)),
        "raw_candidates": int(normalized.get("raw_candidates") or 0),
        "post_policy_visible": int(normalized.get("post_policy_visible") or 0),
        "post_guardrails_visible": int(normalized.get("post_guardrails_visible") or 0),
        "returned_picks": int(normalized.get("returned_picks") or 0),
        "final_trimmed": int(normalized.get("final_trimmed") or 0),
        "drop_counts": drop_counts,
        "primary_starving_gate": primary_starving_gate,
        "symbol_diagnostics": symbol_diagnostics,
    }


def _holdout_has_nonzero_candidate_flow(results: dict[str, Any] | None) -> bool:
    payload = dict(results or {})
    if bool(payload.get("raw_required")) and str(payload.get("raw_pass_state") or "").strip().lower() == "run":
        return int(payload.get("raw_scan_picks") or 0) > 0
    return int(payload.get("policy_gated_scan_picks") or 0) > 0 or int(payload.get("raw_scan_picks") or 0) > 0


def _zero_candidate_market_state(candidate_flow_breakdown: dict[str, Any]) -> bool:
    return str(candidate_flow_breakdown.get("classification") or "").strip().lower() == "no_candidates_from_scan"


def _resolve_seed_issue_if_cleared(
    state: dict[str, Any],
    *,
    issue_id: str,
    now_iso: str,
    resolution_note: str,
) -> list[dict[str, Any]]:
    remaining_seed_ids = [
        str(item.get("issue_id") or "").strip()
        for item in list(state.get("open_issues") or [])
        if str(item.get("source_automation") or "").strip() == "seed"
        and str(item.get("issue_id") or "").strip()
        and str(item.get("issue_id") or "").strip() != str(issue_id).strip()
    ]
    return reconcile_source_open_issues(
        state,
        source_automation="seed",
        active_issue_ids=remaining_seed_ids,
        now_iso=now_iso,
        resolution_note=resolution_note,
    )


def _safe_measurement_gate() -> dict[str, Any]:
    try:
        return dict(evaluate_measurement_gate() or {})
    except Exception as exc:
        return {
            "state": "blocked",
            "blockers": [
                {
                    "code": "measurement_gate_evaluation_failed",
                    "severity": "blocked",
                    "message": str(exc),
                }
            ],
            "error": str(exc),
        }


def _safe_claim_readiness() -> dict[str, Any]:
    try:
        return dict(evaluate_claim_readiness() or {})
    except Exception as exc:
        return {
            "state": "not_claim_ready",
            "claim_ready": False,
            "blockers": [{"code": "claim_readiness_evaluation_failed", "message": str(exc)}],
            "blocker_count": 1,
            "error": str(exc),
        }


def _validation_proof_plan(issue: dict[str, Any] | None) -> dict[str, Any]:
    blocker_class = str((issue or {}).get("blocker_class") or "storage").strip()
    modules = list(VALIDATION_TEST_PLAN_BY_BLOCKER.get(blocker_class, VALIDATION_TEST_MODULES))
    needs_replay = blocker_class in {"replay_matrix_suspicious", "replay_report_integrity"}
    needs_holdout = blocker_class in {"scan_starvation", "fail_open"}
    return {
        "blocker_class": blocker_class,
        "test_tier": "verify:research",
        "modules": modules,
        "needs_smoke": True,
        "needs_replay_matrix": needs_replay,
        "needs_holdout": needs_holdout,
        "playbook": "broad",
        "truth_lane": IMPORTED_DAILY_TRUTH_SOURCE,
        "pricing_spec": "matrix" if needs_replay else "targeted",
    }


def _proof_command_texts(commands: list[Any]) -> set[str]:
    texts: set[str] = set()
    for item in list(commands or []):
        if isinstance(item, dict):
            candidate = str(item.get("command") or "").strip()
        else:
            candidate = str(item or "").strip()
        if candidate:
            texts.add(candidate)
    return texts


def _validation_baseline_artifact_path(proof_dir: Path) -> Path:
    return proof_dir / "validation_baseline.json"


def _shared_replay_matrix_artifact_path(
    proof_fingerprint: str,
    *,
    state_dir: str | Path | None = None,
) -> Path:
    return shared_state_dir(state_dir) / "replay-matrix-cache" / f"{str(proof_fingerprint).strip()}.json"


def _load_validation_baseline_artifact(proof_dir: Path) -> dict[str, Any]:
    artifact = _read_json_artifact(_validation_baseline_artifact_path(proof_dir))
    if artifact is None:
        raise ValueError(
            f"Validation baseline artifact is required before resolving an issue: {_validation_baseline_artifact_path(proof_dir)}"
        )
    return artifact


def _resolution_prerequisite_blockers(
    *,
    state: dict[str, Any],
    current_context: dict[str, Any],
    issue_id: str,
    proof_dir: Path,
    proof_commands: list[str],
    before_after_comparison: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any] | None]:
    blockers: list[str] = []
    prerequisite_blockers = validation_prerequisite_blockers(state)
    if prerequisite_blockers:
        blockers.append(
            "validation_prerequisites_blocked: "
            + ", ".join(sorted(str(item.get("code") or "") for item in prerequisite_blockers if str(item.get("code") or "").strip()))
        )

    health = dict(state.get("latest_operational_health") or {})
    health_status = str(health.get("loop_execution_status") or _infer_loop_execution_status(health)).strip().lower()
    health_evidence = str(health.get("evidence_status") or "").strip().lower()
    if health_status != "healthy" or health_evidence != "trusted":
        blockers.append(
            f"operational_health_not_healthy: loop_execution_status={health_status or 'missing'}, evidence_status={health_evidence or 'missing'}"
        )

    holdout = dict(state.get("latest_truth_holdout") or {})
    holdout_status = str(holdout.get("loop_execution_status") or _infer_loop_execution_status(holdout)).strip().lower()
    holdout_evidence = str(holdout.get("evidence_status") or "").strip().lower()
    if holdout_status != "healthy" or holdout_evidence != "trusted":
        blockers.append(
            f"truth_holdout_not_healthy: loop_execution_status={holdout_status or 'missing'}, evidence_status={holdout_evidence or 'missing'}"
        )

    latest_snapshot = dict(state.get("latest_profit_validation") or {})
    if str(latest_snapshot.get("targeted_issue_id") or "").strip() != str(issue_id or "").strip():
        blockers.append(
            f"targeted_issue_mismatch: latest_targeted_issue_id={latest_snapshot.get('targeted_issue_id')}"
        )

    if not before_after_comparison:
        blockers.append("before_after_comparison_missing")

    proof_bundle_dir = str(latest_snapshot.get("proof_bundle_dir") or "").strip()
    if not proof_bundle_dir:
        blockers.append("proof_bundle_dir_missing")
        return blockers, None

    proof_dir_exists = Path(proof_bundle_dir)
    if not proof_dir_exists.exists() or not proof_dir_exists.is_dir():
        blockers.append(f"proof_bundle_dir_missing_or_invalid: {proof_bundle_dir}")
        return blockers, None

    baseline = _load_validation_baseline_artifact(proof_dir_exists)
    baseline_issue_id = str(baseline.get("targeted_issue_id") or "").strip()
    if baseline_issue_id != str(issue_id or "").strip():
        blockers.append(f"validation_baseline_issue_mismatch: {baseline_issue_id}")

    baseline_context = dict(baseline.get("proof_context") or {})
    expected_context = dict(current_context or {})
    if str(baseline_context.get("base_fingerprint") or "").strip() != str(expected_context.get("base_fingerprint") or "").strip():
        blockers.append("validation_baseline_context_mismatch")

    proof_plan = dict(baseline.get("proof_plan") or {})
    expected_fingerprint = _validation_fingerprint(
        commit_sha=str(expected_context.get("commit_sha") or ""),
        env_hash=str(expected_context.get("env_hash") or ""),
        truth_lane=str(proof_plan.get("truth_lane") or IMPORTED_DAILY_TRUTH_SOURCE),
        playbook=str(proof_plan.get("playbook") or "broad"),
        blocker_class=str(proof_plan.get("blocker_class") or "storage"),
        pricing_spec=str(proof_plan.get("pricing_spec") or "targeted"),
        modules=list(proof_plan.get("modules") or []),
    )
    if str(baseline_context.get("validation_fingerprint") or "").strip() != expected_fingerprint:
        blockers.append("validation_baseline_fingerprint_mismatch")

    baseline_commands = _proof_command_texts(list(baseline.get("commands") or []))
    missing_commands = [command for command in proof_commands if command not in baseline_commands]
    if missing_commands:
        blockers.append(f"proof_commands_not_in_baseline: {missing_commands}")

    comparison = dict(before_after_comparison or {})
    expected_comparison_spec = _expected_validation_comparison_spec(
        latest_snapshot=latest_snapshot,
        baseline=baseline,
    )
    if expected_comparison_spec:
        comparison_spec = dict(comparison.get("comparison_spec") or {})
        mismatched_fields = [
            key
            for key, expected_value in expected_comparison_spec.items()
            if comparison_spec.get(key) != expected_value
        ]
        if mismatched_fields:
            blockers.append(
                "comparison_spec_mismatch: "
                + ", ".join(
                    f"{key}=expected:{expected_comparison_spec.get(key)!r} actual:{comparison_spec.get(key)!r}"
                    for key in mismatched_fields
                )
            )

    if not bool(baseline.get("validation_tests_passed")):
        blockers.append("validation_tests_failed")
    if proof_plan.get("needs_smoke") and not dict(baseline.get("smoke_summary") or {}):
        blockers.append("missing_smoke_summary")
    if proof_plan.get("needs_replay_matrix"):
        replay_cases = list(baseline.get("replay_cases") or [])
        replay_assessment = dict(baseline.get("replay_matrix_assessment") or {})
        if not replay_cases:
            blockers.append("missing_replay_matrix")
        elif any(bool(case.get("error")) for case in replay_cases if isinstance(case, dict)):
            blockers.append("replay_matrix_contains_errors")
        elif not bool(replay_assessment.get("is_valid")):
            blockers.append(f"replay_matrix_invalid: {replay_assessment.get('failure_reason')}")
    if proof_plan.get("needs_holdout") and not dict(baseline.get("holdout_evidence") or {}):
        blockers.append("missing_holdout_evidence")

    return blockers, baseline


def _expected_validation_comparison_spec(
    *,
    latest_snapshot: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    proof_plan = dict((baseline or {}).get("proof_plan") or {})
    refresh_config = dict((((latest_snapshot or {}).get("daily_truth_refresh") or {}).get("refresh_config") or {}))
    if not proof_plan and not refresh_config:
        return {}

    return {
        "playbook": str(proof_plan.get("playbook") or refresh_config.get("playbook") or "broad"),
        "truth_lane": str(proof_plan.get("truth_lane") or refresh_config.get("truth_lane") or IMPORTED_DAILY_TRUTH_SOURCE),
        "pricing_lane": str(refresh_config.get("pricing_lane") or DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE),
        "lookback_years": int(refresh_config.get("lookback_years") or DEFAULT_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS),
        "n_picks": int(refresh_config.get("n_picks") or DEFAULT_DAILY_TRUTH_REFRESH_N_PICKS),
        "iv_adj": float(refresh_config.get("iv_adj") or DEFAULT_DAILY_TRUTH_REFRESH_IV_ADJ),
    }


def _run_proof_modules(modules: list[str], *, repo_root: Path = ROOT_DIR, dry_run: bool = False) -> dict[str, Any]:
    if dry_run or not modules:
        return {
            "record": {"command": "", "passed": True, "stdout": "", "stderr": ""},
            "passed": True,
            "count": 0,
            "module_status": {},
        }
    record = _run_unittest_modules(modules, cwd=repo_root)
    return {
        "record": record,
        "passed": bool(record["passed"]),
        "count": _extract_unittest_count(record["stdout"]),
        "module_status": _extract_unittest_module_status(record["stdout"]),
    }


def _evaluate_profitability_verdict(before_after_comparison: dict[str, Any]) -> str:
    comparison = dict(before_after_comparison or {})
    comparison_spec = dict(comparison.get("comparison_spec") or {})
    required_spec = {"playbook", "truth_lane", "pricing_lane", "lookback_years", "n_picks", "iv_adj"}
    missing = required_spec.difference(comparison_spec.keys())
    if missing:
        raise ValueError(f"before_after_comparison missing comparison_spec keys: {sorted(missing)}")
    baseline = dict(comparison.get("baseline") or {})
    after = dict(comparison.get("after") or {})
    if not baseline or not after:
        raise ValueError("before_after_comparison requires baseline and after payloads")
    truth_quality_regressed = bool(comparison.get("truth_quality_regressed"))
    safety_regressed = bool(comparison.get("safety_regressed"))
    drawdown_regressed = bool(comparison.get("material_drawdown_worsened"))
    forward_status = str(comparison.get("forward_evidence_status") or "sparse").strip().lower()
    baseline_pf = float(baseline.get("profit_factor") or 0.0)
    after_pf = float(after.get("profit_factor") or 0.0)
    baseline_avg = float(baseline.get("avg_pnl_pct") or 0.0)
    after_avg = float(after.get("avg_pnl_pct") or 0.0)
    after_is_profitable = after_pf > 1.0 and after_avg > 0.0

    if truth_quality_regressed or safety_regressed or drawdown_regressed:
        return "regressed"
    if after_pf < baseline_pf or after_avg < baseline_avg:
        return "regressed"
    if after_pf > baseline_pf and after_avg > baseline_avg and after_is_profitable:
        if forward_status in {"non_worse", "improved"}:
            return "improved"
        return "inconclusive"
    return "inconclusive"


def _replay_matrix_assessment(replay_cases: list[dict[str, Any]]) -> dict[str, Any]:
    cases = [dict(item) for item in list(replay_cases or []) if isinstance(item, dict)]
    if len(cases) != len(VALIDATION_REPLAY_CASES):
        return {
            "is_valid": False,
            "failure_reason": "missing_required_cells",
            "meaningfully_distinct": False,
        }
    if any(bool(case.get("error")) for case in cases):
        return {
            "is_valid": False,
            "failure_reason": "replay_case_error",
            "meaningfully_distinct": False,
        }
    invalid_cases = [
        {
            "lookback_years": case.get("lookback_years"),
            "requested_pricing_lane": case.get("requested_pricing_lane"),
            "effective_pricing_lane": case.get("effective_pricing_lane"),
        }
        for case in cases
        if bool(case.get("invalid_for_matrix_comparison"))
    ]
    if invalid_cases:
        return {
            "is_valid": False,
            "failure_reason": "pricing_lane_flattened",
            "meaningfully_distinct": False,
            "invalid_cases": invalid_cases,
            "expected_imported_truth_normalization": False,
        }
    fingerprints = set()
    for case in cases:
        fingerprint = {
            "lookback_years": case.get("lookback_years"),
            "truth_source": case.get("truth_source"),
            "selection_source_counts": case.get("selection_source_counts"),
            "calibration_summary": case.get("calibration_summary"),
            "total_trades": case.get("total_trades"),
            "profit_factor": case.get("profit_factor"),
            "avg_pnl_pct": case.get("avg_pnl_pct"),
            "directional_accuracy_pct": case.get("directional_accuracy_pct"),
            "max_drawdown_pct": case.get("max_drawdown_pct"),
        }
        fingerprint["requested_pricing_lane"] = case.get("requested_pricing_lane")
        fingerprint["effective_pricing_lane"] = case.get("effective_pricing_lane")
        fingerprints.add(json.dumps(fingerprint, sort_keys=True))
    meaningfully_distinct = len(fingerprints) > 1
    return {
        "is_valid": meaningfully_distinct,
        "failure_reason": None if meaningfully_distinct else "collapsed_identical_cells",
        "meaningfully_distinct": meaningfully_distinct,
        "expected_imported_truth_normalization": False,
        "effective_dimensions": ["lookback_years", "pricing_lane"],
    }


def _baseline_replay_matrix(*, playbook: str = "broad", truth_lane: str = IMPORTED_DAILY_TRUTH_SOURCE) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in VALIDATION_REPLAY_CASES:
        output = run_historical_backtest(
            lookback_years=int(case["lookback_years"]),
            n_picks=int(case["n_picks"]),
            iv_adj=float(case["iv_adj"]),
            pricing_lane=str(case["pricing_lane"]),
            playbook=playbook,
            truth_lane=truth_lane,
        )
        results.append(
            {
                **case,
                "truth_source": output.get("truth_source"),
                "requested_pricing_lane": output.get("requested_pricing_lane") or case.get("pricing_lane"),
                "effective_pricing_lane": output.get("effective_pricing_lane") or output.get("pricing_lane"),
                "total_trades": output.get("total_trades"),
                "profit_factor": output.get("profit_factor"),
                "avg_pnl_pct": output.get("avg_pnl_pct"),
                "directional_accuracy_pct": output.get("directional_accuracy_pct"),
                "max_drawdown_pct": output.get("max_drawdown_pct"),
                "selection_source_counts": dict(output.get("selection_source_counts") or {}),
                "calibration_summary": copy.deepcopy(output.get("calibration_summary") or {}),
                "invalid_for_matrix_comparison": bool(
                    output.get("requested_pricing_lane")
                    and output.get("effective_pricing_lane")
                    and str(output.get("requested_pricing_lane")) != str(output.get("effective_pricing_lane"))
                ),
                "error": output.get("error"),
            }
        )
    return results


def _capture_validation_baseline(
    *,
    issue: dict[str, Any],
    state: dict[str, Any],
    run_id: str,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    proof_plan = _validation_proof_plan(issue)
    context = _proof_context(repo_root=repo_root)
    proof_dir = shared_proof_bundle_dir(run_id, state_dir=state_dir)
    health_snapshot = dict(state.get("latest_operational_health") or {})
    holdout_snapshot = dict(state.get("latest_truth_holdout") or {})

    smoke_summary: dict[str, Any]
    smoke_record: dict[str, Any] | None = None
    proof_reuse: list[str] = []
    commands: list[dict[str, Any]] = []

    if dry_run:
        smoke_summary = {"mode": "dry_run"}
        proof_reuse.append("dry_run_smoke")
    elif str(((health_snapshot.get("proof_context") or {}).get("base_fingerprint")) or "") == context["base_fingerprint"]:
        smoke_summary = dict((health_snapshot.get("results") or {}).get("smoke_summary") or {})
        if smoke_summary:
            proof_reuse.append("latest_operational_health.smoke")
        else:
            smoke_summary, smoke_record = _run_json_command(
                [sys.executable, "scripts/options_algorithm_smoke.py", "--fixture"],
                cwd=repo_root,
            )
            commands.append(smoke_record)
    else:
        smoke_summary, smoke_record = _run_json_command(
            [sys.executable, "scripts/options_algorithm_smoke.py", "--fixture"],
            cwd=repo_root,
        )
        commands.append(smoke_record)

    already_proven_modules = set()
    if str(((health_snapshot.get("proof_context") or {}).get("base_fingerprint")) or "") == context["base_fingerprint"]:
        health_results = dict(health_snapshot.get("results") or {})
        if health_results.get("unittest_passed"):
            already_proven_modules.update(list(health_results.get("executed_test_modules") or []))
            if health_results.get("executed_test_modules"):
                proof_reuse.append("latest_operational_health.tests")

    modules_to_run = [module for module in proof_plan["modules"] if module not in already_proven_modules]
    module_result = _run_proof_modules(modules_to_run, repo_root=repo_root, dry_run=dry_run)
    if module_result["record"]["command"]:
        commands.append(module_result["record"])

    replay_cases: list[dict[str, Any]] = []
    replay_matrix_assessment = None
    if proof_plan["needs_replay_matrix"]:
        replay_artifact_path = proof_dir / "replay_matrix.json"
        replay_fingerprint = _validation_fingerprint(
            commit_sha=context["commit_sha"],
            env_hash=context["env_hash"],
            truth_lane=proof_plan["truth_lane"],
            playbook=proof_plan["playbook"],
            blocker_class=proof_plan["blocker_class"],
            pricing_spec="matrix",
            modules=proof_plan["modules"],
        )
        shared_replay_artifact_path = _shared_replay_matrix_artifact_path(
            replay_fingerprint,
            state_dir=state_dir,
        )
        replay_artifact = _read_json_artifact(replay_artifact_path)
        shared_replay_artifact = (
            replay_artifact
            if replay_artifact and replay_artifact.get("proof_fingerprint") == replay_fingerprint
            else _read_json_artifact(shared_replay_artifact_path)
        )
        if replay_artifact and replay_artifact.get("proof_fingerprint") == replay_fingerprint:
            replay_cases = list(replay_artifact.get("replay_cases") or [])
            proof_reuse.append("proof_bundle.replay_matrix")
        elif shared_replay_artifact and shared_replay_artifact.get("proof_fingerprint") == replay_fingerprint:
            replay_cases = list(shared_replay_artifact.get("replay_cases") or [])
            _write_json_artifact(replay_artifact_path, dict(shared_replay_artifact))
            proof_reuse.append("shared_state.replay_matrix")
        else:
            replay_cases = _baseline_replay_matrix(
                playbook=str(proof_plan["playbook"]),
                truth_lane=str(proof_plan["truth_lane"]),
            )
            replay_payload = {
                "run_id": run_id,
                "proof_fingerprint": replay_fingerprint,
                "replay_cases": replay_cases,
            }
            _write_json_artifact(replay_artifact_path, replay_payload)
            _write_json_artifact(shared_replay_artifact_path, replay_payload)
        replay_matrix_assessment = _replay_matrix_assessment(replay_cases)

    holdout_evidence = None
    if proof_plan["needs_holdout"]:
        holdout_context = dict((holdout_snapshot.get("proof_context") or {}))
        if str(holdout_context.get("base_fingerprint") or "").strip() == context["base_fingerprint"]:
            holdout_results = dict(holdout_snapshot.get("results") or {})
            holdout_evidence = {
                "policy_gated_session_id": holdout_results.get("policy_gated_session_id"),
                "raw_session_id": holdout_results.get("raw_session_id"),
                "policy_gated_scan_picks": holdout_results.get("policy_gated_scan_picks"),
                "raw_scan_picks": holdout_results.get("raw_scan_picks"),
                "raw_required": holdout_results.get("raw_required"),
                "raw_pass_state": holdout_results.get("raw_pass_state"),
                "policy_gated_scan_funnel": copy.deepcopy(holdout_results.get("policy_gated_scan_funnel")),
                "raw_scan_funnel": copy.deepcopy(holdout_results.get("raw_scan_funnel")),
                "candidate_flow_breakdown": copy.deepcopy(holdout_results.get("candidate_flow_breakdown")),
                "forward_summary": holdout_results.get("forward_summary"),
                "daily_truth_refresh": holdout_results.get("daily_truth_refresh"),
            }
            proof_reuse.append("latest_truth_holdout")

    baseline = {
        "commands": commands,
        "validation_tests_passed": bool(module_result["passed"]),
        "validation_test_count": module_result["count"],
        "smoke_summary": smoke_summary,
        "replay_cases": replay_cases,
        "replay_matrix_assessment": replay_matrix_assessment,
        "holdout_evidence": holdout_evidence,
        "proof_plan": proof_plan,
        "proof_context": {
            **context,
            "validation_fingerprint": _validation_fingerprint(
                commit_sha=context["commit_sha"],
                env_hash=context["env_hash"],
                truth_lane=proof_plan["truth_lane"],
                playbook=proof_plan["playbook"],
                blocker_class=proof_plan["blocker_class"],
                pricing_spec=proof_plan["pricing_spec"],
                modules=proof_plan["modules"],
            ),
        },
        "proof_reuse": proof_reuse,
        "executed_test_modules": modules_to_run,
        "reused_test_modules": sorted(already_proven_modules.intersection(set(proof_plan["modules"]))),
    }
    _write_json_artifact(
        proof_dir / "validation_baseline.json",
        {
            "run_id": run_id,
            "targeted_issue_id": issue.get("issue_id"),
            **baseline,
        },
    )
    return baseline


def _replay_matrix_seed_issue_cleared(
    issue: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
) -> bool:
    if str((issue or {}).get("issue_id") or "").strip() != "replay-matrix-collapsed-results":
        return False
    assessment = dict((baseline or {}).get("replay_matrix_assessment") or {})
    return bool(assessment.get("is_valid"))


def _count_forward_events(state_dir: str | Path | None = None) -> int:
    """Count eligible+pending forward events for auto-resolve checks."""
    try:
        summary = summarize_forward_holdout(cohort_id=None)
        return int(summary.get("scan_pick_count", 0) or 0)
    except Exception:
        return 0


def run_operational_health(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)

    # Attempt to auto-resolve seeded blockers before health assessment
    _auto_resolved = auto_resolve_seeded_issues(
        state,
        forward_events_count=_count_forward_events(state_dir),
        live_truth_lane=IMPORTED_DAILY_TRUTH_SOURCE,
        policy_truth_source=IMPORTED_DAILY_TRUTH_SOURCE,
    )
    if _auto_resolved:
        save_profit_loop_state(state, state_dir=state_dir)

    context = _proof_context(repo_root=repo_root)
    now_iso = utc_now_iso()
    run_id = f"hourly-operational-health-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}"
    run = begin_active_run(
        state,
        automation_id="hourly-operational-health",
        phase="collect_proof",
        commit_sha=context["commit_sha"],
        env_hash=context["env_hash"],
        proof_bundle_dir=str(shared_proof_bundle_dir(run_id, state_dir=state_dir)),
        run_id=run_id,
    )
    proof_dir = Path(run["proof_bundle_dir"])
    save_profit_loop_state(state, state_dir=state_dir)
    issues: list[dict[str, Any]] = []

    if dry_run:
        smoke_payload = {"mode": "dry_run", "scan_truth_lane": IMPORTED_DAILY_TRUTH_SOURCE}
        smoke_record = {"command": "python scripts/options_algorithm_smoke.py --fixture", "passed": True}
        test_record = {"command": "python -m unittest ...", "passed": True, "stdout": "", "stderr": ""}
    else:
        smoke_payload, smoke_record = _run_json_command(
            [sys.executable, "scripts/options_algorithm_smoke.py", "--fixture"],
            cwd=repo_root,
        )
        test_record = _run_unittest_modules(HEALTH_TEST_MODULES, cwd=repo_root)

    verdict = "healthy"
    if not bool(smoke_record.get("passed")) or not bool(test_record.get("passed")):
        verdict = "blocked"
        issues.append(
            _issue_payload(
                issue_id="operational-health-command-failure",
                source_automation="hourly-operational-health",
                severity="high",
                blocker_class="test_gap",
                summary="Operational health evidence commands failed, so unattended validation cannot trust the current system state.",
                evidence=[
                    f"smoke_passed={bool(smoke_record.get('passed'))}",
                    f"unittest_passed={bool(test_record.get('passed'))}",
                ],
                suggested_fix_targets=["scripts/options_algorithm_smoke.py", "scripts/automation_operational_health.py"],
            )
        )
    else:
        smoke_scan_truth_lane = str(smoke_payload.get("scan_truth_lane") or "").strip().lower() or None
        live_policy_truth_source = str(smoke_payload.get("live_policy_truth_source") or "").strip().lower() or None
        live_policy_error = str(smoke_payload.get("live_policy_error") or "").strip() or None
        if smoke_scan_truth_lane and (live_policy_error or not live_policy_truth_source):
            verdict = "degraded-watch"
            issues.append(
                _issue_payload(
                    issue_id="truth-lane-live-policy-mismatch",
                    source_automation="hourly-operational-health",
                    severity="high",
                    blocker_class="truth_lane_mismatch",
                    summary=(
                        "Operational smoke could not produce a live policy truth source for the scan truth lane, so provenance remains untrusted."
                    ),
                    evidence=[
                        f"smoke_scan_truth_lane={smoke_scan_truth_lane}",
                        f"smoke_live_policy_truth_source={live_policy_truth_source}",
                        f"smoke_live_policy_error={live_policy_error}",
                        f"smoke_requested_policy_truth_lane={smoke_payload.get('requested_policy_truth_lane')}",
                        f"smoke_live_policy_promotion_status={smoke_payload.get('live_policy_promotion_status')}",
                    ],
                    suggested_fix_targets=["scripts/options_algorithm_smoke.py", "supervised_scan.py", "wfo_optimizer.py"],
                )
            )
        elif smoke_scan_truth_lane and live_policy_truth_source and smoke_scan_truth_lane != live_policy_truth_source:
            verdict = "degraded-watch"
            issues.append(
                _issue_payload(
                    issue_id="truth-lane-live-policy-mismatch",
                    source_automation="hourly-operational-health",
                    severity="high",
                    blocker_class="truth_lane_mismatch",
                    summary=(
                        "Operational smoke still shows a mismatch between the scan truth lane and the live policy truth source."
                    ),
                    evidence=[
                        f"smoke_scan_truth_lane={smoke_scan_truth_lane}",
                        f"smoke_live_policy_truth_source={live_policy_truth_source}",
                        f"smoke_requested_policy_truth_lane={smoke_payload.get('requested_policy_truth_lane')}",
                        f"smoke_live_policy_promotion_status={smoke_payload.get('live_policy_promotion_status')}",
                    ],
                    suggested_fix_targets=["options_chatbot.py", "supervised_scan.py", "wfo_optimizer.py"],
                )
            )

    loop_execution_status = "blocked" if verdict == "blocked" else ("degraded" if verdict == "degraded-watch" else "healthy")
    evidence_status = "untrusted" if verdict == "blocked" else "operational_only"
    measurement_gate = _safe_measurement_gate()
    claim_readiness = _safe_claim_readiness()
    loop_health_state = str(measurement_gate.get("state") or "blocked").strip()
    claim_ready = bool(claim_readiness.get("claim_ready", False))
    profitability_verdict = "claim_ready" if claim_ready else ("loop_healthy" if loop_health_state == "healthy" else "unproven")
    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": verdict,
        "run_status": "completed",
        "loop_execution_status": loop_execution_status,
        "evidence_status": evidence_status,
        "profitability_verdict": profitability_verdict,
        "loop_health_state": loop_health_state,
        "claim_ready": claim_ready,
        "evidence_complete": True,
        "proof_reuse": [],
        "proof_bundle_dir": str(proof_dir),
        "proof_context": context,
        "commands": [smoke_record.get("command"), test_record.get("command")],
        "results": {
            "smoke_passed": bool(smoke_record.get("passed")),
            "unittest_passed": bool(test_record.get("passed")),
            "unittest_count": _extract_unittest_count(str(test_record.get("stdout") or "")),
            "executed_test_modules": list(HEALTH_TEST_MODULES),
            "smoke_summary": smoke_payload,
            "smoke_scan_truth_lane": smoke_payload.get("scan_truth_lane"),
            "smoke_live_policy_truth_source": smoke_payload.get("live_policy_truth_source"),
            "smoke_live_policy_error": smoke_payload.get("live_policy_error"),
            "smoke_requested_policy_truth_lane": smoke_payload.get("requested_policy_truth_lane"),
            "smoke_live_policy_promotion_status": smoke_payload.get("live_policy_promotion_status"),
            "smoke_quote_coverage_pct": smoke_payload.get("live_policy_quote_coverage_pct"),
        },
    }
    set_latest_snapshot(state, key="latest_operational_health", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
    reconcile_source_open_issues(
        state,
        source_automation="hourly-operational-health",
        active_issue_ids=[str(issue.get("issue_id") or "").strip() for issue in issues],
        now_iso=now_iso,
        resolution_note="Operational health no longer observes this blocker on the latest smoke and test pass.",
    )
    if not any(str(issue.get("issue_id") or "").strip() == "truth-lane-live-policy-mismatch" for issue in issues):
        _resolve_seed_issue_if_cleared(
            state,
            issue_id="truth-lane-live-policy-mismatch",
            now_iso=now_iso,
            resolution_note="Operational health now shows the live scan truth lane and live policy truth source aligned.",
        )
    complete_active_run(
        state,
        run_id=run["run_id"],
        status="completed",
        phase="completed",
        result_verdict=verdict,
        loop_execution_status=loop_execution_status,
        evidence_status=evidence_status,
        profitability_verdict="unproven",
        now_iso=now_iso,
    )
    _write_json_artifact(
        proof_dir / "operational_health.json",
        {
            "run_id": run["run_id"],
            "snapshot": snapshot,
            "issues": issues,
        },
    )
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run["run_id"],
            "automation_id": "hourly-operational-health",
            "ran_at": now_iso,
            "verdict": verdict,
            "loop_execution_status": loop_execution_status,
            "evidence_status": evidence_status,
            "profitability_verdict": "unproven",
            "state_hash": ((state.get("active_run") or {}).get("state_hash")),
            "issue_ids": [issue["issue_id"] for issue in issues],
        },
        state_dir=state_dir,
    )
    clear_active_run(state, run_id=run["run_id"], now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    return {
        "automation_id": "hourly-operational-health",
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "issues": issues,
    }


def run_truth_holdout(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    daily_truth_refresh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
    context = _proof_context(repo_root=repo_root)
    now = _utc_now()
    now_iso = now.isoformat().replace("+00:00", "Z")
    label_prefix = now.date().isoformat()
    run_id = f"daily-truth-holdout-{now.strftime('%Y%m%dT%H%M%SZ')}"
    run = begin_active_run(
        state,
        automation_id="daily-truth-holdout",
        phase="refresh_truth",
        commit_sha=context["commit_sha"],
        env_hash=context["env_hash"],
        proof_bundle_dir=str(shared_proof_bundle_dir(run_id, state_dir=state_dir)),
        run_id=run_id,
    )
    proof_dir = Path(run["proof_bundle_dir"])
    save_profit_loop_state(state, state_dir=state_dir)
    refresh_result = dict(
        daily_truth_refresh
        or _require_daily_truth_refresh(
            repo_root=repo_root,
            dry_run=dry_run,
            heartbeat=_make_active_run_heartbeat(
                state,
                run_id=run["run_id"],
                phase="refresh_truth",
                state_dir=state_dir,
            ),
        )
    )

    if refresh_result.get("status") == "failed":
        issue = _daily_truth_refresh_failure_issue(
            source_automation="daily-truth-holdout",
            refresh=refresh_result,
        )
        snapshot = {
            "run_id": run["run_id"],
            "ran_at": now_iso,
            "verdict": "blocked-daily-truth-refresh",
            "run_status": "completed",
            "loop_execution_status": "blocked",
            "evidence_status": "untrusted",
            "profitability_verdict": "unproven",
            "evidence_complete": False,
            "proof_reuse": [],
            "proof_bundle_dir": str(proof_dir),
            "proof_context": context,
            "commands": list(refresh_result.get("commands") or []),
            "results": {
                "daily_truth_refresh": refresh_result,
                "forward_summary": None,
            },
        }
        set_latest_snapshot(state, key="latest_truth_holdout", payload=snapshot, now_iso=now_iso)
        upsert_open_issue(state, issue, now_iso=now_iso)
        complete_active_run(
            state,
            run_id=run["run_id"],
            status="failed",
            phase="blocked-daily-truth-refresh",
            result_verdict="blocked-daily-truth-refresh",
            loop_execution_status="blocked",
            evidence_status="untrusted",
            profitability_verdict="unproven",
            now_iso=now_iso,
        )
        _write_json_artifact(
            proof_dir / "truth_holdout.json",
            {
                "run_id": run["run_id"],
                "snapshot": snapshot,
                "issues": [issue],
            },
        )
        save_profit_loop_state(state, state_dir=state_dir)
        if bool(refresh_result.get("timed_out")):
            append_run_ledger(
                {
                    "run_id": run["run_id"],
                    "automation_id": "daily-truth-holdout",
                    "ran_at": now_iso,
                    "verdict": "recovered-timeout-cleanup",
                    "loop_execution_status": "blocked",
                    "evidence_status": "untrusted",
                    "profitability_verdict": "unproven",
                    "phase": refresh_result.get("stage"),
                },
                state_dir=state_dir,
            )
        append_run_ledger(
            {
                "run_id": run["run_id"],
                "automation_id": "daily-truth-holdout",
                "ran_at": now_iso,
                "verdict": "blocked-daily-truth-refresh",
                "loop_execution_status": "blocked",
                "evidence_status": "untrusted",
                "profitability_verdict": "unproven",
                "state_hash": ((state.get("active_run") or {}).get("state_hash")),
                "issue_ids": [issue["issue_id"]],
            },
            state_dir=state_dir,
        )
        clear_active_run(state, run_id=run["run_id"], now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        return {
            "automation_id": "daily-truth-holdout",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": [issue],
        }

    if dry_run:
        policy_payload = {
            "session_id": 0,
            "scan_picks_count": 0,
            "promotion_status": "block",
            "policy_fail_closed": False,
            "scan_funnel": {
                "raw_candidates": 0,
                "post_policy_visible": 0,
                "post_guardrails_visible": 0,
                "returned_picks": 0,
                "policy_filtered_out": 0,
                "guardrail_filtered_out": 0,
                "final_trimmed": 0,
                "policy_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "policy_applied": True,
                "policy_fail_closed": False,
                "include_blocked_policy_picks": False,
                "include_blocked_guardrail_picks": False,
                "drop_counts": {
                    "min_history": 0,
                    "history_or_liquidity": 0,
                    "signal_index": 0,
                    "momentum": 0,
                    "tech_score": 0,
                    "direction_score": 0,
                    "earnings": 0,
                    "option_liquidity": 0,
                    "iv_crush_penalty": 0,
                    "ev_floor": 0,
                    "guardrails": 0,
                    "exceptions": 0,
                },
            },
        }
        policy_record = {
            "command": "python scripts/record_options_forward_truth.py --json [policy-gated]",
            "passed": True,
        }
        raw_payload = dict(policy_payload)
        raw_record = None
        forward_summary = {"available": False, "session_count": 0}
        raw_required = True
        raw_pass_state = "required"
        raw_skip_reason = None
        policy_decisive = False
    else:
        policy_payload, policy_record = _run_json_command(
            [
                sys.executable,
                "scripts/record_options_forward_truth.py",
                "--source",
                f"{label_prefix}_policy_gated_broad_holdout",
                "--playbook",
                "broad",
                "--truth-lane",
                IMPORTED_DAILY_TRUTH_SOURCE,
                "--n-picks",
                "1",
                "--use-recommended-policy",
                "--record-frozen-cohorts",
                "--cohort-id",
                "baseline_broad_control",
                "--cohort-id",
                "broad_ev7_momentum070_exit_time33",
                "--json",
            ],
            cwd=repo_root,
        )
        policy_decisive = int(policy_payload.get("scan_picks_count") or 0) > 0 and not bool(policy_payload.get("policy_fail_closed"))
        raw_required = not policy_decisive
        if raw_required:
            raw_payload, raw_record = _run_json_command(
                [
                    sys.executable,
                    "scripts/record_options_forward_truth.py",
                    "--source",
                    f"{label_prefix}_raw_broad_holdout",
                    "--playbook",
                    "broad",
                    "--truth-lane",
                    IMPORTED_DAILY_TRUTH_SOURCE,
                    "--n-picks",
                    "1",
                    "--use-recommended-policy",
                    "--include-blocked-policy-picks",
                    "--include-blocked-guardrail-picks",
                    "--watchlist-symbol",
                    "SPY",
                    "--watchlist-symbol",
                    "QQQ",
                    "--json",
                ],
                cwd=repo_root,
            )
            raw_pass_state = "run"
            raw_skip_reason = None
        else:
            raw_payload = {
                "session_id": None,
                "scan_picks_count": None,
                "promotion_status": policy_payload.get("promotion_status"),
                "policy_fail_closed": policy_payload.get("policy_fail_closed"),
                "scan_funnel": None,
            }
            raw_record = None
            raw_pass_state = "skipped"
            raw_skip_reason = "policy_decisive"
        forward_summary = summarize_forward_holdout()

    issues: list[dict[str, Any]] = []
    verdict = "recorded"
    raw_scan_picks = int(raw_payload.get("scan_picks_count") or 0) if raw_required else None
    policy_scan_funnel = _normalized_scan_funnel(policy_payload.get("scan_funnel"))
    raw_scan_funnel = _normalized_scan_funnel(raw_payload.get("scan_funnel")) if raw_required else None
    holdout_funnel = {
        "policy_decisive": bool(policy_decisive),
        "raw_required": bool(raw_required),
        "raw_pass_state": raw_pass_state,
        "raw_skip_reason": raw_skip_reason,
        "policy": {
            **policy_scan_funnel,
            "stage": _scan_funnel_stage(policy_payload.get("scan_funnel")),
        },
        "raw": None if raw_scan_funnel is None else {
            **raw_scan_funnel,
            "stage": _scan_funnel_stage(raw_payload.get("scan_funnel")),
        },
    }
    selected_scan_funnel = raw_scan_funnel if raw_required and raw_pass_state == "run" and raw_scan_funnel is not None else policy_scan_funnel
    candidate_flow_breakdown = _candidate_flow_breakdown(
        selected_scan_funnel,
        refresh_status=str(refresh_result.get("status") or "").strip().lower(),
    )
    raw_candidates_zero = int(policy_scan_funnel.get("raw_candidates") or 0) <= 0 and (raw_scan_funnel is None or int(raw_scan_funnel.get("raw_candidates") or 0) <= 0)
    zero_candidate_market_state = _zero_candidate_market_state(candidate_flow_breakdown)
    if raw_candidates_zero and not zero_candidate_market_state:
        verdict = "recorded-no-candidates"
        issues.append(
            _issue_payload(
                issue_id="forward-holdout-no-raw-candidates",
                source_automation="daily-truth-holdout",
                severity="high",
                blocker_class="scan_starvation",
                summary="Forward holdout recorded successfully but scanner diagnostics show zero raw candidates, so the evidence is not strong enough to claim forward improvement.",
                evidence=[
                    f"policy_gated_session_id={policy_payload.get('session_id')}",
                    f"raw_session_id={raw_payload.get('session_id')}",
                    f"policy_gated_scan_picks={policy_payload.get('scan_picks_count')}",
                    f"raw_scan_picks={raw_payload.get('scan_picks_count')}",
                    f"raw_required={raw_required}",
                    f"raw_pass_state={raw_pass_state}",
                    f"raw_skip_reason={raw_skip_reason}",
                    f"candidate_flow_classification={candidate_flow_breakdown['classification']}",
                    f"primary_starving_gate={candidate_flow_breakdown.get('primary_starving_gate')}",
                    f"promotion_status={raw_payload.get('promotion_status') or policy_payload.get('promotion_status')}",
                    f"policy_fail_closed={raw_payload.get('policy_fail_closed')}",
                    f"policy_scan_funnel={json.dumps(policy_scan_funnel, sort_keys=True)}",
                    f"raw_scan_funnel={json.dumps(raw_scan_funnel, sort_keys=True) if raw_scan_funnel is not None else 'null'}",
                    f"holdout_funnel={json.dumps(holdout_funnel, sort_keys=True)}",
                ],
                suggested_fix_targets=["supervised_scan.py", "options_chatbot.py", "docs/autoresearch/truth-first-champions.json"],
            )
        )
    elif raw_candidates_zero:
        verdict = "recorded-empty-market"

    _holdout_low_evidence = verdict in {"recorded-no-candidates", "recorded-empty-market"}
    loop_execution_status = "degraded" if _holdout_low_evidence else "healthy"
    evidence_status = "inconclusive" if _holdout_low_evidence else "recorded_pending_validation"
    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": verdict,
        "run_status": "completed",
        "loop_execution_status": loop_execution_status,
        "evidence_status": evidence_status,
        "profitability_verdict": "unproven",
        "evidence_complete": verdict not in {"recorded-no-candidates", "recorded-empty-market"},
        "proof_reuse": [],
        "proof_bundle_dir": str(proof_dir),
        "proof_context": context,
        "commands": list(refresh_result.get("commands") or []) + [policy_record.get("command")] + ([raw_record.get("command")] if raw_record else []),
        "results": {
            "daily_truth_refresh": refresh_result,
            "policy_gated_session_id": policy_payload.get("session_id"),
            "raw_session_id": raw_payload.get("session_id"),
            "policy_gated_scan_picks": policy_payload.get("scan_picks_count"),
            "raw_scan_picks": raw_scan_picks,
            "raw_required": raw_required,
            "raw_pass_state": raw_pass_state,
            "raw_skip_reason": raw_skip_reason,
            "promotion_status": raw_payload.get("promotion_status") or policy_payload.get("promotion_status"),
            "policy_fail_closed": raw_payload.get("policy_fail_closed"),
            "policy_scan_funnel": policy_scan_funnel,
            "raw_scan_funnel": raw_scan_funnel,
            "holdout_funnel": holdout_funnel,
            "candidate_flow_breakdown": candidate_flow_breakdown,
            "evidence_blocker": (
                candidate_flow_breakdown.get("primary_starving_gate")
                or "raw_candidates_zero"
            ) if verdict == "recorded-no-candidates" else None,
            "empty_market": bool(raw_candidates_zero and zero_candidate_market_state),
            "forward_summary": forward_summary,
        },
    }
    set_latest_snapshot(state, key="latest_truth_holdout", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
    reconcile_source_open_issues(
        state,
        source_automation="daily-truth-holdout",
        active_issue_ids=[str(issue.get("issue_id") or "").strip() for issue in issues],
        now_iso=now_iso,
        resolution_note="Latest truth holdout no longer observes this blocker.",
    )
    if verdict != "recorded-no-candidates":
        _resolve_seed_issue_if_cleared(
            state,
            issue_id="forward-holdout-no-raw-candidates",
            now_iso=now_iso,
            resolution_note="Latest truth holdout either produced candidates or recorded a genuine empty market without scan starvation.",
        )
    complete_active_run(
        state,
        run_id=run["run_id"],
        status="completed",
        phase="completed",
        result_verdict=verdict,
        loop_execution_status=loop_execution_status,
        evidence_status=evidence_status,
        profitability_verdict="unproven",
        now_iso=now_iso,
    )
    _write_json_artifact(
        proof_dir / "truth_holdout.json",
        {
            "run_id": run["run_id"],
            "snapshot": snapshot,
            "issues": issues,
        },
    )
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run["run_id"],
            "automation_id": "daily-truth-holdout",
            "ran_at": now_iso,
                "verdict": verdict,
                "loop_execution_status": loop_execution_status,
                "evidence_status": evidence_status,
                "profitability_verdict": "unproven",
                "state_hash": ((state.get("active_run") or {}).get("state_hash")),
                "issue_ids": [issue["issue_id"] for issue in issues],
        },
        state_dir=state_dir,
    )
    clear_active_run(state, run_id=run["run_id"], now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    return {
        "automation_id": "daily-truth-holdout",
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "issues": issues,
    }


def _prerequisite_issue(blocker: dict[str, Any]) -> dict[str, Any]:
    code = str(blocker.get("code") or "validation-prerequisite-blocker").strip()
    return _issue_payload(
        issue_id=f"profit-validation-{code}",
        source_automation="daily-profit-validation",
        severity="high",
        blocker_class="storage",
        summary=str(blocker.get("message") or "Profit validation prerequisites are missing or stale."),
        evidence=[f"{key}={value}" for key, value in sorted(dict(blocker).items()) if key != "message"],
        suggested_fix_targets=["profit_loop_shared_state.py", "profit_loop_automation.py", "scripts/automation_profit_validation.py"],
    )


def prepare_profit_validation(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    auto_defer: bool = True,
    daily_truth_refresh: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    context = _proof_context(repo_root=repo_root)

    blockers = validation_prerequisite_blockers(state)
    if blockers:
        run_id = f"daily-profit-validation-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}"
        issues = []
        for blocker in blockers:
            issue = _prerequisite_issue(blocker)
            issues.append(issue)
            upsert_open_issue(state, issue, now_iso=now_iso)
        snapshot = {
            "run_id": run_id,
            "ran_at": now_iso,
            "verdict": "blocked-prerequisites",
            "run_status": "completed",
            "loop_execution_status": "blocked",
            "evidence_status": "untrusted",
            "profitability_verdict": "unproven",
            "evidence_complete": False,
            "proof_reuse": [],
            "proof_context": context,
            "targeted_issue_id": None,
            "prerequisite_blockers": blockers,
            "baseline": None,
            "profitability_prerequisites": {
                "holdout_has_candidate_flow": False,
                "measurement_gate_state": "blocked",
                "comparison_spec_exact_match": False,
                "forward_evidence_status": "untrusted",
                "truth_quality_regressed": False,
                "safety_regressed": False,
                "material_drawdown_worsened": False,
            },
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        append_run_ledger(
            {
                "run_id": run_id,
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "blocked-prerequisites",
                "loop_execution_status": "blocked",
                "evidence_status": "untrusted",
                "profitability_verdict": "unproven",
                "issue_ids": [issue["issue_id"] for issue in issues],
            },
            state_dir=state_dir,
        )
        return {
            "automation_id": "daily-profit-validation",
            "action": "blocked_prerequisites",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": issues,
        }

    open_issues = prioritized_open_issues(state)
    if not open_issues:
        run_id = f"daily-profit-validation-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}"
        snapshot = {
            "run_id": run_id,
            "ran_at": now_iso,
            "verdict": "queue-empty",
            "run_status": "completed",
            "loop_execution_status": "idle",
            "evidence_status": "inconclusive",
            "profitability_verdict": "unproven",
            "evidence_complete": False,
            "proof_reuse": [],
            "proof_context": context,
            "targeted_issue_id": None,
            "prerequisite_blockers": [],
            "baseline": None,
            "profitability_prerequisites": {
                "holdout_has_candidate_flow": False,
                "measurement_gate_state": None,
                "comparison_spec_exact_match": False,
                "forward_evidence_status": "unproven",
                "truth_quality_regressed": False,
                "safety_regressed": False,
                "material_drawdown_worsened": False,
            },
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        append_run_ledger(
            {
                "run_id": run_id,
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "queue-empty",
                "loop_execution_status": "idle",
                "evidence_status": "inconclusive",
                "profitability_verdict": "unproven",
                "issue_ids": [],
            },
            state_dir=state_dir,
        )
        return {
            "automation_id": "daily-profit-validation",
            "action": "queue_empty",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": [],
        }

    candidate_issue = dict(open_issues[0])
    run_id = f"daily-profit-validation-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}"
    run = begin_active_run(
        state,
        automation_id="daily-profit-validation",
        phase="refresh_truth",
        commit_sha=context["commit_sha"],
        env_hash=context["env_hash"],
        proof_bundle_dir=str(shared_proof_bundle_dir(run_id, state_dir=state_dir)),
        run_id=run_id,
    )
    proof_dir = Path(run["proof_bundle_dir"])
    save_profit_loop_state(state, state_dir=state_dir)
    refresh_result = dict(
        daily_truth_refresh
        or _require_daily_truth_refresh(
            repo_root=repo_root,
            dry_run=dry_run,
            heartbeat=_make_active_run_heartbeat(
                state,
                run_id=run["run_id"],
                phase="refresh_truth",
                state_dir=state_dir,
            ),
        )
    )
    if refresh_result.get("status") == "failed":
        issue = _daily_truth_refresh_failure_issue(
            source_automation="daily-profit-validation",
            refresh=refresh_result,
        )
        snapshot = {
            "run_id": run["run_id"],
            "ran_at": now_iso,
            "verdict": "blocked-daily-truth-refresh",
            "run_status": "completed",
            "loop_execution_status": "blocked",
            "evidence_status": "untrusted",
            "profitability_verdict": "unproven",
            "evidence_complete": False,
            "proof_reuse": [],
            "proof_bundle_dir": str(proof_dir),
            "proof_context": context,
            "targeted_issue_id": candidate_issue["issue_id"],
            "prerequisite_blockers": [],
            "daily_truth_refresh": refresh_result,
            "baseline": None,
            "profitability_prerequisites": {
                "holdout_has_candidate_flow": False,
                "measurement_gate_state": "blocked",
                "comparison_spec_exact_match": False,
                "forward_evidence_status": "untrusted",
                "truth_quality_regressed": False,
                "safety_regressed": False,
                "material_drawdown_worsened": False,
            },
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        upsert_open_issue(state, issue, now_iso=now_iso)
        complete_active_run(
            state,
            run_id=run["run_id"],
            status="failed",
            phase="blocked-daily-truth-refresh",
            result_verdict="blocked-daily-truth-refresh",
            loop_execution_status="blocked",
            evidence_status="untrusted",
            profitability_verdict="unproven",
            now_iso=now_iso,
        )
        _write_json_artifact(
            proof_dir / "validation_baseline.json",
            {
                "run_id": run["run_id"],
                "targeted_issue_id": candidate_issue["issue_id"],
                "snapshot": snapshot,
                "issues": [issue],
            },
        )
        save_profit_loop_state(state, state_dir=state_dir)
        if bool(refresh_result.get("timed_out")):
            append_run_ledger(
                {
                    "run_id": run["run_id"],
                    "automation_id": "daily-profit-validation",
                    "ran_at": now_iso,
                    "verdict": "recovered-timeout-cleanup",
                    "loop_execution_status": "blocked",
                    "evidence_status": "untrusted",
                    "profitability_verdict": "unproven",
                    "phase": refresh_result.get("stage"),
                },
                state_dir=state_dir,
            )
        append_run_ledger(
            {
                "run_id": run["run_id"],
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "blocked-daily-truth-refresh",
                "loop_execution_status": "blocked",
                "evidence_status": "untrusted",
                "profitability_verdict": "unproven",
                "state_hash": ((state.get("active_run") or {}).get("state_hash")),
                "issue_ids": [candidate_issue["issue_id"], issue["issue_id"]],
            },
            state_dir=state_dir,
        )
        clear_active_run(state, run_id=run["run_id"], now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        return {
            "automation_id": "daily-profit-validation",
            "action": "blocked_daily_truth_refresh",
            "state_dir": str(shared_state_dir(state_dir)),
            "snapshot": snapshot,
            "issues": [issue],
            "targeted_issue": candidate_issue,
        }

    targeted_issue = claim_issue(
        state,
        candidate_issue["issue_id"],
        now_iso=now_iso,
        next_action=VALIDATION_PRIORITY_NEXT_ACTION.get(
            candidate_issue["issue_id"],
            "Investigate the claimed blocker and either land a verified deterministic fix or defer it with exact next steps.",
        ),
        claim_run_id=run["run_id"],
    )
    for open_issue in state.get("open_issues") or []:
        if open_issue.get("issue_id") == targeted_issue["issue_id"]:
            open_issue["proof_bundle_dir"] = str(proof_dir)
            break
    heartbeat_active_run(state, run_id=run["run_id"], phase="capture_baseline", now_iso=now_iso)
    baseline = _capture_validation_baseline(
        issue=targeted_issue,
        state=state,
        run_id=run["run_id"],
        state_dir=state_dir,
        repo_root=repo_root,
        dry_run=dry_run,
    )
    evidence_complete = bool(baseline.get("smoke_summary")) and bool(baseline.get("validation_tests_passed"))
    if baseline.get("proof_plan", {}).get("needs_replay_matrix"):
        replay_assessment = dict(baseline.get("replay_matrix_assessment") or {})
        evidence_complete = evidence_complete and bool(replay_assessment.get("is_valid"))
    if baseline.get("proof_plan", {}).get("needs_holdout"):
        evidence_complete = evidence_complete and bool(baseline.get("holdout_evidence"))

    # Check if bootstrap recovery is needed
    _bootstrap_check = check_bootstrap_recovery_needed(baseline)
    if _bootstrap_check.get("recovery_needed"):
        _bootstrap_issue = _issue_payload(
            issue_id="bootstrap-dominance-recovery-needed",
            source_automation="profit-validation",
            severity="high",
            blocker_class="calibration",
            summary=(
                f"Bootstrap heuristic dominates at {_bootstrap_check['bootstrap_pct']:.0f}% "
                f"({_bootstrap_check['bootstrap_count']}/{_bootstrap_check['total_trades']} trades). "
                f"Suggested: extend lookback to {_bootstrap_check['suggested_lookback_years']}y and re-import daily truth."
            ),
            evidence=[
                f"bootstrap_pct={_bootstrap_check['bootstrap_pct']:.1f}",
                f"current_lookback={_bootstrap_check.get('current_lookback_years')}",
                f"suggested_lookback={_bootstrap_check.get('suggested_lookback_years')}",
            ],
            suggested_fix_targets=["profit_loop_automation.py", "wfo_optimizer.py"],
        )
        upsert_open_issue(state, _bootstrap_issue, now_iso=now_iso)

    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": "claimed-issue" if not auto_defer else "deferred",
        "run_status": "completed",
        "loop_execution_status": "degraded",
        "evidence_status": "trusted" if evidence_complete else "inconclusive",
        "profitability_verdict": "unproven",
        "evidence_complete": evidence_complete,
        "proof_reuse": list(baseline.get("proof_reuse") or []),
        "proof_bundle_dir": str(proof_dir),
        "proof_context": dict(baseline.get("proof_context") or context),
        "targeted_issue_id": targeted_issue["issue_id"],
        "prerequisite_blockers": [],
        "daily_truth_refresh": refresh_result,
        "baseline": baseline,
        "profitability_prerequisites": {
            "holdout_has_candidate_flow": _holdout_has_nonzero_candidate_flow((baseline.get("holdout_evidence") or {})),
            "measurement_gate_state": None,
            "comparison_spec_exact_match": False,
            "forward_evidence_status": "unproven",
            "truth_quality_regressed": False,
            "safety_regressed": False,
            "material_drawdown_worsened": False,
        },
    }

    result_action = "claimed_issue"
    auto_cleared_seed_issue = None
    if _replay_matrix_seed_issue_cleared(targeted_issue, baseline):
        cleared = _resolve_seed_issue_if_cleared(
            state,
            issue_id=targeted_issue["issue_id"],
            now_iso=now_iso,
            resolution_note=(
                "Imported executable truth intentionally normalizes requested replay pricing lanes, and the latest "
                "replay matrix still shows distinct lookback behavior after that normalization."
            ),
        )
        auto_cleared_seed_issue = next(
            (item for item in cleared if str(item.get("issue_id") or "").strip() == targeted_issue["issue_id"]),
            None,
        )
        result_action = "resolved_no_longer_observed"
        snapshot["verdict"] = "resolved-no-longer-observed"
        snapshot["loop_execution_status"] = "degraded"
        snapshot["evidence_status"] = "auto_cleared"
        snapshot["evidence_complete"] = False
        snapshot["resolved_issue"] = targeted_issue["issue_id"]
        snapshot["resolution_note"] = (
            "Replay-matrix pricing-lane collapse is expected under imported executable truth and no longer blocks validation."
        )
    elif auto_defer:
        deferred = defer_issue(
            state,
            targeted_issue["issue_id"],
            deferred_reason="no_safe_fix_plan",
            next_action=VALIDATION_PRIORITY_NEXT_ACTION.get(
                targeted_issue["issue_id"],
                "Investigate the claimed blocker and either land a verified deterministic fix or defer it with exact next steps.",
            ),
            now_iso=now_iso,
        )
        result_action = "deferred"
        snapshot["deferred_issue"] = deferred["issue_id"]

    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    complete_active_run(
        state,
        run_id=run["run_id"],
        status="completed",
        phase="completed",
        result_verdict=snapshot["verdict"],
        loop_execution_status=snapshot["loop_execution_status"],
        evidence_status=snapshot["evidence_status"],
        profitability_verdict="unproven",
        now_iso=now_iso,
    )
    _write_json_artifact(
        proof_dir / "validation_baseline.json",
        {
            "run_id": run["run_id"],
            "targeted_issue_id": targeted_issue["issue_id"],
            **baseline,
            "snapshot": snapshot,
            "resolved_issue": auto_cleared_seed_issue,
        },
    )
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run["run_id"],
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": snapshot["verdict"],
            "loop_execution_status": snapshot["loop_execution_status"],
            "evidence_status": snapshot["evidence_status"],
            "profitability_verdict": "unproven",
            "state_hash": ((state.get("active_run") or {}).get("state_hash")),
            "issue_ids": [targeted_issue["issue_id"]],
        },
        state_dir=state_dir,
    )
    clear_active_run(state, run_id=run["run_id"], now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    return {
        "automation_id": "daily-profit-validation",
        "action": result_action,
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "targeted_issue": targeted_issue,
        "resolved_issue": auto_cleared_seed_issue,
    }


def resolve_profit_validation_issue(
    *,
    issue_id: str,
    resolution_branch: str,
    resolution_commit: str,
    proof_commands: list[str] | None = None,
    before_after_comparison: dict[str, Any] | None = None,
    state_dir: str | Path | None = None,
) -> dict[str, Any]:
    if not list(proof_commands or []):
        raise ValueError("proof_commands are required to resolve a validation issue")
    if before_after_comparison is None:
        raise ValueError("before_after_comparison is required to resolve a validation issue")
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    latest_snapshot = dict(state.get("latest_profit_validation") or {})
    run_id = str(latest_snapshot.get("run_id") or f"daily-profit-validation-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}").strip()
    proof_dir = Path(str(latest_snapshot.get("proof_bundle_dir") or shared_proof_bundle_dir(run_id, state_dir=state_dir)))
    context = _proof_context(repo_root=ROOT_DIR)
    proof_blockers, baseline_artifact = _resolution_prerequisite_blockers(
        state=state,
        current_context=context,
        issue_id=issue_id,
        proof_dir=proof_dir,
        proof_commands=[str(item).strip() for item in list(proof_commands or []) if str(item).strip()],
        before_after_comparison=before_after_comparison,
    )
    if proof_blockers:
        raise ValueError(f"Cannot resolve validation issue without healthy prerequisites and proof artifacts: {proof_blockers}")
    baseline_artifact = dict(baseline_artifact or {})
    baseline_commands = _proof_command_texts(list(baseline_artifact.get("commands") or []))
    missing_commands = [str(item).strip() for item in list(proof_commands or []) if str(item).strip() not in baseline_commands]
    if missing_commands:
        raise ValueError(f"proof_commands do not match the executed commands in the validation baseline: {missing_commands}")
    baseline_profitability_verdict = _evaluate_profitability_verdict(before_after_comparison)
    health_snapshot = dict(state.get("latest_operational_health") or {})
    health_status = str(health_snapshot.get("loop_execution_status") or _infer_loop_execution_status(health_snapshot)).strip().lower()
    holdout_snapshot = dict(state.get("latest_truth_holdout") or {})
    holdout_verdict = str(holdout_snapshot.get("verdict") or "").strip().lower()
    holdout_has_candidate_flow = _holdout_has_nonzero_candidate_flow(holdout_snapshot.get("results") or {})
    measurement_gate = _safe_measurement_gate()
    measurement_gate_state = str(measurement_gate.get("state") or "blocked").strip().lower()
    comparison_spec = dict(before_after_comparison.get("comparison_spec") or {})
    comparison_spec_exact_match = all(
        key in comparison_spec
        for key in ("playbook", "truth_lane", "pricing_lane", "lookback_years", "n_picks", "iv_adj")
    )
    forward_evidence_status = str(before_after_comparison.get("forward_evidence_status") or "sparse").strip().lower()
    truth_quality_regressed = bool(before_after_comparison.get("truth_quality_regressed"))
    safety_regressed = bool(before_after_comparison.get("safety_regressed"))
    material_drawdown_worsened = bool(before_after_comparison.get("material_drawdown_worsened"))
    profitability_verdict = baseline_profitability_verdict
    if baseline_profitability_verdict == "improved" and (
        health_status != "healthy"
        or holdout_verdict != "recorded"
        or not holdout_has_candidate_flow
        or measurement_gate_state != "healthy"
        or not comparison_spec_exact_match
    ):
        profitability_verdict = "inconclusive"
    evidence_status = "trusted" if profitability_verdict == "improved" else "inconclusive"
    evidence_complete = evidence_status == "trusted"
    loop_execution_status = "healthy" if profitability_verdict == "improved" and evidence_complete else "degraded"
    profitability_prerequisites = {
        "operational_health_verdict": health_snapshot.get("verdict"),
        "operational_health_status": health_status or None,
        "truth_holdout_verdict": holdout_snapshot.get("verdict"),
        "holdout_has_candidate_flow": holdout_has_candidate_flow,
        "measurement_gate_state": measurement_gate_state,
        "comparison_spec_exact_match": comparison_spec_exact_match,
        "forward_evidence_status": forward_evidence_status,
        "truth_quality_regressed": truth_quality_regressed,
        "safety_regressed": safety_regressed,
        "material_drawdown_worsened": material_drawdown_worsened,
    }
    resolved = resolve_issue(
        state,
        issue_id,
        resolution_branch=resolution_branch,
        resolution_commit=resolution_commit,
        proof_bundle_dir=str(proof_dir),
        proof_commands=list(proof_commands or []),
        before_after_comparison=before_after_comparison,
        now_iso=now_iso,
    )
    snapshot = {
        "run_id": run_id,
        "ran_at": now_iso,
        "verdict": "resolved",
        "run_status": "completed",
        "loop_execution_status": loop_execution_status,
        "evidence_status": evidence_status,
        "profitability_verdict": profitability_verdict,
        "evidence_complete": evidence_complete,
        "proof_reuse": [],
        "proof_bundle_dir": str(proof_dir),
        "proof_context": context,
        "targeted_issue_id": issue_id,
        "resolution_branch": resolution_branch,
        "resolution_commit": resolution_commit,
        "resolution_kind": resolved.get("resolution_kind"),
        "proof_commands": list(proof_commands or []),
        "before_after_comparison": copy.deepcopy(before_after_comparison),
        "measurement_gate": measurement_gate,
        "profitability_prerequisites": profitability_prerequisites,
    }
    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    _write_json_artifact(
        proof_dir / "resolution.json",
        {
            "run_id": run_id,
            "issue_id": issue_id,
            "resolution_branch": resolution_branch,
            "resolution_commit": resolution_commit,
            "proof_commands": list(proof_commands or []),
            "before_after_comparison": before_after_comparison,
            "measurement_gate": measurement_gate,
            "profitability_prerequisites": profitability_prerequisites,
            "profitability_verdict": profitability_verdict,
        },
    )
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run_id,
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": "resolved",
            "loop_execution_status": loop_execution_status,
            "evidence_status": evidence_status,
            "profitability_verdict": profitability_verdict,
            "issue_ids": [issue_id],
            "resolution_branch": resolution_branch,
            "resolution_commit": resolution_commit,
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": "resolved",
        "state_dir": str(shared_state_dir(state_dir)),
        "resolved_issue": resolved,
        "snapshot": snapshot,
    }


def defer_profit_validation_issue(
    *,
    issue_id: str,
    deferred_reason: str,
    next_action: str,
    state_dir: str | Path | None = None,
) -> dict[str, Any]:
    state = load_profit_loop_state(state_dir)
    now_iso = utc_now_iso()
    latest_snapshot = dict(state.get("latest_profit_validation") or {})
    run_id = str(latest_snapshot.get("run_id") or f"daily-profit-validation-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}").strip()
    deferred = defer_issue(
        state,
        issue_id,
        deferred_reason=deferred_reason,
        next_action=next_action,
        now_iso=now_iso,
    )
    snapshot = {
        "run_id": run_id,
        "ran_at": now_iso,
        "verdict": "deferred",
        "run_status": "completed",
        "loop_execution_status": "degraded",
        "evidence_status": "inconclusive",
        "profitability_verdict": "inconclusive",
        "evidence_complete": False,
        "proof_reuse": [],
        "targeted_issue_id": issue_id,
        "deferred_reason": deferred_reason,
        "next_action": next_action,
        "profitability_prerequisites": {
            "holdout_has_candidate_flow": False,
            "measurement_gate_state": None,
            "comparison_spec_exact_match": False,
            "forward_evidence_status": "inconclusive",
            "truth_quality_regressed": False,
            "safety_regressed": False,
            "material_drawdown_worsened": False,
        },
    }
    set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run_id,
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": "deferred",
            "loop_execution_status": "degraded",
            "evidence_status": "inconclusive",
            "profitability_verdict": "inconclusive",
            "issue_ids": [issue_id],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": "deferred",
        "state_dir": str(shared_state_dir(state_dir)),
        "deferred_issue": deferred,
        "snapshot": snapshot,
    }


def run_profit_loop_canary(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    before_events = list_run_ledger_events(state_dir)
    daily_truth_refresh = _require_daily_truth_refresh(repo_root=repo_root, dry_run=dry_run)
    if str(daily_truth_refresh.get("status") or "").strip().lower() == "failed":
        after_events = list_run_ledger_events(state_dir)
        new_events = after_events[len(before_events) :]
        return {
            "ran_at": utc_now_iso(),
            "state_dir": str(shared_state_dir(state_dir)),
            "dry_run": bool(dry_run),
            "exit_code": 2,
            "daily_truth_refresh": daily_truth_refresh,
            "consistency": {
                "new_event_count": 0,
                "raw_new_event_count": len(new_events),
                "expected_automation_ids": ["hourly-operational-health", "daily-truth-holdout", "daily-profit-validation"],
                "expected_run_ids": [],
                "observed_automation_ids": [],
                "raw_observed_automation_ids": [str(item.get("automation_id") or "") for item in new_events],
                "latest_snapshot_run_ids": [],
                "ledger_run_ids": [],
                "raw_ledger_run_ids": [str(item.get("run_id") or "") for item in new_events],
            },
            "steps": [],
        }
    health = run_operational_health(state_dir=state_dir, repo_root=repo_root, dry_run=dry_run)
    holdout = run_truth_holdout(
        state_dir=state_dir,
        repo_root=repo_root,
        dry_run=dry_run,
        daily_truth_refresh=daily_truth_refresh,
    )
    validation = prepare_profit_validation(
        state_dir=state_dir,
        repo_root=repo_root,
        dry_run=dry_run,
        auto_defer=True,
        daily_truth_refresh=daily_truth_refresh,
    )
    state = load_profit_loop_state(state_dir)
    after_events = list_run_ledger_events(state_dir)
    new_events = after_events[len(before_events) :]
    expected_ids = ["hourly-operational-health", "daily-truth-holdout", "daily-profit-validation"]
    expected_run_ids = [
        str(((health.get("snapshot") or {}).get("run_id")) or ""),
        str(((holdout.get("snapshot") or {}).get("run_id")) or ""),
        str(((validation.get("snapshot") or {}).get("run_id")) or ""),
    ]
    matched_events = [
        dict(item)
        for item in new_events
        if str(item.get("automation_id") or "") in expected_ids and str(item.get("run_id") or "") in expected_run_ids
    ]
    event_ids = [str(item.get("automation_id") or "") for item in new_events]
    matched_event_ids = [str(item.get("automation_id") or "") for item in matched_events]
    latest_run_ids = [
        str((state.get("latest_operational_health") or {}).get("run_id") or ""),
        str((state.get("latest_truth_holdout") or {}).get("run_id") or ""),
        str((state.get("latest_profit_validation") or {}).get("run_id") or ""),
    ]
    ledger_run_ids = [str(item.get("run_id") or "") for item in matched_events]
    consistency = {
        "new_event_count": len(matched_events),
        "raw_new_event_count": len(new_events),
        "expected_automation_ids": expected_ids,
        "expected_run_ids": expected_run_ids,
        "observed_automation_ids": matched_event_ids,
        "raw_observed_automation_ids": event_ids,
        "latest_snapshot_run_ids": latest_run_ids,
        "ledger_run_ids": ledger_run_ids,
        "raw_ledger_run_ids": [str(item.get("run_id") or "") for item in new_events],
    }
    exit_code = 0
    if len(matched_events) != 3 or matched_event_ids != expected_ids or latest_run_ids != expected_run_ids or ledger_run_ids != expected_run_ids:
        exit_code = 2
    elif any(
        str(((step.get("snapshot") or {}).get("loop_execution_status")) or "").strip().lower() == "blocked"
        for step in [health, holdout, validation]
    ):
        exit_code = 2
    return {
        "ran_at": utc_now_iso(),
        "state_dir": str(shared_state_dir(state_dir)),
        "dry_run": bool(dry_run),
        "exit_code": exit_code,
        "daily_truth_refresh": daily_truth_refresh,
        "consistency": consistency,
        "steps": [health, holdout, validation],
    }


def check_bootstrap_recovery_needed(result: dict[str, Any] | None) -> dict[str, Any]:
    """
    Check if a backtest result is dominated by bootstrap heuristic trades
    and suggest recovery actions.
    """
    if not result:
        return {"recovery_needed": False, "reason": "no_result"}

    trades = list(result.get("trades") or [])
    if not trades:
        return {"recovery_needed": False, "reason": "no_trades"}

    bootstrap_count = sum(
        1 for t in trades
        if str(t.get("expectancy_selection_source") or "").strip().lower() == "bootstrap_heuristic"
    )
    total = len(trades)
    bootstrap_pct = (bootstrap_count / total * 100.0) if total > 0 else 0.0

    if bootstrap_pct < BOOTSTRAP_DOMINANCE_THRESHOLD_PCT:
        return {
            "recovery_needed": False,
            "bootstrap_pct": round(bootstrap_pct, 1),
            "total_trades": total,
        }

    current_lookback = int(result.get("lookback_years", 1) or 1)
    suggested_lookback = min(
        BOOTSTRAP_RECOVERY_EXTENDED_LOOKBACK_YEARS,
        current_lookback + 1,
    )

    return {
        "recovery_needed": True,
        "bootstrap_pct": round(bootstrap_pct, 1),
        "total_trades": total,
        "bootstrap_count": bootstrap_count,
        "current_lookback_years": current_lookback,
        "suggested_lookback_years": suggested_lookback,
        "actions": [
            "trigger_historical_data_import",
            f"rerun_backtest_with_lookback_{suggested_lookback}y",
            "switch_to_imported_daily_truth_source",
        ],
    }


RESEARCH_RUNS_DIR = ROOT_DIR / "research_runs"
MAX_RETAINED_RESEARCH_RUNS = 30


def cleanup_research_runs(
    *,
    max_retain: int = MAX_RETAINED_RESEARCH_RUNS,
    protected_run_ids: set[str] | None = None,
) -> dict[str, Any]:
    """
    Remove old research runs, keeping the most recent max_retain runs
    plus any runs referenced by current incumbents.
    """
    runs_dir = RESEARCH_RUNS_DIR
    if not runs_dir.exists():
        return {"cleaned": 0, "retained": 0, "errors": []}

    protected = set(protected_run_ids or set())
    all_runs: list[tuple[float, Path]] = []
    errors: list[str] = []

    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            mtime = entry.stat().st_mtime
            all_runs.append((mtime, entry))
        except OSError as exc:
            errors.append(f"Cannot stat {entry.name}: {exc}")

    # Sort newest first
    all_runs.sort(key=lambda x: x[0], reverse=True)

    retained: list[str] = []
    to_remove: list[Path] = []

    for idx, (mtime, run_path) in enumerate(all_runs):
        run_name = run_path.name
        if idx < max_retain or run_name in protected:
            retained.append(run_name)
        else:
            to_remove.append(run_path)

    cleaned = 0
    for run_path in to_remove:
        try:
            import shutil
            shutil.rmtree(run_path)
            cleaned += 1
        except OSError as exc:
            errors.append(f"Cannot remove {run_path.name}: {exc}")

    return {
        "cleaned": cleaned,
        "retained": len(retained),
        "total_found": len(all_runs),
        "errors": errors,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Shared-state automation drivers for the options profit loop.")
    parser.add_argument(
        "mode",
        choices=[
            "daily-truth-refresh",
            "daily-truth-refresh-artifact",
            "operational-health",
            "truth-holdout",
            "profit-validation",
            "profit-validation-resolve",
            "profit-validation-defer",
            "canary",
        ],
    )
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-code-change", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--issue-id", default=None)
    parser.add_argument("--resolution-branch", default=None)
    parser.add_argument("--resolution-commit", default=None)
    parser.add_argument("--proof-command", action="append", default=[])
    parser.add_argument("--before-after-json", default=None)
    parser.add_argument("--deferred-reason", default=None)
    parser.add_argument("--next-action", default=None)
    parser.add_argument("--lookback-years", type=int, default=DEFAULT_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS)
    parser.add_argument("--n-picks", type=int, default=DEFAULT_DAILY_TRUTH_REFRESH_N_PICKS)
    parser.add_argument("--iv-adj", type=float, default=DEFAULT_DAILY_TRUTH_REFRESH_IV_ADJ)
    parser.add_argument("--pricing-lane", default=DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE)
    parser.add_argument("--playbook", default=DEFAULT_DAILY_TRUTH_REFRESH_PLAYBOOK)
    parser.add_argument("--truth-lane", default=IMPORTED_DAILY_TRUTH_SOURCE)
    args = parser.parse_args(argv)

    if args.mode == "daily-truth-refresh":
        result = _refresh_daily_truth(dry_run=args.dry_run)
    elif args.mode == "daily-truth-refresh-artifact":
        result = run_historical_backtest(
            lookback_years=int(args.lookback_years),
            n_picks=int(args.n_picks),
            iv_adj=float(args.iv_adj),
            pricing_lane=str(args.pricing_lane),
            truth_lane=str(args.truth_lane),
            playbook=str(args.playbook),
        )
    elif args.mode == "operational-health":
        result = run_operational_health(state_dir=args.state_dir, dry_run=args.dry_run)
    elif args.mode == "truth-holdout":
        result = run_truth_holdout(state_dir=args.state_dir, dry_run=args.dry_run)
    elif args.mode == "profit-validation":
        result = prepare_profit_validation(
            state_dir=args.state_dir,
            dry_run=args.dry_run,
            auto_defer=not bool(args.prepare_only),
        )
    elif args.mode == "profit-validation-resolve":
        if not args.issue_id or not args.resolution_branch or not args.resolution_commit:
            raise SystemExit("--issue-id, --resolution-branch, and --resolution-commit are required")
        if not args.before_after_json:
            raise SystemExit("--before-after-json is required")
        try:
            before_after_comparison = json.loads(args.before_after_json)
        except json.JSONDecodeError as exc:
            raise SystemExit("--before-after-json must be valid JSON") from exc
        result = resolve_profit_validation_issue(
            issue_id=args.issue_id,
            resolution_branch=args.resolution_branch,
            resolution_commit=args.resolution_commit,
            proof_commands=list(args.proof_command or []),
            before_after_comparison=before_after_comparison,
            state_dir=args.state_dir,
        )
    elif args.mode == "profit-validation-defer":
        if not args.issue_id or not args.deferred_reason or not args.next_action:
            raise SystemExit("--issue-id, --deferred-reason, and --next-action are required")
        result = defer_profit_validation_issue(
            issue_id=args.issue_id,
            deferred_reason=args.deferred_reason,
            next_action=args.next_action,
            state_dir=args.state_dir,
        )
    else:
        result = run_profit_loop_canary(state_dir=args.state_dir, dry_run=args.dry_run)

    print(json.dumps(result, indent=2))
    if args.mode == "canary":
        return int(result.get("exit_code") or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
