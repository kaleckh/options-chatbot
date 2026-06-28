from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_preregistered_playbook_readiness_selector"

DEFAULT_GOAL_LOOP = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-preregistered-playbook-readiness-selector"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-preregistered-playbook-readiness-selector.md"

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "lane_implementation_performed": False,
    "historical_replay_performed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_implement_scanner_or_playbook_logic",
    "do_not_run_historical_replay",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_use_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
)

PLAYBOOKS = (
    {
        "key": "momentum_continuation_debit_spread",
        "concept_id": "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1",
        "label": "Breadth-confirmed index/QQQ momentum continuation debit spread",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-momentum-continuation-playbook" / "latest.json",
        "expected_structure": "defined_risk_call_debit_spreads_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-bounded-replay" / "latest.json",
        "complexity_score": 1,
        "engine_notes": [
            "defined-risk call debit spread",
            "simpler two-leg debit-spread pricing than credit spreads, calendars, condors, ratio/backspreads, pairs, or PMCC diagonals",
            "Oracle default top candidate unless a concrete artifact blocker is found",
        ],
    },
    {
        "key": "vrp_put_credit_spread",
        "concept_id": "low_mid_vix_index_put_credit_spread_vrp_v1",
        "label": "Low/mid VIX index put credit spread VRP",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-vrp-credit-spread-playbook" / "latest.json",
        "expected_structure": "defined_risk_put_credit_spreads_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-vrp-credit-spread-bounded-replay" / "latest.json",
        "complexity_score": 4,
        "engine_notes": ["credit-spread side-aware pricing", "assignment/expiration", "margin/max-loss convention"],
    },
    {
        "key": "term_structure_calendar_diagonal",
        "concept_id": "low_mid_vix_index_calendar_term_structure_dislocation_v1",
        "label": "Low/mid VIX index calendar or diagonal term-structure dislocation",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-term-structure-calendar-playbook" / "latest.json",
        "expected_structure": "defined_risk_calendar_or_diagonal_debit_spreads_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-term-structure-calendar-bounded-replay" / "latest.json",
        "complexity_score": 5,
        "engine_notes": ["multi-expiry pricing", "front-leg roll/expiry", "strict-new dedupe"],
    },
    {
        "key": "skew_broken_wing_put_fly",
        "concept_id": "low_mid_vix_index_skew_broken_wing_put_fly_v1",
        "label": "Low/mid VIX index skew broken-wing put butterfly",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-skew-broken-wing-playbook" / "latest.json",
        "expected_structure": "defined_risk_broken_wing_put_butterflies_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-skew-broken-wing-bounded-replay" / "latest.json",
        "complexity_score": 6,
        "engine_notes": ["three-leg/four-leg pricing", "skew inputs", "max-loss convention"],
    },
    {
        "key": "macro_event_long_strangle",
        "concept_id": "low_mid_vix_macro_event_long_strangle_v1",
        "label": "Low/mid VIX macro-event long straddle/strangle",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-macro-event-long-strangle-playbook" / "latest.json",
        "expected_structure": "defined_risk_long_straddles_or_strangles_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-macro-event-long-strangle-replay-readiness" / "latest.json",
        "complexity_score": 5,
        "engine_notes": ["event calendar dependency", "two-leg long premium pricing", "event-window leakage guard"],
    },
    {
        "key": "post_event_iv_crush_iron_condor",
        "concept_id": "post_event_iv_crush_index_iron_condor_v1",
        "label": "Post-event IV-crush index iron condor or iron butterfly",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-post-event-iv-crush-iron-condor-playbook" / "latest.json",
        "expected_structure": "defined_risk_short_iron_condors_or_iron_butterflies_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-post-event-iv-crush-replay-readiness" / "latest.json",
        "complexity_score": 7,
        "engine_notes": ["four-leg credit pricing", "event calendar dependency", "margin/max-loss and assignment/expiration"],
    },
    {
        "key": "flow_extreme_ratio_backspread",
        "concept_id": "index_flow_extreme_mean_reversion_ratio_backspread_v1",
        "label": "Index flow-extreme mean-reversion ratio/backspread",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-flow-extreme-ratio-backspread-playbook" / "latest.json",
        "expected_structure": "defined_risk_ratio_spreads_or_backspreads_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-ratio-backspread-replay-readiness" / "latest.json",
        "complexity_score": 8,
        "engine_notes": ["ratio/backspread pricing", "undefined-risk rejection", "flow input dependency"],
    },
    {
        "key": "dispersion_proxy_hybrid",
        "concept_id": "index_constituent_dispersion_proxy_defined_risk_hybrid_v1",
        "label": "Index constituent dispersion-proxy debit/credit hybrid",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-dispersion-proxy-hybrid-playbook" / "latest.json",
        "expected_structure": "defined_risk_index_constituent_debit_credit_hybrid_pairs_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness" / "latest.json",
        "complexity_score": 9,
        "engine_notes": ["paired index/constituent legs", "pair denominator mapping", "source-quality scope for constituents"],
    },
    {
        "key": "pmcc_diagonal_income",
        "concept_id": "low_mid_vix_index_pmcc_diagonal_income_v1",
        "label": "Low/mid VIX index PMCC-style diagonal income",
        "path": ROOT / "data" / "profitability-lab" / "regular-options-preregistered-pmcc-diagonal-playbook" / "latest.json",
        "expected_structure": "defined_risk_pmcc_style_call_diagonals_only",
        "readiness_path": ROOT / "data" / "profitability-lab" / "regular-options-pmcc-diagonal-replay-readiness" / "latest.json",
        "complexity_score": 7,
        "engine_notes": ["long-dated/short-dated call diagonal", "roll ledger", "assignment/ex-dividend and max-loss convention"],
    },
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _artifact_valid(payload: dict[str, Any], spec: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    concept = _as_dict(payload.get("concept"))
    concept_id = payload.get("concept_id") or concept.get("concept_id")
    status = payload.get("status") or concept.get("status")
    structure = payload.get("structure") or concept.get("structure")
    if concept_id != spec["concept_id"]:
        reasons.append("unexpected_concept_id")
    if status != "preregistered_design_only":
        reasons.append("unexpected_status")
    if structure != spec["expected_structure"]:
        reasons.append("unexpected_structure")
    for key in ("accepted_profitability", "lane_implementation_performed", "scanner_policy_changed", "strategy_logic_changed"):
        if payload.get(key) is not False:
            reasons.append(f"{key}_not_false")
    return not reasons, reasons


def _readiness_blockers(readiness_payload: dict[str, Any], readiness_meta: dict[str, Any]) -> list[str]:
    if readiness_meta["status"] != "loaded":
        return []
    blockers: list[str] = []
    for key in ("blockers", "remaining_blockers", "replay_gate_blockers"):
        blockers.extend(str(item) for item in _as_list(readiness_payload.get(key)) if item)
    return sorted(set(blockers))


def _classify_design(spec: dict[str, Any], payload: dict[str, Any], meta: dict[str, Any], readiness_payload: dict[str, Any], readiness_meta: dict[str, Any]) -> dict[str, Any]:
    valid, validation_reasons = _artifact_valid(payload, spec) if meta["status"] == "loaded" else (False, ["missing_preregistered_design_artifact"])
    concept = _as_dict(payload.get("concept"))
    readiness_blockers = _readiness_blockers(readiness_payload, readiness_meta)
    if not valid:
        readiness_status = "requires_readiness_audit_before_approval"
        blockers = validation_reasons
    elif readiness_blockers:
        readiness_status = "blocked_by_known_readiness_audit"
        blockers = readiness_blockers
    elif spec["key"] == "momentum_continuation_debit_spread":
        readiness_status = "candidate_for_research_only_implementation_approval"
        blockers = []
    elif readiness_meta["status"] == "loaded" and not readiness_blockers:
        readiness_status = "candidate_for_research_only_implementation_approval"
        blockers = []
    else:
        readiness_status = "requires_readiness_audit_before_approval"
        blockers = ["no_structure_specific_readiness_audit_yet"]

    return {
        "key": spec["key"],
        "concept_id": spec["concept_id"],
        "label": spec["label"],
        "structure": payload.get("structure") or concept.get("structure") if payload else spec["expected_structure"],
        "artifact_status": meta["status"],
        "artifact_path": meta["path"],
        "validation_valid": valid,
        "validation_reasons": validation_reasons,
        "readiness_status": readiness_status,
        "readiness_artifact_status": readiness_meta["status"] if readiness_meta else "not_configured",
        "readiness_artifact_path": readiness_meta.get("path") if readiness_meta else None,
        "blockers": blockers,
        "complexity_score": spec["complexity_score"],
        "engine_notes": list(spec["engine_notes"]),
        "accepted_profitability": payload.get("accepted_profitability") if payload else None,
        "historical_replay_performed": payload.get("historical_replay_performed") if payload else None,
        "lane_implementation_performed": payload.get("lane_implementation_performed") if payload else None,
    }


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {
        "candidate_for_research_only_implementation_approval": 0,
        "requires_readiness_audit_before_approval": 1,
        "requires_engine_prerequisites_before_replay": 2,
        "blocked_by_known_readiness_audit": 3,
        "duplicate_or_lower_priority": 4,
    }
    return sorted(rows, key=lambda row: (status_rank.get(str(row.get("readiness_status")), 99), int(row["complexity_score"]), str(row["key"])))


def _research_only_task_boundary(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    return (
        "GPT-5.5 Pro may select one bounded research-only implementation/replay task for "
        f"`{row['concept_id']}` only, writing derived research artifacts only, with no live validation, "
        "no auto-track, no broker orders, no quote import, no evidence-store mutation, no protected-holdout "
        "consumption, no scanner release, no stop/sizing/proof-bar changes, and no promotion."
    )


def _goal_state(goal_payload: dict[str, Any], goal_meta: dict[str, Any]) -> dict[str, Any]:
    accounting = _as_dict(goal_payload.get("forward_evidence_accounting"))
    return {
        "artifact_status": goal_meta["status"],
        "current_decision_state": goal_payload.get("current_decision_state"),
        "post_freeze_strict_exact_completed_rows": accounting.get("post_freeze_strict_exact_completed_rows"),
        "minimum_required": accounting.get("minimum_required"),
        "cohort_log_status": accounting.get("cohort_log_status"),
        "strict_usd_pf_lower_bound_5pct": accounting.get("strict_usd_pf_lower_bound_5pct"),
        "live_entry_allowed": accounting.get("live_entry_allowed"),
        "auto_track_allowed": accounting.get("auto_track_allowed"),
        "broker_order_allowed": accounting.get("broker_order_allowed"),
        "promotion_ready": accounting.get("promotion_ready"),
    }


def build_report(*, goal_loop_path: Path = DEFAULT_GOAL_LOOP, generated_at_utc: str | None = None) -> dict[str, Any]:
    goal_payload, goal_meta = _load_json(goal_loop_path, required=False)
    source_artifacts: dict[str, Any] = {"goal_loop": goal_meta}
    rows: list[dict[str, Any]] = []
    for spec in PLAYBOOKS:
        payload, meta = _load_json(spec["path"], required=True)
        readiness_payload: dict[str, Any] = {}
        readiness_meta: dict[str, Any] = {"status": "not_configured", "path": None, "required": False, "exists": False, "error": None}
        if spec.get("readiness_path"):
            readiness_payload, readiness_meta = _load_json(spec["readiness_path"], required=False)
        source_artifacts[spec["key"]] = {"playbook": meta, "readiness": readiness_meta}
        rows.append(_classify_design(spec, payload, meta, readiness_payload, readiness_meta))

    ranked = _rank_rows(rows)
    candidate = next((row for row in ranked if row["readiness_status"] == "candidate_for_research_only_implementation_approval"), None)
    missing = [row["key"] for row in rows if row["artifact_status"] != "loaded"]
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": "candidate_selected_for_research_only_implementation_approval" if candidate else "no_research_implementation_candidate_ready_without_blocker",
        **READ_ONLY_FLAGS,
        "scope": "read_only_preregistered_playbook_implementation_readiness_selector",
        "goal_state": _goal_state(goal_payload, goal_meta),
        "design_inventory": rows,
        "ranked_designs": ranked,
        "top_ranked_candidate": candidate,
        "recommended_operator_approval_question": None,
        "recommended_research_only_task_boundary": _research_only_task_boundary(candidate),
        "missing_preregistered_designs": missing,
        "allowed_next_step": (
            "Return this selector to GPT-5.5 Pro. Do not ask an operator approval question for bounded read-only/research-only work already covered by the Oracle packet posture; instead ask GPT-5.5 Pro for the next concrete Codex task inside the research-only task boundary."
            if candidate
            else "Return this selector to GPT-5.5 Pro to decide whether to ask for approval-gated source repair/forward collection or earn a stop_exception."
        ),
        "source_artifacts": source_artifacts,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    rows = _as_list(report.get("design_inventory"))
    if len(rows) != len(PLAYBOOKS):
        raise ValueError("selector did not inventory every configured playbook")
    ids = {row.get("concept_id") for row in rows}
    expected_ids = {spec["concept_id"] for spec in PLAYBOOKS}
    if ids != expected_ids:
        raise ValueError("selector inventory concept mismatch")
    pmcc = next(row for row in rows if row["key"] == "pmcc_diagonal_income")
    if pmcc["artifact_status"] == "loaded" and pmcc["accepted_profitability"] is not False:
        raise ValueError("PMCC artifact must remain design-only and not profitable")
    vrp = next(row for row in rows if row["key"] == "vrp_put_credit_spread")
    term = next(row for row in rows if row["key"] == "term_structure_calendar_diagonal")
    if vrp["readiness_artifact_status"] == "loaded" and vrp["readiness_status"] != "blocked_by_known_readiness_audit":
        raise ValueError("VRP must preserve known readiness blockers")
    if term["readiness_artifact_status"] == "loaded" and term["readiness_status"] != "blocked_by_known_readiness_audit":
        raise ValueError("term-structure must preserve known readiness blockers")
    boundary = report.get("recommended_research_only_task_boundary")
    if boundary is not None:
        if str(boundary).count("`") < 2:
            raise ValueError("research-only task boundary must name exactly one concept")
        if "no live validation" not in str(boundary) or "no broker orders" not in str(boundary):
            raise ValueError("research-only task boundary must preserve live/broker prohibitions")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Preregistered Playbook Readiness Selector",
        "",
        "This report is generated from `scripts/build_regular_options_preregistered_playbook_readiness_selector.py`. It is a read-only selector across completed preregistered design artifacts. It does not implement scanner or playbook logic, run replay, import quotes, mutate evidence stores, consume protected holdout, enable live validation or auto-track, submit broker orders, change stops/sizing/proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Lane implementation performed: `{_fmt_bool(report['lane_implementation_performed'])}`.",
        f"- Forward strict completed rows: `{report['goal_state'].get('post_freeze_strict_exact_completed_rows')}` / `{report['goal_state'].get('minimum_required')}`.",
        f"- Cohort log status: `{report['goal_state'].get('cohort_log_status')}`.",
        "",
    ]
    candidate = _as_dict(report.get("top_ranked_candidate"))
    if candidate:
        lines.extend(
            [
                "## Selected Candidate",
                "",
                f"- Concept: `{candidate['concept_id']}`.",
                f"- Status: `{candidate['readiness_status']}`.",
                f"- Rationale: `{candidate['label']}` is the lowest-complexity valid preregistered design and uses the simplest defined-risk spread proof path.",
                "",
                "## Recommended Research-Only Task Boundary",
                "",
                str(report.get("recommended_research_only_task_boundary")),
                "",
            ]
        )
    else:
        lines.extend(["## Selected Candidate", "", "No research-only implementation candidate is ready without a named blocker.", ""])

    lines.extend(
        [
            "## Inventory",
            "",
            "| Rank | Concept | Structure | Readiness | Blockers |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for index, row in enumerate(_as_list(report.get("ranked_designs")), start=1):
        row = _as_dict(row)
        blockers = ", ".join(f"`{item}`" for item in _as_list(row.get("blockers"))) or "-"
        lines.append(
            f"| {index} | `{row.get('concept_id')}` | `{row.get('structure')}` | `{row.get('readiness_status')}` | {blockers} |"
        )

    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only preregistered playbook readiness selector.")
    parser.add_argument("--goal-loop", type=Path, default=DEFAULT_GOAL_LOOP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(goal_loop_path=args.goal_loop)
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["status"] in {"candidate_selected_for_research_only_implementation_approval", "no_research_implementation_candidate_ready_without_blocker"} else 1


if __name__ == "__main__":
    sys.exit(main())
