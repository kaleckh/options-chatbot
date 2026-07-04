from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "agent-control" / "agent_control.db"
DEFAULT_EVENTS_PATH = ROOT / "data" / "agent-control" / "events.jsonl"
DEFAULT_ANCHORS_PATH = ROOT / "data" / "agent-control" / "anchors.jsonl"
DEFAULT_SESSIONS_PATH = ROOT / "data" / "agent-control" / "sessions.jsonl"
DEFAULT_DREAMS_DIR = ROOT / "data" / "agent-control" / "dreams"
DEFAULT_DREAM_RUNS_DIR = ROOT / "data" / "agent-control" / "dream-runs"
DEFAULT_CONTEXT_PACKS_DIR = ROOT / "data" / "agent-control" / "context-packs"
DEFAULT_BACKUPS_DIR = ROOT / "data" / "agent-control" / "backups"
DEFAULT_LOCK_PATH = ROOT / "data" / "agent-control" / "agent_control.lock"
DEFAULT_LOCK_STALE_SECONDS = 15 * 60
DEFAULT_TENANT_ID = "options-chatbot"
AGENT_RUN_LEDGER_VERSION = "agent_run_ledger_v1"
CONTROL_SCHEMA_VERSION = "agent_control_schema_v3"
DEFAULT_REPO_INDEX_MAX_FILES = 2000
DEFAULT_REPO_INDEX_MAX_FILE_BYTES = 256_000
DEFAULT_REPO_INDEX_BODY_CHARS = 12_000
DEFAULT_CHECKPOINT_AUTONOMY_LEVEL = "read_only_workers"
DEFAULT_CONTEXT_PACK_LIMIT = 6
DEFAULT_MEMORY_GOLDEN_QUERIES_PATH = ROOT / "data" / "contracts" / "memory-golden-queries.json"
LIVING_HISTORY_INGEST_VERSION = "living_history_ingest_v1"
LIVING_HISTORY_SOURCE_TYPE = "living_history_ingest"

PATHWAYS = {
    "data",
    "candidate",
    "evidence",
    "profitability",
    "promotion",
    "operator",
    "general",
}
TASK_STATUSES = {"open", "claimed", "reported", "accepted", "blocked", "cancelled"}
TERMINAL_TASK_STATUSES = {"accepted", "blocked", "cancelled"}
CHECKPOINT_STATUSES = {"in_progress", "complete", "blocked", "paused"}
PERMISSION_MODES = {
    "context_only",
    "read_only_workers",
    "code_docs",
    "evidence_mutation",
    "broker_paper_discussion",
    "live_capital_discussion",
}
HIGH_RISK_PERMISSION_MODES = {
    "evidence_mutation",
    "broker_paper_discussion",
    "live_capital_discussion",
}
GRAPH_NODE_KINDS = {
    "memory",
    "knowledge",
    "episode",
    "entity",
    "task",
    "blocker",
    "evidence_artifact",
    "decision",
    "worker_run",
}
OPERATING_MEMORY_TYPES = {
    "objective",
    "constraint",
    "decision",
    "blocker",
    "verification",
    "artifact",
    "worker_report",
    "lesson",
    "open_question",
    "superseded_fact",
}
DREAM_PROPOSAL_TYPES = {
    "lesson",
    "constraint",
    "decision",
    "blocker",
    "open_question",
    "superseded_fact",
}
AUTO_DREAM_POLICY_VERSION = "auto_dream_v1"
MEMORY_POLICY_VERSION = "memory_graph_v2_2026_06_28"
AUTO_DREAM_ALLOWED_TYPES = {"lesson", "constraint", "open_question"}
AUTO_DREAM_MANUAL_REVIEW_TYPES = {"decision", "blocker", "superseded_fact"}
AUTO_DREAM_HIGH_RISK_PATTERNS = (
    r"\bauthori[sz]e\b",
    r"\bapproval\b",
    r"\bapprove\b",
    r"\bbroker\b",
    r"\bbroker[-_ ]?orders?\b",
    r"\bsubmit[-_ ]?orders?\b",
    r"\bplace[-_ ]?orders?\b",
    r"\bopen[-_ ]?orders?\b",
    r"\bclose[-_ ]?orders?\b",
    r"\bcreate[-_ ]?orders?\b",
    r"\bcancel[-_ ]?orders?\b",
    r"\blive\b",
    r"\blive[-_ ]?validation\b",
    r"\btrade\b",
    r"\btrading\b",
    r"\bauto[-_ ]?track\b",
    r"\bscanner[-_ ]?policy\b",
    r"\bproof[-_ ]?bars?\b",
    r"\bevidence[-_ ]?mutation\b",
    r"\bevidence[-_ ]?store\b",
    r"\bevidence[-_ ]?store[-_ ]?mutation\b",
    r"\bmutate[-_ ]?evidence\b",
    r"\bquote[-_ ]?imports?\b",
    r"\bimport[-_ ]?quotes?\b",
    r"\bpromotion\b",
    r"\bpromote\b",
    r"\bprotected[-_ ]?holdout\b",
    r"\bstop[-_/ ]?sizing\b",
    r"\bsizing\b",
)
AUTO_DREAM_HIGH_RISK_RE = tuple(re.compile(pattern, re.IGNORECASE) for pattern in AUTO_DREAM_HIGH_RISK_PATTERNS)
AUTO_DREAM_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(lesson|constraint|open[_ -]?question)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
MEMORY_STATUSES = {"active", "resolved", "superseded", "expired", "archived"}
INACTIVE_MEMORY_STATUSES = {"resolved", "superseded", "expired", "archived"}
MEMORY_CONFIDENCE = {"accepted", "observed", "inferred", "unknown"}
OPERATING_AUTHORITY_SCOPE = "orchestration_only"
OPERATING_AUTHORITY_METADATA = {
    "authority_scope": OPERATING_AUTHORITY_SCOPE,
    "does_not_authorize_trading_or_evidence_mutation": True,
}
MEMORY_NON_AUTHORIZATION_BANNER = (
    "Memory is retrieval context only. It never authorizes evidence mutation, scanner or strategy changes, "
    "proof-bar changes, broker action, promotion, live validation, stop/sizing changes, protected-holdout use, "
    "or treating historical rows as forward proof."
)
MEMORY_SOURCE_QUALITY_BY_TYPE = {
    "operating_memory": "accepted_runtime_memory",
    "dream_proposal": "unaccepted_dream_proposal",
    "dream_run": "automation_audit",
    "session_transcript": "session_transcript",
    "startup_doc": "repo_startup_doc",
    "living_doc": "living_doc",
    "control_plane_doc": "living_doc",
    "repo_file_index": "repo_file_index",
    "gateboard_blocker": "generated_gateboard",
    "gateboard_doc": "generated_gateboard",
    "gateboard_latest": "generated_gateboard",
    "gateboard_latest_json": "generated_gateboard",
    "gateboard_pathway": "generated_gateboard",
    "gateboard_source_artifact": "generated_gateboard",
    "static_memory_graph_node": "generated_navigation",
    "static_memory_graph_doc": "generated_navigation",
    "static_memory_graph_json": "generated_navigation",
    "project_memory_seed": "automation_audit",
    "profit_learning_sync": "generated_readback",
    "research_provenance": "research_provenance",
    LIVING_HISTORY_SOURCE_TYPE: "living_history",
}
RETRIEVAL_SOURCE_TYPE_TIERS = {
    "operating_memory": 1,
    "living_doc": 1,
    "control_plane_doc": 1,
    "startup_doc": 1,
    "package_manifest": 1,
    "static_memory_graph_node": 1,
    "static_memory_graph_doc": 1,
    "static_memory_graph_json": 1,
    "gateboard_blocker": 1,
    "gateboard_doc": 1,
    "gateboard_latest": 1,
    "gateboard_latest_json": 1,
    "gateboard_pathway": 1,
    "gateboard_source_artifact": 1,
    LIVING_HISTORY_SOURCE_TYPE: 1,
    "profit_learning_sync": 2,
    "dream_run": 2,
    "repo_file_index": 3,
}
RETRIEVAL_TIER_1_NODE_KINDS = {"memory", "decision", "episode", "blocker"}
RETRIEVAL_REPO_INDEX_TIER = 3
PROVENANCE_KINDS = {
    "strategy_hypothesis",
    "experiment_run",
    "dataset_version",
    "feature_snapshot",
    "zero_candidate_episode",
    "drift_report",
}
AUTHORITY_METADATA_KEYS = {
    "authority_scope",
    "capability_label",
    "append_allowed",
    "appendAllowed",
    "promotion_ready",
    "promotionReady",
    "live_validation_eligible",
    "liveValidationEligible",
}
PROHIBITED_TRUE_FLAG_KEYS = {
    "append_allowed",
    "appendAllowed",
    "promotion_ready",
    "promotionReady",
    "live_validation_eligible",
    "liveValidationEligible",
    "live_entry_allowed",
    "liveEntryAllowed",
    "auto_track_allowed",
    "autoTrackAllowed",
    "broker_order_allowed",
    "brokerOrderAllowed",
    "cohort_append_performed",
    "cohortAppendPerformed",
    "quotes_imported",
    "quotesImported",
    "evidence_stores_mutated",
    "evidenceStoresMutated",
    "scanner_policy_changed",
    "scannerPolicyChanged",
    "strategy_logic_changed",
    "strategyLogicChanged",
    "proof_bars_changed",
    "proofBarsChanged",
    "protected_holdout_consumed",
    "protectedHoldoutConsumed",
}
PROFIT_LEARNING_OMIT_METRIC_KEYS = PROHIBITED_TRUE_FLAG_KEYS | {
    "append_allowed",
    "appendAllowed",
    "live_validation_eligible",
    "liveValidationEligible",
    "accepted_profitability",
    "profitability_readiness",
}
PROFIT_LEARNING_DENOMINATOR_KEYS = (
    "queue_rows",
    "quarantine_queue_count",
    "high_priority_evidence_repair_count",
    "fresh_scan_match_count",
    "total_natural_selections",
    "exact_completed_forward_pnl_count",
    "remaining_rows",
    "strict_reject_counts",
    "warning_states",
    "dependency_blockers",
    "denominator_rule",
)
PROFIT_LEARNING_AUTHORITY_STATUS_TOKENS = {
    "append_allowed",
    "promotion_ready",
    "live_validation_eligible",
    "live_entry_allowed",
    "auto_track_allowed",
    "broker_order_allowed",
    "cohort_append_performed",
    "quotes_imported",
    "evidence_stores_mutated",
    "scanner_policy_changed",
    "strategy_logic_changed",
    "proof_bars_changed",
    "protected_holdout_consumed",
    "approval",
    "approved",
    "authorized",
    "allowed",
    "enabled",
    "cleared",
    "ready",
    "readiness",
    "promotion",
    "live",
    "broker",
}
PROHIBITED_AUTHORITY_VALUE_KEYS = {
    "authority_scope": {
        "broker_action",
        "evidence_mutation",
        "scanner_policy_change",
        "promotion_authority",
        "live_validation_authority",
    },
    "capability_label": {
        "broker_action",
        "evidence_mutation",
        "scanner_policy_change",
        "promotion_authority",
        "live_validation_authority",
    },
}
MEMORY_PROHIBITED_AUTHORITY_RE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:authori[sz]e|approve|approved|approval)\s+(?:live|broker|trade|trading|auto[-_ ]?track|promotion|proof[-_ ]?bar|evidence[-_ ]?mutation|scanner|strategy|stop|sizing|append|cohort[-_ ]?append|candidate[-_ ]?append|guarded[-_ ]?append|append[-_ ]?readiness)",
        r"\b(?:live|broker|trading|trade|orders?|submit[-_ ]?orders?|place[-_ ]?orders?|open[-_ ]?orders?|close[-_ ]?orders?|create[-_ ]?orders?|cancel[-_ ]?orders?|append|cohort[-_ ]?append|candidate[-_ ]?append|guarded[-_ ]?append|append[-_ ]?readiness|auto[-_ ]?track|promotion|proof[-_ ]?bar|evidence[-_ ]?mutation|scanner[-_ ]?policy|strategy|stop[-_/ ]?sizing)\s+(?:is\s+|are\s+)?(?:approved|authorized|allowed|enabled|cleared|complete|ready)",
        r"\b(?:broker[-_ ]?orders?|submit[-_ ]?orders?|place[-_ ]?orders?|open[-_ ]?orders?|close[-_ ]?orders?|create[-_ ]?orders?|cancel[-_ ]?orders?)\b",
        r"\b(?:append|cohort[-_ ]?append|candidate[-_ ]?append|guarded[-_ ]?append|append[-_ ]?readiness)\b[^.;\n]{0,80}\b(?:approved|authorized|allowed|enabled|cleared|complete|ready)\b",
        r"\btreat(?:ing)?\s+historical\s+rows\s+as\s+forward\s+proof\b",
        r"\bhistorical\s+rows\s+(?:are|count\s+as)\s+forward\s+proof\b",
        r"\bappend[_ -]?allowed\s*[:=]\s*true\b",
        r"\bappendAllowed\s*[:=]\s*true\b",
        r"\bpromotion[_ -]?ready\s*[:=]\s*true\b",
        r"\bpromotionReady\s*[:=]\s*true\b",
        r"\blive[_ -]?validation[_ -]?eligible\s*[:=]\s*true\b",
        r"\bliveValidationEligible\s*[:=]\s*true\b",
    )
)
SAFE_NEGATED_AUTHORITY_RE = re.compile(
    r"\b(?:(?:must|does|do|should|can)\s+not|cannot|can't|never)\s+"
    r"(?:authori[sz]e|approve|allow|enable)\s+"
    r"(?:live|broker|trade|trading|auto[-_ ]?track|promotion|proof[-_ ]?bar|"
    r"evidence[-_ ]?mutation|scanner|strategy|stop|sizing|append|cohort[-_ ]?append|"
    r"candidate[-_ ]?append|guarded[-_ ]?append|append[-_ ]?readiness)"
    r"(?:\s+actions?|\s+authority|\s+access|\s+execution)?",
    re.IGNORECASE,
)
OPERATING_MEMORY_KIND_BY_TYPE = {
    "artifact": "evidence_artifact",
    "blocker": "blocker",
    "decision": "decision",
    "open_question": "blocker",
    "verification": "evidence_artifact",
}
STATIC_SEED_SOURCE_TYPES = {"static_memory_graph_node"}
GATEBOARD_CURRENT_SOURCE_TYPES = {
    "gateboard_pathway",
    "gateboard_blocker",
    "gateboard_source_artifact",
}
REPO_FILE_SOURCE_TYPES = {"repo_file_index"}
FILE_FRESHNESS_SOURCE_TYPES = {
    "repo_file_index",
    "living_doc",
    "control_plane_doc",
    "startup_doc",
    LIVING_HISTORY_SOURCE_TYPE,
}
PROFIT_LEARNING_SYNC_TOKEN = "APPROVE_PROFIT_LEARNING_MEMORY_SYNC"
PROFIT_LEARNING_EXTRACTOR_VERSION = "profit_learning_sync_v1"

PROFIT_LEARNING_ARTIFACTS = {
    "gateboard": "data/forward-tracking/project_operator_gateboard_latest.json",
    "strict_forward_operator_queue": "data/forward-tracking/regular_options_strict_forward_operator_queue_latest.json",
    "strict_forward_candidate_review": (
        "data/forward-tracking/regular_options_strict_forward_30_candidate_review_packet_latest.json"
    ),
    "strict_forward_completion_monitor": (
        "data/forward-tracking/regular_options_strict_forward_30_completion_monitor_latest.json"
    ),
    "forward_candidate_throughput": "data/forward-tracking/regular_options_forward_candidate_throughput_audit_latest.json",
    "profit_capture_queue": "data/profitability-lab/regular-options-profit-capture-queue/latest.json",
    "repair_burndown": "data/profitability-lab/regular-options-repair-burndown/latest.json",
}
AGENT_RUN_EVENT_TYPES = {
    "started",
    "heartbeat",
    "tool_call",
    "memory_read",
    "memory_write",
    "approval_requested",
    "approval_recorded",
    "artifact",
    "blocked",
    "failed",
    "completed",
    "cancelled",
}
AGENT_RUN_TERMINAL_EVENT_TYPES = {"blocked", "failed", "completed", "cancelled"}
AGENT_RUN_STATUSES = {"queued", "running", "succeeded", "failed", "blocked", "cancelled"}
AGENT_RUN_EVENT_STATUS = {
    "started": "running",
    "heartbeat": "running",
    "tool_call": "running",
    "memory_read": "running",
    "memory_write": "running",
    "approval_requested": "blocked",
    "approval_recorded": "running",
    "artifact": "running",
    "blocked": "blocked",
    "failed": "failed",
    "completed": "succeeded",
    "cancelled": "cancelled",
}
AGENT_RUN_REDACTED = "[redacted]"
AGENT_RUN_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|auth|credential|cookie|session|private[_-]?key)",
    re.IGNORECASE,
)
AGENT_RUN_BLOCKER_TAXONOMY = {
    "missing_context",
    "test_failure",
    "tool_failure",
    "permission",
    "network",
    "ambiguous_requirement",
    "external_dependency",
    "safety_policy",
    "verification_gap",
    "user_input_required",
}

PROJECT_SEED_FILES = [
    {
        "path": "AGENTS.md",
        "title": "Repo agent guide",
        "sub_tenant_id": "general",
        "authority": "repo_startup",
        "source_type": "startup_doc",
    },
    {
        "path": "README.md",
        "title": "README",
        "sub_tenant_id": "general",
        "authority": "repo_startup",
        "source_type": "startup_doc",
    },
    {
        "path": "docs/index.md",
        "title": "Docs index",
        "sub_tenant_id": "general",
        "authority": "living_doc",
        "source_type": "living_doc",
    },
    {
        "path": "docs/PROJECT_CONTEXT.md",
        "title": "Project context",
        "sub_tenant_id": "general",
        "authority": "living_doc",
        "source_type": "living_doc",
    },
    {
        "path": "docs/DECISIONS.md",
        "title": "Durable decisions",
        "sub_tenant_id": "general",
        "authority": "living_doc",
        "source_type": "living_doc",
    },
    {
        "path": "docs/NEXT_STEPS.md",
        "title": "Next steps",
        "sub_tenant_id": "operator",
        "authority": "living_doc",
        "source_type": "living_doc",
    },
    {
        "path": "docs/agent-control-plane.md",
        "title": "Agent control plane",
        "sub_tenant_id": "operator",
        "authority": "living_doc",
        "source_type": "control_plane_doc",
    },
    {
        "path": "docs/agent-memory-graph.md",
        "title": "Static agent memory graph",
        "sub_tenant_id": "general",
        "authority": "generated_navigation",
        "source_type": "static_memory_graph_doc",
    },
    {
        "path": "data/contracts/agent-memory-graph.json",
        "title": "Static agent memory graph JSON",
        "sub_tenant_id": "general",
        "authority": "generated_navigation",
        "source_type": "static_memory_graph_json",
    },
    {
        "path": "docs/project-operator-gateboard.md",
        "title": "Project operator gateboard",
        "sub_tenant_id": "operator",
        "authority": "generated_readback",
        "source_type": "gateboard_doc",
    },
    {
        "path": "data/forward-tracking/project_operator_gateboard_latest.json",
        "title": "Project operator gateboard latest JSON",
        "sub_tenant_id": "operator",
        "authority": "generated_readback",
        "source_type": "gateboard_latest_json",
    },
    {
        "path": "package.json",
        "title": "Package scripts",
        "sub_tenant_id": "general",
        "authority": "repo_manifest",
        "source_type": "package_manifest",
    },
]

REPO_INDEX_TEXT_EXTENSIONS = {
    "",
    ".bat",
    ".cmd",
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
REPO_INDEX_SKIP_PARTS = {
    ".git",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data/agent-control",
    "data/backups",
    "node_modules",
}


class AgentControlError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_plus_days(days: int, *, from_raw: str | None = None) -> str:
    base = _parse_utc(from_raw) or datetime.now(timezone.utc).replace(microsecond=0)
    return (base + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def parse_json_object(raw: str | None, *, field_name: str) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"{field_name} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AgentControlError(f"{field_name} must be a JSON object")
    return parsed


def parse_key_value_filters(raw_filters: list[str] | None, *, field_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in raw_filters or []:
        if "=" not in raw:
            raise AgentControlError(f"{field_name} entries must use KEY=VALUE")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise AgentControlError(f"{field_name} entries must include a key")
        value = value.strip()
        try:
            parsed_value: Any = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value
        result[key] = parsed_value
    return result


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentControlError(f"{path} line {line_number} must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AgentControlError(f"{path} line {line_number} must be a JSON object")
        rows.append(parsed)
    return rows


def _resolve_inside_repo(repo_root: Path, target: Path) -> Path:
    repo_root = repo_root.resolve()
    resolved = target.resolve() if target.is_absolute() else (repo_root / target).resolve()
    if resolved != repo_root and repo_root not in resolved.parents:
        raise AgentControlError(f"path must stay inside repo root: {target}")
    return resolved


def _relative_to_repo(repo_root: Path, target: Path) -> str:
    return _safe_node_path(str(target.resolve().relative_to(repo_root.resolve())))


def _assert_memory_safe_source_path(relative_path: str) -> None:
    safe_path = _safe_node_path(relative_path)
    name = Path(safe_path).name.lower()
    secret_names = {
        ".env",
        ".env.local",
        "credentials.json",
        "auth.json",
        "secrets.toml",
        "config.yaml",
    }
    secret_suffixes = (".key", ".pem", ".p12", ".pfx", ".sqlite", ".db")
    if name in secret_names or name.startswith(".env.") or name.endswith(secret_suffixes):
        raise AgentControlError(f"memory capture refuses secret or database path: {relative_path}")
    denied_prefixes = (
        ".git/",
        ".next/",
        ".venv/",
        "node_modules/",
        "data/options-validation/",
        "data/forward-tracking/",
        "data/ai-commodity-infra/",
        "data/alpaca-options-strategy-lab/",
        "data/polymarket/",
        "data/profitability-lab/",
    )
    if any(safe_path == prefix.rstrip("/") or safe_path.startswith(prefix) for prefix in denied_prefixes):
        raise AgentControlError(f"memory capture refuses high-risk/generated path: {relative_path}")


def _safe_node_path(relative_path: str) -> str:
    return relative_path.replace("\\", "/").strip("/").lower()


def _path_node_id(relative_path: str) -> str:
    return f"knowledge:{_safe_node_path(relative_path)}"


def _repo_file_node_id(relative_path: str) -> str:
    return f"repo_file:{_safe_node_path(relative_path)}"


def _read_repo_text(repo_root: Path, relative_path: str) -> str | None:
    path = repo_root / relative_path
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _repo_index_skip(relative_path: str) -> bool:
    safe_path = _safe_node_path(relative_path)
    parts = safe_path.split("/")
    for skip in REPO_INDEX_SKIP_PARTS:
        if safe_path == skip or safe_path.startswith(f"{skip}/"):
            return True
        if skip in parts:
            return True
    return False


def _repo_file_category(relative_path: str) -> str:
    safe_path = _safe_node_path(relative_path)
    if safe_path.startswith("docs/"):
        return "docs"
    if safe_path.startswith("scripts/"):
        return "scripts"
    if safe_path.startswith("tests/"):
        return "tests"
    if safe_path.startswith("src/"):
        return "frontend"
    if safe_path.startswith("python-backend/"):
        return "backend"
    if safe_path.startswith("data/contracts/"):
        return "contracts"
    if safe_path.startswith("data/"):
        return "data"
    if safe_path in {"package.json", "README.md".lower(), "agents.md"}:
        return "startup"
    return "repo"


def _repo_file_is_indexable(repo_root: Path, relative_path: str, *, max_file_bytes: int) -> bool:
    if _repo_index_skip(relative_path):
        return False
    try:
        _assert_memory_safe_source_path(relative_path)
    except AgentControlError:
        return False
    path = repo_root / relative_path
    if not path.is_file():
        return False
    if path.suffix.lower() not in REPO_INDEX_TEXT_EXTENSIONS:
        return False
    try:
        return path.stat().st_size <= max_file_bytes
    except OSError:
        return False


def _git_files(repo_root: Path, args: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return [_safe_node_path(line) for line in completed.stdout.splitlines() if line.strip()]


def _git_tracked_files(repo_root: Path) -> list[str]:
    return _git_files(repo_root, ["--cached"])


def _git_visible_files(repo_root: Path) -> list[str]:
    return _git_files(repo_root, ["--cached", "--others", "--exclude-standard"])


def _fallback_repo_files(repo_root: Path) -> list[str]:
    paths: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = _safe_node_path(str(path.relative_to(repo_root)))
        if _repo_index_skip(relative_path):
            continue
        paths.append(relative_path)
    return paths


def _repo_index_paths(repo_root: Path) -> list[str]:
    paths = _git_visible_files(repo_root)
    if not paths:
        paths = _fallback_repo_files(repo_root)
    return sorted(dict.fromkeys(_safe_node_path(path) for path in paths))


def _repo_file_excerpt(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    symbol_prefixes = (
        "#",
        "def ",
        "class ",
        "async def ",
        "function ",
        "export ",
        "interface ",
        "type ",
        "const ",
        "let ",
    )
    symbol_lines = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith(symbol_prefixes)
    ][:140]
    prefix_chars = max(max_chars // 2, 1000)
    excerpt = text[:prefix_chars].rstrip()
    if symbol_lines:
        excerpt += "\n\n[repo-index-symbol-lines]\n" + "\n".join(symbol_lines)
    return excerpt[:max_chars].rstrip() + "\n[truncated]"



def _metadata_lookup(metadata: dict[str, Any], key: str) -> Any:
    current: Any = metadata
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _metadata_value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        if isinstance(actual, list):
            return any(item in expected for item in actual)
        return actual in expected
    if isinstance(expected, dict) and set(expected) == {"contains"}:
        needle = expected["contains"]
        if isinstance(actual, list):
            return needle in actual
        return str(needle).lower() in str(actual).lower()
    if isinstance(actual, list):
        return expected in actual
    return actual == expected


def _metadata_matches(metadata: dict[str, Any], metadata_filter: dict[str, Any] | None) -> bool:
    if not metadata_filter:
        return True
    return all(
        _metadata_value_matches(_metadata_lookup(metadata, key), expected)
        for key, expected in metadata_filter.items()
    )


def _is_operating_memory(metadata: dict[str, Any]) -> bool:
    return metadata.get("source_type") == "operating_memory"


def _has_operating_authority_metadata(metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("authority_scope") == OPERATING_AUTHORITY_SCOPE
        and metadata.get("does_not_authorize_trading_or_evidence_mutation") is True
    )


def _with_operating_authority_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {**metadata, **OPERATING_AUTHORITY_METADATA}


def _with_memory_policy_metadata(
    metadata: dict[str, Any] | None,
    *,
    source_type: str | None = None,
    source_quality: str | None = None,
    capability_label: str = "coordination_only",
) -> dict[str, Any]:
    result = dict(metadata or {})
    if source_type is not None:
        result["source_type"] = source_type
    inferred_source = str(result.get("source_type") or source_type or "")
    result.update(OPERATING_AUTHORITY_METADATA)
    result["memory_policy_version"] = MEMORY_POLICY_VERSION
    result["capability_label"] = capability_label
    result["source_quality"] = source_quality or str(
        result.get("source_quality") or MEMORY_SOURCE_QUALITY_BY_TYPE.get(inferred_source, "unknown")
    )
    result["non_authorization_notice"] = MEMORY_NON_AUTHORIZATION_BANNER
    return result


def _validate_memory_policy_text(
    *,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
    field_name: str = "memory",
) -> list[str]:
    metadata = metadata or {}
    errors: list[str] = []
    if metadata.get("authority_scope", OPERATING_AUTHORITY_SCOPE) != OPERATING_AUTHORITY_SCOPE:
        errors.append(f"{field_name} authority_scope must be {OPERATING_AUTHORITY_SCOPE}")
    if metadata.get("does_not_authorize_trading_or_evidence_mutation", True) is not True:
        errors.append(f"{field_name} must explicitly not authorize trading or evidence mutation")
    if metadata.get("capability_label") in {
        "broker_action",
        "evidence_mutation",
        "scanner_policy_change",
        "promotion_authority",
        "live_validation_authority",
    }:
        errors.append(f"{field_name} capability_label cannot grant action authority")
    def truthy_authority_value(value: Any) -> bool:
        if value is True:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value == 1
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y", "on", "enabled", "ready", "approved"}
        return False

    def scan_metadata(value: Any, path: str = "metadata") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key in PROHIBITED_TRUE_FLAG_KEYS and truthy_authority_value(child):
                    errors.append(f"{field_name} cannot set {child_path}=true")
                prohibited_values = PROHIBITED_AUTHORITY_VALUE_KEYS.get(key)
                normalized_child = str(child).strip().lower()
                if prohibited_values and normalized_child in prohibited_values:
                    errors.append(f"{field_name} cannot set {child_path}={child}")
                scan_metadata(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan_metadata(child, f"{path}[{index}]")

    scan_metadata(metadata)
    metadata_for_scan = {
        key: value
        for key, value in metadata.items()
        if key not in {"non_authorization_notice"}
    }
    haystack = "\n".join([title, body, canonical_json(metadata_for_scan)])
    haystack = SAFE_NEGATED_AUTHORITY_RE.sub("", haystack)
    for pattern in MEMORY_PROHIBITED_AUTHORITY_RE:
        if pattern.search(haystack):
            errors.append(f"{field_name} contains prohibited authority wording: {pattern.pattern}")
            break
    return errors


def _assert_memory_policy_valid(
    *,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
    field_name: str = "memory",
) -> None:
    errors = _validate_memory_policy_text(title=title, body=body, metadata=metadata, field_name=field_name)
    if errors:
        raise AgentControlError("; ".join(errors))


def _metadata_for_retrieval(metadata: dict[str, Any]) -> dict[str, Any]:
    source_type = metadata.get("source_type")
    if _is_operating_memory(metadata):
        return metadata
    sanitized = {
        key: value
        for key, value in metadata.items()
        if key not in AUTHORITY_METADATA_KEYS
    }
    if source_type == "dream_proposal":
        sanitized.pop("entries", None)
        sanitized["entries_omitted_from_retrieval"] = True
    if any(key in metadata for key in AUTHORITY_METADATA_KEYS):
        sanitized["authority_metadata_ignored_for_retrieval"] = True
    sanitized["authority_scope"] = OPERATING_AUTHORITY_SCOPE
    sanitized["capability_label"] = "coordination_only"
    return sanitized


def _metadata_for_prompt(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata") or {}
    if _is_operating_memory(metadata):
        return metadata
    return _metadata_for_retrieval(metadata)


def _non_operating_policy_errors(title: str, body: str, metadata: dict[str, Any]) -> list[str]:
    if _is_operating_memory(metadata):
        return []
    return _validate_memory_policy_text(
        title=title,
        body=body,
        metadata=_with_memory_policy_metadata(
            _metadata_for_retrieval(metadata),
            source_type=str(metadata.get("source_type") or "graph_node"),
        ),
        field_name="non-operating graph context",
    )


def _node_retrieval_title_body(node: dict[str, Any], metadata: dict[str, Any]) -> tuple[str, str]:
    title = str(node.get("title") or "")
    body = str(node.get("body") or "")
    if _non_operating_policy_errors(title, body, metadata):
        return "[non-operating title omitted: prohibited authority wording]", (
            "[non-operating body omitted from retrieval: prohibited authority wording]"
        )
    return title, body


def _node_for_query_result(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata") or {}
    if _is_operating_memory(metadata):
        return node
    title, body = _node_retrieval_title_body(node, metadata)
    return {
        **node,
        "title": title,
        "body": body,
        "metadata": _metadata_for_retrieval(metadata),
    }


def _memory_is_inactive(metadata: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not _is_operating_memory(metadata):
        return False
    if metadata.get("memory_status") in INACTIVE_MEMORY_STATUSES:
        return True
    expires_at = _parse_utc(metadata.get("expires_at"))
    if expires_at is not None and (now or datetime.now(timezone.utc)) >= expires_at:
        return True
    return False


def _memory_is_stale(metadata: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not _is_operating_memory(metadata):
        return False
    now = now or datetime.now(timezone.utc)
    expires_at = _parse_utc(metadata.get("expires_at"))
    if expires_at is not None and now >= expires_at:
        return True
    freshness_days = metadata.get("freshness_days")
    recorded_at = _parse_utc(metadata.get("recorded_at"))
    if recorded_at is None or freshness_days in (None, ""):
        return False
    try:
        days = int(freshness_days)
    except (TypeError, ValueError):
        return False
    return now - recorded_at >= timedelta(days=days)


def _split_memory_items(raw: str) -> list[str]:
    normalized = raw.replace(";", "\n").replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def _query_terms(query: str) -> list[str]:
    return [part for part in query.lower().replace("/", " ").replace("-", " ").split() if part]


def _score_node_for_query(node: dict[str, Any], query: str) -> int | None:
    terms = _query_terms(query)
    if not terms:
        return 0
    metadata = _metadata_for_retrieval(node.get("metadata", {}))
    title, body = _node_retrieval_title_body(node, node.get("metadata") or {})
    haystack = " ".join(
        [
            str(node.get("id", "")),
            title,
            body,
            str(node.get("source_ref", "")),
            canonical_json(metadata) if isinstance(metadata, dict) else str(metadata),
        ]
    ).lower()
    if not all(term in haystack for term in terms):
        return None
    score = sum(haystack.count(term) for term in terms)
    if query.lower() in haystack:
        score += len(terms) * 3
    if title.lower().find(query.lower()) >= 0:
        score += len(terms) * 2
    return score


def _truncate(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _format_graph_context(
    result: dict[str, Any],
    *,
    max_nodes: int = 12,
    max_edges: int = 16,
) -> str:
    context = result["graph_context"]
    lines = [
        "# Agent Graph Context",
        f"Query: {result.get('query', '')}",
        f"Tenant: {result.get('tenant_id')}",
    ]
    if result.get("sub_tenant_id"):
        lines.append(f"Sub-tenant: {result['sub_tenant_id']}")
    if result.get("metadata_filter"):
        lines.append(f"Metadata filter: {canonical_json(result['metadata_filter'])}")
    retrieval = result.get("retrieval") or {}
    if retrieval:
        lines.append(f"Policy: {retrieval.get('policy_banner')}")
        lines.append(f"Retrieval index: {retrieval.get('index')} ({retrieval.get('policy_version')})")

    lines.append("")
    lines.append("Seed nodes:")
    seed_ids = set(context.get("seed_node_ids", []))
    nodes = context.get("nodes", [])
    ordered_nodes = sorted(nodes, key=lambda node: (node["id"] not in seed_ids, node["id"]))
    for node in ordered_nodes[:max_nodes]:
        source_ref = f" source={node.get('source_ref')}" if node.get("source_ref") else ""
        sub_tenant = f"/{node.get('sub_tenant_id')}" if node.get("sub_tenant_id") else ""
        prompt_title, prompt_body = _node_retrieval_title_body(node, node.get("metadata") or {})
        lines.append(f"- {node['id']} [{node.get('kind')}{sub_tenant}] {prompt_title}{source_ref}")
        body = _truncate(prompt_body, 260)
        if body:
            lines.append(f"  body: {body}")
        metadata = _metadata_for_prompt(node)
        if metadata:
            lines.append(f"  metadata: {_truncate(canonical_json(metadata), 360)}")
        explanation = next(
            (
                item
                for item in retrieval.get("seed_explanations", [])
                if item and item.get("source_node_id") == node["id"]
            ),
            None,
        )
        if explanation:
            lines.append(
                "  retrieval: "
                + _truncate(
                    canonical_json(
                        {
                            "source_quality": explanation.get("source_quality"),
                            "authority_scope": explanation.get("authority_scope"),
                            "capability_label": explanation.get("capability_label"),
                            "freshness_status": explanation.get("freshness_status"),
                            "why": explanation.get("why"),
                        }
                    ),
                    360,
                )
            )
    if len(ordered_nodes) > max_nodes:
        lines.append(f"- ... {len(ordered_nodes) - max_nodes} additional nodes omitted")

    lines.append("")
    lines.append("Triplets:")
    triplets = context.get("triplets", [])
    for triplet in triplets[:max_edges]:
        metadata = triplet.get("metadata") or {}
        suffix = f" metadata={_truncate(canonical_json(metadata), 220)}" if metadata else ""
        lines.append(f"- {triplet['source']} --{triplet['relation']}--> {triplet['target']}{suffix}")
    if len(triplets) > max_edges:
        lines.append(f"- ... {len(triplets) - max_edges} additional triplets omitted")
    return "\n".join(lines)


def _format_checkpoint_context(checkpoint: dict[str, Any] | None) -> str:
    lines = ["# CEO Session Checkpoint"]
    if checkpoint is None:
        lines.append("No runtime checkpoint recorded yet.")
        return "\n".join(lines)

    metadata = checkpoint.get("metadata") or {}
    lines.extend(
        [
            f"Status: {metadata.get('status', 'unknown')}",
            f"Objective: {metadata.get('objective', checkpoint.get('title', ''))}",
            f"Scope: {metadata.get('scope', '')}",
            f"Autonomy: {metadata.get('autonomy_level', '')}",
        ]
    )
    summary = _truncate(str(checkpoint.get("body", "")), 700)
    if summary:
        lines.append(f"Summary: {summary}")
    for key, heading in [
        ("success_criteria", "Success criteria"),
        ("constraints", "Constraints"),
        ("next_actions", "Next actions"),
        ("verification", "Verification"),
        ("blockers", "Blockers"),
        ("files_changed", "Files changed"),
        ("commands_run", "Commands run"),
    ]:
        values = metadata.get(key) or []
        if isinstance(values, str):
            values = [values]
        if values:
            lines.append(f"{heading}:")
            for value in values:
                lines.append(f"- {value}")
    return "\n".join(lines)


def _format_bootstrap_context(result: dict[str, Any]) -> str:
    checkpoint_text = _format_checkpoint_context(result.get("latest_checkpoint"))
    graph_text = result["context"]["prompt_context"]
    manifest_text = ""
    if result.get("context_manifest"):
        manifest_text = "\n".join(
            [
                "# Context Manifest",
                f"Path: {result['context_manifest'].get('manifest_path')}",
                f"Policy: {result['context_manifest'].get('policy_banner')}",
            ]
        )
    next_queries = ["# Recommended Graph Queries"]
    for item in result.get("recommended_next_queries", []):
        next_queries.append(f"- {item['purpose']}: `{item['command']}`")
    sections = [checkpoint_text, graph_text]
    if manifest_text:
        sections.append(manifest_text)
    sections.append("\n".join(next_queries))
    return "\n\n".join(sections)


def _format_node_list(nodes: list[dict[str, Any]], *, empty: str) -> list[str]:
    if not nodes:
        return [f"- {empty}"]
    lines: list[str] = []
    for node in nodes:
        metadata = node.get("metadata") or {}
        status = metadata.get("memory_status") or metadata.get("status") or ""
        status_text = f" status={status}" if status else ""
        source = f" source={node.get('source_ref')}" if node.get("source_ref") else ""
        lines.append(f"- {node['id']} [{node.get('kind')}] {node.get('title', '')}{status_text}{source}")
        body = _truncate(str(node.get("body", "")), 220)
        if body:
            lines.append(f"  body: {body}")
        for key, label in [
            ("commands_run", "commands"),
            ("files_artifacts_read", "files read"),
            ("acceptance_criteria", "acceptance criteria"),
            ("review_question", "review question"),
        ]:
            value = metadata.get(key)
            if value:
                lines.append(f"  {label}: {_truncate(str(value), 220)}")
    return lines


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        result.append(node)
    return result


def _format_context_pack(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Context Pack",
        f"Goal/query: {result.get('goal') or '(none)'}",
        f"Tenant: {result.get('tenant_id')}",
        f"Policy: {MEMORY_NON_AUTHORIZATION_BANNER}",
    ]
    if result.get("pathway"):
        lines.append(f"Pathway: {result['pathway']}")
    lines.append("")
    lines.append(_format_checkpoint_context(result.get("latest_checkpoint")))
    sections = [
        ("Active blockers", result.get("active_blockers", []), "No active blockers in this pack."),
        ("Recent decisions", result.get("recent_decisions", []), "No recent decisions in this pack."),
        ("Recent verifications", result.get("recent_verifications", []), "No recent verification memories in this pack."),
        ("Recent artifacts", result.get("recent_artifacts", []), "No recent artifact memories in this pack."),
        ("Accepted worker reports", result.get("worker_reports", []), "No accepted worker reports in this pack."),
        ("Dream-derived lessons and constraints", result.get("dream_lessons", []), "No dream-derived lessons or constraints in this pack."),
        ("Open questions", result.get("open_questions", []), "No open questions in this pack."),
        ("Relevant repo files", result.get("relevant_repo_files", []), "No relevant repo files matched."),
    ]
    for heading, nodes, empty in sections:
        lines.append("")
        lines.append(f"# {heading}")
        lines.extend(_format_node_list(nodes, empty=empty))
    if result.get("recommended_commands"):
        lines.append("")
        lines.append("# Recommended Commands")
        for command in result["recommended_commands"]:
            lines.append(f"- `{command}`")
    if result.get("context_manifest"):
        lines.append("")
        lines.append("# Context Manifest")
        lines.append(f"- {result['context_manifest'].get('manifest_path')}")
    return "\n".join(lines)


def _format_memory_audit(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Memory Audit",
        f"Status: {result.get('status')}",
        f"Checked memories: {result.get('checked_memories')}",
    ]
    for key, heading in [
        ("authority_inconsistencies", "Authority metadata inconsistencies"),
        ("stale_or_expired", "Stale or expired active memories"),
        ("supersession_inconsistencies", "Supersession inconsistencies"),
        ("open_questions", "Open questions"),
        ("open_blockers", "Open blockers"),
    ]:
        lines.append("")
        lines.append(f"# {heading}")
        lines.extend(_format_node_list(result.get(key, []), empty="None."))
    return "\n".join(lines)


def _format_memory_eval(result: dict[str, Any]) -> str:
    lines = ["# Agent Memory Eval", f"Status: {result.get('status')}"]
    for check in result.get("checks", []):
        marker = "PASS" if check.get("pass") else "FAIL"
        detail = f" - {check.get('detail')}" if check.get("detail") else ""
        lines.append(f"- {marker}: {check.get('name')}{detail}")
    return "\n".join(lines)


def _format_dream_review(result: dict[str, Any]) -> str:
    lines = [
        "# Dream Review Packet",
        f"Status: {result.get('status')}",
        f"Proposed dreams: {len(result.get('proposed_dreams', []))}",
        f"Accepted dreams: {len(result.get('accepted_dreams', []))}",
    ]
    for key, heading, empty in [
        ("proposed_dreams", "Proposed dreams needing review", "No proposed dreams."),
        ("accepted_dreams", "Accepted dream proposals", "No accepted dream proposals."),
        ("dream_lessons", "Accepted dream lessons and constraints", "No accepted dream lessons or constraints."),
        ("open_questions", "Open dream-origin questions", "No open dream-origin questions."),
    ]:
        lines.append("")
        lines.append(f"# {heading}")
        lines.extend(_format_node_list(result.get(key, []), empty=empty))
    if result.get("recommended_commands"):
        lines.append("")
        lines.append("# Recommended Commands")
        for command in result["recommended_commands"]:
            lines.append(f"- `{command}`")
    return "\n".join(lines)


def _format_dream_audit(result: dict[str, Any]) -> str:
    lines = ["# Automated Dreaming Audit Summary", f"Status: {result.get('status')}"]
    latest = result.get("latest_run")
    if latest:
        lines.extend(
            [
                f"Latest run: {latest.get('run_id')}",
                f"Policy: {latest.get('policy_version')}",
                f"Completed: {latest.get('completed_at')}",
                f"Generated proposals: {len(latest.get('generated_proposals', []))}",
                f"Processed sessions: {len(latest.get('processed_sessions', []))}",
                f"Accepted dreams: {len(latest.get('accepted', []))}",
                f"Rejected dreams: {len(latest.get('rejected', []))}",
                f"Skipped dreams: {len(latest.get('skipped', []))}",
            ]
        )
    else:
        lines.append("Latest run: none")
    dream_review = result.get("dream_review") or {}
    memory = result.get("memory_audit") or {}
    lines.extend(
        [
            "",
            "# Current Dream State",
            f"- Review status: {dream_review.get('status')}",
            f"- Proposed dreams: {dream_review.get('proposed_count')}",
            f"- Accepted dreams: {dream_review.get('accepted_count')}",
            f"- Dream-origin open questions: {dream_review.get('open_question_count')}",
            "",
            "# Memory Audit State",
            f"- Status: {memory.get('status')}",
            f"- Checked memories: {memory.get('checked_memories')}",
            f"- Authority issues: {memory.get('authority_issue_count')}",
            f"- Stale or expired: {memory.get('stale_or_expired_count')}",
            f"- Supersession issues: {memory.get('supersession_issue_count')}",
            f"- Open blockers: {memory.get('open_blocker_count')}",
            "",
            "# Recommended Commands",
        ]
    )
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _short_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            error_access_denied = 5
            process_query_limited_information = 0x1000
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return ctypes.get_last_error() == error_access_denied
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def _control_file_lock(
    lock_path: Path = DEFAULT_LOCK_PATH,
    *,
    timeout_seconds: float = 10.0,
    poll_seconds: float = 0.05,
    stale_seconds: float = DEFAULT_LOCK_STALE_SECONDS,
):
    _ensure_parent(lock_path)
    deadline = time.monotonic() + timeout_seconds
    handle: int | None = None
    while handle is None:
        try:
            handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, f"{os.getpid()} {utc_now()}\n".encode("utf-8"))
        except FileExistsError:
            stale = False
            try:
                lock_age = time.time() - lock_path.stat().st_mtime
                lock_text = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
                pid_text = lock_text.split(maxsplit=1)[0] if lock_text else ""
                if lock_age > stale_seconds:
                    stale = True
                elif pid_text.isdigit():
                    if not _process_exists(int(pid_text)):
                        stale = True
            except OSError:
                stale = True
            if stale:
                try:
                    lock_path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.monotonic() >= deadline:
                raise AgentControlError(f"agent control lock is held: {lock_path}")
            time.sleep(poll_seconds)
    try:
        yield
    finally:
        if handle is not None:
            os.close(handle)
            handle = None
        for attempt in range(5):
            try:
                lock_path.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)


def _schema_is_current(conn: sqlite3.Connection) -> bool:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if table_exists is None:
        return False
    return (
        conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (CONTROL_SCHEMA_VERSION,)).fetchone()
        is not None
    )


def connect(db_path: Path = DEFAULT_DB_PATH, *, maintenance: bool = False) -> sqlite3.Connection:
    _ensure_parent(db_path)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.create_function("agent_control_maintenance", 0, lambda: 1 if maintenance else 0)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    if not _schema_is_current(conn):
        init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TRIGGER IF EXISTS trg_agent_run_events_append_only_delete")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            pathway TEXT NOT NULL,
            status TEXT NOT NULL,
            permission_mode TEXT NOT NULL,
            owner TEXT,
            priority INTEGER NOT NULL DEFAULT 50,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS task_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            worker_id TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS task_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            worker_id TEXT NOT NULL,
            reported_at TEXT NOT NULL,
            report_json TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            sub_tenant_id TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            source_ref TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS graph_edges (
            id TEXT PRIMARY KEY,
            source_node_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            target_node_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            source_ref TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(source_node_id, relation, target_node_id)
        );

        CREATE TABLE IF NOT EXISTS evidence_artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            path TEXT NOT NULL,
            evidence_class TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS worker_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            worker_id TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL DEFAULT '',
            event_hash TEXT NOT NULL,
            delivered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            sub_tenant_id TEXT,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'agent',
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            payload_sha256 TEXT NOT NULL,
            prev_event_hash TEXT NOT NULL DEFAULT '',
            event_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS agent_run_ledger_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            anchor_type TEXT NOT NULL DEFAULT 'manual',
            row_count INTEGER NOT NULL,
            first_event_id INTEGER,
            last_event_id INTEGER,
            merkle_root TEXT NOT NULL,
            db_sha256 TEXT NOT NULL,
            events_jsonl_sha256 TEXT NOT NULL DEFAULT '',
            prev_anchor_hash TEXT NOT NULL DEFAULT '',
            anchor_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS retrieval_documents (
            doc_id TEXT PRIMARY KEY,
            source_node_id TEXT NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
            source_type TEXT NOT NULL,
            source_quality TEXT NOT NULL,
            authority_scope TEXT NOT NULL,
            capability_label TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            search_text TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            content_sha256 TEXT NOT NULL,
            freshness_status TEXT NOT NULL DEFAULT 'current',
            indexed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS startup_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            kind TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            pathway TEXT,
            status TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            manifest_path TEXT,
            gateboard_hash TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS strategy_hypotheses (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            title TEXT NOT NULL,
            thesis TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'research_only',
            priority_score REAL NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS experiment_runs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            hypothesis_id TEXT REFERENCES strategy_hypotheses(id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            artifact_ref TEXT,
            metric_json TEXT NOT NULL DEFAULT '{}',
            dataset_version_id TEXT,
            feature_snapshot_id TEXT,
            testing_debt_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS zero_candidate_episodes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            lane TEXT NOT NULL,
            selection_date TEXT NOT NULL,
            drop_stage_counts_json TEXT NOT NULL DEFAULT '{}',
            blocker_summary TEXT NOT NULL DEFAULT '',
            source_ref TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_pathway ON tasks(pathway, status);
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_scope ON graph_nodes(tenant_id, sub_tenant_id, kind);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id, relation);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id, relation);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_run ON agent_run_events(run_id, id);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_tenant_run ON agent_run_events(tenant_id, run_id, id);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_tenant_created ON agent_run_events(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_type ON agent_run_events(event_type, status);
        CREATE INDEX IF NOT EXISTS idx_agent_run_anchors_tenant_created ON agent_run_ledger_anchors(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_retrieval_documents_source ON retrieval_documents(source_node_id, source_type);
        CREATE INDEX IF NOT EXISTS idx_startup_runs_created ON startup_runs(created_at);
        CREATE INDEX IF NOT EXISTS idx_zero_candidate_lane_date ON zero_candidate_episodes(lane, selection_date);

        CREATE TRIGGER IF NOT EXISTS trg_agent_run_events_append_only_update
        BEFORE UPDATE ON agent_run_events
        WHEN agent_control_maintenance() = 0
        BEGIN
            SELECT RAISE(ABORT, 'agent_run_events is append-only; use a maintenance connection for audit tests');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_agent_run_events_append_only_delete
        BEFORE DELETE ON agent_run_events
        BEGIN
            SELECT RAISE(ABORT, 'agent_run_events is append-only; deletes are not allowed');
        END;

        DROP TABLE IF EXISTS messages;
        DROP TABLE IF EXISTS blockers;
        DROP TABLE IF EXISTS dataset_versions;
        DROP TABLE IF EXISTS feature_snapshots;
        DROP TABLE IF EXISTS drift_reports;
        DROP TABLE IF EXISTS provenance_edges;
        """
    )
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_documents_fts USING fts5(doc_id UNINDEXED, title, search_text)"
        )
    except sqlite3.OperationalError:
        pass
    zero_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(zero_candidate_episodes)").fetchall()
    }
    if "tenant_id" not in zero_columns:
        conn.execute(
            "ALTER TABLE zero_candidate_episodes ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'"
        )
    hypothesis_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(strategy_hypotheses)").fetchall()
    }
    if "tenant_id" not in hypothesis_columns:
        conn.execute(
            "ALTER TABLE strategy_hypotheses ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'"
        )
    startup_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(startup_runs)").fetchall()
    }
    if "tenant_id" not in startup_columns:
        conn.execute(
            "ALTER TABLE startup_runs ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'"
        )
    experiment_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(experiment_runs)").fetchall()
    }
    if "tenant_id" not in experiment_columns:
        conn.execute(
            "ALTER TABLE experiment_runs ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'"
        )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at, description)
        VALUES (?, ?, ?)
        """,
        (
            CONTROL_SCHEMA_VERSION,
            utc_now(),
            "agent-control schema with retrieval freshness and pruned dead auxiliary tables",
        ),
    )
    conn.commit()


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("metadata_json", "report_json", "payload_json"):
        if key in result:
            result[key.removesuffix("_json")] = json.loads(result.pop(key) or "{}")
    return result


def _append_jsonl(events_path: Path, event: dict[str, Any]) -> None:
    _ensure_parent(events_path)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(event) + "\n")


def _record_event(
    conn: sqlite3.Connection,
    *,
    events_path: Path,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    event = {"event_type": event_type, "created_at": utc_now(), "payload": payload}
    cursor = conn.execute(
        "INSERT INTO event_log(created_at, event_type, payload_json) VALUES (?, ?, ?)",
        (event["created_at"], event_type, canonical_json(payload)),
    )
    previous = conn.execute(
        "SELECT event_hash FROM event_outbox ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = previous["event_hash"] if previous is not None else ""
    outbox_payload = {
        "event_log_id": cursor.lastrowid,
        "event_type": event_type,
        "created_at": event["created_at"],
        "payload": payload,
    }
    hash_input = f"{prev_hash}\n{canonical_json(outbox_payload)}"
    event_hash = _text_sha256(hash_input)
    outbox_cursor = conn.execute(
        """
        INSERT INTO event_outbox(created_at, event_type, payload_json, prev_hash, event_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event["created_at"], event_type, canonical_json(outbox_payload), prev_hash, event_hash),
    )
    event["outbox_event_id"] = outbox_cursor.lastrowid
    event["outbox_hash"] = event_hash
    _append_jsonl(events_path, event)
    return event


def validate_event_outbox(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT id, created_at, event_type, payload_json, prev_hash, event_hash FROM event_outbox ORDER BY id ASC"
    ).fetchall()
    issues: list[dict[str, Any]] = []
    previous_hash = ""
    for row in rows:
        payload_json = row["payload_json"] or "{}"
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            issues.append({"id": row["id"], "issue": "payload_json is not valid JSON"})
            payload = {}
        if row["prev_hash"] != previous_hash:
            issues.append({"id": row["id"], "issue": "prev_hash does not match previous event_hash"})
        expected_hash = _text_sha256(f"{row['prev_hash']}\n{canonical_json(payload)}")
        if row["event_hash"] != expected_hash:
            issues.append({"id": row["id"], "issue": "event_hash does not match payload"})
        previous_hash = row["event_hash"] or ""
    return {
        "status": "pass" if not issues else "issues",
        "count": len(rows),
        "issues": issues,
    }


def _redact_agent_run_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, child in value.items():
            if AGENT_RUN_SENSITIVE_KEY_RE.search(str(key)):
                redacted[key] = AGENT_RUN_REDACTED
            else:
                redacted[key] = _redact_agent_run_payload(child)
        return redacted
    if isinstance(value, list):
        return [_redact_agent_run_payload(item) for item in value]
    if isinstance(value, str):
        redacted = re.sub(
            r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s,;]+",
            rf"\1{AGENT_RUN_REDACTED}",
            value,
        )
        redacted = re.sub(
            r"(?i)\b((?:api[_-]?key|openai_api_key|token|password|secret)\s*[=:]\s*)[^\s,;]+",
            rf"\1{AGENT_RUN_REDACTED}",
            redacted,
        )
        redacted = re.sub(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
            AGENT_RUN_REDACTED,
            redacted,
            flags=re.DOTALL,
        )
        redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", AGENT_RUN_REDACTED, redacted)
        redacted = re.sub(r"\bsk-ant-[A-Za-z0-9_-]{8,}\b", AGENT_RUN_REDACTED, redacted)
        redacted = re.sub(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", AGENT_RUN_REDACTED, redacted)
        redacted = re.sub(r"\bgh[opsru]_[A-Za-z0-9_]{20,}\b", AGENT_RUN_REDACTED, redacted)
        redacted = re.sub(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", AGENT_RUN_REDACTED, redacted)
        redacted = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", AGENT_RUN_REDACTED, redacted)
        return redacted
    return value


def _redact_agent_run_text(value: str) -> str:
    return str(_redact_agent_run_payload(value))


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _agent_run_event_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    payload_json = item.pop("payload_json") or "{}"
    try:
        item["payload"] = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        item["payload"] = {}
        item["payload_parse_error"] = str(exc)
    return item


def _reduce_agent_run_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {}
    first = events[0]
    last = events[-1]
    terminal = next((event for event in reversed(events) if event["event_type"] in AGENT_RUN_TERMINAL_EVENT_TYPES), None)
    status = terminal["status"] if terminal is not None else last["status"]
    blockers: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    tool_calls = 0
    memory_reads = 0
    memory_writes = 0
    for event in events:
        payload = event.get("payload") or {}
        if event["event_type"] in {"blocked", "failed"}:
            blockers.append(
                {
                    "event_id": event["id"],
                    "created_at": event["created_at"],
                    "code": payload.get("blocker_code") or payload.get("reason_code") or payload.get("error_code"),
                    "summary": event.get("summary") or payload.get("summary") or payload.get("error") or "",
                }
            )
        elif event["event_type"] in {"approval_requested", "approval_recorded"}:
            approvals.append(
                {
                    "event_id": event["id"],
                    "created_at": event["created_at"],
                    "type": event["event_type"],
                    "summary": event.get("summary") or payload.get("summary") or "",
                    "decision": payload.get("decision"),
                }
            )
        elif event["event_type"] == "artifact":
            artifacts.append(
                {
                    "event_id": event["id"],
                    "created_at": event["created_at"],
                    "path": payload.get("path") or payload.get("artifact"),
                    "sha256": payload.get("sha256"),
                    "summary": event.get("summary") or "",
                }
            )
        elif event["event_type"] == "tool_call":
            tool_calls += 1
        elif event["event_type"] == "memory_read":
            memory_reads += 1
        elif event["event_type"] == "memory_write":
            memory_writes += 1
    return {
        "run_id": first["run_id"],
        "tenant_id": first["tenant_id"],
        "sub_tenant_id": first.get("sub_tenant_id"),
        "actor": first.get("actor"),
        "title": first.get("title") or last.get("title") or "",
        "status": status,
        "started_at": first["created_at"],
        "updated_at": last["created_at"],
        "event_count": len(events),
        "tool_call_count": tool_calls,
        "memory_read_count": memory_reads,
        "memory_write_count": memory_writes,
        "approval_count": len(approvals),
        "blocker_count": len(blockers),
        "artifact_count": len(artifacts),
        "latest_summary": last.get("summary") or "",
        "blockers": blockers,
        "approvals": approvals,
        "artifacts": artifacts,
    }


def record_agent_run_event(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    run_id: str | None = None,
    event_type: str,
    title: str = "",
    summary: str = "",
    status: str | None = None,
    actor: str = "agent",
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in AGENT_RUN_EVENT_TYPES:
        raise AgentControlError(f"unsupported agent run event type: {event_type}")
    run_status = status or AGENT_RUN_EVENT_STATUS[event_type]
    if run_status not in AGENT_RUN_STATUSES:
        raise AgentControlError(f"unsupported agent run status: {run_status}")
    now = utc_now()
    safe_payload = _redact_agent_run_payload(payload or {})
    safe_title = _redact_agent_run_text(title)
    safe_summary = _redact_agent_run_text(summary)
    payload_sha256 = _text_sha256(canonical_json(safe_payload))
    run_id = run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    with _control_file_lock():
        with closing(connect(db_path)) as conn:
            with conn:
                previous = conn.execute(
                    """
                    SELECT event_hash
                    FROM agent_run_events
                    WHERE tenant_id = ? AND run_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (tenant_id, run_id),
                ).fetchone()
                prev_hash = previous["event_hash"] if previous is not None else ""
                hash_payload = {
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "sub_tenant_id": sub_tenant_id,
                    "created_at": now,
                    "actor": actor,
                    "event_type": event_type,
                    "status": run_status,
                    "title": safe_title,
                    "summary": safe_summary,
                    "payload": safe_payload,
                    "payload_sha256": payload_sha256,
                }
                event_hash = _text_sha256(f"{prev_hash}\n{canonical_json(hash_payload)}")
                cursor = conn.execute(
                    """
                    INSERT INTO agent_run_events(
                        run_id, tenant_id, sub_tenant_id, created_at, actor, event_type, status,
                        title, summary, payload_json, payload_sha256, prev_event_hash, event_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        tenant_id,
                        sub_tenant_id,
                        now,
                        actor,
                        event_type,
                        run_status,
                        safe_title,
                        safe_summary,
                        canonical_json(safe_payload),
                        payload_sha256,
                        prev_hash,
                        event_hash,
                    ),
                )
                event_id = cursor.lastrowid
                _record_event(
                    conn,
                    events_path=events_path,
                    event_type=f"agent_run.{event_type}",
                    payload={
                        "run_id": run_id,
                        "agent_run_event_id": event_id,
                        "status": run_status,
                        "title": safe_title,
                        "summary": safe_summary,
                        "ledger_version": AGENT_RUN_LEDGER_VERSION,
                        "non_authoritative": True,
                        "does_not_authorize_trading_or_evidence_mutation": True,
                    },
                )
    return {
        "id": event_id,
        "run_id": run_id,
        "created_at": now,
        "event_type": event_type,
        "status": run_status,
        "title": safe_title,
        "summary": safe_summary,
        "payload": safe_payload,
        "payload_sha256": payload_sha256,
        "prev_event_hash": prev_hash,
        "event_hash": event_hash,
        "ledger_version": AGENT_RUN_LEDGER_VERSION,
    }


def list_agent_runs(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        run_rows = conn.execute(
            """
            SELECT run_id, max(id) AS latest_id
            FROM agent_run_events
            WHERE tenant_id = ?
            GROUP BY run_id
            ORDER BY latest_id DESC
            """,
            (tenant_id,),
        ).fetchall()
        candidate_run_ids = [row["run_id"] for row in run_rows]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for run_id in candidate_run_ids:
            events = conn.execute(
                """
                SELECT *
                FROM agent_run_events
                WHERE tenant_id = ? AND run_id = ?
                ORDER BY id ASC
                """,
                (tenant_id, run_id),
            ).fetchall()
            grouped[run_id] = [_agent_run_event_row(row) for row in events]
    runs = [_reduce_agent_run_events(events) for events in grouped.values()]
    runs = [run for run in runs if run]
    runs.sort(key=lambda run: run["updated_at"], reverse=True)
    if status:
        runs = [run for run in runs if run["status"] == status]
    return {
        "status": "ready",
        "ledger_version": AGENT_RUN_LEDGER_VERSION,
        "runs": runs[:limit],
    }


def get_agent_run(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    run_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agent_run_events
            WHERE tenant_id = ? AND run_id = ?
            ORDER BY id ASC
            """,
            (tenant_id, run_id),
        ).fetchall()
    events = [_agent_run_event_row(row) for row in rows]
    return {
        "status": "ready" if events else "missing",
        "ledger_version": AGENT_RUN_LEDGER_VERSION,
        "run": _reduce_agent_run_events(events) if events else None,
        "events": events,
    }


def validate_agent_run_ledger(conn: sqlite3.Connection, *, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_events
        WHERE tenant_id = ?
        ORDER BY run_id ASC, id ASC
        """,
        (tenant_id,),
    ).fetchall()
    issues: list[dict[str, Any]] = []
    previous_by_run: dict[str, str] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            issues.append({"id": row["id"], "run_id": row["run_id"], "issue": "payload_json is not valid JSON"})
            payload = {}
        expected_prev = previous_by_run.get(row["run_id"], "")
        if row["prev_event_hash"] != expected_prev:
            issues.append({"id": row["id"], "run_id": row["run_id"], "issue": "prev_event_hash mismatch"})
        payload_sha = _text_sha256(canonical_json(payload))
        if row["payload_sha256"] != payload_sha:
            issues.append({"id": row["id"], "run_id": row["run_id"], "issue": "payload_sha256 mismatch"})
        hash_payload = {
            "run_id": row["run_id"],
            "tenant_id": row["tenant_id"],
            "sub_tenant_id": row["sub_tenant_id"],
            "created_at": row["created_at"],
            "actor": row["actor"],
            "event_type": row["event_type"],
            "status": row["status"],
            "title": row["title"],
            "summary": row["summary"],
            "payload": payload,
            "payload_sha256": row["payload_sha256"],
        }
        expected_hash = _text_sha256(f"{row['prev_event_hash']}\n{canonical_json(hash_payload)}")
        if row["event_hash"] != expected_hash:
            issues.append({"id": row["id"], "run_id": row["run_id"], "issue": "event_hash mismatch"})
        previous_by_run[row["run_id"]] = row["event_hash"]
    return {"status": "pass" if not issues else "issues", "count": len(rows), "issues": issues}


def _merkle_root(leaf_hashes: list[str]) -> str:
    if not leaf_hashes:
        return _text_sha256("[]")
    level = leaf_hashes[:]
    while len(level) > 1:
        next_level: list[str] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(_text_sha256(f"{left}\n{right}"))
        level = next_level
    return level[0]


def _agent_run_ledger_snapshot(
    conn: sqlite3.Connection,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    events_path: Path = DEFAULT_EVENTS_PATH,
    max_event_id: int | None = None,
) -> dict[str, Any]:
    if max_event_id is None:
        rows = conn.execute(
            "SELECT * FROM agent_run_events WHERE tenant_id = ? ORDER BY id ASC",
            (tenant_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_run_events WHERE tenant_id = ? AND id <= ? ORDER BY id ASC",
            (tenant_id, max_event_id),
        ).fetchall()
    row_payloads = [dict(row) for row in rows]
    leaf_hashes = [_text_sha256(canonical_json(row)) for row in row_payloads]
    return {
        "tenant_id": tenant_id,
        "row_count": len(row_payloads),
        "first_event_id": row_payloads[0]["id"] if row_payloads else None,
        "last_event_id": row_payloads[-1]["id"] if row_payloads else None,
        "merkle_root": _merkle_root(leaf_hashes),
        "db_sha256": _text_sha256(canonical_json(row_payloads)),
        "events_jsonl_sha256": _file_sha256(events_path) if events_path.exists() else "",
    }


def _record_agent_run_ledger_anchor_unlocked(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    anchor_type: str = "manual",
) -> dict[str, Any]:
    created_at = utc_now()
    with closing(connect(db_path)) as conn:
        with conn:
            snapshot = _agent_run_ledger_snapshot(conn, tenant_id=tenant_id, events_path=events_path)
            previous = conn.execute(
                """
                SELECT anchor_hash
                FROM agent_run_ledger_anchors
                WHERE tenant_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (tenant_id,),
            ).fetchone()
            prev_anchor_hash = previous["anchor_hash"] if previous is not None else ""
            anchor_payload = {
                "created_at": created_at,
                "tenant_id": tenant_id,
                "anchor_type": anchor_type,
                **snapshot,
                "prev_anchor_hash": prev_anchor_hash,
            }
            anchor_hash = _text_sha256(f"{prev_anchor_hash}\n{canonical_json(anchor_payload)}")
            cursor = conn.execute(
                """
                INSERT INTO agent_run_ledger_anchors(
                    created_at, tenant_id, anchor_type, row_count, first_event_id, last_event_id,
                    merkle_root, db_sha256, events_jsonl_sha256, prev_anchor_hash, anchor_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    tenant_id,
                    anchor_type,
                    snapshot["row_count"],
                    snapshot["first_event_id"],
                    snapshot["last_event_id"],
                    snapshot["merkle_root"],
                    snapshot["db_sha256"],
                    snapshot["events_jsonl_sha256"],
                    prev_anchor_hash,
                    anchor_hash,
                ),
            )
            anchor = {
                "id": cursor.lastrowid,
                **anchor_payload,
                "anchor_hash": anchor_hash,
            }
    _append_jsonl(anchors_path, anchor)
    return anchor


def record_agent_run_ledger_anchor(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    anchor_type: str = "manual",
) -> dict[str, Any]:
    with _control_file_lock():
        return _record_agent_run_ledger_anchor_unlocked(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            tenant_id=tenant_id,
            anchor_type=anchor_type,
        )


def validate_agent_run_ledger_anchors(
    conn: sqlite3.Connection,
    *,
    events_path: Path = DEFAULT_EVENTS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT *
        FROM agent_run_ledger_anchors
        WHERE tenant_id = ?
        ORDER BY id ASC
        """,
        (tenant_id,),
    ).fetchall()
    issues: list[dict[str, Any]] = []
    previous_hash = ""
    for row in rows:
        anchor_payload = {
            "created_at": row["created_at"],
            "tenant_id": row["tenant_id"],
            "anchor_type": row["anchor_type"],
            "row_count": row["row_count"],
            "first_event_id": row["first_event_id"],
            "last_event_id": row["last_event_id"],
            "merkle_root": row["merkle_root"],
            "db_sha256": row["db_sha256"],
            "events_jsonl_sha256": row["events_jsonl_sha256"],
            "prev_anchor_hash": row["prev_anchor_hash"],
        }
        if row["prev_anchor_hash"] != previous_hash:
            issues.append({"id": row["id"], "issue": "prev_anchor_hash mismatch"})
        expected_hash = _text_sha256(f"{row['prev_anchor_hash']}\n{canonical_json(anchor_payload)}")
        if row["anchor_hash"] != expected_hash:
            issues.append({"id": row["id"], "issue": "anchor_hash mismatch"})
        if row["last_event_id"] is None:
            snapshot = {
                "tenant_id": tenant_id,
                "row_count": 0,
                "first_event_id": None,
                "last_event_id": None,
                "merkle_root": _merkle_root([]),
                "db_sha256": _text_sha256(canonical_json([])),
                "events_jsonl_sha256": row["events_jsonl_sha256"],
            }
        else:
            snapshot = _agent_run_ledger_snapshot(
                conn,
                tenant_id=tenant_id,
                events_path=events_path,
                max_event_id=row["last_event_id"],
            )
        for key in ("row_count", "first_event_id", "last_event_id", "merkle_root", "db_sha256"):
            if row[key] != snapshot[key]:
                issues.append({"id": row["id"], "issue": f"anchored ledger {key} mismatch"})
        previous_hash = row["anchor_hash"] or ""
    current_snapshot = _agent_run_ledger_snapshot(conn, tenant_id=tenant_id, events_path=events_path)
    latest = rows[-1] if rows else None
    freshness = "missing"
    if latest is not None:
        freshness = "current"
        for key in ("row_count", "first_event_id", "last_event_id", "merkle_root", "db_sha256"):
            if latest[key] != current_snapshot[key]:
                freshness = "stale"
                break
        if latest["row_count"] > current_snapshot["row_count"]:
            issues.append({"id": latest["id"], "issue": "current ledger has fewer rows than latest anchor"})
    return {
        "status": "pass" if rows and not issues else ("missing" if not rows else "issues"),
        "freshness": freshness,
        "count": len(rows),
        "issues": issues,
        "latest_anchor_hash": latest["anchor_hash"] if latest is not None else "",
        "current_snapshot": current_snapshot,
    }


def agent_run_ledger_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    runs = list_agent_runs(db_path=db_path, tenant_id=tenant_id, status=status, limit=limit)
    with closing(connect(db_path)) as conn:
        audit = validate_agent_run_ledger(conn, tenant_id=tenant_id)
    return {
        **runs,
        "audit": audit,
        "status": "pass" if audit["status"] == "pass" else "issues",
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
    }


def _format_agent_run_ledger(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Run Ledger",
        f"Status: {result.get('status')}",
        f"Version: {result.get('ledger_version')}",
        f"Policy: {result.get('policy_banner') or MEMORY_NON_AUTHORIZATION_BANNER}",
        f"Audit: {(result.get('audit') or {}).get('status', 'not_run')}",
        "",
        "# Runs",
    ]
    for run in result.get("runs", []):
        lines.append(
            f"- {run['run_id']} status={run['status']} events={run['event_count']} "
            f"updated={run['updated_at']} title={run.get('title') or '(untitled)'}"
        )
        if run.get("latest_summary"):
            lines.append(f"  summary: {_truncate(run['latest_summary'], 180)}")
        if run.get("blockers"):
            blocker = run["blockers"][-1]
            lines.append(
                f"  blocker: {blocker.get('code') or 'unspecified'} - "
                f"{_truncate(blocker.get('summary') or '', 160)}"
            )
        if run.get("approvals"):
            lines.append(f"  approvals: {len(run['approvals'])} (ledger notes only; not authorization)")
    if not result.get("runs"):
        lines.append("- No runs recorded.")
    lines.extend(
        [
            "",
            "# Recommended Commands",
            "- `npm run memory:run-ledger`",
            "- `npm run agent:control -- run event --event-type started --title \"...\" --summary \"...\" --prompt-only`",
        ]
    )
    return "\n".join(lines)


def agent_run_anchor_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    write_anchor: bool = False,
    anchor_type: str = "manual",
) -> dict[str, Any]:
    anchor = None
    if write_anchor:
        anchor = record_agent_run_ledger_anchor(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            tenant_id=tenant_id,
            anchor_type=anchor_type,
        )
    with closing(connect(db_path)) as conn:
        validation = validate_agent_run_ledger_anchors(conn, events_path=events_path, tenant_id=tenant_id)
    status = validation["status"]
    if validation["status"] == "pass" and validation["freshness"] != "current":
        status = validation["freshness"]
    return {
        "status": status,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "anchor_written": anchor,
        "anchor_validation": validation,
        "recommended_commands": [
            "npm run memory:anchor-ledger -- --write-anchor",
            "npm run memory:run-ledger",
            "npm run memory:agent-eval",
        ],
    }


def _format_agent_run_anchor_report(result: dict[str, Any]) -> str:
    validation = result.get("anchor_validation") or {}
    lines = [
        "# Agent Run Ledger Anchor",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        f"Anchors: {validation.get('count')} freshness={validation.get('freshness')}",
        f"Latest anchor: {validation.get('latest_anchor_hash') or '(none)'}",
    ]
    if result.get("anchor_written"):
        anchor = result["anchor_written"]
        lines.append(f"Written: id={anchor.get('id')} rows={anchor.get('row_count')} hash={anchor.get('anchor_hash')}")
    lines.append("")
    lines.append("# Issues")
    if not validation.get("issues"):
        lines.append("- None.")
    for issue in validation.get("issues", []):
        lines.append(f"- anchor={issue.get('id')} {issue.get('issue')}")
    snapshot = validation.get("current_snapshot") or {}
    lines.extend(
        [
            "",
            "# Current Snapshot",
            f"- rows: {snapshot.get('row_count')}",
            f"- first_event_id: {snapshot.get('first_event_id')}",
            f"- last_event_id: {snapshot.get('last_event_id')}",
            f"- merkle_root: {snapshot.get('merkle_root')}",
            "",
            "# Recommended Commands",
        ]
    )
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _copy_if_exists(source: Path, target: Path) -> dict[str, Any]:
    if not source.exists():
        return {"source": str(source), "path": str(target), "exists": False, "sha256": ""}
    _ensure_parent(target)
    shutil.copy2(source, target)
    return {"source": str(source), "path": str(target), "exists": True, "sha256": _file_sha256(target)}


def create_memory_backup(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    sessions_path: Path = DEFAULT_SESSIONS_PATH,
    backup_root: Path = DEFAULT_BACKUPS_DIR,
    tenant_id: str = DEFAULT_TENANT_ID,
    write_anchor: bool = True,
) -> dict[str, Any]:
    backup_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    backup_dir = backup_root / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    with _control_file_lock():
        anchor = None
        if write_anchor:
            anchor = _record_agent_run_ledger_anchor_unlocked(
                db_path=db_path,
                events_path=events_path,
                anchors_path=anchors_path,
                tenant_id=tenant_id,
                anchor_type="backup",
            )
        backup_db = backup_dir / "agent_control.db"
        with closing(connect(db_path)) as source, closing(sqlite3.connect(backup_db)) as target:
            source.backup(target)
        files = {
            "db": {"source": str(db_path), "path": str(backup_db), "exists": True, "sha256": _file_sha256(backup_db)},
            "events": _copy_if_exists(events_path, backup_dir / "events.jsonl"),
            "anchors": _copy_if_exists(anchors_path, backup_dir / "anchors.jsonl"),
            "sessions": _copy_if_exists(sessions_path, backup_dir / "sessions.jsonl"),
        }
    manifest_payload = {
        "backup_id": backup_id,
        "created_at": utc_now(),
        "tenant_id": tenant_id,
        "schema_version": CONTROL_SCHEMA_VERSION,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "anchor": anchor,
        "files": files,
    }
    manifest_hash = _text_sha256(canonical_json(manifest_payload))
    manifest = {**manifest_payload, "manifest_sha256": manifest_hash}
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(canonical_json(manifest), encoding="utf-8")
    return {
        "status": "pass",
        "backup_id": backup_id,
        "backup_dir": str(backup_dir),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_hash,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "anchor": anchor,
        "files": files,
    }


def _validate_backup_jsonl_sidecars(
    conn: sqlite3.Connection,
    *,
    events_path: Path,
    anchors_path: Path,
    sessions_path: Path,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> list[str]:
    issues: list[str] = []
    anchor_rows = conn.execute(
        """
        SELECT *
        FROM agent_run_ledger_anchors
        WHERE tenant_id = ?
        ORDER BY id ASC
        """,
        (tenant_id,),
    ).fetchall()
    if anchor_rows:
        if not anchors_path.exists():
            issues.append("anchors.jsonl sidecar is missing")
        else:
            try:
                anchor_sidecar_rows = _read_jsonl(anchors_path)
            except AgentControlError as exc:
                issues.append(str(exc))
                anchor_sidecar_rows = []
            db_anchor_hashes = [row["anchor_hash"] for row in anchor_rows]
            sidecar_hashes = [str(row.get("anchor_hash") or "") for row in anchor_sidecar_rows]
            if sidecar_hashes != db_anchor_hashes:
                issues.append("anchors.jsonl does not match database anchor history")
        latest_anchor = anchor_rows[-1]
        if latest_anchor["events_jsonl_sha256"]:
            if not events_path.exists():
                issues.append("events.jsonl sidecar is missing")
            elif latest_anchor["events_jsonl_sha256"] != _file_sha256(events_path):
                issues.append("events.jsonl sha256 does not match latest ledger anchor")
    if sessions_path.exists():
        try:
            session_rows = _read_jsonl(sessions_path)
        except AgentControlError as exc:
            issues.append(str(exc))
            session_rows = []
        required_keys = {"session_id", "logged_at", "path", "source_sha256"}
        for index, row in enumerate(session_rows, start=1):
            if not required_keys.issubset(row):
                issues.append(f"sessions.jsonl line {index} missing required session fields")
    return issues


def restore_check_memory_backup(
    *,
    backup_dir: Path,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    manifest_path = backup_dir / "manifest.json"
    issues: list[str] = []
    if not manifest_path.exists():
        return {
            "status": "fail",
            "backup_dir": str(backup_dir),
            "issues": ["manifest.json is missing"],
            "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "fail",
            "backup_dir": str(backup_dir),
            "issues": [f"manifest.json is invalid JSON: {exc}"],
            "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        }
    expected_manifest_hash = manifest.get("manifest_sha256")
    manifest_without_hash = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    actual_manifest_hash = _text_sha256(canonical_json(manifest_without_hash))
    if expected_manifest_hash != actual_manifest_hash:
        issues.append("manifest_sha256 mismatch")
    files = manifest.get("files") or {}
    for label, info in files.items():
        if not isinstance(info, dict) or not info.get("exists"):
            continue
        path = Path(str(info.get("path") or ""))
        if not path.exists():
            issues.append(f"{label} backup file is missing")
            continue
        if info.get("sha256") != _file_sha256(path):
            issues.append(f"{label} sha256 mismatch")
    backup_db = Path(str((files.get("db") or {}).get("path") or (backup_dir / "agent_control.db")))
    backup_events = Path(str((files.get("events") or {}).get("path") or (backup_dir / "events.jsonl")))
    backup_anchors = Path(str((files.get("anchors") or {}).get("path") or (backup_dir / "anchors.jsonl")))
    if not backup_db.exists():
        issues.append("agent_control.db backup is missing")
        return {
            "status": "fail",
            "backup_dir": str(backup_dir),
            "issues": issues,
            "manifest_sha256": actual_manifest_hash,
            "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        }
    with closing(sqlite3.connect(backup_db)) as conn:
        conn.row_factory = sqlite3.Row
        conn.create_function("agent_control_maintenance", 0, lambda: 0)
        ledger = validate_agent_run_ledger(conn, tenant_id=tenant_id)
        outbox = validate_event_outbox(conn)
        anchors = validate_agent_run_ledger_anchors(conn, events_path=backup_events, tenant_id=tenant_id)
        sidecar_issues = _validate_backup_jsonl_sidecars(
            conn,
            events_path=backup_events,
            anchors_path=backup_anchors,
            sessions_path=Path(str((files.get("sessions") or {}).get("path") or (backup_dir / "sessions.jsonl"))),
            tenant_id=tenant_id,
        )
        expected_schema_version = str(manifest.get("schema_version") or CONTROL_SCHEMA_VERSION)
        migration = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (expected_schema_version,),
        ).fetchone()
    if ledger["status"] != "pass":
        issues.append("agent run ledger audit failed")
    if outbox["status"] != "pass":
        issues.append("event outbox audit failed")
    if anchors["status"] != "pass":
        issues.append("agent run ledger anchor audit failed")
    issues.extend(sidecar_issues)
    if migration is None:
        issues.append(f"schema migration missing: {expected_schema_version}")
    return {
        "status": "pass" if not issues else "fail",
        "backup_dir": str(backup_dir),
        "issues": issues,
        "manifest_sha256": actual_manifest_hash,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ledger": ledger,
        "event_outbox": outbox,
        "anchors": anchors,
    }


def _format_memory_backup(result: dict[str, Any]) -> str:
    lines = [
        "# Memory Backup",
        f"Status: {result.get('status')}",
        f"Backup: {result.get('backup_dir')}",
        f"Manifest: {result.get('manifest_path')}",
        f"Manifest hash: {result.get('manifest_sha256')}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Files",
    ]
    for label, info in (result.get("files") or {}).items():
        lines.append(f"- {label}: exists={info.get('exists')} sha256={info.get('sha256')} path={info.get('path')}")
    return "\n".join(lines)


def _format_restore_check(result: dict[str, Any]) -> str:
    lines = [
        "# Memory Restore Check",
        f"Status: {result.get('status')}",
        f"Backup: {result.get('backup_dir')}",
        f"Manifest hash: {result.get('manifest_sha256') or ''}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Issues",
    ]
    if not result.get("issues"):
        lines.append("- None.")
    for issue in result.get("issues", []):
        lines.append(f"- {issue}")
    for key, title in [("ledger", "Agent Run Ledger"), ("event_outbox", "Event Outbox"), ("anchors", "Ledger Anchors")]:
        if key in result:
            value = result[key]
            lines.append("")
            lines.append(f"# {title}")
            lines.append(f"- status: {value.get('status')}")
            if "freshness" in value:
                lines.append(f"- freshness: {value.get('freshness')}")
            lines.append(f"- count: {value.get('count')}")
    return "\n".join(lines)


def _latest_backup_dir(backup_root: Path) -> Path | None:
    if not backup_root.exists():
        return None
    candidates = [path for path in backup_root.iterdir() if path.is_dir() and (path / "manifest.json").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path / "manifest.json").stat().st_mtime)


def memory_doctor(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    sessions_path: Path = DEFAULT_SESSIONS_PATH,
    backup_root: Path = DEFAULT_BACKUPS_DIR,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    write_backup: bool = False,
    max_backup_age_hours: int = 48,
) -> dict[str, Any]:
    backup = None
    if write_backup:
        backup = create_memory_backup(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            tenant_id=tenant_id,
        )
    latest_backup = _latest_backup_dir(backup_root)
    restore_check = None
    backup_age_hours = None
    if latest_backup is not None:
        restore_check = restore_check_memory_backup(backup_dir=latest_backup, tenant_id=tenant_id)
        backup_age_hours = (time.time() - (latest_backup / "manifest.json").stat().st_mtime) / 3600
    ledger = agent_run_ledger_report(db_path=db_path, tenant_id=tenant_id, limit=20)
    anchor_report = agent_run_anchor_report(db_path=db_path, events_path=events_path, anchors_path=anchors_path, tenant_id=tenant_id)
    audit = memory_audit(db_path=db_path, tenant_id=tenant_id)
    dashboard = operator_dashboard(db_path=db_path, runs_dir=runs_dir, tenant_id=tenant_id)
    eval_result = agent_eval_harness(db_path=db_path, events_path=events_path, repo_root=repo_root, tenant_id=tenant_id, seed=False)
    freshness = retrieval_freshness_report(db_path=db_path, tenant_id=tenant_id)
    with closing(connect(db_path)) as conn:
        outbox = validate_event_outbox(conn)
    checks = [
        {"name": "agent run ledger audit", "pass": ledger.get("status") == "pass", "detail": ledger.get("status")},
        {
            "name": "agent run ledger anchor current",
            "pass": anchor_report.get("status") == "pass",
            "detail": f"{anchor_report.get('status')} / {(anchor_report.get('anchor_validation') or {}).get('freshness')}",
        },
        {"name": "event outbox audit", "pass": outbox.get("status") == "pass", "detail": outbox.get("status")},
        {"name": "memory audit", "pass": audit.get("status") == "pass", "detail": audit.get("status")},
        {
            "name": "retrieval freshness",
            "pass": True,
            "detail": freshness.get("detail"),
        },
        {"name": "operator dashboard", "pass": dashboard.get("status") == "pass", "detail": dashboard.get("status")},
        {"name": "agent eval harness", "pass": eval_result.get("status") == "pass", "detail": eval_result.get("status")},
        {
            "name": "latest backup restore-check",
            "pass": restore_check is not None and restore_check.get("status") == "pass",
            "detail": restore_check.get("status") if restore_check else "missing",
        },
        {
            "name": "latest backup freshness",
            "pass": backup_age_hours is not None and backup_age_hours <= max_backup_age_hours,
            "detail": "" if backup_age_hours is None else f"{backup_age_hours:.2f}h",
        },
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "fail",
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "checks": checks,
        "backup": backup,
        "latest_backup_dir": str(latest_backup) if latest_backup is not None else "",
        "latest_backup_age_hours": backup_age_hours,
        "ledger": ledger,
        "anchors": anchor_report,
        "event_outbox": outbox,
        "memory_audit": audit,
        "retrieval_freshness": freshness,
        "operator_dashboard": dashboard,
        "agent_eval": eval_result,
        "restore_check": restore_check,
        "recommended_commands": [
            "npm run memory:doctor",
            "npm run memory:backup",
            "npm run memory:agent-eval",
            "npm run memory:run-ledger",
        ],
    }


def _format_memory_doctor(result: dict[str, Any]) -> str:
    lines = [
        "# Memory Doctor",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        f"Latest backup: {result.get('latest_backup_dir') or '(missing)'}",
        "",
        "# Checks",
    ]
    for check in result.get("checks", []):
        marker = "PASS" if check.get("pass") else "FAIL"
        detail = f" - {check.get('detail')}" if check.get("detail") else ""
        lines.append(f"- {marker}: {check.get('name')}{detail}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _memory_doctor_failed_checks(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not result:
        return []
    return [check for check in result.get("checks", []) if not check.get("pass")]


def archive_cross_project_memory(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    actor: str = "memory-maintenance",
) -> dict[str, Any]:
    result = {"status": "pass", "archived_count": 0, "archived_node_ids": [], "repaired_count": 0, "repaired_node_ids": []}
    with closing(connect(db_path, maintenance=True)) as conn, conn:
        repair_rows = conn.execute(
            """
            SELECT *
            FROM graph_nodes
            WHERE tenant_id = ?
              AND json_extract(metadata_json, '$.archive_reason') = 'cross_project_tenant_cleanup'
              AND (
                json_extract(metadata_json, '$.source_type') <> 'operating_memory'
                OR json_extract(metadata_json, '$.source_type') IS NULL
              )
            """,
            (tenant_id,),
        ).fetchall()
        for row in repair_rows:
            node = _row_dict(row)
            if node is None:
                continue
            metadata = {
                key: value
                for key, value in (node.get("metadata") or {}).items()
                if key not in {"archive_reason", "archive_note", "archived_at", "previous_tenant_id"}
            }
            if metadata.get("memory_status") == "archived":
                metadata.pop("memory_status", None)
            conn.execute(
                "UPDATE graph_nodes SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (canonical_json(metadata), utc_now(), node["id"]),
            )
            _upsert_retrieval_document(conn, {**node, "metadata": metadata, "metadata_json": canonical_json(metadata)})
            result["repaired_count"] += 1
            result["repaired_node_ids"].append(node["id"])
        rows = conn.execute(
            """
            SELECT *
            FROM graph_nodes
            WHERE tenant_id = ?
              AND json_extract(metadata_json, '$.source_type') = 'operating_memory'
              AND (
                lower(title) LIKE '%fashion shopping bot%'
                OR lower(title) LIKE '%fashion bot%'
                OR lower(body) LIKE '%fashion shopping bot%'
                OR lower(body) LIKE '%fashion bot%'
                OR lower(metadata_json) LIKE '%fashion shopping bot%'
                OR lower(metadata_json) LIKE '%fashion bot%'
              )
            """,
            (tenant_id,),
        ).fetchall()
        for row in rows:
            node = _row_dict(row)
            if node is None:
                continue
            metadata = node.get("metadata") or {}
            if metadata.get("memory_status") == "archived" and metadata.get("archive_reason") == "cross_project_tenant_cleanup":
                continue
            archived_metadata = {
                **metadata,
                "memory_status": "archived",
                "archived_at": utc_now(),
                "archive_reason": "cross_project_tenant_cleanup",
                "archive_note": "Archived because this Fashion bot memory does not belong to the options-chatbot tenant.",
                "previous_tenant_id": tenant_id,
            }
            conn.execute(
                "UPDATE graph_nodes SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (canonical_json(archived_metadata), utc_now(), node["id"]),
            )
            _upsert_retrieval_document(conn, {**node, "metadata": archived_metadata, "metadata_json": canonical_json(archived_metadata)})
            result["archived_count"] += 1
            result["archived_node_ids"].append(node["id"])
    if result["archived_count"] or result["repaired_count"]:
        record_agent_run_event(
            db_path=db_path,
            events_path=events_path,
            event_type="completed",
            title="Archived cross-project memory",
            summary=(
                f"Archived {result['archived_count']} Fashion bot memory nodes from the options-chatbot tenant; "
                f"repaired {result['repaired_count']} non-operating nodes."
            ),
            actor=actor,
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            payload={
                "authority_scope": OPERATING_AUTHORITY_SCOPE,
                    "non_authoritative": True,
                    "archived_node_ids": result["archived_node_ids"],
                    "repaired_node_ids": result["repaired_node_ids"],
                    "reason": "cross_project_tenant_cleanup",
                },
            )
    return result


def memory_maintenance(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    sessions_path: Path = DEFAULT_SESSIONS_PATH,
    backup_root: Path = DEFAULT_BACKUPS_DIR,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    actor: str = "memory-maintenance",
    max_backup_age_hours: int = 48,
) -> dict[str, Any]:
    started = record_agent_run_event(
        db_path=db_path,
        events_path=events_path,
        event_type="started",
        title="Memory maintenance",
        summary="Memory maintenance started.",
        actor=actor,
        tenant_id=tenant_id,
        sub_tenant_id="operator",
        payload={
            "authority_scope": OPERATING_AUTHORITY_SCOPE,
            "non_authoritative": True,
            "operations": ["backup", "ingest_living_history", "refresh_retrieval_freshness", "archive_cross_project_memory", "doctor", "anchor"],
        },
    )
    run_id = started["run_id"]
    backup = None
    living_history = None
    freshness = None
    tenant_archive = None
    doctor = None
    final_anchor = None
    error = ""
    try:
        backup = create_memory_backup(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            tenant_id=tenant_id,
        )
        living_history = ingest_living_history(
            db_path=db_path,
            repo_root=repo_root,
            tenant_id=tenant_id,
        )
        freshness = refresh_retrieval_freshness(
            db_path=db_path,
            repo_root=repo_root,
            tenant_id=tenant_id,
        )
        tenant_archive = archive_cross_project_memory(
            db_path=db_path,
            events_path=events_path,
            tenant_id=tenant_id,
            actor=actor,
        )
        doctor = memory_doctor(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
            tenant_id=tenant_id,
            write_backup=False,
            max_backup_age_hours=max_backup_age_hours,
        )
        event_type = "completed" if doctor.get("status") == "pass" else "failed"
        summary = "Memory maintenance completed." if event_type == "completed" else "Memory maintenance failed checks."
        record_agent_run_event(
            db_path=db_path,
            events_path=events_path,
            run_id=run_id,
            event_type=event_type,
            title="Memory maintenance",
            summary=summary,
            actor=actor,
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            payload={
                "authority_scope": OPERATING_AUTHORITY_SCOPE,
                "non_authoritative": True,
                "backup_id": backup.get("backup_id"),
                "backup_dir": backup.get("backup_dir"),
                "living_history_status": living_history.get("status"),
                "living_history_nodes_created": living_history.get("nodes_created"),
                "living_history_nodes_updated": living_history.get("nodes_updated"),
                "living_history_nodes_pruned": living_history.get("nodes_pruned"),
                "living_history_edges_created": living_history.get("edges_created"),
                "retrieval_freshness": freshness,
                "cross_project_archived_count": tenant_archive.get("archived_count"),
                "doctor_status": doctor.get("status"),
                "failed_checks": _memory_doctor_failed_checks(doctor),
            },
        )
    except Exception as exc:
        error = str(exc)
        record_agent_run_event(
            db_path=db_path,
            events_path=events_path,
            run_id=run_id,
            event_type="failed",
            title="Memory maintenance",
            summary="Memory maintenance raised an exception.",
            actor=actor,
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            payload={
                "authority_scope": OPERATING_AUTHORITY_SCOPE,
                "non_authoritative": True,
                "error": error,
            },
        )
    try:
        final_anchor = agent_run_anchor_report(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            tenant_id=tenant_id,
            write_anchor=True,
            anchor_type="maintenance",
        )
    except Exception as exc:
        if not error:
            error = str(exc)
    final_doctor = None
    if final_anchor is not None:
        try:
            final_doctor = memory_doctor(
                db_path=db_path,
                events_path=events_path,
                anchors_path=anchors_path,
                sessions_path=sessions_path,
                backup_root=backup_root,
                runs_dir=runs_dir,
                repo_root=repo_root,
                tenant_id=tenant_id,
                write_backup=False,
                max_backup_age_hours=max_backup_age_hours,
            )
        except Exception as exc:
            if not error:
                error = str(exc)
    status = "pass" if not error and final_doctor is not None and final_doctor.get("status") == "pass" else "fail"
    return {
        "status": status,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "run_id": run_id,
        "backup": backup,
        "living_history_ingest": living_history,
        "retrieval_freshness": freshness,
        "cross_project_archive": tenant_archive,
        "doctor": final_doctor or doctor,
        "anchor": final_anchor,
        "error": error,
        "recommended_commands": [
            "npm run memory:maintenance",
            "npm run memory:run-ledger",
            "npm run memory:doctor",
            "npm run memory:backup",
        ],
    }


def _format_memory_maintenance(result: dict[str, Any]) -> str:
    backup = result.get("backup") or {}
    living_history = result.get("living_history_ingest") or {}
    freshness = result.get("retrieval_freshness") or {}
    archive = result.get("cross_project_archive") or {}
    doctor = result.get("doctor") or {}
    anchor = result.get("anchor") or {}
    validation = anchor.get("anchor_validation") or {}
    lines = [
        "# Memory Maintenance",
        f"Status: {result.get('status')}",
        f"Run: {result.get('run_id')}",
        f"Policy: {result.get('policy_banner')}",
        f"Backup: {backup.get('backup_dir') or '(none)'}",
        "Living history ingest: "
        f"{living_history.get('status') or '(not run)'} "
        f"created={living_history.get('nodes_created', 0)} "
        f"updated={living_history.get('nodes_updated', 0)} "
        f"skipped={living_history.get('nodes_skipped', 0)} "
        f"pruned={living_history.get('nodes_pruned', 0)} "
        f"edges={living_history.get('edges_created', 0)}",
        "Retrieval freshness: "
        f"checked={freshness.get('checked', 0)} "
        f"updated={freshness.get('updated', 0)} "
        f"stale={freshness.get('stale', 0)} "
        f"missing={freshness.get('missing', 0)}",
        f"Cross-project archive: archived={archive.get('archived_count', 0)}",
        f"Doctor: {doctor.get('status') or '(not run)'}",
        f"Anchor: {anchor.get('status') or '(not written)'} freshness={validation.get('freshness') or ''}",
    ]
    if result.get("error"):
        lines.extend(["", "# Error", f"- {result.get('error')}"])
    lines.extend(["", "# Failed Checks"])
    failed_checks = _memory_doctor_failed_checks(doctor)
    if not failed_checks:
        lines.append("- None.")
    for check in failed_checks:
        detail = f" - {check.get('detail')}" if check.get("detail") else ""
        lines.append(f"- {check.get('name')}{detail}")
    lines.extend(["", "# Recommended Commands"])
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _latest_successful_memory_maintenance(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT run_id, created_at, actor, summary
            FROM agent_run_events
            WHERE tenant_id = ?
              AND title = 'Memory maintenance'
              AND event_type = 'completed'
              AND status = 'succeeded'
            ORDER BY id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
    return _row_dict(row)


def memory_auto_maintenance(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    anchors_path: Path = DEFAULT_ANCHORS_PATH,
    sessions_path: Path = DEFAULT_SESSIONS_PATH,
    backup_root: Path = DEFAULT_BACKUPS_DIR,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    actor: str = "memory-auto-maintenance",
    min_interval_hours: int = 6,
    max_success_age_hours: int = 24,
    max_backup_age_hours: int = 48,
    force: bool = False,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    latest_success = _latest_successful_memory_maintenance(db_path=db_path, tenant_id=tenant_id)
    latest_success_age_hours = None
    if latest_success:
        completed_at = _parse_utc_timestamp(latest_success.get("created_at"))
        if completed_at is not None:
            latest_success_age_hours = (now - completed_at).total_seconds() / 3600

    latest_backup = _latest_backup_dir(backup_root)
    latest_backup_age_hours = None
    if latest_backup is not None:
        latest_backup_age_hours = (time.time() - (latest_backup / "manifest.json").stat().st_mtime) / 3600

    anchor_report = agent_run_anchor_report(
        db_path=db_path,
        events_path=events_path,
        anchors_path=anchors_path,
        tenant_id=tenant_id,
    )
    doctor = memory_doctor(
        db_path=db_path,
        events_path=events_path,
        anchors_path=anchors_path,
        sessions_path=sessions_path,
        backup_root=backup_root,
        runs_dir=runs_dir,
        repo_root=repo_root,
        tenant_id=tenant_id,
        write_backup=False,
        max_backup_age_hours=max_backup_age_hours,
    )

    reasons: list[str] = []
    if force:
        reasons.append("forced")
    if latest_success is None:
        reasons.append("no successful memory maintenance run")
    elif latest_success_age_hours is not None and latest_success_age_hours > max_success_age_hours:
        reasons.append(f"latest successful memory maintenance is stale ({latest_success_age_hours:.2f}h)")
    if latest_backup is None:
        reasons.append("latest memory backup is missing")
    elif latest_backup_age_hours is not None and latest_backup_age_hours > max_backup_age_hours:
        reasons.append(f"latest memory backup is stale ({latest_backup_age_hours:.2f}h)")
    if anchor_report.get("status") != "pass":
        reasons.append(
            f"agent run ledger anchor is {anchor_report.get('status')} / "
            f"{(anchor_report.get('anchor_validation') or {}).get('freshness')}"
        )
    if doctor.get("status") != "pass":
        failed_names = [str(check.get("name")) for check in _memory_doctor_failed_checks(doctor)]
        reasons.append("memory doctor failed" + (f": {', '.join(failed_names)}" if failed_names else ""))

    if (
        reasons
        and not force
        and latest_success_age_hours is not None
        and latest_success_age_hours < min_interval_hours
        and doctor.get("status") == "pass"
        and anchor_report.get("status") == "pass"
    ):
        reasons = []

    maintenance = None
    action = "skipped"
    status = "pass"
    if reasons:
        action = "ran"
        maintenance = memory_maintenance(
            db_path=db_path,
            events_path=events_path,
            anchors_path=anchors_path,
            sessions_path=sessions_path,
            backup_root=backup_root,
            runs_dir=runs_dir,
            repo_root=repo_root,
            tenant_id=tenant_id,
            actor=actor,
            max_backup_age_hours=max_backup_age_hours,
        )
        status = "pass" if maintenance.get("status") == "pass" else "fail"
    return {
        "status": status,
        "action": action,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "reasons": reasons,
        "latest_success": latest_success,
        "latest_success_age_hours": latest_success_age_hours,
        "latest_backup_dir": str(latest_backup) if latest_backup is not None else "",
        "latest_backup_age_hours": latest_backup_age_hours,
        "anchor": anchor_report,
        "doctor": maintenance.get("doctor") if maintenance else doctor,
        "maintenance": maintenance,
        "recommended_commands": [
            "npm run memory:auto-maintenance",
            "npm run memory:maintenance",
            "npm run memory:doctor",
            "npm run memory:run-ledger",
        ],
    }


def _format_memory_auto_maintenance(result: dict[str, Any]) -> str:
    lines = [
        "# Memory Auto-Maintenance",
        f"Status: {result.get('status')}",
        f"Action: {result.get('action')}",
        f"Policy: {result.get('policy_banner')}",
        f"Latest success age: {_format_optional_hours(result.get('latest_success_age_hours'))}",
        f"Latest backup age: {_format_optional_hours(result.get('latest_backup_age_hours'))}",
        f"Latest backup: {result.get('latest_backup_dir') or '(missing)'}",
        f"Doctor: {(result.get('doctor') or {}).get('status') or '(not run)'}",
        f"Anchor: {(result.get('anchor') or {}).get('status') or '(not checked)'}",
        "",
        "# Reasons",
    ]
    if not result.get("reasons"):
        lines.append("- None; memory health is current.")
    for reason in result.get("reasons", []):
        lines.append(f"- {reason}")
    maintenance = result.get("maintenance") or {}
    if maintenance:
        lines.extend(["", "# Maintenance Run", f"- run_id: {maintenance.get('run_id')}", f"- status: {maintenance.get('status')}"])
    lines.extend(["", "# Recommended Commands"])
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _format_optional_hours(value: Any) -> str:
    if value is None:
        return "(missing)"
    try:
        return f"{float(value):.2f}h"
    except (TypeError, ValueError):
        return str(value)


def daily_operator_brief(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    tenant_id: str = DEFAULT_TENANT_ID,
    since_hours: int = 24,
    stale_hours: int = 6,
    limit: int = 20,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=since_hours)
    stale_cutoff = now - timedelta(hours=stale_hours)
    ledger = agent_run_ledger_report(db_path=db_path, tenant_id=tenant_id, limit=max(limit * 5, limit))
    dashboard = operator_dashboard(db_path=db_path, runs_dir=runs_dir, tenant_id=tenant_id, limit=min(max(limit, 4), 12))
    priorities = research_priority_report(db_path=db_path, tenant_id=tenant_id, limit=min(max(limit, 4), 12))

    recent_runs: list[dict[str, Any]] = []
    attention_runs: list[dict[str, Any]] = []
    stale_running_runs: list[dict[str, Any]] = []
    pending_approvals: list[dict[str, Any]] = []
    for run in ledger.get("runs", []):
        updated_at = _parse_utc_timestamp(run.get("updated_at"))
        if updated_at is not None and updated_at >= cutoff:
            recent_runs.append(run)
        if run.get("status") in {"failed", "blocked"}:
            attention_runs.append(run)
        if run.get("status") == "running" and updated_at is not None and updated_at < stale_cutoff:
            stale_running_runs.append(run)
        approval_events = run.get("approvals") or []
        requested = [event for event in approval_events if event.get("type") == "approval_requested"]
        latest_recorded_id = max(
            (int(event.get("event_id") or 0) for event in approval_events if event.get("type") == "approval_recorded"),
            default=0,
        )
        pending_requested = [
            event for event in requested if int(event.get("event_id") or 0) > latest_recorded_id
        ]
        if pending_requested:
            pending_approvals.append(
                {
                    "run_id": run["run_id"],
                    "summary": pending_requested[-1].get("summary") or run.get("latest_summary") or "",
                    "created_at": pending_requested[-1].get("created_at"),
                    "non_authoritative": True,
                }
            )

    brief_status = "needs_attention" if (
        ledger.get("status") != "pass"
        or dashboard.get("status") != "pass"
        or attention_runs
        or stale_running_runs
        or pending_approvals
    ) else "pass"
    return {
        "status": brief_status,
        "tenant_id": tenant_id,
        "generated_at": utc_now(),
        "since_hours": since_hours,
        "stale_hours": stale_hours,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ledger_status": ledger.get("status"),
        "ledger_audit": ledger.get("audit"),
        "dashboard_status": dashboard.get("status"),
        "dashboard_checks": dashboard.get("checks", []),
        "recent_runs": recent_runs[:limit],
        "attention_runs": attention_runs[:limit],
        "stale_running_runs": stale_running_runs[:limit],
        "pending_approvals": pending_approvals[:limit],
        "research_priorities": {
            "status": priorities.get("status"),
            "zero_candidate_priorities": priorities.get("zero_candidate_priorities", [])[: min(limit, 5)],
            "hypothesis_priorities": priorities.get("hypothesis_priorities", [])[: min(limit, 5)],
        },
        "recommended_commands": [
            "npm run memory:run-ledger",
            "npm run memory:operator-dashboard",
            "npm run memory:research-priorities",
            "npm run memory:daily-brief",
        ],
    }


def _format_daily_operator_brief(result: dict[str, Any]) -> str:
    lines = [
        "# Daily Operator Brief",
        f"Status: {result.get('status')}",
        f"Generated: {result.get('generated_at')}",
        f"Window: {result.get('since_hours')}h recent; stale running after {result.get('stale_hours')}h",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Health",
        f"- ledger: {result.get('ledger_status')} audit={(result.get('ledger_audit') or {}).get('status', 'not_run')}",
        f"- dashboard: {result.get('dashboard_status')}",
        "",
        "# Attention Runs",
    ]
    if not result.get("attention_runs"):
        lines.append("- None.")
    for run in result.get("attention_runs", []):
        blocker = (run.get("blockers") or [{}])[-1]
        lines.append(
            f"- {run['run_id']} status={run['status']} updated={run['updated_at']} "
            f"blocker={blocker.get('code') or 'unspecified'}"
        )
        if blocker.get("summary"):
            lines.append(f"  summary: {_truncate(blocker['summary'], 180)}")
    lines.append("")
    lines.append("# Stale Running Runs")
    if not result.get("stale_running_runs"):
        lines.append("- None.")
    for run in result.get("stale_running_runs", []):
        lines.append(f"- {run['run_id']} updated={run['updated_at']} title={run.get('title') or '(untitled)'}")
    lines.append("")
    lines.append("# Pending Approval Notes")
    if not result.get("pending_approvals"):
        lines.append("- None.")
    for approval in result.get("pending_approvals", []):
        lines.append(
            f"- {approval['run_id']} created={approval.get('created_at')} "
            f"(ledger note only; not authorization)"
        )
        if approval.get("summary"):
            lines.append(f"  summary: {_truncate(approval['summary'], 180)}")
    lines.append("")
    lines.append("# Recent Runs")
    if not result.get("recent_runs"):
        lines.append("- None.")
    for run in result.get("recent_runs", []):
        lines.append(f"- {run['run_id']} status={run['status']} events={run['event_count']} updated={run['updated_at']}")
    lines.append("")
    lines.append("# Research Priorities")
    research = result.get("research_priorities") or {}
    zero_priorities = research.get("zero_candidate_priorities") or []
    hypothesis_priorities = research.get("hypothesis_priorities") or []
    if not zero_priorities and not hypothesis_priorities:
        lines.append("- None.")
    for item in zero_priorities:
        lines.append(f"- zero-candidate {item['lane']} {item['selection_date']} drops={item['total_drops']}")
    for item in hypothesis_priorities:
        lines.append(f"- hypothesis {item['id']} score={item['priority_score']} {item['title']}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def blocker_autopsy_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    min_count: int = 2,
    limit: int = 20,
) -> dict[str, Any]:
    ledger = agent_run_ledger_report(db_path=db_path, tenant_id=tenant_id, limit=max(limit * 20, limit))
    groups: dict[str, dict[str, Any]] = {}
    for run in ledger.get("runs", []):
        for blocker in run.get("blockers") or []:
            code = blocker.get("code") or "unspecified"
            group = groups.setdefault(
                code,
                {
                    "code": code,
                    "count": 0,
                    "run_ids": [],
                    "first_seen": blocker.get("created_at"),
                    "last_seen": blocker.get("created_at"),
                    "latest_summary": "",
                    "taxonomy": code if code in AGENT_RUN_BLOCKER_TAXONOMY else "uncategorized",
                    "safe_next_step": "capture exact blocker evidence and rerun read-only diagnostics",
                },
            )
            group["count"] += 1
            if run["run_id"] not in group["run_ids"]:
                group["run_ids"].append(run["run_id"])
            created_at = blocker.get("created_at")
            if created_at and (not group.get("first_seen") or created_at < group["first_seen"]):
                group["first_seen"] = created_at
            if created_at and (not group.get("last_seen") or created_at > group["last_seen"]):
                group["last_seen"] = created_at
                group["latest_summary"] = blocker.get("summary") or ""
    repeated = [group for group in groups.values() if int(group["count"]) >= min_count]
    repeated.sort(key=lambda item: (-int(item["count"]), str(item.get("last_seen") or "")))
    latest = sorted(groups.values(), key=lambda item: str(item.get("last_seen") or ""), reverse=True)
    return {
        "status": "repeated_blockers" if repeated else ("clear" if ledger.get("status") == "pass" else "issues"),
        "tenant_id": tenant_id,
        "min_count": min_count,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ledger_status": ledger.get("status"),
        "ledger_audit": ledger.get("audit"),
        "repeated_blockers": repeated[:limit],
        "latest_blockers": latest[:limit],
        "recommended_commands": [
            "npm run memory:blocker-autopsy",
            "npm run memory:run-ledger",
            "npm run memory:daily-brief",
        ],
    }


def _format_blocker_autopsy_report(result: dict[str, Any]) -> str:
    lines = [
        "# Blocker Autopsy",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        f"Ledger: {result.get('ledger_status')} audit={(result.get('ledger_audit') or {}).get('status', 'not_run')}",
        "",
        "# Repeated Blockers",
    ]
    if not result.get("repeated_blockers"):
        lines.append("- None.")
    for item in result.get("repeated_blockers", []):
        lines.append(
            f"- {item['code']} count={item['count']} first={item.get('first_seen')} last={item.get('last_seen')}"
        )
        lines.append(f"  runs: {', '.join(item.get('run_ids', [])[:8])}")
        if item.get("latest_summary"):
            lines.append(f"  latest: {_truncate(item['latest_summary'], 180)}")
        lines.append(f"  safe next step: {item.get('safe_next_step')}")
    lines.append("")
    lines.append("# Latest Blockers")
    if not result.get("latest_blockers"):
        lines.append("- None.")
    for item in result.get("latest_blockers", []):
        lines.append(f"- {item['code']} count={item['count']} last={item.get('last_seen')}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def local_inbox_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    stale_hours: int = 6,
    limit: int = 20,
) -> dict[str, Any]:
    ledger = agent_run_ledger_report(db_path=db_path, tenant_id=tenant_id, limit=max(limit * 20, limit))
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
    items: list[dict[str, Any]] = []
    for run in ledger.get("runs", []):
        approval_events = run.get("approvals") or []
        latest_recorded_id = max(
            (int(event.get("event_id") or 0) for event in approval_events if event.get("type") == "approval_recorded"),
            default=0,
        )
        pending_requested = [
            event
            for event in approval_events
            if event.get("type") == "approval_requested" and int(event.get("event_id") or 0) > latest_recorded_id
        ]
        for approval in pending_requested:
            items.append(
                {
                    "kind": "approval_requested",
                    "severity": "needs_operator",
                    "run_id": run["run_id"],
                    "created_at": approval.get("created_at"),
                    "summary": approval.get("summary") or run.get("latest_summary") or "",
                    "non_authoritative": True,
                }
            )
        if run.get("status") in {"blocked", "failed"}:
            blocker = (run.get("blockers") or [{}])[-1]
            items.append(
                {
                    "kind": run.get("status"),
                    "severity": "attention",
                    "run_id": run["run_id"],
                    "created_at": blocker.get("created_at") or run.get("updated_at"),
                    "summary": blocker.get("summary") or run.get("latest_summary") or "",
                    "blocker_code": blocker.get("code"),
                    "non_authoritative": True,
                }
            )
        updated_at = _parse_utc_timestamp(run.get("updated_at"))
        if run.get("status") == "running" and updated_at is not None and updated_at < stale_cutoff:
            items.append(
                {
                    "kind": "stale_running",
                    "severity": "attention",
                    "run_id": run["run_id"],
                    "created_at": run.get("updated_at"),
                    "summary": run.get("latest_summary") or run.get("title") or "",
                    "non_authoritative": True,
                }
            )
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return {
        "status": "pending" if items else ("pass" if ledger.get("status") == "pass" else "issues"),
        "tenant_id": tenant_id,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ledger_status": ledger.get("status"),
        "ledger_audit": ledger.get("audit"),
        "items": items[:limit],
        "recommended_commands": [
            "npm run memory:inbox",
            "npm run memory:daily-brief",
            "npm run memory:run-ledger",
        ],
    }


def _format_local_inbox_report(result: dict[str, Any]) -> str:
    lines = [
        "# Local Agent Inbox",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        f"Ledger: {result.get('ledger_status')} audit={(result.get('ledger_audit') or {}).get('status', 'not_run')}",
        "",
        "# Items",
    ]
    if not result.get("items"):
        lines.append("- None.")
    for item in result.get("items", []):
        code = f" blocker={item.get('blocker_code')}" if item.get("blocker_code") else ""
        lines.append(
            f"- {item['kind']} run={item['run_id']} severity={item['severity']}{code} "
            f"created={item.get('created_at')} (ledger note only; not authorization)"
        )
        if item.get("summary"):
            lines.append(f"  summary: {_truncate(item['summary'], 180)}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _graph_node_search_text(node: dict[str, Any], metadata: dict[str, Any]) -> str:
    metadata = _metadata_for_retrieval(metadata)
    title, body = _node_retrieval_title_body(node, node.get("metadata") or {})
    keywords = metadata.get("retrieval_keywords") or []
    if isinstance(keywords, list):
        keyword_text = " ".join(str(item) for item in keywords)
    else:
        keyword_text = str(keywords)
    return "\n".join(
        [
            str(node.get("id") or ""),
            str(node.get("kind") or ""),
            title,
            body,
            str(node.get("source_ref") or ""),
            keyword_text,
            canonical_json(metadata),
        ]
    )


def _retrieval_source_quality(metadata: dict[str, Any]) -> str:
    source_type = str(metadata.get("source_type") or "")
    return str(metadata.get("source_quality") or MEMORY_SOURCE_QUALITY_BY_TYPE.get(source_type, "unknown"))


def _retrieval_tier(source_type: str, node_kind: str | None = None) -> int:
    if node_kind in RETRIEVAL_TIER_1_NODE_KINDS:
        return 1
    return RETRIEVAL_SOURCE_TYPE_TIERS.get(source_type, 1)


def _retrieval_tier_case_sql(document_alias: str = "d", node_alias: str = "n") -> str:
    tier_one_sources = sorted(
        source_type for source_type, tier in RETRIEVAL_SOURCE_TYPE_TIERS.items() if tier == 1
    )
    tier_two_sources = sorted(
        source_type for source_type, tier in RETRIEVAL_SOURCE_TYPE_TIERS.items() if tier == 2
    )
    tier_one_sql = ", ".join(f"'{source_type}'" for source_type in tier_one_sources)
    tier_two_sql = ", ".join(f"'{source_type}'" for source_type in tier_two_sources)
    tier_one_kinds = ", ".join(f"'{kind}'" for kind in sorted(RETRIEVAL_TIER_1_NODE_KINDS))
    return (
        "CASE "
        f"WHEN {node_alias}.kind IN ({tier_one_kinds}) THEN 1 "
        f"WHEN {document_alias}.source_type IN ({tier_one_sql}) THEN 1 "
        f"WHEN {document_alias}.source_type IN ({tier_two_sql}) THEN 2 "
        f"WHEN {document_alias}.source_type = 'repo_file_index' THEN 3 "
        "ELSE 1 END"
    )


def _upsert_retrieval_document(conn: sqlite3.Connection, node: dict[str, Any]) -> None:
    metadata = node.get("metadata") or {}
    retrieval_metadata = _metadata_for_retrieval(metadata)
    retrieval_title, retrieval_body = _node_retrieval_title_body(node, metadata)
    source_type = str(metadata.get("source_type") or "graph_node")
    authority_scope = str(retrieval_metadata.get("authority_scope") or OPERATING_AUTHORITY_SCOPE)
    capability_label = str(retrieval_metadata.get("capability_label") or "coordination_only")
    search_text = _graph_node_search_text(node, metadata)
    content_sha256 = _text_sha256(
        canonical_json(
            {
                "id": node.get("id"),
                "title": retrieval_title,
                "body": retrieval_body,
                "metadata": retrieval_metadata,
                "source_ref": node.get("source_ref"),
            }
        )
    )
    freshness_status = "stale_or_inactive" if _memory_is_inactive(metadata) or _memory_is_stale(metadata) else "current"
    conn.execute(
        """
        INSERT INTO retrieval_documents(
            doc_id, source_node_id, source_type, source_quality, authority_scope,
            capability_label, title, body, search_text, metadata_json, content_sha256,
            freshness_status, indexed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doc_id) DO UPDATE SET
            source_node_id = excluded.source_node_id,
            source_type = excluded.source_type,
            source_quality = excluded.source_quality,
            authority_scope = excluded.authority_scope,
            capability_label = excluded.capability_label,
            title = excluded.title,
            body = excluded.body,
            search_text = excluded.search_text,
            metadata_json = excluded.metadata_json,
            content_sha256 = excluded.content_sha256,
            freshness_status = excluded.freshness_status,
            indexed_at = excluded.indexed_at
        """,
        (
            str(node["id"]),
            str(node["id"]),
            source_type,
            _retrieval_source_quality(metadata),
            authority_scope,
            capability_label,
            retrieval_title,
            retrieval_body,
            search_text,
            canonical_json(retrieval_metadata),
            content_sha256,
            freshness_status,
            utc_now(),
        ),
    )
    try:
        conn.execute("DELETE FROM retrieval_documents_fts WHERE doc_id = ?", (str(node["id"]),))
        conn.execute(
            "INSERT INTO retrieval_documents_fts(doc_id, title, search_text) VALUES (?, ?, ?)",
            (str(node["id"]), retrieval_title, search_text),
        )
    except sqlite3.OperationalError:
        pass


def _retrieval_file_path(metadata: dict[str, Any], source_ref: str | None) -> str:
    return str(metadata.get("source_path") or metadata.get("path") or source_ref or "").replace("\\", "/").strip()


def _retrieval_file_freshness_status(
    *,
    repo_root: Path,
    source_type: str,
    source_path: str,
    node_body: str,
    metadata: dict[str, Any],
) -> str:
    if not source_path:
        return "missing"
    path = repo_root / source_path
    if not path.exists() or not path.is_file():
        return "missing"
    if source_type == "repo_file_index":
        try:
            size_bytes = path.stat().st_size
        except OSError:
            return "missing"
        indexed_size = metadata.get("size_bytes")
        if indexed_size is not None and int(indexed_size) != int(size_bytes):
            return "stale"
        if size_bytes > DEFAULT_REPO_INDEX_MAX_FILE_BYTES:
            return "current"
    try:
        body = path.read_text(encoding="utf-8")
    except (MemoryError, OSError):
        return "stale"
    except UnicodeDecodeError:
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except (MemoryError, OSError):
            return "stale"
    if source_type == LIVING_HISTORY_SOURCE_TYPE:
        return "current" if _normalized_history_text(node_body) in _normalized_history_text(body) else "stale"
    expected_hash = metadata.get("content_sha256")
    if expected_hash is None:
        return "current"
    return "current" if str(expected_hash) == _text_sha256(body) else "stale"


def refresh_retrieval_freshness(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pass",
        "checked": 0,
        "current": 0,
        "stale": 0,
        "missing": 0,
        "updated": 0,
    }
    with closing(connect(db_path, maintenance=True)) as conn, conn:
        rows = conn.execute(
            """
            SELECT d.doc_id, d.source_type, d.freshness_status, n.body, n.source_ref, n.metadata_json
            FROM retrieval_documents d
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE n.tenant_id = ?
              AND d.source_type IN ({placeholders})
            """.format(placeholders=", ".join("?" for _ in sorted(FILE_FRESHNESS_SOURCE_TYPES))),
            (tenant_id, *sorted(FILE_FRESHNESS_SOURCE_TYPES)),
        ).fetchall()
        for row in rows:
            metadata = json.loads(row["metadata_json"] or "{}")
            source_path = _retrieval_file_path(metadata, row["source_ref"])
            status = _retrieval_file_freshness_status(
                repo_root=repo_root,
                source_type=str(row["source_type"]),
                source_path=source_path,
                node_body=str(row["body"] or ""),
                metadata=metadata,
            )
            result["checked"] += 1
            result[status] += 1
            if row["freshness_status"] != status:
                conn.execute(
                    "UPDATE retrieval_documents SET freshness_status = ?, indexed_at = ? WHERE doc_id = ?",
                    (status, utc_now(), row["doc_id"]),
                )
                result["updated"] += 1
    return result


def retrieval_freshness_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT freshness_status, count(*) AS count
            FROM retrieval_documents d
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE n.tenant_id = ?
            GROUP BY freshness_status
            """,
            (tenant_id,),
        ).fetchall()
    counts = {str(row["freshness_status"]): int(row["count"]) for row in rows}
    stale = int(counts.get("stale", 0))
    missing = int(counts.get("missing", 0))
    return {
        "status": "pass",
        "counts": counts,
        "stale": stale,
        "missing": missing,
        "detail": f"stale={stale} missing={missing}",
    }


def _query_retrieval_documents(
    conn: sqlite3.Connection,
    *,
    query: str,
    tenant_id: str | None,
    sub_tenant_id: str | None,
    metadata_filter: dict[str, Any] | None,
    limit: int,
    include_repo_index: bool = False,
) -> list[dict[str, Any]]:
    terms = [re.sub(r"[^a-zA-Z0-9_]", "", term) for term in _query_terms(query)]
    terms = [term for term in terms if term]
    if not terms:
        return []
    fts_query = " ".join(terms)
    scope_clauses: list[str] = []
    scope_params: list[Any] = []
    if tenant_id is not None:
        scope_clauses.append("n.tenant_id = ?")
        scope_params.append(tenant_id)
    if sub_tenant_id is not None:
        scope_clauses.append("n.sub_tenant_id = ?")
        scope_params.append(sub_tenant_id)
    if not include_repo_index:
        scope_clauses.append("d.source_type <> 'repo_file_index'")
    scope_sql = f" AND {' AND '.join(scope_clauses)}" if scope_clauses else ""
    tier_sql = _retrieval_tier_case_sql()
    freshness_sql = "CASE WHEN d.freshness_status = 'current' THEN 0 ELSE 1 END"
    try:
        rows = conn.execute(
            f"""
            SELECT d.*, n.kind AS node_kind, {tier_sql} AS retrieval_tier,
                   {freshness_sql} AS freshness_rank,
                   bm25(retrieval_documents_fts) AS rank
            FROM retrieval_documents_fts
            JOIN retrieval_documents d ON d.doc_id = retrieval_documents_fts.doc_id
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE retrieval_documents_fts MATCH ?{scope_sql}
            ORDER BY retrieval_tier ASC, freshness_rank ASC, rank ASC
            LIMIT ?
            """,
            (fts_query, *scope_params, max(limit * 50, 500)),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            f"""
            SELECT d.*, n.kind AS node_kind, {tier_sql} AS retrieval_tier,
                   {freshness_sql} AS freshness_rank, 0.0 AS rank
            FROM retrieval_documents d
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE lower(d.search_text) LIKE ?{scope_sql}
            ORDER BY retrieval_tier ASC, freshness_rank ASC, d.indexed_at DESC
            LIMIT ?
            """,
            (f"%{query.lower()}%", *scope_params, max(limit * 50, 500)),
        ).fetchall()
    hits: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        if not _metadata_matches(metadata, metadata_filter):
            continue
        hits.append(
            {
                "doc_id": row["doc_id"],
                "source_node_id": row["source_node_id"],
                "source_type": row["source_type"],
                "source_quality": row["source_quality"],
                "authority_scope": row["authority_scope"],
                "capability_label": row["capability_label"],
                "content_sha256": row["content_sha256"],
                "freshness_status": row["freshness_status"],
                "retrieval_tier": int(row["retrieval_tier"] or _retrieval_tier(row["source_type"], row["node_kind"])),
                "rank": float(row["rank"] or 0.0),
                "why": "Matched retrieval_documents FTS/BM25 index.",
            }
        )
        if len(hits) >= limit:
            break
    return hits


def _validate_choice(value: str, choices: set[str], field_name: str) -> str:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise AgentControlError(f"{field_name} must be one of: {allowed}")
    return value


def _task_row(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = _row_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    if row is None:
        raise AgentControlError(f"Unknown task: {task_id}")
    return row


def _guard_task_status_update(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    next_status: str,
    now: str,
    allowed_statuses: set[str] | None = None,
    disallowed_statuses: set[str] | None = None,
    owner: str | None = None,
) -> None:
    clauses = ["id = ?"]
    params: list[Any] = [task_id]
    if allowed_statuses is not None:
        placeholders = ", ".join("?" for _ in sorted(allowed_statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(sorted(allowed_statuses))
    if disallowed_statuses is not None:
        placeholders = ", ".join("?" for _ in sorted(disallowed_statuses))
        clauses.append(f"status NOT IN ({placeholders})")
        params.extend(sorted(disallowed_statuses))

    set_clause = "status = ?, updated_at = ?"
    update_params: list[Any] = [next_status, now]
    if owner is not None:
        set_clause += ", owner = ?"
        update_params.append(owner)

    cursor = conn.execute(
        f"UPDATE tasks SET {set_clause} WHERE {' AND '.join(clauses)}",
        (*update_params, *params),
    )
    if cursor.rowcount != 1:
        current = _task_row(conn, task_id)
        raise AgentControlError(
            f"Task {task_id} status changed concurrently; current status is {current['status']}"
        )


def _graph_node_row(conn: sqlite3.Connection, node_id: str) -> dict[str, Any]:
    row = _row_dict(conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone())
    if row is None:
        raise AgentControlError(f"Unknown graph node: {node_id}")
    return row


def _edge_id(source_node_id: str, relation: str, target_node_id: str) -> str:
    payload = f"{source_node_id}\0{relation}\0{target_node_id}".encode("utf-8")
    return "edge:" + hashlib.sha256(payload).hexdigest()[:32]


def _assert_metadata_tenant_allowed(metadata: dict[str, Any], *, tenant_id: str) -> None:
    for key in ("tenant_id", "project_tenant_id"):
        value = metadata.get(key)
        if value is not None and str(value) != tenant_id:
            raise AgentControlError(
                f"metadata {key}={value!r} does not match graph node tenant {tenant_id!r}"
            )


def upsert_graph_node(
    conn: sqlite3.Connection,
    *,
    node_id: str,
    kind: str,
    title: str,
    body: str = "",
    tenant_id: str = "options-chatbot",
    sub_tenant_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    upsert: bool = True,
) -> dict[str, Any]:
    _validate_choice(kind, GRAPH_NODE_KINDS, "kind")
    metadata = metadata or {}
    _assert_metadata_tenant_allowed(metadata, tenant_id=tenant_id)
    now = utc_now()
    metadata_json = canonical_json(metadata)
    existing = conn.execute("SELECT id, tenant_id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
    if existing and not upsert:
        raise AgentControlError(f"Graph node already exists: {node_id}")
    if existing:
        if existing["tenant_id"] != tenant_id:
            raise AgentControlError(
                f"Graph node {node_id} already belongs to tenant {existing['tenant_id']}; "
                f"refusing cross-tenant overwrite by {tenant_id}"
            )
        conn.execute(
            """
            UPDATE graph_nodes
            SET kind = ?, tenant_id = ?, sub_tenant_id = ?, title = ?, body = ?,
                metadata_json = ?, source_ref = ?, updated_at = ?
            WHERE id = ?
            """,
            (kind, tenant_id, sub_tenant_id, title, body, metadata_json, source_ref, now, node_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO graph_nodes(
                id, kind, tenant_id, sub_tenant_id, title, body, metadata_json,
                source_ref, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (node_id, kind, tenant_id, sub_tenant_id, title, body, metadata_json, source_ref, now, now),
        )
    node = _graph_node_row(conn, node_id)
    _upsert_retrieval_document(conn, node)
    return node


def upsert_graph_edge(
    conn: sqlite3.Connection,
    *,
    source_node_id: str,
    relation: str,
    target_node_id: str,
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    _graph_node_row(conn, source_node_id)
    _graph_node_row(conn, target_node_id)
    edge_id = _edge_id(source_node_id, relation, target_node_id)
    conn.execute(
        """
        INSERT INTO graph_edges(
            id, source_node_id, relation, target_node_id, metadata_json, source_ref, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_node_id, relation, target_node_id)
        DO UPDATE SET metadata_json = excluded.metadata_json, source_ref = excluded.source_ref
        """,
        (edge_id, source_node_id, relation, target_node_id, canonical_json(metadata or {}), source_ref, utc_now()),
    )
    row = conn.execute("SELECT * FROM graph_edges WHERE id = ?", (edge_id,)).fetchone()
    return _row_dict(row) or {}


def _normalized_history_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tenant_stable_id_component(tenant_id: str) -> str:
    if tenant_id == DEFAULT_TENANT_ID:
        return ""
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:12] + ":"


def _history_node_id(kind: str, source_path: str, stable_heading: str, body: str, *, tenant_id: str) -> str:
    payload = canonical_json(
        {
            "kind": kind,
            "source_path": source_path,
            "stable_heading": stable_heading,
            "body": _normalized_history_text(body),
            "version": LIVING_HISTORY_INGEST_VERSION,
        }
    )
    return (
        f"{kind}:living-history:"
        f"{_tenant_stable_id_component(tenant_id)}{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"
    )


def _repo_reference_node_id(relative_path: str, *, tenant_id: str) -> str:
    return f"repo-ref:{_tenant_stable_id_component(tenant_id)}{hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:24]}"


def _history_title(prefix: str, heading: str, body: str) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", _normalized_history_text(body), maxsplit=1)[0]
    if len(first_sentence) > 96:
        first_sentence = first_sentence[:93].rstrip() + "..."
    return f"{prefix} {heading}: {first_sentence}" if first_sentence else f"{prefix} {heading}"


def _parse_worklog_entries(text: str) -> tuple[list[dict[str, str]], list[str]]:
    entries: list[dict[str, str]] = []
    warnings: list[str] = []
    current_date = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if body:
            entries.append(
                {
                    "kind": "episode",
                    "source_heading": current_date,
                    "source_date": current_date,
                    "body": body,
                }
            )
        current_lines = []

    for raw_line in text.splitlines():
        heading = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", raw_line)
        if heading:
            flush()
            current_date = heading.group(1)
            continue
        if not current_date:
            continue
        if raw_line.startswith("- "):
            flush()
            current_lines = [raw_line[2:].strip()]
        elif current_lines:
            current_lines.append(raw_line.strip())
    flush()
    if not entries:
        warnings.append("no_worklog_entries_parsed")
    return entries, warnings


def _parse_decision_entries(text: str) -> tuple[list[dict[str, str]], list[str]]:
    entries: list[dict[str, str]] = []
    warnings: list[str] = []
    current_heading = ""
    current_date = ""
    current_title = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(line.rstrip() for line in current_lines).strip()
        if current_heading and body:
            entries.append(
                {
                    "kind": "decision",
                    "source_heading": current_heading,
                    "source_date": current_date,
                    "decision_title": current_title,
                    "body": body,
                }
            )
        elif current_heading:
            warnings.append(f"malformed_decision_without_body:{current_heading}")
        current_lines = []

    for raw_line in text.splitlines():
        heading = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})(?::\s*(.+))?\s*$", raw_line)
        if heading:
            flush()
            current_date = heading.group(1)
            current_title = (heading.group(2) or "").strip()
            current_heading = f"{current_date}: {current_title}".rstrip(": ")
            continue
        if current_heading:
            current_lines.append(raw_line)
    flush()
    if not entries:
        warnings.append("no_decision_entries_parsed")
    return entries, warnings


REPO_PATH_REF_RE = re.compile(
    r"(?<![A-Za-z0-9_./\\-])((?:docs|scripts|data|tests|src|python-backend|public|config)"
    r"[\\/][A-Za-z0-9_./\\-]+)"
)


def _extract_repo_path_refs(body: str, *, repo_root: Path, max_edges: int = 12) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in REPO_PATH_REF_RE.finditer(body):
        raw = match.group(1).strip("`'\".,;:)")
        rel = raw.replace("\\", "/")
        path = repo_root / rel
        if rel not in seen and path.exists():
            refs.append(rel)
            seen.add(rel)
        if len(refs) >= max_edges:
            break
    return refs


def ingest_living_history(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    max_edges_per_entry: int = 12,
) -> dict[str, Any]:
    sources = [
        ("docs/WORKLOG.md", _parse_worklog_entries, "WORKLOG"),
        ("docs/DECISIONS.md", _parse_decision_entries, "DECISION"),
    ]
    result: dict[str, Any] = {
        "status": "pass",
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ingest_version": LIVING_HISTORY_INGEST_VERSION,
        "sources": [],
        "nodes_created": 0,
        "nodes_updated": 0,
        "nodes_skipped": 0,
        "nodes_pruned": 0,
        "edges_created": 0,
        "warnings": [],
    }
    with closing(connect(db_path, maintenance=True)) as conn, conn:
        for relative_path, parser, title_prefix in sources:
            path = repo_root / relative_path
            if not path.exists():
                result["warnings"].append(f"missing_source:{relative_path}")
                result["sources"].append({"path": relative_path, "entries": 0, "status": "missing"})
                continue
            text = path.read_text(encoding="utf-8")
            entries, warnings = parser(text)
            result["warnings"].extend(warnings)
            source_summary = {"path": relative_path, "entries": len(entries), "status": "parsed"}
            result["sources"].append(source_summary)
            current_node_ids: set[str] = set()
            for entry in entries:
                kind = entry["kind"]
                body = entry["body"]
                stable_heading = entry["source_heading"]
                node_id = _history_node_id(kind, relative_path, stable_heading, body, tenant_id=tenant_id)
                current_node_ids.add(node_id)
                content_sha256 = _text_sha256(_normalized_history_text(body))
                existing = conn.execute(
                    "SELECT tenant_id, metadata_json FROM graph_nodes WHERE id = ?",
                    (node_id,),
                ).fetchone()
                if existing and existing["tenant_id"] != tenant_id:
                    raise AgentControlError(
                        f"Living-history node {node_id} belongs to tenant {existing['tenant_id']}; "
                        f"refusing cross-tenant ingest by {tenant_id}"
                    )
                existing_metadata = json.loads(existing["metadata_json"] or "{}") if existing else {}
                refs = _extract_repo_path_refs(body, repo_root=repo_root, max_edges=max_edges_per_entry)
                metadata = _with_memory_policy_metadata(
                    {
                        "source_type": LIVING_HISTORY_SOURCE_TYPE,
                        "source_path": relative_path,
                        "source_heading": stable_heading,
                        "source_date": entry.get("source_date"),
                        "decision_title": entry.get("decision_title"),
                        "living_history_kind": kind,
                        "content_sha256": content_sha256,
                        "parser_version": LIVING_HISTORY_INGEST_VERSION,
                        "referenced_repo_paths": refs,
                    },
                    source_type=LIVING_HISTORY_SOURCE_TYPE,
                    source_quality="living_history",
                )
                if existing and existing_metadata.get("content_sha256") == content_sha256:
                    result["nodes_skipped"] += 1
                else:
                    upsert_graph_node(
                        conn,
                        node_id=node_id,
                        kind=kind,
                        title=_history_title(title_prefix, stable_heading, body),
                        body=body,
                        tenant_id=tenant_id,
                        sub_tenant_id="operator",
                        metadata=metadata,
                        source_ref=relative_path,
                    )
                    if existing:
                        result["nodes_updated"] += 1
                    else:
                        result["nodes_created"] += 1
                for rel in refs:
                    target_id = _repo_reference_node_id(rel, tenant_id=tenant_id)
                    target_metadata = _with_memory_policy_metadata(
                        {
                            "source_type": "repo_file_index",
                            "source_path": rel,
                            "created_by": LIVING_HISTORY_INGEST_VERSION,
                            "repo_reference_only": True,
                        },
                        source_type="repo_file_index",
                        source_quality="repo_file_index",
                    )
                    target_existing = conn.execute("SELECT id FROM graph_nodes WHERE id = ?", (target_id,)).fetchone()
                    if target_existing is None:
                        upsert_graph_node(
                            conn,
                            node_id=target_id,
                            kind="knowledge",
                            title=rel,
                            body=f"Repository path referenced by living history: {rel}",
                            tenant_id=tenant_id,
                            sub_tenant_id="operator",
                            metadata=target_metadata,
                            source_ref=rel,
                        )
                    edge_exists = conn.execute(
                        "SELECT 1 FROM graph_edges WHERE source_node_id = ? AND relation = ? AND target_node_id = ?",
                        (node_id, "references", target_id),
                    ).fetchone()
                    upsert_graph_edge(
                        conn,
                        source_node_id=node_id,
                        relation="references",
                        target_node_id=target_id,
                        metadata={"source_type": LIVING_HISTORY_SOURCE_TYPE, "source_path": relative_path},
                        source_ref=relative_path,
                    )
                    if edge_exists is None:
                        result["edges_created"] += 1
            stale_rows = conn.execute(
                """
                SELECT id
                FROM graph_nodes
                WHERE tenant_id = ?
                  AND json_extract(metadata_json, '$.source_type') = ?
                  AND json_extract(metadata_json, '$.source_path') = ?
                """,
                (tenant_id, LIVING_HISTORY_SOURCE_TYPE, relative_path),
            ).fetchall()
            stale_ids = [row["id"] for row in stale_rows if row["id"] not in current_node_ids]
            if stale_ids:
                conn.executemany("DELETE FROM graph_nodes WHERE id = ?", [(node_id,) for node_id in stale_ids])
                result["nodes_pruned"] += len(stale_ids)
    if result["warnings"]:
        result["status"] = "pass_with_warnings"
    return result


def _format_living_history_ingest(result: dict[str, Any]) -> str:
    lines = [
        "# Living History Ingest",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        f"Version: {result.get('ingest_version')}",
        f"Nodes created: {result.get('nodes_created')}",
        f"Nodes updated: {result.get('nodes_updated')}",
        f"Nodes skipped: {result.get('nodes_skipped')}",
        f"Nodes pruned: {result.get('nodes_pruned')}",
        f"Edges created: {result.get('edges_created')}",
        "",
        "# Sources",
    ]
    for source in result.get("sources", []):
        lines.append(f"- {source.get('path')}: {source.get('entries')} entries ({source.get('status')})")
    lines.extend(["", "# Warnings"])
    warnings = result.get("warnings") or []
    if not warnings:
        lines.append("- None.")
    for warning in warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines)


def _prune_seed_nodes_by_source_type(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    source_types: set[str],
) -> int:
    if not source_types:
        return 0
    stale_node_ids: list[str] = []
    rows = conn.execute(
        "SELECT id, metadata_json FROM graph_nodes WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchall()
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if metadata.get("source_type") in source_types:
            if metadata.get("source_type") == "repo_file_index" and metadata.get("repo_reference_only") is True:
                continue
            stale_node_ids.append(row["id"])
    if stale_node_ids:
        conn.executemany("DELETE FROM graph_nodes WHERE id = ?", [(node_id,) for node_id in stale_node_ids])
    return len(stale_node_ids)


def _update_graph_node_metadata(
    conn: sqlite3.Connection,
    node_id: str,
    updates: dict[str, Any],
    *,
    body: str | None = None,
) -> dict[str, Any]:
    node = _graph_node_row(conn, node_id)
    metadata = {**(node.get("metadata") or {}), **updates}
    if body is None:
        conn.execute(
            "UPDATE graph_nodes SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (canonical_json(metadata), utc_now(), node_id),
        )
    else:
        conn.execute(
            "UPDATE graph_nodes SET body = ?, metadata_json = ?, updated_at = ? WHERE id = ?",
            (body, canonical_json(metadata), utc_now(), node_id),
        )
    return _graph_node_row(conn, node_id)


def _update_task_graph_status(conn: sqlite3.Connection, task_id: str, status: str, **extra: Any) -> None:
    node_id = f"task:{task_id}"
    if conn.execute("SELECT id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone() is None:
        return
    _update_graph_node_metadata(conn, node_id, {"status": status, **extra})


def _supersede_memory_node(
    conn: sqlite3.Connection,
    *,
    old_node_id: str,
    new_node_id: str,
    reason: str = "",
) -> dict[str, Any]:
    updated = _update_graph_node_metadata(
        conn,
        old_node_id,
        {
            "memory_status": "superseded",
            "superseded_by": new_node_id,
            "superseded_at": utc_now(),
            "supersession_reason": reason,
        },
    )
    upsert_graph_edge(
        conn,
        source_node_id=new_node_id,
        relation="supersedes",
        target_node_id=old_node_id,
        metadata={"source_type": "operating_memory_supersession", "reason": reason},
        source_ref=new_node_id,
    )
    return updated


def _require_operating_memory_node(
    conn: sqlite3.Connection,
    node_id: str,
    *,
    field_name: str,
) -> dict[str, Any]:
    node = _graph_node_row(conn, node_id)
    if not _is_operating_memory(node.get("metadata") or {}):
        raise AgentControlError(f"{field_name} must be an operating-memory node: {node_id}")
    return node


def create_task(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    title: str,
    description: str = "",
    pathway: str = "general",
    permission_mode: str = "read_only_workers",
    priority: int = 50,
    metadata: dict[str, Any] | None = None,
    tenant_id: str = "options-chatbot",
    sub_tenant_id: str | None = None,
    ack_high_risk: bool = False,
) -> dict[str, Any]:
    pathway = _validate_choice(pathway, PATHWAYS, "pathway")
    permission_mode = _validate_choice(permission_mode, PERMISSION_MODES, "permission_mode")
    if permission_mode in HIGH_RISK_PERMISSION_MODES and not ack_high_risk:
        raise AgentControlError(
            f"{permission_mode} requires --ack-high-risk because the control plane is fail-closed"
        )
    task_id = _short_id("T")
    now = utc_now()
    metadata = metadata or {}
    with closing(connect(db_path)) as conn, conn:
        conn.execute(
            """
            INSERT INTO tasks(
                id, created_at, updated_at, title, description, pathway, status,
                permission_mode, owner, priority, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                task_id,
                now,
                now,
                title,
                description,
                pathway,
                "open",
                permission_mode,
                priority,
                canonical_json(metadata),
            ),
        )
        node = upsert_graph_node(
            conn,
            node_id=f"task:{task_id}",
            kind="task",
            title=title,
            body=description,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id or pathway,
            metadata={
                **metadata,
                "task_id": task_id,
                "pathway": pathway,
                "permission_mode": permission_mode,
                "status": "open",
                "priority": priority,
            },
            source_ref=f"task:{task_id}",
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="task.created",
            payload={"task_id": task_id, "graph_node_id": node["id"], "pathway": pathway},
        )
        task = _task_row(conn, task_id)
        task["graph_node_id"] = node["id"]
        return task


def claim_task(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    task_id: str,
    worker_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        task = _task_row(conn, task_id)
        if task["status"] not in {"open", "reported"}:
            raise AgentControlError(f"Task {task_id} cannot be claimed from status {task['status']}")
        now = utc_now()
        conn.execute(
            """
            INSERT INTO task_claims(task_id, worker_id, claimed_at, status, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, worker_id, now, "active", canonical_json(metadata or {})),
        )
        _guard_task_status_update(
            conn,
            task_id=task_id,
            next_status="claimed",
            now=now,
            allowed_statuses={"open", "reported"},
            owner=worker_id,
        )
        _update_task_graph_status(conn, task_id, "claimed", owner=worker_id)
        run_node = upsert_graph_node(
            conn,
            node_id=f"worker_run:{task_id}:{uuid.uuid4().hex[:8]}",
            kind="worker_run",
            title=f"{worker_id} claimed {task_id}",
            body=f"Worker {worker_id} claimed task {task_id}.",
            sub_tenant_id=task["pathway"],
            metadata={"task_id": task_id, "worker_id": worker_id, "status": "claimed"},
            source_ref=f"task:{task_id}",
        )
        conn.execute(
            """
            INSERT INTO worker_runs(task_id, graph_node_id, worker_id, status, started_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, run_node["id"], worker_id, "claimed", now, canonical_json(metadata or {})),
        )
        upsert_graph_edge(
            conn,
            source_node_id=run_node["id"],
            relation="claims",
            target_node_id=f"task:{task_id}",
            metadata={"worker_id": worker_id},
            source_ref=f"task:{task_id}",
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="task.claimed",
            payload={"task_id": task_id, "worker_id": worker_id, "worker_run_node_id": run_node["id"]},
        )
        result = _task_row(conn, task_id)
        result["worker_run_node_id"] = run_node["id"]
        return result


def report_task(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    task_id: str,
    worker_id: str,
    finding: str,
    proof_gate_status: str = "not_applicable",
    recommendation: str = "",
    verification: str = "",
    blockers: str = "",
    files_read: str = "",
    commands_run: str = "",
    artifacts_written: str = "",
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        task = _task_row(conn, task_id)
        if task["status"] in TERMINAL_TASK_STATUSES:
            raise AgentControlError(f"Task {task_id} cannot be reported from terminal status {task['status']}")
        report = {
            "role": worker_id,
            "task": task_id,
            "files_artifacts_read": files_read,
            "commands_run": commands_run,
            "artifacts_written": artifacts_written,
            "finding": finding,
            "proof_gate_status": proof_gate_status,
            "recommendation": recommendation,
            "verification": verification,
            "blockers": blockers,
        }
        now = utc_now()
        conn.execute(
            """
            INSERT INTO task_reports(task_id, worker_id, reported_at, report_json, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, worker_id, now, canonical_json(report), "submitted"),
        )
        report_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        _guard_task_status_update(
            conn,
            task_id=task_id,
            next_status="reported",
            now=now,
            disallowed_statuses=TERMINAL_TASK_STATUSES,
        )
        _update_task_graph_status(conn, task_id, "reported", latest_report_id=report_id, latest_report_worker=worker_id)
        report_node = upsert_graph_node(
            conn,
            node_id=f"report:{task_id}:{report_id}",
            kind="episode",
            title=f"{worker_id} report for {task_id}",
            body=finding,
            sub_tenant_id=task["pathway"],
            metadata={
                **report,
                "source_type": "task_report",
                "report_status": "submitted",
                "report_id": report_id,
            },
            source_ref=f"task_report:{report_id}",
        )
        upsert_graph_edge(
            conn,
            source_node_id=report_node["id"],
            relation="reports_on",
            target_node_id=f"task:{task_id}",
            metadata={"worker_id": worker_id, "proof_gate_status": proof_gate_status},
            source_ref=f"task_report:{report_id}",
        )
        if blockers:
            blocker_node = upsert_graph_node(
                conn,
                node_id=f"blocker:{task_id}:{report_id}",
                kind="blocker",
                title=f"Blocker for {task_id}",
                body=blockers,
                sub_tenant_id=task["pathway"],
                metadata={
                    "source_type": "task_report",
                    "report_status": "submitted",
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "report_id": report_id,
                },
                source_ref=f"task_report:{report_id}",
            )
            upsert_graph_edge(
                conn,
                source_node_id=blocker_node["id"],
                relation="blocks",
                target_node_id=f"task:{task_id}",
                metadata={"worker_id": worker_id},
                source_ref=f"task_report:{report_id}",
            )
        _record_event(
            conn,
            events_path=events_path,
            event_type="task.reported",
            payload={"task_id": task_id, "worker_id": worker_id, "report_id": report_id},
        )
        result = _row_dict(conn.execute("SELECT * FROM task_reports WHERE id = ?", (report_id,)).fetchone()) or {}
        result["graph_node_id"] = report_node["id"]
        return result


def _operating_kind(memory_type: str) -> str:
    return OPERATING_MEMORY_KIND_BY_TYPE.get(memory_type, "memory")


def _operating_node_id(memory_type: str, title: str) -> str:
    safe_title = _safe_node_path(title).replace("/", "-")[:72] or uuid.uuid4().hex[:8]
    return f"memory:{memory_type}:{safe_title}:{uuid.uuid4().hex[:8]}"


def _upsert_operating_memory(
    conn: sqlite3.Connection,
    *,
    memory_type: str,
    title: str,
    body: str = "",
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = None,
    memory_status: str = "active",
    confidence: str = "accepted",
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    node_id: str | None = None,
    supersedes: list[str] | None = None,
    freshness_days: int | None = None,
) -> dict[str, Any]:
    memory_type = _validate_choice(memory_type, OPERATING_MEMORY_TYPES, "memory_type")
    memory_status = _validate_choice(memory_status, MEMORY_STATUSES, "memory_status")
    confidence = _validate_choice(confidence, MEMORY_CONFIDENCE, "confidence")
    _assert_memory_policy_valid(
        title=title,
        body=body,
        metadata=metadata or {},
        field_name="operating memory input",
    )
    recorded_at = utc_now()
    memory_metadata = _with_memory_policy_metadata(
        {
            **(metadata or {}),
            "memory_type": memory_type,
            "memory_status": memory_status,
            "confidence": confidence,
            "recorded_at": recorded_at,
            "freshness_days": freshness_days,
        },
        source_type="operating_memory",
        source_quality="accepted_runtime_memory",
    )
    if freshness_days is not None:
        memory_metadata["expires_at"] = _utc_plus_days(freshness_days, from_raw=recorded_at)
    if supersedes:
        memory_metadata["supersedes"] = supersedes
    _assert_memory_policy_valid(title=title, body=body, metadata=memory_metadata, field_name="operating memory")
    node = upsert_graph_node(
        conn,
        node_id=node_id or _operating_node_id(memory_type, title),
        kind=_operating_kind(memory_type),
        title=title,
        body=body,
        tenant_id=tenant_id,
        sub_tenant_id=sub_tenant_id,
        metadata=memory_metadata,
        source_ref=source_ref,
    )
    for superseded_node_id in supersedes or []:
        if conn.execute("SELECT id FROM graph_nodes WHERE id = ?", (superseded_node_id,)).fetchone() is not None:
            _require_operating_memory_node(conn, superseded_node_id, field_name="supersedes")
            _supersede_memory_node(
                conn,
                old_node_id=superseded_node_id,
                new_node_id=node["id"],
                reason=f"Superseded by {node['id']}",
            )
    return node


def _latest_task_report(conn: sqlite3.Connection, task_id: str) -> dict[str, Any] | None:
    return _row_dict(
        conn.execute(
            "SELECT * FROM task_reports WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    )


def _writeback_accepted_report(
    conn: sqlite3.Connection,
    *,
    task: dict[str, Any],
    report_row: dict[str, Any],
    decision_node_id: str,
    accepted_by: str,
) -> list[str]:
    report = report_row.get("report") or {}
    report_id = report_row["id"]
    task_id = task["id"]
    source_ref = f"task_report:{report_id}"
    base_metadata = {
        "task_id": task_id,
        "report_id": report_id,
        "worker_id": report.get("role") or report_row.get("worker_id"),
        "accepted_by": accepted_by,
        "proof_gate_status": report.get("proof_gate_status"),
        "pathway": task.get("pathway"),
        "files_artifacts_read": report.get("files_artifacts_read"),
        "commands_run": report.get("commands_run"),
    }
    accepted_node_ids: list[str] = []
    report_node_id = f"report:{task_id}:{report_id}"
    if conn.execute("SELECT id FROM graph_nodes WHERE id = ?", (report_node_id,)).fetchone() is not None:
        _update_graph_node_metadata(
            conn,
            report_node_id,
            {"report_status": "accepted", "accepted_by": accepted_by, "accepted_at": utc_now()},
        )
        upsert_graph_edge(
            conn,
            source_node_id=decision_node_id,
            relation="accepts",
            target_node_id=report_node_id,
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
    report_memory = _upsert_operating_memory(
        conn,
        memory_type="worker_report",
        title=f"Accepted worker report for {task_id}",
        body=str(report.get("finding") or ""),
        sub_tenant_id=task.get("pathway"),
        metadata={**base_metadata, "recommendation": report.get("recommendation")},
        source_ref=source_ref,
        node_id=f"memory:worker_report:{task_id}:{report_id}",
    )
    accepted_node_ids.append(report_memory["id"])
    upsert_graph_edge(
        conn,
        source_node_id=report_memory["id"],
        relation="derived_from",
        target_node_id=report_node_id,
        metadata={"source_type": "accepted_report_writeback"},
        source_ref=source_ref,
    )
    upsert_graph_edge(
        conn,
        source_node_id=report_memory["id"],
        relation="reports_on",
        target_node_id=f"task:{task_id}",
        metadata={"source_type": "accepted_report_writeback"},
        source_ref=source_ref,
    )
    upsert_graph_edge(
        conn,
        source_node_id=decision_node_id,
        relation="accepts",
        target_node_id=report_memory["id"],
        metadata={"source_type": "accepted_report_writeback"},
        source_ref=source_ref,
    )
    verification = str(report.get("verification") or "").strip()
    if verification:
        verification_node = _upsert_operating_memory(
            conn,
            memory_type="verification",
            title=f"Verification for {task_id}",
            body=verification,
            sub_tenant_id=task.get("pathway"),
            metadata=base_metadata,
            source_ref=source_ref,
            node_id=f"memory:verification:{task_id}:{report_id}",
        )
        accepted_node_ids.append(verification_node["id"])
        upsert_graph_edge(
            conn,
            source_node_id=report_memory["id"],
            relation="verified_by",
            target_node_id=verification_node["id"],
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
        upsert_graph_edge(
            conn,
            source_node_id=verification_node["id"],
            relation="verifies",
            target_node_id=f"task:{task_id}",
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
    blockers = str(report.get("blockers") or "").strip()
    if blockers:
        blocker_node = _upsert_operating_memory(
            conn,
            memory_type="blocker",
            title=f"Accepted blocker for {task_id}",
            body=blockers,
            sub_tenant_id=task.get("pathway"),
            metadata=base_metadata,
            source_ref=source_ref,
            node_id=f"memory:blocker:{task_id}:{report_id}",
        )
        accepted_node_ids.append(blocker_node["id"])
        upsert_graph_edge(
            conn,
            source_node_id=blocker_node["id"],
            relation="blocks",
            target_node_id=f"task:{task_id}",
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
    for index, artifact in enumerate(_split_memory_items(str(report.get("artifacts_written") or "")), start=1):
        artifact_node = _upsert_operating_memory(
            conn,
            memory_type="artifact",
            title=artifact,
            body=artifact,
            sub_tenant_id=task.get("pathway"),
            metadata={**base_metadata, "artifact": artifact},
            source_ref=source_ref,
            node_id=f"memory:artifact:{task_id}:{report_id}:{index}",
        )
        accepted_node_ids.append(artifact_node["id"])
        upsert_graph_edge(
            conn,
            source_node_id=report_memory["id"],
            relation="produced",
            target_node_id=artifact_node["id"],
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
        upsert_graph_edge(
            conn,
            source_node_id=artifact_node["id"],
            relation="documents",
            target_node_id=f"task:{task_id}",
            metadata={"source_type": "accepted_report_writeback"},
            source_ref=source_ref,
        )
    conn.execute("UPDATE task_reports SET status = ? WHERE id = ?", ("accepted", report_id))
    return accepted_node_ids


def accept_task(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    task_id: str,
    accepted_by: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        task = _task_row(conn, task_id)
        if task["status"] not in {"reported", "claimed", "open"}:
            raise AgentControlError(f"Task {task_id} cannot be accepted from status {task['status']}")
        now = utc_now()
        _guard_task_status_update(
            conn,
            task_id=task_id,
            next_status="accepted",
            now=now,
            allowed_statuses={"reported", "claimed", "open"},
        )
        _update_task_graph_status(conn, task_id, "accepted", accepted_by=accepted_by)
        decision_node = _upsert_operating_memory(
            conn,
            node_id=f"decision:{task_id}:{uuid.uuid4().hex[:8]}",
            memory_type="decision",
            title=f"Accepted {task_id}",
            body=summary,
            sub_tenant_id=task["pathway"],
            metadata={
                **(metadata or {}),
                "task_id": task_id,
                "accepted_by": accepted_by,
                "pathway": task["pathway"],
            },
            source_ref=f"task:{task_id}",
        )
        conn.execute(
            """
            INSERT INTO decisions(task_id, graph_node_id, summary, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, decision_node["id"], summary, now, canonical_json(metadata or {})),
        )
        upsert_graph_edge(
            conn,
            source_node_id=decision_node["id"],
            relation="accepts",
            target_node_id=f"task:{task_id}",
            metadata={"accepted_by": accepted_by},
            source_ref=f"task:{task_id}",
        )
        latest_report = _latest_task_report(conn, task_id)
        writeback_node_ids: list[str] = []
        if latest_report is not None:
            writeback_node_ids = _writeback_accepted_report(
                conn,
                task=task,
                report_row=latest_report,
                decision_node_id=decision_node["id"],
                accepted_by=accepted_by,
            )
        _record_event(
            conn,
            events_path=events_path,
            event_type="task.accepted",
            payload={
                "task_id": task_id,
                "accepted_by": accepted_by,
                "decision_node_id": decision_node["id"],
                "writeback_node_ids": writeback_node_ids,
            },
        )
        result = _task_row(conn, task_id)
        result["decision_node_id"] = decision_node["id"]
        result["writeback_node_ids"] = writeback_node_ids
        return result


def remember_graph_node(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    kind: str,
    title: str,
    body: str = "",
    tenant_id: str = "options-chatbot",
    sub_tenant_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    node_id: str | None = None,
    upsert: bool = True,
) -> dict[str, Any]:
    node_id = node_id or _short_id(kind.upper())
    metadata = metadata or {}
    if metadata.get("source_type") == "operating_memory":
        raise AgentControlError("graph remember cannot create operating_memory nodes; use memory remember")
    _assert_memory_policy_valid(
        title=title,
        body=body,
        metadata=_with_memory_policy_metadata(metadata, source_type=str(metadata.get("source_type") or "graph_node")),
        field_name="graph memory",
    )
    metadata = _metadata_for_retrieval(metadata)
    with closing(connect(db_path)) as conn, conn:
        node = upsert_graph_node(
            conn,
            node_id=node_id,
            kind=kind,
            title=title,
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata=metadata,
            source_ref=source_ref,
            upsert=upsert,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="graph.node.remembered",
            payload={"node_id": node["id"], "kind": kind, "tenant_id": tenant_id, "sub_tenant_id": sub_tenant_id},
        )
        return node


def remember_operating_memory(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    memory_type: str,
    title: str,
    body: str = "",
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = None,
    memory_status: str = "active",
    confidence: str = "inferred",
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
    node_id: str | None = None,
    supersedes: list[str] | None = None,
    freshness_days: int | None = None,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        node = _upsert_operating_memory(
            conn,
            memory_type=memory_type,
            title=title,
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            memory_status=memory_status,
            confidence=confidence,
            metadata=metadata,
            source_ref=source_ref,
            node_id=node_id,
            supersedes=supersedes,
            freshness_days=freshness_days,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="memory.remembered",
            payload={
                "node_id": node["id"],
                "memory_type": memory_type,
                "memory_status": memory_status,
                "supersedes": supersedes or [],
            },
        )
        return node


def log_session(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    sessions_path: Path = DEFAULT_SESSIONS_PATH,
    transcript_path: Path,
    repo_root: Path = ROOT,
    session_id: str | None = None,
    title: str = "",
    summary: str = "",
    actor: str = "agent",
    expected_sha256: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = "operator",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = _resolve_inside_repo(repo_root, transcript_path)
    if not resolved.is_file():
        raise AgentControlError(f"transcript file not found: {resolved}")
    relative_path = _relative_to_repo(repo_root, resolved)
    _assert_memory_safe_source_path(relative_path)
    current_sha256 = _file_sha256(resolved)
    if expected_sha256 is not None and expected_sha256 != current_sha256:
        raise AgentControlError(
            f"transcript hash mismatch for {resolved}: expected {expected_sha256}, got {current_sha256}"
        )
    text = resolved.read_text(encoding="utf-8")
    session_id = session_id or _short_id("S")
    now = utc_now()
    payload = {
        "session_id": session_id,
        "logged_at": now,
        "title": title or relative_path,
        "summary": summary,
        "actor": actor,
        "path": relative_path,
        "source_sha256": current_sha256,
        "bytes": resolved.stat().st_size,
        "line_count": len(text.splitlines()),
        "metadata": metadata or {},
    }
    with closing(connect(db_path)) as conn, conn:
        node = upsert_graph_node(
            conn,
            node_id=f"session:{session_id}",
            kind="episode",
            title=payload["title"],
            body=summary or _repo_file_excerpt(text, max_chars=2500),
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata={
                **(metadata or {}),
                "source_type": "session_transcript",
                "session_id": session_id,
                "actor": actor,
                "path": relative_path,
                "source_sha256": current_sha256,
                "line_count": payload["line_count"],
                "bytes": payload["bytes"],
                "logged_at": now,
            },
            source_ref=relative_path,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="session.logged",
            payload={"session_id": session_id, "node_id": node["id"], "path": relative_path},
        )
    _append_jsonl(sessions_path, payload)
    payload["graph_node_id"] = f"session:{session_id}"
    return payload


def _parse_dream_entries(raw_entries: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_entries, list):
        raise AgentControlError("dream proposal entries must be a list")
    entries: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            raise AgentControlError(f"dream entry {index} must be a JSON object")
        memory_type = str(raw.get("type") or "").strip()
        if memory_type not in DREAM_PROPOSAL_TYPES:
            raise AgentControlError(
                f"dream entry {index} type must be one of: {', '.join(sorted(DREAM_PROPOSAL_TYPES))}"
            )
        title = str(raw.get("title") or "").strip()
        body = str(raw.get("body") or "").strip()
        if not title or not body:
            raise AgentControlError(f"dream entry {index} requires title and body")
        confidence = str(raw.get("confidence") or "inferred").strip()
        if confidence not in {"observed", "inferred", "unknown"}:
            raise AgentControlError(f"dream entry {index} confidence must be observed, inferred, or unknown")
        entry_id = str(raw.get("id") or f"entry-{index}").strip()
        identity = (memory_type, entry_id)
        if identity in seen_ids:
            raise AgentControlError(f"dream entry {index} duplicates entry id {memory_type}:{entry_id}")
        seen_ids.add(identity)
        evidence = raw.get("evidence", [])
        if evidence is None:
            evidence = []
        if not isinstance(evidence, list):
            raise AgentControlError(f"dream entry {index} evidence must be a list")
        if any(not isinstance(value, str) or not value.strip() for value in evidence):
            raise AgentControlError(f"dream entry {index} evidence entries must be non-empty strings")
        supersedes = raw.get("supersedes", [])
        if supersedes is None:
            supersedes = []
        if isinstance(supersedes, str) or not isinstance(supersedes, list):
            raise AgentControlError(f"dream entry {index} supersedes must be a list")
        if any(not isinstance(value, str) or not value.strip() for value in supersedes):
            raise AgentControlError(f"dream entry {index} supersedes entries must be non-empty strings")
        freshness_days = raw.get("freshness_days")
        if freshness_days is not None and (
            isinstance(freshness_days, bool) or not isinstance(freshness_days, int) or freshness_days < 0
        ):
            raise AgentControlError(f"dream entry {index} freshness_days must be a non-negative integer")
        raw_metadata = raw.get("metadata", {})
        if raw_metadata is None:
            raw_metadata = {}
        if not isinstance(raw_metadata, dict):
            raise AgentControlError(f"dream entry {index} metadata must be a JSON object")
        entry_metadata = dict(raw_metadata)
        for key in [
            "target_project",
            "pathway",
            "intended_consumer",
            "promotion_target",
            "review_question",
            "acceptance_criteria",
            "reject_if",
            "retrieval_keywords",
        ]:
            if key in raw and key not in entry_metadata:
                entry_metadata[key] = raw[key]
        entries.append(
            {
                "id": entry_id,
                "type": memory_type,
                "title": title,
                "body": body,
                "confidence": confidence,
                "evidence": evidence,
                "supersedes": supersedes,
                "freshness_days": freshness_days,
                "metadata": entry_metadata,
            }
        )
    return entries


def propose_dream(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    proposal_path: Path,
    repo_root: Path = ROOT,
    dream_id: str | None = None,
    title: str = "",
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = "operator",
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    resolved = _resolve_inside_repo(repo_root, proposal_path)
    if not resolved.is_file():
        raise AgentControlError(f"dream proposal file not found: {resolved}")
    relative_path = _relative_to_repo(repo_root, resolved)
    _assert_memory_safe_source_path(relative_path)
    current_sha256 = _file_sha256(resolved)
    if expected_sha256 is not None and expected_sha256 != current_sha256:
        raise AgentControlError(
            f"dream proposal hash mismatch for {resolved}: expected {expected_sha256}, got {current_sha256}"
        )
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"dream proposal must be valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise AgentControlError("dream proposal must be a JSON object")
    entries = _parse_dream_entries(raw.get("entries") or [])
    if not entries:
        raise AgentControlError("dream proposal requires at least one entry")
    dream_id = dream_id or _short_id("DREAM")
    now = utc_now()
    proposal = {
        "dream_id": dream_id,
        "status": "proposed",
        "tenant_id": tenant_id,
        "sub_tenant_id": sub_tenant_id,
        "title": title or str(raw.get("title") or relative_path),
        "summary": str(raw.get("summary") or ""),
        "proposed_at": now,
        "path": relative_path,
        "source_sha256": current_sha256,
        "entry_count": len(entries),
        "entries": entries,
        "evidence": raw.get("evidence") or [],
    }
    with closing(connect(db_path)) as conn, conn:
        node = upsert_graph_node(
            conn,
            node_id=f"dream:{dream_id}",
            kind="memory",
            title=proposal["title"],
            body=proposal["summary"],
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata=_with_memory_policy_metadata(
                {
                    "dream_id": dream_id,
                    "proposal_status": "proposed",
                    "source_sha256": current_sha256,
                    "path": relative_path,
                    "entry_count": len(entries),
                    "entries": entries,
                    "evidence": proposal["evidence"],
                    "proposed_at": now,
                },
                source_type="dream_proposal",
                source_quality="unaccepted_dream_proposal",
            ),
            source_ref=relative_path,
            upsert=False,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="dream.proposed",
            payload={"dream_id": dream_id, "node_id": node["id"], "entry_count": len(entries)},
        )
    proposal["graph_node_id"] = f"dream:{dream_id}"
    return proposal


def accept_dream(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    dream_id: str,
    accepted_by: str = "CEO",
    note: str = "",
) -> dict[str, Any]:
    dream_node_id = dream_id if dream_id.startswith("dream:") else f"dream:{dream_id}"
    accepted_at = utc_now()
    accepted_memory_ids: list[str] = []
    with closing(connect(db_path)) as conn, conn:
        proposal = _graph_node_row(conn, dream_node_id)
        metadata = proposal.get("metadata") or {}
        if metadata.get("source_type") != "dream_proposal":
            raise AgentControlError(f"not a dream proposal node: {dream_node_id}")
        if metadata.get("proposal_status") != "proposed":
            raise AgentControlError(
                f"dream proposal {dream_node_id} cannot be accepted from status {metadata.get('proposal_status')}"
            )
        entries = _parse_dream_entries(metadata.get("entries") or [])
        for entry in entries:
            if entry["confidence"] == "observed" and not entry.get("evidence"):
                raise AgentControlError(
                    f"dream entry {entry['id']} cannot be accepted as observed without evidence"
                )
            entry_metadata = _with_memory_policy_metadata(
                {
                    **(entry.get("metadata") or {}),
                    "origin": "dreaming",
                    "proposal_origin": "dream",
                    "non_authoritative": True,
                    "dream_id": metadata.get("dream_id"),
                    "dream_node_id": dream_node_id,
                    "source_sha256": metadata.get("source_sha256"),
                    "evidence": entry.get("evidence") or [],
                    "accepted_by": accepted_by,
                    "accepted_at": accepted_at,
                },
                source_type="operating_memory",
                source_quality="accepted_dream_memory",
            )
            _assert_memory_policy_valid(
                title=entry["title"],
                body=entry["body"],
                metadata=entry_metadata,
                field_name=f"dream entry {entry['id']}",
            )
            node = _upsert_operating_memory(
                conn,
                memory_type=entry["type"],
                title=entry["title"],
                body=entry["body"],
                tenant_id=proposal.get("tenant_id") or DEFAULT_TENANT_ID,
                sub_tenant_id=proposal.get("sub_tenant_id"),
                confidence=entry["confidence"],
                metadata=entry_metadata,
                source_ref=dream_node_id,
                node_id=f"memory:{entry['type']}:dream:{metadata.get('dream_id')}:{entry['id']}",
                supersedes=[str(item) for item in entry.get("supersedes") or []],
                freshness_days=entry.get("freshness_days"),
            )
            accepted_memory_ids.append(node["id"])
            upsert_graph_edge(
                conn,
                source_node_id=node["id"],
                relation="derived_from",
                target_node_id=dream_node_id,
                metadata={"source_type": "dream_acceptance"},
                source_ref=dream_node_id,
            )
        _update_graph_node_metadata(
            conn,
            dream_node_id,
            {
                "proposal_status": "accepted",
                "accepted_by": accepted_by,
                "accepted_at": accepted_at,
                "acceptance_note": note,
                "accepted_memory_ids": accepted_memory_ids,
            },
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="dream.accepted",
            payload={
                "dream_id": metadata.get("dream_id"),
                "dream_node_id": dream_node_id,
                "accepted_by": accepted_by,
                "accepted_memory_ids": accepted_memory_ids,
            },
        )
    return {
        "dream_id": metadata.get("dream_id"),
        "dream_node_id": dream_node_id,
        "status": "accepted",
        "accepted_memory_ids": accepted_memory_ids,
    }


def reject_dream(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    dream_id: str,
    rejected_by: str = "CEO",
    reason: str = "",
) -> dict[str, Any]:
    dream_node_id = dream_id if dream_id.startswith("dream:") else f"dream:{dream_id}"
    with closing(connect(db_path)) as conn, conn:
        proposal = _graph_node_row(conn, dream_node_id)
        metadata = proposal.get("metadata") or {}
        if metadata.get("source_type") != "dream_proposal":
            raise AgentControlError(f"not a dream proposal node: {dream_node_id}")
        if metadata.get("proposal_status") != "proposed":
            raise AgentControlError(
                f"dream proposal {dream_node_id} cannot be rejected from status {metadata.get('proposal_status')}"
            )
        _update_graph_node_metadata(
            conn,
            dream_node_id,
            {
                "proposal_status": "rejected",
                "rejected_by": rejected_by,
                "rejected_at": utc_now(),
                "rejection_reason": reason,
            },
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="dream.rejected",
            payload={"dream_id": metadata.get("dream_id"), "dream_node_id": dream_node_id, "reason": reason},
        )
    return {"dream_id": metadata.get("dream_id"), "dream_node_id": dream_node_id, "status": "rejected"}


def list_dreams(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    rows = query_graph(
        db_path=db_path,
        query="dream",
        tenant_id=tenant_id,
        metadata_filter={"source_type": "dream_proposal"},
        limit=max(limit, 1),
        max_depth=0,
    )["graph_context"]["nodes"]
    dreams = []
    for node in rows:
        metadata = node.get("metadata") or {}
        if status is not None and metadata.get("proposal_status") != status:
            continue
        dreams.append(node)
        if len(dreams) >= limit:
            break
    return {"dreams": dreams}


def review_dreams(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 12,
) -> dict[str, Any]:
    proposed = list_dreams(db_path=db_path, tenant_id=tenant_id, status="proposed", limit=limit)["dreams"]
    accepted = list_dreams(db_path=db_path, tenant_id=tenant_id, status="accepted", limit=limit)["dreams"]
    with closing(connect(db_path)) as conn, conn:
        dream_lessons = [
            node
            for node in _dedupe_nodes(
                [
                    *_select_graph_nodes(
                        conn,
                        tenant_id=tenant_id,
                        memory_type="lesson",
                        active_only=True,
                        limit=limit,
                    ),
                    *_select_graph_nodes(
                        conn,
                        tenant_id=tenant_id,
                        memory_type="constraint",
                        active_only=True,
                        limit=limit,
                    ),
                ]
            )
            if (node.get("metadata") or {}).get("origin") == "dreaming"
        ][:limit]
        open_questions = [
            node
            for node in _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                memory_type="open_question",
                active_only=True,
                limit=max(limit * 3, 12),
            )
            if (node.get("metadata") or {}).get("origin") == "dreaming"
        ][:limit]
    return {
        "status": "review_required" if proposed else "no_proposed_dreams",
        "tenant_id": tenant_id,
        "proposed_dreams": proposed,
        "accepted_dreams": accepted,
        "dream_lessons": dream_lessons,
        "open_questions": open_questions,
        "recommended_commands": [
            "npm run memory:review-dreams",
            "npm run memory:dreams",
            "npm run memory:audit",
            "npm run agent:control -- dream accept <dream-id> --accepted-by CEO --json",
            "npm run agent:control -- dream reject <dream-id> --reason \"Weak or stale evidence.\" --json",
        ],
    }


def _normalize_dream_line_type(raw_type: str) -> str:
    normalized = raw_type.lower().replace("-", "_").replace(" ", "_")
    if normalized == "open_question":
        return "open_question"
    return normalized


def _auto_dream_text_has_high_risk(text: str) -> bool:
    return any(pattern.search(text) for pattern in AUTO_DREAM_HIGH_RISK_RE)


def _auto_dream_evidence_issue(
    conn: sqlite3.Connection,
    evidence_refs: Any,
    *,
    tenant_id: str,
    field_name: str,
    current_node_id: str,
) -> str | None:
    if evidence_refs is None:
        return None
    if not isinstance(evidence_refs, list):
        return f"{field_name} evidence must be a list"
    for value in evidence_refs:
        if not isinstance(value, str) or not value.strip():
            return f"{field_name} evidence entries must be non-empty graph node ids"
        evidence_node_id = value.strip()
        if evidence_node_id == current_node_id:
            return f"{field_name} evidence cannot cite the dream proposal itself: {evidence_node_id}"
        node = _row_dict(
            conn.execute(
                "SELECT * FROM graph_nodes WHERE id = ?",
                (evidence_node_id,),
            ).fetchone()
        )
        if node is None:
            return f"{field_name} evidence graph node not found: {evidence_node_id}"
        if node.get("tenant_id") != tenant_id:
            return f"{field_name} evidence graph node belongs to another tenant: {evidence_node_id}"
        evidence_metadata = node.get("metadata") or {}
        if evidence_metadata.get("source_type") != "session_transcript":
            return f"{field_name} evidence must cite session_transcript nodes for auto-accept: {evidence_node_id}"
    return None


def _auto_dream_session_source_text(session_node: dict[str, Any], *, repo_root: Path) -> tuple[str, list[str]]:
    texts = [str(session_node.get("body") or "")]
    sources = ["graph_body"]
    metadata = session_node.get("metadata") or {}
    path = metadata.get("path") or session_node.get("source_ref")
    if isinstance(path, str) and path.strip():
        try:
            resolved = _resolve_inside_repo(repo_root, Path(path))
            if resolved.is_file():
                texts.append(resolved.read_text(encoding="utf-8"))
                sources.append("transcript_file")
            else:
                sources.append("transcript_file_unreadable")
        except (OSError, UnicodeDecodeError, AgentControlError):
            sources.append("transcript_file_unreadable")
    return "\n".join(texts), sources


def _auto_dream_title(text: str, *, max_chars: int = 96) -> str:
    title = " ".join(text.split())
    if len(title) <= max_chars:
        return title
    return title[: max_chars - 3].rstrip() + "..."


def _extract_session_dream_entries(
    session_node: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> tuple[list[dict[str, Any]], list[str]]:
    metadata = session_node.get("metadata") or {}
    session_id = str(metadata.get("session_id") or session_node["id"]).replace("session:", "")
    evidence_id = session_node["id"]
    entries: list[dict[str, Any]] = []
    source_text, scanned_sources = _auto_dream_session_source_text(session_node, repo_root=repo_root)
    seen_entries: set[tuple[str, str]] = set()
    for line in source_text.splitlines():
        match = AUTO_DREAM_LINE_RE.match(line)
        if not match:
            continue
        memory_type = _normalize_dream_line_type(match.group(1))
        body = " ".join(match.group(2).split())
        if not body:
            continue
        identity = (memory_type, body)
        if identity in seen_entries:
            continue
        seen_entries.add(identity)
        entry_hash = _text_sha256(f"{evidence_id}:{memory_type}:{body}")[:12]
        entries.append(
            {
                "id": f"{session_id}-{entry_hash}",
                "type": memory_type,
                "title": _auto_dream_title(body),
                "body": body,
                "confidence": "inferred",
                "evidence": [evidence_id],
                "metadata": {
                    "target_project": DEFAULT_TENANT_ID,
                    "pathway": metadata.get("sub_tenant_id") or "operator",
                    "intended_consumer": "future_agents",
                    "retrieval_keywords": ["agent-memory", "dreaming", session_id],
                    "auto_generated_from_session": True,
                },
            }
        )
    return entries, scanned_sources


def _auto_dream_evaluate_node(
    node: dict[str, Any],
    *,
    conn: sqlite3.Connection,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    metadata = node.get("metadata") or {}
    try:
        entries = _parse_dream_entries(metadata.get("entries", []))
    except AgentControlError as exc:
        return {"decision": "reject", "reason": f"invalid dream proposal: {exc}"}
    if not entries:
        return {"decision": "reject", "reason": "dream proposal has no entries"}
    proposal_evidence = metadata.get("evidence") or []
    proposal_evidence_issue = _auto_dream_evidence_issue(
        conn,
        proposal_evidence,
        tenant_id=tenant_id,
        field_name="proposal",
        current_node_id=node["id"],
    )
    if proposal_evidence_issue:
        return {"decision": "reject", "reason": proposal_evidence_issue}
    reasons: list[str] = []
    for entry in entries:
        if entry["type"] in AUTO_DREAM_MANUAL_REVIEW_TYPES:
            reasons.append(f"{entry['id']} type {entry['type']} requires manual review")
        elif entry["type"] not in AUTO_DREAM_ALLOWED_TYPES:
            reasons.append(f"{entry['id']} type {entry['type']} is not auto-acceptable")
        if entry.get("confidence") == "observed":
            reasons.append(f"{entry['id']} uses observed confidence; auto dreams use inferred/unknown only")
        if entry.get("supersedes"):
            reasons.append(f"{entry['id']} supersedes existing memory; auto dreams do not supersede")
        entry_evidence = entry.get("evidence") or []
        if not entry_evidence:
            reasons.append(f"{entry['id']} has no entry-level evidence")
        evidence_issue = _auto_dream_evidence_issue(
            conn,
            entry_evidence,
            tenant_id=tenant_id,
            field_name=f"{entry['id']} entry",
            current_node_id=node["id"],
        )
        if evidence_issue:
            reasons.append(evidence_issue)
        text = f"{entry.get('title', '')}\n{entry.get('body', '')}\n{canonical_json(entry.get('metadata') or {})}"
        if _auto_dream_text_has_high_risk(text):
            reasons.append(f"{entry['id']} contains high-risk options/action wording")
        policy_errors = _validate_memory_policy_text(
            title=entry.get("title", ""),
            body=entry.get("body", ""),
            metadata=_with_memory_policy_metadata(entry.get("metadata") or {}, source_type="operating_memory"),
            field_name=f"{entry['id']} entry",
        )
        reasons.extend(policy_errors)
    if reasons:
        return {"decision": "reject", "reason": "; ".join(reasons)}
    return {"decision": "accept", "reason": "all entries are low-risk, evidence-backed orchestration memory"}


def _load_proposed_dream_nodes(
    conn: sqlite3.Connection,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM graph_nodes
        WHERE tenant_id = ?
        ORDER BY updated_at ASC, created_at ASC
        """,
        (tenant_id,),
    ).fetchall()
    nodes: list[dict[str, Any]] = []
    for row in rows:
        node = _row_dict(row)
        if node is None:
            continue
        metadata = node.get("metadata") or {}
        if metadata.get("source_type") != "dream_proposal":
            continue
        if metadata.get("proposal_status") != "proposed":
            continue
        nodes.append(node)
        if len(nodes) >= limit:
            break
    return nodes


def _load_auto_dream_session_nodes(
    conn: sqlite3.Connection,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM graph_nodes
        WHERE tenant_id = ?
        ORDER BY updated_at ASC, created_at ASC
        """,
        (tenant_id,),
    ).fetchall()
    nodes: list[dict[str, Any]] = []
    for row in rows:
        node = _row_dict(row)
        if node is None:
            continue
        metadata = node.get("metadata") or {}
        if metadata.get("source_type") != "session_transcript":
            continue
        try:
            extracted_entry_count = int(metadata.get("auto_dream_extracted_entry_count") or 0)
        except (TypeError, ValueError):
            extracted_entry_count = 0
        if metadata.get("auto_dream_processed_at") and (
            metadata.get("auto_dream_policy_version") == AUTO_DREAM_POLICY_VERSION
            or extracted_entry_count > 0
        ):
            continue
        nodes.append(node)
        if len(nodes) >= limit:
            break
    return nodes


def _write_auto_dream_proposal_file(
    *,
    dreams_dir: Path,
    run_id: str,
    entries: list[dict[str, Any]],
) -> Path:
    target_dir = dreams_dir / "auto"
    target_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = target_dir / f"{run_id}.json"
    payload = {
        "title": f"Automated memory dream {run_id}",
        "summary": "Deterministic extraction of explicit session lessons for future agent context.",
        "evidence": sorted({item for entry in entries for item in entry.get("evidence", [])}),
        "entries": entries,
        "metadata": {
            "automation": True,
            "auto_policy_version": AUTO_DREAM_POLICY_VERSION,
            "does_not_authorize_trading_or_evidence_mutation": True,
        },
    }
    proposal_path.write_text(pretty_json(payload) + "\n", encoding="utf-8")
    return proposal_path


def _format_dream_run_audit(result: dict[str, Any]) -> str:
    lines = [
        "# Automated Dreaming Audit",
        f"Run ID: {result.get('run_id')}",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_version')}",
        f"Started: {result.get('started_at')}",
        f"Completed: {result.get('completed_at')}",
        "",
        "# Summary",
        f"- Generated proposals: {len(result.get('generated_proposals', []))}",
        f"- Processed sessions: {len(result.get('processed_sessions', []))}",
        f"- Accepted dreams: {len(result.get('accepted', []))}",
        f"- Rejected dreams: {len(result.get('rejected', []))}",
        f"- Skipped dreams: {len(result.get('skipped', []))}",
    ]
    for key, heading in [
        ("generated_proposals", "Generated Proposals"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("skipped", "Skipped"),
    ]:
        lines.append("")
        lines.append(f"# {heading}")
        items = result.get(key, [])
        if not items:
            lines.append("- None.")
            continue
        for item in items:
            if isinstance(item, dict):
                detail = item.get("dream_node_id") or item.get("proposal_path") or item.get("id") or item.get("dream_id")
                reason = item.get("reason")
                suffix = f" - {reason}" if reason else ""
                lines.append(f"- {detail}{suffix}")
            else:
                lines.append(f"- {item}")
    lines.append("")
    lines.append("# Audit Commands")
    lines.append("- `npm run memory:dream-audit`")
    lines.append("- `npm run memory:review-dreams`")
    lines.append("- `npm run memory:audit`")
    return "\n".join(lines)


def _write_dream_run_audit_files(result: dict[str, Any], *, runs_dir: Path) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = result["run_id"]
    json_text = pretty_json(result) + "\n"
    md_text = _format_dream_run_audit(result) + "\n"
    (runs_dir / f"{run_id}.json").write_text(json_text, encoding="utf-8")
    (runs_dir / f"{run_id}.md").write_text(md_text, encoding="utf-8")
    (runs_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (runs_dir / "latest.md").write_text(md_text, encoding="utf-8")


def run_dream_cycle(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    dreams_dir: Path = DEFAULT_DREAMS_DIR,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 50,
    actor: str = "AutoDream",
    generate_from_sessions: bool = True,
    auto_resolve: bool = True,
) -> dict[str, Any]:
    started_at = utc_now()
    run_id = _short_id("DREAMRUN")
    result: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "policy_version": AUTO_DREAM_POLICY_VERSION,
        "started_at": started_at,
        "completed_at": None,
        "tenant_id": tenant_id,
        "generated_proposals": [],
        "processed_sessions": [],
        "accepted": [],
        "rejected": [],
        "skipped": [],
        "audit_paths": {
            "latest_json": str((runs_dir / "latest.json").resolve()),
            "latest_md": str((runs_dir / "latest.md").resolve()),
        },
        "safety": {
            "authority_scope": OPERATING_AUTHORITY_SCOPE,
            "does_not_authorize_trading_or_evidence_mutation": True,
            "auto_accepts_only": sorted(AUTO_DREAM_ALLOWED_TYPES),
        },
    }
    if generate_from_sessions:
        entries: list[dict[str, Any]] = []
        session_updates: list[dict[str, Any]] = []
        with closing(connect(db_path)) as conn:
            sessions = _load_auto_dream_session_nodes(conn, tenant_id=tenant_id, limit=limit)
            for session in sessions:
                session_entries, scanned_sources = _extract_session_dream_entries(session, repo_root=repo_root)
                if session_entries:
                    entries.extend(session_entries)
                source_unreadable = "transcript_file_unreadable" in scanned_sources
                if not source_unreadable:
                    session_updates.append(
                        {
                            "id": session["id"],
                            "extracted_entry_count": len(session_entries),
                            "scanned_sources": scanned_sources,
                        }
                    )
                result["processed_sessions"].append(
                    {
                        "id": session["id"],
                        "extracted_entry_count": len(session_entries),
                        "scanned_sources": scanned_sources,
                        "marked_processed": not source_unreadable,
                    }
                )
                if source_unreadable:
                    result["skipped"].append(
                        {
                            "dream_id": session["id"],
                            "dream_node_id": session["id"],
                            "reason": "session transcript source was unreadable; not marking processed",
                        }
                    )
        if entries:
            proposal_file = _write_auto_dream_proposal_file(dreams_dir=dreams_dir, run_id=run_id, entries=entries)
            proposed = propose_dream(
                db_path=db_path,
                events_path=events_path,
                proposal_path=proposal_file,
                repo_root=repo_root,
                dream_id=f"auto-{run_id}",
                title=f"Automated memory dream {run_id}",
                tenant_id=tenant_id,
                expected_sha256=_file_sha256(proposal_file),
            )
            result["generated_proposals"].append(
                {
                    "dream_id": proposed["dream_id"],
                    "dream_node_id": proposed["graph_node_id"],
                    "proposal_path": str(proposal_file.resolve()),
                    "entry_count": proposed["entry_count"],
                }
            )
        if session_updates:
            with closing(connect(db_path)) as conn, conn:
                for update in session_updates:
                    _update_graph_node_metadata(
                        conn,
                        update["id"],
                        {
                            "auto_dream_processed_at": started_at,
                            "auto_dream_extracted_entry_count": update["extracted_entry_count"],
                            "auto_dream_run_id": run_id,
                            "auto_dream_policy_version": AUTO_DREAM_POLICY_VERSION,
                            "auto_dream_scanned_sources": update["scanned_sources"],
                        },
                    )
    if auto_resolve:
        with closing(connect(db_path)) as conn:
            proposed_nodes = _load_proposed_dream_nodes(conn, tenant_id=tenant_id, limit=limit)
            evaluations = [
                (node, _auto_dream_evaluate_node(node, conn=conn, tenant_id=tenant_id))
                for node in proposed_nodes
            ]
        for node, evaluation in evaluations:
            metadata = node.get("metadata") or {}
            dream_id = str(metadata.get("dream_id") or node["id"])
            if evaluation["decision"] == "accept":
                accepted = accept_dream(
                    db_path=db_path,
                    events_path=events_path,
                    dream_id=dream_id,
                    accepted_by=actor,
                    note=f"Auto-accepted by {AUTO_DREAM_POLICY_VERSION}: {evaluation['reason']}",
                )
                result["accepted"].append(
                    {
                        "dream_id": accepted["dream_id"],
                        "dream_node_id": accepted["dream_node_id"],
                        "accepted_memory_ids": accepted["accepted_memory_ids"],
                        "reason": evaluation["reason"],
                    }
                )
            elif evaluation["decision"] == "reject":
                rejected = reject_dream(
                    db_path=db_path,
                    events_path=events_path,
                    dream_id=dream_id,
                    rejected_by=actor,
                    reason=f"Auto-rejected by {AUTO_DREAM_POLICY_VERSION}: {evaluation['reason']}",
                )
                result["rejected"].append(
                    {
                        "dream_id": rejected["dream_id"],
                        "dream_node_id": rejected["dream_node_id"],
                        "reason": evaluation["reason"],
                    }
                )
            else:
                result["skipped"].append(
                    {
                        "dream_id": dream_id,
                        "dream_node_id": node["id"],
                        "reason": evaluation.get("reason", "not resolved"),
                    }
                )
    result["completed_at"] = utc_now()
    result["status"] = "complete"
    with closing(connect(db_path)) as conn, conn:
        node = upsert_graph_node(
            conn,
            node_id=f"dream_run:{run_id}",
            kind="episode",
            title=f"Automated dreaming run {run_id}",
            body=_format_dream_run_audit(result),
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            metadata={
                "source_type": "dream_run",
                "run_id": run_id,
                "status": result["status"],
                "policy_version": AUTO_DREAM_POLICY_VERSION,
                "accepted_count": len(result["accepted"]),
                "rejected_count": len(result["rejected"]),
                "generated_count": len(result["generated_proposals"]),
                "processed_session_count": len(result["processed_sessions"]),
                **OPERATING_AUTHORITY_METADATA,
            },
            source_ref=str((runs_dir / f"{run_id}.json").resolve()),
        )
        result["graph_node_id"] = node["id"]
        _record_event(
            conn,
            events_path=events_path,
            event_type="dream.auto_run",
            payload={
                "run_id": run_id,
                "graph_node_id": node["id"],
                "accepted_count": len(result["accepted"]),
                "rejected_count": len(result["rejected"]),
                "generated_count": len(result["generated_proposals"]),
            },
        )
    _write_dream_run_audit_files(result, runs_dir=runs_dir)
    return result


def dream_audit(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 12,
) -> dict[str, Any]:
    latest_path = runs_dir / "latest.json"
    latest = None
    if latest_path.exists():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
    review = review_dreams(db_path=db_path, tenant_id=tenant_id, limit=limit)
    memory = memory_audit(db_path=db_path, tenant_id=tenant_id, limit=limit)
    return {
        "status": "pass" if latest is not None and memory["status"] == "pass" else "needs_attention",
        "latest_run": latest,
        "dream_review": {
            "status": review["status"],
            "proposed_count": len(review["proposed_dreams"]),
            "accepted_count": len(review["accepted_dreams"]),
            "open_question_count": len(review["open_questions"]),
        },
        "memory_audit": {
            "status": memory["status"],
            "checked_memories": memory["checked_memories"],
            "authority_issue_count": len(memory.get("authority_inconsistencies", [])),
            "stale_or_expired_count": len(memory.get("stale_or_expired", [])),
            "supersession_issue_count": len(memory.get("supersession_inconsistencies", [])),
            "open_blocker_count": len(memory.get("open_blockers", [])),
        },
        "recommended_commands": [
            "npm run memory:dream-run",
            "npm run memory:dream-audit",
            "npm run memory:review-dreams",
            "npm run memory:audit",
        ],
    }


def supersede_memory(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    old_node_id: str,
    new_node_id: str,
    reason: str = "",
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        _require_operating_memory_node(conn, old_node_id, field_name="old_node_id")
        _require_operating_memory_node(conn, new_node_id, field_name="new_node_id")
        updated = _supersede_memory_node(
            conn,
            old_node_id=old_node_id,
            new_node_id=new_node_id,
            reason=reason,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="memory.superseded",
            payload={"old_node_id": old_node_id, "new_node_id": new_node_id, "reason": reason},
        )
        return updated


def link_graph_nodes(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    source_node_id: str,
    relation: str,
    target_node_id: str,
    metadata: dict[str, Any] | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    if not relation.strip():
        raise AgentControlError("relation is required")
    with closing(connect(db_path)) as conn, conn:
        edge = upsert_graph_edge(
            conn,
            source_node_id=source_node_id,
            relation=relation,
            target_node_id=target_node_id,
            metadata=metadata or {},
            source_ref=source_ref,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="graph.edge.linked",
            payload={
                "edge_id": edge["id"],
                "source_node_id": source_node_id,
                "relation": relation,
                "target_node_id": target_node_id,
            },
        )
        return edge


def _seed_document_nodes(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    tenant_id: str,
    result: dict[str, Any],
) -> set[str]:
    seeded_ids: set[str] = set()
    for spec in PROJECT_SEED_FILES:
        relative_path = spec["path"]
        body = _read_repo_text(repo_root, relative_path)
        if body is None:
            result["skipped_files"].append(relative_path)
            continue
        line_count = len(body.splitlines())
        node = upsert_graph_node(
            conn,
            node_id=_path_node_id(relative_path),
            kind="knowledge",
            title=spec["title"],
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=spec["sub_tenant_id"],
            metadata={
                "path": _safe_node_path(relative_path),
                "source_type": spec["source_type"],
                "authority": spec["authority"],
                "checked_in": True,
                "content_sha256": _text_sha256(body),
                "line_count": line_count,
            },
            source_ref=_safe_node_path(relative_path),
        )
        seeded_ids.add(node["id"])
        result["documents_seeded"] += 1
    return seeded_ids


def _seed_static_memory_graph(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    tenant_id: str,
    document_node_ids: set[str],
    result: dict[str, Any],
) -> None:
    relative_path = "data/contracts/agent-memory-graph.json"
    raw = _read_repo_text(repo_root, relative_path)
    if raw is None:
        return
    try:
        graph = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"{relative_path} must be valid JSON: {exc}") from exc

    result["stale_nodes_pruned"] += _prune_seed_nodes_by_source_type(
        conn,
        tenant_id=tenant_id,
        source_types=STATIC_SEED_SOURCE_TYPES,
    )

    static_node_ids: set[str] = set()
    for item in graph.get("nodes", []):
        static_id = item.get("id")
        if not static_id:
            continue
        node_id = f"static:{static_id}"
        path = _safe_node_path(str(item.get("path", "")))
        body_parts = [
            f"Owner summary: {item.get('owner_summary', '')}",
            f"Read when: {item.get('read_when', '')}",
        ]
        if path:
            body_parts.append(f"Path: {path}")
        node = upsert_graph_node(
            conn,
            node_id=node_id,
            kind="entity",
            title=str(item.get("label") or static_id),
            body="\n".join(part for part in body_parts if part.strip()),
            tenant_id=tenant_id,
            sub_tenant_id="general",
            metadata={
                "source_type": "static_memory_graph_node",
                "static_id": static_id,
                "static_kind": item.get("kind"),
                "path": path or None,
                "read_when": item.get("read_when"),
                "runtime_use": graph.get("runtime_use", False),
            },
            source_ref=relative_path,
        )
        static_node_ids.add(node["id"])
        result["static_nodes_seeded"] += 1
        document_node_id = _path_node_id(path) if path else None
        if document_node_id and document_node_id in document_node_ids:
            upsert_graph_edge(
                conn,
                source_node_id=node["id"],
                relation="describes",
                target_node_id=document_node_id,
                metadata={"source_type": "static_memory_graph_path_link"},
                source_ref=relative_path,
            )
            result["edges_seeded"] += 1

    for item in graph.get("edges", []):
        source = f"static:{item.get('from')}"
        target = f"static:{item.get('to')}"
        if source not in static_node_ids or target not in static_node_ids:
            continue
        upsert_graph_edge(
            conn,
            source_node_id=source,
            relation=str(item.get("type") or "related_to"),
            target_node_id=target,
            metadata={
                "source_type": "static_memory_graph_edge",
                "reason": item.get("reason"),
            },
            source_ref=relative_path,
        )
        result["static_edges_seeded"] += 1
        result["edges_seeded"] += 1


def _gateboard_reason_pathway(reason: str) -> str | None:
    if reason == "broad_missed_pick_economics_negative":
        return "profitability_path"
    if reason in {"no_live_validation_lanes", "open_risk_governor_blocked_or_missing"}:
        return "promotion_path"
    if reason == "no_promotion_ready_fresh_evidence":
        return "evidence_path"
    if reason in {"no_eligible_paper_shortlist_candidates", "suggested_trade_review_attention_required"}:
        return "operator_path"
    return None


def _gateboard_sub_tenant(pathway_id: str | None) -> str:
    if pathway_id is None:
        return "operator"
    candidate = pathway_id.removesuffix("_path")
    return candidate if candidate in PATHWAYS else "operator"


def _seed_gateboard_memory(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    tenant_id: str,
    result: dict[str, Any],
) -> None:
    relative_path = "data/forward-tracking/project_operator_gateboard_latest.json"
    raw = _read_repo_text(repo_root, relative_path)
    if raw is None:
        return
    try:
        gateboard = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"{relative_path} must be valid JSON: {exc}") from exc

    result["stale_nodes_pruned"] += _prune_seed_nodes_by_source_type(
        conn,
        tenant_id=tenant_id,
        source_types=GATEBOARD_CURRENT_SOURCE_TYPES,
    )

    no_chase = gateboard.get("no_chase_manifest") or {}
    prohibited_actions = no_chase.get("prohibited_actions") or []
    gateboard_node = upsert_graph_node(
        conn,
        node_id="knowledge:gateboard:latest",
        kind="knowledge",
        title="Project operator gateboard latest",
        body="\n".join(
            [
                f"Overall status: {gateboard.get('overall_status')}",
                f"Primary message: {gateboard.get('primary_message')}",
                f"No-chase status: {no_chase.get('status')}",
                f"Prohibited actions: {', '.join(prohibited_actions)}",
            ]
        ),
        tenant_id=tenant_id,
        sub_tenant_id="operator",
        metadata={
            "path": relative_path,
            "source_type": "gateboard_latest",
            "generated_at_utc": gateboard.get("generated_at_utc"),
            "overall_status": gateboard.get("overall_status"),
            "no_chase_status": no_chase.get("status"),
            "live_policy_change": no_chase.get("live_policy_change", False),
            "runtime_use": gateboard.get("runtime_use", False),
        },
        source_ref=relative_path,
    )
    result["gateboard_seeded"] = True

    pathway_node_ids: set[str] = set()
    for pathway in gateboard.get("pathway_statuses", []):
        pathway_id = str(pathway.get("id") or "")
        if not pathway_id:
            continue
        node_id = f"entity:gateboard:pathway:{pathway_id}"
        node = upsert_graph_node(
            conn,
            node_id=node_id,
            kind="entity",
            title=str(pathway.get("label") or pathway_id),
            body="\n".join(
                [
                    str(pathway.get("headline") or ""),
                    *[str(detail) for detail in pathway.get("details", [])],
                ]
            ).strip(),
            tenant_id=tenant_id,
            sub_tenant_id=_gateboard_sub_tenant(pathway_id),
            metadata={
                "source_type": "gateboard_pathway",
                "pathway_id": pathway_id,
                "state": pathway.get("state"),
                "owner_docs": pathway.get("owner_docs", []),
                "owner_scripts": pathway.get("owner_scripts", []),
            },
            source_ref=relative_path,
        )
        pathway_node_ids.add(node["id"])
        result["gateboard_pathways_seeded"] += 1
        upsert_graph_edge(
            conn,
            source_node_id=gateboard_node["id"],
            relation="summarizes",
            target_node_id=node["id"],
            metadata={"source_type": "gateboard_pathway_edge", "state": pathway.get("state")},
            source_ref=relative_path,
        )
        result["edges_seeded"] += 1

    for reason in no_chase.get("reasons", []):
        reason_id = str(reason.get("reason") or "")
        if not reason_id:
            continue
        target_pathway = _gateboard_reason_pathway(reason_id)
        node = upsert_graph_node(
            conn,
            node_id=f"blocker:gateboard:{reason_id}",
            kind="blocker",
            title=reason_id.replace("_", " "),
            body="\n".join(
                [
                    f"Severity: {reason.get('severity')}",
                    f"Evidence: {pretty_json(reason.get('evidence') or {})}",
                ]
            ),
            tenant_id=tenant_id,
            sub_tenant_id=_gateboard_sub_tenant(target_pathway),
            metadata={
                "source_type": "gateboard_blocker",
                "reason": reason_id,
                "severity": reason.get("severity"),
                "evidence": reason.get("evidence") or {},
                "overall_status": gateboard.get("overall_status"),
            },
            source_ref=relative_path,
        )
        result["blockers_seeded"] += 1
        upsert_graph_edge(
            conn,
            source_node_id=node["id"],
            relation="blocks",
            target_node_id=gateboard_node["id"],
            metadata={"source_type": "gateboard_no_chase_reason"},
            source_ref=relative_path,
        )
        result["edges_seeded"] += 1
        target_node_id = f"entity:gateboard:pathway:{target_pathway}" if target_pathway else None
        if target_node_id and target_node_id in pathway_node_ids:
            upsert_graph_edge(
                conn,
                source_node_id=node["id"],
                relation="blocks",
                target_node_id=target_node_id,
                metadata={"source_type": "gateboard_no_chase_reason"},
                source_ref=relative_path,
            )
            result["edges_seeded"] += 1

    for key, artifact in (gateboard.get("source_artifacts") or {}).items():
        node = upsert_graph_node(
            conn,
            node_id=f"evidence_artifact:gateboard:{key}",
            kind="evidence_artifact",
            title=f"Gateboard source artifact: {key}",
            body=str(artifact.get("path") or ""),
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            metadata={
                "source_type": "gateboard_source_artifact",
                "artifact_key": key,
                "path": artifact.get("path"),
                "available": artifact.get("available"),
                "status": artifact.get("status"),
                "report_id": artifact.get("report_id"),
                "generated_at_utc": artifact.get("generated_at_utc"),
                "error": artifact.get("error"),
            },
            source_ref=relative_path,
        )
        result["source_artifacts_seeded"] += 1
        upsert_graph_edge(
            conn,
            source_node_id=gateboard_node["id"],
            relation="references",
            target_node_id=node["id"],
            metadata={"source_type": "gateboard_source_artifact_edge"},
            source_ref=relative_path,
        )
        result["edges_seeded"] += 1


def _seed_repo_file_index(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    tenant_id: str,
    document_node_ids: set[str],
    max_files: int,
    max_file_bytes: int,
    max_body_chars: int,
    result: dict[str, Any],
) -> None:
    considered = 0
    result["stale_nodes_pruned"] += _prune_seed_nodes_by_source_type(
        conn,
        tenant_id=tenant_id,
        source_types=REPO_FILE_SOURCE_TYPES,
    )
    tracked_paths = set(_git_tracked_files(repo_root))
    for relative_path in _repo_index_paths(repo_root):
        considered += 1
        if result["repo_files_seeded"] >= max_files:
            result["repo_files_skipped"] += 1
            continue
        if not _repo_file_is_indexable(repo_root, relative_path, max_file_bytes=max_file_bytes):
            result["repo_files_skipped"] += 1
            continue
        body = _read_repo_text(repo_root, relative_path)
        if body is None:
            result["repo_files_skipped"] += 1
            continue
        path = repo_root / relative_path
        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = len(body.encode("utf-8"))
        excerpt = _repo_file_excerpt(body, max_chars=max_body_chars)
        category = _repo_file_category(relative_path)
        is_tracked = relative_path in tracked_paths if tracked_paths else True
        node = upsert_graph_node(
            conn,
            node_id=_repo_file_node_id(relative_path),
            kind="knowledge",
            title=relative_path,
            body=excerpt,
            tenant_id=tenant_id,
            sub_tenant_id=category,
            metadata={
                "path": relative_path,
                "source_type": "repo_file_index",
                "category": category,
                "extension": path.suffix.lower(),
                "checked_in": is_tracked,
                "git_state": "tracked" if is_tracked else "untracked",
                "content_sha256": _text_sha256(body),
                "size_bytes": size_bytes,
                "line_count": len(body.splitlines()),
                "body_truncated": excerpt != body,
            },
            source_ref=relative_path,
        )
        result["repo_files_seeded"] += 1
        document_node_id = _path_node_id(relative_path)
        if document_node_id in document_node_ids and document_node_id != node["id"]:
            upsert_graph_edge(
                conn,
                source_node_id=node["id"],
                relation="indexes_file",
                target_node_id=document_node_id,
                metadata={"source_type": "repo_file_curated_doc_link"},
                source_ref="seed_project_memory",
            )
            result["edges_seeded"] += 1
    result["repo_files_considered"] = considered


def write_checkpoint(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    objective: str,
    scope: str = "",
    status: str = "in_progress",
    summary: str = "",
    success_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
    autonomy_level: str = DEFAULT_CHECKPOINT_AUTONOMY_LEVEL,
    next_actions: list[str] | None = None,
    verification: list[str] | None = None,
    blockers: list[str] | None = None,
    files_changed: list[str] | None = None,
    commands_run: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str = "operator",
) -> dict[str, Any]:
    status = _validate_choice(status, CHECKPOINT_STATUSES, "status")
    autonomy_level = _validate_choice(autonomy_level, PERMISSION_MODES, "autonomy_level")
    if not objective.strip():
        raise AgentControlError("objective is required")
    checkpoint_id = _short_id("checkpoint")
    checkpoint_metadata = {
        **(metadata or {}),
        "source_type": "session_checkpoint",
        "checkpoint_id": checkpoint_id,
        "objective": objective,
        "scope": scope,
        "status": status,
        "success_criteria": success_criteria or [],
        "constraints": constraints or [],
        "autonomy_level": autonomy_level,
        "next_actions": next_actions or [],
        "verification": verification or [],
        "blockers": blockers or [],
        "files_changed": files_changed or [],
        "commands_run": commands_run or [],
    }
    body = summary or objective
    with closing(connect(db_path)) as conn, conn:
        history_node = upsert_graph_node(
            conn,
            node_id=f"checkpoint:{checkpoint_id}",
            kind="episode",
            title=f"CEO checkpoint: {objective}",
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata=checkpoint_metadata,
            source_ref="checkpoint",
        )
        latest_node = upsert_graph_node(
            conn,
            node_id="checkpoint:latest",
            kind="memory",
            title=f"Latest CEO checkpoint: {objective}",
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata=checkpoint_metadata,
            source_ref=history_node["id"],
        )
        upsert_graph_edge(
            conn,
            source_node_id=latest_node["id"],
            relation="mirrors",
            target_node_id=history_node["id"],
            metadata={"source_type": "session_checkpoint_latest"},
            source_ref="checkpoint",
        )
        if conn.execute("SELECT id FROM graph_nodes WHERE id = ?", ("knowledge:gateboard:latest",)).fetchone():
            upsert_graph_edge(
                conn,
                source_node_id=latest_node["id"],
                relation="references",
                target_node_id="knowledge:gateboard:latest",
                metadata={"source_type": "session_checkpoint_gateboard_link"},
                source_ref="checkpoint",
            )
        _record_event(
            conn,
            events_path=events_path,
            event_type="checkpoint.written",
            payload={"checkpoint_id": checkpoint_id, "latest_node_id": latest_node["id"], "status": status},
        )
        latest_node["history_node_id"] = history_node["id"]
        return latest_node


def latest_checkpoint(*, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    with closing(connect(db_path)) as conn, conn:
        return _row_dict(conn.execute("SELECT * FROM graph_nodes WHERE id = ?", ("checkpoint:latest",)).fetchone())


def _latest_gateboard_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT id, title, body, metadata_json, source_ref, updated_at
        FROM graph_nodes
        WHERE metadata_json LIKE '%gateboard%'
        ORDER BY updated_at DESC
        LIMIT 50
        """
    ).fetchall()
    payload = [
        {
            "id": row["id"],
            "title": row["title"],
            "body": row["body"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "source_ref": row["source_ref"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    return _text_sha256(canonical_json(payload))


def _write_context_manifest(
    conn: sqlite3.Connection,
    *,
    result: dict[str, Any],
    manifest_dir: Path,
    kind: str,
) -> dict[str, Any]:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    context_nodes: list[dict[str, Any]] = []
    if "graph_context" in result:
        context_nodes = result.get("graph_context", {}).get("nodes", [])
    else:
        for key in [
            "active_blockers",
            "recent_decisions",
            "recent_verifications",
            "recent_artifacts",
            "worker_reports",
            "open_questions",
            "dream_lessons",
            "relevant_repo_files",
        ]:
            context_nodes.extend(result.get(key, []) or [])
    node_ids = sorted({str(node.get("id")) for node in context_nodes if node.get("id")})
    payload = {
        "kind": kind,
        "generated_at": utc_now(),
        "tenant_id": result.get("tenant_id"),
        "goal": result.get("goal") or result.get("query") or "",
        "pathway": result.get("pathway"),
        "policy_version": MEMORY_POLICY_VERSION,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "node_ids": node_ids,
        "seed_node_ids": result.get("graph_context", {}).get("seed_node_ids", []),
        "retrieval": result.get("retrieval", {}),
        "gateboard_hash": _latest_gateboard_hash(conn),
    }
    manifest_hash = _text_sha256(canonical_json(payload))[:16]
    manifest_path = manifest_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{kind}-{manifest_hash}.json"
    payload["manifest_path"] = str(manifest_path.resolve())
    manifest_path.write_text(pretty_json(payload) + "\n", encoding="utf-8")
    conn.execute(
        """
        INSERT INTO startup_runs(
            created_at, tenant_id, kind, goal, pathway, status, policy_version,
            manifest_path, gateboard_hash, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["generated_at"],
            str(payload.get("tenant_id") or DEFAULT_TENANT_ID),
            kind,
            str(payload["goal"]),
            payload.get("pathway"),
            "pass",
            MEMORY_POLICY_VERSION,
            payload["manifest_path"],
            payload["gateboard_hash"],
            canonical_json({"node_count": len(node_ids), "seed_node_count": len(payload["seed_node_ids"])}),
        ),
    )
    return payload


def seed_project_memory(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    include_static_memory_graph: bool = True,
    include_gateboard: bool = True,
    include_repo_files: bool = True,
    max_repo_files: int = DEFAULT_REPO_INDEX_MAX_FILES,
    max_repo_file_bytes: int = DEFAULT_REPO_INDEX_MAX_FILE_BYTES,
    max_repo_body_chars: int = DEFAULT_REPO_INDEX_BODY_CHARS,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    result: dict[str, Any] = {
        "repo_root": str(repo_root),
        "tenant_id": tenant_id,
        "documents_seeded": 0,
        "static_nodes_seeded": 0,
        "static_edges_seeded": 0,
        "gateboard_seeded": False,
        "gateboard_pathways_seeded": 0,
        "blockers_seeded": 0,
        "source_artifacts_seeded": 0,
        "repo_files_considered": 0,
        "repo_files_seeded": 0,
        "repo_files_skipped": 0,
        "stale_nodes_pruned": 0,
        "edges_seeded": 0,
        "skipped_files": [],
        "seed_node_id": "episode:seed:project-memory:latest",
    }
    with closing(connect(db_path)) as conn, conn:
        document_node_ids = _seed_document_nodes(
            conn,
            repo_root=repo_root,
            tenant_id=tenant_id,
            result=result,
        )
        if include_static_memory_graph:
            _seed_static_memory_graph(
                conn,
                repo_root=repo_root,
                tenant_id=tenant_id,
                document_node_ids=document_node_ids,
                result=result,
            )
        if include_gateboard:
            _seed_gateboard_memory(
                conn,
                repo_root=repo_root,
                tenant_id=tenant_id,
                result=result,
            )
        if include_repo_files:
            _seed_repo_file_index(
                conn,
                repo_root=repo_root,
                tenant_id=tenant_id,
                document_node_ids=document_node_ids,
                max_files=max_repo_files,
                max_file_bytes=max_repo_file_bytes,
                max_body_chars=max_repo_body_chars,
                result=result,
            )
        upsert_graph_node(
            conn,
            node_id=result["seed_node_id"],
            kind="episode",
            title="Project memory seed latest",
            body=pretty_json(
                {
                    "documents_seeded": result["documents_seeded"],
                    "static_nodes_seeded": result["static_nodes_seeded"],
                    "gateboard_seeded": result["gateboard_seeded"],
                    "blockers_seeded": result["blockers_seeded"],
                    "repo_files_seeded": result["repo_files_seeded"],
                    "stale_nodes_pruned": result["stale_nodes_pruned"],
                }
            ),
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            metadata={
                "source_type": "project_memory_seed",
                "repo_root": str(repo_root),
                "include_static_memory_graph": include_static_memory_graph,
                "include_gateboard": include_gateboard,
                "include_repo_files": include_repo_files,
                "skipped_files": result["skipped_files"],
            },
            source_ref="seed_project_memory",
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="seed.project_memory.completed",
            payload=result,
        )
        if manifest_dir is not None:
            result["context_manifest"] = _write_context_manifest(
                conn,
                result={
                    **result,
                    "goal": "seed project memory",
                    "pathway": "operator",
                },
                manifest_dir=manifest_dir,
                kind="seed",
            )
    return result


def bootstrap_project_context(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    seed: bool = True,
    query: str = "gateboard",
    metadata_filter: dict[str, Any] | None = None,
    max_depth: int = 1,
    max_context_nodes: int = 8,
    max_context_edges: int = 8,
    include_repo_files: bool = True,
    max_repo_files: int = DEFAULT_REPO_INDEX_MAX_FILES,
    max_repo_file_bytes: int = DEFAULT_REPO_INDEX_MAX_FILE_BYTES,
    max_repo_body_chars: int = DEFAULT_REPO_INDEX_BODY_CHARS,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    seed_result = None
    if seed:
        seed_result = seed_project_memory(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            tenant_id=tenant_id,
            include_repo_files=include_repo_files,
            max_repo_files=max_repo_files,
            max_repo_file_bytes=max_repo_file_bytes,
            max_repo_body_chars=max_repo_body_chars,
        )
    context = query_graph(
        db_path=db_path,
        query=query,
        tenant_id=tenant_id,
        metadata_filter=metadata_filter or {"source_type": "gateboard_blocker"},
        max_depth=max_depth,
        include_prompt_context=True,
        max_context_nodes=max_context_nodes,
        max_context_edges=max_context_edges,
    )
    result = {
        "repo_root": str(repo_root.resolve()),
        "tenant_id": tenant_id,
        "seed": seed_result,
        "digest": digest(db_path=db_path, recent_limit=5),
        "latest_checkpoint": latest_checkpoint(db_path=db_path),
        "context_query": {
            "query": query,
            "metadata_filter": metadata_filter or {"source_type": "gateboard_blocker"},
            "max_depth": max_depth,
        },
        "context": context,
        "recommended_next_queries": [
            {
                "purpose": "current gateboard blockers",
                "command": 'npm run agent:control -- graph query "gateboard" --metadata source_type=gateboard_blocker --max-depth 1 --context --json',
            },
            {
                "purpose": "living doc by path",
                "command": 'npm run agent:control -- graph query "PROJECT_CONTEXT" --metadata source_type=living_doc --context --json',
            },
            {
                "purpose": "static memory graph owner nodes",
                "command": 'npm run agent:control -- graph query "agent control" --metadata source_type=static_memory_graph_node --max-depth 1 --context --json',
            },
            {
                "purpose": "repo-wide file discovery",
                "command": 'npm run agent:control -- graph query "agent control" --metadata source_type=repo_file_index --include-repo-index --max-depth 0 --context --json',
            },
            {
                "purpose": "script owner discovery",
                "command": 'npm run agent:control -- graph query "checkpoint" --metadata source_type=repo_file_index --include-repo-index --metadata category=scripts --max-depth 0 --context --json',
            },
        ],
    }
    if manifest_dir is not None:
        with closing(connect(db_path)) as conn, conn:
            result["context_manifest"] = _write_context_manifest(
                conn,
                result={
                    **context,
                    "tenant_id": tenant_id,
                    "goal": query,
                    "pathway": "operator",
                },
                manifest_dir=manifest_dir,
                kind="bootstrap",
            )
    result["prompt_context"] = _format_bootstrap_context(result)
    return result


def _matches_scope(node: dict[str, Any], tenant_id: str | None, sub_tenant_id: str | None) -> bool:
    if tenant_id is not None and node["tenant_id"] != tenant_id:
        return False
    if sub_tenant_id is not None and node["sub_tenant_id"] != sub_tenant_id:
        return False
    return True


def query_graph(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    query: str,
    tenant_id: str | None = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = None,
    kind: str | None = None,
    metadata_filter: dict[str, Any] | None = None,
    memory_type: str | None = None,
    include_inactive: bool = False,
    fresh_only: bool = False,
    limit: int = 8,
    max_depth: int = 2,
    include_prompt_context: bool = False,
    max_context_nodes: int = 12,
    max_context_edges: int = 16,
    include_repo_index: bool = False,
) -> dict[str, Any]:
    query = query.strip()
    if kind is not None:
        _validate_choice(kind, GRAPH_NODE_KINDS, "kind")
    if memory_type is not None:
        _validate_choice(memory_type, OPERATING_MEMORY_TYPES, "memory_type")
    with closing(connect(db_path)) as conn, conn:
        retrieval_hits = _query_retrieval_documents(
            conn,
            query=query,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata_filter=metadata_filter,
            limit=limit,
            include_repo_index=include_repo_index,
        )
        retrieval_by_node_id = {hit["source_node_id"]: hit for hit in retrieval_hits}
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if sub_tenant_id is not None:
            clauses.append("sub_tenant_id = ?")
            params.append(sub_tenant_id)
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""
            SELECT * FROM graph_nodes
            {where}
            ORDER BY updated_at DESC
            """,
            tuple(params),
        ).fetchall()
        scored_nodes: list[tuple[int, dict[str, Any]]] = []
        seen_scored_node_ids: set[str] = set()
        for hit_index, hit in enumerate(retrieval_hits):
            node = _row_dict(
                conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (hit["source_node_id"],)).fetchone()
            )
            if node is None:
                continue
            metadata = node.get("metadata", {})
            if not include_repo_index and metadata.get("source_type") == "repo_file_index":
                continue
            if fresh_only and hit.get("freshness_status") != "current":
                continue
            if memory_type is not None and (
                metadata.get("source_type") != "operating_memory" or metadata.get("memory_type") != memory_type
            ):
                continue
            if not include_inactive and _memory_is_inactive(metadata):
                continue
            if fresh_only and _memory_is_stale(metadata):
                continue
            if not _matches_scope(node, tenant_id, sub_tenant_id):
                continue
            if kind is not None and node.get("kind") != kind:
                continue
            scored_nodes.append((10_000 - hit_index, node))
            seen_scored_node_ids.add(node["id"])
        for row in rows:
            node = _row_dict(row)
            if node is None:
                continue
            if node["id"] in seen_scored_node_ids:
                continue
            metadata = node.get("metadata", {})
            if not include_repo_index and metadata.get("source_type") == "repo_file_index":
                continue
            if memory_type is not None and (
                metadata.get("source_type") != "operating_memory" or metadata.get("memory_type") != memory_type
            ):
                continue
            if not include_inactive and _memory_is_inactive(metadata):
                continue
            if fresh_only and _memory_is_stale(metadata):
                continue
            if not _metadata_matches(metadata, metadata_filter):
                continue
            score = _score_node_for_query(node, query)
            if score is None:
                continue
            scored_nodes.append((score, node))
            seen_scored_node_ids.add(node["id"])
        scored_nodes.sort(key=lambda item: -item[0])
        seed_nodes = [node for _, node in scored_nodes[:limit]]

        node_map: dict[str, dict[str, Any]] = {node["id"]: node for node in seed_nodes}
        edge_map: dict[str, dict[str, Any]] = {}
        frontier = deque((node["id"], 0) for node in seed_nodes)
        seen_depth = {node["id"]: 0 for node in seed_nodes}
        while frontier:
            node_id, depth = frontier.popleft()
            if depth >= max_depth:
                continue
            edge_rows = conn.execute(
                """
                SELECT * FROM graph_edges
                WHERE source_node_id = ? OR target_node_id = ?
                ORDER BY created_at DESC
                """,
                (node_id, node_id),
            ).fetchall()
            for edge_row in edge_rows:
                edge = _row_dict(edge_row)
                if edge is None:
                    continue
                other_id = (
                    edge["target_node_id"]
                    if edge["source_node_id"] == node_id
                    else edge["source_node_id"]
                )
                other = _row_dict(conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (other_id,)).fetchone())
                if other is None or not _matches_scope(other, tenant_id, sub_tenant_id):
                    continue
                other_metadata = other.get("metadata", {})
                if not include_repo_index and other_metadata.get("source_type") == "repo_file_index":
                    continue
                if not include_inactive and _memory_is_inactive(other_metadata):
                    continue
                if fresh_only and _memory_is_stale(other_metadata):
                    continue
                edge_map[edge["id"]] = edge
                node_map[other["id"]] = other
                if other["id"] not in seen_depth or seen_depth[other["id"]] > depth + 1:
                    seen_depth[other["id"]] = depth + 1
                    frontier.append((other["id"], depth + 1))

        triplets = [
            {
                "source": edge["source_node_id"],
                "relation": edge["relation"],
                "target": edge["target_node_id"],
                "metadata": edge.get("metadata", {}),
            }
            for edge in edge_map.values()
        ]
        result = {
            "query": query,
            "tenant_id": tenant_id,
            "sub_tenant_id": sub_tenant_id,
            "kind": kind,
            "metadata_filter": metadata_filter or {},
            "memory_type": memory_type,
            "include_inactive": include_inactive,
            "fresh_only": fresh_only,
            "graph_context": {
                "seed_node_ids": [node["id"] for node in seed_nodes],
                "nodes": sorted((_node_for_query_result(node) for node in node_map.values()), key=lambda item: item["id"]),
                "edges": sorted(edge_map.values(), key=lambda item: item["id"]),
                "triplets": sorted(triplets, key=lambda item: (item["source"], item["relation"], item["target"])),
            },
            "retrieval": {
                "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
                "policy_version": MEMORY_POLICY_VERSION,
                "index": "retrieval_documents",
                "document_hits": retrieval_hits,
                "seed_explanations": [
                    retrieval_by_node_id.get(node["id"])
                    or {
                        "source_node_id": node["id"],
                        "source_type": _metadata_for_retrieval(node.get("metadata") or {}).get("source_type", "graph_node"),
                        "source_quality": _retrieval_source_quality(_metadata_for_retrieval(node.get("metadata") or {})),
                        "authority_scope": _metadata_for_retrieval(node.get("metadata") or {}).get("authority_scope", OPERATING_AUTHORITY_SCOPE),
                        "capability_label": _metadata_for_retrieval(node.get("metadata") or {}).get("capability_label", "coordination_only"),
                        "freshness_status": (
                            conn.execute(
                                "SELECT freshness_status FROM retrieval_documents WHERE source_node_id = ?",
                                (node["id"],),
                            ).fetchone()
                            or {"freshness_status": "current"}
                        )["freshness_status"],
                        "retrieval_tier": _retrieval_tier(
                            str(_metadata_for_retrieval(node.get("metadata") or {}).get("source_type", "graph_node")),
                            str(node.get("kind") or ""),
                        ),
                        "why": "Matched legacy graph substring scoring fallback.",
                    }
                    for node in seed_nodes
                ],
            },
        }
        if include_prompt_context:
            result["prompt_context"] = _format_graph_context(
                result,
                max_nodes=max_context_nodes,
                max_edges=max_context_edges,
            )
        return result


def _select_graph_nodes(
    conn: sqlite3.Connection,
    *,
    tenant_id: str = DEFAULT_TENANT_ID,
    sub_tenant_id: str | None = None,
    memory_type: str | None = None,
    source_type: str | None = None,
    kind: str | None = None,
    active_only: bool = True,
    limit: int = DEFAULT_CONTEXT_PACK_LIMIT,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = ?"]
    params: list[Any] = [tenant_id]
    if sub_tenant_id is not None:
        clauses.append("sub_tenant_id = ?")
        params.append(sub_tenant_id)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    rows = conn.execute(
        f"""
        SELECT * FROM graph_nodes
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    ).fetchall()
    nodes: list[dict[str, Any]] = []
    for row in rows:
        node = _row_dict(row)
        if node is None:
            continue
        metadata = node.get("metadata") or {}
        if memory_type is not None and (
            metadata.get("source_type") != "operating_memory" or metadata.get("memory_type") != memory_type
        ):
            continue
        if source_type is not None and metadata.get("source_type") != source_type:
            continue
        if active_only and _memory_is_inactive(metadata):
            continue
        nodes.append(node)
        if len(nodes) >= limit:
            break
    return nodes


def build_context_pack(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    goal: str = "",
    pathway: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = DEFAULT_CONTEXT_PACK_LIMIT,
    include_prompt_context: bool = False,
    manifest_dir: Path | None = None,
) -> dict[str, Any]:
    if pathway is not None:
        _validate_choice(pathway, PATHWAYS, "pathway")
    latest = latest_checkpoint(db_path=db_path)
    with closing(connect(db_path)) as conn, conn:
        pathway_blockers = _select_graph_nodes(
            conn,
            tenant_id=tenant_id,
            sub_tenant_id=pathway,
            memory_type="blocker",
            active_only=True,
            limit=limit,
        )
        gateboard_blockers = _select_graph_nodes(
            conn,
            tenant_id=tenant_id,
            source_type="gateboard_blocker",
            active_only=True,
            limit=max(limit, 50),
        )
        result = {
            "goal": goal,
            "tenant_id": tenant_id,
            "pathway": pathway,
            "latest_checkpoint": latest,
            "active_blockers": _dedupe_nodes([*pathway_blockers, *gateboard_blockers]),
            "recent_decisions": _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                sub_tenant_id=pathway,
                memory_type="decision",
                active_only=True,
                limit=limit,
            ),
            "recent_verifications": _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                sub_tenant_id=pathway,
                memory_type="verification",
                active_only=True,
                limit=limit,
            ),
            "recent_artifacts": _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                sub_tenant_id=pathway,
                memory_type="artifact",
                active_only=True,
                limit=limit,
            ),
            "worker_reports": _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                sub_tenant_id=pathway,
                memory_type="worker_report",
                source_type="operating_memory",
                active_only=True,
                limit=limit,
            ),
            "open_questions": _select_graph_nodes(
                conn,
                tenant_id=tenant_id,
                sub_tenant_id=pathway,
                memory_type="open_question",
                active_only=True,
                limit=limit,
            ),
            "dream_lessons": [
                node
                for node in _dedupe_nodes(
                    [
                        *_select_graph_nodes(
                            conn,
                            tenant_id=tenant_id,
                            memory_type="lesson",
                            active_only=True,
                            limit=limit,
                        ),
                        *_select_graph_nodes(
                            conn,
                            tenant_id=tenant_id,
                            memory_type="constraint",
                            active_only=True,
                            limit=limit,
                        ),
                    ]
                )
                if (node.get("metadata") or {}).get("origin") == "dreaming"
            ][:limit],
        }
    repo_query = goal or "agent control checkpoint bootstrap"
    result["relevant_repo_files"] = []
    result["recommended_commands"] = [
        "npm run memory:bootstrap",
        f'npm run memory:context -- --goal "{goal or repo_query}" --prompt-only',
        "npm run memory:operator-dashboard",
        "npm run memory:audit",
        "npm run memory:review-dreams",
        "npm run verify:memory",
        f'npm run agent:control -- graph query "{repo_query}" --include-repo-index --max-depth 0 --context --json',
    ]
    if manifest_dir is not None:
        with closing(connect(db_path)) as conn, conn:
            result["context_manifest"] = _write_context_manifest(
                conn,
                result=result,
                manifest_dir=manifest_dir,
                kind="context_pack",
            )
    if include_prompt_context:
        result["prompt_context"] = _format_context_pack(result)
    return result


def memory_audit(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 12,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    authority_inconsistencies: list[dict[str, Any]] = []
    stale_or_expired: list[dict[str, Any]] = []
    supersession_inconsistencies: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    open_blockers: list[dict[str, Any]] = []
    checked_memories = 0
    with closing(connect(db_path)) as conn, conn:
        rows = conn.execute(
            "SELECT * FROM graph_nodes WHERE tenant_id = ? ORDER BY updated_at DESC",
            (tenant_id,),
        ).fetchall()
        for row in rows:
            node = _row_dict(row)
            if node is None:
                continue
            metadata = node.get("metadata") or {}
            if not _is_operating_memory(metadata):
                continue
            checked_memories += 1
            if not _has_operating_authority_metadata(metadata):
                authority_inconsistencies.append(
                    {
                        **node,
                        "metadata": {
                            **metadata,
                            "audit_issue": (
                                "operating memory must be orchestration_only and must not authorize "
                                "trading or evidence mutation"
                            ),
                        },
                    }
                )
            policy_errors = _validate_memory_policy_text(
                title=str(node.get("title") or ""),
                body=str(node.get("body") or ""),
                metadata=_with_memory_policy_metadata(metadata, source_type="operating_memory"),
                field_name=node["id"],
            )
            if policy_errors:
                authority_inconsistencies.append(
                    {
                        **node,
                        "metadata": {
                            **metadata,
                            "audit_issue": "operating memory contains prohibited authority wording",
                            "policy_errors": policy_errors,
                        },
                    }
                )
            superseded_by = metadata.get("superseded_by")
            supersedes = metadata.get("supersedes") or []
            if isinstance(supersedes, str):
                supersedes = [supersedes]

            def add_supersession_issue(reason: str) -> None:
                issue = {**node, "metadata": {**metadata, "audit_issue": reason}}
                supersession_inconsistencies.append(issue)

            def has_supersedes_edge(source_node_id: str, target_node_id: str) -> bool:
                return conn.execute(
                    """
                    SELECT 1 FROM graph_edges
                    WHERE source_node_id = ? AND relation = ? AND target_node_id = ?
                    """,
                    (source_node_id, "supersedes", target_node_id),
                ).fetchone() is not None

            if metadata.get("memory_status") == "active" and _memory_is_stale(metadata, now=now):
                stale_or_expired.append(node)
            if superseded_by and metadata.get("memory_status") != "superseded":
                add_supersession_issue("superseded_by set but memory_status is not superseded")
            if metadata.get("memory_status") == "superseded" and not superseded_by:
                add_supersession_issue("superseded memory is missing superseded_by")
            if superseded_by:
                superseding_node = _row_dict(
                    conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (superseded_by,)).fetchone()
                )
                if superseding_node is None:
                    add_supersession_issue("superseded_by target is missing")
                else:
                    if not _is_operating_memory(superseding_node.get("metadata") or {}):
                        add_supersession_issue("superseded_by target is not operating memory")
                    if not has_supersedes_edge(str(superseded_by), node["id"]):
                        add_supersession_issue("superseded_by target is missing supersedes edge")
            for superseded_node_id in supersedes:
                superseded_node = _row_dict(
                    conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (superseded_node_id,)).fetchone()
                )
                if superseded_node is None:
                    add_supersession_issue(f"supersedes target is missing: {superseded_node_id}")
                    continue
                superseded_metadata = superseded_node.get("metadata") or {}
                if not _is_operating_memory(superseded_metadata):
                    add_supersession_issue(f"supersedes target is not operating memory: {superseded_node_id}")
                if superseded_metadata.get("superseded_by") != node["id"]:
                    add_supersession_issue(f"supersedes target missing superseded_by: {superseded_node_id}")
                if not has_supersedes_edge(node["id"], str(superseded_node_id)):
                    add_supersession_issue(f"supersedes target is missing edge: {superseded_node_id}")
            if metadata.get("memory_type") == "open_question" and not _memory_is_inactive(metadata):
                open_questions.append(node)
            if metadata.get("memory_type") == "blocker" and not _memory_is_inactive(metadata):
                open_blockers.append(node)
    issue_count = len(authority_inconsistencies) + len(stale_or_expired) + len(supersession_inconsistencies)
    result = {
        "status": "pass" if issue_count == 0 else "issues",
        "checked_memories": checked_memories,
        "authority_inconsistencies": authority_inconsistencies[:limit],
        "stale_or_expired": stale_or_expired[:limit],
        "supersession_inconsistencies": supersession_inconsistencies[:limit],
        "open_questions": open_questions[:limit],
        "open_blockers": open_blockers[:limit],
    }
    return result


def repair_operating_memory_authority_metadata(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    repaired_node_ids: list[str] = []
    skipped_policy_errors: list[dict[str, Any]] = []
    checked_memories = 0
    with closing(connect(db_path)) as conn, conn:
        rows = conn.execute(
            "SELECT id, title, body, metadata_json FROM graph_nodes WHERE tenant_id = ? ORDER BY updated_at DESC",
            (tenant_id,),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(metadata, dict) or not _is_operating_memory(metadata):
                continue
            checked_memories += 1
            candidate_metadata = _with_memory_policy_metadata(metadata, source_type="operating_memory")
            policy_errors = _validate_memory_policy_text(
                title=str(row["title"] or ""),
                body=str(row["body"] or ""),
                metadata=candidate_metadata,
                field_name=row["id"],
            )
            if policy_errors:
                skipped_policy_errors.append({"node_id": row["id"], "policy_errors": policy_errors})
                continue
            if _has_operating_authority_metadata(metadata):
                continue
            conn.execute(
                "UPDATE graph_nodes SET metadata_json = ? WHERE id = ?",
                (canonical_json(candidate_metadata), row["id"]),
            )
            repaired_node_ids.append(row["id"])
    return {
        "status": "issues" if skipped_policy_errors else ("repaired" if repaired_node_ids else "noop"),
        "checked_memories": checked_memories,
        "repaired_count": len(repaired_node_ids),
        "repaired_node_ids": repaired_node_ids,
        "skipped_policy_errors": skipped_policy_errors,
    }


def memory_eval(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    seed: bool = True,
    require_checkpoint: bool = False,
) -> dict[str, Any]:
    seed_result = None
    if seed:
        seed_result = seed_project_memory(
            db_path=db_path,
            events_path=events_path,
            repo_root=repo_root,
            tenant_id=tenant_id,
        )
    checkpoint = latest_checkpoint(db_path=db_path)
    gateboard = query_graph(
        db_path=db_path,
        query="gateboard",
        tenant_id=tenant_id,
        metadata_filter={"source_type": "gateboard_blocker"},
        limit=5,
        max_depth=1,
        include_prompt_context=True,
    )
    repo_files = query_graph(
        db_path=db_path,
        query="agent control",
        tenant_id=tenant_id,
        metadata_filter={"source_type": "repo_file_index"},
        limit=5,
        max_depth=0,
        include_repo_index=True,
    )
    context_pack = build_context_pack(
        db_path=db_path,
        goal="agent control",
        tenant_id=tenant_id,
        limit=5,
        include_prompt_context=True,
    )
    audit = memory_audit(db_path=db_path, tenant_id=tenant_id)
    with closing(connect(db_path)) as conn:
        retrieval_count = conn.execute("SELECT count(*) FROM retrieval_documents").fetchone()[0]
        outbox_count = conn.execute("SELECT count(*) FROM event_outbox").fetchone()[0]
    gateboard_blocker_ids = gateboard["graph_context"]["seed_node_ids"]
    if seed_result is not None:
        expected_gateboard_blockers = int(seed_result.get("blockers_seeded") or 0)
        if not seed_result.get("gateboard_seeded"):
            gateboard_recovered = False
            gateboard_detail = "gateboard not seeded"
        else:
            gateboard_recovered = bool(gateboard_blocker_ids) if expected_gateboard_blockers else True
            gateboard_detail = (
                ",".join(gateboard_blocker_ids[:5])
                if gateboard_blocker_ids
                else "no current gateboard blockers"
            )
    else:
        gateboard_recovered = bool(gateboard_blocker_ids)
        gateboard_detail = ",".join(gateboard_blocker_ids[:5])
    checks = [
        {
            "name": "latest checkpoint exists",
            "pass": checkpoint is not None or not require_checkpoint,
            "detail": checkpoint["metadata"].get("objective") if checkpoint else "not required",
        },
        {
            "name": "checkpoint autonomy fails closed",
            "pass": (
                checkpoint is None and not require_checkpoint
            ) or checkpoint is not None and checkpoint.get("metadata", {}).get("autonomy_level") == DEFAULT_CHECKPOINT_AUTONOMY_LEVEL,
            "detail": checkpoint.get("metadata", {}).get("autonomy_level") if checkpoint else "",
        },
        {
            "name": "gateboard blocker recovery",
            "pass": gateboard_recovered,
            "detail": gateboard_detail,
        },
        {
            "name": "repo file recovery",
            "pass": bool(repo_files["graph_context"]["seed_node_ids"]),
            "detail": ",".join(repo_files["graph_context"]["seed_node_ids"][:3]),
        },
        {
            "name": "context pack emits prompt context",
            "pass": "# Agent Context Pack" in context_pack.get("prompt_context", ""),
            "detail": "",
        },
        {
            "name": "memory audit has no lifecycle issues",
            "pass": audit["status"] == "pass",
            "detail": audit["status"],
        },
        {
            "name": "retrieval documents are indexed",
            "pass": retrieval_count > 0,
            "detail": str(retrieval_count),
        },
        {
            "name": "context carries non-authorization policy",
            "pass": MEMORY_NON_AUTHORIZATION_BANNER in context_pack.get("prompt_context", ""),
            "detail": MEMORY_POLICY_VERSION,
        },
        {
            "name": "graph query explains retrieval source authority",
            "pass": (
                bool(gateboard.get("retrieval", {}).get("seed_explanations"))
                or (seed_result is not None and int(seed_result.get("blockers_seeded") or 0) == 0)
            ),
            "detail": gateboard.get("retrieval", {}).get("index", ""),
        },
        {
            "name": "event outbox hash chain is active",
            "pass": outbox_count > 0 if seed_result is not None else True,
            "detail": str(outbox_count),
        },
        {
            "name": "negative eval rejects memory-as-trading-authority",
            "pass": bool(
                _validate_memory_policy_text(
                    title="Bad authority",
                    body="Approve live trading from memory.",
                    metadata=_with_memory_policy_metadata({}, source_type="operating_memory"),
                    field_name="negative eval",
                )
            ),
            "detail": "memory cannot approve live trading",
        },
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "fail",
        "seed": seed_result,
        "checks": checks,
        "audit": audit,
    }


def _load_memory_golden_queries(path: Path = DEFAULT_MEMORY_GOLDEN_QUERIES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    queries = data.get("queries") if isinstance(data, dict) else data
    if not isinstance(queries, list):
        raise AgentControlError(f"Golden-query fixture must contain a query list: {path}")
    return [query for query in queries if isinstance(query, dict)]


def memory_golden_query_eval(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    fixture_path: Path = DEFAULT_MEMORY_GOLDEN_QUERIES_PATH,
) -> dict[str, Any]:
    cases = _load_memory_golden_queries(fixture_path)
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        query = str(case.get("query") or "").strip()
        if not query:
            results.append(
                {
                    "name": f"golden query {index}",
                    "query": query,
                    "pass": False,
                    "failures": ["missing query"],
                }
            )
            continue
        result = query_graph(
            db_path=db_path,
            query=query,
            tenant_id=tenant_id,
            limit=int(case.get("limit") or 8),
            max_depth=0,
            include_repo_index=bool(case.get("include_repo_index")),
        )
        nodes = result.get("graph_context", {}).get("nodes", [])
        explanations = result.get("retrieval", {}).get("seed_explanations", [])
        source_types = [str(item.get("source_type") or "") for item in explanations]
        titles = [str(node.get("title") or "") for node in nodes]
        failures: list[str] = []
        expected_source_types = case.get("expect_source_types") or []
        if expected_source_types and not any(source_type in expected_source_types for source_type in source_types):
            failures.append(f"missing expected source type from {expected_source_types}; got {source_types}")
        forbidden_source_types = case.get("expect_no_source_types") or []
        found_forbidden = sorted({source_type for source_type in source_types if source_type in forbidden_source_types})
        if found_forbidden:
            failures.append(f"returned forbidden source types: {found_forbidden}")
        title_needles = [str(needle).lower() for needle in case.get("expect_title_contains_any") or []]
        if title_needles and not any(
            needle in title.lower() for needle in title_needles for title in titles
        ):
            failures.append(f"missing title containing any of {title_needles}; got {titles}")
        results.append(
            {
                "name": str(case.get("name") or f"golden query {index}"),
                "query": query,
                "pass": not failures,
                "failures": failures,
                "source_types": source_types,
                "seed_node_ids": result.get("graph_context", {}).get("seed_node_ids", []),
            }
        )
    return {
        "status": "pass" if all(result["pass"] for result in results) else "fail",
        "fixture_path": str(fixture_path),
        "query_count": len(results),
        "results": results,
    }


def _write_agent_eval_fixture_repo(repo_root: Path) -> None:
    for relative_path in [
        "AGENTS.md",
        "README.md",
        "docs/index.md",
        "docs/PROJECT_CONTEXT.md",
        "docs/DECISIONS.md",
        "docs/NEXT_STEPS.md",
        "docs/agent-control-plane.md",
        "docs/agent-memory-graph.md",
        "docs/project-operator-gateboard.md",
        "package.json",
    ]:
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative_path}\nagent eval fixture\n", encoding="utf-8")
    graph_path = repo_root / "data" / "contracts" / "agent-memory-graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(canonical_json({"runtime_use": False, "nodes": [], "edges": []}), encoding="utf-8")
    gateboard_path = repo_root / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
    gateboard_path.parent.mkdir(parents=True, exist_ok=True)
    gateboard_path.write_text(
        canonical_json(
            {
                "generated_at_utc": "2026-06-29T00:00:00Z",
                "runtime_use": False,
                "overall_status": "safe_blocked_no_live_release",
                "primary_message": "Agent eval fixture blocker.",
                "no_chase_manifest": {
                    "status": "no_chase_active",
                    "live_policy_change": False,
                    "prohibited_actions": [],
                    "reasons": [
                        {
                            "reason": "agent_eval_fixture_blocker",
                            "severity": "block_new_scanner_origin_entries",
                            "evidence": {"status": "fixture"},
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def agent_eval_harness(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    seed: bool = True,
) -> dict[str, Any]:
    memory_eval_result = memory_eval(
        db_path=db_path,
        events_path=events_path,
        repo_root=repo_root,
        tenant_id=tenant_id,
        seed=seed,
    )
    golden_query_result = memory_golden_query_eval(
        db_path=db_path,
        tenant_id=tenant_id,
        fixture_path=repo_root / "data" / "contracts" / "memory-golden-queries.json",
    )
    live_ledger = agent_run_ledger_report(db_path=db_path, tenant_id=tenant_id, limit=20)
    self_checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="agent-eval-") as tmp_name:
        tmp_root = Path(tmp_name)
        fixture_repo = tmp_root / "repo"
        fixture_db = tmp_root / "agent_control.db"
        fixture_events = tmp_root / "events.jsonl"
        fixture_runs = tmp_root / "dream-runs"
        _write_agent_eval_fixture_repo(fixture_repo)
        seed_project_memory(
            db_path=fixture_db,
            events_path=fixture_events,
            repo_root=fixture_repo,
            tenant_id=tenant_id,
        )
        started = record_agent_run_event(
            db_path=fixture_db,
            events_path=fixture_events,
            run_id="RUN-agent-eval",
            event_type="started",
            title="Eval token sk-agentEvalSecret123",
            summary="Eval run started.",
            tenant_id=tenant_id,
            payload={"api_key": "secret"},
        )
        record_agent_run_event(
            db_path=fixture_db,
            events_path=fixture_events,
            run_id="RUN-agent-eval",
            event_type="approval_requested",
            summary="Eval pending approval note.",
            tenant_id=tenant_id,
            payload={"approval_scope": "eval_only"},
        )
        record_agent_run_event(
            db_path=fixture_db,
            events_path=fixture_events,
            run_id="RUN-agent-eval",
            event_type="blocked",
            summary="Eval blocked self-test.",
            tenant_id=tenant_id,
            payload={"blocker_code": "agent_eval_fixture"},
        )
        fixture_ledger = agent_run_ledger_report(db_path=fixture_db, tenant_id=tenant_id)
        fixture_brief = daily_operator_brief(
            db_path=fixture_db,
            runs_dir=fixture_runs,
            tenant_id=tenant_id,
            since_hours=24,
            limit=10,
        )
        self_checks.extend(
            [
                {
                    "name": "ledger self-test audit passes",
                    "pass": fixture_ledger.get("status") == "pass",
                    "detail": fixture_ledger.get("status"),
                },
                {
                    "name": "ledger redacts secrets before storage",
                    "pass": AGENT_RUN_REDACTED in started["title"] and started["payload"]["api_key"] == AGENT_RUN_REDACTED,
                    "detail": started["title"],
                },
                {
                    "name": "daily brief surfaces blocked run",
                    "pass": any(run["run_id"] == "RUN-agent-eval" for run in fixture_brief.get("attention_runs", [])),
                    "detail": fixture_brief.get("status"),
                },
                {
                    "name": "daily brief keeps approval notes non-authoritative",
                    "pass": any(
                        approval.get("run_id") == "RUN-agent-eval" and approval.get("non_authoritative")
                        for approval in fixture_brief.get("pending_approvals", [])
                    ),
                    "detail": str(len(fixture_brief.get("pending_approvals", []))),
                },
            ]
        )
    checks = [
        {
            "name": "existing memory eval passes",
            "pass": memory_eval_result.get("status") == "pass",
            "detail": memory_eval_result.get("status"),
        },
        {
            "name": "live agent run ledger audit passes",
            "pass": live_ledger.get("status") == "pass",
            "detail": (live_ledger.get("audit") or {}).get("status"),
        },
        {
            "name": "non-authorization policy present",
            "pass": any(
                check.get("name") == "context carries non-authorization policy" and check.get("pass")
                for check in memory_eval_result.get("checks", [])
            ),
            "detail": MEMORY_POLICY_VERSION,
        },
        {
            "name": "golden-query retrieval eval passes",
            "pass": golden_query_result.get("status") == "pass",
            "detail": f"{golden_query_result.get('query_count')} queries",
        },
        *self_checks,
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "fail",
        "tenant_id": tenant_id,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "checks": checks,
        "memory_eval": memory_eval_result,
        "golden_query_eval": golden_query_result,
        "agent_run_ledger": live_ledger,
        "recommended_commands": [
            "npm run memory:agent-eval",
            "npm run memory:daily-brief",
            "npm run memory:run-ledger",
            "npm run verify:agent-control",
        ],
    }


def _format_agent_eval_harness(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Eval Harness",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Checks",
    ]
    for check in result.get("checks", []):
        marker = "PASS" if check.get("pass") else "FAIL"
        detail = f" - {check.get('detail')}" if check.get("detail") else ""
        lines.append(f"- {marker}: {check.get('name')}{detail}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def operator_dashboard(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    runs_dir: Path = DEFAULT_DREAM_RUNS_DIR,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 8,
) -> dict[str, Any]:
    audit = memory_audit(db_path=db_path, tenant_id=tenant_id, limit=limit)
    dreams = dream_audit(db_path=db_path, runs_dir=runs_dir, tenant_id=tenant_id, limit=limit)
    eval_result = memory_eval(db_path=db_path, tenant_id=tenant_id, seed=False)
    with closing(connect(db_path)) as conn:
        outbox_audit = validate_event_outbox(conn)
        counts = {
            "graph_nodes": conn.execute("SELECT count(*) FROM graph_nodes WHERE tenant_id = ?", (tenant_id,)).fetchone()[0],
            "retrieval_documents": conn.execute(
                """
                SELECT count(*)
                FROM retrieval_documents d
                JOIN graph_nodes n ON n.id = d.source_node_id
                WHERE n.tenant_id = ?
                """,
                (tenant_id,),
            ).fetchone()[0],
            "event_outbox": outbox_audit["count"],
            "zero_candidate_episodes": conn.execute(
                "SELECT count(*) FROM zero_candidate_episodes WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()[0],
            "strategy_hypotheses": conn.execute(
                "SELECT count(*) FROM strategy_hypotheses WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()[0],
            "experiment_runs": conn.execute(
                "SELECT count(*) FROM experiment_runs WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()[0],
        }
        latest_startup = _row_dict(
            conn.execute(
                "SELECT * FROM startup_runs WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
        )
        latest_seed = _row_dict(
            conn.execute(
                "SELECT * FROM graph_nodes WHERE id = ?",
                ("episode:seed:project-memory:latest",),
            ).fetchone()
        )
    checks = [
        {"name": "memory audit", "pass": audit["status"] == "pass", "detail": audit["status"]},
        {"name": "dream auto-resolution", "pass": dreams["status"] == "pass", "detail": dreams["status"]},
        {
            "name": "startup/context manifest",
            "pass": latest_startup is not None and bool(latest_startup.get("manifest_path")),
            "detail": latest_startup.get("manifest_path") if latest_startup else "missing",
        },
        {
            "name": "retrieval index",
            "pass": counts["retrieval_documents"] > 0,
            "detail": str(counts["retrieval_documents"]),
        },
        {
            "name": "outbox hash chain",
            "pass": outbox_audit["count"] > 0 and outbox_audit["status"] == "pass",
            "detail": f"{outbox_audit['count']} rows; {outbox_audit['status']}",
        },
        {
            "name": "memory eval",
            "pass": eval_result["status"] == "pass",
            "detail": eval_result["status"],
        },
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "needs_attention",
        "policy_version": MEMORY_POLICY_VERSION,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "checks": checks,
        "counts": counts,
        "latest_startup": latest_startup,
        "latest_seed": latest_seed,
        "event_outbox_audit": outbox_audit,
        "memory_audit": audit,
        "dream_audit": dreams,
        "memory_eval": eval_result,
        "recommended_commands": [
            "npm run memory:bootstrap",
            "npm run memory:dream-run",
            "npm run memory:dream-audit",
            "npm run memory:operator-dashboard",
            "npm run memory:research-priorities",
            "npm run verify:memory",
        ],
    }


def _format_operator_dashboard(result: dict[str, Any]) -> str:
    lines = [
        "# Memory Operator Dashboard",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_version')}",
        f"Non-authorization: {result.get('policy_banner')}",
        "",
        "# Checks",
    ]
    for check in result.get("checks", []):
        marker = "PASS" if check.get("pass") else "FAIL"
        detail = f" - {check.get('detail')}" if check.get("detail") else ""
        lines.append(f"- {marker}: {check.get('name')}{detail}")
    lines.append("")
    lines.append("# Counts")
    for key, value in sorted((result.get("counts") or {}).items()):
        lines.append(f"- {key}: {value}")
    latest_startup = result.get("latest_startup")
    lines.append("")
    lines.append("# Latest Startup")
    if latest_startup:
        lines.append(f"- {latest_startup.get('created_at')} {latest_startup.get('kind')} {latest_startup.get('status')}")
        if latest_startup.get("manifest_path"):
            lines.append(f"- manifest: {latest_startup.get('manifest_path')}")
    else:
        lines.append("- None.")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def record_zero_candidate_episode(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    lane: str,
    selection_date: str,
    drop_stage_counts: dict[str, Any] | None = None,
    blocker_summary: str = "",
    source_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    if not lane.strip():
        raise AgentControlError("lane is required")
    if not selection_date.strip():
        raise AgentControlError("selection_date is required")
    episode_id = episode_id or f"zero:{_safe_node_path(lane)}:{selection_date}:{uuid.uuid4().hex[:8]}"
    safe_metadata = _with_memory_policy_metadata(
        {
            **(metadata or {}),
            "provenance_kind": "zero_candidate_episode",
            "tenant_id": tenant_id,
            "lane": lane,
            "selection_date": selection_date,
            "drop_stage_counts": drop_stage_counts or {},
        },
        source_type="research_provenance",
        source_quality="research_provenance",
    )
    _assert_memory_policy_valid(
        title=f"Zero candidate episode: {lane} {selection_date}",
        body=blocker_summary,
        metadata=safe_metadata,
        field_name="zero candidate episode",
    )
    with closing(connect(db_path)) as conn, conn:
        existing_episode = conn.execute(
            "SELECT tenant_id FROM zero_candidate_episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()
        if existing_episode is not None and existing_episode["tenant_id"] != tenant_id:
            raise AgentControlError(
                f"Zero candidate episode {episode_id} already belongs to tenant {existing_episode['tenant_id']}; "
                f"refusing cross-tenant overwrite by {tenant_id}"
            )
        conn.execute(
            """
            INSERT INTO zero_candidate_episodes(
                id, created_at, tenant_id, lane, selection_date, drop_stage_counts_json,
                blocker_summary, source_ref, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tenant_id = excluded.tenant_id,
                drop_stage_counts_json = excluded.drop_stage_counts_json,
                blocker_summary = excluded.blocker_summary,
                source_ref = excluded.source_ref,
                metadata_json = excluded.metadata_json
            """,
            (
                episode_id,
                utc_now(),
                tenant_id,
                lane,
                selection_date,
                canonical_json(drop_stage_counts or {}),
                blocker_summary,
                source_ref,
                canonical_json(safe_metadata),
            ),
        )
        node = upsert_graph_node(
            conn,
            node_id=f"provenance:{episode_id}",
            kind="episode",
            title=f"Zero candidate episode: {lane} {selection_date}",
            body=blocker_summary or canonical_json(drop_stage_counts or {}),
            tenant_id=tenant_id,
            sub_tenant_id="profitability",
            metadata=safe_metadata,
            source_ref=source_ref,
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="provenance.zero_candidate.recorded",
            payload={"id": episode_id, "graph_node_id": node["id"], "lane": lane, "selection_date": selection_date},
        )
    return {
        "id": episode_id,
        "graph_node_id": f"provenance:{episode_id}",
        "lane": lane,
        "selection_date": selection_date,
        "drop_stage_counts": drop_stage_counts or {},
        "blocker_summary": blocker_summary,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
    }


def research_priority_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 10,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        zero_rows = conn.execute(
            """
            SELECT * FROM zero_candidate_episodes
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            """,
            (tenant_id,),
        ).fetchall()
        hypothesis_rows = conn.execute(
            """
            SELECT * FROM strategy_hypotheses
            WHERE tenant_id = ?
            ORDER BY priority_score DESC, updated_at DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
    zero_episodes = []
    for row in zero_rows:
        counts = json.loads(row["drop_stage_counts_json"] or "{}")
        total_drops = 0
        for value in counts.values():
            try:
                total_drops += int(value)
            except (TypeError, ValueError):
                continue
        zero_episodes.append(
            {
                "id": row["id"],
                "lane": row["lane"],
                "selection_date": row["selection_date"],
                "drop_stage_counts": counts,
                "total_drops": total_drops,
                "blocker_summary": row["blocker_summary"],
                "source_ref": row["source_ref"],
                "priority_reason": "Highest recent zero-candidate drop counts should guide research-only diagnosis.",
            }
        )
    zero_episodes.sort(key=lambda item: (-int(item["total_drops"]), item["selection_date"], item["lane"]))
    hypotheses = []
    for row in hypothesis_rows:
        hypotheses.append(
            {
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "priority_score": row["priority_score"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
        )
    return {
        "status": "ready" if zero_episodes or hypotheses else "empty",
        "tenant_id": tenant_id,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "zero_candidate_priorities": zero_episodes[:limit],
        "hypothesis_priorities": hypotheses,
        "recommended_commands": [
            "npm run memory:operator-dashboard",
            "npm run memory:context -- --goal \"research provenance\" --pathway profitability --prompt-only",
            "npm run verify:memory",
        ],
    }


def _format_research_priority_report(result: dict[str, Any]) -> str:
    lines = [
        "# Research Priority Report",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Zero Candidate Priorities",
    ]
    if not result.get("zero_candidate_priorities"):
        lines.append("- None.")
    for item in result.get("zero_candidate_priorities", []):
        lines.append(
            f"- {item['lane']} {item['selection_date']} drops={item['total_drops']} source={item.get('source_ref') or ''}"
        )
        if item.get("blocker_summary"):
            lines.append(f"  blocker: {_truncate(item['blocker_summary'], 220)}")
    lines.append("")
    lines.append("# Hypothesis Priorities")
    if not result.get("hypothesis_priorities"):
        lines.append("- None.")
    for item in result.get("hypothesis_priorities", []):
        lines.append(f"- {item['id']} score={item['priority_score']} status={item['status']} {item['title']}")
    lines.append("")
    lines.append("# Recommended Commands")
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _first_string_field(payload: Any, names: tuple[str, ...]) -> str | None:
    if isinstance(payload, dict):
        for name in names:
            value = payload.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _first_string_field(value, names)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _first_string_field(item, names)
            if found:
                return found
    return None


def _collect_named_values(payload: Any, names: set[str], *, limit: int = 80) -> list[Any]:
    values: list[Any] = []

    def visit(value: Any) -> None:
        if len(values) >= limit:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if key in names:
                    values.append(child)
                    if len(values) >= limit:
                        return
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
                if len(values) >= limit:
                    return

    visit(payload)
    return values


def _flatten_strings(value: Any, *, limit: int = 80) -> list[str]:
    strings: list[str] = []

    def visit(item: Any) -> None:
        if len(strings) >= limit:
            return
        if isinstance(item, str):
            if item.strip():
                strings.append(item.strip())
        elif isinstance(item, dict):
            for key in ("reason", "status", "blocker", "stage", "classification", "branch_id", "id"):
                child = item.get(key)
                if isinstance(child, str) and child.strip():
                    strings.append(child.strip())
                    if len(strings) >= limit:
                        return
            for child in item.values():
                visit(child)
                if len(strings) >= limit:
                    return
        elif isinstance(item, list):
            for child in item:
                visit(child)
                if len(strings) >= limit:
                    return

    visit(value)
    return strings[:limit]


def _safe_identifier(value: str, *, fallback: str = "unknown") -> str:
    safe = re.sub(r"[^a-z0-9_./:-]+", "-", str(value).lower()).strip("-")
    safe = safe.replace("/", "-").replace(".", "-").replace(":", "-")
    return safe[:96] or fallback


def _dedupe_strings(values: list[str], *, limit: int = 12) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _safe_profit_learning_metadata(metadata: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    allowed = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "prohibited_actions",
            "deferred_actions",
            "safety_flags",
            "future_operator_checklist",
            "validation",
        }
    }
    allowed["research_only"] = True
    allowed["promotion_allowed"] = False
    return _with_memory_policy_metadata(
        allowed,
        source_type=source_type,
        source_quality="generated_readback",
    )


def _artifact_status(payload: dict[str, Any]) -> str:
    return _safe_profit_learning_status(
        _first_string_field(
            payload,
            (
                "overall_status",
                "status",
                "fresh_forward_capture_status",
                "completion_status",
                "stager_status",
                "report_status",
            ),
        )
        or "loaded"
    )


def _safe_profit_learning_status(value: Any) -> str:
    text = str(value or "loaded").strip()
    token = _safe_identifier(text)
    token_parts = {part for part in re.split(r"[^a-z0-9]+", token.lower()) if part}
    if token in PROFIT_LEARNING_AUTHORITY_STATUS_TOKENS or token_parts & PROFIT_LEARNING_AUTHORITY_STATUS_TOKENS:
        return "generated_readback_status_omitted_authority_like"
    return text or "loaded"


def _profit_learning_semantic_key(value: str, *, fallback: str = "unknown") -> str:
    safe = _safe_identifier(value, fallback=fallback)
    digest = _text_sha256(str(value or fallback))[:10]
    return f"{safe[:72]}-{digest}"


def _artifact_generated_at(payload: dict[str, Any]) -> str | None:
    raw = _first_string_field(payload, ("generated_at_utc", "generated_at", "created_at", "timestamp_utc"))
    if not raw:
        return None
    parsed = _parse_utc(raw)
    if parsed is None:
        return None
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _artifact_blockers(payload: dict[str, Any], *, limit: int = 16) -> list[str]:
    blockers = []
    for value in _collect_named_values(
        payload,
        {
            "blockers",
            "reason_codes",
            "reasons",
            "dependency_blockers",
            "warning_states",
            "stager_rejected_counts",
            "scheduled_phase2_eligibility_blocker_counts",
            "scheduled_phase2_drop_counts",
        },
    ):
        blockers.extend(_flatten_strings(value, limit=limit * 2))
    zero = payload.get("zero_candidate_diagnostics")
    if isinstance(zero, dict):
        status = _safe_profit_learning_status(zero.get("status"))
        if status and status != "loaded":
            blockers.append(f"zero_candidate_status:{status}")
    summary = payload.get("scheduled_phase2_drop_stage_summary")
    if isinstance(summary, dict):
        status = _safe_profit_learning_status(summary.get("status"))
        if status and status != "loaded":
            blockers.append(f"drop_stage_status:{status}")
    return _dedupe_strings(blockers, limit=limit)


def _copy_nested_value(payload: dict[str, Any], dotted_key: str) -> Any:
    value: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _artifact_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "strict_forward_rows",
        "required_rows",
        "candidate_rows_staged",
        "target_date_phase2_scan_pick_count",
        "scheduled_phase2_drop_count_total",
        "scheduled_scan_session_count",
    )
    result = {key: payload[key] for key in keys if key in payload}
    omitted_count = sum(1 for key in PROFIT_LEARNING_OMIT_METRIC_KEYS if key in payload)
    for key in PROFIT_LEARNING_DENOMINATOR_KEYS:
        value = _copy_nested_value(payload, key)
        if value is not None:
            result[key] = value
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in PROFIT_LEARNING_DENOMINATOR_KEYS:
            if key in summary:
                result[key] = summary[key]
        for key in (
            "tier_counts",
            "selection_readiness_counts",
            "repair_actionability_counts",
            "fresh_scan_guardrail_decision_counts",
        ):
            if key in summary:
                result[key] = summary[key]
    phase2 = payload.get("phase2_forward_report")
    if isinstance(phase2, dict):
        counts = phase2.get("counts")
        if isinstance(counts, dict):
            for key in ("total_natural_selections", "exact_completed_forward_pnl_count", "remaining_rows"):
                if key in counts:
                    result[key] = counts[key]
        if "denominator_rule" in phase2:
            result["denominator_rule"] = phase2["denominator_rule"]
    zero = payload.get("zero_candidate_diagnostics")
    if isinstance(zero, dict):
        for key in (
            "drop_count_total",
            "returned_picks",
            "candidate_rows_staged",
            "scheduled_scan_picks_count",
            "scheduled_sessions_reviewed",
        ):
            if key in zero:
                result[f"zero_candidate_{key}"] = zero[key]
    if omitted_count:
        result["omitted_authority_metric_count"] = omitted_count
    return result


def _profit_learning_denominator_terms(metrics: dict[str, Any], *, limit: int = 8) -> list[str]:
    terms: list[str] = []
    for key in PROFIT_LEARNING_DENOMINATOR_KEYS:
        if key in metrics:
            value = metrics[key]
            if isinstance(value, (dict, list)):
                terms.append(f"{key}:{_truncate(canonical_json(value), 120)}")
            else:
                terms.append(f"{key}:{value}")
        if len(terms) >= limit:
            break
    return terms


def _assert_profit_learning_write_paths(*, repo_root: Path, db_path: Path, events_path: Path) -> tuple[Path, Path]:
    allowed_dir = (repo_root / "data" / "agent-control").resolve()

    def resolve_path(path: Path, label: str) -> Path:
        resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
        if resolved != allowed_dir and allowed_dir not in resolved.parents:
            raise AgentControlError(f"profit-learning {label} writes must stay under data/agent-control: {path}")
        return resolved

    return resolve_path(db_path, "db"), resolve_path(events_path, "event")


def _profit_learning_source_artifacts(repo_root: Path, artifact_names: list[str] | None = None) -> list[dict[str, Any]]:
    selected_names = artifact_names or list(PROFIT_LEARNING_ARTIFACTS)
    unknown = sorted(set(selected_names) - set(PROFIT_LEARNING_ARTIFACTS))
    if unknown:
        raise AgentControlError(f"unknown profit-learning artifact(s): {', '.join(unknown)}")
    artifacts: list[dict[str, Any]] = []
    for name in selected_names:
        relative_path = PROFIT_LEARNING_ARTIFACTS[name]
        path = _resolve_inside_repo(repo_root, Path(relative_path))
        item: dict[str, Any] = {
            "artifact_kind": name,
            "source_ref": _safe_node_path(relative_path),
            "path": path,
            "exists": path.is_file(),
        }
        if not path.is_file():
            item["status"] = "missing"
            item["error"] = "source artifact is missing"
            artifacts.append(item)
            continue
        item["source_sha256"] = _file_sha256(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            item["status"] = "malformed"
            item["error"] = f"source artifact is malformed JSON: {exc}"
            artifacts.append(item)
            continue
        if not isinstance(payload, dict):
            item["status"] = "malformed"
            item["error"] = "source artifact root must be a JSON object"
            artifacts.append(item)
            continue
        generated_at = _artifact_generated_at(payload)
        if not generated_at:
            item["status"] = "stale_or_unknown"
            item["error"] = "source artifact is missing generated timestamp"
            artifacts.append(item)
            continue
        item["status"] = "loaded"
        item["payload"] = payload
        item["artifact_status"] = _artifact_status(payload)
        item["generated_at_utc"] = generated_at
        item["blockers"] = _artifact_blockers(payload)
        item["metrics"] = _artifact_metrics(payload)
        artifacts.append(item)
    return artifacts


def _profit_learning_base_metadata(artifact: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = {
        "provenance_kind": "profit_learning_sync",
        "artifact_kind": artifact["artifact_kind"],
        "source_ref": artifact["source_ref"],
        "source_sha256": artifact.get("source_sha256"),
        "artifact_generated_at": artifact.get("generated_at_utc"),
        "artifact_status": artifact.get("artifact_status"),
        "extractor_version": PROFIT_LEARNING_EXTRACTOR_VERSION,
        "sync_scope": "research_only",
        "blocker_count": len(artifact.get("blockers") or []),
    }
    if extra:
        metadata.update(extra)
    return _safe_profit_learning_metadata(metadata, source_type="profit_learning_sync")


def _profit_learning_experiment_records(artifacts: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    tenant_prefix = _safe_identifier(tenant_id)
    for artifact in artifacts:
        if artifact.get("status") != "loaded":
            continue
        record_id = f"{tenant_prefix}:experiment:profit-sync:{artifact['artifact_kind']}"
        blockers = artifact.get("blockers") or []
        body = (
            f"Research-only generated readback `{artifact['artifact_kind']}` reports status "
            f"`{artifact.get('artifact_status')}` with {len(blockers)} blocker/reason categories. "
            "Use this for diagnostic routing only; it cannot authorize options actions."
        )
        metadata = _profit_learning_base_metadata(
            artifact,
            {
                "record_kind": "experiment_run",
                "blockers": blockers[:12],
                "metrics": artifact.get("metrics") or {},
            },
        )
        _assert_memory_policy_valid(
            title=f"Profit learning readback: {artifact['artifact_kind']}",
            body=body,
            metadata=metadata,
            field_name="profit-learning experiment",
        )
        records.append(
            {
                "id": record_id,
                "status": str(artifact.get("artifact_status") or "loaded"),
                "artifact_ref": artifact["source_ref"],
                "metric_json": artifact.get("metrics") or {},
                "metadata": metadata,
                "title": f"Profit learning readback: {artifact['artifact_kind']}",
                "body": body,
            }
        )
    return records


def _profit_learning_zero_records(artifacts: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    tenant_prefix = _safe_identifier(tenant_id)
    for artifact in artifacts:
        if artifact.get("artifact_kind") != "forward_candidate_throughput" or artifact.get("status") != "loaded":
            continue
        payload = artifact["payload"]
        zero = payload.get("zero_candidate_diagnostics")
        if not isinstance(zero, dict):
            continue
        drop_counts = payload.get("scheduled_phase2_drop_counts")
        summary = payload.get("scheduled_phase2_drop_stage_summary")
        if isinstance(summary, dict) and isinstance(summary.get("drop_counts"), dict):
            drop_counts = summary["drop_counts"]
        if not isinstance(drop_counts, dict):
            drop_counts = {}
        selection_date = str(
            zero.get("target_selection_date")
            or payload.get("target_selection_date")
            or (artifact.get("generated_at_utc") or "unknown")[:10]
        )
        total = 0
        for value in drop_counts.values():
            try:
                total += int(value)
            except (TypeError, ValueError):
                continue
        if total <= 0 and int(zero.get("candidate_rows_staged") or 0) != 0:
            continue
        lane = "phase2_forward_cohort"
        record_id = f"{tenant_prefix}:zero:profit-sync:{lane}:{_profit_learning_semantic_key(selection_date)}"
        blocker_summary = (
            f"Research-only candidate-starvation readback for {selection_date}: "
            f"status `{_safe_profit_learning_status(zero.get('status') or artifact.get('artifact_status'))}`, "
            f"total drop count {total}. "
            "Use this to select diagnostics only; it cannot authorize options actions."
        )
        metadata = _profit_learning_base_metadata(
            artifact,
            {
                "record_kind": "zero_candidate_episode",
                "zero_candidate_status": _safe_profit_learning_status(zero.get("status")),
                "returned_picks": zero.get("returned_picks"),
                "candidate_rows_staged": zero.get("candidate_rows_staged"),
                "drop_stage_counts": drop_counts,
            },
        )
        _assert_memory_policy_valid(
            title=f"Zero candidate episode: {lane} {selection_date}",
            body=blocker_summary,
            metadata=metadata,
            field_name="profit-learning zero-candidate episode",
        )
        records.append(
            {
                "id": record_id,
                "lane": lane,
                "selection_date": selection_date,
                "drop_stage_counts": drop_counts,
                "blocker_summary": blocker_summary,
                "source_ref": artifact["source_ref"],
                "metadata": metadata,
            }
        )
    return records


def _profit_learning_hypothesis_records(artifacts: list[dict[str, Any]], *, tenant_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    tenant_prefix = _safe_identifier(tenant_id)
    for artifact in artifacts:
        if artifact.get("status") != "loaded":
            continue
        payload = artifact["payload"]
        branch_items: list[dict[str, Any]] = []
        if isinstance(payload.get("blocked_or_superseded_branches"), list):
            branch_items.extend(item for item in payload["blocked_or_superseded_branches"] if isinstance(item, dict))
        no_chase = payload.get("no_chase_manifest")
        if isinstance(no_chase, dict) and isinstance(no_chase.get("reasons"), list):
            branch_items.extend(item for item in no_chase["reasons"] if isinstance(item, dict))
        if not branch_items and artifact.get("blockers"):
            denominator_terms = _profit_learning_denominator_terms(artifact.get("metrics") or {}, limit=8)
            branch_items.append(
                {
                    "id": artifact["artifact_kind"],
                    "status": artifact.get("artifact_status"),
                    "classification": "artifact_blocker_summary",
                    "blockers": denominator_terms + list(artifact.get("blockers") or []),
                    "denominator_context": denominator_terms,
                }
            )
        for index, item in enumerate(branch_items[:24]):
            branch_id = str(item.get("branch_id") or item.get("reason") or item.get("id") or f"item-{index}")
            status = _safe_profit_learning_status(
                item.get("status") or item.get("classification") or artifact.get("artifact_status") or "research_only"
            )
            blockers = _dedupe_strings(_flatten_strings(item.get("blockers") or item.get("evidence") or item, limit=32), limit=10)
            if not blockers and artifact.get("blockers"):
                blockers = list(artifact["blockers"][:6])
            record_id = (
                f"{tenant_prefix}:hyp:profit-sync:{artifact['artifact_kind']}:"
                f"{_profit_learning_semantic_key(branch_id)}"
            )
            priority_score = float(10 + min(len(blockers) * 8, 64))
            if "ready_for_research_only" in status or "candidate_selected_for_research_only" in status:
                priority_score += 20
            if "falsified" in status or "exhausted" in status or "do_not_repeat" in status:
                priority_score = max(1.0, priority_score - 24)
            title = f"Research-only profit blocker: {branch_id}"
            thesis = (
                f"`{branch_id}` is tracked from `{artifact['artifact_kind']}` with status `{status}`. "
                f"Blocker/reason categories: {', '.join(blockers[:6]) or 'none recorded'}. "
                "Memory ranks diagnostic follow-up only; it cannot authorize options actions."
            )
            metadata = _profit_learning_base_metadata(
                artifact,
                {
                    "record_kind": "strategy_hypothesis",
                    "branch_id": branch_id,
                    "hypothesis_status": status,
                    "blockers": blockers,
                    "denominator_context": _profit_learning_denominator_terms(artifact.get("metrics") or {}, limit=8),
                },
            )
            _assert_memory_policy_valid(
                title=title,
                body=thesis,
                metadata=metadata,
                field_name="profit-learning hypothesis",
            )
            records.append(
                {
                    "id": record_id,
                    "title": title,
                    "thesis": thesis,
                    "status": "research_only",
                    "priority_score": priority_score,
                    "metadata": metadata,
                    "source_ref": artifact["source_ref"],
                }
            )
    return records


def profit_learning_sync(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    artifact_names: list[str] | None = None,
    write_memory: bool = False,
) -> dict[str, Any]:
    artifacts = _profit_learning_source_artifacts(repo_root, artifact_names)
    loaded = [artifact for artifact in artifacts if artifact.get("status") == "loaded"]
    skipped = [
        {
            "artifact_kind": artifact["artifact_kind"],
            "source_ref": artifact["source_ref"],
            "status": artifact.get("status"),
            "error": artifact.get("error"),
        }
        for artifact in artifacts
        if artifact.get("status") != "loaded"
    ]
    zero_records = _profit_learning_zero_records(loaded, tenant_id=tenant_id)
    hypothesis_records = _profit_learning_hypothesis_records(loaded, tenant_id=tenant_id)
    experiment_records = _profit_learning_experiment_records(loaded, tenant_id=tenant_id)
    proposed = {
        "zero_candidate_episodes": zero_records,
        "strategy_hypotheses": hypothesis_records,
        "experiment_runs": experiment_records,
    }
    written = {"zero_candidate_episodes": 0, "strategy_hypotheses": 0, "experiment_runs": 0, "graph_nodes": 0}
    if write_memory:
        db_path, events_path = _assert_profit_learning_write_paths(
            repo_root=repo_root,
            db_path=db_path,
            events_path=events_path,
        )
        now = utc_now()
        with closing(connect(db_path)) as conn, conn:
            for table, records in (
                ("zero_candidate_episodes", zero_records),
                ("strategy_hypotheses", hypothesis_records),
                ("experiment_runs", experiment_records),
            ):
                for record in records:
                    existing_tenant = conn.execute(
                        f"SELECT tenant_id FROM {table} WHERE id = ?",
                        (record["id"],),
                    ).fetchone()
                    if existing_tenant is not None and existing_tenant["tenant_id"] != tenant_id:
                        raise AgentControlError(
                            f"Profit-learning record {record['id']} in {table} already belongs to "
                            f"tenant {existing_tenant['tenant_id']}; refusing cross-tenant overwrite by {tenant_id}"
                        )
            for record in zero_records:
                conn.execute(
                    """
                    INSERT INTO zero_candidate_episodes(
                        id, created_at, tenant_id, lane, selection_date, drop_stage_counts_json,
                        blocker_summary, source_ref, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        tenant_id = excluded.tenant_id,
                        drop_stage_counts_json = excluded.drop_stage_counts_json,
                        blocker_summary = excluded.blocker_summary,
                        source_ref = excluded.source_ref,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        record["id"],
                        now,
                        tenant_id,
                        record["lane"],
                        record["selection_date"],
                        canonical_json(record["drop_stage_counts"]),
                        record["blocker_summary"],
                        record["source_ref"],
                        canonical_json(record["metadata"]),
                    ),
                )
                upsert_graph_node(
                    conn,
                    node_id=f"provenance:{record['id']}",
                    kind="episode",
                    title=f"Zero candidate episode: {record['lane']} {record['selection_date']}",
                    body=record["blocker_summary"],
                    tenant_id=tenant_id,
                    sub_tenant_id="profitability",
                    metadata=record["metadata"],
                    source_ref=record["source_ref"],
                )
                written["zero_candidate_episodes"] += 1
                written["graph_nodes"] += 1
            for record in hypothesis_records:
                conn.execute(
                    """
                    INSERT INTO strategy_hypotheses(
                        id, created_at, updated_at, tenant_id, title, thesis, status, priority_score, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        tenant_id = excluded.tenant_id,
                        title = excluded.title,
                        thesis = excluded.thesis,
                        status = excluded.status,
                        priority_score = excluded.priority_score,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        record["id"],
                        now,
                        now,
                        tenant_id,
                        record["title"],
                        record["thesis"],
                        record["status"],
                        record["priority_score"],
                        canonical_json(record["metadata"]),
                    ),
                )
                upsert_graph_node(
                    conn,
                    node_id=f"provenance:{record['id']}",
                    kind="blocker",
                    title=record["title"],
                    body=record["thesis"],
                    tenant_id=tenant_id,
                    sub_tenant_id="profitability",
                    metadata=record["metadata"],
                    source_ref=record["source_ref"],
                )
                written["strategy_hypotheses"] += 1
                written["graph_nodes"] += 1
            for record in experiment_records:
                conn.execute(
                    """
                    INSERT INTO experiment_runs(
                        id, created_at, tenant_id, hypothesis_id, status, artifact_ref,
                        metric_json, dataset_version_id, feature_snapshot_id, testing_debt_json, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        tenant_id = excluded.tenant_id,
                        status = excluded.status,
                        artifact_ref = excluded.artifact_ref,
                        metric_json = excluded.metric_json,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        record["id"],
                        now,
                        tenant_id,
                        None,
                        record["status"],
                        record["artifact_ref"],
                        canonical_json(record["metric_json"]),
                        None,
                        None,
                        "[]",
                        canonical_json(record["metadata"]),
                    ),
                )
                upsert_graph_node(
                    conn,
                    node_id=f"provenance:{record['id']}",
                    kind="evidence_artifact",
                    title=record["title"],
                    body=record["body"],
                    tenant_id=tenant_id,
                    sub_tenant_id="profitability",
                    metadata=record["metadata"],
                    source_ref=record["artifact_ref"],
                )
                written["experiment_runs"] += 1
                written["graph_nodes"] += 1
            _record_event(
                conn,
                events_path=events_path,
                event_type="profit_learning.sync",
                payload={
                    "tenant_id": tenant_id,
                    "extractor_version": PROFIT_LEARNING_EXTRACTOR_VERSION,
                    "artifact_count": len(loaded),
                    "written": written,
                    "source_refs": [artifact["source_ref"] for artifact in loaded],
                },
            )
    return {
        "status": "ready" if loaded else "empty",
        "mode": "write_memory" if write_memory else "dry_run",
        "tenant_id": tenant_id,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "extractor_version": PROFIT_LEARNING_EXTRACTOR_VERSION,
        "loaded_artifacts": [
            {
                "artifact_kind": artifact["artifact_kind"],
                "source_ref": artifact["source_ref"],
                "source_sha256": artifact.get("source_sha256"),
                "generated_at_utc": artifact.get("generated_at_utc"),
                "artifact_status": artifact.get("artifact_status"),
                "blocker_count": len(artifact.get("blockers") or []),
            }
            for artifact in loaded
        ],
        "skipped_artifacts": skipped,
        "proposed_counts": {key: len(value) for key, value in proposed.items()},
        "proposed": proposed,
        "written_counts": written,
        "recommended_commands": [
            "npm run memory:research-priorities",
            "npm run memory:operator-dashboard",
            "npm run verify:memory",
        ],
    }


def profit_learning_audit(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    artifact_names: list[str] | None = None,
) -> dict[str, Any]:
    db_path, _ = _assert_profit_learning_write_paths(
        repo_root=repo_root,
        db_path=db_path,
        events_path=repo_root / "data" / "agent-control" / "events.jsonl",
    )
    dry_run = profit_learning_sync(
        db_path=db_path,
        repo_root=repo_root,
        tenant_id=tenant_id,
        artifact_names=artifact_names,
        write_memory=False,
    )
    priorities = research_priority_report(db_path=db_path, tenant_id=tenant_id)
    checks = [
        {
            "name": "allowlisted artifacts loaded",
            "pass": bool(dry_run["loaded_artifacts"]),
            "detail": str(len(dry_run["loaded_artifacts"])),
        },
        {
            "name": "dry-run proposes research provenance",
            "pass": sum(dry_run["proposed_counts"].values()) > 0,
            "detail": canonical_json(dry_run["proposed_counts"]),
        },
        {
            "name": "runtime research priorities populated",
            "pass": priorities["status"] == "ready",
            "detail": priorities["status"],
        },
        {
            "name": "skipped artifacts are explicit",
            "pass": all(item.get("error") for item in dry_run["skipped_artifacts"]),
            "detail": str(len(dry_run["skipped_artifacts"])),
        },
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "needs_attention",
        "tenant_id": tenant_id,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "checks": checks,
        "dry_run": {
            "loaded_artifacts": dry_run["loaded_artifacts"],
            "skipped_artifacts": dry_run["skipped_artifacts"],
            "proposed_counts": dry_run["proposed_counts"],
        },
        "research_priorities": priorities,
        "recommended_commands": [
            (
                "npm run agent:control -- memory profit-learning-sync --write-memory "
                "--approval-token APPROVE_PROFIT_LEARNING_MEMORY_SYNC --prompt-only"
            ),
            "npm run memory:research-priorities",
            "npm run verify:memory",
        ],
    }


def _format_profit_learning_sync(result: dict[str, Any]) -> str:
    lines = [
        "# Profit Learning Sync",
        f"Status: {result.get('status')}",
        f"Mode: {result.get('mode')}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Artifacts",
    ]
    if not result.get("loaded_artifacts"):
        lines.append("- None loaded.")
    for artifact in result.get("loaded_artifacts", []):
        lines.append(
            f"- {artifact['artifact_kind']} status={artifact.get('artifact_status')} "
            f"blockers={artifact.get('blocker_count')} source={artifact.get('source_ref')}"
        )
    if result.get("skipped_artifacts"):
        lines.append("")
        lines.append("# Skipped Artifacts")
        for item in result["skipped_artifacts"]:
            lines.append(f"- {item['artifact_kind']} {item.get('status')}: {item.get('error')}")
    lines.extend(["", "# Counts"])
    for key, value in result.get("proposed_counts", {}).items():
        lines.append(f"- proposed {key}: {value}")
    for key, value in result.get("written_counts", {}).items():
        lines.append(f"- written {key}: {value}")
    lines.extend(["", "# Recommended Commands"])
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _format_profit_learning_audit(result: dict[str, Any]) -> str:
    lines = [
        "# Profit Learning Audit",
        f"Status: {result.get('status')}",
        f"Policy: {result.get('policy_banner')}",
        "",
        "# Checks",
    ]
    for check in result.get("checks", []):
        status = "PASS" if check.get("pass") else "FAIL"
        lines.append(f"- {status}: {check.get('name')} - {check.get('detail')}")
    lines.extend(["", "# Dry-Run Counts"])
    for key, value in result.get("dry_run", {}).get("proposed_counts", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "# Research Priority Status"])
    lines.append(f"- {result.get('research_priorities', {}).get('status')}")
    lines.extend(["", "# Recommended Commands"])
    for command in result.get("recommended_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def digest(*, db_path: Path = DEFAULT_DB_PATH, recent_limit: int = 8) -> dict[str, Any]:
    with closing(connect(db_path)) as conn, conn:
        task_counts = {
            row["status"]: row["count"]
            for row in conn.execute("SELECT status, count(*) AS count FROM tasks GROUP BY status")
        }
        graph_counts = {
            row["kind"]: row["count"]
            for row in conn.execute("SELECT kind, count(*) AS count FROM graph_nodes GROUP BY kind")
        }
        recent_tasks = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM tasks
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (recent_limit,),
            )
        ]
        blockers = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT graph_nodes.*
                FROM graph_nodes
                WHERE kind = 'blocker'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (recent_limit,),
            )
        ]
        events = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM event_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (recent_limit,),
            )
        ]
        return {
            "db_path": str(db_path),
            "runtime_use": True,
            "task_counts": task_counts,
            "graph_counts": graph_counts,
            "recent_tasks": [row for row in recent_tasks if row is not None],
            "open_blockers": [row for row in blockers if row is not None],
            "recent_events": [row for row in events if row is not None],
        }


def list_tasks(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    status: str | None = None,
    pathway: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if status is not None:
        _validate_choice(status, TASK_STATUSES, "status")
    if pathway is not None:
        _validate_choice(pathway, PATHWAYS, "pathway")
    clauses = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if pathway is not None:
        clauses.append("pathway = ?")
        params.append(pathway)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with closing(connect(db_path)) as conn, conn:
        rows = conn.execute(
            f"""
            SELECT * FROM tasks
            {where}
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return {"tasks": [_row_dict(row) for row in rows]}


def _emit(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(pretty_json(result))
        return
    if "id" in result and "title" in result:
        print(f"{result['id']}: {result.get('status', result.get('kind', 'ok'))} - {result['title']}")
    else:
        print(pretty_json(result))


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Runtime SQLite control DB path.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH, help="Append-only JSONL event mirror.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local CEO/worker runtime memory graph control plane.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Common agent commands:
  npm run memory:bootstrap
  npm run memory:context -- --goal "current task" --pathway operator --prompt-only
  npm run memory:audit
  npm run memory:repair-authority
  npm run memory:dream-run
  npm run memory:dream-audit
  npm run memory:operator-dashboard
  npm run memory:run-ledger
  npm run memory:anchor-ledger
  npm run memory:backup
  npm run memory:doctor
  npm run memory:maintenance
  npm run memory:auto-maintenance
  npm run memory:daily-brief
  npm run memory:blocker-autopsy
  npm run memory:inbox
  npm run memory:research-priorities
  npm run memory:profit-learning-sync
  npm run memory:profit-learning-audit
  npm run memory:review-dreams
  npm run memory:dreams
  npm run memory:eval
  npm run memory:agent-eval
  npm run verify:memory
  npm run agent:control -- writeback <task-id> --summary "Accepted after review."
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_alias = subparsers.add_parser("audit", help="Shortcut for memory audit --prompt-only.")
    audit_alias.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    audit_alias.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    audit_alias.add_argument("--limit", type=int, default=12)
    audit_alias.set_defaults(func=_cmd_audit_alias)

    dreams_alias = subparsers.add_parser("dreams", help="Shortcut for dream review --prompt-only.")
    dreams_alias.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dreams_alias.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dreams_alias.add_argument("--limit", type=int, default=12)
    dreams_alias.add_argument("--json", action="store_true")
    dreams_alias.set_defaults(func=_cmd_dreams_alias)

    run = subparsers.add_parser("run", help="Record and inspect append-only agent run ledger events.")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_event = run_sub.add_parser("event", help="Append an agent run event.")
    _add_common(run_event)
    run_event.add_argument("--run-id")
    run_event.add_argument("--event-type", required=True, choices=sorted(AGENT_RUN_EVENT_TYPES))
    run_event.add_argument("--title", default="")
    run_event.add_argument("--summary", default="")
    run_event.add_argument("--status", choices=sorted(AGENT_RUN_STATUSES))
    run_event.add_argument("--actor", default="agent")
    run_event.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    run_event.add_argument("--sub-tenant-id")
    run_event.add_argument("--payload", help="JSON object payload; sensitive keys are redacted before storage.")
    run_event.add_argument("--prompt-only", action="store_true")
    run_event.set_defaults(func=_cmd_run_event)

    run_list = run_sub.add_parser("list", help="List reduced agent runs.")
    run_list.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    run_list.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    run_list.add_argument("--status", choices=sorted(AGENT_RUN_STATUSES))
    run_list.add_argument("--limit", type=int, default=20)
    run_list.add_argument("--prompt-only", action="store_true")
    run_list.add_argument("--json", action="store_true")
    run_list.set_defaults(func=_cmd_run_list)

    run_show = run_sub.add_parser("show", help="Show one agent run with events.")
    run_show.add_argument("run_id")
    run_show.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    run_show.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    run_show.add_argument("--json", action="store_true")
    run_show.set_defaults(func=_cmd_run_show)

    writeback = subparsers.add_parser(
        "writeback",
        help="Accept latest worker report and write accepted operating memory.",
    )
    _add_common(writeback)
    writeback.add_argument("task_id")
    writeback.add_argument("--accepted-by", default="CEO")
    writeback.add_argument("--summary", required=True)
    writeback.add_argument("--metadata", default="{}")
    writeback.set_defaults(func=_cmd_writeback)

    seed = subparsers.add_parser("seed", help="Seed visible project context into the runtime graph.")
    seed_sub = seed.add_subparsers(dest="seed_command", required=True)

    seed_project = seed_sub.add_parser("project", help="Seed living docs, static graph, gateboard context, and visible repo files.")
    _add_common(seed_project)
    seed_project.add_argument("--repo-root", type=Path, default=ROOT)
    seed_project.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    seed_project.add_argument("--no-static-memory-graph", action="store_true")
    seed_project.add_argument("--no-gateboard", action="store_true")
    seed_project.add_argument("--no-repo-files", action="store_true")
    seed_project.add_argument("--max-repo-files", type=int, default=DEFAULT_REPO_INDEX_MAX_FILES)
    seed_project.add_argument("--max-repo-file-bytes", type=int, default=DEFAULT_REPO_INDEX_MAX_FILE_BYTES)
    seed_project.add_argument("--max-repo-body-chars", type=int, default=DEFAULT_REPO_INDEX_BODY_CHARS)
    seed_project.set_defaults(func=_cmd_seed_project)

    bootstrap = subparsers.add_parser("bootstrap", help="Seed project memory and emit a prompt-ready context pack.")
    _add_common(bootstrap)
    bootstrap.add_argument("--repo-root", type=Path, default=ROOT)
    bootstrap.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    bootstrap.add_argument("--skip-seed", action="store_true")
    bootstrap.add_argument("--query", default="gateboard")
    bootstrap.add_argument("--no-repo-files", action="store_true")
    bootstrap.add_argument("--max-repo-files", type=int, default=DEFAULT_REPO_INDEX_MAX_FILES)
    bootstrap.add_argument("--max-repo-file-bytes", type=int, default=DEFAULT_REPO_INDEX_MAX_FILE_BYTES)
    bootstrap.add_argument("--max-repo-body-chars", type=int, default=DEFAULT_REPO_INDEX_BODY_CHARS)
    bootstrap.add_argument("--metadata-filter", default='{"source_type":"gateboard_blocker"}')
    bootstrap.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Metadata filter as KEY=VALUE. May be repeated; avoids shell JSON quoting.",
    )
    bootstrap.add_argument("--max-depth", type=int, default=1)
    bootstrap.add_argument("--max-context-nodes", type=int, default=8)
    bootstrap.add_argument("--max-context-edges", type=int, default=8)
    bootstrap.add_argument("--manifest-dir", type=Path, default=DEFAULT_CONTEXT_PACKS_DIR)
    bootstrap.add_argument("--prompt-only", action="store_true", help="Print only the prompt-ready context text.")
    bootstrap.set_defaults(func=_cmd_bootstrap)

    checkpoint = subparsers.add_parser("checkpoint", help="Write and read CEO session checkpoints.")
    checkpoint_sub = checkpoint.add_subparsers(dest="checkpoint_command", required=True)

    checkpoint_write = checkpoint_sub.add_parser("write", help="Record the current CEO objective and next actions.")
    _add_common(checkpoint_write)
    checkpoint_write.add_argument("--objective", required=True)
    checkpoint_write.add_argument("--scope", default="")
    checkpoint_write.add_argument("--status", default="in_progress", choices=sorted(CHECKPOINT_STATUSES))
    checkpoint_write.add_argument("--summary", default="")
    checkpoint_write.add_argument("--success-criteria", action="append", default=[])
    checkpoint_write.add_argument("--constraint", action="append", default=[])
    checkpoint_write.add_argument("--autonomy-level", default=DEFAULT_CHECKPOINT_AUTONOMY_LEVEL)
    checkpoint_write.add_argument("--next-action", action="append", default=[])
    checkpoint_write.add_argument("--verification", action="append", default=[])
    checkpoint_write.add_argument("--blocker", action="append", default=[])
    checkpoint_write.add_argument("--file", action="append", default=[])
    checkpoint_write.add_argument("--command", action="append", default=[])
    checkpoint_write.add_argument("--metadata", default="{}")
    checkpoint_write.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    checkpoint_write.add_argument("--sub-tenant-id", default="operator")
    checkpoint_write.add_argument("--prompt-only", action="store_true")
    checkpoint_write.set_defaults(func=_cmd_checkpoint_write)

    checkpoint_latest = checkpoint_sub.add_parser("latest", help="Read the latest CEO checkpoint.")
    checkpoint_latest.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    checkpoint_latest.add_argument("--json", action="store_true")
    checkpoint_latest.add_argument("--prompt-only", action="store_true")
    checkpoint_latest.set_defaults(func=_cmd_checkpoint_latest)

    task = subparsers.add_parser("task", help="Create, claim, report, accept, and list tasks.")
    task_sub = task.add_subparsers(dest="task_command", required=True)

    create = task_sub.add_parser("create", help="Create a scoped worker task.")
    _add_common(create)
    create.add_argument("--title", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--pathway", default="general", choices=sorted(PATHWAYS))
    create.add_argument("--permission-mode", default="read_only_workers", choices=sorted(PERMISSION_MODES))
    create.add_argument("--priority", type=int, default=50)
    create.add_argument("--metadata", default="{}")
    create.add_argument("--tenant-id", default="options-chatbot")
    create.add_argument("--sub-tenant-id")
    create.add_argument("--ack-high-risk", action="store_true")
    create.set_defaults(func=_cmd_task_create)

    claim = task_sub.add_parser("claim", help="Claim a task for one worker.")
    _add_common(claim)
    claim.add_argument("task_id")
    claim.add_argument("--worker-id", required=True)
    claim.add_argument("--metadata", default="{}")
    claim.set_defaults(func=_cmd_task_claim)

    report = task_sub.add_parser("report", help="Submit a worker report.")
    _add_common(report)
    report.add_argument("task_id")
    report.add_argument("--worker-id", required=True)
    report.add_argument("--finding", required=True)
    report.add_argument("--proof-gate-status", default="not_applicable")
    report.add_argument("--recommendation", default="")
    report.add_argument("--verification", default="")
    report.add_argument("--blockers", default="")
    report.add_argument("--files-read", default="")
    report.add_argument("--commands-run", default="")
    report.add_argument("--artifacts-written", default="")
    report.set_defaults(func=_cmd_task_report)

    accept = task_sub.add_parser("accept", help="Accept a reported task.")
    _add_common(accept)
    accept.add_argument("task_id")
    accept.add_argument("--accepted-by", default="CEO")
    accept.add_argument("--summary", required=True)
    accept.add_argument("--metadata", default="{}")
    accept.set_defaults(func=_cmd_task_accept)

    list_cmd = task_sub.add_parser("list", help="List tasks.")
    _add_common(list_cmd)
    list_cmd.add_argument("--status", choices=sorted(TASK_STATUSES))
    list_cmd.add_argument("--pathway", choices=sorted(PATHWAYS))
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=_cmd_task_list)

    graph = subparsers.add_parser("graph", help="Remember, link, and query runtime graph context.")
    graph_sub = graph.add_subparsers(dest="graph_command", required=True)

    remember = graph_sub.add_parser("remember", help="Store a memory, knowledge item, episode, or entity.")
    _add_common(remember)
    remember.add_argument("--kind", required=True, choices=sorted(GRAPH_NODE_KINDS))
    remember.add_argument("--title", required=True)
    remember.add_argument("--body", default="")
    remember.add_argument("--tenant-id", default="options-chatbot")
    remember.add_argument("--sub-tenant-id")
    remember.add_argument("--metadata", default="{}")
    remember.add_argument("--source-ref")
    remember.add_argument("--node-id")
    remember.add_argument("--no-upsert", action="store_true")
    remember.set_defaults(func=_cmd_graph_remember)

    link = graph_sub.add_parser("link", help="Create a source -> relation -> target graph triplet.")
    _add_common(link)
    link.add_argument("--source", required=True)
    link.add_argument("--relation", required=True)
    link.add_argument("--target", required=True)
    link.add_argument("--metadata", default="{}")
    link.add_argument("--source-ref")
    link.set_defaults(func=_cmd_graph_link)

    query_cmd = graph_sub.add_parser("query", help="Retrieve matching nodes plus graph neighborhood.")
    _add_common(query_cmd)
    query_cmd.add_argument("query")
    query_cmd.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    query_cmd.add_argument("--sub-tenant-id")
    query_cmd.add_argument("--kind", choices=sorted(GRAPH_NODE_KINDS))
    query_cmd.add_argument("--metadata-filter", default="{}")
    query_cmd.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Metadata filter as KEY=VALUE. May be repeated; avoids shell JSON quoting.",
    )
    query_cmd.add_argument("--memory-type", choices=sorted(OPERATING_MEMORY_TYPES))
    query_cmd.add_argument("--include-inactive", action="store_true")
    query_cmd.add_argument("--fresh-only", action="store_true")
    query_cmd.add_argument(
        "--include-repo-index",
        action="store_true",
        help="Allow tier-3 repo_file_index retrieval docs; tier 1/2 hits still rank first.",
    )
    query_cmd.add_argument("--limit", type=int, default=8)
    query_cmd.add_argument("--max-depth", type=int, default=2)
    query_cmd.add_argument("--context", action="store_true", help="Include prompt-ready graph context text.")
    query_cmd.add_argument("--max-context-nodes", type=int, default=12)
    query_cmd.add_argument("--max-context-edges", type=int, default=16)
    query_cmd.add_argument("--prompt-only", action="store_true", help="Print only the prompt-ready context text.")
    query_cmd.set_defaults(func=_cmd_graph_query)

    context = subparsers.add_parser("context", help="Build prompt-ready context packs.")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    context_pack = context_sub.add_parser("pack", help="Emit a focused operating-memory context pack.")
    _add_common(context_pack)
    context_pack.add_argument("--goal", default="")
    context_pack.add_argument("--pathway", choices=sorted(PATHWAYS))
    context_pack.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    context_pack.add_argument("--limit", type=int, default=DEFAULT_CONTEXT_PACK_LIMIT)
    context_pack.add_argument("--manifest-dir", type=Path, default=DEFAULT_CONTEXT_PACKS_DIR)
    context_pack.add_argument("--prompt-only", action="store_true")
    context_pack.set_defaults(func=_cmd_context_pack)

    session = subparsers.add_parser("session", help="Capture session transcript metadata into runtime memory.")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_log = session_sub.add_parser("log", help="Log one transcript file with a SHA-256 guard.")
    _add_common(session_log)
    session_log.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS_PATH)
    session_log.add_argument("--repo-root", type=Path, default=ROOT)
    session_log.add_argument("--transcript", type=Path, required=True)
    session_log.add_argument("--session-id")
    session_log.add_argument("--title", default="")
    session_log.add_argument("--summary", default="")
    session_log.add_argument("--actor", default="agent")
    session_log.add_argument("--expected-sha256")
    session_log.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    session_log.add_argument("--sub-tenant-id", default="operator")
    session_log.add_argument("--metadata", default="{}")
    session_log.set_defaults(func=_cmd_session_log)

    dream = subparsers.add_parser("dream", help="Propose, review, and accept out-of-band memory updates.")
    dream_sub = dream.add_subparsers(dest="dream_command", required=True)
    dream_propose = dream_sub.add_parser("propose", help="Store a non-authoritative dream proposal from JSON.")
    _add_common(dream_propose)
    dream_propose.add_argument("--repo-root", type=Path, default=ROOT)
    dream_propose.add_argument("--file", type=Path, required=True)
    dream_propose.add_argument("--dream-id")
    dream_propose.add_argument("--title", default="")
    dream_propose.add_argument("--expected-sha256")
    dream_propose.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dream_propose.add_argument("--sub-tenant-id", default="operator")
    dream_propose.set_defaults(func=_cmd_dream_propose)

    dream_accept = dream_sub.add_parser("accept", help="Promote a proposed dream into operating memory.")
    _add_common(dream_accept)
    dream_accept.add_argument("dream_id")
    dream_accept.add_argument("--accepted-by", default="CEO")
    dream_accept.add_argument("--note", default="")
    dream_accept.set_defaults(func=_cmd_dream_accept)

    dream_reject = dream_sub.add_parser("reject", help="Reject a proposed dream without promoting memory.")
    _add_common(dream_reject)
    dream_reject.add_argument("dream_id")
    dream_reject.add_argument("--rejected-by", default="CEO")
    dream_reject.add_argument("--reason", default="")
    dream_reject.set_defaults(func=_cmd_dream_reject)

    dream_list = dream_sub.add_parser("list", help="List dream proposals.")
    dream_list.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dream_list.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dream_list.add_argument("--status", choices=["proposed", "accepted", "rejected"])
    dream_list.add_argument("--limit", type=int, default=20)
    dream_list.add_argument("--json", action="store_true")
    dream_list.set_defaults(func=_cmd_dream_list)

    dream_review = dream_sub.add_parser("review", help="Emit a prompt-ready dream review packet.")
    dream_review.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dream_review.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dream_review.add_argument("--limit", type=int, default=12)
    dream_review.add_argument("--prompt-only", action="store_true")
    dream_review.add_argument("--json", action="store_true")
    dream_review.set_defaults(func=_cmd_dream_review)

    dream_run = dream_sub.add_parser("run", help="Run automated dreaming and auto-resolution.")
    dream_run.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dream_run.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    dream_run.add_argument("--repo-root", type=Path, default=ROOT)
    dream_run.add_argument("--dreams-dir", type=Path, default=DEFAULT_DREAMS_DIR)
    dream_run.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    dream_run.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dream_run.add_argument("--limit", type=int, default=50)
    dream_run.add_argument("--actor", default="AutoDream")
    dream_run.add_argument("--no-generate-from-sessions", action="store_true")
    dream_run.add_argument("--no-auto-resolve", action="store_true")
    dream_run.add_argument("--prompt-only", action="store_true")
    dream_run.add_argument("--json", action="store_true")
    dream_run.set_defaults(func=_cmd_dream_run)

    dream_audit_parser = dream_sub.add_parser("audit", help="Inspect automated dreaming state.")
    dream_audit_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    dream_audit_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    dream_audit_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    dream_audit_parser.add_argument("--limit", type=int, default=12)
    dream_audit_parser.add_argument("--prompt-only", action="store_true")
    dream_audit_parser.add_argument("--json", action="store_true")
    dream_audit_parser.set_defaults(func=_cmd_dream_audit)

    memory = subparsers.add_parser("memory", help="Remember, supersede, audit, and evaluate operating memory.")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_run_ledger = memory_sub.add_parser("run-ledger", help="Prompt-ready append-only agent run ledger report.")
    memory_run_ledger.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_run_ledger.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_run_ledger.add_argument("--status", choices=sorted(AGENT_RUN_STATUSES))
    memory_run_ledger.add_argument("--limit", type=int, default=20)
    memory_run_ledger.add_argument("--json", action="store_true")
    memory_run_ledger.add_argument("--prompt-only", action="store_true")
    memory_run_ledger.set_defaults(func=_cmd_memory_run_ledger)
    memory_anchor_ledger = memory_sub.add_parser("anchor-ledger", help="Write or validate agent run ledger hash anchors.")
    memory_anchor_ledger.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_anchor_ledger.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_anchor_ledger.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS_PATH)
    memory_anchor_ledger.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_anchor_ledger.add_argument("--write-anchor", action="store_true")
    memory_anchor_ledger.add_argument("--anchor-type", default="manual")
    memory_anchor_ledger.add_argument("--json", action="store_true")
    memory_anchor_ledger.add_argument("--prompt-only", action="store_true")
    memory_anchor_ledger.set_defaults(func=_cmd_memory_anchor_ledger)
    memory_backup = memory_sub.add_parser("backup", help="Back up local memory DB and JSONL sidecars with hashes.")
    memory_backup.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_backup.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_backup.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS_PATH)
    memory_backup.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS_PATH)
    memory_backup.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUPS_DIR)
    memory_backup.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_backup.add_argument("--no-anchor", action="store_true")
    memory_backup.add_argument("--json", action="store_true")
    memory_backup.add_argument("--prompt-only", action="store_true")
    memory_backup.set_defaults(func=_cmd_memory_backup)
    memory_restore_check = memory_sub.add_parser("restore-check", help="Validate a memory backup bundle without overwriting live state.")
    memory_restore_check.add_argument("backup_dir", type=Path)
    memory_restore_check.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_restore_check.add_argument("--json", action="store_true")
    memory_restore_check.add_argument("--prompt-only", action="store_true")
    memory_restore_check.set_defaults(func=_cmd_memory_restore_check)
    memory_doctor_parser = memory_sub.add_parser("doctor", help="Run full memory integrity, backup, and eval checks.")
    memory_doctor_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_doctor_parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_doctor_parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS_PATH)
    memory_doctor_parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS_PATH)
    memory_doctor_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUPS_DIR)
    memory_doctor_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    memory_doctor_parser.add_argument("--repo-root", type=Path, default=ROOT)
    memory_doctor_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_doctor_parser.add_argument("--write-backup", action="store_true")
    memory_doctor_parser.add_argument("--max-backup-age-hours", type=int, default=48)
    memory_doctor_parser.add_argument("--json", action="store_true")
    memory_doctor_parser.add_argument("--prompt-only", action="store_true")
    memory_doctor_parser.set_defaults(func=_cmd_memory_doctor)
    memory_maintenance_parser = memory_sub.add_parser(
        "maintenance",
        help="Run self-logging backup, doctor, and anchor maintenance.",
    )
    memory_maintenance_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_maintenance_parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_maintenance_parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS_PATH)
    memory_maintenance_parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS_PATH)
    memory_maintenance_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUPS_DIR)
    memory_maintenance_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    memory_maintenance_parser.add_argument("--repo-root", type=Path, default=ROOT)
    memory_maintenance_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_maintenance_parser.add_argument("--actor", default="memory-maintenance")
    memory_maintenance_parser.add_argument("--max-backup-age-hours", type=int, default=48)
    memory_maintenance_parser.add_argument("--json", action="store_true")
    memory_maintenance_parser.add_argument("--prompt-only", action="store_true")
    memory_maintenance_parser.set_defaults(func=_cmd_memory_maintenance)
    memory_ingest_history = memory_sub.add_parser(
        "ingest-living-history",
        help="Ingest docs/WORKLOG.md and docs/DECISIONS.md into episode/decision memory nodes.",
    )
    memory_ingest_history.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_ingest_history.add_argument("--repo-root", type=Path, default=ROOT)
    memory_ingest_history.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_ingest_history.add_argument("--json", action="store_true")
    memory_ingest_history.add_argument("--prompt-only", action="store_true")
    memory_ingest_history.set_defaults(func=_cmd_memory_ingest_living_history)
    memory_auto_maintenance_parser = memory_sub.add_parser(
        "auto-maintenance",
        help="Run memory maintenance only when memory health or freshness requires it.",
    )
    memory_auto_maintenance_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_auto_maintenance_parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_auto_maintenance_parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS_PATH)
    memory_auto_maintenance_parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS_PATH)
    memory_auto_maintenance_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUPS_DIR)
    memory_auto_maintenance_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    memory_auto_maintenance_parser.add_argument("--repo-root", type=Path, default=ROOT)
    memory_auto_maintenance_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_auto_maintenance_parser.add_argument("--actor", default="memory-auto-maintenance")
    memory_auto_maintenance_parser.add_argument("--min-interval-hours", type=int, default=6)
    memory_auto_maintenance_parser.add_argument("--max-success-age-hours", type=int, default=24)
    memory_auto_maintenance_parser.add_argument("--max-backup-age-hours", type=int, default=48)
    memory_auto_maintenance_parser.add_argument("--force", action="store_true")
    memory_auto_maintenance_parser.add_argument("--json", action="store_true")
    memory_auto_maintenance_parser.add_argument("--prompt-only", action="store_true")
    memory_auto_maintenance_parser.set_defaults(func=_cmd_memory_auto_maintenance)
    memory_daily_brief = memory_sub.add_parser("daily-brief", help="Prompt-ready daily operator brief from memory and run ledger state.")
    memory_daily_brief.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_daily_brief.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    memory_daily_brief.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_daily_brief.add_argument("--since-hours", type=int, default=24)
    memory_daily_brief.add_argument("--stale-hours", type=int, default=6)
    memory_daily_brief.add_argument("--limit", type=int, default=20)
    memory_daily_brief.add_argument("--json", action="store_true")
    memory_daily_brief.add_argument("--prompt-only", action="store_true")
    memory_daily_brief.set_defaults(func=_cmd_memory_daily_brief)
    memory_blocker_autopsy = memory_sub.add_parser("blocker-autopsy", help="Group repeated failed/blocked agent run blockers.")
    memory_blocker_autopsy.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_blocker_autopsy.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_blocker_autopsy.add_argument("--min-count", type=int, default=2)
    memory_blocker_autopsy.add_argument("--limit", type=int, default=20)
    memory_blocker_autopsy.add_argument("--json", action="store_true")
    memory_blocker_autopsy.add_argument("--prompt-only", action="store_true")
    memory_blocker_autopsy.set_defaults(func=_cmd_memory_blocker_autopsy)
    memory_inbox = memory_sub.add_parser("inbox", help="Show local pending agent inbox items from the run ledger.")
    memory_inbox.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_inbox.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_inbox.add_argument("--stale-hours", type=int, default=6)
    memory_inbox.add_argument("--limit", type=int, default=20)
    memory_inbox.add_argument("--json", action="store_true")
    memory_inbox.add_argument("--prompt-only", action="store_true")
    memory_inbox.set_defaults(func=_cmd_memory_inbox)
    memory_remember = memory_sub.add_parser("remember", help="Store typed operating memory.")
    _add_common(memory_remember)
    memory_remember.add_argument("--type", required=True, choices=sorted(OPERATING_MEMORY_TYPES))
    memory_remember.add_argument("--title", required=True)
    memory_remember.add_argument("--body", default="")
    memory_remember.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_remember.add_argument("--sub-tenant-id")
    memory_remember.add_argument("--status", default="active", choices=sorted(MEMORY_STATUSES))
    memory_remember.add_argument("--confidence", default="inferred", choices=sorted(MEMORY_CONFIDENCE))
    memory_remember.add_argument("--metadata", default="{}")
    memory_remember.add_argument("--source-ref")
    memory_remember.add_argument("--node-id")
    memory_remember.add_argument("--supersedes", action="append", default=[])
    memory_remember.add_argument("--freshness-days", type=int)
    memory_remember.set_defaults(func=_cmd_memory_remember)

    memory_supersede = memory_sub.add_parser("supersede", help="Mark an operating memory as superseded by another.")
    _add_common(memory_supersede)
    memory_supersede.add_argument("--old", required=True)
    memory_supersede.add_argument("--new", required=True)
    memory_supersede.add_argument("--reason", default="")
    memory_supersede.set_defaults(func=_cmd_memory_supersede)

    memory_audit_parser = memory_sub.add_parser("audit", help="Audit operating memory lifecycle state.")
    memory_audit_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_audit_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_audit_parser.add_argument("--limit", type=int, default=12)
    memory_audit_parser.add_argument("--json", action="store_true")
    memory_audit_parser.add_argument("--prompt-only", action="store_true")
    memory_audit_parser.set_defaults(func=_cmd_memory_audit)

    memory_repair_authority = memory_sub.add_parser(
        "repair-authority",
        help="Backfill required authority metadata on operating memory nodes.",
    )
    memory_repair_authority.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_repair_authority.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_repair_authority.add_argument("--json", action="store_true")
    memory_repair_authority.set_defaults(func=_cmd_memory_repair_authority)

    memory_eval_parser = memory_sub.add_parser("eval", help="Run deterministic memory recovery checks.")
    _add_common(memory_eval_parser)
    memory_eval_parser.add_argument("--repo-root", type=Path, default=ROOT)
    memory_eval_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_eval_parser.add_argument("--skip-seed", action="store_true")
    memory_eval_parser.add_argument("--require-checkpoint", action="store_true")
    memory_eval_parser.add_argument("--prompt-only", action="store_true")
    memory_eval_parser.set_defaults(func=_cmd_memory_eval)

    memory_agent_eval = memory_sub.add_parser("agent-eval", help="Run deterministic agent control-plane eval harness.")
    _add_common(memory_agent_eval)
    memory_agent_eval.add_argument("--repo-root", type=Path, default=ROOT)
    memory_agent_eval.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_agent_eval.add_argument("--skip-seed", action="store_true")
    memory_agent_eval.add_argument("--prompt-only", action="store_true")
    memory_agent_eval.set_defaults(func=_cmd_memory_agent_eval)

    memory_operator_dashboard = memory_sub.add_parser(
        "operator-dashboard",
        help="Show automatic memory/dream/retrieval/provenance health for audit.",
    )
    memory_operator_dashboard.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_operator_dashboard.add_argument("--runs-dir", type=Path, default=DEFAULT_DREAM_RUNS_DIR)
    memory_operator_dashboard.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_operator_dashboard.add_argument("--limit", type=int, default=8)
    memory_operator_dashboard.add_argument("--prompt-only", action="store_true")
    memory_operator_dashboard.add_argument("--json", action="store_true")
    memory_operator_dashboard.set_defaults(func=_cmd_memory_operator_dashboard)

    memory_zero = memory_sub.add_parser(
        "record-zero-candidate",
        help="Record a research-only zero-candidate episode in provenance memory.",
    )
    _add_common(memory_zero)
    memory_zero.add_argument("--lane", required=True)
    memory_zero.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_zero.add_argument("--selection-date", required=True)
    memory_zero.add_argument("--drop-stage", action="append", default=[], help="Stage count as KEY=VALUE.")
    memory_zero.add_argument("--blocker-summary", default="")
    memory_zero.add_argument("--source-ref")
    memory_zero.add_argument("--metadata", default="{}")
    memory_zero.add_argument("--episode-id")
    memory_zero.set_defaults(func=_cmd_memory_record_zero_candidate)

    memory_research = memory_sub.add_parser(
        "research-priorities",
        help="Rank research-only provenance priorities without changing trading gates.",
    )
    memory_research.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_research.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_research.add_argument("--limit", type=int, default=10)
    memory_research.add_argument("--prompt-only", action="store_true")
    memory_research.add_argument("--json", action="store_true")
    memory_research.set_defaults(func=_cmd_memory_research_priorities)

    memory_profit_sync = memory_sub.add_parser(
        "profit-learning-sync",
        help="Dry-run or write research-only profit-learning provenance from allowlisted generated readbacks.",
    )
    _add_common(memory_profit_sync)
    memory_profit_sync.add_argument("--repo-root", type=Path, default=ROOT)
    memory_profit_sync.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_profit_sync.add_argument(
        "--artifact",
        action="append",
        default=[],
        choices=sorted(PROFIT_LEARNING_ARTIFACTS),
        help="Restrict sync to one allowlisted artifact kind. Repeatable.",
    )
    memory_profit_sync.add_argument("--write-memory", action="store_true")
    memory_profit_sync.add_argument("--approval-token", default="")
    memory_profit_sync.add_argument("--prompt-only", action="store_true")
    memory_profit_sync.set_defaults(func=_cmd_memory_profit_learning_sync)

    memory_profit_audit = memory_sub.add_parser(
        "profit-learning-audit",
        help="Audit profit-learning sync readiness and current research-priority coverage.",
    )
    memory_profit_audit.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_profit_audit.add_argument("--repo-root", type=Path, default=ROOT)
    memory_profit_audit.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_profit_audit.add_argument(
        "--artifact",
        action="append",
        default=[],
        choices=sorted(PROFIT_LEARNING_ARTIFACTS),
        help="Restrict audit to one allowlisted artifact kind. Repeatable.",
    )
    memory_profit_audit.add_argument("--prompt-only", action="store_true")
    memory_profit_audit.add_argument("--json", action="store_true")
    memory_profit_audit.set_defaults(func=_cmd_memory_profit_learning_audit)

    digest_parser = subparsers.add_parser("digest", help="Summarize task and graph state.")
    digest_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    digest_parser.add_argument("--recent-limit", type=int, default=8)
    digest_parser.add_argument("--json", action="store_true")
    digest_parser.set_defaults(func=_cmd_digest)
    return parser


def _cmd_seed_project(args: argparse.Namespace) -> int:
    result = seed_project_memory(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        include_static_memory_graph=not args.no_static_memory_graph,
        include_gateboard=not args.no_gateboard,
        include_repo_files=not args.no_repo_files,
        max_repo_files=args.max_repo_files,
        max_repo_file_bytes=args.max_repo_file_bytes,
        max_repo_body_chars=args.max_repo_body_chars,
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    metadata_filter = parse_json_object(args.metadata_filter, field_name="metadata_filter")
    metadata_filter.update(parse_key_value_filters(args.metadata, field_name="metadata"))
    result = bootstrap_project_context(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        seed=not args.skip_seed,
        query=args.query,
        metadata_filter=metadata_filter,
        max_depth=args.max_depth,
        max_context_nodes=args.max_context_nodes,
        max_context_edges=args.max_context_edges,
        include_repo_files=not args.no_repo_files,
        max_repo_files=args.max_repo_files,
        max_repo_file_bytes=args.max_repo_file_bytes,
        max_repo_body_chars=args.max_repo_body_chars,
        manifest_dir=args.manifest_dir,
    )
    if args.prompt_only:
        print(result["prompt_context"])
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_checkpoint_write(args: argparse.Namespace) -> int:
    result = write_checkpoint(
        db_path=args.db,
        events_path=args.events,
        objective=args.objective,
        scope=args.scope,
        status=args.status,
        summary=args.summary,
        success_criteria=args.success_criteria,
        constraints=args.constraint,
        autonomy_level=args.autonomy_level,
        next_actions=args.next_action,
        verification=args.verification,
        blockers=args.blocker,
        files_changed=args.file,
        commands_run=args.command,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
    )
    if args.prompt_only:
        print(_format_checkpoint_context(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_checkpoint_latest(args: argparse.Namespace) -> int:
    result = latest_checkpoint(db_path=args.db)
    if args.prompt_only:
        print(_format_checkpoint_context(result))
        return 0
    _emit(result or {"checkpoint": None}, as_json=True if args.json else False)
    return 0


def _cmd_task_create(args: argparse.Namespace) -> int:
    result = create_task(
        db_path=args.db,
        events_path=args.events,
        title=args.title,
        description=args.description,
        pathway=args.pathway,
        permission_mode=args.permission_mode,
        priority=args.priority,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        ack_high_risk=args.ack_high_risk,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_task_claim(args: argparse.Namespace) -> int:
    result = claim_task(
        db_path=args.db,
        events_path=args.events,
        task_id=args.task_id,
        worker_id=args.worker_id,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_task_report(args: argparse.Namespace) -> int:
    result = report_task(
        db_path=args.db,
        events_path=args.events,
        task_id=args.task_id,
        worker_id=args.worker_id,
        finding=args.finding,
        proof_gate_status=args.proof_gate_status,
        recommendation=args.recommendation,
        verification=args.verification,
        blockers=args.blockers,
        files_read=args.files_read,
        commands_run=args.commands_run,
        artifacts_written=args.artifacts_written,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_task_accept(args: argparse.Namespace) -> int:
    result = accept_task(
        db_path=args.db,
        events_path=args.events,
        task_id=args.task_id,
        accepted_by=args.accepted_by,
        summary=args.summary,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_writeback(args: argparse.Namespace) -> int:
    with closing(connect(args.db)) as conn:
        _task_row(conn, args.task_id)
        if _latest_task_report(conn, args.task_id) is None:
            raise AgentControlError(
                f"writeback requires a worker report for task {args.task_id}; "
                "use task accept for non-report acceptance"
            )
    result = accept_task(
        db_path=args.db,
        events_path=args.events,
        task_id=args.task_id,
        accepted_by=args.accepted_by,
        summary=args.summary,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
    )
    if not result.get("writeback_node_ids"):
        raise AgentControlError(f"writeback accepted task {args.task_id} but wrote no operating memory")
    _emit(result, as_json=args.json)
    return 0


def _cmd_task_list(args: argparse.Namespace) -> int:
    result = list_tasks(db_path=args.db, status=args.status, pathway=args.pathway, limit=args.limit)
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_graph_remember(args: argparse.Namespace) -> int:
    result = remember_graph_node(
        db_path=args.db,
        events_path=args.events,
        kind=args.kind,
        title=args.title,
        body=args.body,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        source_ref=args.source_ref,
        node_id=args.node_id,
        upsert=not args.no_upsert,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_graph_link(args: argparse.Namespace) -> int:
    result = link_graph_nodes(
        db_path=args.db,
        events_path=args.events,
        source_node_id=args.source,
        relation=args.relation,
        target_node_id=args.target,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        source_ref=args.source_ref,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_graph_query(args: argparse.Namespace) -> int:
    metadata_filter = parse_json_object(args.metadata_filter, field_name="metadata_filter")
    metadata_filter.update(parse_key_value_filters(args.metadata, field_name="metadata"))
    result = query_graph(
        db_path=args.db,
        query=args.query,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        kind=args.kind,
        metadata_filter=metadata_filter,
        memory_type=args.memory_type,
        include_inactive=args.include_inactive,
        fresh_only=args.fresh_only,
        limit=args.limit,
        max_depth=args.max_depth,
        include_prompt_context=args.context or args.prompt_only,
        max_context_nodes=args.max_context_nodes,
        max_context_edges=args.max_context_edges,
        include_repo_index=args.include_repo_index,
    )
    if args.prompt_only:
        print(result["prompt_context"])
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_context_pack(args: argparse.Namespace) -> int:
    result = build_context_pack(
        db_path=args.db,
        goal=args.goal,
        pathway=args.pathway,
        tenant_id=args.tenant_id,
        limit=args.limit,
        include_prompt_context=True,
        manifest_dir=args.manifest_dir,
    )
    if args.prompt_only:
        print(result["prompt_context"])
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_session_log(args: argparse.Namespace) -> int:
    result = log_session(
        db_path=args.db,
        events_path=args.events,
        sessions_path=args.sessions,
        transcript_path=args.transcript,
        repo_root=args.repo_root,
        session_id=args.session_id,
        title=args.title,
        summary=args.summary,
        actor=args.actor,
        expected_sha256=args.expected_sha256,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_propose(args: argparse.Namespace) -> int:
    result = propose_dream(
        db_path=args.db,
        events_path=args.events,
        proposal_path=args.file,
        repo_root=args.repo_root,
        dream_id=args.dream_id,
        title=args.title,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        expected_sha256=args.expected_sha256,
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_accept(args: argparse.Namespace) -> int:
    result = accept_dream(
        db_path=args.db,
        events_path=args.events,
        dream_id=args.dream_id,
        accepted_by=args.accepted_by,
        note=args.note,
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_reject(args: argparse.Namespace) -> int:
    result = reject_dream(
        db_path=args.db,
        events_path=args.events,
        dream_id=args.dream_id,
        rejected_by=args.rejected_by,
        reason=args.reason,
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_list(args: argparse.Namespace) -> int:
    result = list_dreams(
        db_path=args.db,
        tenant_id=args.tenant_id,
        status=args.status,
        limit=args.limit,
    )
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_review(args: argparse.Namespace) -> int:
    result = review_dreams(
        db_path=args.db,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_dream_review(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_run(args: argparse.Namespace) -> int:
    result = run_dream_cycle(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        dreams_dir=args.dreams_dir,
        runs_dir=args.runs_dir,
        tenant_id=args.tenant_id,
        limit=args.limit,
        actor=args.actor,
        generate_from_sessions=not args.no_generate_from_sessions,
        auto_resolve=not args.no_auto_resolve,
    )
    if args.prompt_only:
        print(_format_dream_run_audit(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_dream_audit(args: argparse.Namespace) -> int:
    result = dream_audit(
        db_path=args.db,
        runs_dir=args.runs_dir,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_dream_audit(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


def _cmd_audit_alias(args: argparse.Namespace) -> int:
    result = memory_audit(
        db_path=args.db,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    print(_format_memory_audit(result))
    return 0


def _cmd_dreams_alias(args: argparse.Namespace) -> int:
    result = review_dreams(
        db_path=args.db,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.json:
        _emit(result, as_json=True)
        return 0
    print(_format_dream_review(result))
    return 0


def _cmd_run_event(args: argparse.Namespace) -> int:
    result = record_agent_run_event(
        db_path=args.db,
        events_path=args.events,
        run_id=args.run_id,
        event_type=args.event_type,
        title=args.title,
        summary=args.summary,
        status=args.status,
        actor=args.actor,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        payload=parse_json_object(args.payload, field_name="payload"),
    )
    if args.prompt_only:
        print(
            "\n".join(
                [
                    "# Agent Run Event",
                    f"Run: {result['run_id']}",
                    f"Event: {result['event_type']}",
                    f"Status: {result['status']}",
                    f"Hash: {result['event_hash']}",
                ]
            )
        )
        return 0
    _emit(result, as_json=args.json)
    return 0


def _cmd_run_list(args: argparse.Namespace) -> int:
    result = agent_run_ledger_report(
        db_path=args.db,
        tenant_id=args.tenant_id,
        status=args.status,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_agent_run_ledger(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_run_show(args: argparse.Namespace) -> int:
    result = get_agent_run(db_path=args.db, run_id=args.run_id, tenant_id=args.tenant_id)
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_memory_run_ledger(args: argparse.Namespace) -> int:
    result = agent_run_ledger_report(
        db_path=args.db,
        tenant_id=args.tenant_id,
        status=args.status,
        limit=args.limit,
    )
    if args.prompt_only or not args.json:
        print(_format_agent_run_ledger(result))
        return 0
    _emit(result, as_json=True)
    return 0


def _cmd_memory_anchor_ledger(args: argparse.Namespace) -> int:
    result = agent_run_anchor_report(
        db_path=args.db,
        events_path=args.events,
        anchors_path=args.anchors,
        tenant_id=args.tenant_id,
        write_anchor=args.write_anchor,
        anchor_type=args.anchor_type,
    )
    if args.prompt_only or not args.json:
        print(_format_agent_run_anchor_report(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_backup(args: argparse.Namespace) -> int:
    result = create_memory_backup(
        db_path=args.db,
        events_path=args.events,
        anchors_path=args.anchors,
        sessions_path=args.sessions,
        backup_root=args.backup_root,
        tenant_id=args.tenant_id,
        write_anchor=not args.no_anchor,
    )
    if args.prompt_only or not args.json:
        print(_format_memory_backup(result))
        return 0
    _emit(result, as_json=True)
    return 0


def _cmd_memory_restore_check(args: argparse.Namespace) -> int:
    result = restore_check_memory_backup(
        backup_dir=args.backup_dir,
        tenant_id=args.tenant_id,
    )
    if args.prompt_only or not args.json:
        print(_format_restore_check(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_doctor(args: argparse.Namespace) -> int:
    result = memory_doctor(
        db_path=args.db,
        events_path=args.events,
        anchors_path=args.anchors,
        sessions_path=args.sessions,
        backup_root=args.backup_root,
        runs_dir=args.runs_dir,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        write_backup=args.write_backup,
        max_backup_age_hours=args.max_backup_age_hours,
    )
    if args.prompt_only or not args.json:
        print(_format_memory_doctor(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_maintenance(args: argparse.Namespace) -> int:
    result = memory_maintenance(
        db_path=args.db,
        events_path=args.events,
        anchors_path=args.anchors,
        sessions_path=args.sessions,
        backup_root=args.backup_root,
        runs_dir=args.runs_dir,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        actor=args.actor,
        max_backup_age_hours=args.max_backup_age_hours,
    )
    if args.prompt_only or not args.json:
        print(_format_memory_maintenance(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_ingest_living_history(args: argparse.Namespace) -> int:
    result = ingest_living_history(
        db_path=args.db,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
    )
    if args.prompt_only or not args.json:
        print(_format_living_history_ingest(result))
        return 0 if str(result.get("status", "")).startswith("pass") else 1
    _emit(result, as_json=True)
    return 0 if str(result.get("status", "")).startswith("pass") else 1


def _cmd_memory_auto_maintenance(args: argparse.Namespace) -> int:
    result = memory_auto_maintenance(
        db_path=args.db,
        events_path=args.events,
        anchors_path=args.anchors,
        sessions_path=args.sessions,
        backup_root=args.backup_root,
        runs_dir=args.runs_dir,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        actor=args.actor,
        min_interval_hours=args.min_interval_hours,
        max_success_age_hours=args.max_success_age_hours,
        max_backup_age_hours=args.max_backup_age_hours,
        force=args.force,
    )
    if args.prompt_only or not args.json:
        print(_format_memory_auto_maintenance(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_daily_brief(args: argparse.Namespace) -> int:
    result = daily_operator_brief(
        db_path=args.db,
        runs_dir=args.runs_dir,
        tenant_id=args.tenant_id,
        since_hours=args.since_hours,
        stale_hours=args.stale_hours,
        limit=args.limit,
    )
    if args.prompt_only or not args.json:
        print(_format_daily_operator_brief(result))
        return 0
    _emit(result, as_json=True)
    return 0


def _cmd_memory_blocker_autopsy(args: argparse.Namespace) -> int:
    result = blocker_autopsy_report(
        db_path=args.db,
        tenant_id=args.tenant_id,
        min_count=args.min_count,
        limit=args.limit,
    )
    if args.prompt_only or not args.json:
        print(_format_blocker_autopsy_report(result))
        return 0
    _emit(result, as_json=True)
    return 0


def _cmd_memory_inbox(args: argparse.Namespace) -> int:
    result = local_inbox_report(
        db_path=args.db,
        tenant_id=args.tenant_id,
        stale_hours=args.stale_hours,
        limit=args.limit,
    )
    if args.prompt_only or not args.json:
        print(_format_local_inbox_report(result))
        return 0
    _emit(result, as_json=True)
    return 0


def _cmd_memory_remember(args: argparse.Namespace) -> int:
    result = remember_operating_memory(
        db_path=args.db,
        events_path=args.events,
        memory_type=args.type,
        title=args.title,
        body=args.body,
        tenant_id=args.tenant_id,
        sub_tenant_id=args.sub_tenant_id,
        memory_status=args.status,
        confidence=args.confidence,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        source_ref=args.source_ref,
        node_id=args.node_id,
        supersedes=args.supersedes,
        freshness_days=args.freshness_days,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_memory_supersede(args: argparse.Namespace) -> int:
    result = supersede_memory(
        db_path=args.db,
        events_path=args.events,
        old_node_id=args.old,
        new_node_id=args.new,
        reason=args.reason,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_memory_audit(args: argparse.Namespace) -> int:
    result = memory_audit(
        db_path=args.db,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_memory_audit(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_memory_repair_authority(args: argparse.Namespace) -> int:
    result = repair_operating_memory_authority_metadata(
        db_path=args.db,
        tenant_id=args.tenant_id,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_memory_eval(args: argparse.Namespace) -> int:
    result = memory_eval(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        seed=not args.skip_seed,
        require_checkpoint=args.require_checkpoint,
    )
    if args.prompt_only:
        print(_format_memory_eval(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_agent_eval(args: argparse.Namespace) -> int:
    result = agent_eval_harness(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        seed=not args.skip_seed,
    )
    if args.prompt_only:
        print(_format_agent_eval_harness(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_operator_dashboard(args: argparse.Namespace) -> int:
    result = operator_dashboard(
        db_path=args.db,
        runs_dir=args.runs_dir,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_operator_dashboard(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


def _cmd_memory_record_zero_candidate(args: argparse.Namespace) -> int:
    result = record_zero_candidate_episode(
        db_path=args.db,
        events_path=args.events,
        tenant_id=args.tenant_id,
        lane=args.lane,
        selection_date=args.selection_date,
        drop_stage_counts=parse_key_value_filters(args.drop_stage, field_name="drop_stage"),
        blocker_summary=args.blocker_summary,
        source_ref=args.source_ref,
        metadata=parse_json_object(args.metadata, field_name="metadata"),
        episode_id=args.episode_id,
    )
    _emit(result, as_json=args.json)
    return 0


def _cmd_memory_research_priorities(args: argparse.Namespace) -> int:
    result = research_priority_report(
        db_path=args.db,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
    if args.prompt_only:
        print(_format_research_priority_report(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_memory_profit_learning_sync(args: argparse.Namespace) -> int:
    if args.approval_token and args.approval_token != PROFIT_LEARNING_SYNC_TOKEN:
        raise AgentControlError("invalid profit-learning sync approval token")
    if args.write_memory and args.approval_token != PROFIT_LEARNING_SYNC_TOKEN:
        raise AgentControlError("profit-learning writes require --approval-token APPROVE_PROFIT_LEARNING_MEMORY_SYNC")
    write_memory = bool(args.write_memory)
    result = profit_learning_sync(
        db_path=args.db,
        events_path=args.events,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        artifact_names=args.artifact or None,
        write_memory=write_memory,
    )
    if args.prompt_only:
        print(_format_profit_learning_sync(result))
        return 0
    _emit(result, as_json=True if args.json else False)
    return 0


def _cmd_memory_profit_learning_audit(args: argparse.Namespace) -> int:
    result = profit_learning_audit(
        db_path=args.db,
        repo_root=args.repo_root,
        tenant_id=args.tenant_id,
        artifact_names=args.artifact or None,
    )
    if args.prompt_only:
        print(_format_profit_learning_audit(result))
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


def _cmd_digest(args: argparse.Namespace) -> int:
    result = digest(db_path=args.db, recent_limit=args.recent_limit)
    _emit(result, as_json=True if args.json else False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AgentControlError as exc:
        print(f"agent_control: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
