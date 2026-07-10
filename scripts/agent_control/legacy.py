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
import threading
import time
import uuid
from collections import deque
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.archive_project_memory import verify_archive_manifest as _verify_project_memory_archive_manifest
except ModuleNotFoundError:  # pragma: no cover - direct script execution from scripts/
    from archive_project_memory import verify_archive_manifest as _verify_project_memory_archive_manifest


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
CONTROL_SCHEMA_VERSION = "agent_control_schema_v5"
BACKUP_MANIFEST_VERSION = "agent_memory_backup_v2"
EVENT_OUTBOX_HASH_VERSION_V1 = "event_outbox_hash_v1"
EVENT_OUTBOX_HASH_VERSION_V2 = "event_outbox_hash_v2"
DEFAULT_REPO_INDEX_MAX_FILES = 2000
DEFAULT_REPO_INDEX_MAX_FILE_BYTES = 256_000
DEFAULT_REPO_INDEX_BODY_CHARS = 12_000
DEFAULT_CHECKPOINT_AUTONOMY_LEVEL = "read_only_workers"
DEFAULT_CONTEXT_PACK_LIMIT = 6
DEFAULT_MEMORY_GOLDEN_QUERIES_PATH = ROOT / "data" / "contracts" / "memory-golden-queries.json"
LIVING_HISTORY_INGEST_VERSION = "living_history_ingest_v1"
LIVING_HISTORY_SOURCE_TYPE = "living_history_ingest"
LIVING_HISTORY_REQUIRED_SOURCE_PATHS = ("docs/WORKLOG.md", "docs/DECISIONS.md")
LIVING_HISTORY_EXPECTATION_PREFIX = f"required:{LIVING_HISTORY_SOURCE_TYPE}:"
LIVING_HISTORY_ACTIVATION_EVENT_TYPE = "memory.living_history.sources_activated"
PROJECT_MEMORY_ARCHIVE_RELATIVE_ROOT = "docs/archive/project-memory"

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
TRADING_FAIL_CLOSED_PERMISSION_MODES = {"context_only", "read_only_workers", "code_docs"}
PROOF_GATE_STATUSES = {
    "not_applicable",
    "not_applicable_observe_only",
    "observe_only",
    "pass",
    "passed",
    "blocked",
    "failed",
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
DREAM_OBSERVED_EVIDENCE_NODE_KINDS = {"evidence_artifact", "episode"}
DREAM_OBSERVED_EVIDENCE_SOURCE_TYPES = {
    "session_transcript",
    "operating_memory",
    "gateboard_source_artifact",
    "profit_learning_sync",
    "research_provenance",
}
TRUSTED_EVIDENCE_ATTESTATION_KEY = "trusted_writer_attestation"
TRUSTED_EVIDENCE_ATTESTATION_VERSION = "trusted_evidence_writer_v1"
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
REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES = {
    "living_doc",
    "control_plane_doc",
    "startup_doc",
    "package_manifest",
    "gateboard_blocker",
    "gateboard_doc",
    "gateboard_latest",
    "gateboard_latest_json",
    "gateboard_pathway",
    "gateboard_source_artifact",
    LIVING_HISTORY_SOURCE_TYPE,
}
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
MEMORY_SECRET_SHAPED_RE = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\bgh[opsru]_[A-Za-z0-9_]{20,}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----",
        r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b",
        r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\s*[:=]\s*"
        r"(?!\[?redacted\]?|<|\$\{|your[_-])[A-Za-z0-9_./+=-]{12,}",
    )
)
MEMORY_ACTION_IMPERATIVE_RE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:buy|sell)\s+\d+\s+[A-Z]{1,6}\s+(?:calls?|puts?)\b(?:\s+now\b)?",
        r"\b(?:send|submit|place|open|close|cancel|create)\s+(?:an?\s+)?order\s+for\s+\d+\s+"
        r"[A-Z]{1,6}\s+(?:calls?|puts?)\b",
    )
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
GATEBOARD_SOURCE_ARTIFACT_HASH_ROOTS = {
    "data/ai-commodity-infra",
    "data/contracts",
    "data/forward-tracking",
    "data/profitability-lab",
    "docs",
}
GATEBOARD_SOURCE_ARTIFACT_HASH_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt"}
GATEBOARD_SOURCE_ARTIFACT_DENIED_NAMES = {
    ".env",
    ".env.local",
    "auth.json",
    "credentials.json",
    "secrets.json",
}
REPO_FILE_SOURCE_TYPES = {"repo_file_index"}
FILE_FRESHNESS_SOURCE_TYPES = {
    "repo_file_index",
    "living_doc",
    "control_plane_doc",
    "startup_doc",
    LIVING_HISTORY_SOURCE_TYPE,
} | REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES
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
    PROJECT_MEMORY_ARCHIVE_RELATIVE_ROOT,
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
        "config.yml",
        ".npmrc",
        ".netrc",
        "_netrc",
        ".pypirc",
        "cookies",
        "cookies-journal",
        "login data",
        "login data-journal",
        "web data",
        "local state",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
    secret_suffixes = (".key", ".pem", ".p12", ".pfx", ".ppk", ".sqlite", ".db")
    if name in secret_names or name.startswith(".env.") or name.endswith(secret_suffixes):
        raise AgentControlError(f"memory capture refuses secret or database path: {relative_path}")
    if name.startswith("id_") and "." not in name:
        raise AgentControlError(f"memory capture refuses private-key path: {relative_path}")
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
        ".aws/",
        ".ssh/",
        "appdata/local/google/chrome/user data/",
        "appdata/local/microsoft/edge/user data/",
        "appdata/local/bravesoftware/brave-browser/user data/",
        "appdata/roaming/mozilla/firefox/profiles/",
        "browser-profiles/",
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
    for pattern in MEMORY_SECRET_SHAPED_RE:
        if pattern.search(haystack):
            errors.append(f"{field_name} contains secret-shaped content")
            break
    for pattern in MEMORY_ACTION_IMPERATIVE_RE:
        if pattern.search(haystack):
            errors.append(f"{field_name} contains a targeted options-order imperative")
            break
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


def _quarantine_retrieval_metadata(value: Any, *, path: str = "metadata") -> tuple[Any, list[str]]:
    quarantined: list[str] = []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in PROHIBITED_TRUE_FLAG_KEYS:
                quarantined.append(child_path)
                continue
            if key in AUTHORITY_METADATA_KEYS:
                continue
            sanitized_child, child_quarantine = _quarantine_retrieval_metadata(child, path=child_path)
            result[key] = sanitized_child
            quarantined.extend(child_quarantine)
        return result, quarantined
    if isinstance(value, list):
        result_list: list[Any] = []
        for index, child in enumerate(value):
            sanitized_child, child_quarantine = _quarantine_retrieval_metadata(
                child,
                path=f"{path}[{index}]",
            )
            result_list.append(sanitized_child)
            quarantined.extend(child_quarantine)
        return result_list, quarantined
    return value, quarantined


def _prohibited_metadata_paths(value: Any, *, path: str = "metadata") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            truthy = child is True or (
                isinstance(child, (int, float)) and not isinstance(child, bool) and child == 1
            ) or (
                isinstance(child, str)
                and child.strip().lower() in {"true", "1", "yes", "y", "on", "enabled", "ready", "approved"}
            )
            if key in PROHIBITED_TRUE_FLAG_KEYS and truthy:
                paths.append(child_path)
            paths.extend(_prohibited_metadata_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_prohibited_metadata_paths(child, path=f"{path}[{index}]"))
    return paths


def _metadata_for_retrieval(metadata: dict[str, Any]) -> dict[str, Any]:
    source_type = metadata.get("source_type")
    sanitized_value, quarantined = _quarantine_retrieval_metadata(metadata)
    sanitized = dict(sanitized_value) if isinstance(sanitized_value, dict) else {}
    if source_type == "dream_proposal":
        sanitized.pop("entries", None)
        sanitized["entries_omitted_from_retrieval"] = True
    if quarantined:
        sanitized["quarantined_metadata_count"] = len(set(quarantined))
    sanitized.update(OPERATING_AUTHORITY_METADATA)
    sanitized["capability_label"] = "coordination_only"
    sanitized["memory_policy_version"] = MEMORY_POLICY_VERSION
    sanitized["non_authoritative"] = True
    sanitized["non_authorization_notice"] = MEMORY_NON_AUTHORIZATION_BANNER
    return sanitized


def _metadata_for_prompt(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata") or {}
    return _metadata_for_retrieval(metadata)


def _non_operating_policy_errors(title: str, body: str, metadata: dict[str, Any]) -> list[str]:
    return _validate_memory_policy_text(
        title=title,
        body=body,
        metadata=metadata,
        field_name="graph retrieval context",
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
    title, body = _node_retrieval_title_body(node, metadata)
    return {
        **node,
        "title": title,
        "body": body,
        "metadata": _metadata_for_retrieval(metadata),
    }


def _edge_for_query_result(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        **edge,
        "metadata": _metadata_for_retrieval(edge.get("metadata") or {}),
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
        ("retrieval_parity_issues", "Graph/retrieval parity issues"),
        ("required_freshness_issues", "Required living/startup/gateboard freshness issues"),
        ("tier3_repo_mirror_gaps_nonfatal", "Tier-3 repo mirror gaps (nonfatal)"),
        ("quarantined_metadata", "Prohibited legacy action metadata"),
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


def _effective_events_path(*, db_path: Path, events_path: Path) -> Path:
    resolved_db = db_path.resolve()
    if events_path.resolve() == DEFAULT_EVENTS_PATH.resolve() and resolved_db != DEFAULT_DB_PATH.resolve():
        return resolved_db.parent / "events.jsonl"
    return events_path


def _effective_sessions_path(*, db_path: Path, sessions_path: Path) -> Path:
    resolved_db = db_path.resolve()
    if sessions_path.resolve() == DEFAULT_SESSIONS_PATH.resolve() and resolved_db != DEFAULT_DB_PATH.resolve():
        return resolved_db.parent / "sessions.jsonl"
    return sessions_path


def _effective_anchors_path(*, db_path: Path, anchors_path: Path) -> Path:
    resolved_db = db_path.resolve()
    if anchors_path.resolve() == DEFAULT_ANCHORS_PATH.resolve() and resolved_db != DEFAULT_DB_PATH.resolve():
        return resolved_db.parent / "anchors.jsonl"
    return anchors_path


def _connection_db_path(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        return None
    return Path(str(row[2])).resolve()


def _effective_events_path_for_connection(conn: sqlite3.Connection, events_path: Path) -> Path:
    db_path = _connection_db_path(conn)
    if db_path is None:
        if events_path.resolve() == DEFAULT_EVENTS_PATH.resolve():
            return Path(tempfile.gettempdir()) / f"agent-control-memory-{os.getpid()}-events.jsonl"
        return events_path
    return _effective_events_path(db_path=db_path, events_path=events_path)


def _lock_path_for_db(db_path: Path) -> Path:
    if str(db_path) == ":memory:":
        return Path(tempfile.gettempdir()) / f"agent-control-{os.getpid()}-memory.lock"
    if db_path.resolve() == DEFAULT_DB_PATH.resolve():
        return DEFAULT_LOCK_PATH
    return db_path.resolve().parent / f"{db_path.stem}.lock"


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


_CONTROL_THREAD_LOCKS_GUARD = threading.Lock()
_CONTROL_THREAD_LOCKS: dict[str, threading.RLock] = {}
_CONTROL_LOCK_LOCAL = threading.local()


def _thread_lock_for_control_path(lock_path: Path) -> threading.RLock:
    key = str(lock_path.resolve())
    with _CONTROL_THREAD_LOCKS_GUARD:
        return _CONTROL_THREAD_LOCKS.setdefault(key, threading.RLock())


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
    lock_key = str(lock_path.resolve())
    thread_lock = _thread_lock_for_control_path(lock_path)
    if not thread_lock.acquire(timeout=max(timeout_seconds, 0.0)):
        raise AgentControlError(f"agent control lock is held in this process: {lock_path}")
    depths = getattr(_CONTROL_LOCK_LOCAL, "depths", None)
    if depths is None:
        depths = {}
        _CONTROL_LOCK_LOCAL.depths = depths
    if depths.get(lock_key, 0):
        depths[lock_key] += 1
        try:
            yield
        finally:
            depths[lock_key] -= 1
            thread_lock.release()
        return
    depths[lock_key] = 1
    handle: int | None = None
    owner_token = uuid.uuid4().hex
    try:
        while handle is None:
            try:
                handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, f"{os.getpid()} {utc_now()} {owner_token}\n".encode("utf-8"))
            except FileExistsError:
                stale = False
                lock_text = ""
                inspection_error: OSError | None = None
                try:
                    lock_text = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
                    pid_text = lock_text.split(maxsplit=1)[0] if lock_text else ""
                    if pid_text.isdigit():
                        stale = not _process_exists(int(pid_text))
                    else:
                        stale = time.time() - lock_path.stat().st_mtime > stale_seconds
                except PermissionError as exc:
                    inspection_error = exc
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    inspection_error = exc
                if stale:
                    try:
                        if lock_path.read_text(encoding="utf-8", errors="ignore").strip() == lock_text:
                            lock_path.unlink()
                            continue
                    except FileNotFoundError:
                        continue
                    except PermissionError as exc:
                        inspection_error = exc
                if time.monotonic() >= deadline:
                    if inspection_error is not None:
                        raise AgentControlError(
                            f"agent control lock cannot be inspected or removed: {lock_path}: {inspection_error}"
                        ) from inspection_error
                    raise AgentControlError(f"agent control lock is held: {lock_path}")
                time.sleep(poll_seconds)
        yield
    finally:
        try:
            if handle is not None:
                os.close(handle)
                handle = None
                for attempt in range(5):
                    try:
                        lock_text = lock_path.read_text(encoding="utf-8", errors="ignore").strip()
                        parts = lock_text.split(maxsplit=2)
                        if len(parts) != 3 or parts[2] != owner_token:
                            break
                        lock_path.unlink()
                        break
                    except FileNotFoundError:
                        break
                    except PermissionError as exc:
                        if attempt == 4:
                            raise AgentControlError(f"agent control lock could not be released: {lock_path}: {exc}") from exc
                        time.sleep(0.05)
        finally:
            depths.pop(lock_key, None)
            thread_lock.release()


def _schema_is_current(conn: sqlite3.Connection) -> bool:
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if table_exists is None:
        return False
    if conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (CONTROL_SCHEMA_VERSION,),
    ).fetchone() is None:
        return False
    required_tenant_tables = {
        "tasks",
        "task_claims",
        "task_reports",
        "evidence_artifacts",
        "decisions",
        "worker_runs",
    }
    for table_name in required_tenant_tables:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if "tenant_id" not in columns:
            return False
    required_tables = {"session_sidecar_outbox", "retrieval_source_expectations"}
    present_tables = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({})".format(
                ", ".join("?" for _ in required_tables)
            ),
            tuple(sorted(required_tables)),
        ).fetchall()
    }
    if present_tables != required_tables:
        return False
    outbox_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(event_outbox)").fetchall()}
    if not {"tenant_id", "hash_version"}.issubset(outbox_columns):
        return False
    required_indexes = {
        "idx_tasks_tenant_status",
        "idx_task_claims_tenant_task",
        "idx_task_reports_tenant_task",
        "idx_worker_runs_tenant_task",
        "idx_task_claims_one_active",
        "idx_event_outbox_tenant_id",
        "idx_retrieval_expectations_tenant",
    }
    present_indexes = {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name IN ({})".format(
                ", ".join("?" for _ in required_indexes)
            ),
            tuple(sorted(required_indexes)),
        ).fetchall()
    }
    return present_indexes == required_indexes


def _set_wal_journal_mode_with_retry(
    conn: sqlite3.Connection,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.05,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    conn.execute("PRAGMA busy_timeout=250")
    try:
        while True:
            try:
                row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
                mode = str(row[0] if row is not None else "").lower()
                if mode not in {"wal", "memory"}:
                    raise AgentControlError(f"failed to enable WAL journal mode: {mode or 'unknown'}")
                return
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "locked" not in message and "busy" not in message:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AgentControlError("timed out enabling WAL journal mode while database was busy") from exc
                time.sleep(min(poll_seconds, remaining))
    finally:
        conn.execute("PRAGMA busy_timeout=30000")


def connect(db_path: Path = DEFAULT_DB_PATH, *, maintenance: bool = False) -> sqlite3.Connection:
    _ensure_parent(db_path)
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.create_function("agent_control_maintenance", 0, lambda: 1 if maintenance else 0)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        with _control_file_lock(_lock_path_for_db(db_path), timeout_seconds=30.0):
            _set_wal_journal_mode_with_retry(conn)
            if not _schema_is_current(conn):
                init_schema(conn)
        return conn
    except Exception:
        conn.close()
        raise


def init_schema(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.commit()
    try:
        _init_schema_exclusive(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _init_schema_exclusive(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        BEGIN EXCLUSIVE;
        DROP TRIGGER IF EXISTS trg_agent_run_events_append_only_delete;
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
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
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            claimed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS task_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            worker_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
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
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            path TEXT NOT NULL,
            evidence_class TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS worker_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
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
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL DEFAULT '',
            event_hash TEXT NOT NULL,
            hash_version TEXT NOT NULL DEFAULT 'event_outbox_hash_v2',
            delivered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS session_sidecar_outbox (
            session_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT 'options-chatbot',
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            delivered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS retrieval_source_expectations (
            tenant_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(tenant_id, node_id)
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
    outbox_columns = {row["name"] for row in conn.execute("PRAGMA table_info(event_outbox)").fetchall()}
    if "tenant_id" not in outbox_columns:
        conn.execute("ALTER TABLE event_outbox ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'")
    if "hash_version" not in outbox_columns:
        conn.execute(
            "ALTER TABLE event_outbox ADD COLUMN hash_version TEXT NOT NULL DEFAULT 'event_outbox_hash_v1'"
        )
    conn.execute(
        """
        UPDATE event_outbox
        SET tenant_id = COALESCE(
            CASE WHEN json_valid(payload_json) THEN NULLIF(json_extract(payload_json, '$.tenant_id'), '') END,
            CASE WHEN json_valid(payload_json) THEN NULLIF(json_extract(payload_json, '$.payload.tenant_id'), '') END,
            tenant_id,
            ?
        )
        """,
        (DEFAULT_TENANT_ID,),
    )
    conn.execute(
        "UPDATE event_outbox SET hash_version = ? WHERE hash_version IS NULL OR hash_version = ''",
        (EVENT_OUTBOX_HASH_VERSION_V1,),
    )
    task_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "tenant_id" not in task_columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'")
    for table_name in ("task_claims", "task_reports", "evidence_artifacts", "decisions", "worker_runs"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if "tenant_id" not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'options-chatbot'")
    conn.execute(
        """
        UPDATE tasks
        SET tenant_id = (
            SELECT graph_nodes.tenant_id FROM graph_nodes WHERE graph_nodes.id = 'task:' || tasks.id
        )
        WHERE EXISTS (SELECT 1 FROM graph_nodes WHERE graph_nodes.id = 'task:' || tasks.id)
        """
    )
    for table_name in ("task_claims", "task_reports", "evidence_artifacts", "decisions", "worker_runs"):
        conn.execute(
            f"""
            UPDATE {table_name}
            SET tenant_id = COALESCE(
                (SELECT tasks.tenant_id FROM tasks WHERE tasks.id = {table_name}.task_id),
                tenant_id
            )
            """
        )
    conn.execute(
        """
        UPDATE graph_nodes
        SET tenant_id = (
            SELECT tasks.tenant_id
            FROM tasks
            WHERE tasks.id = json_extract(graph_nodes.metadata_json, '$.task_id')
        )
        WHERE json_extract(metadata_json, '$.task_id') IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM tasks
              WHERE tasks.id = json_extract(graph_nodes.metadata_json, '$.task_id')
          )
        """
    )
    conn.execute(
        """
        UPDATE task_claims
        SET status = COALESCE((SELECT tasks.status FROM tasks WHERE tasks.id = task_claims.task_id), 'closed')
        WHERE status = 'active'
          AND COALESCE((SELECT tasks.status FROM tasks WHERE tasks.id = task_claims.task_id), 'closed') <> 'claimed'
        """
    )
    conn.execute(
        """
        UPDATE task_claims
        SET status = 'superseded'
        WHERE status = 'active'
          AND id NOT IN (SELECT max(id) FROM task_claims WHERE status = 'active' GROUP BY task_id)
        """
    )
    conn.execute(
        """
        UPDATE worker_runs
        SET status = COALESCE((SELECT tasks.status FROM tasks WHERE tasks.id = worker_runs.task_id), 'closed'),
            finished_at = COALESCE(
                finished_at,
                (SELECT tasks.updated_at FROM tasks WHERE tasks.id = worker_runs.task_id),
                ?
            )
        WHERE finished_at IS NULL
          AND COALESCE((SELECT tasks.status FROM tasks WHERE tasks.id = worker_runs.task_id), 'closed') <> 'claimed'
        """,
        (utc_now(),),
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_tenant_status ON tasks(tenant_id, status, priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_claims_tenant_task ON task_claims(tenant_id, task_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_reports_tenant_task ON task_reports(tenant_id, task_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_runs_tenant_task ON worker_runs(tenant_id, task_id, status)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_task_claims_one_active ON task_claims(task_id) WHERE status = 'active'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_outbox_tenant_id ON event_outbox(tenant_id, id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_retrieval_expectations_tenant "
        "ON retrieval_source_expectations(tenant_id, source_type, node_id)"
    )
    conn.execute(
        "DELETE FROM retrieval_source_expectations WHERE source_type = ? AND node_id NOT LIKE ?",
        (LIVING_HISTORY_SOURCE_TYPE, f"{LIVING_HISTORY_EXPECTATION_PREFIX}%"),
    )
    now = utc_now()
    living_history_sources = conn.execute(
        """
        SELECT DISTINCT tenant_id, lower(json_extract(metadata_json, '$.source_path')) AS source_path
        FROM graph_nodes
        WHERE json_extract(metadata_json, '$.source_type') = ?
        """,
        (LIVING_HISTORY_SOURCE_TYPE,),
    ).fetchall()
    for source in living_history_sources:
        source_path = _safe_node_path(str(source["source_path"] or ""))
        if source_path not in {_safe_node_path(path) for path in LIVING_HISTORY_REQUIRED_SOURCE_PATHS}:
            continue
        conn.execute(
            """
            INSERT INTO retrieval_source_expectations(
                tenant_id, node_id, source_type, source_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, node_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (
                str(source["tenant_id"]),
                f"{LIVING_HISTORY_EXPECTATION_PREFIX}{source_path}",
                LIVING_HISTORY_SOURCE_TYPE,
                source_path,
                now,
                now,
            ),
        )
    for row in conn.execute("SELECT * FROM graph_nodes").fetchall():
        node = _row_dict(row)
        if node is not None:
            _upsert_retrieval_document(conn, node)
            _upsert_retrieval_source_expectation(conn, node)
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, applied_at, description)
        VALUES (?, ?, ?)
        """,
        (
            CONTROL_SCHEMA_VERSION,
            utc_now(),
            "versioned outbox integrity, serialized migration, strict backup/session parity, and retrieval provenance",
        ),
    )


@contextmanager
def _locked_db_transaction(db_path: Path, *, maintenance: bool = False):
    with _control_file_lock(_lock_path_for_db(db_path), timeout_seconds=30.0):
        with closing(connect(db_path, maintenance=maintenance)) as conn:
            with conn:
                yield conn


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
        handle.flush()
        os.fsync(handle.fileno())


def _event_outbox_hash_v2(
    *,
    prev_hash: str,
    event_id: int,
    tenant_id: str,
    event_type: str,
    created_at: str,
    payload: dict[str, Any],
) -> str:
    bound_event = {
        "id": event_id,
        "tenant_id": tenant_id,
        "event_type": event_type,
        "created_at": created_at,
        "payload": payload,
    }
    return _text_sha256(
        f"{EVENT_OUTBOX_HASH_VERSION_V2}\n{prev_hash}\n{canonical_json(bound_event)}"
    )


def _event_outbox_rows(
    conn: sqlite3.Connection,
    *,
    include_prev_hash: bool,
) -> tuple[list[sqlite3.Row], bool, bool]:
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(event_outbox)").fetchall()}
    if not columns:
        return [], False, False
    has_tenant = "tenant_id" in columns
    has_hash_version = "hash_version" in columns
    tenant_expression = "tenant_id" if has_tenant else f"'{DEFAULT_TENANT_ID}' AS tenant_id"
    version_expression = (
        "hash_version"
        if has_hash_version
        else f"'{EVENT_OUTBOX_HASH_VERSION_V1}' AS hash_version"
    )
    prev_expression = ", prev_hash" if include_prev_hash else ""
    rows = conn.execute(
        "SELECT id, {tenant}, created_at, event_type, payload_json, event_hash, {version}{prev} "
        "FROM event_outbox ORDER BY id ASC".format(
            tenant=tenant_expression,
            version=version_expression,
            prev=prev_expression,
        )
    ).fetchall()
    return rows, has_tenant, has_hash_version


def _lock_path_for_connection(conn: sqlite3.Connection) -> Path:
    db_path = _connection_db_path(conn)
    if db_path is None:
        return Path(tempfile.gettempdir()) / f"agent-control-{os.getpid()}-connection.lock"
    return _lock_path_for_db(db_path)


def _record_event(
    conn: sqlite3.Connection,
    *,
    events_path: Path,
    event_type: str,
    payload: dict[str, Any],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    events_path = _effective_events_path_for_connection(conn, events_path)
    resolved_tenant = str(tenant_id or payload.get("tenant_id") or DEFAULT_TENANT_ID)
    with _control_file_lock(_lock_path_for_connection(conn), timeout_seconds=30.0):
        created_at = utc_now()
        cursor = conn.execute(
            "INSERT INTO event_log(created_at, event_type, payload_json) VALUES (?, ?, ?)",
            (created_at, event_type, canonical_json(payload)),
        )
        previous = conn.execute(
            "SELECT event_hash FROM event_outbox ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = previous["event_hash"] if previous is not None else ""
        outbox_cursor = conn.execute(
            """
            INSERT INTO event_outbox(
                tenant_id, created_at, event_type, payload_json, prev_hash, event_hash, hash_version
            )
            VALUES (?, ?, ?, '{}', ?, '', ?)
            """,
            (resolved_tenant, created_at, event_type, prev_hash, EVENT_OUTBOX_HASH_VERSION_V2),
        )
        event_id = int(outbox_cursor.lastrowid)
        outbox_payload = {
            "outbox_event_id": event_id,
            "event_log_id": int(cursor.lastrowid),
            "tenant_id": resolved_tenant,
            "event_type": event_type,
            "created_at": created_at,
            "payload": payload,
        }
        event_hash = _event_outbox_hash_v2(
            prev_hash=prev_hash,
            event_id=event_id,
            tenant_id=resolved_tenant,
            event_type=event_type,
            created_at=created_at,
            payload=payload,
        )
        conn.execute(
            "UPDATE event_outbox SET payload_json = ?, event_hash = ? WHERE id = ?",
            (canonical_json(outbox_payload), event_hash, event_id),
        )
        row = conn.execute(
            "SELECT id, tenant_id, created_at, event_type, payload_json, event_hash, hash_version "
            "FROM event_outbox WHERE id = ?",
            (event_id,),
        ).fetchone()
        event = _event_mirror_row(row)
        _append_jsonl(events_path, event)
        return event


def validate_event_outbox(conn: sqlite3.Connection) -> dict[str, Any]:
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'event_outbox'"
    ).fetchone() is None:
        return {
            "status": "issues",
            "count": 0,
            "hash_version_counts": {},
            "issues": [{"issue": "event_outbox table is missing"}],
        }
    rows, has_tenant_column, _has_hash_version_column = _event_outbox_rows(
        conn,
        include_prev_hash=True,
    )
    issues: list[dict[str, Any]] = []
    previous_hash = ""
    version_counts: dict[str, int] = {}
    for row in rows:
        payload_json = row["payload_json"] or "{}"
        try:
            wrapper = json.loads(payload_json)
        except json.JSONDecodeError:
            issues.append({"id": row["id"], "issue": "payload_json is not valid JSON"})
            wrapper = {}
        if not isinstance(wrapper, dict):
            issues.append({"id": row["id"], "issue": "payload_json must be a JSON object"})
            wrapper = {}
        if row["prev_hash"] != previous_hash:
            issues.append({"id": row["id"], "issue": "prev_hash does not match previous event_hash"})
        version = str(row["hash_version"] or EVENT_OUTBOX_HASH_VERSION_V1)
        version_counts[version] = version_counts.get(version, 0) + 1
        for key in ("created_at", "event_type"):
            if wrapper.get(key) != row[key]:
                issues.append({"id": row["id"], "issue": f"SQL {key} differs from payload duplicate"})
        domain_payload = wrapper.get("payload")
        if not isinstance(domain_payload, dict):
            issues.append({"id": row["id"], "issue": "payload wrapper must contain an object payload"})
            domain_payload = {}
        if version == EVENT_OUTBOX_HASH_VERSION_V2:
            if wrapper.get("outbox_event_id") != row["id"]:
                issues.append({"id": row["id"], "issue": "SQL id differs from payload duplicate"})
            if wrapper.get("tenant_id") != row["tenant_id"]:
                issues.append({"id": row["id"], "issue": "SQL tenant_id differs from payload duplicate"})
            expected_hash = _event_outbox_hash_v2(
                prev_hash=str(row["prev_hash"] or ""),
                event_id=int(row["id"]),
                tenant_id=str(row["tenant_id"]),
                event_type=str(row["event_type"]),
                created_at=str(row["created_at"]),
                payload=domain_payload,
            )
        elif version == EVENT_OUTBOX_HASH_VERSION_V1:
            payload_tenant = domain_payload.get("tenant_id")
            if (
                has_tenant_column
                and payload_tenant is not None
                and str(payload_tenant) != str(row["tenant_id"])
            ):
                issues.append({"id": row["id"], "issue": "SQL tenant_id differs from legacy payload tenant"})
            expected_hash = _text_sha256(f"{row['prev_hash']}\n{canonical_json(wrapper)}")
        else:
            issues.append({"id": row["id"], "issue": f"unsupported outbox hash_version: {version}"})
            expected_hash = ""
        if row["event_hash"] != expected_hash:
            issues.append({"id": row["id"], "issue": "event_hash does not match bound event payload"})
        event_log_id = wrapper.get("event_log_id")
        if not isinstance(event_log_id, int):
            issues.append({"id": row["id"], "issue": "event_log_id duplicate is missing or invalid"})
        else:
            event_log = conn.execute(
                "SELECT created_at, event_type, payload_json FROM event_log WHERE id = ?",
                (event_log_id,),
            ).fetchone()
            if event_log is None:
                issues.append({"id": row["id"], "issue": "event_log_id is absent from event_log"})
            else:
                if event_log["created_at"] != row["created_at"] or event_log["event_type"] != row["event_type"]:
                    issues.append({"id": row["id"], "issue": "event_log columns differ from outbox columns"})
                try:
                    event_log_payload = json.loads(event_log["payload_json"] or "{}")
                except json.JSONDecodeError:
                    event_log_payload = None
                if event_log_payload != domain_payload:
                    issues.append({"id": row["id"], "issue": "event_log payload differs from outbox payload"})
        previous_hash = row["event_hash"] or ""
    return {
        "status": "pass" if not issues else "issues",
        "count": len(rows),
        "hash_version_counts": version_counts,
        "issues": issues,
    }


def _event_mirror_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    version = str(row["hash_version"] or EVENT_OUTBOX_HASH_VERSION_V1)
    base = {
        "event_type": row["event_type"],
        "created_at": row["created_at"],
        "payload": payload.get("payload") or {},
        "outbox_event_id": row["id"],
        "outbox_hash": row["event_hash"],
    }
    if version == EVENT_OUTBOX_HASH_VERSION_V1:
        return base
    return {
        "outbox_event_id": row["id"],
        "outbox_hash_version": version,
        "outbox_hash": row["event_hash"],
        "tenant_id": row["tenant_id"],
        "event_type": row["event_type"],
        "created_at": row["created_at"],
        "payload": payload.get("payload") or {},
    }


def validate_event_mirror(conn: sqlite3.Connection, *, events_path: Path) -> dict[str, Any]:
    db_rows, _has_tenant_column, _has_hash_version_column = _event_outbox_rows(
        conn,
        include_prev_hash=False,
    )
    expected = {int(row["id"]): _event_mirror_row(row) for row in db_rows}
    issues: list[dict[str, Any]] = []
    legacy_count = 0
    seen: dict[int, list[tuple[int, str]]] = {}
    if events_path.exists():
        try:
            mirror_rows = _read_jsonl(events_path)
        except AgentControlError as exc:
            mirror_rows = []
            issues.append({"issue": str(exc)})
    else:
        mirror_rows = []
        if expected:
            issues.append({"issue": "events.jsonl mirror is missing"})
    for line_number, row in enumerate(mirror_rows, start=1):
        raw_id = row.get("outbox_event_id")
        if raw_id is None:
            legacy_count += 1
            issues.append({"line": line_number, "issue": "legacy mirror row is non-canonical and requires repair"})
            continue
        try:
            event_id = int(raw_id)
        except (TypeError, ValueError):
            issues.append({"line": line_number, "issue": "outbox_event_id is not an integer"})
            continue
        event_hash = str(row.get("outbox_hash") or "")
        seen.setdefault(event_id, []).append((line_number, event_hash))
        if event_id not in expected:
            issues.append({"line": line_number, "id": event_id, "issue": "mirror id is absent from DB outbox"})
        else:
            expected_row = expected[event_id]
            if event_hash != expected_row["outbox_hash"]:
                issues.append({"line": line_number, "id": event_id, "issue": "mirror hash differs from DB outbox"})
            actual_row = {**row, "outbox_event_id": event_id}
            if canonical_json(actual_row) != canonical_json(expected_row):
                issues.append({"line": line_number, "id": event_id, "issue": "mirror event fields differ from DB outbox"})
    mirror_order = [event_id for event_id, occurrences in seen.items() for _ in occurrences]
    expected_order = list(expected)
    if mirror_order != expected_order:
        issues.append(
            {
                "issue": "mirror rows are not in canonical DB outbox order",
                "expected_order": expected_order,
                "actual_order": mirror_order,
            }
        )
    for event_id in expected:
        occurrences = seen.get(event_id, [])
        if not occurrences:
            issues.append({"id": event_id, "issue": "DB outbox id is missing from mirror"})
        elif len(occurrences) > 1:
            issues.append(
                {
                    "id": event_id,
                    "issue": "mirror contains duplicate outbox id",
                    "occurrences": len(occurrences),
                    "conflicting_hashes": sorted({event_hash for _, event_hash in occurrences}),
                }
            )
    return {
        "status": "pass" if not issues else "issues",
        "db_count": len(expected),
        "active_mirror_count": sum(len(values) for values in seen.values()),
        "legacy_row_count": legacy_count,
        "quarantined_legacy_row_count": legacy_count,
        "events_path": str(events_path),
        "issues": issues,
    }


def repair_event_mirror(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    archive_dir: Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    events_path = _effective_events_path(db_path=db_path, events_path=events_path)
    archive_dir = archive_dir or (events_path.parent / "archive")
    with _control_file_lock(_lock_path_for_db(db_path)):
        with closing(connect(db_path)) as conn:
            outbox = validate_event_outbox(conn)
            current = validate_event_mirror(conn, events_path=events_path)
            if outbox["status"] != "pass":
                raise AgentControlError("event mirror repair refuses an invalid DB outbox chain")
            rows = conn.execute(
                "SELECT id, tenant_id, created_at, event_type, payload_json, event_hash, hash_version "
                "FROM event_outbox ORDER BY id ASC"
            ).fetchall()
            expected_rows = [_event_mirror_row(row) for row in rows]
        if not apply:
            return {
                "status": "pass" if current["status"] == "pass" else "would_repair",
                "applied": False,
                "events_path": str(events_path),
                "expected_count": len(expected_rows),
                "current": current,
                "archive_dir": str(archive_dir),
            }
        archive_path: Path | None = None
        if events_path.exists():
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive_path = archive_dir / (
                f"events-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
                f"{_file_sha256(events_path)[:12]}-{uuid.uuid4().hex[:8]}.jsonl"
            )
            shutil.copy2(events_path, archive_path)
        _ensure_parent(events_path)
        temp_path = events_path.with_name(f".{events_path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_text("".join(canonical_json(row) + "\n" for row in expected_rows), encoding="utf-8")
        os.replace(temp_path, events_path)
        with closing(connect(db_path)) as conn:
            repaired = validate_event_mirror(conn, events_path=events_path)
        if repaired["status"] != "pass":
            if archive_path is not None:
                shutil.copy2(archive_path, events_path)
            raise AgentControlError("event mirror repair verification failed; archived original was restored")
        return {
            "status": "pass",
            "applied": True,
            "events_path": str(events_path),
            "archive_path": str(archive_path) if archive_path is not None else "",
            "expected_count": len(expected_rows),
            "before": current,
            "after": repaired,
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
    events_path = _effective_events_path(db_path=db_path, events_path=events_path)
    with _control_file_lock(_lock_path_for_db(db_path)):
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
                        "tenant_id": tenant_id,
                    },
                    tenant_id=tenant_id,
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
    events_path = _effective_events_path(db_path=db_path, events_path=events_path)
    anchors_path = _effective_anchors_path(db_path=db_path, anchors_path=anchors_path)
    with _control_file_lock(_lock_path_for_db(db_path)):
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


def _copy_required_sidecar(source: Path, target: Path, *, member: str) -> dict[str, Any]:
    _ensure_parent(target)
    if source.exists():
        shutil.copy2(source, target)
    else:
        target.write_text("", encoding="utf-8")
    return {"source": str(source), "member": member, "exists": True, "sha256": _file_sha256(target)}


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
    events_path = _effective_events_path(db_path=db_path, events_path=events_path)
    anchors_path = _effective_anchors_path(db_path=db_path, anchors_path=anchors_path)
    sessions_path = _effective_sessions_path(db_path=db_path, sessions_path=sessions_path)
    backup_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    backup_dir = backup_root / backup_id
    backup_dir.mkdir(parents=True, exist_ok=False)
    with _control_file_lock(_lock_path_for_db(db_path)):
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
            "db": {"source": str(db_path), "member": "agent_control.db", "exists": True, "sha256": _file_sha256(backup_db)},
            "events": _copy_required_sidecar(events_path, backup_dir / "events.jsonl", member="events.jsonl"),
            "anchors": _copy_required_sidecar(anchors_path, backup_dir / "anchors.jsonl", member="anchors.jsonl"),
            "sessions": _copy_required_sidecar(sessions_path, backup_dir / "sessions.jsonl", member="sessions.jsonl"),
        }
    manifest_payload = {
        "backup_id": backup_id,
        "manifest_version": BACKUP_MANIFEST_VERSION,
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
    try:
        anchor_sidecar_rows = _read_jsonl(anchors_path)
    except AgentControlError as exc:
        issues.append(str(exc))
        anchor_sidecar_rows = []
    db_anchor_hashes = [row["anchor_hash"] for row in anchor_rows]
    sidecar_hashes = [
        str(row.get("anchor_hash") or "")
        for row in anchor_sidecar_rows
        if str(row.get("tenant_id") or DEFAULT_TENANT_ID) == tenant_id
    ]
    if sidecar_hashes != db_anchor_hashes:
        issues.append("anchors.jsonl does not match database anchor history")
    if anchor_rows:
        latest_anchor = anchor_rows[-1]
        if latest_anchor["events_jsonl_sha256"]:
            if not events_path.exists():
                issues.append("events.jsonl sidecar is missing")
            elif latest_anchor["events_jsonl_sha256"] != _file_sha256(events_path):
                issues.append("events.jsonl sha256 does not match latest ledger anchor")
    try:
        session_rows = _read_jsonl(sessions_path)
    except AgentControlError as exc:
        issues.append(str(exc))
        session_rows = []
    required_keys = {"session_id", "logged_at", "path", "source_sha256"}
    sidecar_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(session_rows, start=1):
        if not required_keys.issubset(row):
            issues.append(f"sessions.jsonl line {index} missing required session fields")
            continue
        session_id = str(row["session_id"])
        if session_id in sidecar_by_id:
            issues.append(f"sessions.jsonl contains duplicate session_id: {session_id}")
            continue
        row_tenant = str(row.get("tenant_id") or DEFAULT_TENANT_ID)
        if row_tenant == tenant_id:
            sidecar_by_id[session_id] = row
    db_session_rows = conn.execute(
        """
        SELECT id, title, source_ref, metadata_json
        FROM graph_nodes
        WHERE tenant_id = ? AND json_extract(metadata_json, '$.source_type') = 'session_transcript'
        ORDER BY id
        """,
        (tenant_id,),
    ).fetchall()
    db_sessions: dict[str, dict[str, Any]] = {}
    for row in db_session_rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        session_id = str(metadata.get("session_id") or str(row["id"]).removeprefix("session:"))
        if session_id in db_sessions:
            issues.append(f"database contains duplicate session_id metadata: {session_id}")
        db_sessions[session_id] = {
            "path": str(metadata.get("path") or row["source_ref"] or ""),
            "source_sha256": str(metadata.get("source_sha256") or ""),
            "logged_at": str(metadata.get("logged_at") or ""),
        }
    if set(sidecar_by_id) != set(db_sessions):
        issues.append("sessions.jsonl session ids do not match database session nodes")
    for session_id in sorted(set(sidecar_by_id) & set(db_sessions)):
        sidecar = sidecar_by_id[session_id]
        expected = db_sessions[session_id]
        for key in ("path", "source_sha256", "logged_at"):
            if str(sidecar.get(key) or "") != expected[key]:
                issues.append(f"sessions.jsonl {session_id} {key} does not match database session node")
    session_outbox_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'session_sidecar_outbox'"
    ).fetchone()
    outbox_rows = (
        conn.execute(
            "SELECT session_id, payload_json, payload_sha256, delivered_at "
            "FROM session_sidecar_outbox WHERE tenant_id = ? ORDER BY session_id",
            (tenant_id,),
        ).fetchall()
        if session_outbox_exists is not None
        else []
    )
    for row in outbox_rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            issues.append(f"session sidecar outbox payload is invalid JSON: {row['session_id']}")
            continue
        if _text_sha256(canonical_json(payload)) != row["payload_sha256"]:
            issues.append(f"session sidecar outbox payload hash mismatch: {row['session_id']}")
        if payload.get("session_id") != row["session_id"]:
            issues.append(f"session sidecar outbox payload session id mismatch: {row['session_id']}")
        if row["session_id"] not in sidecar_by_id or row["delivered_at"] is None:
            issues.append(f"session sidecar outbox is not durably delivered: {row['session_id']}")
    return issues


def restore_check_memory_backup(
    *,
    backup_dir: Path,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
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
    if not isinstance(manifest, dict):
        return {
            "status": "fail",
            "backup_dir": str(backup_dir),
            "issues": ["manifest.json must be a JSON object"],
            "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        }
    expected_manifest_hash = manifest.get("manifest_sha256")
    manifest_without_hash = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    actual_manifest_hash = _text_sha256(canonical_json(manifest_without_hash))
    if expected_manifest_hash != actual_manifest_hash:
        issues.append("manifest_sha256 mismatch")
    manifest_tenant = manifest.get("tenant_id")
    if manifest_tenant != tenant_id:
        issues.append(f"manifest tenant_id must exactly match requested tenant: {tenant_id}")
    files = manifest.get("files") or {}
    if not isinstance(files, dict):
        issues.append("manifest files must be a JSON object")
        files = {}
    manifest_version = str(manifest.get("manifest_version") or "legacy_absolute_paths_v1")
    if manifest_version not in {BACKUP_MANIFEST_VERSION, "legacy_absolute_paths_v1"}:
        issues.append(f"unsupported backup manifest_version: {manifest_version}")
    expected_members = {
        "db": "agent_control.db",
        "events": "events.jsonl",
        "anchors": "anchors.jsonl",
        "sessions": "sessions.jsonl",
    }
    resolved_files: dict[str, Path] = {}
    validated_labels: set[str] = set()
    for label, expected_member in expected_members.items():
        info = files.get(label)
        if not isinstance(info, dict):
            issues.append(f"{label} backup member is not declared")
            continue
        if info.get("exists") is not True:
            issues.append(f"{label} backup member must be declared present")
            continue
        if manifest_version == BACKUP_MANIFEST_VERSION:
            raw_member = str(info.get("member") or "")
            member_path = Path(raw_member)
            if not raw_member or member_path.is_absolute() or ".." in member_path.parts:
                issues.append(f"{label} backup member must be a relative in-bundle path")
                continue
            if raw_member.replace("\\", "/") != expected_member:
                issues.append(f"{label} backup member must be exactly {expected_member}")
                continue
            path = (backup_dir / member_path).resolve()
            if path != backup_dir and backup_dir not in path.parents:
                issues.append(f"{label} backup member escapes the supplied bundle")
                continue
        else:
            legacy_path = Path(str(info.get("path") or expected_member))
            if legacy_path.name != expected_member:
                issues.append(f"{label} legacy backup member has an unexpected filename")
                continue
            path = (backup_dir / expected_member).resolve()
        resolved_files[label] = path
        if not path.exists():
            issues.append(f"{label} backup file is missing")
            continue
        if info.get("sha256") != _file_sha256(path):
            issues.append(f"{label} sha256 mismatch")
            continue
        validated_labels.add(label)
    required_labels = set(expected_members)
    if validated_labels != required_labels or expected_manifest_hash != actual_manifest_hash or manifest_tenant != tenant_id:
        return {
            "status": "fail",
            "backup_dir": str(backup_dir),
            "issues": issues,
            "manifest_sha256": actual_manifest_hash,
            "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        }
    backup_db = resolved_files["db"]
    backup_events = resolved_files["events"]
    backup_anchors = resolved_files["anchors"]
    backup_sessions = resolved_files["sessions"]
    with closing(sqlite3.connect(backup_db)) as conn:
        conn.row_factory = sqlite3.Row
        conn.create_function("agent_control_maintenance", 0, lambda: 0)
        ledger = validate_agent_run_ledger(conn, tenant_id=tenant_id)
        outbox = validate_event_outbox(conn)
        mirror = validate_event_mirror(conn, events_path=backup_events)
        anchors = validate_agent_run_ledger_anchors(conn, events_path=backup_events, tenant_id=tenant_id)
        sidecar_issues = _validate_backup_jsonl_sidecars(
            conn,
            events_path=backup_events,
            anchors_path=backup_anchors,
            sessions_path=backup_sessions,
            tenant_id=tenant_id,
        )
        expected_schema_version = str(manifest.get("schema_version") or CONTROL_SCHEMA_VERSION)
        migration = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            (expected_schema_version,),
        ).fetchone()
        schema_shape_current = (
            _schema_is_current(conn)
            if expected_schema_version == CONTROL_SCHEMA_VERSION
            else migration is not None
        )
    if ledger["status"] != "pass":
        issues.append("agent run ledger audit failed")
    if outbox["status"] != "pass":
        issues.append("event outbox audit failed")
    if mirror["status"] != "pass":
        issues.append("events.jsonl mirror audit failed")
    if anchors["status"] != "pass":
        issues.append("agent run ledger anchor audit failed")
    issues.extend(sidecar_issues)
    if migration is None:
        issues.append(f"schema migration missing: {expected_schema_version}")
    elif not schema_shape_current:
        issues.append(f"schema structure is incomplete for: {expected_schema_version}")
    return {
        "status": "pass" if not issues else "fail",
        "backup_dir": str(backup_dir),
        "issues": issues,
        "manifest_sha256": actual_manifest_hash,
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
        "ledger": ledger,
        "event_outbox": outbox,
        "event_mirror": mirror,
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
        lines.append(f"- {label}: exists={info.get('exists')} sha256={info.get('sha256')} member={info.get('member')}")
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
    events_path = _effective_events_path(db_path=db_path, events_path=events_path)
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
    freshness_refresh = refresh_retrieval_freshness(
        db_path=db_path,
        repo_root=repo_root,
        tenant_id=tenant_id,
    )
    audit = memory_audit(db_path=db_path, tenant_id=tenant_id)
    dashboard = operator_dashboard(db_path=db_path, runs_dir=runs_dir, tenant_id=tenant_id)
    eval_result = agent_eval_harness(db_path=db_path, events_path=events_path, repo_root=repo_root, tenant_id=tenant_id, seed=False)
    freshness = retrieval_freshness_report(db_path=db_path, tenant_id=tenant_id)
    with closing(connect(db_path)) as conn:
        outbox = validate_event_outbox(conn)
        mirror = validate_event_mirror(conn, events_path=events_path)
    checks = [
        {"name": "agent run ledger audit", "pass": ledger.get("status") == "pass", "detail": ledger.get("status")},
        {
            "name": "agent run ledger anchor current",
            "pass": anchor_report.get("status") == "pass",
            "detail": f"{anchor_report.get('status')} / {(anchor_report.get('anchor_validation') or {}).get('freshness')}",
        },
        {"name": "event outbox audit", "pass": outbox.get("status") == "pass", "detail": outbox.get("status")},
        {"name": "events.jsonl mirror", "pass": mirror.get("status") == "pass", "detail": mirror.get("status")},
        {"name": "memory audit", "pass": audit.get("status") == "pass", "detail": audit.get("status")},
        {
            "name": "retrieval freshness",
            "pass": freshness.get("status") == "pass",
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
        "event_mirror": mirror,
        "memory_audit": audit,
        "retrieval_freshness": freshness,
        "retrieval_freshness_refresh": freshness_refresh,
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
            events_path=events_path,
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


def _upsert_retrieval_source_expectation(conn: sqlite3.Connection, node: dict[str, Any]) -> None:
    metadata = node.get("metadata") or {}
    source_type = str(metadata.get("source_type") or "")
    conn.execute("DELETE FROM retrieval_source_expectations WHERE node_id = ?", (str(node["id"]),))
    if source_type not in REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES or source_type == LIVING_HISTORY_SOURCE_TYPE:
        return
    now = utc_now()
    conn.execute(
        """
        INSERT INTO retrieval_source_expectations(
            tenant_id, node_id, source_type, source_path, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, node_id) DO UPDATE SET
            source_type = excluded.source_type,
            source_path = excluded.source_path,
            updated_at = excluded.updated_at
        """,
        (
            str(node.get("tenant_id") or DEFAULT_TENANT_ID),
            str(node["id"]),
            source_type,
            _retrieval_file_path(metadata, node.get("source_ref")),
            now,
            now,
        ),
    )


def _missing_required_retrieval_expectations(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.node_id, e.source_type, e.source_path, n.metadata_json AS graph_metadata_json,
               d.source_type AS retrieval_source_type, d.freshness_status,
               CASE WHEN n.id IS NULL THEN 1 ELSE 0 END AS graph_node_missing,
               CASE WHEN d.doc_id IS NULL THEN 1 ELSE 0 END AS retrieval_document_missing
        FROM retrieval_source_expectations e
        LEFT JOIN graph_nodes n ON n.id = e.node_id AND n.tenant_id = e.tenant_id
        LEFT JOIN retrieval_documents d ON d.source_node_id = e.node_id
        WHERE e.tenant_id = ?
          AND e.source_type <> ?
        ORDER BY e.source_type, e.node_id
        """,
        (tenant_id, LIVING_HISTORY_SOURCE_TYPE),
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        reasons: list[str] = []
        if item["graph_node_missing"]:
            reasons.append("graph_node_missing")
        if item["retrieval_document_missing"]:
            reasons.append("retrieval_document_missing")
        graph_source_type = ""
        if not item["graph_node_missing"]:
            try:
                graph_metadata = json.loads(item.get("graph_metadata_json") or "{}")
            except json.JSONDecodeError:
                graph_metadata = {}
            if isinstance(graph_metadata, dict):
                graph_source_type = str(graph_metadata.get("source_type") or "")
            if graph_source_type != item["source_type"]:
                reasons.append("graph_source_type_reclassified")
        if not item["retrieval_document_missing"]:
            if str(item.get("retrieval_source_type") or "") != item["source_type"]:
                reasons.append("retrieval_source_type_reclassified")
            if str(item.get("freshness_status") or "") != "current":
                reasons.append(f"freshness_{item.get('freshness_status') or 'unknown'}")
        if reasons:
            item["issue"] = ",".join(reasons)
            issues.append(item)
    return issues


def _latest_project_memory_seed_contract(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT payload_json
        FROM event_outbox
        WHERE tenant_id = ? AND event_type = 'seed.project_memory.completed'
        ORDER BY id DESC
        """,
        (tenant_id,),
    ).fetchall()
    for row in rows:
        try:
            stored = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(stored, dict):
            continue
        payload = stored.get("payload", stored)
        if not isinstance(payload, dict):
            continue
        if str(payload.get("tenant_id") or tenant_id) != tenant_id:
            continue
        if not str(payload.get("repo_root") or "").strip():
            continue
        return payload
    return None


def _canonical_required_retrieval_specs(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    seed_contract = _latest_project_memory_seed_contract(conn, tenant_id=tenant_id)
    if seed_contract is None:
        return []
    repo_root = str(seed_contract["repo_root"])
    return [
        {
            "tenant_id": tenant_id,
            "repo_root": repo_root,
            "node_id": _path_node_id(str(spec["path"])),
            "source_type": str(spec["source_type"]),
            "source_path": _safe_node_path(str(spec["path"])),
        }
        for spec in PROJECT_SEED_FILES
        if str(spec["source_type"]) in REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES
    ]


def _canonical_required_retrieval_issues(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for spec in _canonical_required_retrieval_specs(conn, tenant_id=tenant_id):
        row = conn.execute(
            """
            SELECT n.id, n.metadata_json, n.source_ref, d.doc_id,
                   d.source_type AS retrieval_source_type, d.freshness_status
            FROM (SELECT 1) marker
            LEFT JOIN graph_nodes n ON n.id = ? AND n.tenant_id = ?
            LEFT JOIN retrieval_documents d ON d.source_node_id = n.id
            """,
            (spec["node_id"], tenant_id),
        ).fetchone()
        reasons: list[str] = []
        graph_node_missing = row is None or row["id"] is None
        retrieval_document_missing = graph_node_missing or row["doc_id"] is None
        if graph_node_missing:
            reasons.append("canonical_graph_node_missing")
        else:
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            if str(metadata.get("source_type") or "") != spec["source_type"]:
                reasons.append("canonical_source_type_reclassified")
            if _safe_node_path(_retrieval_file_path(metadata, row["source_ref"])) != spec["source_path"]:
                reasons.append("canonical_source_path_changed")
        if retrieval_document_missing:
            reasons.append("canonical_retrieval_document_missing")
        else:
            if str(row["retrieval_source_type"] or "") != spec["source_type"]:
                reasons.append("canonical_retrieval_source_type_reclassified")
            if str(row["freshness_status"] or "") != "current":
                reasons.append(f"freshness_{row['freshness_status'] or 'unknown'}")
        if reasons:
            issues.append(
                {
                    **spec,
                    "graph_node_missing": graph_node_missing,
                    "retrieval_document_missing": retrieval_document_missing,
                    "freshness_status": None if retrieval_document_missing else str(row["freshness_status"]),
                    "issue": ",".join(reasons),
                    "canonical_contract": True,
                }
            )
    return issues


def _present_required_retrieval_issues(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT n.id AS node_id, n.metadata_json, n.source_ref, d.doc_id,
               d.source_type AS retrieval_source_type, d.freshness_status
        FROM graph_nodes n
        LEFT JOIN retrieval_documents d ON d.source_node_id = n.id
        WHERE n.tenant_id = ?
        ORDER BY n.id
        """,
        (tenant_id,),
    ).fetchall()
    issues: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, dict):
            continue
        source_type = str(metadata.get("source_type") or "")
        if source_type not in REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES or source_type == LIVING_HISTORY_SOURCE_TYPE:
            continue
        reasons: list[str] = []
        retrieval_document_missing = row["doc_id"] is None
        if retrieval_document_missing:
            reasons.append("retrieval_document_missing")
        else:
            if str(row["retrieval_source_type"] or "") != source_type:
                reasons.append("retrieval_source_type_reclassified")
            if str(row["freshness_status"] or "") != "current":
                reasons.append(f"freshness_{row['freshness_status'] or 'unknown'}")
        if reasons:
            issues.append(
                {
                    "tenant_id": tenant_id,
                    "node_id": str(row["node_id"]),
                    "source_type": source_type,
                    "source_path": _retrieval_file_path(metadata, row["source_ref"]),
                    "graph_node_missing": False,
                    "retrieval_document_missing": retrieval_document_missing,
                    "freshness_status": None if retrieval_document_missing else str(row["freshness_status"]),
                    "issue": ",".join(reasons),
                }
            )
    return issues


def _living_history_required_retrieval_issues(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    rows_by_source = {_safe_node_path(path): [] for path in LIVING_HISTORY_REQUIRED_SOURCE_PATHS}
    allowed_paths = set(rows_by_source)
    expected_paths: set[str] = set()
    activation_rows = conn.execute(
        """
        SELECT payload_json
        FROM event_outbox
        WHERE tenant_id = ? AND event_type = ?
        ORDER BY id
        """,
        (tenant_id, LIVING_HISTORY_ACTIVATION_EVENT_TYPE),
    ).fetchall()
    for activation_row in activation_rows:
        try:
            wrapper = json.loads(activation_row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        payload = wrapper.get("payload", wrapper) if isinstance(wrapper, dict) else {}
        activated = payload.get("activated_source_paths") if isinstance(payload, dict) else []
        if not isinstance(activated, list):
            continue
        expected_paths.update(
            path
            for raw_path in activated
            if (path := _safe_node_path(str(raw_path or ""))) in allowed_paths
        )
    expectation_rows = conn.execute(
        """
        SELECT node_id, source_path
        FROM retrieval_source_expectations
        WHERE tenant_id = ? AND source_type = ?
        """,
        (tenant_id, LIVING_HISTORY_SOURCE_TYPE),
    ).fetchall()
    for expectation_row in expectation_rows:
        node_id = str(expectation_row["node_id"] or "")
        raw_path = (
            node_id.removeprefix(LIVING_HISTORY_EXPECTATION_PREFIX)
            if node_id.startswith(LIVING_HISTORY_EXPECTATION_PREFIX)
            else str(expectation_row["source_path"] or "")
        )
        source_path = _safe_node_path(raw_path)
        if source_path in allowed_paths:
            expected_paths.add(source_path)
    rows = conn.execute(
        """
        SELECT n.id, n.metadata_json, n.source_ref, d.doc_id,
               d.source_type AS retrieval_source_type, d.freshness_status
        FROM graph_nodes n
        LEFT JOIN retrieval_documents d ON d.source_node_id = n.id
        WHERE n.tenant_id = ?
          AND json_extract(n.metadata_json, '$.source_type') = ?
        ORDER BY n.id
        """,
        (tenant_id, LIVING_HISTORY_SOURCE_TYPE),
    ).fetchall()
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(metadata, dict):
            continue
        source_path = _safe_node_path(_retrieval_file_path(metadata, row["source_ref"]))
        if source_path in rows_by_source:
            rows_by_source[source_path].append(row)
            expected_paths.add(source_path)

    issues: list[dict[str, Any]] = []
    for source_path in sorted(expected_paths):
        source_rows = rows_by_source[source_path]
        current_rows = [
            row
            for row in source_rows
            if row["doc_id"] is not None
            and str(row["retrieval_source_type"] or "") == LIVING_HISTORY_SOURCE_TYPE
            and str(row["freshness_status"] or "") == "current"
        ]
        if current_rows:
            continue
        graph_node_missing = not source_rows
        retrieval_document_missing = not any(row["doc_id"] is not None for row in source_rows)
        reasons: list[str] = []
        if graph_node_missing:
            reasons.append("living_history_source_missing")
        elif retrieval_document_missing:
            reasons.append("retrieval_document_missing")
        else:
            reasons.append("living_history_source_not_current")
        issues.append(
            {
                "tenant_id": tenant_id,
                "node_id": f"{LIVING_HISTORY_EXPECTATION_PREFIX}{source_path}",
                "source_type": LIVING_HISTORY_SOURCE_TYPE,
                "source_path": source_path,
                "graph_node_missing": graph_node_missing,
                "retrieval_document_missing": retrieval_document_missing,
                "freshness_status": None if retrieval_document_missing else "not_current",
                "issue": ",".join(reasons),
                "class_contract": True,
                "current_node_count": 0,
            }
        )
    return issues


def _required_retrieval_freshness_issues(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    sources = [
        *_missing_required_retrieval_expectations(conn, tenant_id=tenant_id),
        *_canonical_required_retrieval_issues(conn, tenant_id=tenant_id),
        *_present_required_retrieval_issues(conn, tenant_id=tenant_id),
        *_living_history_required_retrieval_issues(conn, tenant_id=tenant_id),
    ]
    for source in sources:
        node_id = str(source["node_id"])
        reason_set = {reason for reason in str(source.get("issue") or "").split(",") if reason}
        if node_id not in merged:
            merged[node_id] = {
                **source,
                "graph_node_missing": bool(source.get("graph_node_missing")),
                "retrieval_document_missing": bool(source.get("retrieval_document_missing")),
                "issue_reasons": sorted(reason_set),
            }
            continue
        current = merged[node_id]
        current["graph_node_missing"] = bool(current.get("graph_node_missing")) or bool(
            source.get("graph_node_missing")
        )
        current["retrieval_document_missing"] = bool(current.get("retrieval_document_missing")) or bool(
            source.get("retrieval_document_missing")
        )
        current["canonical_contract"] = bool(current.get("canonical_contract")) or bool(
            source.get("canonical_contract")
        )
        current["issue_reasons"] = sorted(set(current.get("issue_reasons") or []) | reason_set)
        if source.get("repo_root"):
            current["repo_root"] = source["repo_root"]
        if source.get("freshness_status") not in (None, "current"):
            current["freshness_status"] = source["freshness_status"]
    for item in merged.values():
        item["issue"] = ",".join(item.pop("issue_reasons", []))
    return sorted(merged.values(), key=lambda item: (str(item.get("source_type") or ""), item["node_id"]))


def _retrieval_file_path(metadata: dict[str, Any], source_ref: str | None) -> str:
    return str(metadata.get("source_path") or metadata.get("path") or source_ref or "").replace("\\", "/").strip()


def _resolve_gateboard_source_artifact_hash_path(repo_root: Path, source_path: str) -> Path | None:
    try:
        resolved = _resolve_inside_repo(repo_root, Path(source_path))
        relative_path = _safe_node_path(_relative_to_repo(repo_root, resolved))
    except (AgentControlError, OSError, RuntimeError):
        return None
    path = Path(relative_path)
    if path.name.lower() in GATEBOARD_SOURCE_ARTIFACT_DENIED_NAMES:
        return None
    if path.suffix.lower() not in GATEBOARD_SOURCE_ARTIFACT_HASH_SUFFIXES:
        return None
    if not any(relative_path == root or relative_path.startswith(f"{root}/") for root in GATEBOARD_SOURCE_ARTIFACT_HASH_ROOTS):
        return None
    return resolved


def _gateboard_source_artifact_hash(repo_root: Path, source_path: str) -> str | None:
    path = _resolve_gateboard_source_artifact_hash_path(repo_root, source_path)
    if path is None or not path.is_file():
        return None
    try:
        return _file_sha256(path)
    except (MemoryError, OSError):
        return None


def _resolve_retrieval_freshness_path(
    *,
    repo_root: Path,
    source_type: str,
    source_path: str,
) -> Path | None:
    if source_type == "gateboard_source_artifact":
        return _resolve_gateboard_source_artifact_hash_path(repo_root, source_path)
    try:
        resolved = _resolve_inside_repo(repo_root, Path(source_path))
        relative_path = _relative_to_repo(repo_root, resolved)
        try:
            _assert_memory_safe_source_path(relative_path)
        except AgentControlError:
            allowed_gateboard_path = "data/forward-tracking/project_operator_gateboard_latest.json"
            if not (
                source_type.startswith("gateboard_")
                and _safe_node_path(relative_path) == allowed_gateboard_path
            ):
                raise
        return resolved
    except (AgentControlError, OSError, RuntimeError):
        return None


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
    if source_type == LIVING_HISTORY_SOURCE_TYPE:
        physical_paths = metadata.get("source_physical_paths")
        candidates = physical_paths if isinstance(physical_paths, list) and physical_paths else [source_path]
        found = False
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            path = _resolve_retrieval_freshness_path(
                repo_root=repo_root,
                source_type=source_type,
                source_path=candidate,
            )
            if path is None:
                continue
            if not path.is_file():
                continue
            found = True
            try:
                body = path.read_text(encoding="utf-8")
            except (MemoryError, OSError):
                continue
            except UnicodeDecodeError:
                try:
                    body = path.read_text(encoding="utf-8", errors="replace")
                except (MemoryError, OSError):
                    continue
            if _normalized_history_text(node_body) in _normalized_history_text(body):
                return "current"
        return "stale" if found else "missing"
    if source_type == "gateboard_source_artifact":
        path = _resolve_gateboard_source_artifact_hash_path(repo_root, source_path)
        if path is None or not path.is_file():
            return "missing"
        expected_hash = str(metadata.get("source_content_sha256") or "")
        if re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None:
            return "stale"
        try:
            actual_hash = _file_sha256(path)
        except (MemoryError, OSError):
            return "stale"
        return "current" if actual_hash == expected_hash else "stale"
    path = _resolve_retrieval_freshness_path(
        repo_root=repo_root,
        source_type=source_type,
        source_path=source_path,
    )
    if path is None or not path.exists() or not path.is_file():
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
    expected_source_hash = metadata.get("source_content_sha256")
    if expected_source_hash is not None:
        return "current" if str(expected_source_hash) == _text_sha256(body) else "stale"
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
        "missing_required_count": 0,
        "missing_required_source_types": [],
        "missing_required_sources": [],
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
        required_issues = _required_retrieval_freshness_issues(conn, tenant_id=tenant_id)
        result["missing_required_sources"] = required_issues
        result["missing_required_count"] = len(required_issues)
        result["missing_required_source_types"] = sorted({row["source_type"] for row in required_issues})
        if required_issues:
            result["status"] = "issues"
    return result


def retrieval_freshness_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    with closing(connect(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT source_type, freshness_status, count(*) AS count
            FROM retrieval_documents d
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE n.tenant_id = ?
            GROUP BY source_type, freshness_status
            """,
            (tenant_id,),
        ).fetchall()
        required_freshness_issues = _required_retrieval_freshness_issues(conn, tenant_id=tenant_id)
    counts: dict[str, int] = {}
    required_issues = 0
    tier3_repo_gaps = 0
    for row in rows:
        source_type = str(row["source_type"])
        freshness_status = str(row["freshness_status"])
        count = int(row["count"])
        counts[freshness_status] = counts.get(freshness_status, 0) + count
        if source_type == "repo_file_index" and freshness_status in {"missing", "stale"}:
            tier3_repo_gaps += count
    stale = int(counts.get("stale", 0))
    missing = int(counts.get("missing", 0))
    required_issues = len(required_freshness_issues)
    return {
        "status": "pass" if required_issues == 0 else "issues",
        "counts": counts,
        "stale": stale,
        "missing": missing,
        "required_issue_count": required_issues,
        "missing_required_source_types": sorted({row["source_type"] for row in required_freshness_issues}),
        "missing_required_sources": required_freshness_issues,
        "tier3_repo_gap_count": tier3_repo_gaps,
        "detail": (
            f"stale={stale} missing={missing} required_issues={required_issues} "
            f"tier3_repo_gaps_nonfatal={tier3_repo_gaps}"
        ),
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
    fresh_only: bool = False,
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
    if fresh_only:
        scope_clauses.append("d.freshness_status = 'current'")
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
    _upsert_retrieval_source_expectation(conn, node)
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
    edge_metadata = dict(metadata or {})
    _assert_memory_policy_valid(
        title=relation,
        body="",
        metadata=edge_metadata,
        field_name="graph edge metadata",
    )
    source_node = _graph_node_row(conn, source_node_id)
    target_node = _graph_node_row(conn, target_node_id)
    if source_node["tenant_id"] != target_node["tenant_id"]:
        raise AgentControlError(
            f"graph edge cannot cross tenants: {source_node_id} ({source_node['tenant_id']}) -> "
            f"{target_node_id} ({target_node['tenant_id']})"
        )
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
        (edge_id, source_node_id, relation, target_node_id, canonical_json(edge_metadata), source_ref, utc_now()),
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
        heading = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})(?:\s+\([^)]*\))?\s*$", raw_line)
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


def _living_history_corpus_sources(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    logical_paths = {"docs/WORKLOG.md", "docs/DECISIONS.md"}
    sources: dict[str, list[dict[str, Any]]] = {path: [] for path in logical_paths}
    resolved_root = repo_root.resolve()
    archive_root = (resolved_root / PROJECT_MEMORY_ARCHIVE_RELATIVE_ROOT).resolve()
    try:
        archive_root.relative_to(resolved_root)
    except ValueError as exc:
        raise AgentControlError("project-memory archive root escapes repository root") from exc
    if archive_root.exists():
        for manifest_path in sorted(archive_root.glob("*/manifest.json")):
            verification = _verify_project_memory_archive_manifest(root=resolved_root, manifest_path=manifest_path)
            if verification["status"] != "pass":
                raise AgentControlError(
                    f"invalid project-memory archive manifest {manifest_path}: {', '.join(verification['issues'])}"
                )
            manifest = verification["manifest"]
            capture_date = str(manifest["capture_date"])
            for item in manifest["files"]:
                logical_path = str(item["logical_path"])
                if logical_path not in logical_paths or item["living_history_ingest"] is not True:
                    continue
                physical = (resolved_root / str(item["archive_path"])).resolve()
                sources[logical_path].append(
                    {
                        "logical_path": logical_path,
                        "physical_path": physical.relative_to(resolved_root).as_posix(),
                        "source_kind": "archive",
                        "capture_date": capture_date,
                    }
                )
    for logical_path in sorted(logical_paths):
        live = (resolved_root / logical_path).resolve()
        try:
            live.relative_to(resolved_root)
        except ValueError as exc:
            raise AgentControlError(f"living-history source escapes repository root: {logical_path}") from exc
        if live.is_file():
            sources[logical_path].append(
                {
                    "logical_path": logical_path,
                    "physical_path": logical_path,
                    "source_kind": "live",
                    "capture_date": None,
                }
            )
    return sources


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
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    max_edges_per_entry: int = 12,
) -> dict[str, Any]:
    sources = [
        ("docs/WORKLOG.md", _parse_worklog_entries, "WORKLOG"),
        ("docs/DECISIONS.md", _parse_decision_entries, "DECISION"),
    ]
    corpus_sources = _living_history_corpus_sources(repo_root)
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
    activated_source_paths: set[str] = set()
    with closing(connect(db_path, maintenance=True)) as conn, conn:
        existing_activation_paths: set[str] = set()
        activation_rows = conn.execute(
            "SELECT payload_json FROM event_outbox WHERE tenant_id = ? AND event_type = ?",
            (tenant_id, LIVING_HISTORY_ACTIVATION_EVENT_TYPE),
        ).fetchall()
        for activation_row in activation_rows:
            try:
                wrapper = json.loads(activation_row["payload_json"] or "{}")
            except json.JSONDecodeError:
                continue
            payload = wrapper.get("payload", wrapper) if isinstance(wrapper, dict) else {}
            paths = payload.get("activated_source_paths") if isinstance(payload, dict) else []
            if isinstance(paths, list):
                existing_activation_paths.update(_safe_node_path(str(path or "")) for path in paths)
        conn.execute(
            """
            DELETE FROM retrieval_source_expectations
            WHERE tenant_id = ? AND source_type = ? AND node_id NOT LIKE ?
            """,
            (tenant_id, LIVING_HISTORY_SOURCE_TYPE, f"{LIVING_HISTORY_EXPECTATION_PREFIX}%"),
        )
        for relative_path, parser, title_prefix in sources:
            physical_sources = corpus_sources.get(relative_path) or []
            if not physical_sources:
                result["warnings"].append(f"missing_source:{relative_path}")
                result["sources"].append({"path": relative_path, "entries": 0, "status": "missing"})
                continue
            current_node_ids: set[str] = set()
            entries_by_node_id: dict[str, dict[str, str]] = {}
            locations_by_node_id: dict[str, list[dict[str, Any]]] = {}
            for source in physical_sources:
                physical_path = str(source["physical_path"])
                path = repo_root / physical_path
                text = path.read_text(encoding="utf-8")
                entries, warnings = parser(text)
                for warning in warnings:
                    if warning not in result["warnings"]:
                        result["warnings"].append(warning)
                result["sources"].append(
                    {
                        "path": physical_path,
                        "logical_path": relative_path,
                        "source_kind": source["source_kind"],
                        "capture_date": source.get("capture_date"),
                        "entries": len(entries),
                        "status": "parsed",
                    }
                )
                for entry in entries:
                    node_id = _history_node_id(
                        entry["kind"],
                        relative_path,
                        entry["source_heading"],
                        entry["body"],
                        tenant_id=tenant_id,
                    )
                    current_node_ids.add(node_id)
                    entries_by_node_id[node_id] = entry
                    locations_by_node_id.setdefault(node_id, []).append(source)
            if current_node_ids:
                activated_source_paths.add(_safe_node_path(relative_path))
                now = utc_now()
                conn.execute(
                    """
                    INSERT INTO retrieval_source_expectations(
                        tenant_id, node_id, source_type, source_path, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, node_id) DO UPDATE SET
                        source_path = excluded.source_path,
                        updated_at = excluded.updated_at
                    """,
                    (
                        tenant_id,
                        f"{LIVING_HISTORY_EXPECTATION_PREFIX}{_safe_node_path(relative_path)}",
                        LIVING_HISTORY_SOURCE_TYPE,
                        relative_path,
                        now,
                        now,
                    ),
                )
            for node_id, entry in entries_by_node_id.items():
                kind = entry["kind"]
                body = entry["body"]
                stable_heading = entry["source_heading"]
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
                locations = locations_by_node_id[node_id]
                physical_paths = list(dict.fromkeys(str(item["physical_path"]) for item in locations))
                archive_dates = list(
                    dict.fromkeys(
                        str(item["capture_date"])
                        for item in locations
                        if item.get("source_kind") == "archive" and item.get("capture_date")
                    )
                )
                metadata = _with_memory_policy_metadata(
                    {
                        "source_type": LIVING_HISTORY_SOURCE_TYPE,
                        "source_path": relative_path,
                        "source_physical_path": physical_paths[-1],
                        "source_physical_paths": physical_paths,
                        "archive_capture_dates": archive_dates,
                        "archived_source_present": bool(archive_dates),
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
                if existing and canonical_json(existing_metadata) == canonical_json(metadata):
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
        if activated_source_paths - existing_activation_paths:
            _record_event(
                conn,
                events_path=events_path,
                event_type=LIVING_HISTORY_ACTIVATION_EVENT_TYPE,
                tenant_id=tenant_id,
                payload={
                    "tenant_id": tenant_id,
                    "ingest_version": LIVING_HISTORY_INGEST_VERSION,
                    "activated_source_paths": sorted(existing_activation_paths | activated_source_paths),
                },
            )
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
    updated = _graph_node_row(conn, node_id)
    _upsert_retrieval_document(conn, updated)
    return updated


def _close_task_activity(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    status: str,
    now: str,
) -> None:
    run_rows = conn.execute(
        "SELECT graph_node_id FROM worker_runs WHERE task_id = ? AND finished_at IS NULL",
        (task_id,),
    ).fetchall()
    conn.execute(
        "UPDATE task_claims SET status = ? WHERE task_id = ? AND status = 'active'",
        (status, task_id),
    )
    conn.execute(
        "UPDATE worker_runs SET status = ?, finished_at = ? WHERE task_id = ? AND finished_at IS NULL",
        (status, now, task_id),
    )
    for row in run_rows:
        node_id = row["graph_node_id"]
        if node_id and conn.execute("SELECT 1 FROM graph_nodes WHERE id = ?", (node_id,)).fetchone():
            _update_graph_node_metadata(conn, str(node_id), {"status": status, "finished_at": now})


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
    _assert_metadata_tenant_allowed(metadata, tenant_id=tenant_id)
    with _locked_db_transaction(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tasks(
                id, tenant_id, created_at, updated_at, title, description, pathway, status,
                permission_mode, owner, priority, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                task_id,
                tenant_id,
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
                "tenant_id": tenant_id,
            },
            source_ref=f"task:{task_id}",
        )
        _record_event(
            conn,
            events_path=events_path,
            event_type="task.created",
            payload={"task_id": task_id, "graph_node_id": node["id"], "pathway": pathway, "tenant_id": tenant_id},
            tenant_id=tenant_id,
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
    with _locked_db_transaction(db_path) as conn:
        task = _task_row(conn, task_id)
        if task["status"] not in {"open", "reported"}:
            raise AgentControlError(f"Task {task_id} cannot be claimed from status {task['status']}")
        if conn.execute(
            "SELECT 1 FROM task_claims WHERE task_id = ? AND status = 'active'",
            (task_id,),
        ).fetchone():
            raise AgentControlError(f"Task {task_id} already has an active claim")
        claim_metadata = metadata or {}
        _assert_metadata_tenant_allowed(claim_metadata, tenant_id=task["tenant_id"])
        now = utc_now()
        conn.execute(
            """
            INSERT INTO task_claims(task_id, worker_id, tenant_id, claimed_at, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, worker_id, task["tenant_id"], now, "active", canonical_json(claim_metadata)),
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
            tenant_id=task["tenant_id"],
            sub_tenant_id=task["pathway"],
            metadata={"task_id": task_id, "worker_id": worker_id, "status": "claimed"},
            source_ref=f"task:{task_id}",
        )
        conn.execute(
            """
            INSERT INTO worker_runs(task_id, graph_node_id, tenant_id, worker_id, status, started_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, run_node["id"], task["tenant_id"], worker_id, "claimed", now, canonical_json(claim_metadata)),
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
            payload={
                "task_id": task_id,
                "worker_id": worker_id,
                "worker_run_node_id": run_node["id"],
                "tenant_id": task["tenant_id"],
            },
            tenant_id=task["tenant_id"],
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
    proof_gate_status = _validate_choice(proof_gate_status, PROOF_GATE_STATUSES, "proof_gate_status")
    with _locked_db_transaction(db_path) as conn:
        task = _task_row(conn, task_id)
        if task["status"] != "claimed" or task.get("owner") != worker_id:
            raise AgentControlError(
                f"Task {task_id} report requires the active claim owner; "
                f"status={task['status']} owner={task.get('owner')!r}"
            )
        if conn.execute(
            "SELECT 1 FROM task_claims WHERE task_id = ? AND worker_id = ? AND status = 'active'",
            (task_id, worker_id),
        ).fetchone() is None:
            raise AgentControlError(f"Task {task_id} report requires an active claim for {worker_id}")
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
            INSERT INTO task_reports(task_id, worker_id, tenant_id, reported_at, report_json, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, worker_id, task["tenant_id"], now, canonical_json(report), "submitted"),
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
        _close_task_activity(conn, task_id=task_id, status="reported", now=now)
        report_node = upsert_graph_node(
            conn,
            node_id=f"report:{task_id}:{report_id}",
            kind="episode",
            title=f"{worker_id} report for {task_id}",
            body=finding,
            tenant_id=task["tenant_id"],
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
                tenant_id=task["tenant_id"],
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
            payload={
                "task_id": task_id,
                "worker_id": worker_id,
                "report_id": report_id,
                "tenant_id": task["tenant_id"],
            },
            tenant_id=task["tenant_id"],
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
        "tenant_id": task.get("tenant_id") or DEFAULT_TENANT_ID,
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
        tenant_id=task.get("tenant_id") or DEFAULT_TENANT_ID,
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
            tenant_id=task.get("tenant_id") or DEFAULT_TENANT_ID,
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
            tenant_id=task.get("tenant_id") or DEFAULT_TENANT_ID,
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
            tenant_id=task.get("tenant_id") or DEFAULT_TENANT_ID,
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
    with _locked_db_transaction(db_path) as conn:
        task = _task_row(conn, task_id)
        if task["status"] != "reported":
            raise AgentControlError(f"Task {task_id} cannot be accepted from status {task['status']}")
        accept_metadata = metadata or {}
        _assert_metadata_tenant_allowed(accept_metadata, tenant_id=task["tenant_id"])
        now = utc_now()
        _guard_task_status_update(
            conn,
            task_id=task_id,
            next_status="accepted",
            now=now,
            allowed_statuses={"reported"},
        )
        _update_task_graph_status(conn, task_id, "accepted", accepted_by=accepted_by)
        _close_task_activity(conn, task_id=task_id, status="accepted", now=now)
        decision_node = _upsert_operating_memory(
            conn,
            node_id=f"decision:{task_id}:{uuid.uuid4().hex[:8]}",
            memory_type="decision",
            title=f"Accepted {task_id}",
            body=summary,
            tenant_id=task["tenant_id"],
            sub_tenant_id=task["pathway"],
            metadata={
                **accept_metadata,
                "task_id": task_id,
                "accepted_by": accepted_by,
                "pathway": task["pathway"],
            },
            source_ref=f"task:{task_id}",
        )
        conn.execute(
            """
            INSERT INTO decisions(task_id, graph_node_id, tenant_id, summary, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, decision_node["id"], task["tenant_id"], summary, now, canonical_json(accept_metadata)),
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
                "tenant_id": task["tenant_id"],
            },
            tenant_id=task["tenant_id"],
        )
        result = _task_row(conn, task_id)
        result["decision_node_id"] = decision_node["id"]
        result["writeback_node_ids"] = writeback_node_ids
        return result


def _assert_public_trusted_evidence_attestation_absent(
    metadata: dict[str, Any],
    *,
    field_name: str,
) -> None:
    if TRUSTED_EVIDENCE_ATTESTATION_KEY in metadata:
        raise AgentControlError(
            f"{field_name} cannot set reserved trusted evidence attestation; use a trusted evidence writer"
        )


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
    upsert: bool = False,
) -> dict[str, Any]:
    node_id = node_id or _short_id(kind.upper())
    metadata = dict(metadata or {})
    _assert_public_trusted_evidence_attestation_absent(metadata, field_name="graph remember")
    if metadata.get("source_type") == "operating_memory":
        raise AgentControlError("graph remember cannot create operating_memory nodes; use memory remember")
    if node_id.startswith("memory:"):
        raise AgentControlError("graph remember cannot use reserved operating-memory ids")
    if node_id.startswith("session:"):
        raise AgentControlError("graph remember cannot use reserved trusted-session ids")
    _assert_memory_policy_valid(
        title=title,
        body=body,
        metadata=metadata,
        field_name="graph memory",
    )
    metadata = _metadata_for_retrieval(metadata)
    with _locked_db_transaction(db_path) as conn:
        existing = _row_dict(conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone())
        if existing is not None and _is_operating_memory(existing.get("metadata") or {}):
            raise AgentControlError(f"graph remember cannot replace operating-memory node: {node_id}")
        if existing is not None and TRUSTED_EVIDENCE_ATTESTATION_KEY in (existing.get("metadata") or {}):
            raise AgentControlError(f"graph remember cannot replace trusted evidence node: {node_id}")
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
            tenant_id=tenant_id,
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
    metadata = dict(metadata or {})
    _assert_public_trusted_evidence_attestation_absent(metadata, field_name="memory remember")
    with _locked_db_transaction(db_path) as conn:
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
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
        )
        return node


def _session_payload_sha256(payload: dict[str, Any]) -> str:
    return _text_sha256(canonical_json(payload))


def _deliver_session_sidecar_unlocked(
    *,
    db_path: Path,
    sessions_path: Path,
    session_id: str,
) -> None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT payload_json, payload_sha256 FROM session_sidecar_outbox WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        raise AgentControlError(f"session sidecar outbox row is missing: {session_id}")
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"session sidecar outbox payload is invalid: {session_id}") from exc
    if not isinstance(payload, dict) or payload.get("session_id") != session_id:
        raise AgentControlError(f"session sidecar outbox payload identity mismatch: {session_id}")
    if _session_payload_sha256(payload) != row["payload_sha256"]:
        raise AgentControlError(f"session sidecar outbox payload hash mismatch: {session_id}")
    existing_rows = _read_jsonl(sessions_path)
    matching = [item for item in existing_rows if item.get("session_id") == session_id]
    if len(matching) > 1:
        raise AgentControlError(f"sessions.jsonl contains duplicate session id: {session_id}")
    if matching:
        if canonical_json(matching[0]) != canonical_json(payload):
            raise AgentControlError(f"sessions.jsonl conflicts with durable session payload: {session_id}")
    else:
        try:
            _append_jsonl(sessions_path, payload)
        except OSError as exc:
            raise AgentControlError(f"session sidecar delivery failed and remains retryable: {session_id}: {exc}") from exc
    with _locked_db_transaction(db_path) as conn:
        conn.execute(
            "UPDATE session_sidecar_outbox SET delivered_at = COALESCE(delivered_at, ?) WHERE session_id = ?",
            (utc_now(), session_id),
        )


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
    metadata = dict(metadata or {})
    _assert_public_trusted_evidence_attestation_absent(metadata, field_name="session log")
    sessions_path = _effective_sessions_path(db_path=db_path, sessions_path=sessions_path)
    resolved = _resolve_inside_repo(repo_root, transcript_path)
    if not resolved.is_file():
        raise AgentControlError(f"transcript file not found: {resolved}")
    relative_path = _relative_to_repo(repo_root, resolved)
    _assert_memory_safe_source_path(relative_path)
    try:
        source_snapshot = resolved.read_bytes()
        text = source_snapshot.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentControlError(f"session transcript must be UTF-8 text: {relative_path}") from exc
    except OSError as exc:
        raise AgentControlError(f"session transcript could not be read: {relative_path}: {exc}") from exc
    current_sha256 = hashlib.sha256(source_snapshot).hexdigest()
    if expected_sha256 is not None and expected_sha256 != current_sha256:
        raise AgentControlError(
            f"transcript hash mismatch for {resolved}: expected {expected_sha256}, got {current_sha256}"
        )
    if any(pattern.search(text) for pattern in MEMORY_SECRET_SHAPED_RE):
        raise AgentControlError(f"session transcript contains secret-shaped content: {relative_path}")
    session_id = session_id or _short_id("S")
    now = utc_now()
    payload = {
        "session_id": session_id,
        "logged_at": now,
        "title": title or relative_path,
        "summary": summary,
        "actor": actor,
        "tenant_id": tenant_id,
        "path": relative_path,
        "source_sha256": current_sha256,
        "bytes": len(source_snapshot),
        "line_count": len(text.splitlines()),
        "metadata": metadata,
    }
    trusted_attestation = {
        "version": TRUSTED_EVIDENCE_ATTESTATION_VERSION,
        "writer": "log_session",
        "record_type": "session_sidecar_outbox",
        "record_id": session_id,
    }
    node_body = summary or _repo_file_excerpt(text, max_chars=2500)
    _assert_memory_policy_valid(
        title=payload["title"],
        body=node_body,
        metadata=_with_memory_policy_metadata(metadata, source_type="session_transcript"),
        field_name="session transcript memory",
    )
    with _control_file_lock(_lock_path_for_db(db_path), timeout_seconds=30.0):
        idempotent = False
        with closing(connect(db_path)) as conn, conn:
            existing = _row_dict(
                conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (f"session:{session_id}",)).fetchone()
            )
            if existing is not None:
                existing_metadata = existing.get("metadata") or {}
                if existing.get("tenant_id") != tenant_id:
                    raise AgentControlError(f"session id already belongs to another tenant: {session_id}")
                if (
                    existing_metadata.get("source_type") != "session_transcript"
                    or existing_metadata.get("session_id") != session_id
                ):
                    raise AgentControlError(f"session id collides with a non-session graph node: {session_id}")
                if existing_metadata.get("source_sha256") != current_sha256:
                    raise AgentControlError(f"session id is immutable and already has different content: {session_id}")
                try:
                    existing_bytes = int(existing_metadata.get("bytes"))
                except (TypeError, ValueError) as exc:
                    raise AgentControlError(
                        f"session id is immutable and has invalid stored provenance: {session_id}"
                    ) from exc
                if (
                    existing_metadata.get("path") != relative_path
                    or existing_bytes != len(source_snapshot)
                ):
                    raise AgentControlError(f"session id is immutable and already has different provenance: {session_id}")
                payload["logged_at"] = existing_metadata.get("logged_at") or payload["logged_at"]
                idempotent = True
            else:
                node = upsert_graph_node(
                    conn,
                    node_id=f"session:{session_id}",
                    kind="episode",
                    title=payload["title"],
                    body=node_body,
                    tenant_id=tenant_id,
                    sub_tenant_id=sub_tenant_id,
                    metadata={
                        **metadata,
                        "source_type": "session_transcript",
                        "session_id": session_id,
                        "actor": actor,
                        "path": relative_path,
                        "source_sha256": current_sha256,
                        "line_count": payload["line_count"],
                        "bytes": payload["bytes"],
                        "logged_at": now,
                        TRUSTED_EVIDENCE_ATTESTATION_KEY: trusted_attestation,
                    },
                    source_ref=relative_path,
                    upsert=False,
                )
                _record_event(
                    conn,
                    events_path=events_path,
                    event_type="session.logged",
                    payload={
                        "session_id": session_id,
                        "node_id": node["id"],
                        "path": relative_path,
                        "tenant_id": tenant_id,
                    },
                    tenant_id=tenant_id,
                )
            payload_json = canonical_json(payload)
            payload_sha256 = _session_payload_sha256(payload)
            existing_outbox = conn.execute(
                "SELECT payload_sha256 FROM session_sidecar_outbox WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing_outbox is not None and existing_outbox["payload_sha256"] != payload_sha256:
                raise AgentControlError(f"session sidecar outbox conflicts with immutable session: {session_id}")
            conn.execute(
                """
                INSERT INTO session_sidecar_outbox(
                    session_id, tenant_id, payload_json, payload_sha256, created_at, delivered_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (session_id, tenant_id, payload_json, payload_sha256, payload["logged_at"]),
            )
            if existing is not None:
                _update_graph_node_metadata(
                    conn,
                    f"session:{session_id}",
                    {TRUSTED_EVIDENCE_ATTESTATION_KEY: trusted_attestation},
                )
        _deliver_session_sidecar_unlocked(
            db_path=db_path,
            sessions_path=sessions_path,
            session_id=session_id,
        )
    result = {**payload, "graph_node_id": f"session:{session_id}"}
    if idempotent:
        result["idempotent"] = True
    return result


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


def _read_dream_proposal_snapshot(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    try:
        snapshot = path.read_bytes()
        raw_text = snapshot.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AgentControlError("dream proposal must be UTF-8 JSON") from exc
    except OSError as exc:
        raise AgentControlError(f"dream proposal could not be read: {path}: {exc}") from exc
    if any(pattern.search(raw_text) for pattern in MEMORY_SECRET_SHAPED_RE):
        raise AgentControlError("dream proposal contains secret-shaped content")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AgentControlError(f"dream proposal must be valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise AgentControlError("dream proposal must be a JSON object")
    entries = _parse_dream_entries(raw.get("entries") or [])
    if not entries:
        raise AgentControlError("dream proposal requires at least one entry")
    return raw, entries, hashlib.sha256(snapshot).hexdigest()


def _dream_evidence_integrity_hash(metadata: dict[str, Any]) -> str:
    value = metadata.get("source_sha256") or metadata.get("source_content_sha256") or metadata.get("content_sha256")
    return str(value or "")


def _session_evidence_attestation_is_valid(
    conn: sqlite3.Connection,
    *,
    node: dict[str, Any],
    metadata: dict[str, Any],
    attestation: dict[str, Any],
    integrity_hash: str,
) -> bool:
    session_id = str(metadata.get("session_id") or "")
    if (
        attestation.get("writer") != "log_session"
        or attestation.get("record_type") != "session_sidecar_outbox"
        or str(attestation.get("record_id") or "") != session_id
        or not session_id
        or node.get("id") != f"session:{session_id}"
        or node.get("kind") != "episode"
    ):
        return False
    row = conn.execute(
        """
        SELECT tenant_id, payload_json, payload_sha256
        FROM session_sidecar_outbox
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None or str(row["tenant_id"]) != str(node.get("tenant_id") or ""):
        return False
    try:
        payload = json.loads(row["payload_json"] or "{}")
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict) or _session_payload_sha256(payload) != str(row["payload_sha256"] or ""):
        return False
    path = str(metadata.get("path") or "")
    try:
        metadata_bytes = int(metadata.get("bytes"))
        payload_bytes = int(payload.get("bytes"))
    except (TypeError, ValueError):
        return False
    return (
        payload.get("session_id") == session_id
        and str(payload.get("tenant_id") or "") == str(node.get("tenant_id") or "")
        and str(payload.get("path") or "") == path
        and str(payload.get("source_sha256") or "") == integrity_hash
        and payload_bytes == metadata_bytes
        and str(payload.get("logged_at") or "") == str(metadata.get("logged_at") or "")
        and str(node.get("source_ref") or "") == path
    )


def _artifact_evidence_attestation_is_valid(
    conn: sqlite3.Connection,
    *,
    node: dict[str, Any],
    metadata: dict[str, Any],
    attestation: dict[str, Any],
    integrity_hash: str,
) -> bool:
    artifact_id = attestation.get("artifact_id")
    if (
        attestation.get("writer") != "evidence_artifact"
        or isinstance(artifact_id, bool)
        or not isinstance(artifact_id, int)
        or artifact_id < 1
    ):
        return False
    row = conn.execute(
        """
        SELECT id, graph_node_id, tenant_id, path, evidence_class, metadata_json
        FROM evidence_artifacts
        WHERE id = ?
        """,
        (artifact_id,),
    ).fetchone()
    if (
        row is None
        or str(row["graph_node_id"] or "") != str(node.get("id") or "")
        or str(row["tenant_id"] or "") != str(node.get("tenant_id") or "")
        or not str(row["evidence_class"] or "").strip()
    ):
        return False
    try:
        artifact_metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        return False
    if not isinstance(artifact_metadata, dict):
        return False
    artifact_hash = _dream_evidence_integrity_hash(artifact_metadata)
    node_path = str(metadata.get("path") or metadata.get("source_path") or node.get("source_ref") or "")
    return (
        artifact_metadata.get("trusted_writer_attestation_version") == TRUSTED_EVIDENCE_ATTESTATION_VERSION
        and artifact_hash == integrity_hash
        and bool(node_path)
        and _safe_node_path(str(row["path"])) == _safe_node_path(node_path)
    )


def _dream_evidence_is_reviewed(conn: sqlite3.Connection, node: dict[str, Any]) -> bool:
    metadata = node.get("metadata") or {}
    source_type = str(metadata.get("source_type") or "")
    if node.get("kind") not in DREAM_OBSERVED_EVIDENCE_NODE_KINDS:
        return False
    if source_type not in DREAM_OBSERVED_EVIDENCE_SOURCE_TYPES:
        return False
    integrity_hash = _dream_evidence_integrity_hash(metadata)
    if re.fullmatch(r"[0-9a-f]{64}", integrity_hash) is None:
        return False
    attestation = metadata.get(TRUSTED_EVIDENCE_ATTESTATION_KEY)
    if (
        not isinstance(attestation, dict)
        or attestation.get("version") != TRUSTED_EVIDENCE_ATTESTATION_VERSION
    ):
        return False
    if source_type == "session_transcript":
        return _session_evidence_attestation_is_valid(
            conn,
            node=node,
            metadata=metadata,
            attestation=attestation,
            integrity_hash=integrity_hash,
        )
    if not _artifact_evidence_attestation_is_valid(
        conn,
        node=node,
        metadata=metadata,
        attestation=attestation,
        integrity_hash=integrity_hash,
    ):
        return False
    if source_type == "operating_memory":
        return (
            _has_operating_authority_metadata(metadata)
            and metadata.get("memory_type") in {"artifact", "verification", "worker_report"}
            and metadata.get("confidence") in {"accepted", "observed"}
        )
    return True


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
    raw, entries, current_sha256 = _read_dream_proposal_snapshot(resolved)
    if expected_sha256 is not None and expected_sha256 != current_sha256:
        raise AgentControlError(
            f"dream proposal hash mismatch for {resolved}: expected {expected_sha256}, got {current_sha256}"
        )
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
    with _locked_db_transaction(db_path) as conn:
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
                    "proposal_repo_root": str(repo_root.resolve()),
                    "path": relative_path,
                    "entry_count": len(entries),
                    "entries": entries,
                    "source_entries_sha256": _text_sha256(canonical_json(entries)),
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
            payload={
                "dream_id": dream_id,
                "node_id": node["id"],
                "entry_count": len(entries),
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
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
    repo_root: Path | None = None,
) -> dict[str, Any]:
    dream_node_id = dream_id if dream_id.startswith("dream:") else f"dream:{dream_id}"
    accepted_at = utc_now()
    accepted_memory_ids: list[str] = []
    with _locked_db_transaction(db_path) as conn:
        proposal = _graph_node_row(conn, dream_node_id)
        metadata = proposal.get("metadata") or {}
        if metadata.get("source_type") != "dream_proposal":
            raise AgentControlError(f"not a dream proposal node: {dream_node_id}")
        if metadata.get("proposal_status") != "proposed":
            raise AgentControlError(
                f"dream proposal {dream_node_id} cannot be accepted from status {metadata.get('proposal_status')}"
            )
        source_root = (repo_root or Path(str(metadata.get("proposal_repo_root") or ROOT))).resolve()
        source_path = _resolve_inside_repo(
            source_root,
            Path(str(metadata.get("path") or proposal.get("source_ref") or "")),
        )
        _assert_memory_safe_source_path(_relative_to_repo(source_root, source_path))
        if not source_path.is_file():
            raise AgentControlError(f"dream proposal source changed or is missing: {source_path}")
        _source_raw, source_entries, source_sha256 = _read_dream_proposal_snapshot(source_path)
        if source_sha256 != metadata.get("source_sha256"):
            raise AgentControlError(f"dream proposal source changed or is missing: {source_path}")
        entries = _parse_dream_entries(metadata.get("entries") or [])
        if canonical_json(source_entries) != canonical_json(entries):
            raise AgentControlError("dream proposal stored entries differ from the verified source entries")
        if metadata.get("source_entries_sha256") not in {
            None,
            "",
            _text_sha256(canonical_json(source_entries)),
        }:
            raise AgentControlError("dream proposal stored entry digest differs from the verified source entries")
        for entry in entries:
            if entry["confidence"] == "observed" and not entry.get("evidence"):
                raise AgentControlError(
                    f"dream entry {entry['id']} cannot be accepted as observed without evidence"
                )
            if entry["confidence"] == "observed":
                for evidence_node_id in entry.get("evidence") or []:
                    evidence_node = _row_dict(
                        conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (evidence_node_id,)).fetchone()
                    )
                    if evidence_node is None:
                        raise AgentControlError(
                            f"dream entry {entry['id']} evidence graph node not found: {evidence_node_id}"
                        )
                    if evidence_node.get("tenant_id") != proposal.get("tenant_id"):
                        raise AgentControlError(
                            f"dream entry {entry['id']} evidence belongs to another tenant: {evidence_node_id}"
                        )
                    if evidence_node.get("kind") not in DREAM_OBSERVED_EVIDENCE_NODE_KINDS:
                        raise AgentControlError(
                            f"dream entry {entry['id']} evidence kind is not allowed: {evidence_node_id}"
                        )
                    if not _dream_evidence_is_reviewed(conn, evidence_node):
                        raise AgentControlError(
                            f"dream entry {entry['id']} evidence is not reviewed, provenanced, and integrity-bearing: "
                            f"{evidence_node_id}"
                        )
            entry_pathway = str((entry.get("metadata") or {}).get("pathway") or "").strip()
            if entry_pathway:
                _validate_choice(entry_pathway, PATHWAYS, "dream entry pathway")
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
                sub_tenant_id=entry_pathway or proposal.get("sub_tenant_id"),
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
                "tenant_id": proposal.get("tenant_id") or DEFAULT_TENANT_ID,
            },
            tenant_id=proposal.get("tenant_id") or DEFAULT_TENANT_ID,
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
    with _locked_db_transaction(db_path) as conn:
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
            payload={
                "dream_id": metadata.get("dream_id"),
                "dream_node_id": dream_node_id,
                "reason": reason,
                "tenant_id": proposal.get("tenant_id") or DEFAULT_TENANT_ID,
            },
            tenant_id=proposal.get("tenant_id") or DEFAULT_TENANT_ID,
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
        if not _dream_evidence_is_reviewed(conn, node):
            return f"{field_name} evidence is not trusted-writer attested: {evidence_node_id}"
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
                expected_sha256 = str(metadata.get("source_sha256") or "")
                if expected_sha256 and _file_sha256(resolved) != expected_sha256:
                    sources.append("transcript_hash_mismatch")
                    return "", sources
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
        if not _dream_evidence_is_reviewed(conn, node):
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
                source_invalid = any(
                    marker in scanned_sources
                    for marker in {"transcript_file_unreadable", "transcript_hash_mismatch"}
                )
                if not source_invalid:
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
                        "marked_processed": not source_invalid,
                    }
                )
                if source_invalid:
                    reason = (
                        "session transcript hash changed; not marking processed"
                        if "transcript_hash_mismatch" in scanned_sources
                        else "session transcript source was unreadable; not marking processed"
                    )
                    result["skipped"].append(
                        {
                            "dream_id": session["id"],
                            "dream_node_id": session["id"],
                            "reason": reason,
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
    with _locked_db_transaction(db_path) as conn:
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
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
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
    with _locked_db_transaction(db_path) as conn:
        old_node = _require_operating_memory_node(conn, old_node_id, field_name="old_node_id")
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
            payload={
                "old_node_id": old_node_id,
                "new_node_id": new_node_id,
                "reason": reason,
                "tenant_id": old_node["tenant_id"],
            },
            tenant_id=old_node["tenant_id"],
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
    with _locked_db_transaction(db_path) as conn:
        source_node = _graph_node_row(conn, source_node_id)
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
                "tenant_id": source_node["tenant_id"],
            },
            tenant_id=source_node["tenant_id"],
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
    source_content_sha256 = _text_sha256(raw)
    gateboard_snapshot_sha256 = _gateboard_source_artifact_hash(repo_root, relative_path)
    if gateboard_snapshot_sha256 is None:
        raise AgentControlError(f"gateboard snapshot is missing or unsafe: {relative_path}")

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
            "source_content_sha256": source_content_sha256,
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
                "source_content_sha256": source_content_sha256,
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
                "source_content_sha256": source_content_sha256,
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
        artifact_path = str(artifact.get("path") or "")
        artifact_available = artifact.get("available")
        if artifact_available not in {True, False}:
            raise AgentControlError(f"gateboard source artifact available must be boolean: {key}")
        artifact_snapshot_sha256 = None
        if artifact_available:
            artifact_snapshot_sha256 = _gateboard_source_artifact_hash(repo_root, artifact_path)
            if artifact_snapshot_sha256 is None:
                raise AgentControlError(
                    f"declared available gateboard source artifact is missing or unsafe: {key}: {artifact_path}"
                )
        node = upsert_graph_node(
            conn,
            node_id=f"evidence_artifact:gateboard:{key}",
            kind="evidence_artifact",
            title=f"Gateboard source artifact: {key}",
            body=artifact_path,
            tenant_id=tenant_id,
            sub_tenant_id="operator",
            metadata={
                "source_type": "gateboard_source_artifact",
                "source_path": relative_path,
                "source_content_sha256": gateboard_snapshot_sha256,
                "freshness_provenance_mode": "gateboard_snapshot_sha256",
                "gateboard_source_path": relative_path,
                "gateboard_source_content_sha256": gateboard_snapshot_sha256,
                "gateboard_body_sha256": source_content_sha256,
                "artifact_snapshot_path": artifact_path,
                "artifact_snapshot_sha256": artifact_snapshot_sha256,
                "artifact_snapshot_hash_mode": "sha256_bytes" if artifact_available else None,
                "artifact_key": key,
                "path": artifact_path,
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
    with _locked_db_transaction(db_path) as conn:
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
            node_id=_latest_checkpoint_node_id(tenant_id),
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
        if conn.execute(
            "SELECT id FROM graph_nodes WHERE id = ? AND tenant_id = ?",
            ("knowledge:gateboard:latest", tenant_id),
        ).fetchone():
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
            payload={
                "checkpoint_id": checkpoint_id,
                "latest_node_id": latest_node["id"],
                "status": status,
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
        )
        latest_node["history_node_id"] = history_node["id"]
        return latest_node


def _latest_checkpoint_node_id(tenant_id: str) -> str:
    if tenant_id == DEFAULT_TENANT_ID:
        return "checkpoint:latest"
    return f"checkpoint:latest:{hashlib.sha256(tenant_id.encode('utf-8')).hexdigest()[:12]}"


def latest_checkpoint(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any] | None:
    with _locked_db_transaction(db_path) as conn:
        return _row_dict(
            conn.execute(
                "SELECT * FROM graph_nodes WHERE id = ? AND tenant_id = ?",
                (_latest_checkpoint_node_id(tenant_id), tenant_id),
            ).fetchone()
        )


def _latest_gateboard_hash(conn: sqlite3.Connection, *, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    rows = conn.execute(
        """
        SELECT id, title, body, metadata_json, source_ref, updated_at
        FROM graph_nodes
        WHERE tenant_id = ? AND metadata_json LIKE '%gateboard%'
        ORDER BY updated_at DESC
        LIMIT 50
        """,
        (tenant_id,),
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
        "gateboard_hash": _latest_gateboard_hash(
            conn,
            tenant_id=str(result.get("tenant_id") or DEFAULT_TENANT_ID),
        ),
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
    with _locked_db_transaction(db_path) as conn:
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
            tenant_id=tenant_id,
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
        "digest": digest(db_path=db_path, recent_limit=5, tenant_id=tenant_id),
        "latest_checkpoint": latest_checkpoint(db_path=db_path, tenant_id=tenant_id),
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
            fresh_only=fresh_only,
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
            if fresh_only:
                freshness_row = conn.execute(
                    "SELECT freshness_status FROM retrieval_documents WHERE source_node_id = ?",
                    (node["id"],),
                ).fetchone()
                if freshness_row is None or freshness_row["freshness_status"] != "current":
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
                if fresh_only:
                    freshness_row = conn.execute(
                        "SELECT freshness_status FROM retrieval_documents WHERE source_node_id = ?",
                        (other["id"],),
                    ).fetchone()
                    if freshness_row is None or freshness_row["freshness_status"] != "current":
                        continue
                edge_map[edge["id"]] = edge
                node_map[other["id"]] = other
                if other["id"] not in seen_depth or seen_depth[other["id"]] > depth + 1:
                    seen_depth[other["id"]] = depth + 1
                    frontier.append((other["id"], depth + 1))

        safe_edges = {edge_id: _edge_for_query_result(edge) for edge_id, edge in edge_map.items()}
        triplets = [
            {
                "source": edge["source_node_id"],
                "relation": edge["relation"],
                "target": edge["target_node_id"],
                "metadata": edge.get("metadata", {}),
            }
            for edge in safe_edges.values()
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
                "edges": sorted(safe_edges.values(), key=lambda item: item["id"]),
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
        nodes.append(_node_for_query_result(node))
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
    include_repo_index: bool = False,
) -> dict[str, Any]:
    if pathway is not None:
        _validate_choice(pathway, PATHWAYS, "pathway")
    latest = latest_checkpoint(db_path=db_path, tenant_id=tenant_id)
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
                            sub_tenant_id=pathway,
                            memory_type="lesson",
                            active_only=True,
                            limit=limit,
                        ),
                        *_select_graph_nodes(
                            conn,
                            tenant_id=tenant_id,
                            sub_tenant_id=pathway,
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
    if include_repo_index:
        repo_hits = query_graph(
            db_path=db_path,
            query=repo_query,
            tenant_id=tenant_id,
            metadata_filter={"source_type": "repo_file_index"},
            limit=limit,
            max_depth=0,
            include_repo_index=True,
            fresh_only=True,
        )
        result["relevant_repo_files"] = repo_hits["graph_context"]["nodes"][:limit]
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
    retrieval_parity_issues: list[dict[str, Any]] = []
    required_freshness_issues: list[dict[str, Any]] = []
    tier3_repo_mirror_gaps: list[dict[str, Any]] = []
    quarantined_metadata: list[dict[str, Any]] = []
    quarantined_edge_metadata: list[dict[str, Any]] = []
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
            source_type = str(metadata.get("source_type") or "graph_node")
            prohibited_paths = _prohibited_metadata_paths(metadata)
            if prohibited_paths:
                quarantined_metadata.append(
                    {
                        **node,
                        "metadata": {
                            **metadata,
                            "audit_issue": "prohibited action flags",
                            "paths": prohibited_paths,
                        },
                    }
                )
            document_row = conn.execute(
                "SELECT * FROM retrieval_documents WHERE source_node_id = ?",
                (node["id"],),
            ).fetchone()
            if document_row is None:
                issue = {**node, "metadata": {**metadata, "audit_issue": "retrieval document missing"}}
                if source_type == "repo_file_index":
                    tier3_repo_mirror_gaps.append(issue)
                else:
                    retrieval_parity_issues.append(issue)
            else:
                retrieval_metadata = _metadata_for_retrieval(metadata)
                retrieval_title, retrieval_body = _node_retrieval_title_body(node, metadata)
                expected_content_sha256 = _text_sha256(
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
                parity_matches = (
                    document_row["title"] == retrieval_title
                    and document_row["body"] == retrieval_body
                    and json.loads(document_row["metadata_json"] or "{}") == retrieval_metadata
                    and document_row["content_sha256"] == expected_content_sha256
                    and document_row["source_type"] == source_type
                )
                if not parity_matches:
                    retrieval_parity_issues.append(
                        {
                            **node,
                            "metadata": {
                                **metadata,
                                "audit_issue": "graph/retrieval content or metadata mismatch",
                            },
                        }
                    )
                freshness_status = str(document_row["freshness_status"])
                if freshness_status != "current":
                    issue = {
                        **node,
                        "metadata": {
                            **metadata,
                            "audit_issue": f"retrieval freshness is {freshness_status}",
                        },
                    }
                    if source_type == "repo_file_index":
                        tier3_repo_mirror_gaps.append(issue)
                    elif source_type in REQUIRED_FRESH_RETRIEVAL_SOURCE_TYPES:
                        required_freshness_issues.append(issue)
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
                metadata=metadata,
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
        existing_required_ids = {str(item.get("id") or "") for item in required_freshness_issues}
        for issue in _required_retrieval_freshness_issues(conn, tenant_id=tenant_id):
            if issue["node_id"] in existing_required_ids:
                continue
            existing_node = _row_dict(
                conn.execute(
                    "SELECT * FROM graph_nodes WHERE id = ? AND tenant_id = ?",
                    (issue["node_id"], tenant_id),
                ).fetchone()
            )
            if existing_node is not None:
                existing_metadata = existing_node.get("metadata") or {}
                required_freshness_issues.append(
                    {
                        **existing_node,
                        "metadata": {
                            **existing_metadata,
                            "required_source_type": issue["source_type"],
                            "audit_issue": issue["issue"],
                            "graph_node_missing": bool(issue["graph_node_missing"]),
                            "retrieval_document_missing": bool(issue["retrieval_document_missing"]),
                        },
                    }
                )
            else:
                required_freshness_issues.append(
                    {
                        "id": issue["node_id"],
                        "kind": "knowledge",
                        "tenant_id": tenant_id,
                        "sub_tenant_id": None,
                        "title": f"Missing required retrieval source: {issue['source_type']}",
                        "body": issue.get("source_path") or "",
                        "source_ref": issue.get("source_path") or "",
                        "created_at": "",
                        "updated_at": "",
                        "metadata": {
                            "source_type": issue["source_type"],
                            "audit_issue": issue["issue"],
                            "graph_node_missing": bool(issue["graph_node_missing"]),
                            "retrieval_document_missing": bool(issue["retrieval_document_missing"]),
                        },
                    }
                )
            existing_required_ids.add(issue["node_id"])
        edge_rows = conn.execute(
            """
            SELECT e.*
            FROM graph_edges e
            JOIN graph_nodes source ON source.id = e.source_node_id
            WHERE source.tenant_id = ?
            ORDER BY e.created_at DESC
            """,
            (tenant_id,),
        ).fetchall()
        for edge_row in edge_rows:
            edge = _row_dict(edge_row)
            if edge is None:
                continue
            edge_metadata = edge.get("metadata") or {}
            prohibited_paths = _prohibited_metadata_paths(edge_metadata)
            policy_errors = _validate_memory_policy_text(
                title=str(edge.get("relation") or ""),
                body="",
                metadata=edge_metadata,
                field_name=f"edge {edge['id']}",
            )
            if prohibited_paths or policy_errors:
                quarantined_edge_metadata.append(
                    {
                        **edge,
                        "metadata": {
                            **edge_metadata,
                            "audit_issue": "edge metadata contains prohibited authority context",
                            "paths": prohibited_paths,
                            "policy_errors": policy_errors,
                        },
                    }
                )
    issue_count = (
        len(authority_inconsistencies)
        + len(stale_or_expired)
        + len(supersession_inconsistencies)
        + len(retrieval_parity_issues)
        + len(required_freshness_issues)
        + len(quarantined_metadata)
        + len(quarantined_edge_metadata)
    )
    safe_nodes = lambda items: [_node_for_query_result(item) for item in items[:limit]]
    result = {
        "status": "pass" if issue_count == 0 else "issues",
        "checked_memories": checked_memories,
        "authority_inconsistencies": safe_nodes(authority_inconsistencies),
        "stale_or_expired": safe_nodes(stale_or_expired),
        "supersession_inconsistencies": safe_nodes(supersession_inconsistencies),
        "retrieval_parity_issues": safe_nodes(retrieval_parity_issues),
        "required_freshness_issues": safe_nodes(required_freshness_issues),
        "tier3_repo_mirror_gaps_nonfatal": safe_nodes(tier3_repo_mirror_gaps),
        "quarantined_metadata": safe_nodes(quarantined_metadata),
        "quarantined_edge_metadata": [
            _edge_for_query_result(edge) for edge in quarantined_edge_metadata[:limit]
        ],
        "open_questions": safe_nodes(open_questions),
        "open_blockers": safe_nodes(open_blockers),
        "policy_banner": MEMORY_NON_AUTHORIZATION_BANNER,
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
    with _locked_db_transaction(db_path) as conn:
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
            _upsert_retrieval_document(conn, _graph_node_row(conn, row["id"]))
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
    checkpoint = latest_checkpoint(db_path=db_path, tenant_id=tenant_id)
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
        retrieval_count = conn.execute(
            """
            SELECT count(*) FROM retrieval_documents d
            JOIN graph_nodes n ON n.id = d.source_node_id
            WHERE n.tenant_id = ?
            """,
            (tenant_id,),
        ).fetchone()[0]
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
            ) or checkpoint is not None and checkpoint.get("metadata", {}).get("autonomy_level") in TRADING_FAIL_CLOSED_PERMISSION_MODES,
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
    with _locked_db_transaction(db_path) as conn:
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
            payload={
                "id": episode_id,
                "graph_node_id": node["id"],
                "lane": lane,
                "selection_date": selection_date,
                "tenant_id": tenant_id,
            },
            tenant_id=tenant_id,
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
        with _locked_db_transaction(db_path) as conn:
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
                tenant_id=tenant_id,
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


def digest(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    recent_limit: int = 8,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    with _locked_db_transaction(db_path) as conn:
        task_counts = {
            row["status"]: row["count"]
            for row in conn.execute(
                "SELECT status, count(*) AS count FROM tasks WHERE tenant_id = ? GROUP BY status",
                (tenant_id,),
            )
        }
        graph_counts = {
            row["kind"]: row["count"]
            for row in conn.execute(
                "SELECT kind, count(*) AS count FROM graph_nodes WHERE tenant_id = ? GROUP BY kind",
                (tenant_id,),
            )
        }
        recent_tasks = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM tasks
                WHERE tenant_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (tenant_id, recent_limit),
            )
        ]
        blockers = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT graph_nodes.*
                FROM graph_nodes
                WHERE kind = 'blocker' AND tenant_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (tenant_id, recent_limit),
            )
        ]
        events = [
            _row_dict(row)
            for row in conn.execute(
                """
                SELECT * FROM event_log
                WHERE json_extract(payload_json, '$.tenant_id') = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (tenant_id, recent_limit),
            )
        ]
        return {
            "db_path": str(db_path),
            "runtime_use": True,
            "tenant_id": tenant_id,
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
    tenant_id: str = DEFAULT_TENANT_ID,
    limit: int = 20,
) -> dict[str, Any]:
    if status is not None:
        _validate_choice(status, TASK_STATUSES, "status")
    if pathway is not None:
        _validate_choice(pathway, PATHWAYS, "pathway")
    clauses = ["tenant_id = ?"]
    params: list[Any] = [tenant_id]
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
    checkpoint_latest.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
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
    report.add_argument("--proof-gate-status", default="not_applicable", choices=sorted(PROOF_GATE_STATUSES))
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
    list_cmd.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
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
    remember.add_argument(
        "--no-upsert",
        action="store_true",
        help="Deprecated compatibility flag; graph remember is always create-only.",
    )
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
    context_pack.add_argument(
        "--include-repo-index",
        action="store_true",
        help="Opt in to goal-aware tier-3 repo-file hits; the safe default remains off.",
    )
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
    dream_accept.add_argument("--repo-root", type=Path)
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
    memory_mirror_repair = memory_sub.add_parser(
        "repair-event-mirror",
        help="Rebuild events.jsonl from the DB outbox; dry-run unless --apply is supplied.",
    )
    memory_mirror_repair.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    memory_mirror_repair.add_argument("--events", type=Path, default=DEFAULT_EVENTS_PATH)
    memory_mirror_repair.add_argument("--archive-dir", type=Path)
    memory_mirror_repair.add_argument("--apply", action="store_true")
    memory_mirror_repair.add_argument("--json", action="store_true")
    memory_mirror_repair.set_defaults(func=_cmd_memory_repair_event_mirror)
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
    digest_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
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
    result = latest_checkpoint(db_path=args.db, tenant_id=args.tenant_id)
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
    result = list_tasks(
        db_path=args.db,
        status=args.status,
        pathway=args.pathway,
        tenant_id=args.tenant_id,
        limit=args.limit,
    )
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
        upsert=False,
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
        include_repo_index=args.include_repo_index,
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
        repo_root=args.repo_root,
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
    return 0 if result["status"] == "pass" else 1


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


def _cmd_memory_repair_event_mirror(args: argparse.Namespace) -> int:
    result = repair_event_mirror(
        db_path=args.db,
        events_path=args.events,
        archive_dir=args.archive_dir,
        apply=args.apply,
    )
    _emit(result, as_json=True)
    return 0 if result["status"] in {"pass", "would_repair"} else 1


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
        return 0 if result["status"] == "pass" else 1
    _emit(result, as_json=True if args.json else False)
    return 0 if result["status"] == "pass" else 1


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
    result = digest(db_path=args.db, recent_limit=args.recent_limit, tenant_id=args.tenant_id)
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
