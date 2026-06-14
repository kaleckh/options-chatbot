from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import uuid
from collections import deque
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "agent-control" / "agent_control.db"
DEFAULT_EVENTS_PATH = ROOT / "data" / "agent-control" / "events.jsonl"
DEFAULT_TENANT_ID = "options-chatbot"
DEFAULT_REPO_INDEX_MAX_FILES = 2000
DEFAULT_REPO_INDEX_MAX_FILE_BYTES = 256_000
DEFAULT_REPO_INDEX_BODY_CHARS = 12_000
DEFAULT_CHECKPOINT_AUTONOMY_LEVEL = "read_only_workers"
DEFAULT_CONTEXT_PACK_LIMIT = 6

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
MEMORY_STATUSES = {"active", "resolved", "superseded", "expired", "archived"}
INACTIVE_MEMORY_STATUSES = {"resolved", "superseded", "expired", "archived"}
MEMORY_CONFIDENCE = {"accepted", "observed", "inferred", "unknown"}
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
    ".env",
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
    metadata = node.get("metadata", {})
    haystack = " ".join(
        [
            str(node.get("id", "")),
            str(node.get("title", "")),
            str(node.get("body", "")),
            str(node.get("source_ref", "")),
            canonical_json(metadata) if isinstance(metadata, dict) else str(metadata),
        ]
    ).lower()
    if not all(term in haystack for term in terms):
        return None
    score = sum(haystack.count(term) for term in terms)
    if query.lower() in haystack:
        score += len(terms) * 3
    if str(node.get("title", "")).lower().find(query.lower()) >= 0:
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

    lines.append("")
    lines.append("Seed nodes:")
    seed_ids = set(context.get("seed_node_ids", []))
    nodes = context.get("nodes", [])
    ordered_nodes = sorted(nodes, key=lambda node: (node["id"] not in seed_ids, node["id"]))
    for node in ordered_nodes[:max_nodes]:
        source_ref = f" source={node.get('source_ref')}" if node.get("source_ref") else ""
        sub_tenant = f"/{node.get('sub_tenant_id')}" if node.get("sub_tenant_id") else ""
        lines.append(f"- {node['id']} [{node.get('kind')}{sub_tenant}] {node.get('title', '')}{source_ref}")
        body = _truncate(str(node.get("body", "")), 260)
        if body:
            lines.append(f"  body: {body}")
        metadata = node.get("metadata") or {}
        if metadata:
            lines.append(f"  metadata: {_truncate(canonical_json(metadata), 360)}")
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
    next_queries = ["# Recommended Graph Queries"]
    for item in result.get("recommended_next_queries", []):
        next_queries.append(f"- {item['purpose']}: `{item['command']}`")
    return "\n\n".join([checkpoint_text, graph_text, "\n".join(next_queries)])


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
    return "\n".join(lines)


def _format_memory_audit(result: dict[str, Any]) -> str:
    lines = [
        "# Agent Memory Audit",
        f"Status: {result.get('status')}",
        f"Checked memories: {result.get('checked_memories')}",
    ]
    for key, heading in [
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


def _short_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    _ensure_parent(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
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

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            role TEXT NOT NULL,
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
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

        CREATE TABLE IF NOT EXISTS blockers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
            graph_node_id TEXT REFERENCES graph_nodes(id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT
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

        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_pathway ON tasks(pathway, status);
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_scope ON graph_nodes(tenant_id, sub_tenant_id, kind);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id, relation);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id, relation);
        """
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
    conn.execute(
        "INSERT INTO event_log(created_at, event_type, payload_json) VALUES (?, ?, ?)",
        (event["created_at"], event_type, canonical_json(payload)),
    )
    _append_jsonl(events_path, event)
    return event


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


def _graph_node_row(conn: sqlite3.Connection, node_id: str) -> dict[str, Any]:
    row = _row_dict(conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone())
    if row is None:
        raise AgentControlError(f"Unknown graph node: {node_id}")
    return row


def _edge_id(source_node_id: str, relation: str, target_node_id: str) -> str:
    payload = f"{source_node_id}\0{relation}\0{target_node_id}".encode("utf-8")
    return "edge:" + hashlib.sha256(payload).hexdigest()[:32]


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
    now = utc_now()
    metadata_json = canonical_json(metadata or {})
    existing = conn.execute("SELECT id FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
    if existing and not upsert:
        raise AgentControlError(f"Graph node already exists: {node_id}")
    if existing:
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
    return _graph_node_row(conn, node_id)


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
        conn.execute(
            "UPDATE tasks SET status = ?, owner = ?, updated_at = ? WHERE id = ?",
            ("claimed", worker_id, now, task_id),
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
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            ("reported", now, task_id),
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
            conn.execute(
                """
                INSERT INTO blockers(task_id, graph_node_id, status, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, blocker_node["id"], "open", blockers, now),
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
    recorded_at = utc_now()
    memory_metadata = {
        **(metadata or {}),
        "source_type": "operating_memory",
        "memory_type": memory_type,
        "memory_status": memory_status,
        "confidence": confidence,
        "recorded_at": recorded_at,
        "freshness_days": freshness_days,
    }
    if freshness_days is not None:
        memory_metadata["expires_at"] = _utc_plus_days(freshness_days, from_raw=recorded_at)
    if supersedes:
        memory_metadata["supersedes"] = supersedes
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
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            ("accepted", now, task_id),
        )
        _update_task_graph_status(conn, task_id, "accepted", accepted_by=accepted_by)
        decision_node = upsert_graph_node(
            conn,
            node_id=f"decision:{task_id}:{uuid.uuid4().hex[:8]}",
            kind="decision",
            title=f"Accepted {task_id}",
            body=summary,
            sub_tenant_id=task["pathway"],
            metadata={
                **(metadata or {}),
                "source_type": "operating_memory",
                "memory_type": "decision",
                "memory_status": "active",
                "confidence": "accepted",
                "recorded_at": now,
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
    with closing(connect(db_path)) as conn, conn:
        node = upsert_graph_node(
            conn,
            node_id=node_id,
            kind=kind,
            title=title,
            body=body,
            tenant_id=tenant_id,
            sub_tenant_id=sub_tenant_id,
            metadata=metadata or {},
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
    confidence: str = "accepted",
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
    return result


def bootstrap_project_context(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    events_path: Path = DEFAULT_EVENTS_PATH,
    repo_root: Path = ROOT,
    tenant_id: str = DEFAULT_TENANT_ID,
    seed: bool = True,
    query: str = "open risk",
    metadata_filter: dict[str, Any] | None = None,
    max_depth: int = 1,
    max_context_nodes: int = 8,
    max_context_edges: int = 8,
    include_repo_files: bool = True,
    max_repo_files: int = DEFAULT_REPO_INDEX_MAX_FILES,
    max_repo_file_bytes: int = DEFAULT_REPO_INDEX_MAX_FILE_BYTES,
    max_repo_body_chars: int = DEFAULT_REPO_INDEX_BODY_CHARS,
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
                "command": 'npm run agent:control -- graph query "open risk" --metadata source_type=gateboard_blocker --max-depth 1 --context --json',
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
                "command": 'npm run agent:control -- graph query "agent control" --metadata source_type=repo_file_index --max-depth 0 --context --json',
            },
            {
                "purpose": "script owner discovery",
                "command": 'npm run agent:control -- graph query "checkpoint" --metadata source_type=repo_file_index --metadata category=scripts --max-depth 0 --context --json',
            },
        ],
    }
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
) -> dict[str, Any]:
    query = query.strip()
    if kind is not None:
        _validate_choice(kind, GRAPH_NODE_KINDS, "kind")
    if memory_type is not None:
        _validate_choice(memory_type, OPERATING_MEMORY_TYPES, "memory_type")
    with closing(connect(db_path)) as conn, conn:
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
        for row in rows:
            node = _row_dict(row)
            if node is None:
                continue
            metadata = node.get("metadata", {})
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
                "nodes": sorted(node_map.values(), key=lambda item: item["id"]),
                "edges": sorted(edge_map.values(), key=lambda item: item["id"]),
                "triplets": sorted(triplets, key=lambda item: (item["source"], item["relation"], item["target"])),
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
        }
    repo_query = goal or "agent control checkpoint bootstrap"
    repo_context = query_graph(
        db_path=db_path,
        query=repo_query,
        tenant_id=tenant_id,
        metadata_filter={"source_type": "repo_file_index"},
        limit=limit,
        max_depth=0,
    )
    result["relevant_repo_files"] = repo_context["graph_context"]["nodes"][:limit]
    result["recommended_commands"] = [
        "npm run agent:control -- bootstrap --prompt-only",
        f'npm run agent:control -- context pack --goal "{goal or repo_query}" --prompt-only',
        "npm run agent:control -- memory audit --prompt-only",
        "npm run verify:memory",
    ]
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
    issue_count = len(stale_or_expired) + len(supersession_inconsistencies)
    result = {
        "status": "pass" if issue_count == 0 else "issues",
        "checked_memories": checked_memories,
        "stale_or_expired": stale_or_expired[:limit],
        "supersession_inconsistencies": supersession_inconsistencies[:limit],
        "open_questions": open_questions[:limit],
        "open_blockers": open_blockers[:limit],
    }
    return result


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
    )
    context_pack = build_context_pack(
        db_path=db_path,
        goal="agent control",
        tenant_id=tenant_id,
        limit=5,
        include_prompt_context=True,
    )
    audit = memory_audit(db_path=db_path, tenant_id=tenant_id)
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
    ]
    return {
        "status": "pass" if all(check["pass"] for check in checks) else "fail",
        "seed": seed_result,
        "checks": checks,
        "audit": audit,
    }


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
    parser = argparse.ArgumentParser(description="Local CEO/worker runtime memory graph control plane.")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
    bootstrap.add_argument("--query", default="open risk")
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
    context_pack.add_argument("--prompt-only", action="store_true")
    context_pack.set_defaults(func=_cmd_context_pack)

    memory = subparsers.add_parser("memory", help="Remember, supersede, audit, and evaluate operating memory.")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_remember = memory_sub.add_parser("remember", help="Store typed operating memory.")
    _add_common(memory_remember)
    memory_remember.add_argument("--type", required=True, choices=sorted(OPERATING_MEMORY_TYPES))
    memory_remember.add_argument("--title", required=True)
    memory_remember.add_argument("--body", default="")
    memory_remember.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_remember.add_argument("--sub-tenant-id")
    memory_remember.add_argument("--status", default="active", choices=sorted(MEMORY_STATUSES))
    memory_remember.add_argument("--confidence", default="accepted", choices=sorted(MEMORY_CONFIDENCE))
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

    memory_eval_parser = memory_sub.add_parser("eval", help="Run deterministic memory recovery checks.")
    _add_common(memory_eval_parser)
    memory_eval_parser.add_argument("--repo-root", type=Path, default=ROOT)
    memory_eval_parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    memory_eval_parser.add_argument("--skip-seed", action="store_true")
    memory_eval_parser.add_argument("--require-checkpoint", action="store_true")
    memory_eval_parser.add_argument("--prompt-only", action="store_true")
    memory_eval_parser.set_defaults(func=_cmd_memory_eval)

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
    )
    if args.prompt_only:
        print(result["prompt_context"])
        return 0
    _emit(result, as_json=True if args.json else False)
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
