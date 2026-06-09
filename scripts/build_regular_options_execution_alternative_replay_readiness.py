from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_execution_alternative_replay_readiness"

DEFAULT_FILL_ATTEMPTS = ROOT / "data" / "forward-tracking" / "fill_attempts.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-execution-alternative-replay-readiness.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_execution_alternative_replay_readiness",
    "do_not_submit_broker_order_from_execution_alternative_replay_readiness",
    "do_not_mutate_database_from_execution_alternative_replay_readiness",
    "do_not_change_scanner_policy_from_execution_alternative_replay_readiness",
    "do_not_change_contract_selection_from_execution_alternative_replay_readiness",
    "do_not_change_stop_policy_from_execution_alternative_replay_readiness",
    "do_not_change_sizing_from_execution_alternative_replay_readiness",
    "do_not_synthesize_alternative_pnl_from_midpoint_daily_stale_or_display_marks",
    "do_not_promote_readiness_rows_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": str(path), "exists": path.exists(), "status": "missing", "error": None, "row_count": 0}
    if not path.exists():
        meta["error"] = "missing_artifact"
        return [], meta
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf8").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    return rows, meta


def _has_live_policy_change(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "live_policy_change" and bool(item):
                return True
            if _has_live_policy_change(item):
                return True
    if isinstance(value, list):
        return any(_has_live_policy_change(item) for item in value)
    return False


def _selected_spread(row: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(row.get("selected_spread"))


def _pair_from_spread(spread: dict[str, Any]) -> tuple[str, str]:
    long_symbol = _norm(spread.get("long_contract_symbol")).upper()
    short_symbol = _norm(spread.get("short_contract_symbol")).upper()
    for leg in _as_list(spread.get("legs")):
        leg = _as_dict(leg)
        role = _norm(leg.get("role")).lower()
        symbol = _norm(leg.get("contract_symbol")).upper()
        if role == "long" and symbol:
            long_symbol = symbol
        if role == "short" and symbol:
            short_symbol = symbol
    return long_symbol, short_symbol


def _selected_pair(row: dict[str, Any]) -> tuple[str, str]:
    selected = _selected_spread(row)
    long_symbol, short_symbol = _pair_from_spread(selected)
    long_symbol = long_symbol or _norm(row.get("long_contract_symbol")).upper()
    short_symbol = short_symbol or _norm(row.get("short_contract_symbol")).upper()
    return long_symbol, short_symbol


def _alternatives(row: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    alternatives: list[dict[str, Any]] = []
    for source_key in ("top_alternatives", "top_spread_alternatives"):
        for raw in _as_list(row.get(source_key)):
            alt = _as_dict(raw)
            if not alt:
                continue
            pair = _pair_from_spread(alt)
            identity = (source_key, alt.get("rank"), pair[0], pair[1], alt.get("long_strike"), alt.get("short_strike"))
            if identity in seen:
                continue
            seen.add(identity)
            alternatives.append({**alt, "source_key": source_key})
    return alternatives


def _entry_time(row: dict[str, Any]) -> str:
    selected = _selected_spread(row)
    return _norm(
        _first_present(
            row.get("attempted_limit_quote_time_utc"),
            row.get("quote_time_utc"),
            row.get("quote_timestamp_utc"),
            selected.get("quote_time_utc"),
            row.get("filled_at"),
            row.get("logged_at"),
        )
    )


def _entry_price(row: dict[str, Any]) -> float | None:
    selected = _selected_spread(row)
    return _safe_float(
        _first_present(
            row.get("filled_price"),
            row.get("attempted_limit_price"),
            row.get("intended_limit_price"),
            selected.get("entry_execution_price"),
            selected.get("spread_entry_debit"),
            selected.get("net_debit"),
        )
    )


def _expiry(row: dict[str, Any]) -> str:
    selected = _selected_spread(row)
    return _norm(_first_present(selected.get("expiry"), row.get("expiry")))


def _is_exact_opra_entry(row: dict[str, Any]) -> bool:
    selected = _selected_spread(row)
    tokens = [
        row.get("pricing_evidence_class"),
        row.get("candidate_execution_label"),
        row.get("options_data_source"),
        row.get("selection_source"),
        selected.get("quote_source"),
        selected.get("options_data_source"),
        selected.get("entry_execution_basis"),
    ]
    for leg in _as_list(selected.get("legs")):
        leg = _as_dict(leg)
        tokens.extend([leg.get("quote_source"), leg.get("data_source"), leg.get("source_feed")])
    blob = " ".join(_norm(token).lower() for token in tokens)
    return (
        _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
        or ("opra" in blob and "exact" in blob)
        or "live_chain_exact_contract" in blob
    )


def _spread_metric(row: dict[str, Any], key: str) -> Any:
    selected = _selected_spread(row)
    return _first_present(selected.get(key), row.get(key))


def _alternative_summary(alt: dict[str, Any]) -> dict[str, Any]:
    long_symbol, short_symbol = _pair_from_spread(alt)
    return {
        "source_key": alt.get("source_key"),
        "rank": alt.get("rank"),
        "long_contract_symbol": long_symbol or None,
        "short_contract_symbol": short_symbol or None,
        "long_strike": alt.get("long_strike"),
        "short_strike": alt.get("short_strike"),
        "net_debit": alt.get("net_debit"),
        "entry_debit": alt.get("entry_debit"),
        "spread_width": alt.get("spread_width"),
        "debit_pct_of_width": alt.get("debit_pct_of_width"),
        "spread_bid_ask_pct_of_mid": alt.get("spread_bid_ask_pct_of_mid"),
        "worst_leg_bid_ask_spread_pct": alt.get("worst_leg_bid_ask_spread_pct"),
        "min_leg_volume": alt.get("min_leg_volume"),
        "min_leg_open_interest": alt.get("min_leg_open_interest"),
        "liquidity_first_score": alt.get("liquidity_first_score"),
        "is_illiquid": alt.get("is_illiquid"),
    }


def _candidate_queue_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    selected_long, selected_short = _selected_pair(row)
    alternatives = _alternatives(row)
    alternative_pairs = [_pair_from_spread(alt) for alt in alternatives]
    replacement_pairs = [
        pair
        for pair in alternative_pairs
        if pair[0]
        and pair[1]
        and (pair[0], pair[1]) != (selected_long, selected_short)
    ]
    exact_entry = _is_exact_opra_entry(row)
    entry_time = _entry_time(row)
    entry_price = _entry_price(row)
    blockers: list[str] = []
    if not exact_entry:
        blockers.append("entry_not_proof_live_exact_contract")
    if not selected_long:
        blockers.append("missing_selected_long_contract_symbol")
    if not selected_short:
        blockers.append("missing_selected_short_contract_symbol")
    if not entry_time:
        blockers.append("missing_entry_quote_time")
    if entry_price is None or entry_price <= 0:
        blockers.append("missing_entry_execution_price")
    if not alternatives:
        blockers.append("top_alternatives_not_logged")
    if alternatives and not any(pair[0] and pair[1] for pair in alternative_pairs):
        blockers.append("missing_alternative_contract_symbols")

    if blockers:
        readiness_status = "blocked_missing_alternative_replay_seed"
    elif replacement_pairs:
        readiness_status = "alternative_seed_ready_engine_missing"
        blockers = [
            "contract_replacement_exit_survivability_replay_engine_missing",
            "top_spread_liquidity_first_replay_engine_missing",
            "alternate_contract_exit_quote_coverage_missing",
            "true_alternative_replay_pnl_rows_missing",
        ]
    else:
        readiness_status = "top_alternative_seed_ready_no_replacement_candidate"
        blockers = [
            "no_distinct_replacement_contract_logged",
            "top_spread_liquidity_first_replay_engine_missing",
            "alternate_contract_exit_quote_coverage_missing",
            "true_top_spread_replay_pnl_rows_missing",
        ]

    return {
        "source": "fill_attempts",
        "row_index": index,
        "readiness_status": readiness_status,
        "ticker": row.get("ticker"),
        "lane": row.get("playbook_id") or row.get("cohort_id"),
        "scan_date": row.get("scan_date"),
        "logged_at": row.get("logged_at"),
        "entry_time_utc": entry_time,
        "expiry": _expiry(row),
        "selected_long_contract_symbol": selected_long or None,
        "selected_short_contract_symbol": selected_short or None,
        "selected_entry_execution_price": entry_price,
        "selected_spread_width": _spread_metric(row, "spread_width"),
        "selected_debit_pct_of_width": _spread_metric(row, "debit_pct_of_width"),
        "selected_spread_bid_ask_pct_of_mid": _spread_metric(row, "spread_bid_ask_pct_of_mid"),
        "fill_degradation_vs_mid_pct": row.get("fill_degradation_vs_mid_pct"),
        "pricing_evidence_class": row.get("pricing_evidence_class"),
        "selection_source": row.get("selection_source"),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "auto_track_position_id": row.get("auto_track_position_id"),
        "top_alternative_count": len(alternatives),
        "replacement_alternative_count": len(replacement_pairs),
        "top_alternatives": [_alternative_summary(alt) for alt in alternatives[:3]],
        "blockers": blockers,
        "required_next_evidence": [
            "alternative_contract_exact_entry_seed",
            "alternative_contract_exit_quote_coverage",
            "contract_replacement_exit_survivability_replay_engine",
            "top_spread_liquidity_first_replay_engine",
            "true_alternative_replay_pnl_rows",
        ],
    }


def _overall_status(missing_required: list[str], live_policy_change: bool, top_seed_count: int, contract_seed_count: int) -> str:
    if live_policy_change:
        return "invalid_live_policy_change"
    if missing_required:
        return "blocked_missing_inputs"
    if contract_seed_count > 0:
        return "blocked_ready_seed_missing_execution_alternative_replay_engine"
    if top_seed_count > 0:
        return "blocked_top_spread_seed_missing_distinct_replacement_or_engine"
    return "blocked_no_execution_alternative_seed_rows"


def build_report(
    *,
    fill_attempts_path: Path = DEFAULT_FILL_ATTEMPTS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    fill_rows, fill_meta = _load_jsonl(fill_attempts_path)
    missing_required = ["fill_attempts"] if fill_meta.get("status") != "loaded" else []
    live_policy_change = _has_live_policy_change(fill_rows)

    candidate_rows = [row for row in fill_rows if _norm(row.get("event_type")) == "candidate_shown"]
    queue_rows = [_candidate_queue_row(row, index) for index, row in enumerate(candidate_rows)]
    queue_rows.sort(
        key=lambda item: (
            0 if item.get("readiness_status") == "alternative_seed_ready_engine_missing" else 1,
            str(item.get("entry_time_utc") or ""),
            str(item.get("ticker") or ""),
        )
    )
    status_counts = Counter(str(row.get("readiness_status")) for row in queue_rows)
    top_seed_count = int(status_counts.get("alternative_seed_ready_engine_missing", 0)) + int(
        status_counts.get("top_alternative_seed_ready_no_replacement_candidate", 0)
    )
    contract_seed_count = int(status_counts.get("alternative_seed_ready_engine_missing", 0))
    alternatives_logged_count = sum(1 for row in candidate_rows if _alternatives(row))
    replacement_logged_count = sum(1 for row in queue_rows if int(row.get("replacement_alternative_count") or 0) > 0)

    blockers = [
        "contract_replacement_exit_survivability_replay_engine_missing",
        "top_spread_liquidity_first_replay_engine_missing",
        "alternate_contract_exit_quote_coverage_missing",
        "true_alternative_replay_pnl_rows_missing",
    ]
    if top_seed_count == 0:
        blockers.append("no_top_spread_alternative_seed_rows")
    if contract_seed_count == 0:
        blockers.append("no_distinct_contract_replacement_seed_rows")
    if missing_required:
        blockers.extend(missing_required)

    report_status = (
        "invalid_live_policy_change"
        if live_policy_change
        else "blocked_missing_inputs"
        if missing_required
        else "execution_alternative_replay_readiness_readback"
    )
    overall_status = _overall_status(missing_required, live_policy_change, top_seed_count, contract_seed_count)

    return {
        "report_id": REPORT_ID,
        "status": report_status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_execution_alternative_replay_readiness_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": {
            "overall_status": overall_status,
            "candidate_shown_count": len(candidate_rows),
            "selected_spread_count": sum(1 for row in candidate_rows if isinstance(row.get("selected_spread"), dict)),
            "top_alternative_logged_row_count": alternatives_logged_count,
            "replacement_alternative_logged_row_count": replacement_logged_count,
            "exact_opra_entry_seed_count": sum(1 for row in candidate_rows if _is_exact_opra_entry(row)),
            "proof_live_pricing_class_count": sum(
                1 for row in candidate_rows if _norm(row.get("pricing_evidence_class")) == "proof_live_opra_exact_contract"
            ),
            "top_spread_replay_seed_count": top_seed_count,
            "contract_replacement_seed_count": contract_seed_count,
            "blocked_missing_alternative_replay_seed_count": int(status_counts.get("blocked_missing_alternative_replay_seed", 0)),
            "true_top_spread_replay_pnl_count": 0,
            "true_contract_replacement_pnl_count": 0,
            "liquidity_first_replay_engine_status": "missing",
            "contract_replacement_replay_engine_status": "missing",
            "alternative_exit_quote_coverage_status": "missing",
            "missing_required_inputs": missing_required,
            "blocker_count": len(sorted(set(blockers))),
            "blockers": sorted(set(blockers)),
            "live_policy_change": live_policy_change,
        },
        "evidence_boundary": {
            "readback_is": "readiness queue for future exact OPRA/NBBO top-spread and contract-replacement replay work",
            "readback_is_not": "simulated P&L, contract-selection permission, promotion proof, broker action, or a live-risk instruction",
            "trusted_future_requirement": "exact-contract OPRA/NBBO bid/ask replay for selected and alternative contracts from entry through exit with no midpoint, daily/EOD, stale, display, or manual marks",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "inputs": {"fill_attempts": fill_meta},
        "readiness_status_counts": dict(sorted(status_counts.items())),
        "candidate_queue": queue_rows[:50],
        "next_evidence_queue": [
            {
                "priority": 0,
                "action": "build_contract_replacement_exit_survivability_replay_engine",
                "count": 1,
                "reason": "contract_replacement_exit_survivability_replay_engine_missing",
                "operator_next_step": "Replay selected contracts against distinct logged alternatives using exact entry and exit OPRA/NBBO quotes before changing contract selection.",
            },
            {
                "priority": 1,
                "action": "build_top_spread_liquidity_first_replay_engine",
                "count": 1,
                "reason": "top_spread_liquidity_first_replay_engine_missing",
                "operator_next_step": "Use the logged top alternatives as the candidate set for liquidity-first v2 replay; do not promote from logged ranking alone.",
            },
            {
                "priority": 2,
                "action": "import_or_query_alternative_exit_quotes",
                "count": top_seed_count,
                "reason": "alternate_contract_exit_quote_coverage_missing_for_seed_rows",
                "operator_next_step": "Collect exact OPRA/NBBO exit-window quotes for selected and alternative long/short contracts.",
            },
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    return _norm(value).replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Execution Alternative Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_execution_alternative_replay_readiness.py`. It is a read-only readiness queue for future top-spread and contract-replacement replay work and does not simulate P&L or change contract selection.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Overall status: `{summary.get('overall_status')}`.",
        f"- Candidate-shown rows: `{summary.get('candidate_shown_count')}`.",
        f"- Top-spread replay seeds: `{summary.get('top_spread_replay_seed_count')}`.",
        f"- Contract-replacement seeds: `{summary.get('contract_replacement_seed_count')}`.",
        f"- True top-spread / contract-replacement P&L rows: `{summary.get('true_top_spread_replay_pnl_count')}` / `{summary.get('true_contract_replacement_pnl_count')}`.",
        f"- Alternative exit quote coverage: `{summary.get('alternative_exit_quote_coverage_status')}`.",
        f"- Replay engines: `{summary.get('liquidity_first_replay_engine_status')}` / `{summary.get('contract_replacement_replay_engine_status')}`.",
        f"- Blockers: `{_json_inline(summary.get('blockers') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Candidate Queue",
        "",
        "| Status | Ticker | Lane | Entry Time | Selected Long | Selected Short | Alternatives | Replacements | Blockers |",
        "|---|---|---|---|---|---|---:|---:|---|",
    ]
    for row in _as_list(report.get("candidate_queue"))[:25]:
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('readiness_status'))}`",
                    _cell(row.get("ticker")),
                    _cell(row.get("lane")),
                    _cell(row.get("entry_time_utc")),
                    _cell(row.get("selected_long_contract_symbol")),
                    _cell(row.get("selected_short_contract_symbol")),
                    _cell(row.get("top_alternative_count")),
                    _cell(row.get("replacement_alternative_count")),
                    _cell(", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Next Evidence Queue",
            "",
            "| Priority | Action | Count | Reason |",
            "|---:|---|---:|---|",
        ]
    )
    for item in _as_list(report.get("next_evidence_queue")):
        item = _as_dict(item)
        lines.append(
            f"| {_cell(item.get('priority'))} | `{_cell(item.get('action'))}` | {_cell(item.get('count'))} | {_cell(item.get('reason'))} |"
        )
    boundary = _as_dict(report.get("evidence_boundary"))
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Readback is: `{boundary.get('readback_is')}`.",
            f"- Readback is not: `{boundary.get('readback_is_not')}`.",
            f"- Trusted future requirement: `{boundary.get('trusted_future_requirement')}`.",
            "",
            "This readiness report is read-only. It does not create trades, submit broker orders, mutate DB state, change scanner policy, change contract selection, change stops, change sizing, synthesize alternative P&L from midpoint/daily/stale/display marks, lower proof bars, or promote readiness rows to production proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only regular-options execution alternative replay readiness queue.")
    parser.add_argument("--fill-attempts", type=Path, default=DEFAULT_FILL_ATTEMPTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(fill_attempts_path=args.fill_attempts)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
