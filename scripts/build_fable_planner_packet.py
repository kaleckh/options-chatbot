from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "fable_planner_packet"

DEFAULT_PROJECT_CONTEXT = ROOT / "docs" / "PROJECT_CONTEXT.md"
DEFAULT_DECISIONS = ROOT / "docs" / "DECISIONS.md"
DEFAULT_NEXT_STEPS = ROOT / "docs" / "NEXT_STEPS.md"
DEFAULT_AGENT_CONTROL = ROOT / "docs" / "agent-control-plane.md"
DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_ORACLE_PACKET = ROOT / "data" / "forward-tracking" / "options_oracle_profit_loop_packet_latest.json"
DEFAULT_OUTPUT_JSON = ROOT / "data" / "agent-control" / "fable" / "planner_packet_latest.json"
DEFAULT_OUTPUT_MD = ROOT / "data" / "agent-control" / "fable" / "planner_packet_latest.md"
DEFAULT_NORMALIZED_PLAN_JSON = ROOT / "data" / "agent-control" / "fable" / "validated_plan_latest.json"
DEFAULT_NORMALIZED_PLAN_MD = ROOT / "data" / "agent-control" / "fable" / "validated_plan_latest.md"

PROHIBITED_AUTHORITY_PATTERNS = [
    r"\bauthori[sz]e[s]?\s+(live|broker|trade|trading|order|orders|append|promotion|promote|proof)",
    r"\bapproved?\s+(live|broker|trade|trading|order|orders|append|promotion|promote|proof)",
    r"\bsubmit\s+(broker\s+)?orders?\b",
    r"\bplace\s+(live\s+)?orders?\b",
    r"\benable\s+(live validation|auto[- ]?track|broker)\b",
    r"\blower\s+proof[- ]?bars?\b",
    r"\bconsume\s+protected[- ]?holdout\b",
    r"\bpromote\s+(lane|strategy|to live|to production)\b",
]

REQUIRED_PLAN_KEYS = [
    "planner",
    "verdict",
    "selected_task",
    "branch_statuses",
    "assumption_challenges",
    "operator_questions",
    "non_authorization_statement",
]

REQUIRED_TASK_KEYS = [
    "title",
    "objective",
    "why_now",
    "scope",
    "non_goals",
    "files_to_read",
    "files_to_change",
    "commands",
    "verification",
    "acceptance_criteria",
    "failure_criteria",
    "risks",
    "approval_required",
    "proof_boundary_statement",
]

PLAN_SCHEMA = {
    "planner": "fable",
    "verdict": "implement|ask_operator|blocked|decline",
    "selected_task": {
        "title": "string",
        "objective": "string",
        "why_now": "string",
        "scope": "string",
        "non_goals": ["string"],
        "files_to_read": ["repo-relative path"],
        "files_to_change": ["repo-relative path"],
        "commands": ["command"],
        "verification": ["command or check"],
        "acceptance_criteria": ["measurable criterion"],
        "failure_criteria": ["measurable stop condition"],
        "risks": ["risk"],
        "approval_required": [
            {
                "action": "string",
                "reason": "string",
                "safe_fallback": "string",
            }
        ],
        "proof_boundary_statement": "string",
    },
    "branch_statuses": [
        {
            "branch_id": "string",
            "status": "continue_now|approval_blocked|source_blocked|market_window_blocked|parked_until_state_change|falsified_under_current_data|exhausted_under_current_data",
            "reason": "string",
        }
    ],
    "assumption_challenges": [
        {
            "assumption": "string",
            "risk": "string",
            "verification": "string",
        }
    ],
    "operator_questions": [
        {
            "question": "string",
            "why_it_matters": "string",
            "default_if_unanswered": "string",
        }
    ],
    "non_authorization_statement": "This plan is orchestration context only and does not authorize trading, evidence mutation, scanner/proof-bar changes, broker action, promotion, live validation, stop/sizing changes, protected-holdout use, or treating historical rows as forward proof.",
}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _read_text(path: Path, max_chars: int) -> str:
    if not path.exists():
        return f"[missing: {_rel(path)}]"
    text = path.read_text(encoding="utf8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": _rel(path)}
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {"malformed": True, "path": _rel(path), "error": str(exc)}


def _compact_gateboard(gateboard: dict[str, Any]) -> dict[str, Any]:
    if gateboard.get("missing") or gateboard.get("malformed"):
        return gateboard
    return {
        "report_id": gateboard.get("report_id"),
        "status": gateboard.get("status") or gateboard.get("overall_status"),
        "generated_at": gateboard.get("generated_at"),
        "no_chase_reasons": gateboard.get("no_chase_reasons") or gateboard.get("blockers"),
        "pathways": gateboard.get("pathways") or gateboard.get("pathway_statuses"),
    }


def _compact_oracle_packet(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("missing") or packet.get("malformed"):
        return packet
    current = packet.get("current_evidence_summary") if isinstance(packet.get("current_evidence_summary"), dict) else {}
    return {
        "report_id": packet.get("report_id"),
        "status": packet.get("status"),
        "generated_at": packet.get("generated_at"),
        "profitability_target": packet.get("profitability_target"),
        "safety_flags": packet.get("safety_flags"),
        "continuation_branches": packet.get("continuation_branches"),
        "current_evidence_summary_keys": sorted(current.keys()),
        "artifacts": packet.get("artifacts"),
    }


def build_prompt(
    *,
    objective: str,
    gateboard_summary: dict[str, Any],
    oracle_summary: dict[str, Any],
    project_context_excerpt: str,
    decisions_excerpt: str,
    next_steps_excerpt: str,
    agent_control_excerpt: str,
) -> str:
    return f"""You are Claude Fable 5 acting as an external technical planner for this local repo.
Codex will implement only after reviewing your plan against the repo, tests, and fail-closed evidence rules.

Objective:
{objective}

Your output must be exactly one JSON object matching this schema:
{json.dumps(PLAN_SCHEMA, indent=2, sort_keys=True)}

Planning rules:
- Choose the smallest concrete technical plan that moves the objective.
- Prefer repo patterns and existing commands over new abstractions.
- Include exact files to read before implementation and exact files that may need edits.
- Include commands and acceptance/failure criteria that Codex can run locally.
- Challenge weak assumptions explicitly.
- If the task needs operator approval, market hours, provider credentials, external source files, quote import, source-row writes, cohort append, evidence mutation, live validation, auto-track, broker action, scanner/proof-bar changes, stop/sizing changes, protected-holdout use, or promotion, mark it `approval_blocked`, ask the exact operator question, and provide a safe read-only fallback.
- Do not treat historical rows, generated packets, memory, worker reports, or your own plan as forward proof.
- Do not authorize live trading, broker orders, evidence mutation, scanner policy changes, proof-bar changes, promotion, holdout use, or treating historical rows as forward proof. Your plan is advisory orchestration context only.

Current gateboard summary:
{json.dumps(gateboard_summary, indent=2, sort_keys=True)}

Current Oracle/GPT profitability packet summary, if available:
{json.dumps(oracle_summary, indent=2, sort_keys=True)}

Relevant PROJECT_CONTEXT excerpt:
{project_context_excerpt}

Relevant DECISIONS excerpt:
{decisions_excerpt}

Relevant NEXT_STEPS excerpt:
{next_steps_excerpt}

Relevant agent-control excerpt:
{agent_control_excerpt}
"""


def build_packet(
    *,
    objective: str,
    project_context: Path = DEFAULT_PROJECT_CONTEXT,
    decisions: Path = DEFAULT_DECISIONS,
    next_steps: Path = DEFAULT_NEXT_STEPS,
    agent_control: Path = DEFAULT_AGENT_CONTROL,
    gateboard: Path = DEFAULT_GATEBOARD,
    oracle_packet: Path = DEFAULT_ORACLE_PACKET,
    excerpt_chars: int = 12000,
) -> dict[str, Any]:
    gateboard_summary = _compact_gateboard(_read_json(gateboard))
    oracle_summary = _compact_oracle_packet(_read_json(oracle_packet))
    prompt = build_prompt(
        objective=objective,
        gateboard_summary=gateboard_summary,
        oracle_summary=oracle_summary,
        project_context_excerpt=_read_text(project_context, excerpt_chars),
        decisions_excerpt=_read_text(decisions, excerpt_chars),
        next_steps_excerpt=_read_text(next_steps, excerpt_chars),
        agent_control_excerpt=_read_text(agent_control, min(excerpt_chars, 8000)),
    )
    return {
        "report_id": REPORT_ID,
        "status": "ready_for_fable_planning",
        "generated_at": datetime.now(UTC).isoformat(),
        "objective": objective,
        "provider": {
            "name": "Claude Fable 5",
            "model_id": "claude-fable-5",
            "api_call_implemented": False,
            "handoff_mode": "manual_or_future_api",
        },
        "inputs": {
            "project_context": _rel(project_context),
            "decisions": _rel(decisions),
            "next_steps": _rel(next_steps),
            "agent_control": _rel(agent_control),
            "gateboard": _rel(gateboard),
            "oracle_packet": _rel(oracle_packet),
        },
        "plan_schema": PLAN_SCHEMA,
        "prompt": prompt,
    }


def render_packet_markdown(packet: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Fable Planner Packet",
            "",
            "This artifact is a manual/API-neutral handoff for Claude Fable 5 to produce technical plans for Codex review and implementation.",
            "",
            "## Status",
            "",
            f"- Status: `{packet.get('status')}`.",
            f"- Objective: {packet.get('objective')}",
            f"- Provider model ID: `{packet.get('provider', {}).get('model_id')}`.",
            f"- API call implemented: `{packet.get('provider', {}).get('api_call_implemented')}`.",
            "",
            "## Prompt",
            "",
            "```text",
            str(packet.get("prompt", "")),
            "```",
            "",
        ]
    )


def write_packet(packet: dict[str, Any], *, output_json: Path, output_md: Path) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {"json": _rel(output_json), "markdown": _rel(output_md)}
    packet_with_artifacts = dict(packet)
    packet_with_artifacts["artifacts"] = artifacts
    output_json.write_text(json.dumps(packet_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    output_md.write_text(render_packet_markdown(packet_with_artifacts), encoding="utf8")
    packet["artifacts"] = artifacts
    return artifacts


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _contains_prohibited_authority(value: Any) -> list[str]:
    text = _stringify(value).lower()
    matches = []
    for pattern in PROHIBITED_AUTHORITY_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 32) : match.start()]
            if "does not " in prefix or "do not " in prefix or "not " in prefix:
                continue
            matches.append(pattern)
            break
    return matches


def validate_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for key in REQUIRED_PLAN_KEYS:
        if key not in plan:
            errors.append(f"missing top-level key: {key}")
    task = plan.get("selected_task")
    if not isinstance(task, dict):
        errors.append("selected_task must be an object")
        task = {}
    for key in REQUIRED_TASK_KEYS:
        if key not in task:
            errors.append(f"missing selected_task key: {key}")
    verdict = plan.get("verdict")
    if verdict not in {"implement", "ask_operator", "blocked", "decline"}:
        errors.append("verdict must be one of implement, ask_operator, blocked, decline")
    if str(plan.get("planner", "")).lower() not in {"fable", "claude fable 5", "claude-fable-5"}:
        errors.append("planner must identify Fable")
    for list_key in ["branch_statuses", "assumption_challenges", "operator_questions"]:
        if not isinstance(plan.get(list_key), list):
            errors.append(f"{list_key} must be a list")
    approval_required = task.get("approval_required", [])
    if not isinstance(approval_required, list):
        errors.append("selected_task.approval_required must be a list")
    prohibited_matches = _contains_prohibited_authority(plan)
    if prohibited_matches:
        errors.append(
            "plan contains prohibited authority-shaped wording; convert it to approval_required plus safe fallback: "
            + ", ".join(prohibited_matches)
        )
    statement = str(plan.get("non_authorization_statement", "")).lower()
    if "does not authorize" not in statement:
        errors.append("non_authorization_statement must explicitly say the plan does not authorize high-risk actions")
    return not errors, errors


def render_plan_markdown(plan: dict[str, Any]) -> str:
    task = plan.get("selected_task") if isinstance(plan.get("selected_task"), dict) else {}
    lines = [
        "# Validated Fable Plan",
        "",
        f"- Verdict: `{plan.get('verdict')}`",
        f"- Task: {task.get('title', '')}",
        f"- Objective: {task.get('objective', '')}",
        "",
        "## Commands",
        "",
    ]
    for command in task.get("commands", []) if isinstance(task.get("commands"), list) else []:
        lines.append(f"- `{command}`")
    lines.extend(["", "## Verification", ""])
    for check in task.get("verification", []) if isinstance(task.get("verification"), list) else []:
        lines.append(f"- `{check}`")
    lines.extend(["", "## Boundary", "", str(task.get("proof_boundary_statement", "")), ""])
    return "\n".join(lines)


def write_validated_plan(plan: dict[str, Any], *, output_json: Path, output_md: Path) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(plan)
    payload["validated_at"] = datetime.now(UTC).isoformat()
    payload["validation_status"] = "valid_fable_plan"
    artifacts = {"json": _rel(output_json), "markdown": _rel(output_md)}
    payload["artifacts"] = artifacts
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    output_md.write_text(render_plan_markdown(payload), encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or validate a Claude Fable 5 planner packet.")
    parser.add_argument("--objective", default="Plan the next technical work for options-chatbot.")
    parser.add_argument("--project-context", type=Path, default=DEFAULT_PROJECT_CONTEXT)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--next-steps", type=Path, default=DEFAULT_NEXT_STEPS)
    parser.add_argument("--agent-control", type=Path, default=DEFAULT_AGENT_CONTROL)
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--oracle-packet", type=Path, default=DEFAULT_ORACLE_PACKET)
    parser.add_argument("--excerpt-chars", type=int, default=12000)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--validate-plan", type=Path)
    parser.add_argument("--write-normalized-plan", action="store_true")
    parser.add_argument("--normalized-plan-json", type=Path, default=DEFAULT_NORMALIZED_PLAN_JSON)
    parser.add_argument("--normalized-plan-md", type=Path, default=DEFAULT_NORMALIZED_PLAN_MD)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    if args.validate_plan:
        plan = _read_json(args.validate_plan)
        ok, errors = validate_plan(plan)
        result: dict[str, Any] = {
            "status": "valid_fable_plan" if ok else "invalid_fable_plan",
            "plan_path": _rel(args.validate_plan),
            "errors": errors,
        }
        if ok and args.write_normalized_plan:
            result["artifacts"] = write_validated_plan(
                plan,
                output_json=args.normalized_plan_json,
                output_md=args.normalized_plan_md,
            )
        print(json.dumps(result, indent=2, sort_keys=True) if args.json_output else result["status"])
        return 0 if ok else 1

    packet = build_packet(
        objective=args.objective,
        project_context=args.project_context,
        decisions=args.decisions,
        next_steps=args.next_steps,
        agent_control=args.agent_control,
        gateboard=args.gateboard,
        oracle_packet=args.oracle_packet,
        excerpt_chars=args.excerpt_chars,
    )
    if not args.no_write:
        write_packet(packet, output_json=args.output_json, output_md=args.output_md)
    if args.json_output:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(packet["status"])
        print(packet["prompt"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
