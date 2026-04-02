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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, ROOT_DIR / "python-backend"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # pragma: no cover - optional local convenience
    _load_dotenv = None


def _load_local_env(root_dir: Path = ROOT_DIR) -> list[str]:
    loaded: list[str] = []
    for name in (".env", ".env.local"):
        path = Path(root_dir) / name
        if not path.exists():
            continue
        if _load_dotenv is not None:
            _load_dotenv(path, override=False)
        else:
            for raw_line in path.read_text(encoding="utf8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                os.environ[key] = value
        loaded.append(str(path))
    return loaded


_ENV_FILES_LOADED = _load_local_env()

from forward_options_ledger import summarize_forward_holdout
from historical_options_store import DAILY_SNAPSHOT_KIND, HistoricalOptionsStore
from profit_loop_shared_state import (
    append_run_ledger,
    begin_active_run,
    claim_issue,
    complete_active_run,
    defer_issue,
    ensure_profit_loop_state,
    heartbeat_active_run,
    load_profit_loop_state,
    list_run_ledger_events,
    proof_bundle_dir as shared_proof_bundle_dir,
    prioritized_open_issues,
    resolve_issue,
    save_profit_loop_state,
    set_latest_snapshot,
    shared_state_dir,
    upsert_open_issue,
    utc_now_iso,
    validation_prerequisite_blockers,
)
from wfo_optimizer import IMPORTED_DAILY_TRUTH_SOURCE, OPTIONS_VALIDATION_DAILY_LATEST_FILE, run_historical_backtest


DAILY_TRUTH_AUTO_REFRESH_ENV = "OPTIONS_DAILY_TRUTH_AUTO_REFRESH"
DAILY_TRUTH_IMPORT_MANIFEST_ENV = "OPTIONS_DAILY_TRUTH_IMPORT_MANIFEST"
LEGACY_DAILY_TRUTH_IMPORT_MANIFEST_ENV = "HISTORICAL_OPTIONS_IMPORT_MANIFEST"
DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST = ROOT_DIR / "data" / "options-validation" / "daily_truth_import_manifest.json"
DEFAULT_DAILY_TRUTH_REFRESH_LOOKBACK_YEARS = 2
DEFAULT_DAILY_TRUTH_REFRESH_N_PICKS = 1
DEFAULT_DAILY_TRUTH_REFRESH_IV_ADJ = 1.2
DEFAULT_DAILY_TRUTH_REFRESH_PRICING_LANE = "pessimistic"
DEFAULT_DAILY_TRUTH_REFRESH_PLAYBOOK = "broad"

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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _command_text(command: list[str]) -> str:
    rendered: list[str] = []
    for item in command:
        rendered.append("python" if str(item) == sys.executable else str(item))
    return " ".join(rendered)


def _run_command(command: list[str], *, cwd: Path = ROOT_DIR) -> dict[str, Any]:
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
    }


def _run_json_command(command: list[str], *, cwd: Path = ROOT_DIR) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _run_command(command, cwd=cwd)
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
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


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
        issue_id="daily-truth-refresh-failed",
        source_automation=source_automation,
        severity="high",
        blocker_class="truth_data_refresh",
        summary="Imported-daily truth refresh failed, so the profit loop cannot trust the current truth horizon.",
        evidence=evidence,
        suggested_fix_targets=[
            "profit_loop_automation.py",
            "scripts/import_historical_options_snapshots.py",
            _repo_relative_text(refresh.get("manifest_path") or DEFAULT_DAILY_TRUTH_IMPORT_MANIFEST),
        ],
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
    manifest_entries = _load_manifest_entries(manifest_path)
    import_entries, pre_import_summary = _daily_truth_entries_needing_import(
        manifest_entries,
        repo_root=repo_root,
        db_path=historical_db_path,
    )
    base_result["pre_import_store_summary"] = pre_import_summary

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
                import_payload, import_record = _run_json_command(import_command, cwd=repo_root)
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
        f"run_historical_backtest --truth-lane {IMPORTED_DAILY_TRUTH_SOURCE}"
        f" --pricing-lane {refresh_config['pricing_lane']}"
        f" --lookback-years {refresh_config['lookback_years']}"
        f" --n-picks {refresh_config['n_picks']}"
        f" --iv-adj {refresh_config['iv_adj']}"
        f" --playbook {refresh_config['playbook']}"
    )
    try:
        artifact_result = run_historical_backtest(
            lookback_years=int(refresh_config["lookback_years"]),
            n_picks=int(refresh_config["n_picks"]),
            iv_adj=float(refresh_config["iv_adj"]),
            pricing_lane=str(refresh_config["pricing_lane"]),
            truth_lane=IMPORTED_DAILY_TRUTH_SOURCE,
            playbook=str(refresh_config["playbook"]),
        )
        if artifact_result.get("error"):
            raise ProfitLoopAutomationError(str(artifact_result.get("error")))
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
    }


def _require_daily_truth_refresh(
    *,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
    refresh_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(refresh_result or _refresh_daily_truth(repo_root=repo_root, dry_run=dry_run))
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

    if truth_quality_regressed or safety_regressed or drawdown_regressed:
        return "regressed"
    if after_pf < baseline_pf or after_avg < baseline_avg:
        return "regressed"
    if after_pf > baseline_pf and after_avg > baseline_avg:
        if forward_status in {"non_worse", "improved"}:
            return "improved"
        return "inconclusive"
    return "inconclusive"


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
                "total_trades": output.get("total_trades"),
                "profit_factor": output.get("profit_factor"),
                "avg_pnl_pct": output.get("avg_pnl_pct"),
                "directional_accuracy_pct": output.get("directional_accuracy_pct"),
                "max_drawdown_pct": output.get("max_drawdown_pct"),
                "selection_source_counts": dict(output.get("selection_source_counts") or {}),
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
    if proof_plan["needs_replay_matrix"]:
        replay_artifact_path = proof_dir / "replay_matrix.json"
        replay_artifact = _read_json_artifact(replay_artifact_path)
        replay_fingerprint = _validation_fingerprint(
            commit_sha=context["commit_sha"],
            env_hash=context["env_hash"],
            truth_lane=proof_plan["truth_lane"],
            playbook=proof_plan["playbook"],
            blocker_class=proof_plan["blocker_class"],
            pricing_spec="matrix",
            modules=proof_plan["modules"],
        )
        if replay_artifact and replay_artifact.get("proof_fingerprint") == replay_fingerprint:
            replay_cases = list(replay_artifact.get("replay_cases") or [])
            proof_reuse.append("proof_bundle.replay_matrix")
        else:
            replay_cases = _baseline_replay_matrix(
                playbook=str(proof_plan["playbook"]),
                truth_lane=str(proof_plan["truth_lane"]),
            )
            _write_json_artifact(
                replay_artifact_path,
                {
                    "run_id": run_id,
                    "proof_fingerprint": replay_fingerprint,
                    "replay_cases": replay_cases,
                },
            )

    holdout_evidence = None
    if proof_plan["needs_holdout"]:
        holdout_evidence = {
            "policy_gated_session_id": ((holdout_snapshot.get("results") or {}).get("policy_gated_session_id")),
            "raw_session_id": ((holdout_snapshot.get("results") or {}).get("raw_session_id")),
            "policy_gated_scan_picks": ((holdout_snapshot.get("results") or {}).get("policy_gated_scan_picks")),
            "raw_scan_picks": ((holdout_snapshot.get("results") or {}).get("raw_scan_picks")),
            "forward_summary": ((holdout_snapshot.get("results") or {}).get("forward_summary")),
            "daily_truth_refresh": ((holdout_snapshot.get("results") or {}).get("daily_truth_refresh")),
        }
        proof_reuse.append("latest_truth_holdout")

    baseline = {
        "commands": commands,
        "validation_tests_passed": bool(module_result["passed"]),
        "validation_test_count": module_result["count"],
        "smoke_summary": smoke_summary,
        "replay_cases": replay_cases,
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


def run_operational_health(
    *,
    state_dir: str | Path | None = None,
    repo_root: Path = ROOT_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    state = load_profit_loop_state(state_dir)
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
        if smoke_scan_truth_lane and live_policy_truth_source and smoke_scan_truth_lane != live_policy_truth_source:
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
                        f"smoke_live_policy_promotion_status={smoke_payload.get('live_policy_promotion_status')}",
                    ],
                    suggested_fix_targets=["options_chatbot.py", "supervised_scan.py", "wfo_optimizer.py"],
                )
            )

    loop_execution_status = "blocked" if verdict == "blocked" else ("degraded" if verdict == "degraded-watch" else "healthy")
    evidence_status = "untrusted" if verdict == "blocked" else "trusted"
    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": verdict,
        "run_status": "completed",
        "loop_execution_status": loop_execution_status,
        "evidence_status": evidence_status,
        "profitability_verdict": "unproven",
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
            "smoke_live_policy_promotion_status": smoke_payload.get("live_policy_promotion_status"),
            "smoke_quote_coverage_pct": smoke_payload.get("live_policy_quote_coverage_pct"),
        },
    }
    set_latest_snapshot(state, key="latest_operational_health", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
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
        or _require_daily_truth_refresh(repo_root=repo_root, dry_run=dry_run)
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
        raw_required = int(policy_payload.get("scan_picks_count") or 0) <= 0 or bool(policy_payload.get("policy_fail_closed"))
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
                    "--record-frozen-cohorts",
                    "--cohort-id",
                    "baseline_broad_control",
                    "--cohort-id",
                    "broad_ev7_momentum070_exit_time33",
                    "--json",
                ],
                cwd=repo_root,
            )
            raw_pass_state = "run"
        else:
            raw_payload = {
                "session_id": None,
                "scan_picks_count": None,
                "promotion_status": policy_payload.get("promotion_status"),
                "policy_fail_closed": policy_payload.get("policy_fail_closed"),
            }
            raw_record = None
            raw_pass_state = "skipped"
        forward_summary = summarize_forward_holdout()

    issues: list[dict[str, Any]] = []
    verdict = "recorded"
    raw_scan_picks = int(raw_payload.get("scan_picks_count") or 0) if raw_required else None
    if (raw_required and int(raw_payload.get("scan_picks_count") or 0) <= 0 and int(policy_payload.get("scan_picks_count") or 0) <= 0) or (
        not raw_required and int(policy_payload.get("scan_picks_count") or 0) <= 0
    ):
        verdict = "recorded-no-candidates"
        issues.append(
            _issue_payload(
                issue_id="forward-holdout-no-raw-candidates",
                source_automation="daily-truth-holdout",
                severity="high",
                blocker_class="scan_starvation",
                summary="Forward holdout recorded successfully but both the policy-gated and raw scans produced zero candidates.",
                evidence=[
                    f"policy_gated_session_id={policy_payload.get('session_id')}",
                    f"raw_session_id={raw_payload.get('session_id')}",
                    f"policy_gated_scan_picks={policy_payload.get('scan_picks_count')}",
                    f"raw_scan_picks={raw_payload.get('scan_picks_count')}",
                    f"raw_required={raw_required}",
                    f"raw_pass_state={raw_pass_state}",
                    f"promotion_status={raw_payload.get('promotion_status') or policy_payload.get('promotion_status')}",
                    f"policy_fail_closed={raw_payload.get('policy_fail_closed')}",
                ],
                suggested_fix_targets=["supervised_scan.py", "options_chatbot.py", "docs/autoresearch/truth-first-champions.json"],
            )
        )

    loop_execution_status = "degraded" if verdict == "recorded-no-candidates" else "healthy"
    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": verdict,
        "run_status": "completed",
        "loop_execution_status": loop_execution_status,
        "evidence_status": "trusted",
        "profitability_verdict": "unproven",
        "evidence_complete": True,
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
            "promotion_status": raw_payload.get("promotion_status") or policy_payload.get("promotion_status"),
            "policy_fail_closed": raw_payload.get("policy_fail_closed"),
            "forward_summary": forward_summary,
        },
    }
    set_latest_snapshot(state, key="latest_truth_holdout", payload=snapshot, now_iso=now_iso)
    for issue in issues:
        upsert_open_issue(state, issue, now_iso=now_iso)
    complete_active_run(
        state,
        run_id=run["run_id"],
        status="completed",
        phase="completed",
        result_verdict=verdict,
        loop_execution_status=loop_execution_status,
        evidence_status="trusted",
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
            "evidence_status": "trusted",
            "profitability_verdict": "unproven",
            "state_hash": ((state.get("active_run") or {}).get("state_hash")),
            "issue_ids": [issue["issue_id"] for issue in issues],
        },
        state_dir=state_dir,
    )
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
            "loop_execution_status": "healthy",
            "evidence_status": "trusted",
            "profitability_verdict": "unproven",
            "evidence_complete": True,
            "proof_reuse": [],
            "proof_context": context,
            "targeted_issue_id": None,
            "prerequisite_blockers": [],
            "baseline": None,
        }
        set_latest_snapshot(state, key="latest_profit_validation", payload=snapshot, now_iso=now_iso)
        save_profit_loop_state(state, state_dir=state_dir)
        append_run_ledger(
            {
                "run_id": run_id,
                "automation_id": "daily-profit-validation",
                "ran_at": now_iso,
                "verdict": "queue-empty",
                "loop_execution_status": "healthy",
                "evidence_status": "trusted",
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
        or _require_daily_truth_refresh(repo_root=repo_root, dry_run=dry_run)
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
        evidence_complete = evidence_complete and all(not case.get("error") for case in list(baseline.get("replay_cases") or []))
    snapshot = {
        "run_id": run["run_id"],
        "ran_at": now_iso,
        "verdict": "claimed-issue" if not auto_defer else "deferred",
        "run_status": "completed",
        "loop_execution_status": "healthy",
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
    }

    result_action = "claimed_issue"
    if auto_defer:
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
        loop_execution_status="healthy",
        evidence_status=snapshot["evidence_status"],
        profitability_verdict="unproven",
        now_iso=now_iso,
    )
    _write_json_artifact(
        proof_dir / "validation_baseline.json",
        {
            "run_id": run["run_id"],
            "targeted_issue_id": targeted_issue["issue_id"],
            "snapshot": snapshot,
        },
    )
    save_profit_loop_state(state, state_dir=state_dir)
    append_run_ledger(
        {
            "run_id": run["run_id"],
            "automation_id": "daily-profit-validation",
            "ran_at": now_iso,
            "verdict": snapshot["verdict"],
            "loop_execution_status": "healthy",
            "evidence_status": snapshot["evidence_status"],
            "profitability_verdict": "unproven",
            "state_hash": ((state.get("active_run") or {}).get("state_hash")),
            "issue_ids": [targeted_issue["issue_id"]],
        },
        state_dir=state_dir,
    )
    return {
        "automation_id": "daily-profit-validation",
        "action": result_action,
        "state_dir": str(shared_state_dir(state_dir)),
        "snapshot": snapshot,
        "targeted_issue": targeted_issue,
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
    profitability_verdict = _evaluate_profitability_verdict(before_after_comparison)
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
        "loop_execution_status": "healthy",
        "evidence_status": "trusted",
        "profitability_verdict": profitability_verdict,
        "evidence_complete": True,
        "proof_reuse": [],
        "proof_bundle_dir": str(proof_dir),
        "targeted_issue_id": issue_id,
        "resolution_branch": resolution_branch,
        "resolution_commit": resolution_commit,
        "proof_commands": list(proof_commands or []),
        "before_after_comparison": copy.deepcopy(before_after_comparison),
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
            "loop_execution_status": "healthy",
            "evidence_status": "trusted",
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
    event_ids = [str(item.get("automation_id") or "") for item in new_events]
    latest_run_ids = [
        str((state.get("latest_operational_health") or {}).get("run_id") or ""),
        str((state.get("latest_truth_holdout") or {}).get("run_id") or ""),
        str((state.get("latest_profit_validation") or {}).get("run_id") or ""),
    ]
    ledger_run_ids = [str(item.get("run_id") or "") for item in new_events]
    consistency = {
        "new_event_count": len(new_events),
        "expected_automation_ids": expected_ids,
        "observed_automation_ids": event_ids,
        "latest_snapshot_run_ids": latest_run_ids,
        "ledger_run_ids": ledger_run_ids,
    }
    exit_code = 0
    if len(new_events) != 3 or event_ids != expected_ids or latest_run_ids != ledger_run_ids:
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Shared-state automation drivers for the options profit loop.")
    parser.add_argument(
        "mode",
        choices=[
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
    args = parser.parse_args(argv)

    if args.mode == "operational-health":
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
