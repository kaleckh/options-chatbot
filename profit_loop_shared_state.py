from __future__ import annotations

import copy
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

SCHEMA_VERSION = 1
DEFAULT_OPERATIONAL_MAX_AGE_HOURS = 2
DEFAULT_WEEKEND_HOLDOUT_MAX_AGE_DAYS = 3

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
OPEN_STATUSES = {"open", "claimed", "deferred"}

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


def empty_profit_loop_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
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
    evidence = list(payload.get("evidence") or base.get("evidence") or [])
    suggested_fix_targets = list(payload.get("suggested_fix_targets") or base.get("suggested_fix_targets") or [])
    status = str(payload.get("status") or base.get("status") or "open").strip().lower()
    if status not in OPEN_STATUSES | {"resolved"}:
        raise ValueError(f"Unsupported issue status {status!r} for issue {issue_id}")
    first_seen = str(payload.get("first_seen_at") or base.get("first_seen_at") or current_time)
    last_seen = str(payload.get("last_seen_at") or current_time)

    normalized = {
        "issue_id": issue_id,
        "source_automation": source_automation,
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "severity": severity,
        "blocker_class": blocker_class,
        "summary": summary,
        "evidence": [str(item) for item in evidence],
        "suggested_fix_targets": [str(item) for item in suggested_fix_targets],
        "status": status,
        "deferred_reason": payload.get("deferred_reason", base.get("deferred_reason")),
        "next_action": payload.get("next_action", base.get("next_action")),
        "last_validation_attempt_at": payload.get("last_validation_attempt_at", base.get("last_validation_attempt_at")),
        "resolved_at": payload.get("resolved_at", base.get("resolved_at")),
        "resolution_branch": payload.get("resolution_branch", base.get("resolution_branch")),
        "resolution_commit": payload.get("resolution_commit", base.get("resolution_commit")),
    }
    missing = REQUIRED_ISSUE_KEYS.difference(normalized.keys())
    if missing:
        raise ValueError(f"Issue {issue_id} missing keys: {sorted(missing)}")
    return normalized


def validate_profit_loop_state(payload: dict[str, Any]) -> dict[str, Any]:
    required_top_level = {
        "schema_version",
        "updated_at",
        "latest_operational_health",
        "latest_truth_holdout",
        "latest_profit_validation",
        "open_issues",
        "resolved_issues",
    }
    missing = required_top_level.difference(payload.keys())
    if missing:
        raise ValueError(f"Profit loop state missing keys: {sorted(missing)}")
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {payload.get('schema_version')!r}")
    if not isinstance(payload.get("open_issues"), list):
        raise ValueError("open_issues must be a list")
    if not isinstance(payload.get("resolved_issues"), list):
        raise ValueError("resolved_issues must be a list")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": str(payload.get("updated_at") or utc_now_iso()),
        "latest_operational_health": payload.get("latest_operational_health"),
        "latest_truth_holdout": payload.get("latest_truth_holdout"),
        "latest_profit_validation": payload.get("latest_profit_validation"),
        "open_issues": [],
        "resolved_issues": [],
    }
    for issue in list(payload.get("open_issues") or []):
        normalized["open_issues"].append(_normalize_issue(dict(issue), existing=None))
    for issue in list(payload.get("resolved_issues") or []):
        normalized["resolved_issues"].append(
            _normalize_issue(dict(issue) | {"status": "resolved"}, existing=None)
        )
    return normalized


def _legacy_seed_payload() -> dict[str, Any]:
    state = empty_profit_loop_state()
    now_iso = utc_now_iso()
    state["open_issues"] = [_normalize_issue(issue, now_iso=now_iso) for issue in SEEDED_ISSUES]
    return state


def _import_legacy_repo_handoff() -> dict[str, Any] | None:
    payload = _load_json(LEGACY_REPO_HANDOFF_PATH)
    if not payload or payload.get("example_only"):
        return None
    imported = empty_profit_loop_state()
    imported["updated_at"] = str(payload.get("updated_at") or utc_now_iso())
    imported["latest_operational_health"] = payload.get("latest_operational_health")
    imported["latest_truth_holdout"] = payload.get("latest_truth_holdout")
    imported["latest_profit_validation"] = payload.get("latest_profit_validation")
    now_iso = utc_now_iso()
    for issue in list(payload.get("open_issues") or []):
        imported["open_issues"].append(_normalize_issue(dict(issue), now_iso=now_iso))
    for issue in list(payload.get("resolved_issues") or []):
        imported["resolved_issues"].append(
            _normalize_issue(dict(issue) | {"status": "resolved"}, now_iso=now_iso)
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
    path = state_path(directory)
    if not path.exists():
        initialize_profit_loop_state(directory)
    return directory


def load_profit_loop_state(state_dir: str | Path | None = None) -> dict[str, Any]:
    ensure_profit_loop_state(state_dir)
    payload = _load_json(state_path(state_dir))
    if payload is None:
        return initialize_profit_loop_state(state_dir)
    return validate_profit_loop_state(payload)


def save_profit_loop_state(payload: dict[str, Any], *, state_dir: str | Path | None = None) -> Path:
    normalized = validate_profit_loop_state(payload)
    normalized["updated_at"] = utc_now_iso()
    return _atomic_write_json(state_path(state_dir), normalized)


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
        dict(issue) | {"status": "open", "last_seen_at": current_time},
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

    if open_index is not None:
        open_issues[open_index] = normalized
    else:
        open_issues.append(normalized)
    state["open_issues"] = open_issues
    state["resolved_issues"] = resolved_issues
    state["updated_at"] = current_time
    return normalized


def claim_issue(
    state: dict[str, Any],
    issue_id: str,
    *,
    now_iso: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
    open_issues = list(state.get("open_issues") or [])
    index = _find_issue_index(open_issues, issue_id)
    if index is None:
        raise ValueError(f"Cannot claim unknown issue: {issue_id}")
    issue = _normalize_issue(
        dict(open_issues[index])
        | {
            "status": "claimed",
            "last_seen_at": current_time,
            "last_validation_attempt_at": current_time,
            "next_action": next_action or open_issues[index].get("next_action"),
        },
        now_iso=current_time,
        existing=open_issues[index],
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
    now_iso: str | None = None,
) -> dict[str, Any]:
    current_time = str(now_iso or utc_now_iso())
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
            "resolution_branch": str(resolution_branch or "").strip() or None,
            "resolution_commit": str(resolution_commit or "").strip() or None,
            "deferred_reason": None,
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
    state[key] = copy.deepcopy(payload)
    state["updated_at"] = str(now_iso or utc_now_iso())
    return state


def issue_sort_key(issue: dict[str, Any]) -> tuple[int, int, str]:
    blocker_priority = BLOCKER_PRIORITY.get(str(issue.get("blocker_class") or "").strip(), 999)
    severity_priority = SEVERITY_PRIORITY.get(str(issue.get("severity") or "").strip().lower(), 999)
    first_seen = str(issue.get("first_seen_at") or "")
    return (blocker_priority, severity_priority, first_seen)


def prioritized_open_issues(state: dict[str, Any]) -> list[dict[str, Any]]:
    issues = [dict(item) for item in list(state.get("open_issues") or [])]
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

    health = dict(state.get("latest_operational_health") or {})
    health_time = _parse_iso_datetime(health.get("ran_at"))
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

    holdout = dict(state.get("latest_truth_holdout") or {})
    holdout_time = _parse_iso_datetime(holdout.get("ran_at"))
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
    return blockers
