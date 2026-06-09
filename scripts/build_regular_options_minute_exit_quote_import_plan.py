from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT_ID = "regular_options_minute_exit_quote_import_plan"

DEFAULT_READINESS = ROOT / "data" / "forward-tracking" / "regular_options_minute_exit_replay_readiness_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-minute-exit-quote-import-plan.md"
DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_INTERVAL = "1m"
DEFAULT_EXIT_END_TIME_ET = "16:00:00"

READY_STATUS = "minute_exit_quote_import_plan_ready_engine_blocked"
NO_SEEDS_STATUS = "no_minute_exit_quote_seeds_to_plan"
UNPARSED_STATUS = "blocked_unparsed_minute_exit_quote_demands"
MISSING_STATUS = "blocked_missing_inputs"
INVALID_STATUS = "invalid_live_policy_change"

OCC_CONTRACT_RE = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")
NY_TZ = ZoneInfo("America/New_York")

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_minute_exit_quote_import_plan",
    "do_not_submit_broker_order_from_minute_exit_quote_import_plan",
    "do_not_mutate_trading_row_database_from_minute_exit_quote_import_plan",
    "do_not_change_scanner_policy_from_minute_exit_quote_import_plan",
    "do_not_change_stop_policy_from_minute_exit_quote_import_plan",
    "do_not_change_sizing_from_minute_exit_quote_import_plan",
    "do_not_synthesize_minute_exit_pnl_from_import_plan",
    "do_not_promote_minute_quote_import_plan_to_production_proof",
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


def _parse_occ_contract(symbol: Any) -> dict[str, Any]:
    contract_symbol = _norm(symbol).upper()
    match = OCC_CONTRACT_RE.match(contract_symbol)
    if not match:
        return {"contract_symbol": contract_symbol, "parse_status": "unparsed_contract_symbol"}
    root, expiry_yyMMdd, right_code, strike_raw = match.groups()
    expiry_year = 2000 + int(expiry_yyMMdd[:2])
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


def _parse_iso_date(value: Any) -> date | None:
    raw = _norm(value)[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _dte(quote_date_et: Any, expiry: Any) -> int | None:
    quote_date = _parse_iso_date(quote_date_et)
    expiry_date = _parse_iso_date(expiry)
    if quote_date is None or expiry_date is None:
        return None
    return max(0, (expiry_date - quote_date).days)


def _entry_datetime_utc(value: Any) -> datetime | None:
    raw = _norm(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _entry_window(seed: dict[str, Any]) -> tuple[str, str, str]:
    parsed = _entry_datetime_utc(seed.get("entry_time_utc"))
    if parsed is None:
        quote_date = _norm(seed.get("scan_date"))[:10]
        return quote_date, "09:30:00", DEFAULT_EXIT_END_TIME_ET
    entry_et = parsed.astimezone(NY_TZ)
    return entry_et.date().isoformat(), entry_et.strftime("%H:%M:%S"), DEFAULT_EXIT_END_TIME_ET


def _unique_sorted(items: list[Any]) -> list[Any]:
    return sorted({item for item in items if item not in {None, ""}}, key=lambda item: str(item))


def _quote_demands(readiness: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary = _as_dict(readiness.get("summary"))
    if (
        _norm(summary.get("minute_quote_coverage_status")) == "full"
        and _safe_int(summary.get("true_minute_exit_pnl_count")) >= _safe_int(summary.get("entry_seed_ready_count"))
        and _safe_int(summary.get("entry_seed_ready_count")) > 0
    ):
        return [], []
    manifest: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    for seed in _as_list(readiness.get("candidate_queue")):
        seed = _as_dict(seed)
        if not seed:
            continue
        quote_date_et, start_time_et, end_time_et = _entry_window(seed)
        seed_status = _norm(seed.get("readiness_status")) or "unknown"
        replay_eligibility = (
            "position_seed_ready" if seed_status == "position_seed_ready_engine_missing" else "entry_seed_only"
        )
        for leg_role, key in (("long", "long_contract_symbol"), ("short", "short_contract_symbol")):
            parsed = _parse_occ_contract(seed.get(key))
            row = {
                "priority": 0 if replay_eligibility == "position_seed_ready" else 1,
                "seed_row_index": seed.get("row_index"),
                "seed_readiness_status": seed_status,
                "replay_eligibility": replay_eligibility,
                "ticker": seed.get("ticker"),
                "lane": seed.get("lane"),
                "auto_track_position_id": seed.get("auto_track_position_id"),
                "fill_status": seed.get("fill_status"),
                "fill_outcome": seed.get("fill_outcome"),
                "leg_role": leg_role,
                "contract_symbol": parsed.get("contract_symbol") or _norm(seed.get(key)).upper(),
                "parse_status": parsed.get("parse_status"),
                "underlying": parsed.get("underlying") or _norm(seed.get("ticker")).upper(),
                "expiry": parsed.get("expiry") or seed.get("expiry"),
                "right": parsed.get("right"),
                "strike": parsed.get("strike"),
                "quote_date_et": quote_date_et,
                "start_time_et": start_time_et,
                "end_time_et": end_time_et,
                "snapshot_kind": "intraday",
                "data_trust": "trusted",
                "quote_evidence_class": "trusted_intraday_opra_nbbo",
                "usage_labels": [f"minute_exit:{leg_role}_path"],
                "missing_reasons": ["minute_level_exit_quote_coverage_missing"],
                "source_seed": seed,
            }
            row["dte"] = _dte(row.get("quote_date_et"), row.get("expiry"))
            if row["parse_status"] != "parsed" or not row.get("underlying") or not row.get("quote_date_et"):
                row["planner_blocker"] = "unparsed_or_incomplete_minute_exit_quote_seed"
                unparsed.append(row)
                continue
            manifest.append(row)
    return sorted(
        manifest,
        key=lambda item: (
            _safe_int(item.get("priority")),
            _norm(item.get("quote_date_et")),
            _norm(item.get("underlying")),
            _norm(item.get("right")),
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
            _norm(demand.get("underlying")).upper(),
            _norm(demand.get("right")),
            _safe_int(demand.get("priority")),
        )
        grouped[key].append(demand)
    groups: list[dict[str, Any]] = []
    for index, (key, demands) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][3], item[0][0], item[0][1], item[0][2])),
        start=1,
    ):
        quote_date_et, underlying, right, priority = key
        dtes = [int(item["dte"]) for item in demands if item.get("dte") is not None]
        min_dte = min(dtes) if dtes else 0
        max_dte = max(dtes) if dtes else 90
        start_time = min(_norm(item.get("start_time_et")) for item in demands if _norm(item.get("start_time_et")))
        end_time = max(_norm(item.get("end_time_et")) for item in demands if _norm(item.get("end_time_et")))
        group = {
            "group_id": f"minute_exit_quote_group_{index:03d}",
            "priority": priority,
            "quote_date_et": quote_date_et,
            "right": right,
            "symbols": [underlying],
            "start_time_et": start_time,
            "end_time_et": end_time,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "demand_count": len(demands),
            "seed_count": len({item.get("seed_row_index") for item in demands}),
            "contract_count": len({item.get("contract_symbol") for item in demands}),
            "position_linked_seed_count": sum(1 for item in demands if item.get("replay_eligibility") == "position_seed_ready"),
            "entry_only_seed_count": sum(1 for item in demands if item.get("replay_eligibility") == "entry_seed_only"),
            "status": "ready_for_import_or_query",
            "dry_run_command": _powershell_command(
                symbols=[underlying],
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
                symbols=[underlying],
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
    return groups


def _summary(
    *,
    status: str,
    readiness: dict[str, Any],
    readiness_meta: dict[str, Any],
    missing_required: list[str],
    live_policy_change: bool,
    manifest: list[dict[str, Any]],
    unparsed: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    source_summary = _as_dict(readiness.get("summary"))
    eligibility_counts = Counter(str(item.get("replay_eligibility")) for item in manifest)
    demand_dates = _unique_sorted([item.get("quote_date_et") for item in manifest])
    underlyings = _unique_sorted([item.get("underlying") for item in manifest])
    return {
        "overall_status": status,
        "source_readiness_status": readiness.get("status"),
        "source_readiness_generated_at_utc": readiness_meta.get("generated_at_utc"),
        "source_overall_status": source_summary.get("overall_status"),
        "missing_required_inputs": missing_required,
        "live_policy_change": live_policy_change,
        "source_entry_seed_ready_count": source_summary.get("entry_seed_ready_count"),
        "source_position_seed_ready_count": source_summary.get("position_seed_ready_count"),
        "source_true_minute_exit_pnl_count": source_summary.get("true_minute_exit_pnl_count"),
        "source_minute_exit_replay_engine_status": source_summary.get("minute_exit_replay_engine_status"),
        "source_minute_quote_coverage_status": source_summary.get("minute_quote_coverage_status"),
        "source_open_risk_status": source_summary.get("open_risk_status"),
        "quote_demand_count": len(manifest) + len(unparsed),
        "exact_contract_manifest_count": len(manifest),
        "unparsed_quote_demand_count": len(unparsed),
        "command_group_count": len(groups),
        "quote_date_count": len(demand_dates),
        "quote_dates": demand_dates,
        "underlying_count": len(underlyings),
        "underlyings": underlyings,
        "position_linked_quote_demand_count": int(eligibility_counts.get("position_seed_ready", 0)),
        "entry_only_quote_demand_count": int(eligibility_counts.get("entry_seed_only", 0)),
        "operator_command_status": "ready_for_dry_run_then_operator_import" if groups else "not_available",
        "replay_pnl_status": "available_in_source_readiness"
        if _safe_int(source_summary.get("true_minute_exit_pnl_count")) > 0
        else "not_available_until_quotes_and_engine_exist",
    }


def build_report(
    *,
    readiness_path: Path = DEFAULT_READINESS,
    theta_url: str = DEFAULT_THETA_URL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    readiness, readiness_meta = _load_json(readiness_path)
    missing_required: list[str] = []
    if readiness_meta.get("status") != "loaded" or readiness.get("status") != "minute_exit_replay_readiness_readback":
        missing_required.append("minute_exit_replay_readiness")
    live_policy_change = _has_live_policy_change(readiness)
    manifest: list[dict[str, Any]] = []
    unparsed: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    if not missing_required and not live_policy_change:
        manifest, unparsed = _quote_demands(readiness)
        groups = _command_groups(manifest, theta_url=theta_url, timeout_seconds=timeout_seconds)

    if live_policy_change:
        status = INVALID_STATUS
    elif missing_required:
        status = MISSING_STATUS
    elif not manifest and not unparsed:
        status = NO_SEEDS_STATUS
    elif manifest:
        status = READY_STATUS
    else:
        status = UNPARSED_STATUS

    summary = _summary(
        status=status,
        readiness=readiness,
        readiness_meta=readiness_meta,
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
                "action": "run_minute_exit_quote_import_plan_commands",
                "count": len(groups),
                "reason": "minute_exit_quote_demands_ready_for_import_or_query",
                "operator_next_step": "Run dry-run imports first; after trusted minute quotes exist, rerun minute readiness, monthly profitability, and only then build true minute-exit P&L.",
            }
        )
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "scope": "regular_options_minute_exit_quote_import_plan_read_only",
        "schema_version": 1,
        "read_only": True,
        "live_policy_change": live_policy_change,
        "summary": summary,
        "inputs": {
            "minute_exit_replay_readiness": readiness_meta,
            "theta_url": theta_url,
            "timeout_seconds": int(timeout_seconds),
            "importer": r"scripts\import_thetadata_options_nbbo.py",
        },
        "command_groups": groups,
        "exact_contract_manifest": manifest,
        "unparsed_quote_demands": unparsed,
        "next_evidence_queue": next_queue,
        "evidence_boundary": {
            "readback_is": "read-only import/query coordination for minute-level exact OPRA/NBBO exit quote coverage",
            "readback_is_not": "minute-exit P&L, stop-policy permission, broker action, trading-row DB mutation, or production proof",
            "operator_rule": "Import commands collect quote evidence only; true minute-exit P&L requires a replay engine and exact quotes before any stop or promotion discussion.",
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
        "# Regular Options Minute-Exit Quote Import Plan",
        "",
        "This report is generated from `scripts/build_regular_options_minute_exit_quote_import_plan.py`. It is a read-only import/query plan for exact OPRA/NBBO minute quote coverage needed before minute-level exit replay.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Source readiness: `{summary.get('source_readiness_status')}` / `{summary.get('source_overall_status')}`.",
        f"- Source entry / position seeds: `{summary.get('source_entry_seed_ready_count')}` / `{summary.get('source_position_seed_ready_count')}`.",
        f"- Exact quote demands: `{summary.get('exact_contract_manifest_count')}` parsed, `{summary.get('unparsed_quote_demand_count')}` unparsed.",
        f"- Command groups: `{summary.get('command_group_count')}`.",
        f"- Dates: `{_json_inline(summary.get('quote_dates') or [])}`.",
        f"- Underlyings: `{_json_inline(summary.get('underlyings') or [])}`.",
        f"- Replay P&L status: `{summary.get('replay_pnl_status')}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Command Groups",
        "",
        "| Group | Priority | Date | Right | Symbols | Time Window | DTE | Demands | Seeds | Contracts |",
        "|---|---:|---|---|---|---|---|---:|---:|---:|",
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
                    _cell(group.get("right")),
                    _cell(",".join(str(item) for item in _as_list(group.get("symbols")))),
                    _cell(f"{group.get('start_time_et')} to {group.get('end_time_et')}"),
                    _cell(f"{group.get('min_dte')} to {group.get('max_dte')}"),
                    _cell(group.get("demand_count")),
                    _cell(group.get("seed_count")),
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
            "| Priority | Contract | Date | Window | Leg | Replay Eligibility | Ticker | Lane |",
            "|---:|---|---|---|---|---|---|---|",
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
                    _cell(f"{demand.get('start_time_et')} to {demand.get('end_time_et')}"),
                    _cell(demand.get("leg_role")),
                    _cell(demand.get("replay_eligibility")),
                    _cell(demand.get("ticker")),
                    _cell(demand.get("lane")),
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
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This plan is read-only. It does not create trades, submit broker orders, mutate trading-row DB state, change scanner policy, change stops, change sizing, synthesize minute-exit P&L, lower exact OPRA/NBBO proof bars, or promote quote-import rows to production proof.",
            "",
        ]
    )
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
    parser = argparse.ArgumentParser(description="Build a read-only minute-exit quote import plan.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
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
        readiness_path=args.readiness,
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
