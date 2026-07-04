from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_phase2_regular_options_forward_paper_shadow_candidate_rows as stager  # noqa: E402
from scripts import build_regular_options_forward_candidate_throughput_audit as throughput  # noqa: E402


REPORT_ID = "regular_options_phase2_drop_decomposition"
DEFAULT_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
DEFAULT_THROUGHPUT_LATEST = ROOT / "data" / "forward-tracking" / "regular_options_forward_candidate_throughput_audit_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking" / "regular-options-phase2-drop-decomposition"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-phase2-drop-decomposition.md"
MAX_INPUT_AGE_DAYS = 5

STATUS_VOCABULARY = {
    "phase2_drop_decomposition_ready",
    "phase2_drop_decomposition_waiting_for_symbol_drop_reasons",
    "blocked_missing_or_stale_inputs",
}

FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "forward_rows_are_profitability_proof": False,
    "promotion_ready": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "cohort_append_performed": False,
}


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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_json", "error": str(exc)}
    if not isinstance(payload, dict):
        return {}, {"path": _rel(path), "exists": True, "status": "invalid_payload"}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded"}


def _parse_datetime(value: Any) -> datetime | None:
    text = _norm(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _input_age_days(input_generated_at: Any, reference: datetime) -> int | None:
    parsed = _parse_datetime(input_generated_at)
    if parsed is None:
        return None
    return max((reference.date() - parsed.date()).days, 0)


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _top_counter(counter: Counter[str], *, limit: int = 20) -> list[dict[str, Any]]:
    total = sum(counter.values())
    return [
        {"key": key, "count": count, "pct": round(count / total, 6) if total else 0.0}
        for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * float(fraction)))))
    return round(ordered[index], 6)


def _selection_date_from_session(session: dict[str, Any]) -> str:
    run_id = _norm(session.get("run_id"))
    parts = run_id.split(":")
    if len(parts) > 1 and parts[1]:
        return parts[1]
    return _norm(session.get("recorded_at_utc"))[:10]


def _drop_reason_text(details: dict[str, Any]) -> str:
    return (
        _norm(details.get("reason"))
        or _norm(details.get("no_fill_reason"))
        or _norm(details.get("candidate_execution_label"))
        or "unknown"
    )


def _rows_for_session(session: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], int, int]:
    playbook = _norm(session.get("playbook"))
    selection_date = _selection_date_from_session(session)
    month = selection_date[:7]
    notes = throughput._parse_json_dict(session.get("notes_json"))
    scan_funnel = _as_dict(notes.get("scan_funnel"))
    symbol_diagnostics = _as_dict(notes.get("symbol_diagnostics"))
    scan_drop_reasons = _as_dict(symbol_diagnostics.get("scan_drop_reasons") or notes.get("scan_drop_reasons"))
    aggregate_drop_counts = {
        str(key): _safe_int(value)
        for key, value in _as_dict(scan_funnel.get("drop_counts")).items()
        if _safe_int(value) > 0
    }
    raw_candidates = _safe_int(_first_present(scan_funnel.get("raw_candidates"), notes.get("candidate_count")))
    returned_picks = _safe_int(_first_present(scan_funnel.get("returned_picks"), notes.get("returned_count")))
    rows: list[dict[str, Any]] = []
    for symbol, reason in sorted(scan_drop_reasons.items(), key=lambda item: str(item[0]).upper()):
        reason_payload = _as_dict(reason)
        details = _as_dict(reason_payload.get("details"))
        drop_key = _norm(reason_payload.get("drop_key")) or "unknown"
        components = throughput._threshold_distance_components(details)
        distance = round(sum(components.values()), 6) if components else None
        rows.append(
            {
                "selection_date": selection_date,
                "month": month,
                "session_id": session.get("id"),
                "recorded_at_utc": session.get("recorded_at_utc"),
                "playbook": playbook,
                "symbol": str(symbol or "").strip().upper(),
                "drop_key": drop_key,
                "reason": _drop_reason_text(details),
                "gate_category": throughput._drop_gate_category(drop_key, details),
                "candidate_execution_label": _norm(details.get("candidate_execution_label")),
                "distance_to_pass": distance,
                "distance_components": components,
                "research_only": True,
                "non_promotable": True,
            }
        )
    return rows, aggregate_drop_counts, raw_candidates, returned_picks


def _grouped_counts(rows: Sequence[dict[str, Any]], key: str) -> dict[str, int]:
    return _counter_dict(Counter(_norm(row.get(key)) or "unknown" for row in rows))


def _monthly_breakdown(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_month[_norm(row.get("month")) or "unknown"].append(row)
    return [
        {
            "month": month,
            "symbol_drop_reason_rows": len(month_rows),
            "drop_key_counts": _grouped_counts(month_rows, "drop_key"),
            "gate_category_counts": _grouped_counts(month_rows, "gate_category"),
            "playbook_counts": _grouped_counts(month_rows, "playbook"),
        }
        for month, month_rows in sorted(by_month.items())
    ]


def _combined_breakdown(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str, str, str, str]] = Counter()
    for row in rows:
        counter[
            (
                _norm(row.get("month")) or "unknown",
                _norm(row.get("symbol")) or "unknown",
                _norm(row.get("drop_key")) or "unknown",
                _norm(row.get("reason")) or "unknown",
                _norm(row.get("playbook")) or "unknown",
                _norm(row.get("gate_category")) or "unknown",
            )
        ] += 1
    return [
        {
            "month": month,
            "symbol": symbol,
            "drop_key": drop_key,
            "reason": reason,
            "playbook": playbook,
            "gate_category": gate_category,
            "count": count,
        }
        for (month, symbol, drop_key, reason, playbook, gate_category), count in sorted(
            counter.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _distance_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values = [value for row in rows if (value := _safe_float(row.get("distance_to_pass"))) is not None]
    return {
        "distance_available_count": len(values),
        "min_distance_to_pass": min(values) if values else None,
        "median_distance_to_pass": _percentile(values, 0.5),
        "p90_distance_to_pass": _percentile(values, 0.9),
    }


def _session_survival_by(session_summaries: Sequence[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"raw_candidates": 0, "returned_picks": 0, "aggregate_drops": 0, "session_count": 0, "drop_counts": Counter()}
    )
    for session in session_summaries:
        group_key = _norm(session.get(key)) or "unknown"
        bucket = grouped[group_key]
        bucket["session_count"] += 1
        bucket["raw_candidates"] += _safe_int(session.get("raw_candidates"))
        bucket["returned_picks"] += _safe_int(session.get("returned_picks"))
        for drop_key, count in _as_dict(session.get("aggregate_drop_counts")).items():
            parsed_count = _safe_int(count)
            bucket["aggregate_drops"] += parsed_count
            bucket["drop_counts"][str(drop_key)] += parsed_count
    rows: list[dict[str, Any]] = []
    for group_key, bucket in sorted(grouped.items()):
        denominator = _safe_int(bucket["aggregate_drops"]) + _safe_int(bucket["returned_picks"])
        rows.append(
            {
                key: group_key,
                "session_count": bucket["session_count"],
                "raw_candidates": bucket["raw_candidates"],
                "returned_picks": bucket["returned_picks"],
                "aggregate_drops": bucket["aggregate_drops"],
                "recorded_drop_denominator": denominator,
                "returned_pick_rate_over_recorded_drops": round(bucket["returned_picks"] / denominator, 6)
                if denominator
                else None,
                "drop_counts": _counter_dict(bucket["drop_counts"]),
            }
        )
    return rows


def _drop_share_rows(rows: Sequence[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter = Counter(_norm(row.get(key)) or "unknown" for row in rows)
    total = sum(counter.values())
    return [
        {key: value, "symbol_drop_reason_rows": count, "pct_of_symbol_drop_reasons": round(count / total, 6) if total else 0.0}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_report(
    *,
    ledger_db_path: Path = DEFAULT_LEDGER_DB,
    throughput_latest_path: Path = DEFAULT_THROUGHPUT_LATEST,
    selection_date: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    reference = _parse_datetime(generated_at) or datetime.now(UTC)
    throughput_latest, throughput_meta = _load_json(throughput_latest_path)
    target_date = selection_date or _norm(throughput_latest.get("target_selection_date")) or throughput._default_selection_date(generated_at)
    blockers: list[str] = []
    if throughput_meta.get("status") != "loaded":
        blockers.append("throughput_latest_not_loaded")
    else:
        age_days = _input_age_days(throughput_latest.get("generated_at_utc"), reference)
        throughput_meta["age_days"] = age_days
        if age_days is None:
            blockers.append("throughput_latest_missing_generated_at_utc")
        elif age_days > MAX_INPUT_AGE_DAYS:
            blockers.append("throughput_latest_stale_generated_at_utc")
    sessions, session_error = throughput._load_scheduled_scan_sessions(
        ledger_db_path=ledger_db_path,
        selection_date=target_date,
        playbooks=list(stager.ALLOWED_LANES),
    )
    ledger_meta = {
        "path": _rel(ledger_db_path),
        "exists": ledger_db_path.exists(),
        "status": "loaded" if ledger_db_path.exists() and session_error is None else session_error or "missing",
    }
    if session_error:
        blockers.append("scheduled_scan_session_source_unavailable")

    rows: list[dict[str, Any]] = []
    aggregate_drop_counts: Counter[str] = Counter()
    raw_candidates = 0
    returned_picks = 0
    session_summaries: list[dict[str, Any]] = []
    for session in sessions:
        session_rows, session_drop_counts, session_raw_candidates, session_returned_picks = _rows_for_session(session)
        rows.extend(session_rows)
        raw_candidates += session_raw_candidates
        returned_picks += session_returned_picks
        for key, count in session_drop_counts.items():
            aggregate_drop_counts[key] += count
        session_summaries.append(
            {
                "session_id": session.get("id"),
                "playbook": _norm(session.get("playbook")),
                "recorded_at_utc": session.get("recorded_at_utc"),
                "selection_date": _selection_date_from_session(session),
                "month": _selection_date_from_session(session)[:7],
                "raw_candidates": session_raw_candidates,
                "returned_picks": session_returned_picks,
                "aggregate_drop_counts": session_drop_counts,
                "symbol_drop_reason_rows": len(session_rows),
            }
        )

    throughput_drop_total = _safe_int(throughput_latest.get("scheduled_phase2_drop_count_total"))
    throughput_symbol_reason_total = _safe_int(throughput_latest.get("scheduled_phase2_scan_drop_reason_count_total"))
    aggregate_drop_total = sum(aggregate_drop_counts.values())
    symbol_reason_total = len(rows)
    if throughput_meta.get("status") == "loaded":
        if throughput_drop_total != aggregate_drop_total:
            blockers.append("aggregate_drop_count_mismatch_with_throughput_latest")
        if throughput_symbol_reason_total != symbol_reason_total:
            blockers.append("symbol_drop_reason_count_mismatch_with_throughput_latest")

    if blockers:
        status = "blocked_missing_or_stale_inputs"
    elif not rows and aggregate_drop_total > 0:
        status = "phase2_drop_decomposition_waiting_for_symbol_drop_reasons"
    else:
        status = "phase2_drop_decomposition_ready"
    assert status in STATUS_VOCABULARY

    liquidity_rows = [
        row
        for row in rows
        if row.get("gate_category") == "liquidity_or_history"
        or row.get("drop_key") in {"option_liquidity", "history_or_liquidity"}
    ]
    drop_key_counts = Counter(_norm(row.get("drop_key")) or "unknown" for row in rows)
    reason_counts = Counter(_norm(row.get("reason")) or "unknown" for row in rows)
    symbol_counts = Counter(_norm(row.get("symbol")) or "unknown" for row in rows)
    playbook_counts = Counter(_norm(row.get("playbook")) or "unknown" for row in rows)
    gate_category_counts = Counter(_norm(row.get("gate_category")) or "unknown" for row in rows)
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "status": status,
        "status_vocabulary": sorted(STATUS_VOCABULARY),
        "scope": "read_only_scheduled_phase2_drop_decomposition",
        "read_only": True,
        "research_only": True,
        "target_selection_date": target_date,
        "inputs": {
            "ledger_db": ledger_meta,
            "throughput_latest": throughput_meta,
        },
        "blockers": blockers,
        "reconciliation": {
            "aggregate_drop_count_total": aggregate_drop_total,
            "throughput_latest_aggregate_drop_count_total": throughput_drop_total,
            "aggregate_drop_count_matches_throughput_latest": aggregate_drop_total == throughput_drop_total,
            "symbol_drop_reason_count_total": symbol_reason_total,
            "throughput_latest_symbol_drop_reason_count_total": throughput_symbol_reason_total,
            "symbol_drop_reason_count_matches_throughput_latest": symbol_reason_total == throughput_symbol_reason_total,
        },
        "scheduled_phase2_throughput": {
            "session_count": len(sessions),
            "raw_candidates": raw_candidates,
            "returned_picks": returned_picks,
            "returned_pick_rate": round(returned_picks / raw_candidates, 6) if raw_candidates else None,
            "recorded_drop_denominator": aggregate_drop_total + returned_picks,
            "returned_pick_rate_over_recorded_drops": round(returned_picks / (aggregate_drop_total + returned_picks), 6)
            if (aggregate_drop_total + returned_picks)
            else None,
            "candidate_starvation": returned_picks == 0 and aggregate_drop_total > 0,
        },
        "aggregate_drop_counts": _counter_dict(aggregate_drop_counts),
        "symbol_reason_decomposition": {
            "row_count": symbol_reason_total,
            "drop_key_counts": _counter_dict(drop_key_counts),
            "reason_counts": _counter_dict(reason_counts),
            "symbol_counts": _counter_dict(symbol_counts),
            "playbook_counts": _counter_dict(playbook_counts),
            "gate_category_counts": _counter_dict(gate_category_counts),
            "top_drop_keys": _top_counter(drop_key_counts),
            "top_reasons": _top_counter(reason_counts),
            "top_symbols": _top_counter(symbol_counts),
            "top_playbooks": _top_counter(playbook_counts),
            "top_gate_categories": _top_counter(gate_category_counts),
            "monthly_breakdown": _monthly_breakdown(rows),
            "symbol_month_drop_key_breakdown": _combined_breakdown(rows),
            "drop_rows": rows,
            "distance_summary": _distance_summary(rows),
        },
        "production_gate_survival": {
            "source_support": (
                "Returned picks and aggregate scan-funnel drops are session-level, so survival rates are computed by "
                "session-backed dimensions such as playbook and month. Symbol/drop-key/gate rows report drop share, not "
                "returned-pick survival, because returned picks are not attributed to rejected symbols."
            ),
            "overall": {
                "raw_candidates": raw_candidates,
                "returned_picks": returned_picks,
                "aggregate_drops": aggregate_drop_total,
                "recorded_drop_denominator": aggregate_drop_total + returned_picks,
                "returned_pick_rate_over_recorded_drops": round(returned_picks / (aggregate_drop_total + returned_picks), 6)
                if (aggregate_drop_total + returned_picks)
                else None,
            },
            "by_playbook": _session_survival_by(session_summaries, "playbook"),
            "by_month": _session_survival_by(session_summaries, "month"),
            "drop_share_by_symbol": _drop_share_rows(rows, "symbol"),
            "drop_share_by_drop_key": _drop_share_rows(rows, "drop_key"),
            "drop_share_by_gate_category": _drop_share_rows(rows, "gate_category"),
        },
        "liquidity_or_history_decomposition": {
            "row_count": len(liquidity_rows),
            "pct_of_symbol_drop_reasons": round(len(liquidity_rows) / symbol_reason_total, 6) if symbol_reason_total else 0.0,
            "drop_key_counts": _grouped_counts(liquidity_rows, "drop_key"),
            "reason_counts": _grouped_counts(liquidity_rows, "reason"),
            "symbol_counts": _grouped_counts(liquidity_rows, "symbol"),
            "distance_summary": _distance_summary(liquidity_rows),
        },
        "session_summaries": session_summaries[:200],
        "sample_rows": rows[:50],
        "proof_boundary": (
            "This decomposition is read-only diagnostic evidence about scheduled Phase 2 drop reasons. It does not "
            "change scanner policy, filters, thresholds, proof bars, stops, sizing, live validation, auto-track, broker "
            "behavior, cohort rows, quote stores, evidence stores, holdout state, accepted profitability, or promotion."
        ),
        "prohibited_actions": [
            "do_not_change_scanner_policy_from_drop_decomposition",
            "do_not_change_filter_or_threshold_from_drop_decomposition",
            "do_not_change_proof_bars_from_drop_decomposition",
            "do_not_append_cohort_rows_from_drop_decomposition",
            "do_not_import_quotes_from_drop_decomposition",
            "do_not_mutate_evidence_stores_from_drop_decomposition",
            "do_not_enable_live_validation_from_drop_decomposition",
            "do_not_enable_auto_track_from_drop_decomposition",
            "do_not_submit_broker_orders_from_drop_decomposition",
            "do_not_consume_protected_holdout_from_drop_decomposition",
            "do_not_promote_from_drop_decomposition",
        ],
        **FALSE_FLAGS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    recon = _as_dict(report.get("reconciliation"))
    throughput_info = _as_dict(report.get("scheduled_phase2_throughput"))
    symbol_decomp = _as_dict(report.get("symbol_reason_decomposition"))
    liquidity = _as_dict(report.get("liquidity_or_history_decomposition"))
    survival = _as_dict(report.get("production_gate_survival"))
    lines = [
        "# Regular Options Phase 2 Drop Decomposition",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Target selection date: `{report.get('target_selection_date')}`.",
        f"- Blockers: `{json.dumps(report.get('blockers') or [], sort_keys=True)}`.",
        f"- Scheduled sessions: `{throughput_info.get('session_count')}`.",
        f"- Raw candidates / returned picks: `{throughput_info.get('raw_candidates')}` / `{throughput_info.get('returned_picks')}`.",
        f"- Aggregate drops: `{recon.get('aggregate_drop_count_total')}`; throughput latest match `{recon.get('aggregate_drop_count_matches_throughput_latest')}`.",
        f"- Symbol drop-reason rows: `{recon.get('symbol_drop_reason_count_total')}`; throughput latest match `{recon.get('symbol_drop_reason_count_matches_throughput_latest')}`.",
        f"- Liquidity/history rows: `{liquidity.get('row_count')}` ({liquidity.get('pct_of_symbol_drop_reasons')}).",
        f"- Returned-pick rate over recorded drops: `{_as_dict(survival.get('overall')).get('returned_pick_rate_over_recorded_drops')}`.",
        "",
        "## Top Drop Keys",
        "",
    ]
    for row in _as_list(symbol_decomp.get("top_drop_keys"))[:10]:
        row = _as_dict(row)
        lines.append(f"- `{row.get('key')}`: `{row.get('count')}` ({row.get('pct')}).")
    lines.extend(["", "## Top Symbols", ""])
    for row in _as_list(symbol_decomp.get("top_symbols"))[:10]:
        row = _as_dict(row)
        lines.append(f"- `{row.get('key')}`: `{row.get('count')}` ({row.get('pct')}).")
    lines.extend(["", "## Monthly Breakdown", "", "| Month | Symbol Drop Reasons | Top Drop Keys |", "|---|---:|---|"])
    for row in _as_list(symbol_decomp.get("monthly_breakdown")):
        row = _as_dict(row)
        drop_keys = ", ".join(f"{key}={value}" for key, value in _as_dict(row.get("drop_key_counts")).items())
        lines.append(f"| `{row.get('month')}` | {row.get('symbol_drop_reason_rows')} | {drop_keys} |")
    lines.extend(["", "## Production-Gate Survival By Playbook", "", "| Playbook | Sessions | Drops | Returned Picks | Returned Rate |", "|---|---:|---:|---:|---:|"])
    for row in _as_list(survival.get("by_playbook")):
        row = _as_dict(row)
        lines.append(
            f"| `{row.get('playbook')}` | {row.get('session_count')} | {row.get('aggregate_drops')} | {row.get('returned_picks')} | {row.get('returned_pick_rate_over_recorded_drops')} |"
        )
    lines.extend(["", "## Boundary", "", str(report.get("proof_boundary") or "")])
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
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only scheduled Phase 2 drop decomposition.")
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--throughput-latest", type=Path, default=DEFAULT_THROUGHPUT_LATEST)
    parser.add_argument("--selection-date", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        ledger_db_path=args.ledger_db,
        throughput_latest_path=args.throughput_latest,
        selection_date=args.selection_date,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
