from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_execution_alternative_quote_import_plan"

DEFAULT_COVERAGE = (
    ROOT / "data" / "forward-tracking" / "regular_options_execution_alternative_replay_coverage_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-execution-alternative-quote-import-plan.md"
DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_INTERVAL = "1m"

OCC_CONTRACT_RE = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_execution_alternative_quote_import_plan",
    "do_not_submit_broker_order_from_execution_alternative_quote_import_plan",
    "do_not_mutate_trading_row_database_from_execution_alternative_quote_import_plan",
    "do_not_change_scanner_policy_from_execution_alternative_quote_import_plan",
    "do_not_change_contract_selection_policy_from_execution_alternative_quote_import_plan",
    "do_not_change_stop_policy_from_execution_alternative_quote_import_plan",
    "do_not_change_sizing_from_execution_alternative_quote_import_plan",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_execution_alternative_quote_import_plan",
    "do_not_promote_quote_import_plan_to_production_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "error": None,
    }
    if not path.exists():
        meta["error"] = "missing_artifact"
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "json_root_not_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("generated_at")
    return payload, meta


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


def _minute_to_time(value: Any) -> str | None:
    minute = _safe_int(value, default=-1)
    if minute < 0 or minute >= 24 * 60:
        return None
    return f"{minute // 60:02d}:{minute % 60:02d}:00"


def _parse_iso_date(value: Any) -> date | None:
    raw = _norm(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_occ_contract(symbol: Any) -> dict[str, Any]:
    contract_symbol = _norm(symbol).upper()
    match = OCC_CONTRACT_RE.match(contract_symbol)
    if not match:
        return {
            "contract_symbol": contract_symbol,
            "parse_status": "unparsed_contract_symbol",
        }
    root, expiry_yyMMdd, right_code, strike_raw = match.groups()
    yy = int(expiry_yyMMdd[:2])
    expiry_year = 2000 + yy
    expiry = f"{expiry_year:04d}-{int(expiry_yyMMdd[2:4]):02d}-{int(expiry_yyMMdd[4:6]):02d}"
    right = "call" if right_code == "C" else "put"
    return {
        "contract_symbol": contract_symbol,
        "parse_status": "parsed",
        "underlying": root,
        "expiry": expiry,
        "right": right,
        "right_code": right_code,
        "strike": round(int(strike_raw) / 1000.0, 3),
    }


def _first_source_ticker(demand: dict[str, Any]) -> str | None:
    for row in _as_list(demand.get("source_rows")):
        row = _as_dict(row)
        ticker = _norm(row.get("ticker")).upper()
        if ticker:
            return ticker
    return None


def _dte(quote_date_et: Any, expiry: Any) -> int | None:
    quote_date = _parse_iso_date(quote_date_et)
    expiry_date = _parse_iso_date(expiry)
    if quote_date is None or expiry_date is None:
        return None
    return max(0, (expiry_date - quote_date).days)


def _unique_sorted(items: list[Any]) -> list[Any]:
    return sorted({item for item in items if item not in {None, ""}}, key=lambda item: str(item))


def _normalize_demands(coverage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    for raw in _as_list(coverage.get("quote_demands")):
        demand = _as_dict(raw)
        if not demand:
            continue
        parsed = _parse_occ_contract(demand.get("contract_symbol"))
        minute = _safe_int(demand.get("quote_minute_et"), default=-1)
        quote_time = _minute_to_time(minute)
        row = {
            "priority": _safe_int(demand.get("priority")),
            "contract_symbol": parsed.get("contract_symbol") or _norm(demand.get("contract_symbol")).upper(),
            "parse_status": parsed.get("parse_status"),
            "underlying": parsed.get("underlying") or _first_source_ticker(demand),
            "expiry": parsed.get("expiry"),
            "right": parsed.get("right"),
            "strike": parsed.get("strike"),
            "quote_date_et": _norm(demand.get("quote_date_et"))[:10],
            "quote_minute_et": minute if minute >= 0 else None,
            "quote_time_et": quote_time,
            "window_minutes": _safe_int(demand.get("window_minutes")),
            "quote_phase": _norm(demand.get("quote_phase")) or "unknown",
            "snapshot_kind": _norm(demand.get("snapshot_kind")) or "intraday",
            "data_trust": _norm(demand.get("data_trust")) or "trusted",
            "quote_evidence_class": _norm(demand.get("quote_evidence_class")) or "trusted_intraday_opra_nbbo",
            "source_labels": _unique_sorted([_norm(item) for item in _as_list(demand.get("source_labels"))]),
            "usage_labels": _unique_sorted([_norm(item) for item in _as_list(demand.get("usage_labels"))]),
            "missing_reasons": _unique_sorted([_norm(item) for item in _as_list(demand.get("missing_reasons"))]),
            "source_row_count": _safe_int(demand.get("source_row_count")),
            "source_rows": _as_list(demand.get("source_rows")),
        }
        row["dte"] = _dte(row.get("quote_date_et"), row.get("expiry"))
        if row["parse_status"] != "parsed" or not row.get("underlying") or quote_time is None:
            row["planner_blocker"] = "unparsed_or_incomplete_quote_demand"
            unparsed.append(row)
            continue
        manifest.append(row)
    return sorted(
        manifest,
        key=lambda item: (
            _safe_int(item.get("priority")),
            _norm(item.get("quote_date_et")),
            _safe_int(item.get("quote_minute_et")),
            _norm(item.get("quote_phase")),
            _norm(item.get("contract_symbol")),
        ),
    ), unparsed


def _powershell_command(
    *,
    symbols: list[str],
    quote_date_et: str,
    start_time_et: str,
    end_time_et: str,
    min_dte: int,
    max_dte: int,
    right: str,
    theta_url: str,
    timeout_seconds: int,
    dry_run: bool,
) -> str:
    parts = [
        "uv",
        "run",
        "--locked",
        "python",
        r"scripts\import_thetadata_options_nbbo.py",
        "--symbols",
        ",".join(symbols),
        "--date-from",
        quote_date_et,
        "--date-to",
        quote_date_et,
        "--snapshot-kind",
        "intraday",
        "--start-time",
        start_time_et,
        "--end-time",
        end_time_et,
        "--interval",
        DEFAULT_INTERVAL,
        "--min-dte",
        str(min_dte),
        "--max-dte",
        str(max_dte),
        "--right",
        right,
        "--theta-url",
        theta_url,
        "--timeout",
        str(timeout_seconds),
    ]
    if dry_run:
        parts.append("--dry-run")
    parts.append("--json")
    return " ".join(parts)


def _command_groups(
    manifest: list[dict[str, Any]],
    *,
    theta_url: str,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for demand in manifest:
        key = (
            _norm(demand.get("quote_date_et")),
            _norm(demand.get("quote_phase")),
            _norm(demand.get("right")) or "both",
            _safe_int(demand.get("window_minutes")),
        )
        grouped[key].append(demand)
    groups: list[dict[str, Any]] = []
    for index, (key, demands) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3])),
        start=1,
    ):
        quote_date_et, quote_phase, right, window_minutes = key
        minutes = [_safe_int(item.get("quote_minute_et")) for item in demands]
        start_minute = max(0, min(minutes) - window_minutes)
        end_minute = min((24 * 60) - 1, max(minutes) + window_minutes)
        start_time = _minute_to_time(start_minute) or "00:00:00"
        end_time = _minute_to_time(end_minute) or start_time
        dtes = [int(item["dte"]) for item in demands if item.get("dte") is not None]
        min_dte = min(dtes) if dtes else 0
        max_dte = max(dtes) if dtes else 90
        symbols = _unique_sorted([_norm(item.get("underlying")).upper() for item in demands])
        usage_labels = _unique_sorted(
            [usage for item in demands for usage in _as_list(item.get("usage_labels"))]
        )
        group = {
            "group_id": f"execution_alternative_quote_group_{index:03d}",
            "priority": min(_safe_int(item.get("priority")) for item in demands),
            "quote_date_et": quote_date_et,
            "quote_phase": quote_phase,
            "right": right,
            "symbols": symbols,
            "start_time_et": start_time,
            "end_time_et": end_time,
            "window_minutes": window_minutes,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "demand_count": len(demands),
            "contract_count": len({item.get("contract_symbol") for item in demands}),
            "usage_labels": usage_labels,
            "status": "ready_for_import_or_query",
            "dry_run_command": _powershell_command(
                symbols=symbols,
                quote_date_et=quote_date_et,
                start_time_et=start_time,
                end_time_et=end_time,
                min_dte=min_dte,
                max_dte=max_dte,
                right=right,
                theta_url=theta_url,
                timeout_seconds=timeout_seconds,
                dry_run=True,
            ),
            "write_command": _powershell_command(
                symbols=symbols,
                quote_date_et=quote_date_et,
                start_time_et=start_time,
                end_time_et=end_time,
                min_dte=min_dte,
                max_dte=max_dte,
                right=right,
                theta_url=theta_url,
                timeout_seconds=timeout_seconds,
                dry_run=False,
            ),
            "exact_contract_symbols": sorted({str(item.get("contract_symbol")) for item in demands}),
        }
        groups.append(group)
    return sorted(groups, key=lambda item: (_safe_int(item.get("priority")), _norm(item.get("quote_date_et")), _norm(item.get("group_id"))))


def _summary(
    *,
    status: str,
    coverage: dict[str, Any],
    coverage_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    manifest: list[dict[str, Any]],
    unparsed: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    phase_counts = Counter(str(item.get("quote_phase")) for item in manifest)
    right_counts = Counter(str(item.get("right")) for item in manifest)
    usage_counts = Counter(
        str(usage)
        for item in manifest
        for usage in _as_list(item.get("usage_labels"))
    )
    demand_dates = _unique_sorted([item.get("quote_date_et") for item in manifest])
    symbols = _unique_sorted([item.get("underlying") for item in manifest])
    coverage_summary = _as_dict(coverage.get("summary"))
    return {
        "overall_status": status,
        "source_coverage_status": coverage.get("status"),
        "source_coverage_generated_at_utc": coverage_meta.get("generated_at_utc"),
        "source_quote_demand_manifest_status": coverage_summary.get("quote_demand_manifest_status"),
        "source_missing_quote_demand_count": coverage_summary.get("missing_quote_demand_count"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "quote_import_plan_status": status,
        "quote_demand_count": len(manifest) + len(unparsed),
        "exact_contract_manifest_count": len(manifest),
        "unparsed_quote_demand_count": len(unparsed),
        "command_group_count": len(groups),
        "entry_quote_demand_count": int(phase_counts.get("entry", 0)),
        "exit_quote_demand_count": int(phase_counts.get("exit", 0)),
        "quote_date_count": len(demand_dates),
        "quote_dates": demand_dates,
        "underlying_count": len(symbols),
        "underlyings": symbols,
        "phase_counts": dict(sorted(phase_counts.items())),
        "right_counts": dict(sorted(right_counts.items())),
        "usage_counts": dict(sorted(usage_counts.items())),
        "theta_probe_status": "not_requested",
        "operator_command_status": "ready_for_dry_run_then_operator_import" if groups else "not_available",
    }


def build_report(
    *,
    coverage_path: Path = DEFAULT_COVERAGE,
    theta_url: str = DEFAULT_THETA_URL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    coverage, coverage_meta = _load_json(coverage_path)
    missing_required: list[str] = []
    if coverage_meta.get("status") != "loaded" or coverage.get("status") != "execution_alternative_replay_coverage_readback":
        missing_required.append("execution_alternative_replay_coverage")
    live_policy_change = _has_live_policy_change(coverage)
    manifest: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    if not missing_required and not live_policy_change:
        manifest, unparsed = _normalize_demands(coverage)
        groups = _command_groups(manifest, theta_url=theta_url, timeout_seconds=timeout_seconds)

    if live_policy_change:
        status = "invalid_live_policy_change"
    elif missing_required:
        status = "blocked_missing_inputs"
    elif not manifest and not unparsed:
        status = "no_quote_demands_to_plan"
    elif manifest:
        status = "execution_alternative_quote_import_plan_ready"
    else:
        status = "blocked_unparsed_quote_demands"

    summary = _summary(
        status=status,
        coverage=coverage,
        coverage_meta=coverage_meta,
        missing_required=missing_required,
        live_policy_change=live_policy_change,
        manifest=manifest,
        unparsed=unparsed,
        groups=groups,
    )
    next_queue: list[dict[str, Any]] = []
    if groups:
        next_queue.append(
            {
                "priority": 7,
                "action": "run_execution_alternative_quote_import_commands",
                "count": len(groups),
                "reason": "execution_alternative_quote_demands_ready_for_import_or_query",
                "operator_next_step": "Run the dry-run commands first; if ThetaData is available and rows parse cleanly, run the write commands, then rerun execution-alternative coverage and monthly profitability audit.",
            }
        )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_execution_alternative_quote_import_plan_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {
            "execution_alternative_replay_coverage": coverage_meta,
            "theta_url": theta_url,
            "timeout_seconds": int(timeout_seconds),
            "importer": r"scripts\import_thetadata_options_nbbo.py",
        },
        "command_groups": groups,
        "exact_contract_manifest": manifest,
        "unparsed_quote_demands": unparsed,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only quote import/query coordination for execution-alternative replay gaps",
            "readback_is_not": "scanner policy, contract-selection permission, broker action, trading-row DB mutation, stop/sizing change, or promotion proof",
            "operator_rule": "Dry-run commands may fetch and parse; write commands import quote evidence only and still require rerunning coverage before any P&L claim.",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _cell(value: Any) -> str:
    text = _norm(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Execution Alternative Quote Import Plan",
        "",
        "This report is generated from `scripts/build_regular_options_execution_alternative_quote_import_plan.py`. It is a read-only import/query plan for exact OPRA/NBBO quote demands produced by the execution-alternative replay coverage layer.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source coverage: `{summary.get('source_coverage_status')}` / `{summary.get('source_quote_demand_manifest_status')}`.",
        f"- Exact quote demands: `{summary.get('exact_contract_manifest_count')}` parsed, `{summary.get('unparsed_quote_demand_count')}` unparsed.",
        f"- Entry / exit demands: `{summary.get('entry_quote_demand_count')}` / `{summary.get('exit_quote_demand_count')}`.",
        f"- Command groups: `{summary.get('command_group_count')}`.",
        f"- Dates: `{_json_inline(summary.get('quote_dates') or [])}`.",
        f"- Underlyings: `{_json_inline(summary.get('underlyings') or [])}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        f"- Theta probe: `{summary.get('theta_probe_status')}`.",
        "",
        "## Command Groups",
        "",
        "| Group | Priority | Date | Phase | Right | Symbols | Time Window | DTE | Demands | Contracts |",
        "|---|---:|---|---|---|---|---|---|---:|---:|",
    ]
    for group in _as_list(report.get("command_groups")):
        group = _as_dict(group)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(group.get("group_id")),
                    _cell(group.get("priority")),
                    _cell(group.get("quote_date_et")),
                    _cell(group.get("quote_phase")),
                    _cell(group.get("right")),
                    _cell(",".join(str(item) for item in _as_list(group.get("symbols")))),
                    _cell(f"{group.get('start_time_et')} to {group.get('end_time_et')}"),
                    _cell(f"{group.get('min_dte')} to {group.get('max_dte')}"),
                    _cell(group.get("demand_count")),
                    _cell(group.get("contract_count")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Commands", ""])
    if not _as_list(report.get("command_groups")):
        lines.append("No import/query command groups are available.")
    for group in _as_list(report.get("command_groups")):
        group = _as_dict(group)
        lines.extend(
            [
                f"### {group.get('group_id')}",
                "",
                "Dry run:",
                "",
                "```powershell",
                _norm(group.get("dry_run_command")),
                "```",
                "",
                "Write import:",
                "",
                "```powershell",
                _norm(group.get("write_command")),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Exact Contract Manifest",
            "",
            "| Priority | Contract | Date | Time | Phase | Right | Expiry | Strike | Usage | Missing Reasons |",
            "|---:|---|---|---|---|---|---|---:|---|---|",
        ]
    )
    for demand in _as_list(report.get("exact_contract_manifest"))[:80]:
        demand = _as_dict(demand)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(demand.get("priority")),
                    _cell(demand.get("contract_symbol")),
                    _cell(demand.get("quote_date_et")),
                    _cell(demand.get("quote_time_et")),
                    _cell(demand.get("quote_phase")),
                    _cell(demand.get("right")),
                    _cell(demand.get("expiry")),
                    _cell(demand.get("strike")),
                    _cell(",".join(str(item) for item in _as_list(demand.get("usage_labels")))),
                    _cell(",".join(str(item) for item in _as_list(demand.get("missing_reasons")))),
                ]
            )
            + " |"
        )
    if _as_list(report.get("unparsed_quote_demands")):
        lines.extend(
            [
                "",
                "## Unparsed Demands",
                "",
                f"- Count: `{len(_as_list(report.get('unparsed_quote_demands')))}`.",
                "- These rows are not grouped into importer commands until the contract/date/minute fields are repaired.",
            ]
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
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This import plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, change scanner policy, change contract selection, change stops, change sizing, lower exact OPRA/NBBO proof bars, or promote replay rows to production proof.",
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
    parser = argparse.ArgumentParser(description="Build a read-only execution-alternative quote import plan.")
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        coverage_path=args.coverage,
        theta_url=args.theta_url,
        timeout_seconds=args.timeout,
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
