from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_SHARED_STATE_DIR = DEFAULT_CODEX_HOME / "automations" / "shared" / "options-chatbot"
DEFAULT_STATE_FILE_NAME = "profit-loop-state.json"
DEFAULT_RUN_LEDGER_FILE_NAME = "profit-loop-runs.jsonl"
LEGACY_REPO_HANDOFF_PATH = ROOT_DIR / "docs" / "autoresearch" / "automation-handoff.json"

SCHEMA_VERSION = 2
DEFAULT_OPERATIONAL_MAX_AGE_HOURS = 2
DEFAULT_WEEKEND_HOLDOUT_MAX_AGE_DAYS = 3
DEFAULT_RUN_LEASE_MINUTES = 90
DEFAULT_CLAIM_LEASE_MINUTES = 180

RUN_STATUSES = {"running", "completed", "failed", "expired"}
LOOP_EXECUTION_STATUSES = {"healthy", "degraded", "blocked"}
EVIDENCE_STATUSES = {"trusted", "inconclusive", "untrusted"}
PROFITABILITY_VERDICTS = {"unproven", "inconclusive", "improved", "regressed"}
OPEN_STATUSES = {"open", "claimed", "deferred"}

BLOCKER_PRIORITY = {
    "truth_lane_mismatch": 0,
    "truth_provenance": 0,
    "calibration": 0,
    "scan_starvation": 1,
    "fail_open": 1,
    "market_data": 2,
    "storage": 2,
    "replay_matrix_suspicious": 3,
    "replay_report_integrity": 3,
    "test_gap": 4,
    "documentation_only": 5,
}
SEVERITY_PRIORITY = {"high": 0, "medium": 1, "low": 2}

REQUIRED_ISSUE_KEYS = {
    "issue_id",
    "source_automation",
    "first_seen_at",
    "last_seen_at",
    "severity",
    "blocker_class",
    "summary",
    "evidence",
    "suggested_fix_targets",
    "status",
    "deferred_reason",
    "next_action",
    "last_validation_attempt_at",
    "resolved_at",
    "resolution_branch",
    "resolution_commit",
    "resolution_kind",
    "claim_run_id",
    "claimed_at",
    "claim_expires_at",
    "proof_bundle_dir",
    "proof_commands",
    "before_after_comparison",
}

REQUIRED_ACTIVE_RUN_KEYS = {
    "run_id",
    "automation_id",
    "phase",
    "started_at",
    "heartbeat_at",
    "lease_expires_at",
    "status",
    "commit_sha",
    "env_hash",
    "proof_bundle_dir",
    "state_hash",
}

SEEDED_ISSUES = [
    {
        "issue_id": "truth-lane-live-policy-mismatch",
        "source_automation": "seed",
        "severity": "high",
        "blocker_class": "truth_lane_mismatch",
        "summary": (
            "Seeded blocker: live scan truth lane and live policy truth source need alignment "
            "before unattended profit validation can trust scan-policy outcomes."
        ),
        "evidence": [
            "Seeded from the April 2, 2026 manual automation validation run.",
            "Expected authoritative lane: historical_imported_daily.",
            "Observed mismatch previously routed policy from synthetic_research.",
        ],
        "suggested_fix_targets": ["options_chatbot.py", "supervised_scan.py", "wfo_optimizer.py"],
        "status": "open",
    },
    {
        "issue_id": "forward-holdout-no-raw-candidates",
        "source_automation": "seed",
        "severity": "high",
        "blocker_class": "scan_starvation",
        "summary": (
            "Seeded blocker: forward holdout recording was mechanically successful but produced "
            "zero raw candidates, so the loop has no forward trade evidence to learn from."
        ),
        "evidence": [
            "Seeded from the April 2, 2026 manual automation validation run.",
            "Both policy-gated and raw holdout passes recorded zero picks.",
        ],
        "suggested_fix_targets": ["supervised_scan.py", "options_chatbot.py", "docs/autoresearch/truth-first-champions.json"],
        "status": "open",
    },
    {
        "issue_id": "replay-matrix-collapsed-results",
        "source_automation": "seed",
        "severity": "medium",
        "blocker_class": "replay_matrix_suspicious",
        "summary": (
            "Seeded blocker: the required 1y/2y and mid/pessimistic replay matrix collapsed to "
            "identical results, so daily profit validation must treat replay evidence as suspect."
        ),
        "evidence": [
            "Seeded from the April 2, 2026 manual automation validation run.",
            "All four replay cells returned the same trade count and summary metrics.",
        ],
        "suggested_fix_targets": ["wfo_optimizer.py", "scripts/options_experiment_matrix.py"],
        "status": "open",
    },
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _codex_home() -> Path:
    override = str(os.getenv("CODEX_HOME") or "").strip()
    return Path(override).resolve() if override else DEFAULT_CODEX_HOME


def shared_state_dir(state_dir: str | Path | None = None) -> Path:
    if state_dir is not None:
        return Path(state_dir).resolve()
    override = str(os.getenv("OPTIONS_PROFIT_LOOP_STATE_DIR") or "").strip()
    if override:
        return Path(override).resolve()
    return (_codex_home() / "automations" / "shared" / "options-chatbot").resolve()


def state_path(state_dir: str | Path | None = None) -> Path:
    return shared_state_dir(state_dir) / DEFAULT_STATE_FILE_NAME


def runs_ledger_path(state_dir: str | Path | None = None) -> Path:
    return shared_state_dir(state_dir) / DEFAULT_RUN_LEDGER_FILE_NAME


def proof_runs_dir(state_dir: str | Path | None = None) -> Path:
    return shared_state_dir(state_dir) / "runs"


def proof_bundle_dir(run_id: str, *, state_dir: str | Path | None = None) -> Path:
    return proof_runs_dir(state_dir) / str(run_id).strip()


def empty_profit_loop_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "active_run": None,
        "latest_operational_health": None,
        "latest_truth_holdout": None,
        "latest_profit_validation": None,
        "open_issues": [],
        "resolved_issues": [],
    }


def example_profit_loop_state() -> dict[str, Any]:
    payload = empty_profit_loop_state()
    payload["example_only"] = True
    payload["notes"] = [
        "This repo file is documentation only.",
        "Live automation state now lives under %CODEX_HOME%/automations/shared/options-chatbot.",
    ]
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def _append_jsonl(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")
    return path


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Shared profit-loop state is not valid JSON: {path}") from exc


def _infer_loop_execution_status(snapshot: dict[str, Any] | None) -> str:
    verdict = str((snapshot or {}).get("verdict") or "").strip().lower()
    if verdict.startswith("blocked"):
        return "blocked"
    if verdict in {"degraded-watch", "recorded-no-candidates", "deferred"}:
        return "degraded"
    return "healthy"


def _infer_evidence_status(snapshot: dict[str, Any] | None) -> str:
    payload = dict(snapshot or {})
    if payload.get("loop_execution_status") == "blocked" or _infer_loop_execution_status(payload) == "blocked":
        return "untrusted"
    if payload.get("evidence_complete"):
        return "trusted"
    return "inconclusive"


def _infer_profitability_verdict(snapshot: dict[str, Any] | None) -> str:
    payload = dict(snapshot or {})
    verdict = str(payload.get("verdict") or "").strip().lower()
    if verdict == "resolved":
        return str(payload.get("profitability_verdict") or "inconclusive").strip().lower() or "inconclusive"
    return "unproven"


def _normalize_snapshot_evidence_status(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized == "degraded":
        return "inconclusive"
    if normalized in EVIDENCE_STATUSES:
        return normalized
    return None


def _snapshot_default_fields(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    payload = copy.deepcopy(dict(snapshot))
    loop_execution_status = str(payload.get("loop_execution_status") or "").strip().lower()
    if loop_execution_status not in LOOP_EXECUTION_STATUSES:
        loop_execution_status = _infer_loop_execution_status(payload)
    payload["loop_execution_status"] = loop_execution_status
    payload["evidence_status"] = (
        _normalize_snapshot_evidence_status(payload.get("evidence_status"))
        or _infer_evidence_status(payload)
    )
    profitability_verdict = str(payload.get("profitability_verdict") or "").strip().lower()
    if profitability_verdict not in PROFITABILITY_VERDICTS:
        profitability_verdict = _infer_profitability_verdict(payload)
    payload["profitability_verdict"] = profitability_verdict
    payload.setdefault("proof_reuse", [])
    payload.setdefault("evidence_complete", False)
    return payload


def _migrate_issue(issue: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(issue or {})
    migrated.setdefault("claim_run_id", None)
    migrated.setdefault("claimed_at", None)
    migrated.setdefault("claim_expires_at", None)
    migrated.setdefault("proof_bundle_dir", None)
    migrated.setdefault("proof_commands", [])
    migrated.setdefault("before_after_comparison", None)
    migrated.setdefault("resolution_kind", None)
    return migrated


def _normalize_issue(
    issue: dict[str, Any],
    *,
    now_iso: str | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    base = dict(existing or {})
    payload = dict(issue or {})
    issue_id = str(payload.get("issue_id") or base.get("issue_id") or "").strip()
    if not issue_id:
        raise ValueError("issue_id is required")
    source_automation = str(payload.get("source_automation") or base.get("source_automation") or "").strip()
    if not source_automation:
        raise ValueError(f"source_automation is required for issue {issue_id}")
    severity = str(payload.get("severity") or base.get("severity") or "medium").strip().lower()
    if severity not in SEVERITY_PRIORITY:
        raise ValueError(f"Unsupported severity {severity!r} for issue {issue_id}")
    blocker_class = str(payload.get("blocker_class") or base.get("blocker_class") or "").strip()
    if not blocker_class:
        raise ValueError(f"blocker_class is required for issue {issue_id}")
    summary = str(payload.get("summary") or base.get("summary") or "").strip()
    if not summary:
        raise ValueError(f"summary is required for issue {issue_id}")

    status = str(payload.get("status") or base.get("status") or "open").strip().lower()
    if status not in OPEN_STATUSES | {"resolved"}:
        raise ValueError(f"Unsupported issue status {status!r} for issue {issue_id}")

    first_seen = str(payload.get("first_seen_at") or base.get("first_seen_at") or current_time)
    last_seen = str(payload.get("last_seen_at") or current_time)
    proof_commands = list(payload.get("proof_commands") or base.get("proof_commands") or [])
    before_after = payload.get("before_after_comparison", base.get("before_after_comparison"))

    normalized = {
        "issue_id": issue_id,
        "source_automation": source_automation,
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "severity": severity,
        "blocker_class": blocker_class,
        "summary": summary,
        "evidence": [str(item) for item in list(payload.get("evidence") or base.get("evidence") or [])],
        "suggested_fix_targets": [str(item) for item in list(payload.get("suggested_fix_targets") or base.get("suggested_fix_targets") or [])],
        "status": status,
        "deferred_reason": payload.get("deferred_reason", base.get("deferred_reason")),
        "next_action": payload.get("next_action", base.get("next_action")),
        "last_validation_attempt_at": payload.get("last_validation_attempt_at", base.get("last_validation_attempt_at")),
        "resolved_at": payload.get("resolved_at", base.get("resolved_at")),
        "resolution_branch": payload.get("resolution_branch", base.get("resolution_branch")),
        "resolution_commit": payload.get("resolution_commit", base.get("resolution_commit")),
        "resolution_kind": payload.get("resolution_kind", base.get("resolution_kind")),
        "claim_run_id": payload.get("claim_run_id", base.get("claim_run_id")),
        "claimed_at": payload.get("claimed_at", base.get("claimed_at")),
        "claim_expires_at": payload.get("claim_expires_at", base.get("claim_expires_at")),
        "proof_bundle_dir": payload.get("proof_bundle_dir", base.get("proof_bundle_dir")),
        "proof_commands": [str(item) for item in proof_commands],
        "before_after_comparison": copy.deepcopy(before_after) if before_after is not None else None,
    }
    missing = REQUIRED_ISSUE_KEYS.difference(normalized.keys())
    if missing:
        raise ValueError(f"Issue {issue_id} missing keys: {sorted(missing)}")
    return normalized


def _normalize_active_run(active_run: dict[str, Any] | None) -> dict[str, Any] | None:
    if active_run is None:
        return None
    payload = dict(active_run or {})
    normalized = {
        "run_id": str(payload.get("run_id") or "").strip(),
        "automation_id": str(payload.get("automation_id") or "").strip(),
        "phase": str(payload.get("phase") or "").strip(),
        "started_at": str(payload.get("started_at") or "").strip(),
        "heartbeat_at": str(payload.get("heartbeat_at") or "").strip(),
        "lease_expires_at": str(payload.get("lease_expires_at") or "").strip(),
        "status": str(payload.get("status") or "").strip().lower(),
        "commit_sha": str(payload.get("commit_sha") or "").strip(),
        "env_hash": str(payload.get("env_hash") or "").strip(),
        "proof_bundle_dir": str(payload.get("proof_bundle_dir") or "").strip(),
        "state_hash": str(payload.get("state_hash") or "").strip() or None,
    }
    missing = [key for key in REQUIRED_ACTIVE_RUN_KEYS if not normalized.get(key) and key != "state_hash"]
    if missing:
        raise ValueError(f"active_run missing keys: {sorted(missing)}")
    if normalized["status"] not in RUN_STATUSES:
        raise ValueError(f"Unsupported active_run status: {normalized['status']!r}")
    normalized.update(
        {
            "result_verdict": payload.get("result_verdict"),
            "loop_execution_status": payload.get("loop_execution_status"),
            "evidence_status": payload.get("evidence_status"),
            "profitability_verdict": payload.get("profitability_verdict"),
        }
    )
    return normalized


def migrate_profit_loop_state(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Profit loop state payload must be a dict")
    version = int(payload.get("schema_version") or 1)
    if version == SCHEMA_VERSION:
        migrated = copy.deepcopy(payload)
        defaults = empty_profit_loop_state()
        migrated.setdefault("updated_at", defaults["updated_at"])
        migrated.setdefault("active_run", defaults["active_run"])
        migrated.setdefault("latest_operational_health", defaults["latest_operational_health"])
        migrated.setdefault("latest_truth_holdout", defaults["latest_truth_holdout"])
        migrated.setdefault("latest_profit_validation", defaults["latest_profit_validation"])
        migrated.setdefault("open_issues", copy.deepcopy(defaults["open_issues"]))
        migrated.setdefault("resolved_issues", copy.deepcopy(defaults["resolved_issues"]))
    elif version == 1:
        migrated = copy.deepcopy(payload)
        migrated["schema_version"] = SCHEMA_VERSION
        migrated.setdefault("active_run", None)
        migrated["open_issues"] = [_migrate_issue(dict(issue)) for issue in list(migrated.get("open_issues") or [])]
        migrated["resolved_issues"] = [_migrate_issue(dict(issue)) for issue in list(migrated.get("resolved_issues") or [])]
        migrated["latest_operational_health"] = _snapshot_default_fields(migrated.get("latest_operational_health"))
        migrated["latest_truth_holdout"] = _snapshot_default_fields(migrated.get("latest_truth_holdout"))
        migrated["latest_profit_validation"] = _snapshot_default_fields(migrated.get("latest_profit_validation"))
    else:
        raise ValueError(f"Unsupported schema_version: {payload.get('schema_version')!r}")
    return migrated


def validate_profit_loop_state(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_profit_loop_state(payload)
    required_top_level = {
        "schema_version",
        "updated_at",
        "active_run",
        "latest_operational_health",
        "latest_truth_holdout",
        "latest_profit_validation",
        "open_issues",
        "resolved_issues",
    }
    missing = required_top_level.difference(migrated.keys())
    if missing:
        raise ValueError(f"Profit loop state missing keys: {sorted(missing)}")
    if int(migrated.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {migrated.get('schema_version')!r}")
    if not isinstance(migrated.get("open_issues"), list):
        raise ValueError("open_issues must be a list")
    if not isinstance(migrated.get("resolved_issues"), list):
        raise ValueError("resolved_issues must be a list")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": str(migrated.get("updated_at") or utc_now_iso()),
        "active_run": _normalize_active_run(migrated.get("active_run")),
        "latest_operational_health": _snapshot_default_fields(migrated.get("latest_operational_health")),
        "latest_truth_holdout": _snapshot_default_fields(migrated.get("latest_truth_holdout")),
        "latest_profit_validation": _snapshot_default_fields(migrated.get("latest_profit_validation")),
        "open_issues": [],
        "resolved_issues": [],
    }
    if "example_only" in migrated:
        normalized["example_only"] = bool(migrated.get("example_only"))
    if "notes" in migrated:
        normalized["notes"] = list(migrated.get("notes") or [])

    for issue in list(migrated.get("open_issues") or []):
        normalized["open_issues"].append(_normalize_issue(_migrate_issue(dict(issue)), existing=None))
    for issue in list(migrated.get("resolved_issues") or []):
        normalized["resolved_issues"].append(
            _normalize_issue(_migrate_issue(dict(issue)) | {"status": "resolved"}, existing=None)
        )
    return normalized


def _legacy_seed_payload() -> dict[str, Any]:
    state = empty_profit_loop_state()
    now_iso = utc_now_iso()
    state["open_issues"] = [_normalize_issue(_migrate_issue(issue), now_iso=now_iso) for issue in SEEDED_ISSUES]
    return state


def _import_legacy_repo_handoff() -> dict[str, Any] | None:
    payload = _load_json(LEGACY_REPO_HANDOFF_PATH)
    if not payload or payload.get("example_only"):
        return None
    imported = empty_profit_loop_state()
    imported["updated_at"] = str(payload.get("updated_at") or utc_now_iso())
    imported["latest_operational_health"] = _snapshot_default_fields(payload.get("latest_operational_health"))
    imported["latest_truth_holdout"] = _snapshot_default_fields(payload.get("latest_truth_holdout"))
    imported["latest_profit_validation"] = _snapshot_default_fields(payload.get("latest_profit_validation"))
    now_iso = utc_now_iso()
    for issue in list(payload.get("open_issues") or []):
        imported["open_issues"].append(_normalize_issue(_migrate_issue(dict(issue)), now_iso=now_iso))
    for issue in list(payload.get("resolved_issues") or []):
        imported["resolved_issues"].append(
            _normalize_issue(_migrate_issue(dict(issue)) | {"status": "resolved"}, now_iso=now_iso)
        )
    return imported


def initialize_profit_loop_state(state_dir: str | Path | None = None) -> dict[str, Any]:
    initial = _import_legacy_repo_handoff() or _legacy_seed_payload()
    initial["updated_at"] = utc_now_iso()
    save_profit_loop_state(initial, state_dir=state_dir)
    return initial


def ensure_profit_loop_state(state_dir: str | Path | None = None) -> Path:
    directory = shared_state_dir(state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    ledger = runs_ledger_path(directory)
    if not ledger.exists():
        ledger.touch()
    proof_runs_dir(directory).mkdir(parents=True, exist_ok=True)
    path = state_path(directory)
    if not path.exists():
        initialize_profit_loop_state(directory)
    return directory


def _state_hash_payload(payload: dict[str, Any]) -> str:
    hashable = copy.deepcopy(payload)
    active = dict(hashable.get("active_run") or {})
    if active:
        active["state_hash"] = None
        hashable["active_run"] = active
    encoded = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf8")).hexdigest()


def _refresh_state_hash(payload: dict[str, Any]) -> dict[str, Any]:
    active = dict(payload.get("active_run") or {})
    if active:
        active["state_hash"] = _state_hash_payload(payload)
        payload["active_run"] = active
    return payload


def _is_expired(iso_value: str | None, *, now: datetime) -> bool:
    lease_time = _parse_iso_datetime(iso_value)
    return lease_time is not None and lease_time <= now


def expire_stale_leases(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or _utc_now()
    current_iso = current_time.isoformat().replace("+00:00", "Z")
    changed = False
    expired_run: dict[str, Any] | None = None
    reopened_issue_ids: list[str] = []

    active = dict(state.get("active_run") or {})
    if active and str(active.get("status") or "").strip().lower() == "running" and _is_expired(
        active.get("lease_expires_at"), now=current_time
    ):
        active["status"] = "expired"
        active["heartbeat_at"] = current_iso
        active["lease_expires_at"] = current_iso
        state["active_run"] = None
        changed = True
        expired_run = dict(active)
    elif active and str(active.get("status") or "").strip().lower() in RUN_STATUSES.difference({"running"}):
        state["active_run"] = None
        changed = True

    refreshed_open: list[dict[str, Any]] = []
    for issue in list(state.get("open_issues") or []):
        normalized = dict(issue)
        if str(normalized.get("status") or "").strip().lower() == "claimed" and _is_expired(
            normalized.get("claim_expires_at"), now=current_time
        ):
            normalized["status"] = "open"
            normalized["claim_run_id"] = None
            normalized["claimed_at"] = None
            normalized["claim_expires_at"] = None
            normalized["last_seen_at"] = current_iso
            changed = True
            reopened_issue_ids.append(str(normalized.get("issue_id") or "").strip())
        refreshed_open.append(normalized)
    if changed:
        state["open_issues"] = refreshed_open
        state["updated_at"] = current_iso
    return {
        "changed": changed,
        "expired_run": expired_run,
        "reopened_issue_ids": reopened_issue_ids,
        "expired_at": current_iso,
    }


def load_profit_loop_state(state_dir: str | Path | None = None) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    payload = _load_json(state_path(state_dir))
    if payload is None:
        return initialize_profit_loop_state(state_dir)
    normalized = validate_profit_loop_state(payload)
    lease_recovery = expire_stale_leases(normalized)
    if lease_recovery["changed"] or int(payload.get("schema_version") or 1) != SCHEMA_VERSION:
        save_profit_loop_state(normalized, state_dir=state_dir)
    expired_run = dict(lease_recovery.get("expired_run") or {})
    if expired_run:
        append_run_ledger(
            {
                "run_id": expired_run.get("run_id"),
                "automation_id": expired_run.get("automation_id"),
                "ran_at": lease_recovery.get("expired_at"),
                "verdict": "recovered-expired-lease",
                "loop_execution_status": "blocked",
                "evidence_status": "untrusted",
                "profitability_verdict": "unproven",
                "phase": expired_run.get("phase"),
                "reopened_issue_ids": list(lease_recovery.get("reopened_issue_ids") or []),
            },
            state_dir=state_dir,
        )
    return normalized


def save_profit_loop_state(payload: dict[str, Any], *, state_dir: str | Path | None = None) -> Path:
    normalized = validate_profit_loop_state(payload)
    normalized["updated_at"] = utc_now_iso()
    _refresh_state_hash(normalized)
    path = _atomic_write_json(state_path(state_dir), normalized)
    if isinstance(payload, dict):
        payload.clear()
        payload.update(copy.deepcopy(normalized))
    return path


def append_run_ledger(event: dict[str, Any], *, state_dir: str | Path | None = None) -> Path:
    payload = dict(event or {})
    payload.setdefault("recorded_at", utc_now_iso())
    return _append_jsonl(runs_ledger_path(state_dir), payload)


def list_run_ledger_events(state_dir: str | Path | None = None) -> list[dict[str, Any]]:
    ensure_profit_loop_state(state_dir)
    path = runs_ledger_path(state_dir)
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        events.append(json.loads(stripped))
    return events


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _find_issue_index(issues: list[dict[str, Any]], issue_id: str) -> Optional[int]:
    normalized = str(issue_id or "").strip()
    for index, issue in enumerate(issues):
        if str(issue.get("issue_id") or "").strip() == normalized:
            return index
    return None


def upsert_open_issue(
    state: dict[str, Any],
    issue: dict[str, Any],
    *,
    now_iso: str | None = None,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    open_issues = list(state.get("open_issues") or [])
    resolved_issues = list(state.get("resolved_issues") or [])
    issue_id = str(issue.get("issue_id") or "").strip()
    existing: dict[str, Any] | None = None

    open_index = _find_issue_index(open_issues, issue_id)
    if open_index is not None:
        existing = dict(open_issues[open_index])
    else:
        resolved_index = _find_issue_index(resolved_issues, issue_id)
        if resolved_index is not None:
            existing = dict(resolved_issues.pop(resolved_index))

    normalized = _normalize_issue(
        _migrate_issue(dict(issue)) | {"status": "open", "last_seen_at": current_time},
        now_iso=current_time,
        existing=existing,
    )
    normalized["evidence"] = _dedupe_strings(
        list((existing or {}).get("evidence") or []) + list(normalized.get("evidence") or [])
    )
    normalized["suggested_fix_targets"] = _dedupe_strings(
        list((existing or {}).get("suggested_fix_targets") or []) + list(normalized.get("suggested_fix_targets") or [])
    )
    normalized["deferred_reason"] = None
    normalized["next_action"] = issue.get("next_action") or (existing or {}).get("next_action")
    normalized["last_validation_attempt_at"] = (existing or {}).get("last_validation_attempt_at")
    normalized["resolved_at"] = None
    normalized["resolution_branch"] = None
    normalized["resolution_commit"] = None
    normalized["resolution_kind"] = None
    normalized["claim_run_id"] = None
    normalized["claimed_at"] = None
    normalized["claim_expires_at"] = None
    normalized["proof_bundle_dir"] = None
    normalized["proof_commands"] = []
    normalized["before_after_comparison"] = None

    if open_index is not None:
        open_issues[open_index] = normalized
    else:
        open_issues.append(normalized)
    state["open_issues"] = open_issues
    state["resolved_issues"] = resolved_issues
    state["updated_at"] = current_time
    return normalized


def reconcile_source_open_issues(
    state: dict[str, Any],
    *,
    source_automation: str,
    active_issue_ids: list[str] | set[str] | tuple[str, ...],
    now_iso: str | None = None,
    resolution_note: str | None = None,
) -> list[dict[str, Any]]:
    normalized_source = str(source_automation or "").strip()
    if not normalized_source:
        raise ValueError("source_automation is required to reconcile issues")
    current_time = str(now_iso or utc_now_iso())
    active_ids = {str(issue_id).strip() for issue_id in list(active_issue_ids or []) if str(issue_id).strip()}
    open_issues = list(state.get("open_issues") or [])
    resolved_issues = list(state.get("resolved_issues") or [])
    remaining_open: list[dict[str, Any]] = []
    cleared: list[dict[str, Any]] = []

    for item in open_issues:
        issue = dict(item)
        if str(issue.get("source_automation") or "").strip() != normalized_source:
            remaining_open.append(issue)
            continue
        issue_id = str(issue.get("issue_id") or "").strip()
        if issue_id in active_ids:
            remaining_open.append(issue)
            continue
        resolved_index = _find_issue_index(resolved_issues, issue_id)
        if resolved_index is not None:
            resolved_issues.pop(resolved_index)
        resolution_reason = str(resolution_note or "").strip() or f"{normalized_source} no longer observes this blocker."
        resolved = _normalize_issue(
            issue
            | {
                "status": "resolved",
                "last_seen_at": current_time,
                "resolved_at": current_time,
                "resolution_kind": "no_longer_observed",
                "deferred_reason": None,
                "claim_run_id": None,
                "claimed_at": None,
                "claim_expires_at": None,
                "before_after_comparison": {
                    "resolution_kind": "no_longer_observed",
                    "resolved_by_source": normalized_source,
                    "resolution_reason": resolution_reason,
                },
            },
            now_iso=current_time,
            existing=issue,
        )
        resolved_issues.append(resolved)
        cleared.append(resolved)

    if cleared:
        state["open_issues"] = remaining_open
        state["resolved_issues"] = resolved_issues
        state["updated_at"] = current_time
    return cleared


def claim_issue(
    state: dict[str, Any],
    issue_id: str,
    *,
    now_iso: str | None = None,
    next_action: str | None = None,
    claim_run_id: str | None = None,
    claim_ttl_minutes: int = DEFAULT_CLAIM_LEASE_MINUTES,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    current_dt = _parse_iso_datetime(current_time) or _utc_now()
    open_issues = list(state.get("open_issues") or [])
    index = _find_issue_index(open_issues, issue_id)
    if index is None:
        raise ValueError(f"Cannot claim unknown issue: {issue_id}")
    existing = dict(open_issues[index])
    existing_claim_run_id = str(existing.get("claim_run_id") or "").strip() or None
    if str(existing.get("status") or "").strip().lower() == "claimed" and existing_claim_run_id and existing_claim_run_id != str(claim_run_id or "").strip():
        if not _is_expired(existing.get("claim_expires_at"), now=current_dt):
            raise ValueError(f"Issue {issue_id} is already claimed by another active run")
    claim_expires_at = (current_dt + timedelta(minutes=int(claim_ttl_minutes))).isoformat().replace("+00:00", "Z")
    issue = _normalize_issue(
        existing
        | {
            "status": "claimed",
            "last_seen_at": current_time,
            "last_validation_attempt_at": current_time,
            "next_action": next_action or existing.get("next_action"),
            "claim_run_id": str(claim_run_id or existing.get("claim_run_id") or "").strip() or None,
            "claimed_at": current_time,
            "claim_expires_at": claim_expires_at,
        },
        now_iso=current_time,
        existing=existing,
    )
    open_issues[index] = issue
    state["open_issues"] = open_issues
    state["updated_at"] = current_time
    return issue


def defer_issue(
    state: dict[str, Any],
    issue_id: str,
    *,
    deferred_reason: str,
    next_action: str,
    now_iso: str | None = None,
) -> dict[str, Any]:
    if not str(next_action or "").strip():
        raise ValueError("next_action is required when deferring an issue")
    current_time = str(now_iso or utc_now_iso())
    open_issues = list(state.get("open_issues") or [])
    index = _find_issue_index(open_issues, issue_id)
    if index is None:
        raise ValueError(f"Cannot defer unknown issue: {issue_id}")
    issue = _normalize_issue(
        dict(open_issues[index])
        | {
            "status": "deferred",
            "last_seen_at": current_time,
            "last_validation_attempt_at": current_time,
            "deferred_reason": str(deferred_reason or "").strip() or "deferred",
            "next_action": str(next_action).strip(),
            "claim_run_id": None,
            "claimed_at": None,
            "claim_expires_at": None,
        },
        now_iso=current_time,
        existing=open_issues[index],
    )
    open_issues[index] = issue
    state["open_issues"] = open_issues
    state["updated_at"] = current_time
    return issue


def resolve_issue(
    state: dict[str, Any],
    issue_id: str,
    *,
    resolution_branch: str,
    resolution_commit: str,
    proof_bundle_dir: str | None = None,
    proof_commands: list[str] | None = None,
    before_after_comparison: dict[str, Any] | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    normalized_branch = str(resolution_branch or "").strip()
    normalized_commit = str(resolution_commit or "").strip()
    if not normalized_branch:
        raise ValueError("resolution_branch is required to resolve an issue")
    if not normalized_commit:
        raise ValueError("resolution_commit is required to resolve an issue")
    proof_bundle_raw = str(proof_bundle_dir or "").strip()
    if not proof_bundle_raw:
        raise ValueError("proof_bundle_dir is required to resolve an issue")
    proof_dir = Path(proof_bundle_raw)
    if not proof_dir.exists() or not proof_dir.is_dir():
        raise ValueError(f"proof_bundle_dir does not exist or is not a directory: {proof_dir}")
    proof_commands = [str(item).strip() for item in list(proof_commands or []) if str(item).strip()]
    if not proof_commands:
        raise ValueError("proof_commands are required to resolve an issue")
    if before_after_comparison is None:
        raise ValueError("before_after_comparison is required to resolve an issue")
    open_issues = list(state.get("open_issues") or [])
    resolved_issues = list(state.get("resolved_issues") or [])
    index = _find_issue_index(open_issues, issue_id)
    if index is None:
        raise ValueError(f"Cannot resolve unknown issue: {issue_id}")
    issue = _normalize_issue(
        dict(open_issues.pop(index))
        | {
            "status": "resolved",
            "last_seen_at": current_time,
            "last_validation_attempt_at": current_time,
                "resolved_at": current_time,
                "resolution_branch": normalized_branch,
            "resolution_commit": normalized_commit,
            "resolution_kind": "proof_resolved",
            "deferred_reason": None,
            "proof_bundle_dir": str(proof_dir),
            "proof_commands": proof_commands,
            "before_after_comparison": copy.deepcopy(before_after_comparison),
            "claim_run_id": None,
            "claimed_at": None,
            "claim_expires_at": None,
        },
        now_iso=current_time,
    )
    resolved_issues.append(issue)
    state["open_issues"] = open_issues
    state["resolved_issues"] = resolved_issues
    state["updated_at"] = current_time
    return issue


def set_latest_snapshot(
    state: dict[str, Any],
    *,
    key: str,
    payload: dict[str, Any],
    now_iso: str | None = None,
) -> dict[str, Any]:
    if key not in {"latest_operational_health", "latest_truth_holdout", "latest_profit_validation"}:
        raise ValueError(f"Unsupported latest snapshot key: {key}")
    state[key] = _snapshot_default_fields(copy.deepcopy(payload))
    state["updated_at"] = str(now_iso or utc_now_iso())
    return state


def begin_active_run(
    state: dict[str, Any],
    *,
    automation_id: str,
    phase: str,
    commit_sha: str,
    env_hash: str,
    proof_bundle_dir: str,
    now_iso: str | None = None,
    lease_minutes: int = DEFAULT_RUN_LEASE_MINUTES,
    run_id: str | None = None,
    allow_replace: bool = False,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    current_dt = _parse_iso_datetime(current_time) or _utc_now()
    active = _normalize_active_run(state.get("active_run")) if state.get("active_run") else None
    if active and active["status"] == "running" and not _is_expired(active.get("lease_expires_at"), now=current_dt):
        if not allow_replace:
            raise ValueError(f"Active run already in progress for {active['automation_id']}")
    run_payload = {
        "run_id": str(run_id or f"{automation_id}-{current_dt.strftime('%Y%m%dT%H%M%SZ')}"),
        "automation_id": str(automation_id).strip(),
        "phase": str(phase).strip(),
        "started_at": current_time,
        "heartbeat_at": current_time,
        "lease_expires_at": (current_dt + timedelta(minutes=int(lease_minutes))).isoformat().replace("+00:00", "Z"),
        "status": "running",
        "commit_sha": str(commit_sha or "").strip(),
        "env_hash": str(env_hash or "").strip(),
        "proof_bundle_dir": str(proof_bundle_dir or "").strip(),
        "state_hash": None,
    }
    state["active_run"] = _normalize_active_run(run_payload)
    state["updated_at"] = current_time
    return copy.deepcopy(state["active_run"])


def heartbeat_active_run(
    state: dict[str, Any],
    *,
    run_id: str,
    phase: str | None = None,
    now_iso: str | None = None,
    lease_minutes: int = DEFAULT_RUN_LEASE_MINUTES,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    current_dt = _parse_iso_datetime(current_time) or _utc_now()
    active = _normalize_active_run(state.get("active_run"))
    if active is None or active.get("run_id") != str(run_id).strip():
        raise ValueError(f"Cannot heartbeat unknown active run: {run_id}")
    active["heartbeat_at"] = current_time
    active["lease_expires_at"] = (current_dt + timedelta(minutes=int(lease_minutes))).isoformat().replace("+00:00", "Z")
    if phase:
        active["phase"] = str(phase).strip()
    state["active_run"] = active
    state["updated_at"] = current_time
    return copy.deepcopy(active)


def complete_active_run(
    state: dict[str, Any],
    *,
    run_id: str,
    status: str,
    now_iso: str | None = None,
    phase: str | None = None,
    result_verdict: str | None = None,
    loop_execution_status: str | None = None,
    evidence_status: str | None = None,
    profitability_verdict: str | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in RUN_STATUSES.difference({"running"}):
        raise ValueError(f"Unsupported completed run status: {status!r}")
    current_time = str(now_iso or utc_now_iso())
    active = _normalize_active_run(state.get("active_run"))
    if active is None or active.get("run_id") != str(run_id).strip():
        raise ValueError(f"Cannot complete unknown active run: {run_id}")
    active["status"] = normalized_status
    active["heartbeat_at"] = current_time
    active["lease_expires_at"] = current_time
    if phase:
        active["phase"] = str(phase).strip()
    if result_verdict is not None:
        active["result_verdict"] = result_verdict
    if loop_execution_status is not None:
        active["loop_execution_status"] = loop_execution_status
    if evidence_status is not None:
        active["evidence_status"] = evidence_status
    if profitability_verdict is not None:
        active["profitability_verdict"] = profitability_verdict
    state["active_run"] = active
    state["updated_at"] = current_time
    return copy.deepcopy(active)


def clear_active_run(
    state: dict[str, Any],
    *,
    run_id: str | None = None,
    now_iso: str | None = None,
) -> dict[str, Any] | None:
    active = _normalize_active_run(state.get("active_run")) if state.get("active_run") else None
    if active is None:
        return None
    if run_id is not None and active.get("run_id") != str(run_id).strip():
        raise ValueError(f"Cannot clear unknown active run: {run_id}")
    state["active_run"] = None
    state["updated_at"] = str(now_iso or utc_now_iso())
    return active


def issue_sort_key(issue: dict[str, Any]) -> tuple[int, int, int, str]:
    blocker_priority = BLOCKER_PRIORITY.get(str(issue.get("blocker_class") or "").strip(), 999)
    severity_priority = SEVERITY_PRIORITY.get(str(issue.get("severity") or "").strip().lower(), 999)
    status_priority = 0 if str(issue.get("status") or "").strip().lower() == "open" else 1
    first_seen = str(issue.get("first_seen_at") or "")
    return (blocker_priority, severity_priority, status_priority, first_seen)


def prioritized_open_issues(state: dict[str, Any], *, include_claimed: bool = False) -> list[dict[str, Any]]:
    issues = []
    for item in list(state.get("open_issues") or []):
        status = str(item.get("status") or "").strip().lower()
        if include_claimed:
            if status in OPEN_STATUSES:
                issues.append(dict(item))
        elif status in {"open", "deferred"}:
            issues.append(dict(item))
    issues.sort(key=issue_sort_key)
    return issues


def _is_same_date(lhs: datetime | None, rhs: datetime | None) -> bool:
    return lhs is not None and rhs is not None and lhs.date() == rhs.date()


def validation_prerequisite_blockers(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
    operational_max_age_hours: int = DEFAULT_OPERATIONAL_MAX_AGE_HOURS,
    weekend_holdout_max_age_days: int = DEFAULT_WEEKEND_HOLDOUT_MAX_AGE_DAYS,
) -> list[dict[str, Any]]:
    current_time = now or _utc_now()
    blockers: list[dict[str, Any]] = []

    active = _normalize_active_run(state.get("active_run")) if state.get("active_run") else None
    if active and active["automation_id"] == "daily-profit-validation" and active["status"] == "running":
        if not _is_expired(active.get("lease_expires_at"), now=current_time):
            blockers.append(
                {
                    "code": "active_profit_validation_run",
                    "severity": "blocked",
                    "message": "Daily profit validation already has an active leased run.",
                    "run_id": active.get("run_id"),
                    "lease_expires_at": active.get("lease_expires_at"),
                }
            )

    health = dict(state.get("latest_operational_health") or {})
    health_time = _parse_iso_datetime(health.get("ran_at"))
    health_status = str(health.get("loop_execution_status") or _infer_loop_execution_status(health)).strip().lower()
    if health_time is None:
        blockers.append(
            {
                "code": "missing_operational_health",
                "severity": "blocked",
                "message": "Daily profit validation requires a recent operational health snapshot.",
            }
        )
    elif current_time - health_time > timedelta(hours=int(operational_max_age_hours)):
        blockers.append(
            {
                "code": "stale_operational_health",
                "severity": "blocked",
                "message": "Operational health is older than the validation freshness window.",
                "ran_at": health.get("ran_at"),
                "allowed_age_hours": int(operational_max_age_hours),
            }
        )
    elif health_status == "blocked":
        blockers.append(
            {
                "code": "blocked_operational_health",
                "severity": "blocked",
                "message": "Operational health is currently blocked, so profit validation cannot trust prerequisites.",
                "ran_at": health.get("ran_at"),
                "loop_execution_status": health_status,
            }
        )

    holdout = dict(state.get("latest_truth_holdout") or {})
    holdout_time = _parse_iso_datetime(holdout.get("ran_at"))
    holdout_status = str(holdout.get("loop_execution_status") or _infer_loop_execution_status(holdout)).strip().lower()
    refresh_status = str((((holdout.get("results") or {}).get("daily_truth_refresh") or {}).get("status")) or "").strip().lower()
    if holdout_time is None:
        blockers.append(
            {
                "code": "missing_truth_holdout",
                "severity": "blocked",
                "message": "Daily profit validation requires a recent truth holdout snapshot.",
            }
        )
    else:
        current_weekday = current_time.weekday()
        if current_weekday < 5:
            if not _is_same_date(holdout_time, current_time):
                blockers.append(
                    {
                        "code": "stale_truth_holdout",
                        "severity": "blocked",
                        "message": "Weekday validation requires a same-day truth holdout snapshot.",
                        "ran_at": holdout.get("ran_at"),
                    }
                )
        else:
            max_age = timedelta(days=int(weekend_holdout_max_age_days))
            if current_time - holdout_time > max_age or holdout_time.weekday() >= 5:
                blockers.append(
                    {
                        "code": "stale_truth_holdout",
                        "severity": "blocked",
                        "message": "Weekend validation requires the most recent weekday holdout snapshot.",
                        "ran_at": holdout.get("ran_at"),
                        "allowed_age_days": int(weekend_holdout_max_age_days),
                    }
                )
    if holdout_status == "blocked" or refresh_status == "failed":
        blockers.append(
            {
                "code": "failed_truth_holdout",
                "severity": "blocked",
                "message": "The latest truth holdout snapshot failed or used an untrusted truth refresh.",
                "ran_at": holdout.get("ran_at"),
                "loop_execution_status": holdout_status,
                "daily_truth_refresh_status": refresh_status,
            }
        )

    validation = dict(state.get("latest_profit_validation") or {})
    validation_run_status = str(validation.get("run_status") or "").strip().lower()
    validation_time = _parse_iso_datetime(validation.get("ran_at"))
    if validation_run_status == "running":
        blockers.append(
            {
                "code": "stale_profit_validation_snapshot",
                "severity": "blocked",
                "message": "The latest profit validation snapshot is still marked running.",
                "ran_at": validation.get("ran_at"),
                "run_id": validation.get("run_id"),
            }
        )
    return blockers
